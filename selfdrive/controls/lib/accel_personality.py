"""Maximum-acceleration curves from CT921/openpilot TOP01003.

Donor: 615799f95e978fbf643d1e762d605b4d5b06499f,
top/selfdrive/controls/lib/accel_personality/accel_profiles.py.
Copyright (c) 2021-, rav4kumar, Haibin Wen, sunnypilot, and other contributors.
Donor numerical routines are licensed under the MIT License.
"""
from enum import IntEnum
from numbers import Real

import numpy as np


class AccelProfile(IntEnum):
  sport = 0
  normal = 1
  eco = 2
  stock = 3


def validate_profile(profile: int | AccelProfile = AccelProfile.stock) -> AccelProfile:
  # Reject bool, floats, strings and unrelated enums rather than coercing them.
  if type(profile) not in (int, AccelProfile):
    raise TypeError('acceleration profile must be an int or AccelProfile')
  try:
    return AccelProfile(profile)
  except ValueError as exc:
    raise ValueError(f'unsupported acceleration profile: {profile}') from exc


# Speed in m/s; acceleration in m/s². Stock deliberately has no donor curve.
MAX_ACCEL_BREAKPOINTS = [0., 1., 3., 6., 8., 11., 16., 20., 25., 30., 55.]
MAX_ACCEL_PROFILES = {
  'eco':    [2.0, 2.0, 1.5, .75, .60, .55, .40, .36, .28, .22, .08],
  'normal': [2.0, 2.0, 1.9, 1.42, .95, .83, .61, .54, .45, .38, .15],
  'sport':  [2.0, 2.0, 1.9, 1.75, 1.3, 1.1, .82, .71, .55, .48, .25],
}


def _compute_symmetric_slopes(x, y):
  n = len(x)
  if n < 2:
    raise ValueError('At least two points are required to compute slopes.')
  m = np.zeros(n)
  for i in range(n):
    if i == 0:
      m[i] = (y[i+1] - y[i]) / (x[i+1] - x[i])
    elif i == n-1:
      m[i] = (y[i] - y[i-1]) / (x[i] - x[i-1])
    else:
      m[i] = ((y[i+1] - y[i]) / (x[i+1] - x[i]) + (y[i] - y[i-1]) / (x[i] - x[i-1])) / 2
  return m


MAX_ACCEL_SLOPES = {
  mode: _compute_symmetric_slopes(MAX_ACCEL_BREAKPOINTS, values)
  for mode, values in MAX_ACCEL_PROFILES.items()
}


def _hermite_interpolate(x, xp, yp, slopes):
  x = np.clip(x, xp[0], xp[-1])
  idx = np.searchsorted(xp, x) - 1
  idx = np.clip(idx, 0, len(slopes) - 1)

  x0, x1 = xp[idx], xp[idx+1]
  y0, y1 = yp[idx], yp[idx+1]
  m0, m1 = slopes[idx], slopes[idx+1]

  t = (x - x0) / (x1 - x0)
  h00 = 2*t**3 - 3*t**2 + 1
  h10 = t**3 - 2*t**2 + t
  h01 = -2*t**3 + 3*t**2
  h11 = t**3 - t**2
  return (h00 * y0) + (h10 * (x1 - x0) * m0) + (h01 * y1) + (h11 * (x1 - x0) * m1)


def get_max_accel(v_ego: float, profile: int | AccelProfile = AccelProfile.stock) -> float:
  """Return donor maximum acceleration (m/s²) for a finite scalar speed (m/s).

  Stock is an adapter bypass state; the caller must use the existing HANK
  lookup for it. This function does not impose any output clamp on Hermite.
  """
  selected = validate_profile(profile)
  if selected is AccelProfile.stock:
    raise ValueError('stock profile has no donor maximum curve; use the HANK adapter bypass')
  if isinstance(v_ego, bool) or not isinstance(v_ego, Real):
    raise TypeError('speed must be a real scalar')
  if not np.isfinite(v_ego):
    raise ValueError('speed must be finite')
  mode = selected.name
  return float(_hermite_interpolate(v_ego, MAX_ACCEL_BREAKPOINTS, MAX_ACCEL_PROFILES[mode], MAX_ACCEL_SLOPES[mode]))
