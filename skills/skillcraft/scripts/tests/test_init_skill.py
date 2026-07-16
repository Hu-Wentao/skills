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


if __name__ == "__main__":
    unittest.main()
