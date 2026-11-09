"""D-024 UI presentation and the sole UI request path to the owner coordinator."""
from dataclasses import dataclass
import socket
import time

from openpilot.selfdrive.selfdrived.hank_owner import Evidence, Sample, GATE, IN_FLIGHT, interlock_reason, read_state, raw_value, supported
from openpilot.system.manager.hank_owner_service import request_owner, socket_address


BLOCKED_DETAILS = {
  "BLOCKED_ENGAGED": "Driver control required; disengage selfdrive, ALKA and ACC.",
  "BLOCKED_STALE_OR_INVALID": "Fresh vehicle data required before switching.",
  "BLOCKED_OFFROAD": "Vehicle must be onroad before requesting a switch.",
  "BLOCKED_UNVERIFIED": "Owner verification required before switching.",
  "BLOCKED_AUTHORITY_CHANGED": "Owner authority changed; wait for verification.",
  "BLOCKED_INVALID_TARGET": "Invalid owner request.",
  "TRANSPORT_TIMEOUT": "Coordinator timed out; waiting for new safe evidence.",
  "TRANSPORT_UNAVAILABLE": "Coordinator unavailable; waiting for new safe evidence.",
}


UI_TOPICS = ("deviceState", "selfdriveState", "carControl", "carState", "managerState")


def owner_ui_evidence(sm):
  """Use existing UI subscriptions and the coordinator's timestamp/validity rules."""
  return Evidence(time.monotonic_ns(), {
    topic: Sample(sm[topic], sm.logMonoTime[topic], sm.valid[topic])
    for topic in UI_TOPICS if sm.seen.get(topic, False)
  })


def coordinator_available(params):
  # Connect only: no datagram, request, heartbeat protocol or Params write.
  # managerState is published after OwnerService.poll; a bound socket alone
  # does not prove the manager is making progress.
  with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
    try:
      client.connect(socket_address(params))
      return True
    except OSError:
      return False


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

  @property
  def hank_profile_active(self):
    # Switching may be blocked by active driving while Requested profile edits
    # remain allowed under D-023. Do not present in-flight/failed authority active.
    return self.current_owner == "HANK" and self.profile_role == "active" and self.state not in IN_FLIGHT


class HankOwnerUIModel:
  """Read-only authority projection plus coordinator transport.

  Neither this model nor its UI callers write owner, transaction, gate, or
  lifecycle Params. Safety eligibility is decided exclusively by coordinator.
  """
  def __init__(self, params, requester=request_owner, observer=lambda: None,
               transport_available=coordinator_available, clock_ns=time.monotonic_ns):
    self.params = params
    self.requester = requester
    self.observer = observer
    self.transport_available = transport_available
    self.clock_ns = clock_ns
    self._rejected_at = None
    self.last_result = None
    self.last_reason = None

  @staticmethod
  def confirmation_text(target):
    return (f"Switch to {target}? Take driver control with selfdrive, ALKA and ACC disengaged. " +
            "Offroad -> Onroad restart. Engagement stays blocked until owner verification succeeds.")

  @staticmethod
  def _unavailable():
    return HankOwnerDisplay(False, "UNAVAILABLE", None, None, "", "", None, "", False,
                            False, False, False, "unavailable")

  @staticmethod
  def _unverified(detail="Owner/session evidence is not confirmed."):
    return HankOwnerDisplay(True, "UNVERIFIED", None, None, "Verifying HANK/TSS ownership",
                            detail, None, "Verifying", False, False, False, False, "unavailable")

  def _eligibility(self, cp):
    """Advisory UI eligibility only; never grants owner/session authority."""
    if interlock_reason(self.params, cp) is not None:
      return "BLOCKED_AUTHORITY_CHANGED", BLOCKED_DETAILS["BLOCKED_AUTHORITY_CHANGED"]
    evidence = self.observer()
    if evidence is None:
      return "BLOCKED_STALE_OR_INVALID", BLOCKED_DETAILS["BLOCKED_STALE_OR_INVALID"]
    # Re-evaluate age at the call, including confirmation; never trust cached now.
    evidence = Evidence(self.clock_ns(), evidence.samples)
    reason = evidence.idle_reason()
    if reason:
      detail = BLOCKED_DETAILS[reason]
      if reason == "BLOCKED_ENGAGED":
        sd, cc, cs = (evidence.samples[k].value for k in ("selfdriveState", "carControl", "carState"))
        active = [name for name, enabled in (
          ("selfdrive", sd.enabled), ("control commands", cc.enabled),
          ("ALKA/lateral", cc.latActive), ("longitudinal commands", cc.longActive),
          ("factory ACC", cs.cruiseState.enabled),
        ) if enabled]
        detail = "Driver control required; active: " + ", ".join(active)
      return reason, detail
    if not evidence.fresh("managerState") or not self.transport_available(self.params):
      return "TRANSPORT_UNAVAILABLE", "Owner coordinator unavailable; waiting for fresh manager progress."
    if self._rejected_at is not None and not all(evidence.fresh(topic, self._rejected_at) for topic in UI_TOPICS):
      return self.last_result, BLOCKED_DETAILS.get(self.last_result, "Coordinator unavailable; waiting for new safe evidence.")
    return None, None

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
    rejected = self.last_result is not None and self.last_result.startswith(("BLOCKED_", "TRANSPORT_"))
    if rejected and self._rejected_at is None:
      self._rejected_at = self.clock_ns()
    try:
      reason, detail = self._eligibility(cp)
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
      reason, detail = "BLOCKED_STALE_OR_INVALID", BLOCKED_DETAILS["BLOCKED_STALE_OR_INVALID"]
    if reason:
      return HankOwnerDisplay(
        True, reason, owner, None, "Owner switch unavailable" if reason.startswith("TRANSPORT_") else "Owner switch blocked",
        detail, target, f"Switch to {target}", False, False, False, False,
        "unavailable" if reason == "BLOCKED_AUTHORITY_CHANGED" else "active" if owner == "HANK" else "stored_future",
      )
    # Fresh safe observations restore a manual confirmation, never replay target.
    if rejected:
      self.last_result, self.last_reason, self._rejected_at = None, None, None
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
    if not view.action_enabled:
      return view.state if view.state.startswith(("BLOCKED_", "TRANSPORT_")) else "BLOCKED_UNVERIFIED"
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
    if self.last_result.startswith(("BLOCKED_", "TRANSPORT_")):
      self._rejected_at = self.clock_ns()
    return self.last_result

  onroad_request = request
  settings_request = request
