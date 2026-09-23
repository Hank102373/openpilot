"""D-024 UI-02 presentation and request-transport contract."""
import json

import pytest
from cereal import car

from openpilot.common.params import Params
from openpilot.selfdrive.controls.lib.hank_config import initialize_session
from openpilot.selfdrive.selfdrived import hank_owner as ho
from openpilot.selfdrive.ui.hank_owner import HankOwnerUIModel


BOOT = "11111111-2222-3333-4444-555555555555"


def cp_for(owner="HANK", supported=True):
  cp = car.CarParams.new_message()
  cp.brand = "toyota" if supported else "honda"
  cp.carFingerprint = ho.TARGET_CAR if supported else "unsupported"
  cp.openpilotLongitudinalControl = owner == "HANK"
  return cp


def transaction(owner="HANK", state="CONFIRMED", target=None):
  return ho.Transaction(1, owner, target, state, BOOT if state == "SWITCH_FAILED" else None)


def put_authority(params, value, gate=True):
  params.put(ho.STATE, json.loads(ho.serialize_state(value)))
  params.put(ho.GATE, gate)
  params.put(ho.OWNER, value.confirmed_owner == "TSS")


@pytest.fixture
def rig(tmp_path):
  params = Params(str(tmp_path))
  calls = []

  def request(_params, target, timeout=3.0):
    calls.append((target, timeout))
    return {"result": "REQUESTED", "reason": "CYCLING"}

  return params, calls, HankOwnerUIModel(params, requester=request)


@pytest.mark.parametrize(("owner", "visible_state", "target", "profile_role"), [
  ("HANK", "CURRENT_HANK", "TSS", "active"),
  ("TSS", "CURRENT_TSS", "HANK", "stored_future"),
])
def test_confirmed_owner_display_and_action(rig, owner, visible_state, target, profile_role):
  params, _, ui = rig
  put_authority(params, transaction(owner))
  view = ui.state(cp_for(owner))
  assert (view.state, view.current_owner, view.action_target) == (visible_state, owner, target)
  assert view.action_enabled
  assert view.profile_role == profile_role


@pytest.mark.parametrize("value,gate", [(None, False), (transaction("HANK"), False), (transaction(None, "UNVERIFIED"), False)])
def test_unverified_never_presents_confirmed_owner(rig, value, gate):
  params, _, ui = rig
  if value is not None:
    put_authority(params, value, gate)
  view = ui.state(cp_for())
  assert view.state == "UNVERIFIED"
  assert view.current_owner is None
  assert not view.action_enabled
  assert "Verifying" in view.status


@pytest.mark.parametrize("state", ["REQUESTED", "CYCLING", "REINITIALIZING", "VERIFYING"])
def test_pending_states_show_previous_and_target_without_actions(rig, state):
  params, _, ui = rig
  put_authority(params, transaction("HANK", state, "TSS"), gate=False)
  view = ui.state(cp_for("TSS"))
  assert (view.state, view.current_owner, view.target_owner) == (state, "HANK", "TSS")
  assert "in progress" in view.status
  assert not view.action_enabled
  assert not view.cancel_available


def test_failed_state_has_reboot_only_and_runtime_unverified(rig):
  params, _, ui = rig
  put_authority(params, transaction("HANK", "SWITCH_FAILED", "TSS"), gate=False)
  view = ui.state(cp_for("HANK"))
  assert view.state == "SWITCH_FAILED"
  assert (view.current_owner, view.target_owner) == ("HANK", "TSS")
  assert "NOT verified" in view.detail
  assert view.reboot_available
  assert not view.retry_available
  assert not view.action_enabled


@pytest.mark.parametrize("owner,target", [("HANK", "TSS"), ("TSS", "HANK")])
def test_opposite_request_uses_only_coordinator_transport(rig, owner, target):
  params, calls, ui = rig
  put_authority(params, transaction(owner))
  before = {key: params.get(key) for key in (ho.OWNER, ho.STATE, ho.GATE, ho.CYCLE)}
  response = ui.request(target, cp_for(owner))
  after = {key: params.get(key) for key in before}
  assert response == "REQUESTED"
  assert calls == [(target, 3.0)]
  assert after == before


def test_same_owner_is_local_no_op_without_transport(rig):
  params, calls, ui = rig
  put_authority(params, transaction("HANK"))
  assert ui.request("HANK", cp_for("HANK")) == "NO_OP"
  assert calls == []


@pytest.mark.parametrize(("result", "expected"), [
  ("BLOCKED_ENGAGED", "Driver control required"),
  ("BLOCKED_STALE_OR_INVALID", "Fresh vehicle data required"),
  ("BLOCKED_UNVERIFIED", "Owner verification required"),
  ("BLOCKED_OFFROAD", "Vehicle must be onroad"),
])
def test_blocked_response_is_presented_without_retry(rig, result, expected):
  params, _, ui = rig
  put_authority(params, transaction("HANK"))
  ui.requester = lambda *_args, **_kwargs: {"result": result, "reason": result}
  assert ui.request("TSS", cp_for("HANK")) == result
  view = ui.state(cp_for("HANK"))
  assert view.state == result
  assert expected in view.detail
  assert view.action_enabled  # A later manual request is allowed; there is no automatic retry.
  assert not view.retry_available


@pytest.mark.parametrize("failure", ["unavailable", "timeout", "malformed"])
def test_transport_failure_never_falls_back_to_params(rig, failure):
  params, _, ui = rig
  put_authority(params, transaction("HANK"))
  before = {key: params.get(key) for key in (ho.OWNER, ho.STATE, ho.GATE, ho.CYCLE)}
  if failure == "unavailable":
    ui.requester = lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline"))
  elif failure == "timeout":
    ui.requester = lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("late"))
  else:
    ui.requester = lambda *_args, **_kwargs: {"unexpected": True}
  assert ui.request("TSS", cp_for("HANK")) == ("TRANSPORT_TIMEOUT" if failure == "timeout" else "TRANSPORT_UNAVAILABLE")
  assert {key: params.get(key) for key in before} == before


def test_unsupported_vehicle_hides_selector(rig):
  params, calls, ui = rig
  put_authority(params, transaction("HANK"))
  view = ui.state(cp_for(supported=False))
  assert not view.visible
  assert not view.action_enabled
  assert ui.request("TSS", cp_for(supported=False)) == "UNSUPPORTED"
  assert calls == []


def test_switch_does_not_modify_cfg_or_dynamic_follow(rig):
  params, _, ui = rig
  initialize_session(params)
  put_authority(params, transaction("HANK"))
  before = (params.get("HankConfigRequested"), params.get("HankConfigActive"), params.get("HankDynamicFollowActive"))
  ui.request("TSS", cp_for("HANK"))
  assert (params.get("HankConfigRequested"), params.get("HankConfigActive"), params.get("HankDynamicFollowActive")) == before


def test_ui_model_has_no_direct_write_retry_or_cancel_api(rig):
  _, _, ui = rig
  assert not hasattr(ui, "set_owner_param")
  assert not hasattr(ui, "retry")
  assert not hasattr(ui, "cancel")


def test_onroad_and_settings_share_same_request_method(rig):
  _, _, ui = rig
  assert ui.onroad_request == ui.request
  assert ui.settings_request == ui.request


def test_confirmation_text_states_driver_and_lifecycle_constraints(rig):
  text = rig[2].confirmation_text("TSS")
  assert all(part in text for part in ("driver", "disengaged", "Offroad", "Onroad", "verification"))


def test_request_refreshes_display_after_transaction_progress(rig):
  params, _, ui = rig
  put_authority(params, transaction("HANK"))

  def request(_params, _target, timeout=3.0):
    put_authority(params, transaction("HANK", "CYCLING", "TSS"), gate=False)
    return {"result": "REQUESTED", "reason": "CYCLING"}

  ui.requester = request
  assert ui.request("TSS", cp_for("HANK")) == "REQUESTED"
  assert ui.state(cp_for("TSS")).state == "CYCLING"
