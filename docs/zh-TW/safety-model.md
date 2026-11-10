# 安全模型

**語言：** [English](../safety-model.md) · 繁體中文 — [← 回到 README](../../README.zh-TW.md)

- 一律先 dry-run；未經明確確認絕不寫入。
- 一天一個檔：重新分析某天只會覆寫該天的檔案，其他日期檔逐位元組保持不動。
- 每天的 `MANUAL` 區段與索引的 `MANUAL` 區段都逐字保留；只有自動產生區段會被覆蓋。
- 每日檔案採交易式寫入（所有目標日期一起暫存、驗證、原子替換，失敗即 rollback），
  失敗不會留下「部分日期已更新」的狀態；索引原子寫入，且永遠可由日期檔重建。
- **Apply 寫入的就是 preview 本身，不是重新產生的版本。** Preview record 存有每個目標
  檔案的最終內容，而 `git-worklog apply` 只收一個 preview id——所以落到磁碟上的，就是
  當初顯示在畫面上的那份，任何重新產生的內容都沒有路徑可以進入檔案系統。
- Apply 前會重新驗證那份 payload 所依賴的一切：repository identity、git dir、branch、
  HEAD、submodule、working tree（僅當該 run 有讀取時）、`index.md`、各日期檔、目錄清單、
  分析 run，以及專案語言設定。只要有任一項變動，或 preview 已過期／已取消／已失敗／
  已套用，一律拒絕，而不是自行調和。
- 同一份工作日誌的並行 apply 會被鎖擋下；只有在持有者確定已死時才會破鎖。
- Skill **絕不主動執行** `git add/commit/push/fetch/pull/checkout/switch/merge/rebase`。
  一次執行只寫入日檔然後停下，不會因為「日誌寫完了」就順手 stage、commit 或移動 repo。
  日誌產出之後你另外要求 agent commit，那是你對自己 repo 的決定，這條規則管不到。
