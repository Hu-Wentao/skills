#!/usr/bin/env python3
"""Produce conservative PostgreSQL starting options from host capacity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any


SCHEMA = "host-governance.postgres-sizing.v1"
MIB = 1024 * 1024


@dataclass(frozen=True)
class Inputs:
    host_memory_mib: int
    host_available_memory_mib: int
    cpu_count: int
    other_services_budget_mib: int
    disk_free_mib: int
    current_postgres_rss_mib: int
    current_shared_buffers_mib: int
    pool_max_connections: int | None
    wal_rate_mib_per_hour: int
    archive_free_mib: int
    archive_retention_hours: int
    archive_filesystem: str
    historical_available_p10_mib: int | None
    psi_some_avg10: float
    psi_full_avg10: float
    workload: str
    storage: str
    mode: str
    archive_rpo_minutes: int


PROFILES: tuple[dict[str, Any], ...] = (
    {
        "name": "shared-conservative",
        "mode": "shared",
        "host_memory_ratio": 0.30,
        "effective_cache_ratio": 0.60,
        "connection_factor": 10,
        "connection_base": 10,
        "work_mem_cap_mib": 4,
        "maintenance_cap_mib": 128,
        "cpu_ratio": 0.50,
        "requires_history": False,
    },
    {
        "name": "shared-balanced",
        "mode": "shared",
        "host_memory_ratio": 0.40,
        "effective_cache_ratio": 0.70,
        "connection_factor": 15,
        "connection_base": 10,
        "work_mem_cap_mib": 8,
        "maintenance_cap_mib": 256,
        "cpu_ratio": 0.75,
        "requires_history": True,
    },
    {
        "name": "dedicated",
        "mode": "dedicated",
        "host_memory_ratio": 0.70,
        "effective_cache_ratio": 0.75,
        "connection_factor": 20,
        "connection_base": 20,
        "work_mem_cap_mib": 16,
        "maintenance_cap_mib": 512,
        "cpu_ratio": 0.90,
        "requires_history": True,
    },
)


def round_down(value: float, quantum: int) -> int:
    return int(value // quantum) * quantum


def round_up(value: float, quantum: int) -> int:
    return int(math.ceil(value / quantum)) * quantum


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate(inputs: Inputs) -> None:
    positive = {
        "host_memory_mib": inputs.host_memory_mib,
        "host_available_memory_mib": inputs.host_available_memory_mib,
        "cpu_count": inputs.cpu_count,
        "disk_free_mib": inputs.disk_free_mib,
        "wal_rate_mib_per_hour": inputs.wal_rate_mib_per_hour,
        "archive_free_mib": inputs.archive_free_mib,
        "archive_retention_hours": inputs.archive_retention_hours,
        "archive_rpo_minutes": inputs.archive_rpo_minutes,
    }
    for name, value in positive.items():
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    nonnegative = {
        "other_services_budget_mib": inputs.other_services_budget_mib,
        "current_postgres_rss_mib": inputs.current_postgres_rss_mib,
        "current_shared_buffers_mib": inputs.current_shared_buffers_mib,
        "psi_some_avg10": inputs.psi_some_avg10,
        "psi_full_avg10": inputs.psi_full_avg10,
    }
    for name, value in nonnegative.items():
        if value < 0:
            raise ValueError(f"{name} must not be negative")
    if inputs.host_available_memory_mib > inputs.host_memory_mib:
        raise ValueError("host_available_memory_mib cannot exceed host_memory_mib")
    if inputs.mode == "shared" and inputs.other_services_budget_mib == 0:
        raise ValueError("a shared host requires a nonzero other_services_budget_mib")
    if inputs.pool_max_connections is not None and inputs.pool_max_connections <= 0:
        raise ValueError("pool_max_connections must be positive")
    choices = {
        "workload": (inputs.workload, {"mixed", "oltp", "analytics"}),
        "storage": (inputs.storage, {"hdd", "ssd", "nvme"}),
        "mode": (inputs.mode, {"shared", "dedicated"}),
        "archive_filesystem": (
            inputs.archive_filesystem,
            {"shared", "separate"},
        ),
    }
    for name, (value, allowed) in choices.items():
        if value not in allowed:
            raise ValueError(f"{name} must be one of: {', '.join(sorted(allowed))}")


def host_reserve_mib(inputs: Inputs) -> int:
    ratio = 0.25 if inputs.mode == "shared" else 0.20
    return round_up(max(1024, inputs.host_memory_mib * ratio), 256)


def hardware_connection_ceiling(profile: dict[str, Any], inputs: Inputs) -> int:
    factor = int(profile["connection_factor"])
    if inputs.workload == "oltp":
        factor += 5
    elif inputs.workload == "analytics":
        factor = max(4, factor // 2)
    value = int(profile["connection_base"]) + inputs.cpu_count * factor
    return max(20, min(200, value))


def option_for(profile: dict[str, Any], inputs: Inputs, reserve_mib: int) -> dict[str, Any]:
    blockers: list[str] = []
    hard_ceiling = inputs.host_memory_mib - reserve_mib - inputs.other_services_budget_mib
    ratio_ceiling = round_down(inputs.host_memory_mib * float(profile["host_memory_ratio"]), 512)
    memory_limit = round_down(min(hard_ceiling, ratio_ceiling), 512)
    if memory_limit < 1024:
        blockers.append("postgres_memory_budget_below_1_gib")
        memory_limit = max(512, memory_limit)

    shared_buffers = max(128, round_down(memory_limit * 0.25, 128))
    effective_cache = max(
        shared_buffers,
        round_down(memory_limit * float(profile["effective_cache_ratio"]), 128),
    )
    maintenance = max(
        64,
        min(int(profile["maintenance_cap_mib"]), round_down(memory_limit / 16, 64)),
    )

    connection_ceiling = hardware_connection_ceiling(profile, inputs)
    requested_connections = (
        inputs.pool_max_connections + 10
        if inputs.pool_max_connections is not None
        else connection_ceiling
    )
    if requested_connections > connection_ceiling:
        blockers.append("aggregate_pool_exceeds_hardware_connection_budget")
    max_connections = min(requested_connections, connection_ceiling)
    pool_limit = min(inputs.pool_max_connections or max_connections - 10, max_connections - 10)
    active_connections = max(1, pool_limit)

    fixed_private_headroom = round_up(memory_limit * 0.25, 128)
    private_budget = max(
        1,
        memory_limit - shared_buffers - maintenance - fixed_private_headroom,
    )
    memory_operations_per_query = 4 if inputs.workload == "analytics" else 2
    calculated_work_mem = max(
        1,
        private_budget // (active_connections * memory_operations_per_query),
    )
    work_mem = min(int(profile["work_mem_cap_mib"]), calculated_work_mem)

    checkpoint_minutes = 15
    wal_for_two_windows = math.ceil(
        inputs.wal_rate_mib_per_hour * (checkpoint_minutes / 60) * 2
    )
    buffer_wal_multiplier = 4 if inputs.storage == "hdd" else 2
    max_wal = round_up(
        max(1024, shared_buffers * buffer_wal_multiplier, wal_for_two_windows),
        256,
    )
    min_wal = round_up(max(80, max_wal / 4), 64)

    cpu_limit = max(1, math.floor(inputs.cpu_count * float(profile["cpu_ratio"])))
    pids_limit = max(128, round_up(max_connections + 64, 64))
    restart_reclaimable = max(
        inputs.current_postgres_rss_mib,
        inputs.current_shared_buffers_mib,
    )
    restart_available = inputs.host_available_memory_mib + restart_reclaimable
    startup_required = shared_buffers + max(512, round_up(memory_limit * 0.10, 128))
    if restart_available < startup_required:
        blockers.append("insufficient_restart_memory_headroom")
    if inputs.psi_some_avg10 > 5.0 or inputs.psi_full_avg10 > 1.0:
        blockers.append("memory_pressure_gate_failed")
    disk_headroom_required = max(10240, max_wal * 4)
    if inputs.disk_free_mib < disk_headroom_required:
        blockers.append("insufficient_postgres_filesystem_headroom")
    forced_segment_rate = math.ceil(16 * 60 / inputs.archive_rpo_minutes)
    archive_rate_upper_bound = max(
        inputs.wal_rate_mib_per_hour,
        forced_segment_rate,
    )
    archive_headroom_required = round_up(
        archive_rate_upper_bound * inputs.archive_retention_hours * 1.10 + max_wal,
        256,
    )
    if inputs.archive_free_mib < archive_headroom_required:
        blockers.append("insufficient_wal_archive_headroom")
    combined_filesystem_headroom_required: int | None = None
    if inputs.archive_filesystem == "shared":
        combined_filesystem_headroom_required = (
            disk_headroom_required + archive_headroom_required
        )
        shared_filesystem_free = min(inputs.disk_free_mib, inputs.archive_free_mib)
        if shared_filesystem_free < combined_filesystem_headroom_required:
            blockers.append("insufficient_combined_postgres_archive_headroom")

    historical_restart_available: int | None = None
    if bool(profile["requires_history"]):
        if inputs.historical_available_p10_mib is None:
            blockers.append("historical_memory_headroom_required")
        else:
            historical_restart_available = (
                inputs.historical_available_p10_mib + restart_reclaimable
            )
            if historical_restart_available < startup_required:
                blockers.append("historical_memory_headroom_insufficient")

    wal_compression = "lz4" if inputs.cpu_count >= 4 else "off"
    return {
        "name": profile["name"],
        "eligible": not blockers,
        "blockers": blockers,
        "container": {
            "cpus": cpu_limit,
            "memory_limit_mib": memory_limit,
            "pids_limit": pids_limit,
        },
        "postgresql": {
            "max_connections": max_connections,
            "shared_buffers_mib": shared_buffers,
            "effective_cache_size_mib": effective_cache,
            "work_mem_mib": work_mem,
            "maintenance_work_mem_mib": maintenance,
            "wal_level": "replica",
            "archive_mode": "on",
            "archive_timeout_minutes": inputs.archive_rpo_minutes,
            "full_page_writes": "on",
            "wal_compression": wal_compression,
            "checkpoint_timeout_minutes": checkpoint_minutes,
            "checkpoint_completion_target": 0.9,
            "max_wal_size_mib": max_wal,
            "min_wal_size_mib": min_wal,
        },
        "consumer": {"aggregate_pool_max_connections": pool_limit},
        "admission": {
            "hard_postgres_memory_ceiling_mib": hard_ceiling,
            "restart_available_memory_mib": restart_available,
            "startup_memory_required_mib": startup_required,
            "historical_restart_available_p10_mib": historical_restart_available,
            "disk_headroom_required_mib": disk_headroom_required,
            "archive_rate_upper_bound_mib_per_hour": archive_rate_upper_bound,
            "archive_headroom_required_mib": archive_headroom_required,
            "combined_filesystem_headroom_required_mib": (
                combined_filesystem_headroom_required
            ),
        },
    }


def recommend(inputs: Inputs) -> dict[str, Any]:
    validate(inputs)
    reserve_mib = host_reserve_mib(inputs)
    profiles = [profile for profile in PROFILES if profile["mode"] == inputs.mode]
    options = [option_for(profile, inputs, reserve_mib) for profile in profiles]
    default_name = "shared-conservative" if inputs.mode == "shared" else "dedicated"
    selected = next(option for option in options if option["name"] == default_name)
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "inputs": asdict(inputs),
        "derived": {
            "host_reserve_mib": reserve_mib,
            "hard_postgres_memory_ceiling_mib": (
                inputs.host_memory_mib
                - reserve_mib
                - inputs.other_services_budget_mib
            ),
        },
        "default_option": default_name,
        "default_option_eligible": selected["eligible"],
        "options": options,
        "invariants": [
            "effective_cache_size is a planner estimate, not allocated memory",
            "work_mem can be allocated multiple times per query and per parallel worker",
            "max_wal_size is a soft limit and requires filesystem headroom",
            "archive_timeout follows the accepted RPO, not host capacity",
            "apply must recompute sizing under the host transaction lock",
        ],
    }
    result["sizing_hash"] = hashlib.sha256(stable_json(result).encode("utf-8")).hexdigest()
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-memory-mib", type=int, required=True)
    parser.add_argument("--host-available-memory-mib", type=int, required=True)
    parser.add_argument("--cpu-count", type=int, required=True)
    parser.add_argument("--other-services-budget-mib", type=int, required=True)
    parser.add_argument("--disk-free-mib", type=int, required=True)
    parser.add_argument("--current-postgres-rss-mib", type=int, default=0)
    parser.add_argument("--current-shared-buffers-mib", type=int, default=0)
    parser.add_argument("--pool-max-connections", type=int)
    parser.add_argument("--wal-rate-mib-per-hour", type=int, required=True)
    parser.add_argument("--archive-free-mib", type=int, required=True)
    parser.add_argument("--archive-retention-hours", type=int, required=True)
    parser.add_argument(
        "--archive-filesystem",
        choices=("shared", "separate"),
        required=True,
    )
    parser.add_argument("--historical-available-p10-mib", type=int)
    parser.add_argument("--psi-some-avg10", type=float, default=0.0)
    parser.add_argument("--psi-full-avg10", type=float, default=0.0)
    parser.add_argument("--workload", choices=("mixed", "oltp", "analytics"), default="mixed")
    parser.add_argument("--storage", choices=("hdd", "ssd", "nvme"), default="ssd")
    parser.add_argument("--mode", choices=("shared", "dedicated"), default="shared")
    parser.add_argument("--archive-rpo-minutes", type=int, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = recommend(Inputs(**vars(args)))
    except ValueError as exc:
        print(stable_json({"schema": SCHEMA, "status": "invalid", "error": str(exc)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
