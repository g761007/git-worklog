# Provider Models

Per-host subagent model selection for the `git-worklog` skill.

**Two files, two owners.**

- `git_worklog/data/provider_models.json` is what the skill **ships**: the
  defaults, and the single place this repository stores model ids. This document
  is its human-facing mirror. Never add a third place — update that JSON and this
  file only.
- `~/.git-worklog/provider_models.json` is what a run **reads**, and it belongs to
  the user. The first time a model is resolved it is copied from the shipped
  file; after that the tool never rewrites it — not on a run, not on an upgrade.
  Models are renamed and retired faster than a tool should have to be released,
  so a new model id is an edit to this file. (`$GIT_WORKLOG_HOME` moves it along
  with the rest of the state directory.)

The tables below are the shipped defaults. What a given machine actually uses is
whatever its own file says: `git-worklog models` prints it, and
`git-worklog doctor` lists where it differs from the defaults of the installed
version — the same list whether the user edited on purpose or an upgrade moved
the defaults on.

The skill runs under one of three hosts. Each host has one provider key and one
model. Every Day Subagent and Code Analysis Subagent for a run is spawned on the
model belonging to the host the skill is currently running under. Defaults are
chosen for **cost efficiency** on bounded, per-day analysis — do not silently
replace them with pricier models.

## Per-host models (defaults)

| Host        | provider key | display_name       | default model_id       | reasoning_effort |
| ----------- | ------------ | ------------------ | ---------------------- | ---------------- |
| Claude Code | `anthropic`  | Claude Haiku 4.5   | `claude-haiku-4-5`     | —                |
| Codex       | `openai`     | GPT-6 Luna         | `gpt-6-luna`           | `low`            |
| Gemini      | `google`     | Gemini 3.8 Flash   | `gemini-3.8-flash`     | —                |

`reasoning_effort` applies to `openai` only. For `anthropic` and `google` the
field is **omitted entirely** (never an empty string) from the resolver output
and the manifest.

## display_name vs model_id

- `display_name` is the human-facing label shown in menus, dry-run summaries, and
  candidate lists.
- `model_id` is the runtime dispatch identifier the host actually resolves when
  spawning a subagent. If the host's exact id differs from the default, override
  it (see below) rather than editing multiple files — a wrong `model_id` must
  surface as an unavailable model, never as a silent fallback.

## Resolving the model (nothing to resolve)

The orchestrator does not resolve the model at all. It names the host it is
running under, and `analyze prepare` does the rest:

```text
analyze prepare <range> --host <anthropic|openai|google>
  -> reads ~/.git-worklog/provider_models.json (copying the shipped defaults
     there first if it does not exist)
  -> applies the override precedence below
  -> reports { provider, model:{display_name, model_id[, reasoning_effort]} }
  -> stamps both on every day's manifest
  -> every Day / Code-Analysis subagent for the run runs on that model
```

There is no separate resolve step to forget, and no model object to carry
between two commands and get wrong. Read `provider` and `model` back off
prepare's output when you need to show the user which model the run will use.

## Host selection — never guessed

The host is one of `anthropic` / `openai` / `google`, decided by which runtime the
skill is executing under (Claude Code → `anthropic`, Codex → `openai`, Gemini →
`google`). The orchestrator passes it as `--host`.

- Only that one provider's entry is used. The three providers are **never** all
  passed to a subagent at once.
- The provider is **never** inferred from a model name.
- If the host cannot be determined, `analyze prepare --host` returns an
  `UNKNOWN_HOST` error and the skill **stops and reports a configuration error**.
  It never defaults to the first provider.

## Override precedence

For a given host, the model id is chosen in this order (highest first):

1. an explicit runtime id passed to the command (`--model`),
2. the environment variable for that provider,
3. the provider default in the user's `~/.git-worklog/provider_models.json`.

The skill never auto-substitutes an arbitrary host default beyond step 3. A user
file that cannot be read, or that leaves the host out, is an error
(`CONFIG_ERROR` / `UNKNOWN_HOST`) naming the file — never a reason to fall back
to the shipped defaults, which would swap the model the user chose for one they
did not. Only when the file cannot be *created* (a read-only home) are the
shipped defaults used, with a `USER_MODELS_NOT_WRITTEN` warning.

## Changing the models: `git-worklog models`

Editing the user's file by hand is fine. The command is the same edit, for when
a coding agent makes it:

```text
git-worklog models                                    # show the file, and its differences from the shipped defaults
git-worklog models --host <host> --model <id>         # dry-run: before / after, nothing written
git-worklog models --host <host> --model <id> --apply # write it
```

Fields: `--model`, `--display-name` (defaults to the model id when the model
changes), `--reasoning-effort`, `--escalation-model`,
`--escalation-reasoning-effort`. Only the named host and the named fields
change; every other key in the file is kept as found. The command does not check
that an id exists — only the host can, at dispatch, and a rejected id still
halts and asks.

The first time the file is created, the run reports `USER_MODELS_CREATED`, and
the skill asks the user whether to update the shipped defaults to the host's
current models. How the agent does that is in SKILL.md §3; it needs nothing from
this document.

| provider    | environment variable            |
| ----------- | ------------------------------- |
| `anthropic` | `GIT_WORKLOG_ANTHROPIC_MODEL`  |
| `openai`    | `GIT_WORKLOG_OPENAI_MODEL`     |
| `google`    | `GIT_WORKLOG_GOOGLE_MODEL`     |

The pre-v0.7 names — `REPO_WORKLOG_<PROVIDER>_MODEL` — shipped in v0.3.0–v0.4.0
and are **still honoured**, because someone's shell profile still exports one and
ignoring it would silently swap their model back to the config default: exactly
the substitution this whole file exists to prevent. The current name wins when
both are set, and a run that used a deprecated name reports it:

```json
"warnings": [{"code": "DEPRECATED_ENV_VAR",
              "deprecated": "REPO_WORKLOG_OPENAI_MODEL",
              "replacement": "GIT_WORKLOG_OPENAI_MODEL"}]
```

Surface that warning in the dry-run summary rather than swallowing it; the old
names are removed in v2.0.

## Unavailable-model policy

The config sets `model_unavailable_policy: halt-and-ask`. If the selected
`model_id` cannot be resolved or the host rejects it, the skill MUST halt and ask
rather than proceed. It MUST NOT:

- silently switch to a more expensive model,
- auto-pick another model,
- fall back to the escalation models (Sonnet / Sol / Pro),
- degrade to reading only commit messages,
- ignore the error and keep generating a worklog.

It MUST report at least the `provider`, the requested `model_id`, the reason, and
the currently selectable candidate models, then let the user decide. The resolver
supplies the candidate list on `MODEL_UNAVAILABLE`.

Example message:

```text
Unable to start Git Worklog subagent.
Provider: openai
Requested model: gpt-6-luna
The requested model is not available in the current host.
No fallback model was selected automatically.

Currently selectable models:
  - Claude Haiku 4.5 (anthropic / claude-haiku-4-5)
  - Gemini 3.8 Flash (google / gemini-3.8-flash)

Please configure an available model ID and run the dry-run again.
```

## Escalation (opt-in, default OFF)

Each provider also carries an escalation model for the rare case where the
low-cost default cannot resolve a day confidently. Escalation is **never
automatic**.

| provider    | escalation_model_id       | escalation_reasoning_effort |
| ----------- | ------------------------- | --------------------------- |
| `anthropic` | `claude-sonnet-5-5`       | —                           |
| `openai`    | `gpt-6.1-sol`             | `medium`                    |
| `google`    | `gemini-3.1-pro-preview`  | —                           |

Rules (`escalation_policy.automatic` is fixed to `false`):

- Subagents never switch to the escalation model on their own.
- The orchestrator may only **suggest** escalation in a dry-run, when a day's
  return has `escalation_recommended: true` (see `subagent-contract.md` §7) — the
  `suggest_when` reasons are: analysis incomplete, confidence unknown, conflicting
  evidence, unresolved merge result, unclear revert final state, or unreadable
  required code context.
- Escalation runs only after the user explicitly approves. The approved day(s) are
  re-analysed with `analyze prepare --host <key> --escalate`, which mints a
  **new** dry-run and a **new `preview_id`**. The original preview is never
  edited in place.
