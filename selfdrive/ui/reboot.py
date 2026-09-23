"""Shared normal reboot confirmation used by settings and D-024 failure UI."""
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import DialogResult
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog, alert_dialog


def show_reboot_confirmation(params):
  if ui_state.engaged:
    gui_app.set_modal_overlay(alert_dialog(tr("Disengage to Reboot")))
    return

  def perform(result):
    if not ui_state.engaged and result == DialogResult.CONFIRM:
      params.put_bool_nonblocking("DoReboot", True)

  dialog = ConfirmDialog(tr("Are you sure you want to reboot?"), tr("Reboot"))
  gui_app.set_modal_overlay(dialog, callback=perform)
