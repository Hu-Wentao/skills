#!/usr/bin/env python3
"""Tests for project-governance Markdown and defect-ledger validation."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
import json
from pathlib import Path


VALIDATOR = Path(__file__).resolve().parents[1] / "validate-governance.mjs"


def contracted_document(identifier: str, body: str) -> str:
    return f"""---
mdq:
  version: 1
  records:
    boundary:
      source: heading
      levels: [1]
    key:
      source: marker
  fields:
    raw:
      source: body
  tolerance:
    incomplete: true
---
<!-- mdq:record id="{identifier}" -->
{body}"""


class GovernanceValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="project-governance-validate-")
        self.root = Path(self.temp.name)
        self.docs = self.root / "docs"
        (self.docs / "defects").mkdir(parents=True)
        (self.docs / "requirements.md").write_text(
            contracted_document(
                "REQUIREMENTS",
                "# Requirements\n\n## REQ-TEST-001 Example\n",
            ),
            encoding="utf-8",
        )
        (self.docs / "defects" / "README.md").write_text(
            contracted_document("DEFECT-INDEX", "# Defects\n"),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_validator(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["node", str(VALIDATOR), "--root", str(self.root), *extra],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def write_defect(self, identifier: str, *, prior: str = "none", include_compatibility: bool = True) -> None:
        compatibility = "\n## Compatibility\n\nNo breaking changes.\n" if include_compatibility else ""
        (self.docs / "defects" / f"{identifier}.md").write_text(
            f"""---
mdq:
  version: 1
  records:
    boundary:
      source: heading
      levels: [1]
    key:
      source: marker
  fields:
    raw:
      source: body
  tolerance:
    incomplete: true
id: {identifier}
status: implemented
date: 2026-07-16
requirements: REQ-TEST-001
recurrence: first
prior-defects: {prior}
---
<!-- mdq:record id="{identifier}" -->
# {identifier}: Example

## Observed and Expected

Observed differs from expected.

## Failure Family

Example family.

## Causes and Ownership

The owner was incorrect.

## Repair and Next Unseen Case

The repair delegates ownership.

## Verification and Test Escape

Focused verification owns the invariant.
{compatibility}""",
            encoding="utf-8",
        )

    def test_accepts_structured_defect_record(self) -> None:
        self.write_defect("DEF-20260716-example")
        result = self.run_validator()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 defect records: 0 error(s), 0 warning(s)", result.stdout)

    def test_rejects_missing_heading_and_unknown_prior_defect(self) -> None:
        self.write_defect("DEF-20260716-example", prior="DEF-20260715-missing", include_compatibility=False)
        result = self.run_validator()
        self.assertEqual(result.returncode, 1)
        self.assertIn("defect record missing heading: Compatibility", result.stdout)
        self.assertIn("prior defect DEF-20260715-missing is not declared", result.stdout)

    def test_emits_stable_json_audit(self) -> None:
        self.write_defect("DEF-20260716-example")
        result = self.run_validator("--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["schema"], "project-governance.document-audit.v1")
        self.assertEqual(report["state"], "audit_completed")
        self.assertEqual(report["counts"]["defectRecords"], 1)

    def test_rejects_governed_document_without_persistent_contract(self) -> None:
        plans = self.docs / "plans"
        plans.mkdir()
        (plans / "README.md").write_text(
            contracted_document("PLAN-INDEX", "# Plans\n\n- [Example](./example.md)\n"),
            encoding="utf-8",
        )
        (plans / "example.md").write_text(
            "# Example plan\n\n- 状态：Planned\n",
            encoding="utf-8",
        )

        result = self.run_validator()

        self.assertEqual(result.returncode, 1)
        self.assertIn("[persistent_contract_required]", result.stdout)
        self.assertIn("docs/plans/example.md:1", result.stdout)

    def test_rejects_declared_but_invalid_persistent_contract(self) -> None:
        archive = self.docs / "archive"
        archive.mkdir()
        (archive / "invalid.md").write_text(
            "---\nmdq:\n  version: 1\n---\n# Invalid contract\n",
            encoding="utf-8",
        )

        result = self.run_validator()

        self.assertEqual(result.returncode, 1)
        self.assertIn("[profile_invalid]", result.stdout)
        self.assertIn("docs/archive/invalid.md", result.stdout)

    def test_rejects_evaluation_without_persistent_contract(self) -> None:
        evaluations = self.docs / "evaluations"
        evaluations.mkdir()
        (evaluations / "example.md").write_text(
            "# TECH-EVAL-EXAMPLE Example\n\n- Status: assessed\n",
            encoding="utf-8",
        )

        result = self.run_validator()

        self.assertEqual(result.returncode, 1)
        self.assertIn("[persistent_contract_required]", result.stdout)
        self.assertIn("docs/evaluations/example.md:1", result.stdout)

    def test_ordinary_markdown_outside_governed_paths_does_not_require_contract(
        self,
    ) -> None:
        (self.docs / "notes.md").write_text("# Ordinary notes\n", encoding="utf-8")
        result = self.run_validator()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
