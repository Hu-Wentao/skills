#!/usr/bin/env python3
"""Execute one validated host-governance task operation."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


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
        raise TaskError(f"{field} must be one of: {', '.join(map(str, parameter['enum']))}")
    if "pattern" in parameter and not re.fullmatch(parameter["pattern"], str(parsed)):
        raise TaskError(f"{field} does not match its required pattern")
    return parsed


def build_operation_argv(
    operation: dict[str, Any], arguments: list[str]
) -> list[str]:
    parameters = operation["parameters"]
    by_flag = {parameter["flag"]: (name, parameter) for name, parameter in parameters.items()}
    values: dict[str, Any] = {}
    index = 0
    while index < len(arguments):
        flag = arguments[index]
        if flag not in by_flag:
            raise TaskError(f"unsupported operation argument: {flag}")
        name, parameter = by_flag[flag]
        if name in values:
            raise TaskError(f"operation argument was provided more than once: {flag}")
        if parameter["type"] == "boolean":
            values[name] = True
            index += 1
            continue
        if index + 1 >= len(arguments):
            raise TaskError(f"operation argument requires a value: {flag}")
        values[name] = parse_value(arguments[index + 1], parameter, flag)
        index += 2

    for name, parameter in parameters.items():
        if name not in values and "default" in parameter:
            values[name] = parameter["default"]
        if parameter["required"] and name not in values:
            raise TaskError(f"missing required operation argument: {parameter['flag']}")

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


def resolve_operation(cwd: Path, task: str, operation: str) -> dict[str, Any]:
    resolver = Path(__file__).with_name("resolve.py")
    result = subprocess.run(
        [
            sys.executable,
            str(resolver),
            "--cwd",
            str(cwd),
            "--task",
            task,
            "--operation",
            operation,
            "--format",
            "json",
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise TaskError(result.stderr.strip() or "host-governance task resolution failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise TaskError(f"host-governance resolver returned invalid JSON: {exc}") from exc


def main() -> int:
    argv = sys.argv[1:]
    cwd = Path.cwd()
    authorized = False
    while argv and argv[0].startswith("--"):
        if argv[0] == "--authorized":
            authorized = True
            argv = argv[1:]
        elif argv[0] == "--cwd" and len(argv) >= 2:
            cwd = Path(argv[1])
            argv = argv[2:]
        else:
            break
    if not argv or argv[0] not in {"execute", "control"}:
        print("error: expected execute or control", file=sys.stderr)
        return 2
    domain = argv[0]
    argv = argv[1:]
    task = "control"
    operation_name = ""
    if domain == "control":
        if argv:
            operation_name = argv[0]
            argv = argv[1:]
    else:
        while argv and argv[0] in {"--task", "--operation"}:
            if len(argv) < 2:
                print(f"error: {argv[0]} requires a value", file=sys.stderr)
                return 2
            flag, value = argv[0], argv[1]
            if flag == "--task":
                task = value
            else:
                operation_name = value
            argv = argv[2:]
    if not operation_name:
        print("error: an operation is required", file=sys.stderr)
        return 2
    remaining = argv
    try:
        resolved = resolve_operation(cwd.resolve(), task, operation_name)
        operation = resolved["contract"]["operations"][operation_name]
        if operation["authorization"] != "none" and not authorized:
            raise TaskError(
                f"{task} {operation_name} requires --authorized after current user approval"
            )
        command = build_operation_argv(operation, remaining)
        result = subprocess.run(
            command,
            cwd=resolved["project_root"],
            check=False,
        )
        return result.returncode
    except TaskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
