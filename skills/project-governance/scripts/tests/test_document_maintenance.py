#!/usr/bin/env python3
"""Tests for project-wide document maintenance inspection and planning."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "document-maintenance.py"


def requirements_document() -> str:
    return """---
mdq:
  version: 1
  records:
    boundary:
      source: heading
      levels: [2]
      pattern: '^(?P<id>REQ-[A-Z0-9-]+) .+$'
    key:
      source: heading
      pattern: '^(?P<id>REQ-[A-Z0-9-]+) .+$'
      group: id
  fields:
    status:
      source: label
      labels: [Status]
    raw:
      source: body
  tolerance:
    incomplete: true
---
# Requirements

## REQ-TEST-001 Example

- Status: Planned
"""


def plan_document(*, expose_status: bool) -> str:
    status_field = """
    status:
      source: label
      labels: [Status]
""" if expose_status else ""
    return f"""---
mdq:
  version: 1
  records:
    boundary:
      source: heading
      levels: [1]
    key:
      source: marker
  fields:{status_field}
    raw:
      source: body
  tolerance:
    incomplete: true
---
<!-- mdq:record id="PLAN-EXAMPLE" -->
# Example Plan

- Status: Planned
"""


class DocumentMaintenanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="document-maintenance-")
        self.root = Path(self.temp.name)
        (self.root / ".git").mkdir()
        self.docs = self.root / "docs"
        self.docs.mkdir()
        (self.docs / "requirements.md").write_text(
            requirements_document(), encoding="utf-8"
        )
        (self.root / "README.md").write_text("# Ordinary README\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_script(self, operation: str, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                operation,
                "--root",
                str(self.root),
                *extra,
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_inspect_can_inventory_all_markdown_without_governing_readme(self) -> None:
        result = self.run_script("inspect", "--scope", "all-markdown")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["schema"], "project-governance.document-maintenance.v1")
        self.assertEqual(report["state"], "inspection_completed")
        self.assertEqual(report["counts"]["inventory_files"], 2)
        self.assertEqual(report["counts"]["governed_files"], 1)
        self.assertFalse(
            any(issue["file"] == "README.md" for issue in report["issues"])
        )

    def test_plan_surfaces_undeclared_lifecycle_status(self) -> None:
        plans = self.docs / "plans"
        plans.mkdir()
        (plans / "README.md").write_text(
            "# Plans\n\nUser-facing planning overview.\n",
            encoding="utf-8",
        )
        (plans / "example.md").write_text(
            plan_document(expose_status=False), encoding="utf-8"
        )

        result = self.run_script("plan", "--kind", "contracts")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "maintenance_planned")
        self.assertTrue(
            any(
                issue["file"] == "docs/plans/example.md"
                and "unknown_field" in issue["message"]
                for issue in report["issues"]
            )
        )
        self.assertTrue(report["batches"])
        self.assertTrue(report["source_snapshot"])

    def test_readme_is_not_a_governed_document(self) -> None:
        plans = self.docs / "plans"
        plans.mkdir()
        (plans / "README.md").write_text(
            "# Plans\n\nUser-facing planning overview.\n",
            encoding="utf-8",
        )

        result = self.run_script("inspect", "--scope", "governed")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["counts"]["governed_files"], 1)
        self.assertFalse(any(issue["file"].endswith("README.md") for issue in report["issues"]))

    def test_inspect_governs_embedded_bff_contracts_outside_docs(self) -> None:
        bff = self.root / "lib/app/home/home.bff.md"
        bff.parent.mkdir(parents=True)
        bff.write_text(
            "---\nbff_meta:\n  schema: bff-md-meta/v8\n---\n# Home BFF\n",
            encoding="utf-8",
        )

        result = self.run_script("inspect", "--kind", "contracts")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["counts"]["governed_files"], 2)
        self.assertEqual(report["counts"]["inventory_files"], 2)
        self.assertTrue(
            any(
                issue["file"] == "lib/app/home/home.bff.md"
                and "persistent_contract_required" in issue["message"]
                for issue in report["issues"]
            )
        )

    def test_verify_fails_closed_while_structural_drift_remains(self) -> None:
        plans = self.docs / "plans"
        plans.mkdir()
        (plans / "example.md").write_text(
            "# Example Plan\n\n- Status: Planned\n", encoding="utf-8"
        )

        result = self.run_script("verify")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "maintenance_incomplete")
        self.assertGreater(report["counts"]["errors"], 0)


if __name__ == "__main__":
    unittest.main()
