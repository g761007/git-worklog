# Safety model

**Languages:** English · [繁體中文](zh-TW/safety-model.md) — [← back to the README](../README.md)

- Dry-run first, always; nothing is written without explicit confirmation.
- One file per day: re-analysing a day rewrites only that day's file; every other
  day file is left byte-for-byte untouched.
- Each day's `MANUAL` region and the index's `MANUAL` region are preserved
  verbatim; only the generated regions are overwritten.
- Day-file writes are transactional (all target days stage, validate, and swap in
  atomically, with rollback), so a failed run never leaves some days updated and
  others not. The index is written atomically and is always reconstructable from
  the day files.
- **An apply writes the preview, not a reconstruction of it.** The preview record
  holds the final text of every target file, and `git-worklog apply` takes a
  preview id and nothing else — so what lands on disk is what was on screen, and
  no re-render can reach the filesystem.
- Applies are gated on everything that payload depends on: repository identity,
  git dir, branch, HEAD, submodules, the working tree (when the run read it),
  `index.md`, each day file, the directory listing, the analysis run, and the
  project's language settings. Anything moved, or a preview that is expired,
  cancelled, failed or already applied, is refused rather than reconciled.
- Concurrent applies to one worklog are locked out; a lock is broken only when
  its owner is provably dead.
- The skill never runs `git add/commit/push/fetch/pull/checkout/switch/merge/rebase`
  on its own initiative. A run writes day files and stops; it never stages,
  commits, or moves the repository as a consequence of having produced a
  worklog. Asking your agent to commit the result afterwards is a separate
  decision of yours, and the skill does not override it.
