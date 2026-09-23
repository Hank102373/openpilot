"""CFG-01 v1 selection schema and single-owner session snapshot contract.

plannerd integration is separate. Call initialize_session once, before planner
construction; never retry a failed initialization inside the same session.
"""
from dataclasses import asdict, dataclass
from enum import Enum
import json
from pathlib import Path

from cereal import log


REQUESTED = "HankConfigRequested"
ACTIVE = "HankConfigActive"
LATCH = "HankConfigSessionStarted"
LEGACY_REQUESTED = "HankDynamicFollow"
LEGACY_ACTIVE = "HankDynamicFollowActive"


class ConfigValidationError(ValueError):
  pass


class SessionError(RuntimeError):
  """Initialization failed; the owner must wait for a new lifecycle session."""


@dataclass(frozen=True)
class HankConfig:
  version: int = 1
  dynamic_follow: bool = False
  accel_profile: int = 3


@dataclass(frozen=True)
class HankConfigV2:
  version: int = 2
  dynamic_follow: bool = False
  hank_profile: str = "original"
  accel_profile: int = 3


Config = HankConfig | HankConfigV2
STOCK_CONFIG = HankConfig()
ORIGINAL_CONFIG = HankConfigV2()
PROFILE_ACCEL = {"compact": 0, "normal": 1, "comfortable": 2, "original": 3}
PROFILE_PERSONALITY = {
  "compact": log.LongitudinalPersonality.aggressive,
  "normal": log.LongitudinalPersonality.standard,
  "comfortable": log.LongitudinalPersonality.relaxed,
  "original": log.LongitudinalPersonality.standard,
}
NEXT_PROFILE = {"compact": "normal", "normal": "comfortable", "comfortable": "compact"}


def _validate(value):
  if type(value) is not dict or type(value.get("version")) is not int:
    raise ConfigValidationError("expected a versioned config object")
  if value["version"] == 1:
    if set(value) != {"version", "dynamic_follow", "accel_profile"}:
      raise ConfigValidationError("expected exactly version, dynamic_follow, accel_profile")
    config_type = HankConfig
  elif value["version"] == 2:
    if set(value) != {"version", "dynamic_follow", "hank_profile", "accel_profile"}:
      raise ConfigValidationError("expected exactly version, dynamic_follow, hank_profile, accel_profile")
    if type(value["hank_profile"]) is not str or value["hank_profile"] not in PROFILE_ACCEL:
      raise ConfigValidationError("invalid hank_profile")
    if type(value["accel_profile"]) is not int or value["accel_profile"] != PROFILE_ACCEL[value["hank_profile"]]:
      raise ConfigValidationError("accel_profile does not match hank_profile")
    config_type = HankConfigV2
  else:
    raise ConfigValidationError("unsupported version")
  if type(value["dynamic_follow"]) is not bool:
    raise ConfigValidationError("dynamic_follow must be boolean")
  if type(value["accel_profile"]) is not int or value["accel_profile"] not in (0, 1, 2, 3):
    raise ConfigValidationError("accel_profile must be integer 0, 1, 2, or 3")
  return config_type(**value)


def base_personality(config: Config):
  """Return None for v1: that schema never recorded a personality."""
  return PROFILE_PERSONALITY[config.hank_profile] if isinstance(config, HankConfigV2) else None


def _unique_object(pairs):
  result = {}
  for key, value in pairs:
    if key in result:
      raise ConfigValidationError(f"duplicate key: {key}")
    result[key] = value
  return result


def _reject_constant(value):
  raise ConfigValidationError(f"non-standard JSON numeric value: {value}")


def parse_config(raw: bytes | str) -> Config:
  try:
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    value = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    return _validate(value)
  except (ValueError, TypeError, RecursionError) as error:
    raise ConfigValidationError(str(error)) from error


def serialize_config(config: Config) -> str:
  if not isinstance(config, (HankConfig, HankConfigV2)):
    raise ConfigValidationError("expected a complete HankConfig")
  value = asdict(config)
  _validate(value)
  return json.dumps(value, allow_nan=False, separators=(",", ":"))


class ReadState(Enum):
  MISSING = "MISSING"
  VALID = "VALID"
  CORRUPT = "CORRUPT"
  IO_ERROR = "IO_ERROR"


@dataclass(frozen=True)
class ReadResult:
  state: ReadState
  value: bytes | Config | None = None
  reason: str = ""


def read_raw(params, key: str) -> ReadResult:
  path = Path(params.get_param_path(key))
  try:
    return ReadResult(ReadState.VALID, path.read_bytes())
  except FileNotFoundError as error:
    # ENOENT must mean an absent key, not a lost storage directory or dangling key.
    try:
      path.parent.stat()
      try:
        path.lstat()
      except FileNotFoundError:
        return ReadResult(ReadState.MISSING)
    except OSError as storage_error:
      return ReadResult(ReadState.IO_ERROR, reason=str(storage_error))
    return ReadResult(ReadState.IO_ERROR, reason=str(error))
  except OSError as error:
    return ReadResult(ReadState.IO_ERROR, reason=str(error))


def read_config(params, key: str) -> ReadResult:
  result = read_raw(params, key)
  if result.state != ReadState.VALID:
    return result
  try:
    return ReadResult(ReadState.VALID, parse_config(result.value))
  except ConfigValidationError as error:
    return ReadResult(ReadState.CORRUPT, reason=str(error))


def read_latch(params) -> ReadResult:
  result = read_raw(params, LATCH)
  if result.state == ReadState.VALID and result.value != b"1":
    return ReadResult(ReadState.CORRUPT, reason="session latch must be raw 1")
  return result


def _require_no_io(result: ReadResult, key: str):
  if result.state == ReadState.IO_ERROR:
    raise SessionError(f"IO_ERROR {key}: {result.reason}")


def _put(params, key, value):
  try:
    params.put(key, value)
  except OSError as error:
    raise SessionError(f"IO_ERROR writing {key}: {error}") from error


def _save_config(params, key: str, config: Config) -> Config:
  # Validate before any write. Params.put performs the single atomic JSON write.
  value = json.loads(serialize_config(config))
  _put(params, key, value)
  result = read_config(params, key)
  _require_no_io(result, key)
  if result.state != ReadState.VALID or result.value != config:
    raise SessionError(f"REJECT_AND_WAIT_NEW_SESSION: {key} readback mismatch ({result.state.value})")
  return result.value


def save_requested(params, config: Config) -> Config:
  """Save a complete candidate; never mutate Active or the session latch."""
  return _save_config(params, REQUESTED, config)


def restore_stock(params) -> HankConfig:
  """Preserve the CFG-01 v1 stock API for existing callers."""
  return save_requested(params, STOCK_CONFIG)


def restore_original(params) -> HankConfigV2:
  """Advanced v2 reset; applies on the next legitimate session."""
  return save_requested(params, ORIGINAL_CONFIG)


def _current_requested(params) -> Config:
  result = read_config(params, REQUESTED)
  _require_no_io(result, REQUESTED)
  if result.state == ReadState.MISSING:
    return STOCK_CONFIG
  if result.state != ReadState.VALID:
    raise ConfigValidationError(f"invalid Requested: {result.reason}")
  return result.value


def save_profile(params, profile: str) -> HankConfigV2:
  if type(profile) is not str or profile not in NEXT_PROFILE:
    raise ConfigValidationError("expected one of the three HANK profiles")
  previous = _current_requested(params)
  return save_requested(params, HankConfigV2(dynamic_follow=previous.dynamic_follow,
                                             hank_profile=profile, accel_profile=PROFILE_ACCEL[profile]))


def cycle_requested_profile(params) -> HankConfigV2:
  previous = _current_requested(params)
  current = previous.hank_profile if isinstance(previous, HankConfigV2) else "original"
  profile = NEXT_PROFILE.get(current, "compact")
  return save_requested(params, HankConfigV2(dynamic_follow=previous.dynamic_follow,
                                             hank_profile=profile, accel_profile=PROFILE_ACCEL[profile]))


def set_requested_dynamic_follow(params, enabled: bool) -> Config:
  if type(enabled) is not bool:
    raise ConfigValidationError("dynamic_follow must be boolean")
  previous = _current_requested(params)
  value = asdict(previous)
  value["dynamic_follow"] = enabled
  return save_requested(params, _validate(value))


@dataclass(frozen=True)
class SessionSnapshot:
  action: str
  config: Config
  reason: str


def _requested_for_new_session(params) -> tuple[Config, str]:
  requested = read_config(params, REQUESTED)
  _require_no_io(requested, REQUESTED)
  if requested.state == ReadState.VALID:
    return requested.value, "REQUESTED"
  if requested.state == ReadState.CORRUPT:
    # Preserve the corrupt original for diagnosis; this recovery is explicit.
    return ORIGINAL_CONFIG, f"RECOVERED_CORRUPT_REQUESTED: {requested.reason}"

  legacy = read_raw(params, LEGACY_REQUESTED)
  _require_no_io(legacy, LEGACY_REQUESTED)
  if legacy.state == ReadState.MISSING:
    config, reason = STOCK_CONFIG, "DEFAULT_NO_REQUEST"
  elif legacy.value in (b"0", b"1"):
    config = HankConfig(dynamic_follow=legacy.value == b"1")
    reason = "MIGRATED_LEGACY"
  else:
    config, reason = STOCK_CONFIG, "RECOVERED_CORRUPT_LEGACY"
  save_requested(params, config)
  return config, reason


def initialize_session(params) -> SessionSnapshot:
  """Reuse a valid pair, or initialize only after the legacy Active guard.

  This is a single-owner operation, not a multi-writer transaction. Lifecycle
  clearing is external. No keys are removed and no lifecycle cycle is triggered.
  """
  active = read_config(params, ACTIVE)
  latch = read_latch(params)
  _require_no_io(active, ACTIVE)
  _require_no_io(latch, LATCH)
  if active.state == ReadState.VALID and latch.state == ReadState.VALID:
    return SessionSnapshot("REUSE_ACTIVE", active.value, "VALID_ACTIVE")
  if active.state != ReadState.MISSING or latch.state != ReadState.MISSING:
    raise SessionError("REJECT_AND_WAIT_NEW_SESSION: invalid Active/latch pair")

  legacy = read_raw(params, LEGACY_ACTIVE)
  _require_no_io(legacy, LEGACY_ACTIVE)
  if legacy.state != ReadState.MISSING:
    raise SessionError("REJECT_AND_WAIT_NEW_SESSION: legacy Active exists")

  try:
    _put(params, LATCH, True)
    latch = read_latch(params)
    _require_no_io(latch, LATCH)
    if latch.state != ReadState.VALID:
      raise SessionError("REJECT_AND_WAIT_NEW_SESSION: latch readback failed")
    config, reason = _requested_for_new_session(params)
    verified = _save_config(params, ACTIVE, config)
  except SessionError:
    # A mismatching but schema-valid Active must not become reusable on restart.
    # Mark the latch invalid; never delete it to reopen new-session initialization.
    # If storage itself has failed, the owner still must stop until a new session.
    try:
      _put(params, LATCH, False)
    except SessionError:
      pass
    raise
  return SessionSnapshot("NEW_SESSION", verified, reason)
