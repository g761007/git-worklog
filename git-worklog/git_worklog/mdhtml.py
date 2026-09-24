"""Worklog Markdown to HTML, safe by construction (``git-worklog view``).

A day file is Markdown an LLM wrote after reading the repository, plus whatever
a human put in its MANUAL region. Either can hold text shaped like HTML: a
worklog that describes an XSS fix quotes ``<script>``, and a repository can
carry text written to steer the model that summarised it. A general Markdown
library passes inline HTML through by design. This renderer is built the other
way round: **nothing the input says is ever emitted as markup.** Every
character is escaped first, and the only tags in the output are the ones this
module adds itself.

It supports what the worklog format actually uses (worklog-format.md §3): ATX
headings, paragraphs, bullet and ordered lists nested by indentation, fenced
code, inline code, ``**bold**``, ``*italic*`` and http(s) links. Anything else
-- tables, block quotes, footnotes, raw HTML -- is shown as the text it is, line
breaks kept. That is the safe way to be incomplete: an unsupported construct
reads a little plainer, it never runs.

Two omissions are deliberate:

- ``_underscore_`` emphasis. Worklogs name identifiers such as
  REPO_WORKLOG_ANTHROPIC_MODEL outside backticks, and reading their underscores
  as emphasis would mangle exactly the names a reader searches for.
- Links other than http(s) and the worklog's own day files. ``javascript:`` and
  ``data:`` are the obvious ones, but ``//host`` matters too: on a ``file://``
  page it resolves to ``file://host/``, which Windows opens as a network share.
"""

from __future__ import annotations

import html
import re

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$")
_LIST_RE = re.compile(r"^( *)([-*+]|\d{1,9}[.)])(?:\s+(.*))?$")
_HR_RE = re.compile(r"^ {0,3}([-*_])(?:\s*\1){2,}\s*$")
# A whole-line HTML comment -- in a day file, a GIT_WORKLOG marker. It is
# structure, not text: dropped, and it ends the paragraph it interrupts, so a
# summary bracketed by SUMMARY markers never runs into the line after them.
COMMENT_RE = re.compile(r"^\s*<!--.*-->\s*$")

_CODE_RE = re.compile(r"(`+)(.+?)\1")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^()\s]*)(?:\s+\"[^\"]*\")?\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^()\s]*)(?:\s+\"[^\"]*\")?\)")
_AUTOLINK_RE = re.compile(r"<(https?://[^\s<>]+)>", re.IGNORECASE)
_STRONG_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_EM_RE = re.compile(r"(?<!\*)\*(?=[^\s*])([^*]+?)(?<=[^\s*])\*(?!\*)")
_DAY_LINK_RE = re.compile(r"^(?:\.{1,2}/)*(?:days/)?(\d{4}-\d{2}-\d{2})\.md$")
# Placeholders are NUL-delimited, and NUL is stripped from every input first,
# so text can never forge one.
_SLOT_RE = re.compile("\x00(\\d+)\x00")

_EXTERNAL = ' rel="noopener noreferrer" target="_blank"'


def _clean(text: str) -> str:
    return (text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
            .expandtabs(4))


def _href(target: str, dates) -> "str | None":
    """Where a link may point, or None to keep only its text."""
    t = target.strip()
    low = t.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return t
    m = _DAY_LINK_RE.match(t)
    if m and m.group(1) in dates:
        return "#d-" + m.group(1)
    return None


def inline(text: str, *, dates=frozenset(), links: bool = True) -> str:
    """One line of Markdown as HTML.

    ``dates`` are the day files a relative ``<date>.md`` link may be rewritten
    to. ``links=False`` keeps link text and drops the link, for places that are
    themselves inside a link.
    """
    slots: "list[str]" = []

    def slot(fragment: str) -> str:
        slots.append(fragment)
        return f"\x00{len(slots) - 1}\x00"

    def code(m):
        return slot("<code>" + html.escape(m.group(2), quote=False) + "</code>")

    def image(m):
        return slot(html.escape(m.group(1), quote=False))

    def link(m):
        label = _emphasis(html.escape(m.group(1), quote=False))
        href = _href(m.group(2), dates) if links else None
        if href is None:
            return slot(label)
        extra = "" if href.startswith("#") else _EXTERNAL
        return slot(f'<a href="{html.escape(href)}"{extra}>{label}</a>')

    def autolink(m):
        shown = html.escape(m.group(1), quote=False)
        if not links:
            return slot(shown)
        return slot(f'<a href="{html.escape(m.group(1))}"{_EXTERNAL}>{shown}</a>')

    text = _CODE_RE.sub(code, _clean(text))
    text = _IMAGE_RE.sub(image, text)
    text = _LINK_RE.sub(link, text)
    text = _AUTOLINK_RE.sub(autolink, text)
    text = _emphasis(html.escape(text, quote=False))
    # A link label can hold a code span, so a slot can hold a slot.
    while _SLOT_RE.search(text):
        text = _SLOT_RE.sub(lambda m: slots[int(m.group(1))], text)
    return text


def _emphasis(escaped: str) -> str:
    escaped = _STRONG_RE.sub(r"<strong>\1</strong>", escaped)
    return _EM_RE.sub(r"<em>\1</em>", escaped)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _fenced(lines: "list[str]", i: int, opener: str, indent: int,
            out: "list[str]") -> int:
    """Emit the fenced block opening at ``lines[i]``; return the next index."""
    close = re.compile(r"^\s*" + re.escape(opener[0]) + "{" + str(len(opener)) + r",}\s*$")
    body = []
    i += 1
    while i < len(lines) and not close.match(lines[i]):
        line = lines[i]
        body.append(line[min(indent, _indent(line)):])
        i += 1
    out.append("<pre><code>" + html.escape("\n".join(body), quote=False)
               + "</code></pre>")
    return i + 1   # past the closing fence -- or the end, if it never closed


def _list(lines: "list[str]", i: int, out: "list[str]", dates) -> int:
    """Emit the list starting at ``lines[i]``; return the next index."""
    base = _indent(lines[i])
    ordered = _LIST_RE.match(lines[i]).group(2)[0].isdigit()
    items: "list[dict]" = []
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            # A blank line ends the list unless the list, or its last item,
            # carries on after it.
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n and items and (_indent(lines[j]) > base or (
                    _indent(lines[j]) == base and _LIST_RE.match(lines[j]))):
                i = j
                continue
            break
        if COMMENT_RE.match(line):
            break
        ind = _indent(line)
        m = _LIST_RE.match(line)
        if m and ind == base:
            items.append({"text": [m.group(3) or ""], "children": []})
            i += 1
        elif m and ind > base and items:
            i = _list(lines, i, items[-1]["children"], dates)
        elif ind > base and items:
            fence = _FENCE_RE.match(line.strip())
            if fence:
                i = _fenced(lines, i, fence.group(1), ind, items[-1]["children"])
            else:
                items[-1]["text"].append(line.strip())
                i += 1
        else:
            break
    tag = "ol" if ordered else "ul"
    parts = [f"<{tag}>"]
    for item in items:
        # An item that opens with bold text is a labelled field -- the shape of
        # every work-item bullet (`- **label：** value`). Marked here, by
        # structure, so the page can style the label without knowing its words.
        opener = '<li class="kv">' if item["text"][0].startswith("**") else "<li>"
        text = "<br>\n".join(inline(t, dates=dates) for t in item["text"])
        parts.append(opener + text + "".join(item["children"]) + "</li>")
    parts.append(f"</{tag}>")
    out.append("\n".join(parts))
    return i


def render(md: str, *, dates=frozenset(), min_heading: int = 4) -> str:
    """A block of Markdown as HTML.

    Headings are clamped to at least ``min_heading``, because this text always
    sits inside a page that already has its own h1-h3.
    """
    lines = _clean(md).split("\n")
    out: "list[str]" = []
    para: "list[str]" = []

    def flush():
        if para:
            out.append("<p>" + "<br>\n".join(inline(p, dates=dates) for p in para)
                       + "</p>")
            para.clear()

    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        fence = _FENCE_RE.match(line)
        if fence:
            flush()
            i = _fenced(lines, i, fence.group(1), _indent(line), out)
            continue
        if not line.strip() or COMMENT_RE.match(line):
            flush()
            i += 1
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            flush()
            level = min(6, max(min_heading, len(heading.group(1))))
            out.append(f"<h{level}>{inline(heading.group(2), dates=dates)}</h{level}>")
            i += 1
            continue
        if _HR_RE.match(line):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if _LIST_RE.match(line):
            flush()
            i = _list(lines, i, out, dates)
            continue
        para.append(line.strip())
        i += 1
    flush()
    return "\n".join(out)
