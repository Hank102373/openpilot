"""PORT-03 max-accel oracle: TOP01003 615799f95e978fbf643d1e762d605b4d5b06499f."""
import importlib

import pytest


MODULE = 'openpilot.selfdrive.controls.lib.accel_personality'
try:
  helper = importlib.import_module(MODULE)
except ModuleNotFoundError as exc:
  if exc.name != MODULE:
    raise
  helper = None

# Frozen output from pinned B accel_profiles.py, not calculated by production code.
# Each row is (speed m/s, sport, normal, eco); acceleration is m/s².
BREAKPOINT_ORACLE = [
  (-0.001, 2, 2, 2),
  (0, 2, 2, 2),
  (0.001, 2.000000024975, 2.000000024975, 2.000000124875),
  (0.999, 2.000024950025, 2.000024950025, 2.000124750125),
  (1, 2, 2, 2),
  (1.001, 1.99997497500625, 1.9999750024925, 1.99987487503125),
  (2.999, 1.9000500124937498, 1.9001049575075, 1.50025006246875),
  (3, 1.9, 1.9, 1.5),
  (3.001, 1.8999500291569444, 1.8998949758352777, 1.4997499708430555),
  (5.999, 1.7501374416763888, 1.420197493331389, 0.7501625583236111),
  (6, 1.75, 1.42, 0.75),
  (6.001, 1.7498623729583334, 1.41980241378375, 0.7498375729020833),
  (7.999, 1.3001459562083337, 0.95013761621625, 0.6000458187645834),
  (8, 1.3, 0.95, 0.6),
  (8.001, 1.2998542176584629, 0.9498625656556111, 0.5999541883293518),
  (10.999, 1.1000613105082038, 0.8300419661777221, 0.5500233191706482),
  (11, 1.1, 0.83, 0.55),
  (11.001, 1.099938665950357, 0.82995799655061, 0.5499766620006667),
  (15.999, 0.8200417546329766, 0.6100307556993899, 0.4000200053326667),
  (16, 0.82, 0.61, 0.4),
  (16.001, 0.8199582576864687, 0.6099692566866561, 0.39998000574918746),
  (19.999, 0.7100297453135312, 0.5400177465633439, 0.3600129960008125),
  (20, 0.71, 0.54, 0.36),
  (20.001, 0.70997024730045, 0.5399822495000901, 0.3599869984002),
  (24.999, 0.5500230040495502, 0.45001600084991006, 0.28001400139980004),
  (25, 0.55, 0.45, 0.28),
  (25.001, 0.5499770031197361, 0.44998400032001595, 0.27998600016004804),
  (29.999, 0.48001159916026404, 0.38001160055998406, 0.22000880087995203),
  (30, 0.48, 0.38, 0.22),
  (30.001, 0.47998840019199607, 0.3799884001919961, 0.21999120025599486),
  (54.999, 0.25000919990400383, 0.1500091999040038, 0.0800055998720051),
  (55, 0.25, 0.15, 0.08),
  (55.001, 0.25, 0.15, 0.08),
]
INTERIOR_ORACLE = [
  (0.1, 2.000225, 2.000225, 2.001125),
  (0.6666666666666666, 2.0037037037037035, 2.0037037037037035, 2.0185185185185186),
  (5, 1.8388888888888888, 1.6088888888888886, 0.961111111111111),
  (10, 1.1467037037037038, 0.8492222222222222, 0.5631481481481482),
  (15, 0.8660266666666666, 0.64584, 0.42466666666666664),
  (27.777777778, 0.5045267489685761, 0.4083676268830672, 0.24337448559404118),
  (40, 0.3793599999999999, 0.27935999999999994, 0.15248),
  (60, 0.25, 0.15, 0.08),
]


def maximum(speed, profile):
  if helper is None:
    # Test-first counterfactual: execute current HANK's actual lookup so absence
    # is evidenced by a numerical mismatch, not only a missing import.
    from openpilot.selfdrive.controls.lib.longitudinal_planner import get_max_accel
    return get_max_accel(speed)
  return helper.get_max_accel(speed, profile)


@pytest.fixture
def api():
  assert helper is not None, 'PORT-03 validated helper is absent'
  return helper


def test_donor_numerical_presence():
  assert maximum(0., 2) == pytest.approx(2., rel=0, abs=1e-12)


@pytest.mark.parametrize('profile', [0, 1, 2], ids=['sport', 'normal', 'eco'])
@pytest.mark.parametrize('row', BREAKPOINT_ORACLE, ids=lambda row: f'v={row[0]}')
def test_breakpoint_neighborhood(profile, row):
  assert maximum(row[0], profile) == pytest.approx(row[profile + 1], rel=0, abs=1e-12)


@pytest.mark.parametrize('profile', [0, 1, 2], ids=['sport', 'normal', 'eco'])
@pytest.mark.parametrize('row', INTERIOR_ORACLE, ids=lambda row: f'v={row[0]}')
def test_interior_hermite(profile, row):
  assert maximum(row[0], profile) == pytest.approx(row[profile + 1], rel=0, abs=1e-12)


@pytest.mark.parametrize('profile', [0, 1, 2], ids=['sport', 'normal', 'eco'])
@pytest.mark.parametrize('speed', [-100., -1., 0., 55., 56., 60., 100.])
def test_domain_clipping(profile, speed):
  expected = 2. if speed <= 0 else [.25, .15, .08][profile]
  assert maximum(speed, profile) == pytest.approx(expected, rel=0, abs=1e-12)


@pytest.mark.parametrize(('name', 'value'), [('sport', 0), ('normal', 1), ('eco', 2), ('stock', 3)])
def test_profile_values(api, name, value):
  profile = getattr(api.AccelProfile, name)
  assert profile.value == value
  assert api.validate_profile(value) is profile
  assert api.validate_profile(profile) is profile
  if name != 'stock':
    assert api.get_max_accel(55., profile) == pytest.approx([.25, .15, .08][value], rel=0, abs=1e-12)


def test_stock_and_default_are_adapter_states_only(api):
  assert api.validate_profile() is api.AccelProfile.stock
  assert api.validate_profile(3) is api.AccelProfile.stock
  with pytest.raises(ValueError, match='stock'):
    api.get_max_accel(5., api.AccelProfile.stock)
  with pytest.raises(ValueError, match='stock'):
    api.get_max_accel(5.)


@pytest.mark.parametrize('profile', [-1, 4, 99])
def test_invalid_profile_value(api, profile):
  with pytest.raises(ValueError, match='profile'):
    api.validate_profile(profile)
  with pytest.raises(ValueError, match='profile'):
    api.get_max_accel(5., profile)


@pytest.mark.parametrize('profile', ['normal', 'invalid', '1', None, 1.0, True, False, [], {}])
def test_invalid_profile_type(api, profile):
  with pytest.raises(TypeError, match='profile'):
    api.validate_profile(profile)
  with pytest.raises(TypeError, match='profile'):
    api.get_max_accel(5., profile)


@pytest.mark.parametrize('speed', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_speed(api, speed):
  with pytest.raises(ValueError, match='speed'):
    api.get_max_accel(speed, 1)


@pytest.mark.parametrize('speed', [None, '5', True, [], 1j])
def test_invalid_speed_type(api, speed):
  with pytest.raises(TypeError, match='speed'):
    api.get_max_accel(speed, 1)


@pytest.mark.parametrize(('profile', 'expected'), [
  (0, 2.0037037037037035), (1, 2.0037037037037035), (2, 2.0185185185185186),
])
def test_donor_overshoot_is_preserved(profile, expected):
  actual = maximum(2 / 3, profile)
  assert actual > 2.
  assert actual == pytest.approx(expected, rel=0, abs=1e-12)
