"""Tests for the directory-based worklog engine.

Covers worklog_markers (day + index primitives), update_daily_worklog,
rebuild_worklog_index, the two validators, and preview_state.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS, run_script, rmtree

sys.path.insert(0, SCRIPTS)
import worklog_markers as wm  # noqa: E402


def day_entries(mapping: dict, meta: dict | None = None) -> str:
    return json.dumps({
        "meta": meta or {"timezone": "Asia/Taipei", "branch": "main", "head": "abc1234"},
        "entries": {d: {"generated_markdown": g} for d, g in mapping.items()},
    })


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


class TestMarkers(unittest.TestCase):
    def test_day_roundtrip_and_empty_manual(self):
        text = wm.render_new_day_file("2026-07-15", "## 當日摘要\n\nX", timezone="Asia/Taipei")
        day, issues = wm.scan_day(text, "2026-07-15")
        self.assertEqual(issues, [])
        self.assertEqual(day.title_date, "2026-07-15")
        self.assertEqual(day.manual, "\n")

    def test_overwrite_preserves_manual_byte_for_byte(self):
        text = wm.render_new_day_file("2026-07-15", "## 當日摘要\n\nfirst")
        marker = "<!-- REPO_WORKLOG:2026-07-15:MANUAL:START -->\n"
        text = text.replace(marker, marker + "issue #42 decision\n")
        before = wm.parse_day(text, "2026-07-15").manual
        out = wm.overwrite_day_generated(text, "2026-07-15", "## 當日摘要\n\nsecond",
                                         timezone="Asia/Taipei", branch="dev", head="ff")
        after = wm.parse_day(out, "2026-07-15")
        self.assertEqual(after.manual, before)          # MANUAL survives exactly
        self.assertIn("second", after.generated)
        self.assertNotIn("first", out)                  # old generated gone
        self.assertIn("Branch：dev", out)               # meta refreshed

    def test_marker_date_mismatch_is_fatal(self):
        text = wm.render_new_day_file("2026-07-15", "x")
        text = text.replace("2026-07-15:MANUAL", "2026-07-99:MANUAL")
        _, issues = wm.scan_day(text, "2026-07-15")
        self.assertTrue(any(i["code"] in ("MARKER_DATE_MISMATCH", "MISSING_MANUAL")
                            for i in issues))
        with self.assertRaises(wm.WorklogFormatError):
            wm.parse_day(text, "2026-07-15")

    def test_summary_extraction(self):
        gen = "## 當日摘要\n\n新增會員搜尋快取並補充 API 測試。\n\n## 主要異動\n"
        self.assertEqual(wm.summarise_generated(gen), "新增會員搜尋快取並補充 API 測試。")
        self.assertEqual(wm.summarise_generated("## 主要異動\n\nno summary section"), "")

    def test_participants_line_below_summary_does_not_hijack_the_index(self):
        # 參與者 must sit BELOW the summary paragraph. summarise_generated takes
        # the first non-empty line under 當日摘要, so putting the participants
        # line first makes every index row read "參與者：…" instead of what
        # actually happened that day — which is exactly what shipped until an
        # end-to-end run caught it.
        gen = ("## 當日摘要\n\n新增會員搜尋快取並補充 API 測試。\n\n"
               "參與者：Alice Chen、Bob Lin\n\n## 主要異動\n")
        self.assertEqual(wm.summarise_generated(gen), "新增會員搜尋快取並補充 API 測試。")

    def test_participants_line_above_summary_would_hijack_the_index(self):
        # Pins the mechanism the rule exists for: this ordering is wrong, and
        # this is precisely how it goes wrong.
        gen = ("## 當日摘要\n\n參與者：Alice Chen\n\n新增會員搜尋快取。\n\n## 主要異動\n")
        self.assertEqual(wm.summarise_generated(gen), "參與者：Alice Chen")

    def test_summary_escapes_pipe_and_caps_length(self):
        gen = "## 當日摘要\n\n" + "A|B " * 40
        out = wm.summarise_generated(gen)
        self.assertLessEqual(len(out), wm.SUMMARY_MAX_CHARS)
        self.assertNotIn("| ", out.replace("\\|", ""))  # raw pipes escaped

    def test_index_roundtrip_and_order(self):
        rows = [("2026-07-15", "a"), ("2026-07-14", "b")]
        idx = wm.render_index(rows)
        doc, issues = wm.scan_index(idx)
        self.assertEqual(issues, [])
        self.assertEqual([d for d, _ in doc.rows], ["2026-07-15", "2026-07-14"])

    def test_parse_date_filename(self):
        self.assertEqual(wm.parse_date_filename("2026-07-15.md"), "2026-07-15")
        self.assertIsNone(wm.parse_date_filename("index.md"))
        self.assertIsNone(wm.parse_date_filename("notes.md"))

    def test_contains_marker_line(self):
        # A bare marker line is detected; the same text mid-line is not a marker.
        self.assertTrue(wm.contains_marker_line(
            "text\n<!-- REPO_WORKLOG:2026-07-15:MANUAL:START -->\n"))
        self.assertTrue(wm.contains_marker_line(
            "<!-- REPO_WORKLOG:INDEX:GENERATED:START -->"))
        self.assertFalse(wm.contains_marker_line(
            "see <!-- REPO_WORKLOG:INDEX:GENERATED:START --> inline"))
        self.assertFalse(wm.contains_marker_line("## 當日摘要\n\nplain text"))

    def test_overwrite_preserves_trailing_content(self):
        # Content a user placed after MANUAL:END must survive re-analysis.
        text = wm.render_new_day_file("2026-07-15", "## 當日摘要\n\nv1") + "footer note\n"
        day, _ = wm.scan_day(text, "2026-07-15")
        self.assertEqual(day.trailing, "footer note\n")
        out = wm.overwrite_day_generated(text, "2026-07-15", "## 當日摘要\n\nv2")
        self.assertIn("footer note", out)
        self.assertIn("v2", out)
        self.assertNotIn("v1", out)

    def test_duplicate_end_marker_detected(self):
        text = wm.render_new_day_file("2026-07-15", "x").replace(
            "<!-- REPO_WORKLOG:2026-07-15:GENERATED:END -->",
            "<!-- REPO_WORKLOG:2026-07-15:GENERATED:END -->\ndup\n"
            "<!-- REPO_WORKLOG:2026-07-15:GENERATED:END -->")
        _, issues = wm.scan_day(text, "2026-07-15")
        self.assertIn("DUPLICATE_GENERATED", [i["code"] for i in issues])


class TestUpdateDaily(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="rw_daily_")
        self.dir = os.path.join(self.work, "PROJECT_WORKLOG")

    def tearDown(self):
        rmtree(self.work)

    def test_dry_run_creates_nothing(self):
        d, _, _ = run_script("update_daily_worklog.py", ["--dir", self.dir],
                             stdin=day_entries({"2026-07-15": "## 當日摘要\n\nX"}))
        self.assertEqual(d["mode"], "dry-run")
        self.assertFalse(os.path.isdir(self.dir))
        self.assertEqual(d["planned_changes"][0]["action"], "create")
        self.assertEqual(d["summaries"]["2026-07-15"], "X")

    def test_apply_creates_isolated_files(self):
        run_script("update_daily_worklog.py", ["--dir", self.dir, "--apply"],
                   stdin=day_entries({"2026-07-15": "## 當日摘要\n\na",
                                      "2026-07-14": "## 當日摘要\n\nb"}))
        self.assertTrue(os.path.exists(os.path.join(self.dir, "2026-07-15.md")))
        self.assertTrue(os.path.exists(os.path.join(self.dir, "2026-07-14.md")))
        v, _, _ = run_script("validate_daily_worklog.py", ["--dir", self.dir])
        self.assertTrue(v["ok"])
        self.assertEqual(v["file_count"], 2)

    def test_overwrite_preserves_manual_and_leaves_other_days(self):
        run_script("update_daily_worklog.py", ["--dir", self.dir, "--apply"],
                   stdin=day_entries({"2026-07-15": "## 當日摘要\n\nfirst",
                                      "2026-07-14": "## 當日摘要\n\nkeep"}))
        p15 = os.path.join(self.dir, "2026-07-15.md")
        p14 = os.path.join(self.dir, "2026-07-14.md")
        marker = "<!-- REPO_WORKLOG:2026-07-15:MANUAL:START -->\n"
        write(p15, read(p15).replace(marker, marker + "issue #42\n"))
        before_14 = read(p14)
        d, _, _ = run_script("update_daily_worklog.py", ["--dir", self.dir, "--apply"],
                             stdin=day_entries({"2026-07-15": "## 當日摘要\n\nsecond"}))
        self.assertEqual(d["planned_changes"][0]["action"], "overwrite")
        out15 = read(p15)
        self.assertIn("second", out15)
        self.assertNotIn("first", out15)
        self.assertIn("issue #42", out15)
        self.assertEqual(read(p14), before_14)  # untouched day is byte-identical

    def test_reapply_identical_is_no_change(self):
        payload = day_entries({"2026-07-15": "## 當日摘要\n\nsame"})
        run_script("update_daily_worklog.py", ["--dir", self.dir, "--apply"], stdin=payload)
        d, _, _ = run_script("update_daily_worklog.py", ["--dir", self.dir, "--apply"], stdin=payload)
        self.assertEqual(d["planned_changes"][0]["action"], "no_change")
        self.assertEqual(d["written_dates"], [])

    def test_refuses_corrupt_day_file(self):
        os.makedirs(self.dir)
        write(os.path.join(self.dir, "2026-07-13.md"), "garbage, no markers\n")
        d, _, _ = run_script("update_daily_worklog.py", ["--dir", self.dir],
                             stdin=day_entries({"2026-07-13": "## 當日摘要\n\nx"}))
        self.assertFalse(d["ok"])
        self.assertEqual(d["errors"][0]["code"], "CORRUPT_MARKERS")

    def test_marker_collision_rejected_as_json_on_both_paths(self):
        # A generated body carrying a REPO_WORKLOG marker line must be refused
        # with a JSON error (not a traceback), consistently in dry-run and apply.
        payload = day_entries({"2026-07-15":
                               "## 當日摘要\n\nquote:\n<!-- REPO_WORKLOG:2026-07-15:MANUAL:START -->"})
        dry, rc1, err1 = run_script("update_daily_worklog.py", ["--dir", self.dir], stdin=payload)
        self.assertIsNotNone(dry, err1)                     # got JSON, not a traceback
        self.assertFalse(dry["ok"])
        self.assertEqual(dry["errors"][0]["code"], "GENERATED_CONTAINS_MARKER")
        ap, rc2, err2 = run_script("update_daily_worklog.py", ["--dir", self.dir, "--apply"],
                                   stdin=payload)
        self.assertIsNotNone(ap, err2)
        self.assertEqual(ap["errors"][0]["code"], "GENERATED_CONTAINS_MARKER")
        self.assertFalse(os.path.isdir(self.dir))           # nothing written

    def test_transactional_rollback_leaves_no_partial_state(self):
        # A mid-swap failure must restore the overwritten day, drop the created
        # day, and leak no temp files (acceptance criterion: no partial writes).
        import update_daily_worklog as u
        os.makedirs(self.dir)
        write(os.path.join(self.dir, "2026-07-15.md"),
              wm.render_new_day_file("2026-07-15", "## 當日摘要\n\nORIGINAL"))
        writes = u._plan(self.dir, {
            "2026-07-15": {"generated_markdown": "## 當日摘要\n\nNEW"},
            "2026-07-16": {"generated_markdown": "## 當日摘要\n\nBRANDNEW"},
        }, {"timezone": "Asia/Taipei"})

        real_replace = os.replace
        calls = {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("injected swap failure")
            return real_replace(src, dst)

        os.replace = flaky
        try:
            with self.assertRaises(OSError):
                u._transactional_apply(self.dir, writes)
        finally:
            os.replace = real_replace

        remaining = sorted(f for f in os.listdir(self.dir) if f.endswith(".md"))
        self.assertEqual(remaining, ["2026-07-15.md"])            # created day dropped
        self.assertIn("ORIGINAL", read(os.path.join(self.dir, "2026-07-15.md")))  # restored
        self.assertEqual([f for f in os.listdir(self.dir) if f.startswith(".rw-")], [])


class TestRebuildIndex(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="rw_idx_")
        self.dir = os.path.join(self.work, "PROJECT_WORKLOG")
        run_script("update_daily_worklog.py", ["--dir", self.dir, "--apply"],
                   stdin=day_entries({"2026-07-15": "## 當日摘要\n\nnewest",
                                      "2026-07-13": "## 當日摘要\n\noldest"}))

    def tearDown(self):
        rmtree(self.work)

    def test_apply_does_not_block_on_an_open_stdin_pipe(self):
        # SKILL.md §8 runs `rebuild_worklog_index.py --apply` with no stdin
        # redirect. Under an agent harness, CI, or cron, stdin is then neither a
        # TTY nor closed, so an isatty()-only guard falls through to
        # sys.stdin.read() and hangs forever. The rest of the suite passes
        # stdin="" (closed immediately), which is exactly why it never caught
        # this. Here stdin stays open, reproducing the real invocation.
        proc = subprocess.Popen(
            ["python3", os.path.join(SCRIPTS, "rebuild_worklog_index.py"),
             "--dir", self.dir, "--apply"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
        )
        # Deliberately do NOT close proc.stdin and do NOT use communicate():
        # both send EOF, which is what makes the rest of the suite pass while
        # the real invocation hangs. Holding the write end open is the whole
        # point of this test.
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            self.fail("rebuild_worklog_index.py --apply blocked on an open stdin "
                      "pipe instead of rebuilding from the day files")
        out = proc.stdout.read()
        proc.stdin.close()
        proc.stdout.close()
        proc.stderr.close()
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(json.loads(out)["ok"])

    def test_builds_descending_with_summaries(self):
        d, _, _ = run_script("rebuild_worklog_index.py", ["--dir", self.dir, "--apply"], stdin="")
        self.assertEqual(d["dates"], ["2026-07-15", "2026-07-13"])
        idx = read(os.path.join(self.dir, "index.md"))
        self.assertIn("[2026-07-15](./2026-07-15.md) | newest", idx)
        v, _, _ = run_script("validate_worklog_index.py", ["--dir", self.dir])
        self.assertTrue(v["ok"])

    def test_overrides_preview_pending_date(self):
        # A date not yet on disk shows up in the preview via overrides.
        d, _, _ = run_script("rebuild_worklog_index.py", ["--dir", self.dir],
                             stdin=json.dumps({"overrides": {"2026-07-16": "pending day"}}))
        self.assertEqual(d["dates"][0], "2026-07-16")
        self.assertIn("pending day", d["preview"])

    def test_preserves_index_manual(self):
        run_script("rebuild_worklog_index.py", ["--dir", self.dir, "--apply"], stdin="")
        idx_path = os.path.join(self.dir, "index.md")
        marker = "<!-- REPO_WORKLOG:INDEX:MANUAL:START -->\n"
        write(idx_path, read(idx_path).replace(marker, marker + "里程碑：v1 上線\n"))
        run_script("rebuild_worklog_index.py", ["--dir", self.dir, "--apply"], stdin="")
        self.assertIn("里程碑：v1 上線", read(idx_path))

    def test_ignores_non_date_markdown(self):
        write(os.path.join(self.dir, "README.md"), "# not a day\n")
        d, _, _ = run_script("rebuild_worklog_index.py", ["--dir", self.dir], stdin="")
        self.assertEqual(d["dates"], ["2026-07-15", "2026-07-13"])


class TestValidators(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="rw_val_")
        self.dir = os.path.join(self.work, "PROJECT_WORKLOG")
        run_script("update_daily_worklog.py", ["--dir", self.dir, "--apply"],
                   stdin=day_entries({"2026-07-15": "## 當日摘要\n\nx"}))
        run_script("rebuild_worklog_index.py", ["--dir", self.dir, "--apply"], stdin="")

    def tearDown(self):
        rmtree(self.work)

    def test_index_link_missing_is_fatal(self):
        os.remove(os.path.join(self.dir, "2026-07-15.md"))
        v, rc, _ = run_script("validate_worklog_index.py", ["--dir", self.dir])
        self.assertFalse(v["ok"])
        self.assertEqual(rc, 2)
        self.assertIn("INDEX_LINK_MISSING", [e["code"] for e in v["errors"]])

    def test_orphan_day_file_is_warning(self):
        run_script("update_daily_worklog.py", ["--dir", self.dir, "--apply"],
                   stdin=day_entries({"2026-07-20": "## 當日摘要\n\norphan"}))
        v, rc, _ = run_script("validate_worklog_index.py", ["--dir", self.dir])
        self.assertTrue(v["ok"])  # still valid; just stale
        self.assertIn("INDEX_ROW_MISSING", [w["code"] for w in v["warnings"]])

    def test_validate_single_day_target(self):
        v, _, _ = run_script("validate_daily_worklog.py",
                             ["--target", os.path.join(self.dir, "2026-07-15.md")])
        self.assertTrue(v["ok"])
        self.assertEqual(v["date"], "2026-07-15")


class TestPreviewState(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rw_home_")
        self.env = {"HOME": self.home}
        self.fp = {
            "repository": {"root": "/repo", "branch": "main", "head": "abc123",
                           "worktree_fingerprint": None},
            "worklog": {"index_sha256": "idx1",
                        "day_files": {"2026-07-15": "h15", "2026-07-14": "missing"},
                        "dir_fingerprint": "df1"},
            "params": {"timezone": "Asia/Taipei", "include_uncommitted": False},
        }

    def tearDown(self):
        rmtree(self.home)

    def _create(self):
        d, _, _ = run_script("preview_state.py",
                             ["create", "--now", "2026-07-15T12:00:00+08:00"],
                             stdin=json.dumps(self.fp), env=self.env)
        return d["preview_id"]

    def _verify(self, worklog, now="2026-07-15T12:05:00+08:00", mark=False):
        pid = self._create()
        state = {"repository": self.fp["repository"], "worklog": worklog,
                 "params": self.fp["params"]}
        extra = ["--mark-applied"] if mark else []
        return run_script("preview_state.py",
                          ["verify", "--id", pid, "--now", now, *extra],
                          stdin=json.dumps(state), env=self.env)

    def test_consistent_when_unchanged(self):
        d, rc, _ = self._verify(self.fp["worklog"])
        self.assertTrue(d["consistent"])
        self.assertEqual(rc, 0)

    def test_changed_day_file_blocks(self):
        wl = {**self.fp["worklog"], "day_files": {"2026-07-15": "CHANGED", "2026-07-14": "missing"}}
        d, rc, _ = self._verify(wl)
        self.assertFalse(d["consistent"])
        self.assertEqual(rc, 3)
        self.assertTrue(any(m["field"] == "day files" for m in d["mismatches"]))

    def test_directory_listing_change_blocks(self):
        wl = {**self.fp["worklog"], "dir_fingerprint": "df2"}
        d, rc, _ = self._verify(wl)
        self.assertFalse(d["consistent"])
        self.assertTrue(any(m["field"] == "worklog directory listing" for m in d["mismatches"]))

    def test_index_change_blocks(self):
        wl = {**self.fp["worklog"], "index_sha256": "idx2"}
        d, rc, _ = self._verify(wl)
        self.assertFalse(d["consistent"])
        self.assertTrue(any(m["field"] == "index.md content" for m in d["mismatches"]))


if __name__ == "__main__":
    unittest.main()
