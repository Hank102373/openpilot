"""Read-only FIX-UI-02 baseline: actual planner/MPC and actual HUD expression."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace as NS
from tempfile import TemporaryDirectory

from cereal import log
from openpilot.common.params import Params
from openpilot.selfdrive.controls.lib import hank_config as cfg
from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner, DPFlags
from openpilot.selfdrive.controls.tests.test_dtsc_bounds import make_messages
from dragonpilot.selfdrive.controls.lib.apm import APM_ACTIVATE_SPEED, APM_DEACTIVATE_SPEED

root = Path('/home/hank/src/dp-sienna-0103')
tree = ast.parse((root / 'selfdrive/ui/onroad/hud_renderer.py').read_text())
assignment = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'apm_override' for t in n.targets))
expression = compile(ast.Expression(assignment.value), '<actual HUD apm_override>', 'eval')
rows = []
failures = []

class SM(dict):
  logMonoTime = {'modelV2': 1}
  def all_checks(self, service_list):
    return True

class PM:
  def send(self, topic, msg):
    self.plan = msg.to_bytes()  # Real Cereal serialization of planner publication.

with TemporaryDirectory(prefix='fix-ui-02-') as d:
  params = Params(d)
  for profile in ('normal', 'comfortable', 'compact'):
    cfg.save_profile(params, profile)
    # Test-fixture lifecycle only, isolated Params; never production Params.
    from openpilot.common.params import ParamKeyFlag
    params.clear_all(ParamKeyFlag.CLEAR_ON_OFFROAD_TRANSITION)
    cfg.initialize_session(params)
    active = cfg.read_config(params, cfg.ACTIVE)
    before = [cfg.read_raw(params, k).value for k in (cfg.REQUESTED, cfg.ACTIVE)]
    base = cfg.base_personality(active.value)
    cp = NS(openpilotLongitudinalControl=True, steerRatio=15., wheelbase=2.7,
            longitudinalActuatorDelay=.2, vEgoStopping=.25)
    planner = LongitudinalPlanner(cp)
    planner.maa_helper = None
    captured = {}
    weights, update = planner.mpc.set_weights, planner.mpc.update
    def weights_spy(*args, _captured=captured, _weights=weights, **kwargs):
      _captured['weights'] = int(kwargs['personality'])
      return _weights(*args, **kwargs)
    def update_spy(*args, _captured=captured, _update=update, **kwargs):
      _captured['mpc_update'] = int(kwargs['personality'])
      return _update(*args, **kwargs)
    planner.mpc.set_weights = weights_spy
    planner.mpc.update = update_spy
    sequence = [(APM_ACTIVATE_SPEED, True), (0., True), (APM_ACTIVATE_SPEED, True),
                (APM_DEACTIVATE_SPEED, True), (APM_DEACTIVATE_SPEED + .01, True), (0., False)]
    for speed, enabled in sequence:
      sm = SM(make_messages())
      sm['selfdriveState'].personality = base
      sm['carState'].vEgo = speed
      planner.update(sm, DPFlags.APM if enabled else 0)
      pm = PM()
      planner.publish(sm, pm)
      with log.Event.from_bytes(pm.plan) as event:
        published_keys = sorted(event.longitudinalPlan.to_dict())
      displayed = eval(expression, {'owner_state': NS(hank_profile_active=True),
                                   'active_config': active, 'ReadState': cfg.ReadState,
                                   'HankConfigV2': cfg.HankConfigV2, 'base_personality': cfg.base_personality,
                                   'ui_state': NS(sm=sm)})
      expected = captured['mpc_update'] != int(base)
      row = dict(profile=profile, speed=speed, apm_enabled=enabled, base=int(base),
                 effective=captured['mpc_update'], weights=captured['weights'],
                 hud_override=displayed, expected_override=expected,
                 solution_status=planner.mpc.solution_status)
      assert captured['mpc_update'] == captured['weights']
      assert before == [cfg.read_raw(params, k).value for k in (cfg.REQUESTED, cfg.ACTIVE)]
      rows.append(row)
      if displayed != expected:
        failures.append(row)
print(json.dumps({'rows': rows, 'published_keys': published_keys, 'mismatches': len(failures),
                  'cfg_unchanged': True}, indent=2))
assert not failures, f'FIX-UI-02: actual HUD misses {len(failures)} real planner effective overrides'
