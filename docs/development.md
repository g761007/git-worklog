# Development

**Languages:** English · [繁體中文](zh-TW/development.md) — [← back to the README](../README.md)

## Layout

```
git-worklog/                  # the skill (this whole directory is the skill)
├── SKILL.md                  # control layer: triggers, flow, script/reference map
├── agents/
│   └── openai.yaml           # host manifest: display name, UI metadata, model_config pointer
├── git_worklog/              # the engine + `git-worklog` CLI (stdlib only)
│   ├── __init__.py           # __version__ — the single source of the product version
│   ├── data/
│   │   └── provider_models.json  # shipped defaults for per-host subagent models; seeds ~/.git-worklog/provider_models.json
│   ├── markers.py            # day/index parser/serialiser; the format's definition
│   ├── paths.py              # user-level state dir ($GIT_WORKLOG_HOME, ~/.git-worklog)
│   ├── language.py           # BCP 47 resolution; the run's one output language
│   ├── config.py             # project config.json reader
│   ├── dates.py              # date/timezone contract; the day window everything agrees on
│   ├── providers.py          # per-host provider/model resolution (overrides, escalation)
│   ├── writer.py             # planning and transactionally writing day files + index.md
│   ├── preview.py            # the immutable preview record, its state machine and apply lock
│   ├── migrate.py            # one-time migration of a legacy worklog into .git-worklog/
│   ├── analysis/             # the pipeline: history -> manifest -> results (+ worktree, refs, coverage, reconcile)
│   └── cli/                  # version / doctor / validate / analyze / preview / apply / report
├── scripts/                  # thin command-line shells over the package (stdlib only)
│   ├── resolve_provider_model.py    # resolve per-host provider/model (overrides, escalation, halt-and-ask)
│   ├── resolve_date_range.py        # date/timezone parsing, day-span cap, per-day bounds
│   ├── resolve_ref_range.py         # report mode: tag/ref -> authoritative commit set
│   ├── check_worklog_coverage.py    # report mode: per-date covered / gap / no-commits
│   ├── collect_git_history.py      # repo metadata + per-day commit facts (no summaries)
│   ├── inspect_worktree.py         # staged/unstaged/untracked + worktree fingerprint
│   ├── build_analysis_manifest.py  # one day's manifest (analyze prepare does a range)
│   ├── collect_day_results.py      # flat-dir result validation (analyze collect also checks coverage)
│   ├── update_daily_worklog.py     # create/overwrite per-day files (transactional); preserve MANUAL
│   ├── rebuild_worklog_index.py    # rebuild index.md from day files; preserve index MANUAL
│   ├── validate_daily_worklog.py   # per-day file marker/title/UTF-8 validation
│   ├── validate_worklog_index.py   # index marker/order/link/UTF-8 validation
│   ├── migrate_legacy_worklog.py   # one-time split of the legacy single file
│   └── worklog_markers.py          # compatibility shim -> git_worklog.markers
└── references/               # detailed specs the skill loads on demand
    ├── report-mode.md
    ├── interaction-flow.md
    ├── date-parameter-contract.md
    ├── code-analysis-rules.md
    ├── subagent-contract.md
    ├── worklog-format.md
    └── provider-models.md

tools/
└── build_skill_zip.py        # build/verify skill.zip; ships what git tracks

docs/
├── naming-conventions.md     # canonical names: brand, skill, CLI, package, directories
└── plans/                    # design plans, newest last (yyyy-MM-dd-<topic>.md)
    ├── 2026-07-15-repo-worklog-skill-design.md   # the original spec (single-file era)
    ├── 2026-07-16-commit-author-and-report-mode.md
    └── 2026-07-16-git-worklog-v1-roadmap.md      # the v1.0 rebrand + refactor roadmap
```

The worklog itself is written to `.git-worklog/` at the repository root:

```
.git-worklog/
├── VERSION           # on-disk layout version
├── config.json       # project settings (timezone, …)
├── index.md          # navigation: a date-descending table linking every day
└── days/
    ├── 2026-07-15.md # exactly one day per file
    ├── 2026-07-14.md
    └── ...
```

## Development commands

Every command prints one JSON object to stdout; `--text` renders it for humans.
No install needed — run them from the skill directory:

```bash
cd git-worklog
python3 -m git_worklog version
python3 -m git_worklog --text doctor
python3 -m git_worklog --text validate --dir /tmp/.git-worklog
python3 -m git_worklog --text coverage 7d --repo /path/to/repo --timezone Asia/Taipei
python3 -m git_worklog --text refs --repo /path/to/repo --list-tags
python3 -m git_worklog --text report --tag v1.0.1 --repo /path/to/repo --language en
python3 -m git_worklog --text reindex --dir /tmp/.git-worklog
```

`scripts/` holds thin shells over the same engine, kept for anyone who scripted
against them. They are not the skill's path and not where new work goes.

## Building the release archive

```bash
python3 tools/build_skill_zip.py            # writes ./skill.zip
python3 tools/build_skill_zip.py --check    # verify an existing one
```

What ships is whatever `git ls-files git-worklog/` reports, so `.gitignore` is
the only place that decides what counts as build litter — there is no second
exclusion list to drift from it. The consequence: the archive contains what is
**committed**, and uncommitted edits do not ship.

It stages the skill under `git-worklog/`, so the directory a user unzips is the
name Claude Code triggers on. CI builds it on every PR, unzips it, and runs the
CLI out of it with nothing installed, because a broken archive is otherwise
invisible until release day.

## Tests

A stdlib-only `unittest` suite lives in `tests/` (no third-party dependencies).
Run it from the project root:

```bash
python3 -m unittest discover -s tests -v
```

It builds a controlled Git fixture (single/multi-commit days, revert, rename,
binary, empty repo) and covers the date contract, Git collection, worktree
inspection, the analysis manifest, the day-file engine (create, overwrite,
MANUAL preservation, no-change, corruption refusal), the index rebuild (summaries,
ordering, MANUAL preservation), both validators, multi-file preview consistency,
legacy migration, and the full deterministic pipeline. CI runs the same suite
(see `.github/workflows/ci.yml`).
`docs/plans/2026-07-15-repo-worklog-skill-design.md` section 27 lists the broader
acceptance-test matrix.
