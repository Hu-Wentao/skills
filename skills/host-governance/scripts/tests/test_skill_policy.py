#!/usr/bin/env python3
"""Policy routing and mechanical-gate tests for host-governance."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[2]


class SkillPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.references = {
            path.name: path.read_text(encoding="utf-8")
            for path in (SKILL_ROOT / "references").glob("*.md")
        }

    def assert_unique_owner(self, phrase: str, owner: str) -> None:
        corpus = {"SKILL.md": self.skill, **self.references}
        locations = [name for name, text in corpus.items() if phrase in text]
        self.assertEqual(locations, [owner], f"{phrase!r} owners: {locations}")

    def test_router_links_every_owning_reference_directly(self) -> None:
        expected = {
            "context.md", "control.md", "project_config.md",
            "authorization-and-safety.md", "procedure-productization.md",
            "server-bootstrap.md", "docker-install.md",
            "docker-storage-maintenance.md", "github-actions-runner.md",
            "jenkins.md", "postgresql.md", "tailscale.md", "caddy.md",
            "cloudflare.md", "cloudflare-tunnel.md",
        }
        links = set(re.findall(r"\]\(references/([^)]+)\)", self.skill))
        self.assertTrue(expected <= links)
        for name in links:
            self.assertTrue((SKILL_ROOT / "references" / name).is_file(), name)
            self.assertNotIn("/", name)

    def test_detailed_authorization_has_one_owner(self) -> None:
        for phrase in (
            "Multiple tool calls needed for that same task are covered",
            "Never turn the exception into a persistent arbitrary-command capability",
            "remote-ready marker",
        ):
            self.assert_unique_owner(phrase, "authorization-and-safety.md")

    def test_product_detail_remains_in_owning_reference(self) -> None:
        checks = {
            "procedure-productization.md": "Never create a generic arbitrary-command, arbitrary-package, or shell-fragment executor",
            "docker-install.md": "Never use `docker system prune`",
            "docker-storage-maintenance.md": "Never use `docker volume prune`",
            "github-actions-runner.md": "`/opt/actions-runner`",
            "server-bootstrap.md": "A registered proposal is never evidence",
            "postgresql.md": "Derive `work_mem`",
        }
        for owner, phrase in checks.items():
            self.assertIn(" ".join(phrase.split()), " ".join(self.references[owner].split()))

    def test_one_time_operations_do_not_imply_productization(self) -> None:
        productization = self.references["procedure-productization.md"]
        self.assertIn(
            "A request to execute, repair, recover, clean up, migrate, or order steps for one current target is a one-time operation",
            self.skill,
        )
        self.assertIn(
            "Selecting a plan or sequence authorizes only that execution path",
            self.skill,
        )
        self.assertIn(
            "Do not edit the host repository, controllers, contracts, tests, documentation, or versions",
            self.skill,
        )
        self.assertIn("Productization requires explicit current-request intent", productization)
        self.assertIn("never productize merely to unblock the current operation", productization)
        self.assertNotIn("Otherwise capture the reviewed stable method", self.skill)
        self.assertNotIn("Use the newly contracted controller to complete the current request", productization)

    def test_runner_enforces_current_user_authorization(self) -> None:
        resolver = (SKILL_ROOT / "scripts" / "resolve.py").read_text(encoding="utf-8")
        runner = (SKILL_ROOT / "scripts" / "host-governance.py").read_text(encoding="utf-8")
        self.assertIn('mutability != "read_only" and authorization != "current_user"', resolver)
        self.assertIn('if operation["authorization"] != "none" and not authorized', runner)
        self.assertIn("requires --authorized after current user approval", runner)

    def test_secret_sources_remain_child_environment_only(self) -> None:
        runner = (SKILL_ROOT / "scripts" / "host-governance.py").read_text(encoding="utf-8")
        self.assertIn("resolve_environment(operation)", runner)
        self.assertIn("env=environment", runner)
        self.assertNotIn("print(environment)", runner)


if __name__ == "__main__":
    unittest.main()
