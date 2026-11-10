"""Provider/model selection, manifest threading, fallback, and escalation.

Covers scripts/resolve_provider_model.py (per-host selection, override
precedence, halt-and-ask, escalation), the structured `model` object threaded
into build_analysis_manifest.py, and a static guard that the retired default
model names do not reappear as active defaults anywhere in the shipped skill.

It also covers the user's own model table, ~/.git-worklog/provider_models.json:
that it is seeded once and then left alone, that it is the table a run reads,
and that `git-worklog models` and `doctor` treat it as the user's file.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unittest

from helpers import run_cli, run_script, ROOT

SKILL_DIR = os.path.join(ROOT, "git-worklog")
CONFIG_PATH = os.path.join(SKILL_DIR, "git_worklog", "data", "provider_models.json")

NEW_DEFAULTS = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-6-luna",
    "google": "gemini-3.8-flash",
}
EXPECTED_ESCALATION = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "gpt-6.1-sol",
    "google": "gemini-3.1-pro-preview",
}


def _write_config(body: dict) -> str:
    fd, path = tempfile.mkstemp(prefix="rw_cfg_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(body, fh)
    return path


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


class TestProviderMapping(unittest.TestCase):
    """Each host selects exactly its own provider's default model."""

    def test_anthropic_selects_haiku(self):
        out, rc, err = run_script("resolve_provider_model.py", ["--host", "anthropic"])
        self.assertEqual(rc, 0, err)
        self.assertTrue(out["ok"])
        self.assertEqual(out["provider"], "anthropic")
        self.assertEqual(out["model"]["model_id"], "claude-haiku-4-5")
        self.assertEqual(out["model"]["display_name"], "Claude Haiku 4.5")
        # anthropic has no reasoning_effort — the key must be absent, not "".
        self.assertNotIn("reasoning_effort", out["model"])

    def test_openai_selects_luna_with_low_effort(self):
        out, rc, err = run_script("resolve_provider_model.py", ["--host", "openai"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(out["provider"], "openai")
        self.assertEqual(out["model"]["model_id"], "gpt-6-luna")
        self.assertEqual(out["model"]["reasoning_effort"], "low")

    def test_google_selects_flash_without_effort(self):
        out, rc, err = run_script("resolve_provider_model.py", ["--host", "google"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(out["provider"], "google")
        self.assertEqual(out["model"]["model_id"], "gemini-3.8-flash")
        self.assertNotIn("reasoning_effort", out["model"])

    def test_unknown_host_errors(self):
        out, rc, _ = run_script("resolve_provider_model.py", ["--host", "codex"])
        self.assertEqual(rc, 2)
        self.assertFalse(out["ok"])
        self.assertEqual(out["errors"][0]["code"], "UNKNOWN_HOST")
        self.assertNotIn("model", out)  # never falls through to a model

    def test_missing_host_errors_without_guessing(self):
        out, rc, _ = run_script("resolve_provider_model.py", [])
        self.assertEqual(rc, 2)
        self.assertEqual(out["errors"][0]["code"], "UNKNOWN_HOST")
        # It must NOT default to the first provider.
        self.assertNotIn("provider", out)

    def test_does_not_borrow_another_providers_model(self):
        out, _, _ = run_script("resolve_provider_model.py", ["--host", "anthropic"])
        blob = json.dumps(out)
        self.assertNotIn("gpt-6-luna", blob)
        self.assertNotIn("gemini-3.8-flash", blob)


class TestOverrides(unittest.TestCase):
    """cli --model > env GIT_WORKLOG_<HOST>_MODEL > config default."""

    def test_no_override_uses_config_default(self):
        out, _, _ = run_script("resolve_provider_model.py", ["--host", "openai"])
        self.assertEqual(out["model"]["model_id"], "gpt-6-luna")
        self.assertEqual(out["model_id_source"], "config")

    def test_env_override(self):
        out, _, _ = run_script(
            "resolve_provider_model.py", ["--host", "openai"],
            env={"GIT_WORKLOG_OPENAI_MODEL": "gpt-5.6-luna-2026-07"})
        self.assertEqual(out["model"]["model_id"], "gpt-5.6-luna-2026-07")
        self.assertEqual(out["model_id_source"], "env")
        self.assertNotIn("warnings", out)

    def test_cli_beats_env(self):
        out, _, _ = run_script(
            "resolve_provider_model.py", ["--host", "openai", "--model", "gpt-from-cli"],
            env={"GIT_WORKLOG_OPENAI_MODEL": "gpt-from-env"})
        self.assertEqual(out["model"]["model_id"], "gpt-from-cli")
        self.assertEqual(out["model_id_source"], "cli")


class TestLegacyEnvVar(unittest.TestCase):
    """REPO_WORKLOG_<HOST>_MODEL shipped in v0.3.0-v0.4.0 and is still honoured."""

    def test_legacy_var_still_selects_the_model(self):
        # Ignoring it would silently swap the user's model back to the config
        # default -- the exact silent substitution this script exists to prevent.
        out, _, _ = run_script(
            "resolve_provider_model.py", ["--host", "openai"],
            env={"REPO_WORKLOG_OPENAI_MODEL": "gpt-from-legacy"})
        self.assertEqual(out["model"]["model_id"], "gpt-from-legacy")
        self.assertEqual(out["model_id_source"], "env")

    def test_legacy_var_is_reported_not_silently_obeyed(self):
        out, _, _ = run_script(
            "resolve_provider_model.py", ["--host", "openai"],
            env={"REPO_WORKLOG_OPENAI_MODEL": "gpt-from-legacy"})
        warn = out["warnings"][0]
        self.assertEqual(warn["code"], "DEPRECATED_ENV_VAR")
        self.assertEqual(warn["deprecated"], "REPO_WORKLOG_OPENAI_MODEL")
        self.assertEqual(warn["replacement"], "GIT_WORKLOG_OPENAI_MODEL")

    def test_current_var_wins_over_legacy(self):
        out, _, _ = run_script(
            "resolve_provider_model.py", ["--host", "openai"],
            env={"GIT_WORKLOG_OPENAI_MODEL": "gpt-current",
                 "REPO_WORKLOG_OPENAI_MODEL": "gpt-legacy"})
        self.assertEqual(out["model"]["model_id"], "gpt-current")
        self.assertNotIn("warnings", out)   # nothing deprecated was used

    def test_cli_still_beats_the_legacy_var(self):
        out, _, _ = run_script(
            "resolve_provider_model.py", ["--host", "openai", "--model", "gpt-cli"],
            env={"REPO_WORKLOG_OPENAI_MODEL": "gpt-legacy"})
        self.assertEqual(out["model"]["model_id"], "gpt-cli")
        self.assertEqual(out["model_id_source"], "cli")
        self.assertNotIn("warnings", out)   # the legacy var did not decide anything


class TestManifestModel(unittest.TestCase):
    """The resolved model object is threaded verbatim onto the manifest."""

    _HISTORY = json.dumps({"ok": True, "commits": []})

    def _manifest(self, provider, model_json=None):
        args = ["--date", "2026-07-15", "--timezone", "Asia/Taipei", "--provider", provider]
        if model_json is not None:
            args += ["--model-json", model_json]
        out, rc, err = run_script("build_analysis_manifest.py", args, stdin=self._HISTORY)
        self.assertEqual(rc, 0, err)
        self.assertTrue(out["ok"], err)
        return out

    def test_openai_manifest_has_low_reasoning_effort(self):
        resolved, _, _ = run_script("resolve_provider_model.py", ["--host", "openai"])
        man = self._manifest("openai", json.dumps(resolved["model"]))
        self.assertEqual(man["provider"], "openai")
        self.assertEqual(man["model"]["reasoning_effort"], "low")

    def test_anthropic_manifest_has_no_reasoning_effort(self):
        resolved, _, _ = run_script("resolve_provider_model.py", ["--host", "anthropic"])
        man = self._manifest("anthropic", json.dumps(resolved["model"]))
        self.assertNotIn("reasoning_effort", man["model"])

    def test_google_manifest_has_no_reasoning_effort(self):
        resolved, _, _ = run_script("resolve_provider_model.py", ["--host", "google"])
        man = self._manifest("google", json.dumps(resolved["model"]))
        self.assertNotIn("reasoning_effort", man["model"])

    def test_model_override_flows_into_manifest(self):
        override = {"display_name": "Custom", "model_id": "custom-xyz"}
        man = self._manifest("openai", json.dumps(override))
        self.assertEqual(man["model"], override)

    def test_no_model_json_yields_null(self):
        man = self._manifest("anthropic")
        self.assertIsNone(man["model"])

    def test_bad_model_json_is_rejected(self):
        out, rc, _ = run_script(
            "build_analysis_manifest.py",
            ["--date", "2026-07-15", "--timezone", "Asia/Taipei", "--model-json", "not-json"],
            stdin=self._HISTORY)
        self.assertEqual(rc, 2)
        self.assertEqual(out["errors"][0]["code"], "BAD_MODEL_JSON")


class TestFallback(unittest.TestCase):
    """An unresolvable model halts; no silent fallback to a default or pricier model."""

    def test_empty_model_id_halts_with_candidates(self):
        cfg = _write_config({
            "providers": {
                "openai": {"display_name": "GPT-5.6 Luna", "model_id": ""},
                "anthropic": {"display_name": "Claude Haiku 4.5", "model_id": "claude-haiku-4-5"},
                "google": {"display_name": "Gemini 3.5 Flash", "model_id": "gemini-3.5-flash"},
            },
            "model_unavailable_policy": "halt-and-ask",
        })
        try:
            out, rc, _ = run_script("resolve_provider_model.py",
                                    ["--host", "openai", "--config", cfg])
            self.assertEqual(rc, 2)
            err = out["errors"][0]
            self.assertEqual(err["code"], "MODEL_UNAVAILABLE")
            self.assertEqual(err["provider"], "openai")
            self.assertIn("requested_model_id", err)          # requested id reported
            self.assertTrue(err["candidates"])                # selectable list supplied
            self.assertNotIn("model", out)                    # no auto-fallback model
        finally:
            os.remove(cfg)

    def test_does_not_use_escalation_model_as_fallback(self):
        # Default resolve (no --escalate) must never surface the escalation model
        # as the active model, even though it is available.
        out, _, _ = run_script("resolve_provider_model.py", ["--host", "openai"])
        self.assertEqual(out["escalated"], False)
        self.assertEqual(out["model"]["model_id"], "gpt-6-luna")
        self.assertNotEqual(out["model"]["model_id"], out["escalation"]["model_id"])


class TestEscalation(unittest.TestCase):
    """Escalation is opt-in; automatic is off; a re-run mints a fresh preview id."""

    def test_policy_automatic_is_false(self):
        out, _, _ = run_script("resolve_provider_model.py", ["--host", "openai"])
        self.assertFalse(out["escalation_policy"]["automatic"])

    def test_confidence_unknown_only_suggests(self):
        # The resolver never escalates on its own; without --escalate the active
        # model stays the cost-first default regardless of subagent confidence.
        out, _, _ = run_script("resolve_provider_model.py", ["--host", "anthropic"])
        self.assertFalse(out["escalated"])
        self.assertEqual(out["model"]["model_id"], "claude-haiku-4-5")

    def test_escalate_flag_selects_escalation_model(self):
        out, rc, err = run_script("resolve_provider_model.py",
                                  ["--host", "openai", "--escalate"])
        self.assertEqual(rc, 0, err)
        self.assertTrue(out["escalated"])
        self.assertEqual(out["model"]["model_id"], "gpt-6.1-sol")
        self.assertEqual(out["model"]["reasoning_effort"], "medium")

    def test_escalation_unavailable_errors(self):
        cfg = _write_config({
            "providers": {"google": {"display_name": "Gemini 3.5 Flash",
                                     "model_id": "gemini-3.5-flash"}},
            "escalation_policy": {"automatic": False, "suggest_when": []},
        })
        try:
            out, rc, _ = run_script("resolve_provider_model.py",
                                    ["--host", "google", "--escalate", "--config", cfg])
            self.assertEqual(rc, 2)
            self.assertEqual(out["errors"][0]["code"], "NO_ESCALATION_MODEL")
        finally:
            os.remove(cfg)


class TestConfigIsSingleSource(unittest.TestCase):
    """The JSON config is the one source; its defaults meet the acceptance bar."""

    def setUp(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            self.config = json.load(fh)

    def test_defaults_are_cost_first(self):
        providers = self.config["providers"]
        for host, model_id in NEW_DEFAULTS.items():
            self.assertEqual(providers[host]["model_id"], model_id)
        self.assertEqual(providers["openai"]["reasoning_effort"], "low")
        self.assertNotIn("reasoning_effort", providers["anthropic"])
        self.assertNotIn("reasoning_effort", providers["google"])

    def test_escalation_models_configured(self):
        providers = self.config["providers"]
        for host, esc in EXPECTED_ESCALATION.items():
            self.assertEqual(providers[host]["escalation_model_id"], esc)
        self.assertFalse(self.config["escalation_policy"]["automatic"])


class TestNoRetiredDefaults(unittest.TestCase):
    """Old default model names must not reappear as active defaults.

    Scoped to the shipped skill (git-worklog/). The historical design docs under
    docs/plans/ are intentionally excluded — they record pre-change plans.
    The escalation ids are permitted ONLY in an escalation context. Retired ids
    must be gone: gemini-3-flash-preview (the 0.3.0 google default) and
    gpt-5.6-luna / gpt-5.6-terra / gemini-3.5-flash (replaced by GPT-6 and
    Gemini 3.8). claude-sonnet-5 cannot be listed — it is a prefix of its
    replacement, claude-sonnet-5-5.
    """

    RETIRED_EVERYWHERE = ["gemini-3-flash-preview", "gpt-5.6-luna", "gpt-5.6-terra",
                          "gemini-3.5-flash"]
    ESCALATION_ONLY = ["claude-sonnet-5-5", "gpt-6.1-sol", "gemini-3.1-pro-preview"]

    def _shipped_files(self):
        for dirpath, _dirs, names in os.walk(SKILL_DIR):
            if "__pycache__" in dirpath:
                continue
            for n in names:
                if n.endswith((".md", ".yaml", ".yml", ".json", ".py")):
                    yield os.path.join(dirpath, n)

    def test_retired_default_fully_absent(self):
        for path in self._shipped_files():
            text = _read(path)
            for token in self.RETIRED_EVERYWHERE:
                self.assertNotIn(
                    token, text,
                    f"retired model {token!r} still present in {path}")

    def test_old_names_only_in_escalation_context(self):
        heading = re.compile(r"^#{1,6}\s+(.*)$")
        for path in self._shipped_files():
            lines = _read(path).splitlines()
            current_heading = ""
            for line in lines:
                m = heading.match(line)
                if m:
                    current_heading = m.group(1).lower()
                for token in self.ESCALATION_ONLY:
                    if token in line:
                        ok = ("escalation" in line.lower()
                              or "escalation" in current_heading)
                        self.assertTrue(
                            ok,
                            f"{token!r} in {path} is not in an escalation context: {line!r}")


class TestHaltTemplateNamesRequestedModel(unittest.TestCase):
    """The user-facing halt-and-ask template names the requested model id."""

    def test_provider_models_doc_has_requested_model_line(self):
        doc = os.path.join(SKILL_DIR, "references", "provider-models.md")
        text = _read(doc)
        self.assertIn("Requested model:", text)
        self.assertIn("No fallback model was selected automatically", text)


class UserHome(unittest.TestCase):
    """Each test gets a home of its own, with no model table in it yet."""

    def setUp(self):
        self.home = os.path.join(tempfile.mkdtemp(prefix="gw_models_"), "state")
        self.addCleanup(shutil.rmtree, os.path.dirname(self.home), True)
        self.env = {"GIT_WORKLOG_HOME": self.home}
        self.table = os.path.join(self.home, "provider_models.json")

    def resolve(self, *args, **env):
        return run_script("resolve_provider_model.py", list(args), env={**self.env, **env})

    def models(self, *args):
        return run_cli("models", *args, env=self.env)

    def edit(self, host: str, **fields) -> None:
        with open(self.table, encoding="utf-8") as fh:
            table = json.load(fh)
        table["providers"][host].update(fields)
        with open(self.table, "w", encoding="utf-8") as fh:
            json.dump(table, fh)


class TestTheUsersModelTable(UserHome):
    """A new model is an edit to the user's file, not a release of the tool."""

    def test_the_first_run_copies_the_shipped_defaults_out(self):
        self.assertFalse(os.path.exists(self.table))
        out, rc, err = self.resolve("--host", "anthropic")
        self.assertEqual(rc, 0, err)
        self.assertEqual((out["model"]["model_id"], out["config_path"]),
                         (NEW_DEFAULTS["anthropic"], self.table))
        # Shipped defaults age, so the moment the file appears the user is asked
        # whether the host has newer models -- once, not on every run after.
        self.assertEqual([(w["code"], w["target"]) for w in out["warnings"]],
                         [("USER_MODELS_CREATED", self.table)])
        self.assertIn("ask the user", out["warnings"][0]["message"])
        again, _, _ = self.resolve("--host", "anthropic")
        self.assertNotIn("warnings", again)
        shipped, seeded = json.loads(_read(CONFIG_PATH)), json.loads(_read(self.table))
        for key in shipped:
            if key != "_comment":
                self.assertEqual(seeded[key], shipped[key], key)
        # The shipped comment calls that file the single source of truth, which
        # the copy is not; the copy's comment is addressed to whoever edits it.
        self.assertNotEqual(seeded["_comment"], shipped["_comment"])
        self.assertIn("This file is yours", seeded["_comment"])

    def test_an_edit_to_the_file_is_what_the_next_run_uses(self):
        self.resolve("--host", "anthropic")
        self.edit("anthropic", model_id="claude-haiku-9", escalation_model_id="claude-sonnet-9")
        out, _, _ = self.resolve("--host", "anthropic")
        self.assertEqual((out["model"]["model_id"], out["model_id_source"]),
                         ("claude-haiku-9", "config"))
        out, _, _ = self.resolve("--host", "anthropic", "--escalate")
        self.assertEqual(out["model"]["model_id"], "claude-sonnet-9")
        # The other hosts were not edited and still resolve.
        out, _, _ = self.resolve("--host", "google")
        self.assertEqual(out["model"]["model_id"], NEW_DEFAULTS["google"])

    def test_the_environment_and_the_flag_still_outrank_the_file(self):
        self.resolve("--host", "openai")
        self.edit("openai", model_id="from-file")
        out, _, _ = self.resolve("--host", "openai", GIT_WORKLOG_OPENAI_MODEL="from-env")
        self.assertEqual((out["model"]["model_id"], out["model_id_source"]), ("from-env", "env"))
        out, _, _ = self.resolve("--host", "openai", "--model", "from-flag",
                                 GIT_WORKLOG_OPENAI_MODEL="from-env")
        self.assertEqual((out["model"]["model_id"], out["model_id_source"]), ("from-flag", "cli"))

    def test_an_existing_file_is_never_rewritten(self):
        os.makedirs(self.home)
        body = '{"providers": {"anthropic": {"model_id": "mine"}},  "kept": [1, 2]}\n'
        with open(self.table, "w", encoding="utf-8") as fh:
            fh.write(body)
        out, rc, _ = self.resolve("--host", "anthropic")
        self.assertEqual((rc, out["model"]["model_id"]), (0, "mine"))
        self.assertEqual(_read(self.table), body)   # byte for byte, spacing included
        # A host the file leaves out is an error, not a reason to read the shipped one.
        out, rc, _ = self.resolve("--host", "google")
        self.assertEqual((rc, out["errors"][0]["code"]), (2, "UNKNOWN_HOST"))

    def test_a_broken_file_stops_the_run_and_is_named(self):
        os.makedirs(self.home)
        for body in ("{ not json", "[]", '{"providers": []}'):
            with self.subTest(body=body):
                with open(self.table, "w", encoding="utf-8") as fh:
                    fh.write(body)
                out, rc, _ = self.resolve("--host", "anthropic")
                self.assertEqual((rc, out["errors"][0]["code"]), (2, "CONFIG_ERROR"))
                self.assertEqual(out["errors"][0]["target"], self.table)
                self.assertEqual(_read(self.table), body)   # reported, not repaired

    def test_a_home_that_cannot_be_written_falls_back_and_says_so(self):
        blocker = os.path.dirname(self.home) + "/file"
        with open(blocker, "w", encoding="utf-8") as fh:
            fh.write("not a directory")
        out, rc, _ = run_script("resolve_provider_model.py", ["--host", "anthropic"],
                                env={"GIT_WORKLOG_HOME": os.path.join(blocker, "state")})
        self.assertEqual((rc, out["model"]["model_id"]), (0, NEW_DEFAULTS["anthropic"]))
        self.assertEqual(out["config_path"], CONFIG_PATH)
        self.assertEqual([w["code"] for w in out["warnings"]], ["USER_MODELS_NOT_WRITTEN"])

    def test_an_explicit_config_is_read_as_given_and_seeds_nothing(self):
        out, rc, _ = self.resolve("--host", "anthropic", "--config", CONFIG_PATH)
        self.assertEqual((rc, out["config_path"]), (0, CONFIG_PATH))
        self.assertFalse(os.path.exists(self.table))

    def test_analyze_prepare_reads_the_same_file(self):
        self.models("--host", "anthropic", "--model", "claude-haiku-9", "--apply")
        out, rc, err = run_cli("analyze", "prepare", "--date", "2026-07-01", "--repo", ROOT,
                               "--host", "anthropic", env=self.env)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out["model"]["model_id"], "claude-haiku-9")


class TestModelsCommand(UserHome):
    """``git-worklog models``: the same edit, as a command an agent can run."""

    def test_with_no_host_it_reports_and_creates_nothing(self):
        out, rc, err = self.models()
        self.assertEqual(rc, 0, err)
        self.assertEqual((out["mode"], out["exists"], out["path"], out["differences"]),
                         ("show", False, self.table, []))
        self.assertIn("does not exist yet", out["note"])
        self.assertEqual(out["providers"]["openai"]["model_id"], NEW_DEFAULTS["openai"])
        self.assertFalse(os.path.exists(self.home))

    def test_a_change_is_shown_first_and_written_only_with_apply(self):
        out, rc, _ = self.models("--host", "anthropic", "--model", "claude-haiku-9")
        self.assertEqual((rc, out["mode"], out["changed"]),
                         (0, "dry-run", ["display_name", "model_id"]))
        self.assertEqual((out["before"]["model_id"], out["after"]["model_id"]),
                         (NEW_DEFAULTS["anthropic"], "claude-haiku-9"))
        self.assertFalse(os.path.exists(self.home))

        out, rc, _ = self.models("--host", "anthropic", "--model", "claude-haiku-9", "--apply")
        self.assertEqual((rc, out["mode"], out["exists"]), (0, "apply", True))
        written = json.loads(_read(self.table))
        self.assertEqual(written["providers"]["anthropic"]["model_id"], "claude-haiku-9")
        # Only the named host and the named field moved.
        self.assertEqual(written["providers"]["anthropic"]["escalation_model_id"],
                         EXPECTED_ESCALATION["anthropic"])
        self.assertEqual(written["providers"]["google"],
                         json.loads(_read(CONFIG_PATH))["providers"]["google"])
        shown, _, _ = self.models()
        self.assertEqual({(d["provider"], d["field"]) for d in shown["differences"]},
                         {("anthropic", "model_id"), ("anthropic", "display_name")})

    def test_the_label_follows_the_model_unless_one_is_given(self):
        # The old model's name on a new model id would be a label that lies.
        out, _, _ = self.models("--host", "anthropic", "--model", "claude-haiku-9")
        self.assertEqual(out["after"]["display_name"], "claude-haiku-9")
        out, _, _ = self.models("--host", "anthropic", "--model", "claude-haiku-9",
                                "--display-name", "Claude Haiku 9")
        self.assertEqual(out["after"]["display_name"], "Claude Haiku 9")
        out, _, _ = self.models("--host", "anthropic", "--escalation-model", "claude-sonnet-9")
        self.assertEqual((out["changed"], out["after"]["display_name"]),
                         (["escalation_model_id"], "Claude Haiku 4.5"))

    def test_it_keeps_what_it_does_not_understand(self):
        os.makedirs(self.home)
        with open(self.table, "w", encoding="utf-8") as fh:
            json.dump({"providers": {"openai": {"model_id": "old", "note": "mine"}},
                       "team": "platform"}, fh)
        self.models("--host", "openai", "--model", "new", "--reasoning-effort", "low",
                    "--escalation-model", "big", "--escalation-reasoning-effort", "medium",
                    "--apply")
        written = json.loads(_read(self.table))
        self.assertEqual(written["team"], "platform")
        self.assertEqual(written["providers"]["openai"],
                         {"model_id": "new", "note": "mine", "display_name": "new",
                          "reasoning_effort": "low", "escalation_model_id": "big",
                          "escalation_reasoning_effort": "medium"})

    def test_what_it_refuses(self):
        for args, code in ((["--model", "x"], "ARG_CONFLICT"),
                           (["--apply"], "ARG_CONFLICT"),
                           (["--host", "anthropic"], "ARG_CONFLICT"),
                           (["--host", "mistral", "--model", "x"], "UNKNOWN_HOST")):
            with self.subTest(args=args):
                out, rc, _ = self.models(*args)
                self.assertEqual((rc, out["errors"][0]["code"]), (2, code))
        self.assertFalse(os.path.exists(self.home))

    def test_doctor_says_where_the_file_stands(self):
        def check():
            out, _, _ = run_cli("doctor", "--repo", ROOT, env=self.env)
            return next(c for c in out["checks"] if c["check"] == "provider_models")

        self.assertEqual(check()["status"], "ok")               # not created yet
        self.resolve("--host", "anthropic")
        self.assertEqual(check()["status"], "ok")               # a fresh copy
        self.models("--host", "google", "--model", "gemini-9-flash", "--apply")
        found = check()
        self.assertEqual(found["status"], "warn")
        self.assertIn({"provider": "google", "field": "model_id",
                       "yours": "gemini-9-flash", "shipped": NEW_DEFAULTS["google"]},
                      found["differences"])
        with open(self.table, "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        self.assertEqual(check()["status"], "fail")


if __name__ == "__main__":
    unittest.main()
