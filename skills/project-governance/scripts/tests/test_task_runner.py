#!/usr/bin/env python3
"""Tests for the executable project-governance task contract runner."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[2]
RUNNER = SKILL_ROOT / "scripts" / "project-governance.py"


class TaskRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="project-governance-runner-")
        self.root = Path(self.temp.name)
        (self.root / ".git").mkdir()
        config_root = (
            self.root / ".agents" / "skills-config" / "project-governance"
        )
        config_root.mkdir(parents=True)
        (self.root / "collector.py").write_text(
            "import json,sys\n"
            "print(json.dumps({'schema':'test.evidence.v1','argv':sys.argv[1:]}))\n",
            encoding="utf-8",
        )
        (config_root / "policy.md").write_text("# Policy\n", encoding="utf-8")
        (config_root / "config.yaml").write_text(
            """schema: project-governance.config.v3
profile: test
ports:
  project_segment: "42"
  instances:
    local_dev: 0
    local_e2e: 1
    local_preproduction: 2
    remote_preproduction: 5
    remote_production: 6
  services:
    allocation: sequential
    start: 0
    capacity: 100
    assignments:
      api: 0
      worker: 1
tasks:
  defect-diagnosis:
    base: references/defect-governance.md
    profile: policy.md
    contract: contract.json
  resource-diagnosis:
    base: references/resource-diagnostics.md
    profile: policy.md
    contract: resource-contract.json
  release-deployment:
    base: references/release-deployment.md
    profile: policy.md
    contract: release-contract.json
""",
            encoding="utf-8",
        )
        self.contract_path = config_root / "contract.json"
        self.write_contract("read_only")
        self.resource_contract_path = config_root / "resource-contract.json"
        self.write_resource_contract()
        (config_root / "release-contract.json").write_text(
            json.dumps(
                {
                    "schema": "project-governance.task-contract.v1",
                    "id": "test.release.v1",
                    "task": "release-deployment",
                    "operations": {
                        operation: {
                            "description": f"{operation}.",
                            "command": [sys.executable, "collector.py"],
                            "mutability": mutability,
                            "authorization": (
                                "none"
                                if mutability == "read_only"
                                else "current_user"
                            ),
                            "parameters": {
                                "base_tag": {
                                    "flag": "--base-tag",
                                    "type": "string",
                                    "required": True,
                                    "pattern": "^v[0-9]+\\.[0-9]+\\.[0-9]+$",
                                }
                            },
                            "output_schema": "test.evidence.v1",
                            "exit_codes": {"0": "completed"},
                            "next_states": ["complete"],
                        }
                        for operation, mutability in (
                            ("repair-plan", "read_only"),
                            ("repair", "external_write"),
                            ("hotfix-plan", "read_only"),
                            ("hotfix-qualify", "external_write"),
                            ("hotfix-run", "external_write"),
                        )
                    },
                }
            ),
            encoding="utf-8",
        )

    def write_resource_contract(self) -> None:
        self.resource_contract_path.write_text(
            json.dumps(
                {
                    "schema": "project-governance.task-contract.v1",
                    "id": "test.resource.v1",
                    "task": "resource-diagnosis",
                    "operations": {
                        "collect": {
                            "description": "Collect resource evidence.",
                            "command": [sys.executable, "collector.py"],
                            "mutability": "read_only",
                            "authorization": "none",
                            "parameters": {
                                "target": {
                                    "flag": "--target",
                                    "type": "string",
                                    "required": True,
                                    "enum": ["llm-dev", "llm"],
                                }
                            },
                            "output_schema": "test.evidence.v1",
                            "exit_codes": {"0": "evidence_collected"},
                            "next_states": ["semantic_classification"],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_contract(self, mutability: str) -> None:
        self.contract_path.write_text(
            json.dumps(
                {
                    "schema": "project-governance.task-contract.v1",
                    "id": "test.defect.v1",
                    "task": "defect-diagnosis",
                    "operations": {
                        "collect": {
                            "description": "Collect.",
                            "command": [sys.executable, "collector.py"],
                            "mutability": mutability,
                            "authorization": (
                                "none" if mutability == "read_only" else "current_user"
                            ),
                            "parameters": {
                                "request_id": {
                                    "flag": "--request-id",
                                    "type": "string",
                                    "required": True,
                                    "pattern": "^req_[A-Za-z0-9_-]+$",
                                }
                            },
                            "output_schema": "test.evidence.v1",
                            "exit_codes": {"0": "evidence_collected"},
                            "next_states": ["semantic_classification"],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def invoke(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--cwd",
                str(self.root),
                *args,
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_executes_validated_read_only_operation(self) -> None:
        result = self.invoke("defect", "collect", "--request-id", "req_test")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["argv"], ["--request-id", "req_test"])

    def test_resource_diagnose_alias_executes_read_only_collection(self) -> None:
        result = self.invoke("resource", "diagnose", "--target", "llm")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["argv"], ["--target", "llm"])

    def test_rejects_parameter_outside_contract(self) -> None:
        result = self.invoke("defect", "collect", "--unknown", "value")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unsupported operation argument", result.stderr)

    def test_requires_authorized_gate_for_write(self) -> None:
        self.write_contract("external_write")
        blocked = self.invoke("defect", "collect", "--request-id", "req_test")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("requires --authorized", blocked.stderr)
        allowed = self.invoke(
            "--authorized", "defect", "collect", "--request-id", "req_test"
        )
        self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_executes_release_repair_plan_alias_without_write_authority(self) -> None:
        result = self.invoke("release", "repair-plan", "--base-tag", "v1.2.3")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["argv"], ["--base-tag", "v1.2.3"])

    def test_release_repair_alias_requires_current_write_authority(self) -> None:
        blocked = self.invoke("release", "repair", "--base-tag", "v1.2.3")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("requires --authorized", blocked.stderr)
        allowed = self.invoke(
            "--authorized", "release", "repair", "--base-tag", "v1.2.3"
        )
        self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_release_hotfix_aliases_preserve_plan_qualification_and_run_authority(self) -> None:
        planned = self.invoke("release", "hotfix-plan", "--base-tag", "v1.2.3")
        self.assertEqual(planned.returncode, 0, planned.stderr)
        self.assertEqual(json.loads(planned.stdout)["argv"], ["--base-tag", "v1.2.3"])

        for operation in ("hotfix-qualify", "hotfix-run"):
            blocked = self.invoke("release", operation, "--base-tag", "v1.2.3")
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("requires --authorized", blocked.stderr)
            allowed = self.invoke(
                "--authorized", "release", operation, "--base-tag", "v1.2.3"
            )
            self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_document_maintenance_aliases_preserve_operation_authority(self) -> None:
        inspected = self.invoke("docs", "inspect", "--limit", "1")
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        inspected_report = json.loads(inspected.stdout)
        self.assertEqual(inspected_report["operation"], "inspect")

        blocked = self.invoke("docs", "maintain", "--limit", "1")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("requires --authorized", blocked.stderr)

        allowed = self.invoke(
            "--authorized", "docs", "maintain", "--limit", "1"
        )
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        allowed_report = json.loads(allowed.stdout)
        self.assertEqual(allowed_report["operation"], "maintain")

    def test_docs_audit_is_read_only_maintenance_verification_alias(self) -> None:
        result = self.invoke("docs", "audit")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["schema"], "project-governance.document-audit.v1")

    def test_domain_aliases_preserve_read_and_write_authority(self) -> None:
        inspected = self.invoke("domain", "inspect", "--mode", "catalog")
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        inspected_report = json.loads(inspected.stdout)
        self.assertEqual(inspected_report["operation"], "inspect")
        self.assertEqual(inspected_report["state"], "not_configured")
        self.assertEqual(inspected_report["mode"], "catalog")

        blocked = self.invoke("domain", "maintain", "--mode", "bounded")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("requires --authorized", blocked.stderr)

        allowed = self.invoke(
            "--authorized", "domain", "maintain", "--mode", "bounded"
        )
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        allowed_report = json.loads(allowed.stdout)
        self.assertEqual(allowed_report["operation"], "maintain")
        self.assertEqual(allowed_report["state"], "maintenance_scope_ready")
        self.assertTrue(allowed_report["ready_to_create"])


if __name__ == "__main__":
    unittest.main()
