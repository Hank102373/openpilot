"""UI-01 presentation and actions over the versioned HANK config authority."""
from dataclasses import dataclass
import time

from openpilot.selfdrive.controls.lib.hank_config import (HankConfigV2, ReadState, read_config, read_latch,
                                                          save_profile, cycle_requested_profile, set_requested_dynamic_follow, restore_original,
                                                          REQUESTED, ACTIVE, base_personality)


PROFILE_LABELS = {"compact": "緊湊", "normal": "一般", "comfortable": "舒適", "original": "Original"}


@dataclass(frozen=True)
class HankProfileDisplay:
  owner_label: str
  active_label: str
  requested_label: str
  pending: bool
  requested_dynamic_follow: bool | None
  hank_controls_longitudinal: bool
  error: str | None


class HankProfileUIModel:
  def __init__(self, params):
    self.params = params

  def select_mode(self, profile: str):
    return save_profile(self.params, profile)

  def cycle_mode(self):
    return cycle_requested_profile(self.params)

  def set_dynamic_follow(self, enabled: bool):
    return set_requested_dynamic_follow(self.params, enabled)

  def restore_original(self):
    return restore_original(self.params)

  @staticmethod
  def _label(config):
    return PROFILE_LABELS[config.hank_profile] if isinstance(config, HankConfigV2) else "Legacy"

  def state(self, openpilot_longitudinal_control: bool) -> HankProfileDisplay:
    active = read_config(self.params, ACTIVE)
    requested = read_config(self.params, REQUESTED)
    latch = read_latch(self.params)
    active_valid = active.state == ReadState.VALID and latch.state == ReadState.VALID
    requested_valid = requested.state == ReadState.VALID
    error = None
    if active.state in (ReadState.CORRUPT, ReadState.IO_ERROR) or latch.state in (ReadState.CORRUPT, ReadState.IO_ERROR):
      error = "Active configuration unavailable"
    elif requested.state in (ReadState.CORRUPT, ReadState.IO_ERROR):
      error = "Requested configuration unavailable"
    return HankProfileDisplay(
      owner_label="HANK" if openpilot_longitudinal_control else "TSS",
      active_label=self._label(active.value) if active_valid else "Unavailable",
      requested_label=self._label(requested.value) if requested_valid else "Unavailable",
      pending=active_valid and requested_valid and active.value != requested.value,
      requested_dynamic_follow=requested.value.dynamic_follow if requested_valid else None,
      hank_controls_longitudinal=openpilot_longitudinal_control and active_valid,
      error=error,
    )


def personality_status(params, sm, hank_active: bool, stock_long: bool, session_ns: int, now_ns: int | None = None) -> str:
  """Present observed planner state, never infer APM hysteresis from speed or Params."""
  if stock_long:
    return "APM inactive (TSS)"
  unavailable = "APM status unavailable"
  if not hank_active or session_ns <= 0:
    return unavailable
  active, latch = read_config(params, ACTIVE), read_latch(params)
  if active.state != ReadState.VALID or latch.state != ReadState.VALID:
    return unavailable
  now_ns = time.monotonic_ns() if now_ns is None else now_ns
  try:
    if not sm.seen["longitudinalPlan"] or not sm.valid["longitudinalPlan"]:
      return unavailable
    plan = sm["longitudinalPlan"]
    telemetry = plan.hankPersonality
    if telemetry.version != 1 or not telemetry.applies:
      return unavailable
    stamps = (sm.logMonoTime["longitudinalPlan"], plan.modelMonoTime, telemetry.selfdriveStateMonoTime)
    if any(stamp <= 0 or stamp < session_ns or not 0 <= now_ns - stamp <= 500_000_000 for stamp in stamps):
      return unavailable
    base, effective = telemetry.base.raw, telemetry.effective.raw
    if base not in (0, 1, 2) or effective not in (0, 1, 2):
      return unavailable
    if isinstance(active.value, HankConfigV2) and base != int(base_personality(active.value)):
      return unavailable
    if not telemetry.apmEnabled:
      return "APM OFF" if base == effective else unavailable
    names = {0: "Aggressive", 1: "Standard", 2: "Relaxed"}
    return f"APM effective override: {names[effective]}" if effective != base else "APM: no override"
  except (AttributeError, KeyError, TypeError, ValueError):
    # Old/absent observations never imply enum-default Aggressive or APM OFF.
    return unavailable
