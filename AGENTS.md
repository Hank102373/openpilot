# HANK repository execution instructions

Read `HANK_EXECUTION_PLAN.md`, `docs/hank/CURRENT_STATE.md`, and the relevant latest entries in `HANK_DECISION_LOG.md`, `HANK_INTEGRATION_SPEC.md`, and `HANK_TEST_MATRIX.md` before making changes.

- `HANK_EXECUTION_PLAN.md` is the user-approved highest-priority repository execution plan for task order, workspace routing, gates, and continuation. Explicit later user instructions take precedence. It does not silently replace product/safety decisions.
- Authoritative execution workspace: WSL Ubuntu-24.04 `/home/hank/src/dp-sienna-0103`, branch `hank/implementation-v1`. The Windows checkout `C:\HANK\dp-sienna-0103` is a historical copy, not a second implementation authority. A task opened there must route execution to the verified WSL workspace; do not synchronize or edit the historical copy implicitly.
- Verify branch, HEAD, working tree and relevant upstream refs before a change. Preserve unexpected user work; do not reset, clean, stash, checkout, pull, merge or rebase to force a precheck to pass.
- Work one logical unit at a time. Update current state and retain reproducible evidence. Historical NEXT/PASS statements in checkpoint history do not authorize new work or release.
- Do not repeat completed ABC analysis or PORT units. Current accepted MPC dimension is 7 under F-002, not the earlier PORT-01 dimension 6.
- Preserve RC1 `b35a4c1bdbe83468690935cf08d6c3e8d0174855` and its branch/tag. Corrections require a new candidate; never move old RC refs.
- No push, mirror update, C3X install, device connection/flash, engagement, or road testing without explicit authorization for that action. The current authorization covers the local plan/handoff checkpoint, not publication or deployment.
- Do not log or commit SecOC keys, credentials, or device secrets. Never manually seed a permissive owner-verification gate.
