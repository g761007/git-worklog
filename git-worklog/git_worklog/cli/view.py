"""``git-worklog view`` — the worklog as one page in a browser.

Read-only, like ``validate``: nothing in the repository or its worklog is
written. The page is derived from the day files every time
(:mod:`git_worklog.viewer`) and lands outside the repository, in
``~/.git-worklog/view/``, under a name fixed per worklog -- so re-running the
command and reloading the tab is how the page refreshes. The file is
owner-only because it embeds the whole worklog, quotes from the source
included.

Git is asked, read-only, about the commits the worklog cites, so a hash on the
page opens its commit. The repository asked is the directory the worklog sits
in -- the same one the page is named for -- not the cwd, which with ``--dir``
may be another project altogether.

``--serve`` keeps the command running as a local server
(:mod:`git_worklog.viewserver`) instead of writing a file, which is what lets
the page show diffs. The JSON still comes first and whole: ``run`` binds the
port and opens the browser, the answer is printed, and only then does
``after_emit`` start answering requests, until it is interrupted.

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
from git_worklog import paths, viewer, viewserver, writer

NOTE = ("The page embeds the whole worklog, quotes from the source included, and "
        "is written owner-only. Share it only where the source may be read.")
SERVE_NOTE = ("Serving on 127.0.0.1 until interrupted (Ctrl+C). The page shows "
              "diffs, which are source code. The URL holds this run's access "
              "token: it stays in the browser's history and in this output, "
              "and stops working when the server does.")


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

    # Where the worklog lives, which is where its commits are.
    repo_dir = os.path.dirname(os.path.realpath(worklog_dir))
    if getattr(args, "serve", False):
        return _serve(args, worklog_dir, target, repo_dir)

    try:
        page, info = viewer.build(worklog_dir, repo=repo_dir)
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
    opened = _open(args, url, f"The page was written, but {{}}. Open {out}.", out, warnings)
    return {
        "ok": True,
        "worklog_dir": target,
        "layout": info["layout"],
        "output": out,
        "url": url,
        "opened": opened,
        "day_count": info["day_count"],
        "commit_count": info["commit_count"],
        "range": info["range"],
        "warnings": warnings,
        "note": NOTE,
    }, 0


def _open(args, url: str, message: str, target: str, warnings: list) -> bool:
    """Open ``url`` unless told not to; a browser that will not start is a warning."""
    if args.no_open:
        return False
    reason = _open_quietly(url)
    if reason:
        warnings.append({"code": "BROWSER_NOT_OPENED",
                         "message": message.format(reason), "target": target})
    return reason is None


def _serve(args, worklog_dir: str, target: str, repo_dir: str) -> "tuple[dict, int]":
    """Bind, build once and answer; :func:`after_emit` does the serving."""
    server = None
    try:
        server = viewserver.Server(worklog_dir, repo_dir)
        _page, info = server.page()
    except OSError as exc:
        if server is not None:
            server.server_close()
        return {"ok": False, "worklog_dir": target, "errors": [{
            "code": "IO_ERROR", "message": str(exc)}]}, 2
    args.server = server
    url = server.url
    warnings = list(info["warnings"])
    # The socket is already listening, so a browser that is quicker than
    # after_emit just waits in the backlog.
    opened = _open(args, url, f"The page is being served, but {{}}. Open {url}.", url,
                   warnings)
    return {
        "ok": True,
        "worklog_dir": target,
        "layout": info["layout"],
        "output": None,
        "url": url,
        "serving": True,
        "opened": opened,
        "day_count": info["day_count"],
        "commit_count": info["commit_count"],
        "range": info["range"],
        "warnings": warnings,
        "note": SERVE_NOTE,
    }, 0


def after_emit(args, payload: dict, code: int) -> int:
    """Serve until interrupted, once the answer is out."""
    server = getattr(args, "server", None)
    if server is None:
        return code
    # A pipe is block-buffered: unflushed, the reader would wait for a URL that
    # is only printed when the server stops.
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def render_text(p: dict) -> str:
    if not p.get("ok"):
        return "".join(f"error: {e['message']}\n" for e in p.get("errors", []))
    head = f"git-worklog view — {p['day_count']} day file(s)"
    if p["range"]:
        head += f", {p['range']['from']} → {p['range']['to']}"
    lines = [head, f"  {p['output'] or 'serving ' + p['url']}",
             "  opened in your browser" if p["opened"] else f"  open: {p['url']}"]
    if p.get("serving"):
        lines.append("  press Ctrl+C to stop")
    lines.extend(f"  warning: {w['message']}" for w in p["warnings"])
    return "\n".join(lines) + "\n"
