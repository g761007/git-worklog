"""Tests for ref-scope reconciliation: analysis/reconcile.py.

The unit under test decides what a release report is allowed to describe, so
these tests are written against that question rather than against the return
shape: each one should fail if a report could go wrong in the way it names.
"""

from __future__ import annotations

import os
import sys
import unittest
from zoneinfo import ZoneInfo

from helpers import SKILL_ROOT, day_file, make_tagged_repo, rmtree, wm

sys.path.insert(0, SKILL_ROOT)

from git_worklog.analysis import reconcile as rc  # noqa: E402
from git_worklog.analysis import refs as refs_engine  # noqa: E402

TPE = "Asia/Taipei"


def _write_day(worklog_dir: str, date: str, generated: str) -> None:
    path = day_file(worklog_dir, date)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(wm.render_new_day_file(date, generated, timezone=TPE,
                                        branch="main", head="0" * 40))


class TestReconcile(unittest.TestCase):
    """v1.0.1 spans 2026-09-02..03. v1.0.0's commit and the untagged 09-05
    commit are outside it -- the two things a report on v1.0.1 must not describe.
    """

    @classmethod
    def setUpClass(cls):
        cls.repo = make_tagged_repo()
        cls.worklog = os.path.join(cls.repo, ".git-worklog")
        r = refs_engine.resolve(repo=cls.repo, tag="v1.0.1", timezone=TPE)
        cls.commits = r["commits"]
        cls.dates = r["dates"]
        by_subject = {c["subject"]: c for c in cls.commits}
        cls.search = by_subject["feat: add search"]
        cls.fix = by_subject["fix: search off-by-one"]
        # The two commits outside the v1.0.1 range.
        cls.core = refs_engine.resolve(repo=cls.repo, tag="v1.0.0",
                                       timezone=TPE)["commits"][0]
        cls.chore = refs_engine.collect_range(
            cls.repo, "v1.0.1", "main", ZoneInfo(TPE), "committer")[0]
        # Short hashes get used in nearly every line below; naming them keeps the
        # day-file bodies readable as the prose a subagent would actually write.
        cls.h_search = cls.search["short_hash"]
        cls.h_fix = cls.fix["short_hash"]
        cls.h_core = cls.core["short_hash"]
        cls.h_chore = cls.chore["short_hash"]

    @classmethod
    def tearDownClass(cls):
        rmtree(cls.repo)

    def _run(self):
        return rc.reconcile(self.repo, self.worklog, self.commits, self.dates)

    def test_day_files_citing_only_the_range_reconcile_clean(self):
        _write_day(self.worklog, "2026-09-02",
                   f"- **相關 commits：** {self.h_search} (Bob Lin) 新增搜尋")
        _write_day(self.worklog, "2026-09-03",
                   f"- **相關 commits：** {self.h_fix} (Alice Chen) 修正 off-by-one")
        r = self._run()
        self.assertEqual(r["out_of_range"], [])
        self.assertEqual(r["unbacked"], [])
        self.assertTrue(r["clean"])
        self.assertEqual(r["backed_count"], 2)

    def test_a_commit_from_another_release_is_flagged_as_out_of_range(self):
        # The whole point: a day file describes everything committed that day,
        # so a report on v1.0.1 must be told which citations belong to v1.0.0.
        _write_day(self.worklog, "2026-09-02",
                   f"- {self.h_search} 新增搜尋\n"
                   f"- {self.h_core} 這是 v1.0.0 的工作,不該進 v1.0.1")
        _write_day(self.worklog, "2026-09-03", f"- {self.h_fix} 修正")
        r = self._run()
        self.assertEqual([c["short_hash"] for c in r["out_of_range"]],
                         [self.h_core])
        self.assertEqual(r["out_of_range"][0]["subject"], "feat: add core")
        self.assertEqual(r["out_of_range"][0]["cited_on"], ["2026-09-02"])
        self.assertFalse(r["clean"])

    def test_work_landed_after_the_tag_is_flagged_as_out_of_range(self):
        # The other direction of over-inclusion: a tag cut at midday, with the
        # afternoon's commits sharing the day file.
        _write_day(self.worklog, "2026-09-02", f"- {self.h_search} 新增搜尋")
        _write_day(self.worklog, "2026-09-03",
                   f"- {self.h_fix} 修正\n"
                   f"- {self.h_chore} tag 之後才進來的整理")
        r = self._run()
        self.assertEqual([c["subject"] for c in r["out_of_range"]],
                         ["chore: tidy imports"])

    def test_a_range_commit_no_day_file_mentions_is_unbacked(self):
        # 'covered' means the day has a file, not that the file describes your
        # commit. A release report must not claim to have analysed this one.
        _write_day(self.worklog, "2026-09-02", f"- {self.h_search} 新增搜尋")
        _write_day(self.worklog, "2026-09-03", "- 今天沒提到任何 commit")
        r = self._run()
        self.assertEqual([c["short_hash"] for c in r["unbacked"]],
                         [self.h_fix])
        self.assertFalse(r["clean"])

    def test_a_missing_day_file_leaves_its_commits_unbacked(self):
        _write_day(self.worklog, "2026-09-02", f"- {self.h_search} 新增搜尋")
        path = day_file(self.worklog, "2026-09-03")
        if os.path.isfile(path):
            os.remove(path)
        r = self._run()
        self.assertEqual([c["short_hash"] for c in r["unbacked"]],
                         [self.h_fix])

    def test_reconciliation_does_not_depend_on_the_day_files_language(self):
        # The `相關 commits` label is zh-TW; §6.2 lets a day file be written in
        # any language. Keying off the label would find zero hashes here and
        # report a clean reconciliation -- a check that passes because it looked
        # at nothing. This is the index-summary bug of PR 4, one module over.
        _write_day(self.worklog, "2026-09-02",
                   f"- **Related commits:** {self.h_search} (Bob Lin) add search\n"
                   f"- **Related commits:** {self.h_core} (Alice) v1.0.0's work")
        _write_day(self.worklog, "2026-09-03",
                   f"- **Related commits:** {self.h_fix} (Alice Chen) fix off-by-one")
        r = self._run()
        self.assertEqual(r["backed_count"], 2)
        self.assertEqual([c["short_hash"] for c in r["out_of_range"]],
                         [self.h_core])

    def test_the_files_own_head_metadata_is_not_a_citation(self):
        # render_new_day_file stamps `> HEAD：<hash>` above the GENERATED region.
        # Reading the whole file would report the repo's own HEAD as out-of-range
        # work on every single day.
        head = rc._batch_resolve(self.repo, ["HEAD"])  # the real HEAD sha
        real_head = list(head.values())[0] if head else None
        self.assertIsNotNone(real_head)
        path = day_file(self.worklog, "2026-09-02")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(wm.render_new_day_file(
                "2026-09-02", f"- {self.h_search} 新增搜尋",
                timezone=TPE, branch="main", head=real_head))
        _write_day(self.worklog, "2026-09-03", f"- {self.h_fix} 修正")
        r = self._run()
        self.assertEqual(r["out_of_range"], [])
        self.assertTrue(r["clean"])

    def test_a_full_length_hash_reconciles_like_a_short_one(self):
        _write_day(self.worklog, "2026-09-02", f"- {self.search['full_hash']} 新增搜尋")
        _write_day(self.worklog, "2026-09-03", f"- {self.fix['full_hash']} 修正")
        r = self._run()
        self.assertTrue(r["clean"])
        self.assertEqual(r["backed_count"], 2)

    def test_an_uppercase_hash_still_reconciles(self):
        # Missing a real hash would under-report out-of-range work, which is the
        # failure this module exists to prevent. Worth the prose false positives.
        _write_day(self.worklog, "2026-09-02", f"- {self.h_search.upper()} 新增搜尋")
        _write_day(self.worklog, "2026-09-03",
                   f"- {self.h_fix} 修正\n"
                   f"- {self.h_core.upper()} v1.0.0 的工作")
        r = self._run()
        self.assertEqual(r["backed_count"], 2)
        self.assertEqual([c["short_hash"] for c in r["out_of_range"]],
                         [self.h_core])

    def test_a_hash_naming_no_commit_here_is_unresolved_not_out_of_range(self):
        # A fabricated or rebased-away hash is not evidence of over-inclusion;
        # saying it is would send the user hunting for a release that never
        # contained it.
        _write_day(self.worklog, "2026-09-02",
                   f"- {self.h_search} 新增搜尋\n- deadbeef1234 這個 commit 不存在")
        _write_day(self.worklog, "2026-09-03", f"- {self.h_fix} 修正")
        r = self._run()
        self.assertEqual(r["out_of_range"], [])
        self.assertEqual([u["hash"] for u in r["unresolved"]], ["deadbeef1234"])
        self.assertEqual(r["unresolved"][0]["cited_on"], ["2026-09-02"])

    def test_the_manual_region_is_not_reconciled(self):
        # MANUAL is a human's own note, never analysis material, and is never
        # translated or rewritten. A note pointing at another release's commit
        # is not the model over-including.
        _write_day(self.worklog, "2026-09-02", f"- {self.h_search} 新增搜尋")
        path = day_file(self.worklog, "2026-09-03")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(wm.build_day_file(
                "2026-09-03", f"- {self.h_fix} 修正",
                manual_inner=f"\n手動註記:參考 {self.h_core}\n",
                timezone=TPE, branch="main"))
        r = self._run()
        self.assertEqual(r["out_of_range"], [])
        self.assertTrue(r["clean"])


class TestAmbiguousCitation(unittest.TestCase):
    """A citation that names several of the range's commits names none of them.

    Crediting all of them would let a release report claim analysis exists for a
    commit nothing described — `unbacked` is the list that stops exactly that, so
    over-crediting is the one direction this must not fail in. Git cannot be made
    to produce a short-hash collision on demand, but `commits` is an argument, so
    the case is reachable directly.
    """

    @classmethod
    def setUpClass(cls):
        cls.repo = make_tagged_repo()
        cls.worklog = os.path.join(cls.repo, ".git-worklog")

    @classmethod
    def tearDownClass(cls):
        rmtree(cls.repo)

    def test_a_prefix_naming_two_range_commits_backs_neither(self):
        commits = [
            {"full_hash": "aaaaaaa" + "1" * 33, "short_hash": "aaaaaaa1",
             "author_name": "Alice Chen", "subject": "feat: one", "date": "2026-09-02"},
            {"full_hash": "aaaaaaa" + "2" * 33, "short_hash": "aaaaaaa2",
             "author_name": "Bob Lin", "subject": "feat: two", "date": "2026-09-02"},
        ]
        _write_day(self.worklog, "2026-09-02", "- aaaaaaa 這是哪一個?")
        r = rc.reconcile(self.repo, self.worklog, commits, ["2026-09-02"])
        self.assertEqual(r["backed"], [])
        self.assertEqual([c["subject"] for c in r["unbacked"]],
                         ["feat: one", "feat: two"])
        self.assertEqual([u["hash"] for u in r["unresolved"]], ["aaaaaaa"])
        self.assertFalse(r["clean"])

    def test_an_unambiguous_prefix_of_the_same_pair_still_backs_its_commit(self):
        # The guard must not cost precision: one more character resolves it.
        commits = [
            {"full_hash": "aaaaaaa" + "1" * 33, "short_hash": "aaaaaaa1",
             "author_name": "Alice Chen", "subject": "feat: one", "date": "2026-09-02"},
            {"full_hash": "aaaaaaa" + "2" * 33, "short_hash": "aaaaaaa2",
             "author_name": "Bob Lin", "subject": "feat: two", "date": "2026-09-02"},
        ]
        _write_day(self.worklog, "2026-09-02", "- aaaaaaa1 明確指向第一個")
        r = rc.reconcile(self.repo, self.worklog, commits, ["2026-09-02"])
        self.assertEqual([c["subject"] for c in r["backed"]], ["feat: one"])
        self.assertEqual([c["subject"] for c in r["unbacked"]], ["feat: two"])
        self.assertEqual(r["unresolved"], [])


class TestCitedHashes(unittest.TestCase):
    def test_finds_hashes_regardless_of_surrounding_prose(self):
        self.assertEqual(rc.cited_hashes("- abc1234 (Alice) 新增"), {"abc1234"})
        self.assertEqual(rc.cited_hashes("- **Related:** abc1234 add"), {"abc1234"})

    def test_ignores_tokens_too_short_to_be_a_hash(self):
        # Git's own minimum is 4, but 7 is what this tool emits; anything
        # shorter in prose is far more likely to be a word than a commit.
        self.assertEqual(rc.cited_hashes("abc123 and dead"), set())

    def test_does_not_match_inside_a_longer_word(self):
        self.assertEqual(rc.cited_hashes("abcdef1234ghijk"), set())

    def test_lowercases_what_it_finds(self):
        self.assertEqual(rc.cited_hashes("ABC1234"), {"abc1234"})


if __name__ == "__main__":
    unittest.main()
