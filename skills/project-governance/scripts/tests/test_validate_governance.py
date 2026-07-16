#!/usr/bin/env python3
"""Tests for project-governance Markdown and defect-ledger validation."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


VALIDATOR = Path(__file__).resolve().parents[1] / "validate-governance.mjs"


class GovernanceValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="project-governance-validate-")
        self.root = Path(self.temp.name)
        self.docs = self.root / "docs"
        (self.docs / "defects").mkdir(parents=True)
        (self.docs / "requirements.md").write_text("## REQ-TEST-001 Example\n", encoding="utf-8")
        (self.docs / "defects" / "README.md").write_text("# Defects\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_validator(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["node", str(VALIDATOR), "--root", str(self.root)],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def write_defect(self, identifier: str, *, prior: str = "none", include_compatibility: bool = True) -> None:
        compatibility = "\n## Compatibility\n\nNo breaking changes.\n" if include_compatibility else ""
        (self.docs / "defects" / f"{identifier}.md").write_text(
            f"""---
id: {identifier}
status: implemented
date: 2026-07-16
requirements: REQ-TEST-001
recurrence: first
prior-defects: {prior}
---

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


if __name__ == "__main__":
    unittest.main()
