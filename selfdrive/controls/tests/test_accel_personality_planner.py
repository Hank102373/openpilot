"""PORT-03 planner/native integration; D-009 TOP01003 maximum curves only."""
import inspect
import json
from types import SimpleNamespace

import numpy as np
import pytest
from cereal import log

from dragonpilot.selfdrive.controls.lib import aem, acm
from openpilot.selfdrive.controls.lib import longitudinal_planner as lp
from openpilot.selfdrive.controls.lib.accel_personality import AccelProfile
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import N, T_IDXS, get_STOP_DISTANCE
from openpilot.selfdrive.controls.tests.test_dtsc_bounds import make_messages
from openpilot.selfdrive.controls.tests.test_longitudinal_mode import NativeModeSpy, capture_weight_inputs, expected_d021_weights
from openpilot.selfdrive.controls.tests.test_dynamic_follow import donor_at_speed
from openpilot.selfdrive.modeld.constants import ModelConstants


@pytest.fixture
def turn_calls(monkeypatch):
  calls = []
  original = lp.limit_accel_in_turns

  def observe(speed, angle, bounds, cp):
    result = original(speed, angle, bounds, cp)
    calls.append((speed, list(bounds), list(result)))
    return result

  monkeypatch.setattr(lp, 'limit_accel_in_turns', observe)
  return calls


def setup(profile=AccelProfile.stock, speed=20., longitudinal=True, dynamic=False, default=False):
  cp = SimpleNamespace(openpilotLongitudinalControl=longitudinal, steerRatio=15., wheelbase=2.7,
                       longitudinalActuatorDelay=.2, vEgoStopping=.25)
  kwargs = dict(init_v=speed, dynamic_follow_active=dynamic)
  # Before integration, execute the real baseline planner without inventing a
  # profile field. This permits a numerical failure before the API exists.
  if not default and 'accel_profile' in inspect.signature(lp.LongitudinalPlanner).parameters:
    kwargs['accel_profile'] = profile
  planner = lp.LongitudinalPlanner(cp, **kwargs)
  planner.maa_helper = None
  spy = NativeModeSpy(planner)
  planner.mpc.solver = spy
  sm = make_messages()
  set_speed(sm, speed)
  return planner, spy, sm


def set_speed(sm, speed):
  t = np.asarray(ModelConstants.T_IDXS)
  sm['carState'].vEgo = speed
  sm['modelV2'].position.x = (speed * t).tolist()
  sm['modelV2'].velocity.x = np.full(len(t), speed).tolist()
  sm['modelV2'].acceleration.x = np.zeros(len(t)).tolist()
  sm['modelV2'].orientationRate.z = np.zeros(len(t)).tolist()
  sm['modelV2'].orientation = SimpleNamespace(x=np.zeros(len(t)).tolist())


def run(planner, spy, sm, flags=0):
  planner.update(sm, flags)
  frame = spy.frames[-1]
  assert frame['native_status'] == planner.mpc.solution_status == 0
  assert spy.resets == 0
  assert frame['p'].shape == (N + 1, 7)
  assert all(np.all(np.isfinite(x)) for x in [frame['p'], planner.mpc.v_solution,
                                            planner.mpc.a_solution, planner.mpc.j_solution])
  print('A2_NATIVE ' + json.dumps({'native_status': frame['native_status'],
                                  'solution_status': planner.mpc.solution_status,
                                  'finite_params_v_a_j': True, 'resets': spy.resets,
                                  'mode': frame['mpc_mode'], 'output': float(planner.output_a_target)}))
  return frame


def test_donor_upper_reaches_planner(turn_calls):
  planner, spy, sm = setup(AccelProfile.eco)
  run(planner, spy, sm)
  assert turn_calls[-1][1][1] == pytest.approx(.36, rel=0, abs=1e-12)


@pytest.mark.parametrize(('speed', 'expected'), [
  (0., [2., 2., 2., 1.6]),
  (5., [1.8388888888888888, 1.6088888888888886, .961111111111111, 1.4]),
  (20., [.71, .54, .36, .9333333333333333]),
  (40., [.3793599999999999, .27935999999999994, .15248, .6]),
])
@pytest.mark.parametrize('profile', list(AccelProfile))
def test_raw_upper_and_default_solver_bounds(turn_calls, speed, expected, profile):
  planner, spy, sm = setup(profile, speed)
  frame = run(planner, spy, sm)
  assert turn_calls[-1][0] == speed
  np.testing.assert_allclose(turn_calls[-1][1], [-3.5, expected[int(profile)]], rtol=0, atol=1e-12)
  assert turn_calls[-1][2][1] <= turn_calls[-1][1][1]
  np.testing.assert_array_equal(frame['p'][:, :2], np.tile([-3.5, 2.], (N + 1, 1)))


def test_stock_equals_default(turn_calls):
  explicit, spy1, sm1 = setup()
  default, spy2, sm2 = setup(default=True)
  first = run(explicit, spy1, sm1)
  second = run(default, spy2, sm2)
  for field in ['p', 'W', 'yref']:
    for a, b in zip(first[field], second[field], strict=True):
      np.testing.assert_array_equal(a, b)
  assert explicit.output_a_target == default.output_a_target
  np.testing.assert_array_equal(explicit.mpc.a_solution, default.mpc.a_solution)


@pytest.mark.parametrize('profile', list(AccelProfile))
def test_blended_does_not_use_profile_upper(turn_calls, profile):
  planner, spy, sm = setup(profile)
  sm['selfdriveState'].experimentalMode = True
  frame = run(planner, spy, sm)
  assert not turn_calls
  assert frame['planner_mode'] == frame['mpc_mode'] == 'blended'
  np.testing.assert_array_equal(planner.prev_accel_clip, [-3.5, 2.])
  np.testing.assert_array_equal(frame['p'][:, :2], np.tile([-3.5, 2.], (N + 1, 1)))


@pytest.mark.parametrize('profile', [AccelProfile.stock, AccelProfile.eco])
@pytest.mark.parametrize('transition', ['experimental', 'aem'])
def test_final_mode_transitions(monkeypatch, turn_calls, profile, transition):
  planner, spy, sm = setup(profile)
  weight_calls = capture_weight_inputs(monkeypatch, planner.mpc)
  clock = [100.]
  monkeypatch.setattr(aem, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
  t = np.asarray(ModelConstants.T_IDXS)
  flags = lp.DPFlags.AEM if transition == 'aem' else 0
  for index, mode in enumerate(['acc', 'blended', 'acc']):
    clock[0] = 100. + index
    sm['selfdriveState'].experimentalMode = transition == 'experimental' and index == 1
    stopping = transition == 'aem' and index == 1
    sm['modelV2'].position.x = (20 * t - 1.25 * t**2 if stopping else 20 * t).tolist()
    sm['modelV2'].velocity.x = (20 - 2.5 * t if stopping else np.full(len(t), 20.)).tolist()
    sm['modelV2'].acceleration.x = np.full(len(t), -2.5 if stopping else 0.).tolist()
    frame = run(planner, spy, sm, flags)
    assert frame['planner_mode'] == frame['mpc_mode'] == mode
    assert planner.accel_profile is profile
    if transition == 'aem':
      assert planner.aem._active == (index == 1)
    blended = mode == 'blended'
    weights = expected_d021_weights(weight_calls[-1], mode)
    for stage in range(N + 1):
      expected = weights.copy()
      expected[4] *= np.interp(T_IDXS[min(stage, N - 1)], [0, 1, 2], [1, 1, 0])
      np.testing.assert_allclose(frame['W'][stage], np.diag(expected[:5] if stage == N else expected))
    np.testing.assert_array_equal(frame['p'][:, 5], 1. if blended else .75)
    yref = np.array([r[:4] for r in frame['yref']])
    if blended:
      v = np.interp(T_IDXS, t, sm['modelV2'].velocity.x)
      x = np.cumsum(np.insert((v[1:] + v[:-1]) / 2 * np.diff(T_IDXS), 0, 0))
      np.testing.assert_allclose(yref[:, 1], x)
      np.testing.assert_allclose(yref[:, 2], v)
      np.testing.assert_allclose(yref[:, 3], -2.5 if stopping else 0.)
    else:
      np.testing.assert_array_equal(yref, 0)
      assert turn_calls[-1][1][1] == pytest.approx(.36 if profile == AccelProfile.eco else 14/15)


@pytest.mark.parametrize('profile', [AccelProfile.stock, AccelProfile.eco])
def test_dtsc_intersection_and_off_restoration(profile):
  planner, spy, sm = setup(profile)
  calls = []
  original = planner.dtsc.get_mpc_constraints

  def capture(*args):
    lo, hi = original(*args)
    calls.append((args[2], args[3], lo.copy(), hi.copy()))
    return lo, hi

  planner.dtsc.get_mpc_constraints = capture
  for enabled, curve in [(False, False), (True, False), (True, True), (False, True)]:
    sm['modelV2'].orientationRate.z = (np.linspace(0, .4, len(ModelConstants.T_IDXS))
                                     if curve else np.zeros(len(ModelConstants.T_IDXS))).tolist()
    frame = run(planner, spy, sm, lp.DPFlags.DTSC if enabled else 0)
    if enabled:
      base_lo, base_hi, lo, hi = calls[-1]
      assert base_hi == pytest.approx(.36 if profile == AccelProfile.eco else 14/15)
      expected = np.column_stack((np.maximum(base_lo, lo), np.minimum(base_hi, hi)))
      np.testing.assert_allclose(frame['p'][:, :2], expected)
      assert np.all(frame['p'][:, 1] <= base_hi)
      if curve:
        assert planner.dtsc.active
        assert np.any(frame['p'][:, 1] < base_hi)
    else:
      np.testing.assert_array_equal(frame['p'][:, :2], np.tile([-3.5, 2.], (N + 1, 1)))


@pytest.mark.parametrize('dynamic', [False, True])
def test_dynamic_follow_and_apm_independence(turn_calls, dynamic):
  planner, spy, sm = setup(AccelProfile.eco, speed=6., dynamic=dynamic)
  sm['selfdriveState'].personality = log.LongitudinalPersonality.relaxed
  for speed, name in [(6., 'aggressive'), (10., 'aggressive'), (15., 'relaxed')]:
    set_speed(sm, speed)
    frame = run(planner, spy, sm, lp.DPFlags.APM)
    assert planner.accel_profile is AccelProfile.eco
    expected_follow = donor_at_speed(planner.mpc.x0[1], name) if dynamic else (1.25 if name == 'aggressive' else 1.75)
    np.testing.assert_allclose(frame['p'][:, 4], expected_follow)
    np.testing.assert_allclose(frame['p'][:, 6], get_STOP_DISTANCE(getattr(log.LongitudinalPersonality, name)))
    expected_upper = {6.: .75, 10.: .5631481481481482, 15.: .42466666666666664}
    # Independent frozen values below are checked at the exact measured speed.
    assert turn_calls[-1][1][1] == pytest.approx(expected_upper[speed], abs=1e-12)


@pytest.mark.parametrize('profile', [AccelProfile.stock, AccelProfile.eco])
@pytest.mark.parametrize('moving', [False, True])
def test_pull_away_obstacles_preserved(profile, moving):
  planner, spy, sm = setup(profile, speed=0.)
  speed = 1. if moving else 0.
  sm['radarState'].leadOne = SimpleNamespace(status=True, dRel=2., vLead=speed, aLeadK=0.,
                                           aLeadTau=1.5, modelProb=0., vRel=speed)
  frame = run(planner, spy, sm)
  expected = 2 + speed * T_IDXS + (2.2 if moving else 0.)
  np.testing.assert_allclose(frame['obstacles'][:, 0], expected)
  np.testing.assert_allclose(frame['p'][:, 2], frame['obstacles'].min(axis=1))


def test_acm_stays_after_mpc(monkeypatch, turn_calls):
  planner, spy, sm = setup(AccelProfile.eco)
  planner.acm.enabled = True
  sm['carControl'].orientationNED = [0., 0., 0.]
  sm['carState'].vCruise = 70.
  monkeypatch.setattr(acm, 'time', SimpleNamespace(monotonic=lambda: 1000.))
  calls = []
  original = planner.acm.update_a_desired_trajectory

  def observe(trajectory):
    assert len(spy.frames) == 1
    before = trajectory.copy()
    after = original(trajectory)
    calls.append((before, after.copy()))
    return after

  planner.acm.update_a_desired_trajectory = observe
  run(planner, spy, sm, lp.DPFlags.ACM)
  assert turn_calls[-1][1][1] == pytest.approx(.36)
  assert planner.acm.active
  before, after = calls[0]
  assert np.any((before > -1.) & (before < 0.))
  np.testing.assert_array_equal(after, np.where((before > -1.) & (before < 0.), 0., before))
  np.testing.assert_array_equal(planner.a_desired_trajectory, after)


def test_dasr_limits_final_bounds_history(turn_calls):
  planner, spy, sm = setup(AccelProfile.eco, speed=5.)
  for expected_upper in [1.85, 1.70]:
    run(planner, spy, sm, lp.DPFlags.DASR)
    assert turn_calls[-1][1][1] == pytest.approx(.961111111111111)
    assert planner.dasr.slew_rate == pytest.approx(.15)
    assert planner.prev_accel_clip[1] == pytest.approx(expected_upper)
    assert planner.output_a_target <= expected_upper
  assert planner.accel_profile is AccelProfile.eco


@pytest.mark.parametrize('profile', list(AccelProfile))
def test_stock_long_bypass(turn_calls, profile):
  planner, spy, sm = setup(profile, longitudinal=False)
  frame = run(planner, spy, sm)
  assert turn_calls[-1][1][1] == pytest.approx(14/15)
  np.testing.assert_array_equal(frame['p'][:, :2], np.tile([-3.5, 2.], (N + 1, 1)))


def test_planner_profile_read_only():
  planner, _, _ = setup(AccelProfile.eco)
  assert planner.accel_profile is AccelProfile.eco
  with pytest.raises(AttributeError):
    planner.accel_profile = AccelProfile.sport


@pytest.mark.parametrize('profile', [None, True, 'eco', 1.0, -1, 4])
def test_invalid_planner_profile_rejected(profile):
  cp = SimpleNamespace(openpilotLongitudinalControl=True)
  with pytest.raises((TypeError, ValueError), match='profile'):
    lp.LongitudinalPlanner(cp, accel_profile=profile)
