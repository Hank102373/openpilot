# 2026-11-10 HANK readiness audit evidence

Audited runtime source: b35a4c1bdbe83468690935cf08d6c3e8d0174855, WSL Ubuntu-24.04, Python 3.12.3, SCons 4.9.1, pytest 8.4.2, Ruff 0.13.1. Windows checkout remained at 95bd593. Both tracked working trees were clean at audit completion. Evidence below was copied from the original audit /tmp logs into this docs-only checkpoint.

## Executed checks

All test commands ran from `/home/hank/src/dp-sienna-0103` after activating `.venv`, with `PYTHONDONTWRITEBYTECODE=1 python -m pytest -o addopts= -p no:cacheprovider -q` plus the following paths.

- `targeted.log`: selfdrive/controls/tests/{test_accel_personality,test_accel_personality_planner,test_dtsc_bounds,test_dynamic_follow,test_following_distance,test_hank_config,test_hank_config_plannerd,test_hank_profiles,test_longitudinal_mode,test_low_speed_response,test_pull_away,test_radar_early_decel,test_stop_distance}.py; selfdrive/selfdrived/tests/{test_hank_owner,test_hank_owner_service,test_hank_profile_gap}.py; selfdrive/ui/tests/{test_hank_owner_ui,test_hank_owner_ui_wiring,test_hank_profile_state}.py. The braces here abbreviate explicit filenames passed in the actual command. Result: 727 passed in 53.18s.
- `core.log`: selfdrive/controls/tests/test_leads.py selfdrive/controls/tests/test_longcontrol.py. Result: 4 passed in 1.10s, one Python fork warning.
- `longitudinal.log`: selfdrive/test/longitudinal_maneuvers/test_longitudinal.py. Result: 4 passed, 58 subtests passed in 33.41s; 42 SQP_RTI status-3 diagnostic messages. Do not confuse diagnostic count with pytest failures.
- `build.log`: `scons -u -j4`. Command reported exit 0 and done building targets. This was not a clean-room build or C3X build.
- `ruff.log`: `ruff check --no-cache` on the 38 Python files returned by `git diff --name-only 1986516 HEAD -- '*.py'`. Exit 1; 17 diagnostics. `lint_baseline.json` compares baseline/current code, diagnostic message and stripped source-line fingerprints: zero new diagnostics. Do not label raw lint clean.
- `git diff --check`: exit 0. No tracked runtime/test/doc change during audit; local ignored build artifacts were produced.

## Independent contract probes

`contract_probes.json`: using native Params under TemporaryDirectory and actual HankOwnerUIModel, initialize confirmed HANK authority, set last_result to each BLOCKED_ENGAGED, BLOCKED_STALE_OR_INVALID, TRANSPORT_UNAVAILABLE, then call state(cp). D-024 expected action_enabled false; all three actual values true. This audit probe records failures as data, not a new committed pytest test. Existing test_hank_owner_ui.py:127 asserts true and does not protect the decision contract.

The same evidence calls actual APM.get_personality(0.0, standard): base=1, effective=0. Source-traced HUD expression compares published base to active base and returns false. This establishes a data-flow mismatch; it is not a rendered HUD test.

## Source/remote observations

On 2026-11-10 `git ls-remote origin` showed implementation branch, hank/phase1-rc1 and peeled hank-phase1-rc1 tag equal b35a4c1bdbe83468690935cf08d6c3e8d0174855. c3x-mirror flat hank-phase1-rc1 branch and peeled tag matched. Mirror symbolic HEAD was tn-2025-11v1 at e0231f076c09c30e40a275a49359100c2b367f8d. These are timestamped observations; re-read before any publication/device action.

No device install/flash, vehicle experiment, push, source tuning, or safety approval occurred. Use HANK_EXECUTION_PLAN.md and CURRENT_STATE.md for the corrective sequence.
