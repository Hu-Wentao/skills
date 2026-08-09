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

    def test_jump_transport_socket_activation_and_local_config_are_durable(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference = (SKILL_ROOT / "references" / "server-bootstrap.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Never guess an SSH alias", skill)
        self.assertIn("remote-ready marker", skill)
        self.assertIn("systemd socket activation", skill)
        self.assertIn("local SSH host block", skill)
        self.assertIn("same route for `host-key`", reference)
        self.assertIn("`ssh.socket` override", reference)
        self.assertIn("Filesystem sandbox denial", reference)

    def test_interactive_tailscale_login_url_is_returned_immediately(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference = (SKILL_ROOT / "references" / "server-bootstrap.md").read_text(
            encoding="utf-8"
        )
        for text in (skill, reference):
            self.assertIn("https://login.tailscale.com/a/...", text)
            self.assertIn("awaiting-tailnet-auth", text)
        self.assertIn("return it to the user as soon as it appears", skill)
        self.assertIn("Return the URL to the user immediately", reference)
        self.assertIn("missing operation is an explicit contract blocker", skill)
        self.assertIn(
            "If a v2 contract lacks interactive enrollment",
            " ".join(reference.split()),
        )


if __name__ == "__main__":
    unittest.main()
