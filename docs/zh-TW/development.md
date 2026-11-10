# 開發

**語言：** [English](../development.md) · 繁體中文 — [← 回到 README](../../README.zh-TW.md)

## 目錄結構

- `git-worklog/`：整個目錄就是 skill 本體。
  - `SKILL.md`：控制層——觸發條件、流程、腳本與 references 對照。
  - `agents/openai.yaml`：宿主 manifest——顯示名稱、UI metadata、model_config 指標。
  - `scripts/`：套件的命令列薄殼（僅用標準庫，各自輸出單一 JSON）。
    - `resolve_provider_model.py`：依宿主解析 provider／模型（覆寫、escalation、halt-and-ask）。
    - `resolve_date_range.py`：日期／時區解析、日數上限（`--max-days`，預設 30）、逐日半開區間。
    - `resolve_ref_range.py`：報告模式——把 tag／ref 解析成權威的 commit 集合與對應日期。
    - `check_worklog_coverage.py`：報告模式——逐日覆蓋狀態（covered／gap／no-commits）。
    - `collect_git_history.py`：repo 中繼資料與逐日 commit 事實（不摘要、不依作者過濾）。
    - `inspect_worktree.py`：staged／unstaged／untracked 與 worktree 指紋。
    - `build_analysis_manifest.py`：單日 manifest（`analyze prepare` 一次處理整個範圍）。
    - `collect_day_results.py`：扁平目錄的結果驗證。它看不到 manifest，因此無法檢查覆蓋率，也不假裝檢查；請優先用 `analyze collect`。
    - `update_daily_worklog.py`：建立／覆蓋每日檔案（交易式）、保留 MANUAL。
    - `rebuild_worklog_index.py`：由日期檔重建 index.md、保留索引 MANUAL。
    - `validate_daily_worklog.py`：每日檔案的標記／標題／UTF-8 驗證。
    - `validate_worklog_index.py`：索引標記／排序／連結／UTF-8 驗證。
    - `migrate_legacy_worklog.py`：一次性把舊單檔拆成目錄式。
    - `worklog_markers.py`：相容轉接層，實際模組為 `git_worklog.markers`。
  - `git_worklog/`：引擎與 `git-worklog` CLI 本體（僅標準庫）。
    - `__init__.py`：`__version__`——產品版本的單一來源。
    - `data/provider_models.json`：逐宿主 subagent 模型的**內建預設**（放在套件內，
      安裝版 CLI 才讀得到）；首次使用時複製成 `~/.git-worklog/provider_models.json`。
    - `markers.py`：日期檔／索引的解析與序列化，即格式的定義。
    - `paths.py`：使用者層級狀態目錄（`$GIT_WORKLOG_HOME`、`~/.git-worklog`）。
    - `language.py`：BCP 47 語言解析——一個 run 只有一種輸出語言。
    - `config.py`：專案 `config.json` 讀取。
    - `dates.py`：日期／時區契約，以及全工具共用的單日半開區間。
    - `providers.py`：依宿主解析 provider／模型（覆寫、escalation）。
    - `writer.py`：規劃並以交易方式寫入日期檔與 `index.md`。
    - `preview.py`：不可變的 preview record、其狀態機與 apply 鎖。
    - `migrate.py`：一次性把舊版工作日誌遷移進 `.git-worklog/`。
    - `analysis/`：分析流程（history → manifest → results，另有 worktree、refs、coverage、reconcile）。
    - `cli/`：`version`／`doctor`／`validate`／`analyze`／`preview`／`apply`／`report`。
  - `references/`：skill 依需求載入的詳細規格（報告模式、互動流程、日期契約、
    程式碼分析規則、subagent 契約、工作日誌格式、模型設定）。
- `docs/naming-conventions.md`：品牌、skill、CLI、package 與目錄的正式命名對照。
- `docs/plans/`：設計計畫，檔名格式 `yyyy-MM-dd-<主題>.md`。
  - `2026-07-15-repo-worklog-skill-design.md`：原始設計規格（單檔時代）。
  - `2026-07-16-commit-author-and-report-mode.md`：commit 作者與報告模式。
  - `2026-07-16-git-worklog-v1-roadmap.md`：v1.0 更名與重構路線圖。

工作日誌本身寫在 repository 根目錄的 `.git-worklog/`：

```
.git-worklog/
├── VERSION           # 磁碟佈局版本
├── config.json       # 專案設定（時區等）
├── index.md          # 導航：依日期由新到舊連結各日
└── days/
    ├── 2026-07-15.md # 一天一個檔
    ├── 2026-07-14.md
    └── ...
```

## 開發指令

每個指令都輸出單一 JSON 物件；`--text` 則渲染成人類可讀格式。不需安裝，直接在
skill 目錄下執行：

```bash
cd git-worklog
python3 -m git_worklog version
python3 -m git_worklog --text doctor
python3 -m git_worklog --text validate --dir /tmp/.git-worklog
python3 -m git_worklog --text coverage 7d --repo /path/to/repo --timezone Asia/Taipei
python3 -m git_worklog --text refs --repo /path/to/repo --list-tags
python3 -m git_worklog --text report --tag v1.0.1 --repo /path/to/repo --language en
```

`scripts/` 是同一套引擎的命令列薄殼，保留給曾經接過它們的腳本；那不是 skill 的
路徑，新功能也不寫在那裡。

## 打包發布用的封存檔

```bash
python3 tools/build_skill_zip.py            # 產生 ./skill.zip
python3 tools/build_skill_zip.py --check    # 驗證既有的封存檔
```

出貨內容完全由 `git ls-files git-worklog/` 決定，因此 `.gitignore` 是唯一定義
「什麼算建置垃圾」的地方——沒有第二份排除清單可以跟它漂移。代價是：封存檔裝的是
**已提交**的內容，未提交的修改不會進去。

它會把 skill 打包在 `git-worklog/` 之下，讓使用者解壓後的目錄名等於 Claude Code
的觸發名。CI 每個 PR 都會建置、解壓，並在完全未安裝的情況下跑一次 CLI——否則壞掉的
封存檔要到發布當天才會被發現。

## 測試

`tests/` 內含只用標準庫的 `unittest` 測試（零第三方相依），於專案根目錄執行：

```bash
python3 -m unittest discover -s tests -v
```

涵蓋日期契約、Git 收集、工作區檢查、分析 manifest、日期檔引擎（建立／覆蓋／
MANUAL 保留／no-change／損壞拒絕）、索引重建（摘要／排序／MANUAL 保留）、兩支驗證器、
多檔 preview 一致性、舊檔遷移與完整確定性管線；CI 也會跑同一套。
