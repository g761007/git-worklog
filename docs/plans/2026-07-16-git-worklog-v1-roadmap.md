# Git Worklog v1.0 重構計畫

> 本文件為使用者於 2026-07-16 起草的 v1.0 重構路線圖原文(§1–§23,逐字保留),
> 加上兩個附錄:附錄 A 為對照程式碼實況後的修正,附錄 B 為已定案決策。
> 執行任何 PR 前,請以「原文 + 附錄修正」的合併結果為準。

## 1. 專案定位

**Git Worklog** 是一套以 Git 歷史與實際程式碼變更為依據,產生工程工作日誌、版本紀錄、交接摘要與技術報告的系統。

產品核心定位:

> Git Worklog is an evidence-based engine for generating engineering worklogs, reports, and changelogs from actual Git changes.

Git Worklog 不應只被定位成 ChatGPT Skill,而應以共用 Engine 為核心,提供多種操作介面:

~~~text
Git Repository
      │
      ▼
Git Worklog Engine
      │
 ┌────┼─────────────┐
 │    │             │
Skill CLI     Future Frontends
                  │
          GitHub Action / API
          VS Code / Web UI
~~~

---

# 2. 最終命名規範

## 2.1 品牌名稱

~~~text
Git Worklog
~~~

## 2.2 Repository

原名稱:

~~~text
repo_worklog_skill
~~~

新名稱:

~~~text
git-worklog
~~~

GitHub Repository:

~~~text
https://github.com/g761007/git-worklog
~~~

## 2.3 Skill

~~~yaml
name: git-worklog
~~~

Display Name:

~~~text
Git Worklog
~~~

Description:

~~~text
Generate evidence-based engineering worklogs, reports, changelogs, handoff summaries, contribution reports, and technical-debt reviews from actual Git history and source-code changes.
~~~

## 2.4 CLI

~~~text
git-worklog
~~~

未來預計支援:

~~~bash
git-worklog init
git-worklog generate
git-worklog report
git-worklog validate
git-worklog doctor
git-worklog preview
git-worklog apply
git-worklog migrate
git-worklog clean
git-worklog version
~~~

## 2.5 Python Package

~~~text
git_worklog
~~~

## 2.6 專案輸出目錄

原目錄:

~~~text
PROJECT_WORKLOG/
~~~

新目錄:

~~~text
.git-worklog/
~~~

## 2.7 使用者層級資料目錄

原目錄:

~~~text
~/.repo_worklog/
~~~

新目錄:

~~~text
~/.git-worklog/
~~~

---

# 3. 目標專案結構

> **修訂（2026-07-17,PR 7a）**:原規劃的 `skill/` + `git_worklog/` 平行拆分**已放棄**,
> 套件維持在 skill 目錄內。理由見 §3.1。以下為實際結構。

~~~text
git-worklog/                  # repo root
├── README.md
├── CHANGELOG.md
├── LICENSE
├── pyproject.toml
│
├── git-worklog/              # 整個目錄就是 skill(= Claude Code 的觸發名)
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── config/provider_models.json
│   ├── references/
│   ├── scripts/              # 套件的命令列薄殼
│   └── git_worklog/          # 引擎 + CLI,住在 skill 目錄「內」
│       ├── cli/
│       ├── analysis/         # history / manifest / results / worktree / refs / coverage
│       ├── markers.py  paths.py  language.py  config.py
│       ├── dates.py    providers.py  migrate.py
│       └── writer.py   preview.py
│
├── tests/
└── docs/
~~~

## 3.1 為何不拆 `skill/` + `git_worklog/`

§3 原本的平行佈局與 §14 的承諾互相矛盾:

- §14:「Standalone 模式應為選配功能,**不應成為 Skill 使用 CLI 的必要條件**」。
- SKILL.md 現在寫「nothing needs installing」,`python3 -m git_worklog` 從 skill 目錄
  直接可跑——這只在套件位於 skill 目錄內時成立。

一旦兩者變成 repo root 下的兄弟目錄,把 `skill/` 複製進 host 的 skills 資料夾就會得到
一個沒有引擎的 skill,`python3 -m git_worklog` 直接 import 失敗。要救只有兩條路:打包時
把套件 inline 進 staged 目錄(repo 佈局 ≠ 出貨佈局,且救不了 symlink 式的開發安裝),
或要求 `pip install`(直接違反 §14)。兩者都是拿真實的使用者體驗換一個目錄圖。

`pyproject.toml` 的註解在 PR 3 就標記了這顆地雷並留給 PR 7。PR 7a 的結論:**保留套件在
skill 目錄內,放棄 §3 的拆分**。§15.2 的 `repo_worklog/ → skill/` 一併作廢——目錄已於
PR 1 改名為 `git-worklog/`,那才是最終名稱(skill 目錄名 = 觸發名 = skill name)。

## 3.2 為何沒有 `engine/` `git/` `models/` `storage/` `utils/`

原規劃的五個子命名空間未建立。實際落點:

- `engine`/`git` → 已由 `analysis/` 承擔(history 就是 git 讀取層)。
- `storage` → `writer.py` + `preview.py`,兩個模組不需要一個目錄。
- `models` → 全流程以 dict + JSON schema 溝通,沒有 model class 可放。
- `report` → PR 8 的範圍,屆時若真的長出多種報告再建。
- `utils` → 沒有無處可去的東西;真有了再說。

為五個各只有一兩個模組的概念先建目錄,是替單一呼叫點造抽象。等某個概念大到目錄能還清
它的成本再拆。

---

# 4. `.git-worklog/` 目錄結構

~~~text
.git-worklog/
├── VERSION
├── config.json
├── index.md
│
├── days/
│   ├── 2026-07-14.md
│   ├── 2026-07-15.md
│   └── ...
│
├── reports/
│   ├── weekly/
│   ├── releases/
│   ├── contributors/
│   ├── handoff/
│   ├── timeline/
│   └── features/
│
├── analysis/
├── preview/
├── cache/
└── state/
~~~

## 4.1 每日工作日誌

~~~text
.git-worklog/days/YYYY-MM-DD.md
~~~

## 4.2 索引

~~~text
.git-worklog/index.md
~~~

## 4.3 報告

~~~text
.git-worklog/reports/
~~~

## 4.4 專案設定

~~~text
.git-worklog/config.json
~~~

初始格式:

~~~json
{
  "schema_version": 1,
  "timezone": "Asia/Taipei",
  "language": "auto",
  "index_language": "auto",
  "authors": [],
  "ignore": []
}
~~~

---

# 5. 使用者層級狀態目錄

~~~text
~/.git-worklog/
├── analysis/
├── previews/
├── logs/
├── cache/
└── tmp/
~~~

這些資料不應直接提交至目標 Git Repository。

## 5.1 權限要求

在支援 POSIX 權限的環境中:

- 目錄使用 `0700`
- 分析與 Preview 檔案使用 `0600`

## 5.2 清理指令

未來 CLI 應提供:

~~~bash
git-worklog clean analysis --older-than 30d
git-worklog clean previews --expired
git-worklog clean cache
~~~

---

# 6. 架構原則

## 6.1 Engine、CLI 與 LLM 的責任分工

CLI 不取代 LLM。

CLI 與 Engine 負責確定性工作:

- 日期與時區解析
- Git 歷史收集
- Commit 與檔案清單建立
- Analysis Manifest 建立
- 結果 Schema 驗證
- Evidence Coverage 驗證
- Preview 狀態管理
- Stale Preview 檢查
- Transactional Apply
- Index 重建
- Migration
- Report Scope 計算

Code Agent 的 LLM 負責語意分析:

- 閱讀實際 Patch
- 閱讀歷史版本的原始碼
- 理解程式行為改變
- 將變更歸納為工程工作項目
- 判斷同日新增、修改與 Revert 的最終狀態
- 辨識技術債、風險與不確定性
- 建立具體 Evidence

架構如下:

~~~text
User
  │
  ▼
Code Agent / ChatGPT Skill
  │
  ▼
git-worklog CLI
  ├── Collect Git history
  ├── Build analysis tasks
  ├── Define required evidence
  └── Provide result schema
          │
          ▼
      Agent LLM
          ├── Read patches
          ├── Read historical source code
          ├── Analyze semantics
          └── Write structured result
                  │
                  ▼
          git-worklog CLI
                  ├── Validate schema
                  ├── Validate coverage
                  ├── Build preview
                  └── Apply safely
~~~

## 6.2 分析與輸出語言策略

Git Worklog 的分析語言與使用者可見輸出語言,應以目前 Code Agent 或 Agent Host 的有效語言設定為主。

系統不得因為:

- Git Commit Message 使用英文
- 原始碼註解使用英文
- Skill 文件使用英文
- CLI 預設訊息使用英文
- Repository 的主要程式語言或文件語言

就自動將工作日誌與報告固定輸出為英文。

### 6.2.1 預設行為

未指定語言時,依下列優先順序決定輸出語言:

1. 使用者在本次要求中明確指定的語言
2. CLI 參數中的明確語言覆寫
3. 專案設定中的明確語言覆寫
4. 目前 Code Agent 或 Agent Host 提供的有效回覆語言設定
5. 當前對話中使用者主要使用的語言
6. Standalone CLI 的環境變數
7. 系統 Locale
8. 無法判定時使用英文

~~~text
Explicit user request
        ↓
CLI argument
        ↓
Project config
        ↓
Current Agent Host language
        ↓
Current conversation language
        ↓
Environment variable
        ↓
System locale
        ↓
English fallback
~~~

使用者於本次要求明確指定的語言,應始終具有最高優先權。

### 6.2.2 語言責任邊界

Agent Host 負責決定實際使用的自然語言。

Git Worklog CLI 與 Engine 負責:

- 接收已解析的語言資訊
- 將語言資訊寫入 Analysis Manifest
- 驗證同一 Run 的 Analysis Results 使用一致語言
- 將語言資訊保存於 Preview Record
- 確保 Apply 不會在確認後改變輸出語言
- 對 CLI 固定狀態訊息提供在地化能力
- 保持 JSON Key 與 API 欄位穩定

Agent LLM 負責:

- 使用指定語言撰寫摘要
- 使用指定語言撰寫工作項目
- 使用指定語言描述影響、風險、技術債與不確定性
- 保留程式碼符號、路徑、Commit Hash、API 名稱與專有名詞的原始形式
- 必要時使用指定語言解釋技術詞彙
- 不得翻譯識別符、檔案路徑或程式符號

### 6.2.3 語言與內容來源分離

來源資料可以包含多種語言:

- Commit Message
- Branch Name
- File Path
- Source Code
- Code Comment
- Issue 或 Ticket 標題
- Existing Worklog
- Pull Request 描述

來源資料的語言,不直接決定最終輸出語言。

例如:

~~~text
Commit Message: Fix token refresh race condition
Agent Language: zh-TW
~~~

輸出可為:

~~~text
修正 Token Refresh 的競態條件,避免多個更新請求同時覆寫憑證狀態。
~~~

Evidence 中仍保留原始識別資訊:

~~~json
{
  "commit": "abcdef123456",
  "file": "src/auth/token_manager.py",
  "symbol": "refresh_token"
}
~~~

### 6.2.4 語言代碼

內部統一使用 BCP 47 語言標籤,例如:

~~~text
en
en-US
zh-TW
zh-CN
ja
ko
de
fr
~~~

繁體中文預設使用:

~~~text
zh-TW
~~~

不得只使用含義模糊的值:

~~~text
zh
chinese
traditional
~~~

### 6.2.5 Agent-hosted 模式

在 Agent-hosted 模式中,CLI 通常無法直接讀取 Code Agent 的內部偏好設定。

因此 Skill 或 Agent 在呼叫 CLI 時,必須將已解析的有效語言明確傳入:

~~~bash
git-worklog analyze prepare \
  --from 2026-07-01 \
  --to 2026-07-07 \
  --language zh-TW
~~~

這裡的 `--language` 應由目前 Agent 根據下列資訊解析:

- 使用者明確要求
- Agent Host 的語言設定
- 目前對話語言
- 專案 Config 覆寫

CLI 不應自行從作業系統 Locale 推斷使用者希望的工作日誌語言,因為:

- 系統 Locale 不一定等於使用者的對話語言
- 遠端開發環境可能固定為英文
- Container 或 CI 常使用 `C` 或 `en_US`
- 同一位使用者可能在不同對話中要求不同語言
- Agent Host 可能有獨立於作業系統的語言偏好

### 6.2.6 Standalone CLI 模式

Standalone CLI 可接受:

~~~bash
git-worklog generate --language zh-TW
git-worklog report weekly --language en
~~~

設定優先順序:

1. Command-line `--language`
2. `.git-worklog/config.json`
3. `GIT_WORKLOG_LANGUAGE`
4. 系統 Locale
5. 英文

Standalone CLI 使用系統 Locale 只應作為低優先順序 fallback。

### 6.2.7 專案設定

`.git-worklog/config.json` 支援:

~~~json
{
  "schema_version": 1,
  "timezone": "Asia/Taipei",
  "language": "auto",
  "index_language": "auto",
  "authors": [],
  "ignore": []
}
~~~

`language` 支援值:

~~~text
auto
en
en-US
zh-TW
zh-CN
ja
ko
de
fr
...
~~~

`auto` 的意義:

- Agent-hosted 模式:由目前 Agent Host 決定,並在建立任務時傳入
- Standalone CLI 模式:依 CLI fallback 規則決定

專案 Config 不應覆蓋使用者於本次要求中明確指定的語言。

### 6.2.8 Analysis Manifest

Analysis Manifest 應加入:

~~~json
{
  "language": {
    "requested": "auto",
    "resolved": "zh-TW",
    "source": "agent-host",
    "fallback": "en"
  }
}
~~~

`source` 支援:

~~~text
user-request
cli-argument
project-config
environment
agent-host
conversation
system-locale
fallback
~~~

每個同一 Run 的 Task 原則上必須使用相同的 `resolved` 語言。

### 6.2.9 Analysis Result

Analysis Result 應加入:

~~~json
{
  "schema_version": 1,
  "run_id": "01JXYZ123",
  "date": "2026-07-15",
  "language": "zh-TW",
  "summary": "重構報告產生流程,並強化分析結果驗證。",
  "work_items": []
}
~~~

Collector 必須驗證:

- Result 是否包含語言欄位
- Result 語言是否符合 Manifest 的 `resolved`
- 同一 Run 是否出現非預期的混合語言
- 固定技術識別符是否被錯誤翻譯

不建議僅靠自然語言偵測器判定是否符合語言,因為工程內容本來就會包含大量英文識別符與技術名詞。

驗證應以結構契約為主,語言偵測只作為 Warning。

### 6.2.10 Preview 與 Apply

Preview Record 必須保存:

~~~json
{
  "language": {
    "resolved": "zh-TW",
    "source": "agent-host"
  }
}
~~~

Apply 時不得:

- 重新偵測語言
- 根據新的對話內容改變語言
- 重新翻譯已確認的 Preview
- 讓同一 Preview 中不同日期使用不同語言

若使用者在 Preview 後要求改變語言,必須:

1. 將原 Preview 標記為失效或取消
2. 使用新語言重新產生 Analysis Result 或 Rendered Output
3. 建立新的 Preview ID
4. 再次要求使用者確認

### 6.2.11 Daily Worklog 與 Report 語言

Daily Worklog 的 GENERATED 區段使用該次 Run 的解析語言。

MANUAL 區段必須逐字保留,不得因語言設定而翻譯或改寫。

~~~text
GENERATED section
→ 使用 resolved language

MANUAL section
→ 原文保留
~~~

Report 的預設語言:

1. 目前使用者或 Agent Host 的有效語言
2. 不必被既有 Daily Worklog 的語言綁定
3. 可讀取不同語言的 Daily Worklogs,再使用目前要求的語言輸出報告

例如:

~~~bash
git-worklog report release \
  --from-tag v1.0.0 \
  --to-tag v1.1.0 \
  --language en
~~~

即使來源 Daily Worklogs 為 `zh-TW`,Release Report 仍可輸出英文。

### 6.2.12 Index 語言

`.git-worklog/index.md` 需要採用穩定策略,避免每次由不同語言的 Agent 執行時反覆改寫表頭。

支援兩種模式。

#### 固定專案語言

由 Config 決定:

~~~json
{
  "index_language": "zh-TW"
}
~~~

適合將 `.git-worklog/` 提交到共享 Repository 的團隊。

#### 自動但首次固定

~~~json
{
  "index_language": "auto"
}
~~~

首次建立 Index 時保存解析語言,後續重建沿用,不因每次執行的 Agent 語言而改變。

建議預設採用首次建立後固定的策略。

### 6.2.13 CLI 系統訊息與內容語言分離

CLI 應區分:

- `content_language`:工作日誌與報告內容
- `interface_language`:CLI 狀態、錯誤與提示訊息

例如:

~~~bash
git-worklog generate \
  --language zh-TW \
  --interface-language en
~~~

第一階段可只完整支援英文 CLI 系統訊息,但不能因此讓產出的 Worklog 固定使用英文。

CLI JSON 模式中的機器欄位必須保持固定英文 Key:

~~~json
{
  "status": "success",
  "language": "zh-TW",
  "preview_id": "preview_01JABC456"
}
~~~

不得依語言翻譯 JSON Key,以維持 API 穩定性。

### 6.2.14 錯誤與警告

若無法解析 Agent Host 語言,CLI 應回傳結構化警告:

~~~json
{
  "code": "LANGUAGE_NOT_RESOLVED",
  "message": "No output language was provided; falling back to English.",
  "fallback_language": "en"
}
~~~

Agent 收到此警告後,若能從目前對話判定語言,應重新執行並明確傳入 `--language`,而不是直接接受錯誤的 fallback。

---

# 7. Agent-hosted 分析流程

Agent-hosted 模式是 Skill 與 Code Agent 的預設模式。

CLI 不需要自行呼叫模型 API,而是由目前宿主 Agent 的 LLM 完成分析。

## 7.1 建立分析任務

~~~bash
git-worklog analyze prepare \
  --from 2026-07-01 \
  --to 2026-07-07 \
  --language zh-TW
~~~

輸出範例:

~~~json
{
  "schema_version": 1,
  "run_id": "01JXYZ123",
  "language": {
    "requested": "auto",
    "resolved": "zh-TW",
    "source": "agent-host",
    "fallback": "en"
  },
  "tasks": [
    {
      "date": "2026-07-01",
      "manifest_path": "/home/user/.git-worklog/analysis/01JXYZ123/tasks/2026-07-01.json",
      "result_path": "/home/user/.git-worklog/analysis/01JXYZ123/results/2026-07-01.json"
    }
  ]
}
~~~

## 7.2 Agent 執行分析

Agent 必須:

1. 讀取每個 Task Manifest
2. 逐一檢查必要 Commit 與檔案
3. 使用歷史 Commit Tree,而不是目前 Checkout 的程式碼
4. 分析實際 Patch 與相關程式碼
5. 依 Manifest 的 `resolved` 語言撰寫結果
6. 將結果寫入指定的 `result_path`
7. 不得只根據 Commit Message 產生摘要
8. 不得翻譯檔案路徑、程式符號或 Commit Hash

## 7.3 收集分析結果

~~~bash
git-worklog analyze collect --run-id 01JXYZ123
~~~

CLI 應驗證:

- 每個日期是否都有結果
- JSON Schema 是否有效
- 日期與 Run ID 是否一致
- 語言是否符合 Manifest
- 同一 Run 的結果語言是否一致
- 必要 Commit 是否被覆蓋
- 必要 Commit/File Pair 是否有 Evidence
- Evidence 中的 Commit 是否存在
- Evidence 中的檔案是否屬於該 Commit
- 是否存在未知或遺漏的 Task

---

# 8. Analysis Manifest 規格

每個日期使用一份 Manifest。

~~~json
{
  "schema_version": 1,
  "run_id": "01JXYZ123",
  "date": "2026-07-15",
  "timezone": "Asia/Taipei",
  "language": {
    "requested": "auto",
    "resolved": "zh-TW",
    "source": "agent-host",
    "fallback": "en"
  },
  "repository": {
    "root": "/path/to/repository",
    "git_dir": "/path/to/repository/.git",
    "head": "abcdef123456",
    "branch": "main"
  },
  "commits": [
    {
      "hash": "abcdef123456",
      "author": "Developer",
      "author_email": "developer@example.com",
      "author_date": "2026-07-15T09:20:00+08:00",
      "committer_date": "2026-07-15T10:10:00+08:00",
      "subject": "Refactor report generation",
      "files": [
        {
          "path": "src/report.py",
          "status": "modified"
        }
      ]
    }
  ],
  "required_commit_file_pairs": [
    {
      "commit": "abcdef123456",
      "file": "src/report.py",
      "required": true
    }
  ],
  "analysis_rules": [
    "Read the actual patch.",
    "Read historical source code from the target commit.",
    "Do not rely only on commit messages.",
    "Describe the final state after all commits on the same day.",
    "Write all user-facing analysis using the resolved language.",
    "Preserve code symbols, file paths, commit hashes, and identifiers."
  ],
  "result_path": "/home/user/.git-worklog/analysis/01JXYZ123/results/2026-07-15.json"
}
~~~

---

# 9. Analysis Result 規格

~~~json
{
  "schema_version": 1,
  "run_id": "01JXYZ123",
  "date": "2026-07-15",
  "language": "zh-TW",
  "summary": "重構報告產生流程,並強化分析結果驗證。",
  "work_items": [
    {
      "title": "重構報告產生流程",
      "description": "將報告產生責任移入可重用模組,並簡化原有流程協調邏輯。",
      "impact": "Skill 與未來 CLI 指令可共用相同的報告產生能力。",
      "evidence": [
        {
          "commit": "abcdef123456",
          "file": "src/report.py",
          "symbol": "generate_report",
          "lines": "42-118",
          "note": "Introduced the reusable report generation entrypoint."
        }
      ]
    }
  ],
  "risks": [],
  "technical_debt": [],
  "uncertainties": []
}
~~~

---

# 10. Preview 與 Apply 設計

## 10.1 Preview 必須是不可變 Artifact

Preview Record 應保存:

- Repository Identity
- Repository Root
- Git Directory
- Branch
- HEAD
- Worktree Fingerprint
- Submodule Fingerprint
- Skill Version
- CLI Version
- Schema Version
- 執行參數
- 解析後語言
- 語言來源
- 完整 Daily Worklog Apply Payload
- 完整 Index Apply Payload
- Analysis Result Hash
- 每個輸出檔案的 SHA-256
- Preview 建立時間
- Preview 到期時間
- Apply 狀態

Preview 不能只保存參數,再由 Agent 於確認後重新產生內容。

## 10.2 建立 Preview

~~~bash
git-worklog preview --run-id 01JXYZ123
~~~

輸出:

~~~json
{
  "preview_id": "preview_01JABC456",
  "status": "pending",
  "language": {
    "resolved": "zh-TW",
    "source": "agent-host"
  },
  "files": [
    {
      "path": ".git-worklog/days/2026-07-15.md",
      "action": "create"
    },
    {
      "path": ".git-worklog/index.md",
      "action": "update"
    }
  ]
}
~~~

## 10.3 Apply

使用者明確確認後:

~~~bash
git-worklog apply --preview-id preview_01JABC456
~~~

Apply 前必須重新驗證:

- Repository Identity
- HEAD
- Branch
- Working Tree
- 目標檔案 Hash
- `.git-worklog/` 檔案集合
- Preview 是否過期
- Preview 是否已套用
- Analysis Result 是否被修改
- Preview 語言是否未被變更

任一驗證失敗時,必須拒絕 Apply 並要求重新建立 Preview。

---

# 11. Report 架構

正式 Report Module:

~~~text
git_worklog/report/
├── weekly.py
├── release.py
├── contributor.py
├── handoff.py
├── timeline.py
├── feature.py
└── technical_debt.py
~~~

CLI:

~~~bash
git-worklog report weekly
git-worklog report release --from-tag v1.0.0 --to-tag v1.1.0
git-worklog report contributor --author developer@example.com
git-worklog report handoff --days 30
git-worklog report timeline --feature authentication
git-worklog report technical-debt
~~~

指定輸出語言:

~~~bash
git-worklog report weekly --language zh-TW
git-worklog report release --language en
~~~

輸出預設寫入:

~~~text
.git-worklog/reports/
~~~

---

# 12. CLI 初始指令設計

## 12.1 第一階段

先建立最小可用 CLI:

~~~bash
git-worklog version
git-worklog doctor
git-worklog validate
~~~

### `git-worklog version`

顯示:

- CLI Version
- Engine Version
- Schema Version
- Skill Compatibility Version

### `git-worklog doctor`

檢查:

- Python 版本
- Git 版本
- 是否位於 Git Repository
- Repository 是否為 Shallow Clone
- Working Tree 狀態
- `.git-worklog/` 是否有效
- Config 是否有效
- 使用者資料目錄權限
- Skill 與 CLI 是否相容
- 語言設定是否有效
- `index_language` 是否有效

### `git-worklog validate`

驗證:

- Daily Worklog 格式
- GENERATED/MANUAL Marker
- Index
- Config
- Preview Records
- Analysis Results
- Evidence Links
- 語言欄位
- 同一 Run 的語言一致性

## 12.2 第二階段

~~~bash
git-worklog init
git-worklog analyze prepare
git-worklog analyze collect
git-worklog preview
git-worklog apply
~~~

## 12.3 第三階段

~~~bash
git-worklog generate
git-worklog report
git-worklog migrate
git-worklog clean
~~~

---

# 13. Skill 精簡目標

未來 `SKILL.md` 應只負責高階流程,不再逐一呼叫大量 Python Scripts。

目標流程:

1. 解析目前使用者與 Agent Host 的有效語言
2. 執行 `git-worklog analyze prepare`
3. 透過 `--language` 明確傳入解析後語言
4. 讀取產生的 Analysis Tasks
5. 使用 Agent LLM 分析每個日期的 Git Patch 與歷史程式碼
6. 將結構化結果寫入 Task 指定位置
7. 執行 `git-worklog analyze collect`
8. 執行 `git-worklog preview`
9. 向使用者顯示完整 Preview
10. 僅在使用者明確確認後執行 `git-worklog apply`

Skill 不應再直接管理:

- 日期運算
- Git Commit 收集
- Preview Hash
- Apply Payload
- Index 重建
- Rollback
- Migration State
- Validation State
- 語言持久化
- Apply 時的語言一致性

這些責任全部移交 CLI 與 Engine。

---

# 14. Standalone CLI 模式

Agent-hosted 模式完成後,可選擇支援 Standalone CLI。

~~~bash
git-worklog generate --provider openai
git-worklog generate --provider anthropic
git-worklog generate --provider local
~~~

指定語言:

~~~bash
git-worklog generate \
  --provider openai \
  --language zh-TW
~~~

模型層應使用 Adapter Pattern:

~~~python
from typing import Protocol


class Analyzer(Protocol):
    def analyze(self, task: "AnalysisTask") -> "AnalysisResult":
        ...
~~~

可能的實作:

~~~text
AgentHostedAnalyzer
OpenAIAnalyzer
AnthropicAnalyzer
LocalAnalyzer
FixtureAnalyzer
~~~

核心 Engine 不得直接綁定單一模型供應商。

Standalone 模式應為選配功能,不應成為 Skill 使用 CLI 的必要條件。

---

# 15. Migration 設計

## 15.1 Repository Rename

~~~text
repo_worklog_skill
→
git-worklog
~~~

## 15.2 Skill Directory Rename

> **修訂(2026-07-17,PR 7a)**:已完成,且**不再有第二階段**。

~~~text
repo_worklog/
→
git-worklog/            # PR 1 完成,即最終名稱
~~~

原文把 `git-worklog/` 當成過渡、最終要拆成 `skill/` + `git_worklog/`。該拆分已放棄
(理由見 §3.1:與 §14 的「不需安裝」承諾衝突)。`git-worklog/` 是終點——skill 目錄名
必須等於 Claude Code 的觸發名,也等於 skill name。

## 15.3 Python 名稱

~~~text
repo_worklog
→
git_worklog
~~~

## 15.4 Environment Variables

~~~text
REPO_WORKLOG_HOME
→
GIT_WORKLOG_HOME
~~~

新增:

~~~text
GIT_WORKLOG_LANGUAGE
~~~

過渡版本可同時支援舊 Home 變數:

1. 優先讀取 `GIT_WORKLOG_HOME`
2. 若不存在則讀取 `REPO_WORKLOG_HOME`
3. 顯示 Deprecated Warning
4. v2.0 移除舊名稱

## 15.5 專案資料目錄

~~~text
PROJECT_WORKLOG/
→
.git-worklog/
~~~

Daily Files:

~~~text
PROJECT_WORKLOG/YYYY-MM-DD.md
→
.git-worklog/days/YYYY-MM-DD.md
~~~

Index:

~~~text
PROJECT_WORKLOG/index.md
→
.git-worklog/index.md
~~~

## 15.6 使用者狀態目錄

~~~text
~/.repo_worklog/
→
~/.git-worklog/
~~~

---

# 16. Migration Command

~~~bash
git-worklog migrate
~~~

Migration 必須:

1. 檢查來源目錄是否存在
2. 檢查目標目錄是否已存在
3. 建立 Migration Preview
4. 顯示將移動與修改的檔案
5. 要求明確確認
6. 使用 Transactional Apply
7. 失敗時 Rollback
8. 驗證新目錄格式
9. 保留 Manual Sections
10. 不覆蓋衝突檔案
11. 保留既有 Worklog 的原始語言
12. 不因 Migration 自動翻譯既有內容

支援:

~~~bash
git-worklog migrate --from-project-worklog
git-worklog migrate --from-repo-worklog-home
git-worklog migrate --dry-run
~~~

---

# 17. 分階段 PR 計畫

## PR 1:品牌與公開名稱重構

風險:低

內容:

- Repository 改名為 `git-worklog`
- README 標題與產品描述更新
- Skill Name 改為 `git-worklog`
- Display Name 改為 `Git Worklog`
- 更新文件中的品牌名稱
- 更新 Badge 與連結
- 增加命名規範文件
- 暫時保留既有執行路徑相容性

驗收:

- 文件不再以 `repo_worklog_skill` 作為產品名稱
- Skill 可被正常載入
- 所有測試通過

## PR 2:`.git-worklog/` 目錄與 Migration

風險:中

內容:

- `PROJECT_WORKLOG/` 改為 `.git-worklog/`
- Daily Files 移至 `.git-worklog/days/`
- Index 移至 `.git-worklog/index.md`
- 新增 `config.json`
- 新增 `VERSION`
- 實作舊目錄 Migration
- 更新相關測試
- 保留舊格式讀取相容性

驗收:

- 新專案使用新目錄
- 舊專案可安全 Migration
- Manual Content 不遺失
- 既有語言內容不被改寫
- Preview 與 Apply 可正確處理新路徑

## PR 3:CLI 基礎架構

風險:中

內容:

- 新增 `pyproject.toml`
- 建立 `git_worklog` Python Package
- 建立 Console Entry Point
- 實作:
  - `git-worklog version`
  - `git-worklog doctor`
  - `git-worklog validate`
- 保留既有 Scripts Wrapper
- 建立 CLI Integration Tests

驗收:

~~~bash
git-worklog version
git-worklog doctor
git-worklog validate
~~~

皆可在支援環境執行。

## PR 4:Language Resolution and Output Contract

風險:中

內容:

- 新增 BCP 47 語言欄位
- 新增 `--language`
- 新增 `--interface-language`
- 新增 `GIT_WORKLOG_LANGUAGE`
- Config 新增 `language`
- Config 新增 `index_language`
- Manifest 新增 requested、resolved、source、fallback
- Result Schema 新增語言
- Preview 保存語言
- Collector 驗證語言一致性
- Daily Worklog 使用解析後語言
- Report 支援指定輸出語言
- MANUAL 區段永遠保持原文
- Index 採用穩定語言策略
- 新增語言相關測試

驗收:

- Agent Host 使用繁體中文時,產出預設為 `zh-TW`
- Agent Host 使用英文時,產出預設為英文
- 使用者明確指定語言時可覆蓋預設
- Commit Message 語言不影響輸出語言
- Preview 與 Apply 語言完全一致
- Report 可使用不同於 Daily Worklog 的輸出語言
- 不翻譯檔案路徑、程式符號與 Commit Hash

## PR 5:Agent-hosted Analysis Pipeline

風險:高

內容:

- 實作 `analyze prepare`
- 實作 Analysis Manifest
- 實作 Result Schema
- 實作 `analyze collect`
- 實作 Evidence Coverage Validation
- Skill 改用 CLI 建立分析任務
- Agent LLM 維持語意分析責任
- Skill 明確傳入解析後語言

驗收:

- Code Agent 可透過自身 LLM 完成分析
- CLI 不需要模型 API Key
- 缺少 Evidence 時 CLI 會拒絕結果
- 不完整日期不能進入 Preview
- 同一 Run 語言不一致時拒絕 Collect

## PR 6:Immutable Preview 與 State Machine

風險:高

內容:

- Preview 保存完整 Apply Payload
- Preview 保存解析後語言
- 實作 Preview TTL
- 實作 Repository Fingerprint
- 實作 Concurrent Apply Lock
- 實作 Preview State Machine
- Apply 不再依賴 Agent 對話內容
- 實作 Transactional Apply 與 Rollback
- 語言變更時強制建立新 Preview

狀態:

~~~text
prepared
  ↓
analyzing
  ↓
collected
  ↓
previewed
  ↓
confirmed
  ↓
applied
~~~

錯誤狀態:

~~~text
failed
stale
expired
cancelled
~~~

## PR 7:Engine 模組化

風險:高

內容:

- 將 Scripts 內的商業邏輯移入 `git_worklog/`
- Scripts 僅保留相容 Wrapper
- 建立:
  - `engine`
  - `git`
  - `models`
  - `storage`
  - `report`
- Skill 僅呼叫公開 CLI
- 移除重複流程邏輯

## PR 8:Report Architecture

風險:中

內容:

- Weekly Report
- Release Report
- Contributor Report
- Handoff Report
- Timeline Report
- Technical Debt Report
- 統一 Report Output Schema
- 支援 Markdown 與 JSON 輸出
- 支援獨立指定 Report 輸出語言

## PR 9:Standalone Provider Adapters

風險:中至高

內容:

- Provider-neutral Analyzer Interface
- OpenAI Adapter
- Anthropic Adapter
- Local Adapter
- Provider Availability Detection
- API Key 與隱私文件
- Cost Controls
- Provider 與語言設定分離

此 PR 不阻塞 Skill 與 Agent-hosted CLI 的正式發布。

---

# 18. 建議版本策略

## v0.5

- 完成品牌 Rename
- Repository 改為 `git-worklog`
- Skill 改為 `git-worklog`
- 新增命名與 Migration 文件

## v0.6

- `.git-worklog/`
- `days/`
- `reports/`
- Config
- Migration

## v0.7

- CLI Foundation
- `version`
- `doctor`
- `validate`

## v0.8

- Language Resolution
- BCP 47 Contract
- `--language`
- Manifest 與 Result 語言欄位
- Index 語言策略

## v0.9

- Agent-hosted Analysis Pipeline
- Manifest
- Result Schema
- Coverage Validation
- Immutable Preview
- State Machine
- CLI-driven Skill

## v1.0

- Stable Engine API
- Stable CLI
- Stable Skill
- Stable Migration
- Stable Language Contract
- Report Architecture
- 完整文件與相容性矩陣

---

# 19. 不在第一階段處理的項目

以下項目先不納入品牌 Rename PR:

- 直接串接 OpenAI API
- 直接串接 Anthropic API
- Web UI
- VS Code Extension
- GitHub Action
- 遠端同步
- 團隊帳號系統
- Database
- SaaS Hosting
- 全面重寫所有 Scripts
- 修改 Daily Worklog Markdown Schema
- 完整 CLI 多語系介面
- 自動翻譯既有 Worklog

優先確保:

1. Rename 安全
2. Migration 安全
3. 現有功能不退化
4. Agent LLM 分析能力保留
5. CLI 與 Skill 可以逐步共用 Engine
6. 分析與輸出語言契約明確
7. Preview 與 Apply 語言一致

---

# 20. 核心設計決策

## 決策一:產品名稱統一為 Git Worklog

所有公開介面統一使用:

~~~text
Git Worklog
git-worklog
git_worklog
.git-worklog/
~/.git-worklog/
~~~

## 決策二:Repository 使用產品名稱

~~~text
git-worklog
~~~

不使用:

~~~text
git-worklog-skill
git-worklog-cli
~~~

目前採 Monorepo,將 Skill、CLI 與 Engine 集中管理。

## 決策三:`.git-worklog/` 是專案資料目錄

它包含可提交至 Git 的:

- Daily Worklogs
- Index
- Reports
- Config
- Version Metadata

暫存與可能敏感的執行資料原則上放在:

~~~text
~/.git-worklog/
~~~

## 決策四:LLM 分析能力保留在 Agent

將流程改為 CLI 後,Code Agent 仍使用自身 LLM 分析程式碼。

CLI 不應把語意分析退化成 Commit Message 摘要。

## 決策五:CLI 管理流程與安全性

CLI 是 Workflow Control Plane,負責:

- 任務建立
- Schema
- Validation
- Preview
- Apply
- State
- Migration
- Reports
- 語言契約
- 語言一致性

## 決策六:Standalone LLM Provider 為選配

Standalone CLI 可以在未來加入模型 Adapter,但不能讓核心 Engine 綁定特定 Provider。

## 決策七:輸出語言預設繼承目前 Agent Host

Git Worklog 在 Agent-hosted 模式中,預設使用目前 Code Agent 或 Agent Host 的有效回覆語言。

Agent 必須將解析後的 BCP 47 語言代碼明確傳給 CLI。

CLI 不應依 Commit Message 或系統 Locale 自行猜測內容語言。

## 決策八:語言是 Preview 契約的一部分

Preview 建立後,輸出語言不得改變。

切換語言必須重新建立 Preview。

## 決策九:來源語言與輸出語言分離

Git 歷史、Commit Message、原始碼與既有文件使用何種語言,不影響工作日誌與報告的輸出語言。

## 決策十:Manual Content 不自動翻譯

任何既有 MANUAL 區段都必須逐字保留。

## 決策十一:CLI 介面語言與內容語言分離

CLI 狀態訊息可使用一種語言,工作日誌內容可使用另一種語言。

JSON Key 永遠保持英文與穩定格式。

## 決策十二:Index 語言必須穩定

Index 不得因不同 Code Agent 的語言設定而在每次重建時反覆改寫。

---

# 21. 測試策略

## 21.1 品牌與路徑測試

- Repository 名稱相關文件
- Skill Name
- Python Package Import
- CLI Entry Point
- `.git-worklog/` 路徑
- 舊路徑 Migration
- `GIT_WORKLOG_HOME`
- 舊 Environment Variable 相容性

## 21.2 Pipeline 測試

- Single-day Analysis
- Multi-day Analysis
- Empty Day
- Revert
- Rename
- Binary File
- Merge Commit
- Detached HEAD
- Shallow Clone
- Worktree
- Submodule
- Dirty Working Tree
- Concurrent Apply
- Preview Expiration
- Preview Reuse
- Transaction Rollback

## 21.3 Evidence Coverage 測試

- 每個 Commit 至少有 Evidence
- 每個必要 Commit/File Pair 被覆蓋
- Evidence Commit 不存在
- Evidence File 不屬於 Commit
- Rename 前後路徑
- Binary Classification
- Ignored File Reason
- Partial Result
- Missing Task

## 21.4 語言測試

新增以下測試:

- 使用者明確指定 `zh-TW`
- 使用者明確指定英文
- Agent Host 設定為 `zh-TW`
- Config 設為 `auto`
- Config 固定為 `ja`
- CLI Argument 覆蓋 Config
- 使用者本次要求覆蓋專案預設
- Commit Message 全英文但輸出為繁體中文
- Commit Message 中英混合
- 原始碼含大量英文識別符
- MANUAL 區段語言不同但內容保持不變
- Report 語言與 Daily Worklog 不同
- Preview 後要求切換語言
- 多日 Task 結果語言不一致
- Index 不因不同 Agent 語言反覆變更
- 無法判定語言時使用英文並回傳 Warning
- 非 ASCII 語言內容的 UTF-8 寫入與讀取
- `zh-TW`、`zh-CN` 不得被視為相同設定
- CLI Interface Language 與 Content Language 不同
- JSON Key 不隨語言變化
- Migration 不翻譯既有 Worklog

---

# 22. v1.0 Definition of Done

Git Worklog v1.0 完成時,應符合:

## 22.1 命名與結構

- [ ] Repository 名稱為 `git-worklog`
- [ ] Skill Name 為 `git-worklog`
- [ ] Display Name 為 `Git Worklog`
- [ ] Python Package 為 `git_worklog`
- [ ] CLI 指令為 `git-worklog`
- [ ] 專案輸出使用 `.git-worklog/`
- [ ] Daily Files 使用 `.git-worklog/days/`
- [ ] Reports 使用 `.git-worklog/reports/`
- [ ] 使用者狀態使用 `~/.git-worklog/`
- [ ] 舊格式可安全 Migration

## 22.2 Engine 與 CLI

- [ ] Skill 透過 CLI 執行確定性流程
- [ ] Agent LLM 繼續負責程式語意分析
- [ ] CLI 驗證 Evidence Coverage
- [ ] Preview 保存完整不可變 Apply Payload
- [ ] Apply 不依賴對話上下文
- [ ] 支援 Transactional Apply 與 Rollback
- [ ] 支援 Concurrent Apply Lock
- [ ] 支援 `doctor`
- [ ] 支援 `validate`
- [ ] 支援 Weekly 與 Release Reports
- [ ] Engine、CLI 與 Skill 的責任界線清楚

## 22.3 語言

- [ ] 支援 BCP 47 語言代碼
- [ ] Agent-hosted 模式預設繼承目前 Agent Host 語言
- [ ] Skill 將解析後語言明確傳給 CLI
- [ ] 支援 `--language`
- [ ] 支援 `--interface-language`
- [ ] 支援 `GIT_WORKLOG_LANGUAGE`
- [ ] Config 支援 `language`
- [ ] Config 支援 `index_language`
- [ ] Manifest 保存 requested、resolved、source 與 fallback
- [ ] Result Schema 保存輸出語言
- [ ] Collector 驗證同一 Run 的語言一致性
- [ ] Preview 保存語言並禁止 Apply 時改變
- [ ] Daily Worklog 使用解析後語言
- [ ] Report 可獨立指定輸出語言
- [ ] Commit Message 語言不會決定輸出語言
- [ ] 程式符號、檔案路徑與 Commit Hash 保持原文
- [ ] MANUAL 區段不被翻譯
- [ ] Index 語言不會因不同 Agent Host 反覆變更
- [ ] CLI JSON Key 不依語言變化
- [ ] 無法解析語言時回傳 Warning 並使用英文 fallback

## 22.4 品質與文件

- [ ] 所有測試通過
- [ ] README 完整
- [ ] Migration Guide 完整
- [ ] CLI Reference 完整
- [ ] Language Contract 文件完整
- [ ] Skill Compatibility Matrix 完整
- [ ] Provider Adapter 文件完整
- [ ] 隱私、資料保留與清理文件完整

---

# 23. 最終目標架構

~~~text
                         User
                           │
                           ▼
                 Code Agent / Skill
                           │
              Resolve language and intent
                           │
                           ▼
                    git-worklog CLI
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
     Git Collector    State Machine    Report Engine
          │                │                │
          ▼                ▼                ▼
  Analysis Manifest   Preview / Apply   Report Scope
          │
          ▼
      Agent LLM
          │
   Semantic analysis
          │
          ▼
  Analysis Result JSON
          │
          ▼
 Validation and Coverage
          │
          ▼
  Immutable Preview Artifact
          │
   Explicit user confirmation
          │
          ▼
   Transactional Apply
          │
          ▼
      .git-worklog/
~~~

Git Worklog v1.0 的核心原則:

> CLI 負責決定要分析什麼、如何驗證、何時可以安全寫入;Agent LLM 負責理解這些程式變更代表什麼。

語言原則:

> 分析與使用者可見輸出的語言,預設繼承目前 Code Agent 的有效語言設定,並由 Agent 明確傳入 CLI;來源程式碼與 Commit Message 的語言不決定最終輸出語言。

---

# 附錄 A:現況對照與修正(2026-07-16)

以下為 2026-07-16 對照 commit `28bfa85` 工作樹的 read-only 盤查結果。執行各 PR 時,以本附錄修正原文對應章節。

## A1. §15.4 的 `REPO_WORKLOG_HOME` 環境變數不存在

使用者層級路徑目前是硬編碼,沒有任何環境變數:

- `repo_worklog/scripts/preview_state.py:43` — `STATE_DIR = ~/.repo_worklog/previews`
- `repo_worklog/scripts/collect_day_results.py:48` — `ANALYSIS_DIR = ~/.repo_worklog/analysis`

因此 `GIT_WORKLOG_HOME` 是**新增**而非改名。§15.4 的過渡策略修正為:

1. 優先讀取 `GIT_WORKLOG_HOME`
2. 若未設定,使用預設 `~/.git-worklog/`
3. 若新目錄不存在但硬編碼的舊路徑 `~/.repo_worklog/` 存在,fallback 讀取並顯示 migration 提示
4. v2.0 移除舊路徑 fallback

## A2. PR 1 的實際 rename 面比原文預估小

`repo_worklog_skill` 字串只出現在:

- `CHANGELOG.md`(5 處,多為歷史紀錄——**不改寫歷史條目**,只修改改名後會失效的連結)
- git remote URL(`gh repo rename` 後由 GitHub 自動轉址,本地 remote 同步更新)

真正的 PR 1 命名面是:

- `repo_worklog/SKILL.md` frontmatter:`name: repo_worklog`
- `repo_worklog/agents/openai.yaml`:`name: repo_worklog`、`display_name: Repository Worklog`、`command: /repo_worklog`
- `README.md` 標題(`# repo_worklog skill`)與產品描述(雙語,英文與繁體中文區段都要改)

## A3. `PROJECT_WORKLOG` → `.git-worklog/` 屬於 PR 2,不是 PR 1

Runtime 有單一定義點:`repo_worklog/scripts/worklog_markers.py:58`(`WORKLOG_DIRNAME = "PROJECT_WORKLOG"`),8 個 scripts 經 `--dir` 參數引用此預設值。

但文件層大量硬寫名稱,PR 2 必須文件與程式同步改:

- `repo_worklog/SKILL.md`:13 處
- `README.md`:16 處
- `repo_worklog/references/`:共 33 處(worklog-format.md 11、interaction-flow.md 14、report-mode.md 6、code-analysis-rules.md 1、subagent-contract.md 1)
- `tests/`:12 處(helpers.py 3、test_worklog_engine.py 3、test_report_scope.py 3、test_migrate.py 2、test_pipeline.py 1)
- `repo_worklog/agents/openai.yaml`:2 處

## A4. 本專案自身的 dogfooding 資料也要 migration

Repo 根目錄已提交 `PROJECT_WORKLOG/`(本專案自己的工作日誌,2026-07-15、2026-07-16)。PR 2 必須用新的 migration 流程把它遷移到 `.git-worklog/`,作為 migration 的第一個實測案例。原文 §16 未提及此項。

## A5. CI 路徑寫死,目錄改名的 PR 必須同步更新

`.github/workflows/ci.yml` 的 byte-compile 與 smoke-test 步驟硬寫 `repo_worklog/scripts/*.py`。任何移動 scripts 目錄的 PR(PR 3、PR 7)必須在同一個 PR 內更新 CI,否則 CI 直接失敗。CI 目前跑 Python 3.9 / 3.12 / 3.13,3.9 是文件承諾的最低版本——新增的 CLI 與 package 程式碼必須維持 3.9 相容。

## A6. 測試以 sys.path 注入 + subprocess 呼叫 scripts

`tests/helpers.py:18-21` 定義 `SCRIPTS = <root>/repo_worklog/scripts` 並注入 `sys.path` 後 `import worklog_markers`;各測試經 `run_script()` 以 subprocess 呼叫 scripts。PR 3 建立 `git_worklog` package 時這是結構性風險點:需保留 scripts wrapper 相容,或在同 PR 改寫 helpers 的 import 與呼叫路徑。

## A7. 目前完全沒有語言處理邏輯

對 `repo_worklog/scripts/*.py` 與 `repo_worklog/config/*.json` 全面 grep 確認:沒有任何 language/locale 相關程式碼。PR 4 是 100% 新工作,不是改造既有功能,估點與排程時以此為準。

## A8. skill.zip 目前是手動打包,無 build script

既然只 ship v1.0(見附錄 B),打包腳本排入 PR 3 或 PR 7 完成即可。打包時需把 skill 目錄 stage 成 `git-worklog/`,讓使用者解壓安裝後的目錄名(= Claude Code 的觸發名)與 skill name 一致。

## A9. 版本策略修正:v0.5–v0.9 不對外發布

- v0.5–v0.9 為內部里程碑:不建 GitHub Release、不出 skill.zip、tag 可選
- `CHANGELOG.md` 持續累積在 `[Unreleased]`,v1.0 發布時一次 cut
- `repo_worklog/agents/openai.yaml` 的 `version:`(現為 `0.4.0`)在中間 PR 不逐版遞增,v1.0 時一次調整
- 對外可見的最後發布版本維持 v0.4.0,直到 v1.0 就緒

## A10. Plan 檔存放慣例

本專案既有慣例是 `docs/plans/`(已有 2026-07-15、2026-07-16 各一份),與全域規範的 `plans/` 不同。依「專案慣例優先」原則,所有計畫文件放 `docs/plans/`。

---

# 附錄 B:已定案決策(2026-07-16)

1. **2026-07-16 的 session 為純規劃階段**:交付本路線圖文件與 GitHub tracking issues,不修改任何程式碼。PR 1 的實際執行留待後續 session。
2. **GitHub repository 改名由 Claude 執行**:在執行 PR 1 的 session 中以 `gh repo rename git-worklog` 改名,並同步更新本地 git remote URL。舊 URL 由 GitHub 自動轉址。
3. **PR 1 只改名稱、不動目錄**:SKILL.md frontmatter、openai.yaml、README 改為 git-worklog / Git Worklog;repo 內目錄 `repo_worklog/` 暫時保留(CI、測試路徑不動)。目錄拆分為 `skill/` + `git_worklog/` 依 §15.2 的最終佈局於 PR 7 進行。
4. **只有 v1.0 會正式對外發布**:v0.5–v0.9 為內部里程碑(詳見附錄 A9)。
5. **本地資料夾改名**(`~/Documents/program/projects/repo_worklog_skill`)由使用者自行擇時處理,不納入任何 PR。
