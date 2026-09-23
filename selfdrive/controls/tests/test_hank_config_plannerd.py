"""CFG-01 native registry and real plannerd startup data-flow evidence."""
import json
from pathlib import Path

import numpy as np
import pytest
from cereal import car

from openpilot.common.params import Params, ParamKeyFlag, ParamKeyType
from openpilot.selfdrive.controls import plannerd
from openpilot.selfdrive.controls.lib import longitudinal_planner as lp
from openpilot.selfdrive.controls.lib.accel_personality import AccelProfile
from openpilot.selfdrive.controls.lib.hank_config import SessionError
from openpilot.selfdrive.controls.tests.test_dtsc_bounds import make_messages

REQUESTED = "HankConfigRequested"
ACTIVE = "HankConfigActive"
LATCH = "HankConfigSessionStarted"
LEGACY = "HankDynamicFollow"
LEGACY_ACTIVE = "HankDynamicFollowActive"
STOCK = {"version": 1, "dynamic_follow": False, "accel_profile": 3}
ORIGINAL = {"version": 2, "dynamic_follow": False, "hank_profile": "original", "accel_profile": 3}
ECO = {"version": 1, "dynamic_follow": True, "accel_profile": 2}


@pytest.fixture
def params(tmp_path):
  result = Params(str(tmp_path))
  for key in [REQUESTED, ACTIVE, LATCH]:
    result.check_key(key)  # No alias or fallback: stale native registry must fail.
  return result


@pytest.mark.parametrize("key,kind,flags,value", [
  (REQUESTED, ParamKeyType.JSON, 2, ECO),
  (ACTIVE, ParamKeyType.JSON, 144, ECO),
  (LATCH, ParamKeyType.BOOL, 144, True),
])
def test_native_registry_contract(params, key, kind, flags, value):
  assert params.get_type(key) == kind
  assert params.get_default_value(key) is None
  assert params.get(key, return_default=True) is None
  params.put(key, value)
  assert params.get(key) == value
  if kind == ParamKeyType.BOOL:
    assert Path(params.get_param_path(key)).read_bytes() == b"1"
  # Complement clear verifies there are no additional native flags.
  params.clear_all(int(ParamKeyFlag.ALL) ^ flags)
  assert params.get(key) == value
  for bit in [2, 16, 128]:
    params.put(key, value)
    params.clear_all(bit)
    assert (params.get(key) is None) == bool(flags & bit)
  params.put(key, value)
  params.remove(key)
  assert params.get(key) is None


@pytest.fixture
def startup(params, monkeypatch):
  planners = []

  class StartupComplete(Exception):
    pass

  def construct(*args, **kwargs):
    planner = lp.LongitudinalPlanner(*args, **kwargs)
    planners.append((planner, kwargs))
    return planner

  def stop_before_loop(*args, **kwargs):
    raise StartupComplete

  monkeypatch.setattr(plannerd, "Params", lambda: params)
  monkeypatch.setattr(plannerd, "config_realtime_process", lambda *args: None)
  monkeypatch.setattr(plannerd, "LongitudinalPlanner", construct)
  monkeypatch.setattr(plannerd.messaging, "PubMaster", stop_before_loop)

  def start(longitudinal=True):
    cp = car.CarParams.new_message()
    cp.brand = "toyota"
    cp.openpilotLongitudinalControl = longitudinal
    cp.steerRatio = 15.
    cp.wheelbase = 2.7
    cp.longitudinalActuatorDelay = .2
    cp.vEgoStopping = .25
    params.put("CarParams", cp.to_bytes())
    before = len(planners)
    with pytest.raises(StartupComplete):
      plannerd.main()
    assert len(planners) == before + 1
    return planners[-1]

  start.planners = planners
  return start


def selections(planner):
  return planner._dynamic_follow_active, planner.accel_profile


def test_requested_eco_reaches_real_planner(params, startup):
  params.put(REQUESTED, ECO)
  planner, arguments = startup()
  # Baseline data-flow oracle: the old main constructs false + stock (3).
  assert selections(planner) == (True, AccelProfile.eco)
  assert arguments["dynamic_follow_active"] is True
  assert arguments["accel_profile"] is AccelProfile.eco
  assert params.get(ACTIVE) == ECO
  assert params.get(LATCH) is True
  assert params.get(LEGACY_ACTIVE) is None


def test_default_snapshot(params, startup):
  planner, _ = startup()
  assert selections(planner) == (False, AccelProfile.stock)
  assert params.get(ACTIVE) == STOCK
  assert params.get(REQUESTED) == STOCK


@pytest.mark.parametrize("flag", [ParamKeyFlag.CLEAR_ON_OFFROAD_TRANSITION, ParamKeyFlag.CLEAR_ON_IGNITION_ON])
def test_requested_change_restart_then_lifecycle(params, startup, flag):
  params.put(REQUESTED, ECO)
  first, _ = startup()
  params.put(REQUESTED, STOCK)
  restarted, _ = startup()
  assert selections(first) == selections(restarted) == (True, AccelProfile.eco)
  assert params.get(ACTIVE) == ECO
  params.clear_all(flag)
  assert params.get(ACTIVE) is None
  assert params.get(LATCH) is None
  assert params.get(REQUESTED) == STOCK
  next_session, _ = startup()
  assert selections(next_session) == (False, AccelProfile.stock)
  assert params.get(ACTIVE) == STOCK


def test_corrupt_requested_original_recovery(params, startup):
  Path(params.get_param_path(REQUESTED)).write_bytes(b"{")
  planner, _ = startup()
  assert selections(planner) == (False, AccelProfile.stock)
  assert params.get(ACTIVE) == ORIGINAL
  assert Path(params.get_param_path(REQUESTED)).read_bytes() == b"{"


@pytest.mark.parametrize("active,latch", [(b"{", b"1"), (None, b"1"), (json.dumps(ECO).encode(), None)])
def test_bad_session_never_constructs_planner(params, startup, active, latch):
  if active is not None:
    Path(params.get_param_path(ACTIVE)).write_bytes(active)
  if latch is not None:
    Path(params.get_param_path(LATCH)).write_bytes(latch)
  with pytest.raises(SessionError, match="REJECT_AND_WAIT_NEW_SESSION"):
    startup()
  assert not startup.planners


@pytest.mark.parametrize("enabled", [False, True])
def test_legacy_requested_migration(params, startup, enabled):
  params.put_bool(LEGACY, enabled)
  planner, _ = startup()
  assert selections(planner) == (enabled, AccelProfile.stock)
  assert params.get(ACTIVE) == {**STOCK, "dynamic_follow": enabled}
  assert params.get(LEGACY) is enabled
  assert params.get(LEGACY_ACTIVE) is None


@pytest.mark.parametrize("legacy_active", [b"0", b"1", b"bad"])
def test_legacy_active_rejects_before_planner(params, startup, legacy_active):
  params.put_bool(LEGACY, True)
  Path(params.get_param_path(LEGACY_ACTIVE)).write_bytes(legacy_active)
  with pytest.raises(SessionError, match="REJECT_AND_WAIT_NEW_SESSION"):
    startup()
  assert not startup.planners
  assert params.get(REQUESTED) is None
  assert params.get(ACTIVE) is None
  assert Path(params.get_param_path(LEGACY_ACTIVE)).read_bytes() == legacy_active


def test_valid_new_pair_reuses_despite_legacy_active(params, startup):
  params.put(ACTIVE, ECO)
  params.put_bool(LATCH, True)
  params.put_bool(LEGACY_ACTIVE, False)
  params.put(REQUESTED, STOCK)
  planner, _ = startup()
  assert selections(planner) == (True, AccelProfile.eco)
  assert params.get(LEGACY_ACTIVE) is False


def test_stock_long_preserves_config_and_bypasses_features(params, startup, monkeypatch):
  params.put(REQUESTED, ECO)
  planner, _ = startup(longitudinal=False)
  assert selections(planner) == (True, AccelProfile.eco)
  assert params.get(ACTIVE) == ECO

  bounds, dynamic = [], []
  original_limit = lp.limit_accel_in_turns
  original_update = planner.mpc.update

  def observe_limit(speed, angle, limits, cp):
    bounds.append((speed, list(limits)))
    return original_limit(speed, angle, limits, cp)

  def observe_update(*args, **kwargs):
    dynamic.append(kwargs["dynamic_follow"])
    return original_update(*args, **kwargs)

  monkeypatch.setattr(lp, "limit_accel_in_turns", observe_limit)
  monkeypatch.setattr(planner.mpc, "update", observe_update)
  planner.maa_helper = None
  sm = make_messages()
  planner.update(sm)
  assert dynamic == [False]
  assert bounds[0][0] == 20.
  assert bounds[0][1][1] == pytest.approx(.9333333333333333)
  assert bounds[0][1][1] != pytest.approx(.36)  # Eco donor maximum at 20 m/s.
  assert planner.mpc.solution_status == 0
  assert np.isfinite(planner.mpc.v_solution).all()
  assert params.get(ACTIVE) == ECO
