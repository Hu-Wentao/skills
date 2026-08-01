#!/usr/bin/env python3
"""Tests for managed domain knowledge inspection and verification."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = SKILL_ROOT / "scripts" / "domain-knowledge.py"


CONTRACT = """---
mdq:
  version: 1
  dialect: gfm
  records:
    boundary:
      source: heading
      levels: [1, 2]
      pattern: '^(?P<id>CONCEPT-[A-Z0-9-]+)(?:[ ：—-]+(?P<title>.+))$'
    key:
      source: heading
      pattern: '^(?P<id>CONCEPT-[A-Z0-9-]+)(?:[ ：—-]+(?P<title>.+))$'
      group: id
  fields:
    title:
      source: heading
      pattern: '^(?P<id>CONCEPT-[A-Z0-9-]+)(?:[ ：—-]+(?P<title>.+))$'
      group: title
    semantic_status:
      source: label
      labels: [Semantic Status, 语义状态]
    kind:
      source: label
      labels: [Kind, 类型]
    context:
      source: label
      labels: [Context, 限界上下文]
    aliases:
      source: label
      labels: [Aliases, 别名]
    scope_note:
      source: section
      headings: [Scope Note, 范围说明]
    definition:
      source: section
      headings: [Definition, 定义]
    anti_definition:
      source: section
      headings: [Not This, 非此概念]
    broader:
      source: label
      labels: [Broader, 上位概念]
    narrower:
      source: label
      labels: [Narrower, 下位概念]
    related:
      source: label
      labels: [Related, 相关概念]
    sources:
      source: section
      headings: [Sources, 权威来源]
---
"""


def concept(
    identifier: str,
    title: str,
    *,
    context: str = "tenancy",
    aliases: str = "",
    related: str = "",
) -> str:
    alias_line = f"Aliases: {aliases}\n" if aliases else ""
    related_line = f"Related: {related}\n" if related else ""
    return f"""
## {identifier} — {title}

Semantic Status: accepted
Kind: role
Context: {context}
{alias_line}{related_line}
### Definition

Definition for {title}.

### Scope Note

Scope for {title}.

### Sources

- [Authority](requirements.md)
"""


class DomainKnowledgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="project-governance-domain-")
        self.root = Path(self.temp.name)
        (self.root / ".git").mkdir()
        (self.root / "docs").mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def invoke(self, operation: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                operation,
                "--root",
                str(self.root),
                *args,
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    def write_catalog(self, content: str) -> Path:
        path = self.root / "docs" / "domain-concepts.md"
        path.write_text(CONTRACT + content, encoding="utf-8")
        return path

    def test_missing_default_catalog_is_non_breaking(self) -> None:
        result = self.invoke("inspect")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "not_configured")
        self.assertEqual(report["mode"], "lite")

    def test_lite_catalog_verifies_with_minimal_required_fields(self) -> None:
        self.write_catalog(concept("CONCEPT-TEAM", "Team"))

        result = self.invoke("verify", "--mode", "lite")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "verified")
        self.assertEqual(report["counts"]["records"], 1)
        self.assertEqual(report["counts"]["errors"], 0)

    def test_catalog_get_does_not_treat_unselected_relation_as_missing(self) -> None:
        self.write_catalog(
            concept(
                "CONCEPT-PARTNER",
                "Partner",
                aliases="合作商",
                related="CONCEPT-TEAM",
            )
            + concept("CONCEPT-TEAM", "Team", aliases="团队")
        )

        result = self.invoke(
            "get",
            "--mode",
            "catalog",
            "--id",
            "CONCEPT-PARTNER",
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "lookup_completed")
        self.assertEqual([item["key"] for item in report["records"]], ["CONCEPT-PARTNER"])
        self.assertNotIn(
            "unknown_concept_reference",
            {item["code"] for item in report["diagnostics"]},
        )

        missing = self.invoke(
            "get",
            "--mode",
            "catalog",
            "--id",
            "CONCEPT-ABSENT",
        )
        self.assertEqual(missing.returncode, 0, missing.stderr + missing.stdout)
        self.assertEqual(json.loads(missing.stdout)["records"], [])

        searched = self.invoke(
            "search",
            "--mode",
            "catalog",
            "--text",
            "Definition for Partner",
        )
        self.assertEqual(searched.returncode, 0, searched.stderr + searched.stdout)
        self.assertEqual(
            [item["key"] for item in json.loads(searched.stdout)["records"]],
            ["CONCEPT-PARTNER"],
        )

    def test_bounded_profile_allows_same_alias_in_different_contexts(self) -> None:
        self.write_catalog(
            concept(
                "CONCEPT-TENANT-OWNER",
                "Tenant Owner",
                aliases="Owner",
                context="tenancy",
            )
            + concept(
                "CONCEPT-BILLING-OWNER",
                "Billing Owner",
                aliases="Owner",
                context="billing",
            )
        )

        result = self.invoke("verify", "--mode", "bounded")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "verified")
        self.assertEqual(report["counts"]["errors"], 0)

    def test_bounded_profile_rejects_unknown_relation(self) -> None:
        self.write_catalog(
            concept(
                "CONCEPT-PARTNER",
                "Partner",
                related="CONCEPT-MISSING",
            )
        )

        result = self.invoke("verify", "--mode", "bounded")

        self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "verification_incomplete")
        self.assertIn(
            "unknown_concept_reference",
            {item["code"] for item in report["diagnostics"]},
        )

    def test_catalog_rejects_duplicate_alias(self) -> None:
        self.write_catalog(
            concept("CONCEPT-PARTNER", "Partner", aliases="Owner")
            + concept("CONCEPT-TEAM-OWNER", "Team Owner", aliases="Owner")
        )

        result = self.invoke("verify", "--mode", "catalog")

        self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertIn(
            "ambiguous_domain_term",
            {item["code"] for item in report["diagnostics"]},
        )

    def test_docs_path_cannot_escape_project_root(self) -> None:
        result = self.invoke("inspect", "--docs", "../outside.md")

        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertEqual(report["error"]["code"], "operational_error")


if __name__ == "__main__":
    unittest.main()
