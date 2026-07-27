"""Guards for the two things that make this skill user-invoked, and only that.

Both of them are static text with no runtime behaviour behind them, so nothing
else in the suite would notice if they were undone:

* ``disable-model-invocation: true`` in the SKILL.md frontmatter is the entire
  mechanism. Delete that one line and the skill silently goes back to being
  auto-triggered during unrelated work — no error, no failing command, no
  visible difference until it fires when nobody asked.

* The no-argument menu exists twice on purpose. SKILL.md holds the copy the model
  prints; ``agents/openai.yaml`` holds the copy a non-Claude host reads as data,
  which is why it cannot be replaced by a cross-reference. The two were already
  drifting before this test existed — same options, different blank lines — and a
  third copy in ``references/interaction-flow.md`` was removed in 1.1.0 for the
  same reason.

Menu *language* is deliberately not asserted. A menu translated back to zh-TW is
a loud failure — you see it on the next invocation — and a rule that overlaps
with the drift check below would only add false reds.
"""

from __future__ import annotations

import os
import re
import unittest

from helpers import ROOT

SKILL_MD = os.path.join(ROOT, "git-worklog", "SKILL.md")
OPENAI_YAML = os.path.join(ROOT, "git-worklog", "agents", "openai.yaml")
INTERACTION_FLOW = os.path.join(
    ROOT, "git-worklog", "references", "interaction-flow.md")

# A numbered menu row: leading spaces (10 and 11 are right-aligned), the number,
# a dot, then the label. Matching on the row rather than the whole block is what
# lets the two copies keep their own framing -- SKILL.md fences its copy, the
# YAML indents its under `default_prompt: |` -- while still failing if an option
# is added, dropped, renumbered or reworded in one place only.
_OPTION = re.compile(r"^\s*(\d+)\.\s+(\S.*?)\s*$")

EXPECTED_OPTION_COUNT = 11


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _frontmatter(text: str) -> "dict[str, str]":
    """The SKILL.md frontmatter as flat key -> value, without a YAML library.

    Only handles the scalar one-line form, which is all this frontmatter uses
    since 1.1.0 dropped the folded `description: >-` block.
    """
    if not text.startswith("---\n"):
        raise AssertionError("SKILL.md does not open with a frontmatter fence")
    end = text.index("\n---\n", 3)
    fields = {}
    for line in text[4:end].split("\n"):
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _menu_options(text: str) -> "list[tuple[str, str]]":
    """Every numbered option row in a menu copy, in order.

    Scoped to the region between the menu's first and last line so a numbered
    list elsewhere in the file cannot be mistaken for a menu row.
    """
    start = text.index("Choose what to do:")
    end = text.index("Reply with an option number", start)
    rows = []
    for line in text[start:end].split("\n"):
        m = _OPTION.match(line)
        if m:
            rows.append((m.group(1), m.group(2)))
    return rows


class TestTheSkillIsUserInvoked(unittest.TestCase):
    def test_frontmatter_disables_model_invocation(self):
        fields = _frontmatter(_read(SKILL_MD))
        self.assertEqual(
            fields.get("disable-model-invocation"), "true",
            "SKILL.md must keep `disable-model-invocation: true` — it is the "
            "only thing stopping the skill from being auto-triggered during "
            "unrelated development work, and removing it fails nothing else.")

    def test_frontmatter_offers_an_argument_hint(self):
        fields = _frontmatter(_read(SKILL_MD))
        self.assertIn(
            "argument-hint", fields,
            "A user-invoked skill has to say what it accepts on the invocation "
            "line; without the hint the menu is the only way to discover it.")
        self.assertTrue(fields["argument-hint"].strip())

    def test_the_description_is_one_short_line(self):
        # With model invocation off, the description is no longer matched against
        # anything -- it is the line a user reads in the slash-command picker,
        # which shows one line. The old trigger-keyword blob was 12 lines.
        fields = _frontmatter(_read(SKILL_MD))
        self.assertNotIn(
            ">-", fields["description"],
            "description should be a plain one-liner, not a folded block")
        self.assertLessEqual(len(fields["description"]), 120)


class TestTheMenuCopiesAgree(unittest.TestCase):
    def test_skill_md_and_openai_yaml_list_the_same_options(self):
        skill = _menu_options(_read(SKILL_MD))
        manifest = _menu_options(_read(OPENAI_YAML))
        self.assertEqual(
            skill, manifest,
            "The menu in SKILL.md §1 and agents/openai.yaml's default_prompt "
            "have drifted. The YAML copy cannot be a cross-reference (a host "
            "reads it as data), so both move together or neither does.")

    def test_both_copies_carry_every_option(self):
        # Pins the count as well as the text: a silently dropped trailing row
        # would otherwise agree with itself in both files.
        for path in (SKILL_MD, OPENAI_YAML):
            with self.subTest(path=os.path.basename(path)):
                self.assertEqual(
                    len(_menu_options(_read(path))), EXPECTED_OPTION_COUNT)

    def test_options_are_numbered_one_to_eleven_in_order(self):
        numbers = [n for n, _ in _menu_options(_read(SKILL_MD))]
        self.assertEqual(
            numbers, [str(i) for i in range(1, EXPECTED_OPTION_COUNT + 1)])

    def test_interaction_flow_does_not_reintroduce_a_third_copy(self):
        # The third copy is how the drift started. It is now a cross-reference,
        # and this is what stops someone helpfully pasting it back.
        text = _read(INTERACTION_FLOW)
        self.assertNotIn(
            "Choose what to do:", text,
            "references/interaction-flow.md must point at SKILL.md §1 for the "
            "menu text rather than holding a copy of it.")
        self.assertIn("SKILL.md` §1", text)


if __name__ == "__main__":
    unittest.main()
