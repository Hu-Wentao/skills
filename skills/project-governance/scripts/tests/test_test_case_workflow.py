#!/usr/bin/env python3
"""Tests for governed test-case development inspection and gates."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "test-case-workflow.py"


class TestCaseWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="project-governance-test-cases-")
        self.root = Path(self.temp.name)
        (self.root / ".git").mkdir()
        (self.root / "docs" / "verification").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_project(
        self,
        *,
        status: str = "active",
        authority: str = "resolved",
        result: str = "",
        duplicate: bool = False,
    ) -> None:
        docs = self.root / "docs" / "verification"
        (docs / "cases.md").write_text(
            f"---\nstatus: {status}\n---\n# Cases\n", encoding="utf-8"
        )
        rows = [
            {
                "CaseID": "TC-001",
                "Requirement": "REQ-001",
                "Title": "Valid login",
                "Steps": "Log in",
                "Expected": "Home is visible",
                "Result": result,
            }
        ]
        if duplicate:
            rows.append(dict(rows[0]))
        with (docs / "cases.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("CaseID", "Requirement", "Title", "Steps", "Expected", "Result"),
            )
            writer.writeheader()
            writer.writerows(rows)

        config_root = (
            self.root / ".agents" / "skills-config" / "project-governance"
        )
        config_root.mkdir(parents=True)
        (config_root / "test-case-workflow.json").write_text(
            json.dumps(
                {
                    "schema": "project-governance.test-case-workflow.v1",
                    "profile": "test",
                    "catalogs": {
                        "app": {
                            "path": "docs/verification/cases.csv",
                            "format": "csv",
                            "encoding": "utf-8",
                            "governance_document": "docs/verification/cases.md",
                            "eligible_document_statuses": ["active"],
                            "requirement_authority": authority,
                            "columns": {
                                "id": "CaseID",
                                "requirement": "Requirement",
                                "title": "Title",
                                "steps": "Steps",
                                "expected": "Expected",
                                "result": "Result",
                            },
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def invoke(self, operation: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                operation,
                "--root",
                str(self.root),
                "--catalog",
                "app",
                *args,
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_missing_configuration_is_non_mutating_and_explicit(self) -> None:
        result = self.invoke("inspect")

        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "not_configured")

    def test_inspect_reports_structural_implementation_eligibility(self) -> None:
        self.write_project()

        result = self.invoke("inspect", "--case-id", "TC-001")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "inspection_completed")
        self.assertEqual(report["eligibility"], "implementation_preflight_ready")
        self.assertFalse(report["policy"]["test_cases_define_product_semantics"])

    def test_plan_fails_closed_for_draft_and_unresolved_authority(self) -> None:
        self.write_project(status="draft_unreviewed", authority="unresolved")

        result = self.invoke("plan", "--case-id", "TC-001")

        self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "decision_required")
        self.assertEqual(
            {item["code"] for item in report["diagnostics"]},
            {"ineligible_document_status", "requirement_authority_unresolved"},
        )

    def test_plan_allows_only_structural_preflight_after_authority_resolves(self) -> None:
        self.write_project()

        result = self.invoke("plan", "--case-id", "TC-001")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "implementation_preflight_ready")
        self.assertTrue(report["policy"]["semantic_review_required"])

    def test_verify_treats_pass_as_evidence_not_semantic_completion(self) -> None:
        self.write_project(result="PASS")

        result = self.invoke("verify", "--case-id", "TC-001")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "verification_evidence_available")
        self.assertEqual(report["semantic_conclusion"], "not_inferred")
        self.assertFalse(report["policy"]["passing_result_authorizes_release"])

    def test_verify_fails_when_result_is_blank(self) -> None:
        self.write_project()

        result = self.invoke("verify", "--case-id", "TC-001")

        self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "verification_incomplete")
        self.assertIn("test_not_run", {item["code"] for item in report["diagnostics"]})

    def test_duplicate_case_ids_block_plan(self) -> None:
        self.write_project(duplicate=True)

        result = self.invoke("plan", "--case-id", "TC-001")

        self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
        self.assertIn(
            "duplicate_case_id",
            {item["code"] for item in json.loads(result.stdout)["diagnostics"]},
        )

    def test_catalog_path_cannot_escape_project_root(self) -> None:
        self.write_project()
        config_path = (
            self.root
            / ".agents"
            / "skills-config"
            / "project-governance"
            / "test-case-workflow.json"
        )
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["catalogs"]["app"]["path"] = "../outside.csv"
        config_path.write_text(json.dumps(config), encoding="utf-8")

        result = self.invoke("inspect")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["state"], "operational_error")


if __name__ == "__main__":
    unittest.main()
