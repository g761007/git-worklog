"""``git-worklog version`` — every version that matters, and what each governs.

Roadmap §12.1 asks for the CLI, engine, schema and skill-compatibility versions.
They are reported separately because they answer different questions and move on
different clocks: the product version tracks releases, while the layout and
schema versions track the shape of data already on someone's disk and bump only
when a migration is needed. Collapsing them would imply every release migrates
user data. See issue #12 and docs/naming-conventions.md.
"""

from __future__ import annotations

import platform

from git_worklog import __version__
from git_worklog.markers import LAYOUT_VERSION

# The skill body and this package ship together in one directory, so they cannot
# drift apart in a normal install. The number exists for the case where they can:
# a pip-installed CLI meeting a separately-copied skill. Bump it when the CLI
# changes in a way an older skill body cannot drive.
SKILL_COMPAT_VERSION = 1


def run(args) -> "tuple[dict, int]":
    return {
        "ok": True,
        "cli_version": __version__,
        # The engine is this same package today; PR 7 may split it out, at which
        # point this stops being a copy of cli_version.
        "engine_version": __version__,
        "layout_version": LAYOUT_VERSION,
        "schema_version": LAYOUT_VERSION,
        "skill_compat_version": SKILL_COMPAT_VERSION,
        "python_version": platform.python_version(),
    }, 0


def render_text(p: dict) -> str:
    return (
        f"git-worklog {p['cli_version']}\n"
        f"  engine        {p['engine_version']}\n"
        f"  layout        {p['layout_version']}    (.git-worklog/VERSION)\n"
        f"  config schema {p['schema_version']}    (config.json schema_version)\n"
        f"  skill compat  {p['skill_compat_version']}\n"
        f"  python        {p['python_version']}\n"
    )
