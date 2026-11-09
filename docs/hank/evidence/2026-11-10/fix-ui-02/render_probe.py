"""Actual desktop HUD, real planner/native MPC, isolated Params and synthetic topics."""
import json
from pathlib import Path
import time
import pyray as rl
from cereal import messaging, log
from openpilot.common.params import Params
from openpilot.selfdrive.controls.lib import hank_config as cfg
from openpilot.selfdrive.selfdrived import hank_owner as ho
from openpilot.selfdrive.ui.tests.test_hank_owner_ui import cp_for, put_authority, transaction
from openpilot.selfdrive.ui.tests import test_hank_personality as probe
from openpilot.system.ui.lib.application import gui_app
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.ui.onroad.hud_renderer import HudRenderer

out = Path('/tmp/fix-ui-02-impl')
params = Params()
cfg.save_profile(params, 'normal')
cfg.initialize_session(params)
put_authority(params, transaction())
ui_state.CP = cp_for()
ui_state.started = True
ui_state.started_time = time.monotonic()
ui_state.sm = messaging.SubMaster(['deviceState', 'selfdriveState', 'carControl', 'carState', 'managerState', 'longitudinalPlan'])
gui_app.init_window('FIX-UI-02 isolated real planner HUD')
hud = HudRenderer()
canvas = rl.load_render_texture(gui_app.width, gui_app.height)
hud._hank_owner.transport_available = lambda _: True
calls = []
hud._hank_owner.requester = lambda *a, **k: calls.append(a)
planner = probe.make_planner()
texts = []
draw_text = rl.draw_text_ex

def capture(font, text, pos, size, spacing, color):
  texts.append((text, pos.y, size))
  return draw_text(font, text, pos, size, spacing, color)

rl.draw_text_ex = capture

def frame(kind):
  probe.NOW = time.monotonic_ns()
  probe.SM.logMonoTime = {'modelV2': probe.NOW, 'selfdriveState': probe.NOW}
  speed = 41/3.6 if kind == 'cleared' else 0.
  flags = 0 if kind == 'off' else probe.DPFlags.APM
  raw = probe.publish(planner, 1, speed, flags)
  with log.Event.from_bytes(raw) as event:
    plan = event.as_builder()
  if kind == 'unavailable':
    plan.valid = False
  topics = ('deviceState', 'selfdriveState', 'carControl', 'carState', 'managerState')
  msgs = [messaging.new_message(t, valid=True) for t in topics]
  msgs[0].deviceState.started = True
  msgs[0].deviceState.startedMonoTime = 1
  if kind in ('engaged', 'multiple-blockers'):
    msgs[1].selfdriveState.enabled = True
    msgs[2].carControl.enabled = True
    msgs[2].carControl.latActive = True
    msgs[2].carControl.longActive = True
    if kind == 'multiple-blockers':
      msgs[3].carState.cruiseState.enabled = True
  ui_state.sm.update_msgs(time.monotonic(), msgs + [plan])

results = {}
for kind, expected in [('override', 'APM effective override: Aggressive'), ('cleared', 'APM: no override'),
                       ('off', 'APM OFF'), ('unavailable', 'APM status unavailable'),
                       ('pending', 'APM effective override: Aggressive'), ('engaged', 'APM effective override: Aggressive'),
                       ('multiple-blockers', 'APM effective override: Aggressive'), ('tss', 'APM inactive (TSS)'),
                       ('failed', 'APM status unavailable')]:
  if kind == 'pending':
    cfg.save_profile(params, 'comfortable')
  elif kind == 'tss':
    put_authority(params, transaction('TSS'))
    ui_state.CP = cp_for('TSS')
  elif kind == 'failed':
    put_authority(params, transaction('HANK', 'SWITCH_FAILED', 'TSS'), gate=False)
    ui_state.CP = cp_for()
  protected = {key: params.get(key) for key in (cfg.REQUESTED, cfg.ACTIVE, cfg.LATCH, ho.OWNER, ho.GATE, ho.STATE, ho.CYCLE)}
  for _ in range(3):
    frame(kind)
    texts.clear()
    rl.begin_texture_mode(canvas)
    rl.clear_background(rl.BLACK)
    hud._draw_hank_profile(rl.Rectangle(0, 0, gui_app.width, gui_app.height))
    rl.end_texture_mode()
  assert expected in [t[0] for t in texts], (kind, texts)
  apm = next(t for t in texts if t[0] == expected)
  assert apm[1] + apm[2] < hud._hank_buttons[0].rect.y, (kind, 'APM/button overlap', texts)
  if kind in ('engaged', 'multiple-blockers', 'failed'):
    assert not hud._hank_owner.state(ui_state.CP).action_enabled
  if kind == 'failed':
    assert hud._hank_owner.state(ui_state.CP).reboot_available
  assert {key: params.get(key) for key in protected} == protected
  assert calls == []
  name = 'hud-' + kind + '.png'
  pixels = rl.load_image_from_texture(canvas.texture)
  rl.image_flip_vertical(pixels)
  rl.export_image(pixels, str(out / name))
  rl.unload_image(pixels)
  results[kind] = expected
print(json.dumps({'rendered': results, 'requests': calls, 'protected_params': 'unchanged'}))
rl.unload_render_texture(canvas)
gui_app.close()
