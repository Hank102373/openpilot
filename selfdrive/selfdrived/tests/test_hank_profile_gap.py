"""D-023 gap button must change Requested, never current personality."""
import json

from cereal import car
from openpilot.common.params import Params, ParamKeyFlag
from openpilot.selfdrive.controls.lib.hank_config import initialize_session, save_profile
from openpilot.selfdrive.selfdrived import selfdrived


def gap_release():
  button = car.CarState.ButtonEvent.new_message()
  button.type = car.CarState.ButtonEvent.Type.gapAdjustCruise
  button.pressed = False
  return button


def test_gap_cycles_requested_without_live_personality_write(tmp_path):
  params = Params(str(tmp_path))
  params.put("LongitudinalPersonality", 1)
  initialize_session(params)
  cp = car.CarParams.new_message()
  cp.openpilotLongitudinalControl = True
  for expected in ("compact", "normal", "comfortable", "compact"):
    assert selfdrived.handle_hank_gap_request(params, cp, [gap_release()]) == expected
    assert params.get("HankConfigRequested")["hank_profile"] == expected
    assert params.get("HankConfigActive") == {"version": 1, "dynamic_follow": False, "accel_profile": 3}
    assert params.get("LongitudinalPersonality") == 1


def test_gap_follows_pending_requested_and_preserves_dynamic_follow(tmp_path):
  params = Params(str(tmp_path))
  initialize_session(params)
  save_profile(params, "normal")
  requested = params.get("HankConfigRequested")
  requested["dynamic_follow"] = True
  params.put("HankConfigRequested", requested)
  cp = car.CarParams.new_message()
  cp.openpilotLongitudinalControl = True
  assert selfdrived.handle_hank_gap_request(params, cp, [gap_release()]) == "comfortable"
  assert params.get("HankConfigRequested")["dynamic_follow"] is True


def test_gap_ignores_tss_and_button_press(tmp_path):
  params = Params(str(tmp_path))
  initialize_session(params)
  before = json.dumps(params.get("HankConfigRequested"))
  cp = car.CarParams.new_message()
  cp.openpilotLongitudinalControl = False
  assert selfdrived.handle_hank_gap_request(params, cp, [gap_release()]) is None
  assert json.dumps(params.get("HankConfigRequested")) == before
  cp.openpilotLongitudinalControl = True
  button = gap_release()
  button.pressed = True
  assert selfdrived.handle_hank_gap_request(params, cp, [button]) is None
  assert json.dumps(params.get("HankConfigRequested")) == before


def test_v2_active_personality_waits_for_snapshot_and_ignores_legacy_key(tmp_path):
  params = Params(str(tmp_path))
  params.put("LongitudinalPersonality", 2)
  save_profile(params, "compact")
  assert selfdrived.read_hank_session_personality(params) == (None, False)
  initialize_session(params)
  assert selfdrived.read_hank_session_personality(params) == (0, True)
  params.put("LongitudinalPersonality", 1)
  assert selfdrived.read_hank_session_personality(params) == (0, True)
  params.clear_all(ParamKeyFlag.CLEAR_ON_OFFROAD_TRANSITION)
  assert selfdrived.read_hank_session_personality(params) == (None, False)
