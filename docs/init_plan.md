# `repo_worklog` Skill 完整計劃

## 1. Skill 目標

建立一個名為：

~~~text
repo_worklog
~~~

的 Skill，讓使用者透過：

~~~text
/repo_worklog
~~~

或自然語言指令，分析目前 Git repository 在指定日期範圍內的實際程式碼異動，並整理成方便維護者、協作者與接手人員快速閱讀的專案工作日誌。

這個 Skill 必須：

- 分析全專案的 commits，不依作者過濾。
- 實際閱讀 Git diff 與程式碼內容。
- 不得只根據 commit message 產生摘要。
- 依日期逐日分析。
- 多日分析時，每一天分別指派 Subagent。
- 產生 Markdown 工作日誌。
- 正確插入或覆蓋指定日期。
- 保留人工補充內容。
- 預設只執行 dry-run。
- 使用者確認後才真正寫入檔案。
- 最大分析範圍為 30 個曆日。

---

# 2. Skill 名稱與呼叫方式

## 2.1 Skill 名稱

Skill 目錄與內部名稱：

~~~text
repo_worklog
~~~

使用者直接呼叫：

~~~text
/repo_worklog
~~~

## 2.2 無參數呼叫行為

當使用者只輸入：

~~~text
/repo_worklog
~~~

不得直接分析今天。

Skill 必須先顯示所有可用操作，並等待使用者再以自然語言或選項編號指定需求。

建議固定顯示：

~~~text
請選擇要整理的專案工作日誌範圍：

1. 今天
2. 指定日期
3. 最近 7 天
4. 最近 30 天
5. 自訂日期範圍
6. 今天，並包含尚未提交的異動
7. 自訂日期或範圍，並包含尚未提交的異動

日期範圍最多為 30 天。

所有操作都會先顯示 dry-run 預覽，不會直接修改專案檔案。

你可以直接輸入選項編號，或用自然語言回答，例如：

- 整理今天
- 整理 2026-07-01
- 整理最近 7 天
- 整理 2026-07-01 到 2026-07-10
- 整理今天並包含未提交異動
- 整理近 30 天
~~~

此時不得執行：

- Git history 掃描。
- Subagent 指派。
- 日誌預覽生成。
- 檔案建立或修改。

使用者選擇範圍後才開始分析。

## 2.3 自然語言驅動

使用者可直接輸入：

~~~text
今天
~~~

~~~text
整理最近一週
~~~

~~~text
幫我補 2026 年 7 月 1 日的工作日誌
~~~

~~~text
整理 7 月 1 日到 7 月 10 日
~~~

~~~text
今天，包含還沒有 commit 的修改
~~~

~~~text
整理近 30 天，但不要包含 working tree
~~~

Skill 將自然語言轉換為標準內部參數，再交由確定性腳本驗證。

## 2.4 選項編號

無參數選單出現後，以下輸入也應支援：

~~~text
1
~~~

代表今天。

~~~text
3
~~~

代表最近 7 天。

~~~text
6
~~~

代表今天並包含未提交異動。

若選擇需要補充資料的項目，例如：

~~~text
2
~~~

Skill 再詢問：

~~~text
請輸入要整理的日期，例如 2026-07-01。
~~~

若選擇：

~~~text
5
~~~

則詢問：

~~~text
請輸入起始與結束日期，例如 2026-07-01 到 2026-07-10。
~~~

## 2.5 直接帶參數呼叫

熟悉介面的使用者可以跳過選單：

~~~text
/repo_worklog date=2026-07-01
~~~

~~~text
/repo_worklog days=7
~~~

~~~text
/repo_worklog 7d
~~~

~~~text
/repo_worklog 30d
~~~

~~~text
/repo_worklog from=2026-07-01 to=2026-07-10
~~~

~~~text
/repo_worklog date=2026-07-15 include_uncommitted=true
~~~

有效參數存在時，直接進入分析流程，不再顯示功能選單。

---

# 3. 日期參數契約

## 3.1 支援參數

~~~text
date
days
from
to
include_uncommitted
~~~

支援快捷格式：

~~~text
7d
30d
2026-07-01
~~~

## 3.2 單日模式

~~~text
date=2026-07-01
~~~

等同：

~~~text
2026-07-01
~~~

只處理指定日期。

## 3.3 最近天數模式

~~~text
days=7
~~~

等同：

~~~text
7d
~~~

包含執行當日在內的最近 7 個曆日。

例如在 2026-07-15 執行：

~~~text
7d
~~~

日期範圍為：

~~~text
2026-07-09 至 2026-07-15
~~~

`days=1` 代表今天。

## 3.4 自訂日期範圍

~~~text
from=2026-07-01 to=2026-07-10
~~~

起始日與結束日皆包含。

總天數計算為：

~~~text
to - from + 1
~~~

## 3.5 最大天數

最大範圍固定為：

~~~text
30 天
~~~

有效：

~~~text
days=30
~~~

無效：

~~~text
days=31
~~~

無效：

~~~text
from=2026-06-01 to=2026-07-15
~~~

超過 30 天時：

- 不執行分析。
- 不自動截短成 30 天。
- 顯示實際要求的天數。
- 請使用者縮小範圍。

範例：

~~~text
指定範圍共 45 天，超過 repo_worklog 的 30 天上限。
請將日期範圍縮小至 30 天以內。
~~~

## 3.6 日期模式互斥

以下模式互斥：

- `date`
- `days`
- `from` 與 `to`

例如：

~~~text
date=2026-07-01 days=7
~~~

應回報參數衝突。

不得自行判斷哪一個參數優先。

## 3.7 其他驗證規則

- `days` 必須是 1 至 30 的整數。
- `from` 不得晚於 `to`。
- `to` 不得單獨存在。
- `from` 原則上也必須搭配 `to`。
- 日期格式標準化為 `YYYY-MM-DD`。
- 無效日期必須拒絕，例如 `2026-02-30`。
- 自然語言中的「近一個月」固定解析為最近 30 天，而不是依月份實際天數。
- 未來日期可以解析，但若沒有 Git 異動，應明確顯示沒有可分析內容。

---

# 4. 時區規則

## 4.1 日期依據

所有日期範圍都必須依執行環境的本地時區計算。

取得時區的優先順序：

1. 執行環境提供的 IANA timezone。
2. 作業系統本地 timezone。
3. 專案設定中的 timezone。
4. Skill 額外設定的 timezone。
5. 若仍無法可靠判斷，再要求使用者指定。

例如：

~~~text
Asia/Taipei
~~~

## 4.2 每日時間範圍

每一天使用半開區間：

~~~text
[當日 00:00:00, 次日 00:00:00)
~~~

避免使用：

~~~text
23:59:59.999
~~~

以降低毫秒精度與夏令時間問題。

## 4.3 Commit 日期欄位

預設使用：

~~~text
committer date
~~~

決定 commit 歸屬哪一天。

同時保留：

- author date
- committer date

若兩者差異會影響理解，可在分析證據中標示。

---

# 5. Repository 分析範圍

## 5.1 全專案

分析目前 branch 可見歷史中的所有相關 commits。

不得依下列資料自動篩選作者：

~~~text
git config user.name
git config user.email
~~~

這份日誌是專案工作日誌，不是個人工作日報。

## 5.2 Branch 規則

預設分析目前 checkout 的 branch。

Skill 不得自動執行：

~~~text
git fetch
git pull
git checkout
git switch
git merge
git rebase
~~~

dry-run 摘要應顯示：

- repository root
- current branch
- HEAD hash
- 是否為 detached HEAD
- dirty working tree 狀態
- 使用的時區

## 5.3 空 repository

若 repository 尚無 commit：

- `include_uncommitted=false`：回報沒有可整理的 Git 歷史。
- `include_uncommitted=true`：可以只分析 working tree。
- 不得假裝存在 commit-based 工作日誌。

---

# 6. 未提交異動

## 6.1 預設值

~~~text
include_uncommitted=false
~~~

預設不分析：

- staged changes
- unstaged tracked changes
- untracked files

## 6.2 開啟方式

~~~text
include_uncommitted=true
~~~

或自然語言：

~~~text
包含未提交異動
~~~

~~~text
連 working tree 一起整理
~~~

~~~text
包含還沒有 commit 的內容
~~~

## 6.3 分析內容

開啟後分析：

- staged diff
- unstaged diff
- untracked files
- 新增 binary files
- 刪除或重新命名但尚未提交的檔案

## 6.4 日期歸屬

未提交內容只能歸入執行當日。

例如：

~~~text
/repo_worklog 30d include_uncommitted=true
~~~

其中：

- 前 29 天只分析已提交 commits。
- 今天額外分析 working tree。
- 不得依檔案修改時間把 working tree 分配到歷史日期。

## 6.5 日誌呈現

未提交內容必須放在獨立區段：

~~~text
### 尚未提交的異動
~~~

並區分：

- staged
- unstaged
- untracked

不得將未提交內容描述成已完成或已進入正式 Git 歷史。

---

# 7. Subagent 模型設定

## 7.1 Claude Code

使用：

~~~text
claude-sonnet-5
~~~

## 7.2 Codex

使用：

~~~text
gpt-5.6-terra
~~~

## 7.3 Gemini

使用：

~~~text
gemini-flash-3.0
~~~

## 7.4 模型設定結構

模型設定應將顯示名稱與實際模型識別字分開：

~~~yaml
providers:
  claude_code:
    display_name: claude-sonnet-5
    model_id: <runtime-specific-model-id>

  codex:
    display_name: gpt-5.6 Terra
    model_id: <runtime-specific-model-id>

  gemini:
    display_name: gemini-flash-3.0
    model_id: <runtime-specific-model-id>
~~~

正式實作時，實際 `model_id` 必須依宿主工具支援的識別字設定。

## 7.5 模型不可用

若指定模型不可用：

- 不得靜默改用更昂貴模型。
- 不得自行選擇其他模型。
- 不得退化成只讀 commit message。
- 應停止尚未開始的相關 Subagent 任務。
- 顯示指定模型不可用。
- 列出目前可選候選模型。
- 由使用者決定是否替換。

---

# 8. 整體執行流程

完整流程如下：

1. 解析 `/repo_worklog` 呼叫。
2. 無參數時顯示功能選單。
3. 接收自然語言或選項編號。
4. 將輸入正規化為標準參數。
5. 驗證日期、範圍與參數衝突。
6. 偵測 repository、branch、HEAD 與 timezone。
7. 將日期範圍切成逐日任務。
8. 為每一天建立分析 manifest。
9. 每一天指派一個 Day Subagent。
10. Day Subagent 必要時再分派 Code Analysis Subagent。
11. 讀取實際 Git diff。
12. 閱讀必要的程式碼上下文。
13. 確認當日結束時的最終程式碼狀態。
14. 產生結構化每日分析。
15. 主協調者合併每日結果。
16. 產生 Markdown 工作日誌草稿。
17. 模擬插入或覆蓋工作日誌。
18. 顯示完整 dry-run 預覽。
19. 產生 preview ID。
20. 等待使用者確認。
21. apply 前重新驗證 repository 狀態。
22. 安全寫入工作日誌。
23. 寫入後重新驗證。
24. 顯示實際更新摘要。

---

# 9. 逐日 Subagent 架構

## 9.1 一天一個 Day Subagent

多日範圍必須以天為單位拆分。

例如：

~~~text
days=7
~~~

建立：

~~~text
Day Agent: 2026-07-09
Day Agent: 2026-07-10
Day Agent: 2026-07-11
Day Agent: 2026-07-12
Day Agent: 2026-07-13
Day Agent: 2026-07-14
Day Agent: 2026-07-15
~~~

每個 Day Subagent：

- 只負責自己的日期。
- 不得直接修改工作日誌。
- 必須回傳結構化分析結果。
- 即使沒有 commit，也必須回報 `has_changes=false`。

## 9.2 主協調者責任

主協調者負責：

- 使用者互動。
- 自然語言解析。
- 日期驗證。
- 每日任務切分。
- Subagent 指派。
- 結果完整性驗證。
- 跨日期去重。
- Markdown 生成。
- dry-run。
- preview 管理。
- 寫入與驗證。

主協調者不得用 commit subject 直接替代程式碼分析結果。

## 9.3 Day Subagent 責任

每個 Day Subagent 必須：

- 取得當日 commits。
- 取得 commit metadata。
- 取得每個 commit 的實際 patch。
- 分析 changed files。
- 追蹤 rename 與 copy。
- 分析 merge 與 revert。
- 將 commits 按實際工作主題分組。
- 閱讀修改後的完整程式碼。
- 閱讀直接呼叫端與依賴。
- 閱讀相關測試。
- 判斷當日最終狀態。
- 回傳結構化結果與證據。

## 9.4 單日大型異動

若單日變更量較大，Day Subagent 可以再指派 Code Analysis Subagent。

分組優先順序：

1. 實際功能或模組。
2. 彼此相關的檔案群。
3. backend / frontend / mobile。
4. API。
5. database / migration。
6. tests。
7. configuration / CI。
8. deployment。
9. documentation。

不得預設使用：

~~~text
一個 commit 一個 Subagent
~~~

因為同一工作項目可能跨多個 commits。

---

# 10. Git 資料收集規則

## 10.1 Commit 基本資料

每個 commit 至少收集：

- full commit hash
- short commit hash
- author name
- author email
- author date
- committer name
- committer email
- committer date
- subject
- body
- parent hashes
- merge 狀態
- changed files
- add / modify / delete / rename / copy 狀態
- diffstat
- actual patch

Commit message 只作為背景資訊與索引。

## 10.2 強制讀取實際 diff

每個相關 commit 必須取得相當於：

~~~text
git show --format=fuller --find-renames --find-copies <commit>
~~~

所提供的資訊。

不得只執行：

~~~text
git log --oneline
~~~

也不得只依賴：

- commit subject
- commit body
- changed file list
- diffstat
- 新增與刪除行數

## 10.3 程式碼上下文閱讀

對重要變更，必須繼續閱讀：

- 變更所在的完整函式。
- 完整 class。
- 完整 component。
- interface 與 type。
- route。
- controller。
- service。
- repository 或 data-access layer。
- schema。
- migration。
- feature flag。
- configuration。
- 直接呼叫端。
- 直接依賴。
- 相關測試。

不得只讀 diff 上下幾行就直接下結論。

## 10.4 上下文擴張策略

從 changed files 開始：

1. 閱讀變更區塊所在的完整語意單位。
2. 閱讀一層直接依賴。
3. 閱讀一層直接呼叫端。
4. 閱讀對應測試。
5. 涉及 public API、schema 或核心共用元件時，擴張第二層。
6. 證據仍不足時，標示不確定性。

不得無限制掃描整個 repository。

不得為了節省模型成本而省略必要程式碼閱讀。

---

# 11. 當日最終狀態規則

同一天可能有多個 commit 反覆修改相同功能。

例如：

~~~text
Commit A：加入快取
Commit B：修正快取 key
Commit C：撤回快取
~~~

最終日誌應寫：

~~~text
當日曾導入快取機制，但後續已撤回；當日結束時的程式碼未保留該快取行為。
~~~

不能把三個 commit 分別列成三個仍有效的功能異動。

Day Subagent 必須比較：

- 當日第一個 commit 前的狀態。
- 當日各 commit 過程。
- 當日最後一個 commit 後的狀態。
- 必要時目前 repository 中該程式碼的最終版本。

---

# 12. 特殊 Git 情境

## 12.1 Merge commit

避免 merge commit 與 parent commits 重複統計。

仍必須分析：

- merge conflict resolution
- merge result 才出現的程式碼
- squash merge
- merge 後造成的實際行為變化

## 12.2 Revert

不得只寫：

~~~text
Revert abc123
~~~

必須判斷：

- 哪些行為被撤回。
- 是否完整撤回。
- 是否仍保留部分程式碼。
- 當日最終狀態。

## 12.3 Rename 與 Copy

必須啟用 rename 與 copy detection。

應描述：

- 檔案搬移。
- 模組重新組織。
- 命名調整。
- 是否同時有實質行為變更。

不得一律誤判成刪除與新增。

## 12.4 Binary files

可以記錄：

- 路徑
- 新增、修改或刪除
- 大小或 Git metadata
- 可能的使用位置

不得聲稱已理解 binary 內容。

## 12.5 Generated files

優先分析來源檔。

只有在下列情況詳細記錄生成結果：

- 生成結果影響 runtime。
- 生成結果影響部署。
- 來源檔不可取得。
- 生成結果本身是交付物。

## 12.6 Lockfile

不逐行解讀 lockfile。

只摘要：

- 主要依賴新增或移除。
- 直接依賴版本變化。
- major version 變化。
- 大量 transitive dependency 變化。
- build 或 runtime 風險。

## 12.7 Submodule

若 submodule revision 改變，記錄：

- submodule path
- old revision
- new revision
- 是否可取得子 repository 內容
- 是否完成子 repository 分析

無法取得時不得猜測變更內容。

---

# 13. Day Subagent 回傳格式

Day Subagent 不直接撰寫最終工作日誌，而是回傳結構化資料。

建議 schema：

~~~json
{
  "date": "2026-07-15",
  "timezone": "Asia/Taipei",
  "has_changes": true,
  "commits": [],
  "work_items": [],
  "fixes": [],
  "refactors": [],
  "tests": [],
  "database_changes": [],
  "configuration_changes": [],
  "deployment_changes": [],
  "uncommitted_changes": [],
  "handoff_notes": [],
  "uncertainties": [],
  "evidence": []
}
~~~

每個 `work_item`：

~~~json
{
  "title": "工作主題",
  "summary": "完成了什麼",
  "behavior_change": "程式碼行為如何改變",
  "implementation": "主要實作方式",
  "impact": "影響範圍",
  "files": [],
  "commits": [],
  "tests": [],
  "risks": [],
  "maintenance_notes": [],
  "follow_ups": [],
  "confidence": "verified",
  "evidence": []
}
~~~

## 13.1 Confidence

允許值：

~~~text
verified
inferred
unknown
~~~

定義：

- `verified`：可由程式碼、diff 或測試直接證實。
- `inferred`：根據上下文合理推論，但沒有直接證據。
- `unknown`：現有資料不足以判定。

任何推論都不得被寫成已證實事實。

## 13.2 Evidence

每項重要結論至少應附：

- commit hash
- file path
- symbol 或函式名稱
- 相關 diff 或程式碼區域
- 測試檔案
- 必要時的行號或範圍

---

# 14. 工作日誌格式

## 14.1 格式選擇

正式日誌使用：

~~~text
Markdown
~~~

不使用 YAML 或 JSON 作為主要輸出。

理由：

- 最適合人類快速閱讀。
- GitHub、GitLab 與 IDE 可直接預覽。
- 適合放置路徑、commit、程式碼與交接說明。
- 適合 code review。
- 可安全保留人工補充。
- 可使用固定 HTML comments 作為更新標記。

JSON 可作為 Subagent 內部交換格式。

## 14.2 預設檔案

~~~text
docs/PROJECT_WORKLOG.md
~~~

若 `docs/` 不存在：

- dry-run 不建立目錄。
- apply 階段才建立目錄與檔案。

---

# 15. 工作日誌檔案結構

~~~markdown
# Project Worklog

> 本文件依據 Git commit、實際程式碼 diff 與相關程式碼上下文產生。
> 用於專案維護、交接與異動追蹤。
> 日期依執行環境的本地時區判定。

<!-- REPO_WORKLOG:ENTRIES:START -->

<!-- REPO_WORKLOG:2026-07-15:START -->
## 2026-07-15

<!-- REPO_WORKLOG:2026-07-15:GENERATED:START -->

自動產生內容。

<!-- REPO_WORKLOG:2026-07-15:GENERATED:END -->

<!-- REPO_WORKLOG:2026-07-15:MANUAL:START -->

人工補充內容。

<!-- REPO_WORKLOG:2026-07-15:MANUAL:END -->

<!-- REPO_WORKLOG:2026-07-15:END -->

<!-- REPO_WORKLOG:ENTRIES:END -->
~~~

日期排序：

~~~text
最新日期在上
~~~

---

# 16. 每日日誌內容模板

~~~markdown
## 2026-07-15

### 當日摘要

簡述當日完成的主要工作與整體影響。

### 主要異動

#### 工作主題

- **異動內容：**
- **程式碼行為：**
- **實作方式：**
- **影響範圍：**
- **相關檔案：**
- **相關 commits：**
- **測試與驗證：**
- **相容性與風險：**
- **維護注意事項：**
- **後續事項：**

### 修正項目

### 重構與技術債

### 資料庫與 Migration

### 設定、CI 與部署

### 測試狀態

### 尚未提交的異動

### 接手者快速閱讀

- 建議優先閱讀的檔案
- 關鍵流程入口
- 容易踩雷的規則
- 尚未涵蓋的測試
- 未完成或需要追蹤的項目
~~~

沒有內容的區段必須省略。

不得產生大量：

~~~text
無
無異動
N/A
~~~

---

# 17. 人工內容保留

## 17.1 自動內容

Skill 只能覆蓋：

~~~text
GENERATED:START
~~~

與：

~~~text
GENERATED:END
~~~

之間的內容。

## 17.2 人工內容

Skill 必須保留：

- 文件頂部人工內容。
- `ENTRIES` 區域外的內容。
- 每日 `MANUAL` 區段。
- 文件底部人工內容。

使用者可在：

~~~text
MANUAL:START
~~~

與：

~~~text
MANUAL:END
~~~

之間補充：

- Issue 或 ticket 連結。
- 決策背景。
- 部署備註。
- 尚未寫入 Git 的脈絡。
- 接手提醒。
- 團隊討論結果。

重新分析該日期時不得修改 MANUAL 區段。

---

# 18. 插入與覆蓋規則

## 18.1 新日期

若日期不存在：

1. 建立完整日期區段。
2. 找出正確日期排序位置。
3. 依日期降冪插入。
4. 不修改其他日期。
5. 不修改人工內容。

例如目前已有：

~~~text
2026-07-15
2026-07-10
~~~

補寫：

~~~text
2026-07-12
~~~

應插入：

~~~text
2026-07-15
2026-07-12
2026-07-10
~~~

## 18.2 已存在日期

若日期已存在：

1. 保留該日 MANUAL。
2. 完整重新分析該日。
3. 完整取代 GENERATED。
4. 不使用 append。
5. 不保留舊的自動摘要。
6. 保持日期正確排序。

## 18.3 沒有 commit 的日期

多日分析中，沒有 commit 的日期：

- 仍由 Day Subagent 回報完成。
- 預設不建立空日誌區段。
- dry-run 摘要列出該日無異動。

若某日原本已有日誌，但重新分析後沒有可見 commit：

- 不自動刪除整個日期區段。
- dry-run 明確顯示差異。
- MANUAL 永遠保留。
- 使用者確認後才可清空 GENERATED。

---

# 19. Dry-run 規則

## 19.1 永遠先預覽

任何有效分析請求都不得直接寫入。

例如：

~~~text
/repo_worklog date=2026-07-01
~~~

分析完成後只產生 dry-run。

## 19.2 Dry-run 顯示內容

至少包含：

- repository root
- current branch
- HEAD commit
- timezone
- requested date mode
- resolved date range
- include_uncommitted 狀態
- 每日 commit 數量
- 每日分析狀態
- 分析過的檔案數
- 將新增的日期
- 將覆蓋的日期
- 無異動日期
- 被保留的 MANUAL 區段
- 完整工作日誌預覽
- 目標檔案路徑
- preview ID
- 尚未修改任何檔案的提示

範例：

~~~text
Dry-run completed.

Repository:
<repository-root>

Branch:
main

HEAD:
abc1234

Timezone:
Asia/Taipei

Range:
2026-07-09 to 2026-07-15

Target:
docs/PROJECT_WORKLOG.md

Planned changes:
- 2026-07-14: overwrite generated section
- 2026-07-15: insert new entry

No files have been modified.

Preview ID:
rw-20260715-a81f2c
~~~

## 19.3 確認寫入

使用者可用自然語言：

~~~text
寫入
~~~

~~~text
確認更新
~~~

~~~text
套用剛才的預覽
~~~

~~~text
把這份寫進去
~~~

也支援：

~~~text
apply rw-20260715-a81f2c
~~~

只有明確確認後才進行 apply。

---

# 20. Preview 狀態管理

## 20.1 Preview 建立時記錄

- repository root
- current branch
- HEAD hash
- working tree fingerprint
- 工作日誌原始 hash
- 日期參數
- timezone
- include_uncommitted
- 預覽內容 hash
- preview 建立時間
- preview 是否已使用

## 20.2 Preview ID

格式可採：

~~~text
rw-YYYYMMDD-<short-hash>
~~~

例如：

~~~text
rw-20260715-a81f2c
~~~

## 20.3 Apply 前驗證

重新檢查：

- repository 是否相同。
- branch 是否相同。
- HEAD 是否相同。
- working tree 是否改變。
- 工作日誌原檔是否改變。
- preview 是否已經套用。
- preview 是否過期。
- include_uncommitted 狀態是否一致。

任何不一致時：

- 不得寫入。
- preview 標示失效。
- 要求重新 dry-run。

不得把過時預覽直接套用。

---

# 21. 寫入安全

正式寫入流程：

1. 讀取現有日誌。
2. 驗證 ENTRIES 標記。
3. 驗證每日 START 與 END。
4. 驗證 GENERATED 標記。
5. 驗證 MANUAL 標記。
6. 驗證日期唯一。
7. 建立更新後完整內容。
8. 寫入同目錄暫存檔。
9. 重新解析暫存檔。
10. 驗證日期降冪。
11. 驗證人工內容未改變。
12. 驗證 UTF-8。
13. 原子替換正式檔案。
14. 重新讀取正式檔案。
15. 執行最終驗證。
16. 顯示實際更新摘要。

Skill 不得自動執行：

~~~text
git add
git commit
git push
~~~

---

# 22. 錯誤處理

## 22.1 非 Git repository

回報：

~~~text
目前目錄不在 Git repository 中，無法建立專案工作日誌。
~~~

## 22.2 日期超過 30 天

回報：

- 實際要求天數。
- 最大限制。
- 不開始 Subagent。
- 不自動截斷。

## 22.3 標記損壞

以下情況必須停止：

- START 沒有 END。
- END 沒有 START。
- 重複日期。
- 重複 GENERATED。
- 重複 MANUAL。
- 日期標記與標題不一致。
- ENTRIES 標記不成對。
- 日期區段彼此交錯。

不得自動猜測修復。

可在 dry-run 中提供損壞位置與修復建議。

## 22.4 無法讀取程式碼

若因權限、檔案不存在、submodule 缺失或其他原因無法讀取：

- 記錄未分析的檔案。
- 降低 confidence。
- 在 uncertainties 中說明。
- 不得假裝已完成分析。

## 22.5 Subagent 失敗

若某日 Subagent 失敗：

- 不得用 commit message 取代。
- 其他日期可以繼續。
- 整體結果標示為部分完成。
- 預設禁止 apply。
- 顯示失敗日期與原因。

可讓使用者明確選擇：

~~~text
只寫入成功的日期
~~~

但必須重新顯示將寫入的日期與新的 preview ID。

---

# 23. Skill 目錄結構

~~~text
repo_worklog/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── resolve_date_range.py
│   ├── collect_git_history.py
│   ├── inspect_worktree.py
│   ├── build_analysis_manifest.py
│   ├── update_worklog.py
│   ├── validate_worklog.py
│   └── preview_state.py
└── references/
    ├── interaction-flow.md
    ├── date-parameter-contract.md
    ├── code-analysis-rules.md
    ├── subagent-contract.md
    ├── worklog-format.md
    └── provider-models.md
~~~

不需要 assets，除非日後要加入範例專案或模板檔。

---

# 24. 各檔案職責

## 24.1 `SKILL.md`

作為控制層，保持精簡，包含：

- Skill 觸發條件。
- `/repo_worklog` 無參數選單。
- 自然語言輸入流程。
- 日期模式。
- 最大 30 天限制。
- 逐日 Subagent 規則。
- 強制程式碼閱讀。
- dry-run 與 apply 流程。
- references 與 scripts 使用時機。

詳細規格不全部塞進 `SKILL.md`。

## 24.2 `agents/openai.yaml`

包含：

- 顯示名稱。
- 簡短描述。
- UI metadata。
- Skill 預設提示。
- `/repo_worklog` 呈現資訊。

建議顯示名稱：

~~~text
Repository Worklog
~~~

建議簡短描述：

~~~text
Analyze Git commits and source code by day, then preview and maintain a project worklog.
~~~

## 24.3 `scripts/resolve_date_range.py`

負責：

- 標準參數解析。
- `date`。
- `days`。
- `from` 與 `to`。
- `7d` 與 `30d`。
- 本地 timezone。
- 日期清單生成。
- 1 至 30 天限制。
- 衝突驗證。
- 無效日期驗證。

自然語言由模型轉換成標準參數；腳本不自行理解自由文字。

## 24.4 `scripts/collect_git_history.py`

負責：

- repository root。
- current branch。
- HEAD。
- detached HEAD。
- 按日取得 commits。
- commit metadata。
- changed files。
- rename 與 copy。
- merge metadata。
- revert 初步辨識。
- diff 索引。
- binary 狀態。

不負責撰寫摘要。

## 24.5 `scripts/inspect_worktree.py`

只在：

~~~text
include_uncommitted=true
~~~

時執行。

負責：

- staged diff。
- unstaged diff。
- untracked files。
- binary 判斷。
- working tree fingerprint。
- 檔案狀態分類。

## 24.6 `scripts/build_analysis_manifest.py`

為每一天建立分析 manifest，例如：

~~~json
{
  "date": "2026-07-15",
  "timezone": "Asia/Taipei",
  "commits": [],
  "changed_files": [],
  "file_groups": [],
  "required_context": [],
  "include_uncommitted": true,
  "provider": "codex",
  "model": "5.6-terra"
}
~~~

## 24.7 `scripts/update_worklog.py`

負責：

- 解析日誌標記。
- 模擬更新。
- 插入新日期。
- 覆蓋 GENERATED。
- 保留 MANUAL。
- 日期降冪排序。
- 暫存檔。
- 原子替換。

## 24.8 `scripts/validate_worklog.py`

負責：

- ENTRIES 標記。
- 日期 START / END。
- GENERATED。
- MANUAL。
- 日期唯一。
- 日期排序。
- 標記日期與標題一致。
- 人工內容完整。
- UTF-8。

## 24.9 `scripts/preview_state.py`

負責：

- 建立 preview fingerprint。
- 產生 preview ID。
- 保存 preview metadata。
- apply 前一致性驗證。
- 防止重複 apply。
- preview 過期處理。

---

# 25. References 職責

## 25.1 `interaction-flow.md`

包含：

- 無參數功能選單。
- 選項編號處理。
- 自然語言範例。
- 直接參數模式。
- dry-run。
- 使用者確認。
- apply。

## 25.2 `date-parameter-contract.md`

包含：

- 日期模式。
- 時區。
- 30 天限制。
- 衝突規則。
- 邊界案例。
- 自然語言正規化案例。

## 25.3 `code-analysis-rules.md`

包含：

- Git diff 閱讀要求。
- 程式碼上下文規則。
- 最終狀態判定。
- merge。
- revert。
- rename。
- binary。
- generated。
- lockfile。
- submodule。

## 25.4 `subagent-contract.md`

包含：

- Day Subagent prompt。
- Code Analysis Subagent prompt。
- 回傳 JSON schema。
- confidence。
- evidence。
- 禁止只看 commit message。
- 任務失敗處理。

## 25.5 `worklog-format.md`

包含：

- Markdown 模板。
- ENTRIES 標記。
- GENERATED。
- MANUAL。
- 日期排序。
- 插入與覆蓋規則。
- 空日期處理。

## 25.6 `provider-models.md`

包含：

- Claude Code：Sonnet 5。
- Codex：5.6 Terra。
- Gemini：Flash 3.0。
- runtime model ID。
- 模型不可用處理。
- 禁止自動切換昂貴模型。

---

# 26. 自然語言解析案例

## 26.1 今天

輸入：

~~~text
整理今天
~~~

正規化：

~~~text
date=<本地今天>
include_uncommitted=false
~~~

## 26.2 指定日期

輸入：

~~~text
幫我補 2026 年 7 月 1 日的日誌
~~~

正規化：

~~~text
date=2026-07-01
include_uncommitted=false
~~~

## 26.3 最近一週

輸入：

~~~text
整理最近一週
~~~

正規化：

~~~text
days=7
include_uncommitted=false
~~~

## 26.4 最近一個月

輸入：

~~~text
整理近一個月
~~~

正規化：

~~~text
days=30
include_uncommitted=false
~~~

## 26.5 自訂範圍

輸入：

~~~text
整理 2026 年 7 月 1 日到 7 月 10 日
~~~

正規化：

~~~text
from=2026-07-01
to=2026-07-10
include_uncommitted=false
~~~

## 26.6 包含未提交異動

輸入：

~~~text
整理今天，連還沒有 commit 的一起
~~~

正規化：

~~~text
date=<本地今天>
include_uncommitted=true
~~~

## 26.7 多日加未提交異動

輸入：

~~~text
整理最近七天，並包含目前 working tree
~~~

正規化：

~~~text
days=7
include_uncommitted=true
~~~

未提交內容只放入今天。

---

# 27. 驗收測試

## 27.1 無參數互動

輸入：

~~~text
/repo_worklog
~~~

預期：

- 顯示所有選項。
- 不掃描 Git。
- 不指派 Subagent。
- 不建立檔案。
- 等待自然語言或選項編號。

## 27.2 選項編號

輸入：

~~~text
3
~~~

預期正規化：

~~~text
days=7
~~~

輸入：

~~~text
2
~~~

預期詢問指定日期。

## 27.3 日期解析

測試：

- `date=2026-07-01`
- `days=1`
- `days=7`
- `days=30`
- `days=31`
- `7d`
- `30d`
- 單日 from/to
- 跨月
- 跨年
- 無效日期
- `from > to`
- `date + days`
- `to` 單獨存在

## 27.4 Git 情境

建立 fixture repositories，包含：

- 單一 commit。
- 同日多 commit。
- 先新增再 revert。
- rename。
- copy。
- merge。
- conflict resolution。
- migration。
- lockfile。
- binary。
- generated file。
- deleted file。
- empty commit。
- detached HEAD。
- submodule 更新。

驗證日誌描述最終程式碼狀態。

## 27.5 程式碼閱讀

驗證 Subagent：

- 實際讀取 diff。
- 讀取完整函式。
- 讀取直接呼叫端。
- 讀取直接依賴。
- 讀取測試。
- 不只重述 commit subject。

## 27.6 Working tree

測試：

- staged。
- unstaged。
- untracked。
- binary untracked。
- include 關閉。
- include 開啟。
- 多日範圍只歸入今天。

## 27.7 日誌更新

測試：

- 建立新檔。
- 插入最新日期。
- 插入中間日期。
- 插入最舊日期。
- 覆蓋 GENERATED。
- 保留 MANUAL。
- 保留文件外部人工內容。
- 損壞標記。
- 重複日期。
- 非 UTF-8。
- dry-run 不建立 docs 目錄。

## 27.8 Preview

測試：

- 正常 dry-run 後 apply。
- HEAD 改變。
- branch 改變。
- working tree 改變。
- 日誌被修改。
- preview 重複 apply。
- 錯誤 preview ID。
- preview 屬於不同 repository。
- preview 過期。

## 27.9 Subagent 失敗

測試：

- 單日分析失敗。
- Code Analysis Subagent 部分失敗。
- 多日中部分日期失敗。
- 確認預設禁止 apply。
- 使用者選擇只寫成功日期後產生新 preview。

---

# 28. 完成驗收標準

Skill 必須符合以下條件：

1. Skill 名稱為 `repo_worklog`。
2. 可透過 `/repo_worklog` 呼叫。
3. 無參數時顯示完整選項，不直接分析。
4. 使用者可輸入選項編號。
5. 使用者可使用自然語言。
6. 支援 `date`、`days`、`from`、`to`。
7. 支援 `7d`、`30d` 與單一日期快捷格式。
8. 最大日期範圍為 30 天。
9. 多日範圍一天一個 Day Subagent。
10. Claude Code 使用 Sonnet 5。
11. Codex 使用 5.6 Terra。
12. Gemini 使用 Flash 3.0。
13. 分析全專案，不依作者過濾。
14. 預設不包含未提交內容。
15. 支援 `include_uncommitted=true`。
16. 未提交內容只歸入今天。
17. 不得只讀 commit message。
18. 必須讀取實際 diff。
19. 必須閱讀必要的完整程式碼上下文。
20. 日誌以當日最終程式碼狀態為準。
21. 輸出為 Markdown。
22. 預設路徑為 `docs/PROJECT_WORKLOG.md`。
23. 最新日期排列在最上方。
24. 既有日期覆蓋 GENERATED。
25. MANUAL 內容永久保留。
26. 所有執行預設先 dry-run。
27. 使用者明確確認後才能寫入。
28. apply 前驗證 preview 未失效。
29. 寫入採暫存檔與原子替換。
30. 不自動執行 Git add、commit 或 push。
31. 分析不完整時預設禁止寫入。
32. 推論必須明確標示。
33. 無法讀取的內容不得假裝已分析。

---

# 29. 建議實作順序

## 第一階段：Skill 骨架

1. 使用 Skill 初始化工具建立 `repo_worklog`。
2. 建立 `SKILL.md`。
3. 建立 `agents/openai.yaml`。
4. 建立 scripts 與 references 目錄。
5. 移除不需要的範例檔。

## 第二階段：日期與 Git 基礎

1. 實作日期參數解析。
2. 實作 timezone。
3. 實作 30 天限制。
4. 實作 repository 偵測。
5. 實作按日 commit 收集。
6. 實作 working tree 收集。
7. 建立分析 manifest。

## 第三階段：工作日誌引擎

1. 實作 Markdown parser。
2. 實作標記驗證。
3. 實作 GENERATED 更新。
4. 實作 MANUAL 保留。
5. 實作日期排序。
6. 實作 dry-run 差異。
7. 實作安全寫入。

## 第四階段：單日分析

1. 定義 Day Subagent prompt。
2. 強制讀取 diff。
3. 強制程式碼上下文分析。
4. 定義 evidence。
5. 定義 confidence。
6. 實作最終狀態判定。
7. 實作結構化回傳。

## 第五階段：多日分析

1. 一天一個 Subagent。
2. 單日大型任務再分組。
3. 多日結果合併。
4. 無異動日期處理。
5. 部分失敗處理。
6. 30 天效能與成本測試。

## 第六階段：互動流程

1. `/repo_worklog` 無參數選單。
2. 選項編號。
3. 自然語言正規化。
4. 直接參數模式。
5. dry-run 顯示。
6. 自然語言確認寫入。
7. preview ID 與失效處理。

## 第七階段：多宿主適配

1. Claude Code / sonnet 5。
2. Codex / gpt-5.6 terra。
3. Gemini / gemini flash 3.0。
4. 驗證三個宿主皆遵循相同 Subagent contract。
5. 驗證模型不可用時不靜默 fallback。

## 第八階段：測試與封裝

1. 單元測試。
2. Git fixture 測試。
3. 日誌更新測試。
4. preview 一致性測試。
5. 多宿主測試。
6. Skill validator。
7. 封裝為 `skill.zip`。

---

# 30. 最終使用流程範例

使用者輸入：

~~~text
/repo_worklog
~~~

Skill 顯示所有選項，但不開始分析。

使用者輸入：

~~~text
整理最近 7 天，包含目前還沒有 commit 的修改
~~~

Skill 正規化為：

~~~text
days=7
include_uncommitted=true
~~~

接著：

1. 檢查日期不超過 30 天。
2. 取得本地時區。
3. 取得 repository、branch 與 HEAD。
4. 將最近 7 天拆成七個 Day Subagent。
5. 每個 Day Subagent 分析當日 commits。
6. 每個 Agent 讀取實際 diff 與程式碼。
7. 今天額外分析 working tree。
8. 合併每日結果。
9. 模擬更新 `docs/PROJECT_WORKLOG.md`。
10. 顯示完整 dry-run。
11. 顯示 preview ID。
12. 不修改任何檔案。

使用者輸入：

~~~text
確認寫入
~~~

Skill：

1. 驗證 HEAD、branch 與 working tree 未改變。
2. 驗證原工作日誌未改變。
3. 驗證 preview 尚未過期或使用。
4. 保留所有 MANUAL 內容。
5. 寫入 `docs/PROJECT_WORKLOG.md`。
6. 驗證日期排序與標記。
7. 顯示實際更新結果。
8. 不執行 Git commit 或 push。

以上即為 `repo_worklog` Skill 的完整最終計劃。