# 使用方式

**語言：** [English](../usage.md) · 繁體中文 — [← 回到 README](../../README.zh-TW.md)

無參數呼叫時只會顯示選單，**在你選擇之前不做任何分析**：

```
/git-worklog
```

```
Choose what to do:

[Generate worklog] writes to .git-worklog/ — always previews first
 1. Today
 2. A specific date
 3. Last 7 days
 4. Last 30 days
 5. A custom date range
 6. Today, including uncommitted changes
 7. A custom date or range, including uncommitted changes

[Report from the existing worklog] read-only — nothing is modified
 8. Work summary for a period
 9. CHANGELOG for a version or tag
10. What a specific person worked on
11. Outstanding tech debt and follow-ups

Limits: generate up to 30 days, report up to 90 days.
Reply with an option number, or just describe what you want in any language.
```

選單是英文，因為它是**介面**文字；工作日誌本身不是。日誌語言跟著對話走，所以用中文提問、
從英文選單進去，產出的仍是 zh-TW 日誌。詳見[設定](configuration.md)。

也可以跳過選單，直接把要求寫在呼叫行上：

```
/git-worklog days=7
/git-worklog date=2026-07-01
/git-worklog from=2026-07-01 to=2026-07-10
/git-worklog date=2026-07-15 include_uncommitted=true
/git-worklog 整理最近 7 天，包含目前還沒有 commit 的修改
```

任何有效請求都會先產生 **dry-run 預覽**與一個 `preview_id`，以「寫入」／「確認更新」／
`apply <preview_id>` 確認後才會寫入。完整流程見 `git-worklog/references/interaction-flow.md`。

## 從工作日誌產生報告

日誌累積之後，可以直接提問，而不是再產生檔案。報告模式是**唯讀**的——答案直接回在對話裡，
不寫任何檔案，因此沒有 dry-run 需要確認。選單的 `8`–`11` 涵蓋常用情境，其餘直接在呼叫行
上講一句話即可：

```
/git-worklog 整理上一週工作摘要
/git-worklog 整理 v1.0.1 CHANGELOG
/git-worklog 我要交接，整理最近一個月的重點與待辦
/git-worklog Daniel 上個月做了什麼
/git-worklog 會員搜尋這功能是怎麼演進的
/git-worklog 目前累積哪些技術債與待追蹤事項
```

報告是從每日檔案產生的，直接沿用既有分析，不重新推導。若範圍內某天有 commit 卻沒有日誌，
skill 會明講並詢問是否先補齊——**絕不默默降級成摘要 commit message**。（沒有 commit 的日期
本來就不該有檔案，不會被當成缺漏。）

版本範圍以 **commit 集合**界定，不是日期：`v1.0.1` 指的是 `git log v1.0.0..v1.0.1`——
因為某天的日誌可能涵蓋不屬於該版本的 commit，而 cherry-pick 的 commit 也可能落在日期區間外。
`git-worklog report --tag v1.0.1` 會定出這個範圍，並拿它跟每日檔案**對帳**，列出日誌有寫、
但其實屬於別的版本的 commit——版本報告是被「告知」該略過什麼，而不是被「要求」自己想通。
報告語言與工作日誌的語言互相獨立：zh-TW 的日誌可以產出英文的 release note。
詳見 `git-worklog/references/report-mode.md`。

若專案已有舊的單檔 `docs/PROJECT_WORKLOG.md`，可用 `/git-worklog migrate`
（或 `python3 scripts/migrate_legacy_worklog.py`）一次性遷移：它會把每個日期拆成
`.git-worklog/days/<date>.md`，先預覽、絕不刪除舊檔，舊標記損壞時則拒絕遷移。
