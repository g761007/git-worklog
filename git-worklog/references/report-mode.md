# Report mode

How the skill answers a **question** about the project's history — "幫我整理上一週
工作摘要", "整理 v1.0.1 CHANGELOG" — instead of producing worklog files.

Report mode is **read-only**. It reads the day files already under
`.git-worklog/` plus Git facts, and returns prose **in the conversation**. It
writes nothing, so there is no dry-run, no `preview_id`, and no confirmation
gate. The one path that can write is backfilling a gap, and that hands off to the
ordinary generation pipeline with its own dry-run and confirmation (§4).

Generation mode is the subject of `SKILL.md` §§2–6; this file covers report mode
only. Mode routing is `SKILL.md` §1a.

---

## 1. What report mode is for

The day files are expensive, high-quality material: each one was written by a
subagent that read the real diffs and the surrounding code. Report mode is the
consumer. It **re-uses that analysis; it does not redo it.**

The corollary matters: a report is only as good as the day files behind it. Where
they are missing, report mode does not quietly fall back to paraphrasing commit
messages — that is precisely what this skill exists not to do. It surfaces the
gap and asks (§4).

---

## 2. One command settles the scope

Every report starts with `report`. It resolves the scope, checks coverage,
reconciles a tag against the day files and resolves the output language in one
call, and it writes nothing:

```
# Date scope — a period.
python3 -m git_worklog report 7d --repo <root> --language <tag>
python3 -m git_worklog report --from 2026-07-13 --to 2026-07-15 --repo <root>

# Ref scope — a release.
python3 -m git_worklog report --tag v1.0.1 --repo <root> --language <tag>
```

Pass **one** scope. Asking for both is refused (`ARG_CONFLICT`) rather than
resolved by precedence, because the two answer different questions and guessing
which one the user meant produces a confident answer to neither.

Do not reach for `coverage` or `refs` here. They are the primitives `report`
composes, and they exist for their own sake; using them directly for a report
means doing the reconciliation below by hand, which is exactly what this command
exists to stop.

### Date scope — the default

The user names a period: 上一週, 這個月, 最近 30 天, 7/1 到 7/10.

**Dates are authoritative.** Normalise to `--from`/`--to` (or `--date`/`--days`,
or a `NNd` shortcut); `report` resolves them by the same date contract generation
mode uses, with report mode's own 90-day cap (§3). There is no separate date step
to run, and nothing to reconcile: the dates *are* the scope, so anything
committed on them is in it by definition.

### Ref scope — versions and tags

The user names a release: 「整理 v1.0.1 CHANGELOG」, 「上一版之後改了什麼」.

**The commit set is authoritative, not the dates.** `report --tag` returns
`commits[]` (the authority), `scope.commit_range`, `scope.prev_tag`,
`scope.date_span` and `scope.first_release`, plus the `reconciliation` block
below. `--from-ref`/`--to-ref` set an explicit pair; `refs --list-tags` lists
what exists.

**Why the commit set has to win.** A version is bounded by commits; the worklog
is indexed by calendar date. Converting a tag to a date span and reading those
day files is wrong in both directions at once:

- **Over-inclusive** — a day file describes *everything* committed that day,
  including work outside the range: another branch, or commits that landed after
  the tag was cut that afternoon.
- **Under-inclusive** — a cherry-pick keeps its original author date, so it
  belongs to the range while sitting on a day outside the span.

So: `commits[]` is the scope, `dates[]` only locates the day files worth reading,
and the two are **reconciled** — by the command, not by you. Day files carry each
commit's short hash, so `report --tag` checks them against the range and hands
back a `reconciliation` block. Obey it literally:

| field | meaning | what you do |
|---|---|---|
| `out_of_range[]` | The day files describe these, and they belong to a **different release**. | **Leave them out.** Say nothing about them. Each entry carries `cited_on`, so you can see which day file tempted you. |
| `unbacked[]` | In this release, but **no day file describes them**. | Do not claim to have analysed them. List them as shipped-but-unanalysed, or backfill (§4). |
| `backed[]` | In this release and described by a day file. | This is what the report is made of. |
| `unresolved[]` | Cited by a day file, but names no commit in this repository. | Usually prose that happens to look like hex. If it does look like a hash, the day file is citing something fabricated or rebased away — say so, do not describe it. |

A non-empty `out_of_range[]` is **normal**, not an error — a day file describes
everything committed that day, and a release is a slice through that. It is why
the command exits `0` in that case. What is not acceptable is describing those
commits anyway.

`backed[] + unbacked[]` is always the whole range, and every citation in the day
files lands in exactly one of `backed` / `out_of_range` / `unresolved`. Nothing
is silently dropped, so a report that mentions work in none of these buckets is
work you invented.

Report `scope.first_release: true` plainly. "Everything since the beginning of
the project" is a very different answer from "changes since the last release",
and the user should not have to infer which one they got.

---

## 3. The 90-day reading cap

Generation and backfill cap at 30 calendar days because each day costs a
subagent. Report mode reads files already on disk and spawns nothing, so `report`
reads up to **90 days** (`--max-days`, default 90).

The cap still exists — 90 bounds how much day-file text is pulled into context,
not cost. Over 90 days: say so, and ask the user to narrow, exactly as generation
mode does at 30. Never silently truncate.

A ref scope whose `date_span` exceeds 90 days is subject to the same limit.

---

## 4. Coverage, and the gap question

`report` establishes what is actually backed by analysis, in the same call that
resolved the scope — a ref scope's days are a set with gaps rather than a span,
and it already knows which. Exit `1` means at least one gap: the command ran and
the answer to "can I report on this?" is no. Per date it returns a `status`:

| status | meaning | action |
|---|---|---|
| `covered` | has commits **and** a day file | use it |
| `gap` | has commits but **no** day file | **real gap** — ask (below) |
| `no-commits` | no commits, so no file is expected | nothing missing; ignore |

**`no-commits` is not a gap.** `worklog-format.md` §6 gives a commitless day no
file deliberately. Days whose only commits edited `.git-worklog/` also land
here — the collector drops them as self-referential — so a worklog-only day is
never offered for backfill.

Also handle `dir_exists: false` (the project has never run the skill): say so and
offer to generate, rather than returning an empty report.

### When `gaps` is empty

Produce the report. Nothing to ask.

### When `gaps` is non-empty — ask, and recommend backfilling

Show the gap dates with their commit counts, then ask. **Recommend backfilling
first**, because a report stitched from commit messages violates the skill's core
principle invisibly — the user cannot see that the quality was diluted. Backfill
also persists, so the next report over that period is free.

```
這個範圍內有 3 天有 commit，但還沒有工作日誌：

- 2026-07-13（4 個 commit）
- 2026-07-14（2 個 commit）
- 2026-07-15（7 個 commit）

沒有日誌的日子，我只能看到 commit message，看不到實際的程式碼變更。

1. 先補齊這 3 天的日誌，再產生報告（建議）
2. 直接產生報告，並標注這 3 天的資料較淺
3. 取消
```

| choice | what happens |
|---|---|
| 1 | Run the ordinary generation pipeline for **only the gap dates** — `SKILL.md` §§3–6, with its own dry-run, `preview_id`, and explicit confirmation. Then produce the report. |
| 2 | Produce the report, and **mark the shallow dates in it** (below). |
| 3 | Stop. |

Backfill is bounded by the 30-day cap (it spawns subagents). More than 30 gap
dates: say so, and offer to backfill in batches or to proceed with choice 2 —
never start a 45-day generation run.

### Marking a report the user chose not to backfill

Choice 2 is legitimate, but the report **must** say what it is built on. This is
honest reporting, not a decorative footnote:

```
> 註：2026-07-13～2026-07-15 沒有工作日誌，以下內容僅根據 commit message
> 與檔案清單，未經程式碼分析，可靠度低於其他日期。
```

Never present a message-derived paragraph in the same voice as an analysed one.

---

## 5. Producing the report

The orchestrator reads the day files `report` listed in `material[]` (plain
Markdown) and synthesises the answer itself. **Do not spawn a subagent for
synthesis:** the day files are already digested analysis, so another agent only
adds a layer of paraphrase and a chance to lose detail. The only subagents report
mode ever causes are the backfill pipeline's.

Rules:

- **Read the GENERATED region and the MANUAL region.** Human notes in MANUAL are
  often the most valuable part of a day.
- **Obey the `reconciliation` block** (§2) for a ref scope. It is the answer to
  "what may this release's report describe?", already computed — not a hint to
  weigh against your reading of the day file.
- **Write the report in `language.resolved`, not the language of the day files**
  (roadmap §6.2.11). `report` already decided it: pass `--language` with what the
  user asked for, or the language of this conversation when they did not say
  (`--language-source` records which it was). A report is not bound to what it
  reads — reading `zh-TW` day files and producing an English release note is
  correct, and converts nothing on disk: you are writing new prose, not
  translating a file. A range whose days are in more than one language is not a
  problem to resolve either; it is normal, and the report is still written in one
  language: the resolved one. The repository's language never votes, and neither
  does the day files'.
- **Never translate identifiers when quoting a day file.** File paths, code
  symbols, commit hashes, API names, branch and issue references and author
  names stay verbatim in any output language — a reader must be able to grep
  them straight out of the report. Day-file section headings are the day's
  language and are not quoted as if they were yours; describe the content
  instead.
- **Answer the question asked.** A CHANGELOG is not a diary; a weekly summary is
  not a commit list. Structure the output for its purpose.
- **Attribute where it matters.** Day files carry `參與者` and per-commit authors
  (`worklog-format.md` §3).
- **Cite dates.** A reader must be able to reach the underlying day file, so
  reference `.git-worklog/days/<date>.md` for anything substantive.
- **Never invent.** If the day files do not support a claim, say so instead of
  reaching for the commit log.
- Uncertainty is reported, not smoothed over — the same discipline as
  `subagent-contract.md` §7.

---

## 6. Scenarios

One flow serves all of these. They differ only in scope and in what the user is
asking for — none is a separate code path.

| Scenario | Example | Scope | Notes |
|---|---|---|---|
| Period summary (weekly/monthly) | 「幫我整理上一週工作摘要」 | date | Lead with outcomes, not commits. |
| Release CHANGELOG | 「整理 v1.0.1 CHANGELOG」 | ref | Obey the `reconciliation` block (§2). |
| Handoff | 「我要交接，整理最近一個月的重點與待辦」 | date | Lean on each day's `接手者快速閱讀`. |
| Personal contribution | 「Daniel 上個月做了什麼」 | date + author | See the filter rule below. |
| Feature history | 「會員搜尋這功能是怎麼演進的」 | date + files | Filter day files by the paths involved. |
| Debt and follow-ups | 「目前累積哪些技術債與待追蹤事項」 | date | Aggregate `後續事項` / `相容性與風險` / `維護注意事項`. |

The last one is nearly free: those fields already exist in every day file
(`worklog-format.md` §3), so the work is aggregation, not analysis.

### Author filtering

The worklog **stores** every author, always — that rule is unchanged
(`SKILL.md` §0). Report mode may filter by author, under one condition:

- **Only when the user names the person explicitly** — "Daniel 上個月做了什麼".
- **Never infer "me"** from `git config user.name/email`. If the user says "我上
  個月做了什麼" and has not said who they are, ask. Guessing silently produces a
  confidently wrong report about the wrong person.
- Match against the day files' `參與者` and per-commit authors. Say how you
  matched, and flag near-misses (the same human under two spellings) rather than
  merging them on a hunch.

---

## 7. Errors

| Situation | Response |
|---|---|
| `dir_exists: false` | The project has no worklog yet. Offer to generate; do not report on nothing. |
| `NO_SCOPE` | Neither a date nor a ref scope was given. Ask what period or release the user means. |
| `ARG_CONFLICT` | Both scopes were given. Pick one with the user; do not choose for them. |
| `NO_TAGS` | No tags to resolve a version against. Ask for an explicit date range. |
| `UNKNOWN_TAG` | Report it with the `available_tags` list from `refs --list-tags`. |
| `scope.first_release: true` | State that the range runs from the project's first commit. |
| Range over 90 days | Report the span and ask the user to narrow. Never truncate silently. |
| Over 30 gap dates | Backfill cannot run in one pass. Offer batches, or proceed marked-shallow. |
| A day file has corrupt markers | Report it and skip that day; never guess a repair (`worklog-format.md` §8). |

Report mode never runs `git add/commit/push/fetch/pull/checkout/switch/merge/rebase`,
and never writes to `.git-worklog/` except through the backfill pipeline.
