#!/usr/bin/env python3
"""Regression tests for Skillcraft reusable-boundary validation."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from quick_validate import validate_skill  # noqa: E402


class QuickValidateTest(unittest.TestCase):
    def test_validator_requires_uv_script_execution(self) -> None:
        source = (SCRIPTS / "quick_validate.py").read_text(encoding="utf-8")

        self.assertTrue(source.startswith("#!/usr/bin/env -S uv run --script\n"))
        self.assertIn('#   "PyYAML>=6,<7",', source)
        self.assertIn(
            "Usage: uv run --script quick_validate.py <skill_directory>",
            source,
        )

    def write_skill(self, root: Path, resolver: str) -> Path:
        skill = root / "example-skill"
        (skill / "references").mkdir(parents=True)
        (skill / "scripts").mkdir()
        (skill / "SKILL.md").write_text(
            "---\n"
            "name: example-skill\n"
            "description: Exercise project configuration validation.\n"
            "---\n\n"
            "# Example Skill\n",
            encoding="utf-8",
        )
        (skill / "references/project_config.md").write_text(
            "# Project Configuration\n", encoding="utf-8"
        )
        (skill / "scripts/resolve.py").write_text(resolver, encoding="utf-8")
        return skill

    def test_rejects_literal_project_profile_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = self.write_skill(
                Path(temporary),
                "profile = 'generic'\n"
                "if profile == 'customer-a':\n"
                "    print('customer behavior')\n",
            )
            valid, message = validate_skill(skill)

        self.assertFalse(valid)
        self.assertIn("branches on a concrete project profile", message)
        self.assertIn("skills-config/example-skill", message)

    def test_accepts_profile_as_opaque_manifest_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = self.write_skill(
                Path(temporary),
                "profile = load_config().get('profile', 'generic')\n"
                "print(f'profile: {profile}')\n",
            )
            valid, message = validate_skill(skill)

        self.assertTrue(valid, message)


if __name__ == "__main__":
    unittest.main()
