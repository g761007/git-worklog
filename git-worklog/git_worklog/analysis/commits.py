"""What Git knows about the commits a worklog cites (``git-worklog view``).

Read-only, and narrow on purpose: it answers for the hashes it is handed and
for nothing else, so a page built from it shows the commits the worklog talks
about, never the repository's history.

**The repository has to be the one the worklog lives in.** Git looks upward for
a repository, so a worklog kept under an unrelated one -- a dotfiles ``~``, a
monorepo -- would have its hashes resolved there, and ``view --serve`` would
then hand out that repository's diffs. :func:`owns` therefore asks for the
directory to be the top level itself.

**Nothing here is an error.** A worklog outside any repository, a shallow clone
and a hash rebased away are all ordinary; each one just means fewer commits to
show, and the page falls back to what it did before it knew about Git.
"""

from __future__ import annotations

import os
import subprocess

from git_worklog.analysis.history import UNIT_SEP, GitError, _git
from git_worklog.analysis.reconcile import _batch_resolve

RECORD_SEP = "\x1e"
MAX_FILES = 200       # per commit; a vendoring commit lists thousands
MAX_BODY = 20000      # characters of commit message body

# How a commit is diffed -- for the file list here and for the patch the server
# sends, so the two describe the same files. A merge is shown against its first
# parent (what it brought in), the root commit against nothing; a signature is
# never checked, which would start a program named by the repository's config.
DIFF_FLAGS = ["--root", "--diff-merges=first-parent", "--no-show-signature",
              "--submodule=short", "-M"]

_FORMAT = "--format=%x1e" + "%x1f".join(["%H", "%h", "%an", "%aI", "%s", "%b"]) + "%x1f"


def owns(repo: str) -> bool:
    """Whether ``repo`` is itself the top level of a Git work tree."""
    try:
        top = _git(repo, ["rev-parse", "--show-toplevel"]).strip()
    except (GitError, OSError):
        return False
    return os.path.realpath(top) == os.path.realpath(repo)


def _parse(blob: str) -> "dict[str, dict]":
    """``git log -z --numstat`` output, one record per ``RECORD_SEP``.

    A record is its fields, each closed by ``UNIT_SEP``, then NUL; then, when
    the commit changed files, a newline and NUL-terminated entries:
    ``add\\tdel\\tpath``, or for a rename ``add\\tdel\\t`` followed by the old
    and the new path as two entries of their own. Binary files count ``-``.
    """
    commits: "dict[str, dict]" = {}
    for record in blob.split(RECORD_SEP)[1:]:
        head, _, rest = record.partition(UNIT_SEP + "\0")
        fields = head.split(UNIT_SEP)
        if len(fields) < 6:
            continue
        full, short, author, date, subject = fields[:5]
        body = UNIT_SEP.join(fields[5:]).strip()
        entries = rest.lstrip("\n").split("\0")
        files, adds, dels, i = [], 0, 0, 0
        while i < len(entries):
            parts = entries[i].split("\t", 2)
            i += 1
            if len(parts) < 3:
                continue
            add, dele, path = parts
            old = None
            if not path and i + 1 < len(entries):
                old, path = entries[i], entries[i + 1]
                i += 2
            binary = add == "-"
            files.append({"path": path, "old_path": old,
                          "additions": None if binary else int(add),
                          "deletions": None if binary else int(dele)})
            if not binary:
                adds += int(add)
                dels += int(dele)
        commits[full] = {
            "sha": full, "short": short, "author": author, "date": date,
            "subject": subject, "body": body[:MAX_BODY],
            "body_truncated": len(body) > MAX_BODY,
            "files": files[:MAX_FILES], "file_count": len(files),
            "additions": adds, "deletions": dels,
        }
    return commits


def collect(repo: str, tokens) -> "tuple[dict[str, dict], dict[str, str]]":
    """(commits by full hash, full hash by token) for the tokens naming a commit.

    A token that names nothing, names a tree or a blob, or is ambiguous is in
    neither: the caller treats it as text.
    """
    tokens = sorted({t.lower() for t in tokens})
    if not tokens or not owns(repo):
        return {}, {}
    try:
        resolved = _batch_resolve(repo, tokens)
        shas = sorted(set(resolved.values()))
        if not shas:
            return {}, {}
        proc = subprocess.run(
            ["git", "-C", repo, "log", "--no-walk", "--stdin", *DIFF_FLAGS,
             "--numstat", "-z", _FORMAT],
            input="\n".join(shas).encode("ascii"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            return {}, {}
    except (GitError, OSError):
        return {}, {}
    commits = _parse(proc.stdout.decode("utf-8", "replace"))
    return commits, {t: s for t, s in resolved.items() if s in commits}
