"""Git Worklog — engineering worklogs from real Git history and code.

This package is the deterministic engine and CLI. It does the work that must be
exact — date maths, Git collection, marker parsing, transactional writes,
preview integrity — and leaves the semantic work (reading patches, deciding
what actually changed) to the agent's LLM. See ``references/`` in the skill for
that contract.

It lives inside the skill directory so the skill stays copy-to-install with no
dependencies, while ``pip install git-worklog`` puts the same code's CLI on
PATH.
"""

# The single source of truth for the product version. pyproject.toml reads this
# attribute; anything else that reports a version derives from here. The one copy
# that cannot import it -- agents/openai.yaml, static YAML -- is pinned to it by a
# guard test (tests/test_version.py), so the two cannot drift.
#
# Held at 0.4.0 through the internal v0.5-v0.9 milestones, then moved here to
# 1.0.0 for the first public release since v0.4.0. See issue #12.
#
# 1.1.0 is a minor bump on a deliberately loose reading: no command, flag or JSON
# field changed, but the skill stopped answering natural language without
# /git-worklog and its menu switched to English. That is not an API break, and it
# is not invisible either -- hence the prominent Changed entry in the CHANGELOG.
#
# 1.2.0 on the same reading: no command, flag or JSON field changed, but the
# subagent contract pinned the write mechanism to a Bash heredoc, banned the
# Write tool, and gave a Day Subagent a second thing it may reply --
# FAILED:<date>. For anyone reading the contract that is an interface change.
#
# 1.2.1 is a patch: 1.2.0 banned the Write tool but not Edit, so a subagent whose
# result failed its own parse check reached for Edit to fix the one bad line and
# stalled there. Nothing in the interface moved -- the ban simply covers the tool
# it always should have.
__version__ = "1.2.1"

# On-disk layout version of `.git-worklog/`, re-exported for convenience. It
# describes the *data*, not the tool, and bumps only when a migration is needed.
from git_worklog.markers import LAYOUT_VERSION  # noqa: E402

__all__ = ["__version__", "LAYOUT_VERSION"]
