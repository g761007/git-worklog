"""Integration test: the deterministic script pipeline the skill runs end to end.

resolve_date_range -> collect_git_history -> build_analysis_manifest
-> update_worklog (dry-run) -> preview_state create/verify -> update_worklog --apply
-> validate_worklog. Day summaries are synthesised (real runs get them from Day
Subagents) to exercise the JSON hand-offs between scripts.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from helpers import make_history_repo, run_script, rmtree


class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = make_history_repo()

    @classmethod
    def tearDownClass(cls):
        rmtree(cls.repo)

    def test_full_pipeline(self):
        resolved, _, _ = run_script(
            "resolve_date_range.py",
            ["--from", "2026-07-01", "--to", "2026-07-12", "--timezone", "Asia/Taipei"])
        self.assertEqual(resolved["days_count"], 12)

        info, _, _ = run_script("collect_git_history.py", ["--repo", self.repo, "--info-only"])
        self.assertTrue(info["repository"]["has_commits"])

        entries = {}
        commit_days = {}
        for day in resolved["dates"]:
            hist, _, _ = run_script("collect_git_history.py",
                                    ["--repo", self.repo,
                                     "--since", day["start"], "--until", day["end"]])
            man, rc, err = run_script(
                "build_analysis_manifest.py",
                ["--date", day["date"], "--timezone", "Asia/Taipei"],
                stdin=json.dumps(hist))
            self.assertTrue(man["ok"], err)
            if man["has_changes"]:
                commit_days[day["date"]] = man["commit_count"]
                groups = ", ".join(g["group"] for g in man["file_groups"])
                entries[day["date"]] = {
                    "generated_markdown": f"### 當日摘要\n\n{man['commit_count']} commit(s): {groups}."}

        self.assertEqual(set(commit_days), {"2026-07-01", "2026-07-10", "2026-07-12"})
        self.assertEqual(commit_days["2026-07-10"], 3)

        work = tempfile.mkdtemp(prefix="rw_pl_")
        home = tempfile.mkdtemp(prefix="rw_plhome_")
        try:
            target = os.path.join(work, "docs", "PROJECT_WORKLOG.md")
            dry, _, _ = run_script("update_worklog.py", ["--target", target],
                                   stdin=json.dumps({"entries": entries}))
            self.assertEqual(dry["mode"], "dry-run")
            self.assertEqual({p["action"] for p in dry["planned_changes"]}, {"insert"})
            self.assertFalse(os.path.isdir(os.path.dirname(target)))

            fp = {
                "repository": {"root": info["repository"]["root"],
                               "branch": info["repository"]["branch"],
                               "head": info["repository"]["head"],
                               "worktree_fingerprint": None},
                "worklog": {"original_sha256": dry["original_sha256"],
                            "preview_sha256": dry["preview_sha256"]},
                "params": {"mode": "range", "timezone": "Asia/Taipei",
                           "include_uncommitted": False},
            }
            pv, _, _ = run_script("preview_state.py",
                                  ["create", "--now", "2026-07-15T12:00:00+08:00"],
                                  stdin=json.dumps(fp), env={"HOME": home})
            pid = pv["preview_id"]

            verify_state = {"repository": fp["repository"],
                            "worklog": {"original_sha256": dry["original_sha256"]},
                            "params": {"include_uncommitted": False}}
            vr, rc, _ = run_script(
                "preview_state.py",
                ["verify", "--id", pid, "--mark-applied", "--now", "2026-07-15T12:01:00+08:00"],
                stdin=json.dumps(verify_state), env={"HOME": home})
            self.assertTrue(vr["consistent"])

            ap, _, err = run_script("update_worklog.py", ["--target", target, "--apply"],
                                    stdin=json.dumps({"entries": entries}))
            self.assertTrue(ap["ok"], err)
            self.assertEqual(ap["final_dates"], ["2026-07-12", "2026-07-10", "2026-07-01"])

            val, _, _ = run_script("validate_worklog.py", ["--target", target])
            self.assertTrue(val["ok"])
            self.assertEqual(val["errors"], [])
        finally:
            rmtree(work)
            rmtree(home)


if __name__ == "__main__":
    unittest.main()
