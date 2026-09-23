"""D-024 owner transaction authority. Only the manager-owned coordinator writes it."""
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from cereal import car
from opendbc.car.toyota.values import CAR, ToyotaSafetyFlags
from openpilot.selfdrive.controls.lib.hank_config import ReadState, read_raw

STATE = "HankOwnerSwitchState"
GATE = "HankOwnerSessionVerified"
OWNER = "dp_toyota_stock_lon"
CYCLE = "OnroadCycleRequested"
TARGET_CAR = str(CAR.TOYOTA_SIENNA_4TH_GEN)
OWNERS = ("HANK", "TSS")
STATES = ("UNVERIFIED", "CONFIRMED", "REQUESTED", "CYCLING", "REINITIALIZING", "VERIFYING", "SWITCH_FAILED")
IN_FLIGHT = ("REQUESTED", "CYCLING", "REINITIALIZING", "VERIFYING")
TIMEOUT_NS = 90_000_000_000
BOOT_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def valid_boot_id(value):
  return type(value) is str and BOOT_PATTERN.fullmatch(value) is not None


def read_boot_id():
  value = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
  if not valid_boot_id(value):
    raise ValueError("invalid kernel boot ID")
  return value


@dataclass(frozen=True)
class Transaction:
  version: int
  confirmed_owner: str | None
  target_owner: str | None
  state: str
  failure_boot_id: str | None


def validate_state(value):
  if type(value) is not dict or set(value) != set(Transaction.__dataclass_fields__):
    raise ValueError("expected exact five-key owner transaction")
  if type(value["version"]) is not int or value["version"] != 1:
    raise ValueError("owner transaction version must be integer 1")
  state, previous, target, boot = (value[k] for k in ("state", "confirmed_owner", "target_owner", "failure_boot_id"))
  if type(state) is not str or state not in STATES:
    raise ValueError("invalid owner state")
  if previous is not None and (type(previous) is not str or previous not in OWNERS):
    raise ValueError("invalid confirmed owner")
  if state != "UNVERIFIED" and previous is None:
    raise ValueError("confirmed owner required")
  if state in ("UNVERIFIED", "CONFIRMED"):
    if target is not None:
      raise ValueError("target must be null")
  elif type(target) is not str or target not in OWNERS or target == previous:
    raise ValueError("transaction requires opposite target")
  if state == "SWITCH_FAILED":
    if not valid_boot_id(boot):
      raise ValueError("failed transaction requires valid failure_boot_id")
  elif boot is not None:
    raise ValueError("failure_boot_id must be null outside SWITCH_FAILED")
  return Transaction(**value)


def unique_object(pairs):
  value = {}
  for key, item in pairs:
    if key in value:
      raise ValueError("duplicate owner transaction key")
    value[key] = item
  return value


def parse_state(raw):
  return validate_state(json.loads(raw, object_pairs_hook=unique_object))


def serialize_state(state):
  value = asdict(state)
  validate_state(value)
  return json.dumps(value, separators=(",", ":"), allow_nan=False)


def raw_value(params, key):
  result = read_raw(params, key)
  if result.state == ReadState.IO_ERROR:
    raise OSError(f"{key}: {result.reason}")
  return result.value if result.state == ReadState.VALID else None


def read_state(params):
  raw = raw_value(params, STATE)
  return parse_state(raw) if raw is not None else None


def owner_value(params):
  raw = raw_value(params, OWNER)
  if raw not in (b"0", b"1"):
    raise ValueError("owner Param missing or malformed")
  return "TSS" if raw == b"1" else "HANK"


def supported(cp):
  return cp.brand == "toyota" and cp.carFingerprint == TARGET_CAR


def cp_reason(cp, owner):
  if not supported(cp):
    return "UNSUPPORTED_VEHICLE"
  if cp.openpilotLongitudinalControl != (owner == "HANK"):
    return "CARPARAMS_OWNER_MISMATCH"
  if not cp.safetyConfigs:
    return "MISSING_SAFETY_CONFIG"
  toyota = [s for s in cp.safetyConfigs if s.safetyModel == car.CarParams.SafetyModel.toyota]
  if not toyota:
    return "MISSING_TOYOTA_SAFETY"
  if any(bool(s.safetyParam & ToyotaSafetyFlags.STOCK_LONGITUDINAL) != (owner == "TSS") for s in toyota):
    return "TOYOTA_STOCK_LONG_MISMATCH"
  return None


def interlock_reason(params, cp):
  """Independent synchronous reader; never sets a gate or changes ownership."""
  if not supported(cp):
    return None
  try:
    if raw_value(params, GATE) != b"1":
      return "OWNER_SESSION_UNVERIFIED"
    state = read_state(params)
    if state is None or state.state != "CONFIRMED":
      return "OWNER_TRANSACTION_NOT_CONFIRMED"
    if owner_value(params) != state.confirmed_owner:
      return "OWNER_PARAM_MISMATCH"
    return cp_reason(cp, state.confirmed_owner)
  except (OSError, ValueError, TypeError, RecursionError):
    return "OWNER_EVIDENCE_UNREADABLE"


@dataclass(frozen=True)
class Sample:
  value: object
  mono_ns: int
  valid: bool


@dataclass(frozen=True)
class Evidence:
  now_ns: int
  samples: dict[str, Sample]

  def fresh(self, topic, after_ns=0):
    sample = self.samples.get(topic)
    max_age = 55_000_000_000 if topic == "carParams" else 2_000_000_000 if topic == "deviceState" else 1_000_000_000
    return (sample is not None and sample.valid and sample.mono_ns > after_ns
            and 0 <= self.now_ns - sample.mono_ns <= max_age)

  def idle_reason(self, after_ns=0):
    if not all(self.fresh(topic, after_ns) for topic in ("deviceState", "selfdriveState", "carControl", "carState")):
      return "BLOCKED_STALE_OR_INVALID"
    if not self.samples["deviceState"].value.started:
      return "BLOCKED_OFFROAD"
    sd, cc, cs = (self.samples[k].value for k in ("selfdriveState", "carControl", "carState"))
    if sd.enabled or cc.enabled or cc.latActive or cc.longActive or cs.cruiseState.enabled:
      return "BLOCKED_ENGAGED"
    return None


class OwnerCoordinator:
  """Single manager-thread writer, kept alive across onroad cycles.

  A process restart cannot resume in-flight transitions from RAM: it rolls back
  and records SWITCH_FAILED. Only different-boot recovery can clear that failure.
  """
  def __init__(self, params, boot_id_reader=read_boot_id):
    self.params = params
    self.boot_id_reader = boot_id_reader
    self.state = None
    self.reason = "INITIALIZING"
    self.fault = False
    self.epoch_ns = 0
    self.clear_ns = 0
    self.request_epoch = 0
    self.request_ns = 0
    self.offroad_seen = False
    self.verified = False
    try:
      self._gate(False)
      self.state = read_state(params)
      if self.state is None:
        self._persist(Transaction(1, None, None, "UNVERIFIED", None))
      elif self.state.state in IN_FLIGHT:
        self._fail("INTERRUPTED_TRANSACTION")
    except (OSError, ValueError, TypeError, RecursionError) as error:
      self.fault = True
      self.reason = str(error)

  def _gate(self, enabled):
    self.params.put(GATE, enabled)
    if raw_value(self.params, GATE) != (b"1" if enabled else b"0"):
      raise OSError("session gate readback mismatch")
    if not enabled:
      self.verified = False

  def _persist(self, state):
    value = json.loads(serialize_state(state))
    self.params.put(STATE, value)
    if read_state(self.params) != state:
      raise OSError("owner transaction readback mismatch")
    self.state = state

  def _write_owner(self, owner):
    self.params.put(OWNER, owner == "TSS")
    if owner_value(self.params) != owner:
      raise OSError("owner Param readback mismatch")

  def _fail(self, reason):
    self.reason = reason
    self.fault = True
    try:
      self._gate(False)
    except (OSError, ValueError):
      pass
    if self.state is None:
      return
    if self.state.confirmed_owner is None or self.state.target_owner is None:
      return
    try:
      self._write_owner(self.state.confirmed_owner)
    except (OSError, ValueError) as error:
      self.reason += f"; ROLLBACK_FAILED: {error}"
    try:
      boot = self.boot_id_reader()
      failed = Transaction(1, self.state.confirmed_owner, self.state.target_owner, "SWITCH_FAILED", boot)
      self._persist(failed)
    except (OSError, ValueError) as error:
      self.reason += f"; FAILURE_PERSISTENCE_FAILED: {error}"

  def _invalidate(self, reason):
    self.reason, self.fault = reason, True
    self._gate(False)
    if self.state is not None and self.state.state == "CONFIRMED":
      self._persist(Transaction(1, self.state.confirmed_owner, None, "UNVERIFIED", None))

  def session_cleared(self, epoch_ns, clear_ns):
    """Called by manager immediately after its real onroad Params clear."""
    if raw_value(self.params, "CarParams") is not None or epoch_ns <= 0 or clear_ns < epoch_ns:
      self._invalidate("UNPROVEN_CARPARAMS_CLEAR")
      return
    self._gate(False)
    self.epoch_ns, self.clear_ns = epoch_ns, clear_ns

  def _verification_reason(self, evidence, owner, idle=True):
    if self.epoch_ns <= 0 or not self.clear_ns:
      return "WAIT_SESSION_CLEAR"
    topics = ("deviceState", "carParams", "pandaStates", "selfdriveState", "carControl", "carState")
    if not all(evidence.fresh(topic, self.clear_ns) for topic in topics):
      return "WAIT_FRESH_CURRENT_SESSION_DATA"
    device = evidence.samples["deviceState"].value
    if not device.started or device.startedMonoTime != self.epoch_ns:
      return "WAIT_CURRENT_ONROAD_EPOCH"
    if owner_value(self.params) != owner:
      return "OWNER_PARAM_MISMATCH"
    raw_cp = raw_value(self.params, "CarParams")
    if raw_cp is None:
      return "WAIT_CARPARAMS"
    try:
      with car.CarParams.from_bytes(raw_cp) as cp:
        published = evidence.samples["carParams"].value
        if cp.to_dict() != published.to_dict():
          return "CARPARAMS_PUBLICATION_MISMATCH"
        reason = cp_reason(cp, owner)
        if reason:
          return reason
        pandas = evidence.samples["pandaStates"].value
        if not pandas or len(pandas) != len(cp.safetyConfigs):
          return "PANDA_COUNT_MISMATCH"
        for panda, safety in zip(pandas, cp.safetyConfigs, strict=True):
          if (panda.safetyModel != safety.safetyModel or panda.safetyParam != safety.safetyParam
              or panda.alternativeExperience != cp.alternativeExperience):
            return "PANDA_SAFETY_MISMATCH"
    except Exception:
      return "CARPARAMS_UNREADABLE"
    return evidence.idle_reason(self.clear_ns) if idle else None

  def _confirm(self, owner):
    # Owner must still agree immediately before the two ordered, read-back writes.
    if owner_value(self.params) != owner:
      raise OSError("owner changed before confirmation")
    self._persist(Transaction(1, owner, None, "CONFIRMED", None))
    try:
      self._gate(True)
    except (OSError, ValueError):
      self._gate(False)
      raise
    self.verified = True
    self.reason = "CONFIRMED"

  def request(self, target, observe):
    if type(target) is not str or target not in OWNERS:
      return "BLOCKED_INVALID_TARGET"
    if self.fault or self.state is None or self.state.state != "CONFIRMED" or not self.verified:
      return "BLOCKED_UNVERIFIED"
    if target == self.state.confirmed_owner:
      return "NO_OP"
    first = observe()
    reason = first.idle_reason(self.clear_ns)
    if reason:
      return reason
    reason = self._verification_reason(first, self.state.confirmed_owner)
    if reason:
      return f"BLOCKED_{reason}"
    previous = self.state.confirmed_owner
    attempted = Transaction(1, previous, target, "REQUESTED", None)
    try:
      if read_state(self.params) != self.state or raw_value(self.params, GATE) != b"1":
        return "BLOCKED_AUTHORITY_CHANGED"
      self._gate(False)
      second = observe()
      reason = second.idle_reason(self.clear_ns)
      if reason:
        self._invalidate(reason)
        return reason
      self._persist(Transaction(1, previous, target, "REQUESTED", None))
      # Recheck complete evidence and owner, as well as idle predicates, just
      # before touching the owner Param. No stale cached UI precondition.
      latest = observe()
      reason = self._verification_reason(latest, previous)
      if reason:
        raise ValueError(reason)
      self._write_owner(target)
      self._persist(Transaction(1, previous, target, "CYCLING", None))
      self.request_epoch, self.request_ns = self.epoch_ns, latest.now_ns
      self.offroad_seen = False
      self.params.put(CYCLE, True)  # hardwared may consume immediately; no retry/readback inference.
      self.reason = "CYCLING"
      return "REQUESTED"
    except (OSError, ValueError, TypeError) as error:
      if self.state.target_owner is None:
        self.state = attempted
      self._fail(str(error))
      return "SWITCH_FAILED"

  def tick(self, evidence):
    if self.state is None:
      return
    try:
      if self.fault:
        return
      if read_state(self.params) != self.state:
        self._invalidate("TRANSACTION_CHANGED_OUT_OF_BAND")
        return
      if self.state.state in IN_FLIGHT and evidence.now_ns - self.request_ns >= TIMEOUT_NS:
        self._fail("TRANSACTION_TIMEOUT")
        return
      if not evidence.fresh("deviceState"):
        if self.state.state in IN_FLIGHT:
          self._fail("DEVICE_STATE_UNAVAILABLE")
        elif self.verified:
          self._invalidate("DEVICE_STATE_UNAVAILABLE")
        return
      device = evidence.samples["deviceState"].value
      if not device.started:
        if self.verified:
          self._gate(False)
        if self.state.state == "CYCLING":
          self.offroad_seen = True
        return
      if self.state.state == "CYCLING":
        if (self.offroad_seen and device.startedMonoTime > self.request_epoch
            and device.startedMonoTime == self.epoch_ns and self.clear_ns > self.request_ns):
          self._persist(replace_state(self.state, "REINITIALIZING"))
        else:
          return
      if self.state.state == "SWITCH_FAILED":
        boot = self.boot_id_reader()
        if not valid_boot_id(boot) or boot == self.state.failure_boot_id:
          self.reason = "FULL_REBOOT_REQUIRED"
          return
        owner = self.state.confirmed_owner
      elif self.state.state in IN_FLIGHT:
        owner = self.state.target_owner
      else:
        owner = self.state.confirmed_owner or owner_value(self.params)
      if self.verified and raw_value(self.params, GATE) != b"1":
        self._invalidate("SESSION_GATE_INVALIDATED")
        return
      reason = self._verification_reason(evidence, owner, idle=not self.verified)
      if reason:
        self.reason = reason
        if self.state.state in IN_FLIGHT and not reason.startswith("WAIT_"):
          self._fail(reason)
        elif self.verified:
          self._invalidate(reason)
        return
      if not self.verified:
        pending = self.state
        if self.state.state in IN_FLIGHT:
          self._persist(replace_state(self.state, "VERIFYING"))
        try:
          self._confirm(owner)
        except (OSError, ValueError) as error:
          # Retain previous owner/target if the final state/gate write fails.
          # A recovery write failure is a new failure in the current boot.
          self.state = pending
          if pending.state in IN_FLIGHT or pending.state == "SWITCH_FAILED":
            self._fail(str(error))
            return
          raise
    except (OSError, ValueError, TypeError, RecursionError) as error:
      if self.state.state in IN_FLIGHT:
        self._fail(str(error))
      else:
        self.reason = str(error)
        self._gate(False)


def replace_state(state, name):
  return Transaction(1, state.confirmed_owner, state.target_owner, name, None)
