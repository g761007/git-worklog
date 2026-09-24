"""git-worklog view: the worklog as one page, read-only.

Every byte of the page's content is rendered by Python, so it is checked here as
HTML. Navigation is CSS and the one script only adds search -- that part is
verified by hand in a browser, because a JS test runner would cost the
zero-dependency install. What these tests pin hardest is what the page must
never do: let a day file's text become markup, write into the repository or its
worklog, or let a browser's output into the JSON on stdout.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import tempfile
import types
import unittest
from unittest import mock

import helpers  # noqa: F401  (bootstraps sys.path for the git_worklog package)
from helpers import ROOT, rmtree, run_cli

from git_worklog import markers as wm
from git_worklog import mdhtml, viewer
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
                 "h4", "h5", "h6", "hr"}


class Raw:
    """A day file's literal bytes, for files the writer would never produce."""

    def __init__(self, data):
        self.data = data if isinstance(data, bytes) else data.encode("utf-8")


def make_worklog(days: dict, *, index: "str | None" = None, legacy: bool = False,
                 config: "dict | None" = None) -> str:
    """A repository directory holding a worklog with ``days``; returns the repo."""
    repo = tempfile.mkdtemp(prefix="gw_view_")
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
