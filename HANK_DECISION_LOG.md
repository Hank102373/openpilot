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

Legacy Active guard clarification: when `HankConfigActive` and `HankConfigSessionStarted` are both missing, new-CFG session initialization is allowed only if legacy `HankDynamicFollowActive` is also truly missing. If legacy Active exists, raw `"0"`, raw `"1"`, malformed content, or any other content all mean that a legacy session snapshot exists and require `REJECT_AND_WAIT_NEW_SESSION`; false does not mean that no snapshot exists. A legacy Active I/O error fails initialization and is not classified as missing. If a valid new Active/latch pair already exists, it is reused and remains authoritative regardless of legacy Active. The adapter does not delete legacy Active, trigger a lifecycle cycle, or resnapshot Requested in the same session.

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

## D-020 — F-002 uses TOP01003 personality stop distance as MPC p[6]

**Status:** Accepted — F-002 donor/dependency/numerical closure complete (`READY_F002`)

**Date:** 2026-09-17

**Decision**

Use B (`CT921/openpilot`, branch `TOP01003`, commit `615799f95e978fbf643d1e762d605b4d5b06499f`) as the canonical F-002 donor. The frozen source is `selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py`, especially `get_STOP_DISTANCE()`, `get_safe_obstacle_distance()`, `desired_follow_distance()`, `gen_long_model()`, `gen_long_ocp()`, and `LongitudinalMpc.update()`.

The exact donor presets are:

| `LongitudinalPersonality` | `stop_distance` (m) |
|---|---:|
| relaxed | 4.5 |
| standard | 4.0 |
| aggressive | 4.0 |

The HANK port increases `PARAM_DIM` from 6 to 7 and appends `stop_distance` at `p[6]`. Existing meanings and positions remain unchanged:

| Parameter | Meaning |
|---|---|
| `p[0]` | `a_min` |
| `p[1]` | `a_max` |
| `p[2]` | selected `x_obstacle` |
| `p[3]` | `prev_a` |
| `p[4]` | `lead_t_follow` |
| `p[5]` | `lead_danger_factor` |
| `p[6]` | personality-selected `stop_distance` |

`p[6]` is a live ACADOS parameter at every one of the `N+1` horizon rows. The symbolic comfort distance used by both the obstacle cost and danger-zone constraint is:

```text
safe(v_ego, t_follow, stop_distance)
  = v_ego**2 / (2 * COMFORT_BRAKE)
  + t_follow * v_ego
  + stop_distance
```

The lead-relative desired distance remains:

```text
desired(v_ego, v_lead, t_follow, stop_distance)
  = safe(v_ego, t_follow, stop_distance)
  - get_stopped_equivalence_factor(v_lead, v_ego)
```

The current C/TOP096-derived stopped-equivalence transform remains authoritative. F-002 does not replace it with B's pull-away formula. The selected stop distance must also be used for the ACC cruise obstacle and both blended-mode lead-comfort/source checks. Populating only the ACC branch would create inconsistent cost, constraint, and source-selection semantics.

**HANK compatibility boundary**

- Keep `COMFORT_BRAKE = 2.5` m/s². B's `COMFORT_BRAKE = 1.75` is donor context and an excluded F-005/numerical decision, not an F-002 dependency.
- Preserve E-001 `p[0:2]` acceleration-bound behavior, E-002 final mode synchronization, PORT-01 Dynamic Follow at `p[4]`, PORT-02 stopped equivalence and obstacle selection at `p[2]`, and PORT-03 acceleration-profile bounds.
- Use the effective `LongitudinalPersonality` already passed from `LongitudinalPlanner` to the MPC. Consequently, the existing gap-button personality and APM's existing effective-personality override select the corresponding frozen donor preset. F-002 adds no APM/gap handling, writes no personality state, and adds no CFG authority.
- CFG-01 v1 remains exactly `{version, dynamic_follow, accel_profile}`. It gains no stop-distance field and no schema change.
- With `CP.openpilotLongitudinalControl == False`, the planner may calculate a stop-distance parameter, but `controlsd` keeps `CC.longActive` false and factory TSS retains longitudinal actuation authority. F-002 does not change the Stock Long boundary.

The B `ToyotaTune` hook (`+0.5 m` when `ToyotaTune` is true and `SMART_DSU` is absent) is a rejected donor side effect. Do not import its Params read, Toyota flag dependency, or correction. C is comparison evidence only: at commit `3d75e471c74fccf0067dcda8cfe1374cf1268215` it also uses `PARAM_DIM = 7` and `p[6]`, with relaxed/standard/aggressive values 5.0/4.5/4.0 and `COMFORT_BRAKE = 2.5`; its `+1.5 m` Toyota/dynamic-follow correction and braking-offset logic are outside F-002.

**Why seven parameters are required**

Runtime/personality-selectable stop distance participates inside the generated nonlinear cost and constraint expressions. A six-parameter solver can change it only by rebuilding for each value or by overloading an existing parameter such as `x_obstacle`. Rebuilding per value is not runtime selection; shifting `x_obstacle` changes its established obstacle/source meaning and does not faithfully represent an independent comfort-distance input throughout ACC and blended logic. Neither is a credible compatible implementation. The source model, generated solver, Python parameter array, and runtime API must therefore all agree on seven parameters.

Regenerate from the final HANK model; never copy B generated files. `selfdrive/controls/lib/longitudinal_mpc_lib/SConscript` defines the generator as:

```text
cd selfdrive/controls/lib/longitudinal_mpc_lib && python3 long_mpc.py
```

and the repository build as:

```text
scons -u -j4
```

Affected ignored/generated outputs include `acados_ocp_long.json`, the `c_generated_code` model/cost/constraint C sources and headers, `acados_solver_long.c/.h`, `acados_sim_solver_long.c/.h`, `acados_solver.pxd`, Cython output, and the native solver/Cython shared libraries. Implementation evidence must show `PARAM_DIM == 7`, symbolic `model.p` length 7, JSON `np == 7`, generated `LONG_NP == 7` and `casadi_np == 7`, runtime `params.shape == (N+1, 7)`, and successful native `set('p')`/solve. Clean-generation evidence must remove or isolate only these ignored long-MPC outputs, regenerate from HANK source, and build them. Rollback must restore the six-parameter source and regenerate/rebuild six-parameter artifacts before running the old code.

**Numerical meaning and product boundary**

At `v_ego = v_lead = 0`, the stopped-equivalence term and velocity terms are zero, so the MPC desired obstacle distance equals raw `stop_distance`. At equal low nonzero speed `v`, the strict TOP096 pull-away gate is false and equal braking terms cancel, leaving `t_follow * v + stop_distance`. With a stationary lead and moving ego, it is `v_ego**2 / (2 * 2.5) + t_follow * v_ego + stop_distance`. In all cases, increasing `p[6]` by one metre increases the symbolic desired distance by one metre.

This does not prove that the raw value is the physical bumper-to-bumper gap. `lead.dRel` is documented from the ego front bumper, and vision distance is transformed into the radar coordinate, but the inspected source does not establish that every lead target is the physical rear bumper. Radar/model target geometry, filtering, cost/slack tradeoffs, state estimation, actuation, and stop/start behavior can change the observed vehicle gap. No geometry offset is invented here.

The exact B values 4.5/4.0/4.0 form the reproducible donor preset and the only initial F-002 selection set. There is no arbitrary raw stop-distance input. Implementations must reject an unsupported personality and must not place non-finite or non-positive values into `p[6]`. Candidate 1.0/1.5/2.0 values may be deterministic bounded numerical test cases only; they are not frozen as physical 1–2 m gaps or exposed as configuration. A future HANK `緊湊 / 一般 / 舒適` mapping requires a separate versioned schema/product decision, a finite bounded whitelist, C3X evidence, and stationary vehicle measurement before any 1–2 m claim.

**Implementation test contract**

F-002 implementation is test-first and must cover:

1. exact relaxed/standard/aggressive donor presets and unsupported-personality rejection;
2. `p[6]` at every horizon row with no stale value through personality and ACC/blended transitions;
3. unchanged `p[0:6]` meanings, including E-001 DTSC bounds and PORT-01 `p[4]`;
4. zero-speed and low-speed equations with an independent donor-equation oracle;
5. Dynamic Follow OFF/ON changing only `t_follow`, with stop-distance selection orthogonal;
6. unchanged TOP096 pull-away formula and obstacle transform;
7. unchanged Acceleration Personality upper-bound behavior;
8. ACC cruise-obstacle, symbolic cost, and danger constraint use of `p[6]`;
9. blended cost/constraint and both lead-comfort checks using the same `p[6]`;
10. effective-personality transitions, including relaxed/standard/aggressive, APM, gap-source transitions, and no CFG writes;
11. Stock Long retaining no longitudinal actuation authority;
12. Python/model/JSON/generated/native/runtime dimension agreement at 7;
13. native solver status, finite params/v/a/j, and reset evidence;
14. donor-preset restoration and candidate closer values only as finite numerical cases;
15. all existing E-001, E-002, PORT-01, PORT-02, PORT-03, CFG-01, and longitudinal regressions;
16. full `scons -u -j4`, Ruff on changed files, and `git diff --check`;
17. existing longitudinal SQP_RTI status-3 diagnostics compared with baseline 42.

**Excluded**

B Toyota interface, CarState, CarController, toyotacan, Panda safety, custom cereal, AccelController, F-005 jerk/response changes, `COMFORT_BRAKE = 1.75`, B pull-away behavior, ToyotaTune correction, UI, a three-mode product mapping, live arbitrary stop-distance edits, SecOC changes, LongControl replacement, C braking offset, C `+1.5 m` correction, and wholesale donor generated artifacts.

**Validation limit**

This closure freezes source, parameter, generation, and deterministic test boundaries. It does not validate native implementation output, C3X behavior, physical stopped gap, vehicle behavior, deployment safety, or release acceptance.

---

## D-021 — F-005 uses TOP01003 low-speed responsiveness in ACC

**Status:** Accepted — F-005 Phase-1 donor/numerical closure complete (`READY_F005`)

**Date:** 2026-09-22

**Decision**

Use B (`CT921/openpilot`, branch `TOP01003`, commit `615799f95e978fbf643d1e762d605b4d5b06499f`) as the primary F-005 donor. Freeze `get_jerk_factor()` and `LongitudinalMpc.set_weights()` from its `selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py` and processed-lead flow from `selfdrive/controls/lib/longitudinal_planner.py`. C/TOP096 (`3d75e471c74fccf0067dcda8cfe1374cf1268215`) is comparison only. Do not combine B and C or invent an intermediate HANK scale.

**D1 — Exact low-speed scale.** Start `j_ego_v_ego` and `a_change_v_ego` at `1.0`. If both processed stage-0 lead velocities satisfy `v_lead0 >= v_ego` and `v_lead1 >= v_ego`, set each to `np.interp(v_ego, [0, 10], [0.9, 1.0])`, retaining standard endpoint behavior. Otherwise both remain `1.0`. B1 stopped/no-lead native evidence: current `a[1] = 0.028686`, `j[0] = 0.413085`; exact B `a[1] = 0.032822`, `j[0] = 0.472635`. C's `0.05 -> 1.0` low-speed scale is rejected for Phase 1 because its measured response was many times larger.

**D2 — Exact jerk factors.** Relaxed `1.0`, Standard `1.0`, Aggressive `0.45`. Only Aggressive changes from HANK's `0.50`. Reject C's Relaxed `1.0`, Standard `0.5`, Aggressive `0.22`.

**D3 — Processed two-lead AND gate.** `process_lead()` creates a synthetic `v_ego + 10 m/s` lead for each missing real lead. Thus no-lead cruise activates scaling; with one real lead, that lead determines the gate; with two, both must pass. Any processed lead below ego speed immediately restores factors to `1.0`. At ego speed zero a negative raw `vLead` may clip to zero and pass the non-strict gate. B1 observed a Standard stage-0 W[4]/W[5] change from `184/4.6` to `200/5` at 2 m/s when a lead became slower, an approximately 8.7% immediate cost jump. Accept donor discontinuity for Phase 1. Add no hysteresis, debounce, filtering, epsilon, or new lead state before vehicle evidence.

**D4 — ACC only.** Preserve `A_CHANGE_COST = 200`, `J_EGO_COST = 5`, and current W[4] horizon decay. In ACC:

```text
W[4] = jerk_factor * (A_CHANGE_COST if prev_accel_constraint else 0) * a_change_v_ego
W[5] = jerk_factor * J_EGO_COST * j_ego_v_ego
```

`prev_accel_constraint = not (reset_state or carState.standstill)` remains authoritative: when false W[4] stays zero, while W[5] still follows its formula. Blended remains exactly `[0, 0.1, 0.2, 5.0, 40 if prev_accel_constraint else 0, 1.0]`, without B low-speed factors.

**D5 — Planner data flow.** Pass `radarState.leadOne` and `leadTwo` separately through `mpc.process_lead()`, take `[0, 1]` from each processed trajectory, then call `mpc.set_weights(prev_accel_constraint, personality=effective_personality, v_lead0=v_lead0, v_lead1=v_lead1)`. `mpc.update()` will process the leads again for obstacles. Accept this donor-style duplicate processing for Phase 1; do not refactor it away during implementation. The planner's existing `selfdriveState.personality`, overridden by APM when active, is the same effective personality passed to `set_weights()` and `update()`. Add no independent Params read, second personality state, polling, or APM redesign.

**Preserved boundaries and exclusions**

- Keep E-001 solver bounds at `p[0:2]`, E-002 ACC/blended synchronization, PORT-01 Dynamic Follow at `p[4]`, PORT-02 stopped-equivalence/pull-away, PORT-03 maximum Acceleration Personality cap, CFG-01 session configuration/profile selection, F-002 Stop Distance at `p[6]`, and Toyota Stock Long authority.
- Exclude B MIN_ACCEL_PROFILES. B primarily uses them for the ACC cruise synthetic-obstacle lower envelope, not solver `p[0]` or lead braking authority. Low-speed donor minima are less negative than stock `-1.2 m/s²`; PORT-03 remains maximum-acceleration-only.
- Preserve current HANK DASR. B1's 30-frame low-speed no-lead planner trace had `0/30` raw-target clips for Current and B; temporary B DASR bypass changed final target by `0.0`. Other bound histories and deceleration scenarios remain untested. Do not import B fixed slew or tune DASR in F-005.
- Preserve `COMFORT_BRAKE = 2.5 m/s²`; reject B's `1.75`. This constant changes ego safe distance, stopped equivalence, lead obstacles, PORT-02 behavior, and follow/braking geometry; it is not a hard actuator brake limit. A future change requires a separate accepted numerical decision.
- Exclude C's `0.05 -> 1.0` scale, Aggressive `0.22`, Standard `0.5`, `braking_offset`, `smoother_braking`, `t_follow /= braking_offset`, blended W[4] scaling, blended danger-cost change, and stop-distance correction. C remains comparison only.
- Do not import donor planner, AccelController, SmartCruise, SpeedLimit stack, ToyotaDriveMode/interface/CarState/CarController, toyotacan, Panda, SecOC, or custom cereal.

**Solver/build contract**

Phase-1 implementation changes runtime cost weights and planner lead-data flow only. No `PARAM_DIM` change, `model.p` change, CasADi symbolic-model change, solver regeneration, or generated-source change is expected. Production seams are only `selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py` and `selfdrive/controls/lib/longitudinal_planner.py`, plus focused tests.

**Implementation test contract**

Deterministically verify exact B factors for Relaxed/Standard/Aggressive; interpolation at 0, midpoint, and 10 m/s; both processed leads `>=` activating and either `<` disabling scaling; no-lead and one-real/one-synthetic behavior; the ego-zero clipped-lead edge; exact ACC W[4]/W[5] and existing W[4] horizon decay; W[4] remaining zero when `prev_accel_constraint` is false; unchanged blended weights; planner processed-lead path; gate transitions without stale weights; and APM effective-personality transitions. Check unchanged PORT-02 obstacles, PORT-03 max cap, F-002 `p[6]`, Dynamic Follow `p[4]`, E-001 `p[0:2]`, E-002 transitions, DASR interaction, and Stock Long authority. Include native finite/status/reset evidence, an acceleration-side case, a slower-lead/deceleration-side case proving low-speed scaling disables, full longitudinal regression, SQP_RTI status-3 comparison with baseline 42, build, Ruff, and diff checks. Deterministic results are not vehicle-safety evidence.

**User-goal and validation boundary**

Prompt launch is partially addressed by PORT-02 and receives a modest measurable F-005 addition (`a[1] = 0.008913 -> 0.010540 m/s²` in B1's lead pull-away case); C3X sufficiency is unknown. More aggressive acceleration remains partially addressed: PORT-03 owns the positive acceleration cap, and F-005 may approach it more readily but does not raise it. Earlier deceleration and stronger required deceleration are **not addressed by accepted B F-005**. Keep `F005_DECEL_STUDY` unresolved after Phase-1 responsiveness implementation to identify their actual owner. Do not silently change `COMFORT_BRAKE`, PORT-01, PORT-02, PORT-03, F-002, or DASR without another accepted decision. Physical 1–2 m mapping, three-mode product mapping, profile UI, HANK/TSS selector, C3X bench, V0–V3, P0/SecOC/Toyota release acceptance, and Phase 1 completion remain unresolved.

This decision freezes implementation scope, not implementation completion, C3X or vehicle behavior, deployment safety, main merge, or release acceptance.

---

## D-022 — Radar ACC Stateless Relative-Speed Early-Decel Pressure

**Status:** ACCEPTED_FOR_IMPLEMENTATION — Goal-C software architecture closure; not vehicle validated or release ready

**Date:** 2026-09-22

**Decision**

Implement earlier radar ACC deceleration as stateless, per-lead pressure on existing ACC obstacle geometry. A lead is eligible only when `lead.status && lead.radar && lead.radarTrackId >= 0`. For each eligible real radar lead independently:

```text
closing_speed = max(v_ego - v_lead, 0)
pressure = min(cap, gain * closing_speed)
effective_lead_obstacle = base_lead_obstacle - pressure
```

Apply the same pressure to every stage of that lead's MPC horizon column, after the existing lead trajectory and PORT-02 stopped-equivalence calculation but **before** per-stage `min(lead0, lead1, cruise)` selection. The expected primary production seam is `selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py`; add another production file only if required for tunable HANK constant/parameter ownership. Do not change `process_lead()` output, a shared lead trajectory, the cruise synthetic obstacle, already-selected `p[2]`, planner source after solve, or the blended path. Missing/synthetic leads, vision-only leads, invalid radar track IDs, and blended/e2e mode receive no pressure. When `v_lead >= v_ego`, pressure is exactly zero and releases immediately. There is no hysteresis, acquisition-age tracking, pressure slew, cut-in guard, or per-track persistent state. Pressure zero must preserve baseline obstacle and selected `p[2]` behavior.

**Ownership and solver boundary**

- PORT-01 Dynamic Follow and `p[4]`, PORT-02 pull-away/stopped-equivalence transform, F-002 Stop Distance and `p[6]`, and F-005 low-speed response `W[4]/W[5]` remain under their current owners. Closing-speed pressure does not replace their formulas. At zero closing speed, steady equal-speed following returns to PORT-01/existing MPC geometry, final stopped geometry to F-002, and pull-away to PORT-02.
- Preserve `COMFORT_BRAKE = 2.5`, E-001 acceleration bounds at `p[0]/p[1]`, `ACCEL_MIN`, DASR, LongControl, Toyota longitudinal rate limiter, Toyota PID/SecOC path, and E-002 ACC/blended mode ownership. Goal D is **NO_STRONG_DECEL_CHANGE_JUSTIFIED**: Studies A–G show current MPC can issue strong negative requests but do not justify increasing negative acceleration authority or modifying these downstream mechanisms. Toyota actuator behavior remains for C3X/closed-loop validation.
- The mechanism changes only the runtime ACC real-radar lead obstacle column during closing. It does not change `PARAM_DIM`, add a `p[]` slot, change the CasADi symbolic formulation, or require solver regeneration. Do not redesign planner, radar, CFG, UI, Toyota control, solver generation, or model paths for this implementation.

**Why no guard; diagnostic envelope**

Study G found repeatable stateless diagnostic cells with earlier Goal-C raw-deceleration crossing in representative stopped and slower-lead scenarios, no added QP iteration-cap hits across its core matrix, no new solution reset or non-finite output, and no high-gain weak-first-frame close-cut-in pattern. Freeze **NO_GUARD_REQUIRED_FOR_STATELESS_ENVELOPE**. This does not assert that every gain/cap combination is suitable. The diagnostic grid sampled gains `0.004`, `0.02`, `0.0407`, `0.06`, `0.08`, `0.09`, `0.10` and caps `0.6`, `0.8`, `1.0`, `2.0 m`. These six **discrete** cells passed its architecture gates:

| Diagnostic gain | Diagnostic cap (m) |
|---:|---:|
| 0.09 | 0.6 |
| 0.09 | 0.8 |
| 0.09 | 1.0 |
| 0.09 | 2.0 |
| 0.10 | 0.6 |
| 0.10 | 0.8 |

Do **not** treat `0.09–0.10` gain or `0.6–2.0 m` cap as a proven continuous valid interval or as production values. In the selected matrix, gain `<= 0.08` did not satisfy the Goal-C effectiveness gate; gain `0.10`/cap `1.0 m` added a QP cap hit in the 30→20 m/s lead case; gain `0.10`/cap `2.0 m` reproduced the close-cut-in weak-first-frame/stronger-next-frame response. These are scenario-bound diagnostic observations, not universal safety limits. Study E's static warm-start branch at pressure `0.813→0.814 m` did not reproduce in Study F's physically consistent 20 Hz replay; status zero alone is not proof of QP convergence. Retain numerical diagnostics during implementation.

**Gain/cap ownership and Goal-C limit**

The formula and insertion seam are frozen; **gain and cap are both required BENCH / VEHICLE TUNING parameters, with no final numeric values frozen by D-022**. Make them easy to alter for controlled C3X testing without changing the formula. Do not add UI or extend CFG-01 here. Any initial implementation value must be explicitly labelled `C3X BENCH SEED — NOT PRODUCT DEFAULT` and selected during implementation/bench planning, never silently by this decision. Goal C is **IMPLEMENTATION JUSTIFIED**: Study G repeated software-level earlier raw-deceleration crossings, about one 0.05 s planner frame and approximately 1 m in selected stopped-lead cases. These are diagnostic observations, not product requirements or subjective driving claims.

**Final-gap and validation limit**

In Study G's continuous 10 and 20 m/s simplified approaches, ego reached stable near-zero velocity and pressure fell to approximately `3e-5 m`; `p[4]` and `p[6]` remained unchanged and the effective lead obstacle approached its unpressured value. The replay stopped approximately `0.16–0.18 m` from the baseline final position because the earlier trajectory differed; D-022 does **not** claim identical physical stop locations. Actual stopped gap, perceptual early-decel benefit, radar timing, Toyota actuator behavior, cut-in behavior, C3X load/timing, V0–V3, deployment and road approval remain unvalidated. This is software architecture closure only, not implementation completion, vehicle-safety approval, Phase 1 completion, or release acceptance.

Implementation is test-first against the D-022 gates in `HANK_TEST_MATRIX.md`, followed by focused/native and existing longitudinal regressions, SCons, Ruff, and diff review. Keep the source change small and preserve baseline behavior at pressure zero.

---

## D-023 — Phase-1 HANK three-mode profile and CFG v2

**Status:** ACCEPTED_FOR_IMPLEMENTATION (design only; not vehicle validated)
**Date:** 2026-09-22

**Decision**

The only primary HANK modes are `緊湊 / 一般 / 舒適`:

| UI mode | `hank_profile` | Base `LongitudinalPersonality` | PORT-03 `accel_profile` |
|---|---|---|---|
| 緊湊 | `compact` | Aggressive | sport (0) |
| 一般 | `normal` | Standard | normal (1) |
| 舒適 | `comfortable` | Relaxed | eco (2) |

Dynamic Follow is an independent boolean option: selecting a mode preserves its Requested value and never turns it on/off. Stop Distance, F-005 jerk/weights, and the existing Dynamic Follow curves use the **effective** personality: selected base, then APM's existing temporary override when active. APM changes neither Requested/Active nor PORT-03 acceleration profile. The D-022 gain 0.09 and cap 0.6 m remain a separate **C3X BENCH SEED — NOT PRODUCT DEFAULT** and are never scaled by mode. No new MPC formula, donor curve, Stop Distance constant, or F-005 factor is authorized.

The advanced **Restore original/default** action is separate from the three main buttons. It saves base personality Standard, acceleration profile stock (3, the existing HANK lookup), and Dynamic Follow false. Internal `original` is not a fourth main HANK mode or a universal B donor preset. APM can still temporarily produce effective Aggressive at low speed. Real-time `+/-` is `POST_RC_TUNING`, not a Phase-1 control.

**Exact CFG contract**

D-019's strict v1 shape remains supported: exactly `version=1`, `dynamic_follow: bool`, `accel_profile: int 0..3`. Valid v1 Active/latch is reused unchanged in the current session. A valid v1 Requested is never silently mapped to a mode, because v1 never recorded its personality. Existing v1 behavior remains until an explicit v2 choice/reset; no same-session resnapshot or automatic cycle occurs.

The new UI writes complete v2 Requested JSON, and `plannerd` snapshots the identical shape into Active:

```json
{"version":2,"dynamic_follow":false,"hank_profile":"original","accel_profile":3}
```

The exact keys are `version`, `dynamic_follow`, `hank_profile`, `accel_profile`. Version is integer 2; Dynamic Follow is a JSON boolean; profile is one of `compact`, `normal`, `comfortable`, `original`. Acceleration profile must be the corresponding integer 0, 1, 2, 3 respectively. Base personality is derived respectively as Aggressive, Standard, Relaxed, Standard, not duplicated in JSON. Reject unknown/missing/duplicate keys, wrong types, unsupported versions and mismatched profile pairs. Reject invalid UI candidates before writing. For a corrupt persisted Requested on a new session, preserve raw data and record the existing explicit recovery reason, using the v2 `original` bundle. Active/latch corruption or I/O failure remains fail-closed under D-019.

The UI/CFG adapter owns validated atomic whole-JSON Requested saves. Engaged/onroad requests are allowed but never change Active/current control behavior. Only `plannerd` snapshots after a legitimate Offroad→Onroad transition before planner construction. Planner restart or disengage/re-engage in the same onroad session reuses Active. An ordinary profile edit never writes `OnroadCycleRequested`. UI displays separate Active and Requested, plus `pending next session` if different; v1 is shown as legacy/unmapped. The gap button cycles **Requested** `compact → normal → comfortable → compact` and preserves Requested Dynamic Follow. If no v2 Requested exists, its first press explicitly selects `compact`. It never changes Active in the current session.

For v2 Active with HANK longitudinal ownership, `selfdrived` publishes the base personality derived from Active, not from a live `LongitudinalPersonality` Param. `plannerd` and selfdrived must consume the same Active snapshot; missing/invalid Active/latch blocks engagement rather than falling back to a stale Param. The gap button and existing settings personality control must route to Requested HANK profile selection; neither may directly mutate live personality independently. Under v1 Active, gap press still creates a v2 Requested profile instead of changing current personality. Under TSS ownership, gap press does not change HANK profile; UI may edit a stored future HANK Requested profile but must label it inactive. Existing CP guards bypass HANK/TOP longitudinal control under Stock Long.

**UI-01 actions**

| Surface/state | Display and action | Disabled/pending/error |
|---|---|---|
| Onroad HANK mode control | Show Active mode, separate Requested mode, and APM effective override indicator when different. Tap one of the three modes to validate/save Requested. | A saved mismatch says `Pending: next onroad session` even while engaged. Invalid/readback-failed saves show an error and do not change Active. No confirmation or cycle is required for this deferred-only action. |
| TSS owner | Show `TSS owns longitudinal`; any HANK profile is labelled stored for future HANK. | Onroad HANK mode quick control is inactive; settings may still save future HANK Requested. |
| Settings/advanced | Three primary modes, independent Dynamic Follow option, and separate `Restore original/default` action. | Restore explicitly shows that it will set Standard/stock/false next session; failed validation/write/readback shows error. No fourth main mode or live numerical editor. |

**Scope and provenance**

Expected implementation seams: `common/params_keys.h`, `selfdrive/controls/lib/hank_config.py`, `selfdrive/controls/plannerd.py`, existing planner input, `selfdrive/selfdrived/selfdrived.py`, A/DP UI and focused tests. D-023 extends D-019, superseding only its deferred three-mode mapping and old gap-button independence; v1 history remains intact. The user explicitly accepted mapping, independent Dynamic Follow, advanced original reset, gap-button Requested cycling, and deferred apply after the read-only Phase-1 UI source inventory. This is architecture authority, not implementation or vehicle validation.

---

## D-024 — Verified HANK/TSS owner switch with fail-closed rollback

**Status:** ACCEPTED_FOR_IMPLEMENTATION (design only; C3X/vehicle validation required)
**Date:** 2026-09-22

**Decision**

`dp_toyota_stock_lon=true` requests TSS factory longitudinal ownership; `false` requests HANK/openpilot longitudinal ownership. This is a hard owner change, never a personality selector. Show it only for the supported target Toyota configuration. The current DP settings toggle that writes the Param directly must use this coordinator, be disabled, or be removed as a selectable UI path; no bypass may remain.

Before either request, require fresh/valid `selfdriveState.enabled == false`, `carControl.enabled == false`, `carControl.latActive == false`, `carControl.longActive == false` and `carState.cruiseState.enabled == false`. Recheck immediately before writing the owner Param. Missing/stale/contradictory data blocks the request. A/DP ALKA may set `latActive` while selfdrive is disengaged, so `enabled=false` alone is insufficient. A request equal to the confirmed current owner is a no-op, not another cycle.

**Coordinator, Params and gate**

One coordinator owns a new atomic `HankOwnerSwitchState`, `PERSISTENT | JSON`, with no registry default. Its exact five v1 keys are `version` (integer 1), `confirmed_owner` (`HANK`, `TSS`, or null only before first verification), `target_owner` (`HANK`, `TSS`, or null), `state` (`UNVERIFIED`, `CONFIRMED`, `REQUESTED`, `CYCLING`, `REINITIALIZING`, `VERIFYING`, `SWITCH_FAILED`), and `failure_boot_id` (string or null). No other writer may alter it. The confirmed owner remains the previous owner until the new one passes full verification. Missing/corrupt state is unverified, not permission to engage. A second BOOL key `HankOwnerSessionVerified` has no default and clears on manager start, Offroad, Onroad and ignition-on. Its only true writer is the coordinator after current-session verification.

`selfdrived` independently fails closed if the session gate is missing/false, transaction is not `CONFIRMED`, the owner Param differs from confirmed owner, or its current CarParams contradict owner. It must prevent new engagement and disable if the gate becomes false; UI-only disabling is insufficient. An explicit alert/disabled selector explains the reason. At clean startup with no transaction, verify the existing owner Param, freshly initialized CarParams and Panda state before recording the initial confirmed owner and opening the gate. Direct out-of-band Param changes invalidate verification; they do not perform a hot switch.

**Accepted schema amendment (2026-09-23):** The user approved `failure_boot_id` inside the same atomic transaction JSON; no separate boot-identity Param is permitted. Entering `SWITCH_FAILED` closes the gate, attempts/read-backs previous-owner rollback, then reads the current Linux `/proc/sys/kernel/random/boot_id` and persists/read-backs that valid non-empty UUID. In every other state the field is null. Missing/null/malformed failed-state boot evidence, boot-ID read errors, or persistence/readback failure remain fail-closed. Same-boot coordinator or manager restart cannot recover, even with fresh CarParams/Panda. Recovery requires a different current kernel boot ID plus every restored-owner current-session verification predicate; only then persist/read back `CONFIRMED` with target and failure_boot_id null, followed by setting/read-backing the gate true. BootCount, process restart and an onroad epoch alone do not prove a full reboot. All other D-024 semantics remain unchanged.

**State machine and ordering**

`CURRENT_HANK`/`CURRENT_TSS` are UI names for `CONFIRMED` plus a true current-session gate. An engaged request is `BLOCKED_ENGAGED` with no write. For a valid opposite-owner request, record `previous_confirmed_owner`, close/read back the engagement gate, observe no active commands again, and persist `REQUESTED` with target. Write/read back `dp_toyota_stock_lon` for the target; persist `CYCLING`; issue `OnroadCycleRequested` once. Observe actual Offroad followed by a new Onroad epoch using `deviceState.startedMonoTime`, then enter `REINITIALIZING` and `VERIFYING`. Consumption of the request bit is not success. No ACC toggle, `OpenpilotEnabledToggle` shortcut, repeated automatic cycle, or parallel Toyota/Panda initialization is allowed.

Verify current-session `CarParams` after the Onroad clear/new card instance, matching `carParams` when published. `CarParamsPersistent` alone is stale-capable and cannot prove success. Require owner Param, fresh CarParams `openpilotLongitudinalControl` (`false` TSS, `true` HANK), and every connected Panda's safety model, safetyParam and alternative experience to match fresh CarParams. Toyota `STOCK_LONGITUDINAL` must be present for TSS and absent for HANK. Require fresh valid selfdrive/CarControl state with no active commands before reopening engagement. Only then atomically persist `CONFIRMED` with new owner/target null and set the session gate true. Unavailable HANK support, stale/missing data, mismatch or finite timeout means failure. Implementation may select polling periods/timeouts but may not weaken these evidence predicates.

During `REQUESTED`, `CYCLING`, `REINITIALIZING` and `VERIFYING`, UI displays pending and disables repeated taps; engagement stays blocked. A restarted coordinator may resume only with provable Offroad/new-Onroad evidence; otherwise it fails closed. On any request/cycle/verification failure, keep the gate false, write/read back the owner Param to `previous_confirmed_owner`, persist `SWITCH_FAILED`, and show explicit failure plus full C3X reboot fallback. If rollback write/readback also fails, remain `SWITCH_FAILED` and blocked. Restoring the Param is **not** proof that the failed runtime reverted. No automatic retry or silent engagement. Failure persists over reboot; only a newly booted session that verifies fresh CarParams and Panda state for the restored previous owner may clear failure, record `CONFIRMED` and open the gate. Otherwise it remains blocked. First physical validation is stationary in a safe environment.

Under TSS, UI shows TSS as active owner and labels any saved HANK profile `stored for future HANK`, never as controlling TSS. Under HANK, UI shows Active versus Requested profile and pending status. Reuse the A camera/HUD, settings, Params, hardwared/manager, card and Panda-state observation seams. Selector implementation may add the coordinator/interlock in UI/config/selfdrived, but may not modify Toyota interface/CarState/CarController, Panda safety, SecOC/TSK, LongControl, longitudinal MPC/solver, authenticated CAN packing/signing or cereal replacement.

**Allowed state transitions**

| State | Required invariant / next event |
|---|---|
| `UNVERIFIED` | Session gate false; no target. Fresh initial owner/CarParams/Panda verification may establish `CONFIRMED`. |
| `CONFIRMED` | Target null; confirmed owner matches Param, fresh CP/Panda and session gate. Valid opposite-owner request closes gate and enters `REQUESTED`. |
| `REQUESTED` | Previous confirmed owner remains recorded; target is the opposite owner; gate false. Target Param readback permits `CYCLING`. |
| `CYCLING` | Exactly one cycle request issued, gate false. Observed Offroad then new Onroad epoch permits `REINITIALIZING`. |
| `REINITIALIZING` | Wait for new card/CarParams/Panda; no engagement. Complete current-session data permits `VERIFYING`. |
| `VERIFYING` | All owner, flag, Panda and no-command predicates pass to `CONFIRMED` for target; otherwise fail. |
| `SWITCH_FAILED` | Target/previous confirmed owner retained for diagnosis; gate false. Param rollback alone never changes this state. Only full reboot plus fresh restored-owner verification can return to `CONFIRMED`. |

Every transaction state except `UNVERIFIED` and `CONFIRMED` requires a non-null previous confirmed owner and target; a malformed combination is fail-closed. A precondition rejection (`BLOCKED_ENGAGED`) is transient UI state and never mutates this JSON. Any interruption without evidence to resume safely, timeout, readback mismatch or verification failure enters `SWITCH_FAILED`. The coordinator must not open the gate until `CONFIRMED` is durably read back.

**UI-02 actions**

| Visible state | Action and presentation |
|---|---|
| `CURRENT_HANK` / `CURRENT_TSS` | Show verified current owner. Opposite-owner tap opens an explicit takeover/disengage confirmation; confirmation rechecks all preconditions before any write. |
| `BLOCKED_ENGAGED` / unavailable | Disable the switch and state whether selfdrive, ALKA lateral, factory ACC, stale data or unsupported vehicle blocks it. No Param/cycle write. |
| `REQUESTED` / `CYCLING` / `REINITIALIZING` / `VERIFYING` | Show target and pending lifecycle; disable further taps and engagement. Never label target as current owner before verification. |
| `SWITCH_FAILED` | Show previous confirmed owner, failed target, uncertain runtime and explicit reboot fallback. No retry/hot-toggle control; reboot requires its normal confirmation UI. |

**Evidence and relationship**

Read-only inventory confirmed ALKA lateral activity despite `selfdriveState.enabled=false` in `selfdrive/controls/controlsd.py`; cycle consumption in `system/hardware/hardwared.py`; lifecycle key clearing/process restart in `system/manager/manager.py`; Stock Long input before `get_car` in `selfdrive/car/card.py`; Toyota `openpilotLongitudinalControl`/`STOCK_LONGITUDINAL` in `opendbc/car/toyota/interface.py`; and Panda safety reset/reload in `selfdrive/pandad/panda_safety.cc`. No existing complete selector coordinator or hard engagement interlock was found. The user expressly accepted last-confirmed-owner rollback and failed-runtime blocking. D-024 refines D-011 through D-014 without superseding their no-hot-switch/trust-boundary rules. U/S/R/B/V0 tests remain mandatory; this design does not claim a working selector, C3X timing, vehicle safety or Phase-1 completion.

---

## D-025 — Following-distance regression contract after F-002

**Status:** ACCEPTED_FOR_IMPLEMENTATION

**Date:** 2026-09-23

**Decision**

The Phase-1 B2 blocker in `selfdrive/controls/tests/test_following_distance.py` is classified as `STALE_TEST_CONTRACT_AFTER_F002`, not as a production regression. F-002 correctly supplies personality stop distance through solver parameter `p[6]`, but the historical zero-speed maneuver assertion continued to treat the nominal analytic distance as the exact native simulation equilibrium. With Standard/Aggressive `p[6] = 4.0` and ACC `p[5] = 0.75`, the native soft cost/constraint settles near 3.0 simulation-coordinate metres; this does not make 3.0 m, or `p[5] * p[6]`, a product target or physical bumper gap.

**Ownership split**

1. Analytic helper tests own the exact `desired_follow_distance()` equation. They must explicitly pass both `get_T_FOLLOW(personality)` and `get_STOP_DISTANCE(personality)` for Relaxed, Standard and Aggressive; no Relaxed test may inherit the default Standard stop distance.
2. `selfdrive/controls/tests/test_stop_distance.py` and the existing F-002 suite retain exclusive ownership of exact `p[6]` values (Relaxed 4.5, Standard 4.0, Aggressive 4.0), parameter dimension/order, effective-personality propagation, ACC/blended consistency, finite native output and solver status. `test_following_distance.py` must not duplicate `p[6]` as an exact final-gap assertion.
3. Moving-speed maneuver cases at 10 and 35 m/s retain their existing approximate-following-distance contract and existing tolerances, but the oracle becomes explicitly personality-complete:

```python
desired_follow_distance(
  v_lead,
  v_lead,
  get_T_FOLLOW(personality),
  get_STOP_DISTANCE(personality),
)
```

4. Zero-speed maneuver cases own stable, valid native convergence and personality direction, not equality to the nominal analytic distance. For both e2e and non-e2e, require a valid maneuver, finite observed gap/speed/acceleration and relevant solver arrays, `solution_status == 0`, final non-negative ego speed below `0.01 m/s`, absolute final ego acceleration below `1e-3 m/s²`, and `lead0` as the relevant source for the fixed leadOne fixture. Within each mode, Relaxed must finish with a strictly larger simulation-coordinate separation than Standard and Aggressive because Relaxed owns the larger `p[6]`; no Standard-versus-Aggressive ordering is required because both own `p[6] = 4.0` and other personality terms differ.

The speed threshold reuses the maneuver Plant's existing `speed < 0.01` standstill definition. The acceleration threshold reuses the existing maneuver `1e-3 m/s²` small-acceleration scale. A three-repeat read-only probe produced identical results for all six cases: all 18 runs were valid, used `lead0`, and ended with solver status 0; e2e speed/acceleration were exactly zero, while non-e2e maximum final speed was `0.002925707 m/s` and maximum absolute final acceleration was `3.741398e-05 m/s²`. Exact repeat equality and the observed final gaps are evidence, not frozen output values or required margins.

**e2e/non-e2e treatment**

Use the same zero-speed convergence and directional contracts for e2e and non-e2e. Their different internal modes and `p[5]` values may produce different gaps, so do not require cross-mode gap equality. The passing historical e2e nominal-distance assertion is still conceptually replaced; passing did not make nominal distance an exact equilibrium contract.

**Rejected fixes and boundaries**

- Do not widen the historical distance tolerance to make zero-speed cases pass.
- Do not require `final_gap == p[6]` or `final_gap == p[5] * p[6]`.
- Do not freeze approximately 3.0 m as a product target, safety floor, physical stopped gap or new tuning value.
- Do not change production longitudinal code, `COMFORT_BRAKE`, `LEAD_DANGER_FACTOR`, Stop Distance, PORT-01/02/03, F-002, F-005, D-022, solver code, generated solver, UI-01 or UI-02 under this decision.

The intended physical stopped-gap goal remains a C3X/vehicle-level validation concern. Software-coordinate gaps are not physical bumper-gap claims. Implementation is limited to the regression-test contract, followed by the blocked B2 verification gates; it does not establish C3X validation, vehicle safety, Phase-1 completion, deployment approval or release acceptance.

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


## D-026 — Planner-effective personality display telemetry (proposal)

**Status:** PROPOSED — PENDING USER SCHEMA APPROVAL; not implementation authority.
**Date:** 2026-11-10

FIX-UI-02 review at `06dc39a512eb08581d0a8b60548b6538bb6de819` found no valid existing published effective personality. Real planner/native MPC plus actual HUD-expression probe reproduced 6 missing overrides in 18 frames, without CFG changes. D-023 remains authoritative for base/Requested/Active and APM ownership.

Propose additive `LongitudinalPlan.hankPersonality @40 :HankPersonalityState` containing version UInt8, base/effective LongitudinalPersonality, apmEnabled Bool, applies Bool and selfdriveStateMonoTime UInt64 (nested ordinals 0..5). Existing Event timestamp and modelMonoTime provide remaining freshness evidence. Absent/version-zero metadata means unavailable. Sole producer is planner; sole purpose is display; no control algorithms change. UI requires fresh/current-session valid metadata and HANK authority, with 0.5-second age bounds; never recomputes APM hysteresis. Stock Long is inactive, v1 is Legacy, restart reuses Active and waits for valid fresh observations.

The [complete schema, compatibility review, alternatives and test contract](docs/hank/evidence/2026-11-10/fix-ui-02-review/README.md) is pending approval. No schema slot is reserved by this proposal, no production implementation has occurred, and no release/C3X authorization is implied.
