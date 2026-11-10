# Usage

**Languages:** English · [繁體中文](zh-TW/usage.md) — [← back to the README](../README.md)

Run with no arguments to get the menu; the skill does nothing until you pick an
option:

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

The menu is English because it is interface text. The worklog itself is not: its
language follows the conversation, so asking in Chinese gets you a zh-TW worklog
from an English menu. See [Configuration](configuration.md).

Or skip the menu and say what you want on the invocation line:

```
/git-worklog days=7
/git-worklog date=2026-07-01
/git-worklog from=2026-07-01 to=2026-07-10
/git-worklog date=2026-07-15 include_uncommitted=true
/git-worklog 整理最近 7 天，包含目前還沒有 commit 的修改
```

Every valid request produces a **dry-run preview** with a `preview_id`. Confirm
with “寫入” / “確認更新” / `apply <preview_id>` to write. See
`git-worklog/references/interaction-flow.md` for the full flow.

## Reporting from the worklog

Once days are logged, ask questions instead of building files. Reporting is
**read-only** — the answer comes back in the conversation, nothing is written, so
there is no dry-run to confirm. Menu options `8`–`11` cover the common cases;
anything else is a sentence after the invocation:

```
/git-worklog 整理上一週工作摘要
/git-worklog 整理 v1.0.1 CHANGELOG
/git-worklog 我要交接，整理最近一個月的重點與待辦
/git-worklog Daniel 上個月做了什麼
/git-worklog 會員搜尋這功能是怎麼演進的
/git-worklog 目前累積哪些技術債與待追蹤事項
```

Reports are built from the day files, so they inherit their analysis rather than
re-deriving it. If a date in the range has commits but no worklog, the skill says
so and offers to fill it in first — it never quietly downgrades to summarising
commit messages. (A date with no commits has no file by design, and is not
treated as missing.)

Version scopes are resolved by commit set, not by date: `v1.0.1` means
`git log v1.0.0..v1.0.1`, because a day file can cover commits outside a release
and a cherry-pick can land outside its dates. `git-worklog report --tag v1.0.1`
settles that scope and then **reconciles** it against the day files, listing the
commits they describe that belong to a different release — a release report is
told what to leave out rather than asked to work it out. Report language is
independent of the worklog's: zh-TW day files can produce an English release
note. See `git-worklog/references/report-mode.md`.

Already have a legacy single-file `docs/PROJECT_WORKLOG.md`? Migrate it once with
`/git-worklog migrate` (or `python3 scripts/migrate_legacy_worklog.py`). It
splits each date into `.git-worklog/days/<date>.md`, previews first, never deletes
the old file, and refuses if the legacy markers are corrupt.
