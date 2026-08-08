#!/usr/bin/env python3
"""Tests for the reusable server bootstrap planner."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "server_bootstrap.py"
SPEC = importlib.util.spec_from_file_location("server_bootstrap", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ServerBootstrapTest(unittest.TestCase):
    def inspection_file(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory(prefix="server-bootstrap-test-")
        facts = {
            "device_id": "ctb-eu",
            "target": "169.58.146.63",
            "os_id": "ubuntu",
            "os_version": "24.04",
            "ssh_port": "22",
            "ssh_ports": "22",
            "password_auth": "yes",
            "kbd_auth": "yes",
            "pubkey_auth": "yes",
            "root_login": "yes",
            "ssh_socket_active": "inactive",
            "firewall": "inactive",
            "tailscale_state": "absent",
            "beszel_state": "absent",
        }
        payload = {
            "schema": MODULE.SCHEMA,
            "operation": "inspect",
            "status": "server_bootstrap_inspected",
            "facts": facts,
            "generation": MODULE.generation_for(facts),
        }
        path = Path(temporary.name) / "facts.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return temporary, path

    def test_default_plan_contains_only_baseline_actions(self) -> None:
        temporary, path = self.inspection_file()
        self.addCleanup(temporary.cleanup)
        args = Namespace(
            device_id="ctb-eu", target="169.58.146.63", ssh_user="root",
            hostname="ctb-eu", admin_user="wyatt", skip_package_upgrade=False,
            enable_tailscale=False, tailscale_tag="tag:server",
            enable_beszel=False, beszel_key="", facts_file=str(path),
        )
        result = MODULE.plan(args)
        ids = [item["id"] for item in result["actions"]]
        self.assertIn("ssh-hardening", ids)
        self.assertNotIn("tailscale-install", ids)
        self.assertNotIn("beszel-agent", ids)

    def test_options_add_tailscale_and_beszel_steps(self) -> None:
        temporary, path = self.inspection_file()
        self.addCleanup(temporary.cleanup)
        args = Namespace(
            device_id="ctb-eu", target="169.58.146.63", ssh_user="root",
            hostname="ctb-eu", admin_user="wyatt", skip_package_upgrade=False,
            enable_tailscale=True, tailscale_tag="tag:friday-relay-backup",
            enable_beszel=True, beszel_key="ssh-ed25519 AAAA", facts_file=str(path),
        )
        result = MODULE.plan(args)
        ids = [item["id"] for item in result["actions"]]
        self.assertIn("tailscale-policy", ids)
        self.assertIn("beszel-hub-record", ids)
        self.assertEqual(result["authorization_required"], ["host_write", "external_write"])

    def test_rejects_unsafe_target_and_device_id(self) -> None:
        with self.assertRaises(MODULE.BootstrapError):
            MODULE.validate_target("host; reboot")
        with self.assertRaises(MODULE.BootstrapError):
            MODULE.validate_device_id("CTB_EU")
        self.assertEqual(MODULE.validate_ssh_alias("dmit_la_ts"), "dmit_la_ts")
        with self.assertRaises(MODULE.BootstrapError):
            MODULE.validate_ssh_alias("dmit_la_ts; reboot")

    def test_run_ssh_uses_jump_port_identity_and_no_remote_tty(self) -> None:
        args = Namespace(
            target="169.58.146.63",
            ssh_user="root",
            ssh_port=10604,
            jump_host="dmit_la_ts",
            identity_file="~/.ssh/ctb_eu",
            allow_password_bootstrap=False,
        )
        completed = MODULE.subprocess.CompletedProcess([], 0, stdout="ok\n", stderr="")
        with patch.object(MODULE.subprocess, "run", return_value=completed) as run:
            self.assertEqual(MODULE.run_ssh(args, "true"), "ok\n")
        command = run.call_args.args[0]
        self.assertEqual(command[0:5], ["ssh", "-o", "BatchMode=yes", "-T", "-J"])
        self.assertIn("dmit_la_ts", command)
        self.assertIn("10604", command)
        self.assertIn(str(Path("~/.ssh/ctb_eu").expanduser()), command)

    def test_cli_accepts_proxy_jump_transport(self) -> None:
        args = MODULE.build_parser().parse_args([
            "inspect", "--device-id", "ctb-eu", "--target", "169.58.146.63",
            "--ssh-port", "10604", "--jump-host", "dmit_la_ts",
            "--identity-file", "~/.ssh/ctb_eu",
        ])
        self.assertEqual(args.ssh_port, 10604)
        self.assertEqual(args.jump_host, "dmit_la_ts")

    def test_rejects_tampered_facts_file(self) -> None:
        temporary, path = self.inspection_file()
        self.addCleanup(temporary.cleanup)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["facts"]["target"] = "203.0.113.9"
        path.write_text(json.dumps(payload), encoding="utf-8")
        args = Namespace(
            device_id="ctb-eu", target="169.58.146.63", ssh_user="root",
            hostname="ctb-eu", admin_user="wyatt", skip_package_upgrade=False,
            enable_tailscale=False, tailscale_tag="tag:server",
            enable_beszel=False, beszel_key="", facts_file=str(path),
        )
        with self.assertRaises(MODULE.BootstrapError):
            MODULE.plan(args)

    def test_intermediate_operations_cannot_claim_completion(self) -> None:
        temporary, path = self.inspection_file()
        self.addCleanup(temporary.cleanup)
        args = Namespace(
            device_id="ctb-eu", target="169.58.146.63", ssh_user="root",
            hostname="ctb-eu", admin_user="wyatt", skip_package_upgrade=False,
            enable_tailscale=False, tailscale_tag="tag:server",
            enable_beszel=False, beszel_key="", facts_file=str(path),
        )
        self.assertEqual(MODULE.plan(args)["completion"], "pending_apply")

    def test_verify_requires_finalize_evidence_or_reports_blocked(self) -> None:
        args = Namespace(
            device_id="ctb-eu", target="169.58.146.63", ssh_user="wyatt",
            hostname="ctb-eu", enable_tailscale=False, enable_beszel=False,
        )
        clean = {
            "generation": "sha256:clean",
            "facts": {
                "hostname": "ctb-eu",
                "firewall": "active",
                "password_auth": "no",
                "kbd_auth": "no",
                "pubkey_auth": "yes",
                "root_login": "no",
            },
        }
        with patch.object(MODULE, "inspect", return_value=clean):
            result = MODULE.verify(args)
        self.assertEqual(result["completion"], "pending_finalize_verification")
        self.assertIn("prohibited-root rejection", result["next_action"])

        blocked = {
            "generation": "sha256:blocked",
            "facts": {"hostname": "wrong", "firewall": "inactive"},
        }
        with patch.object(MODULE, "inspect", return_value=blocked):
            result = MODULE.verify(args)
        self.assertEqual(result["completion"], "blocked")
        self.assertTrue(result["findings"])


if __name__ == "__main__":
    unittest.main()
