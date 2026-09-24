# `git-worklog view` — 以本機網頁瀏覽工作日誌

日期：2026-09-24
基準版本：1.2.2（新增子命令屬 minor；發佈 1.3.0 另案處理）
範圍：新增**唯讀**子命令 `view`：讀 `.git-worklog/`，產生一個自含的 HTML 檔並開啟瀏覽器。
不改日誌格式、不改 skill 選單、不呼叫 git、不寫入 repo 或 `.git-worklog/`。

---

## 0. 已定案決策（2026-09-24，使用者選定）

| 決策 | 選擇 | 理由 |
|---|---|---|
| 架構 | 靜態單檔 HTML，不開伺服器 | 無網路監聽面；維持「印一個 JSON 就結束」的 CLI 契約；離線可用；`--output` 即交接檔 |
| 範圍 | 瀏覽 + 視覺化總覽：統計卡、活動日曆、時間軸、單日頁、搜尋；只讀 `.git-worklog/` | git 補強（缺口、真實 commit 數）留第二階段 |
| 介面語言 | 英文 | 與 `language.INTERFACE_SUPPORTED = ("en",)`（§6.2.13）、v1.1.0 選單英文化一致；日誌內容照原文 |
| 名稱 | `view` | 短；pip 安裝後依 git 外部子命令機制也可打 `git worklog view` |

## 1. 背景與評估結論

日誌是 Markdown，單檔在 GitHub/IDE 可讀，但跨天掃摘要、看哪幾天最忙、搜尋某個符號何時被動過，
都得自己開一堆檔。Roadmap §1 把 Web UI 列為 Future Frontend、§19 刻意排除於 v1；v1.2.2 後引擎
已穩定，這是第一個前端。

**結論：可行、風險低。** 格式由 `markers.py` 單一定義，且能純依結構解析（§2）。成本集中在三處：
安全的 Markdown 子集渲染器（stdlib 沒有）、頁面 CSS/JS、開瀏覽器時不破壞 JSON 契約。

## 2. 實測：本 repo 6 個真實日誌檔

| 發現 | 設計影響 |
|---|---|
| 6/6 檔 `scan_day` 零 issue；工作項目內 311/311 個 top-level bullet 是 `- **欄位：** 值` | 直接渲染 Markdown、用 CSS 把開頭粗體排成欄位標籤；不建欄位模型（不會漏內容） |
| 標題語言隨 run 而變（`## 當日摘要` / `## Daily summary`） | 只依結構（`##`、`###`、整行註解）切塊，絕不比對標題文字 |
| 07-15、07-16 沒有 SUMMARY 標記 | 導言取「第一個 `##` 區塊的第一段」（標記行視為段落分隔），有無標記都成立 |
| 07-17：git 實際 52 個 commit，`reconcile.cited_hashes` 找到 41 個 | UI 一律寫 “commits cited”；計數沿用 `cited_hashes`，與 `report` 同一把尺 |
| 同檔多種寫法（`SKILL.md` / `git-worklog/SKILL.md`） | 檔案反查需 `git ls-files` 正規化 → 第二階段 |
| 07-15 與 07-16 的 `HEAD` 都是 `da426e7` | header 的 Branch/HEAD 記的是分析那次 run（worklog-format.md §2），不是當天 → 不顯示 |
| MANUAL 全空；index MANUAL 是預設佔位字 | 空筆記、以及任何語言（`INDEX_CHROME_LANGUAGES`）的預設佔位字一律隱藏 |

## 3. 頁面呈現

一個 HTML、三種畫面。**內容全由 Python 預先渲染**；切換畫面用 CSS `:target` + `:has()`，不需 JS
路由（沒有 JS 也能完整瀏覽）。JS 只負責搜尋與快捷鍵。

```text
┌ git-worklog · .git-worklog/                         [ Search the worklog…  / ] ┐
├──────────────┬─────────────────────────────────────────────────────────────────┤
│ Overview     │ 總覽（無 hash 或 #overview）                                      │
│ 2026-08      │  [Days logged 6] [Work items 40] [Commits cited 91] [Span 07-15→08-07]│
│  08-07 Fri 6 │  Activity：週 × 星期的日曆格，深淺 = 當日工作項目數（1–2/3–5/6–9/10+） │
│ 2026-07      │    空格標 “No day file” ＋圖例註明「未對照 git：缺口與沒 commit 看起來一樣」│
│  07-27 Mon 2 │  Project notes：index MANUAL（非預設佔位字才顯示）                   │
│  07-18 Sat 4 │  Timeline：依月分組的每日卡片——導言（CSS 限 3 行）、N items、         │
│  07-17 Fri15 │    N commits cited、章節標籤、Notes / Format issue 徽章              │
│  …           │ 單日（#d-2026-07-18；#d-2026-07-18-i3 直接捲到第 3 個工作項目）      │
│              │  日期＋星期、← 前一天｜後一天 →、本日目錄（## 與 ### 標題）           │
│              │  摘要區塊做成 callout；每個 ### 是 <details open> 卡片；欄位標籤、     │
│              │  code span 以 chip 樣式呈現；MANUAL 人工筆記用虛線框；頁尾顯示檔案路徑 │
│              │ 搜尋（輸入即覆蓋主區）：依日分組的命中清單＋片段高亮，點擊跳到該項目 │
└──────────────┴─────────────────────────────────────────────────────────────────┘
```

- 快捷鍵：`/` 聚焦搜尋、`Esc` 清除、`←/→` 前後日；側欄標示目前所在日。
- 外觀：系統字型（含 PingFang TC / Noto Sans TC / Microsoft JhengHei）、hash 與路徑用等寬字；
  深色模式跟隨 `prefers-color-scheme`；寬度 < 760px 時側欄改為頂部清單；`@media print` 只印目前畫面。
- 字形：`<html lang="en">`；日誌內容容器的 `lang` 取 index 的語言標記（未標記的舊 index 依定義為
  `zh-TW`），否則 `config.language()`，確保中文用繁體字形。
- 空狀態：“No worklog days yet. Generate some with /git-worklog.”
- 壞檔：`scan_day` 回傳 `None` → 警告橫幅＋整檔跳脫後的原文 `<pre>`；解析得出但有 issue → 正常渲染＋
  徽章；非 UTF-8 → 以 `errors="replace"` 解碼並回報 `NON_UTF8`。其他日不受影響。
- 與先前 mockup 的差異：Contributors 卡改成 Span（免解析作者）；拿掉 branch/HEAD chips（見 §2）；
  收合改為整張卡片 `<details>`，不做欄位層級的 “+4 more”。

## 4. 實作架構

```text
.git-worklog/ ──read-only──► git_worklog/viewer.py ──► 一個 HTML 字串（CSS/JS 內嵌，無 CDN）
                               └ git_worklog/mdhtml.py（安全 Markdown 子集）
git_worklog/cli/view.py：解析 --dir → viewer.build → writer.atomic_write → 安全開啟瀏覽器 → 一個 JSON
```

| 檔案 | 內容 | 估計行數 |
|---|---|---|
| `git_worklog/mdhtml.py`（新） | 標題（降級）、段落、巢狀清單、`**粗**`/`*斜*`、code span、fenced code、http(s) 連結；表格與引言區塊以跳脫文字保留換行 | ~170 |
| `git_worklog/viewer.py`（新） | `build(worklog_dir) -> (html, info)`：讀日檔／index／config；fence-aware 切 `##`/`###`；計數；組頁；CSS 與 JS 以字串常數放在模組內（不需 package-data） | ~230 ＋ CSS ~200 ＋ JS ~80 |
| `git_worklog/cli/view.py`（新） | 路徑解析、輸出檔、拒寫 worklog 內、安全開啟瀏覽器、JSON 與 `render_text` | ~110 |
| `git_worklog/cli/__init__.py`（改） | `view` subparser、lazy import 分支、模組 docstring | +12 |
| `git_worklog/paths.py`（改） | `VIEW_SUBDIR = "view"`、`view_dir()` | +5 |
| `tests/test_view.py`（新） | 見 §6 | ~260 |

**沿用的既有程式**：`markers` 的 `detect_layout` / `list_day_dates` / `day_path` / `scan_day` /
`index_path` / `scan_index` / `index_language_of` / `index_chrome` / `INDEX_CHROME_LANGUAGES` /
`summarise_generated`（僅作無 `##` 區塊時的 fallback）；`analysis/reconcile.py` 的 `cited_hashes`
（依前 7 碼去重）；`config.load` / `config.language`；`paths.ensure_dir`；
`writer.atomic_write(target, content, validate, *, prefix)`；`cli/validate.py` 的 dir 解析與
`NOT_FOUND`；`cli/reindex.py` 的 `IO_ERROR`。

**CLI 規格**

```text
git-worklog view [--repo .] [--dir PATH] [--output FILE] [--no-open]
```

- 預設輸出 `~/.git-worklog/view/<專案名>-<sha256(realpath(worklog dir))[:8]>.html`；專案名取
  worklog 目錄上一層的 realpath basename（不是 cwd——SKILL.md 規定從 skill 目錄執行命令）。
  同一 worklog 永遠同一路徑，重跑後瀏覽器重新整理即可。
- 先 `paths.ensure_dir(paths.view_dir())`（`os.makedirs` 的 mode 只作用在最末層），再
  `writer.atomic_write(out, html, lambda _t: None, prefix=".rw-view-")`（mkstemp → 0600；重新整理時
  不會讀到半個檔）。
- `--output` 落在 worklog 目錄內 → `OUTPUT_INSIDE_WORKLOG`（exit 2），否則 `--output .git-worklog/index.md`
  會覆寫日誌。`as_uri()` 前先轉絕對路徑。
- 開瀏覽器（`_open_quietly`）：Linux 上若 `DISPLAY` / `WAYLAND_DISPLAY` / `BROWSER` 皆未設定就不開
  （stdlib 只要有 `TERM` 就會註冊 lynx/w3m 等前景文字瀏覽器，會卡住終端）；其餘情況在呼叫期間把
  fd 1 `dup2` 到 fd 2，避免瀏覽器子行程的輸出混進 JSON。沒開成 → `opened: false` ＋
  `BROWSER_NOT_OPENED` 警告（附檔案路徑），仍 exit 0。
- JSON：`ok, worklog_dir, layout, output, url, opened, day_count, range{from,to}|null, warnings[], note`。
  `warnings` 含各日 issue（附 `date`/`target`）、`NON_UTF8`、`INDEX_UNREADABLE`、`BROWSER_NOT_OPENED`。
- Exit：0 = 頁面已產生；2 = `NOT_FOUND` / `OUTPUT_INSIDE_WORKLOG` / `IO_ERROR`。不使用 1。
- 輸出完全決定性：不嵌時間戳、集合一律排序 → 兩個不同 process 產出位元組相同。

**安全模型**（日誌引用私有原始碼，內容也可能來自被 prompt injection 的 LLM 輸出）

1. 渲染器**先跳脫再組字**：code span 以 placeholder 保護、輸入先剔除 NUL；原始 HTML 一律顯示為文字；
   整行 HTML 註解（SUMMARY 標記等）丟棄並視為區塊分隔；不支援 `_斜體_`（`REPO_WORKLOG_*_MODEL`
   這類字會被吃掉）；元素 id 只由日期與序號組成，絕不取自內容。
2. 連結只允許 http/https（trim 後不分大小寫判斷），拒絕 `//host`（Windows 的 file:// 頁面會變成 SMB
   路徑）；`./days/<date>.md` 這類日檔連結改寫成 `#d-<date>`；其餘相對連結顯示為文字；圖片只顯示文字。
3. `<meta charset="utf-8">` 之後、任何 style/script 之前放
   `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-…';
   style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">`——就算有注入也不能執行、
   不能對外連線（CSS 的 `url()` 也被 `default-src` 擋住）。
4. 搜尋結果只用 `createElement` / `textContent` 組；查詢字串不寫進 URL。
5. 檔案 0600、目錄 0700；不開任何 port；不寫 repo、不寫 `.git-worklog/`。

## 5. Plan agent 對抗式審查：採納紀錄

採納：瀏覽器輸出隔離與 Linux 守門；改為直接渲染 Markdown（原欄位模型會讓非 `###` 章節與標記外段落
漏掉）；改用 `reconcile.cited_hashes`；拿掉 Branch/HEAD；預設佔位字比對所有語言；`ensure_dir`
先行；專案名取 worklog 上層 realpath；`--output` 命名（與 `tools/build_skill_zip.py` 一致）並拒寫
worklog 內；`NON_UTF8` 容錯；`lang` 屬性；CSS/JS 改為 Python 常數（省掉 package-data 與打包風險）；
連結白名單收緊；SKILL.md 命令表補一列；README 註明 Snap 瀏覽器限制。

未採納：「移除全部 JS、搜尋改用 Ctrl+F」與「日曆可省」——與你選定的範圍衝突。折衷：路由改由 CSS
負責，JS 縮到只剩搜尋與快捷鍵（~80 行）。

## 6. 實作步驟（每步附驗證）

1. `mdhtml.py` → 驗證：`<script>`、`<img onerror>`、`JaVaScRiPt:`、`//host`、`data:` 連結全部無活性；
   code span 內 `<b>` 被跳脫；fence 內 `## x` 不成標題；巢狀清單；標記行當段落分隔；snake_case 不變斜體。
2. `viewer.py` → 驗證：每日工作項目數 = fence 外 `###` 數；有／無 SUMMARY 標記與 en 標題的日都取得導言；
   commits cited 與 `cited_hashes` 一致；壞檔走原文 fallback 且其他日正常；legacy 版面、空目錄可讀；
   index 佔位字（zh-TW 與 en）隱藏、自訂筆記顯示；整頁 `<script` 只出現一次、沒有 `on…=` 屬性、
   每個 `href` 符合 `^(https?://|#)`；CSP 的 hash 等於內嵌 script 的 sha256。
3. `cli/view.py` + 接線 + `paths` → 驗證：JSON 契約與 exit code；`NOT_FOUND`；`OUTPUT_INSIDE_WORKLOG`；
   預設路徑在 `GIT_WORKLOG_HOME/view/`（目錄 0700、檔案 0600）；**唯讀保證**（執行前後 worklog 目錄與
   repo 的檔案清單＋位元組完全相同）；`BROWSER=echo` 時 JSON 仍可解析且 `opened: true`；mock
   `webbrowser.open` 回 False → `BROWSER_NOT_OPENED`、exit 0；不同 `PYTHONHASHSEED` 的兩次輸出位元組相同。
   其餘測試一律 `--no-open`。（不可用 `BROWSER=false` 測失敗：`webbrowser` 會退回系統預設瀏覽器真的開頁。）
4. CI（`.github/workflows/ci.yml`）→ 無安裝煙霧測試與 skill-zip job 各加一行
   `view --no-open --output …` 並 grep CSP，證明兩種安裝路徑都帶得到頁面程式。
5. 文件 → README 英文與繁中兩半：CLI 區塊加 `view`、狀態目錄表加 `view/`、疑難排解（Snap 版
   Firefox/Chromium 讀不到 `$HOME` 下的隱藏目錄 → 用 `--output`；無顯示環境 → 手動開輸出路徑）；
   CHANGELOG `[Unreleased]` 加 `### Added`；`git-worklog/SKILL.md` 的 command map 加一列 `view`
   （維持「這就是全部介面」的敘述為真；選單不動）。
6. 實機驗證（§7）。

依專案慣例做 mutation check：拿掉跳脫、拿掉 fence 追蹤、讓 view 寫進 worklog、拿掉 stdout 重導、
拿掉 CSP hash——各自必須讓對應測試轉紅。

## 7. 端到端驗證

- `python3 -m unittest discover -s tests`，於 3.14 與 `/opt/homebrew/bin/python3.9` 各跑一次。
- `python3 tools/build_skill_zip.py --check`；解壓後不設 PYTHONPATH 執行 `python -m git_worklog view --no-open --output …`。
- scratchpad 建 venv `pip install .`，於 temp dir 執行 `git-worklog view --no-open --dir <repo>/.git-worklog --output …`。
- 內建瀏覽器開啟本 repo 的頁面：總覽、6 個單日、搜尋（例：`atomic_write`）、`←/→`、深色模式、
  `resize_window` 手機寬度；`read_console_messages` 確認**沒有 CSP violation**。
- 用合成資料（365 天）量一次頁面大小與開啟速度。
- JS 不進 CI 單元測試（加 JS runner 會破壞零依賴）——列為手動驗證項。

## 8. 不做（本版）與第二階段候選

- `--serve` 即時伺服器（`http.server`、127.0.0.1、Host 標頭檢查、輪詢重載）——也能解決 Snap 限制。
- git 補強：以 `analysis/coverage.py` 的 `check()` 在日曆標出缺口與真實 commit 數；commit 連到 remote。
- 檔案反查視圖（需 `git ls-files` 正規化，見 §2）；Contributors 統計。
- skill 選單加「開瀏覽器」選項（`tests/test_skill_invocation.py` 守著選單列）。
- 介面多語系（可比照 `markers._INDEX_CHROME`）。
- 網頁編輯 MANUAL：會繞過 preview/apply 的寫入保證，刻意不做。

## 9. 風險與未決

- file:// 頁面上的 meta CSP 與 script hash：預期三大瀏覽器都套用，**未實測** → §7 驗證；若不被接受，
  改用 `'unsafe-inline'` 前先回報。
- 子集以外的 Markdown（表格、腳註、原始 HTML）顯示為文字：安全但不美觀，可接受。
- 本 session 的 Write 工具持續失效（呼叫無結果、檔案不存在）；本計劃檔以加引號的 Bash heredoc 寫入。
  實作階段若 Write/Edit 仍失效，同樣改用 heredoc 建檔，並在每次寫入後回讀確認。
- 既有問題（本案不修）：`docs/naming-conventions.md` 的 CLI「Implemented」清單只列 3 個命令，早已過時；另開任務。

## 10. 交付

- 分支 `feat/view-command`；commit 依慣例拆分（`feat(view)`、`test(view)`、`ci`、`docs`）。
  commit / push / PR 待你明確指示。
- 核准後將本計劃複製為 `docs/plans/2026-09-24-worklog-viewer.md`。

---

## 11. 實作紀錄（動工後補，2026-09-24）

與計劃不同之處：

- **header 左上只留 “Git Worklog”**（使用者於實作中要求）；專案名只出現在總覽大標題與分頁標題。
- **搜尋預先轉小寫、改用 `indexOf`**：一年份（365 天、9.8 MB 頁面）時，原本逐次跑不分大小寫的
  regex，最慢約 0.4 秒；改後無命中查詢從約 255 ms 降到約 15 ms，搜尋模式中持續打字每鍵約 40–64 ms。
  第一次進入搜尋模式仍有一次約 0.2–0.3 秒的版面重算（隱藏整個大 DOM），可接受。
- **從搜尋結果跳轉後補捲動**：瀏覽器捲動時目標仍被搜尋結果蓋住，所以不會移動；清除搜尋後補一次
  `scrollIntoView()`。
- **規模估計修正**：計劃估一年約 5 MB，實測 9.8 MB（本 repo 的日誌檔平均約 19 KB）；產頁 0.58 秒，
  瀏覽器 DOMContentLoaded 約 0.34 秒。

實測結果：

- 測試 524 → 558（新增 `tests/test_view.py` 34 個），3.14 與 3.9 皆通過。
- Mutation check 5/5 轉紅：拿掉跳脫、拿掉 fence 追蹤、寫進 worklog、拿掉 stdout 重導、CSP hash 錯誤。
- CSP 在 Chromium 實測生效：動態注入的 inline script 與外部圖片都被擋，console 有 violation 紀錄；
  頁面自己的 script 以 hash 放行。
- 零安裝（複製 skill 目錄、不設 PYTHONPATH）與 `pip install` 兩種方式產出的頁面位元組相同。
- `skill.zip`：commit 後以 `tools/build_skill_zip.py` 實際建置（60 個檔案、223 KB，`--check` 通過），
  三個新模組都在包內，解壓後不設 PYTHONPATH 即可執行 `view`。
- 路由、搜尋、←/→、深淺色、375px 手機寬度：在內建瀏覽器以臨時 localhost 伺服器驗證。

未驗證：

- 真正的 `file://` 開啟：內建瀏覽器把專案內的本機檔當 `data:` 靜態快照，無法導覽，所以路由與搜尋
  改用 http 驗證；Safari / Firefox 未實測。
- Linux「無顯示環境不開瀏覽器」那條分支只在程式碼中存在，macOS 上跑不到；CI 的 Linux job 只會走
  `BROWSER` 已設定的路徑。

過程備註：本 session 的 Write / Edit 工具全程無聲失效（無結果、檔案不變），新檔一律以加引號的
heredoc 建立，修改以「舊字串必須恰好出現一次、全部檢查通過才寫檔」的替換腳本進行，並逐次以
`git diff` 回讀。
