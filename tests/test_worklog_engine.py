"""Tests for the worklog engine: worklog_markers, update, validate, preview."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS, run_script, rmtree

sys.path.insert(0, SCRIPTS)
import worklog_markers as wm  # noqa: E402


def entries(mapping: dict) -> str:
    return json.dumps({"entries": {d: {"generated_markdown": g} for d, g in mapping.items()}})


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


class TestMarkers(unittest.TestCase):
    def test_roundtrip_preserves_manual(self):
        block = wm.render_generated_block("2026-07-15", "GEN BODY")
        doc = wm.WorklogDoc(header=wm.DEFAULT_HEADER, footer="",
                            entries=[wm.Entry("2026-07-15", block, "GEN BODY", "", "## 2026-07-15")])
        text = wm.serialise(doc)
        parsed = wm.parse(text)
        self.assertEqual(parsed.dates(), ["2026-07-15"])

    def test_duplicate_date_is_fatal(self):
        block = wm.render_generated_block("2026-07-15", "x")
        text = (wm.DEFAULT_HEADER + wm.ENTRIES_START + "\n\n"
                + block + "\n" + block + "\n" + wm.ENTRIES_END + "\n")
        _, issues = wm.scan(text)
        codes = {i["code"] for i in issues}
        self.assertIn("DUPLICATE_DATE", codes)
        with self.assertRaises(wm.WorklogFormatError):
            wm.parse(text)


class TestUpdateWorklog(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="rw_wl_")
        self.target = os.path.join(self.work, "docs", "PROJECT_WORKLOG.md")

    def tearDown(self):
        rmtree(self.work)

    def test_dry_run_does_not_create_docs_dir(self):
        d, _, _ = run_script("update_worklog.py", ["--target", self.target],
                             stdin=entries({"2026-07-15": "### 當日摘要\n\nX"}))
        self.assertEqual(d["mode"], "dry-run")
        self.assertFalse(os.path.isdir(os.path.dirname(self.target)))
        self.assertFalse(os.path.exists(self.target))

    def test_apply_inserts_descending(self):
        run_script("update_worklog.py", ["--target", self.target, "--apply"],
                   stdin=entries({"2026-07-10": "a", "2026-07-15": "b"}))
        v, _, _ = run_script("validate_worklog.py", ["--target", self.target])
        self.assertEqual(v["dates"], ["2026-07-15", "2026-07-10"])
        self.assertTrue(v["sorted_descending"])

    def test_overwrite_preserves_manual(self):
        run_script("update_worklog.py", ["--target", self.target, "--apply"],
                   stdin=entries({"2026-07-15": "first version"}))
        # Inject a manual note.
        text = read(self.target)
        marker = "<!-- REPO_WORKLOG:2026-07-15:MANUAL:START -->\n"
        text = text.replace(marker, marker + "\nissue #42 decision: JWT\n")
        write(self.target,text)
        # Overwrite generated.
        d, _, _ = run_script("update_worklog.py", ["--target", self.target, "--apply"],
                             stdin=entries({"2026-07-15": "second version"}))
        self.assertEqual(d["planned_changes"][0]["action"], "overwrite")
        out = read(self.target)
        self.assertIn("second version", out)
        self.assertNotIn("first version", out)
        self.assertIn("issue #42", out)

    def test_middle_insert_keeps_order_and_manual(self):
        run_script("update_worklog.py", ["--target", self.target, "--apply"],
                   stdin=entries({"2026-07-15": "a", "2026-07-10": "b"}))
        text = read(self.target)
        marker = "<!-- REPO_WORKLOG:2026-07-10:MANUAL:START -->\n"
        write(self.target,
            text.replace(marker, marker + "\nkeep me\n"))
        run_script("update_worklog.py", ["--target", self.target, "--apply"],
                   stdin=entries({"2026-07-12": "c"}))
        v, _, _ = run_script("validate_worklog.py", ["--target", self.target])
        self.assertEqual(v["dates"], ["2026-07-15", "2026-07-12", "2026-07-10"])
        self.assertIn("keep me", read(self.target))

    def test_refuses_corrupt_file(self):
        run_script("update_worklog.py", ["--target", self.target, "--apply"],
                   stdin=entries({"2026-07-01": "a"}))
        corrupt = read(self.target).replace(
            "<!-- REPO_WORKLOG:ENTRIES:END -->",
            "<!-- REPO_WORKLOG:2026-07-01:START -->\n## 2026-07-01\n"
            "<!-- REPO_WORKLOG:2026-07-01:GENERATED:START -->\ndup\n"
            "<!-- REPO_WORKLOG:2026-07-01:GENERATED:END -->\n"
            "<!-- REPO_WORKLOG:2026-07-01:MANUAL:START -->\n"
            "<!-- REPO_WORKLOG:2026-07-01:MANUAL:END -->\n"
            "<!-- REPO_WORKLOG:2026-07-01:END -->\n<!-- REPO_WORKLOG:ENTRIES:END -->")
        write(self.target,corrupt)
        v, rc, _ = run_script("validate_worklog.py", ["--target", self.target])
        self.assertEqual(rc, 2)
        self.assertIn("DUPLICATE_DATE", [e["code"] for e in v["errors"]])
        d, _, _ = run_script("update_worklog.py", ["--target", self.target],
                             stdin=entries({"2026-07-01": "z"}))
        self.assertFalse(d["ok"])
        self.assertEqual(d["errors"][0]["code"], "CORRUPT_MARKERS")


class TestPreviewState(unittest.TestCase):
    def setUp(self):
        # Isolate ~/.repo_worklog under a temp HOME so tests never touch the real home.
        self.home = tempfile.mkdtemp(prefix="rw_home_")
        self.env = {"HOME": self.home}
        self.fp = {
            "repository": {"root": "/repo", "branch": "main", "head": "abc123",
                           "worktree_fingerprint": "wtf-1"},
            "worklog": {"original_sha256": "orig-1", "preview_sha256": "prev-deadbeef"},
            "params": {"mode": "days", "timezone": "Asia/Taipei", "include_uncommitted": False},
        }

    def tearDown(self):
        rmtree(self.home)

    def _create(self):
        d, _, _ = run_script("preview_state.py",
                             ["create", "--now", "2026-07-15T12:00:00+08:00"],
                             stdin=json.dumps(self.fp), env=self.env)
        return d["preview_id"]

    def test_id_format(self):
        pid = self._create()
        self.assertTrue(pid.startswith("rw-20260715-"))

    def test_consistent_verify(self):
        pid = self._create()
        state = {"repository": self.fp["repository"],
                 "worklog": {"original_sha256": "orig-1"},
                 "params": {"include_uncommitted": False}}
        d, rc, _ = run_script("preview_state.py",
                             ["verify", "--id", pid, "--now", "2026-07-15T12:05:00+08:00"],
                             stdin=json.dumps(state), env=self.env)
        self.assertTrue(d["consistent"])
        self.assertEqual(rc, 0)

    def test_head_change_blocks(self):
        pid = self._create()
        state = {"repository": {**self.fp["repository"], "head": "zzz"},
                 "worklog": {"original_sha256": "orig-1"},
                 "params": {"include_uncommitted": False}}
        d, rc, _ = run_script("preview_state.py",
                             ["verify", "--id", pid, "--now", "2026-07-15T12:05:00+08:00"],
                             stdin=json.dumps(state), env=self.env)
        self.assertFalse(d["consistent"])
        self.assertEqual(rc, 3)
        self.assertTrue(any(m["field"] == "HEAD" for m in d["mismatches"]))

    def test_expired_blocks(self):
        pid = self._create()
        state = {"repository": self.fp["repository"],
                 "worklog": {"original_sha256": "orig-1"},
                 "params": {"include_uncommitted": False}}
        d, rc, _ = run_script("preview_state.py",
                             ["verify", "--id", pid, "--now", "2026-07-17T13:00:00+08:00"],
                             stdin=json.dumps(state), env=self.env)
        self.assertTrue(d["expired"])
        self.assertEqual(rc, 3)

    def test_double_apply_blocked(self):
        pid = self._create()
        state = {"repository": self.fp["repository"],
                 "worklog": {"original_sha256": "orig-1"},
                 "params": {"include_uncommitted": False}}
        run_script("preview_state.py",
                   ["verify", "--id", pid, "--mark-applied", "--now", "2026-07-15T12:05:00+08:00"],
                   stdin=json.dumps(state), env=self.env)
        d, rc, _ = run_script("preview_state.py",
                             ["verify", "--id", pid, "--now", "2026-07-15T12:06:00+08:00"],
                             stdin=json.dumps(state), env=self.env)
        self.assertTrue(d["already_applied"])
        self.assertEqual(rc, 3)

    def test_unknown_preview(self):
        d, rc, _ = run_script("preview_state.py",
                             ["verify", "--id", "rw-20260715-nope00"],
                             stdin=json.dumps(self.fp), env=self.env)
        self.assertFalse(d["ok"])
        self.assertEqual(d["errors"][0]["code"], "UNKNOWN_PREVIEW")


if __name__ == "__main__":
    unittest.main()
