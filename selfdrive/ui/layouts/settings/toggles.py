from openpilot.common.params import Params, UnknownKeyName
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.list_view import button_item, multiple_button_item, text_item, toggle_item
from openpilot.system.ui.widgets.scroller_tici import Scroller
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.widgets import DialogResult
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.ui.hank_owner import HankOwnerUIModel
from openpilot.selfdrive.ui.hank_profile import HankProfileUIModel
from openpilot.selfdrive.ui.reboot import show_reboot_confirmation
from openpilot.selfdrive.controls.lib.hank_config import ReadState, REQUESTED, read_config
import os

LITE = os.getenv("LITE") is not None

# Description constants
DESCRIPTIONS = {
  "OpenpilotEnabledToggle": tr_noop(
    "Use the openpilot system for adaptive cruise control and lane keep driver assistance. " +
    "Your attention is required at all times to use this feature."
  ),
  "DisengageOnAccelerator": tr_noop("When enabled, pressing the accelerator pedal will disengage openpilot."),
  "IsLdwEnabled": tr_noop(
    "Receive alerts to steer back into the lane when your vehicle drifts over a detected lane line " +
    "without a turn signal activated while driving over 31 mph (50 km/h)."
  ),
  "AlwaysOnDM": tr_noop("Enable driver monitoring even when openpilot is not engaged."),
  'RecordFront': tr_noop("Upload data from the driver facing camera and help improve the driver monitoring algorithm."),
  "IsMetric": tr_noop("Display speed in km/h instead of mph."),
  "RecordAudio": tr_noop("Record and store microphone audio while driving. The audio will be included in the dashcam video in comma connect."),
  "DisableLogging": tr("Disable logging service"),
  "DisableUpdates": tr("Disable update service"),
}


class TogglesLayout(Widget):
  def __init__(self):
    super().__init__()
    self._params = Params()
    self._is_release = self._params.get_bool("IsReleaseBranch")

    # param, title, desc, icon, needs_restart
    self._toggle_defs = {
      "OpenpilotEnabledToggle": (
        lambda: tr("Enable openpilot"),
        DESCRIPTIONS["OpenpilotEnabledToggle"],
        "chffr_wheel.png",
        True,
      ),
      "ExperimentalMode": (
        lambda: tr("Experimental Mode"),
        "",
        "experimental_white.png",
        False,
      ),
      "DisengageOnAccelerator": (
        lambda: tr("Disengage on Accelerator Pedal"),
        DESCRIPTIONS["DisengageOnAccelerator"],
        "disengage_on_accelerator.png",
        False,
      ),
      "IsLdwEnabled": (
        lambda: tr("Enable Lane Departure Warnings"),
        DESCRIPTIONS["IsLdwEnabled"],
        "warning.png",
        False,
      ),
      "AlwaysOnDM": (
        lambda: tr("Always-On Driver Monitoring"),
        DESCRIPTIONS["AlwaysOnDM"],
        "monitoring.png",
        False,
      ),
      "RecordFront": (
        lambda: tr("Record and Upload Driver Camera"),
        DESCRIPTIONS["RecordFront"],
        "monitoring.png",
        True,
      ),
      "RecordAudio": (
        lambda: tr("Record and Upload Microphone Audio"),
        DESCRIPTIONS["RecordAudio"],
        "microphone.png",
        True,
      ),
      "IsMetric": (
        lambda: tr("Use Metric System"),
        DESCRIPTIONS["IsMetric"],
        "metric.png",
        False,
      ),
      "DisableLogging": (
        lambda: tr("Disable Logging"),
        DESCRIPTIONS["DisableLogging"],
        "",
        False,
      ),
      "DisableUpdates": (
        lambda: tr("Disable Updates"),
        DESCRIPTIONS["DisableUpdates"],
        "",
        False,
      ),
    }

    self._hank_profile = HankProfileUIModel(self._params)
    self._hank_owner = HankOwnerUIModel(self._params)
    self._profile_error = None
    self._owner_selector = button_item(
      lambda: tr("Longitudinal owner"),
      lambda: self._owner_action_label(),
      description=lambda: self._owner_description(),
      callback=self._owner_action,
    )
    self._owner_state = text_item(
      lambda: tr("Owner switch state"),
      lambda: self._owner_status(),
      description=lambda: self._owner_description(),
    )
    self._profile_modes = ("compact", "normal", "comfortable")
    self._profile_buttons = multiple_button_item(
      lambda: tr("HANK profile"),
      lambda: tr("Requested profile applies at the next onroad session."),
      buttons=["緊湊", "一般", "舒適"],
      button_width=255,
      callback=self._set_hank_profile,
      selected_index=-1,
      icon="speed_limit.png",
    )
    self._profile_state = text_item(
      lambda: tr("HANK profile state"),
      lambda: self._profile_status(),
      description=lambda: self._profile_error or tr("Active and Requested are separate session values."),
    )
    self._dynamic_follow = toggle_item(
      lambda: tr("Dynamic Follow"),
      lambda: tr("Independent of HANK profile; changes apply next onroad session."),
      False,
      callback=self._set_dynamic_follow,
    )
    self._restore_original = button_item(
      lambda: tr("Advanced: restore original/default"),
      lambda: tr("Restore"),
      description=lambda: tr("Next session: Standard personality, stock acceleration, Dynamic Follow off."),
      callback=self._restore_hank_original,
    )

    self._toggles = {}
    self._locked_toggles = set()

    if LITE:
      for key in ['RecordAudio']:
          self._toggle_defs.pop(key, None)

    for param, (title, desc, icon, needs_restart) in self._toggle_defs.items():
      toggle = toggle_item(
        title,
        desc,
        self._params.get_bool(param),
        callback=lambda state, p=param: self._toggle_callback(state, p),
        icon=icon,
      )

      try:
        locked = self._params.get_bool(param + "Lock")
      except UnknownKeyName:
        locked = False
      toggle.action_item.set_enabled(not locked)

      # Make description callable for live translation
      additional_desc = ""
      if needs_restart and not locked:
        additional_desc = tr("Changing this setting will restart openpilot if the car is powered on.")
      toggle.set_description(lambda og_desc=toggle.description, add_desc=additional_desc: tr(og_desc) + (" " + tr(add_desc) if add_desc else ""))

      # track for engaged state updates
      if locked:
        self._locked_toggles.add(param)

      self._toggles[param] = toggle

      if param == "DisengageOnAccelerator":
        self._toggles["HankOwner"] = self._owner_selector
        self._toggles["HankOwnerState"] = self._owner_state
        self._toggles["HankProfile"] = self._profile_buttons
        self._toggles["HankProfileState"] = self._profile_state
        self._toggles["HankDynamicFollow"] = self._dynamic_follow
        self._toggles["HankRestoreOriginal"] = self._restore_original

    self._update_experimental_mode_icon()
    self._scroller = Scroller(list(self._toggles.values()), line_separator=True, spacing=0)

    ui_state.add_engaged_transition_callback(self._update_toggles)

  def _owner_view(self):
    return self._hank_owner.state(ui_state.CP)

  def _owner_action_label(self):
    view = self._owner_view()
    return tr("Reboot") if view.reboot_available else tr(view.action_label or "Unavailable")

  def _owner_status(self):
    view = self._owner_view()
    return f"{view.status} | {view.detail}" if view.visible else tr("Owner selector unavailable")

  def _owner_description(self):
    view = self._owner_view()
    return view.detail or tr("Verified HANK/TSS owner switching")

  def _owner_action(self):
    view = self._owner_view()
    if view.reboot_available:
      show_reboot_confirmation(self._params)
      return
    if not view.action_enabled or view.action_target is None:
      return
    target = view.action_target

    def confirmed(result):
      if result == DialogResult.CONFIRM:
        self._hank_owner.settings_request(target, ui_state.CP)
        self._refresh_owner()

    dialog = ConfirmDialog(self._hank_owner.confirmation_text(target), tr(f"Switch to {target}"))
    gui_app.set_modal_overlay(dialog, callback=confirmed)

  def _refresh_owner(self):
    view = self._owner_view()
    self._owner_selector.set_visible(view.visible)
    self._owner_state.set_visible(view.visible)
    self._owner_selector.action_item.set_enabled(view.action_enabled or view.reboot_available)

  def _profile_status(self):
    owner_view = self._owner_view()
    hank_active = owner_view.state == "CURRENT_HANK" if owner_view.visible else ui_state.has_longitudinal_control
    state = self._hank_profile.state(hank_active)
    if owner_view.state == "CURRENT_HANK":
      owner = tr("HANK owns longitudinal")
    elif owner_view.state == "CURRENT_TSS":
      owner = tr("TSS owns longitudinal; HANK stored for future use")
    else:
      owner = tr("Longitudinal owner unverified; HANK profile is not active")
    pending = tr("Pending: next onroad session") if state.pending else tr("No pending profile change")
    return f"{owner} | Active: {state.active_label} | Requested: {state.requested_label} | {pending}"

  def _refresh_profile(self):
    owner_view = self._owner_view()
    hank_active = owner_view.state == "CURRENT_HANK" if owner_view.visible else ui_state.has_longitudinal_control
    state = self._hank_profile.state(hank_active)
    requested = read_config(self._params, REQUESTED)
    index = (self._profile_modes.index(requested.value.hank_profile)
             if requested.state == ReadState.VALID and hasattr(requested.value, "hank_profile")
             and requested.value.hank_profile in self._profile_modes else -1)
    self._profile_buttons.action_item.selected_button = index
    if state.requested_dynamic_follow is not None:
      self._dynamic_follow.action_item.set_state(state.requested_dynamic_follow)
    if state.error:
      self._profile_error = state.error
    self._refresh_owner()

  def _set_hank_profile(self, button_index: int):
    try:
      self._hank_profile.select_mode(self._profile_modes[button_index])
      self._profile_error = None
    except (ValueError, OSError, RuntimeError) as error:
      self._profile_error = str(error)
    self._refresh_profile()

  def _set_dynamic_follow(self, enabled: bool):
    try:
      self._hank_profile.set_dynamic_follow(enabled)
      self._profile_error = None
    except (ValueError, OSError, RuntimeError) as error:
      self._profile_error = str(error)
    self._refresh_profile()

  def _restore_hank_original(self):
    try:
      self._hank_profile.restore_original()
      self._profile_error = None
    except (ValueError, OSError, RuntimeError) as error:
      self._profile_error = str(error)
    self._refresh_profile()

  def show_event(self):
    self._scroller.show_event()
    self._update_toggles()
    self._refresh_profile()

  def _update_toggles(self):
    ui_state.update_params()

    e2e_description = tr(
      "openpilot defaults to driving in chill mode. Experimental mode enables alpha-level features that aren't ready for chill mode. " +
      "Experimental features are listed below:<br>" +
      "<h4>End-to-End Longitudinal Control</h4><br>" +
      "Let the driving model control the gas and brakes. openpilot will drive as it thinks a human would, including stopping for red lights and stop signs. " +
      "Since the driving model decides the speed to drive, the set speed will only act as an upper bound. This is an alpha quality feature; " +
      "mistakes should be expected.<br>" +
      "<h4>New Driving Visualization</h4><br>" +
      "The driving visualization will transition to the road-facing wide-angle camera at low speeds to better show some turns. " +
      "The Experimental mode logo will also be shown in the top right corner."
    )

    if ui_state.CP is not None:
      if ui_state.has_longitudinal_control:
        self._toggles["ExperimentalMode"].action_item.set_enabled(True)
        self._toggles["ExperimentalMode"].set_description(e2e_description)

      else:
        # no long for now
        self._toggles["ExperimentalMode"].action_item.set_enabled(False)
        self._toggles["ExperimentalMode"].action_item.set_state(False)

        self._params.remove("ExperimentalMode")

        unavailable = tr("Experimental mode is currently unavailable on this car since the car's stock ACC is used for longitudinal control.")

        long_desc = unavailable + " " + tr("openpilot longitudinal control may come in a future update.")
        if ui_state.CP.alphaLongitudinalAvailable:
          if self._is_release:
            long_desc = unavailable + " " + tr("An alpha version of openpilot longitudinal control can be tested, along with " +
                                               "Experimental mode, on non-release branches.")
          else:
            long_desc = tr("Enable the openpilot longitudinal control (alpha) toggle to allow Experimental mode.")

        self._toggles["ExperimentalMode"].set_description("<b>" + long_desc + "</b><br><br>" + e2e_description)
    else:
      self._toggles["ExperimentalMode"].set_description(e2e_description)

    self._update_experimental_mode_icon()

    # TODO: make a param control list item so we don't need to manage internal state as much here
    # refresh toggles from params to mirror external changes
    for param in self._toggle_defs:
      self._toggles[param].action_item.set_state(self._params.get_bool(param))

    # these toggles need restart, block while engaged
    for toggle_def in self._toggle_defs:
      if self._toggle_defs[toggle_def][3] and toggle_def not in self._locked_toggles:
        self._toggles[toggle_def].action_item.set_enabled(not ui_state.engaged)

  def _render(self, rect):
    self._scroller.render(rect)

  def _update_experimental_mode_icon(self):
    icon = "experimental.png" if self._toggles["ExperimentalMode"].action_item.get_state() else "experimental_white.png"
    self._toggles["ExperimentalMode"].set_icon(icon)

  def _handle_experimental_mode_toggle(self, state: bool):
    confirmed = self._params.get_bool("ExperimentalModeConfirmed")
    if state and not confirmed:
      def confirm_callback(result: int):
        if result == DialogResult.CONFIRM:
          self._params.put_bool("ExperimentalMode", True)
          self._params.put_bool("ExperimentalModeConfirmed", True)
        else:
          self._toggles["ExperimentalMode"].action_item.set_state(False)
        self._update_experimental_mode_icon()

      # show confirmation dialog
      content = (f"<h1>{self._toggles['ExperimentalMode'].title}</h1><br>" +
                 f"<p>{self._toggles['ExperimentalMode'].description}</p>")
      dlg = ConfirmDialog(content, tr("Enable"), rich=True)
      gui_app.set_modal_overlay(dlg, callback=confirm_callback)
    else:
      self._update_experimental_mode_icon()
      self._params.put_bool("ExperimentalMode", state)

  def _toggle_callback(self, state: bool, param: str):
    if param == "ExperimentalMode":
      self._handle_experimental_mode_toggle(state)
      return

    self._params.put_bool(param, state)
    if self._toggle_defs[param][3]:
      self._params.put_bool("OnroadCycleRequested", True)
