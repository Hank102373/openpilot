# HANK current continuation state

Updated: 2026-11-10. Execution authority: [HANK_EXECUTION_PLAN.md](../../HANK_EXECUTION_PLAN.md).

## Workspace and source identity

- Authoritative workspace: WSL Ubuntu-24.04 `/home/hank/src/dp-sienna-0103`; branch `hank/implementation-v1`.
- Windows `C:\HANK\dp-sienna-0103` remains a clean historical copy at `95bd593`; it is not the current implementation workspace.
- Audited runtime baseline / immutable RC1: `b35a4c1bdbe83468690935cf08d6c3e8d0174855`.
- On 2026-11-10, origin implementation and RC1 branch/tag, plus the c3x-mirror flat RC1 branch/tag, resolve to that SHA. This is a timestamped remote observation, not a guarantee about future refs.
- Mirror default HEAD is `tn-2025-11v1` at `e0231f076c09c30e40a275a49359100c2b367f8d`; explicitly select the approved RC and verify SHA.
- Plan checkpoint: `fb25d6c385e0373da9410a5b005555cfdfdc5e12`. This continuation adds the local FIX-UI-01 checkpoint; use `git log` for its SHA. Origin remains at RC1; no publication is authorized.

## COMPLETED

- E-001/E-002, PORT-01/02/03, CFG, F-002, F-005, D-022, UI-01/UI-02 implementation and D-025 have existing source checkpoints. Do not repeat them.
- Historical RC readiness and installer-design reviews occurred; RC1 refs and installation mirror now exist. Their existence does not prove device installation or safety.
- 2026-11-10 fresh audit: selected HANK/CFG/owner/UI/control tests 727 passed; leads/LongControl 4 passed (one Python fork warning); full longitudinal 4 tests/58 subtests passed, 42 historical-matching SQP_RTI status-3 diagnostics; SCons completed.
- Changed-Python Ruff reports 17 diagnostics, all matching A-baseline code/message/source-line fingerprints; no new diagnostic. Raw Ruff is not a zero-error PASS.
- GOV-01: authoritative plan, root agent entrypoint, consolidated state, archived history and durable audit evidence prepared in this documentation checkpoint.

- FIX-UI-01: owner blocked/unavailable actions disabled; fresh safe observations restore manual confirmation only. Existing coordinator protocol/state machine unchanged. Test-first 4 expected failures; final owner/service/coordinator/CFG/profile suites 342 passed in 34.02 s; final affected UI suites 84 passed in 3.66 s; changed-source/test Ruff and diff check pass. Actual desktop owner HUD/settings/dialog render and mouse-interaction probe passed. See [reproducible evidence](evidence/2026-11-10/fix-ui-01/README.md).

## IN PROGRESS

FIX-UI-01 software/desktop owner-surface correction is complete in this local checkpoint. FIX-UI-02 and VERIFY-RC-02 have not started. No new RC candidate or deployment approval.

## OPEN FINDINGS / BLOCKERS

- FIX-UI-01 corrected at software/desktop scope. C3X timing, real service load, language/font and full-app visual acceptance remain unvalidated. English-font desktop probe renders existing Chinese profile labels as `??`; do not count that as localization acceptance.
- FIX-UI-02: HUD APM override compares published base personality with active base; actual planner effective personality is not that signal. Source review and an APM runtime probe establish the data-flow mismatch, not a rendered UI acceptance.
- No dedicated HANK CI gate demonstrated. Actual desktop owner-widget visual/interaction evidence now exists; it does not establish full-app, all-language or C3X acceptance.
- C3X install/boot/runtime, stationary Sienna ownership/SecOC/CAN/rollback, physical gap, V1-V3 and release approval remain unvalidated.
- D-022 gain/cap `0.09/0.6 m` remain C3X BENCH SEED ONLY, not product defaults. Current accepted MPC dimension is 7 and COMFORT_BRAKE is 2.5.

## NEXT

**FIX-UI-02 — APM effective personality display.** Follow HANK_EXECUTION_PLAN.md: establish the real planner-effective signal and any required schema decision before implementation. Do not repeat FIX-UI-01; VERIFY-RC-02 follows both corrections. No push/RC ref/mirror/device action is authorized.

## Readiness and history

WSL development environment: READY. Existing selected software suites/build: PASS with documented limitations. Overall RC repair acceptance: OPEN. C3X/vehicle/deployment: NOT APPROVED.

Original state is preserved verbatim after an archive notice in [historical snapshot](history/CURRENT_STATE_20260923.md). Historical NEXT/PASS statements there and in IMPLEMENTATION_CHECKPOINT.md are not current instructions. Use [audit evidence](evidence/2026-11-10/README.md) and this single current NEXT.
