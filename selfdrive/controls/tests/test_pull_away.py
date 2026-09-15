"""PORT-02 oracle: CT921/openpilot TOP096 3d75e471c74fccf0067dcda8cfe1374cf1268215."""
import json
from types import SimpleNamespace

import numpy as np
import pytest
from opendbc.car.interfaces import ACCEL_MIN, ACCEL_MAX

from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib import long_mpc
from openpilot.selfdrive.controls.lib.longitudinal_planner import DPFlags, LongitudinalPlanner
from openpilot.selfdrive.controls.tests.test_dtsc_bounds import make_messages
from openpilot.selfdrive.controls.tests.test_longitudinal_mode import NativeModeSpy
from openpilot.selfdrive.modeld.constants import ModelConstants


# Independent closure values, not calculated with the production transform.
@pytest.mark.parametrize(('ego', 'lead', 'expected'), [
  (1, 0, 0), (1, 1, .2), (0, .001, .0020002),
  (0, .299, .6158802), (0, .300, .618), (0, .301, .6201202),
  (0, 1, 2.2), (0, 4.999, 14.9960002), (0, 5, 15),
  (0, 5.001, 15.0040002), (0, 5.999, 19.1956002),
  (0, 6, 19.2), (0, 6.001, 19.2024002), (0, 10, 32),
  (26 / 3.6 - .001, 10, 20.000769507692308),
  (26 / 3.6, 10, 20), (26 / 3.6 + .001, 10, 20),
  (3, 4, 4.369230769230769),
])
def test_scalar_oracle(ego, lead, expected):
  # This existing caller works on baseline too, proving a numerical failure,
  # rather than failing only because the new helper signature is absent.
  actual = long_mpc.get_safe_obstacle_distance(ego, 1.45) - long_mpc.desired_follow_distance(ego, lead, 1.45)
  assert actual == pytest.approx(expected, rel=0, abs=1e-12)


@pytest.mark.parametrize(('speeds', 'expected'), [
  ([0] * 13, [0] * 13),
  ([2] * 13, [2.523076923076923] * 13),
  ([.5] * 13, [.05] * 13),
  ([2] * 12 + [1], [.8] * 12 + [.2]),
  ([2] * 12 + [.5], [.8] * 12 + [.05]),
  ([.5] + [2] * 12, [.05] + [.8] * 12),
  ([2] * 6 + [1] + [2] * 6, [.8] * 6 + [.2] + [.8] * 6),
  ([2] * 12 + [1.001], [2.523076923076923] * 12 + [.20212327692307692]),
  ([2] * 12 + [1.299], [2.523076923076923] * 12 + [.8526802]),
  ([2] * 12 + [1.300], [2.523076923076923] * 12 + [.8549230769230769]),
  ([2] * 12 + [1.301], [2.523076923076923] * 12 + [.8571663538461538]),
  ([1] * 13, [.2] * 13),
], ids=['stopped', 'positive', 'negative', 'positive-zero', 'positive-negative',
        'negative-positive', 'middle-zero', 'tiny-positive', 'delta-.299', 'delta-.300',
        'delta-.301', 'all-zero-relative'])
def test_horizon_oracle(speeds, expected):
  speeds = np.array(speeds, dtype=float)
  actual = long_mpc.get_safe_obstacle_distance(1, 1.45) - long_mpc.desired_follow_distance(1, speeds, 1.45)
  np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12)


def lead(distance=2, speed=0, valid=True):
  return SimpleNamespace(status=valid, dRel=distance, vLead=speed, aLeadK=0.,
                         aLeadTau=1.5, modelProb=0., vRel=speed)


def setup(ego=0, dynamic=False):
  cp = SimpleNamespace(openpilotLongitudinalControl=True, steerRatio=15., wheelbase=2.7,
                       longitudinalActuatorDelay=.2, vEgoStopping=.25)
  planner = LongitudinalPlanner(cp, init_v=ego, dynamic_follow_active=dynamic)
  planner.maa_helper = None
  spy = NativeModeSpy(planner)
  planner.mpc.solver = spy
  sm = make_messages()
  times = np.asarray(ModelConstants.T_IDXS)
  sm['carState'].vEgo = ego
  sm['modelV2'].position.x = (ego * times).tolist()
  sm['modelV2'].velocity.x = np.full(len(times), ego).tolist()
  return planner, spy, sm


def run_frame(planner, spy, sm, one, two, flags=0):
  sm['radarState'] = SimpleNamespace(leadOne=one, leadTwo=two)
  planner.update(sm, flags)
  frame = spy.frames[-1]
  assert frame['native_status'] == planner.mpc.solution_status == 0
  assert spy.resets == 0
  for values in (frame['p'], *frame['W'], *frame['yref'], planner.mpc.v_solution,
                 planner.mpc.a_solution, planner.mpc.j_solution):
    assert np.all(np.isfinite(values))
  assert frame['p'].shape == (13, 6)
  np.testing.assert_allclose(frame['p'][:, 2], frame['obstacles'].min(axis=1))
  print(json.dumps({'mode': frame['mpc_mode'], 'source': frame['source'],
                    'p0': frame['p'][0].tolist(), 'native_status': frame['native_status'],
                    'finite': True, 'resets': spy.resets}))
  return frame


@pytest.mark.parametrize(('one_speed', 'two_speed', 'offsets', 'source'), [
  (0, 1, [0, 2.2], 'lead0'),
  (1, 0, [2.2, 0], 'lead1'),
  (0, 0, [0, 0], 'lead0'),
  (.1, .1, [.202, .202], 'lead0'),
])
def test_independent_leads_before_selection(one_speed, two_speed, offsets, source):
  planner, spy, sm = setup()
  captured = run_frame(planner, spy, sm, lead(speed=one_speed), lead(speed=two_speed))
  for index, speed in enumerate((one_speed, two_speed)):
    np.testing.assert_allclose(captured['obstacles'][:, index], 2 + speed * long_mpc.T_IDXS + offsets[index])
  assert captured['source'] == source


def test_source_switch():
  planner, spy, sm = setup()
  for distance, source, obstacle in [(2, 'lead0', 2), (3.5, 'lead1', 3), (2, 'lead0', 2)]:
    captured = run_frame(planner, spy, sm, lead(distance), lead(3))
    assert captured['source'] == source
    np.testing.assert_allclose(captured['p'][:, 2], obstacle)


@pytest.mark.parametrize(('speed', 'equivalence'), [(.1, .202), (0, 0)])
def test_loss_reacquire(speed, equivalence):
  planner, spy, sm = setup()
  frames = []
  for valid in [True, False, True]:
    # Hold the measured/filtered initial condition fixed to isolate lead history.
    planner.v_desired_filter.x = 0.
    planner.a_desired = 0.
    captured = run_frame(planner, spy, sm, lead(speed=speed, valid=valid), lead(valid=False))
    expected = 2 + speed * long_mpc.T_IDXS + equivalence if valid else 82 + 10 * long_mpc.T_IDXS
    np.testing.assert_allclose(captured['obstacles'][:, 0], expected)
    np.testing.assert_allclose(captured['obstacles'][:, 1], 82 + 10 * long_mpc.T_IDXS)
    assert captured['source'] == ('lead0' if valid else 'cruise')
    frames.append(captured)
  np.testing.assert_allclose(frames[0]['p'][:, 2], frames[2]['p'][:, 2])


@pytest.mark.parametrize('blended', [False, True])
@pytest.mark.parametrize('dynamic', [False, True])
@pytest.mark.parametrize('dtsc', [False, True])
def test_focused_interactions(monkeypatch, blended, dynamic, dtsc):
  def observe():
    planner, spy, sm = setup(ego=3, dynamic=dynamic)
    sm['selfdriveState'].experimentalMode = blended
    frame = run_frame(planner, spy, sm, lead(10, 4), lead(valid=False), DPFlags.DTSC if dtsc else 0)
    return frame

  current = observe()
  # Controlled counterfactual: keep real planner, MPC, and native solver; change
  # only stopped equivalence to the pre-PORT-02 quadratic for one fresh frame.
  with monkeypatch.context() as patch:
    patch.setattr(long_mpc, 'get_stopped_equivalence_factor', lambda v_lead, *args: v_lead**2 / 5)
    baseline = observe()

  np.testing.assert_allclose(current['obstacles'][:, 0], 10 + 4 * long_mpc.T_IDXS + 4.369230769230769)
  np.testing.assert_allclose(current['obstacles'][:, 1], 50 + 13 * long_mpc.T_IDXS + 40.815384615384615)
  assert np.any(np.abs(current['p'][:, 2] - baseline['p'][:, 2]) > .1)
  np.testing.assert_allclose(current['p'][:, [0, 1, 3, 4, 5]], baseline['p'][:, [0, 1, 3, 4, 5]])
  if not dtsc:
    np.testing.assert_allclose(current['p'][:, :2], np.tile([ACCEL_MIN, ACCEL_MAX], (13, 1)))
  np.testing.assert_allclose(current['p'][:, 4], 1.2 if dynamic else 1.45)
  np.testing.assert_allclose(current['p'][:, 5], 1 if blended else .75)
  assert current['mpc_mode'] == current['planner_mode'] == ('blended' if blended else 'acc')
  for field in ['W', 'yref']:
    for actual, original in zip(current[field], baseline[field], strict=True):
      np.testing.assert_array_equal(actual, original)
