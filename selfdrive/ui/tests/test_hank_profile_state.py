"""UI-01 display/actions use real CFG Requested and Active Params state."""
from openpilot.common.params import Params, ParamKeyFlag
from openpilot.selfdrive.controls.lib.hank_config import initialize_session
from openpilot.selfdrive.ui.hank_profile import HankProfileUIModel


def test_ui_active_requested_pending_and_next_session(tmp_path):
  params = Params(str(tmp_path))
  initialize_session(params)
  ui = HankProfileUIModel(params)
  assert ui.state(True).active_label == "Legacy"
  ui.select_mode("compact")
  state = ui.state(True)
  assert (state.active_label, state.requested_label, state.pending) == ("Legacy", "緊湊", True)
  params.clear_all(ParamKeyFlag.CLEAR_ON_OFFROAD_TRANSITION)
  initialize_session(params)
  state = ui.state(True)
  assert (state.active_label, state.requested_label, state.pending) == ("緊湊", "緊湊", False)


def test_ui_df_independent_and_original_reset(tmp_path):
  params = Params(str(tmp_path))
  initialize_session(params)
  ui = HankProfileUIModel(params)
  ui.set_dynamic_follow(True)
  ui.select_mode("normal")
  assert ui.state(True).requested_dynamic_follow is True
  ui.select_mode("comfortable")
  assert ui.state(True).requested_dynamic_follow is True
  ui.restore_original()
  state = ui.state(True)
  assert state.requested_label == "Original"
  assert state.requested_dynamic_follow is False
  assert state.pending
  assert params.get("HankConfigRequested") == {
    "version": 2, "dynamic_follow": False, "hank_profile": "original", "accel_profile": 3,
  }


def test_ui_tss_labels_stored_profile_not_active_control(tmp_path):
  params = Params(str(tmp_path))
  initialize_session(params)
  ui = HankProfileUIModel(params)
  ui.select_mode("normal")
  params.clear_all(ParamKeyFlag.CLEAR_ON_OFFROAD_TRANSITION)
  initialize_session(params)
  state = ui.state(False)
  assert state.owner_label == "TSS"
  assert state.active_label == "一般"
  assert state.hank_controls_longitudinal is False
  assert state.pending is False


def test_ui_all_three_modes_and_cycle(tmp_path):
  params = Params(str(tmp_path))
  ui = HankProfileUIModel(params)
  for mode, label in (("compact", "緊湊"), ("normal", "一般"), ("comfortable", "舒適")):
    ui.select_mode(mode)
    assert ui.state(True).requested_label == label
  assert ui.cycle_mode().hank_profile == "compact"
