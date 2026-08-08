#!/usr/bin/env python3
"""Regression tests for critical host-governance bootstrap instructions."""

from __future__ import annotations

import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[2]


class SkillPolicyTest(unittest.TestCase):
    def test_bootstrap_terminal_states_and_non_completion_are_durable(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference = (SKILL_ROOT / "references" / "server-bootstrap.md").read_text(
            encoding="utf-8"
        )
        for phrase in ("`verified complete`", "`explicitly blocked`", "`rolled back`"):
            self.assertIn(phrase, skill)
        self.assertIn("A registered proposal is never evidence", reference)
        self.assertIn("pending verification", reference)
        script = (SKILL_ROOT / "scripts" / "server_bootstrap.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('"completion": "verified_complete"', script)
        self.assertIn('"pending_finalize_verification"', script)

    def test_password_and_provider_boundaries_are_durable(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference = (SKILL_ROOT / "references" / "server-bootstrap.md").read_text(
            encoding="utf-8"
        )
        normalized_skill = " ".join(skill.split())
        normalized_reference = " ".join(reference.split())
        self.assertIn(
            "do not imply that password authentication was attempted",
            normalized_skill,
        )
        self.assertIn(
            "An SSH failure does not authorize a provider-console detour",
            normalized_reference,
        )
        self.assertIn("browser autofill", normalized_reference)


if __name__ == "__main__":
    unittest.main()
