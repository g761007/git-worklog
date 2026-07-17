#!/usr/bin/env python3
"""One-time migration of a legacy worklog into the ``.git-worklog/`` layout.

The engine is :mod:`git_worklog.migrate`; this is the command-line shell around
it. The logic moved into the package because only ``git_worklog*`` is packaged
-- an installed CLI has no ``scripts/`` directory to reach for -- and the two
front ends must not drift apart.

Two legacy shapes are migrated, because the worklog has moved twice: the
pre-v0.2 single file (``--from-file``) and the v0.2-v0.5 flat directory
(``--from-dir``). With neither flag the source is auto-detected, directory
first. See the module docstring for what each shape does to a day file.

It is **never** invoked by normal runs — only explicitly, via ``/git-worklog
migrate`` or by running this script. Dry-run is the default. It never deletes the
source, and never overwrites a day file that already exists.

Usage:
    python3 scripts/migrate_legacy_worklog.py [--from-file docs/PROJECT_WORKLOG.md]
        [--from-dir PROJECT_WORKLOG] [--dir .git-worklog] [--timezone Asia/Taipei]
        [--apply]

Output is a single JSON object on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys

import _bootstrap  # noqa: F401 — must precede any git_worklog import

from git_worklog import migrate

DEFAULT_LEGACY = migrate.DEFAULT_LEGACY
DEFAULT_LEGACY_DIR = migrate.DEFAULT_LEGACY_DIR
DEFAULT_DIR = migrate.DEFAULT_DIR


def _emit(payload: dict) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _fail(code: str, message: str, **extra) -> None:
    _emit({"ok": False, "errors": [{"code": code, "message": message, **extra}]})
    sys.exit(2)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"Migrate a legacy worklog into {DEFAULT_DIR}/.")
    p.add_argument("--from-dir", dest="from_dir",
                   help=f"Flat legacy worklog directory, v0.2-v0.5 (default: {DEFAULT_LEGACY_DIR}).")
    p.add_argument("--from-file", dest="from_file",
                   help=f"Single-file legacy worklog, pre-v0.2 (default: {DEFAULT_LEGACY}).")
    p.add_argument("--legacy", dest="from_file",
                   help="Deprecated alias for --from-file.")
    p.add_argument("--dir", help=f"Target worklog directory (default: {DEFAULT_DIR}).")
    p.add_argument("--timezone",
                   help="Timezone recorded in config.json, and in each day file's header "
                        "when migrating from a single file. Ignored for --from-dir, whose "
                        "day files already record their own.")
    p.add_argument("--apply", action="store_true",
                   help="Write the migration. Without this flag the run is a dry-run.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _emit(migrate.run(from_dir=args.from_dir, from_file=args.from_file,
                          dir=args.dir, timezone=args.timezone, apply=args.apply))
        return 0
    except migrate.MigrateError as exc:
        _fail(exc.code, exc.message, **exc.extra)
    except (json.JSONDecodeError, OSError) as exc:
        _fail("IO_ERROR", f"{exc}")
    except Exception as exc:  # never let a traceback replace the single JSON object
        _fail("UNEXPECTED_ERROR", f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
