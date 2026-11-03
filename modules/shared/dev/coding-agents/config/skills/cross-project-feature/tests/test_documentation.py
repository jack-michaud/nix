"""Offline documentation contracts; no access to private boards or live services."""
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
DOCUMENT = (SKILL / "SKILL.md").read_text()
CASE = DOCUMENT.split("## Case study:", 1)[1].split("## Acceptance checklist", 1)[0]


class DocumentationTest(unittest.TestCase):
    def test_portable_unique_metadata(self):
        header = DOCUMENT.split("---", 2)[1]
        fields = dict(line.split(": ", 1) for line in header.strip().splitlines())
        self.assertEqual(fields["name"], SKILL.name)
        self.assertRegex(fields["name"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        self.assertLessEqual(len(fields["name"]), 64)
        self.assertTrue(1 <= len(fields["description"]) <= 1024)
        self.assertIn("Use for", fields["description"])
        names = []
        for path in SKILL.parent.glob("*/SKILL.md"):
            match = re.search(r"^name: (.+)$", path.read_text(), re.M)
            if match:
                names.append(match[1])
        self.assertEqual(names.count(fields["name"]), 1)

    def test_local_check_references_exist(self):
        for relative in (
            "../../../default.nix",
            "tests/test_skill_discovery.mjs",
            "tests/_test_distribution.nix",
        ):
            self.assertTrue((SKILL / relative).is_file(), relative)
            self.assertIn(relative, DOCUMENT)
        for target in re.findall(r"\]\(([^)]+)\)", DOCUMENT):
            self.assertTrue(target.startswith("https://") or (SKILL / target).exists(), target)

    def test_case_is_separate_from_reusable_instructions(self):
        reusable = DOCUMENT.split("## Case study:", 1)[0]
        self.assertNotIn("/v1/transcription/words", reusable)
        self.assertNotIn("0.14.0", reusable)
        for task in ("jack/5", "jack/6", "IND-1", "APC-2", "APC-3",
                     "JMS-110", "JMS-120", "JMS-121", "FLS-13"):
            self.assertIn(task, CASE)
        for identity in (
            "bb5d0c09249306ce86079dd1e97650486cede166",
            "3fc31d44fdcbad83dcae5bdd3c353575665d9fcc",
            "92e2c1d345b5ff659c51d3a83171d55c645fbdfd",
            "47b85fe7f893a6e270c8d5a0318ad9e51332c09a",
            "3417eba8d2a6dd49dea4c3055f5643e27d12aec0",
            "5143ccf12b8cd29b7d0b9891d5af0a45cb5d30b8",
            "1ea1965ff08a48c3d3a523a3e3d6f9b7beb4e964",
        ):
            self.assertIn(identity, CASE)

    def test_authority_and_delivery_limits_stay_explicit(self):
        plain = re.sub(r"\s+", " ", DOCUMENT)
        for required in (
            "templates, NOT previously sent messages",
            "Please feel free to start the tasks you've created.",
            "no task agents delegated/started",
            "No sends were made by this documentation task.",
            "Not established:",
            "JMS-121 delete UI installation",
            "not live feature success",
            "not a merge gate",
            "no automatic retries",
            "move first",
        ):
            self.assertIn(required, plain)
        self.assertIn("four-part", DOCUMENT)
        self.assertIn("Do not broaden distribution", DOCUMENT)
        self.assertIn("not activation or a full host build", plain)


if __name__ == "__main__":
    unittest.main()
