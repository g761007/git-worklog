# `git-worklog view` — commit 抽屜（摘要內嵌）＋ `--serve` 即時 diff

日期：2026-11-10
基準版本：1.4.0（新增 `--serve` 旗標屬介面變更 → 建議 1.5.0；發版另案，本計畫不 cut release）

## Context

`view` 頁面上的 commit hash badge 目前只能「點擊複製」。讀日誌的人看到一句話想追到背後的
commit 時，還得切回終端機跑 `git show`。本案讓 badge 點擊後在頁面右側開抽屜，顯示該 commit 的
摘要、訊息內文與檔案清單，並可進一步展開 diff。

### 已定案決策（2026-11-10，使用者選定）

| 決策 | 選擇 | 影響 |
|---|---|---|
| 資料來源 | **摘要內嵌、diff 走伺服器** | 靜態頁（`file://`、`--output` 交接檔）看得到 subject／body／作者／日期／檔案 +−；完整 diff 只在 `view --serve` 模式由本機伺服器即時向 git 取 |
| 點擊行為 | 點擊開啟抽屜；複製改為抽屜內的按鈕 | git 找不到的 hash（被 rebase 掉、worklog 不在 repo 內、淺層 clone）維持現行「點擊即複製」 |
| 呈現 | 右側抽屜 | 日誌原文留在左側對照；Esc／點外側關閉；每個檔案的 diff 預設收合 |

這會修改 2026-09-24 計畫的兩條定案：「不呼叫 git」（現在 `view` 會唯讀呼叫 git）與「不開伺服器」
（`--serve` 為 opt-in，預設行為仍是靜態單檔）。

### 實測（本 repo，git 2.54）

- 日誌引用的 token 解析出 89 個 commit；其 metadata 原始大小約 130 KB（現行頁面 195 KB），
  單一 commit 最多 30 個檔案。patch 合計 2.1 MB、最大 158 KB、中位數 16 KB → diff 不內嵌合理。
- `--diff-merges=first-parent` 對 merge commit `0b73090` 給出 11 個 `diff --git` 區塊，與
  `git diff 0b73090^1 0b73090` 相同；不加則為 0。（需 git 2.31，專案下限 2.37）

## 設計

### 1. 取 commit metadata — 新檔 `git-worklog/git_worklog/analysis/commits.py`

- `collect(repo, tokens) -> (commits: dict[full_sha, dict], tokens: dict[token, full_sha])`
  1. **repo 守門**：`git -C repo rev-parse --show-toplevel` 的 realpath 必須等於 `repo` 的 realpath，
     否則回空結果。git 會往上層找 repo，worklog 若放在無關的上層 repo（dotfiles 的 `~`、monorepo）
     底下，不能去解析、更不能去 serve 那個 repo 的 diff。
  2. token → full sha：直接 import `reconcile._batch_resolve`（一次 `cat-file --batch-check`；
     不存在／非 commit／ambiguous 自動略過）。不改名。
  3. 一次 `git log --no-walk --stdin --root --diff-merges=first-parent --no-show-signature
     --submodule=short --numstat -z -M --format=%x1e%H%x1f%h%x1f%an%x1f%aI%x1f%s%x1f%b%x1f`，
     sha 由 stdin 送入。實測輸出形狀：以 `\x1e` 切 record；record 內到第一個 `\x1f\0` 為止是欄位；
     其後若有檔案則為 `\n` 加上 NUL 結尾的項目——一般 `add\tdel\tpath\0`、rename `add\tdel\t\0old\0new\0`、
     binary `-\t-\tpath\0`；沒有 diff 的 commit 沒有 `\n`。自寫小 parser（`history._parse_numstat`
     會丟掉路徑，不動它）。輸出以 `errors="replace"` 解碼。
  4. 上限：每個 commit 最多內嵌 200 個檔案（附真實總數，抽屜顯示「N more」）、body 最多 20,000 字元。
- git 失敗或非 repo → 空結果，不報錯也不加 warning（worklog 放在 repo 外是合法用法）。
- `cli/view.py` 傳入的 repo 一律是 worklog 的上層目錄（`dirname(realpath(worklog_dir))`，與頁面 project
  名同一來源）。未給 `--dir` 時它就是 `--repo`；給了 `--dir` 時 git 跟著 worklog 走。
- 只收「被日誌引用」的 commit：頁面與伺服器都不是通用的 git 瀏覽器。

### 2. 頁面 — `git-worklog/git_worklog/viewer.py`、`mdhtml.py`

- `viewer.build(worklog_dir, *, repo=None, diff_base=None)`；`repo` 給定時呼叫 `commits.collect`。
- **token 來源用兩把尺的聯集**：`reconcile.cited_hashes`（`\b`、含大寫）與 `mdhtml._HASH_RE`（ASCII 邊界、
  可貼著中文）對同一段文字抓到的不同（實測 `修正了d6f6687的問題` 只有後者抓得到），所以對每日的
  GENERATED＋MANUAL 與 index 筆記兩者都跑，確保每個會變成 badge 的 token 都被送去解析。
  `Day.hashes`（統計用，前 7 碼）不動。
- 內嵌：`<script type="application/json" id="commits">`，放在 `</body>` 前，內容
  `{"commits": {full_sha: …}, "tokens": {token: full_sha}}`，`json.dumps(sort_keys=True)` 後把 `<` 換成
  `\u003c`（commit 訊息無法跳出資料區塊；非 JS `type` 的 script 是 data block，不受 `script-src` 管制）。
  排序固定 → 頁面位元組仍然每次相同。
- **badge 查找是查表不是前綴比對**：JS 以 `tokens[data-hash.toLowerCase()]` 取 full sha。git 判定為
  ambiguous 的 token 不在表內，不會誤開別的 commit。
- CSP：靜態頁維持 `default-src 'none'`；只有 `diff_base` 給定（serve 模式）時多一條 `connect-src 'self'`，
  並在 `<html>` 加 `data-diff="diff/"`。兩種模式共用同一份 `_JS`（script hash 不變）。
- `mdhtml.inline` 的 badge 標記不變，只把 `title="Copy <hash>"` 改成中性文字；JS 內重設 title 的兩處
  （`viewer.py:889,893`）同步調整。renderer 不需要知道 git。
- `_JS` 新增（全部 `createElement`/`textContent`，不用 `innerHTML`）：
  - 點 badge：查表命中 → 開抽屜；未命中 → 走現有 `copyText` 流程（原程式碼保留為 fallback）。
    載入時替命中的 badge 加 class，`cursor: copy` 只留給未命中的。
  - 抽屜 `<aside id="commit" role="dialog" aria-labelledby=…>`：short hash＋複製鈕＋關閉鈕／subject／
    作者 · 日期／body（`<pre>`）／`N files +A −D`／檔案列（`<details>`，rename 顯示 `old → new`，
    binary 顯示 `bin`）。
  - diff：`data-diff` 存在時，開抽屜即 `fetch(diffBase + fullSha)`（每 commit 快取）。回應是逐檔 patch
    陣列；數量與檔案清單相符時按索引掛到各檔 `<details>`，展開時才建 DOM 行（`+`／`-`／`@@` 各一個
    class）；不符（或被截斷）則整段放在清單下方。靜態頁時檔案列不可展開，下方顯示
    “Diffs are served live — run `git-worklog view --serve`.”
  - 鍵盤與焦點：開啟時焦點移入抽屜、關閉時還給原 badge；Esc 優先關抽屜（其次才是既有的清除搜尋）；
    抽屜開啟時忽略 ←／→ 換日；`hashchange` 時關閉；點抽屜外關閉。
- `_CSS`：抽屜（`position: fixed; right: 0; width: min(560px, 100vw)`、`z-index` 高於 `.top`）、diff 行
  配色（light/dark 各一組 token）、`@media print` 隱藏。

### 3. 伺服器 — 新檔 `git-worklog/git_worklog/viewserver.py`（僅標準庫）

- `ThreadingHTTPServer`（daemon threads）＋自寫 `BaseHTTPRequestHandler` 子類（絕不用
  `SimpleHTTPRequestHandler`）；只綁 `127.0.0.1`、**port 0** 由系統指派；`log_message` 不輸出。
- URL：`http://127.0.0.1:<port>/<token>/`，`token = secrets.token_urlsafe(16)`，每次執行重新產生，
  以 `secrets.compare_digest` 比對。理由：靜態頁刻意是 0600，伺服器不能讓同機其他使用者讀到日誌與 diff。
- 每個請求：`Host` 必須等於 `127.0.0.1:<port>` → 否則 403；token 不符 → 404；只實作 `do_GET`。
- 所有回應：`Cache-Control: no-store`、`X-Content-Type-Options: nosniff`、
  `Cross-Origin-Resource-Policy: same-origin`；不送任何 CORS 標頭。
- 路由：
  - `GET /<token>/` → 每次請求重新 `viewer.build(...)`（重新整理即更新），並更新引用 sha 集合。
  - `GET /<token>/diff/<sha>` → sha 必須在最近一次 build 的引用集合內（集合成員檢查即足夠），否則 404。
    執行 `git show --no-color --no-ext-diff --no-textconv --no-show-signature --submodule=short --root
    --format= --patch -M --diff-merges=first-parent <sha>`（旗標與 metadata 那次一致，檔案數才對得上）。
    **上限在讀取時執行**：`Popen` 後 `read(2 MB + 1)`，超過即 kill、標記 truncated。
    以 `diff --git ` 行切檔，回 `application/json; charset=utf-8` 的 `{"files": [...], "truncated": bool}`。

### 4. CLI — `cli/view.py`、`cli/__init__.py`

- 新旗標 `--serve`，與 `--output` 互斥（argparse mutually exclusive group）；`--no-open` 照常可用。
- 靜態模式：`viewer.build(worklog_dir, repo=<worklog 上層>)`，其餘流程不變；payload 增加 `commit_count`。
- serve 模式：`run()` 內建頁（驗證 worklog）、bind＋listen、**在 `run()` 內開瀏覽器**（連線由 kernel
  backlog 接住），所以 `opened` 與 `BROWSER_NOT_OPENED` 仍然如實；回傳
  `{"ok": true, "serving": true, "url": …, "output": null, …}`，不寫任何檔案。bind 失敗 → `IO_ERROR`、exit 2。
  server 物件掛在 `args` 上，不用模組全域變數。
- 「先印 JSON 再常駐」：`cli/__init__.py:main` 在 `_emit` 之後，若模組定義了 `after_emit(args, payload, code)`
  就呼叫並以其回傳值為 exit code。`view.after_emit` 只做三件事：`sys.stdout.flush()`（pipe 是 block-buffered，
  不 flush 讀者拿不到 JSON）、`serve_forever()`、Ctrl+C 時關閉並回 0。非 serve 模式直接回傳原 code。
- `render_text` 補上 serve 模式（`output` 為 null 時印 URL 與「Ctrl+C to stop」）。
- `NOTE`／help 文字：伺服器跑到被中斷為止；diff 即原始碼；URL 內的 token 會留在瀏覽器歷史、
  這份 JSON 輸出與瀏覽器行程的參數列，但每次執行都換新。

### 5. 文件

- `viewer.py`／`cli/view.py`／`mdhtml.py` 的 module docstring：改掉「reads day files and nothing else」
  「badge 複製」等已不成立的敘述；“Cited, not made” 一節保留（統計數字仍只描述日誌）。
- `README.md` 英文與中文兩半：`view` 小節加入 commit 抽屜與 `--serve`；`CHANGELOG.md` `[Unreleased]` 加
  Added；`git-worklog/SKILL.md` 命令表註記 `--serve` 會常駐、skill 流程中不得執行。
- 依 G1 把本計畫複製到 `docs/plans/2026-11-10-view-commit-drawer.md`。

## 實作步驟（每步附驗證）

1. `analysis/commits.py` → verify：新測試以 `tests/helpers.make_history_repo()` 等確認
   subject／body／rename／binary／merge／root commit／空 commit／不存在的 token／非 UTF-8 訊息；
   worklog 位於上層 repo 的子目錄時回空結果。
2. `viewer.build` 內嵌 JSON ＋ CSP 分支 → verify：新測試（見下）。既有測試需**刻意修改兩處**：
   `test_view.py:306` 的 `page.count("<script") == 1` 改為精確計數 `<script>` 並加斷言「資料區塊內沒有 `<`」；
   `test_view.py:219` 的 `title="Copy` 斷言隨 title 文字更新。其餘（`page_script()`、CSP hash、
   同位元組、`TestThisRepositorysWorklog`）不改動即通過。
3. `viewserver.py` → verify：測試在 thread 內起伺服器，逐條打路由。
4. CLI `--serve` ＋ `after_emit` → verify：`--serve --output` 被 argparse 拒絕；subprocess 起
   `view --serve --no-open`，累積 stdout 直到 `json.JSONDecoder().raw_decode` 成功（`_emit` 用 `indent=2`，
   不是單行），打 `url` 得 200，送 SIGINT 後 exit code 0（此測試在 Windows 上 skip）。
5. `_JS`／`_CSS` 抽屜 → verify：瀏覽器實測（見「端到端驗證」）。
6. 文件與計畫檔複製 → verify：`python -m unittest discover -s tests` 在 3.14 與 3.9 全綠。

## 測試（加在 `tests/test_view.py`，沿用 `make_worklog`／`run_cli`／`snapshot`）

- 被引用的 commit 出現在 `#commits`，內容與 git 相符；**未被引用的 commit 不出現**。
- 貼著中文的 hash 與大寫 hash 都進得了 `tokens` 表；ambiguous／不存在的 token 不在表內。
- 惡意 commit 訊息 `</script><script>alert(1)</script>`：資料區塊內沒有 `<`。
- 超過 200 個檔案的 commit：內嵌 200 筆且總數正確。
- worklog 不在 git repo 內：`commit_count == 0`、無 warning、badge 標記不變。
- 靜態頁 CSP 沒有 `connect-src`、沒有 `data-diff`；serve 頁兩者皆有，且 script hash 與靜態頁相同。
- 伺服器：正確 token＋Host → 200 且帶三個安全標頭、無 `Access-Control-*`；錯 token → 404；
  `Host: evil.example` 與 `Host: localhost:<port>` → 403；被引用 sha 的 diff 含已知的變更行；
  **存在但未被引用**的 sha → 404；POST 不被接受；超過上限的 diff 標記 truncated；
  前後 `snapshot(repo)` 相同（唯讀）。

## 端到端驗證

1. `PYTHONPATH=git-worklog python3 -m git_worklog view --serve --no-open`（本 repo），用瀏覽器預覽面板
   開啟印出的 URL：點 badge → 抽屜顯示摘要／內文／檔案；展開檔案 → diff 有 +／− 配色；
   `0b73090`（merge commit）有檔案清單與 diff；`acceded`／`defaced` 不是 badge；Esc 關閉、焦點回到 badge；
   深色／淺色各看一次；窄視窗（<760px）抽屜滿版。
2. `view --no-open --output build/view.html` 以 `file://` 開啟：抽屜有摘要與檔案清單，diff 處顯示
   `--serve` 提示；DevTools 無 CSP 違規（確認 JSON data block 沒被擋）、無網路請求。
3. `curl -H 'Host: evil.example' <url>` → 403；`curl <url 去掉 token>` → 404。
4. CI 既有的 `view --no-open --output` 兩個步驟（淺層 checkout、無歷史）仍通過。

## Plan agent 對抗式審查：採納紀錄

採納：既有測試兩處必須修改（原稿誤稱不需改）；`-z` 輸出形狀寫明並加 record 分隔；repo toplevel 守門；
diff 上限改在讀取時執行；`--root`／`--submodule=short`／`--no-show-signature`／`--stdin`；回應標頭與
`BaseHTTPRequestHandler`、`compare_digest`、Host 只收 `127.0.0.1`；token→sha 查表取代前綴比對；
兩把 regex 聯集；瀏覽器在 `run()` 內開啟；內嵌 metadata 上限；無障礙與按鍵優先序；非 UTF-8 測試。

刪減：路徑推導的固定 port（改 port 0）；sha 格式 regex（集合檢查即可）；`_batch_resolve` 改名。

## 不做

- `--port`、閒置自動關閉、檔案變更自動重新整理（輪詢）。
- diff 語法高亮、side-by-side、逐行連結；非引用 commit 的瀏覽；連到 remote（GitHub）頁面。
- 把 diff 內嵌進靜態頁（使用者已選擇不內嵌）。
- cut release／bump 版本（另案；屆時建議 1.5.0）。

## 風險與未確認

- `<script type="application/json">` 不受 `script-src` 管制：依 HTML 規格推論，**尚未在瀏覽器實測** →
  端到端第 2 步確認；若被擋，改成 `<template>` 內的跳脫文字，先回報再改。
- serve 模式每次執行的 port 不同（origin 不同），主題選擇不會跨次執行被記住。
- `--no-show-signature` 是否足以保證 `--format=` 下不呼叫 `gpg.program`：未能確認，旗標照加。
- `--repo` 指向 repo 的子目錄時，toplevel 守門會讓 commit 抽屜停用（badge 退回複製）；屬可接受的保守行為。
- `--serve` 是常駐行程，agent 若誤跑會卡住 → 以 SKILL.md 註記與 help 文字防範，不加 timeout。
- Safari／Firefox 對 `http://127.0.0.1` 頁面的 meta CSP `connect-src 'self'`：預期可用，未實測。
- 記憶提醒：本環境的 Write/Edit 曾無聲失效 → 每次寫檔後回讀確認，失效則改用加引號的 heredoc。

## 關鍵檔案

- 新增：`git-worklog/git_worklog/analysis/commits.py`、`git-worklog/git_worklog/viewserver.py`
- 修改：`git-worklog/git_worklog/viewer.py`、`mdhtml.py`、`cli/view.py`、`cli/__init__.py`、
  `tests/test_view.py`、`README.md`、`CHANGELOG.md`、`git-worklog/SKILL.md`
- 重用：`reconcile.cited_hashes`／`_batch_resolve`、`mdhtml._HASH_RE`、`history.UNIT_SEP`／`GitError`／`_git_ok`、
  `cli/view._open_quietly`、`tests/helpers.make_history_repo`
