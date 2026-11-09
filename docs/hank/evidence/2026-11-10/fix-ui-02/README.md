# FIX-UI-02 — actual APM effective personality display

2026-11-10. Base `b4980601b8cdbce109b5f8b46cf3d0200670d4bc`, WSL Ubuntu-24.04 `/home/hank/src/dp-sienna-0103`, branch `hank/implementation-v1`, clean initial precheck. User explicitly approved the pending D-026 schema and continuation. Local origin tracking, RC1 branch and peeled RC1 tag remain `b35a4c1bdbe83468690935cf08d6c3e8d0174855`. No remote refresh, publication, device connection or RC ref movement claimed/performed.

## Contract and scope

Runtime files: `cereal/log.capnp`, `selfdrive/controls/lib/longitudinal_planner.py`, `selfdrive/ui/hank_profile.py`, `selfdrive/ui/onroad/hud_renderer.py`. One formal test file: `selfdrive/ui/tests/test_hank_personality.py`. Remaining changes are accepted-decision/spec/state/test-matrix/checkpoint and this evidence.

Exact approved additive `LongitudinalPlan.hankPersonality @40` has version UInt8 @0, base/effective LongitudinalPersonality @1/@2, apmEnabled Bool @3, applies Bool @4, selfdriveStateMonoTime UInt64 @5. Existing enum/ordinals untouched. Sole producer snapshots after the completed MPC update, clears the prior snapshot at update start, and never invokes APM twice. Native Cereal enums use their raw ordinal; integer test fixtures remain supported. No snapshot/version 0 before a completed update.

The UI requires verified active HANK authority and a valid Active/latch. Plan must be seen/valid/version 1/applies, with known base/effective, three positive nonfuture timestamps (Event, model, selfdriveState) within 0.5 s and at/after current onroad UI epoch. v2 base matches Active; v1 stays Legacy. OFF must have equal base/effective. Missing, corrupt, stale, old-session or contradictory data shows unavailable; TSS shows inactive. UI does not infer APM from speed or mutate CFG. Separate APM text remains visible when safe owner switching is blocked, while failure/reboot has priority and no override claim.

No APM algorithm/hysteresis, MPC weights/branches/bounds, PARAM_DIM (7), COMFORT_BRAKE (2.5), D-022 bench seed (0.09/0.6), coordinator, CFG authority, Toyota/Panda/SecOC, or solver source change. `selfdriveState.personality` remains base. Runtime display is not a command or engagement authority.

## Test-first and final tests

All commands run from the authoritative repo with `.venv` activated. Common options intentionally retain the existing explicit pytest configuration and avoid cache writes:

```sh
source .venv/bin/activate
PYTHONDONTWRITEBYTECODE=1 python -m pytest -o addopts= -p no:cacheprovider -q selfdrive/ui/tests/test_hank_personality.py
```

Before production edits: exit **1**, **2 failed in 0.35 s** ([baseline.log](baseline.log)), assertion `hankPersonality in event.longitudinalPlan.to_dict()`, Normal and Comfortable. Actual planner/native solver/publish/serialized Event, not an import/mock failure. Final extended suite: exit **0**, **47 passed in 2.44 s** ([focused.log](focused.log)).

Covers all three profiles, Original, v1 Legacy; ACC/blended; strict 30/40 km/h thresholds and in-band hysteresis history; APM OFF; Stock Long; forwarding spies prove weights/update equal published effective. Requested/Active/latch values unchanged. Restart reuses Active and resets only existing planner-local APM history; pending request applies after modeled isolated lifecycle. Invalid/unknown enum/version, absent pointer, invalid/unseen transport, missing/corrupt authority, base mismatch, OFF contradiction, each timestamp's zero/future/stale/session boundaries, and incomplete update are checked.

Development failures were resolved: native Cap'n Proto enums need `.raw` (not `int(dynamic_enum)`); Original uses the dedicated restore API, and corruption fixtures write isolated raw files rather than bypassing typed Params through an invalid put. No production policy was weakened to fit tests.

Existing regression command:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest -o addopts= -p no:cacheprovider -q \
  selfdrive/ui/tests/test_hank_owner_recovery.py \
  selfdrive/ui/tests/test_hank_owner_ui.py \
  selfdrive/ui/tests/test_hank_owner_ui_wiring.py \
  selfdrive/ui/tests/test_hank_profile_state.py \
  selfdrive/selfdrived/tests/test_hank_owner.py \
  selfdrive/selfdrived/tests/test_hank_owner_service.py \
  selfdrive/selfdrived/tests/test_hank_profile_gap.py \
  selfdrive/controls/tests/test_hank_config.py \
  selfdrive/controls/tests/test_hank_config_plannerd.py \
  selfdrive/controls/tests/test_hank_profiles.py \
  selfdrive/controls/tests/test_dtsc_bounds.py \
  selfdrive/controls/tests/test_longitudinal_mode.py \
  selfdrive/controls/tests/test_dynamic_follow.py \
  selfdrive/controls/tests/test_accel_personality_planner.py \
  selfdrive/controls/tests/test_low_speed_response.py \
  selfdrive/controls/tests/test_stop_distance.py
```

Exit **0**, **526 passed in 26.86 s**, no warning summary ([regression.log](regression.log)). After native/Cereal build reran only the affected new suite plus owner recovery/UI/wiring: same options with those four files; exit **0**, **131 passed in 6.84 s** ([post-build.log](post-build.log)). These overlap prior results; do not count them as extra unique tests. No full longitudinal maneuver or whole-release suite in this logical unit; VERIFY-RC-02 remains separate.

## Control equivalence and build

```sh
PYTHONDONTWRITEBYTECODE=1 python docs/hank/evidence/2026-11-10/fix-ui-02/compare_control.py
/usr/bin/time -f 'ELAPSED=%e EXIT=%x' scons -u -j4
```

[Comparison](compare.log), exit **0**: 84 paired sequential frames, baseline planner obtained read-only from `git show b498060:...`, current planner, both actual native solvers. HANK/Stock Long, ACC/blended, all personalities, APM hysteresis/OFF and DTSC/DASR included. Forwarding spies record every p/W/yref write. All inputs and native v/a/j outputs **exactly equal**, finite, status 0; aTarget/shouldStop/source equal. This is deterministic fixture evidence, not a universal or vehicle equivalence proof.

[SCons](scons.log), exit **0**, **73.15 s**. Actual capnpc generation and native compilation/link completed. Two known CasADi 3.7.2 compatibility warning blocks; no compile/generation failure or I/O error. Standard dependency rules also execute acados generation dependencies and rebuild the lateral wrapper, native Params, Panda debug binaries and fonts; these are ignored/generated artifacts, not source edits. Do not describe this as no generation: **no manual solver regeneration and no tracked solver/generated change**. Solver source/model/dimension untouched. No install/flash/device action. Native comparison and 131-test affected suite ran after this build.

## Ruff and diff

```sh
ruff check --no-cache selfdrive/controls/lib/longitudinal_planner.py selfdrive/ui/hank_profile.py selfdrive/ui/onroad/hud_renderer.py selfdrive/ui/tests/test_hank_personality.py
git show b498060:selfdrive/controls/lib/longitudinal_planner.py | ruff check --no-cache --stdin-filename selfdrive/controls/lib/longitudinal_planner.py -
ruff check --no-cache docs/hank/evidence/2026-11-10/fix-ui-02/compare_control.py docs/hank/evidence/2026-11-10/fix-ui-02/render_probe.py
git diff --check
```

Ruff 0.13.1: first two commands exit **1** with exactly identical stdout: only existing PIE790 `DPFlags.pass` at planner:49 ([ruff.log](ruff.log)). **PRE_EXISTING_BASELINE_LINT; no new lint regression PASS**, not raw lint clean. Evidence harness lint exits **0**. Diff check exits **0**. No unrelated cleanup, tolerance change or generated tracked files. Final staged stat is retained in [diff-stat.txt](diff-stat.txt).

## Actual desktop HUD and owner interactions

[render_probe.py](render_probe.py) uses actual HudRenderer, real planner/native MPC and serialized Cereal updates, isolated native Params, synthetic vehicle/manager topics. Owner authority fixtures and transport observer are test-only; no runtime gate seeding, manager/card launch or request. Raylib renders to a native render texture under Xvfb; exported framebuffer pixels are retained, no hand-drawn replacement. This avoids relying on window backbuffer screenshot timing. Existing English font still shows Chinese profile labels as `??`; no localization acceptance claim.

```sh
mkdir -p /tmp/fix-ui-02-impl /dev/shm/msgq_fix-ui-02
LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe \
  PARAMS_ROOT=/tmp/fix-ui-02-impl/visual-params OPENPILOT_PREFIX=fix-ui-02 SCALE=1 BIG=1 \
  PYTHONDONTWRITEBYTECODE=1 xvfb-run -a -s '-screen 0 2160x1080x24' \
  .venv/bin/python docs/hank/evidence/2026-11-10/fix-ui-02/render_probe.py
```

Exit **0** ([render.log](render.log)); nine states assert text reaches actual renderer, no APM/button overlap, protected Params unchanged and zero requests. Pixels visually inspected: [override](hud-override.png), [cleared](hud-cleared.png), [OFF](hud-off.png), [unavailable](hud-unavailable.png), [pending](hud-pending.png), [engaged](hud-engaged.png), [multiple blockers](hud-multiple-blockers.png), [TSS](hud-tss.png), [failed/reboot](hud-failed.png). Limited actual desktop widget evidence, not a full-app/C3X test.

Existing actual widget/mouse/confirmation recovery probe rerun with modified HUD:

```sh
PARAMS_ROOT=/tmp/fix-ui-01/visual-params OPENPILOT_PREFIX=fix-ui-01 SCALE=1 BIG=1 \
  PYTHONDONTWRITEBYTECODE=1 xvfb-run -a -s '-screen 0 2160x1080x24' \
  .venv/bin/python docs/hank/evidence/2026-11-10/fix-ui-01/render_probe.py
```

Exit **0**, [owner-interaction.log](owner-interaction.log): disabled taps produce no dialog/request; fresh recovery enables manual action only; changed conditions during confirmation block send; timeout recovers only with new evidence; failure retains reboot fallback/cancel; protected Params unchanged. No automatic retry.

## Outcome and continuation

FIX_UI_02_STATE = PASS at local software/desktop scope. D-026 accepted and implemented in this single checkpoint. NEXT **VERIFY-RC-02**: whole corrected release regression and native diagnostic gates, then only propose a new candidate. No RC2 refs created. No push/mirror update/device/C3X/vehicle test. No deployment or vehicle-safety claim. Rollback must treat producer/schema/UI together; immutable RC1 stays intact.
