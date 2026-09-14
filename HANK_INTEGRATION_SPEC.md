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

### F-006 — HANK three user modes

- **Source:** HANK-owned configuration layer
- **Modes:** `緊湊 / 一般 / 舒適`
- **Strategy:** Configure donor algorithms; do **not** replace donor algorithms
- **Requirements:** every exposed value has type, unit, min/max, default, validation and donor-original preset
- **Apply policy:** validate -> save -> apply at safe state/profile transition/engagement boundary; safety-relevant values must not change arbitrarily every control cycle
- **Status:** Approved

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

### F-011 — Fast HANK <-> TSS mode switching

- **UI:** HANK may add an on-road camera-screen quick control for desired longitudinal owner (`HANK` / `TSS`).
- **No hot switch while engaged.**
- User must take control and disengage openpilot/ACC first.
- Required preconditions should include at least `selfdriveState.enabled=false`; implementation should additionally verify no active lateral/longitudinal command state before cycling.
- Save `dp_toyota_stock_lon`, then request an A-supported onroad cycle using `OnroadCycleRequested`.
- The cycle forces a short Offroad -> Onroad lifecycle so `card`, `CarParams`, Toyota interface and Panda safety are rebuilt without a full C3X OS reboot.
- Full reboot is fallback only if clean cycle recovery fails.
- First vehicle validation must be done stationary in a safe environment.

- **Status:** Approved architecture, real-car validation mandatory

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
