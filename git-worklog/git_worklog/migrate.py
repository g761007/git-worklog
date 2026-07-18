"""One-time migration of a legacy worklog into the ``.git-worklog/`` layout.

Two legacy shapes are migrated, because the worklog has moved twice:

**Single file** (``from_file``, pre-v0.2) — every day lived in one
``docs/PROJECT_WORKLOG.md`` delimited by ``REPO_WORKLOG:ENTRIES`` and per-date
``START/END`` markers. Each date is split into its own day file, preserving that
date's GENERATED and MANUAL text.

**Flat directory** (``from_dir``, v0.2–v0.5) — ``PROJECT_WORKLOG/<date>.md``
with the index alongside. Day files move to ``.git-worklog/days/<date>.md`` and
their markers are re-tagged ``REPO_WORKLOG`` → ``GIT_WORKLOG``. Nothing else in
a day file changes: the title, meta blockquote, GENERATED prose and MANUAL notes
are copied byte for byte, so a migration never rewrites a worklog's content or
its language. The index is rebuilt (its links must now point into ``days/``)
with its MANUAL region preserved.

With neither given the source is auto-detected, directory first.

It is **never** invoked by normal runs — only explicitly. Dry-run is the default.
It never deletes the source, and never overwrites a day file that already exists
(those are left for the user to reconcile). If the legacy markers are corrupt, it
refuses to migrate rather than guess.
"""

from __future__ import annotations

import hashlib
import os
import re

from git_worklog import markers as wm
from git_worklog import writer

DEFAULT_LEGACY = os.path.join("docs", "PROJECT_WORKLOG.md")
DEFAULT_LEGACY_DIR = wm.LEGACY_WORKLOG_DIRNAME
DEFAULT_DIR = wm.WORKLOG_DIRNAME

_LEGACY_MARKER_RE = re.compile(
    rf"^<!--\s*{wm.LEGACY_PREFIX}:(\d{{4}}-\d{{2}}-\d{{2}}):(GENERATED|MANUAL):(START|END)\s*-->$"
)
_ENTRIES_RE = re.compile(rf"^<!--\s*{wm.LEGACY_PREFIX}:ENTRIES:(START|END)\s*-->$")


class MigrateError(ValueError):
    """A migration that must not proceed, carrying the wire code.

    Mirrors :class:`git_worklog.dates.DateError` and
    :class:`git_worklog.analysis.AnalysisError`.
    """

    def __init__(self, code: str, message: str, **extra):
        self.code = code
        self.message = message
        self.extra = extra
        super().__init__(message)

    def as_error(self) -> dict:
        """The error dict as it goes on the wire."""
        return {"code": self.code, "message": self.message, **self.extra}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_legacy(text: str) -> "dict[str, dict[str, str]]":
    """Extract ``{date: {"generated": ..., "manual": ...}}`` from the legacy file.

    Raises ValueError with a reason when the markers are unbalanced, so a corrupt
    legacy file is refused rather than half-migrated.
    """
    lines = text.splitlines(keepends=True)
    has_entries = any(_ENTRIES_RE.match(ln.strip()) for ln in lines)
    if not has_entries:
        raise ValueError("no REPO_WORKLOG:ENTRIES markers found")

    # Collect marker positions per date.
    marks: "dict[str, dict[str, int]]" = {}
    order: "list[str]" = []
    for idx, raw in enumerate(lines):
        m = _LEGACY_MARKER_RE.match(raw.strip())
        if not m:
            continue
        date, region, edge = m.group(1), m.group(2), m.group(3)
        key = f"{region}_{edge}"
        slot = marks.setdefault(date, {})
        if key in slot:
            raise ValueError(f"duplicate {region}:{edge} marker for {date}")
        slot[key] = idx
        if date not in order:
            order.append(date)

    result: "dict[str, dict[str, str]]" = {}
    for date in order:
        slot = marks[date]
        for need in ("GENERATED_START", "GENERATED_END", "MANUAL_START", "MANUAL_END"):
            if need not in slot:
                raise ValueError(f"missing {need} marker for {date}")
        gs, ge = slot["GENERATED_START"], slot["GENERATED_END"]
        ms, me = slot["MANUAL_START"], slot["MANUAL_END"]
        if not (gs < ge and ms < me):
            raise ValueError(f"markers out of order for {date}")
        result[date] = {
            "generated": "".join(lines[gs + 1:ge]),
            "manual": "".join(lines[ms + 1:me]),
        }
    return result


def _read_utf8(path: str, what: str) -> str:
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MigrateError("NON_UTF8", f"{what} is not valid UTF-8: {exc}", target=path)


def resolve_source(from_dir: "str | None", from_file: "str | None") -> "tuple[str, str]":
    """Decide what we are migrating from. Returns ``(kind, path)``."""
    if from_dir and from_file:
        raise MigrateError("AMBIGUOUS_SOURCE",
                           "Pass only one of --from-dir / --from-file; they are "
                           "different legacy shapes.")
    if from_dir:
        return "dir", from_dir
    if from_file:
        return "file", from_file
    # Auto-detect: the flat directory is the newer legacy shape, so prefer it.
    if wm.detect_layout(DEFAULT_LEGACY_DIR) == wm.LAYOUT_LEGACY:
        return "dir", DEFAULT_LEGACY_DIR
    if os.path.exists(DEFAULT_LEGACY):
        return "file", DEFAULT_LEGACY
    raise MigrateError("LEGACY_NOT_FOUND",
                       f"No legacy worklog found: neither {DEFAULT_LEGACY_DIR}/ (flat "
                       f"directory) nor {DEFAULT_LEGACY} (single file). Pass "
                       "--from-dir or --from-file.")


def _plan_from_file(legacy_path: str, worklog_dir: str,
                    tz: "str | None") -> "tuple[list, list, dict]":
    text = _read_utf8(legacy_path, "Legacy worklog")
    try:
        parsed = parse_legacy(text)
    except ValueError as exc:
        raise MigrateError("LEGACY_CORRUPT",
                           f"Legacy worklog markers are corrupt; refusing to migrate: {exc}",
                           target=legacy_path)
    if not parsed:
        raise MigrateError("LEGACY_EMPTY", "Legacy worklog has no date blocks to migrate.",
                           target=legacy_path)

    planned: "list[dict]" = []
    to_write: "list[tuple[str, str]]" = []
    summaries: "dict[str, str]" = {}
    for date in sorted(parsed, reverse=True):
        gen, manual = parsed[date]["generated"], parsed[date]["manual"]
        if wm.contains_marker_line(gen):
            raise MigrateError("LEGACY_CONTAINS_MARKER",
                               f"Legacy GENERATED content for {date} contains a marker "
                               "line; refusing to migrate rather than produce a corrupt "
                               "day file.", date=date)
        summaries[date] = wm.summarise_generated(gen)
        path = wm.day_path(worklog_dir, date, wm.LAYOUT_CURRENT)
        if os.path.exists(path):
            planned.append({"date": date, "path": path, "action": "skip-exists"})
            continue
        planned.append({"date": date, "path": path, "action": "create"})
        to_write.append((path, wm.build_day_file(date, gen, manual, timezone=tz)))
    return planned, to_write, summaries


def _plan_from_dir(src_dir: str, worklog_dir: str) -> "tuple[list, list, dict]":
    """Plan a flat-directory migration: move day files and re-tag their markers.

    Day content is copied verbatim apart from the marker prefix, so the original
    header metadata (branch, HEAD, timezone) and the prose survive untouched.
    ``timezone`` is deliberately ignored here: each day file already records
    the timezone it was written under, and rewriting it would falsify history.
    """
    if os.path.abspath(src_dir) == os.path.abspath(worklog_dir):
        raise MigrateError("SOURCE_IS_TARGET",
                           f"--from-dir and --dir are the same directory ({src_dir}); "
                           "nothing to migrate.")
    layout = wm.detect_layout(src_dir)
    if layout != wm.LAYOUT_LEGACY:
        raise MigrateError("SOURCE_NOT_LEGACY",
                           f"{src_dir} does not hold a flat legacy worklog (no <date>.md "
                           f"files at its root). Detected layout: {layout}.", target=src_dir)

    planned: "list[dict]" = []
    to_write: "list[tuple[str, str]]" = []
    summaries: "dict[str, str]" = {}
    for date in sorted(wm.list_day_dates(src_dir, layout), reverse=True):
        src = wm.day_path(src_dir, date, layout)
        text = _read_utf8(src, f"Day file {date}.md")
        retagged, _ = wm.retag_markers(text)
        try:
            day = wm.parse_day(retagged, date)
        except wm.WorklogFormatError as exc:
            raise MigrateError("DAY_FILE_CORRUPT",
                               f"Day file {date}.md has corrupt/missing markers; refusing "
                               "to migrate rather than guess a repair.",
                               target=src, issues=exc.issues)
        summaries[date] = wm.summarise_generated(day.generated)
        dst = wm.day_path(worklog_dir, date, wm.LAYOUT_CURRENT)
        if os.path.exists(dst):
            planned.append({"date": date, "path": dst, "action": "skip-exists"})
            continue
        planned.append({"date": date, "path": dst, "action": "create", "source": src})
        to_write.append((dst, retagged))
    if not to_write and not planned:
        raise MigrateError("LEGACY_EMPTY", f"{src_dir} has no day files to migrate.",
                           target=src_dir)
    return planned, to_write, summaries


def _source_index_manual(kind: str, src: str, worklog_dir: str) -> "str | None":
    """The MANUAL region to carry into the new index.

    The target's own index wins if it exists; otherwise a flat source's index
    donates its MANUAL so hand-written navigation notes survive the move.
    """
    target_index = wm.index_path(worklog_dir)
    for path, why in ((target_index, "An existing index.md"),
                      (wm.index_path(src) if kind == "dir" else None, "The source index.md")):
        if not path or not os.path.exists(path):
            continue
        try:
            return wm.parse_index(_read_utf8(path, "index.md")).manual
        except wm.WorklogFormatError as exc:
            raise MigrateError("INDEX_CORRUPT_MARKERS",
                               f"{why} has corrupt markers; refusing to migrate rather "
                               f"than discard its MANUAL region: {exc}", target=path)
    return None


def run(from_dir: "str | None" = None, from_file: "str | None" = None,
        dir: "str | None" = None, timezone: "str | None" = None,
        apply: bool = False) -> dict:
    """Plan (and optionally write) the migration. Raises MigrateError."""
    kind, source = resolve_source(from_dir, from_file)
    worklog_dir = dir or DEFAULT_DIR
    if not os.path.exists(source):
        raise MigrateError("LEGACY_NOT_FOUND", f"Legacy worklog not found: {source}",
                           target=source)

    if kind == "dir":
        planned, to_write, summaries = _plan_from_dir(source, worklog_dir)
    else:
        planned, to_write, summaries = _plan_from_file(source, worklog_dir, timezone)

    # Preview the rebuilt index over all migrated dates (existing + to-create).
    index_path = wm.index_path(worklog_dir)
    existing_manual = _source_index_manual(kind, source, worklog_dir)
    rows = [(d, summaries[d]) for d in sorted(summaries, reverse=True)]
    index_content = wm.render_index(rows, existing_manual, wm.LAYOUT_CURRENT)

    common = {
        "source": source,
        "source_kind": kind,
        "legacy_path": source,   # retained for callers written against the old key
        "worklog_dir": worklog_dir,
        "index_path": index_path,
        "planned_changes": planned,
        "dates": [d for d, _ in rows],
        "index_preview_sha256": _sha256(index_content),
    }

    if not apply:
        return {"ok": True, "mode": "dry-run", **common,
                "index_preview": index_content,
                "config_preview": wm.render_config(timezone),
                "note": ("No files have been modified. The source is never deleted; "
                         "existing day files are never overwritten.")}

    # Write the new day files (and index) atomically; on any failure remove the
    # files we created so a partial migration is never left behind.
    created: "list[str]" = []
    try:
        for path, content in to_write:
            writer.atomic_write(
                path, content,
                lambda t, d=os.path.basename(path)[:-3]: wm.parse_day(t, d),
                prefix=".rw-mig-")
            created.append(path)
        writer.atomic_write(index_path, index_content, wm.parse_index,
                            prefix=".rw-mig-")
        created.extend(wm.ensure_data_dir(worklog_dir, timezone))
    except Exception as exc:
        for path in created:
            try:
                os.unlink(path)
            except OSError:
                pass
        raise MigrateError("MIGRATION_FAILED",
                           f"Migration failed and created files were rolled back: {exc}",
                           worklog_dir=worklog_dir)

    return {"ok": True, "mode": "apply", **common,
            "created_dates": [os.path.basename(p)[:-3] for p, _ in to_write],
            "note": (f"Migration written to {worklog_dir}/. The source ({source}) was NOT "
                     "deleted — review the result, then remove it yourself if you are "
                     "satisfied. No git add / commit / push was performed.")}
