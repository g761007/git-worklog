# Contributing to Git Worklog

Issues and pull requests are welcome. This page is the short version of what a
change needs before it can merge; [docs/development.md](docs/development.md)
has the repository layout and the release build.

## Ground rules

- **No runtime dependencies.** The engine doubles as the skill, and the skill is
  installed by copying a folder. Anything that needs `pip install` to run breaks
  that, so the package and the test suite use the Python standard library only.
- **Python 3.9 is the floor.** CI runs the suite on 3.9 and on newer versions.
- **The package stays inside the skill directory** (`git-worklog/git_worklog/`).
  Moving it out would cost the copy-to-install property.
- **Prose that an agent must obey goes where that agent reads it.** A rule for a
  subagent belongs in the prompt template or the manifest, not only in a
  reference file it may never open.

## Running the tests

Nothing to install:

```bash
python3 -m unittest discover -s tests -v
```

The suite builds its own Git fixtures and uses a throwaway `HOME`, so it does not
touch your repositories or your `~/.git-worklog/`.

To try the CLI from the working tree:

```bash
PYTHONPATH=git-worklog python3 -m git_worklog --text doctor
```

## Making a change

1. Open an issue first for anything larger than a fix, so the approach can be
   agreed before the work is done.
2. Branch from `main` and keep the change focused — one topic per pull request.
3. Add or update tests that would fail if the behaviour were wrong. A bug fix
   comes with a test that reproduces the bug.
4. Update the documentation the change touches: `README.md` and
   `README.zh-TW.md`, the matching pages under `docs/` and `docs/zh-TW/`, and
   `git-worklog/SKILL.md` or `git-worklog/references/` when the skill's
   behaviour changes.
5. Add an entry to `CHANGELOG.md`.

Commit messages follow the style already in the history —
`type(scope): what changed`, for example
`fix(view): escape the commit subject in the drawer`.

## Releases

The version lives in `git-worklog/git_worklog/__init__.py` and is mirrored in
`git-worklog/agents/openai.yaml`; `tests/test_version.py` fails when the two
drift or when the pinned release is not updated. Maintainers cut releases.

## Reporting security issues

Please do not open a public issue for a vulnerability — see
[SECURITY.md](SECURITY.md).
