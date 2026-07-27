#!/usr/bin/env python3
"""Resolve generic and repository-owned project-governance instructions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SKILL_NAME = "project-governance"
RESOLVER_VERSION = "3"
DEFAULT_BASES = {
    "defect-diagnosis": "references/defect-governance.md",
    "defect-history-review": "references/defect-governance.md",
    "port-allocation": "references/port-allocation.md",
    "release-deployment": "references/release-deployment.md",
}
PORT_INSTANCES = {
    "local_dev": 0,
    "local_e2e": 1,
    "local_preproduction": 2,
    "remote_preproduction": 5,
    "remote_production": 6,
}


class ResolveError(ValueError):
    """Raised when project configuration violates the resolver contract."""


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    raise ResolveError("no Git repository found from the selected working directory")


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the mapping-only YAML subset used by project configuration."""

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith("\t"):
            raise ResolveError(f"config.yaml:{line_number}: tabs are not supported")
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % 2 or ":" not in raw_line:
            raise ResolveError(
                f"config.yaml:{line_number}: expected two-space key: value"
            )
        key, value = raw_line.strip().split(":", 1)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ResolveError(f"config.yaml:{line_number}: invalid indentation")
        parent = stack[-1][1]
        if key in parent:
            raise ResolveError(f"config.yaml:{line_number}: duplicate key {key!r}")
        if value.strip():
            parent[key] = value.strip().strip("\"'")
        else:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
    return root


def load_config(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, ""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-not-found]
    except Exception:
        parsed = parse_simple_yaml(text)
    else:
        try:
            parsed = yaml.safe_load(text)
        except Exception as exc:
            raise ResolveError(f"failed to parse config.yaml: {exc}") from exc
        if parsed is None:
            parsed = {}
        if not isinstance(parsed, dict):
            raise ResolveError("config.yaml must contain a mapping")
    return parsed, text


def require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResolveError(f"{field} must be a mapping")
    return value


def require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResolveError(f"{field} must be a non-empty string")
    return value


def require_integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ResolveError(f"{field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        return int(value)
    raise ResolveError(f"{field} must be an integer")


def require_exact_keys(mapping: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ResolveError(f"{field} contains unsupported key(s): {', '.join(unknown)}")


def resolve_path(value: str, root: Path, field: str) -> Path:
    candidate = (root / value).resolve()
    if not is_relative_to(candidate, root.resolve()):
        raise ResolveError(f"{field} escapes its allowed root")
    if not candidate.is_file():
        raise ResolveError(f"{field} not found: {candidate}")
    return candidate


def display_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    if is_relative_to(resolved, repo_root.resolve()):
        return str(resolved.relative_to(repo_root.resolve()))
    return str(resolved)


def normalize_port_config(value: Any) -> dict[str, Any]:
    ports = require_mapping(value, "ports")
    require_exact_keys(
        ports, {"project_segment", "instances", "services"}, "ports"
    )

    project_segment = require_string(
        ports.get("project_segment"), "ports.project_segment"
    )
    if not re.fullmatch(r"[0-9]{2}", project_segment):
        raise ResolveError("ports.project_segment must be exactly two digits")
    project_number = int(project_segment)
    if not 10 <= project_number <= 64:
        raise ResolveError("ports.project_segment must be between 10 and 64")

    instances = require_mapping(ports.get("instances"), "ports.instances")
    require_exact_keys(instances, set(PORT_INSTANCES), "ports.instances")
    normalized_instances: dict[str, int] = {}
    for name, expected in PORT_INSTANCES.items():
        actual = require_integer(instances.get(name), f"ports.instances.{name}")
        if actual != expected:
            raise ResolveError(
                f"ports.instances.{name} must be {expected} under PPISS"
            )
        normalized_instances[name] = actual

    services = require_mapping(ports.get("services"), "ports.services")
    require_exact_keys(
        services,
        {"allocation", "start", "capacity", "assignments"},
        "ports.services",
    )
    if require_string(
        services.get("allocation"), "ports.services.allocation"
    ) != "sequential":
        raise ResolveError("ports.services.allocation must be sequential")
    if require_integer(services.get("start"), "ports.services.start") != 0:
        raise ResolveError("ports.services.start must be 0")
    if require_integer(services.get("capacity"), "ports.services.capacity") != 100:
        raise ResolveError("ports.services.capacity must be 100")

    assignments = require_mapping(
        services.get("assignments"), "ports.services.assignments"
    )
    if not assignments:
        raise ResolveError("ports.services.assignments must not be empty")
    normalized_assignments: dict[str, int] = {}
    for raw_name, raw_service_id in assignments.items():
        service_name = require_string(raw_name, "ports.services.assignments key")
        service_id = require_integer(
            raw_service_id, f"ports.services.assignments.{service_name}"
        )
        if not 0 <= service_id <= 99:
            raise ResolveError(
                f"ports.services.assignments.{service_name} must be between 0 and 99"
            )
        normalized_assignments[service_name] = service_id

    assigned_ids = sorted(normalized_assignments.values())
    if len(set(assigned_ids)) != len(assigned_ids):
        raise ResolveError("ports.services.assignments contains duplicate service ids")
    if assigned_ids != list(range(len(assigned_ids))):
        raise ResolveError(
            "ports.services.assignments must be sequential from 0 without gaps"
        )

    return {
        "project_segment": project_segment,
        "instances": normalized_instances,
        "services": normalized_assignments,
    }


def render_port_config(ports: dict[str, Any]) -> list[str]:
    project_number = int(ports["project_segment"])
    instances = ports["instances"]
    services = ports["services"]
    lines = [
        "## Resolved Port Allocation",
        "",
        f"- Project segment: `{ports['project_segment']}`",
        "- Formula: `PP * 1000 + I * 100 + SS`",
        "",
        "| Environment | I | Service | SS | Port |",
        "| --- | ---: | --- | ---: | ---: |",
    ]
    for environment, instance_id in instances.items():
        for service_name, service_id in sorted(
            services.items(), key=lambda item: item[1]
        ):
            port = project_number * 1000 + instance_id * 100 + service_id
            lines.append(
                f"| {environment} | {instance_id} | {service_name} | "
                f"{service_id:02d} | {port:05d} |"
            )
    return lines


def resolve_task(task: str, cwd: Path) -> tuple[str, Path, str]:
    if task not in DEFAULT_BASES:
        raise ResolveError(f"unsupported task: {task}")

    repo_root = find_repo_root(cwd)
    skill_root = Path(__file__).resolve().parents[1]
    config_root = repo_root / ".agents" / "skills-config" / SKILL_NAME
    config_path = config_root / "config.yaml"
    cache_root = repo_root / ".agents" / ".cache" / SKILL_NAME

    config, config_text = load_config(config_path)
    profile = "generic"
    task_config: dict[str, Any] = {}
    port_config: dict[str, Any] | None = None
    if config:
        schema = config.get("schema")
        if schema == f"{SKILL_NAME}.config.v1":
            require_exact_keys(config, {"schema", "profile", "tasks"}, "config.yaml")
            if task == "port-allocation":
                raise ResolveError(
                    "port-allocation requires project-governance.config.v2"
                )
            allowed_tasks = {
                "defect-diagnosis",
                "defect-history-review",
                "release-deployment",
            }
        elif schema == f"{SKILL_NAME}.config.v2":
            require_exact_keys(
                config, {"schema", "profile", "ports", "tasks"}, "config.yaml"
            )
            allowed_tasks = set(DEFAULT_BASES)
            port_config = normalize_port_config(config.get("ports"))
        else:
            raise ResolveError(
                "config.yaml schema must be "
                "project-governance.config.v1 or project-governance.config.v2"
            )
        profile = require_string(config.get("profile"), "profile")
        tasks = require_mapping(config.get("tasks"), "tasks")
        require_exact_keys(tasks, allowed_tasks, "tasks")
        task_config = require_mapping(tasks.get(task), f"tasks.{task}")
        require_exact_keys(
            task_config, {"base", "profile", "commands"}, f"tasks.{task}"
        )
        sources_configured = True
    else:
        sources_configured = False

    base_value = str(task_config.get("base", DEFAULT_BASES[task]))
    base_path = resolve_path(base_value, skill_root, f"tasks.{task}.base")
    base_text = base_path.read_text(encoding="utf-8").strip()
    sources = {"base": display_path(base_path, repo_root)}
    if sources_configured:
        sources["project_config"] = display_path(config_path, repo_root)

    profile_text = ""
    profile_value = task_config.get("profile")
    if profile_value is not None:
        profile_path = resolve_path(
            require_string(profile_value, f"tasks.{task}.profile"),
            config_root,
            f"tasks.{task}.profile",
        )
        profile_text = profile_path.read_text(encoding="utf-8").strip()
        sources["profile"] = display_path(profile_path, repo_root)

    commands_raw = task_config.get("commands", {})
    commands = require_mapping(commands_raw, f"tasks.{task}.commands")
    normalized_commands = {
        str(key): require_string(value, f"tasks.{task}.commands.{key}")
        for key, value in commands.items()
    }

    parts = [
        f"# Resolved {SKILL_NAME} Instructions",
        "",
        f"- Task: `{task}`",
        f"- Profile: `{profile}`",
        "",
        "## Resolution Policy",
        "",
        "Project instructions override configurable generic defaults when both ",
        "address the same choice. They cannot override external authority, the ",
        "skill's non-configurable safety invariants, schema validation, or ",
        "path-containment rules. Declared commands are not executed by resolution.",
        "",
        "## Generic Instructions",
        "",
        base_text,
    ]
    if profile_text:
        parts.extend(["", "## Project Instructions", "", profile_text])
    if task == "port-allocation" and port_config is not None:
        parts.extend(["", *render_port_config(port_config)])
    if normalized_commands:
        parts.extend(["", "## Declared Commands", ""])
        parts.extend(
            f"- `{name}`: `{command}`"
            for name, command in sorted(normalized_commands.items())
        )
    instructions = "\n".join(parts).rstrip() + "\n"

    hash_input = {
        "resolver_version": RESOLVER_VERSION,
        "skill": SKILL_NAME,
        "task": task,
        "profile": profile,
        "base": base_text,
        "profile_text": profile_text,
        "ports": port_config,
        "commands": normalized_commands,
        "config": config_text,
    }
    digest = hashlib.sha256(
        json.dumps(hash_input, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    instructions_id = f"{SKILL_NAME}/{task}@{digest}"
    cache_path = cache_root / task / f"{digest}.md"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(instructions, encoding="utf-8")

    manifest_lines = [
        "status: ready",
        f"skill: {SKILL_NAME}",
        f"task: {task}",
        f"profile: {profile}",
        f"instructions_id: {instructions_id}",
        "instructions:",
        f"  path: {display_path(cache_path, repo_root)}",
        "sources:",
    ]
    manifest_lines.extend(
        f"  {name}: {value}" for name, value in sorted(sources.items())
    )
    if normalized_commands:
        manifest_lines.append("commands:")
        manifest_lines.extend(
            f"  {name}: {value}"
            for name, value in sorted(normalized_commands.items())
        )
    if task == "port-allocation" and port_config is not None:
        manifest_lines.extend(
            [
                "ports:",
                f"  project_segment: {port_config['project_segment']}",
                f"  instance_count: {len(port_config['instances'])}",
                f"  service_count: {len(port_config['services'])}",
            ]
        )
    return "\n".join(manifest_lines) + "\n", cache_path, instructions


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve project-governance task instructions."
    )
    parser.add_argument("--task", required=True, choices=tuple(DEFAULT_BASES))
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument(
        "--emit", choices=("manifest", "instructions"), default="manifest"
    )
    args = parser.parse_args()
    try:
        manifest, _, instructions = resolve_task(args.task, args.cwd)
    except ResolveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(instructions if args.emit == "instructions" else manifest, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
