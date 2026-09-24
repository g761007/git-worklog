"""The worklog as one self-contained HTML page (``git-worklog view``).

Read-only by construction: this module opens day files, the index and config
for reading and returns a string. Writing that string somewhere and opening a
browser on it is the CLI's job (:mod:`git_worklog.cli.view`), so everything
here can be tested without side effects.

**Structure, never wording.** Headings are written in each run's language
(worklog-format.md §3), so nothing here compares heading text. A day is split
on ``##`` (sections) and ``###`` (work items) outside code fences; its lead is
the first paragraph of its first section, which is where the template puts the
summary with or without SUMMARY markers; and its commits are counted with
:func:`git_worklog.analysis.reconcile.cited_hashes`, the scan ``report`` uses,
so the two commands cannot disagree about what a day cites.

**Cited, not made.** The page reads day files and nothing else, so every number
on it describes the worklog, not the repository. "Commits cited" is what the
prose mentions -- on 2026-07-17 in this repository, 41 of the 52 commits made --
and an empty calendar cell means "no day file", which a gap and a day without
commits look exactly alike as. Telling those apart needs git: see ``coverage``.

**The day header is not shown.** Its Branch/HEAD lines record the run that wrote
the file (worklog-format.md §2); two days analysed together carry the same HEAD,
so printing it beside a date would say something false about that date.

**One script, pinned.** Content goes through :mod:`git_worklog.mdhtml`, which
never lets input become markup. The page's Content-Security-Policy then allows
exactly one script, by hash, and no network access at all -- a backstop, so an
escape that was ever missed still could not run or send anything anywhere.
Navigation is CSS (``:target``), so the page reads fully without the script;
the script adds search and keyboard shortcuts only.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import html
import os
import re
from dataclasses import dataclass, field

from git_worklog import config as gwconfig
from git_worklog import markers as wm
from git_worklog import mdhtml
from git_worklog.analysis.reconcile import cited_hashes

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_WEEKDAYS_LONG = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                  "Saturday", "Sunday")
_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_H2_RE = re.compile(r"^##\s+(.+?)(?:\s+#+)?\s*$")
_H3_RE = re.compile(r"^###\s+(.+?)(?:\s+#+)?\s*$")


@dataclass
class Section:
    title: str
    body: str = ""                                   # Markdown before its first ###
    items: "list[tuple[str, str]]" = field(default_factory=list)   # (title, Markdown)


@dataclass
class Day:
    date: str
    path: str
    sections: "list[Section]"
    manual: str
    raw: "str | None"        # the whole file, when its regions could not be found
    issues: "list[dict]"
    hashes: "frozenset[str]"  # cited commits, first 7 characters
    lead: str

    @property
    def items(self) -> int:
        return sum(len(s.items) for s in self.sections)


def split_sections(generated: str) -> "list[Section]":
    """Cut a GENERATED region into ``##`` sections holding ``###`` work items.

    Fence-aware: a ``##`` line inside a code block is code. Text before the
    first ``##`` -- the template has none -- becomes an untitled section rather
    than being dropped.
    """
    sections: "list[Section]" = []
    lines: "list[str]" = []
    item: "str | None" = None
    fence: "str | None" = None

    def flush():
        text = "\n".join(lines).strip("\n")
        lines.clear()
        if item is not None:
            sections[-1].items.append((item, text))
        elif sections:
            sections[-1].body = text
        elif text.strip():
            sections.append(Section("", text))

    for line in generated.split("\n"):
        opened = _FENCE_RE.match(line)
        if fence:
            if (opened and opened.group(1)[0] == fence[0]
                    and len(opened.group(1)) >= len(fence)
                    and line.strip() == opened.group(1)):
                fence = None
            lines.append(line)
            continue
        if opened:
            fence = opened.group(1)
            lines.append(line)
            continue
        h2 = _H2_RE.match(line)
        h3 = None if h2 else _H3_RE.match(line)
        if not (h2 or h3):
            lines.append(line)
            continue
        flush()
        if h2:
            sections.append(Section(h2.group(1)))
            item = None
        else:
            if not sections:
                sections.append(Section(""))
            item = h3.group(1)
    flush()
    return sections


def lead_of(sections: "list[Section]", generated: str) -> str:
    """The first paragraph of the first section: the day's summary lead."""
    para: "list[str]" = []
    for line in (sections[0].body.split("\n") if sections else []):
        if not line.strip() or mdhtml.COMMENT_RE.match(line):
            if para:
                break
            continue
        para.append(line.strip())
    if para:
        return " ".join(para)
    # No section at all: fall back to the index's own rule (which escapes pipes
    # for its table -- undone here, this is not a table).
    return wm.summarise_generated(generated).replace("\\|", "|")


def load_day(worklog_dir: str, date: str, layout: str) -> Day:
    path = wm.day_path(worklog_dir, date, layout)
    issues: "list[dict]" = []
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        issues.append({"code": "UNREADABLE", "message": f"{path}: {exc}",
                       "date": date, "target": path})
        return Day(date, path, [], "", "", issues, frozenset(), "")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        # One bad file must not take the whole page down; validate reports the
        # same code, and the replacement characters show where the damage is.
        text = data.decode("utf-8", errors="replace")
        issues.append({"code": "NON_UTF8", "message": f"{path} is not valid UTF-8: {exc}",
                       "date": date, "target": path})
    parsed, found = wm.scan_day(text, date)
    issues.extend(dict(i, date=date, target=path) for i in found)
    if parsed is None:
        return Day(date, path, [], "", text, issues, frozenset(), "")
    sections = split_sections(parsed.generated)
    hashes = frozenset(h[:7] for h in cited_hashes(parsed.generated))
    return Day(date, path, sections, parsed.manual, None, issues, hashes,
               lead_of(sections, parsed.generated))


def _index(worklog_dir: str) -> "tuple[str, str | None, list[dict]]":
    """(project notes, content language, warnings) from index.md.

    A missing or broken index is nothing to show, not a failure: the page is
    built from the day files, and the index is only asked for its human notes
    and the language its summaries are in.
    """
    path = wm.index_path(worklog_dir)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return "", None, []
    except (OSError, UnicodeDecodeError) as exc:
        return "", None, [{"code": "INDEX_UNREADABLE", "message": f"{path}: {exc}",
                           "target": path}]
    # Unstamped means "written before the stamp existed", which means zh-TW.
    lang = wm.index_language_of(text) or wm.DEFAULT_INDEX_LANGUAGE
    doc, _issues = wm.scan_index(text)
    if doc is None:
        return "", lang, [{"code": "INDEX_UNREADABLE",
                           "message": f"{path} could not be parsed; its notes are not shown.",
                           "target": path}]
    notes = doc.manual.strip()
    placeholders = {wm.index_chrome(code)["manual_default"].strip()
                    for code in wm.INDEX_CHROME_LANGUAGES}
    return ("" if notes in placeholders else notes), lang, []


def build(worklog_dir: str) -> "tuple[str, dict]":
    """The page for ``worklog_dir``, and what the CLI reports about it."""
    layout = wm.detect_layout(worklog_dir)
    dates = wm.list_day_dates(worklog_dir, layout)
    days = [load_day(worklog_dir, d, layout) for d in dates]
    notes, lang, warnings = _index(worklog_dir)
    if lang is None:
        lang = gwconfig.language(gwconfig.load(worklog_dir))
    for day in days:
        warnings.extend(day.issues)
    real = os.path.realpath(worklog_dir)
    project = os.path.basename(os.path.dirname(real)) or "worklog"
    page = _page(project, os.path.dirname(real), days, notes, lang)
    return page, {
        "layout": layout,
        "day_count": len(days),
        "range": {"from": dates[0], "to": dates[-1]} if dates else None,
        "warnings": warnings,
    }


# --- rendering ---------------------------------------------------------------


def _e(text) -> str:
    return html.escape(str(text), quote=True)


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _weekday(date: str, long: bool = False) -> str:
    # A fixed table, not strftime("%a"), which follows the process locale.
    table = _WEEKDAYS_LONG if long else _WEEKDAYS
    return table[dt.date.fromisoformat(date).weekday()]


def _lang(lang: "str | None") -> str:
    return f' lang="{_e(lang)}"' if lang else ""


def _level(items: int) -> int:
    return 1 if items <= 2 else 2 if items <= 5 else 3 if items <= 9 else 4


def script_hash() -> str:
    """The CSP source that allows the page's one script, and nothing else."""
    digest = hashlib.sha256(_JS.encode("utf-8")).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


def _page(project: str, root: str, days: "list[Day]", notes: str,
          lang: "str | None") -> str:
    known = frozenset(d.date for d in days)
    csp = (f"default-src 'none'; script-src '{script_hash()}'; "
           "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'")
    articles = []
    for i in range(len(days) - 1, -1, -1):          # newest first, like the index
        older = days[i - 1].date if i > 0 else None
        newer = days[i + 1].date if i + 1 < len(days) else None
        articles.append(_day(days[i], older, newer, root, lang, known))
    body = "".join([
        '<header class="top">',
        '<a class="brand" href="#overview">Git Worklog</a>',
        '<input id="q" type="search" placeholder="Search the worklog" '
        'aria-label="Search the worklog" autocomplete="off" spellcheck="false">',
        '<kbd class="hint">/</kbd>',
        "</header>",
        '<div class="layout">',
        _sidebar(days),
        "<main>",
        '<section id="results" class="results" hidden aria-live="polite"></section>',
        _overview(project, days, notes, lang, known),
        "".join(articles),
        "</main>",
        "</div>",
        f'<footer class="foot">Rendered from {_n(len(days), "day file")}. '
        "Re-run <code>git-worklog view</code> to refresh.</footer>",
    ])
    return ("<!DOCTYPE html>\n"
            '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta http-equiv="Content-Security-Policy" content="{csp}">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<meta name="referrer" content="no-referrer">\n'
            f"<title>{_e(project)} · Git Worklog</title>\n"
            f"<style>{_CSS}</style>\n"
            "</head>\n<body>\n"
            f"{body}\n"
            f"<script>{_JS}</script>\n"
            "</body>\n</html>\n")


def _sidebar(days: "list[Day]") -> str:
    parts = ['<nav class="side" aria-label="Days">'
             '<a class="nav-overview" href="#overview">Overview</a>']
    month = None
    for d in reversed(days):
        if d.date[:7] != month:
            month = d.date[:7]
            parts.append(f'<p class="month">{month}</p>')
        flag = ' <span class="flag" title="Format issue">!</span>' if d.issues else ""
        parts.append(f'<a href="#d-{d.date}"><span>{d.date[5:]} {_weekday(d.date)}'
                     f'{flag}</span><span class="n" title="Work items">{d.items}</span></a>')
    parts.append("</nav>")
    return "".join(parts)


def _tile(label: str, value) -> str:
    return f'<div class="tile"><span>{label}</span><b>{value}</b></div>'


def _overview(project: str, days: "list[Day]", notes: str, lang: "str | None",
              known) -> str:
    parts = [f'<section id="overview" class="view overview"><h1>{_e(project)}</h1>']
    if not days:
        parts.append('<p class="empty">No worklog days yet. Generate some with '
                     "<code>/git-worklog</code>.</p></section>")
        return "".join(parts)
    first, last = days[0].date, days[-1].date
    span = (dt.date.fromisoformat(last) - dt.date.fromisoformat(first)).days + 1
    cited = frozenset().union(*(d.hashes for d in days))
    parts.append(f'<p class="sub">{_n(len(days), "day")} logged · {first} → {last}</p>')
    parts.append('<div class="tiles">'
                 + _tile("Days logged", len(days))
                 + _tile("Work items", sum(d.items for d in days))
                 + _tile("Commits cited", len(cited))
                 + _tile("Span", _n(span, "day"))
                 + "</div>")
    parts.append("<h2>Activity</h2>" + _calendar(days))
    if notes:
        parts.append('<section class="notes"><h2>Project notes</h2>'
                     f'<div class="md"{_lang(lang)}>{mdhtml.render(notes, dates=known)}</div>'
                     "</section>")
    parts.append("<h2>Timeline</h2>" + _timeline(days, lang))
    parts.append("</section>")
    return "".join(parts)


def _calendar(days: "list[Day]") -> str:
    by_date = {d.date: d for d in days}
    first = dt.date.fromisoformat(days[0].date)
    last = dt.date.fromisoformat(days[-1].date)
    week = first - dt.timedelta(days=first.weekday())
    end = last + dt.timedelta(days=6 - last.weekday())
    cols = ['<div class="wk days"><span></span><span>Mon</span><span></span>'
            "<span>Wed</span><span></span><span>Fri</span><span></span><span></span></div>"]
    while week <= end:
        label, cells = "", []
        for k in range(7):
            day = week + dt.timedelta(days=k)
            if day.day == 1 or (k == 0 and len(cols) == 1):   # first week, or a new month
                label = _MONTHS[day.month - 1][:3]
            iso = day.isoformat()
            if day < first or day > last:
                cells.append('<span class="c pad"></span>')
            elif iso in by_date:
                d = by_date[iso]
                tip = (f"{iso} · {_n(d.items, 'work item')} · "
                       f"{_n(len(d.hashes), 'commit')} cited")
                cells.append(f'<a class="c l{_level(d.items)}" href="#d-{iso}" '
                             f'title="{tip}" aria-label="{tip}"></a>')
            else:
                cells.append(f'<span class="c" title="{iso} · no day file"></span>')
        cols.append(f'<div class="wk"><span class="mo">{label}</span>'
                    + "".join(cells) + "</div>")
        week += dt.timedelta(days=7)
    legend = ('<p class="legend"><span>Fewer</span><span class="c l1"></span>'
              '<span class="c l2"></span><span class="c l3"></span><span class="c l4"></span>'
              "<span>more work items</span><span>·</span><span class=\"c\"></span>"
              "<span>no day file (not checked against git, so a day nobody logged "
              "looks the same as a day without commits)</span></p>")
    return '<div class="cal-wrap"><div class="cal">' + "".join(cols) + "</div></div>" + legend


def _timeline(days: "list[Day]", lang: "str | None") -> str:
    parts, month = [], None
    for d in reversed(days):
        if d.date[:7] != month:
            month = d.date[:7]
            parts.append(f'<h3 class="month">{_MONTHS[int(month[5:]) - 1]} {month[:4]}</h3>')
        lead = (mdhtml.inline(d.lead, links=False) if d.lead
                else '<span class="muted">No summary</span>')
        badges = ""
        if d.manual.strip():
            badges += '<span class="badge">Notes</span>'
        if d.issues:
            badges += '<span class="badge warn">Format issue</span>'
        tags = "".join(f'<span class="tag">{mdhtml.inline(s.title, links=False)}</span>'
                       for s in d.sections[1:] if s.title)
        parts.append(
            f'<a class="card" href="#d-{d.date}">'
            f'<span class="card-date">{d.date} <span class="wd">{_weekday(d.date)}</span></span>'
            f'<span class="lead"{_lang(lang)}>{lead}</span>'
            '<span class="facts">'
            f'<span class="chip">{_n(d.items, "work item")}</span>'
            f'<span class="chip">{_n(len(d.hashes), "commit")} cited</span>'
            f"{badges}</span>"
            + (f'<span class="tags"{_lang(lang)}>{tags}</span>' if tags else "")
            + "</a>")
    return "".join(parts)


def _toc(d: Day) -> str:
    if not any(s.items for s in d.sections):
        return ""
    parts = ['<nav class="toc" aria-label="On this day"><p class="toc-h">On this day</p><ol>']
    n = 0
    for k, s in enumerate(d.sections, 1):
        sub = []
        for title, _body in s.items:
            n += 1
            sub.append(f'<li><a href="#d-{d.date}-i{n}">{mdhtml.inline(title, links=False)}</a></li>')
        name = mdhtml.inline(s.title, links=False) if s.title else "Untitled"
        parts.append(f'<li><a href="#d-{d.date}-s{k}">{name}</a>'
                     + ("<ol>" + "".join(sub) + "</ol>" if sub else "") + "</li>")
    parts.append("</ol></nav>")
    return "".join(parts)


def _sections(d: Day, known) -> str:
    out, n = [], 0
    for k, s in enumerate(d.sections, 1):
        head = f"<h2>{mdhtml.inline(s.title, dates=known)}</h2>" if s.title else ""
        intro = ""
        if s.body.strip():
            intro = f'<div class="intro" data-unit>{mdhtml.render(s.body, dates=known)}</div>'
        items = []
        for title, body in s.items:
            n += 1
            items.append(
                f'<details class="item" id="d-{d.date}-i{n}" open data-unit>'
                f'<summary><span class="no">{n:02d}</span>'
                f'<span class="t">{mdhtml.inline(title, dates=known)}</span></summary>'
                f'<div class="body">{mdhtml.render(body, dates=known)}</div></details>')
        cls = "block summary" if k == 1 else "block"
        out.append(f'<section class="{cls}" id="d-{d.date}-s{k}">{head}{intro}'
                   + "".join(items) + "</section>")
    return "".join(out)


def _day(d: Day, older: "str | None", newer: "str | None", root: str,
         lang: "str | None", known) -> str:
    rel = os.path.relpath(os.path.realpath(d.path), root).replace(os.sep, "/")
    pager = ('<nav class="pager">'
             + (f'<a href="#d-{older}" rel="prev">← {older}</a>' if older else "<span></span>")
             + (f'<a href="#d-{newer}" rel="next">{newer} →</a>' if newer else "<span></span>")
             + "</nav>")
    banner = ""
    if d.issues:
        codes = ", ".join(sorted({i["code"] for i in d.issues}))
        banner = (f'<p class="banner">This day file has format issues ({_e(codes)}). '
                  "Run <code>git-worklog validate</code> for details.</p>")
    if d.raw is not None:
        content = f'<pre class="raw">{html.escape(d.raw, quote=False)}</pre>'
    else:
        content = _toc(d) + '<div class="sections">' + _sections(d, known)
        if d.manual.strip():
            content += (f'<section class="block manual" id="d-{d.date}-notes"><h2>Notes</h2>'
                        f'<div class="intro" data-unit>{mdhtml.render(d.manual, dates=known)}'
                        "</div></section>")
        content += "</div>"
    return (f'<article id="d-{d.date}" class="view day" data-date="{d.date}" '
            f'data-prev="{"d-" + older if older else ""}" '
            f'data-next="{"d-" + newer if newer else ""}">'
            '<header class="day-head">'
            f'<h1>{d.date} <span class="wd">{_weekday(d.date, long=True)}</span></h1>'
            f"{pager}"
            '<p class="facts">'
            f'<span class="chip">{_n(d.items, "work item")}</span>'
            f'<span class="chip">{_n(len(d.hashes), "commit")} cited</span></p>'
            "</header>"
            f'{banner}<div class="md day-body"{_lang(lang)}>{content}</div>'
            f'<footer class="day-foot"><code>{_e(rel)}</code></footer>'
            "</article>")


# --- page assets ---------------------------------------------------------------
# Kept as strings rather than files: package data is exactly the kind of thing
# that silently stops shipping, and a module cannot be left out of the wheel or
# skill.zip without the import failing loudly.

_CSS = r"""
:root {
  color-scheme: light dark;
  --bg: #fbfaf8; --panel: #ffffff; --line: #e5e1da; --text: #1f1e1c;
  --muted: #66625b; --faint: #99948b; --accent: #0f6e56; --accent-bg: #e3f4ed;
  --warn: #854f0b; --warn-bg: #faeeda; --code: #f3f1ec; --mark: #fad68a;
  --empty: #ece9e3; --l1: #bfe6d5; --l2: #77cda9; --l3: #2e9e77; --l4: #0f6e56;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC",
    "Noto Sans TC", "Microsoft JhengHei", "Hiragino Sans", sans-serif;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161615; --panel: #1e1e1c; --line: #34322e; --text: #ebe9e4;
    --muted: #aaa59c; --faint: #7c776f; --accent: #5dcaa5; --accent-bg: #11352b;
    --warn: #f3c77a; --warn-bg: #3a2a0c; --code: #292826; --mark: #6b5314;
    --empty: #282725; --l1: #1a4a3b; --l2: #1f7a5c; --l3: #35b389; --l4: #86e2c0;
  }
}
* { box-sizing: border-box; }
html { background: var(--bg); }
body { margin: 0; color: var(--text); font: 15px/1.7 var(--sans); }
a { color: var(--accent); }
[id] { scroll-margin-top: 72px; }
.top { position: sticky; top: 0; z-index: 2; display: flex; align-items: center;
  gap: 12px; padding: 10px 20px; background: var(--panel);
  border-bottom: 1px solid var(--line); }
.brand { color: var(--text); font-weight: 600; text-decoration: none; }
#q { margin-left: auto; width: min(360px, 46vw); padding: 6px 10px; font: inherit;
  font-size: 14px; color: var(--text); background: var(--bg);
  border: 1px solid var(--line); border-radius: 8px; }
#q:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
.hint { font: 12px var(--mono); color: var(--faint); border: 1px solid var(--line);
  border-radius: 4px; padding: 0 6px; }
html:not(.js) #q, html:not(.js) .hint { display: none; }
.layout { display: grid; grid-template-columns: 200px minmax(0, 1fr);
  max-width: 1240px; margin: 0 auto; }
.side { position: sticky; top: 53px; align-self: start; max-height: calc(100vh - 53px);
  overflow: auto; padding: 16px 10px 24px; font-size: 13px; }
.side a { display: flex; justify-content: space-between; gap: 8px; padding: 3px 8px;
  border-radius: 6px; color: var(--muted); text-decoration: none; }
.side a:hover { background: var(--code); }
.side a[aria-current] { background: var(--accent-bg); color: var(--accent); }
.side .nav-overview { color: var(--text); font-weight: 600; }
.side .month { margin: 14px 8px 4px; font-size: 11px; color: var(--faint); }
.side .n { color: var(--faint); font-variant-numeric: tabular-nums; }
.flag { color: var(--warn); font-weight: 700; }
main { min-width: 0; padding: 24px 28px 64px; }
h1 { font-size: 24px; line-height: 1.3; margin: 0 0 4px; }
h2 { font-size: 18px; line-height: 1.4; margin: 28px 0 10px; }
h3 { font-size: 15px; margin: 22px 0 8px; }
.sub, .muted, .wd { color: var(--muted); }
.wd { font-weight: 400; }
.empty { color: var(--muted); }
.day { display: none; }
.day:target, .day:has(:target) { display: block; }
main:has(.day:target) #overview, main:has(.day :target) #overview { display: none; }
.searching .view { display: none !important; }
.results[hidden] { display: none; }
.tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px;
  margin: 16px 0 4px; }
.tile { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  padding: 10px 14px; }
.tile span { display: block; font-size: 12px; color: var(--muted); }
.tile b { font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }
.cal-wrap { overflow-x: auto; padding: 2px 0 6px; }
.cal { display: flex; gap: 3px; }
.wk { display: grid; grid-template-rows: 16px repeat(7, 12px); gap: 3px; }
.days span { font-size: 10px; line-height: 12px; color: var(--faint); padding-right: 4px; }
.mo { font-size: 10px; line-height: 14px; color: var(--faint); width: 12px;
  overflow: visible; white-space: nowrap; }
.c { display: block; width: 12px; height: 12px; border-radius: 3px; background: var(--empty); }
.c.pad { background: transparent; }
.c.l1 { background: var(--l1); } .c.l2 { background: var(--l2); }
.c.l3 { background: var(--l3); } .c.l4 { background: var(--l4); }
a.c:hover, a.c:focus { outline: 2px solid var(--text); outline-offset: -1px; }
.legend { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px;
  margin: 6px 0 0; font-size: 12px; color: var(--muted); }
.legend .c { display: inline-block; }
.month { color: var(--muted); font-weight: 500; }
.card { display: block; margin: 0 0 10px; padding: 12px 16px; color: inherit;
  text-decoration: none; background: var(--panel); border: 1px solid var(--line);
  border-radius: 10px; }
.card:hover, .card:focus { border-color: var(--accent); }
.card-date { display: block; font-weight: 600; }
.lead { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
  overflow: hidden; margin: 2px 0 6px; }
.facts, .tags { display: flex; flex-wrap: wrap; gap: 4px 6px; margin: 4px 0 0; }
.chip, .tag, .badge { font-size: 12px; padding: 0 8px; border-radius: 999px;
  border: 1px solid var(--line); color: var(--muted); white-space: nowrap; }
.tag { background: var(--code); border-color: transparent; }
.badge { color: var(--accent); border-color: var(--accent); }
.badge.warn, .banner { color: var(--warn); border-color: var(--warn); }
.banner { background: var(--warn-bg); border-radius: 8px; padding: 8px 12px; }
.day-head { margin: 0 0 18px; }
.pager { display: flex; justify-content: space-between; font-size: 13px; margin: 4px 0; }
.pager a { text-decoration: none; }
.day-body { display: block; }
.toc { font-size: 13px; background: var(--panel); border: 1px solid var(--line);
  border-radius: 10px; padding: 10px 14px; margin: 0 0 18px; }
.toc-h { margin: 0 0 4px; font-weight: 600; color: var(--muted); }
.toc ol { margin: 0; padding-left: 18px; }
.toc a { color: var(--text); text-decoration: none; }
.toc a:hover { color: var(--accent); }
.block.summary { border-left: 3px solid var(--accent); border-radius: 0;
  padding: 2px 0 2px 16px; margin: 0 0 24px; }
.block.summary h2 { font-size: 13px; color: var(--muted); margin: 0 0 4px; }
.block.summary .intro > p:first-child { font-size: 17px; line-height: 1.65; }
.item { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  margin: 0 0 12px; }
.item > summary { display: flex; gap: 10px; align-items: baseline; padding: 12px 16px;
  cursor: pointer; font-weight: 600; list-style: none; }
.item > summary::-webkit-details-marker { display: none; }
.item > summary::after { content: "▾"; margin-left: auto; color: var(--faint); }
.item:not([open]) > summary::after { content: "▸"; }
.item .no { color: var(--faint); font: 12px var(--mono); }
.item .body { padding: 0 16px 10px; border-top: 1px solid var(--line); }
.item .body > ul { list-style: none; padding: 0; margin: 0; }
.item .body > ul > li { padding: 8px 0; border-top: 1px solid var(--line); }
.item .body > ul > li:first-child { border-top: 0; }
li.kv > strong:first-child { display: block; font-size: 12px; font-weight: 600;
  color: var(--muted); }
.md ul ul, .md ol ol, .md ul ol, .md ol ul { margin: 2px 0; padding-left: 20px; }
.md p { margin: 8px 0; }
.md code { font: 0.86em/1.4 var(--mono); background: var(--code);
  border: 1px solid var(--line); border-radius: 5px; padding: 0.05em 0.35em;
  overflow-wrap: anywhere; }
.md pre, pre.raw { overflow: auto; background: var(--code); padding: 10px 12px;
  border-radius: 8px; font: 13px/1.5 var(--mono); }
.md pre code { border: 0; padding: 0; background: none; font-size: inherit; }
.manual { border: 1px dashed var(--faint); border-radius: 10px; padding: 4px 16px 8px; }
.manual h2 { font-size: 13px; color: var(--muted); margin: 10px 0 0; }
.day-foot { margin: 24px 0 0; font-size: 12px; color: var(--faint); }
.day-foot code, .foot code { font-family: var(--mono); }
.results h1 { font-size: 18px; }
.results h2 { font-size: 13px; color: var(--muted); margin: 18px 0 6px; }
.hit { display: block; padding: 8px 12px; margin: 0 0 6px; color: inherit;
  text-decoration: none; background: var(--panel); border: 1px solid var(--line);
  border-radius: 8px; }
.hit:hover, .hit:focus { border-color: var(--accent); }
.hit-title { display: block; font-weight: 600; }
.snip { display: block; font-size: 13px; color: var(--muted); }
mark { background: var(--mark); color: inherit; border-radius: 2px; }
.foot { max-width: 1240px; margin: 0 auto; padding: 16px 28px 32px; font-size: 12px;
  color: var(--faint); }
@media (min-width: 1200px) {
  .day-body { display: grid; grid-template-columns: minmax(0, 1fr) 230px; column-gap: 28px; }
  .day-body > .toc { grid-column: 2; grid-row: 1; position: sticky; top: 72px;
    align-self: start; max-height: calc(100vh - 96px); overflow: auto; margin: 0; }
  .day-body > .sections { grid-column: 1; grid-row: 1; }
}
@media (max-width: 760px) {
  .layout { display: block; }
  .side { position: static; max-height: none; display: flex; flex-wrap: wrap;
    gap: 2px 4px; padding: 10px 12px; border-bottom: 1px solid var(--line); }
  .side .month { flex-basis: 100%; margin: 6px 4px 0; }
  main { padding: 16px; }
  .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  #q { width: auto; flex: 1; }
}
@media print {
  .top, .side, .toc, .pager, .results, .foot { display: none !important; }
  .layout { display: block; }
  main { padding: 0; }
  .card, .item { break-inside: avoid; }
}
"""

_JS = r"""
(function () {
  "use strict";
  document.documentElement.className += " js";
  var q = document.getElementById("q");
  var results = document.getElementById("results");
  var units = null;
  var timer = null;

  function collect() {
    units = [];
    var found = document.querySelectorAll("article.day [data-unit]");
    for (var i = 0; i < found.length; i++) {
      var el = found[i];
      var day = el.closest("article.day");
      var item = el.closest("details.item");
      var block = el.closest("section");
      var title = item ? item.querySelector("summary .t") : block && block.querySelector("h2");
      var unit = {
        date: day.getAttribute("data-date"),
        target: item ? item.id : (block && block.id) || day.id,
        title: title ? title.textContent.trim() : "",
        text: el.textContent.replace(/\s+/g, " ").trim()
      };
      // Lowercased once, here: a year of worklog is megabytes of text, and a
      // case-insensitive regex over all of it on every keystroke is felt.
      unit.hay = (unit.title + " " + unit.text).toLowerCase();
      units.push(unit);
    }
  }

  function escapeRe(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function snippet(text, any) {
    any.lastIndex = 0;
    var first = any.exec(text);
    var at = first ? first.index : 0;
    var start = Math.max(0, at - 60);
    var end = Math.min(text.length, at + 160);
    var piece = (start > 0 ? "…" : "") + text.slice(start, end) + (end < text.length ? "…" : "");
    var span = document.createElement("span");
    span.className = "snip";
    var last = 0;
    var m;
    any.lastIndex = 0;
    while ((m = any.exec(piece)) !== null) {
      span.appendChild(document.createTextNode(piece.slice(last, m.index)));
      var mark = document.createElement("mark");
      mark.textContent = m[0];
      span.appendChild(mark);
      last = m.index + m[0].length;
    }
    span.appendChild(document.createTextNode(piece.slice(last)));
    return span;
  }

  function line(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) { el.className = cls; }
    el.textContent = text;
    return el;
  }

  function search(query) {
    var terms = query.split(/\s+/).filter(function (t) { return t; });
    while (results.firstChild) { results.removeChild(results.firstChild); }
    if (!terms.length) {
      document.body.classList.remove("searching");
      results.hidden = true;
      return;
    }
    if (!units) { collect(); }
    var needles = terms.map(function (t) { return t.toLowerCase(); });
    var any = new RegExp(terms.map(escapeRe).join("|"), "gi");
    var hits = units.filter(function (u) {
      return needles.every(function (t) { return u.hay.indexOf(t) !== -1; });
    });
    document.body.classList.add("searching");
    results.hidden = false;
    results.appendChild(line("h1", "", hits.length + (hits.length === 1 ? " match" : " matches")
      + " for “" + query + "”"));
    var date = null;
    hits.slice(0, 200).forEach(function (u) {
      if (u.date !== date) {
        date = u.date;
        results.appendChild(line("h2", "", date));
      }
      var a = document.createElement("a");
      a.className = "hit";
      a.href = "#" + u.target;
      a.appendChild(line("span", "hit-title", u.title || date));
      a.appendChild(snippet(u.text, any));
      results.appendChild(a);
    });
    if (!hits.length) {
      results.appendChild(line("p", "muted", "No matches. Every word has to appear, in any order."));
    } else if (hits.length > 200) {
      results.appendChild(line("p", "muted", "Showing the first 200. Add a word to narrow it down."));
    }
  }

  function currentDay() {
    var el = location.hash.length > 1 && document.getElementById(location.hash.slice(1));
    return el ? el.closest("article.day") : null;
  }

  function markNav() {
    var day = currentDay();
    var want = "#" + (day ? day.id : "overview");
    var links = document.querySelectorAll(".side a");
    for (var i = 0; i < links.length; i++) {
      if (links[i].getAttribute("href") === want) {
        links[i].setAttribute("aria-current", "page");
      } else {
        links[i].removeAttribute("aria-current");
      }
    }
  }

  function clearSearch() {
    if (q.value) { q.value = ""; search(""); }
  }

  q.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () { search(q.value.trim()); }, 120);
  });
  q.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { clearSearch(); q.blur(); }
  });
  function reveal(scroll) {
    var el = location.hash.length > 1 && document.getElementById(location.hash.slice(1));
    if (el && el.tagName === "DETAILS") { el.open = true; }
    // Coming from search, the browser scrolled while the target was still
    // hidden under the results, so it did not move at all. Scroll again now.
    if (el && scroll) { el.scrollIntoView(); }
  }

  results.addEventListener("click", function (e) {
    var a = e.target.closest("a.hit");
    if (a && a.hash === location.hash) { clearSearch(); reveal(true); }
  });
  document.addEventListener("keydown", function (e) {
    var tag = e.target && e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") { return; }
    if (e.metaKey || e.ctrlKey || e.altKey) { return; }
    if (e.key === "/") { e.preventDefault(); q.focus(); return; }
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") { return; }
    var day = currentDay();
    var to = day && day.getAttribute(e.key === "ArrowLeft" ? "data-prev" : "data-next");
    if (to) { e.preventDefault(); location.hash = to; }
  });
  window.addEventListener("hashchange", function () {
    var searching = !!q.value;
    clearSearch();
    reveal(searching);
    markNav();
  });
  markNav();
})();
"""
