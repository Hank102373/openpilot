> Current execution order: HANK_EXECUTION_PLAN.md. Current continuation: docs/hank/CURRENT_STATE.md. Dated historical PASS/NEXT entries below do not override the latest audit findings in section 19.

# HANK Test Matrix

**Document:** HANK_TEST_MATRIX.md  
**Version:** v1.0  
**Date:** 2026-09-14  
**Target vehicle:** 2022 Toyota Sienna Hybrid  
**Target hardware:** comma 3X (C3X)

---

## 1. Purpose

This matrix defines the minimum verification required before a HANK change may be treated as safe enough for the next validation stage.

A successful compile is **not** a complete test. Real-vehicle ADAS changes require traceability across algorithm, control state, CAN, SecOC and Panda safety behavior.

---

## 2. Legend

### Risk

- **Low** — display/configuration only; no vehicle actuation effect.
- **Medium** — affects behavior selection or non-critical control configuration.
- **High** — directly changes longitudinal/lateral planning or control behavior.
- **Critical** — vehicle actuator path, CAN, safety model or mode ownership.
- **P0** — Toyota SecOC/TSK, Panda safety, authenticated control and fail-safe boundary.

### Test stages

| Code | Stage | Meaning |
|---|---|---|
| U | Unit / deterministic function test | Function/parameter/validation behavior |
| S | Static / build | Import, schema, lint/type where available, solver/build consistency |
| R | Replay / deterministic comparison | Logged or synthetic scenario comparison without live vehicle actuation |
| B | Bench / C3X | Device build/runtime/process/Panda behavior without public-road validation |
| V0 | Vehicle stationary | Parked/private-safe validation on target Sienna |
| V1 | Controlled low speed | Closed/private/low-risk road validation |
| V2 | Normal road | Limited normal-road validation after lower gates pass |
| V3 | Extended regression | Repeated mixed-route validation after all earlier gates pass |

In the tables below:

- **REQ** = required before the stated feature is accepted.
- **OPT** = useful but not mandatory at that gate.
- **—** = not normally applicable.
- Passing status is tracked separately; this file defines requirements, not current results.

---

## 3. Release gate order

No test stage may be skipped simply because a later-stage road test appears successful.

```text
U/S
 -> R
 -> B
 -> V0
 -> V1
 -> V2
 -> V3
```

For Critical/P0 changes, V0 is mandatory before any road test.

---

## 4. Core integration matrix

| ID | Feature / subsystem | Source / owner | Risk | U | S | R | B | V0 | V1 | V2 | V3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T-001 | A baseline unchanged behavior | A | Critical | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-002 | Dynamic Follow | B -> HANK adapter | High | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-003 | Stop Distance | B -> HANK adapter | High | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-004 | Lead Pull-away | C/TOP096 accepted under D-008 -> HANK adapter | High | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-005 | Acceleration Personality | B -> HANK adapter | High | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-006 | Low-speed jerk/response tuning | B/HANK | High | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-007 | HANK profile parameter validation | HANK | Medium | REQ | REQ | REQ | REQ | REQ | OPT | OPT | REQ |
| T-008 | ACM preserved | A | High | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-009 | AEM preserved | A | High | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-010 | DTSC preserved | A | High | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-011 | APM preserved with TOP personalities | A + donor behavior | High | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-012 | DASR preserved | A | High | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-013 | ALKA/lateral regression | A | Critical | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-014 | Lane change / RED / offset regression | A | High | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-015 | Toyota auto lock/unlock regression | A | Medium | REQ | REQ | OPT | REQ | REQ | OPT | REQ | REQ |
| T-016 | Toyota TSS1 SnG feature preservation | A | High | REQ | REQ | REQ | REQ | REQ | OPT | OPT | REQ |
| T-017 | Toyota Stock Long mode | A | Critical | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-018 | HANK <-> TSS quick selector UI | HANK | Medium | REQ | REQ | REQ | REQ | REQ | OPT | OPT | REQ |
| T-019 | `OnroadCycleRequested` mode reload | A mechanism + HANK trigger | Critical | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-020 | Full reboot fallback | A/HANK | Critical | REQ | REQ | OPT | REQ | REQ | OPT | OPT | REQ |
| T-021 | SecOC/TSK key loading | A | P0 | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-022 | SecOC freshness/reset counters | A | P0 | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-023 | Authenticated steering LKA/LTA | A | P0 | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-024 | Authenticated longitudinal `ACC_CONTROL_2` | A | P0 | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-025 | Toyota Panda safety flags/whitelist | A | P0 | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-026 | ACADOS parameter dimension/artifacts | HANK MPC | Critical | REQ | REQ | REQ | REQ | — | — | — | REQ |
| T-027 | Solver convergence/failure recovery | HANK MPC | Critical | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
| T-028 | External radar regression | A | High | REQ | REQ | REQ | REQ | REQ | OPT | REQ | REQ |
| T-029 | MAA integration regression | A | High | REQ | REQ | REQ | REQ | REQ | OPT | REQ | REQ |
| T-030 | UI/device/settings regression | A | Low/Medium | REQ | REQ | OPT | REQ | REQ | OPT | OPT | REQ |

---

## 5. Longitudinal scenario matrix

Every HANK longitudinal build intended for road validation must cover these scenarios.

| Scenario | Dynamic Follow | Stop | Pull-away | Accel profile | FCW/safety | Required observations |
|---|---:|---:|---:|---:|---:|---|
| No-lead cruise | ✓ | — | — | ✓ | ✓ | Stable target speed; no phantom lead behavior |
| Stable lead at constant speed | ✓ | — | — | ✓ | ✓ | Gap converges without oscillation |
| Lead gradually slows | ✓ | ✓ | — | ✓ | ✓ | Timely decel; no late braking |
| Lead hard braking | ✓ | ✓ | — | ✓ | ✓ | Strong enough decel; no solver instability; FCW behavior sane |
| Close cut-in | ✓ | ✓ | — | ✓ | ✓ | Immediate safe reaction without pathological jerk |
| Far cut-in | ✓ | — | — | ✓ | ✓ | No unnecessary abrupt brake |
| Lead lost | ✓ | — | — | ✓ | ✓ | Smooth transition to cruise/model target |
| Lead reacquired | ✓ | — | — | ✓ | ✓ | No acceleration spike or gap discontinuity |
| Lead-one/lead-two switch | ✓ | ✓ | — | ✓ | ✓ | No trajectory discontinuity beyond accepted bounds |
| Approach stopped vehicle | ✓ | ✓ | — | ✓ | ✓ | Stable final stop; no creep-through |
| Stopped behind vehicle | — | ✓ | ✓ | — | ✓ | Hold behavior stable; target distance bounded |
| Lead begins moving | ✓ | — | ✓ | ✓ | ✓ | Prompt launch without unsafe surge |
| Lead pulls away rapidly | ✓ | — | ✓ | ✓ | ✓ | Desired quick response while respecting accel/safety limits |
| Stop-and-go repeated cycle | ✓ | ✓ | ✓ | ✓ | ✓ | No integral/counter/state accumulation fault |
| Uphill approach/launch | ✓ | ✓ | ✓ | ✓ | ✓ | No unexpected pitch compensation regression |
| Downhill approach/stop | ✓ | ✓ | — | ✓ | ✓ | Safe gap/decel; compare donor-specific follow additions |
| Low-speed congestion | ✓ | ✓ | ✓ | ✓ | ✓ | Target HANK use case; no oscillatory throttle/brake |
| Highway steady following | ✓ | — | — | ✓ | ✓ | Higher-speed gap increases as designed |
| Profile switch while disengaged | ✓ | ✓ | ✓ | ✓ | ✓ | New profile applies cleanly at defined boundary |
| Profile switch request while engaged | ✓ | ✓ | ✓ | ✓ | ✓ | Must defer/reject according to policy; no live unsafe jump |

---

## 6. DP-feature interaction tests

### ACM

Verify with HANK donor behavior both OFF and ON:

- trajectory modification occurs only when ACM enabled
- no illegal acceleration output
- coasting behavior does not suppress required lead braking
- disable returns to donor/A baseline behavior

### AEM

Verify:

- ACC/blended mode switching remains functional
- HANK follow/stop behavior is not applied through an invalid mode assumption
- repeated mode transitions do not leave stale MPC state

### DTSC

Verify:

- curvature limits still constrain MPC acceleration bounds
- new MPC parameter layout preserves `a_min/a_max` semantics
- curve-speed constraints cannot overwrite unrelated HANK stop/follow parameter slots

### APM

Verify:

- below configured low-speed threshold, expected aggressive personality mapping occurs
- above restore threshold, user's selected personality returns
- HANK `緊湊/一般/舒適` mapping has deterministic interaction with APM
- no personality thrashing around thresholds

### DASR

Verify:

- slew limiting remains applied at intended output stage
- low-speed responsiveness is not accidentally neutralized
- highway smoothing remains effective
- emergency/required deceleration is not improperly blocked by a smoothing rule

---

## 7. Toyota Stock Long / fast-cycle tests

### T-017 — Stock Long ownership

Required checks:

1. `dp_toyota_stock_lon=ON` results in `openpilotLongitudinalControl=False` after reinitialization.
2. Panda safety contains the expected Stock Long configuration.
3. HANK/DP does not send active longitudinal acceleration commands as controller owner.
4. Toyota factory TSS ACC controls longitudinal behavior normally.
5. HANK/DP lateral remains available according to A behavior.
6. SecOC steering authentication remains valid.

### T-019 — HANK -> TSS cycle

Precondition:

- driver has control
- openpilot disengaged
- no active longitudinal/lateral command ownership

Sequence:

```text
write dp_toyota_stock_lon = true
-> request OnroadCycleRequested
-> observe Offroad transition
-> observe Panda safety reset/no-output state
-> observe new Onroad initialization
-> verify fresh CarParams
-> verify Stock Long mode
-> only then permit re-engagement
```

### T-019B — TSS -> HANK cycle

Same flow with `dp_toyota_stock_lon=false`, followed by verification that:

- openpilot longitudinal is restored
- SecOC ACC path is initialized
- no stale Stock Long safety flag remains
- HANK MPC/controller output resumes only after successful initialization

### Failure-path requirements

If cycle recovery fails:

- do not silently engage
- remain fail-safe/no-output or stock-safe as applicable
- show explicit failure state
- offer full C3X reboot fallback
- never auto-toggle repeatedly in a loop

---

## 8. SecOC / TSK P0 tests

These tests are mandatory because the target Sienna depends on authenticated Toyota communication.

### Key handling

- 32 hex characters accepted -> 16-byte key
- invalid length rejected
- invalid hex rejected safely
- key never logged
- key never committed
- key survives expected Param lifecycle according to A behavior

### Synchronization

- reset counter transition resets local LKA/LTA/ACC counters as A expects
- sync MAC validation behavior unchanged from A
- trip/reset freshness values are consumed correctly

### Message authentication

Compare A baseline vs HANK feature-off for:

- authenticated steering message IDs
- authenticated ACC message IDs
- transmission frequency
- counter progression
- reset behavior
- payload format
- safety configuration

Expected HANK feature-on difference should be the **desired acceleration trajectory**, not authentication mechanics.

### Distinguish failures

Diagnostic logging/test tooling must distinguish at least:

1. SecOC authentication/key/synchronization failure
2. Panda safety rejection
3. CAN communication failure
4. control/planner no-output state
5. Toyota ECU fault/latch state

---

## 9. MPC / solver tests

Required deterministic cases:

- parameter dimension matches generated solver
- all parameter rows initialized
- no NaN/Inf in state/params/solution
- solver reset succeeds
- bad/non-converged solution follows A-compatible safe handling
- extreme valid profile values remain within validated bounds
- donor-original preset reproduces donor equations within accepted tolerance
- feature-off path reproduces A baseline within accepted tolerance where intended

No road validation if solver/generated-code mismatch exists.

---

## 10. Parameter and UI validation

Every user-editable HANK parameter must define:

- name/key
- data type
- engineering unit
- minimum
- maximum
- step
- default
- donor-original value
- validation behavior
- apply timing
- rollback/reset behavior

Tests must cover:

- minimum valid value
- maximum valid value
- out-of-range rejection/clamp policy
- malformed stored value
- missing value/default recovery
- profile save/load
- switching profiles while disengaged
- switch request while engaged

---

## 11. Baseline regression principle

Before enabling a new donor feature, run the same scenario with the feature disabled.

For protected A systems, HANK feature-off must not introduce unexplained changes in:

- CAN IDs/frequency
- SecOC counters/MAC path
- Panda safety flags
- Toyota controller state
- steering behavior
- DP module behavior
- engagement/disengagement behavior

Any unexplained difference blocks acceptance until classified.

---

## 12. Road-validation progression

### V0 — Stationary

Validate:

- startup
- no unexpected dashboard faults
- TSK/SecOC sync
- steering control availability without motion where testable
- Stock Long/HANK cycle transitions
- Panda safety transitions
- UI state and failure recovery

### V1 — Controlled low speed

Validate:

- engage/disengage
- initial acceleration/deceleration
- stopped lead / pull-away
- basic profile differences
- no Toyota fault persistence

### V2 — Normal road

Validate:

- cut-in
- multi-lead transitions
- stop-and-go
- curvature interaction
- APM/ACM/AEM/DTSC/DASR combinations
- Stock Long fallback

### V3 — Extended regression

Validate repeated mixed conditions over enough drives to expose state-retention and intermittent problems:

- repeated start/stop cycles
- repeated HANK/TSS cycles
- cold/warm C3X starts
- different traffic density
- city/highway
- slopes
- long sessions

---

## 13. Required evidence per implementation PR/commit series

For every control-affecting integration item, retain:

- source branch/commit
- donor file/function/constants
- HANK changed files
- reason for adaptation
- test IDs executed
- pass/fail result
- known limitations
- rollback commit/ref

For Critical/P0 work, a statement such as "tested on car and feels fine" is insufficient by itself.

---

## 14. Minimum pre-road checklist

Before the first HANK longitudinal road test:

- [ ] A baseline build reproducible
- [ ] donor source/commit frozen for the feature under test
- [ ] no wholesale Toyota-stack replacement
- [ ] ACADOS generated artifacts match final model
- [ ] Unit/static tests pass
- [ ] deterministic/replay scenarios pass
- [ ] C3X build/runtime passes
- [ ] SecOC key loads without logging secret material
- [ ] Panda safety mode matches intended HANK/Stock ownership
- [ ] stationary vehicle startup has no unexpected ADAS fault
- [ ] disengage path verified
- [ ] Stock Long fallback verified
- [ ] HANK/TSS onroad-cycle behavior verified stationary
- [ ] rollback image/branch is available

Only after these checks should V1 road validation begin.

---

## 15. D-022 radar ACC early-decel implementation gates

D-022 was `ACCEPTED_FOR_IMPLEMENTATION` at architecture closure and is now software implemented at `93340bf33c7e494123a0c2776aa8a35586d47505`. C3X and vehicle behavior are not validated. The implementation uses the existing native LongitudinalMpc; gain `0.09` and cap `0.6 m` are labelled `C3X BENCH SEED — NOT PRODUCT DEFAULT`, not final product values. The following gates remain the deterministic evidence contract:

| Gate | Required deterministic evidence |
|---|---|
| A — Formula | `v_ego - v_lead < 0` and `= 0` produce zero pressure; positive closing produces `gain * closing_speed` until the cap, then saturates. Include exact zero-closing release and finite values. |
| B — Lead validity | Only `status && radar && radarTrackId >= 0` is eligible. Vision-only, no-lead/synthetic, invalid track ID, and absent-status cases are excluded. |
| C — Per-lead handling | leadOne only, leadTwo only, both leads, column/identity swap, source-priority crossing, and disappearance of one lead. Each eligible lead receives its own pressure; no per-track state is retained. |
| D — Mode isolation | ACC applies the candidate. Blended/e2e, no-lead ACC, and vision-only ACC remain exactly baseline at the solver-facing obstacle and output where inputs are otherwise identical. |
| E — Ownership | `p[4]` Dynamic Follow, `p[6]` Stop Distance, `COMFORT_BRAKE = 2.5`, PORT-02 pull-away, F-005 `W[4]/W[5]`, E-001 `p[0]/p[1]`, and DASR behavior are unchanged. E-002 ACC/blended mode ownership remains intact. |
| F — Zero-pressure equivalence | With pressure zero, both full obstacle matrix and selected solver-facing `p[2]` match baseline. Do not change the shared `process_lead()` trajectory. |
| G — Whole horizon and seam | Subtract constant per-lead pressure from every stage of each eligible real-lead ACC obstacle column **before** lead0/lead1/cruise per-stage `min()`. Cruise and ineligible columns are unchanged; do not patch already-selected `p[2]` or post-solver source. |
| H — Pull-away and final gaps | For `v_lead >= v_ego`, pressure is zero, PORT-02 retains pull-away ownership, PORT-01 retains steady-follow gap, and F-002 retains final stopped geometry. Distinguish geometry equality from history-dependent raw/physical stop position. |
| I — Cut-in | Normal slower-lead and close stopped-lead cut-ins: capture first five frames, raw target, `j[0]`, QP status/iterations, residuals, solution status, resets and finite output. No new non-finite/reset failure or high-gain weak-first-frame pattern at the implementation bench seed. |
| J — Native MPC | Representative stopped/slower-lead 20 Hz multi-frame runs show software-level Goal-C onset effect without added QP cap hits or material numerical degradation against matched baseline. Capture gain/cap and solver-facing `p[2]`. Diagnostic samples are not a continuous certified interval. |
| K — Existing suites | E-001, E-002, PORT-01, PORT-02, PORT-03, F-002, F-005, CFG-01, and their relevant combined regression remain passing. |
| L — Full longitudinal | Run existing longitudinal maneuver regression and compare pass/subtest and known SQP_RTI diagnostic counts with baseline. |
| M — Build | Run `scons -u -j4`; no `PARAM_DIM`, CasADi symbolic-model, or generated-solver change is expected. |
| N — Static/diff | Ruff on changed Python files, `git diff --check`, source-scope review, and no unintended generated tracked artifacts. |

Implementation A/B evidence: 20 new focused tests and 528 existing targeted tests passed (548 combined); full longitudinal passed 4 tests/58 subtests with 42 baseline-matching `SQP_RTI` status-3 diagnostics; `scons -u -j4` exited 0 in 37.15 seconds; Ruff and diff check passed. Native pressure, zero-pressure isolation, and finite/no-reset normal/close cut-ins were verified. The A/B result above did not itself claim the detailed I/J comparisons; the later committed-source acceptance below records them. No C3X or vehicle validation is claimed.

**Committed-source acceptance (2026-09-22; implementation `93340bf33c7e494123a0c2776aa8a35586d47505`): `D022_MATRIX_I = PASS`; `D022_MATRIX_J = PASS`.** The existing Study-F/G 20 Hz native replay methodology was run against committed `long_mpc.py` with `0.09/0.6 m` C3X BENCH SEED. Matched current-HANK baseline disabled only `get_early_decel_pressure()`; the candidate used the actual committed helper and no additional obstacle shift. Six representative scenarios were run three times per variant from identical initial state; all raw/`p[2]` traces repeated exactly and matched the archived Study-G `0.09/0.6` diagnostic cell exactly. This does not make the seed a product value.

For first five cut-in frames (frames 8–12, 0.40–0.60 s), normal slower-lead QP-cap counts were baseline/candidate `1/1` and close stopped-lead `2/2`. Normal QP iteration vectors were `[10,6,4,4,4]` / `[10,5,4,4,4]`; close vectors `[10,10,6,7,6]` / `[10,10,5,7,6]`. First-frame normal raw targets were `+0.006704802` / `-0.000110978` m/s² and close `-1.152724806` / `-1.176487726` m/s², so the committed seed did not reproduce the rejected high-gain weak-first-frame close cut-in. First-five maximum absolute solver residuals were normal `5,242,384.590` / `3,913,627.596` and close `19,396,890.490` / `18,696,022.552` (baseline/candidate). All outputs were finite; solver solution-status nonzero count and reset count were zero.

Matched onset used Study-G diagnostic raw-target crossings, not a product threshold. At `raw <= -0.5 m/s²`, 20 m/s → stopped lead at 110 m crossed at frame/time/distance `14 / 0.70 s / 103.994 m` baseline versus `13 / 0.65 s / 104.993 m` committed. At `raw <= -0.2 m/s²`, 20 → 15 m/s slower lead crossed at `34 / 1.70 s / 58.185 m` versus `33 / 1.65 s / 58.452 m`, and 10 m/s → stopped lead at `10 / 0.50 s / 38.994 m` versus `8 / 0.40 s / 40.000 m`. The 20 m/s → stopped lead at 85 m crossed at the same frame for both variants; the representative effect is scenario-dependent. Across the six 120-frame scenarios, candidate QP-cap counts equalled baseline (`1,1,0,1,2,1`), with no new solver failure, non-finite output, or reset. The slower-lead maximum absolute residual rose from `10,117,990.465` to `26,946,786.265` at frame 8; this exact peak already appeared in the accepted Study-G `0.09/0.6` cell, with QP status 0 and no added QP-cap hit. These are committed-source software diagnostics, not C3X or vehicle-safety validation.

A test failure, new solver failure, or ambiguous ownership change blocks implementation checkpoint. This matrix is a software validation contract; C3X bench, physical gap, radar timing, Toyota actuator response, V0–V3, road/deployment approval, and release acceptance remain separate.

## 16. D-023/D-024 Phase-1 UI and owner-selector implementation gates (2026-09-22)

D-023 and D-024 are **IMPLEMENTED_AND_SOFTWARE_VERIFIED**. UI-01 is implemented at `17d75acb523c050a1fbad0b3237c968b3625e88f`, the UI-02 coordinator/interlock core at `f93b319960f4a5d88345e62f4895e085d38a31e5`, and UI wiring at `fa13c3fcbcb278220419380b8ec124c1fe975d2e`. Existing T-007, T-011, T-017–T-025 and T-030 still apply. No `B` or `V0` status is claimed by this software verification.

| Stage | F-006 / UI-01 profile gates | UI-02 / F-011 owner gates |
|---|---|---|
| U | Strict v1/v2 schema, malformed/duplicate/type/pair rejection, full validated atomic Requested save, v1 non-inferred compatibility, original reset, three mappings, independent Dynamic Follow, gap cycle including first v1/no-profile press, engaged request deferred, Active unchanged, same-session planner restart, next-session apply, APM effective/base split, TSS isolation. | Coordinator state/ownership parser, both Param directions, equal-owner no-op, fresh disengaged/no-`carControl.enabled/latActive/longActive`/no-ACC preconditions, ALKA lateral-active block, transaction/gate ordering, rollback readback, interrupted/crash state, no repeated toggle, reboot-only failure recovery, fail-closed engagement gate. |
| S | Params registry flags/defaults, import/schema/lint, UI/settings routing with no live `LongitudinalPersonality` or numeric bypass, build and unchanged donor/solver/P0 source. | New transaction and session-gate key flags, no direct DP settings bypass, build/lint, no Toyota/Panda/SecOC/TSK/CAN/solver edits, no stale generated artifacts. |
| R | Synthetic/replay HANK/TSS frames prove selected Active versus Requested/pending, base/effective personality and APM, accel profile, Dynamic Follow, Stop Distance/F-005 ownership, no mode thrash and no Stock Long influence. Existing longitudinal and combined feature regressions stay passing. | Synthetic/replay HANK→TSS and TSS→HANK: actual Offroad and new Onroad epoch, fresh `CarParams`, expected `openpilotLongitudinalControl`, Toyota Stock Long flag, Panda safety model/param/alternative experience, no active commands, explicit success/failure UI; stale/missing/timeout/corrupt data and rollback Param alone never open engagement. |
| B | On C3X, display and Params/Active timing across engagement, planner restart and legitimate next session; no live profile leakage. | On C3X, exercise both cycles, disengagement/ALKA/ACC blocks, process restarts, fresh card/Panda safety, failed-cycle interlock, explicit reboot fallback and restored-owner post-reboot verification. |
| V0 | Stationary target-Sienna check of controls, indicator/Requested/Active truthfulness, APM/profile presentation and TSS bypass. | Stationary safe-environment HANK↔TSS, driver takeover, no overlapping commands, owner/Panda/CarParams verification, fail-closed behavior and full reboot recovery. P0 Toyota/SecOC/TSK checks remain separately required. |

UI-01 shows Active versus Requested/pending, advanced original reset, and independent Dynamic Follow. UI-02 shows HANK/TSS confirmed owner, disables unavailable/engaged/ALKA/ACC states, shows pending cycle and explicit failure/reboot action, and labels stored HANK profiles inactive under TSS. Onroad camera controls and settings use the same single coordinator transport; they do not directly write owner transaction, gate, owner or lifecycle Params. `selfdrived` independently blocks engagement until current-session owner verification succeeds.

Accepted Part-A software evidence is `317 passed in 29.64s`. It covers strict CFG v1/v2, Requested/Active lifecycle, gap-button Requested-only behavior, APM interaction, independent Dynamic Follow, owner coordinator/service, five-field transaction including `failure_boot_id`, same-boot failure persistence, full-reboot recovery requirements, session gate, `selfdrived` interlock, UI presentation, transport errors and reboot fallback. Passing U/S/R does not imply B/V0, P0/full release acceptance or road approval.

---

## 17. D-025 following-distance regression contract after F-002 (2026-09-23)

D-025 is **ACCEPTED, IMPLEMENTED_AND_VERIFIED**. Closure commit: `5f4086b462c50128ff0dac1d2aa3fed52d510289`. Test-contract implementation commit: `324b4588b44026b8b1757ba32ecb755c21bce1bb`. It corrects the stale regression-test contract only and changes no production longitudinal or solver behavior.

| Owner | Required implementation evidence |
|---|---|
| Analytic helper | Exact formula cases explicitly pass both `get_T_FOLLOW(personality)` and `get_STOP_DISTANCE(personality)` for Relaxed, Standard and Aggressive. |
| F-002 solver parameter | Existing `test_stop_distance.py` remains authoritative for exact `p[6]`, dimension/order, effective personality, ACC/blended propagation, finite native outputs and solver status. Do not duplicate `p[6]` as an exact maneuver gap. |
| Moving-speed maneuver | At 10 and 35 m/s, compare against the personality-complete analytic oracle and retain the existing e2e/non-e2e tolerances unchanged. |
| Zero-speed maneuver | For all three personalities in e2e and non-e2e: valid maneuver, finite gap/speed/acceleration and relevant solver arrays, status 0, `0 <= final_speed < 0.01 m/s`, `abs(final_acceleration) < 1e-3 m/s²`, and `lead0` for the fixed leadOne fixture. |
| Personality direction | Within each mode, Relaxed final simulation-coordinate separation is strictly greater than Standard and Aggressive. Do not require Standard/Aggressive ordering or a fixed minimum margin. |
| Prohibited oracle | No zero-speed assertion of `final_gap ~= p[6]` or `final_gap ~= p[5] * p[6]`; no widening of the historical distance tolerance. |

The zero-speed thresholds reuse existing Plant/maneuver semantics. The closure probe ran every e2e/personality pair three times: all 18 runs were valid with status 0 and `lead0`; each case repeated exactly. E2e ended at zero speed/acceleration. Non-e2e maximum final speed was `0.002925707 m/s`, and maximum absolute final acceleration was `3.741398e-05 m/s²`. These observations justify convergence checks but do not freeze exact gaps, bitwise repeatability or product margins.

Implementation acceptance passed `14` following-distance tests and `13` stop-distance tests. Semantic ownership remains separated: analytic helpers own the exact personality-complete formula; F-002 owns exact solver-facing `p[6]`; moving-speed maneuvers own approximate analytic behavior with unchanged tolerances; zero-speed maneuvers own stable finite convergence and Relaxed directional separation. Approximately 3.0 m and `0.75 * p[6]` remain diagnostics only, not product targets or physical bumper-gap oracles.

## 18. Phase-1 UI-02 B2 final software verification status (2026-09-23)

| Gate | Status | Accepted evidence |
|---|---|---|
| UI-01 implementation | PASS | `17d75acb523c050a1fbad0b3237c968b3625e88f`; three-mode CFG v2, Requested/Active and independent Dynamic Follow |
| UI-02 core | PASS | `f93b319960f4a5d88345e62f4895e085d38a31e5`; coordinator, gate and fail-closed interlock |
| UI-02 UI wiring | PASS | `fa13c3fcbcb278220419380b8ec124c1fe975d2e`; coordinator-only requests and truthful HANK/TSS presentation |
| D-025 diagnosis | PASS | `STALE_TEST_CONTRACT_AFTER_F002`; production behavior was not changed |
| D-025 closure | PASS | `5f4086b462c50128ff0dac1d2aa3fed52d510289` |
| D-025 implementation acceptance | PASS | `324b4588b44026b8b1757ba32ecb755c21bce1bb`; 14 following-distance and 13 stop-distance tests passed |
| B2 final software verification | PASS | Part A 317 passed; Part B 436 passed; full longitudinal 4 tests/58 subtests; SQP_RTI status-3 count 42; SCons exit 0 |
| C3X bench | NOT RUN | No installation, device boot/runtime, manager lifecycle or Panda runtime evidence |
| Stationary vehicle | NOT RUN | No physical owner switch, stopped-gap or target-Sienna stationary evidence |
| Road validation | NOT RUN | No V1–V3 or vehicle-safety evidence |

The accepted B2 build ran `scons -u -j4` in 62.56 seconds with only the known CasADi 3.7.2 compatibility warning and no tracked generated-solver diff. Frozen production values remain `PARAM_DIM = 7`, `COMFORT_BRAKE = 2.5`, Stop Distance Relaxed/Standard/Aggressive = `4.5/4.0/4.0`, and D-022 C3X bench seed gain/cap = `0.09/0.6 m`. The D-022 seed remains **C3X BENCH SEED ONLY — NOT PRODUCT DEFAULT**.

Phase-1 functional implementation is **COMPLETE** and WSL/software verification is **PASS**. C3X bench, stationary vehicle and road validation are **NOT STARTED**. This does not mark Phase 1 fully released. **NEXT: `PHASE1_RC_READINESS_RERUN`.**

## 19. Readiness audit and corrective gates (2026-11-10)

Runtime under audit: `b35a4c1bdbe83468690935cf08d6c3e8d0174855`. Evidence: [audit logs and reproduction details](docs/hank/evidence/2026-11-10/README.md).

| Gate | Current result | Scope / limitation |
|---|---|---|
| Selected HANK/control/CFG/owner/UI suites | PASS: 727 | Existing tests; not proof all UI requirements are covered |
| Existing leads/LongControl | PASS: 4 | One Python multiprocessing fork warning |
| Full longitudinal maneuvers | PASS: 4 / 58 subtests | SQP_RTI status-3 count 42, historical baseline match |
| SCons | PASS | Existing WSL workspace build; not a clean-room/C3X build |
| Changed-Python Ruff | BASELINE DEBT | 17 errors; zero new diagnostics against A code/message/source-line fingerprints |
| D-024 blocked/unavailable action | OPEN / contract probe fails | Three isolated actual Params cases return enabled where disabled is required; existing test expects the wrong result |
| D-023 APM effective display | OPEN / source data-flow mismatch | Actual APM override differs from base; HUD uses published base; no rendered UI verification |
| Corrective fresh-state recovery | NOT RUN | FIX-UI-01 must prove re-enable after fresh safe evidence, no automatic retry, and request-time coordinator rejection |
| Cross planner/UI APM correction | NOT RUN | FIX-UI-02 must prove actual effective-state display and stale-data handling |
| C3X / stationary Sienna / V1-V3 | NOT RUN | Software results do not grant device or vehicle approval |

Prior B2/UI PASS remains historical evidence for those executed tests, not blanket compliance. See the execution plan for ordered correction gates. D-025 tolerances, seven-parameter solver ownership, D-022 bench-seed classification and P0 trust boundaries remain unchanged.
