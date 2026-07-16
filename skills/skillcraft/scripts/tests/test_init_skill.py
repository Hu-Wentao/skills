#!/usr/bin/env python3
"""Integration tests for Skillcraft initialization."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SKILL_ROOT = TEST_DIR.parents[1]
INIT_SCRIPT = SKILL_ROOT / "scripts" / "init_skill.py"


class InitSkillTest(unittest.TestCase):
    def test_project_config_scaffold_and_resolver_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skillcraft-init-") as raw_root:
            root = Path(raw_root)
            repo = root / "repo"
            skills_root = repo / ".agents" / "skills"
            skills_root.mkdir(parents=True)
            (repo / ".git").mkdir()

            initialized = subprocess.run(
                [
                    sys.executable,
                    str(INIT_SCRIPT),
                    "demo-skill",
                    "--path",
                    str(skills_root),
                    "--project-config",
                    "--interface",
                    "display_name=Demo Skill",
                    "--interface",
                    "short_description=Demonstrate project configuration",
                    "--interface",
                    "default_prompt=Use $demo-skill to demonstrate configuration.",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                initialized.returncode,
                0,
                msg=initialized.stdout + initialized.stderr,
            )

            skill = skills_root / "demo-skill"
            expected = (
                skill / "scripts" / "resolve.py",
                skill / "scripts" / "tests" / "test_resolve.py",
                skill / "references" / "default.md",
                skill / "references" / "project_config.md",
            )
            self.assertTrue(all(path.is_file() for path in expected), expected)
            skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("## Resolve Project Behavior", skill_text)
            self.assertIn(
                ".agents/skills/demo-skill/scripts/resolve.py --task <task>",
                skill_text,
            )
            self.assertIn("same reusable skill can behave differently", skill_text)

            generic = subprocess.run(
                [
                    sys.executable,
                    str(skill / "scripts" / "resolve.py"),
                    "--cwd",
                    str(repo),
                    "--task",
                    "default",
                ],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(generic.returncode, 0, generic.stderr)
            self.assertIn("profile: generic", generic.stdout)

            generated_tests = subprocess.run(
                [
                    sys.executable,
                    str(skill / "scripts" / "tests" / "test_resolve.py"),
                ],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                generated_tests.returncode,
                0,
                msg=generated_tests.stdout + generated_tests.stderr,
            )
            self.assertIn("Ran 6 tests", generated_tests.stderr)

    def test_plain_scaffold_replaces_skill_creator_behavior(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skillcraft-plain-") as raw_root:
            output = Path(raw_root) / "skills"
            output.mkdir()
            initialized = subprocess.run(
                [
                    sys.executable,
                    str(INIT_SCRIPT),
                    "Plain Skill",
                    "--path",
                    str(output),
                    "--resources",
                    "scripts,references,assets",
                    "--examples",
                    "--interface",
                    "display_name=Plain Skill",
                    "--interface",
                    "short_description=Create a plain reusable skill",
                    "--interface",
                    "default_prompt=Use $plain-skill for a plain task.",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                initialized.returncode,
                0,
                msg=initialized.stdout + initialized.stderr,
            )
            skill = output / "plain-skill"
            self.assertIn(
                "Normalized skill name from 'Plain Skill' to 'plain-skill'",
                initialized.stdout,
            )
            self.assertTrue((skill / "scripts" / "example.py").is_file())
            self.assertTrue((skill / "references" / "api_reference.md").is_file())
            self.assertTrue((skill / "assets" / "example_asset.txt").is_file())
            openai_yaml = (skill / "agents" / "openai.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn('display_name: "Plain Skill"', openai_yaml)
            self.assertIn('short_description: "Create a plain reusable skill"', openai_yaml)
            self.assertFalse((skill / "scripts" / "resolve.py").exists())
            self.assertFalse((skill / "references" / "project_config.md").exists())
            self.assertNotIn(
                "## Resolve Project Behavior",
                (skill / "SKILL.md").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
