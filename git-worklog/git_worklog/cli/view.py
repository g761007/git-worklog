"""``git-worklog view`` — the worklog as one page in a browser.

Read-only, like ``validate``: nothing in the repository or its worklog is
written. The page is derived from the day files every time
(:mod:`git_worklog.viewer`) and lands outside the repository, in
``~/.git-worklog/view/``, under a name fixed per worklog -- so re-running the
command and reloading the tab is how the page refreshes. The file is
owner-only because it embeds the whole worklog, quotes from the source
included.

Opening a browser is best effort and can never cost the JSON contract. Python's
``webbrowser`` starts some browsers as child processes that inherit stdout, so
for the length of the call stdout points at stderr. And on Linux with no
display, ``webbrowser`` falls back to terminal browsers (lynx, w3m) whenever
``TERM`` is set -- which an agent's shell sets -- and runs them in the
foreground, where they would sit waiting for keys nobody will press. There the
page is written and the browser is not started; the answer says so and exits 0,
because the page is what the command promised.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import webbrowser
from pathlib import Path

from git_worklog import markers as wm
from git_worklog import paths, viewer, writer

NOTE = ("The page embeds the whole worklog, quotes from the source included, and "
        "is written owner-only. Share it only where the source may be read.")


def _default_output(worklog_dir: str) -> str:
    """One stable file per worklog: named for its project, keyed by its path.

    The project is the directory holding the worklog, not the cwd: the skill runs
    every command from its own directory, which would name every page after it.
    """
    real = os.path.realpath(worklog_dir)
    project = re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.basename(os.path.dirname(real)))
    project = project.strip("-.") or "worklog"
    digest = hashlib.sha256(real.encode("utf-8")).hexdigest()[:8]
    return os.path.join(paths.view_dir(), f"{project}-{digest}.html")


def _inside(path: str, directory: str) -> bool:
    path, directory = os.path.realpath(path), os.path.realpath(directory)
    try:
        return os.path.commonpath([path, directory]) == directory
    except ValueError:      # different drives on Windows
        return False


def _open_quietly(url: str) -> "str | None":
    """Open ``url`` in a browser. None when it opened, else why it did not."""
    if sys.platform.startswith("linux") and not any(
            os.environ.get(v) for v in ("DISPLAY", "WAYLAND_DISPLAY", "BROWSER")):
        return "there is no display to open a browser on"
    sys.stdout.flush()
    saved = os.dup(1)
    try:
        os.dup2(2, 1)
        opened = webbrowser.open(url)
    finally:
        os.dup2(saved, 1)
        os.close(saved)
    return None if opened else "no browser could be started"


def run(args) -> "tuple[dict, int]":
    repo = args.repo or "."
    worklog_dir = args.dir or os.path.join(repo, wm.WORKLOG_DIRNAME)
    target = os.path.abspath(worklog_dir)

    if not os.path.isdir(worklog_dir):
        return {"ok": False, "worklog_dir": target, "errors": [{
            "code": "NOT_FOUND", "message": f"{target} does not exist.",
            "target": target}]}, 2
    # The page may go anywhere but into the worklog it shows:
    # `--output .git-worklog/index.md` would replace the index with HTML.
    if args.output and _inside(args.output, worklog_dir):
        out = os.path.abspath(args.output)
        return {"ok": False, "worklog_dir": target, "errors": [{
            "code": "OUTPUT_INSIDE_WORKLOG",
            "message": f"{out} is inside the worklog directory {target}; "
                       "view never writes there.",
            "target": out}]}, 2

    try:
        page, info = viewer.build(worklog_dir)
        if args.output:
            out = os.path.abspath(args.output)
        else:
            # Created first, owner-only: atomic_write would create it too, but
            # with default permissions, and this directory holds private text.
            paths.ensure_dir(paths.view_dir())
            out = _default_output(worklog_dir)
        writer.atomic_write(out, page, lambda _text: None, prefix=".rw-view-")
    except OSError as exc:
        return {"ok": False, "worklog_dir": target, "errors": [{
            "code": "IO_ERROR", "message": str(exc)}]}, 2

    url = Path(out).as_uri()
    warnings = list(info["warnings"])
    opened = False
    if not args.no_open:
        reason = _open_quietly(url)
        opened = reason is None
        if reason:
            warnings.append({"code": "BROWSER_NOT_OPENED",
                             "message": f"The page was written, but {reason}. Open {out}.",
                             "target": out})
    return {
        "ok": True,
        "worklog_dir": target,
        "layout": info["layout"],
        "output": out,
        "url": url,
        "opened": opened,
        "day_count": info["day_count"],
        "range": info["range"],
        "warnings": warnings,
        "note": NOTE,
    }, 0


def render_text(p: dict) -> str:
    if not p.get("ok"):
        return "".join(f"error: {e['message']}\n" for e in p.get("errors", []))
    head = f"git-worklog view — {p['day_count']} day file(s)"
    if p["range"]:
        head += f", {p['range']['from']} → {p['range']['to']}"
    lines = [head, f"  {p['output']}",
             "  opened in your browser" if p["opened"] else f"  open: {p['url']}"]
    lines.extend(f"  warning: {w['message']}" for w in p["warnings"])
    return "\n".join(lines) + "\n"
