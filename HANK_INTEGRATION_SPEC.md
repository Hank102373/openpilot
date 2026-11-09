# HANK Integration Specification

**Document:** HANK_INTEGRATION_SPEC.md  
**Version:** v1.0  
**Date:** 2026-09-14  
**Target vehicle:** 2022 Toyota Sienna Hybrid  
**Target hardware:** comma 3X (C3X)  
**Status:** Architecture baseline / implementation authority

---

## 1. Purpose

HANK is a selective integration project based on dragonpilot A. It is **not** a git merge of A/B/C and it is **not** a new longitudinal-control stack designed from scratch.

The implementation objective is:

1. Keep A/dragonpilot as the platform and Toyota/SecOC foundation.
2. Preserve A/DP functions unless a documented decision explicitly replaces one.
3. Port only the desired TOP behavior from B/C.
4. Keep Toyota CAN, SecOC/TSK, Panda safety and vehicle-interface behavior inside the A trust boundary.
5. Make every deviation traceable to a source, decision, test and rollback path.

---

## 2. Source anchors

| ID | Source | Branch | Commit | Role |
|---|---|---|---|---|
| A | dragonpilot/dragonpilot | `0.10.3-pre-build` | `1986516b325cbf8d173f6ebaea989ed45673c49f` | **Baseline / platform authority** |
| B | CT921/openpilot | `TOP01003` | `615799f95e978fbf643d1e762d605b4d5b06499f` | Primary donor for selected longitudinal behavior |
| C | CT921/openpilot | `TOP096` | `3d75e471c74fccf0067dcda8cfe1374cf1268215` | Secondary donor for selected older TOP behavior |

HANK repository baseline:

- Repository: `Hank102373/dp-sienna-0103`
- `main` must remain traceable to A baseline until an integration change is intentionally merged.
- Prototype branch `sienna-longitudinal-dev` / commit `c4d50cfdb213264fe26ac96c522a33597b6bbe36` is **research only**. Its invented `launch_trigger/gain/offset_max` abstraction is not production authority.

---

## 3. Integration strategy vocabulary

### Preserve
Keep the A implementation and behavior unchanged except for minimal compatibility plumbing.

### Port
Move the donor logic with minimal semantic change. Source behavior remains the authority.

### Behavior-preserving rewrite
Re-express a donor algorithm inside A APIs/data structures without changing its intended behavior. This is used when direct file replacement would import incompatible dependencies.

### Adapter
Thin HANK-owned glue between A and a donor algorithm. An adapter must not become a new control algorithm.

### Reject
Do not import the donor subsystem/dependency.

### HANK-owned
Configuration, validation, mode selection and UI may be implemented by HANK when they do not replace the control algorithm itself.

---

## 4. Global architecture rule

**HANK = A/DP plus selected donor behavior. TOP does not replace DP.**

High-level flow:

```text
HANK UI / profile parameters
        |
        v
A LongitudinalPlanner orchestration
  |-- AEM   (A)
  |-- DTSC  (A)
  |-- APM   (A)
  |-- selected TOP follow/stop/pull-away/accel behavior
  |-- ACM   (A)
  |-- DASR  (A)
        |
        v
A LongControl
        |
======== P0 TOYOTA / SECOC TRUST BOUNDARY ========
        |
A Toyota CarController
A SecOC freshness/counters/AES-CMAC + user TSK
A Toyota Panda safety
A Toyota CAN packing / transmission
        |
        v
2022 Toyota Sienna Hybrid
```

TOP code must not cross the P0 trust boundary unless a later decision explicitly documents the exact dependency, reason and tests.

---

## 5. Feature integration matrix

### F-001 — Dynamic Follow

- **Source:** B / TOP01003
- **Strategy:** Behavior-preserving rewrite / port into A longitudinal MPC architecture
- **Keep from A:** planner orchestration, CarParams contract, longcontrol, Toyota interface/controller, SecOC, safety
- **Adopt from B:** dynamic-follow curve/logic and personality-dependent following behavior
- **Do not import:** B Toyota interface, B Toyota CarState/CarController, B custom cereal schema, B Panda safety as wholesale replacements
- **HANK additions:** external validated profile values may override whitelisted constants; donor preset must remain selectable
- **Status:** Approved architecture; exact field-level port closure required before implementation merge

### F-002 — Stop Distance

- **Source:** B / TOP01003
- **Strategy:** Port/adapt B stop-distance parameterization into A-compatible MPC
- **Keep from A:** stop/start state handling and Toyota actuator stack
- **Adopt from B:** personality-aware `stop_distance` handling where dependency closure confirms equivalence
- **Important:** B `COMFORT_BRAKE=1.75` must **not** be silently imported as a side effect of stop-distance work. Comfort-brake behavior is a separate reviewed decision.
- **Status:** Approved architecture; numerical constants require final freeze

### F-003 — Lead Pull-away

- **Source:** C / TOP096 is the current preferred donor; B remains comparison reference
- **Strategy:** Port only the stopped-equivalence/pull-away behavior, not the C planner or C LongControl
- **Keep from A:** current-generation A control state, planner framework, actuator path
- **Reject:** C whole-module `longcontrol.py`, old planner architecture and unrelated speed-control stack
- **Status:** **Provisional donor decision** until final field-level matrix confirms C behavior is the intended real-world feel

### F-004 — Acceleration Personality

- **Source:** B / TOP01003
- **Strategy:** Port B `accel_personality` algorithm and thin dependencies into A planner/MPC path
- **Keep from A:** Toyota CarController acceleration actuation and safety limits
- **Preferred input path:** HANK Params/profile -> donor acceleration personality
- **Reject:** Toyota physical drive-mode -> custom cereal `accelProfile` dependency unless later proven necessary
- **Status:** Approved architecture

### F-005 — Low-speed jerk / acceleration response

- **Source:** B as primary comparison; C only as historical/aggressiveness reference
- **Strategy:** Selective port after solver/field dependency review
- **Rule:** No blended B+C+new-HANK formula without explicit decision and regression data
- **Status:** Pending final numerical/solver decision

### F-006 — HANK three user modes / UI-01

- **Source/authority:** HANK-owned versioned CFG, D-010 and accepted D-023.
- **Primary mode names and exact mapping:** `緊湊 = Aggressive + sport(0)`; `一般 = Standard + normal(1)`; `舒適 = Relaxed + eco(2)`. These select existing donor inputs, not new MPC formulas.
- **Dynamic Follow:** independent Requested boolean; mode changes preserve it. Existing personality curves, Stop Distance and F-005 use the planner's APM-effective personality. APM does not edit the selected mode or acceleration profile.
- **Original/default restore:** a separate advanced action selects internal `original` (base Standard, acceleration stock(3), Dynamic Follow false); it is not a fourth main HANK mode. D-022 gain/cap remain separate C3X bench calibration, not mode values. Real-time `+/-` is `POST_RC_TUNING`.
- **Apply boundary:** validated whole v2 Requested save is allowed while engaged; Active and behavior change only on the next legitimate onroad session. Same-session planner restart reuses Active. Ordinary profile edits never request a Toyota/Onroad cycle. UI distinguishes Requested, Active and pending.
- **Gap button:** under HANK ownership cycles Requested `緊湊 → 一般 → 舒適 → 緊湊`, never live `LongitudinalPersonality`. Under TSS it does not edit HANK active behavior. Existing personality settings must share this ownership rather than bypass it.
- **Schema/legacy:** D-023 defines exact v2 JSON and strict compatibility for v1; no inferred migration of v1 personality.
- **Status:** Accepted for implementation only; UI/runtime/bench/vehicle gates remain open.

### F-007 — DP longitudinal feature set

The following A/DP functions are **preserved**:

- ACM（Adaptive Coasting Mode，自適應滑行模式）
- AEM（Adaptive Experimental Mode，自適應實驗模式）
- DTSC（Dynamic Turn Speed Control，動態彎道速度控制）
- APM（Adaptive Personality Mode，自適應跟車性格）
- DASR（Dynamic Accel Slew Rate，動態加速度變化率）

**Integration rule:** retain A `LongitudinalPlanner` orchestration so these modules keep their existing insertion points around MPC behavior.

Special note for APM: HANK personality mapping should remain compatible with `Aggressive / Standard / Relaxed`; low-speed automatic aggressive behavior must be tested together with TOP dynamic follow/stop/pull-away parameters.

- **Status:** Must-preserve / regression-gated

### F-008 — DP lateral and UI/device functions

Phase 1 does not replace A lateral control. Preserve existing DP functions including ALKA, lane-change settings, road-edge detection, position offset, UI/device settings, external radar support and MAA integration unless a later decision explicitly changes them.

- **TOP lateral changes:** rejected for Phase 1 because no required dependency crossing has been established.
- **Status:** Must-preserve

### F-009 — Toyota-specific DP functions

Preserve A Toyota-specific behavior including:

- `dp_toyota_door_auto_lock_unlock`
- `dp_toyota_tss1_sng`
- `dp_toyota_stock_lon`
- A Toyota platform detection/flags
- A Toyota actuator/controller behavior
- A SecOC/TSK path

The exact applicability of TSS1 SnG to the 2022 Sienna is separate from preserving the feature in the codebase.

- **Status:** Must-preserve

### F-010 — Toyota Stock Long / HANK lateral mode

When `dp_toyota_stock_lon=ON`:

- `openpilotLongitudinalControl=False`
- Toyota factory TSS ACC owns gas/brake longitudinal control
- HANK/DP may continue lateral control according to existing DP behavior
- HANK/TOP longitudinal algorithms are bypassed
- Toyota/SecOC lateral authentication remains A-controlled

This is a **hard mode boundary**, not a runtime acceleration selector.

- **Status:** Must-preserve

### F-011 — Safe HANK <-> TSS quick selector / UI-02

- **Owner Param:** `dp_toyota_stock_lon=true` means TSS factory longitudinal owner; `false` means HANK/openpilot longitudinal owner. This is a hard ownership boundary, not a personality control.
- **No engaged hot switch:** require fresh `selfdriveState.enabled=false`, `carControl.enabled/latActive/longActive=false` and factory ACC `carState.cruiseState.enabled=false`. ALKA can keep lateral commands active while selfdrive is disengaged. Missing/stale/contradictory signals block a request.
- **Transaction:** D-024's single coordinator records last confirmed owner, closes an independent selfdrived engagement gate, writes/readbacks the desired Param, issues `OnroadCycleRequested` once, observes Offroad and a new Onroad epoch, then verifies fresh CarParams and Panda safety. Repeated automatic cycles and direct DP-toggle bypasses are prohibited.
- **Success:** only matching new CarParams `openpilotLongitudinalControl`, Toyota `STOCK_LONGITUDINAL` flag, every connected Panda safety model/param/alternative experience, and fresh command state allow the new owner to become confirmed and engagement to reopen. A consumed request bit, stale `CarParamsPersistent`, or Param write alone is insufficient.
- **Failure:** restore the Param to `previous_confirmed_owner`, latch `SWITCH_FAILED`, keep engagement blocked, show an explicit failure, and offer full C3X reboot. The rollback write does not prove runtime rollback. After reboot, require the current Linux kernel boot ID to differ from the atomically recorded D-024 `failure_boot_id`, then verify the restored owner with fresh current-session evidence before enabling engagement. Missing/invalid boot evidence fails closed. Never auto-retry.
- **UI:** camera-view owner indicator/control plus pending, blocked and failure states. TSS view labels HANK modes as stored for future HANK, not active longitudinal behavior. Reuse existing A UI/dialog and lifecycle seams; do not modify Toyota/Panda/SecOC/TSK/authenticated CAN for switching.
- **Status:** Accepted for implementation only under D-024. C3X bench and stationary target-Sienna validation are mandatory before owner-switch acceptance.

---

## 6. P0 SecOC / TSK trust boundary

The following A components are protected unless separately approved:

1. `SecOCKey` Params handling and `/cache/params/SecOCKey`
2. `CP.secOcRequired` / `CP.secOcKeyAvailable`
3. `opendbc/car/secoc.py`
4. Toyota CarState SecOC freshness/reset synchronization
5. Toyota CarController LKA/LTA/ACC counters and signing
6. `ACC_CONTROL_2` packing/authentication
7. Toyota interface SecOC flags
8. Panda Toyota safety/whitelist
9. CAN IDs, frequency, reset semantics and message-counter semantics

The user's extracted 16-byte TSK is treated as runtime secret material and must never be logged or committed.

Regression requirement:

- **HANK feature OFF:** SecOC/CAN behavior must match A baseline equivalently.
- **HANK feature ON:** expected differences should be desired longitudinal trajectory/behavior, not authentication mechanism.
- Panda safety rejection must be distinguishable from SecOC authentication failure.

---

## 7. Explicit dependency exclusions for Phase 1

Do not wholesale import:

- B/C Toyota `interface.py`
- B/C Toyota `carcontroller.py`
- B/C Toyota `carstate.py`
- B/C `toyotacan.py`
- B/C Panda Toyota safety
- B `cereal/custom.capnp` (known semantic/ID collision with A)
- C whole planner / old LongControl stack
- TOP lateral stack
- SmartCruise / SpeedLimit / map stack unless later requested

Any exception requires a new Decision Log entry before implementation.

---

## 8. Solver and generated-code rule

B longitudinal MPC uses a different live-parameter dimension than A. If HANK adopts the B parameter layout, ACADOS generated artifacts must be regenerated from the final HANK MPC model. Generated solver files must never be mixed from a different parameter dimension.

Required validation includes:

- clean solver generation/build
- dimension consistency
- convergence/failure handling
- C3X build/runtime validation

---

## 9. Implementation sequence

Recommended production commit sequence:

1. `PORT-01 Dynamic Follow from TOP01003`
2. `PORT-02 Lead Pull-away from TOP096` — only after donor freeze
3. `PORT-03 Accel Personality from TOP01003`
4. `CFG-01 Externalize validated profile parameters`
5. `UI-01 HANK profile editor`
6. `UI-02 HANK/TSS quick selector with safe onroad cycle`

Each port commit must remain independently testable and revertible.

---

## 10. Acceptance gates

A feature is not accepted merely because it compiles or feels good on one drive. Minimum gates are defined in `HANK_TEST_MATRIX.md`.

No Critical/P0 change may be declared complete without:

- source traceability
- unit/static checks where applicable
- replay or equivalent deterministic comparison where available
- bench/C3X build validation
- controlled stationary vehicle validation
- staged road validation
- verified rollback path

---

## 11. Definition of done for Phase 1

Phase 1 is complete when:

- A remains the identifiable baseline.
- Selected TOP longitudinal behavior is integrated without wholesale Toyota-stack replacement.
- A DP longitudinal modules remain functional.
- A Toyota/TSK/SecOC path remains intact.
- HANK can operate in HANK longitudinal mode and Toyota Stock Long mode.
- HANK/TSS desired mode can be changed through a safe Offroad->Onroad cycle without requiring a full C3X reboot, subject to successful real-car validation.
- HANK feature-off behavior has no unexplained regression from A.
- All Critical test-matrix items required for the release stage pass.


## 12. D-026 — Planner-effective personality display (accepted 2026-11-10)

D-023 still owns Requested/Active/base and APM behavior. D-026 adds display-only `LongitudinalPlan.hankPersonality @40`, nested version UInt8 @0, base/effective LongitudinalPersonality @1/@2, apmEnabled Bool @3, applies Bool @4, selfdriveStateMonoTime UInt64 @5. Existing ordinals/enums/topics are unchanged; no deprecated field is repurposed.

Planner alone publishes version 1 after a completed update, capturing the exact base/effective personality used by MPC weights/update. Clear the snapshot before each new update so an incomplete update cannot republish previous metadata. APM executes once; no control input, CFG authority or algorithm change. `applies` is CP.openpilotLongitudinalControl.

UI requires verified active HANK ownership, valid Active/latch, seen/valid plan, supported version, known enums, applies, and positive nonfuture plan/model/selfdriveState timestamps no older than 0.5 seconds and not before the current onroad UI epoch. For v2, base must match Active; v1 remains Legacy. Missing/old/version-zero/unknown/corrupt/stale/old-session/contradictory OFF observations show unavailable, not an inferred OFF or Aggressive default. TSS shows APM inactive. Valid enabled different-effective shows the planner's effective enum; equal-effective shows no override. No UI hysteresis calculation or cached override.

Same-session restart reuses Active but freshly computes APM through the existing planner. Requested edits remain pending and independent. FIX-UI-01 request-time coordinator authority and reboot failure recovery remain unchanged. Desktop evidence is scoped to the actual rendered HUD, synthetic topics and isolated Params; it does not establish C3X, localization or vehicle acceptance. See [implementation evidence](docs/hank/evidence/2026-11-10/fix-ui-02/README.md).
