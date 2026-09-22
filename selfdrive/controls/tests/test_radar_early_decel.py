"""D-022 radar ACC pressure: native MPC data-flow and isolation tests."""
import inspect
from types import SimpleNamespace

import numpy as np
import pytest
from cereal import log
from opendbc.car.interfaces import ACCEL_MIN, ACCEL_MAX

from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib import long_mpc


SEED_GAIN = 0.09
SEED_CAP = 0.6


def lead(*, distance=80., speed=0., status=True, radar=True, track_id=1):
  return SimpleNamespace(status=status, radar=radar, radarTrackId=track_id,
                         dRel=distance, vLead=speed, aLeadK=0., aLeadTau=1.5,
                         modelProb=0., vRel=speed - 20.)


def radar_state(one=None, two=None):
  absent = lead(status=False, radar=False, track_id=-1)
  return SimpleNamespace(leadOne=one or absent, leadTwo=two or absent)


class NativeSolverSpy:
  """Capture MPC inputs at solve(), then call the real generated solver."""

  def __init__(self, solver):
    self.solver = solver
    self.params = {}
    self.weights = {}
    self.frames = []
    self.resets = 0

  def set(self, stage, field, value):
    if field == 'p':
      self.params[stage] = np.array(value, copy=True)
    return self.solver.set(stage, field, value)

  def cost_set(self, stage, field, value):
    if field == 'W':
      self.weights[stage] = np.array(value, copy=True)
    return self.solver.cost_set(stage, field, value)

  def reset(self, *args, **kwargs):
    self.resets += 1
    return self.solver.reset(*args, **kwargs)

  def solve(self):
    frame = inspect.currentframe()
    try:
      update_frame = frame.f_back.f_back
      columns = np.array(update_frame.f_locals['x_obstacles'], copy=True)
    finally:
      del frame
    status = self.solver.solve()
    self.frames.append({'columns': columns,
                        'p': np.array([self.params[i] for i in range(long_mpc.N + 1)]),
                        'W': [self.weights[i].copy() for i in range(long_mpc.N + 1)],
                        'status': status})
    return status

  def __getattr__(self, name):
    return getattr(self.solver, name)


def make_mpc(mode='acc', ego=20.):
  mpc = long_mpc.LongitudinalMpc(mode=mode)
  spy = NativeSolverSpy(mpc.solver)
  mpc.solver = spy
  mpc.set_cur_state(ego, 0.)
  mpc.set_weights(personality=log.LongitudinalPersonality.standard)
  return mpc, spy


def frame(mpc, spy, state, *, cruise=30.):
  x = 20. * long_mpc.T_IDXS
  v = np.full(long_mpc.N + 1, 20.)
  a = np.zeros(long_mpc.N + 1)
  j = np.zeros(long_mpc.N + 1)
  mpc.update(state, cruise, x.copy(), v.copy(), a.copy(), j.copy())
  result = spy.frames[-1]
  result['source'] = mpc.source
  result['v'] = mpc.v_solution.copy()
  result['a'] = mpc.a_solution.copy()
  result['j'] = mpc.j_solution.copy()
  return result


def base_obstacle(mpc, lead_value):
  trajectory = mpc.process_lead(lead_value)
  return trajectory[:, 0] + long_mpc.get_stopped_equivalence_factor(trajectory[:, 1], mpc.x0[1])


def expected_pressure(ego, lead_value):
  if not (lead_value.status and lead_value.radar and lead_value.radarTrackId >= 0):
    return 0.
  return min(SEED_CAP, SEED_GAIN * max(ego - lead_value.vLead, 0.))


@pytest.mark.parametrize(('ego', 'speed', 'expected'), [
  (20., 25., 0.), (20., 20., 0.), (20., 18., 0.18), (20., 0., 0.6),
])
def test_bench_seed_pressure_formula(ego, speed, expected):
  assert long_mpc.get_early_decel_pressure(ego, lead(speed=speed)) == pytest.approx(expected)


@pytest.mark.parametrize(('status', 'radar', 'track_id'), [
  (False, True, 1), (True, False, 1), (True, True, -1), (False, False, -1),
])
def test_ineligible_lead_has_no_pressure(status, radar, track_id):
  assert long_mpc.get_early_decel_pressure(
    20., lead(status=status, radar=radar, track_id=track_id)) == 0.


@pytest.mark.parametrize(('speed_one', 'speed_two'), [(0., 22.), (22., 0.), (17., 14.)])
def test_each_real_lead_receives_independent_whole_horizon_pressure(speed_one, speed_two):
  one = lead(distance=80., speed=speed_one, track_id=1)
  two = lead(distance=90., speed=speed_two, track_id=2)
  mpc, spy = make_mpc()
  bases = [base_obstacle(mpc, item) for item in (one, two)]
  observed = frame(mpc, spy, radar_state(one, two))
  assert observed['status'] == mpc.solution_status == 0
  for index, item in enumerate((one, two)):
    np.testing.assert_allclose(observed['columns'][:, index],
                               bases[index] - expected_pressure(20., item), rtol=0, atol=1e-10)
  np.testing.assert_allclose(observed['p'][:, 2], np.min(observed['columns'], axis=1))
  assert spy.resets == 0


@pytest.mark.parametrize(('status', 'radar', 'track_id'), [
  (False, False, -1), (True, False, -1), (True, True, -1),
])
def test_synthetic_and_vision_leads_preserve_native_baseline(monkeypatch, status, radar, track_id):
  candidate = lead(status=status, radar=radar, track_id=track_id)
  mpc, spy = make_mpc()
  base = base_obstacle(mpc, candidate)
  observed = frame(mpc, spy, radar_state(candidate))
  np.testing.assert_array_equal(observed['columns'][:, 0], base)
  mpc_zero, spy_zero = make_mpc()
  monkeypatch.setattr(long_mpc, 'get_early_decel_pressure', lambda _ego, _lead: 0.)
  baseline = frame(mpc_zero, spy_zero, radar_state(candidate))
  np.testing.assert_array_equal(observed['columns'], baseline['columns'])
  np.testing.assert_array_equal(observed['p'], baseline['p'])
  for field in ('v', 'a', 'j'):
    np.testing.assert_array_equal(observed[field], baseline[field])
  assert observed['status'] == baseline['status'] == 0


def test_valid_radar_lead_changes_solver_facing_obstacle_only(monkeypatch):
  candidate = lead(distance=80., speed=0.)
  mpc, spy = make_mpc()
  base = base_obstacle(mpc, candidate)
  observed = frame(mpc, spy, radar_state(candidate))
  np.testing.assert_allclose(observed['columns'][:, 0], base - SEED_CAP, rtol=0, atol=1e-10)
  np.testing.assert_allclose(observed['p'][:, 2], np.min(observed['columns'], axis=1))
  np.testing.assert_array_equal(observed['p'][:, 0], ACCEL_MIN)
  np.testing.assert_array_equal(observed['p'][:, 1], ACCEL_MAX)
  np.testing.assert_array_equal(observed['p'][:, 4], long_mpc.get_T_FOLLOW())
  np.testing.assert_array_equal(observed['p'][:, 6], long_mpc.get_STOP_DISTANCE())
  np.testing.assert_allclose(observed['columns'][:, 2],
                             np.cumsum(long_mpc.T_DIFFS * np.clip(
                               30. * np.ones(long_mpc.N + 1),
                               20. + long_mpc.T_IDXS * long_mpc.CRUISE_MIN_ACCEL * 1.05,
                               20. + long_mpc.T_IDXS * long_mpc.CRUISE_MAX_ACCEL * 1.05))
                             + long_mpc.get_safe_obstacle_distance(
                               np.clip(30. * np.ones(long_mpc.N + 1),
                                       20. + long_mpc.T_IDXS * long_mpc.CRUISE_MIN_ACCEL * 1.05,
                                       20. + long_mpc.T_IDXS * long_mpc.CRUISE_MAX_ACCEL * 1.05),
                               long_mpc.get_T_FOLLOW(), long_mpc.get_STOP_DISTANCE()))
  np.testing.assert_allclose(np.diag(observed['W'][0])[4:6], [200., 5.])
  mpc_zero, spy_zero = make_mpc()
  monkeypatch.setattr(long_mpc, 'get_early_decel_pressure', lambda _ego, _lead: 0.)
  baseline = frame(mpc_zero, spy_zero, radar_state(candidate))
  np.testing.assert_array_equal(observed['columns'][:, 1:], baseline['columns'][:, 1:])
  np.testing.assert_allclose(observed['p'][:, 2], baseline['p'][:, 2] - SEED_CAP, rtol=0, atol=1e-10)
  for column in (0, 1, 3, 4, 5, 6):
    np.testing.assert_array_equal(observed['p'][:, column], baseline['p'][:, column])
  for actual, expected in zip(observed['W'], baseline['W'], strict=True):
    np.testing.assert_array_equal(actual, expected)


def test_zero_pressure_matches_unmodified_native_geometry_and_raw_output(monkeypatch):
  candidate = lead(distance=80., speed=20.)
  mpc, spy = make_mpc()
  observed = frame(mpc, spy, radar_state(candidate))
  mpc_zero, spy_zero = make_mpc()
  monkeypatch.setattr(long_mpc, 'get_early_decel_pressure', lambda _ego, _lead: 0.)
  baseline = frame(mpc_zero, spy_zero, radar_state(candidate))
  np.testing.assert_array_equal(observed['columns'], baseline['columns'])
  np.testing.assert_array_equal(observed['p'], baseline['p'])
  for actual, expected in zip(observed['W'], baseline['W'], strict=True):
    np.testing.assert_array_equal(actual, expected)
  for key in ('v', 'a', 'j'):
    np.testing.assert_array_equal(observed[key], baseline[key])
  assert observed['status'] == baseline['status'] == 0


def test_pull_away_frozen_geometry_unchanged():
  candidate = lead(distance=80., speed=25.)
  mpc, spy = make_mpc()
  base = base_obstacle(mpc, candidate)
  observed = frame(mpc, spy, radar_state(candidate))
  np.testing.assert_array_equal(observed['columns'][:, 0], base)
  assert long_mpc.get_early_decel_pressure(20., candidate) == 0.


def test_blended_mode_has_no_pressure_even_for_valid_closing_lead(monkeypatch):
  candidate = lead(distance=80., speed=0.)
  mpc, spy = make_mpc(mode='blended')
  observed = frame(mpc, spy, radar_state(candidate))
  mpc_zero, spy_zero = make_mpc(mode='blended')
  monkeypatch.setattr(long_mpc, 'get_early_decel_pressure', lambda _ego, _lead: 0.)
  baseline = frame(mpc_zero, spy_zero, radar_state(candidate))
  np.testing.assert_array_equal(observed['columns'], baseline['columns'])
  np.testing.assert_array_equal(observed['p'], baseline['p'])
  for actual, expected in zip(observed['W'], baseline['W'], strict=True):
    np.testing.assert_array_equal(actual, expected)
  for key in ('v', 'a', 'j'):
    np.testing.assert_array_equal(observed[key], baseline[key])
  assert observed['status'] == baseline['status'] == 0.


@pytest.mark.parametrize(('distance', 'speed'), [(80., 0.), (50., 12.)])
def test_native_cut_in_frames_are_finite_without_reset(distance, speed):
  mpc, spy = make_mpc()
  frames = [
    frame(mpc, spy, radar_state()),
    frame(mpc, spy, radar_state(lead(distance=distance, speed=speed))),
    frame(mpc, spy, radar_state(lead(distance=distance - 2., speed=speed))),
  ]
  for observed in frames:
    assert observed['status'] == 0
    assert np.all(np.isfinite(observed['p']))
    for field in ('v', 'a', 'j'):
      assert np.all(np.isfinite(observed[field]))
  assert spy.resets == 0
