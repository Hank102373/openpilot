# FIX-UI-02 source and runtime evidence / schema review

2026-11-10; base `06dc39a512eb08581d0a8b60548b6538bb6de819`, WSL Ubuntu-24.04, branch `hank/implementation-v1`, clean precheck. Local origin tracking and immutable RC1 branch/peeled tag remain `b35a4c1bdbe83468690935cf08d6c3e8d0174855` (no remote refresh claimed this round).

## Runtime proof

Read-only [baseline_probe.py](baseline_probe.py) constructs real LongitudinalPlanner and native LongitudinalMpc. Forwarding spies capture set_weights/update personality while still calling native code. It calls real planner.publish and serializes the Cereal Event. The display expression is extracted by AST from the actual HUD source, not copied/reimplemented. Native Params are isolated in TemporaryDirectory; synthetic inputs come from the existing deterministic fixture, with optional MAA helper disabled for isolation.

Executed from repo root with `.venv` activated:

```sh
PYTHONDONTWRITEBYTECODE=1 python /tmp/fix-ui-02/probe.py
```

After binding the forwarding spies to their per-planner values (Ruff B023), reran the checked-in command `PYTHONDONTWRITEBYTECODE=1 python docs/hank/evidence/2026-11-10/fix-ui-02-review/baseline_probe.py` with the identical 6-mismatch result. `ruff check --no-cache docs/hank/evidence/2026-11-10/fix-ui-02-review/baseline_probe.py` and `git diff --check` both exit 0. Exit **1, expected**: `AssertionError: FIX-UI-02: actual HUD misses 6 real planner effective overrides`. [Raw output](baseline.log). All 18 frames have solution_status 0 and identical effective personality passed to set_weights/update; Requested/Active bytes unchanged. This is diagnostic evidence, not a failing regression test committed into the test suite.

| Profile | APM sequence | Native effective | HUD override | Contract |
|---|---|---|---|---|
| Normal | 0 m/s, then exact 30 and 40 km/h thresholds | Aggressive (0) | false | Must be true: 3 mismatches |
| Comfortable | same | Aggressive (0) | false | Must be true: 3 mismatches |
| Normal/Comfortable | initially exactly 30 km/h; above 40 km/h; APM OFF | Base | false | Consistent |
| Compact | all six cases | Aggressive = base | false | Consistent |

No vehicle effect claim; native status zero is not vehicle acceptance. This probe does not yet cover Stock Long, process restart, wire validity/freshness or rendered UI; those are implementation gates.

## Source review

- `dragonpilot/selfdrive/controls/lib/apm.py`: strict below-30-km/h activation, strict above-40-km/h deactivation; hysteresis held in planner-local APM instance. UI cannot infer state from current speed.
- `selfdrive/controls/lib/longitudinal_planner.py`: reads selfdriveState.personality, optionally computes APM override, passes local result to both MPC calls. publish omits effective/base/APM metadata.
- `selfdrive/selfdrived/selfdrived.py` and D-023: selfdriveState personality is Active base. Changing it to effective would corrupt the ownership contract.
- `cereal/log.capnp`: LongitudinalPlan uses ordinals 0..39, including deprecated slots; personalityDEPRECATED @36 is not populated and lacks presence/version semantics. No usable existing effective-personality field found.
- `cereal/custom.capnp`: ControlsStateExt contains ALKA only and is owned by controlsd. Adding a second publisher is inappropriate; a new custom topic would add a service and subscription unnecessarily.
- `selfdrive/ui/onroad/hud_renderer.py`: compares published base with Active base; subscribed longitudinalPlan already exists.

## Proposed interface for approval (D-026 pending, NOT accepted)

Add exactly one non-deprecated pointer field to existing `LongitudinalPlan`:

```capnp
hankPersonality @40 :HankPersonalityState;

struct HankPersonalityState {
  version @0 :UInt8;  # producer sets 1; absent/default 0 means unavailable
  base @1 :LongitudinalPersonality;
  effective @2 :LongitudinalPersonality;
  apmEnabled @3 :Bool;
  applies @4 :Bool;  # CP.openpilotLongitudinalControl
  selfdriveStateMonoTime @5 :UInt64;
}
```

@40 is available at the reviewed base. Recheck before editing; never renumber/reuse existing fields. Nested struct name is local to LongitudinalPlan. Existing enum values remain unchanged. Presence/version is mandatory because enum default zero is Aggressive and cannot imply valid observation.

Producer: LongitudinalPlanner is sole writer. Capture the exact pre-APM base and exact post-APM effective used by the same update's MPC calls, plus flags/input timestamp. Publish only a completed update's snapshot, version 1. No second APM call, new threshold, history replay, control input replacement or Params write. For Stock Long, applies=false; metadata must not suggest HANK actuates TSS. Preserve current control execution even if a dormant planner still computes APM internally.

Consumer: shared UI presentation helper reads existing longitudinalPlan. Require seen, Event.valid, supported version, valid known enum values, `applies=true`, current verified HANK ownership, and a valid current Active/latch. Require plan timestamp, modelMonoTime and selfdriveStateMonoTime > 0, not future, within **0.5 seconds** of monotonic now and after current onroad UI epoch. If Active is v2, telemetry.base must equal Active base; v1 remains Legacy, base comes from telemetry without inferred migration. Missing/old/new-unknown schema, stale/invalid/contradictory/current-session-missing data produce **APM status unavailable**, never guessed OFF. Under TSS show stored HANK/inactive, no effective override claim. `apmEnabled && effective != base` shows override; Compact with active APM but unchanged effective shows no override. APM OFF requires base==effective; reject contradictions.

Same-session planner restart reuses CFG Active; new planner recomputes its own APM state through existing algorithm and publishes fresh completed-update metadata. No UI cache of override across invalid/stale/offroad observations. There is no claim of instant crash detection before the 0.5-second freshness deadline. New onroad epoch rejects prior-session messages. No new session or restart authority is introduced.

Compatibility: old readers ignore additive field; new readers reject absent/version=0 metadata. Old logs/software remain readable but show unavailable, not false Aggressive. Native Cereal regeneration/build is required through existing SCons, not manual generated-file edits. This is display-only telemetry, not a control command or a schema replacement. No solver regeneration intended; report actual SCons artifacts if build rules regenerate unrelated targets.

Rejected alternatives: deprecated @36 has ambiguous old/default semantics; selfdriveState must remain base; velocity/params inference duplicates APM hysteresis; Params polling loses per-frame freshness/session binding; another publisher on controlsStateExt violates its ownership; a new custom service duplicates existing plan transport. A lone override Bool cannot distinguish absent/default false or prove MPC effective equality.

## Implementation/test contract after approval

1. Add formal test-first regression over true planner/native MPC, capture published Cereal and consume through UI helper; prove baseline FAIL before changing producer/UI. No mock-only comparison test.
2. Normal/Comfortable override; exact activate/deactivate thresholds and in-band history; APM OFF; Compact same-effective; original and v1; Stock Long; ACC/blended; same-session restart and next session. Assert Requested/Active unchanged and same effective values reach weights/update and telemetry.
3. Old/missing/version-zero/unknown version, invalid enum, false Event.valid, stale/future timestamps, old session, active/base mismatch, contradictory OFF, missing authority; all unavailable/inactive with no stale override.
4. Existing owner/CFG/profile and relevant native longitudinal regression. Compare solver-facing p/W/yref and native output before/after across identical inputs to establish display-only change; no tolerance widening. Targeted lint with known baseline PIE790 classified, Cereal/SCons build and diff check.
5. Actual desktop HUD render of override, cleared, unavailable, Stock Long and pending Requested. Preserve FIX-UI-01 disabled/recovery/confirmation behavior; retain language/font limitation until separately verified.
6. Complete handoff/local implementation checkpoint only when gates pass; VERIFY-RC-02 remains separate. No publication/device action.

## Current outcome

FIX_UI_02_STATE = DECISION_REQUIRED (schema approval). No production/test/schema modification, build, commit of failing tests, push, device work or RC ref movement. This checkpoint contains evidence and a pending decision only. User must accept or revise the additive interface before source implementation; no historical decision is silently superseded. After approval resume from this review, not from FIX-UI-01 or old PORT units.
