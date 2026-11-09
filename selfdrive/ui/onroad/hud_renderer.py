import pyray as rl
from dataclasses import dataclass
from openpilot.common.constants import CV
from openpilot.selfdrive.ui.onroad.exp_button import ExpButton
from openpilot.selfdrive.ui.hank_owner import HankOwnerUIModel, owner_ui_evidence
from openpilot.selfdrive.ui.hank_profile import HankProfileUIModel, personality_status
from openpilot.selfdrive.ui.reboot import show_reboot_confirmation
from openpilot.selfdrive.controls.lib.hank_config import ACTIVE, HankConfigV2, ReadState, read_config
from openpilot.system.ui.widgets.button import Button, ButtonStyle
from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state, UIStatus
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.lib.wrap_text import wrap_text
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.mici.onroad.torque_bar import TorqueBar

# Constants
SET_SPEED_NA = 255
KM_TO_MILE = 0.621371
CRUISE_DISABLED_CHAR = '–'


@dataclass(frozen=True)
class UIConfig:
  header_height: int = 300
  border_size: int = 30
  button_size: int = 192
  set_speed_width_metric: int = 200
  set_speed_width_imperial: int = 172
  set_speed_height: int = 204
  wheel_icon_size: int = 144


@dataclass(frozen=True)
class FontSizes:
  current_speed: int = 176
  speed_unit: int = 66
  max_speed: int = 40
  set_speed: int = 90


@dataclass(frozen=True)
class Colors:
  WHITE = rl.WHITE
  DISENGAGED = rl.Color(145, 155, 149, 255)
  OVERRIDE = rl.Color(145, 155, 149, 255)  # Added
  ENGAGED = rl.Color(128, 216, 166, 255)
  DISENGAGED_BG = rl.Color(0, 0, 0, 153)
  OVERRIDE_BG = rl.Color(145, 155, 149, 204)
  ENGAGED_BG = rl.Color(128, 216, 166, 204)
  GREY = rl.Color(166, 166, 166, 255)
  DARK_GREY = rl.Color(114, 114, 114, 255)
  BLACK_TRANSLUCENT = rl.Color(0, 0, 0, 166)
  WHITE_TRANSLUCENT = rl.Color(255, 255, 255, 200)
  BORDER_TRANSLUCENT = rl.Color(255, 255, 255, 75)
  HEADER_GRADIENT_START = rl.Color(0, 0, 0, 114)
  HEADER_GRADIENT_END = rl.BLANK


UI_CONFIG = UIConfig()
FONT_SIZES = FontSizes()
COLORS = Colors()


class HudRenderer(Widget):
  def __init__(self):
    super().__init__()
    """Initialize the HUD renderer."""
    self.is_cruise_set: bool = False
    self.is_cruise_available: bool = True
    self.set_speed: float = SET_SPEED_NA
    self.speed: float = 0.0
    self.v_ego_cluster_seen: bool = False

    self._font_semi_bold: rl.Font = gui_app.font(FontWeight.SEMI_BOLD)
    self._font_bold: rl.Font = gui_app.font(FontWeight.BOLD)
    self._font_medium: rl.Font = gui_app.font(FontWeight.MEDIUM)

    self._exp_button: ExpButton = ExpButton(UI_CONFIG.button_size, UI_CONFIG.wheel_icon_size)

    self._params = Params()
    self._hank_profile = HankProfileUIModel(self._params)
    self._hank_owner = HankOwnerUIModel(self._params, observer=lambda: owner_ui_evidence(ui_state.sm))
    self._hank_error = None
    self._hank_buttons = [
      Button(label, lambda mode=mode: self._request_hank_profile(mode), font_size=34, button_style=ButtonStyle.NORMAL)
      for label, mode in (("緊湊", "compact"), ("一般", "normal"), ("舒適", "comfortable"))
    ]
    self._owner_button = Button("", self._owner_action, font_size=31, button_style=ButtonStyle.NORMAL)
    self._torque_bar = TorqueBar(scale=4.0)

  def _update_state(self) -> None:
    """Update HUD state based on car state and controls state."""
    sm = ui_state.sm
    if sm.recv_frame["carState"] < ui_state.started_frame:
      self.is_cruise_set = False
      self.set_speed = SET_SPEED_NA
      self.speed = 0.0
      return

    controls_state = sm['controlsState']
    car_state = sm['carState']

    v_cruise_cluster = car_state.vCruiseCluster
    self.set_speed = (
      controls_state.vCruiseDEPRECATED if v_cruise_cluster == 0.0 else v_cruise_cluster
    )
    self.is_cruise_set = 0 < self.set_speed < SET_SPEED_NA
    self.is_cruise_available = self.set_speed != -1

    if self.is_cruise_set and not ui_state.is_metric:
      self.set_speed *= KM_TO_MILE

    v_ego_cluster = car_state.vEgoCluster
    self.v_ego_cluster_seen = self.v_ego_cluster_seen or v_ego_cluster != 0.0
    v_ego = v_ego_cluster if self.v_ego_cluster_seen else car_state.vEgo
    speed_conversion = CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH
    self.speed = max(0.0, v_ego * speed_conversion)

  def _render(self, rect: rl.Rectangle) -> None:
    """Render HUD elements to the screen."""
    # Draw the header background
    rl.draw_rectangle_gradient_v(
      int(rect.x),
      int(rect.y),
      int(rect.width),
      UI_CONFIG.header_height,
      COLORS.HEADER_GRADIENT_START,
      COLORS.HEADER_GRADIENT_END,
    )

    if self.is_cruise_available:
      self._draw_set_speed(rect)

    self._draw_current_speed(rect)

    button_x = rect.x + rect.width - UI_CONFIG.border_size - UI_CONFIG.button_size
    button_y = rect.y + UI_CONFIG.border_size
    self._exp_button.render(rl.Rectangle(button_x, button_y, UI_CONFIG.button_size, UI_CONFIG.button_size))

    self._draw_hank_profile(rect)

    if ui_state.sm['controlsState'].lateralControlState.which() != 'angleState':
      self._torque_bar.render(rect)

  def user_interacting(self) -> bool:
    return self._exp_button.is_pressed or self._owner_button.is_pressed or any(button.is_pressed for button in self._hank_buttons)

  def _request_hank_profile(self, profile: str) -> None:
    try:
      self._hank_profile.select_mode(profile)
      self._hank_error = None
    except (ValueError, OSError, RuntimeError) as error:
      self._hank_error = str(error)

  def _owner_action(self):
    view = self._hank_owner.state(ui_state.CP)
    if view.reboot_available:
      show_reboot_confirmation(self._params)
      return
    if not view.action_enabled or view.action_target is None:
      return
    target = view.action_target

    def confirmed(result):
      if result == DialogResult.CONFIRM:
        self._hank_owner.onroad_request(target, ui_state.CP)

    dialog = ConfirmDialog(self._hank_owner.confirmation_text(target), tr(f"Switch to {target}"))
    gui_app.set_modal_overlay(dialog, callback=confirmed)

  def _draw_hank_profile(self, rect: rl.Rectangle) -> None:
    owner_state = self._hank_owner.state(ui_state.CP)
    has_long = (owner_state.current_owner == "HANK" if owner_state.visible
                else ui_state.CP is not None and ui_state.CP.openpilotLongitudinalControl)
    state = self._hank_profile.state(has_long)
    x = rect.x + rect.width - 790
    y = rect.y + 270
    panel = rl.Rectangle(x, y, 760, 425 if owner_state.reboot_available else 365 if owner_state.visible else 260)
    rl.draw_rectangle_rounded(panel, 0.12, 8, COLORS.BLACK_TRANSLUCENT)
    rl.draw_rectangle_rounded_lines_ex(panel, 0.12, 8, 2, COLORS.BORDER_TRANSLUCENT)
    if owner_state.visible:
      heading = owner_state.status
      active = state.active_label if owner_state.profile_role == "active" else f"{state.active_label} (stored HANK)"
      profile = f"Active: {active}  Requested: {state.requested_label}"
    else:
      owner = "HANK" if has_long else "TSS owns longitudinal"
      active = state.active_label if has_long else f"{state.active_label} (stored HANK)"
      heading = f"{owner}  Active: {active}  Requested: {state.requested_label}"
      profile = None
    rl.draw_text_ex(self._font_medium, heading, rl.Vector2(x + 18, y + 12), 33, 0, COLORS.WHITE)
    if profile is not None:
      rl.draw_text_ex(self._font_medium, profile, rl.Vector2(x + 18, y + 52), 29, 0, COLORS.WHITE)
    active_config = read_config(self._hank_profile.params, ACTIVE)
    profile_detail = (self._hank_error or state.error or
                      ("Pending: next onroad session" if state.pending else "Current session profile"))
    if owner_state.visible and not owner_state.action_enabled:
      detail = owner_state.detail
    elif owner_state.hank_profile_active:
      detail = profile_detail
      if active_config.state == ReadState.VALID and isinstance(active_config.value, HankConfigV2):
        detail += f" | Dynamic Follow: {'On' if active_config.value.dynamic_follow else 'Off'}"
    elif owner_state.visible:
      detail = owner_state.detail
    else:
      detail = profile_detail
    detail_y = y + (92 if owner_state.visible else 63)
    detail_size = 25 if owner_state.visible and not owner_state.state.startswith("CURRENT_") else 29
    detail_lines = [detail]
    if owner_state.visible and not owner_state.action_enabled:
      width = measure_text_cached(self._font_medium, detail, detail_size).x
      if width > 724:
        detail_size = 20
        detail_lines = wrap_text(self._font_medium, detail, detail_size, 724)
    for index, line in enumerate(detail_lines):
      rl.draw_text_ex(self._font_medium, line, rl.Vector2(x + 18, detail_y + index * detail_size), detail_size, 0,
                     COLORS.ENGAGED if state.pending else COLORS.WHITE)
    apm_text = personality_status(self._params, ui_state.sm, owner_state.hank_profile_active,
                                  owner_state.current_owner == "TSS", int(ui_state.started_time * 1e9) if ui_state.started else 0)
    apm_y = max(detail_y + len(detail_lines) * detail_size + 5, y + (162 if owner_state.reboot_available else 127 if owner_state.visible else 98))
    rl.draw_text_ex(self._font_medium, apm_text, rl.Vector2(x + 18, apm_y), 25, 0, COLORS.WHITE)
    button_y = y + (230 if owner_state.reboot_available else 170 if owner_state.visible else 153)
    for index, button in enumerate(self._hank_buttons):
      button.set_enabled((owner_state.hank_profile_active if owner_state.visible else has_long)
                         and state.hank_controls_longitudinal)
      button.render(rl.Rectangle(x + 18 + index * 246, button_y, 230, 85))
    if owner_state.visible:
      self._owner_button.set_text("Reboot C3X" if owner_state.reboot_available else owner_state.action_label)
      self._owner_button.set_enabled(owner_state.action_enabled or owner_state.reboot_available)
      self._owner_button.render(rl.Rectangle(x + 18, y + (330 if owner_state.reboot_available else 270), 724, 75))

  def _draw_set_speed(self, rect: rl.Rectangle) -> None:
    """Draw the MAX speed indicator box."""
    set_speed_width = UI_CONFIG.set_speed_width_metric if ui_state.is_metric else UI_CONFIG.set_speed_width_imperial
    x = rect.x + 60 + (UI_CONFIG.set_speed_width_imperial - set_speed_width) // 2
    y = rect.y + 45

    set_speed_rect = rl.Rectangle(x, y, set_speed_width, UI_CONFIG.set_speed_height)
    rl.draw_rectangle_rounded(set_speed_rect, 0.35, 10, COLORS.BLACK_TRANSLUCENT)
    rl.draw_rectangle_rounded_lines_ex(set_speed_rect, 0.35, 10, 6, COLORS.BORDER_TRANSLUCENT)

    max_color = COLORS.GREY
    set_speed_color = COLORS.DARK_GREY
    if self.is_cruise_set:
      set_speed_color = COLORS.WHITE
      if ui_state.status == UIStatus.ENGAGED:
        max_color = COLORS.ENGAGED
      elif ui_state.status == UIStatus.DISENGAGED:
        max_color = COLORS.DISENGAGED
      elif ui_state.status == UIStatus.OVERRIDE:
        max_color = COLORS.OVERRIDE

    max_text = tr("MAX")
    max_text_width = measure_text_cached(self._font_semi_bold, max_text, FONT_SIZES.max_speed).x
    rl.draw_text_ex(
      self._font_semi_bold,
      max_text,
      rl.Vector2(x + (set_speed_width - max_text_width) / 2, y + 27),
      FONT_SIZES.max_speed,
      0,
      max_color,
    )

    set_speed_text = CRUISE_DISABLED_CHAR if not self.is_cruise_set else str(round(self.set_speed))
    speed_text_width = measure_text_cached(self._font_bold, set_speed_text, FONT_SIZES.set_speed).x
    rl.draw_text_ex(
      self._font_bold,
      set_speed_text,
      rl.Vector2(x + (set_speed_width - speed_text_width) / 2, y + 77),
      FONT_SIZES.set_speed,
      0,
      set_speed_color,
    )

  def _draw_current_speed(self, rect: rl.Rectangle) -> None:
    """Draw the current vehicle speed and unit."""
    speed_text = str(round(self.speed))
    speed_text_size = measure_text_cached(self._font_bold, speed_text, FONT_SIZES.current_speed)
    speed_pos = rl.Vector2(rect.x + rect.width / 2 - speed_text_size.x / 2, 180 - speed_text_size.y / 2)
    rl.draw_text_ex(self._font_bold, speed_text, speed_pos, FONT_SIZES.current_speed, 0, COLORS.WHITE)

    unit_text = tr("km/h") if ui_state.is_metric else tr("mph")
    unit_text_size = measure_text_cached(self._font_medium, unit_text, FONT_SIZES.speed_unit)
    unit_pos = rl.Vector2(rect.x + rect.width / 2 - unit_text_size.x / 2, 290 - unit_text_size.y / 2)
    rl.draw_text_ex(self._font_medium, unit_text, unit_pos, FONT_SIZES.speed_unit, 0, COLORS.WHITE_TRANSLUCENT)
