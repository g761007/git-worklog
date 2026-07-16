"""Make ``git_worklog`` importable from a script run as ``python3 scripts/x.py``.

That form puts ``scripts/`` on sys.path but not the skill root, so the package
sitting next to it is invisible. Importing this module first fixes that.

It exists so the skill keeps working when it is simply copied into a host's
skills folder, with nothing installed. When ``git-worklog`` is pip-installed the
package is already importable and this is a no-op.
"""

from __future__ import annotations

import os
import sys

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if SKILL_ROOT not in sys.path:
    sys.path.insert(0, SKILL_ROOT)
