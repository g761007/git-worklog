# Git Worklog v1.0 重構 — 規劃階段執行計畫(不動程式碼)

## Context

使用者已完成一份完整的 v1.0 重構路線圖(9 個 PR,v0.5→v1.0):將 `repo_worklog_skill` 重新定位為 **Git Worklog** — 以共用 Engine 為核心、提供 Skill 與 CLI 兩種介面、加入 BCP 47 語言契約、Agent-hosted 分析管線與 Immutable Preview。

本 session 經使用者確認為**純規劃階段**:不修改任何程式碼,交付物是(1)修正過的路線圖文件落地到 `docs/plans/`、(2)GitHub tracking issues 與 milestone。已定案的三項決策:

1. **本次只做規劃**,PR 1 的實際 rename 留待後續 session。
2. **GitHub repo 改名由 Claude 執行**(`gh repo rename`),時點在未來執行 PR 1 時,非本次。
3. **PR 1 只改名稱不動目錄**(`repo_worklog/` 目錄保留,frontmatter/manifest/文件改為 git-worklog);**只有 v1.0 會正式對外發布**,v0.5–v0.9 為內部里程碑,不出 GitHub Release 與 skill.zip。

## 現況盤查:路線圖與程式碼實況的落差(需寫入修正附錄)

已完成 read-only 盤查,以下發現必須修正進路線圖,否則執行期會踩到:

1. **§15.4 的 `REPO_WORKLOG_HOME` 環境變數不存在**。使用者層級路徑是硬編碼:`repo_worklog/scripts/preview_state.py:43`(`STATE_DIR = ~/.repo_worklog/previews`)與 `repo_worklog/scripts/collect_day_results.py:48`(`ANALYSIS_DIR = ~/.repo_worklog/analysis`)。因此 `GIT_WORKLOG_HOME` 是**新增**而非改名;過渡相容應改為「找不到新目錄時 fallback 讀取硬編碼的 `~/.repo_worklog/`」。
2. **PR 1 的實際 rename 面比計畫想的小**:`repo_worklog_skill` 字串只出現在 `CHANGELOG.md`(5 處,多為歷史紀錄——不改寫歷史,只修會失效的連結)與 git remote。真正的命名面是 `repo_worklog/SKILL.md` frontmatter(`name: repo_worklog`)、`repo_worklog/agents/openai.yaml`(`name`/`display_name: Repository Worklog`/`command: /repo_worklog`)、README 標題。
3. **`PROJECT_WORKLOG` → `.git-worklog/` 屬於 PR 2,不是 PR 1**。runtime 有單一定義點 `repo_worklog/scripts/worklog_markers.py:58`(`WORKLOG_DIRNAME`),8 個 scripts 經 `--dir` 參數引用;但文件層(SKILL.md 13 處、README 16 處、references/ 共 33 處、tests 12 處)硬寫名稱,PR 2 必須文件與程式同步改。
4. **本專案自己已提交的 `PROJECT_WORKLOG/` 目錄**(dogfooding 資料)也要在 PR 2 一併 migration,計畫未提及。
5. **CI 路徑寫死**:`.github/workflows/ci.yml` 的 byte-compile 與 smoke-test 步驟硬寫 `repo_worklog/scripts/*.py`。任何目錄改名的 PR 必須同 PR 更新 CI。
6. **測試以 sys.path 注入 + subprocess 呼叫 scripts**(`tests/helpers.py:18-21`,`SCRIPTS = repo_worklog/scripts`)。PR 3 建立 `git_worklog` package 時是結構性風險點,需保留 wrapper 相容或同步改寫 helpers。
7. **目前完全沒有語言處理邏輯**(scripts/config 全面 grep 確認)——PR 4 是 100% 新工作,估點時不可當作改造既有功能。
8. **skill.zip 目前是手動打包**,無 build script。既然只 ship v1.0,打包腳本(把 skill 目錄 stage 成 `git-worklog/` 讓安裝後觸發名正確)排入 PR 3 或 PR 7,v1.0 發布前完成即可。
9. **版本策略修正**:v0.5–v0.9 不發布 → CHANGELOG 持續累積在 `[Unreleased]`,v1.0 時一次 cut;`openai.yaml` 的 `version:`(現為 0.4.0)在中間 PR 不逐版遞增,v1.0 時一次調整。
10. **plan 檔存放慣例衝突**:全域 CLAUDE.md G1 指定 `<project_root>/plans/`,但本專案既有慣例是 `docs/plans/`(已有 2026-07-15、2026-07-16 兩份)。依優先序(專案慣例優先)採 `docs/plans/`。

## 執行步驟(核准後)

1. **寫入路線圖文件** `docs/plans/2026-07-16-git-worklog-v1-roadmap.md`:
   - 內容 = 使用者的路線圖原文(§1–§23,逐字保留)
   - 追加「附錄 A:現況對照與修正(2026-07-16)」= 上述 10 點,含 file:line 引用
   - 追加「附錄 B:已定案決策」= 三項使用者決策(planning-only、gh repo rename 由 Claude 於 PR 1 執行、PR 1 只改名稱不動目錄、僅 v1.0 對外發布)
2. **保存本規劃檔**到 `docs/plans/2026-07-16-git-worklog-v1-planning.md`(依 G1,採專案慣例路徑)。
3. **建立 GitHub milestone「v1.0」**(`gh api repos/g761007/repo_worklog_skill/milestones`;gh 已認證、repo scope 具備)。
4. **建立 9 個 tracking issues**(PR 1–PR 9 各一),掛上 milestone:
   - 標題英文(依 F2 慣例,如 `PR 1: Rebrand to git-worklog (names only, no path changes)`)
   - 內文含:對應路線圖章節、範圍摘要、驗收條件(取自路線圖 §17 並套用附錄 A 修正)、風險等級
   - PR 1 的 issue 明確列入「Claude 執行 `gh repo rename git-worklog` + 更新本地 remote」步驟
   - PR 之間的依賴關係在內文標注(PR 2 依賴 PR 1、PR 5/6 依賴 PR 3/4 等)
5. **commit**(僅 `docs/plans/` 兩個檔案,訊息如 `docs(plan): add git-worklog v1.0 roadmap with reality-check appendix`)。**不 push**——推送與否留給使用者。

## 驗證方式

- `git diff --stat` 只出現 `docs/plans/` 兩個新檔,無任何程式碼或既有文件變動
- 路線圖文件包含原文全部 23 個章節 + 兩個附錄;附錄 A 的 file:line 引用逐一開檔抽查
- `gh issue list --milestone v1.0` 回傳 9 筆,標題對應 PR 1–9
- 測試不需重跑(零程式碼變更),但以 `git status` 確認工作樹除新增檔案外乾淨

## 不在本次範圍

- PR 1 的實際執行(所有 rename、`gh repo rename`)
- 任何 scripts/tests/CI/SKILL.md 的修改
- 本地資料夾 `~/Documents/program/projects/repo_worklog_skill` 改名(session 工作目錄限制,留給使用者事後處理)
- skill.zip 重打包、版本 tag
