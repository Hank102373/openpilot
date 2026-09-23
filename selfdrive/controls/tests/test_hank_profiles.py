"""D-023 test-first profile contract against native Params and the real CFG adapter."""
import json
from pathlib import Path

import pytest
from cereal import car, log

from openpilot.common.params import Params, ParamKeyFlag
from openpilot.selfdrive.controls.lib import hank_config as cfg
from openpilot.selfdrive.controls.lib.accel_personality import AccelProfile
from openpilot.selfdrive.controls import plannerd
from openpilot.selfdrive.controls.lib import longitudinal_planner as lp
from dragonpilot.selfdrive.controls.lib.apm import APM


@pytest.fixture
def params(tmp_path):
  return Params(str(tmp_path / "params"))


@pytest.mark.parametrize("mode,accel,personality", [
  ("compact", 0, log.LongitudinalPersonality.aggressive),
  ("normal", 1, log.LongitudinalPersonality.standard),
  ("comfortable", 2, log.LongitudinalPersonality.relaxed),
  ("original", 3, log.LongitudinalPersonality.standard),
])
def test_v2_schema_and_mapping(mode, accel, personality):
  payload = {"version": 2, "dynamic_follow": True, "hank_profile": mode, "accel_profile": accel}
  parsed = cfg.parse_config(json.dumps(payload))
  assert json.loads(cfg.serialize_config(parsed)) == payload
  assert cfg.base_personality(parsed) == personality


@pytest.mark.parametrize("payload", [
  {"version": 2, "dynamic_follow": False, "hank_profile": "unknown", "accel_profile": 3},
  {"version": 2, "dynamic_follow": False, "hank_profile": "normal", "accel_profile": 3},
  {"version": 2, "dynamic_follow": 0, "hank_profile": "normal", "accel_profile": 1},
  {"version": 2, "dynamic_follow": False, "hank_profile": "normal", "accel_profile": True},
  {"version": 2, "dynamic_follow": False, "hank_profile": "normal", "accel_profile": 1, "extra": 1},
  {"version": 2, "dynamic_follow": False, "hank_profile": "normal"},
  {"version": 3, "dynamic_follow": False, "hank_profile": "normal", "accel_profile": 1},
])
def test_v2_rejects_invalid(payload):
  with pytest.raises(cfg.ConfigValidationError):
    cfg.parse_config(json.dumps(payload))


def test_v2_rejects_duplicate_keys():
  with pytest.raises(cfg.ConfigValidationError):
    cfg.parse_config('{"version":2,"version":2,"dynamic_follow":false,"hank_profile":"normal","accel_profile":1}')


def test_v1_remains_exact_and_unmapped():
  old = cfg.parse_config('{"version":1,"dynamic_follow":true,"accel_profile":2}')
  assert cfg.serialize_config(old) == '{"version":1,"dynamic_follow":true,"accel_profile":2}'
  assert cfg.base_personality(old) is None


def test_requested_cycle_preserves_dynamic_follow_and_current_active(params):
  original = cfg.initialize_session(params)
  assert original.config.version == 1
  assert [cfg.cycle_requested_profile(params).hank_profile for _ in range(4)] == [
    "compact", "normal", "comfortable", "compact",
  ]
  assert cfg.initialize_session(params).config == original.config
  assert params.get("HankConfigActive") == json.loads(cfg.serialize_config(original.config))
  cfg.set_requested_dynamic_follow(params, True)
  assert cfg.cycle_requested_profile(params).hank_profile == "normal"
  assert cfg.read_config(params, "HankConfigRequested").value.dynamic_follow is True


def test_v2_next_session_and_same_session_restart(params):
  cfg.initialize_session(params)
  cfg.save_profile(params, "comfortable")
  assert cfg.initialize_session(params).config.version == 1
  params.clear_all(ParamKeyFlag.CLEAR_ON_OFFROAD_TRANSITION)
  next_session = cfg.initialize_session(params)
  assert next_session.config.hank_profile == "comfortable"
  assert next_session.config.accel_profile == 2
  assert cfg.initialize_session(params).action == "REUSE_ACTIVE"


def test_restore_original_is_not_normal(params):
  cfg.save_profile(params, "normal")
  restored = cfg.restore_original(params)
  assert (restored.hank_profile, restored.accel_profile, restored.dynamic_follow) == ("original", 3, False)
  assert cfg.base_personality(restored) == log.LongitudinalPersonality.standard
  assert cfg.read_config(params, "HankConfigRequested").value == restored


def test_invalid_requested_is_not_silently_overwritten(params):
  Path(params.get_param_path("HankConfigRequested")).write_bytes(b"{")
  with pytest.raises(cfg.ConfigValidationError):
    cfg.save_profile(params, "compact")
  assert Path(params.get_param_path("HankConfigRequested")).read_bytes() == b"{"


@pytest.fixture
def startup(params, monkeypatch):
  class StartupComplete(Exception):
    pass

  planners = []

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

  def start():
    cp = car.CarParams.new_message()
    cp.brand = "toyota"
    cp.openpilotLongitudinalControl = True
    cp.steerRatio = 15.
    cp.wheelbase = 2.7
    cp.longitudinalActuatorDelay = .2
    cp.vEgoStopping = .25
    params.put("CarParams", cp.to_bytes())
    with pytest.raises(StartupComplete):
      plannerd.main()
    return planners[-1]

  return start


@pytest.mark.parametrize("mode,accel,personality", [
  ("compact", AccelProfile.sport, log.LongitudinalPersonality.aggressive),
  ("normal", AccelProfile.normal, log.LongitudinalPersonality.standard),
  ("comfortable", AccelProfile.eco, log.LongitudinalPersonality.relaxed),
])
def test_v2_plannerd_snapshot_and_personality_source(startup, params, mode, accel, personality):
  cfg.save_profile(params, mode)
  planner, arguments = startup()
  active = cfg.read_config(params, cfg.ACTIVE).value
  assert isinstance(active, cfg.HankConfigV2)
  assert active.hank_profile == mode
  assert planner.accel_profile is accel
  assert arguments["accel_profile"] is accel
  assert cfg.base_personality(active) == personality
  cfg.save_profile(params, "normal" if mode != "normal" else "comfortable")
  restarted, _ = startup()
  assert restarted.accel_profile is accel
  assert cfg.read_config(params, cfg.ACTIVE).value == active


@pytest.mark.parametrize("mode", ["compact", "comfortable"])
def test_apm_effective_override_never_changes_cfg_identity(params, mode):
  cfg.save_profile(params, mode)
  cfg.initialize_session(params)
  active_before = cfg.read_raw(params, cfg.ACTIVE).value
  requested_before = cfg.read_raw(params, cfg.REQUESTED).value
  base = cfg.base_personality(cfg.read_config(params, cfg.ACTIVE).value)
  apm = APM()
  assert apm.get_personality(0.0, base) == log.LongitudinalPersonality.aggressive
  assert apm.get_personality(20.0, base) == base
  assert cfg.read_raw(params, cfg.ACTIVE).value == active_before
  assert cfg.read_raw(params, cfg.REQUESTED).value == requested_before
