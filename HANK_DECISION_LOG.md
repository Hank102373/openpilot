# HANK Decision Log

**Document:** HANK_DECISION_LOG.md  
**Version:** v1.0  
**Date:** 2026-09-14  
**Purpose:** Preserve architectural intent, rejected alternatives and evidence so later maintenance does not depend on memory.

---

## Status vocabulary

- **Accepted** — current implementation authority.
- **Provisional** — direction accepted but exact donor/constants/dependency closure still needs confirmation.
- **Rejected** — explicitly not selected unless a future decision supersedes this record.
- **Superseded** — replaced by a later decision entry.

---

## D-001 — A is the HANK baseline

**Status:** Accepted  
**Date:** 2026-09-14

**Decision**  
Use A (`dragonpilot/dragonpilot`, branch `0.10.3-pre-build`, commit `1986516b325cbf8d173f6ebaea989ed45673c49f`) as the sole platform baseline for HANK.

**Reason**

- A is the known-good real-car foundation for the user's 2022 Toyota Sienna Hybrid + C3X + extracted TSK.
- A already contains the required Toyota SecOC key path, authenticated steering/longitudinal path, Panda safety integration and DP feature framework.
- A has the DP functions the user wants to retain.
- Starting from A minimizes changes in the highest-risk Toyota/CAN/SecOC layers.

**Rejected**

- B as baseline.
- C as baseline.
- Whole-repository A/B/C merge.

**Evidence**

- A Toyota stack contains SecOC platform detection, key provisioning, freshness synchronization, authenticated Toyota control and Panda safety support.
- B/C contain desired behavior but also incompatible or unnecessary vehicle/schema/control differences.

---

## D-002 — HANK is a selective integration, not a git merge

**Status:** Accepted  
**Date:** 2026-09-14

**Decision**  
Integrate features outward from their exact behavior dependencies. Do not merge B/C branches into A wholesale.

**Reason**

- B and C are different snapshots/generations and include unrelated changes.
- Whole-file replacement can silently import vehicle, schema, safety or lateral dependencies.
- HANK needs traceable, independently revertible feature ports.

**Rejected**

- Merge B into A, then resolve conflicts.
- Merge C into A, then resolve conflicts.
- Replace complete A control directories with TOP equivalents.

---

## D-003 — Port known TOP behavior; do not invent a new longitudinal algorithm

**Status:** Accepted  
**Date:** 2026-09-14

**Decision**  
For the requested follow/stop/pull-away/acceleration behavior, TOP donor logic is the behavioral authority. HANK may adapt APIs and expose validated parameters, but must not replace the donor behavior with an unvalidated new formula.

**Reason**

- The user already knows the practical driving feel of TOP behavior.
- A new hybrid algorithm creates unnecessary convergence and regression risk.
- Behavior-preserving integration is easier to compare and debug.

**Rejected**

- New HANK longitudinal controller from scratch.
- Arbitrary blend of A+B+C constants without provenance.

---

## D-004 — Preserve the A Toyota/SecOC trust boundary

**Status:** Accepted  
**Date:** 2026-09-14

**Decision**  
Keep A as authority for Toyota interface, CarState, CarController, SecOC/TSK, Toyota CAN packing and Panda safety during Phase 1.

**Reason**

- This is the actual known-good vehicle-control/authentication path on the target Sienna.
- Validly signed commands and safety-approved commands are separate requirements; both paths must remain understood.
- Replacing this layer would multiply risk while providing little value for the requested behavioral features.

**Rejected**

- Whole B Toyota stack replacement.
- Whole C Toyota stack replacement.
- B/C Panda safety replacement.

**Protected components include**

- `SecOCKey` handling
- `/cache/params/SecOCKey`
- `opendbc/car/secoc.py`
- Toyota freshness/reset synchronization
- SecOC message counters
- `ACC_CONTROL_2`
- Toyota safety flags/whitelists

---

## D-005 — Preserve A/DP planner orchestration and DP features

**Status:** Accepted  
**Date:** 2026-09-14

**Decision**  
Keep A `LongitudinalPlanner` as the orchestration layer so A DP modules remain functional around the imported TOP behavior.

**Must preserve**

- ACM（Adaptive Coasting Mode，自適應滑行模式）
- AEM（Adaptive Experimental Mode，自適應實驗模式）
- DTSC（Dynamic Turn Speed Control，動態彎道速度控制）
- APM（Adaptive Personality Mode，自適應跟車性格）
- DASR（Dynamic Accel Slew Rate，動態加速度變化率）

**Reason**

These modules already have defined insertion points before/inside/after MPC processing. Replacing the entire planner with TOP would bypass or alter those semantics.

**Rejected**

- B planner as wholesale replacement.
- C planner as wholesale replacement.

---

## D-006 — Dynamic Follow donor is B / TOP01003

**Status:** Accepted architecture; constants/field closure still test-gated  
**Date:** 2026-09-14

**Decision**  
Use B (`TOP01003`) as canonical donor for Dynamic Follow.

**Strategy**  
Behavior-preserving rewrite/port into A-compatible longitudinal MPC.

**Reason**

- B is same-generation enough to integrate with the current A control architecture.
- B contains explicit personality-aware dynamic-follow behavior matching the requested feature family.

**Rejected**

- Importing B Toyota CarController merely to obtain follow behavior.

---

## D-007 — Stop-distance behavior comes from TOP donor logic, not A replacement

**Status:** Accepted architecture  
**Date:** 2026-09-14

**Decision**  
Use B-style personality-aware stop-distance parameterization in the HANK MPC integration while preserving A stopping/actuation stack.

**Important constraint**  
B's `COMFORT_BRAKE=1.75` is not automatically accepted merely because it appears in the same source file. It requires an explicit behavior/test decision.

**Reason**

Stop distance and comfort-brake dynamics are coupled in the math but are separate product decisions.

---

## D-008 — Lead pull-away donor is C / TOP096

**Status:** Accepted
**Date:** 2026-09-14

**Decision**  
Use C (`CT921/openpilot`, branch `TOP096`, commit `3d75e471c74fccf0067dcda8cfe1374cf1268215`) as the canonical PORT-02 donor for lead pull-away behavior. The frozen source is `selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py`, function `get_stopped_equivalence_factor(v_lead, v_ego)`.

The frozen behavior is:

```python
v_diff_offset = 0
if np.all(v_lead - v_ego > 0):
  v_diff_offset = np.clip((v_lead - v_ego) * 2, 0, 12)
  v_diff_offset = np.maximum(
    v_diff_offset * ((26 / 3.6 - v_ego) / (26 / 3.6)),
    0,
  )

stopped_equivalence = v_lead**2 / (2 * 2.5) + v_diff_offset
```

The trigger is a strict, horizon-wide `np.all()` over `v_lead - v_ego > 0`. Gain is 2, the pre-taper offset cap is 12 m, the taper endpoint is 26 km/h, and `COMFORT_BRAKE` is 2.5 m/s². `v_ego` is MPC `self.x0[1]`. The transform is applied independently to leadOne and leadTwo before obstacle/source selection. Missing synthetic leads use the same transform. Do not replace the horizon-wide gate with stage-wise logic or add epsilon, counters, hysteresis, or state.

**Reason**

The desired quick lead-departure response is closer to the older TOP behavior discussed during design review.

**Constraint**  
Only the required stopped-equivalence/pull-away behavior may be taken. Do not import C's old planner/LongControl generation.

PORT-02 explicitly excludes F-002 Stop Distance donor values, personality stop distance, `PARAM_DIM = 7`, `p[6]`, B `COMFORT_BRAKE = 1.75`, C `braking_offset`, C low-speed weight/jerk tuning, F-005 response tuning, donor Dynamic Follow, donor static `T_FOLLOW`, AccelController, donor planner, donor LongControl, Toyota interface/CarState/CarController, Panda, SecOC, cereal schema replacement, and radar implementation replacement.

C stopped-equivalence can coexist with current HANK `STOP_DISTANCE`, `COMFORT_BRAKE = 2.5`, `PARAM_DIM = 6`, PORT-01 Dynamic Follow, E-001 `accel_bounds`, and E-002 mode synchronization.

**Historical provenance and closure evidence**
This decision was originally Provisional on 2026-09-14, with C as the preferred donor and B/TOP01003 as comparison reference. `PORT02_CLOSURE` completed the required field-level dependency analysis and deterministic comparisons and returned `READY_C`. B (`TOP01003`, commit `615799f95e978fbf643d1e762d605b4d5b06499f`) remains comparison evidence only.

The source-level closure confirmed that the horizon-wide discontinuity is intentional donor behavior. It did not validate native solver output, C3X behavior, vehicle behavior, or deployment safety.

---

## D-009 — Acceleration Personality donor is B / TOP01003

**Status:** Accepted architecture  
**Date:** 2026-09-14

**Decision**  
Use B `accel_personality` logic as the donor for acceleration personality.

**Preferred HANK integration**

`HANK profile/Params -> donor accel personality -> A planner/control path`

**Rejected**

- Requiring B custom cereal schema solely to transport Toyota physical drive-mode state.
- Replacing A Toyota controller to obtain this feature.

---

## D-010 — HANK user profiles configure donor behavior

**Status:** Accepted  
**Date:** 2026-09-14

**Decision**  
Expose three HANK modes: `緊湊 / 一般 / 舒適`.

**Rules**

- Profiles configure donor algorithms; they are not independent longitudinal algorithms.
- Donor-original preset must remain available.
- Every exposed parameter requires unit/type/min/max/default/validation.
- Safety-relevant changes are applied only at controlled state boundaries, not arbitrarily each control cycle.

**Reason**

This gives tunability without losing provenance or creating an opaque HANK-only controller.

---

## D-011 — Preserve DP Toyota Stock Long

**Status:** Accepted  
**Date:** 2026-09-14

**Decision**  
Retain `dp_toyota_stock_lon` as a first-class operating mode.

When enabled:

- Toyota factory TSS ACC owns longitudinal gas/brake control.
- HANK/DP can retain lateral control per A behavior.
- HANK/TOP longitudinal behavior is bypassed.
- A Toyota/SecOC lateral path remains active where required.

**Reason**

This is both a user-requested mode and an important fallback path.

---

## D-012 — No engaged hot switch between HANK Long and Toyota TSS

**Status:** Accepted  
**Date:** 2026-09-14

**Decision**  
Do not dynamically flip ownership of longitudinal control while openpilot is engaged.

**Reason**

The mode affects `CarParams.openpilotLongitudinalControl`, Toyota safety flags, Panda safety configuration and control-process state. Treating it as a simple runtime `if/else` could leave overlapping or missing longitudinal ownership.

**Rejected**

- ACC OFF/ON alone as the reinitialization mechanism.
- Changing `dp_toyota_stock_lon` while continuing the same initialized `card`/Panda safety session.

---

## D-013 — Use an Offroad->Onroad cycle instead of full C3X reboot for mode change

**Status:** Accepted architecture; real-car validation mandatory  
**Date:** 2026-09-14

**Decision**  
For HANK<->TSS desired-mode changes:

1. Require driver takeover and openpilot disengagement.
2. Save `dp_toyota_stock_lon`.
3. Trigger the A-supported `OnroadCycleRequested` path.
4. Allow the short Offroad->Onroad lifecycle to rebuild `card`, `CarParams`, Toyota interface and Panda safety.
5. Use full C3X reboot only as fallback if cycle recovery fails.

**Reason**

- A already contains a deliberate short onroad-cycle mechanism.
- Panda safety resets its configured state when offroad and reloads from new CarParams on the next onroad transition.
- This avoids a full OS reboot and should substantially reduce switching time.

**Safety constraint**

Do not allow the UI to execute the cycle while openpilot remains engaged. First vehicle validation must be performed stationary in a safe environment.

---

## D-014 — Do not use `OpenpilotEnabledToggle` alone as the HANK/TSS reconfiguration mechanism

**Status:** Accepted  
**Date:** 2026-09-14

**Decision**  
Do not rely on toggling Dashcam/passive mode alone to apply Stock Long changes.

**Reason**

`OpenpilotEnabledToggle` is consumed during `card` initialization when passive/controller availability and safety configuration are built. Flipping the parameter without a control lifecycle restart does not rebuild the current initialized vehicle state.

---

## D-015 — Preserve DP non-longitudinal functionality by default

**Status:** Accepted  
**Date:** 2026-09-14

**Decision**  
HANK integration must not regress existing A functions that are unrelated to the selected TOP longitudinal ports, including DP lateral, Toyota utility, UI/device, external-radar and MAA capabilities.

**Reason**

HANK is intended to be an A/DP superset for the user's use case, not a reduced TOP conversion.

---

## D-016 — TOP01002 is evidence of partial SecOC support and is not a donor baseline

**Status:** Accepted  
**Date:** 2026-09-14

**Decision**  
Do not treat existence of `SecOCKey` support alone as proof of complete Toyota SecOC longitudinal support.

**Evidence**

TOP01002/TOP01002-C3 contained SecOC key loading and authenticated steering but explicitly forced `openpilotLongitudinalControl=False` for SecOC Toyota and lacked the later complete authenticated ACC_CONTROL_2/0x183 longitudinal path.

**Reason**

This historical example is a permanent warning against validating integration by file names or Params presence alone.

---

## D-017 — Generated MPC artifacts must match the final parameter dimension

**Status:** Accepted  
**Date:** 2026-09-14

**Decision**  
Regenerate ACADOS artifacts whenever the final HANK MPC parameter model differs from A.

**Reason**

B uses a different MPC parameter dimension from A. Mixing generated solver artifacts and Python model dimensions is invalid even if source code otherwise imports successfully.

---

## D-018 — Prototype branch is reference only

**Status:** Accepted  
**Date:** 2026-09-14

**Decision**  
Preserve `sienna-longitudinal-dev` for research history, but do not build production HANK incrementally on its invented launch abstraction.

**Reason**

The production architecture moved to donor-behavior preservation rather than a new HANK reinterpretation.

---

## Future decision-entry template

```text
## D-XXX — <title>

Status:
Date:

Decision:

Reason:

Rejected:

Evidence:

Risks / constraints:

Supersedes:
```

Never delete an old decision because it later became wrong. Mark it **Superseded** and add the replacement decision so the history remains auditable.
