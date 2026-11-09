> CURRENT EXECUTION: follow ../../HANK_EXECUTION_PLAN.md and CURRENT_STATE.md. Earlier NEXT/PASS statements below are dated historical records, not current instructions.

# HANK implementation checkpoint — IMPL-00

> **Historical checkpoint:** This document preserves the audit state recorded before an executable WSL environment and runtime implementation were available. Its blockers and test status are historical evidence, not the current project state. See [CURRENT_STATE.md](CURRENT_STATE.md) for the durable state through E-001, E-002, and PORT-01.

Date: 2026-09-14. Status: baseline/source audit complete; implementation and executable verification BLOCKED. Not a release or vehicle-validation approval.

## Authority and baseline

Repository: Hank102373/dp-sienna-0103.
- A/main: 1986516b325cbf8d173f6ebaea989ed45673c49f.
- Authority: docs/hank-architecture-v1 at f2669c17d9ce9594b77fd88f97689d031f845dd2; all three HANK documents v1.0 read.
- GitHub comparison confirms authority branch is ahead of A with exactly the three authority Markdown files changed.
- Research prototype: sienna-longitudinal-dev at c4d50cfdb213264fe26ac96c522a33597b6bbe36; one commit above A, five files changed.
- Implementation branch: hank/implementation-v1, created from the authority commit (A code plus documents).
- B: CT921/openpilot 615799f95e978fbf643d1e762d605b4d5b06499f.
- C: CT921/openpilot 3d75e471c74fccf0067dcda8cfe1374cf1268215.

Sources: [authority](https://github.com/Hank102373/dp-sienna-0103/tree/f2669c17d9ce9594b77fd88f97689d031f845dd2), [prototype diff](https://github.com/Hank102373/dp-sienna-0103/compare/1986516b325cbf8d173f6ebaea989ed45673c49f...c4d50cfdb213264fe26ac96c522a33597b6bbe36).

The prior standalone ABC analysis artifact has not been located in the inspected branches or available context search. The authority documents and pinned A/B/C source were read; this does not claim the missing artifact was read.

## Spec → existing prototype → required change / compliance

| Spec | Existing prototype | Required change / strategy | Current compliance |
|---|---|---|---|
| F-001 Dynamic Follow | New nine-point HANK curves, not B curves | Behavior-preserving B port; retain original donor preset and boundary tests | Not implemented on production branch |
| F-002 Stop Distance | Seven-parameter model plus new profile values | Adapt B parameterization; retain A comfort brake unless separately decided; regenerate solver | Not accepted; generated/runtime evidence missing |
| F-003 Pull-away | Per-element trigger/gain/offset abstraction | Reject prototype formula under D-003/D-018; complete C donor freeze under D-008 | Provisional; blocked from production activation |
| F-004 Acceleration Personality | HANK interpolation/max-accel cap | Adapt B accel_personality functions with typed Params mapping; reject custom cereal/physical drive-mode transport | Not implemented |
| F-005 Low-speed jerk | HANK jerk_factor with live smoothing | Review B weight dependencies and freeze numerical decision; no invented blend | Pending decision in Spec |
| F-006 Profiles | Reads every 0.25 s; smooths targets during operation | HANK validated immutable active profile; controlled apply boundary; names 緊湊/一般/舒適 | Prototype conflicts with D-010 |
| F-007 DP longitudinal | APM explicitly bypassed when prototype enabled | Preserve APM plus ACM/AEM/DTSC/DASR orchestration; investigate baseline issues below | Source retained in production; behavior unverified |
| F-008 Lateral/UI/device | No changed files in prototype diff | Preserve A; validate regression | Source unchanged; tests not run |
| F-009 Toyota functions | No changed Toyota files in prototype diff | Preserve A including SecOC/TSK and stock-long | Source unchanged; tests not run |
| F-010 Stock Long | No explicit HANK bypass guard in prototype profile/MPC path | Ensure HANK donor behavior bypassed under CP.openpilotLongitudinalControl=False | Not implemented/verified |
| F-011 Quick mode switch | No HANK selector or recovery implementation in prototype diff | Guard disengagement/command state; use A lifecycle; verify ownership and failure path | Not implemented |
| §6 P0 boundary | No Toyota/SecOC/Panda changes in five-file prototype diff | Keep source boundary; compare actual authenticated outputs later | Source-only observation, not P0 acceptance |
| §8 Solver | Prototype changes PARAM_DIM 6→7 | Clean generation, dimensions, convergence, reset, C3X runtime | NOT RUN |
| §10–11 Acceptance | No complete verification evidence supplied | Execute HANK_TEST_MATRIX in required stage order | Not accepted |

## Feature provenance / exact source closure

A/B/C MPC path: selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py.

- F-001: B get_dynamic_follow / get_T_FOLLOW. B speed knots in m/s: [0,6,10,10.01,15,27.7]. Aggressive time gaps: [1,1.2,1,0.9,0.95,1]. Preserve donor preset, including narrow 10→10.01 transition; do not silently smooth a locked donor behavior. Boundary/trajectory tests required.
- B update adds 0.5 s when sin(pitch_rad)<-0.04. Dynamic Follow closure must include pitch availability/units/sign and fallback; copying just the lookup function is not full B behavior.
- F-002: B get_STOP_DISTANCE and live slot 6. B adds 0.5 m if ToyotaTune and not SMART_DSU. Exposing base values as actual applied stopping distance would omit this dependency. A COMFORT_BRAKE=2.5; B=1.75; preserve A pending separate decision.
- F-003: C get_stopped_equivalence_factor uses np.all(delta_speed>0) over the predicted vector, gain 2, cap 12 m, and taper to zero at 26 km/h. B uses threshold >0.3, cap 10 m, taper at 15 km/h. Prototype elementwise clipping is not equivalent to either np.all condition. Test mixed-sign horizons, zero, missing/reacquired leads and both lead slots before freezing C.
- F-004: B top/selfdrive/controls/lib/accel_personality/accel_controller.py imports custom.LongitudinalPlanTOP.AccelerationPersonality and accel_profiles.get_max_accel_hermite/get_min_accel_hermite. Preserve algorithm/provenance including upstream MIT attribution; adapt transport to A. accel_profiles and all callers remain to be fully reviewed. A separate AccelController instance inside B MPC must be checked for personality synchronization with planner.
- F-005: B set_weights applies low-speed factor [0.9,1] over [0,10] m/s only when both lead velocities are >= ego; aggressive jerk factor 0.45. C differs materially (0.05 low-speed factor, braking_offset and aggressive 0.22). Do not combine.
- F-011: A system/hardware/hardwared.py consumes/clears OnroadCycleRequested and gates not_onroad_cycle. A system/manager/manager.py reacts to deviceState.started transitions. Presence alone does not prove safe recovery; caller guards, card restart, fresh CarParams, safety reset and failed-cycle behavior need full closure.

## Hidden dependencies and unresolved evidence

### E-001 — DTSC bound overwrite in A (High)

A planner writes mpc.params[i,0/1] from DTSC immediately before mpc.update(). A MPC update then assigns all rows in slots 0/1 to ACCEL_MIN/MAX before solver execution. This is a source-level overwrite, not a demonstrated numerical test result. Prototype retains the sequence.

Required: deterministic capture of parameters reaching solver under DTSC ON/OFF, and comparison of final output clipping. Spec T-010 requires effective curvature constraints; merely keeping the call cannot satisfy it. A repair may fit D-005 but will alter baseline behavior; classify and document that difference explicitly, with a dedicated regression gate, before accepting it.

### E-002 — A planner local mode and MPC mode differ (High)

A initializes self.mpc.mode='acc'. update() computes local mode from experimentalMode/AEM, but this inspected planner does not assign local mode to self.mpc.mode. Local mode still changes final output selection. Inspect other callers and deterministic transitions before classifying full-system behavior.

Required: capture MPC mode/weights/params and output selection for ACC↔blended/AEM transitions. If repair is necessary to satisfy T-009, document baseline deviation explicitly. Do not silently redesign AEM.

### E-003 — Profile/validation edge cases in research prototype

The prototype JSON path assumes mappings and uses candidate.get without a mapping check. Lists/null can produce AttributeError outside the listed exception handler. Tests cover only three narrow profile cases. Values are live-reloaded and the enabled flag can change while engaged; smoothing alone does not implement the D-010 apply boundary. Reuse concepts only after validation and ownership tests, not the existing control formula.

### E-004 — Build dependency closure

A MPC SConscript regenerates from long_mpc.py, modeld/constants.py and named acados headers/templates; imports from new helper files do not automatically become generation dependencies. If model-generation constants move, declare dependencies explicitly. Generated files are not present in the inspected tracked MPC tree; this alone does not prove a device has a mismatched binary. Clean generation/runtime dimension evidence is mandatory.

## Blockers and next executable unit

- ENV-001: This session exposes GitHub read/write but no shell/Python/build runtime. No Python, SCons, lint, unit, replay or solver command was executed. Before control code changes, provide an executable repository environment or an operational, reviewable CI execution path supporting required dependencies.
- DOC-001: Locate/read prior standalone ABC analysis to avoid losing accepted evidence not reproduced in current docs.
- GATE-001: F-003 donor freeze and F-005 numerical decision remain explicitly pending in authoritative documents. Do not silently mark them Accepted.
- E-001/E-002 require reproduction and classification. If fixing them requires changing architecture/safety decisions, escalate as a decision BLOCKER with evidence; no such decision was changed here.

Next: reproduce E-001/E-002 on pinned A, close B Dynamic Follow inputs/callers, then PORT-01 as an independently testable commit. No vehicle deployment or main merge.

## Commit map and rollback

| Logical unit | Content | Parent / rollback |
|---|---|---|
| Existing prototype c4d50cf | Research profile/MPC/planner changes, five files | A; retained untouched per D-018 |
| Existing authority f2669c1 | Three authority documents, code identical to A | A |
| IMPL-00 (commit containing this report) | Audit/compliance/provenance only | f2669c17d9ce9594b77fd88f97689d031f845dd2; revert this documentation commit |

## Test and regression results

| Check | Result | Scope/limitation |
|---|---|---|
| GitHub baseline ancestry and changed-file inventory | PASS | Authority branch code equals A; prototype five-file diff inspected |
| Authority documents read | PASS | All three v1.0 documents at pinned commit |
| A/B/C source inspection | PARTIAL | MPC, A planner/build/lifecycle excerpts, B accel controller; not complete dependency closure |
| Build / solver generation | NOT RUN | ENV-001 |
| Lint / type / Python static checks | NOT RUN | Source inspection is not executable static checking |
| Available unit tests | NOT RUN | ENV-001; existing tests are not pass evidence |
| Deterministic / replay regression | NOT RUN | ENV-001 |
| C3X bench and V0–V3 | NOT RUN | No device/vehicle evidence in this checkpoint |
| T-001–T-030 acceptance | NOT ACCEPTED | Required executable and physical-stage evidence outstanding |

Final diff for IMPL-00: this report only. Safety-relevant runtime changes: none. No claim of driving safety, behavioral equivalence, or completed Phase 1.

## Current continuation state — D-022 implementation (2026-09-22)

This section records the current state without revising the historical IMPL-00 audit above. The latest production commit is `93340bf33c7e494123a0c2776aa8a35586d47505` (`feat(longitudinal): add radar early-decel pressure`). At this documentation sync start, `origin/hank/implementation-v1` matched that commit and the working tree was clean.

F-005 Goal-C radar ACC early deceleration is **IMPLEMENTED_AND_REGRESSION_VERIFIED** under D-022 `STATELESS_RELATIVE_SPEED_PRESSURE`. Production: `selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py` (+14 lines). Tests: `selfdrive/controls/tests/test_radar_early_decel.py` (+240 lines). The C3X BENCH SEED gain `0.09` and cap `0.6 m` are **NOT PRODUCT DEFAULT**, **NOT FINAL TUNING**, and **NOT YET VALIDATED** on C3X or a vehicle. Goal D remains **NO_STRONG_DECEL_CHANGE_JUSTIFIED**.

Evidence: 20 new focused tests; 528 existing targeted tests; 548 combined; full longitudinal 4 tests/58 subtests with 42 baseline-matching `SQP_RTI` status-3 diagnostics; `scons -u -j4` exit 0 in 37.15 seconds with only the known CasADi warning; Ruff and diff check PASS. Native solver-facing pressure and zero-pressure isolation were verified; normal/close cut-ins were finite with no reset. `PARAM_DIM = 7`, `COMFORT_BRAKE = 2.5`, prior feature/parameter ownership, CasADi symbolic model, and tracked generated solver source were preserved. No solver regeneration occurred.

**NEXT: `PHASE1_RC_READINESS`.** C3X bench, real radar/actuator response, physical stopped-gap mapping, V0–V3, P0/full release acceptance, vehicle safety, and deployment approval remain outstanding. No Phase-1 release or main merge is authorized by this software checkpoint.

## Current continuation state — Phase-1 UI/selector design closure (2026-09-22)

D-023 and D-024 are `ACCEPTED_FOR_IMPLEMENTATION` after the user resolved the four product choices raised by read-only `PHASE1_UI_SELECTOR_CLOSURE`. D-023 freezes the three primary HANK modes (緊湊/Aggressive/sport, 一般/Standard/normal, 舒適/Relaxed/eco), independent Dynamic Follow, advanced original reset (Standard/stock/false), strict v2 Requested/Active session snapshot, gap-button Requested cycling, APM effective-personality precedence, and POST_RC_TUNING classification for real-time +/-. It preserves exact CFG v1 without guessed personality migration. D-022 gain/cap remain C3X bench seeds and are not mode controls.

D-024 freezes the single HANK/TSS owner coordinator and selfdrived engagement interlock: disengaged/no-lateral/no-longitudinal/no-ACC precondition; `dp_toyota_stock_lon` mapping; one existing OnroadCycleRequested Offroad→Onroad cycle; fresh CarParams/Panda safety verification; last-confirmed-owner Param rollback plus explicit `SWITCH_FAILED`; no automatic retry; full reboot and restored-owner re-verification before engagement. The existing DP direct Stock Long setting must not bypass this path. TSS UI cannot claim a saved HANK profile is active. Toyota/Panda/SecOC/TSK/authenticated CAN and longitudinal solver remain protected.

This is docs-only architecture closure. No v2 production/config/UI code, tests, build, C3X or vehicle validation is claimed. U/S/R/B/V0 implementation gates are in `HANK_TEST_MATRIX.md`. **NEXT: `PHASE1_UI_SELECTOR_IMPLEMENTATION`.** Phase 1, P0/full release acceptance, deployment, road validation and main merge remain unapproved.

## Current continuation state — D-025 following-distance test contract (2026-09-23)

`PHASE1_UI02_FINAL_VERIFY_B2` stopped at targeted longitudinal regression with two non-e2e zero-speed failures in `test_following_distance.py`. Diagnosis localized the first runnable failure to F-002 commit `d2eb41426aa3e299f37ae8ffdc73f1c563015a95`: solver-facing `p[6]` was correct, solver status was 0, and F-005, D-022, UI-01 and UI-02 were not the origin. The historical test file had not been migrated when personality stop distance was introduced.

D-025 is `ACCEPTED_FOR_IMPLEMENTATION`. Exact helper equations use explicit T-follow and stop distance; F-002 tests continue to own exact `p[6]`; moving-speed maneuvers retain their existing tolerances with a personality-complete oracle; zero-speed maneuvers instead own valid finite convergence, status 0, final speed below `0.01 m/s`, absolute acceleration below `1e-3 m/s²`, fixed-fixture `lead0`, and Relaxed separation greater than Standard/Aggressive within each mode. There is no Standard/Aggressive ordering, exact gap, cross-mode equality or fixed margin requirement.

Three identical runs of each of the six zero-speed cases were exact repeats. All 18 were valid with status 0 and `lead0`; e2e ended at zero speed/acceleration, while non-e2e maximum final speed was `0.002925707 m/s` and maximum absolute final acceleration was `3.741398e-05 m/s²`. Approximately 3.0 m and `p[5] * p[6]` remain diagnostic observations only, not product or physical-gap targets.

This checkpoint is documentation-only. No production/test code, tolerance, longitudinal tuning, UI, solver or generated artifact changed. B2 final verification has not passed. **NEXT: `PHASE1_B2_FOLLOWING_DISTANCE_TEST_CONTRACT_IMPLEMENTATION`.** C3X, physical-gap mapping, V0–V3, P0/full release acceptance, vehicle safety and deployment approval remain outstanding.

## Current continuation state — Phase-1 UI-02 B2 complete (2026-09-23)

- Implementation branch: `hank/implementation-v1`
- Current implementation HEAD: `324b4588b44026b8b1757ba32ecb755c21bce1bb`
- Working state before this docs-only sync: clean
- Remote state before this docs-only sync: `origin/hank/implementation-v1` matched `324b4588b44026b8b1757ba32ecb755c21bce1bb`
- Last completed gate: `PHASE1_UI02_FINAL_VERIFY_B2_PASS`
- Next gate: `PHASE1_RC_READINESS_RERUN`

Continuation map:

| Unit | Commit | Durable result |
|---|---|---|
| UI-01 three-mode profile configuration | `17d75acb523c050a1fbad0b3237c968b3625e88f` | Implemented and verified: CFG v2, Compact/Normal/Comfortable, Requested/Active/pending, independent Dynamic Follow, Requested-only gap cycle and APM separation |
| UI-02 owner core | `f93b319960f4a5d88345e62f4895e085d38a31e5` | Implemented and verified: single coordinator, five-field transaction, gate-first flow, fresh evidence, rollback, `SWITCH_FAILED`, boot-bound recovery and hard engagement interlock |
| UI-02 UI wiring | `fa13c3fcbcb278220419380b8ec124c1fe975d2e` | Implemented and verified: coordinator-only settings/onroad actions, truthful HANK/TSS state, explicit failure and reboot fallback |
| D-025 closure | `5f4086b462c50128ff0dac1d2aa3fed52d510289` | Accepted personality-complete following-distance regression ownership |
| D-025 implementation | `324b4588b44026b8b1757ba32ecb755c21bce1bb` | Test-only implementation accepted; no production or solver behavior changed |

Final B2 evidence: UI/owner/CFG Part A `317 passed in 29.64s`; D-025 acceptance `14` following-distance plus `13` stop-distance tests; targeted HANK longitudinal Part B `436 passed / 0 failed in 31.16s`; full longitudinal `4 passed / 58 subtests in 31.54s` with 42 baseline-matching SQP_RTI status-3 diagnostics; full `scons -u -j4` exit 0 in 62.56 seconds with only the known CasADi 3.7.2 warning and no tracked generated-solver diff.

Frozen production state: `PARAM_DIM = 7`; `COMFORT_BRAKE = 2.5`; Stop Distance Relaxed/Standard/Aggressive = `4.5/4.0/4.0`; D-022 gain/cap `0.09/0.6 m` remain **C3X BENCH SEED ONLY — NOT PRODUCT DEFAULT**. PORT-01, PORT-02, PORT-03, F-002, F-005 and D-022 remain accepted and unchanged by UI/D-025 work.

Phase-1 functional implementation is **COMPLETE** and WSL/software verification is **PASS**. C3X installation/boot/runtime, actual device manager lifecycle, Panda runtime evidence, stationary owner switching, physical stopped-gap, real CAN behavior, V0–V3, D-022 final tuning, P0/full release acceptance, deployment and vehicle safety remain unproven. Phase 1 is not fully released, and no release branch decision is made here.

**NEXT: `PHASE1_RC_READINESS_RERUN`.** A fresh session should start from this checkpoint and use actual evidence to decide whether the next gate is an RC1 branch or C3X bench work.

## GOV-01 / readiness audit correction — 2026-11-10

Audited runtime baseline: b35a4c1bdbe83468690935cf08d6c3e8d0174855. RC1 and mirror flat RC1 refs exist. The earlier RC-readiness NEXT is completed historical work, not a request to repeat it.

The new execution authority is [HANK_EXECUTION_PLAN.md](../../HANK_EXECUTION_PLAN.md); the single current continuation pointer is [CURRENT_STATE.md](CURRENT_STATE.md). GOV-01 adds the plan, root instructions, history preservation and durable [audit evidence](evidence/2026-11-10/README.md), with no runtime change.

Fresh suites/build passed within their tested scope, but UI compliance is OPEN: blocked/unavailable actions stay enabled contrary to D-024, and APM override display observes base rather than planner effective personality. Prior UI PASS is not proof these requirements are satisfied. FIX-UI-01 is the first runtime correction; FIX-UI-02 follows. C3X/vehicle/release remain unvalidated. Do not move RC1 refs or reuse old PORT-01-only requirements against the current seven-parameter MPC.


## FIX-UI-01 local correction — 2026-11-10

Base `fb25d6c385e0373da9410a5b005555cfdfdc5e12`; user authorized owner blocked/unavailable action repair, tests, handoff and one local checkpoint. Completed model + HUD/settings fix and 51 new regression cases. Baseline independent proof: 4 expected failures. Final relevant suites: 342 passed / 34.02 s; after final text wrapping, actual desktop owner surface render/mouse probe and 7 wiring tests passed; final timeout wording was followed by 84 affected UI tests passing in 3.66 s. Changed-source/test Ruff and diff check pass. [Full evidence and recovery contract](evidence/2026-11-10/fix-ui-01/README.md).

Fresh safe vehicle/manager timestamps and non-sending coordinator socket availability restore a manual confirmation; never replay the rejected target. Real coordinator still rechecks independently. No coordinator protocol/state-machine/schema change, no longitudinal/P0/solver modification. RC1 refs unchanged, no push/device action. Desktop English owner UI acceptance is bounded; Chinese labels under the probe font, full app and C3X remain open. Single current NEXT is FIX-UI-02 in CURRENT_STATE; full build/regression belongs to VERIFY-RC-02.
