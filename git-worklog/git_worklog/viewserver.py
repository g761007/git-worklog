"""The worklog page, served, so it can show diffs (``git-worklog view --serve``).

The static page carries each cited commit's message and file list, but not its
diff: that is source code by the megabyte. This server is the other half. It
serves the same page and, when a commit is opened in it, that commit's patch,
read from Git at that moment.

What it will not do is the design:

- **Listen anywhere but 127.0.0.1**, and answer anyone who does not name it by
  that address: a page on another site that points its own hostname here (DNS
  rebinding) sends that hostname as ``Host`` and gets 403.
- **Answer without the token.** The static page is written owner-only; a port on
  loopback is open to every user of the machine. The URL therefore carries a
  secret made for this run, and anything else is 404.
- **Show a commit the worklog does not cite.** The diff route answers for the
  commits on the page it last built, not for whatever a caller can name.
- **Run anything the repository configures.** No external diff, no textconv, no
  signature check (:data:`git_worklog.analysis.commits.DIFF_FLAGS`).
- **Write.** Not to the repository, not to the worklog, not to a log on stdout,
  which belongs to the command's JSON.
"""

from __future__ import annotations

import json
import re
import secrets
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from git_worklog import viewer
from git_worklog.analysis.commits import DIFF_FLAGS

MAX_DIFF = 2 * 1024 * 1024    # bytes of patch sent for one commit

_FILE_START_RE = re.compile(r"(?m)^(?=diff --git )")


def diff(repo: str, sha: str) -> dict:
    """One commit's patch, cut into one piece per file.

    The cap is applied while reading: a commit that vendors a dependency would
    otherwise be held whole in memory, once per request.
    """
    proc = subprocess.Popen(
        ["git", "-C", repo, "show", "--no-color", "--no-ext-diff", "--no-textconv",
         *DIFF_FLAGS, "--format=", "--patch", sha],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        data = proc.stdout.read(MAX_DIFF + 1)
    finally:
        proc.kill()
        proc.stdout.close()
        proc.wait()
    text = data[:MAX_DIFF].decode("utf-8", "replace")
    files = [part for part in _FILE_START_RE.split(text) if part.startswith("diff --git ")]
    return {"files": files, "truncated": len(data) > MAX_DIFF}


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, worklog_dir: str, repo: str):
        super().__init__(("127.0.0.1", 0), _Handler)   # port 0: the system picks
        self.worklog_dir = worklog_dir
        self.repo = repo
        self.token = secrets.token_urlsafe(16)
        self.commits: "frozenset[str]" = frozenset()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}/{self.token}/"

    def page(self) -> "tuple[str, dict]":
        """Build the page now, and remember which commits it shows."""
        page, info = viewer.build(self.worklog_dir, repo=self.repo, diff_base="diff/")
        self.commits = info["commits"]
        return page, info


class _Handler(BaseHTTPRequestHandler):
    # Only GET exists; the base class answers every other method with 501.

    def log_message(self, format, *args):   # noqa: A002 (the base class's name)
        pass

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(body)

    def _refuse(self, status: int) -> None:
        self._send(status, "text/plain; charset=utf-8", b"")

    def do_GET(self):   # noqa: N802 (the base class's name)
        server = self.server
        if self.headers.get("Host") != f"127.0.0.1:{server.server_port}":
            return self._refuse(403)
        prefix = f"/{server.token}/"
        path = self.path.split("?", 1)[0]
        if not secrets.compare_digest(path[:len(prefix)].encode("utf-8", "replace"),
                                      prefix.encode("ascii")):
            return self._refuse(404)
        rest = path[len(prefix):]
        try:
            if not rest:
                page, _info = server.page()   # rebuilt: reloading the tab refreshes it
                return self._send(200, "text/html; charset=utf-8", page.encode("utf-8"))
            if rest.startswith("diff/") and rest[5:] in server.commits:
                body = json.dumps(diff(server.repo, rest[5:])).encode("ascii")
                return self._send(200, "application/json; charset=utf-8", body)
        except OSError:
            return self._refuse(500)
        return self._refuse(404)
