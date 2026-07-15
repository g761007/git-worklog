"""Tests for migrate_legacy_worklog.py: splitting the legacy single file."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from helpers import run_script, rmtree

LEGACY = """\
# Project Worklog

<!-- REPO_WORKLOG:ENTRIES:START -->

<!-- REPO_WORKLOG:2026-07-15:START -->
## 2026-07-15

<!-- REPO_WORKLOG:2026-07-15:GENERATED:START -->
### 當日摘要

新增會員搜尋快取。
<!-- REPO_WORKLOG:2026-07-15:GENERATED:END -->

<!-- REPO_WORKLOG:2026-07-15:MANUAL:START -->
issue #42：JWT 決策
<!-- REPO_WORKLOG:2026-07-15:MANUAL:END -->

<!-- REPO_WORKLOG:2026-07-15:END -->

<!-- REPO_WORKLOG:2026-07-14:START -->
## 2026-07-14

<!-- REPO_WORKLOG:2026-07-14:GENERATED:START -->
### 當日摘要

重構訂單狀態流程。
<!-- REPO_WORKLOG:2026-07-14:GENERATED:END -->

<!-- REPO_WORKLOG:2026-07-14:MANUAL:START -->

<!-- REPO_WORKLOG:2026-07-14:MANUAL:END -->

<!-- REPO_WORKLOG:2026-07-14:END -->

<!-- REPO_WORKLOG:ENTRIES:END -->
"""


class TestMigrate(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="rw_mig_")
        self.legacy = os.path.join(self.work, "docs", "PROJECT_WORKLOG.md")
        os.makedirs(os.path.dirname(self.legacy))
        Path(self.legacy).write_text(LEGACY, encoding="utf-8")
        self.dir = os.path.join(self.work, "PROJECT_WORKLOG")

    def tearDown(self):
        rmtree(self.work)

    def _run(self, *extra):
        return run_script("migrate_legacy_worklog.py",
                          ["--legacy", self.legacy, "--dir", self.dir,
                           "--timezone", "Asia/Taipei", *extra])

    def test_dry_run_writes_nothing(self):
        d, _, _ = self._run()
        self.assertEqual(d["mode"], "dry-run")
        self.assertFalse(os.path.isdir(self.dir))
        self.assertEqual([p["date"] for p in d["planned_changes"]], ["2026-07-15", "2026-07-14"])

    def test_apply_splits_and_preserves_manual_and_legacy(self):
        d, _, _ = self._run("--apply")
        self.assertEqual(sorted(d["created_dates"], reverse=True), ["2026-07-15", "2026-07-14"])
        day15 = Path(os.path.join(self.dir, "2026-07-15.md")).read_text(encoding="utf-8")
        self.assertIn("新增會員搜尋快取", day15)
        self.assertIn("issue #42：JWT 決策", day15)          # MANUAL carried over
        self.assertTrue(os.path.exists(self.legacy))         # legacy never deleted
        # Result validates under the new engine.
        vd, _, _ = run_script("validate_daily_worklog.py", ["--dir", self.dir])
        self.assertTrue(vd["ok"])
        vi, _, _ = run_script("validate_worklog_index.py", ["--dir", self.dir])
        self.assertTrue(vi["ok"])

    def test_existing_day_file_is_skipped_not_clobbered(self):
        os.makedirs(self.dir)
        run_script("update_daily_worklog.py", ["--dir", self.dir, "--apply"],
                   stdin='{"meta":{"timezone":"Asia/Taipei"},'
                         '"entries":{"2026-07-15":{"generated_markdown":"## 當日摘要\\n\\nkeep mine"}}}')
        d, _, _ = self._run("--apply")
        actions = {p["date"]: p["action"] for p in d["planned_changes"]}
        self.assertEqual(actions["2026-07-15"], "skip-exists")
        self.assertIn("keep mine",
                      Path(os.path.join(self.dir, "2026-07-15.md")).read_text(encoding="utf-8"))

    def test_corrupt_legacy_refused(self):
        Path(self.legacy).write_text(
            "<!-- REPO_WORKLOG:ENTRIES:START -->\n"
            "<!-- REPO_WORKLOG:2026-07-15:GENERATED:START -->\nx\n", encoding="utf-8")
        d, _, _ = self._run()
        self.assertFalse(d["ok"])
        self.assertEqual(d["errors"][0]["code"], "LEGACY_CORRUPT")

    def test_marker_in_legacy_generated_refused(self):
        Path(self.legacy).write_text(
            "<!-- REPO_WORKLOG:ENTRIES:START -->\n"
            "<!-- REPO_WORKLOG:2026-07-15:START -->\n## 2026-07-15\n"
            "<!-- REPO_WORKLOG:2026-07-15:GENERATED:START -->\n"
            "<!-- REPO_WORKLOG:INDEX:GENERATED:START -->\n"     # bare marker inside generated
            "<!-- REPO_WORKLOG:2026-07-15:GENERATED:END -->\n"
            "<!-- REPO_WORKLOG:2026-07-15:MANUAL:START -->\n"
            "<!-- REPO_WORKLOG:2026-07-15:MANUAL:END -->\n"
            "<!-- REPO_WORKLOG:2026-07-15:END -->\n"
            "<!-- REPO_WORKLOG:ENTRIES:END -->\n", encoding="utf-8")
        d, _, _ = self._run()
        self.assertFalse(d["ok"])
        self.assertEqual(d["errors"][0]["code"], "LEGACY_CONTAINS_MARKER")

    def test_corrupt_existing_index_refused_preserving_manual(self):
        os.makedirs(self.dir)
        Path(os.path.join(self.dir, "index.md")).write_text("corrupt, no markers\n",
                                                            encoding="utf-8")
        d, _, _ = self._run("--apply")
        self.assertFalse(d["ok"])
        self.assertEqual(d["errors"][0]["code"], "INDEX_CORRUPT_MARKERS")


if __name__ == "__main__":
    unittest.main()
