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
