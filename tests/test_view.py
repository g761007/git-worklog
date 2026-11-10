"""git-worklog view: the worklog as one page, read-only.

Every byte of the page's content is rendered by Python, so it is checked here as
HTML. Navigation is CSS and the one script only adds search -- that part is
verified by hand in a browser, because a JS test runner would cost the
zero-dependency install. What these tests pin hardest is what the page must
never do: let a day file's text become markup, write into the repository or its
worklog, or let a browser's output into the JSON on stdout.

The same goes for the commits behind the hashes: the drawer that shows one is
script, checked by hand, but what it is given -- which commits, in what form --
and what ``view --serve`` will and will not answer are checked here.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import types
import unittest
import urllib.request
from unittest import mock

import helpers  # noqa: F401  (bootstraps sys.path for the git_worklog package)
from helpers import ROOT, SKILL_ROOT, make_history_repo, rmtree, run_cli

from git_worklog import markers as wm
from git_worklog import mdhtml, viewer, viewserver
from git_worklog.analysis import commits as gitcommits
from git_worklog.analysis.reconcile import cited_hashes
from git_worklog.cli import view as view_cmd

MARKED = """## 當日摘要
<!-- GIT_WORKLOG:SUMMARY:START -->
Lead sentence for the day.
<!-- GIT_WORKLOG:SUMMARY:END -->

A longer paragraph after the markers.

參與者：Alice Chen

## 主要異動

### First item

- **異動內容：** Did `thing` with **care**.
- **相關檔案：** `src/a.py`、`src/b.py`
- **相關 commits：** abc1234 (Alice Chen) feat: a；def5678 (Alice Chen) fix: b

### Second item

- **異動內容：** Another, also abc1234def5678901234567890123456789abcd.

## 修正項目

### A fix under another section

- **異動內容：** Fixed in 1234abc.
"""

HOSTILE = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    '<a href="https://ok.example" onclick="steal()">x</a>',
    "[click](javascript:alert(1))",
    "[click](JaVaScRiPt:alert`1`)",
    "[click](//evil.example/share)",
    "[click](data:text/html;base64,PHNjcmlwdD4=)",
    "![pixel](https://evil.example/p.png)",
    "<https://ok.example/?a=<b>>",
    "`<b>code</b>` and <b>bold</b>",
    "\x000\x00 tries to forge a placeholder `x`",
]

# Every tag the renderer may emit. Anything else in its output came from input.
RENDERER_TAGS = {"p", "br", "ul", "ol", "li", "code", "strong", "em", "a", "pre",
                 "h4", "h5", "h6", "hr", "button", "span"}


class Raw:
    """A day file's literal bytes, for files the writer would never produce."""

    def __init__(self, data):
        self.data = data if isinstance(data, bytes) else data.encode("utf-8")


def make_worklog(days: dict, *, index: "str | None" = None, legacy: bool = False,
                 config: "dict | None" = None, repo: "str | None" = None) -> str:
    """A repository directory holding a worklog with ``days``; returns the repo.

    The directory is not a Git repository unless ``repo`` hands one in.
    """
    repo = repo or tempfile.mkdtemp(prefix="gw_view_")
    worklog = os.path.join(repo, wm.WORKLOG_DIRNAME)
    days_dir = worklog if legacy else os.path.join(worklog, wm.DAYS_SUBDIR)
    os.makedirs(days_dir)
    for date, content in days.items():
        if isinstance(content, Raw):
            data = content.data
        else:
            data = wm.render_new_day_file(date, content, timezone="Asia/Taipei",
                                          branch="main", head="9f9f9f9").encode("utf-8")
        with open(os.path.join(days_dir, f"{date}.md"), "wb") as fh:
            fh.write(data)
    if index is not None:
        with open(os.path.join(worklog, wm.INDEX_FILENAME), "w", encoding="utf-8") as fh:
            fh.write(index)
    if config is not None:
        with open(os.path.join(worklog, wm.CONFIG_FILENAME), "w", encoding="utf-8") as fh:
            json.dump(config, fh)
    return repo


def snapshot(root: str) -> dict:
    """Every file under ``root`` with its bytes."""
    files = {}
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as fh:
                files[os.path.relpath(path, root)] = fh.read()
    return files


def page_script(page: str) -> str:
    return page.split("<script>", 1)[1].split("</script>", 1)[0]


class InertMixin:
    def assert_inert(self, out: str) -> None:
        self.assertNotRegex(out, r"(?i)<script")
        self.assertNotRegex(out, r"(?i)<img")
        self.assertNotRegex(out, r"(?i)<[a-z][^>]*\son\w+\s*=")
        for href in re.findall(r'href="([^"]*)"', out):
            self.assertRegex(href, r"^(https?://|#)")


class TestMarkdownIsInert(InertMixin, unittest.TestCase):
    """No input, however shaped, comes out as markup."""

    def test_hostile_text_never_becomes_markup(self):
        for text in HOSTILE:
            with self.subTest(text=text):
                for out in (mdhtml.render(text), mdhtml.render("- **label：** " + text),
                            mdhtml.inline(text), mdhtml.inline(text, links=False)):
                    self.assert_inert(out)
                    self.assertLessEqual(set(re.findall(r"<([a-z0-9]+)", out)),
                                         RENDERER_TAGS)

    def test_escaped_text_is_still_shown(self):
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;",
                      mdhtml.render("<script>alert(1)</script>"))

    def test_code_span_content_is_escaped(self):
        self.assertIn("<code>&lt;b&gt;x&lt;/b&gt;</code>", mdhtml.inline("`<b>x</b>`"))

    def test_nul_cannot_forge_a_placeholder(self):
        # NUL, "0", NUL is how slot 0 is spelled internally; had it survived, the
        # code span's HTML would be spliced in here too.
        out = mdhtml.inline("a\x000\x00b `x`")
        self.assertIn("a0b", out)
        self.assertEqual(out.count("<code>"), 1)

    def test_only_http_links_are_links(self):
        out = mdhtml.inline("[a](https://x.example/p) [b](http://y.example) "
                            "[c](ftp://z.example) [d](../README.md)")
        self.assertEqual(re.findall(r'href="([^"]*)"', out),
                         ["https://x.example/p", "http://y.example"])
        self.assertIn(" c ", out)
        self.assertTrue(out.endswith(" d"))

    def test_day_links_point_inside_the_page(self):
        out = mdhtml.inline("[prev](./days/2026-07-15.md) [gone](./days/2020-01-01.md)",
                            dates={"2026-07-15"})
        self.assertEqual(re.findall(r'href="([^"]*)"', out), ["#d-2026-07-15"])
        self.assertIn("gone", out)


class TestMarkdownStructure(unittest.TestCase):
    """The constructs the worklog template actually uses."""

    def test_work_item_fields_are_marked_by_shape(self):
        out = mdhtml.render("- **異動內容：** text\n- **相關檔案：**\n  - `a.py`\n  - `b.py`\n"
                            "- plain bullet with **bold** later")
        self.assertIn('<li class="kv"><strong>異動內容：</strong> text</li>', out)
        self.assertRegex(out, r'<li class="kv"><strong>相關檔案：</strong><ul>\s*'
                              r"<li><code>a\.py</code></li>")
        self.assertIn("<li>plain bullet with <strong>bold</strong> later</li>", out)

    def test_heading_inside_a_fence_is_code(self):
        out = mdhtml.render("```\n## not a heading\n```")
        self.assertIn("<pre><code>## not a heading</code></pre>", out)
        self.assertNotIn("<h", out)

    def test_marker_lines_end_a_paragraph(self):
        out = mdhtml.render("<!-- GIT_WORKLOG:SUMMARY:START -->\nLead\n"
                            "<!-- GIT_WORKLOG:SUMMARY:END -->\nNext")
        self.assertEqual(out, "<p>Lead</p>\n<p>Next</p>")

    def test_snake_case_is_not_emphasis(self):
        self.assertNotIn("<em>", mdhtml.inline("REPO_WORKLOG_ANTHROPIC_MODEL and a_b_c"))
        self.assertEqual(mdhtml.inline("*em* **strong**"),
                         "<em>em</em> <strong>strong</strong>")

    def test_unsupported_blocks_keep_their_lines(self):
        out = mdhtml.render("| a | b |\n|---|---|\n> quoted")
        self.assertEqual(out, "<p>| a | b |<br>\n|---|---|<br>\n&gt; quoted</p>")

    def test_headings_are_demoted_below_the_page(self):
        self.assertEqual(mdhtml.render("# Big"), "<h4>Big</h4>")


def badged(html: str) -> "list[str]":
    return re.findall(r'<button type="button" class="hash" data-hash="([0-9a-f]+)"', html)


class TestCommitBadges(unittest.TestCase):
    """Commit hashes become copy buttons; look-alikes stay text."""

    def test_the_formats_own_commit_references_become_badges(self):
        out = mdhtml.inline("d6f6687 (Alice) fix: a；f00b9f3 (Alice) Merge pull request #30")
        self.assertEqual(badged(out), ["d6f6687", "f00b9f3"])
        self.assertIn('title="Copy d6f6687"', out)

    def test_an_all_digit_hash_counts_when_written_as_a_reference(self):
        # Four of this repository's 91 cited commits are all digits.
        self.assertEqual(badged(mdhtml.inline("7545112 (Alice) feat: add it")), ["7545112"])
        self.assertEqual(badged(mdhtml.inline("7545112（Alice）feat: add it")), ["7545112"])

    def test_numbers_and_all_hex_words_stay_text(self):
        self.assertEqual(badged(mdhtml.inline("1047686 bytes; defaced and acceded")), [])

    def test_hashes_in_prose_with_or_without_spaces(self):
        self.assertEqual(badged(mdhtml.inline("修正於1234abc。以及（fc845f7）")),
                         ["1234abc", "fc845f7"])
        full = "754511264668bf03e8d62f58a51795c9cb6f153b"
        self.assertEqual(badged(mdhtml.inline(f"{full} 新增 README.md")), [full])

    def test_never_inside_code_links_paths_or_other_hex(self):
        out = mdhtml.inline("`abc1234` [abc1234](https://x.example/commit/abc1234) "
                            "commit/abc1234 #11352b80 "
                            "sha256:6087a2075f53e4dd14d525109e52c421eade40c39ce4b9e8baeb5ee4e7016d29 "
                            "f076bd5c-b83c-4d62-9f3a-12ab34cd56ef")
        self.assertEqual(badged(out), [])

    def test_inside_a_link_a_hash_is_a_badge_that_does_nothing(self):
        out = mdhtml.inline("reverted d6f6687", links=False)
        self.assertEqual(badged(out), [])
        self.assertIn('<span class="hash">d6f6687</span>', out)


class TestDayStructure(unittest.TestCase):
    """Days are cut by structure, never by the words of their headings."""

    def test_an_english_day_splits_the_same_way(self):
        sections = viewer.split_sections(
            "## Daily summary\n<!-- GIT_WORKLOG:SUMMARY:START -->\nShipped it.\n"
            "<!-- GIT_WORKLOG:SUMMARY:END -->\n\n## Changes\n\n### Did a thing\n\n"
            "- **What:** x\n")
        self.assertEqual([s.title for s in sections], ["Daily summary", "Changes"])
        self.assertEqual([t for t, _ in sections[1].items], ["Did a thing"])
        self.assertEqual(viewer.lead_of(sections, ""), "Shipped it.")

    def test_lead_with_and_without_summary_markers(self):
        marked = viewer.split_sections(MARKED)
        self.assertEqual(viewer.lead_of(marked, MARKED), "Lead sentence for the day.")
        unmarked = "## 當日摘要\n\n建立骨架。\n\n第二段。\n\n參與者：A\n"
        self.assertEqual(viewer.lead_of(viewer.split_sections(unmarked), unmarked),
                         "建立骨架。")

    def test_items_under_every_section_count(self):
        sections = viewer.split_sections(MARKED)
        self.assertEqual(sum(len(s.items) for s in sections), 3)
        self.assertEqual(sections[2].items[0][0], "A fix under another section")

    def test_a_fenced_heading_is_not_an_item(self):
        sections = viewer.split_sections("## A\n\n```\n### not an item\n## nor a section\n"
                                          "```\n\n### real\n")
        self.assertEqual(len(sections), 1)
        self.assertEqual([t for t, _ in sections[0].items], ["real"])
        self.assertIn("### not an item", sections[0].body)

    def test_commits_are_counted_the_way_report_counts_them(self):
        repo = make_worklog({"2026-07-15": MARKED})
        self.addCleanup(rmtree, repo)
        day = viewer.load_day(os.path.join(repo, wm.WORKLOG_DIRNAME), "2026-07-15",
                              wm.LAYOUT_CURRENT)
        self.assertEqual(day.hashes, frozenset(h[:7] for h in cited_hashes(MARKED)))
        # A full hash and its short form are one commit; the header's HEAD is
        # the run's, not a citation, and sits outside GENERATED anyway.
        self.assertEqual(day.hashes, {"abc1234", "def5678", "1234abc"})


class TestPage(InertMixin, unittest.TestCase):
    def build(self, days: dict, **kwargs):
        repo = make_worklog(days, **kwargs)
        self.addCleanup(rmtree, repo)
        return viewer.build(os.path.join(repo, wm.WORKLOG_DIRNAME))

    def test_a_hostile_day_cannot_add_markup_to_the_page(self):
        body = "\n\n".join(HOSTILE)
        text = wm.render_new_day_file(
            "2026-07-15", f"## 當日摘要\n\n{body}\n\n## {HOSTILE[0]}\n\n### {HOSTILE[1]}\n\n"
                          f"- **x：** {body}\n")
        text = text.replace("<!-- GIT_WORKLOG:2026-07-15:MANUAL:START -->\n",
                            "<!-- GIT_WORKLOG:2026-07-15:MANUAL:START -->\n" + body + "\n")
        page, info = self.build({"2026-07-15": Raw(text)})
        self.assertEqual(info["warnings"], [])
        self.assertIn("&lt;script&gt;", page)            # it is there, as text
        self.assertEqual(page.count("<script"), 1)         # and only ours runs
        self.assertNotRegex(page, r"(?i)<[a-z][^>]*\son\w+\s*=")
        for href in re.findall(r'href="([^"]*)"', page):
            self.assertRegex(href, r"^(https?://|#)")

    def test_the_policy_allows_exactly_the_embedded_script(self):
        page, _ = self.build({"2026-07-15": MARKED})
        digest = hashlib.sha256(page_script(page).encode("utf-8")).digest()
        expected = "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"
        policy = re.search(r'http-equiv="Content-Security-Policy" content="([^"]*)"', page)
        self.assertIsNotNone(policy)
        self.assertIn("default-src 'none'", policy.group(1))
        self.assertIn("script-src " + expected, policy.group(1))
        # Before anything it governs, and after the charset a file:// page needs.
        self.assertLess(page.index('<meta charset="utf-8">'), policy.start())
        self.assertLess(policy.start(), page.index("<style>"))

    def test_a_chosen_theme_beats_the_system_either_way(self):
        page, _ = self.build({"2026-07-15": MARKED})
        css = page.split("<style>", 1)[1].split("</style>", 1)[0]
        # A dark system applies only while the reader has not picked light...
        self.assertRegex(css, r'@media \(prefers-color-scheme: dark\) \{\s*'
                              r':root:not\(\[data-theme="light"\]\) \{')
        by_system = css.split(':root:not([data-theme="light"]) {', 1)[1].split("}", 1)[0]
        # ...and picking dark applies it whatever the system says, same palette.
        by_choice = css.split(':root[data-theme="dark"] {', 1)[1].split("}", 1)[0]
        self.assertEqual(by_system.strip(), by_choice.strip())
        self.assertIn("color-scheme: dark", by_choice)
        self.assertIn('<button id="theme"', page)
        # The script that applies a remembered choice runs before the body paints,
        # so the other theme never flashes first.
        self.assertLess(page.index("<script>"), page.index("<body>"))

    def test_hash_badges_never_end_up_inside_a_link(self):
        day = ("## 當日摘要\n\nReverted d6f6687 today.\n\n## 主要異動\n\n"
               "### Revert d6f6687\n\n- **相關 commits：** d6f6687 (Alice) revert\n")
        page, _ = self.build({"2026-07-15": day})
        # The card's lead and the table of contents are links: a span there.
        self.assertIsNone(re.search(r"<a [^>]*>(?:(?!</a>).)*<button", page, re.S))
        self.assertIn('<span class="hash">d6f6687</span>', page)
        # In the day itself -- the item's title and its field -- a copy button.
        article = page.split('<article id="d-2026-07-15"', 1)[1]
        self.assertGreaterEqual(len(badged(article)), 3)

    def test_every_day_gets_an_article_and_the_tiles_add_up(self):
        second = "## 當日摘要\n\nSecond day.\n\n## 主要異動\n\n### Only item\n\n- **x：** 1234abc\n"
        page, info = self.build({"2026-07-15": MARKED, "2026-07-17": second})
        self.assertEqual(info["day_count"], 2)
        self.assertEqual(info["range"], {"from": "2026-07-15", "to": "2026-07-17"})
        self.assertEqual(re.findall(r'<article id="(d-[^"]+)"', page),
                         ["d-2026-07-17", "d-2026-07-15"])
        tiles = dict(re.findall(r'<div class="tile"><span>([^<]+)</span><b>([^<]+)</b>', page))
        self.assertEqual(tiles, {"Days logged": "2", "Work items": "4",
                                 "Commits cited": "3", "Span": "3 days"})
        self.assertIn('title="2026-07-16 · no day file"', page)

    def test_a_corrupt_day_is_shown_raw_and_the_others_still_render(self):
        broken = wm.render_new_day_file("2026-07-16", "## 當日摘要\n\nBroken <b>day</b>.\n")
        broken = broken.replace("<!-- GIT_WORKLOG:2026-07-16:MANUAL:END -->", "")
        page, info = self.build({"2026-07-15": MARKED, "2026-07-16": Raw(broken)})
        self.assertEqual([(w["code"], w["date"]) for w in info["warnings"]],
                         [("MANUAL_UNCLOSED", "2026-07-16")])
        self.assertIn('<pre class="raw">', page)
        self.assertIn("Broken &lt;b&gt;day&lt;/b&gt;.", page)
        self.assertIn("First item", page)

    def test_a_non_utf8_day_is_reported_not_fatal(self):
        good = wm.render_new_day_file("2026-07-15", "## 當日摘要\n\nLatin-1 café.\n")
        bad = good.encode("utf-8").replace("café".encode("utf-8"), b"caf\xe9")
        with self.assertRaises(UnicodeDecodeError):     # the fixture took effect
            bad.decode("utf-8")
        page, info = self.build({"2026-07-15": Raw(bad)})
        self.assertEqual([w["code"] for w in info["warnings"]], ["NON_UTF8"])
        self.assertIn("Latin-1 caf�.", page)

    def test_a_legacy_flat_worklog_is_readable(self):
        page, info = self.build({"2026-07-15": MARKED}, legacy=True)
        self.assertEqual(info["layout"], wm.LAYOUT_LEGACY)
        self.assertIn('<article id="d-2026-07-15"', page)

    def test_an_empty_worklog_says_so(self):
        page, info = self.build({})
        self.assertEqual((info["day_count"], info["range"]), (0, None))
        self.assertIn("No worklog days yet", page)

    def test_placeholder_notes_are_hidden_and_real_notes_shown(self):
        for language in wm.INDEX_CHROME_LANGUAGES:
            with self.subTest(placeholder=language):
                page, _ = self.build({"2026-07-15": MARKED},
                                     index=wm.render_index([], language=language))
                self.assertNotIn("Project notes", page)
        page, _ = self.build({"2026-07-15": MARKED},
                             index=wm.render_index([], manual_inner="Read me first.\n"))
        self.assertIn("Project notes", page)
        self.assertIn("Read me first.", page)

    def test_the_content_language_follows_the_index_then_config(self):
        page, _ = self.build({"2026-07-15": MARKED},
                             index=wm.render_index([], language="en"))
        self.assertIn('class="md day-body" lang="en"', page)
        unstamped = wm.render_index([]).replace(" lang=zh-TW", "")
        self.assertIsNone(wm.index_language_of(unstamped))   # the fixture took effect
        page, _ = self.build({"2026-07-15": MARKED}, index=unstamped)
        self.assertIn('class="md day-body" lang="zh-TW"', page)
        page, _ = self.build({"2026-07-15": MARKED}, config={"language": "ja"})
        self.assertIn('class="md day-body" lang="ja"', page)


class TestViewCommand(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="gw_view_home_")
        self.addCleanup(rmtree, self.home)
        self.repo = make_worklog({"2026-07-15": MARKED})
        self.addCleanup(rmtree, self.repo)
        self.worklog = os.path.join(self.repo, wm.WORKLOG_DIRNAME)

    def cli(self, *args, **env):
        # BROWSER=true: a test that forgets --no-open still starts no browser.
        return run_cli(*args, env={"GIT_WORKLOG_HOME": self.home, "BROWSER": "true", **env})

    def test_writes_an_owner_only_page_and_says_where(self):
        payload, rc, _ = self.cli("view", "--no-open", "--repo", self.repo)
        self.assertEqual(rc, 0, payload)
        out = payload["output"]
        self.assertEqual(os.path.dirname(out), os.path.join(self.home, "view"))
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(out)).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(out).st_mode), 0o600)
        self.assertEqual(payload["url"], "file://" + out)
        self.assertEqual((payload["opened"], payload["warnings"], payload["day_count"]),
                         (False, [], 1))
        again, _, _ = self.cli("view", "--no-open", "--repo", self.repo)
        self.assertEqual(again["output"], out)   # reload the tab, not hunt for a file

    def test_a_missing_worklog_is_not_found(self):
        payload, rc, _ = self.cli("view", "--no-open", "--dir",
                                  os.path.join(self.repo, "nope"))
        self.assertEqual((rc, payload["errors"][0]["code"]), (2, "NOT_FOUND"))

    def test_it_never_writes_into_the_worklog(self):
        index = os.path.join(self.worklog, wm.INDEX_FILENAME)
        with open(index, "w", encoding="utf-8") as fh:
            fh.write(wm.render_index([]))
        before = snapshot(self.worklog)
        payload, rc, _ = self.cli("view", "--no-open", "--repo", self.repo,
                                  "--output", index)
        self.assertEqual((rc, payload["errors"][0]["code"]), (2, "OUTPUT_INSIDE_WORKLOG"))
        self.assertEqual(snapshot(self.worklog), before)

    def test_it_reads_the_repository_and_writes_nothing_there(self):
        before = snapshot(self.repo)
        payload, rc, _ = self.cli("view", "--no-open", "--repo", self.repo)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(snapshot(self.repo), before)

    def test_a_browser_cannot_write_into_the_json(self):
        # echo is a "browser" that prints the URL to its stdout, which it shares
        # with ours -- exactly what a real one may do.
        payload, rc, stderr = self.cli("view", "--repo", self.repo, BROWSER="echo")
        self.assertIsNotNone(payload, "stdout was not one JSON object")
        self.assertEqual((rc, payload["opened"]), (0, True))
        self.assertIn(payload["url"], stderr)

    def test_a_browser_that_will_not_open_is_a_warning(self):
        out = os.path.join(self.home, "page.html")
        args = types.SimpleNamespace(repo=self.repo, dir=None, output=out, no_open=False)
        # BROWSER set gets past the no-display check; nothing starts, it is mocked.
        with mock.patch.dict(os.environ, {"BROWSER": "true"}), \
                mock.patch.object(view_cmd.webbrowser, "open", return_value=False):
            payload, code = view_cmd.run(args)
        self.assertEqual((code, payload["opened"]), (0, False))
        self.assertEqual([w["code"] for w in payload["warnings"]], ["BROWSER_NOT_OPENED"])
        self.assertIn(out, view_cmd.render_text(payload))

    def test_the_page_is_the_same_bytes_every_run(self):
        first = os.path.join(self.home, "a.html")
        second = os.path.join(self.home, "b.html")
        self.cli("view", "--no-open", "--repo", self.repo, "--output", first,
                 PYTHONHASHSEED="1")
        self.cli("view", "--no-open", "--repo", self.repo, "--output", second,
                 PYTHONHASHSEED="2")
        with open(first, "rb") as a, open(second, "rb") as b:
            self.assertEqual(a.read(), b.read())


HOSTILE_SUBJECT = "fix: </script><script>alert(1)</script> <!-- and <b>more</b>"


def git_out(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def commit_data(page: str) -> dict:
    blob = re.search(r'<script type="application/json" id="commits">(.*?)</script>',
                     page, re.S)
    return json.loads(blob.group(1))


class CitedRepo(unittest.TestCase):
    """A real repository whose worklog cites four of its six commits."""

    @classmethod
    def setUpClass(cls):
        cls.repo = make_history_repo()
        cls.addClassCleanup(rmtree, cls.repo)
        helpers._write(cls.repo, "notes.txt", "x\n")
        helpers._commit(cls.repo, "2026-07-13T10:00:00+08:00", HOSTILE_SUBJECT)
        (cls.add, cls.cache, cls.fix, cls.revert, cls.rename,
         cls.hostile) = git_out(cls.repo, "log", "--reverse", "--format=%H").split()
        make_worklog({
            # The second hash is written the way Chinese prose writes one: with
            # no space on either side, which only the renderer's scan finds.
            "2026-07-10": "## 當日摘要\n\nCache work.\n\n## 主要異動\n\n### Cache\n\n"
                          f"- **相關 commits：** {cls.revert[:7]} (Fixture Bot) revert；"
                          f"修正了{cls.fix[:8]}的問題\n",
            "2026-07-12": "## 當日摘要\n\nRename.\n\n## 主要異動\n\n### Rename\n\n"
                          f"- **相關 commits：** {cls.rename[:7]} (Fixture Bot) refactor；"
                          f"{cls.hostile[:7]} (Fixture Bot) fix\n",
        }, repo=cls.repo)
        cls.worklog = os.path.join(cls.repo, wm.WORKLOG_DIRNAME)
        cls.cited = {cls.fix, cls.revert, cls.rename, cls.hostile}


class TestCitedCommits(CitedRepo):
    """What Git says about a cited commit, and that nothing else is asked."""

    def test_git_describes_the_commits_it_is_asked_about(self):
        commits, tokens = gitcommits.collect(
            self.repo, [self.revert[:7], self.rename[:7], self.add, "abcdef1",
                        self.fix[:7].upper()])
        self.assertEqual(tokens, {self.revert[:7]: self.revert, self.rename[:7]: self.rename,
                                  self.add: self.add, self.fix[:7]: self.fix})
        revert = commits[self.revert]
        self.assertEqual((revert["subject"], revert["body"], revert["author"]),
                         ("revert: drop cache layer",
                          "This reverts commit adding src/cache.py", "Fixture Bot"))
        self.assertTrue(revert["date"].startswith("2026-07-10T15:00:00"))
        self.assertEqual(revert["files"], [{"path": "src/cache.py", "old_path": None,
                                            "additions": 0, "deletions": 4}])
        self.assertEqual((revert["file_count"], revert["additions"], revert["deletions"]),
                         (1, 0, 4))
        renamed = {f["path"]: f for f in commits[self.rename]["files"]}
        self.assertEqual(renamed["src/math_utils.py"]["old_path"], "src/calc.py")
        self.assertIsNone(renamed["assets/logo.png"]["additions"])   # binary
        # The root commit has no parent to be diffed against, and still lists its file.
        self.assertEqual([f["path"] for f in commits[self.add]["files"]], ["src/calc.py"])

    def test_only_the_repository_the_worklog_sits_in_is_asked(self):
        # Git would happily answer from a parent repository; that one is not ours.
        self.assertEqual(gitcommits.collect(os.path.join(self.repo, "src"), [self.revert[:7]]),
                         ({}, {}))
        plain = tempfile.mkdtemp(prefix="gw_view_plain_")
        self.addCleanup(rmtree, plain)
        self.assertEqual(gitcommits.collect(plain, [self.revert[:7]]), ({}, {}))

    def test_a_commit_with_too_many_files_is_listed_in_part_and_counted_in_full(self):
        with mock.patch.object(gitcommits, "MAX_FILES", 1):
            commit = gitcommits.collect(self.repo, [self.rename])[0][self.rename]
        self.assertEqual((len(commit["files"]), commit["file_count"]), (1, 2))

    def test_the_page_carries_the_cited_commits_and_no_others(self):
        page, info = viewer.build(self.worklog, repo=self.repo)
        data = commit_data(page)
        self.assertEqual(set(data["commits"]), self.cited)
        self.assertEqual(info["commit_count"], 4)
        self.assertEqual(data["tokens"][self.fix[:8]], self.fix)   # glued to Chinese text
        self.assertEqual(set(data["tokens"].values()), self.cited)
        # The page is not a history browser: an uncited commit is nowhere on it.
        self.assertNotIn("feat: add cache layer", page)
        self.assertNotIn(self.cache, page)
        self.assertEqual(page, viewer.build(self.worklog, repo=self.repo)[0])

    def test_a_commit_message_cannot_leave_its_data_block(self):
        page, _ = viewer.build(self.worklog, repo=self.repo)
        blob = page.split('<script type="application/json" id="commits">', 1)[1]
        blob = blob.split("</script>", 1)[0]
        self.assertNotIn("<", blob)
        self.assertEqual(commit_data(page)["commits"][self.hostile]["subject"], HOSTILE_SUBJECT)
        self.assertEqual(page.count("<script>"), 1)     # still the only one that runs
        self.assertEqual(page.count("<script"), 2)

    def test_without_git_the_page_is_what_it_was(self):
        page, info = viewer.build(self.worklog)
        self.assertEqual(info["commit_count"], 0)
        self.assertNotIn('id="commits"', page)
        plain = make_worklog({"2026-07-15": MARKED})
        self.addCleanup(rmtree, plain)
        page, info = viewer.build(os.path.join(plain, wm.WORKLOG_DIRNAME), repo=plain)
        self.assertEqual((info["commit_count"], info["warnings"]), (0, []))
        self.assertNotIn('id="commits"', page)

    def test_only_a_served_page_may_fetch(self):
        static, _ = viewer.build(self.worklog, repo=self.repo)
        served, _ = viewer.build(self.worklog, repo=self.repo, diff_base="diff/")
        policy = r'http-equiv="Content-Security-Policy" content="([^"]*)"'
        self.assertNotIn("connect-src", re.search(policy, static).group(1))
        self.assertIn("connect-src 'self'", re.search(policy, served).group(1))
        self.assertNotIn("data-diff=", static.split("<style>", 1)[0])
        self.assertIn('<html lang="en" data-diff="diff/">', served)
        self.assertEqual(page_script(static), page_script(served))   # one script, one hash

    def test_the_command_reports_how_many_commits_it_found(self):
        home = tempfile.mkdtemp(prefix="gw_view_home_")
        self.addCleanup(rmtree, home)
        before = snapshot(self.repo)
        payload, rc, _ = run_cli("view", "--no-open", "--repo", self.repo,
                                 env={"GIT_WORKLOG_HOME": home})
        self.assertEqual((rc, payload["commit_count"]), (0, 4))
        self.assertEqual(snapshot(self.repo), before)


class TestViewServer(CitedRepo):
    """``view --serve``: the page and its cited commits' diffs, to one caller."""

    def setUp(self):
        self.server = viewserver.Server(self.worklog, self.repo)
        self.server.page()
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_port
        self.base = f"/{self.server.token}/"

    def request(self, path: str, *, host: "str | None" = None, method: str = "GET"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        self.addCleanup(conn.close)
        conn.putrequest(method, path, skip_host=True)
        conn.putheader("Host", host or f"127.0.0.1:{self.port}")
        conn.endheaders()
        response = conn.getresponse()
        return response.status, response, response.read()

    def test_it_listens_on_loopback_only(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertEqual(self.server.url, f"http://127.0.0.1:{self.port}{self.base}")

    def test_the_page_is_served_with_its_diffs_switched_on(self):
        status, response, body = self.request(self.base)
        self.assertEqual(status, 200)
        self.assertIn('data-diff="diff/"', body.decode("utf-8"))
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.getheader("Cross-Origin-Resource-Policy"), "same-origin")
        self.assertFalse([h for h, _ in response.getheaders()
                          if h.lower().startswith("access-control-")])

    def test_a_cited_commits_diff_comes_one_file_at_a_time(self):
        status, response, body = self.request(self.base + "diff/" + self.fix)
        self.assertEqual(status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/json; charset=utf-8")
        self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
        patch = json.loads(body)
        self.assertEqual((len(patch["files"]), patch["truncated"]), (1, False))
        self.assertTrue(patch["files"][0].startswith("diff --git a/src/cache.py"))
        self.assertIn("\n-def get(k):\n", patch["files"][0])
        self.assertIn("\n+def get(key):\n", patch["files"][0])
        _, _, body = self.request(self.base + "diff/" + self.rename)
        # As many pieces as the page lists files, so the two line up by position.
        self.assertEqual(len(json.loads(body)["files"]), 2)

    def test_a_commit_the_worklog_does_not_cite_is_not_served(self):
        for name in (self.cache, self.add[:7], self.fix[:8], "HEAD", "../" + self.fix, ""):
            with self.subTest(name=name):
                self.assertEqual(self.request(self.base + "diff/" + name)[0], 404)

    def test_the_token_is_the_way_in(self):
        for path in ("/", "/wrong/", "/wrong/diff/" + self.fix, self.base.rstrip("/"),
                     "/" + self.server.token[:-1] + "/"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)

    def test_only_its_own_address_is_answered(self):
        # A rebinding page reaches the port under its own hostname, and says so.
        for host in ("evil.example", f"evil.example:{self.port}", f"localhost:{self.port}",
                     "127.0.0.1"):
            with self.subTest(host=host):
                self.assertEqual(self.request(self.base, host=host)[0], 403)

    def test_it_only_reads(self):
        before = snapshot(self.repo)
        self.assertEqual(self.request(self.base, method="POST")[0], 501)
        self.request(self.base)
        self.request(self.base + "diff/" + self.rename)
        self.assertEqual(snapshot(self.repo), before)

    def test_an_oversized_diff_is_cut_and_says_so(self):
        with mock.patch.object(viewserver, "MAX_DIFF", 60):
            patch = viewserver.diff(self.repo, self.rename)
        self.assertTrue(patch["truncated"])
        self.assertLessEqual(len("".join(patch["files"])), 60)

    def test_serving_and_writing_a_file_do_not_combine(self):
        payload, rc, stderr = run_cli("view", "--serve", "--output", "x.html",
                                      "--repo", self.repo)
        self.assertEqual((payload, rc), (None, 2))
        self.assertIn("not allowed with", stderr)

    @unittest.skipIf(sys.platform == "win32", "SIGINT cannot be sent to a child there")
    def test_the_command_answers_first_and_serves_until_interrupted(self):
        home = tempfile.mkdtemp(prefix="gw_view_home_")
        self.addCleanup(rmtree, home)
        env = dict(os.environ, PYTHONPATH=SKILL_ROOT, GIT_WORKLOG_HOME=home, BROWSER="true")
        proc = subprocess.Popen(
            [sys.executable, "-m", "git_worklog", "view", "--serve", "--no-open",
             "--repo", self.repo], stdout=subprocess.PIPE, env=env)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        self.addCleanup(proc.stdout.close)
        # The answer is whole before the first request is: read until it parses.
        text, payload = "", None
        while payload is None:
            line = proc.stdout.readline().decode("utf-8")
            self.assertTrue(line, f"stdout ended before one JSON object: {text!r}")
            text += line
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                pass
        self.assertEqual((payload["ok"], payload["serving"], payload["output"],
                          payload["opened"], payload["commit_count"]),
                         (True, True, None, False, 4))
        with urllib.request.urlopen(payload["url"], timeout=10) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(os.listdir(home), [])          # served, not written
        proc.send_signal(signal.SIGINT)
        self.assertEqual(proc.wait(timeout=10), 0)


class TestThisRepositorysWorklog(unittest.TestCase):
    """The real worklog, written by real runs, renders without complaint."""

    def test_it_renders_cleanly(self):
        worklog = os.path.join(ROOT, wm.WORKLOG_DIRNAME)
        page, info = viewer.build(worklog)
        self.assertEqual(info["warnings"], [])
        for date in wm.list_day_dates(worklog):
            with self.subTest(date=date):
                self.assertIn(f'<article id="d-{date}"', page)
                day = viewer.load_day(worklog, date, wm.LAYOUT_CURRENT)
                self.assertTrue(day.lead, "every real day has a summary lead")


if __name__ == "__main__":
    unittest.main()
