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
| T-004 | Lead Pull-away | C provisional -> HANK adapter | High | REQ | REQ | REQ | REQ | REQ | REQ | REQ | REQ |
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

D-022 is `ACCEPTED_FOR_IMPLEMENTATION`, not implemented or vehicle validated. Implement test-first using the existing native LongitudinalMpc and, where needed, planner-to-MPC data flow. Keep diagnostic gain/cap seeds labelled `C3X BENCH SEED — NOT PRODUCT DEFAULT`; no product value is frozen. The following gates are required before an implementation checkpoint:

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

A test failure, new solver failure, or ambiguous ownership change blocks implementation checkpoint. This matrix is a software validation contract; C3X bench, physical gap, radar timing, Toyota actuator response, V0–V3, road/deployment approval, and release acceptance remain separate.
