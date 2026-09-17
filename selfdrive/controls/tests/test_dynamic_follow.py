"""PORT-01 oracle: CT921/openpilot TOP01003 at 615799f95e978fbf643d1e762d605b4d5b06499f."""
import json
from types import SimpleNamespace

import numpy as np
import pytest
from cereal import log

from dragonpilot.selfdrive.controls.lib import aem
from openpilot.common.params import Params, ParamKeyFlag, ParamKeyType
from openpilot.selfdrive.controls import plannerd
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib import long_mpc
from openpilot.selfdrive.controls.lib.longitudinal_planner import DPFlags, LongitudinalPlanner
from openpilot.selfdrive.controls.tests.test_dtsc_bounds import make_messages
from openpilot.selfdrive.modeld.constants import ModelConstants


# Independent expected values, including the donor's narrow 10 -> 10.01 m/s transition.
SPEEDS = [-1, 0, 6, 10, 10.005, 10.01, 15, 27.7, 30]
ORACLE = {
  'relaxed': [1.2, 1.2, 1.4, 1.4, 1.45, 1.5, 1.65, 1.8, 1.8],
  'standard': [1.1, 1.1, 1.3, 1.35, 1.375, 1.4, 1.4, 1.45, 1.45],
  'aggressive': [1.0, 1.0, 1.2, 1.0, .95, .9, .95, 1.0, 1.0],
}
STATIC = {'relaxed': 1.75, 'standard': 1.45, 'aggressive': 1.25}
THRESHOLD = float(np.arcsin(-.04))
PITCHES = [pytest.param([], 0, id='missing'),
           pytest.param([0, 0, 0], 0, id='flat'),
           pytest.param([0, .1, 0], 0, id='positive'),
           pytest.param([0, THRESHOLD + 1e-8, 0], 0, id='above-threshold'),
           pytest.param([0, THRESHOLD, 0], 0, id='threshold'),
           pytest.param([0, THRESHOLD - 1e-8, 0], .5, id='below-threshold'),
           pytest.param([0, -.1, 0], .5, id='downhill')]


def cp(longitudinal=True):
  return SimpleNamespace(brand='toyota', openpilotLongitudinalControl=longitudinal,
                         steerRatio=15.0, wheelbase=2.7, longitudinalActuatorDelay=.2, vEgoStopping=.25)


def donor_at_speed(speed, name):
  # Linear interpolation between independent test points; no production helper is used.
  return float(np.interp(speed, SPEEDS, ORACLE[name]))


class NativeSpy:
  def __init__(self, mpc):
    self.mpc = mpc
    self.solver = mpc.solver
    self.values = {}
    self.frames = []
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

  def solve(self):
    snapshot = {
      'speed': float(self.mpc.x0[1]), 'mode': self.mpc.mode, 'source': self.mpc.source,
      'p': np.array([self.values[i, 'p'] for i in range(long_mpc.N + 1)]),
      'W0': np.copy(self.values[0, 'W']), 'yref1': np.copy(self.values[1, 'yref']),
    }
    snapshot['native_status'] = self.solver.solve()
    self.frames.append(snapshot)
    return snapshot['native_status']

  def __getattr__(self, name):
    return getattr(self.solver, name)


def observe(planner):
  planner.maa_helper = None
  spy = NativeSpy(planner.mpc)
  planner.mpc.solver = spy
  return spy


def check_frame(planner, spy, expected, label):
  frame = spy.frames[-1]
  assert frame['p'].shape == (long_mpc.N + 1, 7)
  np.testing.assert_allclose(frame['p'][:, 4], expected, rtol=0, atol=1e-12)
  assert frame['native_status'] == planner.mpc.solution_status == 0
  assert spy.resets == 0
  for values in (frame['p'], frame['W0'], frame['yref1'], planner.mpc.v_solution,
                 planner.mpc.a_solution, planner.mpc.j_solution):
    assert np.all(np.isfinite(values))
  print(json.dumps({'case': label, 'speed': frame['speed'], 'mode': frame['mode'],
                    'source': frame['source'], 'p0': frame['p'][0].tolist(),
                    'W0': np.diag(frame['W0']).tolist(), 'yref1': frame['yref1'].tolist(),
                    'native_status': frame['native_status'], 'solution_status': planner.mpc.solution_status,
                    'finite': True, 'resets': spy.resets}))
  return frame


@pytest.mark.parametrize(('name', 'speed', 'expected'), [
  pytest.param(name, speed, expected, id=f'{name}-{speed}')
  for name, values in ORACLE.items() for speed, expected in zip(SPEEDS, values, strict=True)
])
def test_donor_interpolation(name, speed, expected):
  assert hasattr(long_mpc, 'get_dynamic_follow'), 'PORT-01 donor lookup is missing'
  actual = long_mpc.get_dynamic_follow(speed, getattr(log.LongitudinalPersonality, name))
  assert actual == pytest.approx(expected, rel=0, abs=1e-12)


def test_unsupported_personality():
  assert hasattr(long_mpc, 'get_dynamic_follow'), 'PORT-01 donor lookup is missing'
  with pytest.raises(NotImplementedError, match='personality'):
    long_mpc.get_dynamic_follow(20, 99)


def test_param_contract(tmp_path):
  params = Params(str(tmp_path))
  assert params.get_type('HankDynamicFollow') == ParamKeyType.BOOL
  assert params.get_type('HankDynamicFollowActive') == ParamKeyType.BOOL
  assert params.get('HankDynamicFollow', return_default=True) is False
  assert params.get('HankDynamicFollowActive', return_default=True) is None


def start_plannerd(params, monkeypatch):
  """Run the real entry point through session setup, then stop at messaging startup."""
  class StartupComplete(Exception):
    pass

  planners = []

  def create_planner(*args, **kwargs):
    planner = LongitudinalPlanner(*args, **kwargs)
    planners.append(planner)
    return planner

  def stop_at_pubmaster(*args, **kwargs):
    raise StartupComplete

  params.put('CarParams', b'test transport')
  monkeypatch.setattr(plannerd, 'Params', lambda: params)
  monkeypatch.setattr(plannerd, 'config_realtime_process', lambda *args: None)
  monkeypatch.setattr(plannerd.messaging, 'log_from_bytes', lambda *args: cp())
  monkeypatch.setattr(plannerd.messaging, 'PubMaster', stop_at_pubmaster)
  monkeypatch.setattr(plannerd, 'LongitudinalPlanner', create_planner)
  with pytest.raises(StartupComplete):
    plannerd.main()
  assert len(planners) == 1
  return planners[0]


@pytest.mark.parametrize('requested', [False, True])
@pytest.mark.parametrize('clear_flag', [ParamKeyFlag.CLEAR_ON_OFFROAD_TRANSITION, ParamKeyFlag.CLEAR_ON_IGNITION_ON])
def test_requested_active_lifecycle(tmp_path, monkeypatch, requested, clear_flag):
  params = Params(str(tmp_path))
  requested_config = {'version': 1, 'dynamic_follow': requested, 'accel_profile': 3}
  params.put('HankConfigRequested', requested_config)
  planner = start_plannerd(params, monkeypatch)
  assert params.get('HankConfigActive') == requested_config
  assert params.get_bool('HankConfigSessionStarted')
  assert planner._dynamic_follow_active is requested
  assert params.get('HankDynamicFollowActive') is None
  spy = observe(planner)
  sm = make_messages()

  def check_session(instance, observer, active):
    instance.update(sm)
    expected = donor_at_speed(observer.frames[-1]['speed'], 'standard') if active else 1.45
    check_frame(instance, observer, expected, f'lifecycle-active-{active}')

  check_session(planner, spy, requested)
  next_config = {**requested_config, 'dynamic_follow': not requested}
  params.put('HankConfigRequested', next_config)
  check_session(planner, spy, requested)
  params.put_bool('HankDynamicFollowActive', not requested)
  restarted = start_plannerd(params, monkeypatch)
  assert params.get('HankConfigActive') == requested_config
  assert params.get_bool('HankConfigSessionStarted')
  assert params.get('HankDynamicFollowActive') is not requested
  assert restarted._dynamic_follow_active is requested
  check_session(restarted, observe(restarted), requested)

  # Exercise actual Params lifecycle flags, not just manual removal of Active.
  params.clear_all(clear_flag)
  assert params.get('HankConfigActive') is None
  assert params.get('HankConfigSessionStarted') is None
  assert params.get('HankDynamicFollowActive') is None
  assert params.get('HankConfigRequested') == next_config
  next_session = start_plannerd(params, monkeypatch)
  assert params.get('HankConfigActive') == next_config
  assert params.get_bool('HankConfigSessionStarted')
  assert next_session._dynamic_follow_active is not requested
  assert params.get('HankDynamicFollowActive') is None
  check_session(next_session, observe(next_session), not requested)


@pytest.mark.parametrize('name', list(STATIC))
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize(('orientation', 'addition'), PITCHES)
def test_native_follow_and_pitch(name, enabled, orientation, addition):
  assert np.sin(THRESHOLD) == -.04
  planner = LongitudinalPlanner(cp(), init_v=20, dynamic_follow_active=enabled)
  spy = observe(planner)
  sm = make_messages()
  sm['selfdriveState'].personality = getattr(log.LongitudinalPersonality, name)
  sm['carControl'].orientationNED = orientation
  planner.update(sm)
  speed = spy.frames[-1]['speed']
  expected = donor_at_speed(speed, name) + addition if enabled else STATIC[name]
  frame = check_frame(planner, spy, expected, f'{name}-enabled-{enabled}-pitch-{orientation}')
  np.testing.assert_allclose(frame['p'][:, 6], long_mpc.get_STOP_DISTANCE(getattr(log.LongitudinalPersonality, name)))


def test_uses_mpc_current_speed():
  planner = LongitudinalPlanner(cp(), init_v=10, dynamic_follow_active=True)
  spy = observe(planner)
  sm = make_messages()
  sm['selfdriveState'].personality = log.LongitudinalPersonality.aggressive
  planner.update(sm)
  speed = spy.frames[-1]['speed']
  assert speed != sm['carState'].vEgo
  assert abs(donor_at_speed(speed, 'aggressive') - donor_at_speed(20, 'aggressive')) > .01
  check_frame(planner, spy, donor_at_speed(speed, 'aggressive'), 'filtered-speed')


def test_mpc_api_off_on_off():
  mpc = long_mpc.LongitudinalMpc()
  spy = NativeSpy(mpc)
  mpc.solver = spy
  mpc.set_cur_state(10.005, 0)
  sm = make_messages()
  for enabled, expected in [(False, 1.25), (True, 1.45), (False, 1.25)]:
    mpc.set_weights(personality=log.LongitudinalPersonality.aggressive)
    x = 10.005 * long_mpc.T_IDXS
    v = np.full(long_mpc.N + 1, 10.005)
    a = np.zeros(long_mpc.N + 1)
    j = np.zeros(long_mpc.N + 1)
    mpc.update(sm['radarState'], 20, x, v, a, j,
               personality=log.LongitudinalPersonality.aggressive, dynamic_follow=enabled, pitch_rad=-.1)
    frame = check_frame(SimpleNamespace(mpc=mpc), spy, expected, f'api-enabled-{enabled}')
    np.testing.assert_allclose(frame['p'][:, 6], long_mpc.get_STOP_DISTANCE(log.LongitudinalPersonality.aggressive))


def test_apm_effective_personality():
  planner = LongitudinalPlanner(cp(), init_v=6, dynamic_follow_active=True)
  spy = observe(planner)
  sm = make_messages()
  sm['selfdriveState'].personality = log.LongitudinalPersonality.relaxed
  for speed, name in [(6, 'aggressive'), (9, 'aggressive'), (12, 'relaxed')]:
    sm['carState'].vEgo = speed
    planner.update(sm, DPFlags.APM)
    assert planner.apm._active == (name == 'aggressive')
    frame = check_frame(planner, spy, donor_at_speed(spy.frames[-1]['speed'], name), f'APM-{speed}-{name}')
    np.testing.assert_allclose(frame['p'][:, 6], long_mpc.get_STOP_DISTANCE(getattr(log.LongitudinalPersonality, name)))


@pytest.mark.parametrize('transition', ['experimental', 'aem'])
def test_mode_interaction(monkeypatch, transition):
  planner = LongitudinalPlanner(cp(), init_v=20, dynamic_follow_active=True)
  spy = observe(planner)
  sm = make_messages()
  times = np.asarray(ModelConstants.T_IDXS)
  sm['modelV2'].orientation = SimpleNamespace(x=np.zeros(len(times)).tolist())
  clock = [100.0]
  monkeypatch.setattr(aem, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
  for index, mode in enumerate(['acc', 'blended', 'acc']):
    clock[0] = 100.0 + index
    sm['selfdriveState'].experimentalMode = transition == 'experimental' and index == 1
    stopping = transition == 'aem' and index == 1
    sm['modelV2'].position.x = (20 * times - 1.25 * times**2 if stopping else 20 * times).tolist()
    sm['modelV2'].velocity.x = (20 - 2.5 * times if stopping else np.full(len(times), 20)).tolist()
    sm['modelV2'].acceleration.x = np.full(len(times), -2.5 if stopping else 0).tolist()
    planner.update(sm, DPFlags.AEM if transition == 'aem' else 0)
    frame = check_frame(planner, spy, donor_at_speed(spy.frames[-1]['speed'], 'standard'), f'{transition}-{index}')
    np.testing.assert_allclose(frame['p'][:, 6], long_mpc.get_STOP_DISTANCE(log.LongitudinalPersonality.standard))
    assert planner.mpc.mode == mode
    if transition == 'aem':
      assert planner.aem._active == (index == 1)
    blended = mode == 'blended'
    np.testing.assert_allclose(np.diag(frame['W0']), [0, .1, .2, 5, 40, 1] if blended else [3, 0, 0, 0, 200, 5])
    np.testing.assert_array_equal(frame['p'][:, 5], 1.0 if blended else .75)
    assert frame['source'] == ('e2e' if blended else 'cruise')
    if blended:
      expected_v = np.interp(long_mpc.T_IDXS, times, sm['modelV2'].velocity.x)
      expected_x1 = (expected_v[0] + expected_v[1]) / 2 * long_mpc.T_IDXS[1]
      np.testing.assert_allclose(frame['yref1'], [0, expected_x1, expected_v[1], -2.5 if stopping else 0, 0, 0])
      np.testing.assert_allclose(frame['p'][0, 2], 50 + (frame['speed'] + 10)**2 / 5)
    else:
      np.testing.assert_array_equal(frame['yref1'], 0)
      expected_obstacle = (frame['speed']**2 / 5 + frame['p'][0, 4] * frame['speed']
                           + long_mpc.get_STOP_DISTANCE(log.LongitudinalPersonality.standard))
      np.testing.assert_allclose(frame['p'][0, 2], expected_obstacle)


def test_dtsc_bounds_with_dynamic_follow(monkeypatch):
  planner = LongitudinalPlanner(cp(), init_v=20, dynamic_follow_active=True)
  spy = observe(planner)
  constraints = []
  original = planner.dtsc.get_mpc_constraints

  def capture(*args):
    lower, upper = original(*args)
    constraints.append(np.column_stack((np.maximum(args[2], lower), np.minimum(args[3], upper))))
    return lower, upper

  monkeypatch.setattr(planner.dtsc, 'get_mpc_constraints', capture)
  planner.update(make_messages(), DPFlags.DTSC)
  frame = check_frame(planner, spy, donor_at_speed(spy.frames[-1]['speed'], 'standard'), 'DTSC+DF')
  assert planner.dtsc.active
  assert len(constraints) == 1
  np.testing.assert_allclose(frame['p'][:, :2], constraints[0])
  assert np.all(frame['p'][:, 1] < long_mpc.ACCEL_MAX)


def test_stock_long_disables_donor():
  planner = LongitudinalPlanner(cp(False), init_v=20, dynamic_follow_active=True)
  spy = observe(planner)
  sm = make_messages()
  sm['carControl'].orientationNED = [0, -.1, 0]
  sm['selfdriveState'].personality = log.LongitudinalPersonality.aggressive
  planner.update(sm)
  check_frame(planner, spy, 1.25, 'stock-long')
