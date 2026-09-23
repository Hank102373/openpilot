"""D-024 UI presentation and the sole UI request path to the owner coordinator."""
from dataclasses import dataclass

from openpilot.selfdrive.selfdrived.hank_owner import GATE, IN_FLIGHT, read_state, raw_value, supported
from openpilot.system.manager.hank_owner_service import request_owner


BLOCKED_DETAILS = {
  "BLOCKED_ENGAGED": "Driver control required; disengage selfdrive and ACC.",
  "BLOCKED_STALE_OR_INVALID": "Fresh vehicle data required before switching.",
  "BLOCKED_OFFROAD": "Vehicle must be onroad before requesting a switch.",
  "BLOCKED_UNVERIFIED": "Owner verification required before switching.",
  "BLOCKED_AUTHORITY_CHANGED": "Owner authority changed; wait for verification.",
  "BLOCKED_INVALID_TARGET": "Invalid owner request.",
}


@dataclass(frozen=True)
class HankOwnerDisplay:
  visible: bool
  state: str
  current_owner: str | None
  target_owner: str | None
  status: str
  detail: str
  action_target: str | None
  action_label: str
  action_enabled: bool
  reboot_available: bool
  retry_available: bool
  cancel_available: bool
  profile_role: str


class HankOwnerUIModel:
  """Read-only authority projection plus coordinator transport.

  Neither this model nor its UI callers write owner, transaction, gate, or
  lifecycle Params. Safety eligibility is decided exclusively by coordinator.
  """
  def __init__(self, params, requester=request_owner):
    self.params = params
    self.requester = requester
    self.last_result = None
    self.last_reason = None

  @staticmethod
  def confirmation_text(target):
    return (f"Switch longitudinal owner to {target}? The driver must have control " +
            "and selfdrive/ACC must be disengaged. The system will perform an " +
            "Offroad -> Onroad lifecycle restart. Control remains blocked until " +
            "coordinator verification succeeds.")

  @staticmethod
  def _unavailable():
    return HankOwnerDisplay(False, "UNAVAILABLE", None, None, "", "", None, "", False,
                            False, False, False, "unavailable")

  @staticmethod
  def _unverified(detail="Owner/session evidence is not confirmed."):
    return HankOwnerDisplay(True, "UNVERIFIED", None, None, "Verifying HANK/TSS ownership",
                            detail, None, "Verifying", False, False, False, False, "unavailable")

  def state(self, cp):
    try:
      if cp is None or not supported(cp):
        return self._unavailable()
      transaction = read_state(self.params)
      gate = raw_value(self.params, GATE) == b"1"
    except (OSError, ValueError, TypeError, RecursionError):
      return self._unverified("Owner authority unavailable; engagement remains blocked.")

    if transaction is None:
      return self._unverified()
    if transaction.state == "SWITCH_FAILED":
      return HankOwnerDisplay(
        True, "SWITCH_FAILED", transaction.confirmed_owner, transaction.target_owner,
        "Switch failed",
        (f"Previous owner: {transaction.confirmed_owner}; failed target: {transaction.target_owner}. " +
         "Runtime owner is NOT verified; engagement remains blocked. Full C3X reboot required."),
        None, "Reboot", False, True, False, False, "stored_future",
      )
    if transaction.state in IN_FLIGHT:
      return HankOwnerDisplay(
        True, transaction.state, transaction.confirmed_owner, transaction.target_owner,
        f"Switch in progress: {transaction.state}",
        f"Current confirmed owner: {transaction.confirmed_owner}; target: {transaction.target_owner}.",
        None, transaction.state.title(), False, False, False, False,
        "active" if transaction.confirmed_owner == "HANK" else "stored_future",
      )
    if transaction.state != "CONFIRMED" or not gate:
      return self._unverified()

    owner = transaction.confirmed_owner
    target = "TSS" if owner == "HANK" else "HANK"
    if self.last_result in BLOCKED_DETAILS or (self.last_result is not None and self.last_result.startswith("BLOCKED_")):
      detail = BLOCKED_DETAILS.get(self.last_result, self.last_reason or "Owner switch request blocked.")
      return HankOwnerDisplay(
        True, self.last_result, owner, None, "Owner switch blocked", detail,
        target, f"Switch to {target}", True, False, False, False,
        "active" if owner == "HANK" else "stored_future",
      )
    if self.last_result in ("TRANSPORT_UNAVAILABLE", "TRANSPORT_TIMEOUT"):
      detail = ("Coordinator request timed out." if self.last_result == "TRANSPORT_TIMEOUT"
                else "Owner coordinator unavailable.")
      return HankOwnerDisplay(
        True, self.last_result, owner, None, "Owner switch unavailable", detail,
        target, f"Switch to {target}", True, False, False, False,
        "active" if owner == "HANK" else "stored_future",
      )
    return HankOwnerDisplay(
      True, f"CURRENT_{owner}", owner, None, f"{owner} longitudinal owner verified",
      "HANK profile is active." if owner == "HANK" else "HANK profile stored for future HANK use.",
      target, f"Switch to {target}", True, False, False, False,
      "active" if owner == "HANK" else "stored_future",
    )

  def request(self, target, cp):
    view = self.state(cp)
    if not view.visible:
      self.last_result, self.last_reason = "UNSUPPORTED", "Unsupported vehicle"
      return self.last_result
    if view.current_owner == target and view.state.startswith("CURRENT_"):
      self.last_result, self.last_reason = "NO_OP", "Already confirmed"
      return self.last_result
    if not view.state.startswith("CURRENT_") and not view.state.startswith("BLOCKED_") and not view.state.startswith("TRANSPORT_"):
      self.last_result, self.last_reason = "BLOCKED_UNVERIFIED", "Owner state does not accept requests"
      return self.last_result
    if target != view.action_target:
      self.last_result, self.last_reason = "BLOCKED_INVALID_TARGET", "Invalid target"
      return self.last_result
    try:
      response = self.requester(self.params, target, timeout=3.0)
      if (type(response) is not dict or set(response) != {"result", "reason"}
          or type(response["result"]) is not str or type(response["reason"]) is not str):
        raise ValueError("malformed coordinator response")
      self.last_result = response["result"]
      self.last_reason = response["reason"]
    except TimeoutError:
      self.last_result, self.last_reason = "TRANSPORT_TIMEOUT", "Coordinator timeout"
    except (OSError, ValueError, TypeError, UnicodeError):
      self.last_result, self.last_reason = "TRANSPORT_UNAVAILABLE", "Coordinator unavailable"
    return self.last_result

  onroad_request = request
  settings_request = request
