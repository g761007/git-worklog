# Security Policy

## Supported versions

Security fixes are made on the latest release. Please upgrade before reporting
a problem that may already be fixed — see
[Releases](https://github.com/g761007/git-worklog/releases).

## Reporting a vulnerability

Please report vulnerabilities privately, not in a public issue:

1. Open the repository's
   [Security tab](https://github.com/g761007/git-worklog/security).
2. Choose **Report a vulnerability**.

Include what you did, what happened, what you expected, and the output of
`git-worklog version`. You should receive a reply within a week.

## What is in scope

Git Worklog reads repositories and writes Markdown, so the areas most worth
scrutiny are:

- **`git-worklog view`** — the page embeds worklog text and commit metadata. All
  of it is meant to be escaped, and the page's Content-Security-Policy allows
  only its own script. Anything that lets worklog content or a commit message
  run as markup or script is a vulnerability.
- **`git-worklog view --serve`** — a local server bound to `127.0.0.1` behind a
  per-run token, serving diffs only for commits the worklog cites. Reaching it
  without the token, from another host name, or for an uncited commit is a
  vulnerability.
- **`git-worklog apply`** — writes only the bytes of a stored preview, inside
  the worklog directory. Writing anywhere else, or writing content that was not
  previewed, is a vulnerability.
- **State under `~/.git-worklog/`** — previews and view pages contain source
  text and are written owner-only.

The engine makes no network requests of its own. The model that reads your code
is the agent host you run the skill in; how that host handles your data is
governed by that host, not by this project.
