import inspect
import json
from types import SimpleNamespace

import numpy as np
import pytest

from dragonpilot.selfdrive.controls.lib import aem
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import N, T_IDXS
from openpilot.selfdrive.controls.lib.longitudinal_planner import DPFlags, LongitudinalPlanner
from openpilot.selfdrive.controls.tests.test_dtsc_bounds import make_messages
from openpilot.selfdrive.modeld.constants import ModelConstants


class NativeModeSpy:
  """Observe real planner/MPC frames and forward all calls to the native solver."""

  def __init__(self, planner):
    self.planner = planner
    self.solver = planner.mpc.solver
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
    # solve <- run <- MPC.update <- Planner.update: observe, never replace, branches.
    frame = inspect.currentframe()
    try:
      mpc_frame = frame.f_back.f_back
      planner_frame = mpc_frame.f_back
      snapshot = {
        'planner_mode': planner_frame.f_locals['mode'],
        'mpc_mode': self.planner.mpc.mode,
        'source': self.planner.mpc.source,
        'obstacles': np.copy(mpc_frame.f_locals['x_obstacles']),
        'p': np.array([self.values[i, 'p'] for i in range(N + 1)]),
        'W': [self.values[i, 'W'].copy() for i in range(N + 1)],
        'yref': [self.values[i, 'yref'].copy() for i in range(N + 1)],
      }
    finally:
      del frame
    snapshot['native_status'] = self.solver.solve()
    self.frames.append(snapshot)
    return snapshot['native_status']

  def __getattr__(self, name):
    return getattr(self.solver, name)


@pytest.mark.parametrize('transition', ['experimental', 'aem'])
def test_mode_transitions_reach_native_solver(monkeypatch, transition):
  cp = SimpleNamespace(openpilotLongitudinalControl=True, steerRatio=15.0, wheelbase=2.7,
                       longitudinalActuatorDelay=0.2, vEgoStopping=0.25)
  planner = LongitudinalPlanner(cp, init_v=20.0)
  planner.maa_helper = None
  spy = NativeModeSpy(planner)
  planner.mpc.solver = spy
  sm = make_messages()
  times = np.asarray(ModelConstants.T_IDXS)
  sm['modelV2'].orientation = SimpleNamespace(x=np.zeros(len(times)).tolist())
  clock = [100.0]
  monkeypatch.setattr(aem, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
  flags = DPFlags.AEM if transition == 'aem' else 0

  for index, expected_mode in enumerate(['acc', 'blended', 'acc']):
    clock[0] = 100.0 + index
    sm['selfdriveState'].experimentalMode = transition == 'experimental' and index == 1
    # A physically consistent stopping trajectory triggers the real AEM stop detector.
    stopping = transition == 'aem' and index == 1
    sm['modelV2'].position.x = (20 * times - 1.25 * times**2 if stopping else 20 * times).tolist()
    sm['modelV2'].velocity.x = (20 - 2.5 * times if stopping else np.full(len(times), 20.0)).tolist()
    sm['modelV2'].acceleration.x = np.full(len(times), -2.5 if stopping else 0.0).tolist()
    planner.update(sm, flags)
    captured = spy.frames[-1]
    captured['expected_mode'] = expected_mode
    captured['expected_v'] = np.interp(T_IDXS, times, sm['modelV2'].velocity.x)
    captured['expected_a'] = np.interp(T_IDXS, times, sm['modelV2'].acceleration.x)
    captured['solution_status'] = planner.mpc.solution_status
    captured['finite_solution'] = all(np.all(np.isfinite(v)) for v in
                                      [planner.mpc.v_solution, planner.mpc.a_solution, planner.mpc.j_solution])
    print(json.dumps({'transition': transition, 'frame': index,
                      'planner_mode': captured['planner_mode'], 'mpc_mode': captured['mpc_mode'],
                      'aem_active': planner.aem._active, 'source': captured['source'],
                      'final_source': planner.mpc.source, 'p5': captured['p'][:, 5].tolist(),
                      'W0': np.diag(captured['W'][0]).tolist(), 'yref1': captured['yref'][1].tolist(),
                      'obstacle0': captured['p'][0, 2], 'obstacle_columns': captured['obstacles'].shape[1],
                      'native_status': captured['native_status'], 'solution_status': captured['solution_status'],
                      'finite_solution': captured['finite_solution'], 'resets': spy.resets}))
    if transition == 'aem':
      assert planner.aem._active == (index == 1)

  assert len(spy.frames) == 3
  assert spy.resets == 0, 'Mode transitions must preserve native warm-start state without resets'
  for captured in spy.frames:
    mode = captured['expected_mode']
    assert captured['native_status'] == captured['solution_status'] == 0
    assert captured['finite_solution']
    assert captured['planner_mode'] == mode
    assert captured['mpc_mode'] == mode, 'E-002: final planner mode did not reach MPC in the same frame'
    blended = mode == 'blended'
    weights = np.array([0, .1, .2, 5, 40, 1] if blended else [3, 0, 0, 0, 200, 5], dtype=float)
    for stage in range(N + 1):
      expected_weights = weights.copy()
      expected_weights[4] *= np.interp(T_IDXS[min(stage, N - 1)], [0, 1, 2], [1, 1, 0])
      np.testing.assert_allclose(captured['W'][stage], np.diag(expected_weights[:5] if stage == N else expected_weights))
    np.testing.assert_allclose(captured['p'][:, 5], 1.0 if blended else .75)
    assert captured['obstacles'].shape == (N + 1, 2 if blended else 3)
    np.testing.assert_allclose(captured['p'][:, 2], np.min(captured['obstacles'], axis=1))
    assert captured['source'] == ('e2e' if blended else 'cruise')
    yref = np.array([row[:4] for row in captured['yref']])
    assert np.all(np.isfinite(captured['p']))
    assert np.all(np.isfinite(yref))
    if blended:
      expected_x = np.cumsum(np.insert((captured['expected_v'][1:] + captured['expected_v'][:-1]) / 2 * np.diff(T_IDXS), 0, 0))
      np.testing.assert_allclose(yref[:, 1], expected_x)
      np.testing.assert_allclose(yref[:, 2], captured['expected_v'])
      np.testing.assert_allclose(yref[:, 3], captured['expected_a'])
    else:
      np.testing.assert_array_equal(yref, 0)
