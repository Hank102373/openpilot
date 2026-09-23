"""D-024 deterministic coordinator contract over native temporary Params."""
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from cereal import car
from openpilot.common.params import Params, ParamKeyFlag, ParamKeyType
from openpilot.selfdrive.selfdrived import hank_owner as ho

BOOT_A = "12345678-1234-4234-8234-123456789abc"
BOOT_B = "87654321-4321-4321-8321-cba987654321"


def cp_for(owner):
  cp = car.CarParams.new_message()
  cp.brand = "toyota"
  cp.carFingerprint = ho.TARGET_CAR
  cp.openpilotLongitudinalControl = owner == "HANK"
  cp.safetyConfigs = [{"safetyModel": "toyota", "safetyParam": 512 if owner == "TSS" else 0}]
  cp.alternativeExperience = 0
  return cp


class RecordingParams:
  def __init__(self, native):
    self.native = native
    self.writes = []
    self.fail_key = None

  def get_param_path(self, key=""):
    return self.native.get_param_path(key)

  def put(self, key, value):
    self.writes.append((key, value))
    if key == self.fail_key:
      raise OSError("injected write failure")
    self.native.put(key, value)


@pytest.fixture
def rig(tmp_path):
  native = Params(str(tmp_path))
  params = RecordingParams(native)
  native.put(ho.OWNER, False)
  coordinator = ho.OwnerCoordinator(params, boot_id_reader=lambda: BOOT_A)
  return native, params, coordinator


def observation(owner="HANK", epoch=10., now=11., started=True, cp=None):
  cp = cp or cp_for(owner)
  data = {
    "deviceState": NS(started=started, startedMonoTime=int(epoch * 1e9) if started else 0),
    "selfdriveState": NS(enabled=False),
    "carControl": NS(enabled=False, latActive=False, longActive=False),
    "carState": NS(cruiseState=NS(enabled=False)),
    "carParams": cp,
    "pandaStates": [NS(safetyModel=c.safetyModel, safetyParam=c.safetyParam,
                       alternativeExperience=cp.alternativeExperience) for c in cp.safetyConfigs],
  }
  return ho.Evidence(int(now * 1e9), {k: ho.Sample(v, int(now * 1e9), True) for k, v in data.items()})


def start_session(native, coordinator, owner="HANK", epoch=10.):
  native.clear_all(ParamKeyFlag.CLEAR_ON_ONROAD_TRANSITION)
  coordinator.session_cleared(int(epoch * 1e9), int((epoch + .1) * 1e9))
  native.put("CarParams", cp_for(owner).to_bytes())


def confirm(rig, owner="HANK"):
  native, params, c = rig
  native.put(ho.OWNER, owner == "TSS")
  start_session(native, c, owner)
  c.tick(observation(owner))
  assert c.state.state == "CONFIRMED"
  assert native.get(ho.GATE) is True
  params.writes.clear()
  return c


def switched(rig, owner="TSS"):
  native, params, c = rig
  c.tick(observation(now=12., started=False))
  start_session(native, c, owner, 20.)
  c.tick(observation(owner, epoch=20., now=21.))
  c.tick(observation(owner, epoch=20., now=22.))
  return c


@pytest.mark.parametrize("name", ["UNVERIFIED", "CONFIRMED", "REQUESTED", "CYCLING", "REINITIALIZING", "VERIFYING", "SWITCH_FAILED"])
def test_state_roundtrip(name):
  previous = None if name == "UNVERIFIED" else "HANK"
  target = None if name in ("UNVERIFIED", "CONFIRMED") else "TSS"
  state = ho.Transaction(1, previous, target, name, BOOT_A if name == "SWITCH_FAILED" else None)
  assert ho.parse_state(ho.serialize_state(state)) == state


@pytest.mark.parametrize("change", [
  {"version": True}, {"version": 2}, {"extra": 0}, {"confirmed_owner": "OTHER"},
  {"target_owner": "HANK"}, {"target_owner": "OTHER"}, {"state": "BLOCKED_ENGAGED"},
  {"failure_boot_id": BOOT_A}, {"confirmed_owner": None},
])
def test_strict_schema_rejects(change):
  value = dict(version=1, confirmed_owner="HANK", target_owner=None, state="CONFIRMED", failure_boot_id=None)
  value.update(change)
  with pytest.raises(ValueError):
    ho.parse_state(json.dumps(value))


@pytest.mark.parametrize("boot", [None, "", "invalid", 1, True])
def test_failed_requires_valid_boot(boot):
  with pytest.raises(ValueError):
    ho.serialize_state(ho.Transaction(1, "HANK", "TSS", "SWITCH_FAILED", boot))


def test_missing_and_duplicate_keys():
  with pytest.raises(ValueError):
    ho.parse_state('{"version":1,"version":1}')
  value = json.loads(ho.serialize_state(ho.Transaction(1, "HANK", "TSS", "SWITCH_FAILED", BOOT_A)))
  del value["failure_boot_id"]
  with pytest.raises(ValueError):
    ho.parse_state(json.dumps(value))


def test_native_registry(rig):
  native, _, _ = rig
  assert native.get_type(ho.STATE) == ParamKeyType.JSON
  assert native.get_type(ho.GATE) == ParamKeyType.BOOL
  for key in (ho.STATE, ho.GATE):
    assert native.get_default_value(key) is None
  for flag in (ParamKeyFlag.CLEAR_ON_MANAGER_START, ParamKeyFlag.CLEAR_ON_OFFROAD_TRANSITION,
               ParamKeyFlag.CLEAR_ON_ONROAD_TRANSITION, ParamKeyFlag.CLEAR_ON_IGNITION_ON):
    native.put(ho.GATE, True)
    before = native.get(ho.STATE)
    native.clear_all(flag)
    assert native.get(ho.GATE) is None
    assert native.get(ho.STATE) == before


@pytest.mark.parametrize("owner", ["HANK", "TSS"])
def test_initial_verification(rig, owner):
  confirm(rig, owner)


@pytest.mark.parametrize("field", ["selfdriveState.enabled", "carControl.enabled", "carControl.latActive",
                                  "carControl.longActive", "carState.cruiseState.enabled"])
def test_active_request_rejected_without_writes(rig, field):
  c = confirm(rig)
  e = observation()
  parts = field.split(".")
  obj = e.samples[parts.pop(0)].value
  for name in parts[:-1]:
    obj = getattr(obj, name)
  setattr(obj, parts[-1], True)
  assert c.request("TSS", lambda: e) == "BLOCKED_ENGAGED"
  assert rig[1].writes == []


@pytest.mark.parametrize("topic", ["selfdriveState", "carControl", "carState", "deviceState"])
@pytest.mark.parametrize("bad", ["stale", "invalid", "missing"])
def test_stale_invalid_missing_request(rig, topic, bad):
  c = confirm(rig)
  e = observation()
  if bad == "missing":
    del e.samples[topic]
  else:
    e.samples[topic] = replace(e.samples[topic], mono_ns=0 if bad == "stale" else e.now_ns, valid=bad != "invalid")
  assert c.request("TSS", lambda: e).startswith("BLOCKED")
  assert rig[1].writes == []


def test_same_owner_noop(rig):
  c = confirm(rig)
  assert c.request("HANK", lambda: observation()) == "NO_OP"
  assert rig[1].writes == []


def test_order_and_exactly_one_cycle(rig):
  c = confirm(rig)
  assert c.request("TSS", lambda: observation()) == "REQUESTED"
  writes = rig[1].writes
  assert [k for k, _ in writes] == [ho.GATE, ho.STATE, ho.OWNER, ho.STATE, ho.CYCLE]
  assert writes[0][1] is False
  assert writes[1][1]["state"] == "REQUESTED"
  assert writes[3][1]["state"] == "CYCLING"
  c.request("TSS", lambda: observation())
  assert sum(k == ho.CYCLE for k, _ in writes) == 1


def test_recheck_before_owner_write(rig):
  c = confirm(rig)
  blocked = observation()
  blocked.samples["carControl"].value.latActive = True
  samples = iter([observation(), blocked])
  c.request("TSS", lambda: next(samples))
  assert not any(k == ho.CYCLE for k, _ in rig[1].writes)
  assert rig[0].get(ho.OWNER) is False
  assert rig[0].get(ho.GATE) is False


@pytest.mark.parametrize("previous,target", [("HANK", "TSS"), ("TSS", "HANK")])
def test_complete_switch(rig, previous, target):
  c = confirm(rig, previous)
  c.request(target, lambda: observation(previous))
  rig[0].put(ho.CYCLE, False)
  c.tick(observation(previous, now=11.5))
  assert c.state.state == "CYCLING"
  c.tick(observation(previous, now=12., started=False))
  assert c.state.state == "CYCLING"
  c.tick(observation(previous, now=13.))
  assert c.state.state == "CYCLING"
  switched(rig, target)
  assert c.state == ho.Transaction(1, target, None, "CONFIRMED", None)
  assert rig[0].get(ho.GATE) is True


@pytest.mark.parametrize("kind", ["param_only", "persistent_only", "old_cp", "panda", "extra_panda", "no_panda"])
def test_initial_unproven_never_opens(rig, kind):
  native, _, c = rig
  start_session(native, c)
  e = observation()
  if kind == "param_only":
    native.remove("CarParams")
  elif kind == "persistent_only":
    native.put("CarParamsPersistent", cp_for("HANK").to_bytes())
    native.remove("CarParams")
  elif kind == "old_cp":
    e.samples["carParams"] = replace(e.samples["carParams"], mono_ns=int(9e9))
  elif kind == "panda":
    e.samples["pandaStates"].value[0].safetyParam = 512
  elif kind == "extra_panda":
    e.samples["pandaStates"].value.append(NS(safetyModel="noOutput", safetyParam=0, alternativeExperience=0))
  else:
    e.samples["pandaStates"].value.clear()
  c.tick(e)
  assert native.get(ho.GATE) is False


@pytest.mark.parametrize("kind", ["cp", "panda", "timeout", "missing", "owner_write", "cycle_write"])
def test_failure_rollback_no_retry(rig, kind):
  native, params, c = rig
  confirm(rig)
  if kind == "owner_write":
    params.fail_key = ho.OWNER
  elif kind == "cycle_write":
    params.fail_key = ho.CYCLE
  c.request("TSS", lambda: observation())
  if kind in ("cp", "panda"):
    c.tick(observation(now=12., started=False))
    start_session(native, c, "TSS", 20.)
    e = observation("TSS", 20., 21.)
    if kind == "cp":
      native.put("CarParams", cp_for("HANK").to_bytes())
    else:
      e.samples["pandaStates"].value[0].alternativeExperience = 1
    c.tick(e)
  elif kind in ("timeout", "missing"):
    e = observation(now=200.)
    if kind == "missing":
      e.samples.clear()
    c.tick(e)
  assert c.state.state == "SWITCH_FAILED"
  assert c.state.failure_boot_id == BOOT_A
  assert native.get(ho.GATE) is False
  assert any(k == ho.OWNER and v is False for k, v in params.writes)
  cycles = sum(k == ho.CYCLE for k, _ in params.writes)
  c.tick(observation(now=201.))
  assert sum(k == ho.CYCLE for k, _ in params.writes) == cycles


def fail_transaction(rig):
  c = confirm(rig)
  c.request("TSS", lambda: observation())
  c.tick(observation(now=200.))
  return c


@pytest.mark.parametrize("restart", ["coordinator", "manager"])
def test_same_boot_restart_remains_failed(rig, restart):
  native, params, _ = rig
  fail_transaction(rig)
  if restart == "manager":
    native.clear_all(ParamKeyFlag.CLEAR_ON_MANAGER_START)
  c = ho.OwnerCoordinator(params, boot_id_reader=lambda: BOOT_A)
  start_session(native, c, epoch=210.)
  c.tick(observation(epoch=210., now=211.))
  assert c.state.state == "SWITCH_FAILED"
  assert native.get(ho.GATE) is False


@pytest.mark.parametrize("kind", ["success", "cp", "panda", "boot_read", "boot_malformed"])
def test_reboot_recovery(rig, kind):
  native, params, _ = rig
  fail_transaction(rig)

  def boot():
    if kind == "boot_read":
      raise OSError("boot inaccessible")
    return "bad" if kind == "boot_malformed" else BOOT_B

  c = ho.OwnerCoordinator(params, boot_id_reader=boot)
  start_session(native, c, epoch=10.)
  e = observation()
  if kind == "cp":
    native.put("CarParams", cp_for("TSS").to_bytes())
  if kind == "panda":
    e.samples["pandaStates"].value[0].safetyParam = 512
  c.tick(e)
  assert c.state.state == ("CONFIRMED" if kind == "success" else "SWITCH_FAILED")
  assert native.get(ho.GATE) is (kind == "success")


def test_out_of_band_owner_change(rig):
  c = confirm(rig)
  rig[0].put(ho.OWNER, True)
  c.tick(observation(now=12.))
  assert rig[0].get(ho.GATE) is False
  assert c.state.state != "CONFIRMED"
  assert not any(k == ho.CYCLE for k, _ in rig[1].writes)


def test_interrupted_transaction_restart_fails(rig):
  c = confirm(rig)
  c.request("TSS", lambda: observation())
  restarted = ho.OwnerCoordinator(rig[1], boot_id_reader=lambda: BOOT_A)
  assert restarted.state.state == "SWITCH_FAILED"
  assert rig[0].get(ho.OWNER) is False
  assert rig[0].get(ho.GATE) is False


@pytest.mark.parametrize("kind", ["gate", "state", "owner", "cp", "corrupt", "io"])
def test_independent_interlock(rig, kind):
  native, _, _ = rig
  confirm(rig)
  cp = cp_for("HANK")
  assert ho.interlock_reason(native, cp) is None
  if kind == "gate":
    native.put(ho.GATE, False)
  elif kind == "state":
    native.put(ho.STATE, json.loads(ho.serialize_state(ho.Transaction(1, "HANK", "TSS", "REQUESTED", None))))
  elif kind == "owner":
    native.put(ho.OWNER, True)
  elif kind == "cp":
    cp = cp_for("TSS")
  elif kind == "corrupt":
    Path(native.get_param_path(ho.STATE)).write_bytes(b"{")
  else:
    native.remove(ho.GATE)
  assert ho.interlock_reason(native, cp) is not None


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("owner", ["HANK", "TSS"])
def test_real_selfdrived_event_prevents_entry_and_disables(rig, enabled, owner):
  from cereal import log
  from openpilot.selfdrive.selfdrived.events import Events, ET
  from openpilot.selfdrive.selfdrived.state import StateMachine
  from openpilot.selfdrive.selfdrived.selfdrived import add_owner_interlock

  confirm(rig, owner)
  events = Events()
  events.add(log.OnroadEvent.EventName.pcmEnable)
  state_machine = StateMachine()
  assert add_owner_interlock(events, rig[0], cp_for(owner)) is None
  assert state_machine.update(events)[0] is True
  state_machine.state = log.SelfdriveState.OpenpilotState.enabled if enabled else log.SelfdriveState.OpenpilotState.disabled
  rig[0].put(ho.GATE, False)
  assert add_owner_interlock(events, rig[0], cp_for(owner)) == "OWNER_SESSION_UNVERIFIED"
  assert events.contains(ET.NO_ENTRY)
  assert events.contains(ET.IMMEDIATE_DISABLE)
  assert state_machine.update(events) == (False, False)


@pytest.mark.parametrize("key", [ho.GATE, ho.STATE, ho.OWNER])
def test_readback_mismatch_fails_closed(rig, key):
  native, params, c = rig
  confirm(rig)
  original_put = params.put
  injected = False

  def put(k, value):
    nonlocal injected
    original_put(k, value)
    if k == key and not injected:
      injected = True
      if key == ho.GATE:
        native.put(k, True)
      elif key == ho.STATE:
        native.put(k, {"wrong": "state"})
      else:
        native.put(k, False)

  params.put = put
  assert c.request("TSS", lambda: observation()) == "SWITCH_FAILED"
  assert native.get(ho.GATE) is False
  assert c.state.state == "SWITCH_FAILED"
  assert native.get(ho.OWNER) is False
  assert not any(k == ho.CYCLE for k, _ in params.writes)


def test_final_gate_failure_retains_rollback_authority(rig):
  native, params, c = rig
  confirm(rig)
  c.request("TSS", lambda: observation())
  original_put = params.put

  def put(k, value):
    if k == ho.GATE and value is True:
      raise OSError("cannot open gate")
    original_put(k, value)

  params.put = put
  switched(rig)
  assert c.state == ho.Transaction(1, "HANK", "TSS", "SWITCH_FAILED", BOOT_A)
  assert native.get(ho.OWNER) is False
  assert native.get(ho.GATE) is False


@pytest.mark.parametrize("mode", ["read_error", "malformed", "persist_error"])
def test_failure_boot_evidence_error_cannot_recover(rig, mode):
  native, params, c = rig
  confirm(rig)
  c.request("TSS", lambda: observation())

  def boot():
    if mode == "read_error":
      raise OSError("boot ID read failed")
    return "" if mode == "malformed" else BOOT_A

  c.boot_id_reader = boot
  if mode == "persist_error":
    params.fail_key = ho.STATE
  c.tick(observation(now=200.))
  assert native.get(ho.GATE) is False
  assert c.fault
  params.fail_key = None
  c.boot_id_reader = lambda: BOOT_B
  c.tick(observation(now=201.))
  assert native.get(ho.GATE) is False


@pytest.mark.parametrize("mutation", ["missing", "null", "invalid", "unreadable"])
def test_persisted_failure_invalid_evidence_blocks_restart(rig, mutation):
  native, params, _ = rig
  fail_transaction(rig)
  value = native.get(ho.STATE)
  if mutation == "missing":
    del value["failure_boot_id"]
  elif mutation == "null":
    value["failure_boot_id"] = None
  elif mutation == "invalid":
    value["failure_boot_id"] = "bad"
  else:
    value = None
  if value is None:
    Path(native.get_param_path(ho.STATE)).write_bytes(b"{")
  else:
    native.put(ho.STATE, value)
  restarted = ho.OwnerCoordinator(params, boot_id_reader=lambda: BOOT_B)
  start_session(native, restarted)
  restarted.tick(observation())
  assert native.get(ho.GATE) is False
  assert restarted.fault


def test_raw_io_failure_is_not_missing(rig, monkeypatch):
  from openpilot.selfdrive.controls.lib.hank_config import ReadResult, ReadState
  native, params, c = rig
  confirm(rig)
  real = ho.read_raw

  def read(p, key):
    return ReadResult(ReadState.IO_ERROR, reason="read failed") if key == ho.STATE else real(p, key)

  monkeypatch.setattr(ho, "read_raw", read)
  assert ho.interlock_reason(native, cp_for("HANK")) == "OWNER_EVIDENCE_UNREADABLE"
  c.tick(observation(now=12.))
  assert native.get(ho.GATE) is False


@pytest.mark.parametrize("field,value", [("safetyModel", "noOutput"), ("safetyParam", 512), ("alternativeExperience", 1)])
def test_every_panda_field_checked(rig, field, value):
  native, _, c = rig
  start_session(native, c)
  e = observation()
  setattr(e.samples["pandaStates"].value[0], field, value)
  c.tick(e)
  assert native.get(ho.GATE) is False


def test_fresh_cp_and_panda_but_stale_command_never_recovers(rig):
  native, params, _ = rig
  fail_transaction(rig)
  c = ho.OwnerCoordinator(params, boot_id_reader=lambda: BOOT_B)
  start_session(native, c)
  e = observation()
  e.samples["carControl"] = replace(e.samples["carControl"], mono_ns=int(1e9))
  c.tick(e)
  assert c.state.state == "SWITCH_FAILED"
  assert native.get(ho.GATE) is False


def test_no_clear_proof_and_old_epoch_cannot_verify(rig):
  native, _, c = rig
  native.put("CarParams", cp_for("HANK").to_bytes())
  c.tick(observation())
  assert native.get(ho.GATE) is False
  c.session_cleared(int(10e9), int(10.1e9))
  assert c.fault
  assert native.get(ho.GATE) is False


def test_recheck_after_requested_persistence_before_owner_write(rig):
  c = confirm(rig)
  blocked = observation(now=11.2)
  blocked.samples["carState"].value.cruiseState.enabled = True
  evidence = iter([observation(), observation(now=11.1), blocked])
  assert c.request("TSS", lambda: next(evidence)) == "SWITCH_FAILED"
  assert rig[0].get(ho.OWNER) is False
  assert not any(k == ho.OWNER and v is True for k, v in rig[1].writes)
  assert not any(k == ho.CYCLE for k, _ in rig[1].writes)


def test_confirmation_write_order(rig):
  confirm(rig)
  c = rig[2]
  c.request("TSS", lambda: observation())
  switched(rig)
  writes = rig[1].writes
  confirmed = next(i for i, (key, value) in enumerate(writes)
                   if key == ho.STATE and value["state"] == "CONFIRMED")
  opened = next(i for i, (key, value) in enumerate(writes) if key == ho.GATE and value is True)
  assert confirmed < opened
  assert writes[confirmed][1] == {
    "version": 1, "confirmed_owner": "TSS", "target_owner": None, "state": "CONFIRMED", "failure_boot_id": None,
  }


def test_recovery_gate_failure_records_current_boot_and_blocks_restart(rig):
  native, params, _ = rig
  fail_transaction(rig)
  c = ho.OwnerCoordinator(params, boot_id_reader=lambda: BOOT_B)
  start_session(native, c)
  original_put = params.put

  def put(key, value):
    if key == ho.GATE and value is True:
      raise OSError("recovery gate failure")
    original_put(key, value)

  params.put = put
  c.tick(observation())
  assert c.state == ho.Transaction(1, "HANK", "TSS", "SWITCH_FAILED", BOOT_B)
  assert native.get(ho.GATE) is False
  params.put = original_put
  restarted = ho.OwnerCoordinator(params, boot_id_reader=lambda: BOOT_B)
  start_session(native, restarted, epoch=20.)
  restarted.tick(observation(epoch=20., now=21.))
  assert restarted.state.state == "SWITCH_FAILED"
  assert native.get(ho.GATE) is False
