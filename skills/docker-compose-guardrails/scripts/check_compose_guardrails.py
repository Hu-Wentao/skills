#!/usr/bin/env python3
"""Check Docker Compose files for explicit service resource guardrails."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def compose_config(path: Path) -> dict[str, Any]:
    path = path.resolve()
    command = [
        "docker",
        "compose",
        "--project-directory",
        str(path.parent),
        "-f",
        str(path),
        "config",
        "--format",
        "json",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"could not render Compose config: {detail}")
    try:
        model = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("docker compose did not return JSON configuration") from exc
    if not isinstance(model, dict):
        raise RuntimeError("unexpected Compose configuration structure")
    return model


def present(value: Any) -> bool:
    return value not in (None, "", 0, "0", False)


STARTUP_BUILD = re.compile(
    r"(?:\bnext\s+build\b|\bpnpm(?:\s+[^;&|\n]+)?\s+build\b|"
    r"\bnpm\s+(?:run\s+)?build\b|\byarn\s+build\b)",
    re.IGNORECASE,
)


def command_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(part, str) for part in value):
        return " ".join(value)
    return ""


def check_service(name: str, service: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    deploy = service.get("deploy") if isinstance(service.get("deploy"), dict) else {}
    resources = deploy.get("resources") if isinstance(deploy.get("resources"), dict) else {}
    limits = resources.get("limits") if isinstance(resources.get("limits"), dict) else {}

    for field, deploy_field in (("cpus", "cpus"), ("mem_limit", "memory")):
        if present(service.get(field)):
            continue
        if present(limits.get(deploy_field)):
            warnings.append(
                f"{name}: {field} is supplied only through deploy.resources.limits; "
                "verify the selected deployment target enforces it"
            )
        else:
            errors.append(f"{name}: missing finite {field}")

    if not present(service.get("pids_limit")):
        errors.append(f"{name}: missing finite pids_limit")

    restart = service.get("restart")
    if not present(restart) or str(restart).lower() == "no":
        warnings.append(f"{name}: restart is absent or disabled; confirm this is intentional")

    for field in ("command", "entrypoint"):
        if STARTUP_BUILD.search(command_text(service.get(field))):
            errors.append(
                f"{name}: {field} runs a build at container startup; "
                "move the build to a Dockerfile stage"
            )
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-f", "--file", default="compose.yaml", type=Path, help="Compose file")
    args = parser.parse_args()
    if not args.file.is_file():
        parser.error(f"file not found: {args.file}")

    try:
        model = compose_config(args.file)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    services = model.get("services")
    if not isinstance(services, dict) or not services:
        print("ERROR: no services found", file=sys.stderr)
        return 2

    errors: list[str] = []
    warnings: list[str] = []
    for name, service in services.items():
        if not isinstance(service, dict):
            errors.append(f"{name}: invalid service definition")
            continue
        service_errors, service_warnings = check_service(str(name), service)
        errors.extend(service_errors)
        warnings.extend(service_warnings)

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    print(f"PASS: {len(services)} service(s) have explicit CPU, memory, and PID limits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
