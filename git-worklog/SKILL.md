---
name: git-worklog
description: Per-day project worklog from real Git diffs, and reports built from it.
disable-model-invocation: true
argument-hint: "a range (today, 7d, 2026-07-01), a question, or nothing for the menu"
---

# Git Worklog

Produce a **project** worklog (not a personal report) by reading the real Git
diffs and surrounding code for each day in a requested range, then write one
Markdown file per day under `.git-worklog/` and refresh `.git-worklog/index.md`,
while preserving human notes.

The deterministic work (date math, Git collection, Markdown surgery, preview
integrity) is done by the `git-worklog` CLI. The judgement work (reading code,
deciding what actually changed, writing the summary) is done by you and per-day
subagents. **Never let commit messages stand in for reading the diff.**

`python3` and `git` must be available; nothing needs installing. Run every
command as `python3 -m git_worklog <command>` from this directory. Each prints
one JSON object to stdout. Exit `0` means ok, `1` means it ran and found a
problem, `2` means it could not run.

**Use the CLI, never `scripts/`.** The `scripts/` directory holds thin
command-line shells over the same engine, kept for anyone who scripted against
them; they are not part of your flow and calling them will not give you a run id,
a preview, or anything you can apply.

---

## 0. Golden rules

- **No parameters → show the menu and stop.** Do not scan Git, spawn subagents,
  or generate anything until the user picks a range.
- **Read code, not just messages.** Every relevant commit's actual patch and the
  surrounding code context must be read. See `references/code-analysis-rules.md`.
  This holds in report mode too: where a day has no worklog, its commit messages
  are **not** a substitute — surface the gap and ask.
- **Whole project, every author.** The worklog always *stores* every author;
  never filter by `git config user.name/email`. Report mode may filter by author
  **only when the user names the person explicitly** — never infer who "我" is.
- **Max 30 calendar days for generation and backfill.** The cap bounds per-day
  subagent cost. Report mode only *reads* existing day files and spawns no
  subagents, so it reads up to 90 days (`--max-days 90`). Either way, over the
  limit → refuse, show the requested day count, ask the user to narrow. Never
  silently truncate.
- **Dry-run first, always.** Any valid request produces a preview only. Write
  only after the user explicitly confirms.
- **One file per day; the index is navigation.** Each day is
  `.git-worklog/days/<date>.md`; re-analysing one day never touches another day's
  file. `index.md` is rebuilt from the day files.
- **Preserve every day's MANUAL region and the index MANUAL region, forever.**
- **Never run** `git add/commit/push/fetch/pull/checkout/switch/merge/rebase`
  **on your own initiative.** A worklog run writes files and stops there: it
  does not stage them, commit them, or move the repository underneath the user.
  Nothing in this flow — not `apply`, not a backfill, not report mode — is ever
  a reason to touch git state, and "the worklog is finished, so I should commit
  it" is exactly the reasoning this forbids. What it does *not* forbid is the
  user asking for a commit themselves, in their own words, as a separate
  request; that is their decision about their repository, and this rule has no
  standing over it. The line is who decided, not which command ran.

---

## 1. Trigger & no-argument menu

**The user invokes this skill; you never invoke it yourself.** The frontmatter
carries `disable-model-invocation: true`, so the only way in is the user typing
`/git-worklog`. When they do, they decide *when* it runs and *over what range* —
that is the point, not a limitation to route around.

When invoked with **no usable arguments**, print this menu verbatim and wait —
do nothing else:

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

**The menu is interface text and is English on purpose.** The worklog itself is
not: content language follows §2a, so an English menu routinely produces a
zh-TW worklog. Print it as written rather than translating it — the wording is
pinned by a test against `agents/openai.yaml`, and paraphrasing it hands the
first thing the user sees back to model judgement, which is what this skill is
moving away from.

Options `1`–`7` go to §2 onward; `8`–`11` go to `references/report-mode.md`.
Option numbers map to: `1`→today, `2`→ask for a date, `3`→`days=7`,
`4`→`days=30`, `5`→ask for a from/to range, `6`→today + `include_uncommitted`,
`7`→ask for a date/range + `include_uncommitted`, `8`→ask for a period,
`9`→ask for a version/tag, `10`→**ask who** (never infer it), `11`→ask for a
period, defaulting to the whole worklog.

Full menu, option, and confirmation handling: `references/interaction-flow.md`.

---

## 1a. Route: generate or report

Two modes. Decide before doing anything else.

| The user wants | Mode | Goes to |
|---|---|---|
| The worklog itself built or filled in — 「整理今天」「整理最近 7 天」「補 7/1 的日誌」 | **Generate** (writes) | §2 onward |
| An **answer** drawn from the history — 「整理上一週工作摘要」「整理 v1.0.1 CHANGELOG」「Daniel 上個月做了什麼」「目前有哪些技術債」 | **Report** (read-only) | `references/report-mode.md` |

The tell: generate mode's product is **files**; report mode's product is **prose
in the conversation**. "整理今天" wants a day file. "整理上一週的工作摘要" wants
something to paste into a status update. When it is genuinely ambiguous, ask —
do not write files on a guess.

Report mode reads the existing day files plus Git, writes nothing, and therefore
has no dry-run or confirmation gate. Its one writing path is backfilling a gap,
which hands back to §§2–6 for just those dates, dry-run and confirmation
included.

**The menu covers both modes.** Options `1`–`7` are generate, `8`–`11` are
report; either mode is also reachable by natural language or explicit parameters
*after* the user has invoked the skill. The menu groups the two under headings
that name the consequence — one writes files, the other does not — because that
is the distinction a user needs before picking, not after.

---

## 2. Normalise input → canonical parameters

You (the model) convert natural language into canonical parameters; the scripts
never interpret free text. Canonical parameters:

`date` · `days` · `from` · `to` · `include_uncommitted`, plus the shortcuts
`7d`, `30d`, and a bare `YYYY-MM-DD`.

- "整理今天" → `date=<local today>`
- "最近一週" → `days=7`; "近一個月" → `days=30` (always 30, never the month length)
- "7 月 1 日到 7 月 10 日" → `from=2026-07-01 to=2026-07-10`
- "包含未提交 / 連 working tree 一起" → `include_uncommitted=true`

Modes `date` / `days` / `from`+`to` are mutually exclusive. Normalisation cases:
`references/date-parameter-contract.md`.

---

## 2a. Resolve the output language (roadmap §6.2)

**This is your job, not the scripts'.** The top of the priority order lives only
in this conversation — what the user asked for, what language you are speaking,
what the host is set to. A script cannot see any of it, and `--language` is how
you tell it. Resolve **once per run** and thread the same tag everywhere.

Priority, highest first:

1. **What the user asked for in this request** — "用英文整理" → `en`. Always wins.
2. **The project's `language` in `.git-worklog/config.json`**, if it is not
   `auto`. The scripts read this themselves; pass `--language auto` and let them.
3. **The language you are conversing in with this user, i.e. the host's
   language.** This is the normal case and it is a real answer — pass it, with
   `--language-source agent-host`.

Then also pass `--language-source` saying which of those it was, so the manifest
records *why* and not merely what:

| You resolved it from | `--language-source` |
|---|---|
| The user asking for a language in this request | `user-request` |
| The language of this conversation / your host | `agent-host` |
| Nothing to say — let config and env decide | omit, with `--language auto` |

**Do not let the repository choose.** English commit messages, English
identifiers, English comments and an English README decide nothing. A fully
English repo with a zh-TW conversation produces a zh-TW worklog. Do not "match
the codebase", and do not read this English SKILL.md as a hint.

**Do not infer from the OS locale.** You are an agent-hosted run, and
`--language` is exactly the mechanism that keeps a container pinned to `en_US`
from overriding a user speaking Chinese. The scripts will not consult the locale
for you (§6.2.5); that is deliberate, not a gap to fill.

If a run's manifest comes back with `source: "fallback"` and a
`LANGUAGE_NOT_RESOLVED` warning, you failed to pass a language and the run is
about to be written in English. **Re-run with an explicit `--language` rather
than accepting it** (§6.2.14) — unless English is genuinely right.

**Reports may differ from the worklog.** Day files are written in the language
of the run that produced them; a report is written in the language of the
request that asks for it (§6.2.11) — pass it to `report --language`, resolved the
same way as §2a. Reading zh-TW day files and producing an English release note is
correct and needs no conversion of anything on disk.

**Never translate**: file paths, code symbols, commit hashes, API/class/package
names, branch and issue references, or anything in `evidence[]`. Explaining a
term in the output language is welcome; renaming it is not.

---

## 3. Per-day analysis — one Day Subagent per day

Two commands bracket this section. `analyze prepare` decides **what** must be
analysed and **in which language**; `analyze collect` decides whether to
**believe** what came back. Everything between them — reading the patches,
understanding the code, writing the prose — is yours and the subagents'. The CLI
never does it and needs no model API key.

The field-by-field detail of what these commands emit — every output key, the
manifest contents, the error codes, the check mechanics — is in
`references/analysis-pipeline.md`. What must reach you *inline* is here.

**3a. Prepare the run** (deterministic, once for the whole range):

```
python3 -m git_worklog analyze prepare <range> --repo <root> \
    --host <anthropic|openai|google> \
    --language <tag|auto> --language-source <source> \
    [--timezone <IANA>] [--include-uncommitted]
```

- **`<range>` is what the user said, verbatim** — a shortcut like `7d`, or
  `--date` / `--days` / `--from`+`--to`. Do **not** resolve the dates yourself;
  prepare answers, and its `range` block is what you show in the dry-run.
- **Do not compute a model.** `--host` is the host you run under (Claude Code →
  `anthropic`, Codex → `openai`, Gemini → `google`); prepare resolves the model
  from the packaged config. Never guess the host; if you cannot tell, ask. If the
  model is unavailable it returns `MODEL_UNAVAILABLE` — **halt and ask**, never
  silently pick another. Details: `references/provider-models.md`.
- **`--language` / `--language-source` come from §2a**, resolved once and stamped
  on every manifest — a day whose result disagrees blocks the whole run.
- Keep `run_id`, `run_dir`, and every `tasks[]` entry (each carries a
  `manifest_path` and a `result_path`).
- On `ok:false`, report the error and stop (code table:
  `references/analysis-pipeline.md` §3).

**A `LARGE_DAY` warning means stop and ask before dispatching that day.** It
carries the commit, file and group counts and the resolved model, because one
subagent on the cheap model may not hold a big day. Offer to fan it out into the
recommended Code Analysis Subagents, to escalate the model (`--host … --escalate`,
redo `prepare`), or to proceed as-is — the same surface-and-ask you use for a gap
or an over-30-day range. Do not decide silently: a large day that ran anyway on
the cheap model is exactly the run that came back confidently wrong and nothing
noticed. The counts are there so a 60-file day and a 26-file one are not the same
question; proceeding is a legitimate answer, an unasked question is not.

**3b. Coverage.** Each manifest's `required_commit_file_pairs` marks the source
files the day's analysis **must account for** — naming one in a work item's
`files[]` is enough. A required file the result never mentions fails the day at
collect: a file changed but never described may never have been read, and that is
invisible in a result that otherwise looks confident. Which files are required,
and why deletions and non-source files are excused:
`references/analysis-pipeline.md` §5.

**3c. Spawn one Day Subagent** per day, passing its `manifest_path` **and its
`result_path`**. The subagent reads the real diffs and enough code context,
determines the **end-of-day state** (a feature added then reverted the same day
is *not* a live change), and **writes the structured JSON from
`references/subagent-contract.md` to that path with a Bash quoted heredoc**,
verifies that it parses, then replies only `DONE` — results are never passed back
as reply text, which drops and truncates them (§6a). **The Write and Edit tools
must not be used for this**: in a subagent either call vanishes — no result, no
error, nothing on disk — and the subagent cannot tell, so it cannot retry. That
includes repairing a result that failed its own parse check: the fix is another
whole-file heredoc, never a patch (§6a). It
must not write to the worklog. Days with no commits still write
`has_changes:false`. A large day may fan out into Code Analysis Subagents grouped
by work area, each writing to the manifest's `parts_dir` — never beside
`result_path`, where `collect` would fail the run over it
(`references/subagent-contract.md`).

**3d. Collect every day's result** (deterministic), once all subagents finish:

```
python3 -m git_worklog analyze collect --run-id <run_id> --repo <root>
```

It reads the run's own manifests, so no day can be dropped by being left off a
command line. Every result is checked three ways — **language**, **evidence and
prose symbols against the day's tree**, and **required-file coverage** — and each
failure fails the day. `partial_run:true` (any `missing`, `invalid`, `degraded`
or `unknown` date) blocks apply and exits `1`.

A failed or missing day is **not** an empty one: never treat it as "nothing
happened", never fall back to commit messages. Fix a failure by **re-running that
day's subagent** against the same manifest, then collecting again — never
hand-edit a result, never paper over a gap. Output fields and the check
mechanics: `references/analysis-pipeline.md` §6.

Model per host is resolved by `--host` (cost-first defaults, single source
`git_worklog/data/provider_models.json`); read `model` back off prepare's output.
Overrides, the per-host table, unavailable-model handling and opt-in escalation:
`references/provider-models.md`.

---

## 4. Uncommitted changes (only when include_uncommitted=true)

Pass `--include-uncommitted` to `analyze prepare` (§3a). It classifies
`staged` / `unstaged` / `untracked` (binary-aware), puts them on **today's**
manifest as `uncommitted_changes[]`, and returns a `worktree_fingerprint` on the
run.

Uncommitted content is attributed to **today only** — never spread across
historical days, because a file's mtime says when it was last written, not when
the work happened. In a multi-day range only today's task carries it; if today
is outside the range, prepare warns `UNCOMMITTED_NOT_IN_RANGE` rather than
silently dropping it. Present it in its own `### 尚未提交的異動` section, split
into staged / unstaged / untracked, and never describe it as committed.

---

## 5. Merge results, generate Markdown, dry-run

1. Merge the per-day results from `analyze collect` (§3d). If it reports any
   `missing`, `invalid`, `degraded` or `unknown` date — i.e. `partial_run` —
   mark the run **partial** and default to blocking apply (see error handling
   below).
2. Render each day's GENERATED Markdown from the day template in
   `references/worklog-format.md`, **in the run's resolved language** (§2a) —
   headings included. Omit empty sections — no walls of "無/N/A". Days with no
   changes get no file by default. Lead each day's summary with its single most
   useful sentence and **bracket it in SUMMARY markers**; that line becomes the
   index row, and without the markers a day written in anything but Traditional
   Chinese gets a blank one.
3. Hand the rendered days to `preview`, which freezes everything the apply will
   write. Pass only dates that actually have content:

```
git-worklog preview --run-id <run_id> --repo <root> <<'JSON'
{"entries": {"2026-07-15": {"generated_markdown": "..."}, "...": {...}}}
JSON
```

This is the **only** point at which your prose enters the tool. `preview`
re-runs `collect`'s verdict (a partial run is refused, `RUN_NOT_COLLECTED`),
plans each date as `create` / `overwrite` / `no_change` preserving MANUAL,
rebuilds the index over the pending summaries, and stores the complete final
text of every target file on the record. It returns `preview_id`, `files[]`
(path + action + sha256), `previews` (full per-day file text), `index_preview`,
`language`, `expires_at`, and `not_written` (dates the run analysed that get no
file). Nothing is written and `.git-worklog/` is not created.

A day the run never analysed is refused (`UNKNOWN_DATE`) — do not work around it
by rendering it anyway; prepare a run that covers it. A corrupt existing day file
aborts with `CORRUPT_MARKERS`, a corrupt `index.md` with `INDEX_CORRUPT_MARKERS`
— never guess a repair.

The record also fixes the **language**. A user who confirms a zh-TW preview and
then asks for English is asking for a **different worklog**, not the same one
rendered differently: build and confirm a new preview rather than applying the
old payload under a new language (§6.2.10).

Previews expire after 24h (`--ttl-seconds` to change it). `git-worklog preview
--show <id> --check` reports a stored preview's state; `--cancel <id>` retires
one the user decided against.

4. Show the dry-run summary (`references/interaction-flow.md` has the full
   layout). The load-bearing parts: the resolved range and timezone; the output
   **language** — and if it came from `fallback`, say so, because the user may
   want to correct it before anything is written; the subagent provider/model;
   each date's planned action (create / overwrite / no-change); the preserved
   MANUAL dates; every day file's full preview and the index preview; the
   `preview_id`; and the line **"No files have been modified."** If `not_written`
   is non-empty, say which dates and why — a day the user expected and does not
   get should not be discovered after the write.

---

## 6. Apply only after explicit confirmation

Natural-language confirmations ("寫入", "確認更新", "套用剛才的預覽", "把這份寫進去")
or `apply <preview_id>`.

1. Apply the preview. This is the whole step:

```
git-worklog apply --preview-id <preview_id>
```

   **Do not pass the day content again — there is nowhere to pass it.** The
   record holds the exact bytes the user just approved, and apply writes those.
   Re-rendering, re-reading the results, or re-dispatching a subagent at this
   point would produce a worklog nobody previewed, which is precisely what the
   record exists to prevent.

   Apply re-checks the world first: repository identity, git dir, branch, HEAD,
   submodules, the working tree (when the run read it), every target day file,
   `index.md`, the day-file listing, the run's manifests and results, and the
   project's language settings. It writes the day files as one transaction
   (staged, validated, atomically swapped, rolled back on any failure), then
   rebuilds the index. `.git-worklog/` is created now if it was missing. No git
   add / commit / push.

2. On a refusal, **do not write.** Report the code and build a fresh preview:

   | Code | Meaning |
   |---|---|
   | `PREVIEW_STALE` | Something moved since the preview; `mismatches[]` names what. |
   | `PREVIEW_EXPIRED` | Past its TTL. |
   | `PREVIEW_ALREADY_APPLIED` | Spent. Never re-apply. |
   | `PREVIEW_CANCELLED` | The user retired it. |
   | `PREVIEW_FAILED` | An earlier apply failed and rolled back. Not retryable. |
   | `PREVIEW_INTERRUPTED` | An apply died mid-write; whether it wrote is unknown. Check `.git-worklog/` before doing anything else. |
   | `APPLY_LOCKED` | Another apply is writing to this worklog. Wait. |
   | `INDEX_WRITE_FAILED` | The day files **were** written; only `index.md` was not. No data is lost — the index is a pure function of the day files, so repair it with `python3 -m git_worklog reindex --apply`. |

3. Confirm with `python3 -m git_worklog validate`, then report the actual
   update from apply's own output: `written_dates`, `preserved_manual_dates`,
   `index_action`, and the target directory.

---

## 7. Error handling (summary)

- **Not a Git repo / >30 days / corrupt markers / non-UTF-8:** stop, report,
  never auto-repair. `preview` refuses a corrupt target day file
  (`CORRUPT_MARKERS`) and a corrupt `index.md` (`INDEX_CORRUPT_MARKERS`) so its
  MANUAL is never lost; the validators list every issue.
- **Unreadable code (permissions, missing submodule):** record what was not
  analyzed, lower `confidence`, note it in `uncertainties`; never fake analysis.
- **A day's subagent failed:** keep other days, mark the run partial, block apply
  by default — `preview` refuses a partial run outright (`RUN_NOT_COLLECTED`).
  The user may choose to write only the successful days; that means a run
  prepared for just those dates, not a preview that quietly leaves days out.
- **A day is `missing` and its `result_path` does not exist on disk:** the
  analysis never reached the file. Re-dispatch that date against the same
  manifest, with the §9 prompt template's heredoc block reproduced verbatim —
  a subagent that reached for the Write tool instead produces exactly this
  signature: no file, no error, and nothing in its reply that looks wrong. Do
  not write the result yourself to get past it, and do not re-run `prepare`.
- **A day is `invalid` with `RESULT_NOT_JSON` and the subagent went quiet:** it
  caught its own parse failure and then tried to patch the file with `Edit`,
  which vanishes exactly like `Write`. The analysis is not lost — that subagent
  still holds it. Tell it to rewrite the **whole** file with the same heredoc
  (never `Edit`, never a patch) and to escape every `"` inside a JSON string,
  which is the usual cause. Re-dispatching from scratch throws away work that is
  one rewrite from being correct.
- **Date exists but re-analysis finds no commits:** do not auto-delete the day
  file; show the diff, keep MANUAL, and require explicit confirmation to clear
  GENERATED.
- **A legacy worklog is present:** never migrate automatically. Offer
  `python3 -m git_worklog migrate` (dry-run + confirm); it never deletes the
  source. Two shapes qualify — a flat `PROJECT_WORKLOG/` directory
  (`--from-dir`) and the single `docs/PROJECT_WORKLOG.md` (`--from-file`). With
  neither flag it auto-detects, directory first.
- **Writing refused with `LEGACY_LAYOUT`:** the target directory still holds its
  day files at the root rather than under `days/`. Do not work around it by
  passing a different `--dir` — offer the migration. Reading a legacy directory
  (validate, coverage, report mode) keeps working untouched.

Full rules: `references/interaction-flow.md`, `references/code-analysis-rules.md`.

---

## Reference & command map

| Need | Read |
|------|------|
| `analyze prepare` / `collect` output fields, manifest contents, error codes, check mechanics | `references/analysis-pipeline.md` |
| Report mode: scope (dates vs refs), coverage, gaps, scenarios | `references/report-mode.md` |
| Menu, options, dry-run summary, confirmation, apply | `references/interaction-flow.md` |
| Date modes, timezone, 30-day limit, NL normalisation | `references/date-parameter-contract.md` |
| Diff reading, context expansion, final-state, merge/revert/rename/binary/lockfile/submodule | `references/code-analysis-rules.md` |
| Day/Code-Analysis subagent prompts, return schema, confidence, evidence | `references/subagent-contract.md` |
| Directory layout, day/index markers, create/overwrite, migration | `references/worklog-format.md` |
| Per-host models, overrides, unavailable-model handling, escalation | `references/provider-models.md` |

Every deterministic step is a CLI command (§3). Run each as
`python3 -m git_worklog <command>` from this directory — no install needed. This
is the whole surface you need; there is nothing in `scripts/` that is not here.

| Command | Role |
|---------|------|
| `analyze prepare` | Mint a run: resolve the range, timezone and model, then write one manifest per day (what to analyse, in which language, which files are required, where to write the result) |
| `analyze collect` | Read the run's results back and check them: schema, language, evidence accuracy, coverage, missing/unknown days |
| `preview` | Freeze the apply: store every target file's final text, the fingerprints, the language and a TTL. Returns a `preview_id`. Writes nothing |
| `apply` | Write that stored payload after re-checking the world. Takes a `preview_id` and nothing else |
| `report` | Report mode's entry point: resolve the scope (dates or a tag's commit set), check coverage, reconcile the tag against the day files, resolve the output language. Writes nothing — the prose is yours |
| `coverage` | Per-date `covered` / `gap` / `no-commits`. Exit `1` means a gap — real work nothing has analysed. A primitive `report` composes |
| `refs` | Resolve a tag/ref to its authoritative commit set + derived dates. A primitive `report` composes; `--list-tags` lists what exists |
| `migrate` | One-time migration of a legacy worklog (flat `PROJECT_WORKLOG/`, or the single `docs/PROJECT_WORKLOG.md`) into `.git-worklog/`. Dry-run unless `--apply` |
| `reindex` | Rebuild `index.md` from the day files. Normal runs never need it — `apply` does it — but it is the repair for `INDEX_WRITE_FAILED` |
| `doctor` | Is this environment able to run the tool? |
| `validate` | Is the worklog on disk well-formed? Day markers, index links, config, language stamps |
| `version` | CLI / layout / config-schema versions |
