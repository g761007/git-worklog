# repo_worklog v0.4.0 — commit author 與報告模式

## Context

`repo_worklog` 目前是單向的**寫入管線**：選日期範圍 → 讀真實 diff → 每日一個 Day Subagent → dry-run → 確認 → 寫進 `PROJECT_WORKLOG/<date>.md`。日誌產出後就靜靜躺在那裡，沒有任何消費它的路徑。這次補上兩個缺口：

1. **日誌沒有記錄「誰做的」。** `collect_git_history.py` 其實已完整收集 `author_name`／`author_email`／`author_date`，但 `build_analysis_manifest.py` 在投影 commit 時把作者欄位丟掉了，Day Subagent 從來看不到作者。多人專案的日誌因此無法回答「這段是誰寫的」。

2. **日誌無法被查詢。** 使用者想要的是「幫我整理上一週工作摘要」「整理 v1.0.1 CHANGELOG」這種產物，但目前只能自己打開七個 `.md` 檔手動拼。日誌已經是讀過真實 diff 的高品質素材，卻沒有出口。

預期結果：日誌記錄參與者；並新增一個**唯讀報告模式**，用既有日誌 + git 回答自然語言問題，產物只輸出到對話。

**已確認的決策**（使用者選定）：author 同時出現在 commit 層級與當日參與者列表；報告只輸出到對話、不寫檔；遇到缺口先詢問並建議補齊；報告模式併入本 skill 而非獨立。

---

## 功能 1：commit author 進入日誌

### 唯一的程式碼缺口

`repo_worklog/scripts/build_analysis_manifest.py:230-236` 把 commit 投影成只剩五個欄位，作者在此遺失：

```python
"commits": [{
    "short_hash": c.get("short_hash"),
    "full_hash": c.get("full_hash"),
    "subject": c.get("subject"),
    "is_merge": c.get("is_merge"),
    "is_revert_candidate": c.get("is_revert_candidate"),
} for c in commits],
```

上游 `collect_git_history.py:253-277` 已經有 `author_name` / `author_email`，無需改動。

### 改動

1. **`build_analysis_manifest.py`**
   - commit 投影加入 `author_name`（不放 `author_email`：日誌是給人看的，email 是 PII 雜訊且對敘事無用）。
   - 新增日期層級 `authors: []` — 依 `author_name` 去重、依當日首次出現排序。**這是確定性事實，不是判斷**，所以由腳本算，不交給模型從 20 個 commit 裡歸納（模型會漏人）。這符合 skill 既有分工：「確定性工作歸腳本，判斷工作歸 subagent」。

2. **`references/worklog-format.md` §3** — 模板加入兩處：
   - `## 當日摘要` 區塊開頭一行 `參與者：Daniel Hsieh、Alice Chen`
   - `- **相關 commits：**` 欄位格式改為 `<short_hash> (<author_name>) <subject>`

3. **`references/subagent-contract.md` §3** — manifest 欄位表補上 `commits[].author_name` 與 `authors[]`。

4. **渲染由 orchestrator 負責**（契約 §1 已定「Markdown generation」屬 orchestrator）。orchestrator 本來就持有 manifest，所以：
   - `參與者：` 直接取 manifest 的 `authors[]`。
   - `相關 commits` 的作者用 `short_hash → author_name` 對照表查表。

   **不需要改 Day Subagent 回傳 schema**。作者是查表得到的確定性事實，不經模型轉手就不會被寫錯。

5. **不動** `worklog_markers.py` / `update_daily_worklog.py` / 兩支 validator — 作者活在 GENERATED 內容裡，而 GENERATED 內容本來就是自由格式、只驗結構不驗內容。meta blockquote 維持 `時區/Branch/HEAD`（它是全 run 共用的，塞逐日參與者需要改 meta schema、序列化器與驗證器，代價不成比例）。

### 測試（`tests/`）

- `tests/helpers.py`：`_commit()` 增加 `author: str | None = None` 參數，透過 `GIT_AUTHOR_NAME` / `GIT_AUTHOR_EMAIL` env 注入（既有寫法已用 env 注入日期，照同一模式）。新增 `make_multi_author_repo()` fixture：同一天多位作者、跨日單一作者。
  - 注意：現有 fixture 全部是單一作者 `Fixture Bot`，多作者測試一定要新 fixture。
- `tests/test_pipeline.py` 或 `test_git_collection.py`：斷言 manifest 的 `commits[].author_name` 正確、`authors[]` 去重且順序穩定、單一作者日只出現一次、merge commit 的作者處理正確。

---

## 功能 2：報告模式（唯讀）

### 定位

SKILL.md 開頭新增**模式路由**，分流兩種意圖：

- **產生模式**（現狀，寫入）：「整理今天」「整理最近 7 天」→ 既有管線不變。
- **報告模式**（新增，唯讀）：「整理上一週工作摘要」「整理 v1.0.1 CHANGELOG」→ 讀既有日誌 + git，答案只輸出到對話。

路由放在 SKILL.md §1 之後、§2 之前。**不動「無參數 → 印選單並停止」黃金守則**：報告模式只由自然語言／明確參數觸發，選單不加新選項（選單是「要整理哪個範圍」的問句，報告模式問的是完全不同的問題，硬塞進去會讓選單語意破碎）。

### 兩種 scope（關鍵設計）

這是整個設計最容易做錯的地方。日誌是**以日期為索引**，但版本是**以 commit 集合為界**，兩者不能直接互換：

- **date scope**（週報／月報／交接／個人貢獻）：日期是權威，commit 由日期推導。
- **ref scope**（CHANGELOG）：**`git log <prev-tag>..<tag>` 的 commit 集合才是權威**，日期只是用來「定位該讀哪些日誌檔」的索引。

為什麼不能只把 tag 轉成日期區間就當 date scope 用 —— 那會同時 over-include 與 under-include：

- **多算**：某天的日誌涵蓋當天所有 commit，但其中可能有不屬於這個 tag 範圍的（別的分支、tag 切在當天中午之後的 commit）。
- **少算**：cherry-pick 過來的 commit 帶著舊的 author date，落在區間之外的日子。

所以 ref scope 的流程是：先取權威 commit 集合 → 推導這些 commit 落在哪些日期 → 讀那些日誌檔當**敘事素材** → **但只描述 commit 在範圍內的工作**。日誌的 `相關 commits` 欄位帶著 short hash，所以這個對帳是可執行的，不是空話。

### 新腳本（各自輸出單一 JSON，沿用既有慣例）

1. **`scripts/resolve_ref_range.py`**
   - `--tag v1.0.1`（自動找前一個 tag）／`--from-ref v1.0.0 --to-ref v1.0.1`／`--list-tags`
   - 輸出：`{ok, tag, prev_tag, commit_range, commits: [{short_hash, full_hash, date, author_name, subject}], dates: [], date_span: {from, to}}`
   - 錯誤碼：`UNKNOWN_TAG`、`NO_PREVIOUS_TAG`（首個 tag → 退回 root commit，明確告知）、`NO_TAGS`
   - **為什麼需要腳本而非讓 orchestrator 直接下 git**：tag 排序（`creatordate` vs 版本序）、annotated vs lightweight tag、前一個 tag 的選取、commit→本地日期換算（需時區）都是易錯的確定性邏輯，正是這個 skill 一貫塞進腳本的那類工作。

2. **`scripts/check_worklog_coverage.py`**
   - `--repo <root> --dir PROJECT_WORKLOG --dates <逗號分隔>`（兩種 scope 都餵日期清單進來）
   - 輸出：`{ok, dates: [{date, commit_count, has_worklog, status}], gaps: [], covered: [], no_commit_dates: []}`
   - `status`：`covered`（有 commit 有日誌）／`gap`（**有 commit 但沒日誌 ← 真缺口**）／`no-commits`（沒 commit，依 `worklog-format.md` §6 本來就不該有檔案，**不算缺口**）
   - 重用 `collect_git_history.collect_commits()` 與 `worklog_markers`（`DATE_FILE_RE`、`parse_date_filename`、`scan_day`）—— 不重寫任何解析邏輯。self-referential 排除也因此自動繼承。

3. **`resolve_date_range.py`** 微調：`MAX_DAYS = 30` 改為可用 `--max-days N` 覆寫（預設仍 30）。
   - 理由：30 天上限存在的目的是**限制 subagent 成本**。報告模式的「讀取」不 spawn 任何 subagent，成本結構完全不同，卻會被這個上限擋住（v1.0.1 可能橫跨 90 天）。
   - 邊界：報告模式讀取上限 90 天（`REPORT_MAX_DAYS`）；**補齊仍然一律 30 天**，因為補齊會 spawn subagent。這一點必須寫進 SKILL.md，否則就是把安全閥拆掉。

### 缺口處理流程

```
1. 解析 scope（date 或 ref）→ 得到日期清單
2. check_worklog_coverage.py → 分出 covered / gap / no-commits
3. 沒有 gap → 直接產報告
4. 有 gap → 列出缺口日期與各自 commit 數，詢問使用者：
     a. 先補齊再報告（推薦）→ 交給既有寫入管線（dry-run → 確認 → apply），完成後產報告
     b. 不補，直接報告 → 報告中明確標注哪幾天只有 commit message、沒有深度分析
     c. 取消
5. gap > 30 天 → 無法一次補齊，據實說明並建議分批，或改選 (b)
```

**為什麼預設建議補齊**：skill 的核心原則是「讀 diff，不是讀 commit message」。拿 git log 硬湊摘要等於默默違反它，而且使用者看不出報告品質被稀釋了。補齊後分析會存下來，下次報告免費。

選 (b) 時報告**必須**標注淺資料日期 —— 這是誠實回報要求，不是可選裝飾。

### 黃金守則的分模式收斂

SKILL.md §0 需要改寫兩條，讓它們的適用範圍精確而非被削弱：

| 現況 | 改為 |
|---|---|
| 「Max 30 calendar days」 | 「產生與補齊：最多 30 個日曆天。報告模式讀取既有日誌：最多 90 天（不 spawn subagent）。」 |
| 「Whole project, every author. Never filter by `git config user.name/email`」 | 「日誌**儲存**永遠涵蓋所有作者，絕不依 `git config user.name/email` 自動過濾。報告模式可依作者過濾，但**僅限使用者明確指名**（『Daniel 上個月做了什麼』）—— 絕不從 git config 推斷『我』是誰。」 |

其餘四條（讀 diff 不讀 message／dry-run first／一天一檔／不跑 git 寫入指令）報告模式全部照舊適用；報告模式不寫檔，所以 dry-run 守則自然不觸發。

### 支援情境（`references/report-mode.md` 文件化為 prompt 範例，非各自的程式分支）

全部走同一條泛用流程，差別只在 scope 與提問：

| 情境 | 範例 | scope |
|---|---|---|
| 期間工作摘要（週報／月報） | 「幫我整理上一週工作摘要」 | date |
| 版本 CHANGELOG | 「整理 v1.0.1 CHANGELOG」 | ref |
| 交接摘要 | 「我要交接，整理最近一個月的重點與待辦」 | date |
| 個人貢獻 | 「Daniel 上個月做了什麼」 | date + author 過濾（**功能 1 使能**） |
| 功能／模組演進史 | 「會員搜尋這功能是怎麼演進的」 | date + 檔案過濾 |
| 待辦與風險彙整 | 「目前累積哪些技術債與待追蹤事項」 | date |

最後一項幾乎免費：日誌模板本來就有 `後續事項`、`相容性與風險`、`維護注意事項` 欄位，純聚合即可。

「上一週」→ 由模型正規化成上個日曆週的 `from`/`to`（既有的模型層 NL 正規化職責，`resolve_date_range.py` 本來就吃 `--from`/`--to`，**無需改腳本**）。注意這與既有契約的「最近一週 → `days=7`」語意不同：**「上一週」是上個日曆週，「最近一週」是往回七天** —— 這個區別要寫進 `date-parameter-contract.md`。

### 報告合成

由 orchestrator 直接讀日誌檔（純 Markdown）合成，**不新增 subagent 型別**。日誌已經是消化過的素材，再派 subagent 只是多一層轉述失真。唯一會 spawn subagent 的路徑是補齊 —— 那是既有管線。

---

## 需要修改的檔案

**程式**
- `repo_worklog/scripts/build_analysis_manifest.py` — author 投影 + `authors[]`
- `repo_worklog/scripts/resolve_date_range.py` — `--max-days`
- `repo_worklog/scripts/resolve_ref_range.py` — 新增
- `repo_worklog/scripts/check_worklog_coverage.py` — 新增

**文件**
- `repo_worklog/SKILL.md` — 模式路由、黃金守則收斂、腳本表、reference 表
- `repo_worklog/references/report-mode.md` — 新增（報告模式完整規格）
- `repo_worklog/references/worklog-format.md` — §3 模板加參與者與 commit 作者
- `repo_worklog/references/subagent-contract.md` — §3 manifest 欄位表
- `repo_worklog/references/date-parameter-contract.md` — `--max-days`、「上一週 vs 最近一週」
- `repo_worklog/references/interaction-flow.md` — 報告模式互動與缺口詢問
- `README.md` — 雙語使用範例
- `CHANGELOG.md` + `repo_worklog/agents/openai.yaml` — v0.4.0（minor：新功能、無破壞性變更）

**測試**
- `tests/helpers.py` — `_commit(author=...)`、`make_multi_author_repo()`
- `tests/test_git_collection.py` 或 `test_pipeline.py` — manifest author 斷言
- `tests/test_report_scope.py` — 新增：`resolve_ref_range` 與 `check_worklog_coverage`

---

## 驗證方式

1. **單元測試**：`python3 -m unittest discover -s tests -v`，目前 97 個全綠，新增後應維持全綠。
   - manifest：`commits[].author_name` 正確、`authors[]` 去重與排序、單作者日不重複
   - `resolve_ref_range`：正常 tag 對、首個 tag（退回 root）、未知 tag、無 tag repo、lightweight vs annotated tag
   - `check_worklog_coverage`：三種 status 分類正確 —— 特別是 **no-commits 不得被判為 gap**（這是最容易做錯的一條）
   - `resolve_date_range --max-days`：預設仍 30、覆寫生效、超限仍報 `TOO_MANY_DAYS`
2. **端對端手動驗證**：在本 repo 上跑（已確認本 repo 有 4 個 **annotated** tag `v0.1.0`~`v0.3.1`，是現成的 ref scope 素材）。
   - **前置**：本 repo **目前沒有 `PROJECT_WORKLOG/`**，報告模式會無事可讀。所以先跑產生模式補幾天日誌（順帶 dogfood 功能 1 的參與者輸出），再跑報告模式。
   - 「整理 v0.3.1 CHANGELOG」→ 驗證 tag 範圍解析。因為日誌只補了幾天，這裡**應該**會報大量缺口 —— 正好驗證缺口詢問確實會觸發，而不是默默產出爛報告。
   - 「整理上一週工作摘要」→ 驗證 date scope 與日曆週正規化。
   - 刻意刪掉一個有 commit 的日誌檔 → 驗證被判為 `gap`；再確認一個沒 commit 的日期**不會**被判為 gap（最容易做錯的一條）。
   - 完全沒有 `PROJECT_WORKLOG/` 時跑報告模式 → 應給出明確訊息並建議先產生，而非空報告或例外。
3. **回歸**：既有產生模式的 dry-run → apply 流程未受影響（`test_pipeline.py` 整合測試涵蓋）
4. CI 綠燈（Python 3.9 / 3.12 / 3.13）

---

## 建議的 commit 切分

1. `feat(manifest)`: author_name + authors[] 進入 manifest
2. `test(manifest)`: 多作者 fixture 與斷言
3. `docs(format)`: 日誌模板加入參與者與 commit 作者
4. `feat(report)`: `resolve_ref_range.py` + `check_worklog_coverage.py` + `--max-days`
5. `test(report)`: 報告 scope 測試
6. `docs(skill)`: 模式路由、`report-mode.md`、黃金守則收斂、README
7. `chore(release)`: CHANGELOG + 版本號 → 0.4.0

## 風險與未決

- **範圍不小**：兩個功能、4 支腳本（2 新）、7 份文件。建議功能 1 先獨立完成並驗證（1–3 步），再做功能 2 —— 功能 1 是功能 2「個人貢獻」情境的前置。
- **90 天報告上限**是拍板數字，不是推導出來的。實際跑起來若 context 撐不住需下修。
- **ref scope 的對帳**（只描述範圍內 commit）目前靠模型遵守指示，沒有機制強制。若實測發現模型會漏掉這步，需要在 `check_worklog_coverage.py` 加上 per-commit 覆蓋檢查（用日誌裡的 short hash 比對），但先不預先實作。
