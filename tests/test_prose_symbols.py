"""Tests for prose-symbol verification: results.cited_symbols / validate_prose /
Tree.day_trees / Tree.names_anything (issue #19).

The worklog is written from the prose fields, and until now nothing checked
them: `evidence[]` was verified against the tree while `implementation` was free
to name `PreviewStore` and `read_config()`, and a real subagent did exactly that
(#19, #22). These tests are written against the question the check answers — "is
this a name the project actually has?" — not against its return shape, so each
fails if a fabricated name could slip through or a real one be flagged.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest

from helpers import SKILL_ROOT, _git, _write, rmtree

sys.path.insert(0, SKILL_ROOT)

from git_worklog.analysis import results as R  # noqa: E402


def _short(repo: str, ref: str = "HEAD") -> str:
    return subprocess.run(["git", "-C", repo, "rev-parse", "--short", ref],
                          capture_output=True, text=True).stdout.strip()


class TestCitedSymbols(unittest.TestCase):
    """What counts as a symbol in prose. Being strict here is what keeps the
    check quiet enough that a warning from it means something."""

    def test_a_plain_identifier_span_is_a_symbol(self):
        self.assertEqual(R.cited_symbols("renamed `PreviewStore` for clarity"),
                         ["PreviewStore"])

    def test_a_trailing_call_is_stripped(self):
        self.assertEqual(R.cited_symbols("calls `read_config()` on load"),
                         ["read_config"])

    def test_a_dotted_name_yields_its_parts(self):
        # `Tree.file_at` holds two checkable tokens; the qualified string never
        # appears verbatim in source, so it is split like a `symbol` field is.
        self.assertEqual(R.cited_symbols("see `Tree.file_at` above"),
                         ["Tree", "file_at"])

    def test_a_path_is_not_a_symbol(self):
        self.assertEqual(R.cited_symbols("under `.git-worklog/days/` now"), [])

    def test_a_flag_is_not_a_symbol(self):
        self.assertEqual(R.cited_symbols("pass `--language en` to it"), [])

    def test_a_language_tag_is_not_a_symbol(self):
        self.assertEqual(R.cited_symbols("written in `zh-TW`"), [])

    def test_prose_without_code_spans_yields_nothing(self):
        self.assertEqual(R.cited_symbols("a plain sentence, no code"), [])

    def test_each_token_is_returned_once_in_order(self):
        self.assertEqual(
            R.cited_symbols("`load` then `inspect` then `load` again"),
            ["load", "inspect"])


class TestDayTreesAndGrep(unittest.TestCase):
    """Tree.day_trees picks the right two snapshots, and names_anything asks the
    project-wide question prose (which names no file) can actually answer."""

    @classmethod
    def setUpClass(cls):
        cls.repo = tempfile.mkdtemp(prefix="rw_prose_")
        _git(cls.repo, "init", "-q", "-b", "main")
        _git(cls.repo, "config", "user.email", "t@example.com")
        _git(cls.repo, "config", "user.name", "Tester")
        _git(cls.repo, "config", "commit.gpgsign", "false")
        # Commit 0: the day starts here. parse_legacy exists.
        _write(cls.repo, "src/migrate.py",
               "def parse_legacy(path):\n    return open(path).read()\n")
        _write(cls.repo, "src/util.py", "def helper():\n    return 1\n")
        _git(cls.repo, "add", "-A")
        _git(cls.repo, "commit", "-q", "-m", "before")
        cls.before = _short(cls.repo)
        # The day's two commits: rename parse_legacy -> load_legacy, add a symbol.
        _write(cls.repo, "src/migrate.py",
               "def load_legacy(path):\n    return open(path).read()\n")
        _git(cls.repo, "add", "-A")
        _git(cls.repo, "commit", "-q", "-m", "rename")
        cls.c1 = _short(cls.repo)
        _write(cls.repo, "src/store.py",
               "class PreviewRecord:\n    pass\n")
        _git(cls.repo, "add", "-A")
        _git(cls.repo, "commit", "-q", "-m", "add store")
        cls.c2 = _short(cls.repo)

    @classmethod
    def tearDownClass(cls):
        rmtree(cls.repo)

    def setUp(self):
        self.tree = R.Tree(self.repo)

    def test_day_trees_span_start_state_to_end_state(self):
        trees = self.tree.day_trees([self.c1, self.c2])
        # first^ (the day's start) and the last commit (its end).
        self.assertEqual(trees, (f"{self.c1}^", self.c2))

    def test_a_symbol_added_during_the_day_is_found(self):
        trees = self.tree.day_trees([self.c1, self.c2])
        self.assertTrue(self.tree.names_anything("PreviewRecord", trees))

    def test_a_symbol_removed_during_the_day_is_still_found(self):
        # parse_legacy is gone from the end tree, but the day legitimately
        # describes removing it. Checking only the end would call that a lie.
        trees = self.tree.day_trees([self.c1, self.c2])
        self.assertTrue(self.tree.names_anything("parse_legacy", trees))

    def test_a_name_that_never_existed_is_not_found(self):
        trees = self.tree.day_trees([self.c1, self.c2])
        self.assertFalse(self.tree.names_anything("PreviewStore", trees))

    def test_a_fabrication_is_not_masked_by_a_longer_real_name(self):
        # `Preview` is a fabrication; `PreviewRecord` is real. A fixed-string
        # substring match would find `Preview` inside it and wave the invention
        # through -- which is how a plausible-but-wrong name hides. Whole-word
        # matching is what stops it.
        trees = self.tree.day_trees([self.c1, self.c2])
        self.assertTrue(self.tree.names_anything("PreviewRecord", trees))
        self.assertFalse(self.tree.names_anything("Preview", trees))

    def test_a_real_underscore_name_is_matched_whole(self):
        # -w must not over-tighten: an underscore is a word character, so a real
        # multi-part name is still found, and a bare fragment of it is not. The
        # existing tree already holds `_load_record`-shaped names? No -- assert
        # it against a name known to be in this fixture, `load_legacy`.
        trees = self.tree.day_trees([self.c1, self.c2])
        self.assertTrue(self.tree.names_anything("load_legacy", trees))
        self.assertFalse(self.tree.names_anything("legacy", trees))

    def test_a_name_from_an_unchanged_file_is_found(self):
        # Prose may refer to code the day did not touch ("consistent with
        # `helper`"); searching only the day's own diff would flag it.
        trees = self.tree.day_trees([self.c1, self.c2])
        self.assertTrue(self.tree.names_anything("helper", trees))

    def test_day_trees_of_a_root_commit_is_just_its_end(self):
        # The first commit in the repo has no parent to diff against.
        root = R.Tree(self.repo)
        first_ever = subprocess.run(
            ["git", "-C", self.repo, "rev-list", "--max-parents=0", "HEAD"],
            capture_output=True, text=True).stdout.strip()[:7]
        self.assertEqual(root.day_trees([first_ever]), (first_ever,))

    def test_day_trees_ignores_commits_the_repo_does_not_have(self):
        # A fabricated hash in the manifest's commit list must not crash the
        # scan; it is simply not one of the usable snapshots.
        trees = self.tree.day_trees(["deadbeef", self.c1, self.c2])
        self.assertEqual(trees, (f"{self.c1}^", self.c2))

    def test_no_usable_commits_means_no_trees_to_search(self):
        self.assertEqual(self.tree.day_trees(["deadbeef", "cafef00d"]), ())


class TestValidateProse(unittest.TestCase):
    """The whole check, over a work_item, against a real day."""

    @classmethod
    def setUpClass(cls):
        cls.repo = tempfile.mkdtemp(prefix="rw_prosev_")
        _git(cls.repo, "init", "-q", "-b", "main")
        _git(cls.repo, "config", "user.email", "t@example.com")
        _git(cls.repo, "config", "user.name", "Tester")
        _git(cls.repo, "config", "commit.gpgsign", "false")
        _write(cls.repo, "src/cache.py",
               "class CacheLayer:\n    def get(self, key):\n        return key\n")
        _git(cls.repo, "add", "-A")
        _git(cls.repo, "commit", "-q", "-m", "add cache")
        cls.commit = _short(cls.repo)

    @classmethod
    def tearDownClass(cls):
        rmtree(cls.repo)

    def _check(self, item):
        tree = R.Tree(self.repo)
        trees = tree.day_trees([self.commit])
        return R.validate_prose(item, R.PROSE_KEYS, "work_items[0]", tree, trees)

    def test_prose_naming_real_code_passes(self):
        issues = self._check({"implementation": "extends `CacheLayer`",
                              "summary": "adds a `get` path"})
        self.assertEqual(issues, [])

    def test_a_fabricated_symbol_in_implementation_is_caught(self):
        issues = self._check({"implementation": "stores it in `PreviewStore`"})
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["code"], "PROSE_SYMBOL_NOT_FOUND")
        self.assertEqual(issues[0]["symbol"], "PreviewStore")

    def test_a_fabricated_symbol_in_any_prose_field_is_caught(self):
        # The worklog is written from all of these, so all of them are checked.
        for field in R.PROSE_KEYS:
            with self.subTest(field=field):
                issues = self._check({field: "touched `NonexistentThing` here"})
                self.assertEqual([i["symbol"] for i in issues], ["NonexistentThing"])

    def test_without_a_tree_the_check_is_skipped_not_failed(self):
        # A caller with no manifest cannot know the day's commits, so it must not
        # pretend to check — the same stance validate() takes on coverage.
        self.assertEqual(
            R.validate_prose({"implementation": "`PreviewStore`"},
                             R.PROSE_KEYS, "w", None, ()), [])

    def test_prose_fields_that_are_lists_are_checked(self):
        # follow_ups / risks / maintenance_notes are arrays of strings.
        issues = self._check({"follow_ups": ["revisit `CacheLayer`",
                                             "delete `GhostClass`"]})
        self.assertEqual([i["symbol"] for i in issues], ["GhostClass"])


if __name__ == "__main__":
    unittest.main()
