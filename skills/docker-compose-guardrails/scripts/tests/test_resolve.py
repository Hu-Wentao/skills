#!/usr/bin/env python3
"""Tests for the docker-compose-guardrails project configuration resolver."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_NAME = "docker-compose-guardrails"
SOURCE_SKILL = Path(__file__).resolve().parents[2]


class ResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix=f"{SKILL_NAME}-resolve-")
        self.root = Path(self.temp.name)
        (self.root / ".git").mkdir()
        self.skill = self.root / ".agents" / "skills" / SKILL_NAME
        self.skill.parent.mkdir(parents=True)
        shutil.copytree(SOURCE_SKILL, self.skill)
        self.resolver = self.skill / "scripts" / "resolve.py"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_resolver(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.resolver), "--cwd", str(self.root), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def write_config(self, profile: str = "host-policy.md") -> Path:
        config_root = self.root / ".agents" / "skills-config" / SKILL_NAME
        config_root.mkdir(parents=True)
        (config_root / "config.yaml").write_text(
            f"""schema: {SKILL_NAME}.config.v1
profile: test-host
tasks:
  deploy:
    base: references/deploy.md
    profile: {profile}
    commands:
      preflight: ./ops/check-resource-budget
      verify: ./ops/verify-cgroups
""",
            encoding="utf-8",
        )
        return config_root

    def create_configured_project(
        self, name: str, behavior: str, command: str
    ) -> tuple[Path, Path]:
        root = Path(self.temp.name) / name
        (root / ".git").mkdir(parents=True)
        skill = root / ".agents" / "skills" / SKILL_NAME
        skill.parent.mkdir(parents=True)
        shutil.copytree(SOURCE_SKILL, skill)
        config_root = root / ".agents" / "skills-config" / SKILL_NAME
        config_root.mkdir(parents=True)
        (config_root / "config.yaml").write_text(
            f"""schema: {SKILL_NAME}.config.v1
profile: {name}
tasks:
  deploy:
    base: references/deploy.md
    profile: host-policy.md
    commands:
      preflight: {command}
""",
            encoding="utf-8",
        )
        (config_root / "host-policy.md").write_text(behavior, encoding="utf-8")
        return root, skill / "scripts" / "resolve.py"

    def test_generic_fallback_and_stable_id(self) -> None:
        first = self.run_resolver("--task", "deploy")
        second = self.run_resolver("--task", "deploy")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("profile: generic", first.stdout)
        first_id = next(
            line for line in first.stdout.splitlines() if line.startswith("instructions_id:")
        )
        second_id = next(
            line for line in second.stdout.splitlines() if line.startswith("instructions_id:")
        )
        self.assertEqual(first_id, second_id)

    def test_project_profile_is_composed(self) -> None:
        config_root = self.write_config()
        (config_root / "host-policy.md").write_text(
            "# Host Policy\n\nProtect the gateway with a reviewed minimum.\n",
            encoding="utf-8",
        )
        result = self.run_resolver("--task", "deploy", "--emit", "instructions")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Generic Instructions", result.stdout)
        self.assertIn("## Project Instructions", result.stdout)
        self.assertIn("Protect the gateway", result.stdout)
        self.assertIn("./ops/check-resource-budget", result.stdout)

    def test_same_skill_has_different_behavior_in_two_projects(self) -> None:
        project_a, resolver_a = self.create_configured_project(
            "host-a", "Use host policy A.\n", "preflight-a"
        )
        project_b, resolver_b = self.create_configured_project(
            "host-b", "Use host policy B.\n", "preflight-b"
        )

        def resolve(root: Path, resolver: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, str(resolver), "--cwd", str(root), "--task", "deploy"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )

        result_a = resolve(project_a, resolver_a)
        result_b = resolve(project_b, resolver_b)
        self.assertEqual(result_a.returncode, 0, result_a.stderr)
        self.assertEqual(result_b.returncode, 0, result_b.stderr)
        self.assertIn("profile: host-a", result_a.stdout)
        self.assertIn("profile: host-b", result_b.stdout)
        self.assertIn("preflight: preflight-a", result_a.stdout)
        self.assertIn("preflight: preflight-b", result_b.stdout)

        id_a = next(
            line for line in result_a.stdout.splitlines() if line.startswith("instructions_id:")
        )
        id_b = next(
            line for line in result_b.stdout.splitlines() if line.startswith("instructions_id:")
        )
        self.assertNotEqual(id_a, id_b)

        instructions_a = next(
            line.removeprefix("  path: ")
            for line in result_a.stdout.splitlines()
            if line.startswith("  path: ")
        )
        instructions_b = next(
            line.removeprefix("  path: ")
            for line in result_b.stdout.splitlines()
            if line.startswith("  path: ")
        )
        text_a = (project_a / instructions_a).read_text(encoding="utf-8")
        text_b = (project_b / instructions_b).read_text(encoding="utf-8")
        self.assertIn("Use host policy A.", text_a)
        self.assertNotIn("Use host policy B.", text_a)
        self.assertIn("Use host policy B.", text_b)
        self.assertNotIn("Use host policy A.", text_b)

    def test_invalid_schema_is_rejected(self) -> None:
        config_root = self.write_config()
        config_path = config_root / "config.yaml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                f"{SKILL_NAME}.config.v1", "wrong.config.v1"
            ),
            encoding="utf-8",
        )
        result = self.run_resolver("--task", "deploy")
        self.assertEqual(result.returncode, 2)
        self.assertIn("schema must be", result.stderr)

    def test_missing_configured_task_is_rejected(self) -> None:
        config_root = self.write_config()
        (config_root / "host-policy.md").write_text(
            "# Host Policy\n", encoding="utf-8"
        )
        result = self.run_resolver("--task", "not-configured")
        self.assertEqual(result.returncode, 2)
        self.assertIn("tasks.not-configured must be a mapping", result.stderr)

    def test_profile_path_escape_is_rejected(self) -> None:
        self.write_config("../../outside.md")
        (self.root / ".agents" / "outside.md").write_text(
            "outside", encoding="utf-8"
        )
        result = self.run_resolver("--task", "deploy")
        self.assertEqual(result.returncode, 2)
        self.assertIn("escapes its allowed root", result.stderr)


if __name__ == "__main__":
    unittest.main()
