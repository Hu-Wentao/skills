#!/usr/bin/env python3
"""Tests for the machine-local PPISS project-segment registry."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


SKILL_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = SKILL_ROOT / "scripts" / "project-segments.py"


class ProjectSegmentsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(
            prefix="project-governance-segments-"
        )
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.project_a = self.make_project("project-a")
        self.project_b = self.make_project("project-b")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_project(self, name: str) -> Path:
        project = self.root / name
        (project / ".git").mkdir(parents=True)
        return project

    def run_script(
        self, *args: str, project: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["HOME"] = str(self.home)
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=project or self.root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    @property
    def registry(self) -> Path:
        return (
            self.home
            / ".agents"
            / "skills-config"
            / "project-governance"
            / "project-segments.yaml"
        )

    def test_allocate_is_sequential_and_idempotent(self) -> None:
        first = self.run_script("allocate", "--cwd", str(self.project_a))
        again = self.run_script("allocate", "--cwd", str(self.project_a))
        second = self.run_script("allocate", "--cwd", str(self.project_b))

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("status: allocated", first.stdout)
        self.assertIn("project_segment: 10", first.stdout)
        self.assertIn("status: existing", again.stdout)
        self.assertIn("project_segment: 10", again.stdout)
        self.assertIn("project_segment: 11", second.stdout)

        document = yaml.safe_load(self.registry.read_text(encoding="utf-8"))
        self.assertEqual(
            document,
            {
                "schema": "project-governance.project-segments.v1",
                "allocations": {
                    str(self.project_a.resolve()): "10",
                    str(self.project_b.resolve()): "11",
                },
            },
        )

    def test_claim_accepts_existing_segment_and_rejects_conflicts(self) -> None:
        claimed = self.run_script(
            "claim", "--cwd", str(self.project_a), "--segment", "42"
        )
        repeated = self.run_script(
            "claim", "--cwd", str(self.project_a), "--segment", "42"
        )
        conflicting_owner = self.run_script(
            "claim", "--cwd", str(self.project_b), "--segment", "42"
        )
        conflicting_segment = self.run_script(
            "claim", "--cwd", str(self.project_a), "--segment", "41"
        )

        self.assertEqual(claimed.returncode, 0, claimed.stderr)
        self.assertIn("status: claimed", claimed.stdout)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertIn("status: existing", repeated.stdout)
        self.assertEqual(conflicting_owner.returncode, 2)
        self.assertIn("already owned", conflicting_owner.stderr)
        self.assertEqual(conflicting_segment.returncode, 2)
        self.assertIn("already owns project segment 42", conflicting_segment.stderr)

    def test_check_is_read_only_and_requires_exact_registration(self) -> None:
        self.run_script("claim", "--cwd", str(self.project_a), "--segment", "17")
        before = self.registry.read_text(encoding="utf-8")
        consistent = self.run_script(
            "check", "--cwd", str(self.project_a), "--segment", "17"
        )
        missing = self.run_script(
            "check", "--cwd", str(self.project_b), "--segment", "18"
        )

        self.assertEqual(consistent.returncode, 0, consistent.stderr)
        self.assertIn("status: consistent", consistent.stdout)
        self.assertEqual(missing.returncode, 2)
        self.assertIn("is not registered", missing.stderr)
        self.assertEqual(self.registry.read_text(encoding="utf-8"), before)

    def test_invalid_or_duplicate_registry_is_rejected(self) -> None:
        self.registry.parent.mkdir(parents=True)
        self.registry.write_text(
            f"""schema: project-governance.project-segments.v1
allocations:
  {self.project_a.resolve()}: "19"
  {self.project_b.resolve()}: "19"
""",
            encoding="utf-8",
        )
        result = self.run_script("list")
        self.assertEqual(result.returncode, 2)
        self.assertIn("assigned to both", result.stderr)

    def test_concurrent_allocations_remain_unique(self) -> None:
        projects = [self.make_project(f"parallel-{index}") for index in range(8)]
        environment = os.environ.copy()
        environment["HOME"] = str(self.home)
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    str(SCRIPT),
                    "allocate",
                    "--cwd",
                    str(project),
                ],
                cwd=project,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for project in projects
        ]
        results = [process.communicate() for process in processes]

        for process, (_, stderr) in zip(processes, results, strict=True):
            self.assertEqual(process.returncode, 0, stderr)
        document = yaml.safe_load(self.registry.read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(document["allocations"].values()),
            [f"{number:02d}" for number in range(10, 18)],
        )

    def test_system_application_segments_are_rejected(self) -> None:
        result = self.run_script(
            "claim", "--cwd", str(self.project_a), "--segment", "09"
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be between 10 and 64", result.stderr)


if __name__ == "__main__":
    unittest.main()
