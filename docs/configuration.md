# Configuration

**Languages:** English · [繁體中文](zh-TW/configuration.md) — [← back to the README](../README.md)

- **Target directory:** defaults to `.git-worklog/` at the repo root
  (`update_daily_worklog.py --dir` / `rebuild_worklog_index.py --dir` to override).
- **Timezone:** auto-detected (`$TZ` → `/etc/localtime` → offset); override with
  `resolve_date_range.py --timezone Asia/Taipei`.
- **Output language:** the worklog is written in the language you are asking in,
  not the language the repository is in. English commits, English identifiers and
  an English README do not make an English worklog. Priority: what you asked for
  → `--language` → `.git-worklog/config.json` → the agent host →
  `GIT_WORKLOG_LANGUAGE` → system locale → English. Tags are BCP 47 (`zh-TW`,
  `en`, `ja`); bare `zh` is refused as ambiguous, and `zh-TW`/`zh-CN` are never
  treated as the same setting. Paths, code symbols, commit hashes and API names
  are never translated in any language. `index.md` fixes its language on first
  build so it does not churn between contributors. See roadmap §6.2.
- **Subagent models:** read from **your own file**,
  `~/.git-worklog/provider_models.json`. The first run copies it from the
  defaults the skill ships (cost-first — Claude Haiku 4.5 / GPT-6 Luna /
  Gemini 3.8 Flash) and it is never rewritten after that, so when a provider
  renames or retires a model you edit the file instead of waiting for a
  release. `git-worklog models` shows it, and
  `git-worklog models --host anthropic --model <id> --apply` makes the edit as a
  command — which is how you ask the coding agent you are in to put its host's
  current models there. An upgrade that ships newer defaults does not touch
  your file; `git-worklog doctor` lists where the two differ. For one run,
  `GIT_WORKLOG_{ANTHROPIC,OPENAI,GOOGLE}_MODEL` or an explicit `--model` still
  wins. See `references/provider-models.md`.
- **Preview state:** stored outside the repo in `~/.git-worklog/previews/`.
- **Subagent results:** each Day Subagent writes its analysis to
  `~/.git-worklog/analysis/<run_id>/<date>.json` rather than returning it as
  reply text, which drops and truncates. Files are kept after the run, so a
  surprising worklog entry can be traced to the analysis behind it.

## State directory

Everything the tool remembers between commands lives in one directory outside
your repositories — `~/.git-worklog/`, or wherever `$GIT_WORKLOG_HOME` points:

| Path | Holds |
|---|---|
| `analysis/<run_id>/tasks/` | one manifest per day: what to analyse, in which language, which files are required |
| `analysis/<run_id>/results/` | what each Day Subagent concluded |
| `previews/` | the exact final text of every file a pending apply would write |
| `view/` | the pages `git-worklog view` writes, rebuilt from the worklog on every run |
| `provider_models.json` | the subagent model each host uses — yours to edit; copied from the shipped defaults on first use |

**Nothing here is ever deleted automatically.** A preview past its 24h TTL stops
being applicable but stays on disk, and every run's manifests and results are
kept on purpose, so a worklog entry that reads oddly months later can still be
traced back to the analysis behind it. The directory therefore only grows, and
there is no `prune` command — deciding when a run stops being worth keeping is
yours, not the tool's.

**Deleting it is safe, with one thing to keep.** An applied worklog lives in its
repository under `.git-worklog/` and does not depend on this directory at all.
You lose a preview you have not applied yet — `apply` will answer
`UNKNOWN_PREVIEW`, and you build a new preview — and you lose any edits to
`provider_models.json`, which is then copied afresh from the shipped defaults.
Keep that one file if you changed it; otherwise delete the whole tree, or just
the `analysis/<run_id>/` directories you no longer care about.
