# HANK current implementation state

Updated: 2026-09-17. Scope: durable implementation and verification state through F-002. This is not a release or vehicle-validation approval.

## Repository state

- Repository: `Hank102373/dp-sienna-0103`
- Branch: `hank/implementation-v1`
- Current implementation checkpoint: `d2eb41426aa3e299f37ae8ffdc73f1c563015a95`
- Remote state at synchronization start: `origin/hank/implementation-v1` matched `d2eb41426aa3e299f37ae8ffdc73f1c563015a95`.
- A/main remains the platform authority at `1986516b325cbf8d173f6ebaea989ed45673c49f`.
- `sienna-longitudinal-dev` remains research only under D-018.
- WSL Ubuntu 24.04 provides the executable development environment at `/home/hank/src/dp-sienna-0103`.

## Completed checkpoints

### E-001 — Preserve DTSC acceleration bounds

- Commit: `017d2b17798670f0147a7f633197b0eebf9776f5`
- Message: `fix(longitudinal): preserve DTSC accel bounds into MPC solver`
- Result: `E001_FIX_PASS`

The baseline overwrite was reproduced. `LongitudinalPlanner` now passes `accel_bounds` explicitly to `LongitudinalMpc.update()`. The MPC writes `ACCEL_MIN` and `ACCEL_MAX` every frame when bounds are absent. Provided bounds reject an invalid shape, non-finite values, or any stage where `a_min > a_max`.

Solver-facing OFF -> ON -> OFF behavior was verified, including restoration of defaults and no cross-frame DTSC leakage.

Verification:

- E-001 targeted: 4 passed
- Existing longitudinal: 4 passed / 58 subtests
- SCons: PASS
- `git diff --check`: PASS
- Ruff: no new lint regression; `longitudinal_planner.py:48 PIE790` is `PRE_EXISTING_BASELINE_LINT`
- Existing longitudinal `SQP_RTI` status 3 diagnostic count: 42, matching baseline

Limit: solver-facing data flow was verified. Vehicle behavior was not validated.

### E-002 — Synchronize planner and MPC mode

- Commit: `0940bc5399a1b3533375a6b58aba827c17a1cd7d`
- Message: `fix(longitudinal): synchronize planner mode with MPC`
- Result: `E002_FIX_PASS`

The baseline mismatch between planner final mode and `LongitudinalMpc.mode` was reproduced. The planner now synchronizes the final mode after the AEM decision and before mode-dependent `set_weights()` and `update()` calls.

ACC -> blended -> ACC and AEM inactive -> active -> inactive transitions were verified. W, `p[5]`, obstacle selection, yref, and source follow the final mode. No transition-triggered solver reset was added.

Verification:

- E-002 targeted: 2 passed
- E-001 targeted: 4 passed
- Existing longitudinal: 4 passed / 58 subtests
- SCons: PASS
- Native transition frames: solver status 0, finite v/a/j, reset count 0

Limit: solver-facing mode synchronization was verified. Vehicle behavior was not validated.

### PORT-01 — Dynamic Follow from TOP01003

- Commit: `4c7dd35fce64a7c06253e497cc2afd52d7e0f1d5`
- Message: `feat(longitudinal): port TOP01003 dynamic follow`
- Result: `PORT01_IMPLEMENTATION_PASS`
- Donor: B / `TOP01003` at `615799f95e978fbf643d1e762d605b4d5b06499f`

Implemented behavior:

- Exact B `get_dynamic_follow()` personality curves, including the narrow 10.00 -> 10.01 m/s transition
- Lookup input is MPC `self.x0[1]`
- Feature OFF preserves A static follow values: Relaxed 1.75, Standard 1.45, Aggressive 1.25
- Downhill `+0.5 s` applies only while Dynamic Follow is active
- Requested key: `HankDynamicFollow`, PERSISTENT BOOL, default 0
- Session snapshot: `HankDynamicFollowActive`, BOOL with `CLEAR_ON_OFFROAD_TRANSITION | CLEAR_ON_IGNITION_ON` and no default
- Requested changes during a session do not alter active control behavior
- A same-session `plannerd` restart reuses the existing Active value
- Dynamic Follow requires `CP.openpilotLongitudinalControl`; Toyota Stock Long disables its effective behavior

PORT-01 keeps `PARAM_DIM = 6`. It did not import B static `get_T_FOLLOW` constants, Stop Distance, `COMFORT_BRAKE = 1.75`, pull-away behavior, low-speed jerk tuning, AccelController, ToyotaTune stop correction, or Toyota/SecOC/Panda changes.

Verification:

- PORT-01 targeted: 82 passed
- Donor interpolation: 27 cases plus unsupported-personality rejection PASS
- E-001 targeted: 4 passed
- E-002 targeted: 2 passed
- Existing longitudinal: 4 passed / 58 subtests
- Combined: 92 passed / 58 subtests
- SCons: PASS
- Ruff: no new lint regression; approved baseline PIE790 remains
- `git diff --check`: PASS
- Native evidence: 73 observed frames; native status and solution status 0; params/v/a/j finite; reset count 0
- Existing longitudinal `SQP_RTI` status 3 diagnostic count: 42, matching baseline

Limits: T-002 C3X bench and V0/V1/V2/V3 validation have not run. The deterministic and solver-facing evidence does not approve vehicle deployment.

### PORT-02 — Lead Pull-away from TOP096

- Closure result: `PORT02_CLOSURE: READY_C`
- Implementation commit: `772a786f55b8c195ffd20f038c7757569590db0d`
- Message: `feat(longitudinal): port TOP096 pull-away transform`
- Implementation result: `PORT02_IMPLEMENTATION_PASS`
- Canonical donor: C / `CT921/openpilot`, branch `TOP096`
- Donor commit: `3d75e471c74fccf0067dcda8cfe1374cf1268215`
- Donor file: `selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py`
- Frozen function: `get_stopped_equivalence_factor(v_lead, v_ego)`

The frozen and implemented C behavior uses a strict horizon-wide `np.all(v_lead - v_ego > 0)` trigger, offset gain 2, pre-taper cap 12 m, taper endpoint 26 km/h, and `COMFORT_BRAKE = 2.5` m/s². It uses MPC `self.x0[1]` for `v_ego`, applies independently to leadOne and leadTwo before obstacle/source selection, and applies the same transform to missing synthetic leads. The behavior has no added epsilon, stage-wise replacement, counter, hysteresis, or persistent state. Its horizon-wide discontinuity is intentional and frozen.

The implementation preserves current HANK `STOP_DISTANCE`, `COMFORT_BRAKE = 2.5`, `PARAM_DIM = 6`, PORT-01 Dynamic Follow, E-001 `accel_bounds`, and E-002 mode synchronization. Production scope is limited to `selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py`; deterministic regression coverage is in `selfdrive/controls/tests/test_pull_away.py`. The checkpoint changed 2 files with 173 insertions and 5 deletions.

PORT-02 did not import F-002 donor Stop Distance values, personality stop distance, `PARAM_DIM = 7`/`p[6]`, B `COMFORT_BRAKE = 1.75`, C `braking_offset`, F-005 low-speed jerk/weight or response tuning, donor Dynamic Follow or static `T_FOLLOW`, AccelController, donor planner/LongControl, Toyota interface/CarState/CarController, Panda, SecOC, cereal schema replacement, radar replacement, or generated donor solver artifacts.

Test-first baseline evidence was 32 failed / 13 passed with exit 1. The first meaningful numerical mismatch used ego speed 0 and lead speed 0.001 m/s: baseline A produced approximately 0.0000002 m while frozen C expected 0.0020002 m.

Verification after implementation:

- PORT-02 targeted: 45 passed
- E-001 targeted: 4 passed
- E-002 targeted: 2 passed
- PORT-01 targeted: 82 passed
- Existing longitudinal: 4 passed / 58 subtests
- Combined: 137 passed / 58 subtests
- Existing longitudinal `SQP_RTI` status 3 diagnostic count: 42, matching baseline
- SCons: PASS, exit 0, 37.64 seconds
- Ruff: PASS, all checks passed on the changed production and test files
- `git diff --check`: PASS
- Focused native evidence: 29 frames; native and solution status 0; params/v/a/j finite; reset count 0

Limits: deterministic, solver-facing, regression, lint, and build verification passed. C3X bench, vehicle, and deployment validation remain outstanding.

### PORT-03 — Acceleration Personality from TOP01003

- Closure result: `PORT03_CLOSURE: READY_B_ADAPTER`
- Implementation commit: `dab63d6ea1dcbc23db11ced15c6b08036404bafa`
- Message: `feat(longitudinal): port TOP01003 accel personality`
- Implementation result: `PORT03_IMPLEMENTATION_PASS`
- Canonical donor: B / `CT921/openpilot`, branch `TOP01003`
- Donor commit: `615799f95e978fbf643d1e762d605b4d5b06499f`
- Donor file: `top/selfdrive/controls/lib/accel_personality/accel_profiles.py`
- Frozen scope: B maximum-acceleration personality curves through a thin HANK-owned validated input adapter

The frozen profiles are `sport = 0`, `normal = 1`, `eco = 2`, and `stock = 3`. The speed breakpoints in m/s are `[0., 1., 3., 6., 8., 11., 16., 20., 25., 30., 55.]`. Maximum acceleration values in m/s² are:

```text
eco    = [2.0, 2.0, 1.5, .75, .60, .55, .40, .36, .28, .22, .08]
normal = [2.0, 2.0, 1.9, 1.42, .95, .83, .61, .54, .45, .38, .15]
sport  = [2.0, 2.0, 1.9, 1.75, 1.3, 1.1, .82, .71, .55, .48, .25]
```

The donor-exact algorithm clips speed to the breakpoint domain and uses cubic Hermite interpolation with endpoint secant slopes and averaged adjacent secants for interior slopes. Segment selection remains `np.searchsorted(xp, x) - 1`. Donor Hermite overshoot is preserved without an added output clamp or monotonicity limiter.

The implemented adapter accepts an explicit validated profile. Stock/default preserves current HANK `get_max_accel()` behavior; normal/eco/sport use the exact donor maximum curve. Invalid types or values are rejected without silent fallback. PORT-03 keeps the profile immutable for the planner instance; persistence, live switching, and HANK three-mode mapping remain CFG-01 work.

The application point is the ACC base upper-acceleration cap after final AEM mode selection and E-002 synchronization, and before turn limiting, MAA, coast handling, DTSC, MPC, ACM, output selection, DASR, and final clipping. Blended mode does not directly apply the donor upper. E-001 remains authoritative: DTSC OFF retains MPC default `p[0:2]`, while DTSC ON intersects its constraints with the personality-limited base upper. APM remains independent `LongitudinalPersonality`; PORT-01 `p[4]`, PORT-02 `p[2]`, and Stock Long ownership are preserved.

PORT-03 excludes Toyota physical drive-mode selection, `ToyotaDriveMode`, `CarState.accelProfile`, B custom cereal and telemetry, the whole `AccelController`, its MPC instance synchronization, B minimum-acceleration/lower-envelope activation, F-005 jerk/weight/response and slew tuning, B `COMFORT_BRAKE = 1.75`, C `braking_offset`, and Toyota/SecOC/Panda or generated-solver changes.

Production scope is limited to `selfdrive/controls/lib/accel_personality.py` and `selfdrive/controls/lib/longitudinal_planner.py`. Deterministic coverage is in `selfdrive/controls/tests/test_accel_personality.py` and `selfdrive/controls/tests/test_accel_personality_planner.py`. The checkpoint changed 4 files with 532 insertions and 2 deletions.

Verification:

- PORT-03 helper: 173 passed
- PORT-03 planner integration: 47 passed
- E-001 targeted: 4 passed
- E-002 targeted: 2 passed
- PORT-01 targeted: 82 passed
- PORT-02 targeted: 45 passed
- Targeted subtotal: 353 passed
- Existing longitudinal: 4 passed / 58 subtests
- Combined: 357 passed / 58 subtests
- Existing longitudinal `SQP_RTI` status 3 diagnostic count: 42, matching baseline
- SCons: PASS, exit 0, 40.20 seconds
- Ruff: no new lint regression; `longitudinal_planner.py:49 PIE790` is `PRE_EXISTING_BASELINE_LINT`
- `git diff --check`: PASS
- Focused native evidence: native and solution status 0; params/v/a/j finite; reset count 0

Limits: deterministic, solver-facing, regression, lint, and build verification passed. C3X bench, vehicle, deployment, and release validation remain outstanding.

### CFG-01 — Versioned config lifecycle

- Closure result: `CFG01_CLOSURE: READY_CFG01`
- Implementation commit: `5951b7f9392cae5284c5e09effdd4bdcd120b171`
- Message: `feat(config): add HANK longitudinal session config`
- Implementation result: `CFG01_IMPLEMENTATION_PASS`
- V1 scope: selection-only Dynamic Follow enable and acceleration-profile selection
- Snapshot owner: `plannerd`, after CarParams and before planner construction
- Apply policy: next onroad session only

The implemented schema is an exact version 1 JSON object with `dynamic_follow` boolean and `accel_profile` integer 0 through 3. `HankConfigRequested` is persistent; `HankConfigActive` and the `HankConfigSessionStarted` latch clear on offroad transition or ignition on. All three keys have no registry default. The adapter rejects missing or unknown fields, duplicate keys, wrong types, unsupported versions, invalid JSON, non-standard JSON numeric values, and out-of-range profiles.

`plannerd` snapshots after valid CarParams and before planner construction. Initialization writes and verifies the latch first, then writes, reads back, and validates the complete Active bundle. A valid Active/latch pair is reused across standalone planner restarts; Requested changes apply only after the session state is cleared and the next valid session starts. Missing, corrupt, and I/O-error states remain distinct. Corrupt Requested uses an explicit stock recovery without overwriting the corrupt value; corrupt or inconsistent Active/latch state rejects initialization.

Legacy `HankDynamicFollow` is migrated only when the new Requested key truly does not exist, using Dynamic Follow false/true and stock acceleration. When new Active and latch are both missing, initialization is allowed only if legacy `HankDynamicFollowActive` is also truly missing. Any existing legacy Active raw value, including `"0"`, `"1"`, or malformed content, rejects same-session initialization; a legacy Active I/O failure fails initialization. A valid new Active/latch pair remains authoritative regardless of legacy Active.

Stock Long retains the snapshot while existing `CP.openpilotLongitudinalControl` guards bypass effective Dynamic Follow and Acceleration Personality behavior. APM and the gap button remain independent. Four PORT-01 lifecycle cases now assert the Requested/Active/SessionStarted contract; donor numerical curves, speed behavior, pitch/downhill handling, `p[4]`, APM, solver behavior, and ON/OFF oracle are unchanged.

Verification:

- CFG adapter: 108 passed
- CFG plannerd integration: 18 passed
- Dynamic Follow: 82 passed
- Acceleration Personality helper/planner: 173 / 47 passed
- E-001 / E-002 / PORT-02: 4 / 2 / 45 passed
- Final combined: 483 passed / 58 subtests
- Existing longitudinal: 4 passed / 58 subtests
- Existing longitudinal `SQP_RTI` status 3 diagnostic count: 42, matching baseline
- SCons: PASS, exit 0, 39.86 seconds; only known CasADi 3.7.2 compatibility warnings
- Ruff and `git diff --check`: PASS
- Native Params: actual keys verified with types JSON / JSON / BOOL, flags 2 / 144 / 144, no defaults, write/read/remove PASS, and BOOL raw `"1"` PASS

The checkpoint changed 6 files with 879 insertions and 12 deletions. Exact HANK three-mode mapping, UI, numerical field externalization, follow/stop-distance tuning, F-005, disengaged live apply, and DP-toggle bundling remain deferred.

### F-002 — Stop Distance from TOP01003

- Closure checkpoint: `14a6d7049ce155b3f86706c79dab5c1fca28e0dc`
- Closure message: `docs(hank): freeze TOP01003 stop distance donor`
- Closure result: `F002_CLOSURE: READY_F002`
- Implementation checkpoint: `d2eb41426aa3e299f37ae8ffdc73f1c563015a95`
- Implementation message: `feat(longitudinal): port TOP01003 stop distance`
- Implementation result: `F002_IMPLEMENTATION_PASS`
- Implementation scope: `selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py`, `selfdrive/controls/tests/test_accel_personality_planner.py`, `selfdrive/controls/tests/test_dynamic_follow.py`, `selfdrive/controls/tests/test_pull_away.py`, `selfdrive/controls/tests/test_stop_distance.py`, and `selfdrive/test/longitudinal_maneuvers/test_longitudinal.py`
- Canonical donor: B / `CT921/openpilot`, branch `TOP01003`
- Donor commit: `615799f95e978fbf643d1e762d605b4d5b06499f`

The implementation increases `PARAM_DIM` from 6 to 7 and appends personality-selected `stop_distance` at `p[6]`. Existing positions remain unchanged: `p[0]` a_min, `p[1]` a_max, `p[2]` x_obstacle, `p[3]` prev_a, `p[4]` lead_t_follow, and `p[5]` lead_danger_factor. Unsupported personalities raise `NotImplementedError`.

The exact implemented presets are Relaxed 4.5, Standard 4.0, and Aggressive 4.0. HANK preserves `COMFORT_BRAKE = 2.5`; B's 1.75 value, ToyotaTune, SMART_DSU, the ToyotaTune `+0.5 m` correction, B pull-away behavior, C braking offset, and F-005 jerk tuning were not imported.

One effective stop distance is selected each frame from the effective `LongitudinalPersonality`. The same value reaches solver `p[6]` at all horizon rows, the ACC cruise obstacle, symbolic cost and distance constraint, and blended lead-comfort/source checks. Dynamic Follow remains independent at `p[4]`; Acceleration Personality continues to control acceleration bounds only. The PORT-02 stopped-equivalence transform is unchanged.

CFG-01 v1 remains exactly `{version, dynamic_follow, accel_profile}`: no stop-distance field, schema-version change, or live CFG polling was added. F-002 consumes the existing effective personality path used by APM and the gap button. With `CP.openpilotLongitudinalControl == False`, Toyota TSS retains actuator authority; F-002 calculation creates no longitudinal control authority.

The final HANK model was regenerated through the repository SCons dependency. Generated artifacts remain ignored and were not committed. Verified dimensions are Python `PARAM_DIM = 7`, CasADi `model.p = 7`, acados JSON `np = 7`, generated `LONG_NP = 7`, generated `casadi_np = 7`, and runtime `params.shape = (13, 7)`. Native seven-value parameter vectors were accepted at every required stage with status 0, explicit reset PASS, and finite params/v/a/j.

Verification:

- F-002 focused: 13 passed
- E-001 / E-002: 4 / 2 passed
- PORT-01 / PORT-02: 82 / 45 passed
- PORT-03 helper / planner: 173 / 47 passed
- CFG adapter / plannerd: 108 / 18 passed
- Combined targeted regression: 492 passed
- Existing longitudinal: 4 passed / 58 subtests
- Existing longitudinal `SQP_RTI` status 3 diagnostic count: 42, matching the pre-F-002 baseline
- Final SCons: PASS, exit 0, 39.78 seconds
- Ruff and `git diff --check`: PASS

The initial full longitudinal run exposed one `resume from a stop` failure. Diagnosis classified it as `STALE_TEST_FIXTURE`: the fixture still started at legacy `STOP_DISTANCE = 6.0`, while its implicit personality was aggressive (numeric 0) and runtime correctly supplied `p[6] = 4.0`. The same seven-parameter solver failed only with fixture 6.0 / target 4.0, passed with forced target 6.0 / fixture 6.0, and passed with matching aggressive 4.0 / 4.0. Matching Relaxed 4.5, Standard 4.0, and Aggressive 4.0 fixtures all passed with solver status 0. This excluded the seven-parameter structure, regeneration, and `p[6]` mechanism as the cause.

The corrected maneuver explicitly selects `log.LongitudinalPersonality.aggressive` and derives `initial_distance_lead` from `get_STOP_DISTANCE(log.LongitudinalPersonality.aggressive)`, yielding 4.0. `ensure_start = True`, the `1e-3` acceleration threshold, duration, lead-speed timeline, breakpoints, e2e matrix, and force-decel matrix remain unchanged. Corrected evidence is 1 passed / 15 subtests targeted and 4 passed / 58 subtests full longitudinal; no test threshold was weakened.

The implementation checkpoint changed six files with 234 insertions and 22 deletions. It is independently revertible without reverting E-001, E-002, PORT-01, PORT-02, PORT-03, or CFG-01. Reverting it removes the seven-parameter F-002 source, tests, and resume fixture adaptation; ignored long-MPC artifacts must then be regenerated for the restored six-parameter model.

The user target of an approximately 1–2 m physical stopped gap remains unmapped. Raw 1.0/1.5/2.0 inputs are deterministic coordinate-space test cases only and are not physical bumper-gap claims. Physical mapping requires C3X stationary-vehicle measurement and later validation.

## Current blockers and limitations

- F-003 / D-008 Lead Pull-away from C/TOP096 is implemented at the PORT-02 checkpoint; C3X and vehicle validation remain outstanding.
- F-004 / D-009 Acceleration Personality and CFG-01 externalization are implemented; C3X and vehicle validation remain outstanding.
- F-002 Stop Distance is implemented and deterministic/native/build verification passed; physical stopped-gap mapping, C3X, and vehicle validation remain outstanding.
- F-005 low-speed jerk / acceleration-response donor and numerical closure remains unresolved.
- Future HANK three-mode mapping, profile UI, and HANK/TSS quick-selector UI remain unresolved.
- C3X bench validation has not been completed.
- Vehicle V0 through V3 validation has not been completed.
- Full P0 SecOC/Toyota release acceptance has not been completed.
- Phase 1 is not complete; vehicle safety, deployment approval, main merge, and release acceptance are not established.

The former ENV-001 blocker is closed: the WSL environment has executed setup, native builds, lint, targeted tests, and longitudinal regression.

## NEXT

`F005_CLOSURE` — freeze the Low-speed jerk / acceleration-response donor behavior and numerical/solver dependency boundary before implementation. The closure must distinguish acceleration response, jerk cost, previous-acceleration cost, PORT-02 lead pull-away behavior, PORT-03 Acceleration Personality, F-002 Stop Distance, the `COMFORT_BRAKE` decision, low-speed start response, and ACC versus blended behavior. Do not implement F-005 during closure.

## Commit map and rollback

| Logical unit | Commit | Rollback boundary |
|---|---|---|
| Historical IMPL-00 audit | `e288751973408718a51930dc544593306f2835d8` | Documentation-only historical checkpoint |
| Continuation prerequisite | `95bd593f1d36efffe72a4264b45d9ce7e65c928e` | State recovery before executable work |
| E-001 | `017d2b17798670f0147a7f633197b0eebf9776f5` | Revert E-001 checkpoint independently |
| E-002 | `0940bc5399a1b3533375a6b58aba827c17a1cd7d` | Revert E-002 checkpoint independently |
| PORT-01 | `4c7dd35fce64a7c06253e497cc2afd52d7e0f1d5` | Revert PORT-01 checkpoint independently |
| PORT-02 donor closure | `8935e606abf1629c16260911fe75c7c4d1cd9a6c` | Documentation-only frozen donor boundary |
| PORT-02 | `772a786f55b8c195ffd20f038c7757569590db0d` | Revert PORT-02 checkpoint independently |
| PORT-03 donor closure | `a2486cd4c6575003c6c804240353d249d9a91e27` | Documentation-only frozen donor boundary |
| PORT-03 | `dab63d6ea1dcbc23db11ced15c6b08036404bafa` | Revert PORT-03 checkpoint independently |
| CFG-01 closure | `d082d743a6a7d3273246f60fad0a3830a6f2b3aa` | Documentation-only frozen config boundary |
| CFG-01 | `5951b7f9392cae5284c5e09effdd4bdcd120b171` | Revert CFG-01 checkpoint independently |
| F-002 donor closure | `14a6d7049ce155b3f86706c79dab5c1fca28e0dc` | Documentation-only frozen donor/numerical boundary |
| F-002 | `d2eb41426aa3e299f37ae8ffdc73f1c563015a95` | Revert F-002 source/tests independently, then regenerate the restored six-parameter ignored solver artifacts |

Architecture authority remains `HANK_INTEGRATION_SPEC.md`, `HANK_DECISION_LOG.md`, and `HANK_TEST_MATRIX.md`. This file records execution status and does not supersede D-001 through D-020.
