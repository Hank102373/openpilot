"""F-002 oracle: CT921/openpilot TOP01003 615799f95e978fbf643d1e762d605b4d5b06499f."""
from types import SimpleNamespace

import numpy as np
import pytest
from cereal import log
from opendbc.car.interfaces import ACCEL_MIN, ACCEL_MAX

from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib import long_mpc


PRESETS = {
  log.LongitudinalPersonality.relaxed: 4.5,
  log.LongitudinalPersonality.standard: 4.0,
  log.LongitudinalPersonality.aggressive: 4.0,
}


class NativeParamSpy:
  """Record solver-facing parameters while forwarding to the native solver."""

  def __init__(self, solver):
    self.solver = solver
    self.params = {}
    self.resets = 0
    self.native_statuses = []

  def set(self, stage, field, value):
    if field == 'p':
      self.params[stage] = np.array(value, copy=True)
    return self.solver.set(stage, field, value)

  def reset(self, *args, **kwargs):
    self.resets += 1
    return self.solver.reset(*args, **kwargs)

  def solve(self):
    status = self.solver.solve()
    self.native_statuses.append(status)
    return status

  def __getattr__(self, name):
    return getattr(self.solver, name)


def radar_state():
  lead = SimpleNamespace(status=False, dRel=50.0, vLead=10.0, aLeadK=0.0,
                         aLeadTau=1.5, modelProb=0.0, vRel=10.0)
  return SimpleNamespace(leadOne=lead, leadTwo=lead)


def run_frame(mpc, spy, personality, *, mode='acc', dynamic_follow=False):
  mpc.mode = mode
  mpc.set_weights(personality=personality)
  mpc.set_cur_state(0.0, 0.0)
  spy.params.clear()
  x = np.zeros(long_mpc.N + 1)
  v = np.zeros(long_mpc.N + 1)
  a = np.zeros(long_mpc.N + 1)
  j = np.zeros(long_mpc.N + 1)
  mpc.update(radar_state(), 10.0, x, v, a, j, personality=personality,
             dynamic_follow=dynamic_follow)

  assert set(spy.params) == set(range(long_mpc.N + 1))
  params = np.array([spy.params[stage] for stage in range(long_mpc.N + 1)])
  assert params.shape == (long_mpc.N + 1, 7)
  assert spy.native_statuses[-1] == mpc.solution_status == 0
  assert np.all(np.isfinite(params))
  assert np.all(np.isfinite(mpc.v_solution))
  assert np.all(np.isfinite(mpc.a_solution))
  assert np.all(np.isfinite(mpc.j_solution))
  return params


@pytest.mark.parametrize(('personality', 'expected'), PRESETS.items())
def test_donor_presets(personality, expected):
  assert long_mpc.get_STOP_DISTANCE(personality) == expected


def test_unsupported_personality():
  with pytest.raises(NotImplementedError, match='personality'):
    long_mpc.get_STOP_DISTANCE(99)


def test_stop_distance_parameter_dimension_and_order(monkeypatch):
  from pathlib import Path

  monkeypatch.syspath_prepend(str(Path(long_mpc.__file__).resolve().parents[4] / 'third_party/acados'))
  from openpilot.third_party.acados.acados_template import AcadosModel, AcadosOcp

  monkeypatch.setattr(long_mpc, 'AcadosModel', AcadosModel, raising=False)
  monkeypatch.setattr(long_mpc, 'AcadosOcp', AcadosOcp, raising=False)
  assert long_mpc.PARAM_DIM == 7
  model = long_mpc.gen_long_model()
  assert model.p.shape == (7, 1)
  assert [model.p[index].name() for index in range(7)] == [
    'a_min', 'a_max', 'x_obstacle', 'prev_a', 'lead_t_follow',
    'lead_danger_factor', 'stop_distance',
  ]
  ocp = long_mpc.gen_long_ocp()
  np.testing.assert_allclose(
    ocp.parameter_values,
    [-1.2, 1.2, 0.0, 0.0, long_mpc.get_T_FOLLOW(),
     long_mpc.LEAD_DANGER_FACTOR, 4.0],
  )


@pytest.mark.parametrize('stop_distance', [1.0, 1.5, 2.0, 4.0, 4.5])
def test_distance_oracles(stop_distance):
  t_follow = 1.45
  assert long_mpc.get_safe_obstacle_distance(0.0, t_follow, stop_distance) == stop_distance
  assert long_mpc.desired_follow_distance(0.0, 0.0, t_follow, stop_distance) == stop_distance

  speed = 0.5
  expected = t_follow * speed + stop_distance
  assert long_mpc.desired_follow_distance(speed, speed, t_follow, stop_distance) == pytest.approx(
    expected, rel=0, abs=1e-12,
  )


def test_native_personality_transitions_and_feature_independence():
  mpc = long_mpc.LongitudinalMpc()
  spy = NativeParamSpy(mpc.solver)
  mpc.solver = spy

  frames = []
  for personality in (
    log.LongitudinalPersonality.relaxed,
    log.LongitudinalPersonality.standard,
    log.LongitudinalPersonality.aggressive,
  ):
    params = run_frame(mpc, spy, personality)
    expected = PRESETS[personality]
    np.testing.assert_allclose(params[:, 6], expected)
    np.testing.assert_allclose(params[:, :2], np.tile([ACCEL_MIN, ACCEL_MAX], (long_mpc.N + 1, 1)))
    np.testing.assert_allclose(params[:, 4], long_mpc.get_T_FOLLOW(personality))
    np.testing.assert_allclose(params[:, 5], long_mpc.LEAD_DANGER_FACTOR)
    frames.append(params)

  np.testing.assert_allclose(frames[0][:, 6], 4.5)
  np.testing.assert_allclose(frames[1][:, 6], 4.0)
  np.testing.assert_allclose(frames[2][:, 6], 4.0)

  static = run_frame(mpc, spy, log.LongitudinalPersonality.relaxed, dynamic_follow=False)
  dynamic = run_frame(mpc, spy, log.LongitudinalPersonality.relaxed, dynamic_follow=True)
  assert np.any(static[:, 4] != dynamic[:, 4])
  np.testing.assert_allclose(static[:, 6], 4.5)
  np.testing.assert_allclose(dynamic[:, 6], 4.5)

  blended = run_frame(mpc, spy, log.LongitudinalPersonality.standard, mode='blended')
  np.testing.assert_allclose(blended[:, 5], 1.0)
  np.testing.assert_allclose(blended[:, 6], 4.0)
  assert spy.resets == 0

  mpc.reset()
  assert spy.resets == 1
  assert mpc.params.shape == (long_mpc.N + 1, 7)
  assert mpc.solution_status == 0


@pytest.mark.parametrize(('mode', 'personality', 'expected'), [
  ('acc', log.LongitudinalPersonality.relaxed, 4.5),
  ('blended', log.LongitudinalPersonality.standard, 4.0),
])
def test_acc_and_blended_use_one_effective_stop_distance(monkeypatch, mode, personality, expected):
  calls = []
  original = long_mpc.get_safe_obstacle_distance

  def observe(v_ego, t_follow, stop_distance=None):
    calls.append(stop_distance)
    return original(v_ego, t_follow, stop_distance)

  monkeypatch.setattr(long_mpc, 'get_safe_obstacle_distance', observe)
  mpc = long_mpc.LongitudinalMpc()
  spy = NativeParamSpy(mpc.solver)
  mpc.solver = spy
  params = run_frame(mpc, spy, personality, mode=mode)

  assert calls
  assert all(value == expected for value in calls)
  np.testing.assert_allclose(params[:, 6], expected)
  if mode == 'acc':
    assert params[0, 2] == pytest.approx(expected, rel=0, abs=1e-12)
