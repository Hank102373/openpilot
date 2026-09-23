"""D-019 config contract, using real Params storage without rebuilding native keys."""
import importlib
import json
from pathlib import Path
import re

import pytest

from openpilot.common.params import Params

REQUESTED = "HankConfigRequested"
ACTIVE = "HankConfigActive"
LATCH = "HankConfigSessionStarted"
LEGACY = "HankDynamicFollow"
LEGACY_ACTIVE = "HankDynamicFollowActive"
STOCK = {"version": 1, "dynamic_follow": False, "accel_profile": 3}


class TemporaryParams:
  """Only alias new key names until the native registry is rebuilt in A2/B.

  All writes still call native Params.put (including its atomic rename/fsync).
  Source-backed metadata tests below independently verify the new registry.
  """
  aliases = {REQUESTED: "LiveParameters", ACTIVE: "LastOffroadStatusPacket", LATCH: "IsOnroad"}

  def __init__(self, path):
    self.native = Params(str(path))
    if {REQUESTED.encode(), ACTIVE.encode(), LATCH.encode()} <= set(self.native.all_keys()):
      self.aliases = {}
    self.writes = []

  def get_param_path(self, key):
    return self.native.get_param_path(self.aliases.get(key, key))

  def put(self, key, value):
    self.writes.append((key, value))
    self.native.put(self.aliases.get(key, key), value)


@pytest.fixture
def params(tmp_path):
  return TemporaryParams(tmp_path / "params")


@pytest.fixture
def cfg():
  # Lazy import keeps the independent baseline registry assertion runnable.
  return importlib.import_module("openpilot.selfdrive.controls.lib.hank_config")


def raw(params, key, value):
  Path(params.get_param_path(key)).write_bytes(value)


def read(params, key):
  return Path(params.get_param_path(key)).read_bytes()


def seed_pair(params, config=STOCK):
  raw(params, ACTIVE, json.dumps(config).encode())
  raw(params, LATCH, b"1")


def registry_entries():
  source = Path(__file__).resolve().parents[3] / "common/params_keys.h"
  return dict(re.findall(r'\{"(Hank[^"]+)",\s*\{([^}]*)\}\}', source.read_text()))


def test_versioned_bundle_registry_contract():
  entries = registry_entries()
  expected = {
    REQUESTED: ["PERSISTENT", "JSON"],
    ACTIVE: ["CLEAR_ON_OFFROAD_TRANSITION | CLEAR_ON_IGNITION_ON", "JSON"],
    LATCH: ["CLEAR_ON_OFFROAD_TRANSITION | CLEAR_ON_IGNITION_ON", "BOOL"],
  }
  for key, fields in expected.items():
    assert key in entries, f"{key} absent: repository cannot store the required registered versioned config bundle"
    assert [field.strip() for field in entries[key].split(",")] == fields
  assert [s.strip() for s in entries[LEGACY].split(",")] == ["PERSISTENT", "BOOL", '"0"']
  assert [s.strip() for s in entries[LEGACY_ACTIVE].split(",")] == [
    "CLEAR_ON_OFFROAD_TRANSITION | CLEAR_ON_IGNITION_ON", "BOOL",
  ]


@pytest.mark.parametrize("profile", [0, 1, 2, 3])
@pytest.mark.parametrize("enabled", [False, True])
def test_schema_roundtrip(cfg, profile, enabled):
  expected = {"version": 1, "dynamic_follow": enabled, "accel_profile": profile}
  config = cfg.parse_config(json.dumps(expected).encode())
  assert json.loads(cfg.serialize_config(config)) == expected
  assert cfg.parse_config(cfg.serialize_config(config)) == config


INVALID = [
  b'{"dynamic_follow":false,"accel_profile":3}',
  b'{"version":1,"accel_profile":3}',
  b'{"version":1,"dynamic_follow":false}',
  b'{"version":1,"dynamic_follow":false,"accel_profile":3,"extra":0}',
  b'{"version":1,"version":1,"dynamic_follow":false,"accel_profile":3}',
  b'{"version":1,"dynamic_follow":false,"dynamic_follow":true,"accel_profile":3}',
  b'{"version":1,"dynamic_follow":false,"accel_profile":3,"accel_profile":2}',
  b'[]', b'null', b'1', b'"text"',
  *[json.dumps({**STOCK, "version": v}).encode() for v in [True, 1.0, "1", 2]],
  *[json.dumps({**STOCK, "dynamic_follow": v}).encode() for v in [0, 1, "false"]],
  *[json.dumps({**STOCK, "accel_profile": v}).encode() for v in [True, 1.0, "1", -1, 4, 10**50]],
  b'{', b'', b'\xff',
  b'{"version":1,"dynamic_follow":false,"accel_profile":NaN}',
  b'{"version":1,"dynamic_follow":false,"accel_profile":Infinity}',
  b'{"version":1,"dynamic_follow":false,"accel_profile":-Infinity}',
  json.dumps(STOCK).encode() + b' trailing',
]


@pytest.mark.parametrize("payload", INVALID)
def test_reject_invalid_json(cfg, payload):
  with pytest.raises(cfg.ConfigValidationError):
    cfg.parse_config(payload)


def test_raw_states(cfg, params, monkeypatch):
  assert cfg.read_config(params, REQUESTED).state == cfg.ReadState.MISSING
  raw(params, REQUESTED, json.dumps(STOCK).encode())
  assert cfg.read_config(params, REQUESTED).state == cfg.ReadState.VALID
  raw(params, REQUESTED, b"{")
  assert cfg.read_config(params, REQUESTED).state == cfg.ReadState.CORRUPT
  inject_read_error(monkeypatch, params, REQUESTED)
  assert cfg.read_config(params, REQUESTED).state == cfg.ReadState.IO_ERROR


def inject_read_error(monkeypatch, params, key):
  original = Path.read_bytes
  target = Path(params.get_param_path(key))

  def fail(path):
    if path == target:
      raise PermissionError("injected read failure")
    return original(path)
  monkeypatch.setattr(Path, "read_bytes", fail)


def test_missing_storage_is_io_error(cfg, params):
  path = Path(params.get_param_path(REQUESTED)).parent
  path.resolve().rmdir()
  assert cfg.read_config(params, REQUESTED).state == cfg.ReadState.IO_ERROR


def test_new_session_order_and_real_storage(cfg, params):
  result = cfg.initialize_session(params)
  assert result.action == "NEW_SESSION"
  assert json.loads(cfg.serialize_config(result.config)) == STOCK
  assert [key for key, _ in params.writes] == [LATCH, REQUESTED, ACTIVE]
  assert read(params, LATCH) == b"1"
  assert json.loads(read(params, REQUESTED)) == STOCK
  assert json.loads(read(params, ACTIVE)) == STOCK
  assert params.native.get(params.aliases.get(REQUESTED, REQUESTED)) == STOCK
  assert params.native.get(params.aliases.get(ACTIVE, ACTIVE)) == STOCK


@pytest.mark.parametrize("requested", [b"{", b"future", json.dumps({**STOCK, "accel_profile": 0}).encode()])
@pytest.mark.parametrize("legacy_active", [b"0", b"1", b"invalid"])
def test_reuse_pair_ignores_requested_and_legacy(cfg, params, monkeypatch, requested, legacy_active):
  seed_pair(params)
  raw(params, REQUESTED, requested)
  raw(params, LEGACY_ACTIVE, legacy_active)
  # Reading Requested or legacy Active would fail: neither may be consulted.
  original = Path.read_bytes

  def restricted(path):
    assert path not in [Path(params.get_param_path(REQUESTED)), Path(params.get_param_path(LEGACY_ACTIVE))]
    return original(path)
  monkeypatch.setattr(Path, "read_bytes", restricted)
  result = cfg.initialize_session(params)
  assert result.action == "REUSE_ACTIVE"
  assert json.loads(cfg.serialize_config(result.config)) == STOCK
  assert not params.writes


@pytest.mark.parametrize("legacy_active", [b"0", b"1", b"bad", b"", b"true"])
def test_legacy_active_blocks_migration(cfg, params, legacy_active):
  raw(params, LEGACY_ACTIVE, legacy_active)
  params.native.put_bool(LEGACY, True)
  with pytest.raises(cfg.SessionError, match="REJECT_AND_WAIT_NEW_SESSION"):
    cfg.initialize_session(params)
  assert not params.writes
  assert not Path(params.get_param_path(REQUESTED)).exists()
  assert read(params, LEGACY_ACTIVE) == legacy_active


def test_legacy_active_io_error(cfg, params, monkeypatch):
  inject_read_error(monkeypatch, params, LEGACY_ACTIVE)
  with pytest.raises(cfg.SessionError, match="IO_ERROR"):
    cfg.initialize_session(params)
  assert not params.writes


def test_modeled_lifecycle_allows_migration(cfg, params):
  params.native.put_bool(LEGACY, True)
  raw(params, LEGACY_ACTIVE, b"0")
  with pytest.raises(cfg.SessionError):
    cfg.initialize_session(params)
  # Model the frozen offroad clear; A2/B tests the rebuilt native key flags.
  for key in [ACTIVE, LATCH, LEGACY_ACTIVE]:
    Path(params.get_param_path(key)).unlink(missing_ok=True)
  result = cfg.initialize_session(params)
  assert result.reason == "MIGRATED_LEGACY"
  assert result.config.dynamic_follow is True
  assert result.config.accel_profile == 3
  assert params.native.get(LEGACY) is True


@pytest.mark.parametrize("active,latch", [
  (None, b"1"), (json.dumps(STOCK).encode(), None),
  (b"{", b"1"), (json.dumps({**STOCK, "version": 2}).encode(), b"1"),
  *[(json.dumps(STOCK).encode(), value) for value in [b"0", b"", b"true", b"bad"]],
  *[(None, value) for value in [b"0", b"", b"true", b"bad"]],
])
def test_reject_inconsistent_session(cfg, params, active, latch):
  if active is not None:
    raw(params, ACTIVE, active)
  if latch is not None:
    raw(params, LATCH, latch)
  with pytest.raises(cfg.SessionError, match="REJECT_AND_WAIT_NEW_SESSION"):
    cfg.initialize_session(params)
  assert not params.writes


@pytest.mark.parametrize("key", [REQUESTED, ACTIVE, LATCH, LEGACY])
def test_read_io_failure(cfg, params, monkeypatch, key):
  inject_read_error(monkeypatch, params, key)
  with pytest.raises(cfg.SessionError, match="IO_ERROR"):
    cfg.initialize_session(params)
  assert not Path(params.get_param_path(ACTIVE)).exists()


@pytest.mark.parametrize("legacy,reason,enabled", [
  (b"0", "MIGRATED_LEGACY", False), (b"1", "MIGRATED_LEGACY", True),
  (None, "DEFAULT_NO_REQUEST", False), (b"bad", "RECOVERED_CORRUPT_LEGACY", False),
  (b"", "RECOVERED_CORRUPT_LEGACY", False),
])
def test_legacy_requested_migration(cfg, params, legacy, reason, enabled):
  if legacy is not None:
    raw(params, LEGACY, legacy)
  result = cfg.initialize_session(params)
  assert result.reason == reason
  assert json.loads(read(params, REQUESTED)) == {**STOCK, "dynamic_follow": enabled}
  assert json.loads(read(params, ACTIVE)) == {**STOCK, "dynamic_follow": enabled}
  if legacy is not None:
    assert read(params, LEGACY) == legacy


@pytest.mark.parametrize("payload", [b"{", b"", json.dumps({**STOCK, "version": 2}).encode()])
def test_corrupt_requested_recovers_without_overwrite(cfg, params, payload):
  raw(params, REQUESTED, payload)
  params.native.put_bool(LEGACY, True)
  result = cfg.initialize_session(params)
  assert result.reason.startswith("RECOVERED_CORRUPT_REQUESTED")
  assert json.loads(read(params, ACTIVE)) == {
    "version": 2, "dynamic_follow": False, "hank_profile": "original", "accel_profile": 3,
  }
  assert read(params, REQUESTED) == payload
  assert [key for key, _ in params.writes] == [LATCH, ACTIVE]


def test_requested_is_authority(cfg, params):
  expected = {**STOCK, "accel_profile": 2}
  raw(params, REQUESTED, json.dumps(expected).encode())
  params.native.put_bool(LEGACY, True)
  result = cfg.initialize_session(params)
  assert result.reason == "REQUESTED"
  assert json.loads(cfg.serialize_config(result.config)) == expected
  assert [key for key, _ in params.writes] == [LATCH, ACTIVE]


@pytest.mark.parametrize("key", [LATCH, REQUESTED, ACTIVE])
@pytest.mark.parametrize("failure", ["raise", "missing", "mismatch", "corrupt", "read_error"])
def test_write_verification_and_interrupted_restart(cfg, params, monkeypatch, key, failure):
  original = params.put

  def interrupted(write_key, value):
    if write_key != key:
      return original(write_key, value)
    if failure == "raise":
      raise OSError("injected write failure")
    if failure == "missing":
      return None
    original(write_key, value)
    if failure == "read_error":
      inject_read_error(monkeypatch, params, key)
    else:
      replacement = b"0" if key == LATCH else json.dumps({**STOCK, "accel_profile": 0}).encode()
      raw(params, key, b"{" if failure == "corrupt" else replacement)
    return None

  monkeypatch.setattr(params, "put", interrupted)
  with pytest.raises(cfg.SessionError):
    cfg.initialize_session(params)
  monkeypatch.undo()
  # Once a valid latch exists, an incomplete snapshot may not reread Requested.
  if key in [REQUESTED, ACTIVE]:
    before = list(params.writes)
    with pytest.raises(cfg.SessionError, match="REJECT_AND_WAIT_NEW_SESSION"):
      cfg.initialize_session(params)
    assert params.writes == before


def test_save_and_stock_restore_preserves_session(cfg, params):
  seed_pair(params, {**STOCK, "dynamic_follow": True, "accel_profile": 0})
  before = read(params, ACTIVE), read(params, LATCH)
  config = cfg.parse_config(json.dumps({**STOCK, "accel_profile": 1}).encode())
  assert cfg.save_requested(params, config) == config
  assert json.loads(read(params, REQUESTED)) == {**STOCK, "accel_profile": 1}
  cfg.restore_stock(params)
  assert json.loads(read(params, REQUESTED)) == STOCK
  assert (read(params, ACTIVE), read(params, LATCH)) == before
  assert all(key == REQUESTED for key, _ in params.writes)


def test_save_validates_before_write(cfg, params):
  with pytest.raises(cfg.ConfigValidationError):
    cfg.save_requested(params, cfg.HankConfig(version=True, dynamic_follow=False, accel_profile=3))
  assert not params.writes



def test_snapshot_verifies_latch_before_requested(cfg, params, monkeypatch):
  original = Path.read_bytes
  latch_verified = False

  def observe(path):
    nonlocal latch_verified
    result = original(path)
    if path == Path(params.get_param_path(LATCH)) and result == b"1":
      latch_verified = True
    return result

  original_put = params.put

  def ordered_put(key, value):
    if key == REQUESTED:
      assert latch_verified
      assert not Path(params.get_param_path(ACTIVE)).exists()
    elif key == ACTIVE:
      assert latch_verified
      assert json.loads(read(params, REQUESTED)) == STOCK
    return original_put(key, value)

  monkeypatch.setattr(Path, "read_bytes", observe)
  monkeypatch.setattr(params, "put", ordered_put)
  cfg.initialize_session(params)


def test_latch_only_restart_does_not_read_requested(cfg, params, monkeypatch):
  raw(params, LATCH, b"1")
  original = Path.read_bytes

  def reject_requested(path):
    assert path != Path(params.get_param_path(REQUESTED))
    return original(path)

  monkeypatch.setattr(Path, "read_bytes", reject_requested)
  with pytest.raises(cfg.SessionError, match="REJECT_AND_WAIT_NEW_SESSION"):
    cfg.initialize_session(params)
  assert not params.writes


def test_requested_changes_apply_only_next_session(cfg, params):
  cfg.initialize_session(params)
  next_config = cfg.HankConfig(dynamic_follow=True, accel_profile=0)
  cfg.save_requested(params, next_config)
  assert cfg.initialize_session(params).config == cfg.STOCK_CONFIG
  for key in [ACTIVE, LATCH, LEGACY_ACTIVE]:
    Path(params.get_param_path(key)).unlink(missing_ok=True)
  result = cfg.initialize_session(params)
  assert result.action == "NEW_SESSION"
  assert result.config == next_config


def test_legacy_requested_changes_never_regain_authority(cfg, params):
  params.native.put_bool(LEGACY, True)
  assert cfg.initialize_session(params).config.dynamic_follow is True
  params.native.put_bool(LEGACY, False)
  for key in [ACTIVE, LATCH]:
    Path(params.get_param_path(key)).unlink()
  assert cfg.initialize_session(params).config.dynamic_follow is True


def test_save_semantic_readback_equality(cfg, params, monkeypatch):
  original = params.put

  def reorder(key, value):
    original(key, value)
    raw(params, key, b'{ "accel_profile":3, "dynamic_follow":false, "version":1 }')

  monkeypatch.setattr(params, "put", reorder)
  assert cfg.save_requested(params, cfg.STOCK_CONFIG) == cfg.STOCK_CONFIG


def test_readback_corruption_remains_corrupt_not_missing(cfg, params):
  raw(params, REQUESTED, b"")
  result = cfg.read_config(params, REQUESTED)
  assert result.state == cfg.ReadState.CORRUPT


def test_dangling_key_is_io_error(cfg, params):
  path = Path(params.get_param_path(REQUESTED))
  path.symlink_to(path.parent / "absent-target")
  assert cfg.read_config(params, REQUESTED).state == cfg.ReadState.IO_ERROR
