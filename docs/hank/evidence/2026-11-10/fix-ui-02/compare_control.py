"""Read-only baseline/current planner comparison, both forwarding to native MPC."""
import json
import subprocess
import types
import numpy as np
from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner, DPFlags
from openpilot.selfdrive.ui.tests.test_hank_personality import make_planner, publish

BASE = "b4980601b8cdbce109b5f8b46cf3d0200670d4bc"
source = subprocess.check_output(["git", "show", BASE + ":selfdrive/controls/lib/longitudinal_planner.py"], text=True)
old = types.ModuleType("baseline_planner")
exec(compile(source, "baseline_planner.py", "exec"), old.__dict__)

class Spy:
  def __init__(self, solver):
    self.solver = solver
    self.calls = []

  def set(self, stage, field, value):
    if field in ("p", "W", "yref"):
      self.calls.append((stage, field, np.array(value, copy=True)))
    return self.solver.set(stage, field, value)

  def cost_set(self, stage, field, value):
    if field in ("p", "W", "yref"):
      self.calls.append((stage, field, np.array(value, copy=True)))
    return self.solver.cost_set(stage, field, value)

  def __getattr__(self, name):
    return getattr(self.solver, name)

frames = 0
for stock in (False, True):
  for blended in (False, True):
    for personality in (0, 1, 2):
      cp = make_planner(stock).CP
      planners = [kind(cp) for kind in (old.LongitudinalPlanner, LongitudinalPlanner)]
      for planner in planners:
        planner.maa_helper = None
        planner.mpc.solver = Spy(planner.mpc.solver)
      for speed, flags in ((30/3.6, DPFlags.APM), (0., DPFlags.APM), (35/3.6, DPFlags.APM),
                           (40/3.6, DPFlags.APM), (41/3.6, DPFlags.APM), (0., 0),
                           (20., DPFlags.APM | DPFlags.DTSC | DPFlags.DASR)):
        for planner in planners:
          planner.mpc.solver.calls.clear()
          publish(planner, personality, speed, flags, blended)
        a, b = planners
        assert len(a.mpc.solver.calls) == len(b.mpc.solver.calls)
        assert {call[1] for call in a.mpc.solver.calls} == {"p", "W", "yref"}
        for x, y in zip(a.mpc.solver.calls, b.mpc.solver.calls, strict=True):
          assert x[:2] == y[:2]
          np.testing.assert_array_equal(x[2], y[2])
        for name in ("v_solution", "a_solution", "j_solution", "params", "yref"):
          np.testing.assert_array_equal(getattr(a.mpc, name), getattr(b.mpc, name))
          assert np.isfinite(getattr(b.mpc, name)).all()
        assert a.mpc.solution_status == b.mpc.solution_status == 0
        assert a.output_a_target == b.output_a_target
        assert a.output_should_stop == b.output_should_stop
        assert a.mpc.source == b.mpc.source
        frames += 1
print(json.dumps({"base": BASE, "frame_pairs": frames, "p_W_yref": "exact equal", "native_v_a_j": "exact equal finite",
                  "status": 0, "aTarget_shouldStop_source": "exact equal"}))
