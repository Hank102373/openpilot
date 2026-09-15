from types import SimpleNamespace

import numpy as np
import pytest
from cereal import log
from opendbc.car.interfaces import ACCEL_MIN, ACCEL_MAX

from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import N, LongitudinalMpc
from openpilot.selfdrive.controls.lib.longitudinal_planner import DPFlags, LongitudinalPlanner
from openpilot.selfdrive.modeld.constants import ModelConstants


class SolverParamSpy:
  """Record MPC parameters while forwarding every call to the native solver."""

  def __init__(self, solver):
    self.solver = solver
    self.params = {}

  def set(self, stage, field, value):
    if field == 'p':
      self.params[stage] = np.array(value, copy=True)
    return self.solver.set(stage, field, value)

  def __getattr__(self, name):
    return getattr(self.solver, name)


def make_messages():
  ns = SimpleNamespace
  t_idxs = np.asarray(ModelConstants.T_IDXS)
  model_len = len(t_idxs)
  lead = ns(status=False, dRel=50.0, vLead=30.0, aLeadK=0.0,
            aLeadTau=1.5, modelProb=0.0, vRel=0.0)
  model = ns(position=ns(x=(20.0 * t_idxs).tolist()),
             velocity=ns(x=np.full(model_len, 20.0).tolist()),
             acceleration=ns(x=np.zeros(model_len).tolist()),
             orientationRate=ns(z=np.linspace(0.0, 0.4, model_len).tolist()),
             meta=ns(disengagePredictions=ns(gasPressProbs=[0.0, 1.0])),
             action=ns(desiredAcceleration=0.0, shouldStop=False))
  return {
    'selfdriveState': ns(experimentalMode=False, enabled=True,
                         personality=log.LongitudinalPersonality.standard),
    'carControl': ns(orientationNED=[]),
    'carState': ns(vEgo=20.0, vCruise=80.0, aEgo=0.0, standstill=False,
                   steeringAngleDeg=0.0),
    'controlsState': ns(longControlState=1, forceDecel=False),
    'liveParameters': ns(angleOffsetDeg=0.0),
    'modelV2': model,
    'radarState': ns(leadOne=lead, leadTwo=lead),
  }


def test_dtsc_bounds_reach_native_solver_and_clear_when_disabled():
  ns = SimpleNamespace
  cp = ns(openpilotLongitudinalControl=True, steerRatio=15.0, wheelbase=2.7,
          longitudinalActuatorDelay=0.2, vEgoStopping=0.25)
  planner = LongitudinalPlanner(cp, init_v=20.0)
  planner.maa_helper = None
  solver_spy = SolverParamSpy(planner.mpc.solver)
  planner.mpc.solver = solver_spy
  sm = make_messages()

  dtsc_call = {}
  get_constraints = planner.dtsc.get_mpc_constraints

  def capture_dtsc_constraints(*args):
    a_min, a_max = get_constraints(*args)
    dtsc_call['bounds'] = np.column_stack((a_min, a_max))
    dtsc_call['base_bounds'] = args[2:4]
    return a_min, a_max

  planner.dtsc.get_mpc_constraints = capture_dtsc_constraints

  def solver_bounds(flags):
    solver_spy.params.clear()
    planner.update(sm, flags)
    assert set(solver_spy.params) == set(range(N + 1))
    return np.array([solver_spy.params[i][:2] for i in range(N + 1)])

  default_bounds = np.tile([ACCEL_MIN, ACCEL_MAX], (N + 1, 1))
  np.testing.assert_allclose(solver_bounds(0), default_bounds)

  dtsc_bounds = solver_bounds(DPFlags.DTSC)
  assert planner.dtsc.active
  assert 'bounds' in dtsc_call
  base_min, base_max = dtsc_call['base_bounds']
  expected = np.column_stack((np.maximum(base_min, dtsc_call['bounds'][:, 0]),
                              np.minimum(base_max, dtsc_call['bounds'][:, 1])))
  assert np.any(expected[:, 1] < ACCEL_MAX)
  np.testing.assert_allclose(dtsc_bounds, expected,
                             err_msg="DTSC bounds were overwritten before native solver.set('p')")

  np.testing.assert_allclose(solver_bounds(0), default_bounds,
                             err_msg='DTSC bounds leaked into the next OFF frame')

@pytest.mark.parametrize(('bounds', 'message'), [
  pytest.param(np.zeros((N, 2)), 'shape', id='shape'),
  pytest.param(np.full((N + 1, 2), np.nan), 'finite', id='nonfinite'),
  pytest.param(np.tile([1.0, 0.0], (N + 1, 1)), 'a_min', id='inverted'),
])
def test_invalid_accel_bounds_rejected_before_native_solver(bounds, message):
  mpc = LongitudinalMpc()
  solver_spy = SolverParamSpy(mpc.solver)
  mpc.solver = solver_spy
  radar = make_messages()['radarState']
  x = np.zeros(N + 1)
  v = np.full(N + 1, 20.0)
  a = np.zeros(N + 1)
  j = np.zeros(N + 1)

  with pytest.raises(ValueError, match=message):
    mpc.update(radar, 20.0, x, v, a, j, accel_bounds=bounds)
  assert not solver_spy.params
