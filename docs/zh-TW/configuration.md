# 設定

**語言：** [English](../configuration.md) · 繁體中文 — [← 回到 README](../../README.zh-TW.md)

- **輸出目錄**：預設為 repo 根目錄的 `.git-worklog/`（以
  `update_daily_worklog.py --dir` ／ `rebuild_worklog_index.py --dir` 覆寫）。
- **時區**：自動偵測（`$TZ` → `/etc/localtime` → 系統偏移）；可用
  `resolve_date_range.py --timezone Asia/Taipei` 指定。
- **輸出語言**：日誌用「你提問的語言」寫，不是用「repo 的語言」寫。commit 訊息、識別符、
  README 全是英文，也不會讓日誌變成英文。優先序：本次要求 → `--language` →
  `.git-worklog/config.json` → Agent Host → `GIT_WORKLOG_LANGUAGE` → 系統 locale
  → 英文。語言標籤採 BCP 47（`zh-TW`、`en`、`ja`）；單獨的 `zh` 因語意模糊會被拒絕，
  `zh-TW` 與 `zh-CN` 永不視為同一設定。任何語言下，檔案路徑、程式符號、commit hash
  與 API 名稱都不翻譯。`index.md` 於首次建立時固定語言，避免不同貢獻者反覆改寫。
  詳見 roadmap §6.2。
- **Subagent 模型**：讀的是**你自己的檔案** `~/.git-worklog/provider_models.json`。
  第一次執行時會從 skill 內建的預設（成本優先——Claude Haiku 4.5 ／ GPT-6 Luna ／
  Gemini 3.8 Flash）複製一份過去，之後就不再改寫它；所以供應商改名或下架模型時，改這個
  檔案即可，不必等新版。`git-worklog models` 可以查看；
  `git-worklog models --host anthropic --model <id> --apply` 則是用指令做同一件事——
  你可以直接請目前所在的 coding agent 用它把該宿主現行的模型寫進去。升級後即使內建預設
  更新了，也不會動你的檔案；`git-worklog doctor` 會列出兩者的差異。只想影響單次執行時，
  `GIT_WORKLOG_{ANTHROPIC,OPENAI,GOOGLE}_MODEL` 或 `--model` 仍然優先。詳見
  `references/provider-models.md`。
- **Preview 狀態**：存放在 repo 之外的 `~/.git-worklog/previews/`。
- **Subagent 分析結果**：每個 Day Subagent 把分析**寫進**
  `~/.git-worklog/analysis/<run_id>/<date>.json`，而不是用回傳值交付——回傳通道會掉內容也會截斷。
  結果檔在執行後保留，方便回溯某段日誌是根據什麼分析寫出來的。

## 狀態目錄

工具在指令之間需要記住的東西，全部放在 repo 之外的同一個目錄——`~/.git-worklog/`，
或 `$GIT_WORKLOG_HOME` 指向的位置：

| 路徑 | 內容 |
|---|---|
| `analysis/<run_id>/tasks/` | 每天一份 manifest：要分析什麼、用什麼語言、哪些檔案必須交代 |
| `analysis/<run_id>/results/` | 每個 Day Subagent 的分析結果 |
| `previews/` | 待套用的 apply 會寫入的每個檔案的完整最終內容 |
| `view/` | `git-worklog view` 寫出的頁面，每次執行都從工作日誌重新產生 |
| `provider_models.json` | 各宿主使用的 subagent 模型——這是你的檔案，可自行修改；首次使用時從內建預設複製 |

**這裡的東西永遠不會被自動刪除。** 超過 24 小時 TTL 的 preview 只是不再能套用，檔案仍
留在磁碟上；每次執行的 manifest 與結果也是刻意保留的——幾個月後看到一段讀起來奇怪的
日誌，還能回溯它是根據什麼分析寫出來的。因此這個目錄只增不減，而且**沒有** `prune`
指令：一次執行何時不再值得保留，是你的判斷，不是工具的。

**刪掉它是安全的，只有一個檔案要留意。** 已經套用的日誌存在各自 repo 的
`.git-worklog/` 底下，完全不依賴這個目錄。會失去的是還沒套用的 preview——`apply` 會回報
`UNKNOWN_PREVIEW`，重新建一份 preview 即可——以及你對 `provider_models.json` 的修改：
刪掉之後它會從內建預設重新複製一份。改過的話請留下這個檔案；否則整棵刪掉，或只刪掉你
不再在意的 `analysis/<run_id>/` 都可以。
