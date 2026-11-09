# HANK 最高執行計畫 — RC 缺口修正與驗收

版本：1.0；核准來源：使用者於 2026-11-10 要求將本輪盤點後的安排寫入 Git，作為後續修改的大方向。

## 1. 指示效力與工作區

本檔是 repository **工作順序、續接、範圍與驗收 gate 的最高執行指示**；後續明確的使用者指示優先。產品、架構、安全及數值行為仍由最新 Decision Log / Integration Spec 約束，Test Matrix 規定驗收要求。遇到衝突先提出具體證據與 decision closure，不可利用本計畫默默改變產品或安全決策。

- 唯一正式開發／build／test 工作區：WSL Ubuntu-24.04 `/home/hank/src/dp-sienna-0103`。
- Branch：`hank/implementation-v1`；repository：`Hank102373/dp-sienna-0103`。
- Windows `C:\HANK\dp-sienna-0103` 為歷史副本，本輪仍是 `95bd593`。不得在該舊版重做 PORT-01 或引用舊 CURRENT_STATE 指揮現在的修改。
- 本輪稽核 runtime baseline / immutable RC1：`b35a4c1bdbe83468690935cf08d6c3e8d0174855`。
- 後續文件 checkpoint 可以前進；上述 SHA 是稽核來源身分，不是要求未來每輪 HEAD 都退回此值。
- 任務開始時先核對實際 HEAD、branch、working tree 與最新 CURRENT_STATE。不得 reset/clean/stash/pull/merge/rebase 強制符合舊 precheck。

本檔只規定執行計畫；當前狀態與**唯一有效 NEXT** 位於 [CURRENT_STATE](docs/hank/CURRENT_STATE.md)。所有 history/checkpoint 中的舊 NEXT 均為歷史。

## 2. 已完成的工作不得重做

E-001 DTSC bounds、E-002 MPC mode、PORT-01 Dynamic Follow、PORT-02 Pull-away、PORT-03 Accel Personality、CFG、F-002 Stop Distance、F-005、D-022 early decel、UI-01、UI-02 core/wiring、D-025 均已有實作與歷史驗證。此次 audit 重新檢查選定 suites 與 build，不代表完全沒有功能缺口。

保留：`PARAM_DIM=7`、`COMFORT_BRAKE=2.5`、Stop Distance Relaxed/Standard/Aggressive `4.5/4.0/4.0`；D-022 `0.09/0.6 m` 為 **C3X BENCH SEED ONLY — NOT PRODUCT DEFAULT**。不得在這次 UI 修正中調整它們。

## 3. 依序執行的 logical units

### GOV-01 — 計畫與交接收斂（本 checkpoint）

- 新增本檔及 root AGENTS 續接入口。
- CURRENT_STATE 僅保留最新實況；完整舊版本移入 history，不刪除來源證據。
- Checkpoint/Test Matrix 標明歷史 PASS 的時間與範圍；記錄新發現的 UI 缺口。
- 保存本輪原始測試/build/lint/probe 日誌。
- 完成條件：文件鏈接、歷史保存、scope review、diff check 通過；本地 docs-only commit。此 gate 不宣稱 UI 已修正。

### FIX-UI-01 — Owner blocked/unavailable action 契約修正（第一個程式修改單元）

問題：D-024 要求 blocked/unavailable 時停用切換；`selfdrive/ui/hank_owner.py` 目前仍開啟 action，`test_hank_owner_ui.py` 反而要求它開啟。本輪真實 Params 隔離 probe 已重現。

預期範圍：owner UI model、其 HUD/settings callers 與必要 focused tests。Coordinator 是唯一安全權威；UI 顯示資格不能取代 coordinator 的 request-time fresh recheck，也不能直接寫 owner、gate 或 cycle Params。

1. 先按 D-024 寫獨立契約測試，在未修正程式上證明失敗。
2. `BLOCKED_ENGAGED`、stale/invalid、transport unavailable/timeout 顯示明確原因並停用切換。
3. 明確定義 fresh eligibility 的 UI 資料來源、失效與恢復：條件未恢復不得重新送 request；有新的有效安全證據後可重新啟用「手動確認」操作。不能只改成永久停用，也不能自動重送切換。
4. 保留 selfdrive、ALKA lateral、factory ACC/no-active-command、unsupported vehicle、UNVERIFIED、in-flight、SWITCH_FAILED 的限制。same-boot failure 仍只容許既有 reboot recovery。
5. 測試需涵蓋 blocked → still blocked、blocked → fresh safe recovery、確認期間條件改變、無額外 Params/cycle write、HUD/settings 一致、coordinator 再次拒絕、無自動 retry。
6. 若符合規格需要改 coordinator protocol/state machine 或 schema，先形成小範圍 decision review，不擴大本單元默默修改。

驗收：owner model/wiring/service/coordinator、CFG/profile suites；Ruff 新增診斷為零、diff check；必要 UI 渲染／互動證據。測試綠燈不能替代視覺/互動檢查。取得可用實際 UI surface 前不得標記視覺驗收 PASS。

### FIX-UI-02 — APM effective personality 顯示修正

問題：HUD 比較 published base 與 Active base，但 APM effective personality 僅在 planner 局部變數改變；低速 override 會漏顯示。

- 建立 planner 實際 effective personality → UI 的正確資料流；UI 不可複製另一套 APM 演算法或推測其 state/hysteresis。
- 先檢查既有訊號是否足夠；如需新增 Cereal 欄位或跨程序介面，先完成 decision/schema review。不得為顯示而改變縱向控制行為。
- 先寫能暴露舊訊號錯誤的測試，再做最小實作。
- 覆蓋 Normal/Comfortable 低速 override、解除閾值、APM OFF、Compact 已是 Aggressive、Stock Long、same-session restart、資料缺失/過期；Requested/Active 不得被 override 改寫。
- 以跨 planner→UI 測試及可用 UI surface 證明；僅測局部比較式不足。

### VERIFY-RC-02 — 修正後整體回歸與新候選

- 重跑 HANK/CFG/owner/UI/native MPC suites、E-001/E-002、following-distance、Stop Distance、leads/LongControl、完整 longitudinal maneuvers。
- 執行 `scons -u -j4`、changed-file Ruff、`git diff --check`。新 lint 不得增加；既有 baseline debt 必須列明，不能宣稱 raw Ruff 全綠。
- Native solver 維度/參數、有限值、重置及 SQP_RTI 診斷與 baseline 比較；發現變化先分類，不可改 tolerance 追求綠燈。
- 檢查 Toyota/SecOC/Panda/LongControl 保護範圍與無關調校未被修改。
- 保留不可變 RC1。所有修正 commit 通過且無未解軟體阻塞後，才提出新的 RC 候選 SHA；建立/發布 RC2 refs 與 mirror 更新須有明確授權。

### DIST-01 — 發布來源與 rollback 程序

- 已存在 `Hank102373/openpilot` 的 `hank-phase1-rc1` branch/tag，指向 RC1。
- 但 mirror 預設 `tn-2025-11v1` 指向另一來源；不得以未指定 branch 的 repo URL/clone 當作 RC1。
- 固定完整 SHA、指定 flat branch、遠端讀回並準備來源/裝置 rollback 證據；核對適用的當前安裝流程，不發明 installer URL。
- 既有 release scripts 含固定路徑、dragonpilot remote、清理來源等操作，不直接套用於 HANK 開發目錄。若採 packaging，先做隔離來源與腳本 review。
- CI 尚無 HANK 專用自動 gate；建立最小可重現驗證入口、固定執行清單與版本，CI 接入另列範圍。手動證據不得包裝成已有 CI 保護。

### DEVICE-01 / VEHICLE-01 — 實體驗證（需另行授權與設備）

順序：standalone C3X install/build/source identity/UI/manager → 靜止 Sienna CarParams/Panda/SecOC/owner cycle/failure/reboot/rollback → 依 Test Matrix V1–V3。

裝置上不得人工 seed `HankOwnerSessionVerified`；未通過前不得以軟體 PASS 宣稱可上路。實體 1–2 m stopped-gap mapping、D-022 最終調校及真實 CAN/actuator 行為均仍待驗證。

## 4. 每個單元的完成與 Git 規則

每單元記錄：base SHA、scope、獨立 fail proof（適用時）、精確命令/exit code、通過項目、限制、diff review、rollback 邊界與下一步。先完成必要測試再建立可獨立回復的本地 checkpoint；不提交 failing-test-only 狀態。CURRENT_STATE 與 Test Matrix 必須反映新發現，舊 PASS 不得覆蓋已知缺口。

本輪授權：GOV-01 本地計畫/交接 checkpoint。後續修改以本計畫為大方向。**push、mirror 更新、RC 發布、C3X 安裝/刷機、車輛操作均需明確授權**，不得從「依計畫」推論已獲部署授權。

## 5. 證據與目前 readiness

稽核來源為 RC1 `b35a4c1`；詳見 [本輪 evidence](docs/hank/evidence/2026-11-10/README.md)。WSL environment READY；既有選定 suites/build PASS；UI 契約仍有缺口；整體 release/C3X/vehicle readiness NOT APPROVED。
