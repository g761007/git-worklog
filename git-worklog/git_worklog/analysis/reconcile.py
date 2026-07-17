"""Reconcile a ref scope's authoritative commit set against the day files.

Why this is code rather than an instruction
-------------------------------------------
:mod:`git_worklog.analysis.refs` establishes that a version is bounded by a
commit set while the worklog is indexed by calendar date, so a report on a tag
must read the day files its commits landed on *without* describing everything
else those days contain. Until now that reconciliation was a sentence in
``references/report-mode.md`` addressed to the model:

    Describe only work whose commits appear in ``commits[]``. When a day file
    describes work whose hashes are absent from the range, leave it out.

The day files carry each commit's short hash, so that instruction was always
checkable -- the v0.4.0 design said as much, and deferred the check until there
was evidence the model needed it. Issue #19 supplied the evidence: day subagents
fabricate citations and report themselves as verified. A rule the model is asked
to keep, with nothing checking it, is not a contract. This module turns it into
data the caller can act on.

Language independence
---------------------
Hashes are found by scanning the GENERATED region for Git object names, **not**
by parsing the ``相關 commits`` bullet label. The label is zh-TW; a day file
written in any other language (which §6.2 explicitly allows) carries a
translated one. Keying off the label would make this silently find zero hashes
in an English day file and report a clean reconciliation -- a check that passes
because it looked at nothing is worse than no check, and that exact bug already
shipped once, in the index summary (fixed in PR 4 by adding a marker).

Only the GENERATED region is scanned. MANUAL is a human's own note, never
analysis material, and the file's meta block carries a ``HEAD`` hash that is not
a citation at all -- both sit outside GENERATED, so both are excluded by
construction rather than by a filter that could rot.
"""

from __future__ import annotations

import os
import re
import subprocess

from git_worklog import markers as wm
from git_worklog.analysis.history import UNIT_SEP, GitError

# A Git object name as it appears in prose: 7-40 hex characters on a word
# boundary. Case-insensitive deliberately. Git writes lowercase and every hash
# in a day file arrives from this tool's own output, so an uppercase hash means
# the model reformatted one -- and missing a real hash would under-report
# out-of-range work, which is the failure this whole module exists to prevent.
# The cost is that a rare all-hex English word ("defaced", "acceded") becomes a
# candidate; those land in `unresolved`, which is why that list is a hint to
# look rather than a verdict.
_HASH_RE = re.compile(r"\b[0-9a-fA-F]{7,40}\b")


def cited_hashes(generated: str) -> "set[str]":
    """Every Git object name cited in a day file's GENERATED region, lowercased."""
    return {m.group(0).lower() for m in _HASH_RE.finditer(generated)}


def _read_day(worklog_dir: str, date: str) -> "str | None":
    """A day file's GENERATED region, or None when there is nothing to read.

    A malformed day file yields None rather than raising: reconciliation is a
    read-only question about coverage, and `validate` is the command that has an
    opinion about structure. The day still shows up as citing nothing, so its
    commits are reported unbacked -- the honest answer.
    """
    path = wm.day_path(worklog_dir, date)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    day, _issues = wm.scan_day(text, date)
    return day.generated if day else None


def _batch_resolve(repo: str, tokens: "list[str]") -> "dict[str, str]":
    """Map each token to the full SHA of the commit it names, where it names one.

    One ``cat-file --batch-check`` rather than a ``rev-parse`` per token: a
    90-day report can cite hundreds of hashes, and this keeps that one process
    instead of hundreds. Tokens that name nothing, name a non-commit (a tree, a
    blob), or are ambiguous are simply absent from the result.
    """
    if not tokens:
        return {}
    proc = subprocess.run(
        ["git", "-C", repo, "cat-file", "--batch-check"],
        input="\n".join(tokens).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise GitError(proc.stderr.decode("utf-8", "replace").strip())

    resolved: "dict[str, str]" = {}
    # --batch-check answers in input order: "<sha> commit <size>" for a hit, and
    # "<token> missing" / "<token> ambiguous" otherwise.
    for token, line in zip(tokens, proc.stdout.decode("utf-8", "replace").splitlines()):
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "commit":
            resolved[token] = fields[0]
    return resolved


def _subjects(repo: str, shas: "list[str]") -> "dict[str, dict]":
    """Subject and short hash for each SHA, in one call."""
    if not shas:
        return {}
    fmt = UNIT_SEP.join(["%H", "%h", "%an", "%s"])
    proc = subprocess.run(
        ["git", "-C", repo, "log", "--no-walk", f"--pretty=format:{fmt}", *shas],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise GitError(proc.stderr.decode("utf-8", "replace").strip())

    out: "dict[str, dict]" = {}
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        fields = line.split(UNIT_SEP)
        if len(fields) < 4:
            continue
        full, short, author, subject = fields[:4]
        out[full] = {"full_hash": full, "short_hash": short,
                     "author_name": author, "subject": subject}
    return out


def reconcile(repo: str, worklog_dir: str, commits: "list[dict]",
              dates: "list[str]") -> dict:
    """Check what the day files for ``dates`` cite against ``commits``.

    ``commits`` is the authority (:func:`git_worklog.analysis.refs.resolve`'s
    ``commits[]``); ``dates`` are the days worth reading. Every citation lands in
    exactly one bucket, so nothing goes missing silently:

    * ``backed``       -- in the range, and some day file cites it. Material exists.
    * ``unbacked``     -- in the range, cited by no day file. Either the day is a
      gap, or its file simply does not mention this commit. A report must not
      claim to describe these.
    * ``out_of_range`` -- cited by a day file, a real commit, **not** in the
      range. The enforcement: these are what a report on this tag must leave out.
    * ``unresolved``   -- cited, but does not name **one** commit here. Usually
      prose that happens to be hex; possibly a fabricated or rebased-away hash;
      possibly a prefix short enough to name several commits, which identifies
      none of them.
    """
    in_range = {c["full_hash"]: c for c in commits}

    citations: "dict[str, list[str]]" = {}   # token -> dates citing it
    for date in dates:
        generated = _read_day(worklog_dir, date)
        if generated is None:
            continue
        for token in cited_hashes(generated):
            citations.setdefault(token, []).append(date)

    # A token is in range when it prefixes exactly one of the range's commits.
    # Matching by prefix rather than against short_hash means a day file citing a
    # full 40-char hash reconciles the same as one citing the 7-char form.
    #
    # A token prefixing *several* of them backs none: it does not say which one
    # was described, and crediting all of them would let a report claim analysis
    # exists for a commit nothing analysed -- the one direction this module must
    # never fail in. It joins the leftovers, where Git will call it ambiguous for
    # the same reason and it will surface as unresolved.
    cited_in_range: "set[str]" = set()
    leftover: "list[str]" = []
    for token in citations:
        hit = [full for full in in_range if full.startswith(token)]
        if len(hit) == 1:
            cited_in_range.add(hit[0])
        else:
            leftover.append(token)

    resolved = _batch_resolve(repo, sorted(leftover))
    subjects = _subjects(repo, sorted(set(resolved.values())))

    out_of_range = []
    for token in sorted(leftover):
        full = resolved.get(token)
        if not full:
            continue
        info = dict(subjects.get(full, {"full_hash": full, "short_hash": token,
                                        "author_name": "", "subject": ""}))
        info["cited_on"] = sorted(citations[token])
        out_of_range.append(info)

    unresolved = [{"hash": t, "cited_on": sorted(citations[t])}
                  for t in sorted(leftover) if t not in resolved]

    backed = [c for c in commits if c["full_hash"] in cited_in_range]
    unbacked = [c for c in commits if c["full_hash"] not in cited_in_range]

    return {
        "backed": backed,
        "unbacked": unbacked,
        "out_of_range": out_of_range,
        "unresolved": unresolved,
        "backed_count": len(backed),
        "unbacked_count": len(unbacked),
        "clean": not out_of_range and not unbacked,
    }


__all__ = ["cited_hashes", "reconcile"]
