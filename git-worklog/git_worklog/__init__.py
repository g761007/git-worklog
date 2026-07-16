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
# attribute; anything else that reports a version derives from here.
#
# Frozen at 0.4.0 through the internal v0.5-v0.9 milestones -- the last public
# release -- and moves once, to 1.0.0, when v1.0 ships. See issue #12.
__version__ = "0.4.0"

# On-disk layout version of `.git-worklog/`, re-exported for convenience. It
# describes the *data*, not the tool, and bumps only when a migration is needed.
from git_worklog.markers import LAYOUT_VERSION  # noqa: E402

__all__ = ["__version__", "LAYOUT_VERSION"]
