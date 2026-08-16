#!/usr/bin/env python3
"""Regression tests for hardware-aware PostgreSQL defaults."""

from __future__ import annotations

import unittest

from postgres_sizing import Inputs, recommend


def shared_host(**overrides: object) -> Inputs:
    values: dict[str, object] = {
        "host_memory_mib": 8192,
        "host_available_memory_mib": 5120,
        "cpu_count": 4,
        "other_services_budget_mib": 2048,
        "disk_free_mib": 78 * 1024,
        "current_postgres_rss_mib": 1235,
        "current_shared_buffers_mib": 512,
        "pool_max_connections": 40,
        "wal_rate_mib_per_hour": 128,
        "archive_free_mib": 78 * 1024,
        "archive_retention_hours": 6 * 24,
        "archive_filesystem": "shared",
        "historical_available_p10_mib": 3584,
        "psi_some_avg10": 0.2,
        "psi_full_avg10": 0.1,
        "workload": "mixed",
        "storage": "ssd",
        "mode": "shared",
        "archive_rpo_minutes": 15,
    }
    values.update(overrides)
    return Inputs(**values)  # type: ignore[arg-type]


class PostgresSizingTests(unittest.TestCase):
    def test_eight_gib_shared_host_defaults_to_two_gib_postgres(self) -> None:
        result = recommend(shared_host())
        self.assertEqual(result["default_option"], "shared-conservative")
        self.assertTrue(result["default_option_eligible"])
        conservative = result["options"][0]
        self.assertEqual(conservative["container"]["memory_limit_mib"], 2048)
        self.assertEqual(conservative["container"]["cpus"], 2)
        self.assertEqual(conservative["postgresql"]["shared_buffers_mib"], 512)
        self.assertEqual(conservative["postgresql"]["max_connections"], 50)
        self.assertEqual(conservative["postgresql"]["work_mem_mib"], 4)
        self.assertEqual(conservative["postgresql"]["max_wal_size_mib"], 1024)
        self.assertGreaterEqual(
            conservative["postgresql"]["max_wal_size_mib"],
            conservative["postgresql"]["shared_buffers_mib"] * 2,
        )
        self.assertNotEqual(conservative["container"]["memory_limit_mib"], 4096)
        self.assertNotEqual(conservative["postgresql"]["shared_buffers_mib"], 1536)

    def test_balanced_option_requires_history(self) -> None:
        result = recommend(shared_host(historical_available_p10_mib=None))
        conservative, balanced = result["options"]
        self.assertTrue(conservative["eligible"])
        self.assertFalse(balanced["eligible"])
        self.assertIn("historical_memory_headroom_required", balanced["blockers"])

    def test_pool_larger_than_cpu_budget_is_blocked(self) -> None:
        result = recommend(shared_host(pool_max_connections=120))
        for option in result["options"]:
            self.assertFalse(option["eligible"])
            self.assertIn(
                "aggregate_pool_exceeds_hardware_connection_budget",
                option["blockers"],
            )
            self.assertLess(option["consumer"]["aggregate_pool_max_connections"], 120)

    def test_shared_host_requires_other_service_budget(self) -> None:
        with self.assertRaisesRegex(ValueError, "other_services_budget_mib"):
            recommend(shared_host(other_services_budget_mib=0))

    def test_memory_and_pressure_gates_block_unsafe_host(self) -> None:
        result = recommend(
            shared_host(
                host_memory_mib=2048,
                host_available_memory_mib=256,
                other_services_budget_mib=512,
                current_postgres_rss_mib=0,
                disk_free_mib=4096,
                psi_some_avg10=7.0,
            )
        )
        for option in result["options"]:
            self.assertFalse(option["eligible"])
            self.assertIn("postgres_memory_budget_below_1_gib", option["blockers"])
            self.assertIn("memory_pressure_gate_failed", option["blockers"])
            self.assertIn("insufficient_postgres_filesystem_headroom", option["blockers"])

    def test_sizing_hash_is_stable_and_changes_with_capacity(self) -> None:
        first = recommend(shared_host())
        second = recommend(shared_host())
        changed = recommend(shared_host(other_services_budget_mib=2560))
        self.assertEqual(first["sizing_hash"], second["sizing_hash"])
        self.assertNotEqual(first["sizing_hash"], changed["sizing_hash"])

    def test_short_archive_timeout_must_fit_forced_full_segments(self) -> None:
        result = recommend(shared_host(archive_rpo_minutes=1))
        conservative = result["options"][0]
        self.assertFalse(conservative["eligible"])
        self.assertEqual(
            conservative["admission"]["archive_rate_upper_bound_mib_per_hour"],
            960,
        )
        self.assertIn("insufficient_wal_archive_headroom", conservative["blockers"])

    def test_dedicated_option_requires_explicit_mode_and_history(self) -> None:
        result = recommend(
            shared_host(
                host_memory_mib=16384,
                host_available_memory_mib=12288,
                cpu_count=8,
                other_services_budget_mib=0,
                current_postgres_rss_mib=0,
                current_shared_buffers_mib=0,
                pool_max_connections=100,
                historical_available_p10_mib=10240,
                mode="dedicated",
            )
        )
        self.assertEqual(result["default_option"], "dedicated")
        self.assertTrue(result["default_option_eligible"])
        self.assertEqual(len(result["options"]), 1)
        self.assertEqual(result["options"][0]["name"], "dedicated")


if __name__ == "__main__":
    unittest.main()
