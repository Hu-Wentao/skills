#!/usr/bin/env python3
"""Tests for the versioned shared Markdown query profile asset."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml


SKILL_ROOT = Path(__file__).resolve().parents[2]
PROFILE = SKILL_ROOT / "assets" / "mdq-profiles" / "governed-document-v1.yaml"
PROFILE_REFERENCE = "project-governance/governed-document-v1"


class SharedMdqProfileTest(unittest.TestCase):
    def test_governed_document_profile_is_versioned_and_self_identifying(self) -> None:
        self.assertTrue(PROFILE.is_file())
        document = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(document["x-profile-id"], PROFILE_REFERENCE)
        self.assertEqual(document["x-profile-version"], 1)
        self.assertEqual(document["version"], 1)
        self.assertEqual(document["records"]["boundary"]["levels"], [2])

    def test_profile_key_pattern_covers_standard_governance_headings(self) -> None:
        pattern = re.compile(document_pattern())
        for heading, identifier, title in (
            ("Q-001 — Open question", "Q-001", "Open question"),
            ("REQ-001: Requirement", "REQ-001", "Requirement"),
            ("PLAN-001 - Delivery plan", "PLAN-001", "Delivery plan"),
        ):
            match = pattern.fullmatch(heading)
            self.assertIsNotNone(match, heading)
            assert match is not None
            self.assertEqual(match.group("id"), identifier)
            self.assertEqual(match.group("title"), title)


def document_pattern() -> str:
    document = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    return document["records"]["key"]["pattern"]


if __name__ == "__main__":
    unittest.main()
