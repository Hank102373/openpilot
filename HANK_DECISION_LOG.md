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

**Status:** Accepted — PORT-03 field-level boundary frozen (`READY_B_ADAPTER`)

**Date:** 2026-09-14

**Decision**  
Use B `accel_personality` logic as the donor for acceleration personality.

**Preferred HANK integration**

`HANK profile/Params -> donor accel personality -> A planner/control path`

**Rejected**

- Requiring B custom cereal schema solely to transport Toyota physical drive-mode state.
- Replacing A Toyota controller to obtain this feature.

**PORT-03 frozen closure**

Canonical source is B (`CT921/openpilot`, branch `TOP01003`, commit `615799f95e978fbf643d1e762d605b4d5b06499f`), specifically the maximum-acceleration personality curves in `top/selfdrive/controls/lib/accel_personality/accel_profiles.py`. PORT-03 uses a thin HANK-owned validated input adapter and does not import B product-specific input plumbing.

The acceleration profile values are `sport = 0`, `normal = 1`, `eco = 2`, and `stock = 3`. Speed is in m/s and acceleration is in m/s². The frozen maximum-acceleration data is:

```text
MAX_ACCEL_BREAKPOINTS = [0., 1., 3., 6., 8., 11., 16., 20., 25., 30., 55.]
eco    = [2.0, 2.0, 1.5, .75, .60, .55, .40, .36, .28, .22, .08]
normal = [2.0, 2.0, 1.9, 1.42, .95, .83, .61, .54, .45, .38, .15]
sport  = [2.0, 2.0, 1.9, 1.75, 1.3, 1.1, .82, .71, .55, .48, .25]
```

Interpolation is donor-exact cubic Hermite. Input speed is first clipped to the breakpoint domain. For secants `d[i] = (y[i+1] - y[i]) / (x[i+1] - x[i])`, endpoint slopes are `m[0] = d[0]` and `m[-1] = d[-1]`, and interior slopes are `m[i] = (d[i-1] + d[i]) / 2`. Segment selection remains `np.searchsorted(xp, x) - 1`. No output clamp or monotonicity limiter is added to remove donor Hermite overshoot.

The HANK adapter accepts an explicit validated acceleration profile. `stock` or the default preserves current A/HANK `get_max_accel()` behavior; `normal`, `eco`, and `sport` select the exact B maximum curve. Unsupported types or values are rejected explicitly without silent fallback. The selection is immutable for the planner instance in PORT-03. Params persistence, live profile changes, and HANK three-mode mapping belong to CFG-01.

PORT-03 applies only to the ACC base upper-acceleration cap after the final AEM mode and E-002 MPC mode synchronization, and before turn limiting, MAA, reset/coast handling, DTSC, MPC, ACM, output selection, DASR, and final output clipping. Blended mode does not directly apply the donor profile upper. DTSC OFF retains the existing MPC `p[0:2]` defaults; DTSC ON receives the personality-limited base upper through the existing E-001 intersection, so personality cannot loosen DTSC. Donor minimum profiles are not written into `p[0]`.

APM remains limited to `LongitudinalPersonality`; it is not automatically mapped to acceleration personality. Existing AEM, ACM, DASR, PORT-01 Dynamic Follow, PORT-02 stopped-equivalence, and Toyota Stock Long ownership remain authoritative. `CP.openpilotLongitudinalControl == False` must effectively bypass PORT-03.

**Explicit PORT-03 exclusions**

- Toyota physical SPORT/ECON selection, `ToyotaDriveMode`, `CarState.accelProfile`, B custom cereal acceleration-personality schema, and `longitudinalPlanTOP` telemetry
- Whole `AccelController`, its polling/state/frame counter, and MPC `AccelController` synchronization
- B minimum-acceleration profile and lower-profile cruise-envelope activation
- B low-speed jerk and acceleration-change weight factors, B `COMFORT_BRAKE = 1.75`, C `braking_offset`, donor response tuning, and donor slew policy
- Toyota interface/CarState/CarController, Panda, SecOC, cereal replacement, donor planner/LongControl, and generated donor solver artifacts

F-005 remains a separate unresolved numerical and solver decision.

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

## D-019 — CFG-01 v1 uses a versioned requested/session configuration

**Status:** Accepted — CFG-01 closure complete (`READY_CFG01`)

**Date:** 2026-09-16

**Decision**

CFG-01 v1 is selection-only configuration. It externalizes the PORT-01 Dynamic Follow enable and PORT-03 acceleration-profile selection. It does not externalize numerical donor values and does not add a HANK three-mode selector.

The sole v1 config authority is one versioned Requested JSON, one versioned Active JSON, and a session latch:

| Key | Type | Flags | Registry default |
|---|---|---|---|
| `HankConfigRequested` | JSON | `PERSISTENT` | none |
| `HankConfigActive` | JSON | `CLEAR_ON_OFFROAD_TRANSITION | CLEAR_ON_IGNITION_ON` | none |
| `HankConfigSessionStarted` | BOOL | `CLEAR_ON_OFFROAD_TRANSITION | CLEAR_ON_IGNITION_ON` | none |

The latch carries no feature selection. It distinguishes a new session from same-session Active loss or an interrupted snapshot. External processes must not write or delete Active or the latch.

**V1 schema**

Requested and Active use the exact schema:

```json
{
  "version": 1,
  "dynamic_follow": false,
  "accel_profile": 3
}
```

- `version` is an integer exactly equal to 1.
- `dynamic_follow` is a JSON boolean.
- `accel_profile` is an integer: sport 0, normal 1, eco 2, stock 3.
- Boolean, float, and string substitutes for integer fields are rejected.
- Missing fields, unknown fields, duplicate keys, a non-object root, and unsupported versions are rejected.
- The stock/default bundle is exactly version 1, Dynamic Follow false, and acceleration profile stock.
- `LongitudinalPersonality` is not part of v1.

**Owner and snapshot**

`plannerd` is the snapshot owner. After valid `CarParams` is available and before constructing `LongitudinalPlanner`, it:

1. inspects Active and the latch;
2. reuses a fully valid pair;
3. when both are absent in a valid new session, writes and reads back latch=true;
4. obtains a validated Requested, migration result, or explicit recovery bundle;
5. atomically writes and reads back the complete Active JSON;
6. validates Active again; and
7. only then constructs the planner.

A Requested change does not change Active during the current session. A standalone `plannerd` restart reuses valid Active. Writes are atomic per Params key; the latch-first order turns an interrupted snapshot into an invalid session state rather than a second Requested snapshot.

**Apply lifecycle**

CFG-01 v1 applies on the next onroad session only.

- Requested writes store a candidate and do not change current behavior.
- A normal offroad transition clears Active and the latch.
- The next onroad initialization snapshots the latest valid Requested.
- A valid synthetic `OnroadCycleRequested` cycle follows the same offroad-clear and next-onroad path.
- A normal manager restart, new ignition, or C3X reboot clears/rebuilds session state while preserving Requested.
- A standalone planner restart and disengage/re-engage without a lifecycle transition reuse Active.
- CFG-01 neither triggers `OnroadCycleRequested` nor treats its consumer as a disengagement safety gate.
- Arbitrary and disengaged live apply are outside v1.

Lifecycle clearing is not safety authorization.

**Stock Long, APM, and product modes**

When `CP.openpilotLongitudinalControl == False`, Requested remains stored and Active is still snapshotted without forcing its fields to stock/false. Existing CP guards bypass both configured behaviors. A TSS-to-HANK owner change still requires the D-012/D-013 rebuild cycle; the new HANK session snapshots the latest Requested.

APM continues to override only effective `LongitudinalPersonality`. It does not modify Requested, Active, AccelProfile, or Dynamic Follow enable. The gap button keeps its existing selfdrived path and does not write CFG.

Future `緊湊 / 一般 / 舒適` modes are HANK product selectors, not aliases for donor enums. Their exact mapping is deferred and is not represented in the v1 schema.

**Restore and recovery**

The stock/default restore writes the complete stock bundle and applies next session. Donor-original restore is per field: Dynamic Follow true selects the frozen PORT-01 donor behavior, while PORT-03 requires an explicit sport, normal, or eco choice. There is no invented universal B donor mode.

- A valid Active/latch pair is reused even if Requested changes or becomes corrupt.
- On a new session, a missing Requested invokes the legacy migration. If no legacy request exists, the explicit stock bundle is used.
- An invalid, corrupt, or unsupported Requested on a new session falls back to the stock bundle with an explicit recorded reason; the original corrupt value is not silently rewritten.
- Corrupt/unsupported Active, latch-without-Active, Active-without-valid-latch, or snapshot I/O/readback failure rejects initialization and waits for a new session. It must not reread Requested and continue in the same session.
- Missing, corrupt, and I/O failure are distinct states. The adapter must strictly parse raw stored JSON rather than relying on a typed read that can collapse malformed data to `None`.

**Migration, downgrade, and reset**

Schema version 1 accepts only its exact fields. The HANK config adapter owns migration; v1 does not add a generic migration framework.

Only when `HankConfigRequested` truly does not exist, legacy `HankDynamicFollow` raw `"0"` or `"1"` is migrated, with acceleration profile stock. A missing legacy request means false. The adapter saves the complete new Requested before constructing Active. After migration, the JSON is the sole CFG authority; legacy key definitions remain for old-version compatibility, and `HankDynamicFollowActive` is not new runtime authority.

A controlled downgrade occurs at an offroad/manager-restart boundary. Before downgrade, export Requested and write the desired legacy Dynamic Follow value. A PORT-03 baseline uses stock acceleration because its production caller does not consume a profile Param. Transparent downgrade compatibility is not claimed.

A HANK reset writes the complete stock/default Requested and does not clear current Active or alter APM, `LongitudinalPersonality`, DP toggles, or Stock Long ownership. Existing `dp_dev_reset_conf` behavior is unchanged. A future UI needs a separate HANK reset/restore action.

**Implementation boundary**

Required production scope is `common/params_keys.h`, `selfdrive/controls/plannerd.py`, and a small new `selfdrive/controls/lib/hank_config.py` adapter. Required tests are a new `selfdrive/controls/tests/test_hank_config.py` and updates to `selfdrive/controls/tests/test_dynamic_follow.py`; `test_accel_personality_planner.py` is optional for additional evidence.

CFG-01 excludes production changes to `longitudinal_planner.py`, `accel_personality.py`, `long_mpc.py`, manager, Toyota, Panda, SecOC, LongControl, cereal, UI, F-005, and generated solver artifacts.

**Deferred**

The exact three-mode mapping, UI, numerical field externalization, follow/stop-distance tuning, F-005, disengaged live apply, and possible future DP-toggle bundling remain separate decisions. C3X bench, V0-V3, P0/SecOC/Toyota release acceptance, and Phase 1 completion remain outstanding.

**Rejected**

- Multiple independent Params fields as the v1 CFG authority.
- Per-cycle or disengaged live application in v1.
- Treating enum numeric equality as a semantic product-mode mapping.
- Treating lifecycle clearing or `OnroadCycleRequested` consumption as safety authorization.

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
