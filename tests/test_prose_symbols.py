"""Tests for prose-symbol verification: results.cited_symbols / validate_prose /
Tree.day_scope / Tree.names_anything (issues #19, #36).

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
from unittest import mock

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


class TestDayScopeAndGrep(unittest.TestCase):
    """Tree.day_scope picks the snapshots to search, and names_anything asks the
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

    def test_day_scope_covers_every_state_the_day_passed_through(self):
        scope = self.tree.day_scope([self.c1, self.c2])
        self.assertFalse(scope["truncated"])
        # The day's own commits, in order, preceded by the state it started
        # from. Not "first and last": that only describes a day whose history
        # is one straight line, and assuming it is what broke this (#36).
        self.assertEqual(scope["trees"][1:], (self.c1, self.c2))
        self.assertTrue(scope["trees"][0].startswith(self.before))

    def test_a_symbol_added_during_the_day_is_found(self):
        trees = self.tree.day_scope([self.c1, self.c2])["trees"]
        self.assertTrue(self.tree.names_anything("PreviewRecord", trees))

    def test_a_symbol_removed_during_the_day_is_still_found(self):
        # parse_legacy is gone from the end tree, but the day legitimately
        # describes removing it. Checking only the end would call that a lie.
        trees = self.tree.day_scope([self.c1, self.c2])["trees"]
        self.assertTrue(self.tree.names_anything("parse_legacy", trees))

    def test_a_name_that_never_existed_is_not_found(self):
        trees = self.tree.day_scope([self.c1, self.c2])["trees"]
        self.assertFalse(self.tree.names_anything("PreviewStore", trees))

    def test_a_fabrication_is_not_masked_by_a_longer_real_name(self):
        # `Preview` is a fabrication; `PreviewRecord` is real. A fixed-string
        # substring match would find `Preview` inside it and wave the invention
        # through -- which is how a plausible-but-wrong name hides. Whole-word
        # matching is what stops it.
        trees = self.tree.day_scope([self.c1, self.c2])["trees"]
        self.assertTrue(self.tree.names_anything("PreviewRecord", trees))
        self.assertFalse(self.tree.names_anything("Preview", trees))

    def test_a_real_underscore_name_is_matched_whole(self):
        # -w must not over-tighten: an underscore is a word character, so a real
        # multi-part name is still found, and a bare fragment of it is not. The
        # existing tree already holds `_load_record`-shaped names? No -- assert
        # it against a name known to be in this fixture, `load_legacy`.
        trees = self.tree.day_scope([self.c1, self.c2])["trees"]
        self.assertTrue(self.tree.names_anything("load_legacy", trees))
        self.assertFalse(self.tree.names_anything("legacy", trees))

    def test_a_name_from_an_unchanged_file_is_found(self):
        # Prose may refer to code the day did not touch ("consistent with
        # `helper`"); searching only the day's own diff would flag it.
        trees = self.tree.day_scope([self.c1, self.c2])["trees"]
        self.assertTrue(self.tree.names_anything("helper", trees))

    def test_a_root_commit_has_no_state_before_it(self):
        # The first commit in the repo has no parent to diff against, so the
        # day is its own start.
        root = R.Tree(self.repo)
        first_ever = subprocess.run(
            ["git", "-C", self.repo, "rev-list", "--max-parents=0", "HEAD"],
            capture_output=True, text=True).stdout.strip()[:7]
        self.assertEqual(root.day_scope([first_ever])["trees"], (first_ever,))

    def test_day_scope_ignores_commits_the_repo_does_not_have(self):
        # A fabricated hash in the manifest's commit list must not crash the
        # scan; it is simply not one of the usable snapshots.
        scope = self.tree.day_scope(["deadbeef", self.c1, self.c2])
        self.assertEqual(scope["trees"][1:], (self.c1, self.c2))

    def test_no_usable_commits_means_no_trees_to_search(self):
        self.assertEqual(
            self.tree.day_scope(["deadbeef", "cafef00d"])["trees"], ())


class TestAForkedDay(unittest.TestCase):
    """A day whose commits are not one straight line (issue #36).

    Not hypothetical: a feature branch was rebased onto the day and merged the
    next morning, so the day held two tips, neither an ancestor of the other.
    The manifest orders commits by committer date, the tip of the *other* line
    took the last slot, and all 26 real symbols on the branch were reported as
    invented -- blocking a run whose analysis was entirely correct.
    """

    @classmethod
    def setUpClass(cls):
        cls.repo = tempfile.mkdtemp(prefix="rw_fork_")
        _git(cls.repo, "init", "-q", "-b", "main")
        _git(cls.repo, "config", "user.email", "t@example.com")
        _git(cls.repo, "config", "user.name", "Tester")
        _git(cls.repo, "config", "commit.gpgsign", "false")
        # The state the day starts from.
        _write(cls.repo, "src/app.py", "def shared():\n    return 1\n")
        _git(cls.repo, "add", "-A")
        _git(cls.repo, "commit", "-q", "-m", "before")
        cls.before = _short(cls.repo)
        # The day's trunk.
        _write(cls.repo, "src/app.py",
               "def shared():\n    return 1\n\n\nclass TrunkThing:\n    pass\n")
        _git(cls.repo, "add", "-A")
        _git(cls.repo, "commit", "-q", "-m", "trunk")
        cls.t1 = _short(cls.repo)
        # A branch off the trunk, landing the same day.
        _git(cls.repo, "checkout", "-q", "-b", "feature")
        _write(cls.repo, "src/feature.py", "class BranchOnly:\n    pass\n")
        _git(cls.repo, "add", "-A")
        _git(cls.repo, "commit", "-q", "-m", "branch")
        cls.b1 = _short(cls.repo)
        # Back on the trunk, committed last -- so it wins the "last" slot.
        _git(cls.repo, "checkout", "-q", "main")
        _write(cls.repo, "src/paths.py", "def trunk_tip():\n    return 2\n")
        _git(cls.repo, "add", "-A")
        _git(cls.repo, "commit", "-q", "-m", "trunk tip")
        cls.t2 = _short(cls.repo)
        # The manifest's order: committer date ascending.
        cls.day = [cls.t1, cls.b1, cls.t2]

    @classmethod
    def tearDownClass(cls):
        rmtree(cls.repo)

    def test_the_two_lines_really_do_diverge(self):
        # If this fixture were one straight line, nothing else here would prove
        # anything.
        for a, b in ((self.b1, self.t2), (self.t2, self.b1)):
            code = subprocess.run(
                ["git", "-C", self.repo, "merge-base", "--is-ancestor", a, b],
                capture_output=True).returncode
            self.assertEqual(code, 1, f"{a} must not be an ancestor of {b}")

    def test_the_old_two_tree_scope_would_have_called_it_a_fabrication(self):
        # The regression lock. The scope used to be (first^, last); on this day
        # that is the trunk alone, and `BranchOnly` is nowhere in it. Without
        # this assertion the rest of the class would pass just as well against
        # the code that shipped the bug.
        tree = R.Tree(self.repo)
        self.assertFalse(
            tree.names_anything("BranchOnly", (f"{self.t1}^", self.t2)))

    def test_a_symbol_on_the_other_line_is_found(self):
        tree = R.Tree(self.repo)
        trees = tree.day_scope(self.day)["trees"]
        for name in ("BranchOnly", "TrunkThing", "trunk_tip", "shared"):
            self.assertTrue(tree.names_anything(name, trees), name)

    def test_a_fabrication_is_still_a_fabrication(self):
        # Widening the scope must not amount to switching the check off.
        tree = R.Tree(self.repo)
        trees = tree.day_scope(self.day)["trees"]
        self.assertFalse(tree.names_anything("BranchOnlyStore", trees))

    def test_the_scope_is_the_day_plus_the_one_state_it_started_from(self):
        scope = R.Tree(self.repo).day_scope(self.day)
        self.assertFalse(scope["truncated"])
        self.assertEqual(len(scope["trees"]), 4)
        self.assertTrue(scope["trees"][0].startswith(self.before))

    def test_past_the_limit_the_scope_keeps_both_tips_not_one(self):
        tree = R.Tree(self.repo)
        with mock.patch.object(R, "MAX_DAY_TREES", 2):
            scope = tree.day_scope(self.day)
        self.assertTrue(scope["truncated"])
        # Boundary parent plus *both* tips: the old shape generalised to every
        # line rather than assuming there is one, so even a day too large to
        # search in full still sees the branch.
        self.assertEqual(len(scope["trees"]), 3)
        self.assertTrue(tree.names_anything("BranchOnly", scope["trees"]))

    def test_a_narrowed_scope_is_reported_and_never_silent(self):
        # A check that quietly stopped looking is how this began.
        with mock.patch.object(R, "MAX_DAY_TREES", 2):
            issues = R.validate({"date": "2026-08-27"}, "2026-08-27",
                                tree=R.Tree(self.repo), commits=self.day)
        note = [i for i in issues if i["code"] == "PROSE_SCOPE_TRUNCATED"]
        self.assertEqual([i["severity"] for i in note], ["unverified"])

    def test_a_fabrication_still_fails_the_day(self):
        issues = R.validate(
            {"date": "2026-08-27",
             "work_items": [{"implementation": "stores it in `BranchOnlyStore`"}]},
            "2026-08-27", tree=R.Tree(self.repo), commits=self.day)
        bad = [i for i in issues if i["code"] == "PROSE_SYMBOL_NOT_FOUND"]
        self.assertEqual([i["severity"] for i in bad], ["blocking"])

    def test_priming_agrees_with_asking_one_token_at_a_time(self):
        tokens = ["BranchOnly", "TrunkThing", "trunk_tip", "NeverExisted"]
        singly = R.Tree(self.repo)
        trees = singly.day_scope(self.day)["trees"]
        one_at_a_time = {t: singly.names_anything(t, trees) for t in tokens}
        primed = R.Tree(self.repo)
        primed.prime(tokens, trees)
        self.assertEqual({t: primed.names_anything(t, trees) for t in tokens},
                         one_at_a_time)
        self.assertEqual(one_at_a_time,
                         {"BranchOnly": True, "TrunkThing": True,
                          "trunk_tip": True, "NeverExisted": False})

    def test_a_grep_git_refuses_is_not_recorded_as_absence(self):
        # Caching "absent" from a refused invocation would turn one bad call
        # into a page of fabrication reports against real code.
        tree = R.Tree(self.repo)
        tree.prime(["TrunkThing"], ("no-such-tree-object",))
        self.assertEqual(tree._greps, {})


class TestASymbolThatOnlyExistedMidDay(unittest.TestCase):
    """Created and deleted inside one day: the hole this used to accept.

    The old scope documented it as "rare enough to accept" -- and then a real
    day did it, leaving a flag that no re-analysis could clear, because the
    name it doubted was correct.
    """

    @classmethod
    def setUpClass(cls):
        cls.repo = tempfile.mkdtemp(prefix="rw_midday_")
        _git(cls.repo, "init", "-q", "-b", "main")
        _git(cls.repo, "config", "user.email", "t@example.com")
        _git(cls.repo, "config", "user.name", "Tester")
        _git(cls.repo, "config", "commit.gpgsign", "false")
        _write(cls.repo, "src/app.py", "def shared():\n    return 1\n")
        _git(cls.repo, "add", "-A")
        _git(cls.repo, "commit", "-q", "-m", "before")
        _write(cls.repo, "src/app.py",
               "def shared():\n    return 1\n\n\ndef mirror_state():\n    return 2\n")
        _git(cls.repo, "add", "-A")
        _git(cls.repo, "commit", "-q", "-m", "add it")
        cls.c1 = _short(cls.repo)
        _write(cls.repo, "src/app.py", "def shared():\n    return 1\n")
        _git(cls.repo, "add", "-A")
        _git(cls.repo, "commit", "-q", "-m", "take it out again")
        cls.c2 = _short(cls.repo)

    @classmethod
    def tearDownClass(cls):
        rmtree(cls.repo)

    def test_the_old_two_tree_scope_would_have_missed_it(self):
        tree = R.Tree(self.repo)
        self.assertFalse(
            tree.names_anything("mirror_state", (f"{self.c1}^", self.c2)))

    def test_the_middle_state_is_searched(self):
        tree = R.Tree(self.repo)
        trees = tree.day_scope([self.c1, self.c2])["trees"]
        self.assertTrue(tree.names_anything("mirror_state", trees))


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
        trees = tree.day_scope([self.commit])["trees"]
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
