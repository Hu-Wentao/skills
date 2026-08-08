#!/usr/bin/env python3
"""Tests for the reusable server bootstrap planner."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
