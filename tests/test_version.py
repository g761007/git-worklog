"""Version-number guards: one source of truth, and data versions kept apart.

The product version has a single source of truth — `git_worklog.__version__`,
which `pyproject.toml` reads dynamically and `git-worklog version` derives from.
One copy cannot import it: `agents/openai.yaml` is static YAML. These tests are
what stop that copy drifting, and what stop a product release quietly bumping the
on-disk data versions, which describe a different thing on a different clock
(#12).
"""

from __future__ import annotations

import os
import re
import sys
import unittest

from helpers import ROOT, SKILL_ROOT

sys.path.insert(0, SKILL_ROOT)

from git_worklog import __version__  # noqa: E402
from git_worklog.markers import LAYOUT_VERSION  # noqa: E402

OPENAI_YAML = os.path.join(ROOT, "git-worklog", "agents", "openai.yaml")

# A dotted release number, e.g. 1.0.0. Not SemVer-complete (no pre-release
# suffixes) because the project does not use them; tighten if that changes.
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _yaml_version(path: str) -> str:
    """The `version:` field, read without a YAML library (tests are stdlib-only).

    A line-anchored match, so a `version:` nested inside some other block could
    not be picked up by accident — the manifest's is top-level.
    """
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^version:\s*(\S+)\s*$", line)
            if m:
                return m.group(1)
    raise AssertionError(f"{path} has no top-level version: line")


class TestOneSourceOfTruth(unittest.TestCase):
    def test_the_product_version_is_a_release_number(self):
        self.assertRegex(__version__, _SEMVER)

    def test_openai_yaml_matches_the_package_version(self):
        # The whole point of the guard: the one copy that cannot `import` the
        # source of truth is checked against it, so bumping __version__ without
        # the YAML (or vice versa) fails here rather than shipping a split
        # identity to users.
        self.assertEqual(
            _yaml_version(OPENAI_YAML), __version__,
            "agents/openai.yaml version has drifted from git_worklog.__version__ "
            "— bump both, or the packaged skill and the installed CLI disagree.")

    def test_this_release_is_one_point_zero(self):
        # Pins the actual ship. When the next release bumps __version__, this and
        # the YAML move together or the suite goes red — which is the reminder.
        self.assertEqual(__version__, "1.0.0")


class TestDataVersionsStayIndependent(unittest.TestCase):
    """`.git-worklog/VERSION` and `config.json` schema_version describe on-disk
    data, not the tool. A product release must never move them; only a layout
    change that needs a migration does."""

    def test_layout_version_is_not_the_product_version(self):
        # They are different clocks. If they were ever made equal it would be a
        # coincidence to break deliberately, not a rule to keep: a docs-only
        # v1.0.1 must not churn every user's VERSION file.
        self.assertEqual(LAYOUT_VERSION, 1)

    def test_a_product_bump_leaves_the_layout_version_at_one(self):
        # The release is 1.0.0; the layout is still 1. This pins that the ship
        # did not sweep the data version along with it. It moves only when
        # markers.LAYOUT_VERSION is deliberately bumped for a migration, at which
        # point this test is updated in that same change — on purpose.
        self.assertNotEqual(str(LAYOUT_VERSION), __version__)
        self.assertEqual(LAYOUT_VERSION, 1)


if __name__ == "__main__":
    unittest.main()
