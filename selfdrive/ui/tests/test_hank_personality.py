"""D-026: true planner/native MPC -> serialized plan -> UI telemetry contract."""
from types import SimpleNamespace as NS
from pathlib import Path

import pytest
from cereal import log, messaging
from openpilot.common.params import Params
from openpilot.selfdrive.controls.lib import hank_config as cfg
from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner, DPFlags
from openpilot.selfdrive.controls.tests.test_dtsc_bounds import make_messages
from openpilot.selfdrive.ui.hank_profile import HankProfileUIModel, personality_status

NOW = 11_000_000_000


class SM(dict):
  logMonoTime = {"modelV2": NOW, "selfdriveState": NOW}
  def all_checks(self, service_list):
    return True


class Publisher:
  def send(self, topic, msg):
    msg.logMonoTime = NOW
    self.raw = msg.to_bytes()


def make_planner(stock=False):
  cp = NS(openpilotLongitudinalControl=not stock, steerRatio=15., wheelbase=2.7,
          longitudinalActuatorDelay=.2, vEgoStopping=.25)
  planner = LongitudinalPlanner(cp)
  planner.maa_helper = None
  return planner


def publish(planner, base, speed=0., flags=DPFlags.APM, blended=False):
  sm = SM(make_messages())
  sm['selfdriveState'] = messaging.new_message('selfdriveState').selfdriveState
  sm['selfdriveState'].personality = base
  sm['selfdriveState'].enabled = True
  sm['selfdriveState'].experimentalMode = blended
  sm['carState'].vEgo = speed
  planner.update(sm, flags)
  pm = Publisher()
  planner.publish(sm, pm)
  return pm.raw


@pytest.mark.parametrize("profile", ["normal", "comfortable"])
def test_effective_override_reaches_published_plan_and_ui(tmp_path, profile):
  params = Params(str(tmp_path))
  cfg.save_profile(params, profile)
  active = cfg.initialize_session(params).config
  base = cfg.base_personality(active)
  planner = make_planner()
  raw = publish(planner, base)
  with log.Event.from_bytes(raw) as event:
    assert 'hankPersonality' in event.longitudinalPlan.to_dict(), 'D-026 missing effective personality publication'
    telemetry = event.longitudinalPlan.hankPersonality
    assert telemetry.version == 1
    assert telemetry.base.raw == int(base)
    assert telemetry.effective.raw == 0
    sm = NS(seen={'longitudinalPlan': True}, valid={'longitudinalPlan': event.valid},
            logMonoTime={'longitudinalPlan': NOW})
    class Reader:
      seen, valid, logMonoTime = sm.seen, sm.valid, sm.logMonoTime
      def __getitem__(self, key):
        return event.longitudinalPlan
    assert personality_status(params, Reader(), True, False, NOW - 1, NOW) == 'APM effective override: Aggressive'


class Reader:
  def __init__(self, plan, stamp=NOW, valid=True, seen=True):
    self.plan = plan
    self.seen = {"longitudinalPlan": seen}
    self.valid = {"longitudinalPlan": valid}
    self.logMonoTime = {"longitudinalPlan": stamp}

  def __getitem__(self, key):
    assert key == "longitudinalPlan"
    return self.plan


def display(params, raw, **kwargs):
  with log.Event.from_bytes(raw) as event:
    return personality_status(params, Reader(event.longitudinalPlan, event.logMonoTime, event.valid),
                              kwargs.get("hank", True), kwargs.get("stock", False), kwargs.get("session", NOW - 1), NOW)


@pytest.mark.parametrize("profile", ["compact", "normal", "comfortable", "original", "legacy"])
@pytest.mark.parametrize("blended", [False, True])
def test_real_apm_history_and_mpc_inputs(tmp_path, monkeypatch, profile, blended):
  params = Params(str(tmp_path))
  if profile == "original":
    cfg.restore_original(params)
  elif profile != "legacy":
    cfg.save_profile(params, profile)
  active = cfg.initialize_session(params).config
  base = cfg.base_personality(active) if profile != "legacy" else 2
  before = {key: params.get(key) for key in (cfg.REQUESTED, cfg.ACTIVE, cfg.LATCH)}
  planner = make_planner()
  captured = {}
  for name in ("set_weights", "update"):
    original = getattr(planner.mpc, name)
    def spy(*args, _name=name, _original=original, **kwargs):
      value = kwargs["personality"]
      captured[_name] = getattr(value, "raw", value)
      return _original(*args, **kwargs)
    monkeypatch.setattr(planner.mpc, name, spy)
  # Equality holds prior hysteresis state; initial 30 does not activate.
  for speed, flags, expected in ((30 / 3.6, DPFlags.APM, base), (0., DPFlags.APM, 0),
                                 (30 / 3.6, DPFlags.APM, 0), (35 / 3.6, DPFlags.APM, 0),
                                 (40 / 3.6, DPFlags.APM, 0), (41 / 3.6, DPFlags.APM, base),
                                 (0., 0, base)):
    raw = publish(planner, base, speed, flags, blended)
    with log.Event.from_bytes(raw) as event:
      t = event.longitudinalPlan.hankPersonality
      assert t.base.raw == base
      assert t.effective.raw == expected == captured["set_weights"] == captured["update"]
      assert t.apmEnabled == bool(flags & DPFlags.APM)
      assert t.applies and t.selfdriveStateMonoTime == NOW
    expected_text = ("APM OFF" if not flags else "APM effective override: Aggressive" if expected != base else "APM: no override")
    assert display(params, raw) == expected_text
    assert planner.mpc.solution_status == 0
    assert planner.mpc.mode == ("blended" if blended else "acc")
    assert {key: params.get(key) for key in before} == before
  if profile == "legacy":
    assert HankProfileUIModel(params).state(True).active_label == "Legacy"


def test_restart_pending_and_next_session(tmp_path):
  params = Params(str(tmp_path))
  cfg.save_profile(params, "normal")
  cfg.initialize_session(params)
  planner = make_planner()
  assert display(params, publish(planner, 1)) == "APM effective override: Aggressive"
  cfg.save_profile(params, "comfortable")
  before = {key: params.get(key) for key in (cfg.REQUESTED, cfg.ACTIVE, cfg.LATCH)}
  assert cfg.base_personality(cfg.initialize_session(params).config) == 1
  # Restart at the same in-band speed starts its own APM, not the previous history.
  assert display(params, publish(planner, 1, 35 / 3.6)) == "APM effective override: Aggressive"
  assert display(params, publish(make_planner(), 1, 35 / 3.6)) == "APM: no override"
  assert HankProfileUIModel(params).state(True).pending
  assert {key: params.get(key) for key in before} == before
  old = publish(planner, 1)
  for key in (cfg.ACTIVE, cfg.LATCH):  # Modeled lifecycle, isolated temporary Params only.
    params.remove(key)
  assert cfg.base_personality(cfg.initialize_session(params).config) == 2
  assert display(params, old, session=NOW + 1) == "APM status unavailable"
  assert display(params, publish(make_planner(), 2)) == "APM effective override: Aggressive"


def test_stock_long_and_unverified_owner(tmp_path):
  params = Params(str(tmp_path))
  cfg.save_profile(params, "normal")
  cfg.initialize_session(params)
  raw = publish(make_planner(stock=True), 1)
  with log.Event.from_bytes(raw) as event:
    assert not event.longitudinalPlan.hankPersonality.applies
  assert display(params, raw) == "APM status unavailable"
  assert display(params, raw, hank=False, stock=True) == "APM inactive (TSS)"
  fresh = publish(make_planner(), 1)
  assert display(params, fresh, hank=False) == "APM status unavailable"
  assert display(params, fresh, session=0) == "APM status unavailable"


@pytest.mark.parametrize("fault", ["missing", "version0", "version2", "base_enum", "effective_enum",
                                   "invalid", "unseen", "no_applies", "base_mismatch", "off_contradiction",
                                   "active_missing", "active_corrupt", "latch_missing", "latch_corrupt"])
def test_unavailable_never_claims_off_or_override(tmp_path, fault):
  params = Params(str(tmp_path))
  cfg.save_profile(params, "normal")
  cfg.initialize_session(params)
  with log.Event.from_bytes(publish(make_planner(), 1)) as event:
    plan = event.longitudinalPlan.as_builder()
  t = plan.hankPersonality
  if fault == "missing":
    plan = messaging.new_message('longitudinalPlan').longitudinalPlan
  elif fault.startswith("version"):
    t.version = int(fault[-1])
  elif fault in ("base_enum", "effective_enum"):
    setattr(t, fault.split('_')[0], 99)
  elif fault == "no_applies":
    t.applies = False
  elif fault == "base_mismatch":
    t.base = 2
  elif fault == "off_contradiction":
    t.apmEnabled = False
  elif fault in ("active_missing", "latch_missing"):
    params.remove(cfg.ACTIVE if fault.startswith("active") else cfg.LATCH)
  elif fault in ("active_corrupt", "latch_corrupt"):
    key = cfg.ACTIVE if fault.startswith("active") else cfg.LATCH
    Path(params.get_param_path(key)).write_bytes(b'bad')
  reader = Reader(plan, valid=fault != "invalid", seen=fault != "unseen")
  assert personality_status(params, reader, True, False, NOW - 1, NOW) == "APM status unavailable"
  # No cached prior override when transport loses its metadata/authority.
  reader.seen['longitudinalPlan'] = False
  assert personality_status(params, reader, True, False, NOW - 1, NOW) == "APM status unavailable"


@pytest.mark.parametrize("field", ["event", "model", "selfdrive"])
@pytest.mark.parametrize("stamp,session,available", [(0, 1, False), (NOW + 1, 1, False),
                                                    (NOW - 500_000_001, 1, False), (NOW - 500_000_000, 1, True),
                                                    (NOW - 2, NOW - 1, False), (NOW, NOW, True)])
def test_each_timestamp_freshness_and_session_boundary(tmp_path, field, stamp, session, available):
  params = Params(str(tmp_path))
  cfg.save_profile(params, "normal")
  cfg.initialize_session(params)
  with log.Event.from_bytes(publish(make_planner(), 1)) as event:
    plan = event.longitudinalPlan.as_builder()
  reader = Reader(plan)
  if field == "event":
    reader.logMonoTime['longitudinalPlan'] = stamp
  elif field == "model":
    plan.modelMonoTime = stamp
  else:
    plan.hankPersonality.selfdriveStateMonoTime = stamp
  expected = "APM effective override: Aggressive" if available else "APM status unavailable"
  assert personality_status(params, reader, True, False, session, NOW) == expected


def test_only_completed_update_publishes_snapshot(monkeypatch):
  planner = make_planner()
  sm, pm = SM(make_messages()), Publisher()
  planner.publish(sm, pm)
  with log.Event.from_bytes(pm.raw) as event:
    assert event.longitudinalPlan.hankPersonality.version == 0
  publish(planner, 1)
  def fail(*args, **kwargs):
    raise RuntimeError("incomplete update")
  monkeypatch.setattr(planner.mpc, "update", fail)
  with pytest.raises(RuntimeError, match="incomplete update"):
    publish(planner, 1)
  planner.publish(sm, pm)
  with log.Event.from_bytes(pm.raw) as event:
    assert event.longitudinalPlan.hankPersonality.version == 0
