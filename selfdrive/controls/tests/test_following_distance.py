import itertools
from dataclasses import dataclass

import numpy as np
import pytest
from parameterized import parameterized_class

from cereal import log

from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import desired_follow_distance, get_STOP_DISTANCE, get_T_FOLLOW
from openpilot.selfdrive.test.longitudinal_maneuvers import maneuver
from openpilot.selfdrive.test.longitudinal_maneuvers.plant import Plant


PERSONALITIES = (
  ("relaxed", log.LongitudinalPersonality.relaxed),
  ("standard", log.LongitudinalPersonality.standard),
  ("aggressive", log.LongitudinalPersonality.aggressive),
)


@dataclass(frozen=True)
class FollowingDistanceResult:
  valid: bool
  gap: float
  speed: float
  acceleration: float
  source: str
  solution_status: int
  solver_arrays: tuple[np.ndarray, ...]


class ObservablePlant(Plant):
  last_instance = None

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    type(self).last_instance = self


def run_following_distance_simulation(v_lead, monkeypatch, t_end=100.0, e2e=False, personality=0):
  man = maneuver.Maneuver(
    '',
    duration=t_end,
    initial_speed=float(v_lead),
    lead_relevancy=True,
    initial_distance_lead=100,
    speed_lead_values=[v_lead],
    breakpoints=[0.],
    e2e=e2e,
    personality=personality,
  )

  ObservablePlant.last_instance = None
  monkeypatch.setattr(maneuver, "Plant", ObservablePlant)
  valid, output = man.evaluate()

  plant = ObservablePlant.last_instance
  assert plant is not None
  mpc = plant.planner.mpc
  return FollowingDistanceResult(
    valid=valid,
    gap=float(output[-1, 2] - output[-1, 1]),
    speed=float(output[-1, 3]),
    acceleration=float(output[-1, 5]),
    source=mpc.source,
    solution_status=mpc.solution_status,
    solver_arrays=(mpc.params, mpc.x_sol, mpc.u_sol, mpc.v_solution, mpc.a_solution, mpc.j_solution),
  )


@parameterized_class(("e2e", "personality", "speed"), itertools.product(
                      [True, False],
                      [log.LongitudinalPersonality.relaxed,
                       log.LongitudinalPersonality.standard,
                       log.LongitudinalPersonality.aggressive],
                      [10, 35]))
class TestMovingFollowingDistance:
  def test_following_distance(self, monkeypatch):
    v_lead = float(self.speed)
    result = run_following_distance_simulation(v_lead, monkeypatch, e2e=self.e2e, personality=self.personality)
    assert result.valid

    expected = desired_follow_distance(
      v_lead,
      v_lead,
      get_T_FOLLOW(self.personality),
      get_STOP_DISTANCE(self.personality),
    )
    err_ratio = 0.2 if self.e2e else 0.1
    assert result.gap == pytest.approx(expected, abs=err_ratio * expected + .5)


@pytest.mark.parametrize("e2e", [True, False])
def test_zero_speed_following_distance(e2e, monkeypatch):
  results = {}

  for name, personality in PERSONALITIES:
    result = run_following_distance_simulation(0.0, monkeypatch, e2e=e2e, personality=personality)
    results[name] = result

    assert result.valid
    assert np.isfinite((result.gap, result.speed, result.acceleration)).all()
    assert all(np.isfinite(array).all() for array in result.solver_arrays)
    assert result.solution_status == 0
    assert 0.0 <= result.speed < 0.01
    assert abs(result.acceleration) < 1e-3
    assert result.source == "lead0"

  assert results["relaxed"].gap > results["standard"].gap
  assert results["relaxed"].gap > results["aggressive"].gap
