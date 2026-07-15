"""Tests for resolve_date_range.py — the date/timezone contract."""

from __future__ import annotations

import unittest

from helpers import run_script

TZ = ["--timezone", "Asia/Taipei"]
TODAY = ["--today", "2026-07-15"]


class TestResolveHappyPaths(unittest.TestCase):
    def test_days_window_includes_today(self):
        d, rc, _ = run_script("resolve_date_range.py", ["--days", "7", *TODAY, *TZ])
        self.assertTrue(d["ok"])
        self.assertEqual(d["mode"], "days")
        self.assertEqual(d["days_count"], 7)
        self.assertEqual(d["dates"][0]["date"], "2026-07-09")
        self.assertEqual(d["dates"][-1]["date"], "2026-07-15")

    def test_day_bounds_are_half_open_local_midnight(self):
        d, _, _ = run_script("resolve_date_range.py", ["--days", "1", *TODAY, *TZ])
        day = d["dates"][0]
        self.assertEqual(day["start"], "2026-07-15T00:00:00+08:00")
        self.assertEqual(day["end"], "2026-07-16T00:00:00+08:00")

    def test_days_one_is_today(self):
        d, _, _ = run_script("resolve_date_range.py", ["--days", "1", *TODAY, *TZ])
        self.assertEqual(d["dates"], [d["dates"][0]])
        self.assertEqual(d["dates"][0]["date"], "2026-07-15")

    def test_shortcut_7d(self):
        d, _, _ = run_script("resolve_date_range.py", ["7d", *TODAY, *TZ])
        self.assertEqual(d["mode"], "days")
        self.assertEqual(d["days_count"], 7)

    def test_bare_date(self):
        d, _, _ = run_script("resolve_date_range.py", ["2026-07-01", *TZ])
        self.assertEqual(d["mode"], "date")
        self.assertEqual(d["dates"][0]["date"], "2026-07-01")

    def test_range_inclusive_both_ends(self):
        d, _, _ = run_script("resolve_date_range.py",
                             ["--from", "2026-07-01", "--to", "2026-07-10", *TZ])
        self.assertEqual(d["mode"], "range")
        self.assertEqual(d["days_count"], 10)

    def test_days_30_is_allowed(self):
        d, _, _ = run_script("resolve_date_range.py", ["--days", "30", *TODAY, *TZ])
        self.assertTrue(d["ok"])
        self.assertEqual(d["days_count"], 30)

    def test_explicit_timezone_source(self):
        d, _, _ = run_script("resolve_date_range.py", ["--days", "1", *TODAY, *TZ])
        self.assertEqual(d["timezone"], "Asia/Taipei")
        self.assertEqual(d["timezone_source"], "explicit")


class TestResolveValidation(unittest.TestCase):
    def _code(self, args):
        d, rc, _ = run_script("resolve_date_range.py", [*args, *TZ, *TODAY])
        self.assertFalse(d["ok"])
        self.assertEqual(rc, 2)
        return d["errors"][0]["code"]

    def test_days_over_limit(self):
        self.assertEqual(self._code(["--days", "31"]), "DAYS_OUT_OF_RANGE")

    def test_days_zero(self):
        self.assertEqual(self._code(["--days", "0"]), "DAYS_OUT_OF_RANGE")

    def test_date_days_conflict(self):
        self.assertEqual(self._code(["--date", "2026-07-01", "--days", "7"]),
                         "ARG_CONFLICT")

    def test_from_after_to(self):
        self.assertEqual(self._code(["--from", "2026-07-10", "--to", "2026-07-01"]),
                         "FROM_AFTER_TO")

    def test_range_over_30_days(self):
        d, rc, _ = run_script("resolve_date_range.py",
                             ["--from", "2026-06-01", "--to", "2026-07-15", *TZ])
        self.assertFalse(d["ok"])
        err = d["errors"][0]
        self.assertEqual(err["code"], "TOO_MANY_DAYS")
        self.assertEqual(err["requested_days"], 45)
        self.assertEqual(err["max_days"], 30)

    def test_to_without_from(self):
        self.assertEqual(self._code(["--to", "2026-07-01"]), "TO_WITHOUT_FROM")

    def test_from_without_to(self):
        self.assertEqual(self._code(["--from", "2026-07-01"]), "FROM_WITHOUT_TO")

    def test_impossible_date(self):
        self.assertEqual(self._code(["--date", "2026-02-30"]), "INVALID_DATE")

    def test_bad_format(self):
        self.assertEqual(self._code(["--date", "2026/07/01"]), "INVALID_DATE")

    def test_no_spec(self):
        d, rc, _ = run_script("resolve_date_range.py", [*TZ])
        self.assertEqual(d["errors"][0]["code"], "NO_DATE_SPEC")


if __name__ == "__main__":
    unittest.main()
