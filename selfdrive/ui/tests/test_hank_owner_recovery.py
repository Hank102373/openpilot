"""Independent D-024 disabled-action contract and fresh-evidence recovery."""
from dataclasses import replace
import socket
import json

import pytest
from cereal import messaging

from openpilot.selfdrive.selfdrived import hank_owner as ho
from openpilot.selfdrive.selfdrived.tests.test_hank_owner import observation, start_session
from openpilot.selfdrive.ui.hank_owner import coordinator_available, owner_ui_evidence
from openpilot.system.manager.hank_owner_service import OwnerService, socket_address

from openpilot.selfdrive.ui.tests import test_hank_owner_ui as fixtures
from openpilot.selfdrive.ui.tests.test_hank_owner_ui import cp_for, put_authority, transaction

rig = fixtures.rig


@pytest.mark.parametrize("result", ["BLOCKED_ENGAGED", "BLOCKED_STALE_OR_INVALID", "TRANSPORT_UNAVAILABLE", "TRANSPORT_TIMEOUT"])
def test_rejected_action_stays_disabled_without_new_safe_evidence(rig, result):
  params, calls, ui = rig
  put_authority(params, transaction())
  ui.last_result = result
  view = ui.state(cp_for())
  assert not view.action_enabled, f"D-024 requires disabled action for {result}"
  assert ui.request("TSS", cp_for()) != "REQUESTED"
  assert calls == []


@pytest.fixture
def recovery(rig):
  params, calls, ui = rig
  put_authority(params, transaction())
  evidence = [ui.observer()]
  ui.observer = lambda: evidence[0]
  ui.clock_ns = lambda: evidence[0].now_ns
  return params, calls, ui, evidence


def advance(evidence, now=12.):
  value = observation(now=now)
  value.samples["managerState"] = ho.Sample(None, value.now_ns, True)
  evidence[0] = value


@pytest.mark.parametrize("reason", ["BLOCKED_ENGAGED", "BLOCKED_STALE_OR_INVALID", "TRANSPORT_UNAVAILABLE", "TRANSPORT_TIMEOUT"])
def test_recovery_requires_new_safe_data_then_manual_action(recovery, reason):
  params, calls, ui, evidence = recovery
  before = {key: params.get(key) for key in (ho.OWNER, ho.STATE, ho.GATE, ho.CYCLE)}
  ui.last_result = reason
  assert not ui.state(cp_for()).action_enabled
  for _ in range(3):
    assert ui.request("TSS", cp_for()) == reason
  assert calls == []
  advance(evidence)
  assert ui.state(cp_for()).action_enabled
  assert calls == []  # Recovery observes only, never resends the old request.
  assert {key: params.get(key) for key in before} == before
  assert ui.request("TSS", cp_for()) == "REQUESTED"
  assert calls == [("TSS", 3.0)]
  assert {key: params.get(key) for key in before} == before


@pytest.mark.parametrize("topic", ["deviceState", "selfdriveState", "carControl", "carState", "managerState"])
def test_every_recovery_topic_must_advance_past_rejection(recovery, topic):
  _, calls, ui, evidence = recovery
  ui.last_result = "TRANSPORT_TIMEOUT"
  assert not ui.state(cp_for()).action_enabled
  old = evidence[0].samples[topic]
  advance(evidence, now=11.5)
  evidence[0].samples[topic] = old  # Still fresh, but predates the rejection.
  assert not ui.state(cp_for()).action_enabled
  ui.request("TSS", cp_for())
  assert calls == []


@pytest.mark.parametrize("topic,field,label", [
  ("selfdriveState", "enabled", "selfdrive"),
  ("carControl", "enabled", "control commands"),
  ("carControl", "latActive", "ALKA/lateral"),
  ("carControl", "longActive", "longitudinal commands"),
  ("carState", "cruiseState", "factory ACC"),
])
def test_live_blocks_and_conditions_changing_during_confirmation(recovery, topic, field, label):
  params, calls, ui, evidence = recovery
  assert ui.state(cp_for()).action_enabled  # The dialog could open here.
  before = {key: params.get(key) for key in (ho.OWNER, ho.STATE, ho.GATE, ho.CYCLE)}
  advance(evidence)
  value = evidence[0].samples[topic].value
  if field == "cruiseState":
    value.cruiseState.enabled = True
  else:
    setattr(value, field, True)
  assert ui.request("TSS", cp_for()) == "BLOCKED_ENGAGED"
  assert label in ui.state(cp_for()).detail
  assert not ui.state(cp_for()).action_enabled
  assert calls == []
  assert {key: params.get(key) for key in before} == before
  advance(evidence, now=13.)
  assert ui.state(cp_for()).action_enabled
  assert calls == []


@pytest.mark.parametrize("topic", ["deviceState", "selfdriveState", "carControl", "carState", "managerState"])
@pytest.mark.parametrize("fault", ["missing", "invalid", "stale", "future"])
def test_missing_invalid_stale_future_evidence_never_enables(recovery, topic, fault):
  _, calls, ui, evidence = recovery
  sample = evidence[0].samples[topic]
  if fault == "missing":
    del evidence[0].samples[topic]
  else:
    evidence[0].samples[topic] = replace(sample, valid=fault != "invalid",
                                       mono_ns=sample.mono_ns + (1 if fault == "future" else -int(3e9) if fault == "stale" else 0))
  assert not ui.state(cp_for()).action_enabled
  ui.request("TSS", cp_for())
  assert calls == []


def test_cached_observation_time_cannot_keep_action_enabled(recovery):
  _, calls, ui, _ = recovery
  ui.clock_ns = lambda: int(30e9)
  assert not ui.state(cp_for()).action_enabled
  ui.request("TSS", cp_for())
  assert calls == []


def test_transport_and_manager_progress_are_both_required(recovery):
  _, calls, ui, evidence = recovery
  ui.transport_available = lambda _: False
  assert ui.state(cp_for()).state == "TRANSPORT_UNAVAILABLE"
  advance(evidence)
  assert not ui.state(cp_for()).action_enabled
  ui.transport_available = lambda _: True
  del evidence[0].samples["managerState"]
  assert not ui.state(cp_for()).action_enabled
  advance(evidence, now=13.)
  assert ui.state(cp_for()).action_enabled
  assert calls == []


@pytest.mark.parametrize("change", ["owner", "gate", "cp", "offroad", "failed"])
def test_authority_rechecked_on_confirmation(recovery, change):
  params, calls, ui, evidence = recovery
  assert ui.state(cp_for()).action_enabled
  cp = cp_for()
  if change == "owner":
    params.put(ho.OWNER, True)
  elif change == "gate":
    params.put(ho.GATE, False)
  elif change == "cp":
    cp = cp_for("TSS")
  elif change == "offroad":
    evidence[0].samples["deviceState"].value.started = False
  else:
    put_authority(params, transaction("HANK", "SWITCH_FAILED", "TSS"), gate=False)
  assert not ui.state(cp).action_enabled
  ui.request("TSS", cp)
  assert calls == []


def test_actual_submaster_validity_and_timestamp_adapter():
  sm = messaging.SubMaster(["deviceState", "managerState"])
  msg = messaging.new_message("managerState", valid=True)
  sm.update_msgs(11., [msg])
  result = owner_ui_evidence(sm)
  assert result.samples["managerState"].mono_ns == msg.logMonoTime
  assert result.samples["managerState"].valid
  assert "deviceState" not in result.samples
  msg.valid = False
  sm.update_msgs(12., [msg])
  assert not owner_ui_evidence(sm).samples["managerState"].valid


def test_real_service_connect_probe_sends_no_datagram_or_params_write(recovery):
  params, _, _, _ = recovery
  assert not coordinator_available(params)
  sm = messaging.SubMaster(["deviceState", "selfdriveState", "carControl", "carState", "carParams", "pandaStates"])
  server = OwnerService(params, sm)
  try:
    before = {key: params.get(key) for key in (ho.OWNER, ho.STATE, ho.GATE, ho.CYCLE)}
    for _ in range(3):
      assert coordinator_available(params)
    with pytest.raises(BlockingIOError):
      server.socket.recvfrom(256)
    assert {key: params.get(key) for key in before} == before
  finally:
    server.close()
  assert not coordinator_available(params)


def test_real_coordinator_can_reject_after_ui_safe_observation(recovery):
  params, _, ui, evidence = recovery
  sm = messaging.SubMaster(["deviceState", "selfdriveState", "carControl", "carState", "carParams", "pandaStates"])
  server = OwnerService(params, sm)
  try:
    start_session(params, server.coordinator)
    server.observe = lambda refresh=False: evidence[0]
    server.poll()
    ui.transport_available = coordinator_available
    assert ui.state(cp_for()).action_enabled
    before = {key: params.get(key) for key in (ho.OWNER, ho.STATE, ho.GATE, ho.CYCLE)}

    def forwarding_request(_params, target, timeout):
      # Real transport and coordinator see a newer ALKA-active frame than UI.
      blocked = observation(now=11.1)
      blocked.samples["carControl"].value.latActive = True
      server.observe = lambda refresh=False: blocked
      with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        client.bind(bytes([0]) + b"fix-ui-01-" + str(params.get_param_path()).encode()[-70:])
        client.settimeout(timeout)
        client.sendto(json.dumps({"target": target}).encode(), socket_address(params))
        server.poll()
        return json.loads(client.recv(2048))

    ui.requester = forwarding_request
    assert ui.request("TSS", cp_for()) == "BLOCKED_ENGAGED"
    assert not ui.state(cp_for()).action_enabled
    assert {key: params.get(key) for key in before} == before
  finally:
    server.close()


@pytest.mark.parametrize("owner", ["HANK", "TSS"])
def test_owner_switch_block_does_not_change_cfg_profile_authority(recovery, owner):
  params, _, ui, evidence = recovery
  put_authority(params, transaction(owner))
  evidence[0].samples["carControl"].value.latActive = True
  view = ui.state(cp_for(owner))
  assert not view.action_enabled
  assert view.hank_profile_active == (owner == "HANK")
  put_authority(params, transaction(owner, "CYCLING", "TSS" if owner == "HANK" else "HANK"), gate=False)
  assert not ui.state(cp_for(owner)).hank_profile_active


def test_manager_heartbeat_is_published_after_service_poll():
  # The UI liveness observation relies on this existing manager ordering.
  from pathlib import Path
  from openpilot.common.basedir import BASEDIR
  source = (Path(BASEDIR) / "system/manager/manager.py").read_text()
  loop = source[source.index("def manager_thread"):]
  assert loop.index("owner_service.poll()") < loop.index("pm.send('managerState', msg)")
