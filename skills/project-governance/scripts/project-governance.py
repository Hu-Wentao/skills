#!/usr/bin/env python3
"""Resolve and execute one validated project-governance task operation."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from resolve import ResolveError, resolve_task


ALIASES = {
    ("defect", "collect"): ("defect-diagnosis", "collect"),
    ("docs", "audit"): ("document-maintenance", "audit"),
    ("docs", "inspect"): ("document-maintenance", "inspect"),
    ("docs", "plan"): ("document-maintenance", "plan"),
    ("docs", "maintain"): ("document-maintenance", "maintain"),
    ("docs", "verify"): ("document-maintenance", "verify"),
    ("domain", "inspect"): ("domain-knowledge", "inspect"),
    ("domain", "get"): ("domain-knowledge", "get"),
    ("domain", "search"): ("domain-knowledge", "search"),
    ("domain", "plan"): ("domain-knowledge", "plan"),
    ("domain", "maintain"): ("domain-knowledge", "maintain"),
    ("domain", "verify"): ("domain-knowledge", "verify"),
    ("git", "snapshot"): ("git-snapshot", "snapshot"),
    ("release", "sync-main-plan"): ("release-deployment", "sync-main-plan"),
    ("release", "sync-main"): ("release-deployment", "sync-main"),
    ("release", "inspect"): ("release-deployment", "inspect"),
    ("release", "bootstrap-plan"): ("release-deployment", "bootstrap-plan"),
    ("release", "bootstrap"): ("release-deployment", "bootstrap"),
    ("release", "plan"): ("release-deployment", "plan"),
    ("release", "prepare-plan"): ("release-deployment", "prepare-plan"),
    ("release", "prepare"): ("release-deployment", "prepare"),
    ("release", "run"): ("release-deployment", "run"),
    ("release", "promote-plan"): ("release-deployment", "promote-plan"),
    ("release", "promote"): ("release-deployment", "promote"),
    ("release", "retry"): ("release-deployment", "retry"),
    ("release", "repair-prepare-plan"): ("release-deployment", "repair-prepare-plan"),
    ("release", "repair-prepare"): ("release-deployment", "repair-prepare"),
    ("release", "repair-plan"): ("release-deployment", "repair-plan"),
    ("release", "repair"): ("release-deployment", "repair"),
}


class TaskError(ValueError):
    """Raised when an invocation violates the resolved task contract."""


def parse_value(value: str, parameter: dict[str, Any], field: str) -> Any:
    parameter_type = parameter["type"]
    if parameter_type == "integer":
        if not re.fullmatch(r"-?[0-9]+", value):
            raise TaskError(f"{field} must be an integer")
        parsed: Any = int(value)
    elif parameter_type == "boolean":
        if value not in {"true", "false"}:
            raise TaskError(f"{field} must be true or false")
        parsed = value == "true"
    else:
        parsed = value
    if "enum" in parameter and parsed not in parameter["enum"]:
        raise TaskError(f"{field} must be one of: {', '.join(parameter['enum'])}")
    if "pattern" in parameter and not re.fullmatch(parameter["pattern"], str(parsed)):
        raise TaskError(f"{field} has an invalid format")
    return parsed


def build_command(
    operation: dict[str, Any], raw_args: list[str], authorized: bool
) -> list[str]:
    mutability = operation["mutability"]
    if mutability != "read_only" and not authorized:
        raise TaskError(
            f"{mutability} operation requires --authorized after current user approval"
        )
    parameters = operation["parameters"]
    by_flag = {parameter["flag"]: (name, parameter) for name, parameter in parameters.items()}
    values: dict[str, Any] = {}
    index = 0
    while index < len(raw_args):
        flag = raw_args[index]
        if flag == "--":
            index += 1
            continue
        selected = by_flag.get(flag)
        if selected is None:
            raise TaskError(f"unsupported operation argument: {flag}")
        name, parameter = selected
        if name in values:
            raise TaskError(f"duplicate operation argument: {flag}")
        if parameter["type"] == "boolean":
            values[name] = True
            index += 1
            continue
        if index + 1 >= len(raw_args) or raw_args[index + 1].startswith("--"):
            raise TaskError(f"{flag} requires a value")
        values[name] = parse_value(raw_args[index + 1], parameter, flag)
        index += 2

    for name, parameter in parameters.items():
        if name not in values and "default" in parameter:
            values[name] = parameter["default"]
        if parameter["required"] and name not in values:
            raise TaskError(f"missing required argument: {parameter['flag']}")

    command = list(operation["command"])
    for name, parameter in parameters.items():
        if name not in values:
            continue
        value = values[name]
        if parameter["type"] == "boolean":
            if value:
                command.append(parameter["flag"])
        else:
            command.extend([parameter["flag"], str(value)])
    return command


def load_manifest(cwd: Path, task: str) -> dict[str, Any]:
    manifest_text, _, _ = resolve_task(task, cwd, "json")
    manifest = json.loads(manifest_text)
    if "contract" not in manifest:
        raise TaskError(
            "the selected project still uses a legacy command list; migrate it to "
            "project-governance.config.v3 before using the task runner"
        )
    return manifest


def execute(
    *,
    cwd: Path,
    task: str,
    operation_name: str,
    raw_args: list[str],
    authorized: bool,
) -> int:
    manifest = load_manifest(cwd, task)
    operations = manifest["contract"]["operations"]
    if operation_name not in operations:
        raise TaskError(
            f"operation {operation_name!r} is unavailable; allowed: "
            f"{', '.join(sorted(operations))}"
        )
    operation = operations[operation_name]
    command = build_command(operation, raw_args, authorized)
    result = subprocess.run(command, cwd=cwd, check=False)
    state = operation["exit_codes"].get(str(result.returncode), "unexpected_failure")
    if result.returncode != 0:
        print(
            json.dumps(
                {
                    "schema": "project-governance.execution-result.v1",
                    "status": "failed",
                    "task": task,
                    "operation": operation_name,
                    "state": state,
                    "exit_code": result.returncode,
                    "next_states": operation["next_states"],
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve and execute a validated project-governance operation."
    )
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--authorized", action="store_true")
    parser.add_argument(
        "domain", choices=("defect", "docs", "domain", "git", "release", "execute")
    )
    parser.add_argument("action", nargs="?")
    parser.add_argument("--task")
    parser.add_argument("--operation")
    args, remaining = parser.parse_known_args()

    if args.domain == "execute":
        task = args.task
        operation = args.operation
        if not task or not operation:
            raise TaskError("execute requires --task and --operation")
    else:
        selected = ALIASES.get((args.domain, args.action or ""))
        if selected is None:
            available = ", ".join(
                f"{domain} {action}" for domain, action in sorted(ALIASES)
            )
            raise TaskError(f"unsupported task alias; allowed: {available}")
        task, operation = selected

    return execute(
        cwd=args.cwd.resolve(),
        task=task,
        operation_name=operation,
        raw_args=remaining,
        authorized=args.authorized,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ResolveError, TaskError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
