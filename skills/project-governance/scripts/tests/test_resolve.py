#!/usr/bin/env python3
"""Tests for the project-governance project configuration resolver."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
import json
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

    def write_port_config(self) -> Path:
        config_root = self.root / ".agents" / "skills-config" / SKILL_NAME
        config_root.mkdir(parents=True, exist_ok=True)
        (config_root / "config.yaml").write_text(
            f"""schema: {SKILL_NAME}.config.v2
profile: test-project
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
  defect-history-review:
    base: references/defect-governance.md
  port-allocation:
    base: references/port-allocation.md
""",
            encoding="utf-8",
        )
        return config_root

    def write_v3_config(self, *, mutability: str = "read_only") -> Path:
        config_root = self.root / ".agents" / "skills-config" / SKILL_NAME
        config_root.mkdir(parents=True, exist_ok=True)
        (self.root / "collect.py").write_text(
            "import json\nprint(json.dumps({'schema': 'test.evidence.v1'}))\n",
            encoding="utf-8",
        )
        (config_root / "config.yaml").write_text(
            f"""schema: {SKILL_NAME}.config.v3
profile: test-project
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
    profile: project.md
    contract: defect.contract.json
""",
            encoding="utf-8",
        )
        (config_root / "project.md").write_text(
            "# Project Defect Policy\n", encoding="utf-8"
        )
        (config_root / "defect.contract.json").write_text(
            json.dumps(
                {
                    "schema": "project-governance.task-contract.v1",
                    "id": "test.defect.v1",
                    "task": "defect-diagnosis",
                    "operations": {
                        "collect": {
                            "description": "Collect evidence.",
                            "command": [sys.executable, "collect.py"],
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
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return config_root

    def test_v3_config_requires_ppiss_ports(self) -> None:
        config_root = self.write_v3_config()
        config_path = config_root / "config.yaml"
        text = config_path.read_text(encoding="utf-8")
        start = text.index("ports:\n")
        end = text.index("tasks:\n")
        config_path.write_text(text[:start] + text[end:], encoding="utf-8")

        result = self.run_resolver("--task", "defect-diagnosis")

        self.assertEqual(result.returncode, 2)
        self.assertIn("ports must be a mapping", result.stderr)

    def test_generic_fallback_and_stable_id_for_both_tasks(self) -> None:
        for task in (
            "defect-feedback-lifecycle",
            "defect-diagnosis",
            "defect-history-review",
            "document-audit",
            "document-maintenance",
            "domain-knowledge",
            "port-allocation",
            "release-deployment",
        ):
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

    def test_v3_returns_small_json_contract_without_composed_policy(self) -> None:
        self.write_v3_config()
        result = self.run_resolver(
            "--task", "defect-diagnosis", "--format", "json"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(result.stdout)
        self.assertEqual(manifest["state"], "resolved")
        self.assertEqual(
            manifest["contract"]["operations"]["collect"]["mutability"],
            "read_only",
        )
        self.assertEqual(
            manifest["contract"]["operations"]["collect"]["output_schema"],
            "test.evidence.v1",
        )
        self.assertIn("policy_refs", manifest)
        self.assertNotIn("Generic Instructions", result.stdout)
        self.assertNotIn("state_path", manifest)
        self.assertFalse(
            (
                self.root
                / ".agents"
                / ".cache"
                / "project-governance"
                / "defect-diagnosis"
            ).exists()
        )

        selected = self.run_resolver(
            "--task",
            "defect-diagnosis",
            "--operation",
            "collect",
            "--format",
            "json",
        )
        self.assertEqual(selected.returncode, 0, selected.stderr)
        selected_manifest = json.loads(selected.stdout)
        self.assertEqual(selected_manifest["selected_operation"], "collect")
        self.assertEqual(
            list(selected_manifest["contract"]["operations"]), ["collect"]
        )
        self.assertEqual(selected_manifest["entry_command"][-1], "collect")

    def test_missing_release_task_uses_managed_contract_instead_of_mapping_error(self) -> None:
        self.write_port_config()
        result = self.run_resolver(
            "--task", "release-deployment", "--format", "json"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(result.stdout)
        self.assertEqual(manifest["workflow"]["mode"], "managed")
        self.assertEqual(
            manifest["workflow"]["configuration"], "bootstrap_required"
        )
        self.assertEqual(
            manifest["contract"]["id"],
            "project-governance.release-deployment.managed.v1",
        )
        self.assertIn("prepare", manifest["contract"]["operations"])
        self.assertIn("promote-plan", manifest["contract"]["operations"])
        self.assertIn("promote", manifest["contract"]["operations"])

    def test_missing_document_maintenance_task_uses_managed_contract(self) -> None:
        self.write_port_config()
        result = self.run_resolver(
            "--task", "document-maintenance", "--format", "json"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(result.stdout)
        self.assertEqual(manifest["workflow"]["mode"], "managed")
        self.assertEqual(
            manifest["workflow"]["configuration"], "project_defaults"
        )
        self.assertEqual(
            manifest["contract"]["id"],
            "project-governance.document-maintenance.managed.v1",
        )
        self.assertEqual(
            manifest["contract"]["operations"]["maintain"]["mutability"],
            "repository_write",
        )
        self.assertEqual(
            manifest["contract"]["operations"]["verify"]["mutability"],
            "read_only",
        )

    def test_missing_domain_knowledge_task_uses_managed_contract(self) -> None:
        self.write_port_config()
        result = self.run_resolver(
            "--task", "domain-knowledge", "--format", "json"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(result.stdout)
        self.assertEqual(manifest["workflow"]["mode"], "managed")
        self.assertEqual(
            manifest["workflow"]["configuration"], "project_defaults"
        )
        self.assertEqual(
            manifest["contract"]["id"],
            "project-governance.domain-knowledge.managed.v1",
        )
        self.assertEqual(
            set(manifest["contract"]["operations"]),
            {"inspect", "get", "search", "plan", "maintain", "verify"},
        )
        self.assertEqual(
            manifest["contract"]["operations"]["maintain"]["mutability"],
            "repository_write",
        )
        self.assertEqual(
            manifest["contract"]["operations"]["inspect"]["parameters"]["mode"][
                "enum"
            ],
            ["lite", "catalog", "bounded"],
        )

    def test_v3_rejects_missing_executor(self) -> None:
        config_root = self.write_v3_config()
        contract_path = config_root / "defect.contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["operations"]["collect"]["command"] = [
            sys.executable,
            "missing.py",
        ]
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        result = self.run_resolver("--task", "defect-diagnosis")
        self.assertEqual(result.returncode, 2)
        self.assertIn("script not found", result.stderr)

    def test_v3_rejects_write_without_current_user_authorization(self) -> None:
        config_root = self.write_v3_config(mutability="external_write")
        contract_path = config_root / "defect.contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["operations"]["collect"]["authorization"] = "none"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        result = self.run_resolver("--task", "defect-diagnosis")
        self.assertEqual(result.returncode, 2)
        self.assertIn("must require current_user authorization", result.stderr)

    def test_release_deployment_profile_is_composed_with_commands_and_tags(self) -> None:
        config_root = self.write_config(
            task="release-deployment",
            profile="release.md",
            command="node ops/deployment/release-deploy.mjs",
        )
        config_path = config_root / "config.yaml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                "references/defect-governance.md",
                "references/release-deployment.md",
            ),
            encoding="utf-8",
        )
        (config_root / "release.md").write_text(
            "# Repository Release Rules\n\nUse preproduction before production.\n",
            encoding="utf-8",
        )

        result = self.run_resolver(
            "--task", "release-deployment", "--emit", "instructions"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        normalized = " ".join(result.stdout.split())
        self.assertIn("deploy/<target>/<UTC timestamp>/v<version>", result.stdout)
        self.assertIn(
            "inspect the resolved task contract and project profile for every declared",
            normalized,
        )
        self.assertIn(
            "When no stable tag or artifact manifest exists",
            normalized,
        )
        self.assertIn("Use preproduction before production.", result.stdout)
        self.assertIn("node ops/deployment/release-deploy.mjs", result.stdout)

    def test_defect_feedback_profile_is_composed(self) -> None:
        config_root = self.write_config(
            task="defect-feedback-lifecycle",
            profile="feedback.md",
            command="feedback audit",
        )
        config_path = config_root / "config.yaml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                "references/defect-governance.md",
                "references/defect-feedback-lifecycle.md",
            ),
            encoding="utf-8",
        )
        (config_root / "feedback.md").write_text(
            "# Repository Feedback Rules\n\nUse the product-owned reward workflow.\n",
            encoding="utf-8",
        )

        result = self.run_resolver(
            "--task", "defect-feedback-lifecycle", "--emit", "instructions"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Treat a collaboration tracker as a projection", result.stdout)
        self.assertIn("Use the product-owned reward workflow.", result.stdout)
        self.assertIn("feedback audit", result.stdout)

    def test_supported_sibling_task_does_not_block_release_resolution(self) -> None:
        config_root = self.root / ".agents" / "skills-config" / SKILL_NAME
        config_root.mkdir(parents=True)
        (config_root / "config.yaml").write_text(
            f"""schema: {SKILL_NAME}.config.v1
profile: test-project
tasks:
  defect-feedback-lifecycle:
    base: references/defect-feedback-lifecycle.md
    profile: feedback.md
  release-deployment:
    base: references/release-deployment.md
    profile: release.md
""",
            encoding="utf-8",
        )
        (config_root / "feedback.md").write_text("Feedback profile.\n", encoding="utf-8")
        (config_root / "release.md").write_text("Release profile.\n", encoding="utf-8")

        result = self.run_resolver("--task", "release-deployment")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("task: release-deployment", result.stdout)

    def test_port_config_is_validated_and_rendered(self) -> None:
        self.write_port_config()
        result = self.run_resolver(
            "--task", "port-allocation", "--emit", "instructions"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Resolved Port Allocation", result.stdout)
        self.assertIn("| local_dev | 0 | api | 00 | 42000 |", result.stdout)
        self.assertIn(
            "| remote_production | 6 | worker | 01 | 42601 |", result.stdout
        )

    def test_v1_config_cannot_configure_ports(self) -> None:
        self.write_config()
        result = self.run_resolver("--task", "port-allocation")
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires project-governance.config.v2", result.stderr)

    def test_port_service_ids_must_be_sequential(self) -> None:
        config_root = self.write_port_config()
        config_path = config_root / "config.yaml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace("worker: 1", "worker: 2"),
            encoding="utf-8",
        )
        result = self.run_resolver("--task", "port-allocation")
        self.assertEqual(result.returncode, 2)
        self.assertIn("sequential from 0 without gaps", result.stderr)

    def test_port_instance_mapping_is_fixed(self) -> None:
        config_root = self.write_port_config()
        config_path = config_root / "config.yaml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace("local_dev: 0", "local_dev: 1"),
            encoding="utf-8",
        )
        result = self.run_resolver("--task", "port-allocation")
        self.assertEqual(result.returncode, 2)
        self.assertIn("ports.instances.local_dev must be 0", result.stderr)

    def test_project_segment_must_preserve_full_production_range(self) -> None:
        config_root = self.write_port_config()
        config_path = config_root / "config.yaml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                'project_segment: "42"', 'project_segment: "65"'
            ),
            encoding="utf-8",
        )
        result = self.run_resolver("--task", "port-allocation")
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be between 10 and 64", result.stderr)

    def test_system_application_project_segment_is_rejected(self) -> None:
        config_root = self.write_port_config()
        config_path = config_root / "config.yaml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                'project_segment: "42"', 'project_segment: "09"'
            ),
            encoding="utf-8",
        )
        result = self.run_resolver("--task", "port-allocation")
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be between 10 and 64", result.stderr)

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
