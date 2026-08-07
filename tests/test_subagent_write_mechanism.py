"""Guards for how a subagent hands its result back: a Bash quoted heredoc.

This is prose with no runtime behind it, and it is the kind of prose that gets
"cleaned up" — a prompt template that spells out one shell command reads like an
implementation detail leaking into a contract. It is not. The Write tool cannot
deliver a subagent's result at all: the call vanishes with no tool result, no
error and no file, and in the subagent's next turn it never happened. The
subagent therefore cannot detect the failure and cannot fall back, so the only
place this can be prevented is the text it is handed. A run that lost a full
day's analysis to exactly this is written up in
`docs/plans/2026-08-07-subagent-file-write-mechanism.md`.

Three things have to survive together, which is why they are tested together:
the *quoted* delimiter (unquoted, the `backticked` symbols §8 requires would be
executed as commands), the explicit ban on the Write tool (without it a model
reaches for the obvious tool and burns its turns on a call that does nothing),
and the self-verification (a malformed result caught in the subagent is
repairable; caught at `collect` the analysis is already gone).
"""

from __future__ import annotations

import os
import unittest

from helpers import ROOT

CONTRACT = os.path.join(
    ROOT, "git-worklog", "references", "subagent-contract.md")
SKILL_MD = os.path.join(ROOT, "git-worklog", "SKILL.md")

DELIMITER = "GIT_WORKLOG_JSON_EOF"
QUOTED_OPENER = "<<'%s'" % DELIMITER


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _flat(text: str) -> str:
    """Whitespace collapsed to single spaces, for phrase assertions.

    These files are hard-wrapped at 80 columns, so any phrase long enough to be
    worth pinning will sooner or later straddle a newline. Asserting on the raw
    text turns a reflow into a false red.
    """
    return " ".join(text.split())


def _section(text: str, heading: str, next_heading: "str | None" = None) -> str:
    """The contract text between two `## ` headings, the latter excluded.

    Scoping matters: a heredoc mentioned anywhere in the file would satisfy a
    whole-file search while the template a subagent is actually handed said
    something else. `next_heading=None` runs to end of file, for the last
    section.
    """
    start = text.index(heading)
    if next_heading is None:
        return text[start:]
    end = text.index(next_heading, start)
    return text[start:end]


def _day_template() -> str:
    return _section(_read(CONTRACT),
                    "## 9. Day Subagent — PROMPT TEMPLATE",
                    "## 10. Code Analysis Subagent — PROMPT TEMPLATE")


def _code_analysis_template() -> str:
    return _section(_read(CONTRACT),
                    "## 10. Code Analysis Subagent — PROMPT TEMPLATE",
                    "## 11. Failure handling")


def _templates() -> "list[tuple[str, str]]":
    return [("§9 Day Subagent", _day_template()),
            ("§10 Code Analysis Subagent", _code_analysis_template())]


class TestBothPromptTemplatesPinTheMechanism(unittest.TestCase):
    def test_the_heredoc_delimiter_is_quoted(self):
        for name, template in _templates():
            with self.subTest(template=name):
                self.assertIn(
                    QUOTED_OPENER, _flat(template),
                    "%s must open its heredoc as %s. Unquoted, the shell runs "
                    "every `backticked` code symbol in the result prose as a "
                    "command and expands $ — and §8 requires that prose to be "
                    "full of them." % (name, QUOTED_OPENER))

    def test_the_delimiter_is_closed_at_column_zero(self):
        for name, template in _templates():
            with self.subTest(template=name):
                self.assertRegex(
                    template, r"(?m)^\s*%s\s*$" % DELIMITER,
                    "%s must show the closing delimiter on a line of its own; "
                    "an indented terminator does not end a heredoc." % name)

    def test_the_write_and_edit_tools_are_banned_outright(self):
        for name, template in _templates():
            with self.subTest(template=name):
                self.assertIn(
                    "MUST NOT use the Write tool or the Edit tool",
                    _flat(template),
                    "%s must ban Write *and* Edit by name. Stating the heredoc "
                    "alone is not enough: the failure is silent, so a model "
                    "that tries Write first loses those turns and learns "
                    "nothing. Edit matters just as much — it is what a subagent "
                    "reaches for to repair a file that failed its own parse "
                    "check, and it vanishes the same way." % name)

    def test_the_repair_is_a_whole_file_rewrite(self):
        # The failure this pins: verification catches a malformed result, the
        # subagent opens Edit to fix the one bad line, the call vanishes, and a
        # day that was one rewrite from correct stalls instead.
        for name, template in _templates():
            with self.subTest(template=name):
                flat = _flat(template)
                self.assertIn("never Edit", flat)
                self.assertRegex(
                    flat, r"(?i)(whole|entire) file again",
                    "%s must say the repair is a whole-file heredoc rewrite, "
                    "not a patch." % name)

    def test_json_string_quotes_must_be_escaped(self):
        # A heredoc passes text through literally, so a raw " inside a JSON
        # string value ends it early. Observed in a real run: the result was
        # 20KB of correct analysis that would not parse.
        for name, template in _templates():
            with self.subTest(template=name):
                self.assertIn(
                    'escaped as \\"', _flat(template),
                    "%s must tell the subagent to escape double quotes inside "
                    "JSON string values." % name)

    def test_the_subagent_verifies_what_it_wrote(self):
        for name, template in _templates():
            with self.subTest(template=name):
                self.assertIn(
                    "json.load(open(", _flat(template),
                    "%s must tell the subagent to parse its own file back. "
                    "A malformed result is repairable there and unrecoverable "
                    "by the time `collect` sees it." % name)

    def test_no_template_asks_only_for_a_generic_file_write(self):
        # The original wording. It named no mechanism, so subagents picked the
        # obvious tool -- which is the bug.
        contract = _flat(_read(CONTRACT))
        self.assertNotIn(
            "MUST be a file write", contract,
            "The contract must not go back to asking for 'a file write' "
            "without naming the mechanism.")


class TestTheRationaleTravelsWithTheRule(unittest.TestCase):
    def test_section_6a_explains_the_mechanism_it_pins(self):
        # §6a is where a maintainer looks before changing the templates. If the
        # reason is not here, the rule reads arbitrary and gets simplified away.
        exchange = _flat(_section(_read(CONTRACT),
                                  "## 6a. Result exchange",
                                  "## 6b. Language"))
        self.assertIn(QUOTED_OPENER, exchange)
        self.assertIn("Write tool", exchange)

    def test_skill_md_names_the_mechanism_and_the_ban(self):
        # §3c is what the orchestrator reads when it dispatches; the contract is
        # a reference it may or may not open.
        skill = _flat(_read(SKILL_MD))
        self.assertIn("Bash quoted heredoc", skill)
        self.assertIn("The Write and Edit tools must not be used", skill)


class TestTheFailedReplyIsDocumented(unittest.TestCase):
    def test_failure_handling_covers_the_failed_reply(self):
        failure = _flat(_section(_read(CONTRACT), "## 11. Failure handling"))
        self.assertIn(
            "FAILED:<date>", failure,
            "§11 must say what a FAILED reply means, since §9 now tells a "
            "subagent to send one.")
        self.assertIn(
            "collect", failure,
            "§11 must keep saying that `collect` is the judge — a FAILED "
            "reply reports, it does not decide.")


if __name__ == "__main__":
    unittest.main()
