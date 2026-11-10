"""``git-worklog models`` — read or change the user's subagent model table.

The table is ``~/.git-worklog/provider_models.json``
(:mod:`git_worklog.providers`): the user's file, seeded from the shipped
defaults and never rewritten behind their back. This command is the same edit
they could make by hand, for when the one making it is a coding agent that
knows which models its own host currently offers -- so a new model does not
wait for a release of this tool.

With no ``--host`` it only reports: where the file is, what each host resolves
to, and where that differs from the shipped defaults. With ``--host`` and at
least one field it shows the change, and writes it only with ``--apply`` --
dry-run first, like every other command here that writes. It changes the one
host it is given and leaves every other key of the file as it found it.

It does not check that a model id exists. Only the host can say that, at
dispatch time, and an id it rejects still halts the run and asks
(``model_unavailable_policy``); nothing is substituted.
"""

from __future__ import annotations

import os

from git_worklog import paths, providers

# argparse destination -> the table's field.
FIELDS = (
    ("model", "model_id"),
    ("display_name", "display_name"),
    ("reasoning_effort", "reasoning_effort"),
    ("escalation_model", "escalation_model_id"),
    ("escalation_reasoning_effort", "escalation_reasoning_effort"),
)


NOT_CREATED = ("The file does not exist yet, so these are the defaults shipped with "
               "this version and may be older than the models the host offers now. "
               "Set the current ones with --host <host> --model <id> --apply.")


def _fail(code: str, message: str, **extra) -> "tuple[dict, int]":
    return {"ok": False, "errors": [{"code": code, "message": message, **extra}]}, 2


def run(args) -> "tuple[dict, int]":
    path = paths.models_path()
    exists = os.path.exists(path)
    try:
        shipped = providers.load_config()
        current = providers.load_config(path) if exists else providers.seed()
    except providers.ProviderError as exc:
        return {"ok": False, "errors": [exc.as_error()]}, 2

    changes = {field: getattr(args, dest) for dest, field in FIELDS if getattr(args, dest)}
    common = {"ok": True, "path": path, "exists": exists}
    if not args.host:
        if changes or args.apply:
            return _fail("ARG_CONFLICT", "--host says whose model to change; "
                                         "without it this command only reports.")
        return {**common, "mode": "show", "providers": current["providers"],
                "differences": providers.differences(current, shipped),
                **({} if exists else {"note": NOT_CREATED})}, 0
    if args.host not in providers.VALID_HOSTS:
        return _fail("UNKNOWN_HOST", f"Unknown host '{args.host}'.",
                     requested_host=args.host, valid_hosts=list(providers.VALID_HOSTS))
    if not changes:
        return _fail("ARG_CONFLICT", "Nothing to change: pass --model, "
                                     "--escalation-model or another field.")

    before = dict(current["providers"].get(args.host) or {})
    # A new default model under the old model's name would be a label that lies.
    if "model_id" in changes and "display_name" not in changes \
            and changes["model_id"] != before.get("model_id"):
        changes["display_name"] = changes["model_id"]
    after = dict(before, **changes)
    changed = sorted(f for f in after if after[f] != before.get(f))
    payload = {**common, "host": args.host, "before": before, "after": after,
               "changed": changed}
    if not args.apply:
        return {**payload, "mode": "dry-run",
                "note": "Nothing was written. Re-run with --apply to write it."}, 0
    if changed or not exists:
        updated = dict(current, providers=dict(current["providers"], **{args.host: after}))
        try:
            providers.write_user_config(updated)
        except OSError as exc:
            return _fail("IO_ERROR", f"{path} could not be written: {exc}", target=path)
    return {**payload, "mode": "apply", "exists": True}, 0


def render_text(p: dict) -> str:
    if not p.get("ok"):
        return "".join(f"error: {e['message']}\n" for e in p.get("errors", []))
    lines = [f"git-worklog models — {p['path']}"
             + ("" if p["exists"] else " (not created yet; shipped defaults shown)")]
    if p["mode"] == "show":
        for host, entry in p["providers"].items():
            lines.append(f"  {host}: {entry.get('model_id')}"
                         f"  (escalation: {entry.get('escalation_model_id')})")
        lines.extend(f"  differs from shipped — {d['provider']}.{d['field']}: "
                     f"yours {d['yours']!r}, shipped {d['shipped']!r}"
                     for d in p["differences"])
        return "\n".join(lines) + "\n"
    for field in p["changed"]:
        lines.append(f"  {p['host']}.{field}: {p['before'].get(field)!r} -> "
                     f"{p['after'][field]!r}")
    if not p["changed"]:
        lines.append(f"  {p['host']}: already set; nothing to change")
    lines.append("  written" if p["mode"] == "apply"
                 else "  dry-run: nothing written (re-run with --apply)")
    return "\n".join(lines) + "\n"
