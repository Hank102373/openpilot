# HANK current implementation state

Updated: 2026-09-15. Scope: durable implementation and verification state through PORT-01 and the PORT-02 donor closure. This is not a release or vehicle-validation approval.

## Repository state

- Repository: `Hank102373/dp-sienna-0103`
- Branch: `hank/implementation-v1`
- Current implementation checkpoint: `4c7dd35fce64a7c06253e497cc2afd52d7e0f1d5`
- Remote state at synchronization start: `origin/hank/implementation-v1` matched `4c7dd35fce64a7c06253e497cc2afd52d7e0f1d5`.
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

### PORT-02 closure — Lead Pull-away donor freeze

- Result: `PORT02_CLOSURE: READY_C`
- Canonical donor: C / `CT921/openpilot`, branch `TOP096`
- Donor commit: `3d75e471c74fccf0067dcda8cfe1374cf1268215`
- Donor file: `selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py`
- Frozen function: `get_stopped_equivalence_factor(v_lead, v_ego)`

The frozen C behavior uses a strict horizon-wide `np.all(v_lead - v_ego > 0)` trigger, offset gain 2, pre-taper cap 12 m, taper endpoint 26 km/h, and `COMFORT_BRAKE = 2.5` m/s². It uses MPC `self.x0[1]` for `v_ego`, applies independently to leadOne and leadTwo before obstacle/source selection, and applies the same transform to missing synthetic leads. The donor behavior has no added epsilon, stage-wise replacement, counter, hysteresis, or persistent state. Its horizon-wide discontinuity is intentional and frozen.

The selected transform can preserve current HANK `STOP_DISTANCE`, `COMFORT_BRAKE = 2.5`, `PARAM_DIM = 6`, PORT-01 Dynamic Follow, E-001 `accel_bounds`, and E-002 mode synchronization. PORT-02 excludes donor stop-distance values and personality, `PARAM_DIM = 7`/`p[6]`, B `COMFORT_BRAKE = 1.75`, C `braking_offset`, C low-speed weight/jerk tuning, F-005 response tuning, donor Dynamic Follow and static `T_FOLLOW`, AccelController, donor planner/LongControl, Toyota interface/CarState/CarController, Panda, SecOC, cereal schema replacement, and radar implementation replacement.

No PORT-02 production implementation has occurred. Source and deterministic closure is complete; native solver, C3X, vehicle, and deployment validation remain outstanding.

## Current blockers and limitations

- F-003 / D-008 Lead Pull-away donor selection is frozen as C/TOP096; PORT-02 implementation has not started.
- F-005 low-speed jerk / acceleration-response numerical decision remains unresolved.
- C3X bench validation has not been completed.
- Vehicle V0 through V3 validation has not been completed.
- Full P0 SecOC/Toyota release acceptance has not been completed.
- Phase 1 is not complete; vehicle safety, deployment approval, main merge, and release acceptance are not established.

The former ENV-001 blocker is closed: the WSL environment has executed setup, native builds, lint, targeted tests, and longitudinal regression.

## NEXT

`PORT02_IMPLEMENTATION` — implement the frozen C/TOP096 stopped-equivalence/pull-away transform within the current HANK MPC boundary, with deterministic regression tests and without importing the explicit exclusions recorded in D-008.

## Commit map and rollback

| Logical unit | Commit | Rollback boundary |
|---|---|---|
| Historical IMPL-00 audit | `e288751973408718a51930dc544593306f2835d8` | Documentation-only historical checkpoint |
| Continuation prerequisite | `95bd593f1d36efffe72a4264b45d9ce7e65c928e` | State recovery before executable work |
| E-001 | `017d2b17798670f0147a7f633197b0eebf9776f5` | Revert E-001 checkpoint independently |
| E-002 | `0940bc5399a1b3533375a6b58aba827c17a1cd7d` | Revert E-002 checkpoint independently |
| PORT-01 | `4c7dd35fce64a7c06253e497cc2afd52d7e0f1d5` | Revert PORT-01 checkpoint independently |

Architecture authority remains `HANK_INTEGRATION_SPEC.md`, `HANK_DECISION_LOG.md`, and `HANK_TEST_MATRIX.md`. This file records execution status and does not supersede D-001 through D-018.
