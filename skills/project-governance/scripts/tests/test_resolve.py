#!/usr/bin/env python3
"""Tests for the project-governance project configuration resolver."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_NAME = "project-governance"
SOURCE_SKILL = Path(__file__).resolve().parents[2]
SOURCE_RESOLVER = SOURCE_SKILL / "scripts" / "resolve.py"


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

    def run_resolver(
        self, *args: str, root: Path | None = None, resolver: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        selected_root = root or self.root
        selected_resolver = resolver or self.resolver
        return subprocess.run(
            [
                sys.executable,
                str(selected_resolver),
                "--cwd",
                str(selected_root),
                *args,
            ],
            cwd=selected_root,
            capture_output=True,
            text=True,
            check=False,
        )

    def write_config(
        self,
        root: Path | None = None,
        *,
        task: str = "defect-diagnosis",
        profile: str = "project.md",
        command: str = "uv run python -m unittest",
    ) -> Path:
        selected_root = root or self.root
        config_root = selected_root / ".agents" / "skills-config" / SKILL_NAME
        config_root.mkdir(parents=True)
        (config_root / "config.yaml").write_text(
            f"""schema: {SKILL_NAME}.config.v1
profile: {selected_root.name}
tasks:
  {task}:
    base: references/defect-governance.md
    profile: {profile}
    commands:
      validate: {command}
""",
            encoding="utf-8",
        )
        return config_root

    def configured_project(
        self, name: str, behavior: str, command: str
    ) -> Path:
        root = Path(self.temp.name) / name
        (root / ".git").mkdir(parents=True)
        config_root = self.write_config(root, command=command)
        (config_root / "project.md").write_text(behavior, encoding="utf-8")
        return root

    def test_generic_fallback_and_stable_id_for_both_tasks(self) -> None:
        for task in ("defect-diagnosis", "defect-history-review"):
            first = self.run_resolver("--task", task)
            second = self.run_resolver("--task", task)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("profile: generic", first.stdout)
            first_id = next(
                line
                for line in first.stdout.splitlines()
                if line.startswith("instructions_id:")
            )
            second_id = next(
                line
                for line in second.stdout.splitlines()
                if line.startswith("instructions_id:")
            )
            self.assertEqual(first_id, second_id)

    def test_project_profile_is_composed(self) -> None:
        config_root = self.write_config()
        (config_root / "project.md").write_text(
            "# Repository Rules\n\nUse the project history source.\n",
            encoding="utf-8",
        )
        result = self.run_resolver(
            "--task", "defect-diagnosis", "--emit", "instructions"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Generic Instructions", result.stdout)
        self.assertIn("## Project Instructions", result.stdout)
        self.assertIn("Use the project history source.", result.stdout)
        self.assertIn("uv run python -m unittest", result.stdout)

    def test_same_installed_skill_differs_across_two_projects(self) -> None:
        project_a = self.configured_project("project-a", "Use behavior A.\n", "validate-a")
        project_b = self.configured_project("project-b", "Use behavior B.\n", "validate-b")

        result_a = self.run_resolver(
            "--task", "defect-diagnosis", root=project_a, resolver=SOURCE_RESOLVER
        )
        result_b = self.run_resolver(
            "--task", "defect-diagnosis", root=project_b, resolver=SOURCE_RESOLVER
        )
        self.assertEqual(result_a.returncode, 0, result_a.stderr)
        self.assertEqual(result_b.returncode, 0, result_b.stderr)
        self.assertIn("profile: project-a", result_a.stdout)
        self.assertIn("profile: project-b", result_b.stdout)
        self.assertIn("validate: validate-a", result_a.stdout)
        self.assertIn("validate: validate-b", result_b.stdout)

        id_a = next(
            line for line in result_a.stdout.splitlines() if line.startswith("instructions_id:")
        )
        id_b = next(
            line for line in result_b.stdout.splitlines() if line.startswith("instructions_id:")
        )
        self.assertNotEqual(id_a, id_b)

        path_a = next(
            line.removeprefix("  path: ")
            for line in result_a.stdout.splitlines()
            if line.startswith("  path: ")
        )
        path_b = next(
            line.removeprefix("  path: ")
            for line in result_b.stdout.splitlines()
            if line.startswith("  path: ")
        )
        text_a = (project_a / path_a).read_text(encoding="utf-8")
        text_b = (project_b / path_b).read_text(encoding="utf-8")
        self.assertIn("Use behavior A.", text_a)
        self.assertNotIn("Use behavior B.", text_a)
        self.assertIn("Use behavior B.", text_b)
        self.assertNotIn("Use behavior A.", text_b)

    def test_source_or_global_resolver_uses_its_own_skill_root(self) -> None:
        config_root = self.write_config()
        (config_root / "project.md").write_text("Use external install.\n", encoding="utf-8")
        result = self.run_resolver(
            "--task", "defect-diagnosis", resolver=SOURCE_RESOLVER
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(SOURCE_SKILL / "references" / "defect-governance.md"), result.stdout)

    def test_invalid_schema_is_rejected(self) -> None:
        config_root = self.write_config()
        config_path = config_root / "config.yaml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                f"{SKILL_NAME}.config.v1", "wrong.config.v1"
            ),
            encoding="utf-8",
        )
        result = self.run_resolver("--task", "defect-diagnosis")
        self.assertEqual(result.returncode, 2)
        self.assertIn("schema must be", result.stderr)

    def test_missing_configured_task_is_rejected(self) -> None:
        config_root = self.write_config()
        (config_root / "project.md").write_text("rules\n", encoding="utf-8")
        result = self.run_resolver("--task", "defect-history-review")
        self.assertEqual(result.returncode, 2)
        self.assertIn("tasks.defect-history-review must be a mapping", result.stderr)

    def test_profile_path_escape_is_rejected(self) -> None:
        self.write_config(profile="../../outside.md")
        (self.root / ".agents" / "outside.md").write_text("outside", encoding="utf-8")
        result = self.run_resolver("--task", "defect-diagnosis")
        self.assertEqual(result.returncode, 2)
        self.assertIn("escapes its allowed root", result.stderr)

    def test_base_path_escape_is_rejected(self) -> None:
        config_root = self.write_config()
        config_path = config_root / "config.yaml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                "references/defect-governance.md", "../../outside.md"
            ),
            encoding="utf-8",
        )
        result = self.run_resolver("--task", "defect-diagnosis")
        self.assertEqual(result.returncode, 2)
        self.assertIn("escapes its allowed root", result.stderr)

    def test_unknown_config_key_is_rejected(self) -> None:
        config_root = self.write_config()
        config_path = config_root / "config.yaml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8") + "unexpected: true\n",
            encoding="utf-8",
        )
        result = self.run_resolver("--task", "defect-diagnosis")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unsupported key", result.stderr)


if __name__ == "__main__":
    unittest.main()
