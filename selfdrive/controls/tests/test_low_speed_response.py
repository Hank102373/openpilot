"""F-005 exact TOP01003 low-speed responsiveness contract (D-021)."""
from types import SimpleNamespace

import numpy as np
import pytest
from cereal import log
from opendbc.car.interfaces import ACCEL_MAX, ACCEL_MIN

from openpilot.selfdrive.controls.lib import longitudinal_planner as lp
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib import long_mpc
from openpilot.selfdrive.controls.tests.test_dtsc_bounds import make_messages
from openpilot.selfdrive.modeld.constants import ModelConstants


PERSONALITIES = {
  'relaxed': log.LongitudinalPersonality.relaxed,
  'standard': log.LongitudinalPersonality.standard,
  'aggressive': log.LongitudinalPersonality.aggressive,
}


class NativeSpy:
  def __init__(self, solver):
    self.solver = solver
    self.values = {}
    self.resets = 0

  def set(self, stage, field, value):
    self.values[stage, field] = np.array(value, copy=True)
    return self.solver.set(stage, field, value)

  def cost_set(self, stage, field, value):
    self.values[stage, field] = np.array(value, copy=True)
    return self.solver.cost_set(stage, field, value)

  def reset(self, *args, **kwargs):
    self.resets += 1
    return self.solver.reset(*args, **kwargs)

  def __getattr__(self, name):
    return getattr(self.solver, name)


def lead(speed=0., distance=20., valid=True):
  return SimpleNamespace(status=valid, dRel=distance, vLead=speed, aLeadK=0.,
                         aLeadTau=1.5, modelProb=0., vRel=speed)


def radar(one=None, two=None):
  return SimpleNamespace(leadOne=one if one is not None else lead(valid=False),
                         leadTwo=two if two is not None else lead(valid=False))


def mpc_at(speed, mode='acc'):
  mpc = long_mpc.LongitudinalMpc(mode=mode)
  spy = NativeSpy(mpc.solver)
  mpc.solver = spy
  mpc.set_cur_state(speed, 0.)
  return mpc, spy


def processed(mpc, leads):
  return (float(mpc.process_lead(leads.leadOne)[0, 1]),
          float(mpc.process_lead(leads.leadTwo)[0, 1]))


def weight_vector(spy, stage=0):
  return np.diag(spy.values[stage, 'W'])


@pytest.mark.parametrize(('name', 'expected'), [
  ('relaxed', 1.0), ('standard', 1.0), ('aggressive', 0.45),
])
def test_exact_donor_jerk_factors(name, expected):
  assert long_mpc.get_jerk_factor(PERSONALITIES[name]) == expected


@pytest.mark.parametrize(('speed', 'expected_scale'), [(0., .9), (5., .95), (10., 1.), (15., 1.)])
@pytest.mark.parametrize(('name', 'factor'), [('relaxed', 1.), ('standard', 1.), ('aggressive', .45)])
def test_acc_exact_costs_and_horizon(name, factor, speed, expected_scale):
  mpc, spy = mpc_at(speed)
  v0, v1 = processed(mpc, radar())
  assert (v0, v1) == (speed + 10, speed + 10)
  mpc.set_weights(personality=PERSONALITIES[name], v_lead0=v0, v_lead1=v1)
  np.testing.assert_allclose(weight_vector(spy), [3., 0., 0., 0., factor * 200 * expected_scale,
                                                   factor * 5 * expected_scale], rtol=0, atol=1e-12)
  for stage in range(long_mpc.N):
    decay = np.interp(long_mpc.T_IDXS[stage], [0., 1., 2.], [1., 1., 0.])
    assert weight_vector(spy, stage)[4] == pytest.approx(factor * 200 * expected_scale * decay, abs=1e-12)


@pytest.mark.parametrize(('case', 'speed', 'one', 'two', 'expected_processed', 'gate'), [
  ('none', 2., None, None, (12., 12.), True),
  ('both_same', 2., (2., True), (2., True), (2., 2.), True),
  ('both_faster', 2., (4., True), (4., True), (4., 4.), True),
  ('one_faster', 2., (4., True), None, (4., 12.), True),
  ('two_faster', 2., None, (4., True), (12., 4.), True),
  ('one_slower', 2., (1., True), None, (1., 12.), False),
  ('two_slower', 2., None, (1., True), (12., 1.), False),
  ('both_slower', 2., (1., True), (1., True), (1., 1.), False),
  ('zero_clipped_one', 0., (-1., True), None, (0., 10.), True),
  ('zero_clipped_two', 0., None, (-1., True), (10., 0.), True),
])
def test_processed_lead_gate(case, speed, one, two, expected_processed, gate):
  mpc, spy = mpc_at(speed)
  leads = radar(lead(one[0], valid=one[1]) if one else None, lead(two[0], valid=two[1]) if two else None)
  v0, v1 = processed(mpc, leads)
  assert (v0, v1) == expected_processed
  mpc.set_weights(personality=PERSONALITIES['standard'], v_lead0=v0, v_lead1=v1)
  scale = float(np.interp(speed, [0., 10.], [.9, 1.])) if gate else 1.
  np.testing.assert_allclose(weight_vector(spy)[4:6], [200 * scale, 5 * scale], rtol=0, atol=1e-12)


def test_gate_transitions_have_no_stale_weight():
  mpc, spy = mpc_at(2.)
  for leads, expected in [(radar(), (184., 4.6)),
                          (radar(lead(1.), None), (200., 5.)),
                          (radar(lead(4.), lead(4.)), (184., 4.6)),
                          (radar(), (184., 4.6))]:
    v0, v1 = processed(mpc, leads)
    mpc.set_weights(v_lead0=v0, v_lead1=v1)
    np.testing.assert_allclose(weight_vector(spy)[4:6], expected, rtol=0, atol=1e-12)


def test_disabled_previous_accel_constraint_and_compatibility_default():
  mpc, spy = mpc_at(0.)
  mpc.set_weights(False, personality=PERSONALITIES['aggressive'], v_lead0=10., v_lead1=10.)
  np.testing.assert_allclose(weight_vector(spy)[4:6], [0., 2.025], rtol=0, atol=1e-12)
  # Existing callers without lead arguments must retain the baseline cost.
  mpc.set_weights(personality=PERSONALITIES['aggressive'])
  np.testing.assert_allclose(weight_vector(spy)[4:6], [90., 2.25], rtol=0, atol=1e-12)


@pytest.mark.parametrize('previous', [False, True])
def test_blended_weights_unchanged(previous):
  mpc, spy = mpc_at(0., mode='blended')
  mpc.set_weights(previous, personality=PERSONALITIES['aggressive'], v_lead0=10., v_lead1=10.)
  np.testing.assert_allclose(weight_vector(spy), [0., .1, .2, 5., 40. if previous else 0., 1.], rtol=0, atol=0)


def test_planner_processed_leads_and_effective_apm(monkeypatch):
  cp = SimpleNamespace(openpilotLongitudinalControl=True, steerRatio=15., wheelbase=2.7,
                       longitudinalActuatorDelay=.2, vEgoStopping=.25)
  planner = lp.LongitudinalPlanner(cp, init_v=6.)
  planner.maa_helper = None
  spy = NativeSpy(planner.mpc.solver)
  planner.mpc.solver = spy
  sm = make_messages()
  sm['carState'].vEgo = 6.
  sm['selfdriveState'].personality = PERSONALITIES['relaxed']
  sm['radarState'] = radar(lead(8.), None)
  t = np.asarray(ModelConstants.T_IDXS)
  sm['modelV2'].position.x = (6 * t).tolist()
  sm['modelV2'].velocity.x = np.full(len(t), 6.).tolist()
  sm['modelV2'].acceleration.x = np.zeros(len(t)).tolist()
  sm['modelV2'].orientationRate.z = np.zeros(len(t)).tolist()
  calls = {}
  original_weights = planner.mpc.set_weights
  original_update = planner.mpc.update

  def capture_weights(*args, **kwargs):
    calls['weights'] = (args, kwargs)
    return original_weights(*args, **kwargs)

  def capture_update(*args, **kwargs):
    calls['update'] = (args, kwargs)
    return original_update(*args, **kwargs)

  monkeypatch.setattr(planner.mpc, 'set_weights', capture_weights)
  monkeypatch.setattr(planner.mpc, 'update', capture_update)
  planner.update(sm, lp.DPFlags.APM)
  assert planner.apm._active
  assert calls['weights'][1]['personality'] == calls['update'][1]['personality'] == PERSONALITIES['aggressive']
  assert calls['weights'][1]['v_lead0'] == pytest.approx(8.)
  assert calls['weights'][1]['v_lead1'] == pytest.approx(10.)  # MPC x0 is updated after donor-style preprocessing.
  assert planner.mpc.solution_status == 0
  assert spy.resets == 0


@pytest.mark.parametrize(('name', 'speed', 'leads', 'expected_a1', 'expected_j0'), [
  ('stopped_no_lead', 0., radar(), .032822, .472635),
  ('stopped_pull_away', 0., radar(lead(1., 4.), None), .010540, .151781),
  ('ego2_faster', 2., radar(lead(4.), lead(4.)), .023935, .344659),
  ('ego5_faster', 5., radar(lead(7.), lead(7.)), .020064, .288926),
  ('ego5_slower', 5., radar(lead(4.), lead(4.)), .005887, .084772),
])
def test_native_focused_scenarios(name, speed, leads, expected_a1, expected_j0):
  mpc, spy = mpc_at(speed)
  v0, v1 = processed(mpc, leads)
  mpc.set_weights(personality=PERSONALITIES['aggressive'], v_lead0=v0, v_lead1=v1)
  x = speed * long_mpc.T_IDXS.copy()
  v = np.full(long_mpc.N + 1, speed)
  a = np.zeros(long_mpc.N + 1)
  j = np.zeros(long_mpc.N + 1)
  mpc.update(leads, 12. if speed == 5. else 10., x, v, a, j,
             personality=PERSONALITIES['aggressive'])
  params = np.array([spy.values[i, 'p'] for i in range(long_mpc.N + 1)])
  assert long_mpc.PARAM_DIM == 7
  assert params.shape == (long_mpc.N + 1, 7)
  np.testing.assert_allclose(params[:, :2], np.tile([ACCEL_MIN, ACCEL_MAX], (long_mpc.N + 1, 1)))
  np.testing.assert_allclose(params[:, 6], long_mpc.get_STOP_DISTANCE(PERSONALITIES['aggressive']))
  assert mpc.solution_status == 0
  assert spy.resets == 0
  assert all(np.all(np.isfinite(z)) for z in [params, mpc.v_solution, mpc.a_solution, mpc.j_solution])
  assert mpc.a_solution[1] == pytest.approx(expected_a1, abs=2e-5)
  assert mpc.j_solution[0] == pytest.approx(expected_j0, abs=2e-5)
  print(name, 'status', mpc.solution_status, 'a1', float(mpc.a_solution[1]), 'j0', float(mpc.j_solution[0]))


def test_low_speed_planner_dasr_trace(monkeypatch):
  cp = SimpleNamespace(openpilotLongitudinalControl=True, steerRatio=15., wheelbase=2.7,
                       longitudinalActuatorDelay=.2, vEgoStopping=.25)
  planner = lp.LongitudinalPlanner(cp, init_v=.5)
  planner.maa_helper = None
  sm = make_messages()
  sm['selfdriveState'].personality = PERSONALITIES['aggressive']
  sm['carState'].vCruise = 80.
  sm['carState'].standstill = False
  original = lp.get_accel_from_plan
  raw = []

  def capture(*args, **kwargs):
    result = original(*args, **kwargs)
    raw.append(float(result[0]))
    return result

  monkeypatch.setattr(lp, 'get_accel_from_plan', capture)
  v, accel, clipped = .5, 0., 0
  for _ in range(30):
    t = np.asarray(ModelConstants.T_IDXS)
    sm['carState'].vEgo = v
    sm['carState'].aEgo = accel
    sm['modelV2'].position.x = (v * t).tolist()
    sm['modelV2'].velocity.x = np.full(len(t), v).tolist()
    sm['modelV2'].acceleration.x = np.zeros(len(t)).tolist()
    sm['modelV2'].orientationRate.z = np.zeros(len(t)).tolist()
    planner.update(sm, lp.DPFlags.DASR)
    assert planner.mpc.solution_status == 0
    clipped += abs(raw[-1] - planner.output_a_target) > 1e-9
    accel = float(planner.output_a_target)
    v = max(0., v + accel * planner.dt)
  assert clipped == 0
  print('DASR clips', clipped, 'of 30', 'final', accel)
