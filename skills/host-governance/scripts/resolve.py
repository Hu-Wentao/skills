#!/usr/bin/env python3
"""Resolve generic and repository-owned host-governance task contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

SKILL_NAME = "host-governance"
RESOLVER_VERSION = "2"
SKILL_ROOT = Path(__file__).resolve().parents[1]


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
    except ImportError:
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


def normalize_environment(value: Any, field: str) -> dict[str, dict[str, bool]]:
    environment = require_mapping(value, field)
    normalized: dict[str, dict[str, bool]] = {}
    for raw_name, raw_requirement in environment.items():
        name = require_string(raw_name, f"{field} key")
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", name):
            raise ResolveError(f"{field} key must be an uppercase environment name")
        requirement_field = f"{field}.{name}"
        requirement = require_mapping(raw_requirement, requirement_field)
        require_exact_keys(requirement, {"required", "sensitive"}, requirement_field)
        normalized[name] = {
            "required": require_boolean(
                requirement.get("required", False), f"{requirement_field}.required"
            ),
            "sensitive": require_boolean(
                requirement.get("sensitive", False), f"{requirement_field}.sensitive"
            ),
        }
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
        "host-governance.task-contract.v1"
    ):
        raise ResolveError(f"{field}.schema must be host-governance.task-contract.v1")
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
                "environment",
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
            "host_write",
            "external_write",
            "composite_write",
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
        normalized_operation = {
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
        if "environment" in operation:
            normalized_operation["environment"] = normalize_environment(
                operation["environment"], f"{operation_field}.environment"
            )
        normalized_operations[name] = normalized_operation
    return {
        "schema": "host-governance.task-contract.v1",
        "id": require_string(value.get("id"), f"{field}.id"),
        "task": contract_task,
        "operations": normalized_operations,
    }


def resolve_task(
    task: str, cwd: Path, operation: str | None = None
) -> tuple[str, Path | None, str, dict[str, Any] | None]:
    repo_root = find_repo_root(cwd)
    skill_root = SKILL_ROOT
    config_root = repo_root / ".agents" / "skills-config" / SKILL_NAME
    config_path = config_root / "config.yaml"
    cache_root = repo_root / ".agents" / ".cache" / SKILL_NAME

    config, config_text = load_config(config_path)
    profile = "generic"
    schema = ""
    task_config: dict[str, Any] = {}
    if config:
        schema = require_string(config.get("schema"), "config.yaml schema")
        expected = {f"{SKILL_NAME}.config.v1", f"{SKILL_NAME}.config.v2"}
        if schema not in expected:
            raise ResolveError(
                f"config.yaml schema must be one of: {', '.join(sorted(expected))}"
            )
        profile = require_string(config.get("profile", "project"), "profile")
        tasks = require_mapping(config.get("tasks"), "tasks")
        task_config = require_mapping(tasks.get(task), f"tasks.{task}")

    base_value = str(task_config.get("base", f"references/{task}.md"))
    base_path = resolve_path(base_value, skill_root, f"tasks.{task}.base")
    base_text = base_path.read_text(encoding="utf-8").strip()
    sources = {"base": display_path(base_path, repo_root)}
    if config:
        sources["project_config"] = display_path(config_path, repo_root)

    profile_text = ""
    profile_path: Path | None = None
    profile_value = task_config.get("profile")
    if profile_value is not None:
        profile_path = resolve_path(
            str(profile_value), config_root, f"tasks.{task}.profile"
        )
        profile_text = profile_path.read_text(encoding="utf-8").strip()
        sources["profile"] = display_path(profile_path, repo_root)

    commands_raw = task_config.get("commands", {})
    commands = require_mapping(commands_raw, f"tasks.{task}.commands")
    normalized_commands = {str(key): str(value) for key, value in commands.items()}
    if schema == f"{SKILL_NAME}.config.v2" and normalized_commands:
        raise ResolveError("host-governance.config.v2 uses contract instead of commands")

    parts = [
        f"# Resolved {SKILL_NAME} Instructions",
        "",
        f"- Task: `{task}`",
        f"- Profile: `{profile}`",
        "",
        "## Resolution Policy",
        "",
        "Project instructions override generic configurable defaults when both ",
        "address the same choice. They cannot override external authority, the ",
        "skill's non-configurable safety invariants, schema validation, or ",
        "path-containment rules. Resolution never executes configured operations.",
        "",
        "## Generic Instructions",
        "",
        base_text,
    ]
    if profile_text:
        parts.extend(["", "## Project Instructions", "", profile_text])
    if normalized_commands:
        parts.extend(["", "## Declared Commands", ""])
        parts.extend(
            f"- `{name}`: `{command}`"
            for name, command in sorted(normalized_commands.items())
        )
    instructions = "\n".join(parts).rstrip() + "\n"

    contract: dict[str, Any] | None = None
    contract_for_hash: dict[str, Any] | None = None
    contract_path: Path | None = None
    if schema == f"{SKILL_NAME}.config.v2":
        contract_value = task_config.get("contract")
        if contract_value is None:
            raise ResolveError(f"tasks.{task}.contract is required for config.v2")
        contract_path = resolve_path(
            str(contract_value), config_root, f"tasks.{task}.contract"
        )
        contract = normalize_contract(
            load_json(contract_path, f"tasks.{task}.contract"),
            task=task,
            repo_root=repo_root,
            skill_root=skill_root,
            field=f"tasks.{task}.contract",
        )
        contract_for_hash = contract
        sources["contract"] = display_path(contract_path, repo_root)
        if operation is not None:
            if operation not in contract["operations"]:
                raise ResolveError(f"operation is not configured for {task}: {operation}")
            contract = {
                **contract,
                "operations": {operation: contract["operations"][operation]},
            }
    elif operation is not None:
        raise ResolveError(
            "operation execution requires host-governance.config.v2 with a task contract"
        )

    hash_input = {
        "resolver_version": RESOLVER_VERSION,
        "skill": SKILL_NAME,
        "task": task,
        "profile": profile,
        "base": base_text,
        "profile_text": profile_text,
        "commands": normalized_commands,
        "contract": contract_for_hash,
        "config": config_text,
    }
    digest = hashlib.sha256(
        json.dumps(hash_input, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    instructions_id = f"{SKILL_NAME}/{task}@{digest}"

    cache_path: Path | None = None
    if contract is None:
        cache_path = cache_root / task / f"{digest}.md"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(instructions, encoding="utf-8")

    manifest_lines = [
        "status: ready",
        f"skill: {SKILL_NAME}",
        f"task: {task}",
        f"profile: {profile}",
        f"instructions_id: {instructions_id}",
    ]
    if cache_path is not None:
        manifest_lines.extend(
            ["instructions:", f"  path: {display_path(cache_path, repo_root)}"]
        )
    manifest_lines.append("sources:")
    manifest_lines.extend(
        f"  {name}: {value}" for name, value in sorted(sources.items())
    )
    if normalized_commands:
        manifest_lines.append("commands:")
        manifest_lines.extend(
            f"  {name}: {value}"
            for name, value in sorted(normalized_commands.items())
        )

    resolved: dict[str, Any] | None = None
    if contract is not None:
        policy_refs = [display_path(base_path, repo_root)]
        if profile_path is not None:
            policy_refs.append(display_path(profile_path, repo_root))
        entry_command = [
            "uv",
            "run",
            "python",
            str(skill_root / "scripts" / "host-governance.py"),
            "--cwd",
            str(repo_root),
            "execute",
            "--task",
            task,
        ]
        if operation is not None:
            entry_command.extend(["--operation", operation])
        resolved = {
            "status": "ready",
            "state": "resolved",
            "skill": SKILL_NAME,
            "task": task,
            "profile": profile,
            "instructions_id": instructions_id,
            "policy_refs": policy_refs,
            "sources": sources,
            "contract": contract,
            "selected_operation": operation,
            "entry_command": entry_command,
            "workflow": {"mode": "project_contract", "configuration": "project_owned"},
            "project_root": str(repo_root),
        }
    return "\n".join(manifest_lines) + "\n", cache_path, instructions, resolved


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Resolve {SKILL_NAME} task instructions or contract."
    )
    parser.add_argument("--task", default="control")
    parser.add_argument("--operation")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument(
        "--emit", choices=("manifest", "instructions"), default="manifest"
    )
    parser.add_argument("--format", choices=("manifest", "json"), default="manifest")
    args = parser.parse_args()
    try:
        manifest, _, instructions, resolved = resolve_task(
            args.task, args.cwd, args.operation
        )
        if args.format == "json":
            if resolved is None:
                raise ResolveError(
                    "JSON task resolution requires host-governance.config.v2"
                )
            print(json.dumps(resolved, indent=2))
        else:
            print(instructions if args.emit == "instructions" else manifest, end="")
    except ResolveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
