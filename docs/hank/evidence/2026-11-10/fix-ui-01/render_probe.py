"""Standalone desktop widgets only: synthetic topics, native isolated Params."""
import json
from pathlib import Path
import time

import pyray as rl
from cereal import messaging
from openpilot.common.params import Params
from openpilot.selfdrive.controls.lib.hank_config import initialize_session
from openpilot.selfdrive.selfdrived import hank_owner as ho
from openpilot.selfdrive.ui.tests.test_hank_owner_ui import cp_for, put_authority, transaction
from openpilot.system.ui.lib.application import gui_app, MouseEvent, MousePos
from openpilot.system.ui.widgets import DialogResult
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.ui.onroad.hud_renderer import HudRenderer
from openpilot.selfdrive.ui.layouts.settings.toggles import TogglesLayout

out = Path('/tmp/fix-ui-01')
params = Params()
initialize_session(params)
put_authority(params, transaction())
ui_state.CP = cp_for()
ui_state.has_longitudinal_control = True
ui_state.started = True
ui_state.sm = messaging.SubMaster(['deviceState', 'selfdriveState', 'carControl', 'carState', 'managerState'])
gui_app.init_window('FIX-UI-01 isolated widget verification')
hud, settings = HudRenderer(), TogglesLayout()
calls = []
for model in (hud._hank_owner, settings._hank_owner):
  model.transport_available = lambda _: True
  model.requester = lambda _p, target, timeout: calls.append(target) or {'result': 'BLOCKED_ENGAGED', 'reason': 'ALKA'}

def frame(active=False):
  msgs = [messaging.new_message(t, valid=True) for t in ('deviceState', 'selfdriveState', 'carControl', 'carState', 'managerState')]
  msgs[0].deviceState.started = True
  msgs[0].deviceState.startedMonoTime = 1
  msgs[2].carControl.latActive = active
  ui_state.sm.update_msgs(time.monotonic(), msgs)

def draw(name, surface):
  frame_rect = rl.Rectangle(0, 0, gui_app.width, gui_app.height)
  for _ in range(2):
    rl.begin_drawing()
    rl.clear_background(rl.BLACK)
    if surface == 'hud':
      hud._draw_hank_profile(frame_rect)
    elif surface == 'settings':
      settings._refresh_owner()
      settings._owner_selector.set_parent_rect(frame_rect)
      settings._owner_state.set_parent_rect(frame_rect)
      settings._owner_selector.render(rl.Rectangle(80, 120, gui_app.width - 160, 330))
      settings._owner_state.render(rl.Rectangle(80, 500, gui_app.width - 160, 330))
    else:
      gui_app._modal_overlay.overlay.render(frame_rect)
    rl.end_drawing()
  rl.take_screenshot(name + '.png')
  Path(name + '.png').replace(out / (name + '.png'))

def click(button):
  hit = button._button if button is settings._owner_selector.action_item else button
  p = MousePos(hit.rect.x + hit.rect.width / 2, hit.rect.y + hit.rect.height / 2)
  for pressed in (True, False):
    gui_app._mouse_events = [MouseEvent(p, 0, pressed, not pressed, pressed, time.monotonic())]
    rl.begin_drawing()
    if button is settings._owner_selector.action_item:
      settings._owner_selector.render(settings._owner_selector.rect)
    else:
      button.render(button.rect)
    rl.end_drawing()
  gui_app._mouse_events = []

before = {k: params.get(k) for k in (ho.OWNER, ho.GATE, ho.STATE, ho.CYCLE)}
frame(active=True)
draw('hud-blocked', 'hud')
draw('settings-blocked', 'settings')
assert not hud._owner_button.enabled
assert not settings._owner_selector.action_item.enabled
for button in (hud._owner_button, settings._owner_selector.action_item):
  click(button)
assert gui_app._modal_overlay.overlay is None
assert calls == []
assert hud._hank_owner.state(ui_state.CP).hank_profile_active

frame()
draw('hud-recovered', 'hud')
draw('settings-recovered', 'settings')
assert hud._owner_button.enabled and settings._owner_selector.action_item.enabled
for button in (hud._owner_button, settings._owner_selector.action_item):
  frame()
  settings._refresh_owner()
  click(button)
  assert gui_app._modal_overlay.overlay is not None
  draw('confirmation', 'dialog')
  frame(active=True)  # Changes after the dialog opened.
  gui_app._modal_overlay.callback(DialogResult.CONFIRM)
  gui_app.set_modal_overlay(None)
assert calls == []
assert {k: params.get(k) for k in before} == before

for surface, model in (('hud', hud._hank_owner), ('settings', settings._hank_owner)):
  frame()
  model.last_result = 'TRANSPORT_TIMEOUT'
  draw(surface + '-timeout', surface)
  assert not model.state(ui_state.CP).action_enabled
  frame()
  draw(surface + '-timeout-recovered', surface)
  assert model.state(ui_state.CP).action_enabled
assert calls == []
assert {k: params.get(k) for k in before} == before
frame(active=True)
ui_state.sm['selfdriveState'].enabled = True
ui_state.sm['carControl'].enabled = True
ui_state.sm['carControl'].longActive = True
ui_state.sm['carState'].cruiseState.enabled = True
draw('hud-multiple-blockers', 'hud')
frame()
put_authority(params, transaction('HANK', 'SWITCH_FAILED', 'TSS'), gate=False)
draw('hud-failed', 'hud')
draw('settings-failed', 'settings')
assert hud._hank_owner.state(ui_state.CP).reboot_available
assert not hud._hank_owner.state(ui_state.CP).action_enabled
click(hud._owner_button)
assert gui_app._modal_overlay.overlay is not None
gui_app._modal_overlay.callback(DialogResult.CANCEL)
gui_app.set_modal_overlay(None)
assert params.get('DoReboot') is not True
assert calls == []
print(json.dumps({'surfaces': ['actual HudRenderer panel', 'actual TogglesLayout owner items', 'actual ConfirmDialog'],
                  'blocked_clicks': 'no dialog/request', 'safe_recovery': 'manual actions enabled',
                  'confirmation_changed': 'no request', 'timeout_recovery': 'fresh data, no automatic retry',
                  'protected_params': 'unchanged', 'requests': calls}))
gui_app.close()
