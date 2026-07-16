"""Entry point for ``python3 -m git_worklog``.

The console script (``git-worklog``) only exists after a pip install. This form
works straight from the skill directory with nothing installed, which is how the
skill itself runs.
"""

from git_worklog.cli import main

raise SystemExit(main())
