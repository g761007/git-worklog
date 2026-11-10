"""Resolve the subagent provider/model for the host the skill runs under.

The Git Worklog orchestrator runs under exactly one host — Claude Code
(``anthropic``), Codex (``openai``), or Gemini (``google``) — and every Day
Subagent and Code Analysis Subagent for a run executes on that host's single
model. This is the deterministic, single-source resolver: it reads the model
table, selects the entry for the given host, and applies the override
precedence.

**The table is the user's file.** Models are renamed and retired faster than a
tool should have to be released, so the table that is read is
``~/.git-worklog/provider_models.json`` (:func:`git_worklog.paths.models_path`),
not the one inside the package. The packaged
``git_worklog/data/provider_models.json`` is only the seed: the first time a
model is resolved it is copied out, and from then on the copy is read and
never rewritten -- not by a run, not by an upgrade. A newer release that ships
newer defaults therefore changes nothing for someone who already has the file;
``git-worklog doctor`` is what tells them the two differ.

Override precedence for the model id (highest first):

  1. ``model`` (explicit runtime/CLI model id)
  2. environment variable ``GIT_WORKLOG_<HOST>_MODEL`` (or the deprecated
     ``REPO_WORKLOG_<HOST>_MODEL``)
  3. the provider default in the user's ``provider_models.json``

The host is NEVER guessed: a missing or unknown host is a configuration error,
never a silent pick of the first provider. A model that cannot be resolved (empty
id) raises with the selectable candidate list — the skill must never silently
fall back to a pricier or arbitrary host default.

Escalation is opt-in only: automatic escalation is disabled and the flag is used
solely after the user explicitly approves an escalation re-run.
"""

from __future__ import annotations

import json
import os
import tempfile

from git_worklog import paths

VALID_HOSTS = ("anthropic", "openai", "google")


class ProviderError(ValueError):
    """A provider/model that cannot be resolved, carrying the wire code.

    Mirrors :class:`git_worklog.dates.DateError` and
    :class:`git_worklog.analysis.AnalysisError`: the callers are thin shells that
    owe the user one JSON object with a stable ``code``.
    """

    def __init__(self, code: str, message: str, **extra):
        self.code = code
        self.message = message
        self.extra = extra
        super().__init__(message)

    def as_error(self) -> dict:
        """The error dict as it goes on the wire."""
        return {"code": self.code, "message": self.message, **self.extra}


def default_config_path() -> str:
    """``provider_models.json`` as shipped inside the package.

    It lives in the package rather than in a sibling ``config/`` directory
    because only ``git_worklog*`` is packaged: from a sibling, an installed CLI
    could not find it and would have no model to resolve. Here, the skill layout
    and the wheel reach the same one file -- which is the point of calling it the
    single source of truth.
    """
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "provider_models.json")


USER_COMMENT = (
    "Subagent models per host, read by git-worklog on every run. This file is "
    "yours: edit model_id / escalation_model_id (and display_name) when a "
    "provider renames or retires a model. git-worklog copied it from its "
    "shipped defaults once and never rewrites it on its own; `git-worklog models "
    "--host <host> --model <id> --apply` is the same edit as a command. "
    "`git-worklog doctor` lists "
    "where it differs from the defaults of the installed version; delete the "
    "file to start again from those.")


def write_user_config(config: dict) -> str:
    """Write ``config`` as the user's model table, whole or not at all."""
    path = paths.models_path()
    paths.ensure_dir(os.path.dirname(path))
    fd, staged = tempfile.mkstemp(prefix=".rw-models-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(config, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(staged, path)   # two first runs at once: either copy is right
    except BaseException:
        os.unlink(staged)
        raise
    return path


def seed() -> dict:
    """What a new user table holds: the shipped defaults, addressed to the user."""
    return dict(load_config(default_config_path()), _comment=USER_COMMENT)


def ensure_user_config() -> "tuple[str, dict | None]":
    """The path of the model table to read, seeding the user's copy if absent.

    Returns ``(path, notice)``. Seeding is reported, once, as
    ``USER_MODELS_CREATED``: the shipped defaults are as old as the release they
    came in, and the moment the file appears is the moment to ask the user
    whether the host has newer models. The notice carries that instruction
    itself, because the agent reading this output is the one who has to ask.

    When the copy cannot be written -- a read-only home, a sandbox -- the
    shipped table is read instead and ``USER_MODELS_NOT_WRITTEN`` says so: a run
    still resolves a model, and the user learns why their file is not there to
    edit.
    """
    path = paths.models_path()
    if os.path.exists(path):
        return path, None
    try:
        write_user_config(seed())
    except OSError as exc:
        return default_config_path(), {
            "code": "USER_MODELS_NOT_WRITTEN",
            "message": f"{path} could not be created ({exc}); the shipped model "
                       "defaults were used for this run.",
            "target": path,
        }
    return path, {
        "code": "USER_MODELS_CREATED",
        "message": f"{path} did not exist and was created from the defaults shipped "
                   "with this version, which may be older than the models the host "
                   "offers now. Before going on, ask the user whether to update it "
                   "to the host's current models; if they agree, look up the "
                   "host's current model ids and write them with `git-worklog "
                   "models --host <host> --model <id> --escalation-model <id> "
                   "--apply`. It is the user's file and is never rewritten for them.",
        "target": path,
    }


def differences(user: dict, shipped: dict) -> "list[dict]":
    """Where the user's providers differ from the shipped ones, field by field."""
    out = []
    ours, theirs = user.get("providers") or {}, shipped.get("providers") or {}
    for host in sorted(set(ours) | set(theirs)):
        a, b = ours.get(host) or {}, theirs.get(host) or {}
        for field in sorted(set(a) | set(b)):
            if a.get(field) != b.get(field):
                out.append({"provider": host, "field": field,
                            "yours": a.get(field), "shipped": b.get(field)})
    return out


def env_var(host: str) -> str:
    return f"GIT_WORKLOG_{host.upper()}_MODEL"


def _legacy_env_var(host: str) -> str:
    """The pre-v0.7 name. Shipped in v0.3.0-v0.4.0, so it is still honoured."""
    return f"REPO_WORKLOG_{host.upper()}_MODEL"


def _resolve_env(host: str) -> "tuple[str | None, str | None]":
    """Read the model override from the environment.

    Returns ``(value, deprecated_var_used)``. The current name wins; the legacy
    one is honoured because it was publicly released and someone's shell profile
    still exports it. Silently ignoring it would swap their model without a word
    -- the one thing this module exists to never do.
    """
    val = os.environ.get(env_var(host)) or None
    if val:
        return val, None
    legacy = os.environ.get(_legacy_env_var(host)) or None
    if legacy:
        return legacy, _legacy_env_var(host)
    return None, None


def _candidates(providers: dict) -> list:
    """Every configured provider's human label + id, for halt-and-ask lists."""
    out = []
    for key in VALID_HOSTS:
        entry = providers.get(key)
        if not entry:
            continue
        out.append({
            "provider": key,
            "display_name": entry.get("display_name"),
            "model_id": entry.get("model_id"),
        })
    return out


def load_config(path: "str | None" = None) -> dict:
    """Read a model table. Raises ProviderError if it is unusable.

    A table that cannot be read is an error and never a reason to read another
    one: quietly falling back to the shipped defaults would swap the model the
    user chose for one they did not.
    """
    path = path or default_config_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            config = json.load(fh)
    except FileNotFoundError:
        raise ProviderError("CONFIG_NOT_FOUND",
                            f"Provider model config not found: {path}", target=path)
    except (ValueError, OSError) as exc:
        raise ProviderError("CONFIG_ERROR",
                            f"Could not read provider model config {path}: {exc}",
                            target=path)
    if not isinstance(config, dict) or not isinstance(config.get("providers"), dict):
        raise ProviderError("CONFIG_ERROR",
                            f"{path} has no \"providers\" object.", target=path)
    return config


def resolve(host: "str | None", model: "str | None" = None,
            reasoning_effort: "str | None" = None, escalate: bool = False,
            config_path: "str | None" = None) -> dict:
    """Resolve ``host`` to its model. Raises ProviderError on any config fault.

    With no ``config_path`` the user's table is read, and seeded first if it
    does not exist yet. An explicit path is read as given and seeds nothing.
    """
    seed_warning = None
    if config_path is None:
        config_path, seed_warning = ensure_user_config()
    config = load_config(config_path)
    providers = config.get("providers") or {}

    # The host is never guessed. Missing / unknown host is a config error.
    if not host:
        raise ProviderError(
            "UNKNOWN_HOST",
            "No host was provided. The skill must detect its host (Claude Code -> "
            "anthropic, Codex -> openai, Gemini -> google) and pass --host; it must "
            "not guess or default to the first provider.",
            valid_hosts=list(VALID_HOSTS))
    if host not in VALID_HOSTS or host not in providers:
        raise ProviderError(
            "UNKNOWN_HOST",
            f"Unknown or unconfigured host '{host}'.",
            requested_host=host, valid_hosts=list(VALID_HOSTS))

    entry = providers[host]
    escalating = bool(escalate)

    # Pick the base id for this mode, then apply the override precedence on top.
    if escalating:
        base_id = entry.get("escalation_model_id")
        if not base_id:
            raise ProviderError(
                "NO_ESCALATION_MODEL",
                f"Provider '{host}' has no escalation_model_id configured; "
                "escalation is unavailable for this host.",
                provider=host)
        base_effort = entry.get("escalation_reasoning_effort")
    else:
        base_id = entry.get("model_id")
        base_effort = entry.get("reasoning_effort")

    env_val, deprecated_var = _resolve_env(host)
    cli_val = model or None
    if cli_val:
        model_id, source = cli_val, "cli"
    elif env_val:
        model_id, source = env_val, "env"
    else:
        model_id, source = base_id, "config"

    if not model_id or not str(model_id).strip():
        # Never silently fall back to a host default or a pricier model.
        raise ProviderError(
            "MODEL_UNAVAILABLE",
            f"No model id could be resolved for provider '{host}'. No fallback "
            "model was selected automatically. Configure an available model id "
            f"(config default, {env_var(host)}, or --model) and re-run the dry-run.",
            provider=host,
            requested_model_id=model_id or "",
            candidates=_candidates(providers))

    # reasoning_effort: CLI override wins; otherwise the mode's configured value.
    # Absent (e.g. anthropic / google) -> the key is omitted entirely, never "".
    effort = reasoning_effort or base_effort
    resolved_model = {
        "display_name": entry.get("display_name") if not escalating else str(model_id),
        "model_id": str(model_id),
    }
    if effort:
        resolved_model["reasoning_effort"] = effort

    escalation_id = entry.get("escalation_model_id")
    result = {
        "ok": True,
        "provider": host,
        "escalated": escalating,
        "model": resolved_model,
        "model_id_source": source,
        "config_path": config_path,
        "escalation": {
            "available": bool(escalation_id),
            "model_id": escalation_id,
        },
        "escalation_policy": config.get("escalation_policy",
                                        {"automatic": False, "suggest_when": []}),
        "model_unavailable_policy": config.get("model_unavailable_policy",
                                               "halt-and-ask"),
    }

    # An honoured-but-renamed variable is reported, never silently obeyed: the
    # user is picking a model, and they should know which knob actually did it.
    if deprecated_var and source == "env":
        result["warnings"] = [{
            "code": "DEPRECATED_ENV_VAR",
            "message": f"{deprecated_var} is deprecated and will be removed in "
                       f"v2.0; rename it to {env_var(host)}. It was honoured "
                       "for this run.",
            "deprecated": deprecated_var,
            "replacement": env_var(host),
        }]
    if seed_warning:
        result.setdefault("warnings", []).append(seed_warning)
    esc_effort = entry.get("escalation_reasoning_effort")
    if esc_effort:
        result["escalation"]["reasoning_effort"] = esc_effort
    return result
