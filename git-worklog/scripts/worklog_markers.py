#!/usr/bin/env python3
"""Compatibility shim: the real module is ``git_worklog.markers``.

The format parser/serialiser moved into the package so the CLI and the scripts
share exactly one definition of it. The scripts import it as ``worklog_markers``
and are run as ``python3 scripts/<name>.py``, which puts *this* directory on
sys.path but not the skill root -- so the skill root is added below before
re-exporting.

Import ``git_worklog.markers`` directly in new code. This shim exists so the
scripts, and anything pinned to the old import, keep working.
"""

from __future__ import annotations

import os
import sys

_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)

# Re-export the module's full surface, including the private names the module's
# own tests reach for. `import *` would silently drop those and every underscore
# helper, so bind the module's namespace wholesale instead.
from git_worklog import markers as _markers  # noqa: E402

globals().update({k: v for k, v in vars(_markers).items()
                  if k not in ("__name__", "__file__", "__doc__", "__loader__",
                               "__spec__", "__package__")})
