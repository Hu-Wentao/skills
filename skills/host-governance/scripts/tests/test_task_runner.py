#!/usr/bin/env python3
"""Tests for the host-governance contracted task runner."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_NAME = "host-governance"
SOURCE_SKILL = Path(__file__).resolve().parents[2]


class TaskRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="host-governance-runner-")
        self.root = Path(self.temp.name)
        (self.root / ".git").mkdir()
        self.skill = self.root / ".agents" / "skills" / SKILL_NAME
        self.skill.parent.mkdir(parents=True)
        shutil.copytree(SOURCE_SKILL, self.skill)
        self.runner = self.skill / "scripts" / "host-governance.py"
        config_root = self.root / ".agents" / "skills-config" / SKILL_NAME
        config_root.mkdir(parents=True)
        (self.root / "executor.py").write_text(
            "import json, sys\nprint(json.dumps({'schema':'test.host.v1','argv':sys.argv[1:]}))\n",
            encoding="utf-8",
        )
        (config_root / "config.yaml").write_text(
            f"""schema: {SKILL_NAME}.config.v2
profile: runner-test
tasks:
  control:
    base: references/control.md
    contract: control.contract.json
""",
            encoding="utf-8",
        )
        common = {
            "parameters": {
                "target": {
                    "flag": "--target",
                    "type": "string",
                    "required": True,
                    "enum": ["dev", "prod"],
                },
                "force": {
                    "flag": "--force",
                    "type": "boolean",
                    "required": False,
                },
            },
            "output_schema": "test.host.v1",
            "exit_codes": {"0": "ok"},
            "next_states": ["verified"],
        }
        contract = {
            "schema": "host-governance.task-contract.v1",
            "id": "runner.control.v1",
            "task": "control",
            "operations": {
                "inspect": {
                    "description": "Inspect.",
                    "command": [sys.executable, "executor.py", "inspect"],
                    "mutability": "read_only",
                    "authorization": "none",
                    **common,
                },
                "apply": {
                    "description": "Apply.",
                    "command": [sys.executable, "executor.py", "apply"],
                    "mutability": "host_write",
                    "authorization": "current_user",
                    **common,
                },
                "cloudflare-apply": {
                    "description": "Apply a host and Cloudflare transaction.",
                    "command": [sys.executable, "executor.py", "cloudflare-apply"],
                    "mutability": "composite_write",
                    "authorization": "current_user",
                    "environment": {
                        "CLOUDFLARE_API_TOKEN": {
                            "required": True,
                            "sensitive": True,
                        }
                    },
                    **common,
                },
            },
        }
        (config_root / "control.contract.json").write_text(
            json.dumps(contract, indent=2), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def invoke(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.runner), "--cwd", str(self.root), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_executes_read_only_operation_without_authorization(self) -> None:
        result = self.invoke("control", "inspect", "--target", "dev")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["argv"], ["inspect", "--target", "dev"]
        )

    def test_write_operation_requires_current_user_authorization(self) -> None:
        blocked = self.invoke("control", "apply", "--target", "prod")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("requires --authorized", blocked.stderr)
        allowed = self.invoke(
            "--authorized", "control", "apply", "--target", "prod", "--force"
        )
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(
            json.loads(allowed.stdout)["argv"],
            ["apply", "--target", "prod", "--force"],
        )

    def test_execute_form_uses_selected_task_operation(self) -> None:
        result = self.invoke(
            "execute", "--task", "control", "--operation", "inspect", "--target", "dev"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_composite_write_requires_secret_environment_without_exposing_value(self) -> None:
        missing = self.invoke(
            "--authorized", "control", "cloudflare-apply", "--target", "prod"
        )
        self.assertEqual(missing.returncode, 2)
        self.assertIn("CLOUDFLARE_API_TOKEN", missing.stderr)

        environment = os.environ.copy()
        environment["CLOUDFLARE_API_TOKEN"] = "not-printed-test-token"
        allowed = subprocess.run(
            [
                sys.executable,
                str(self.runner),
                "--cwd",
                str(self.root),
                "--authorized",
                "control",
                "cloudflare-apply",
                "--target",
                "prod",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertNotIn("not-printed-test-token", allowed.stdout + allowed.stderr)

    def test_rejects_missing_unknown_and_invalid_arguments(self) -> None:
        missing = self.invoke("control", "inspect")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("missing required", missing.stderr)
        unknown = self.invoke("control", "inspect", "--target", "dev", "--unknown")
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("unsupported operation argument", unknown.stderr)
        invalid = self.invoke("control", "inspect", "--target", "staging")
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("must be one of", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
