"""Static seams for D-024 UI wiring that should never bypass coordinator."""
import ast
from pathlib import Path

import pytest

from openpilot.common.basedir import BASEDIR
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import (
  EARLY_DECEL_C3X_BENCH_SEED_CAP,
  EARLY_DECEL_C3X_BENCH_SEED_GAIN,
)


ROOT = Path(BASEDIR)
HUD = ROOT / "selfdrive/ui/onroad/hud_renderer.py"
SETTINGS = ROOT / "selfdrive/ui/layouts/settings/toggles.py"
REBOOT = ROOT / "selfdrive/ui/reboot.py"
DP_SETTINGS = ROOT / "dragonpilot/settings.py"
PROTECTED = {"dp_toyota_stock_lon", "HankOwnerSwitchState", "HankOwnerSessionVerified", "OnroadCycleRequested"}


def method_calls(path, class_name, method_name):
  tree = ast.parse(path.read_text())
  cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
  method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == method_name)
  return method, {node.func.attr for node in ast.walk(method) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}


@pytest.mark.parametrize(("path", "class_name", "request_method"), [
  (HUD, "HudRenderer", "onroad_request"),
  (SETTINGS, "TogglesLayout", "settings_request"),
])
def test_surfaces_use_shared_coordinator_model(path, class_name, request_method):
  source = path.read_text()
  assert "HankOwnerUIModel" in source
  assert request_method in method_calls(path, class_name, "_owner_action")[1]


@pytest.mark.parametrize(("path", "class_name"), [(HUD, "HudRenderer"), (SETTINGS, "TogglesLayout")])
def test_owner_actions_never_write_protected_owner_params(path, class_name):
  method = method_calls(path, class_name, "_owner_action")[0]
  strings = {node.value for node in ast.walk(method)
             if isinstance(node, ast.Constant) and isinstance(node.value, str)}
  assert not strings.intersection(PROTECTED)


def test_failure_reboot_uses_shared_normal_confirmation():
  assert "show_reboot_confirmation" in HUD.read_text()
  assert "show_reboot_confirmation" in SETTINGS.read_text()
  source = REBOOT.read_text()
  assert "ConfirmDialog" in source
  assert '"DoReboot"' in source
  assert not any(key in source for key in PROTECTED)


def test_old_direct_stock_long_toggle_is_not_selectable():
  assert "dp_toyota_stock_lon" not in DP_SETTINGS.read_text()


def test_d022_seed_is_unchanged():
  assert EARLY_DECEL_C3X_BENCH_SEED_GAIN == 0.09
  assert EARLY_DECEL_C3X_BENCH_SEED_CAP == 0.6
