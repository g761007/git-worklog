"""``git-worklog report`` — everything a report needs decided before it is written.

Report mode's one entry point. It answers, in a single call, the four questions
that must be settled before a word of a report is written:

* **What is in scope?** A date range, or a tag's commit set (:mod:`.refs`).
* **Is it backed by analysis?** Which days have a day file (:mod:`.coverage`).
* **What must be left out?** For a tag, which citations in those day files belong
  to another release (:mod:`.reconcile`).
* **In which language?** Resolved here, independently of the day files being read.

It writes nothing. The prose is the agent LLM's job (§6.1): this command decides
*what may be said*, not what to say. There is deliberately no ``--out`` — the
report does not exist yet at this point, so there would be nothing to write.

Why one command rather than a module per report type
----------------------------------------------------
The roadmap (§11) sketched ``weekly.py`` / ``release.py`` / ``contributor.py``
and four more. They are not here, because the seven report types differ only in
their scope, an optional filter, and which question the user asked — and the
v0.4.0 design that shipped report mode said so explicitly: the types are prompt
examples in ``references/report-mode.md``, "非各自的程式分支". Seven modules each
forwarding to the same two scope resolvers would be an abstraction over a single
call site. §3.2 reserved the namespace for the day the types actually diverge;
they have not, so the namespace stays unbuilt.
"""

from __future__ import annotations

import os

from git_worklog import dates as gwdates
from git_worklog import language
from git_worklog import markers as wm
from git_worklog.analysis import AnalysisError
from git_worklog.analysis import coverage as cov
from git_worklog.analysis import history as ah
from git_worklog.analysis import manifest as am
from git_worklog.analysis import reconcile as rec
from git_worklog.analysis import refs as refs_engine

def _material(worklog_dir: str, dates: "list[str]") -> "list[dict]":
    """The day files worth reading, in date order."""
    out = []
    for date in dates:
        path = wm.day_path(worklog_dir, date)
        if os.path.isfile(path):
            out.append({"date": date, "path": path})
    return out


def run(args) -> "tuple[dict, int]":
    try:
        payload = _run(args)
        # Exit 1 for a gap, matching `coverage`: it ran fine and the answer to
        # "can I report on this?" is no. `out_of_range` deliberately does not
        # earn a 1 — a day file citing another release's work is the normal
        # case, not a failure. It is *why* the reconciliation exists, and the
        # report simply leaves those commits out. Exiting 1 on the ordinary case
        # would train the caller to ignore the code.
        return payload, (0 if payload["fully_covered"] else 1)
    except (AnalysisError, gwdates.DateError) as exc:
        return {"ok": False, "errors": [
            {"code": exc.code, "message": exc.message, **exc.extra}]}, 2
    except language.LanguageError as exc:
        return {"ok": False, "errors": [
            {"code": exc.code, "message": exc.message, **exc.extra}]}, 2
    except (ah.GitError, refs_engine.GitError) as exc:
        return {"ok": False, "errors": [
            {"code": "GIT_ERROR", "message": str(exc)}]}, 2


def _run(args) -> dict:
    is_ref = bool(args.tag or args.from_ref or args.to_ref)
    is_date = bool(args.shortcut or args.date or args.days is not None
                   or getattr(args, "from") or args.to)
    if is_ref and is_date:
        raise AnalysisError(
            "ARG_CONFLICT",
            "A report has one scope: a tag's commit set (--tag/--to-ref) or a "
            "date range. The two do not mean the same thing — a version is "
            "bounded by commits, the worklog is indexed by date. Pass one.")
    if not is_ref and not is_date:
        raise AnalysisError(
            "NO_SCOPE",
            "Provide a date scope (NNd, --date, --days, --from/--to) or a ref "
            "scope (--tag, or --to-ref with an optional --from-ref).")

    # Resolved before any Git work: an unusable language tag should say so
    # whether or not the tag exists. Report language is decided here and owes
    # nothing to the language the day files happen to be written in (§6.2.11) —
    # this command never reads their language, only their hashes and prose.
    lang = am.resolve_language(args.language, args.language_source, args.dir)

    scope: dict
    reconciliation = None
    if is_ref:
        r = refs_engine.resolve(
            repo=args.repo, tag=args.tag, from_ref=args.from_ref,
            to_ref=args.to_ref, list_tags_only=False,
            timezone=args.timezone or "UTC", date_field=args.date_field)
        scope = {
            "kind": "ref",
            "tag": r["tag"],
            "prev_tag": r["prev_tag"],
            "first_release": r["first_release"],
            "commit_range": r["commit_range"],
            "date_span": r["date_span"],
        }
        dates_arg = ",".join(r["dates"])
        # An empty range has no dates to check; coverage would reject "".
        coverage = (cov.check(repo=args.repo, dir=args.dir, dates=dates_arg,
                              timezone=args.timezone or "UTC",
                              date_field=args.date_field,
                              worklog_dir=args.worklog_dir)
                    if r["dates"] else None)
    else:
        scope = {"kind": "date"}
        coverage = cov.check(
            repo=args.repo, dir=args.dir, dates="", timezone=args.timezone,
            date_field=args.date_field, worklog_dir=args.worklog_dir,
            shortcut=args.shortcut, date=args.date, days=args.days,
            from_=getattr(args, "from"), to=args.to, today=args.today,
            max_days=args.max_days)
        r = None

    if coverage is None:
        # A tag containing no commits: real (an empty release), and not a gap.
        # There are no dates to ask `coverage` about — it rejects an empty
        # --dates — so the same answer is assembled here. detect_timezone rather
        # than a literal, so `timezone.source` carries the same vocabulary as
        # every other path: a caller must not have to special-case the shape of
        # an empty release.
        info = ah.repo_info(args.repo)
        _tz, tz_name, tz_source = gwdates.detect_timezone(args.timezone or "UTC")
        resolved_dir = (args.dir if os.path.isabs(args.dir)
                        else os.path.join(info["root"], args.dir))
        coverage = {
            "ok": True,
            "repository": {"root": info["root"], "has_commits": info["has_commits"]},
            "worklog_dir": resolved_dir, "dir_exists": os.path.isdir(resolved_dir),
            "timezone": {"resolved": tz_name, "source": tz_source},
            "date_field": args.date_field, "dates": [], "covered": [], "gaps": [],
            "no_commit_dates": [], "gap_commit_count": 0, "fully_covered": True,
        }

    dates = [row["date"] for row in coverage["dates"]]
    if is_ref:
        # The check the prose could not hold. Runs for a ref scope only: a date
        # scope has no authoritative commit set to reconcile against — its dates
        # *are* the authority, so a day file citing anything on those days is
        # in scope by definition.
        reconciliation = rec.reconcile(args.repo, coverage["worklog_dir"],
                                       r["commits"], r["dates"])

    payload = {
        "ok": True,
        "scope": scope,
        "language": lang.as_manifest(),
        "repository": coverage["repository"],
        "worklog_dir": coverage["worklog_dir"],
        "dir_exists": coverage["dir_exists"],
        "timezone": coverage["timezone"],
        "date_field": coverage["date_field"],
        "dates": coverage["dates"],
        "covered": coverage["covered"],
        "gaps": coverage["gaps"],
        "no_commit_dates": coverage["no_commit_dates"],
        "gap_commit_count": coverage["gap_commit_count"],
        "fully_covered": coverage["fully_covered"],
        "material": _material(coverage["worklog_dir"], dates),
        "warnings": list(lang.warnings),
    }
    if is_ref:
        payload["commit_count"] = r["commit_count"]
        payload["commits"] = r["commits"]
        payload["reconciliation"] = reconciliation
    return payload


def render_text(p: dict) -> str:
    if not p.get("ok"):
        return "".join(f"error: {e['message']}\n" for e in p.get("errors", []))

    s, tz = p["scope"], p["timezone"]
    head = (f"{s['commit_range']}" if s["kind"] == "ref"
            else f"{p['dates'][0]['date']} .. {p['dates'][-1]['date']}"
            if p["dates"] else "no dates")
    lines = [f"git-worklog report — {head}\n"]
    lines.append(f"  language: {p['language']['resolved']} "
                 f"(via {p['language']['source']})\n")
    lines.append(f"  ({tz['resolved']} via {tz['source']})\n")
    if s["kind"] == "ref" and s["first_release"]:
        lines.append("  first release: the range runs from the root commit\n")
    lines.append("\n")

    symbol = {"covered": "✓", "gap": "✗", "no-commits": "·"}
    for row in p["dates"]:
        note = (f"{row['commit_count']} commit(s)" if row["commit_count"]
                else "no commits, no file expected")
        lines.append(f"  {symbol[row['status']]} {row['date']}  "
                     f"{row['status']:11} {note}\n")

    if not p["fully_covered"]:
        lines.append(f"\n{len(p['gaps'])} gap(s) covering {p['gap_commit_count']} "
                     f"commit(s): {', '.join(p['gaps'])}\n")
        lines.append("Real work exists on those days that nothing has analysed.\n")

    rn = p.get("reconciliation")
    if rn is not None:
        lines.append(f"\n{p['commit_count']} commit(s) in range; "
                     f"{rn['backed_count']} backed by a day file.\n")
        for c in rn["unbacked"]:
            lines.append(f"  unbacked     {c['short_hash']}  {c['subject']}\n")
        if rn["unbacked"]:
            lines.append("  ^ in this release, but no day file describes them. "
                         "Do not claim to have analysed these.\n")
        for c in rn["out_of_range"]:
            lines.append(f"  out of range {c['short_hash']}  {c['subject']}\n"
                         f"               cited on {', '.join(c['cited_on'])}\n")
        if rn["out_of_range"]:
            lines.append("  ^ the day files describe these, but they belong to a "
                         "different release. Leave them out.\n")
        for u in rn["unresolved"]:
            lines.append(f"  unresolved   {u['hash']}  "
                         f"cited on {', '.join(u['cited_on'])}, names no commit here\n")
    return "".join(lines)
