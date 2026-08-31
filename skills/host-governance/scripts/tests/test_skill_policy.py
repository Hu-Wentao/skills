#!/usr/bin/env python3
"""Regression tests for critical host-governance bootstrap instructions."""

from __future__ import annotations

import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[2]


class SkillPolicyTest(unittest.TestCase):
    def test_requested_procedures_become_reusable_contracted_functions(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference = (
            SKILL_ROOT / "references" / "procedure-productization.md"
        ).read_text(encoding="utf-8")
        normalized_skill = " ".join(skill.split())
        normalized_reference = " ".join(reference.split())
        for phrase in (
            "implement a deterministic project-owned controller",
            "use that controller for the current task",
            "resolve and execute the existing contracted controller first",
            "Never replace a reusable function with an ad hoc remote command",
        ):
            self.assertIn(phrase, normalized_skill)
        for phrase in (
            "future invocations execute directly",
            "stable method",
            "Turn real, reviewed variations into typed contract parameters",
            "Never create a generic arbitrary-command, arbitrary-package, or shell-fragment executor",
            "Use the newly contracted controller to complete the current request",
            "A successful no-op plan and verify is the correct fast path",
        ):
            self.assertIn(phrase, normalized_reference)

    def test_docker_install_transaction_and_privilege_boundaries_are_durable(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference = (SKILL_ROOT / "references" / "docker-install.md").read_text(
            encoding="utf-8"
        )
        normalized_skill = " ".join(skill.split())
        normalized_reference = " ".join(reference.split())
        self.assertIn("docker-install.md", skill)
        self.assertIn("root-equivalent access", skill)
        self.assertIn("bounded automatic BuildKit cache cleanup", normalized_skill)
        for phrase in (
            "project-owned `host-governance.config.v2` control",
            "no TCP Docker API listener or firewall change",
            "Never pipe a remote install script to a shell",
            "Remove the test container and remove its image only",
            "Never compensate with broad package purge",
            "Compare effective TCP listeners and firewall exposure",
            "root-owned systemd service and timer",
            "only re-creatable BuildKit cache",
            "Never use `docker system prune`",
            "immediate cleanup of an existing cache",
            "cleanup service/timer ownership and digests",
        ):
            self.assertIn(phrase, normalized_reference)

    def test_docker_storage_incidents_use_exact_separately_authorized_cleanup(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference = (
            SKILL_ROOT / "references" / "docker-storage-maintenance.md"
        ).read_text(encoding="utf-8")
        normalized_skill = " ".join(skill.split())
        normalized_reference = " ".join(reference.split())
        self.assertIn("docker-storage-maintenance.md", skill)
        for phrase in (
            "separately authorized incident workflow",
            "never infer that a dangling volume is disposable",
            "Preserve named volumes by default",
        ):
            self.assertIn(phrase, normalized_skill)
        for phrase in (
            "`dangling` means unreferenced, not disposable",
            "Fix the source lifecycle first",
            "docker rm --volumes",
            "candidate digest",
            "Never use `docker volume prune`",
            "deleting a volume has no generic rollback",
            "reject any generation or candidate-digest drift",
            "Stop expansion on the first unexpected result",
            "without starting containers that were previously stopped",
            "pre-incident running-service baseline is restored",
        ):
            self.assertIn(phrase, normalized_reference)

    def test_github_actions_runner_identity_path_and_service_are_durable(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference = (
            SKILL_ROOT / "references" / "github-actions-runner.md"
        ).read_text(encoding="utf-8")
        self.assertIn("github-actions-runner.md", skill)
        for phrase in (
            "dedicated unprivileged user named `actions`",
            "`/opt/actions-runner`",
            "Do not run\n`config.sh` with `sudo`, as root",
            "./svc.sh install actions",
            "./svc.sh start",
        ):
            self.assertIn(phrase, reference)

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

    def test_emergency_manual_authorization_is_one_round_and_bounded(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        normalized_skill = " ".join(skill.split())
        for phrase in (
            "grant one emergency manual-operation round",
            "Multiple tool calls needed for that same bounded task are covered",
            "never turn the exception into a persistent arbitrary-command capability",
            "Expire the authorization at the end of this round",
            "A later assistant turn or new task requires the user to state the emergency manual authorization again",
            "The explicitly authorized one-round emergency manual operation above is the only exception",
        ):
            self.assertIn(phrase, normalized_skill)

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

    def test_postgres_parameters_require_hardware_aware_sizing(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference = (SKILL_ROOT / "references" / "postgresql.md").read_text(
            encoding="utf-8"
        )
        script = (SKILL_ROOT / "scripts" / "postgres_sizing.py").read_text(
            encoding="utf-8"
        )
        normalized_skill = " ".join(skill.split())
        for phrase in (
            "Never recommend or apply fixed PostgreSQL",
            "scripts/postgres_sizing.py",
            "shared host defaults to the conservative eligible option",
        ):
            self.assertIn(phrase, normalized_skill)
        for phrase in (
            "effective_cache_size` only as a planner estimate",
            "Derive `work_mem`",
            "max_wal_size` as a soft limit",
            "Reject a pool larger than the hardware option",
        ):
            self.assertIn(phrase, reference)
        self.assertIn("host-governance.postgres-sizing.v1", script)


if __name__ == "__main__":
    unittest.main()
