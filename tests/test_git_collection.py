"""Tests for collect_git_history.py, inspect_worktree.py, build_analysis_manifest.py."""

from __future__ import annotations

import json
import os
import subprocess
import unittest

from helpers import make_empty_repo, make_history_repo, run_script, rmtree

DAY_10 = ["--since", "2026-07-10T00:00:00+08:00", "--until", "2026-07-11T00:00:00+08:00"]
DAY_12 = ["--since", "2026-07-12T00:00:00+08:00", "--until", "2026-07-13T00:00:00+08:00"]
DAY_02 = ["--since", "2026-07-02T00:00:00+08:00", "--until", "2026-07-03T00:00:00+08:00"]


class TestCollectGitHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = make_history_repo()

    @classmethod
    def tearDownClass(cls):
        rmtree(cls.repo)

    def test_info_only(self):
        d, _, _ = run_script("collect_git_history.py", ["--repo", self.repo, "--info-only"])
        r = d["repository"]
        self.assertEqual(r["branch"], "main")
        self.assertTrue(r["has_commits"])
        self.assertFalse(r["detached_head"])
        self.assertFalse(r["dirty_worktree"])

    def test_not_a_git_repo(self):
        import tempfile
        tmp = tempfile.mkdtemp(prefix="rw_notgit_")
        try:
            d, rc, _ = run_script("collect_git_history.py", ["--repo", tmp, "--info-only"])
            self.assertFalse(d["ok"])
            self.assertEqual(d["errors"][0]["code"], "NOT_A_GIT_REPO")
        finally:
            rmtree(tmp)

    def test_multi_commit_day_with_revert(self):
        d, _, _ = run_script("collect_git_history.py", ["--repo", self.repo, *DAY_10])
        self.assertEqual(d["commit_count"], 3)
        subjects = [c["subject"] for c in d["commits"]]
        self.assertEqual(subjects,
                         ["feat: add cache layer", "fix: correct cache key name",
                          "revert: drop cache layer"])
        # Commits are ordered ascending by committer date within the day.
        revert = d["commits"][-1]
        self.assertTrue(revert["is_revert_candidate"])
        self.assertEqual(revert["files"][0]["status"], "D")
        self.assertEqual(revert["files"][0]["path"], "src/cache.py")

    def test_final_state_shows_add_then_delete(self):
        # The whole day: cache.py is A then M then D -> net removed.
        d, _, _ = run_script("collect_git_history.py", ["--repo", self.repo, *DAY_10])
        statuses = [c["files"][0]["status"] for c in d["commits"]]
        self.assertEqual(statuses, ["A", "M", "D"])

    def test_rename_detected(self):
        d, _, _ = run_script("collect_git_history.py", ["--repo", self.repo, *DAY_12])
        files = {f["path"]: f for c in d["commits"] for f in c["files"]}
        renamed = files["src/math_utils.py"]
        self.assertEqual(renamed["status"], "R")
        self.assertEqual(renamed["old_path"], "src/calc.py")
        self.assertEqual(renamed["similarity"], 100)

    def test_binary_detected(self):
        d, _, _ = run_script("collect_git_history.py", ["--repo", self.repo, *DAY_12])
        files = {f["path"]: f for c in d["commits"] for f in c["files"]}
        logo = files["assets/logo.png"]
        self.assertTrue(logo["is_binary"])
        self.assertIsNone(logo["additions"])
        self.assertIsNone(logo["deletions"])

    def test_empty_day_returns_no_commits(self):
        d, _, _ = run_script("collect_git_history.py", ["--repo", self.repo, *DAY_02])
        self.assertTrue(d["ok"])
        self.assertEqual(d["commit_count"], 0)

    def test_empty_repo(self):
        repo = make_empty_repo()
        try:
            info, _, _ = run_script("collect_git_history.py", ["--repo", repo, "--info-only"])
            self.assertFalse(info["repository"]["has_commits"])
            d, _, _ = run_script("collect_git_history.py", ["--repo", repo, *DAY_10])
            self.assertTrue(d["ok"])
            self.assertEqual(d["commits"], [])
        finally:
            rmtree(repo)


class TestInspectWorktree(unittest.TestCase):
    def test_classifies_and_fingerprints(self):
        repo = make_history_repo()
        try:
            # staged change
            with open(os.path.join(repo, "src", "math_utils.py"), "w") as f:
                f.write("def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n")
            subprocess.run(["git", "-C", repo, "add", "src/math_utils.py"], check=True)
            # unstaged change on top
            with open(os.path.join(repo, "src", "math_utils.py"), "a") as f:
                f.write("\ndef mul(a, b):\n    return a * b\n")
            # untracked text + binary
            with open(os.path.join(repo, "NOTES.txt"), "w") as f:
                f.write("todo\n")
            with open(os.path.join(repo, "data.bin"), "wb") as f:
                f.write(b"\x00\x01binary\xff")

            d, _, _ = run_script("inspect_worktree.py", ["--repo", repo])
            self.assertTrue(d["has_uncommitted"])
            self.assertEqual([f["path"] for f in d["staged"]], ["src/math_utils.py"])
            self.assertEqual([f["path"] for f in d["unstaged"]], ["src/math_utils.py"])
            untracked = {f["path"]: f["is_binary"] for f in d["untracked"]}
            self.assertFalse(untracked["NOTES.txt"])
            self.assertTrue(untracked["data.bin"])

            # Fingerprint is stable across identical states.
            d2, _, _ = run_script("inspect_worktree.py", ["--repo", repo])
            self.assertEqual(d["worktree_fingerprint"], d2["worktree_fingerprint"])
        finally:
            rmtree(repo)

    def test_fingerprint_changes_with_content(self):
        repo = make_history_repo()
        try:
            a, _, _ = run_script("inspect_worktree.py", ["--repo", repo])
            with open(os.path.join(repo, "new.txt"), "w") as f:
                f.write("x\n")
            b, _, _ = run_script("inspect_worktree.py", ["--repo", repo])
            self.assertNotEqual(a["worktree_fingerprint"], b["worktree_fingerprint"])
        finally:
            rmtree(repo)


class TestBuildManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = make_history_repo()

    @classmethod
    def tearDownClass(cls):
        rmtree(cls.repo)

    def _manifest(self, day_window, date):
        hist, _, _ = run_script("collect_git_history.py", ["--repo", self.repo, *day_window])
        man, rc, err = run_script(
            "build_analysis_manifest.py",
            ["--date", date, "--timezone", "Asia/Taipei"],
            stdin=json.dumps(hist),
        )
        self.assertTrue(man["ok"], err)
        return man

    def test_groups_and_default_provider(self):
        man = self._manifest(DAY_10, "2026-07-10")
        self.assertEqual(man["provider"], "anthropic")  # unified vendor default
        self.assertTrue(man["has_changes"])
        cache = [f for f in man["changed_files"] if f["path"] == "src/cache.py"][0]
        self.assertEqual(cache["category"], "backend")
        self.assertEqual(sorted(cache["statuses"]), ["A", "D", "M"])

    def test_binary_grouped_separately(self):
        man = self._manifest(DAY_12, "2026-07-12")
        groups = {g["group"] for g in man["file_groups"]}
        self.assertIn("other:assets/logo.png", groups)
        self.assertTrue(any(g["has_binary"] for g in man["file_groups"]))


if __name__ == "__main__":
    unittest.main()
