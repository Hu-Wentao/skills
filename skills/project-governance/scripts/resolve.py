#!/usr/bin/env python3
"""Resolve generic and repository-owned project-governance instructions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


SKILL_NAME = "project-governance"
RESOLVER_VERSION = "7"
DEFAULT_BASES = {
    "defect-feedback-lifecycle": "references/defect-feedback-lifecycle.md",
    "defect-diagnosis": "references/defect-governance.md",
    "defect-history-review": "references/defect-governance.md",
    "document-audit": "references/document-audit.md",
    "git-snapshot": "references/git-snapshot.md",
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


def require_boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ResolveError(f"{field} must be a boolean")
    return value


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


def load_json(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ResolveError(f"{field} is not valid JSON: {exc}") from exc
    return require_mapping(value, field)


def expand_contract_path(value: str, repo_root: Path, skill_root: Path) -> str:
    return value.replace("<project-root>", str(repo_root)).replace(
        "<skill-root>", str(skill_root)
    )


def validate_command(
    command: list[str], repo_root: Path, skill_root: Path, field: str
) -> list[str]:
    if not command:
        raise ResolveError(f"{field} must not be empty")
    expanded = [
        expand_contract_path(require_string(value, f"{field} item"), repo_root, skill_root)
        for value in command
    ]
    executable = expanded[0]
    if "/" in executable:
        executable_path = Path(executable)
        if not executable_path.is_absolute():
            executable_path = (repo_root / executable_path).resolve()
        if not executable_path.is_file():
            raise ResolveError(f"{field} executable not found: {executable_path}")
    elif shutil.which(executable) is None:
        raise ResolveError(f"{field} executable not found on PATH: {executable}")

    executable_name = Path(executable).name
    if (
        executable_name == "node" or executable_name.startswith("python")
    ) and len(expanded) > 1:
        script = next((item for item in expanded[1:] if not item.startswith("-")), "")
        if script:
            script_path = Path(script)
            if not script_path.is_absolute():
                script_path = (repo_root / script_path).resolve()
            if not script_path.is_file():
                raise ResolveError(f"{field} script not found: {script_path}")
    if executable_name == "uv" and expanded[1:3] == ["run", "python"]:
        if len(expanded) < 4:
            raise ResolveError(f"{field} is missing the Python script")
        script_path = Path(expanded[3])
        if not script_path.is_absolute():
            script_path = (repo_root / script_path).resolve()
        if not script_path.is_file():
            raise ResolveError(f"{field} script not found: {script_path}")
    if executable_name == "pnpm" and len(expanded) > 1 and not expanded[1].startswith("-"):
        package_path = repo_root / "package.json"
        if not package_path.is_file():
            raise ResolveError(f"{field} requires package.json")
        package = load_json(package_path, "package.json")
        scripts = require_mapping(package.get("scripts", {}), "package.json scripts")
        if expanded[1] not in scripts:
            raise ResolveError(
                f"{field} references missing package.json script: {expanded[1]}"
            )
    return expanded


def normalize_parameter(value: Any, field: str) -> dict[str, Any]:
    parameter = require_mapping(value, field)
    require_exact_keys(
        parameter,
        {"flag", "type", "required", "enum", "pattern", "default"},
        field,
    )
    flag = require_string(parameter.get("flag"), f"{field}.flag")
    if not re.fullmatch(r"--[a-z][a-z0-9-]*", flag):
        raise ResolveError(f"{field}.flag must be a long option")
    parameter_type = require_string(parameter.get("type"), f"{field}.type")
    if parameter_type not in {"string", "integer", "boolean"}:
        raise ResolveError(f"{field}.type must be string, integer, or boolean")
    normalized: dict[str, Any] = {
        "flag": flag,
        "type": parameter_type,
        "required": require_boolean(parameter.get("required", False), f"{field}.required"),
    }
    if "enum" in parameter:
        enum = parameter["enum"]
        if not isinstance(enum, list) or not enum:
            raise ResolveError(f"{field}.enum must be a non-empty list")
        normalized["enum"] = [
            require_string(item, f"{field}.enum item") for item in enum
        ]
    if "pattern" in parameter:
        pattern = require_string(parameter["pattern"], f"{field}.pattern")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ResolveError(f"{field}.pattern is invalid: {exc}") from exc
        normalized["pattern"] = pattern
    if "default" in parameter:
        default = parameter["default"]
        if parameter_type == "string" and not isinstance(default, str):
            raise ResolveError(f"{field}.default must be a string")
        if parameter_type == "integer" and (
            isinstance(default, bool) or not isinstance(default, int)
        ):
            raise ResolveError(f"{field}.default must be an integer")
        if parameter_type == "boolean" and not isinstance(default, bool):
            raise ResolveError(f"{field}.default must be a boolean")
        if "enum" in normalized and default not in normalized["enum"]:
            raise ResolveError(f"{field}.default must be present in enum")
        if "pattern" in normalized and not re.fullmatch(
            normalized["pattern"], str(default)
        ):
            raise ResolveError(f"{field}.default does not match pattern")
        normalized["default"] = default
    return normalized


def normalize_contract(
    value: dict[str, Any],
    *,
    task: str,
    repo_root: Path,
    skill_root: Path,
    field: str,
) -> dict[str, Any]:
    require_exact_keys(value, {"schema", "id", "task", "operations"}, field)
    if require_string(value.get("schema"), f"{field}.schema") != (
        "project-governance.task-contract.v1"
    ):
        raise ResolveError(
            f"{field}.schema must be project-governance.task-contract.v1"
        )
    contract_task = require_string(value.get("task"), f"{field}.task")
    if contract_task != task:
        raise ResolveError(f"{field}.task must equal {task}")
    operations = require_mapping(value.get("operations"), f"{field}.operations")
    if not operations:
        raise ResolveError(f"{field}.operations must not be empty")
    normalized_operations: dict[str, Any] = {}
    for operation_name, raw_operation in operations.items():
        seen_flags: set[str] = set()
        name = require_string(operation_name, f"{field}.operations key")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            raise ResolveError(f"{field}.operations key is invalid: {name}")
        operation_field = f"{field}.operations.{name}"
        operation = require_mapping(raw_operation, operation_field)
        require_exact_keys(
            operation,
            {
                "description",
                "command",
                "mutability",
                "authorization",
                "parameters",
                "output_schema",
                "exit_codes",
                "next_states",
            },
            operation_field,
        )
        command_raw = operation.get("command")
        if not isinstance(command_raw, list):
            raise ResolveError(f"{operation_field}.command must be an argv list")
        mutability = require_string(
            operation.get("mutability"), f"{operation_field}.mutability"
        )
        if mutability not in {
            "read_only",
            "repository_write",
            "external_write",
            "destructive",
        }:
            raise ResolveError(f"{operation_field}.mutability is unsupported")
        authorization = require_string(
            operation.get("authorization"), f"{operation_field}.authorization"
        )
        if authorization not in {"none", "current_user"}:
            raise ResolveError(f"{operation_field}.authorization is unsupported")
        if mutability != "read_only" and authorization != "current_user":
            raise ResolveError(
                f"{operation_field} writes state and must require current_user authorization"
            )
        parameters_raw = require_mapping(
            operation.get("parameters", {}), f"{operation_field}.parameters"
        )
        parameters: dict[str, Any] = {}
        for parameter_name, raw_parameter in parameters_raw.items():
            parameter = normalize_parameter(
                raw_parameter, f"{operation_field}.parameters.{parameter_name}"
            )
            if parameter["flag"] in seen_flags:
                raise ResolveError(
                    f"{operation_field} reuses parameter flag {parameter['flag']}"
                )
            seen_flags.add(parameter["flag"])
            parameters[str(parameter_name)] = parameter
        exit_codes_raw = require_mapping(
            operation.get("exit_codes"), f"{operation_field}.exit_codes"
        )
        exit_codes: dict[str, str] = {}
        for raw_code, raw_state in exit_codes_raw.items():
            code = str(raw_code)
            if not re.fullmatch(r"[0-9]{1,3}", code):
                raise ResolveError(f"{operation_field}.exit_codes key must be numeric")
            exit_codes[code] = require_string(
                raw_state, f"{operation_field}.exit_codes.{code}"
            )
        if "0" not in exit_codes:
            raise ResolveError(f"{operation_field}.exit_codes must define 0")
        next_states_raw = operation.get("next_states", [])
        if not isinstance(next_states_raw, list):
            raise ResolveError(f"{operation_field}.next_states must be a list")
        normalized_operations[name] = {
            "description": require_string(
                operation.get("description"), f"{operation_field}.description"
            ),
            "command": validate_command(
                command_raw, repo_root, skill_root, f"{operation_field}.command"
            ),
            "mutability": mutability,
            "authorization": authorization,
            "parameters": parameters,
            "output_schema": require_string(
                operation.get("output_schema"), f"{operation_field}.output_schema"
            ),
            "exit_codes": exit_codes,
            "next_states": [
                require_string(item, f"{operation_field}.next_states item")
                for item in next_states_raw
            ],
        }
    return {
        "schema": "project-governance.task-contract.v1",
        "id": require_string(value.get("id"), f"{field}.id"),
        "task": contract_task,
        "operations": normalized_operations,
    }


def managed_release_contract(repo_root: Path, skill_root: Path) -> dict[str, Any]:
    """Return the project-neutral release contract supplied by this skill."""

    script = str(skill_root / "scripts" / "release-workflow.py")
    semver = "^[0-9]+\\.[0-9]+\\.[0-9]+$"
    tag = "^v[0-9]+\\.[0-9]+\\.[0-9]+$"

    def operation(
        name: str,
        description: str,
        mutability: str,
        parameters: dict[str, Any],
        success: str,
        next_states: list[str],
    ) -> dict[str, Any]:
        return {
            "description": description,
            "command": [sys.executable, script, name],
            "mutability": mutability,
            "authorization": "none" if mutability == "read_only" else "current_user",
            "parameters": parameters,
            "output_schema": "project-governance.release-event.v1",
            "exit_codes": {
                "0": success,
                "1": "release_operation_failed",
                "2": "release_workflow_not_configured_or_invalid",
            },
            "next_states": next_states,
        }

    target = {
        "flag": "--target",
        "type": "string",
        "required": True,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
    }
    version = {
        "flag": "--version",
        "type": "string",
        "required": True,
        "pattern": semver,
    }
    base_tag = {
        "flag": "--base-tag",
        "type": "string",
        "required": True,
        "pattern": tag,
    }
    release_tag = {
        "flag": "--tag",
        "type": "string",
        "required": True,
        "pattern": tag,
    }
    resume = {"flag": "--resume", "type": "boolean", "required": False}
    migration = {"flag": "--migration", "type": "boolean", "required": False}
    raw = {
        "schema": "project-governance.task-contract.v1",
        "id": "project-governance.release-deployment.managed.v1",
        "task": "release-deployment",
        "operations": {
            "sync-main-plan": operation(
                "sync-main-plan",
                "Inspect whether the highest stable tag must be synchronized into committed integration history.",
                "read_only",
                {},
                "main_sync_inspected",
                ["authorized_main_sync", "release_prepare_plan"],
            ),
            "sync-main": operation(
                "sync-main",
                "Synchronize the highest stable tag into a clean checked-out integration branch without starting a release.",
                "repository_write",
                {},
                "main_synchronized",
                ["release_prepare_plan", "report_main_sync_conflict"],
            ),
            "inspect": operation(
                "inspect",
                "Inspect committed source, control-worktree state, stable tags, and managed workflow readiness without changing state.",
                "read_only",
                {
                    "target": {
                        "flag": "--target",
                        "type": "string",
                        "required": False,
                        "pattern": target["pattern"],
                    }
                },
                "release_inspected",
                ["release_bootstrap_plan", "release_plan"],
            ),
            "bootstrap-plan": operation(
                "bootstrap-plan",
                "Inspect a reusable release-workflow preset without writing project configuration.",
                "read_only",
                {
                    "preset": {
                        "flag": "--preset",
                        "type": "string",
                        "required": False,
                        "default": "auto",
                        "enum": ["auto", "node-pnpm", "python-uv", "flutter-fvm"],
                    }
                },
                "release_bootstrap_planned",
                ["authorized_release_bootstrap"],
            ),
            "bootstrap": operation(
                "bootstrap",
                "Create a minimal managed release hook scaffold without inventing deployment targets.",
                "repository_write",
                {
                    "preset": {
                        "flag": "--preset",
                        "type": "string",
                        "required": False,
                        "default": "auto",
                        "enum": ["auto", "node-pnpm", "python-uv", "flutter-fvm"],
                    }
                },
                "release_bootstrapped",
                ["configure_artifact_and_target_hooks"],
            ),
            "plan": operation(
                "plan",
                "Validate the managed workflow and exact target without changing repository or external state.",
                "read_only",
                {"target": target},
                "release_planned",
                ["release_prepare_plan"],
            ),
            "prepare-plan": operation(
                "prepare-plan",
                "Plan version reservation and an isolated retained release worktree from committed integration source.",
                "read_only",
                {"version": version, "target": target},
                "release_prepare_planned",
                ["authorized_release_prepare"],
            ),
            "prepare": operation(
                "prepare",
                "Reserve a version and create or resume its retained release branch worktree without mutating the control worktree.",
                "repository_write",
                {"version": version, "target": target, "resume": resume},
                "release_prepared_and_version_reserved",
                ["authorized_release_run", "repair_untagged_candidate"],
            ),
            "repair-prepare-plan": operation(
                "repair-prepare-plan",
                "Plan the immediate next patch repair lineage directly from one failed immutable tag.",
                "read_only",
                {"base_tag": base_tag, "version": version, "target": target},
                "repair_prepare_planned",
                ["authorized_repair_prepare"],
            ),
            "repair-prepare": operation(
                "repair-prepare",
                "Reserve the immediate next patch and create its retained repair worktree from the failed tag.",
                "repository_write",
                {"base_tag": base_tag, "version": version, "target": target, "resume": resume},
                "repair_prepared_and_version_reserved",
                ["commit_minimal_repair", "authorized_repair_run"],
            ),
            "repair-plan": operation(
                "repair-prepare-plan",
                "Validate the immediate-next-patch repair identity and target without changing state.",
                "read_only",
                {"base_tag": base_tag, "version": version, "target": target},
                "repair_release_planned",
                ["authorized_repair_prepare", "authorized_repair_run"],
            ),
            "run": operation(
                "run",
                "Run gates, freeze content-identified artifacts, create one immutable tag, deploy, and verify the prepared lineage.",
                "external_write",
                {"version": version, "target": target, "migration": migration},
                "release_workflow_completed",
                ["report_release_evidence", "retry_same_fixed_tag", "repair_next_patch"],
            ),
            "promote-plan": operation(
                "promote-plan",
                "Plan one exact release tag promotion to a target and report whether its immutable target artifact already exists.",
                "read_only",
                {"tag": release_tag, "target": target},
                "release_promotion_planned",
                ["authorized_release_promotion"],
            ),
            "promote": operation(
                "promote",
                "Deploy one exact release tag to a target, appending only that target's first immutable artifact manifest when needed.",
                "external_write",
                {"tag": release_tag, "target": target, "migration": migration},
                "release_promoted",
                ["report_promotion_evidence", "retry_same_fixed_tag", "repair_next_patch"],
            ),
            "repair": operation(
                "repair",
                "Freeze, tag, deploy, and verify one prepared immediate-next-patch repair lineage.",
                "external_write",
                {"base_tag": base_tag, "version": version, "target": target, "migration": migration},
                "repair_release_workflow_completed",
                ["report_repair_evidence", "retry_same_fixed_tag"],
            ),
            "retry": operation(
                "retry",
                "Retry deployment from one exact annotated tag, commit, frozen artifact manifest, and target in a fresh detached worktree.",
                "external_write",
                {
                    "tag": release_tag,
                    "target": target,
                },
                "fixed_tag_retry_completed",
                ["report_retry_evidence", "repair_next_patch", "request_rollback_authority"],
            ),
        },
    }
    return normalize_contract(
        raw,
        task="release-deployment",
        repo_root=repo_root,
        skill_root=skill_root,
        field="managed release contract",
    )


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


def render_manifest(manifest: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    lines: list[str] = []

    def emit(mapping: dict[str, Any], indent: int = 0) -> None:
        prefix = " " * indent
        for key, value in mapping.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                emit(value, indent + 2)
            elif isinstance(value, list):
                lines.append(f"{prefix}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"{prefix}  -")
                        emit(item, indent + 4)
                    else:
                        lines.append(f"{prefix}  - {item}")
            else:
                lines.append(f"{prefix}{key}: {value}")

    emit(manifest)
    return "\n".join(lines) + "\n"


def resolve_task(
    task: str,
    cwd: Path,
    output_format: str = "yaml",
    selected_operation: str | None = None,
) -> tuple[str, Path | None, str]:
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
    config_schema = ""
    managed_release = False
    if config:
        schema = config.get("schema")
        if schema == f"{SKILL_NAME}.config.v1":
            config_schema = schema
            require_exact_keys(config, {"schema", "profile", "tasks"}, "config.yaml")
            if task == "port-allocation":
                raise ResolveError(
                    "port-allocation requires project-governance.config.v2"
                )
            allowed_tasks = set(DEFAULT_BASES) - {"port-allocation"}
        elif schema == f"{SKILL_NAME}.config.v2":
            config_schema = schema
            require_exact_keys(
                config, {"schema", "profile", "ports", "tasks"}, "config.yaml"
            )
            allowed_tasks = set(DEFAULT_BASES)
            port_config = normalize_port_config(config.get("ports"))
        elif schema == f"{SKILL_NAME}.config.v3":
            config_schema = schema
            require_exact_keys(config, {"schema", "profile", "ports", "tasks"}, "config.yaml")
            allowed_tasks = set(DEFAULT_BASES)
            port_config = normalize_port_config(config.get("ports"))
        else:
            raise ResolveError(
                "config.yaml schema must be "
                "project-governance.config.v1, project-governance.config.v2, "
                "or project-governance.config.v3"
            )
        profile = require_string(config.get("profile"), "profile")
        tasks = require_mapping(config.get("tasks"), "tasks")
        require_exact_keys(tasks, allowed_tasks, "tasks")
        raw_task_config = tasks.get(task)
        if raw_task_config is None and task == "release-deployment":
            managed_release = True
            task_config = {}
        else:
            task_config = require_mapping(raw_task_config, f"tasks.{task}")
            if config_schema == f"{SKILL_NAME}.config.v3":
                require_exact_keys(
                    task_config, {"base", "profile", "contract"}, f"tasks.{task}"
                )
            else:
                require_exact_keys(
                    task_config, {"base", "profile", "commands"}, f"tasks.{task}"
                )
        sources_configured = True
    else:
        sources_configured = False
        managed_release = task == "release-deployment"

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

    contract: dict[str, Any] | None = None
    if managed_release:
        contract = managed_release_contract(repo_root, skill_root)
        release_config_path = config_root / "release-workflow.json"
        release_config_text = ""
        if release_config_path.is_file():
            release_config_text = release_config_path.read_text(encoding="utf-8")
            sources["release_config"] = display_path(release_config_path, repo_root)
        workflow = {
            "mode": "managed",
            "configuration": "present" if release_config_text else "bootstrap_required",
        }
    elif config_schema == f"{SKILL_NAME}.config.v3":
        contract_path = resolve_path(
            require_string(task_config.get("contract"), f"tasks.{task}.contract"),
            config_root,
            f"tasks.{task}.contract",
        )
        contract = normalize_contract(
            load_json(contract_path, f"tasks.{task}.contract"),
            task=task,
            repo_root=repo_root,
            skill_root=skill_root,
            field=f"tasks.{task}.contract",
        )
        release_config_text = ""
        workflow = {"mode": "project_contract", "configuration": "project_owned"}
        sources["contract"] = display_path(contract_path, repo_root)

    if contract is not None:
        if selected_operation is not None and selected_operation not in contract["operations"]:
            raise ResolveError(
                f"operation {selected_operation!r} is not declared for task {task}"
            )
        policy_paths = [display_path(base_path, repo_root)]
        if profile_text:
            policy_paths.append(sources["profile"])
        state = {
            "schema": "project-governance.resolved-task.v1",
            "status": "ready",
            "skill": SKILL_NAME,
            "task": task,
            "profile": profile,
            "state": "resolved",
            "contract": contract,
            "policy_refs": policy_paths,
            "sources": sources,
            "workflow": workflow,
        }
        hash_input = {
            "resolver_version": RESOLVER_VERSION,
            "state": state,
            "ports": port_config,
            "config": config_text,
            "release_config": release_config_text,
        }
        digest = hashlib.sha256(
            json.dumps(hash_input, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        instructions_id = f"{SKILL_NAME}/{task}@{digest}"
        state["instructions_id"] = instructions_id
        state["entry_command"] = [
            "uv",
            "run",
            "python",
            str(skill_root / "scripts" / "project-governance.py"),
            "--cwd",
            str(repo_root),
            "execute",
            "--task",
            task,
            "--operation",
            "<operation>",
        ]
        state_text = json.dumps(state, indent=2, sort_keys=True) + "\n"
        contract_view = contract
        if selected_operation is not None:
            contract_view = {
                **contract,
                "operations": {
                    selected_operation: contract["operations"][selected_operation]
                },
            }
        manifest = {
            "status": "ready",
            "skill": SKILL_NAME,
            "task": task,
            "profile": profile,
            "state": "resolved",
            "instructions_id": instructions_id,
            "policy_refs": policy_paths,
            "contract": contract_view,
            "entry_command": state["entry_command"],
            "sources": sources,
            "workflow": workflow,
        }
        if selected_operation is not None:
            manifest["selected_operation"] = selected_operation
            manifest["entry_command"][-1] = selected_operation
        if task == "port-allocation" and port_config is not None:
            manifest["ports"] = {
                "project_segment": port_config["project_segment"],
                "instance_count": len(port_config["instances"]),
                "service_count": len(port_config["services"]),
            }
        return render_manifest(manifest, output_format), None, state_text

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

    manifest: dict[str, Any] = {
        "status": "ready",
        "skill": SKILL_NAME,
        "task": task,
        "profile": profile,
        "instructions_id": instructions_id,
        "instructions": {"path": display_path(cache_path, repo_root)},
        "sources": dict(sorted(sources.items())),
    }
    if normalized_commands:
        manifest["commands"] = dict(sorted(normalized_commands.items()))
    if task == "port-allocation" and port_config is not None:
        manifest["ports"] = {
            "project_segment": port_config["project_segment"],
            "instance_count": len(port_config["instances"]),
            "service_count": len(port_config["services"]),
        }
    return render_manifest(manifest, output_format), cache_path, instructions


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve project-governance task instructions."
    )
    parser.add_argument("--task", required=True, choices=tuple(DEFAULT_BASES))
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument(
        "--emit", choices=("manifest", "instructions"), default="manifest"
    )
    parser.add_argument("--format", choices=("yaml", "json"), default="yaml")
    parser.add_argument("--operation")
    args = parser.parse_args()
    try:
        manifest, _, instructions = resolve_task(
            args.task, args.cwd, args.format, args.operation
        )
    except ResolveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(instructions if args.emit == "instructions" else manifest, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
