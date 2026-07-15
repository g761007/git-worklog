# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-07-16

### Changed

- **BREAKING:** the worklog is now a directory, not a single file. It moves from
  `docs/PROJECT_WORKLOG.md` to `PROJECT_WORKLOG/` at the repository root — one file
  per day (`<date>.md`) plus a navigation `index.md`. Re-analysing a day rewrites
  only that day's file; every other day file is left byte-for-byte untouched, which
  keeps diffs small, avoids re-reading/rewriting one large file, and prevents
  multi-author conflicts on different dates.
- Each day file keeps a human-owned `MANUAL` region (preserved verbatim, including
  any content placed after `MANUAL:END`) and a tool-owned title/meta header plus
  `GENERATED` region. `index.md` has its own preserved `MANUAL` region.
- The apply-time preview fingerprint is now multi-file (index hash + per-day file
  hashes + the day-file directory listing), so a change to any target day file, to
  `index.md`, or to the set of day files invalidates a stale preview.

### Added

- `update_daily_worklog.py` — transactional multi-day writer (stage → validate →
  atomic swap → rollback); a failed run never leaves some days updated and others
  not.
- `rebuild_worklog_index.py` — rebuild `index.md` from the day files, preserving the
  index `MANUAL` region; an `overrides` input previews pending writes without
  touching disk.
- `validate_daily_worklog.py` / `validate_worklog_index.py` — per-day-file and index
  structural validation.
- `migrate_legacy_worklog.py` (`/repo_worklog migrate`) — one-time split of a legacy
  single-file worklog. Previews first, never deletes the legacy file, never
  overwrites an existing day file, and refuses corrupt or marker-colliding input.

### Removed

- `update_worklog.py` and `validate_worklog.py` (replaced by the per-day scripts
  above).

### Fixed

- Writer scripts emit a single JSON object on every path — an unexpected error can
  no longer surface as a bare Python traceback.
- Generated content containing a bare `REPO_WORKLOG` marker line is refused up front
  (`GENERATED_CONTAINS_MARKER`) instead of producing an unparseable day file; the
  same guard protects migration.
- Transactional writes no longer leak a staged temp file when validation fails, and
  rollback restores the original files atomically.
- Content after a day file's `MANUAL:END`, and duplicate end markers, are now handled
  correctly.

### Migrating from 0.1.0

Run `/repo_worklog migrate` (or `python3 scripts/migrate_legacy_worklog.py`) to
convert an existing `docs/PROJECT_WORKLOG.md` into `PROJECT_WORKLOG/`. It previews
the split first and never deletes the legacy file — remove it yourself once you are
satisfied.

## [0.1.0] - 2026-07-15

### Added

- Initial release of the `repo_worklog` agent skill: turns a Git repository's real
  code history into a per-day project worklog by reading actual diffs and the
  surrounding code (never just commit messages), with one day subagent per day and
  the whole project's history (every author).
- Deterministic, stdlib-only helper scripts — date-range resolution, Git history
  collection, worktree inspection, analysis-manifest building, and the worklog
  write/validate engine — each printing a single JSON object.
- Dry-run-first workflow: every request previews first, and a preview fingerprint
  (repo / branch / HEAD / worktree / worklog hash) gates each apply. MANUAL regions
  are preserved; the skill never runs `git add/commit/push`.
- Reference docs (interaction flow, date-parameter contract, code-analysis rules,
  subagent contract, worklog format, provider models), a bilingual README, and the
  MIT license.
- A stdlib-only `unittest` suite and GitHub Actions CI on Python 3.9 / 3.12 / 3.13,
  with a `skill.zip` release artifact.

[0.2.0]: https://github.com/g761007/repo_worklog_skill/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/g761007/repo_worklog_skill/releases/tag/v0.1.0
