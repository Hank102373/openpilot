# FIX-UI-01 — owner disabled action and safe manual recovery

Date: 2026-11-10. Base: `fb25d6c385e0373da9410a5b005555cfdfdc5e12`, WSL Ubuntu-24.04, `hank/implementation-v1`, clean precheck. User authorized this local implementation/test/handoff checkpoint. RC1 branch and peeled tag remain `b35a4c1bdbe83468690935cf08d6c3e8d0174855`; tag object `36e274111712b76f2e8fc580c1d0779bb2fe89ea`. A read-only `git ls-remote origin` also confirmed origin implementation and RC1 refs remain at RC1. No fetch/push or ref movement.

## Contract and scope review

Only owner UI model, HUD/settings callers and focused tests change runtime/test behavior. No coordinator/service/manager protocol, state machine, Cereal schema, Params registry, planner, control algorithm, Toyota, Panda, SecOC, solver or generated artifact change. Existing coordinator remains the sole owner writer and request-time authority. The APM signal mismatch remains FIX-UI-02; this change only preserves profile edit/display eligibility when owner switching is blocked.

Fresh UI evidence uses existing SubMaster topics `deviceState`, `selfdriveState`, `carControl`, `carState`, `managerState`, with logMonoTime/valid/seen. Reuses coordinator Evidence.idle_reason and its age limits (device 2 s, remaining UI topics 1 s); recomputes age using monotonic time at every display/confirmation call. Owner Param/transaction/gate/CP consistency uses existing interlock_reason. No UI evidence grants engagement or validates Panda.

Manager publishes managerState after owner_service.poll. A non-sending AF_UNIX datagram connect additionally checks that the existing service socket endpoint is present. Neither check sends a request or creates a new heartbeat protocol. Together these are advisory progress/availability evidence, not a guarantee that the next transport round trip succeeds. A later timeout is handled closed again. Rejected/timeout requests retain a monotonic barrier: ALL five topics must be newer than the rejection and currently safe/valid, with available endpoint and confirmed authority. Then only manual confirmation is re-enabled. No same-owner health request, invalid-message ping, automatic resend or Params/cycle writes.

UNVERIFIED, in-flight and SWITCH_FAILED take precedence; failure retains reboot-only recovery. HANK Requested profile edits remain independent of owner-switch eligibility while active driving; TSS profiles stay stored, not active. HUD/settings share model/adapter, refresh on render and on confirmation, show reasons, wrap long blockers, and use a shorter confirmation retaining driver/ALKA/ACC/lifecycle/verification semantics.

## Test-first failure

Before any production edit, added only `test_rejected_action_stays_disabled_without_new_safe_evidence`, parametrized for BLOCKED_ENGAGED, BLOCKED_STALE_OR_INVALID, TRANSPORT_UNAVAILABLE, TRANSPORT_TIMEOUT. Real isolated native Params contain confirmed HANK authority; last_result is the rejected case. Existing UI model returns enabled. Command (repo root, `.venv` activated):

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest -o addopts= -p no:cacheprovider -q selfdrive/ui/tests/test_hank_owner_recovery.py
```

Exit 1: **4 failed in 0.26 s**, each exactly `assert not view.action_enabled`. Raw [baseline.log](baseline.log). No failing-test-only commit. The final file extends that contract with 47 additional cases (51 total).

## Final verification

```sh
source .venv/bin/activate
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
  selfdrive/controls/tests/test_hank_profiles.py
```

Exit 0: **342 passed in 34.02 s**, no warnings reported ([targeted.log](targeted.log)). Includes real Params, real SubMaster conversion, actual service socket with no datagram on availability probe, and real OwnerService/OwnerCoordinator rejecting ALKA after the UI's safe observation without owner/cycle mutation. Covers stale/future/invalid/missing data, all active commands, delayed confirmation, unchanged topics after rejection, safe recovery, offroad, authority change, unsupported/in-flight/failed gates, profile isolation and manager publication ordering.

Final changes after this suite wrap HUD text/space the failed-state panel and distinguish timeout wording. Actual widget render/interaction probe rerun exit 0; affected static wiring suite rerun: **7 passed in 0.13 s**, exit 0 ([final-wiring.log](final-wiring.log)). After the final timeout wording, reran recovery/model/wiring suites together: **84 passed in 3.66 s**, exit 0 ([final-ui.log](final-ui.log)); command is the same pytest options with `test_hank_owner_recovery.py`, `test_hank_owner_ui.py`, `test_hank_owner_ui_wiring.py`. No final source change after this run.

```sh
ruff check --no-cache selfdrive/ui/hank_owner.py selfdrive/ui/onroad/hud_renderer.py \
  selfdrive/ui/layouts/settings/toggles.py selfdrive/ui/tests/test_hank_owner_ui.py \
  selfdrive/ui/tests/test_hank_owner_recovery.py
```

The final Ruff command additionally included the checked-in `render_probe.py` evidence harness. Ruff 0.13.1: exit 0, All checks passed ([ruff.log](ruff.log)). `git diff --check`: exit 0. Historical repository-wide lint debt remains historical; no claim it was cleaned.

During development a partial-subscription fixture exposed a missing-topic KeyError (fixed to fail closed), test import edits needed correction, and confirmation wording initially missed an exact `disengaged` assertion (wording preserved). These were resolved before final gates. No broad longitudinal run or SCons in this logical unit; VERIFY-RC-02 owns those gates.

## Real desktop UI surface evidence

[render_probe.py](render_probe.py) creates actual HudRenderer panel, TogglesLayout owner items and ConfirmDialog under Xvfb at 2160x1080 (BIG=1/SCALE=1), native isolated Params and synthetic Cereal frames. It injects mouse press/release events through the widgets. Transport is an observing stub in this visual probe; real socket/coordinator coverage is in pytest above. No manager/card/device launched.

Reproduce from repository root (existing Xvfb/Raylib; no package install):

```sh
mkdir -p /tmp/fix-ui-01 /dev/shm/msgq_fix-ui-01
PARAMS_ROOT=/tmp/fix-ui-01/visual-params OPENPILOT_PREFIX=fix-ui-01 SCALE=1 BIG=1 \
  PYTHONDONTWRITEBYTECODE=1 xvfb-run -a -s '-screen 0 2160x1080x24' \
  .venv/bin/python docs/hank/evidence/2026-11-10/fix-ui-01/render_probe.py
```

Exit 0 ([render.log](render.log)): blocked actual mouse clicks open no dialog/request; safe frames re-enable both surfaces; confirmed dialog after ALKA activation sends no request; timeout recovery requires fresh frames and sends nothing automatically. Protected Params unchanged during those flows. A separately seeded temporary failed fixture shows reboot only; reboot confirmation is cancelled and DoReboot is not set. Early harness attempts required creating its isolated msgq directory, setting list viewport bounds and selecting the correct BIG desktop size; those were harness setup errors, not device results.

Inspected screenshots: [HUD blocked](hud-blocked.png), [HUD recovered](hud-recovered.png), [settings blocked](settings-blocked.png), [settings recovered](settings-recovered.png), [timeout](hud-timeout.png), [confirmation](confirmation.png), [combined blockers](hud-multiple-blockers.png), [failure/reboot](hud-failed.png). Owner reasons/actions fit; confirmation no longer overlaps buttons. Scope: English owner surfaces on software desktop only. Existing Chinese profile labels show `??` with this English font configuration: localization/font and full-app/C3X visual acceptance remain OPEN, not silently accepted or expanded into this fix.

## Handoff / rollback boundary

FIX-UI-01 software contract + desktop owner-surface verification: PASS. NEXT is FIX-UI-02. Preserve this local checkpoint as an independently revertible unit; reverting it would restore the known disabled-action defect and requires regression review, not RC1 ref changes. Existing RC1 remains immutable. C3X/vehicle/release acceptance remains NOT APPROVED. No push, mirror update, device operation, solver regeneration, control tuning or permissive real-runtime owner-gate seeding.
