#!/usr/bin/env python3
"""Project-neutral release lineage and deployment workflow.

The workflow owns Git identity, isolated worktrees, immutable tags, artifact
identity, locks, and retry/repair semantics. Projects supply only deterministic
argv hooks in release-workflow.json.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA = "project-governance.release-workflow.v1"
EVENT_SCHEMA = "project-governance.release-event.v1"
ARTIFACT_SCHEMA = "project-governance.artifact-freeze.v1"
DEPLOYED_RELEASE_SCHEMA = "project-governance.deployed-release.v1"
SEMVER = re.compile(r"^(?P<major>0|[1-9][0-9]*)\.(?P<minor>0|[1-9][0-9]*)\.(?P<patch>0|[1-9][0-9]*)$")
TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
VERSION_KINDS = {"package-json", "pyproject", "pubspec"}


class WorkflowError(RuntimeError):
    def __init__(self, code: str, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


def emit(event: str, **fields: Any) -> None:
    print(json.dumps({"schema": EVENT_SCHEMA, "event": event, **fields}, sort_keys=True))


def release_boundary() -> dict[str, str]:
    """Describe the authority boundary after a committed source is frozen."""

    return {
        "identityAuthority": "retained_lineage",
        "controlWorktreeAfterFreeze": "excluded",
        "postReleaseIntegration": "separate",
    }


def run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    capture: bool = True,
    code: str = "COMMAND_FAILED",
) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
        check=False,
    )
    if result.returncode != 0:
        raise WorkflowError(code, f"command failed with exit {result.returncode}: {argv[0]}")
    return result.stdout.strip() if capture else ""


def run_bytes(argv: list[str], *, cwd: Path, code: str) -> bytes:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, check=False)
    if result.returncode != 0:
        raise WorkflowError(code, f"command failed with exit {result.returncode}: {argv[0]}")
    return result.stdout


def git(root: Path, *args: str, code: str = "GIT_FAILED") -> str:
    return run(["git", *args], cwd=root, code=code)


def repo_root(cwd: Path) -> Path:
    output = run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, code="NOT_A_GIT_REPOSITORY")
    return Path(output).resolve()


def common_git_dir(root: Path) -> Path:
    value = Path(git(root, "rev-parse", "--git-common-dir"))
    return (root / value).resolve() if not value.is_absolute() else value.resolve()


def runtime_root(root: Path) -> Path:
    path = common_git_dir(root) / "project-governance-release"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path(root: Path) -> Path:
    return root / ".agents" / "skills-config" / "project-governance" / "release-workflow.json"


def require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkflowError("INVALID_RELEASE_CONFIG", f"{field} must be an object", exit_code=2)
    return value


def require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError("INVALID_RELEASE_CONFIG", f"{field} must be a non-empty string", exit_code=2)
    return value


def argv_value(value: Any, field: str, *, allow_empty: bool = False) -> list[str]:
    if allow_empty and value in (None, []):
        return []
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise WorkflowError("INVALID_RELEASE_CONFIG", f"{field} must be a non-empty argv array", exit_code=2)
    return list(value)


def contained_file(root: Path, relative: str, field: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise WorkflowError("INVALID_RELEASE_CONFIG", f"{field} escapes the repository", exit_code=2) from exc
    if not candidate.is_file():
        raise WorkflowError("INVALID_RELEASE_CONFIG", f"{field} does not exist: {relative}", exit_code=2)
    return candidate


def load_config(
    root: Path,
    *,
    require_complete: bool = False,
    require_hotfix: bool = False,
    target: str | None = None,
) -> dict[str, Any]:
    path = config_path(root)
    if not path.is_file():
        raise WorkflowError(
            "RELEASE_WORKFLOW_NOT_CONFIGURED",
            f"missing {path.relative_to(root)}; run release bootstrap-plan and an authorized release bootstrap",
            exit_code=2,
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError("INVALID_RELEASE_CONFIG", f"cannot parse {path}: {exc}", exit_code=2) from exc
    config = require_mapping(raw, "release workflow config")
    allowed = {"schema", "integration_branch", "version", "gates", "artifact", "targets", "migration", "hotfix"}
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise WorkflowError("INVALID_RELEASE_CONFIG", f"unsupported config keys: {', '.join(unknown)}", exit_code=2)
    if config.get("schema") != SCHEMA:
        raise WorkflowError("INVALID_RELEASE_CONFIG", f"schema must be {SCHEMA}", exit_code=2)
    require_string(config.get("integration_branch"), "integration_branch")
    version = require_mapping(config.get("version"), "version")
    if set(version) != {"kind", "path"}:
        raise WorkflowError("INVALID_RELEASE_CONFIG", "version must contain only kind and path", exit_code=2)
    if version.get("kind") not in VERSION_KINDS:
        raise WorkflowError("INVALID_RELEASE_CONFIG", f"version.kind must be one of: {', '.join(sorted(VERSION_KINDS))}", exit_code=2)
    contained_file(root, require_string(version.get("path"), "version.path"), "version.path")
    gates = config.get("gates", [])
    if not isinstance(gates, list):
        raise WorkflowError("INVALID_RELEASE_CONFIG", "gates must be a list of argv arrays", exit_code=2)
    for index, command in enumerate(gates):
        argv_value(command, f"gates[{index}]")
    artifact = require_mapping(config.get("artifact", {}), "artifact")
    if set(artifact) - {"freeze"}:
        raise WorkflowError("INVALID_RELEASE_CONFIG", "artifact contains unsupported keys", exit_code=2)
    freeze = argv_value(artifact.get("freeze"), "artifact.freeze", allow_empty=True)
    targets = require_mapping(config.get("targets", {}), "targets")
    for name, value in targets.items():
        if not SAFE_TARGET.fullmatch(str(name)):
            raise WorkflowError("INVALID_RELEASE_CONFIG", f"invalid target name: {name}", exit_code=2)
        item = require_mapping(value, f"targets.{name}")
        if set(item) - {"inspect", "deploy", "verify"} or not {"deploy", "verify"}.issubset(item):
            raise WorkflowError(
                "INVALID_RELEASE_CONFIG",
                f"targets.{name} must contain deploy and verify, with optional inspect",
                exit_code=2,
            )
        if "inspect" in item:
            argv_value(item.get("inspect"), f"targets.{name}.inspect")
        argv_value(item.get("deploy"), f"targets.{name}.deploy")
        argv_value(item.get("verify"), f"targets.{name}.verify")
    hotfix = config.get("hotfix")
    if hotfix is not None:
        hotfix_value = require_mapping(hotfix, "hotfix")
        if set(hotfix_value) != {"scope", "gates", "freeze"}:
            raise WorkflowError("INVALID_RELEASE_CONFIG", "hotfix must contain scope, gates, and freeze", exit_code=2)
        argv_value(hotfix_value.get("scope"), "hotfix.scope")
        hotfix_gates = hotfix_value.get("gates")
        if not isinstance(hotfix_gates, list) or not hotfix_gates:
            raise WorkflowError("INVALID_RELEASE_CONFIG", "hotfix.gates must be a non-empty list of argv arrays", exit_code=2)
        for index, command in enumerate(hotfix_gates):
            argv_value(command, f"hotfix.gates[{index}]")
        argv_value(hotfix_value.get("freeze"), "hotfix.freeze")
    migration = config.get("migration")
    if migration is not None:
        migration_value = require_mapping(migration, "migration")
        if set(migration_value) != {"preflight", "apply", "verify"}:
            raise WorkflowError("INVALID_RELEASE_CONFIG", "migration must contain preflight, apply, and verify", exit_code=2)
        for name in ("preflight", "apply", "verify"):
            argv_value(migration_value.get(name), f"migration.{name}")
    if require_complete:
        missing: list[str] = []
        if not freeze:
            missing.append("artifact.freeze")
        if target is None or target not in targets:
            missing.append(f"targets.{target or '<target>'}")
        if missing:
            raise WorkflowError("RELEASE_WORKFLOW_NOT_CONFIGURED", f"missing release hooks: {', '.join(missing)}", exit_code=2)
    if require_hotfix:
        missing_hotfix: list[str] = []
        if target is None or target not in targets:
            missing_hotfix.append(f"targets.{target or '<target>'}")
        elif "inspect" not in targets[target]:
            missing_hotfix.append(f"targets.{target}.inspect")
        if hotfix is None:
            missing_hotfix.append("hotfix")
        if missing_hotfix:
            raise WorkflowError(
                "HOTFIX_WORKFLOW_NOT_CONFIGURED",
                f"missing hotfix hooks: {', '.join(missing_hotfix)}",
                exit_code=2,
            )
    return config


def load_config_from_ref(root: Path, ref: str, *, require_complete: bool, target: str | None) -> dict[str, Any]:
    relative_config = Path(".agents/skills-config/project-governance/release-workflow.json")
    config_text = git(root, "show", f"{ref}:{relative_config.as_posix()}", code="RELEASE_CONFIG_AT_TAG_MISSING")
    try:
        raw = require_mapping(json.loads(config_text), "release workflow config")
        version = require_mapping(raw.get("version"), "version")
        version_relative = require_string(version.get("path"), "version.path")
    except json.JSONDecodeError as exc:
        raise WorkflowError("INVALID_RELEASE_CONFIG", f"cannot parse release config at {ref}", exit_code=2) from exc
    with tempfile.TemporaryDirectory(prefix="release-config-") as temporary_name:
        temporary = Path(temporary_name)
        config_copy = temporary / relative_config
        config_copy.parent.mkdir(parents=True, exist_ok=True)
        config_copy.write_text(config_text + "\n", encoding="utf-8")
        version_copy = (temporary / version_relative).resolve()
        try:
            version_copy.relative_to(temporary.resolve())
        except ValueError as exc:
            raise WorkflowError("INVALID_RELEASE_CONFIG", "version.path escapes the repository", exit_code=2) from exc
        version_copy.parent.mkdir(parents=True, exist_ok=True)
        version_copy.write_text(git(root, "show", f"{ref}:{version_relative}", code="INVALID_RELEASE_CONFIG") + "\n", encoding="utf-8")
        return load_config(temporary, require_complete=require_complete, target=target)


def config_status(root: Path, target: str | None) -> dict[str, Any]:
    try:
        config = load_config(root)
    except WorkflowError as exc:
        if exc.code == "RELEASE_WORKFLOW_NOT_CONFIGURED":
            return {"configured": False, "complete": False, "reason": exc.code}
        raise
    freeze = bool(config.get("artifact", {}).get("freeze"))
    target_ready = target in config.get("targets", {}) if target else bool(config.get("targets"))
    return {
        "configured": True,
        "complete": freeze and target_ready,
        "integrationBranch": config["integration_branch"],
        "targets": sorted(config.get("targets", {})),
        "missing": [name for name, present in (("artifact.freeze", freeze), (f"targets.{target or '<target>'}", target_ready)) if not present],
    }


def stable_tags(root: Path) -> list[str]:
    return [tag for tag in git(root, "tag", "--list", "v*", "--sort=-version:refname").splitlines() if TAG.fullmatch(tag)]


def ref_exists(root: Path, ref: str) -> bool:
    return subprocess.run(["git", "show-ref", "--verify", "--quiet", ref], cwd=root, check=False).returncode == 0


def full_commit(root: Path, ref: str) -> str:
    value = git(root, "rev-parse", f"{ref}^{{commit}}", code="INVALID_RELEASE_IDENTITY")
    if not COMMIT.fullmatch(value):
        raise WorkflowError("INVALID_RELEASE_IDENTITY", f"cannot resolve full commit for {ref}")
    return value


def semver_tuple(value: str) -> tuple[int, int, int]:
    match = SEMVER.fullmatch(value)
    if not match:
        raise WorkflowError("INVALID_RELEASE_VERSION", f"invalid SemVer: {value}", exit_code=2)
    return tuple(int(match.group(name)) for name in ("major", "minor", "patch"))


def tag_version(tag: str) -> tuple[int, int, int]:
    if not TAG.fullmatch(tag):
        raise WorkflowError("INVALID_RELEASE_TAG", f"invalid stable tag: {tag}", exit_code=2)
    return semver_tuple(tag[1:])


def bump_patch(value: tuple[int, int, int]) -> tuple[int, int, int]:
    return value[0], value[1], value[2] + 1


def format_semver(value: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in value)


def committed_integration_branch(root: Path) -> str:
    relative = config_path(root).relative_to(root).as_posix()
    text = git(root, "show", f"HEAD:{relative}", code="RELEASE_CONFIG_AT_COMMIT_MISSING")
    try:
        value = require_mapping(json.loads(text), "release workflow config")
    except json.JSONDecodeError as exc:
        raise WorkflowError("INVALID_RELEASE_CONFIG", "cannot parse committed release workflow config", exit_code=2) from exc
    return require_string(value.get("integration_branch"), "integration_branch")


def current_controller_commit(root: Path) -> str:
    branch = committed_integration_branch(root)
    ref = f"refs/heads/{branch}"
    if not ref_exists(root, ref):
        raise WorkflowError("INTEGRATION_BRANCH_MISSING", f"missing {ref}", exit_code=2)
    return full_commit(root, ref)


@contextmanager
def materialized_ref(root: Path, ref: str) -> Iterator[Path]:
    archive_bytes = run_bytes(
        ["git", "archive", "--format=tar", ref],
        cwd=root,
        code="CONTROLLER_SOURCE_ARCHIVE_FAILED",
    )
    with tempfile.TemporaryDirectory(prefix="project-governance-controller-") as temporary_name:
        destination = Path(temporary_name)
        try:
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
                archive.extractall(destination, filter="data")
        except (tarfile.TarError, ValueError, OSError) as exc:
            raise WorkflowError(
                "CONTROLLER_SOURCE_ARCHIVE_INVALID",
                f"cannot materialize committed controller source: {exc}",
                exit_code=2,
            ) from exc
        yield destination


def is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, descendant], cwd=root, check=False).returncode == 0


def control_worktree(root: Path) -> dict[str, Any]:
    return {
        "branch": git(root, "branch", "--show-current"),
        "commit": full_commit(root, "HEAD"),
        "dirty": bool(git(root, "status", "--porcelain")),
    }


def state_path(root: Path, version: str) -> Path:
    return runtime_root(root) / "releases" / f"v{version}.json"


def legacy_artifact_path(root: Path, tag: str) -> Path:
    return runtime_root(root) / "artifacts" / f"{tag}.json"


def artifact_path(root: Path, tag: str, target: str) -> Path:
    return runtime_root(root) / "artifacts" / tag / f"{target}.json"


def transaction_path(root: Path, target: str) -> Path:
    return runtime_root(root) / "transactions" / f"{target}.json"


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def atomic_json_once(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise WorkflowError("ARTIFACT_MANIFEST_EXISTS", f"refusing to replace {path}", exit_code=2) from exc
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path, code: str) -> dict[str, Any]:
    if not path.is_file():
        raise WorkflowError(code, f"required state is missing: {path}")
    try:
        return require_mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    except json.JSONDecodeError as exc:
        raise WorkflowError(code, f"invalid state file: {path}") from exc


@contextmanager
def release_lock(root: Path) -> Iterator[None]:
    path = runtime_root(root) / "lock"
    try:
        path.mkdir()
        (path / "owner.json").write_text(json.dumps({"pid": os.getpid(), "cwd": str(root)}) + "\n", encoding="utf-8")
    except FileExistsError as exc:
        raise WorkflowError("RELEASE_LOCKED", f"another release operation owns {path}", exit_code=2) from exc
    try:
        yield
    finally:
        shutil.rmtree(path, ignore_errors=True)


def worktree_root(root: Path) -> Path:
    digest = hashlib.sha256(str(common_git_dir(root)).encode()).hexdigest()[:10]
    path = root.parent / f".{root.name}-release-worktrees-{digest}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def branch_path(root: Path, branch: str) -> Path:
    return worktree_root(root) / branch.replace("/", "-")


def current_version(root: Path, version: dict[str, Any]) -> str:
    path = contained_file(root, version["path"], "version.path")
    text = path.read_text(encoding="utf-8")
    kind = version["kind"]
    if kind == "package-json":
        value = json.loads(text).get("version")
    elif kind == "pyproject":
        project = tomllib.loads(text).get("project")
        value = project.get("version") if isinstance(project, dict) else None
    else:
        match = re.search(r"(?m)^version:\s*([^+\s]+)(?:\+[^\s]+)?\s*$", text)
        value = match.group(1) if match else None
    if not isinstance(value, str) or not SEMVER.fullmatch(value):
        raise WorkflowError("INVALID_PROJECT_VERSION", f"cannot read SemVer from {version['path']}")
    return value


def write_version(root: Path, version_config: dict[str, Any], desired: str) -> Path:
    if not SEMVER.fullmatch(desired):
        raise WorkflowError("INVALID_RELEASE_VERSION", f"invalid SemVer: {desired}", exit_code=2)
    path = contained_file(root, version_config["path"], "version.path")
    text = path.read_text(encoding="utf-8")
    kind = version_config["kind"]
    if kind == "package-json":
        pattern = re.compile(r'(?m)^(\s*"version"\s*:\s*")[^"]+("\s*,?\s*)$')
        updated, count = pattern.subn(rf"\g<1>{desired}\g<2>", text, count=1)
    elif kind == "pyproject":
        section = re.search(r"(?ms)^\[project\]\s*$.*?(?=^\[|\Z)", text)
        if section is None:
            updated, count = text, 0
        else:
            block = section.group(0)
            pattern = re.compile(r"(?m)^(version\s*=\s*[\"'])[^\"']+([\"']\s*)$")
            replaced, count = pattern.subn(rf"\g<1>{desired}\g<2>", block, count=1)
            updated = text[: section.start()] + replaced + text[section.end() :]
    else:
        pattern = re.compile(r"(?m)^(version:\s*)[^+\s]+((?:\+[^\s]+)?\s*)$")
        updated, count = pattern.subn(rf"\g<1>{desired}\g<2>", text, count=1)
    if count != 1:
        raise WorkflowError("INVALID_PROJECT_VERSION", f"cannot update version in {version_config['path']}")
    path.write_text(updated, encoding="utf-8")
    return path


def expand(argv: list[str], values: dict[str, str]) -> list[str]:
    try:
        return [item.format_map(values) for item in argv]
    except (KeyError, ValueError) as exc:
        raise WorkflowError(
            "INVALID_RELEASE_CONFIG",
            f"unsupported hook placeholder: {exc}",
            exit_code=2,
        ) from exc


def hook_env(
    root: Path,
    *,
    version: str,
    tag: str,
    target: str,
    worktree: Path,
    artifact: Path,
    hotfix: dict[str, Any] | None = None,
) -> dict[str, str]:
    result = {
        **os.environ,
        "PROJECT_GOVERNANCE_RELEASE_VERSION": version,
        "PROJECT_GOVERNANCE_RELEASE_TAG": tag,
        "PROJECT_GOVERNANCE_RELEASE_TARGET": target,
        "PROJECT_GOVERNANCE_RELEASE_WORKTREE": str(worktree),
        "PROJECT_GOVERNANCE_ARTIFACT_MANIFEST": str(artifact),
        "PROJECT_GOVERNANCE_REPOSITORY": str(root),
    }
    if hotfix:
        result.update(
            {
                "PROJECT_GOVERNANCE_HOTFIX_BASE_TAG": str(hotfix["baseTag"]),
                "PROJECT_GOVERNANCE_HOTFIX_BASE_COMMIT": str(hotfix["baseCommit"]),
                "PROJECT_GOVERNANCE_HOTFIX_EVIDENCE_DIGEST": str(hotfix["evidenceDigest"]),
                "PROJECT_GOVERNANCE_HOTFIX_CONTROLLER_COMMIT": str(hotfix["controllerCommit"]),
                "PROJECT_GOVERNANCE_HOTFIX_SUPERSEDED_RESERVATIONS": json.dumps(
                    hotfix.get("supersededReservations", []), separators=(",", ":")
                ),
            }
        )
    return result


def assert_transaction_compatible(root: Path, state: dict[str, Any]) -> None:
    """Fence a partially switched target to its fixed tag or patch repair."""

    path = transaction_path(root, state["target"])
    if not path.is_file():
        return
    existing = read_json(path, "DEPLOYMENT_TRANSACTION_INVALID")
    if existing.get("status") == "succeeded" or existing.get("tag") == state["tag"]:
        return
    dangerous = {
        "migration_started",
        "migration_completed",
        "deployment_started",
        "deployed",
    }
    if existing.get("phase") not in dangerous:
        return
    if state.get("baseTag") == existing.get("tag"):
        return
    raise WorkflowError(
        "PARTIAL_DEPLOYMENT_RECONCILIATION_REQUIRED",
        f"target {state['target']} is fenced to incomplete {existing.get('tag')}",
        exit_code=2,
    )


def run_hook(argv: list[str], *, cwd: Path, values: dict[str, str], env: dict[str, str], code: str) -> str:
    expanded = expand(argv, values)
    raw_executable = Path(expanded[0])
    if "/" not in expanded[0]:
        executable = shutil.which(expanded[0])
    elif raw_executable.is_absolute():
        executable = str(raw_executable)
    else:
        resolved = (cwd / raw_executable).resolve()
        try:
            resolved.relative_to(cwd.resolve())
        except ValueError as exc:
            raise WorkflowError(
                "INVALID_RELEASE_CONFIG",
                f"hook executable escapes the release worktree: {expanded[0]}",
                exit_code=2,
            ) from exc
        executable = str(resolved)
    if not executable or not Path(executable).exists():
        raise WorkflowError("RELEASE_HOOK_UNAVAILABLE", f"hook executable is unavailable: {expanded[0]}", exit_code=2)
    expanded[0] = executable
    executable_name = Path(executable).name
    inline_or_module = any(flag in expanded[1:3] for flag in ("-c", "-e", "-m"))
    if not inline_or_module and (executable_name == "node" or executable_name.startswith("python")):
        script = next((item for item in expanded[1:] if not item.startswith("-")), None)
        if script:
            script_path = Path(script)
            if not script_path.is_absolute():
                script_path = (cwd / script_path).resolve()
                try:
                    script_path.relative_to(cwd.resolve())
                except ValueError as exc:
                    raise WorkflowError(
                        "INVALID_RELEASE_CONFIG",
                        f"hook script escapes the release worktree: {script}",
                        exit_code=2,
                    ) from exc
            if not script_path.is_file():
                raise WorkflowError("RELEASE_HOOK_UNAVAILABLE", f"hook script is unavailable: {script}", exit_code=2)
    return run(expanded, cwd=cwd, env=env, capture=True, code=code)


def parse_deployed_release_output(
    output: str,
    *,
    root: Path,
    target: str,
    controller_commit: str,
) -> dict[str, str]:
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        raise WorkflowError("DEPLOYED_RELEASE_EVIDENCE_MISSING", "target inspect hook returned no evidence", exit_code=2)
    try:
        value = require_mapping(json.loads(lines[-1]), "target inspect output")
    except json.JSONDecodeError as exc:
        raise WorkflowError(
            "DEPLOYED_RELEASE_EVIDENCE_INVALID",
            "target inspect hook must end with one JSON object",
            exit_code=2,
        ) from exc
    deployed_target = value.get("target")
    tag = value.get("tag")
    commit = value.get("commit")
    evidence_digest = value.get("evidenceDigest")
    if value.get("schema") != DEPLOYED_RELEASE_SCHEMA:
        raise WorkflowError("DEPLOYED_RELEASE_EVIDENCE_INVALID", f"schema must be {DEPLOYED_RELEASE_SCHEMA}", exit_code=2)
    if deployed_target != target or not TAG.fullmatch(str(tag)) or not COMMIT.fullmatch(str(commit)):
        raise WorkflowError("DEPLOYED_RELEASE_EVIDENCE_INVALID", "target, tag, or commit is invalid", exit_code=2)
    if value.get("deploymentStatus") != "succeeded" or value.get("transactionStatus") != "succeeded":
        raise WorkflowError(
            "DEPLOYED_RELEASE_NOT_VERIFIED",
            "current target deployment and transaction must both be succeeded",
            exit_code=2,
        )
    if not DIGEST.fullmatch(str(evidence_digest)):
        raise WorkflowError("DEPLOYED_RELEASE_EVIDENCE_INVALID", "evidenceDigest must be sha256:<64 lowercase hex>", exit_code=2)
    tagged_commit = annotated_tag_commit(root, str(tag))
    if tagged_commit != commit:
        raise WorkflowError(
            "DEPLOYED_RELEASE_IDENTITY_MISMATCH",
            "target evidence does not match the local annotated release tag",
            exit_code=2,
        )
    deployment_tags = git(
        root,
        "for-each-ref",
        "--sort=-creatordate",
        "--format=%(refname:short)",
        f"refs/tags/deploy/{target}/*/{tag}",
    ).splitlines()
    deployment_tag = next(
        (candidate for candidate in deployment_tags if annotated_tag_commit(root, candidate) == commit),
        None,
    )
    if deployment_tag is None:
        raise WorkflowError(
            "DEPLOYED_RELEASE_GIT_EVIDENCE_MISSING",
            f"no annotated deploy/{target} evidence tag matches {tag} {commit}",
            exit_code=2,
        )
    return {
        "target": target,
        "baseTag": str(tag),
        "baseCommit": str(commit),
        "evidenceDigest": str(evidence_digest),
        "deploymentTag": deployment_tag,
        "controllerCommit": controller_commit,
    }


def inspect_deployed_release(
    root: Path,
    *,
    target: str,
    controller_commit: str | None = None,
) -> dict[str, str]:
    selected_controller = controller_commit or current_controller_commit(root)
    with materialized_ref(root, selected_controller) as controller:
        config = load_config(controller, require_hotfix=True, target=target)
        inspect_hook = config["targets"][target]["inspect"]
        values = {
            "version": "",
            "tag": "",
            "target": target,
            "worktree": str(controller),
            "artifact_manifest": "",
        }
        env = {
            **os.environ,
            "PROJECT_GOVERNANCE_RELEASE_TARGET": target,
            "PROJECT_GOVERNANCE_RELEASE_WORKTREE": str(controller),
            "PROJECT_GOVERNANCE_REPOSITORY": str(root),
            "PROJECT_GOVERNANCE_HOTFIX_CONTROLLER_COMMIT": selected_controller,
        }
        output = run_hook(
            inspect_hook,
            cwd=controller,
            values=values,
            env=env,
            code="DEPLOYED_RELEASE_INSPECTION_FAILED",
        )
    return parse_deployed_release_output(
        output,
        root=root,
        target=target,
        controller_commit=selected_controller,
    )


def release_inspect(root: Path, target: str | None) -> int:
    tags = stable_tags(root)
    branch = "main"
    try:
        status = config_status(root, target)
        if status.get("integrationBranch"):
            branch = status["integrationBranch"]
    except WorkflowError:
        raise
    source_ref = f"refs/heads/{branch}"
    source = full_commit(root, source_ref) if ref_exists(root, source_ref) else None
    previous = tags[0] if tags else None
    emit(
        "release_inspected",
        status="ready" if status["complete"] else "bootstrap_required",
        source={"branch": branch, "commit": source},
        previousStableTag=previous,
        previousTagReachable=(is_ancestor(root, previous, source_ref) if previous and source else None),
        target=target,
        workflow=status,
    )
    return 0


def sync_main(root: Path, *, dry_run: bool) -> int:
    config = load_config(root)
    branch = config["integration_branch"]
    source_ref = f"refs/heads/{branch}"
    if not ref_exists(root, source_ref):
        raise WorkflowError("INTEGRATION_BRANCH_MISSING", f"missing {source_ref}", exit_code=2)
    tags = stable_tags(root)
    latest = tags[0] if tags else None
    reachable = latest is None or is_ancestor(root, latest, source_ref)
    control = control_worktree(root)
    event = {
        "integrationBranch": branch,
        "sourceCommit": full_commit(root, source_ref),
        "previousStableTag": latest,
        "syncRequired": not reachable,
        "controlWorktree": control,
    }
    if dry_run or reachable:
        emit("main_sync_inspected" if dry_run else "main_already_synchronized", **event)
        return 0
    if control["branch"] != branch or control["dirty"]:
        raise WorkflowError(
            "MAIN_SYNC_REQUIRES_CLEAN_CONTROL_WORKTREE",
            f"explicit main synchronization requires clean checked-out {branch}; no changes were committed or cleaned",
            exit_code=2,
        )
    with release_lock(root):
        git(root, "merge", "--no-ff", "--no-edit", latest, code="MAIN_SYNC_FAILED")
        event["sourceCommit"] = full_commit(root, "HEAD")
        emit("main_synchronized", **event)
    return 0


def bootstrap_plan(root: Path, preset: str) -> int:
    detected = "custom"
    if (root / "pnpm-lock.yaml").is_file() and (root / "package.json").is_file():
        detected = "node-pnpm"
    elif (root / "pyproject.toml").is_file():
        detected = "python-uv"
    elif (root / "pubspec.yaml").is_file():
        detected = "flutter-fvm"
    emit("release_bootstrap_planned", requestedPreset=preset, detectedPreset=detected, path=str(config_path(root)), exists=config_path(root).exists())
    return 0


def scaffold(root: Path, preset: str) -> dict[str, Any]:
    selected = preset
    if preset == "auto":
        if (root / "pnpm-lock.yaml").is_file() and (root / "package.json").is_file():
            selected = "node-pnpm"
        elif (root / "pyproject.toml").is_file():
            selected = "python-uv"
        elif (root / "pubspec.yaml").is_file():
            selected = "flutter-fvm"
        else:
            raise WorkflowError("RELEASE_PRESET_UNDETECTED", "cannot infer a supported release preset", exit_code=2)
    if selected == "node-pnpm":
        version = {"kind": "package-json", "path": "package.json"}
        package = json.loads((root / "package.json").read_text(encoding="utf-8"))
        scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
        gates = [["pnpm", name] for name in ("lint", "typecheck", "test") if name in scripts]
    elif selected == "python-uv":
        version = {"kind": "pyproject", "path": "pyproject.toml"}
        gates = []
    elif selected == "flutter-fvm":
        version = {"kind": "pubspec", "path": "pubspec.yaml"}
        gates = [["fvm", "flutter", "analyze"], ["fvm", "flutter", "test"]]
    else:
        raise WorkflowError("RELEASE_PRESET_UNSUPPORTED", f"unsupported preset: {selected}", exit_code=2)
    return {
        "schema": SCHEMA,
        "integration_branch": "main",
        "version": version,
        "gates": gates,
        "artifact": {"freeze": []},
        "targets": {},
    }


def bootstrap(root: Path, preset: str) -> int:
    path = config_path(root)
    if path.exists():
        raise WorkflowError("RELEASE_CONFIG_EXISTS", f"refusing to overwrite {path}", exit_code=2)
    value = scaffold(root, preset)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    emit("release_bootstrapped", status="hooks_required", preset=preset, path=str(path), missing=["artifact.freeze", "targets.<target>"])
    return 0


def reservation_records(root: Path, desired_branch: str | None = None) -> list[dict[str, Any]]:
    output = git(
        root,
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/heads/release/v*",
        "refs/heads/repair/v*",
        "refs/heads/hotfix/v*",
    )
    records: list[dict[str, Any]] = []
    for branch in output.splitlines():
        if not branch or branch == desired_branch:
            continue
        version_tag = branch.split("/", 1)[1]
        if ref_exists(root, f"refs/tags/{version_tag}") or not TAG.fullmatch(version_tag):
            continue
        records.append(
            {
                "branch": branch,
                "tag": version_tag,
                "version": tag_version(version_tag),
                "commit": full_commit(root, f"refs/heads/{branch}"),
            }
        )
    return sorted(records, key=lambda item: item["version"])


def active_reservations(root: Path, desired_branch: str) -> list[str]:
    tags = stable_tags(root)
    highest_stable = tag_version(tags[0]) if tags else None
    return [
        item["branch"]
        for item in reservation_records(root, desired_branch)
        if highest_stable is None or item["version"] > highest_stable
    ]


def plan_prepare(root: Path, *, version: str, target: str, base_tag: str | None = None) -> dict[str, Any]:
    config = load_config(root)
    load_config(root, require_complete=True, target=target)
    if not SEMVER.fullmatch(version):
        raise WorkflowError("INVALID_RELEASE_VERSION", f"invalid SemVer: {version}", exit_code=2)
    tag = f"v{version}"
    if ref_exists(root, f"refs/tags/{tag}"):
        raise WorkflowError("RELEASE_VERSION_EXISTS", f"tag already exists: {tag}", exit_code=2)
    if base_tag:
        if not TAG.fullmatch(base_tag) or not ref_exists(root, f"refs/tags/{base_tag}"):
            raise WorkflowError("INVALID_REPAIR_BASE", f"repair base tag is unavailable: {base_tag}", exit_code=2)
        tags = stable_tags(root)
        if not tags or tags[0] != base_tag:
            raise WorkflowError(
                "INVALID_REPAIR_BASE",
                f"repair base must be the highest stable tag {tags[0] if tags else '(none)'}",
                exit_code=2,
            )
        base_version = tag_version(base_tag)
        desired = semver_tuple(version)
        if desired != (base_version[0], base_version[1], base_version[2] + 1):
            raise WorkflowError("INVALID_REPAIR_VERSION", "repair must reserve the immediate next patch", exit_code=2)
        source_ref = f"refs/tags/{base_tag}"
        source_commit = full_commit(root, source_ref)
        branch = f"repair/{tag}"
        lineage = "repair"
    else:
        source_ref = f"refs/heads/{config['integration_branch']}"
        if not ref_exists(root, source_ref):
            raise WorkflowError("INTEGRATION_BRANCH_MISSING", f"missing {source_ref}", exit_code=2)
        source_commit = full_commit(root, source_ref)
        tags = stable_tags(root)
        if tags and not is_ancestor(root, tags[0], source_commit):
            raise WorkflowError("MAIN_SYNC_REQUIRED", f"{tags[0]} is not reachable from {config['integration_branch']}", exit_code=2)
        branch = f"release/{tag}"
        lineage = "release"
    tags = stable_tags(root)
    if tags and semver_tuple(version) <= tag_version(tags[0]):
        raise WorkflowError(
            "RELEASE_VERSION_SUPERSEDED",
            f"version {version} is not greater than highest stable tag {tags[0]}",
            exit_code=2,
        )
    reservations = active_reservations(root, branch)
    if reservations:
        raise WorkflowError("RELEASE_VERSION_RESERVED", f"active release reservation exists: {reservations[0]}", exit_code=2)
    return {
        "version": version,
        "tag": tag,
        "target": target,
        "lineage": lineage,
        "branch": branch,
        "sourceRef": source_ref,
        "sourceCommit": source_commit,
        "worktree": str(branch_path(root, branch)),
        "baseTag": base_tag,
        "releaseBoundary": release_boundary(),
    }


def plan_hotfix_prepare(
    root: Path,
    *,
    version: str,
    target: str,
    base_tag: str,
    base_commit: str,
    evidence_digest: str,
    controller_commit: str | None = None,
) -> dict[str, Any]:
    if not SEMVER.fullmatch(version):
        raise WorkflowError("INVALID_RELEASE_VERSION", f"invalid SemVer: {version}", exit_code=2)
    if not TAG.fullmatch(base_tag) or not COMMIT.fullmatch(base_commit) or not DIGEST.fullmatch(evidence_digest):
        raise WorkflowError("INVALID_HOTFIX_BASE", "hotfix base tag, commit, or evidence digest is invalid", exit_code=2)
    deployed = inspect_deployed_release(root, target=target, controller_commit=controller_commit)
    expected = {
        "baseTag": base_tag,
        "baseCommit": base_commit,
        "evidenceDigest": evidence_digest,
    }
    if any(deployed[name] != value for name, value in expected.items()):
        raise WorkflowError(
            "HOTFIX_BASE_CHANGED",
            "current target deployment no longer matches the authorized hotfix base",
            exit_code=2,
        )
    tag = f"v{version}"
    branch = f"hotfix/{tag}"
    if ref_exists(root, f"refs/tags/{tag}"):
        raise WorkflowError("RELEASE_VERSION_EXISTS", f"tag already exists: {tag}", exit_code=2)
    identities = [tag_version(item) for item in stable_tags(root)]
    reservations = reservation_records(root, branch)
    identities.extend(item["version"] for item in reservations)
    if not identities:
        raise WorkflowError("HOTFIX_VERSION_BASE_MISSING", "hotfix requires an existing stable release identity", exit_code=2)
    required = bump_patch(max(identities))
    desired = semver_tuple(version)
    if desired != required:
        raise WorkflowError(
            "INVALID_HOTFIX_VERSION",
            f"hotfix must reserve next global patch {format_semver(required)}",
            exit_code=2,
        )
    superseded = [item["branch"] for item in reservations if item["branch"] != branch and item["version"] < desired]
    blocking = [item["branch"] for item in reservations if item["branch"] != branch and item["version"] >= desired]
    if blocking:
        raise WorkflowError("RELEASE_VERSION_RESERVED", f"higher release reservation exists: {blocking[0]}", exit_code=2)
    return {
        "version": version,
        "tag": tag,
        "target": target,
        "lineage": "hotfix",
        "branch": branch,
        "sourceRef": f"refs/tags/{base_tag}",
        "sourceCommit": base_commit,
        "worktree": str(branch_path(root, branch)),
        "baseTag": base_tag,
        "baseCommit": base_commit,
        "evidenceDigest": evidence_digest,
        "deploymentTag": deployed["deploymentTag"],
        "controllerCommit": deployed["controllerCommit"],
        "supersededReservations": superseded,
        "releaseBoundary": release_boundary(),
    }


def apply_prepared_plan(
    root: Path,
    *,
    plan: dict[str, Any],
    resume: bool,
    version_config: dict[str, Any],
    event: str,
) -> int:
    branch = plan["branch"]
    version = plan["version"]
    worktree = Path(plan["worktree"])
    existing_state = None
    if resume and state_path(root, version).is_file():
        existing_state = read_json(state_path(root, version), "RELEASE_STATE_INVALID")
        identity_fields = ["version", "tag", "target", "lineage", "branch", "sourceCommit"]
        identity_fields.extend(
            field
            for field in ("baseTag", "baseCommit", "evidenceDigest", "controllerCommit")
            if field in plan
        )
        for field in identity_fields:
            if existing_state.get(field) != plan.get(field):
                raise WorkflowError(
                    "RELEASE_IDENTITY_MISMATCH",
                    f"retained state field {field} does not match the requested lineage",
                    exit_code=2,
                )
    if ref_exists(root, f"refs/heads/{branch}"):
        if not resume:
            raise WorkflowError("RELEASE_VERSION_RESERVED", f"branch already exists: {branch}; use --resume", exit_code=2)
        if not worktree.is_dir():
            git(root, "worktree", "add", str(worktree), branch)
    else:
        if worktree.exists():
            raise WorkflowError("RELEASE_WORKTREE_COLLISION", f"worktree path already exists: {worktree}", exit_code=2)
        git(root, "worktree", "add", "-b", branch, str(worktree), plan["sourceCommit"])
    if git(worktree, "status", "--porcelain"):
        raise WorkflowError("RELEASE_WORKTREE_DIRTY", f"release worktree is dirty: {worktree}")
    observed = current_version(worktree, version_config)
    if observed != version:
        changed = write_version(worktree, version_config, version)
        relative = changed.relative_to(worktree)
        git(worktree, "add", "--", str(relative))
        git(worktree, "commit", "-m", f"chore(release): v{version}")
    candidate = full_commit(worktree, "HEAD")
    prepared_commit = (
        existing_state.get("preparedCommit")
        if existing_state and COMMIT.fullmatch(str(existing_state.get("preparedCommit", "")))
        else candidate
    )
    state = {
        "schema": "project-governance.release-state.v1",
        **plan,
        "preparedCommit": prepared_commit,
        "candidateCommit": candidate,
        "status": "prepared",
        "phase": "version_reserved",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(state_path(root, version), state)
    emit(event, **state)
    return 0


def prepare(root: Path, *, version: str, target: str, base_tag: str | None, dry_run: bool, resume: bool) -> int:
    plan = plan_prepare(root, version=version, target=target, base_tag=base_tag)
    if dry_run:
        emit("repair_prepare_planned" if base_tag else "release_prepare_planned", **plan)
        return 0
    with release_lock(root):
        plan = plan_prepare(root, version=version, target=target, base_tag=base_tag)
        config = load_config(root)
        return apply_prepared_plan(
            root,
            plan=plan,
            resume=resume,
            version_config=config["version"],
            event="repair_prepared" if base_tag else "release_prepared",
        )


def hotfix_prepare(
    root: Path,
    *,
    version: str,
    target: str,
    base_tag: str,
    base_commit: str,
    evidence_digest: str,
    dry_run: bool,
    resume: bool,
) -> int:
    resume_controller = None
    if resume and state_path(root, version).is_file():
        retained = read_json(state_path(root, version), "RELEASE_STATE_INVALID")
        if retained.get("lineage") == "hotfix" and COMMIT.fullmatch(str(retained.get("controllerCommit", ""))):
            resume_controller = retained["controllerCommit"]
    plan = plan_hotfix_prepare(
        root,
        version=version,
        target=target,
        base_tag=base_tag,
        base_commit=base_commit,
        evidence_digest=evidence_digest,
        controller_commit=resume_controller,
    )
    if dry_run:
        emit("hotfix_prepare_planned", **plan)
        return 0
    with release_lock(root):
        plan = plan_hotfix_prepare(
            root,
            version=version,
            target=target,
            base_tag=base_tag,
            base_commit=base_commit,
            evidence_digest=evidence_digest,
            controller_commit=plan["controllerCommit"],
        )
        with materialized_ref(root, plan["controllerCommit"]) as controller:
            config = load_config(controller, require_hotfix=True, target=target)
            return apply_prepared_plan(
                root,
                plan=plan,
                resume=resume,
                version_config=config["version"],
                event="hotfix_prepared",
            )
    return 0


def parse_artifact_output(output: str, *, tag: str, commit: str, target: str) -> dict[str, Any]:
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        raise WorkflowError("ARTIFACT_FREEZE_EVIDENCE_MISSING", "artifact freeze hook returned no evidence")
    try:
        value = require_mapping(json.loads(lines[-1]), "artifact freeze output")
    except json.JSONDecodeError as exc:
        raise WorkflowError("ARTIFACT_FREEZE_EVIDENCE_INVALID", "artifact freeze hook must end with one JSON object") from exc
    if value.get("schema") != ARTIFACT_SCHEMA:
        raise WorkflowError("ARTIFACT_FREEZE_EVIDENCE_INVALID", f"artifact schema must be {ARTIFACT_SCHEMA}")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise WorkflowError("ARTIFACT_FREEZE_EVIDENCE_INVALID", "artifacts must be a non-empty list")
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(artifacts):
        entry = require_mapping(item, f"artifacts[{index}]")
        normalized.append({"name": require_string(entry.get("name"), f"artifacts[{index}].name"), "digest": require_string(entry.get("digest"), f"artifacts[{index}].digest")})
    return {"schema": ARTIFACT_SCHEMA, "tag": tag, "commit": commit, "target": target, "artifacts": normalized, "frozenAt": datetime.now(timezone.utc).isoformat()}


def load_target_artifact(root: Path, *, tag: str, commit: str, target: str, required: bool) -> tuple[Path, dict[str, Any]] | None:
    selected = artifact_path(root, tag, target)
    if not selected.is_file():
        legacy = legacy_artifact_path(root, tag)
        if legacy.is_file():
            selected = legacy
        elif not required:
            return None
    artifact = read_json(selected, "ARTIFACT_FREEZE_EVIDENCE_MISSING")
    if selected == legacy_artifact_path(root, tag) and artifact.get("target") != target and not required:
        if artifact.get("schema") == ARTIFACT_SCHEMA and artifact.get("tag") == tag and artifact.get("commit") == commit:
            return None
    if artifact.get("schema") != ARTIFACT_SCHEMA or artifact.get("tag") != tag or artifact.get("commit") != commit or artifact.get("target") != target:
        raise WorkflowError("RELEASE_IDENTITY_MISMATCH", "frozen artifact identity does not match tag/commit/target", exit_code=2)
    artifacts = artifact.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise WorkflowError("ARTIFACT_FREEZE_EVIDENCE_INVALID", "frozen artifact manifest has no artifacts", exit_code=2)
    for index, entry in enumerate(artifacts):
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"] or not isinstance(entry.get("digest"), str) or not entry["digest"]:
            raise WorkflowError("ARTIFACT_FREEZE_EVIDENCE_INVALID", f"invalid frozen artifact entry at index {index}", exit_code=2)
    return selected, artifact


def annotated_tag_commit(root: Path, tag: str) -> str | None:
    if not ref_exists(root, f"refs/tags/{tag}"):
        return None
    if git(root, "cat-file", "-t", f"refs/tags/{tag}") != "tag":
        raise WorkflowError("RELEASE_TAG_NOT_ANNOTATED", f"release tag is not annotated: {tag}")
    return full_commit(root, tag)


def execute_deployment(
    root: Path,
    *,
    config: dict[str, Any],
    state: dict[str, Any],
    worktree: Path,
    artifact: dict[str, Any],
    artifact_file: Path,
    migration: bool,
    hook_cwd: Path | None = None,
    hotfix: dict[str, Any] | None = None,
) -> None:
    version = state["version"]
    tag = state["tag"]
    target = state["target"]
    values = {"version": version, "tag": tag, "target": target, "worktree": str(worktree), "artifact_manifest": str(artifact_file)}
    env = hook_env(
        root,
        version=version,
        tag=tag,
        target=target,
        worktree=worktree,
        artifact=artifact_file,
        hotfix=hotfix,
    )
    execution_cwd = hook_cwd or worktree
    assert_transaction_compatible(root, state)
    transaction = {
        "schema": "project-governance.deployment-transaction.v1",
        "target": target,
        "tag": tag,
        "commit": state["candidateCommit"],
        "artifactManifest": str(artifact_file),
        "status": "running",
        "phase": "artifact_frozen",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(transaction_path(root, target), transaction)
    migration_config = config.get("migration")
    if migration:
        if not migration_config:
            raise WorkflowError("MIGRATION_WORKFLOW_NOT_CONFIGURED", "--migration requires migration hooks", exit_code=2)
        run_hook(migration_config["preflight"], cwd=execution_cwd, values=values, env=env, code="MIGRATION_PREFLIGHT_FAILED")
        transaction["phase"] = "migration_started"
        atomic_json(transaction_path(root, target), transaction)
        run_hook(migration_config["apply"], cwd=execution_cwd, values=values, env=env, code="MIGRATION_FAILED")
        run_hook(migration_config["verify"], cwd=execution_cwd, values=values, env=env, code="MIGRATION_VERIFICATION_FAILED")
        transaction["phase"] = "migration_completed"
        atomic_json(transaction_path(root, target), transaction)
    transaction["phase"] = "deployment_started"
    atomic_json(transaction_path(root, target), transaction)
    target_config = config["targets"][target]
    run_hook(target_config["deploy"], cwd=execution_cwd, values=values, env=env, code="DEPLOYMENT_FAILED")
    transaction["phase"] = "deployed"
    atomic_json(transaction_path(root, target), transaction)
    run_hook(target_config["verify"], cwd=execution_cwd, values=values, env=env, code="DEPLOYMENT_VERIFICATION_FAILED")
    transaction.update({"phase": "completed", "status": "succeeded", "updatedAt": datetime.now(timezone.utc).isoformat()})
    atomic_json(transaction_path(root, target), transaction)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    deploy_tag = f"deploy/{target}/{timestamp}/{tag}"
    manifest_digest = f"sha256:{hashlib.sha256(artifact_file.read_bytes()).hexdigest()}"
    transaction_file = transaction_path(root, target)
    transaction_digest = f"sha256:{hashlib.sha256(transaction_file.read_bytes()).hexdigest()}"
    annotation = json.dumps(
        {
            "schema": "project-governance.deployment-tag.v1",
            "releaseTag": tag,
            "releaseCommit": state["candidateCommit"],
            "target": target,
            "artifactManifestDigest": manifest_digest,
            "artifacts": artifact["artifacts"],
            "deploymentTransactionDigest": transaction_digest,
        },
        sort_keys=True,
    )
    git(root, "tag", "-a", deploy_tag, state["candidateCommit"], "-m", annotation)
    emit("deployment_verified", tag=tag, commit=state["candidateCommit"], target=target, deploymentTag=deploy_tag, artifactManifestDigest=manifest_digest, transaction=str(transaction_path(root, target)))


def run_release(root: Path, *, version: str, target: str, migration: bool, repair_base: str | None = None) -> int:
    config = load_config(root, require_complete=True, target=target)
    state = read_json(state_path(root, version), "RELEASE_NOT_PREPARED")
    expected_lineage = "repair" if repair_base else "release"
    if state.get("lineage") != expected_lineage or state.get("target") != target:
        raise WorkflowError("RELEASE_IDENTITY_MISMATCH", "prepared release identity does not match this operation", exit_code=2)
    if repair_base and state.get("baseTag") != repair_base:
        raise WorkflowError("RELEASE_IDENTITY_MISMATCH", "repair base does not match prepared lineage", exit_code=2)
    worktree = Path(state["worktree"])
    if not worktree.is_dir():
        raise WorkflowError("RELEASE_WORKTREE_MISSING", f"missing prepared worktree: {worktree}")
    with release_lock(root):
        if git(worktree, "branch", "--show-current") != state["branch"]:
            raise WorkflowError("RELEASE_IDENTITY_MISMATCH", "release worktree branch changed")
        if git(worktree, "status", "--porcelain"):
            raise WorkflowError("RELEASE_WORKTREE_DIRTY", "commit the authorized candidate repair before continuing")
        candidate = full_commit(worktree, "HEAD")
        if not is_ancestor(root, state["sourceCommit"], candidate):
            raise WorkflowError("RELEASE_LINEAGE_DIVERGED", "candidate is not a descendant of frozen source")
        state["candidateCommit"] = candidate
        tag = state["tag"]
        if annotated_tag_commit(root, tag) is not None:
            raise WorkflowError("RELEASE_ALREADY_TAGGED", f"use release retry for existing tag {tag}", exit_code=2)
        artifact_file = artifact_path(root, tag, target)
        values = {"version": version, "tag": tag, "target": target, "worktree": str(worktree), "artifact_manifest": str(artifact_file)}
        env = hook_env(root, version=version, tag=tag, target=target, worktree=worktree, artifact=artifact_file)
        for index, gate in enumerate(config["gates"]):
            emit("release_gate_started", index=index, executable=gate[0])
            run_hook(gate, cwd=worktree, values=values, env=env, code="RELEASE_GATE_FAILED")
        output = run_hook(config["artifact"]["freeze"], cwd=worktree, values=values, env=env, code="ARTIFACT_FREEZE_FAILED")
        artifact = parse_artifact_output(output, tag=tag, commit=candidate, target=target)
        if git(worktree, "status", "--porcelain"):
            raise WorkflowError("ARTIFACT_FREEZE_MUTATED_SOURCE", "artifact freeze changed tracked source")
        atomic_json_once(artifact_file, artifact)
        git(root, "tag", "-a", tag, candidate, "-m", f"Release {tag}")
        if annotated_tag_commit(root, tag) != candidate:
            raise WorkflowError("RELEASE_TAG_IDENTITY_MISMATCH", "annotated tag does not match frozen candidate")
        state.update({"status": "tagged", "phase": "artifact_frozen", "candidateCommit": candidate, "updatedAt": datetime.now(timezone.utc).isoformat()})
        atomic_json(state_path(root, version), state)
        try:
            execute_deployment(root, config=config, state=state, worktree=worktree, artifact=artifact, artifact_file=artifact_file, migration=migration)
        except WorkflowError:
            state.update({"status": "failed", "phase": "deployment_failed", "updatedAt": datetime.now(timezone.utc).isoformat()})
            atomic_json(state_path(root, version), state)
            raise
        state.update({"status": "succeeded", "phase": "completed", "updatedAt": datetime.now(timezone.utc).isoformat()})
        atomic_json(state_path(root, version), state)
        emit(
            "release_completed",
            tag=tag,
            commit=candidate,
            target=target,
            artifactManifest=str(artifact_file),
            releaseBoundary=release_boundary(),
        )
    return 0


def run_hotfix(
    root: Path,
    *,
    version: str,
    target: str,
    base_tag: str,
    base_commit: str,
    evidence_digest: str,
) -> int:
    state = read_json(state_path(root, version), "RELEASE_NOT_PREPARED")
    expected = {
        "lineage": "hotfix",
        "target": target,
        "baseTag": base_tag,
        "baseCommit": base_commit,
        "evidenceDigest": evidence_digest,
    }
    if any(state.get(name) != value for name, value in expected.items()):
        raise WorkflowError("RELEASE_IDENTITY_MISMATCH", "prepared hotfix identity does not match this operation", exit_code=2)
    worktree = Path(state["worktree"])
    if not worktree.is_dir():
        raise WorkflowError("RELEASE_WORKTREE_MISSING", f"missing prepared worktree: {worktree}")
    with release_lock(root):
        deployed = inspect_deployed_release(
            root,
            target=target,
            controller_commit=state["controllerCommit"],
        )
        if any(deployed[name] != state[name] for name in ("baseTag", "baseCommit", "evidenceDigest")):
            raise WorkflowError(
                "HOTFIX_BASE_CHANGED",
                "current target deployment changed after hotfix preparation",
                exit_code=2,
            )
        tags = stable_tags(root)
        if tags and semver_tuple(version) <= tag_version(tags[0]):
            raise WorkflowError(
                "HOTFIX_VERSION_SUPERSEDED",
                f"hotfix version {version} is not greater than highest stable tag {tags[0]}",
                exit_code=2,
            )
        if git(worktree, "branch", "--show-current") != state["branch"]:
            raise WorkflowError("RELEASE_IDENTITY_MISMATCH", "hotfix worktree branch changed")
        if git(worktree, "status", "--porcelain"):
            raise WorkflowError("RELEASE_WORKTREE_DIRTY", "commit the authorized hotfix before continuing")
        candidate = full_commit(worktree, "HEAD")
        if candidate == state.get("preparedCommit"):
            raise WorkflowError("HOTFIX_REPAIR_COMMIT_MISSING", "hotfix requires a committed repair after preparation", exit_code=2)
        if not is_ancestor(root, state["sourceCommit"], candidate):
            raise WorkflowError("RELEASE_LINEAGE_DIVERGED", "hotfix candidate is not a descendant of deployed source")
        if git(root, "rev-list", "--merges", f"{state['sourceCommit']}..{candidate}"):
            raise WorkflowError("HOTFIX_MERGE_COMMIT_FORBIDDEN", "hotfix lineage must not contain merge commits", exit_code=2)
        tag = state["tag"]
        if annotated_tag_commit(root, tag) is not None:
            raise WorkflowError("RELEASE_ALREADY_TAGGED", f"use release retry for existing tag {tag}", exit_code=2)
        artifact_file = artifact_path(root, tag, target)
        values = {
            "version": version,
            "tag": tag,
            "target": target,
            "worktree": str(worktree),
            "artifact_manifest": str(artifact_file),
        }
        with materialized_ref(root, state["controllerCommit"]) as controller:
            config = load_config(controller, require_complete=True, require_hotfix=True, target=target)
            env = hook_env(
                root,
                version=version,
                tag=tag,
                target=target,
                worktree=worktree,
                artifact=artifact_file,
                hotfix=state,
            )
            run_hook(
                config["hotfix"]["scope"],
                cwd=controller,
                values=values,
                env=env,
                code="HOTFIX_SCOPE_REJECTED",
            )
            for index, gate in enumerate(config["hotfix"]["gates"]):
                emit("hotfix_gate_started", index=index, executable=gate[0])
                run_hook(gate, cwd=controller, values=values, env=env, code="HOTFIX_GATE_FAILED")
            output = run_hook(
                config["hotfix"]["freeze"],
                cwd=controller,
                values=values,
                env=env,
                code="HOTFIX_ARTIFACT_FREEZE_FAILED",
            )
            artifact = parse_artifact_output(output, tag=tag, commit=candidate, target=target)
            if git(worktree, "status", "--porcelain"):
                raise WorkflowError("ARTIFACT_FREEZE_MUTATED_SOURCE", "hotfix hooks changed candidate source")
            deployed_before_tag = inspect_deployed_release(
                root,
                target=target,
                controller_commit=state["controllerCommit"],
            )
            if any(
                deployed_before_tag[name] != state[name]
                for name in ("baseTag", "baseCommit", "evidenceDigest")
            ):
                raise WorkflowError(
                    "HOTFIX_BASE_CHANGED",
                    "current target deployment changed while hotfix gates were running",
                    exit_code=2,
                )
            atomic_json_once(artifact_file, artifact)
            git(root, "tag", "-a", tag, candidate, "-m", f"Release {tag}")
            if annotated_tag_commit(root, tag) != candidate:
                raise WorkflowError("RELEASE_TAG_IDENTITY_MISMATCH", "annotated tag does not match frozen hotfix")
            state.update(
                {
                    "status": "tagged",
                    "phase": "artifact_frozen",
                    "candidateCommit": candidate,
                    "updatedAt": datetime.now(timezone.utc).isoformat(),
                }
            )
            atomic_json(state_path(root, version), state)
            try:
                execute_deployment(
                    root,
                    config=config,
                    state=state,
                    worktree=worktree,
                    artifact=artifact,
                    artifact_file=artifact_file,
                    migration=False,
                    hook_cwd=controller,
                    hotfix=state,
                )
            except WorkflowError:
                state.update(
                    {
                        "status": "failed",
                        "phase": "deployment_failed",
                        "updatedAt": datetime.now(timezone.utc).isoformat(),
                    }
                )
                atomic_json(state_path(root, version), state)
                raise
        state.update({"status": "succeeded", "phase": "completed", "updatedAt": datetime.now(timezone.utc).isoformat()})
        atomic_json(state_path(root, version), state)
        emit(
            "hotfix_completed",
            tag=tag,
            commit=candidate,
            target=target,
            baseTag=base_tag,
            baseCommit=base_commit,
            artifactManifest=str(artifact_file),
            supersededReservations=state.get("supersededReservations", []),
            releaseBoundary=release_boundary(),
        )
    return 0


def retry(root: Path, *, tag: str, target: str) -> int:
    if not TAG.fullmatch(tag):
        raise WorkflowError("INVALID_RELEASE_TAG", f"invalid stable tag: {tag}", exit_code=2)
    commit = annotated_tag_commit(root, tag)
    if commit is None:
        raise WorkflowError("RELEASE_TAG_MISSING", f"release tag does not exist: {tag}", exit_code=2)
    selected = load_target_artifact(root, tag=tag, commit=commit, target=target, required=True)
    assert selected is not None
    artifact_file, artifact = selected
    version = tag[1:]
    retained_state: dict[str, Any] | None = None
    retained_path = state_path(root, version)
    if retained_path.is_file():
        candidate_state = read_json(retained_path, "RELEASE_STATE_INVALID")
        if candidate_state.get("lineage") == "hotfix":
            if (
                candidate_state.get("tag") != tag
                or candidate_state.get("target") != target
                or candidate_state.get("candidateCommit") != commit
                or not COMMIT.fullmatch(str(candidate_state.get("controllerCommit", "")))
            ):
                raise WorkflowError(
                    "RELEASE_IDENTITY_MISMATCH",
                    "retained hotfix state does not match the fixed-tag retry",
                    exit_code=2,
                )
            retained_state = candidate_state
    attempt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    worktree = worktree_root(root) / f"retry-{tag}-{target}-{attempt}"
    with release_lock(root):
        git(root, "worktree", "add", "--detach", str(worktree), tag)
        try:
            if full_commit(worktree, "HEAD") != commit or git(worktree, "status", "--porcelain"):
                raise WorkflowError("RELEASE_IDENTITY_MISMATCH", "retry worktree identity check failed")
            if retained_state is not None:
                with materialized_ref(root, retained_state["controllerCommit"]) as controller:
                    config = load_config(controller, require_complete=True, require_hotfix=True, target=target)
                    retry_state = {**retained_state, "candidateCommit": commit}
                    execute_deployment(
                        root,
                        config=config,
                        state=retry_state,
                        worktree=worktree,
                        artifact=artifact,
                        artifact_file=artifact_file,
                        migration=False,
                        hook_cwd=controller,
                        hotfix=retained_state,
                    )
                    emit(
                        "release_retry_completed",
                        tag=tag,
                        commit=commit,
                        target=target,
                        artifactManifest=str(artifact_file),
                        controllerCommit=retained_state["controllerCommit"],
                        releaseBoundary=release_boundary(),
                    )
                return 0
            config = load_config(worktree, require_complete=True, target=target)
            for index, gate in enumerate(config["gates"]):
                values = {"version": version, "tag": tag, "target": target, "worktree": str(worktree), "artifact_manifest": str(artifact_file)}
                env = hook_env(root, version=version, tag=tag, target=target, worktree=worktree, artifact=artifact_file)
                emit("retry_gate_started", index=index, executable=gate[0])
                run_hook(gate, cwd=worktree, values=values, env=env, code="RETRY_GATE_FAILED")
            state = {"version": version, "tag": tag, "target": target, "candidateCommit": commit}
            execute_deployment(root, config=config, state=state, worktree=worktree, artifact=artifact, artifact_file=artifact_file, migration=False)
            emit(
                "release_retry_completed",
                tag=tag,
                commit=commit,
                target=target,
                artifactManifest=str(artifact_file),
                releaseBoundary=release_boundary(),
            )
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=root, check=False, capture_output=True)
    return 0


def plan_promotion(root: Path, *, tag: str, target: str) -> int:
    if not TAG.fullmatch(tag):
        raise WorkflowError("INVALID_RELEASE_TAG", f"invalid stable tag: {tag}", exit_code=2)
    commit = annotated_tag_commit(root, tag)
    if commit is None:
        raise WorkflowError("RELEASE_TAG_MISSING", f"release tag does not exist: {tag}", exit_code=2)
    load_config_from_ref(root, tag, require_complete=True, target=target)
    selected = load_target_artifact(root, tag=tag, commit=commit, target=target, required=False)
    emit(
        "release_promotion_planned",
        tag=tag,
        commit=commit,
        target=target,
        artifactAction="reuse" if selected else "freeze_first_for_target",
        artifactManifest=str(selected[0]) if selected else str(artifact_path(root, tag, target)),
    )
    return 0


def promote(root: Path, *, tag: str, target: str, migration: bool) -> int:
    if not TAG.fullmatch(tag):
        raise WorkflowError("INVALID_RELEASE_TAG", f"invalid stable tag: {tag}", exit_code=2)
    commit = annotated_tag_commit(root, tag)
    if commit is None:
        raise WorkflowError("RELEASE_TAG_MISSING", f"release tag does not exist: {tag}", exit_code=2)
    version = tag[1:]
    attempt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    worktree = worktree_root(root) / f"promote-{tag}-{target}-{attempt}"
    with release_lock(root):
        git(root, "worktree", "add", "--detach", str(worktree), tag)
        try:
            if full_commit(worktree, "HEAD") != commit or git(worktree, "status", "--porcelain"):
                raise WorkflowError("RELEASE_IDENTITY_MISMATCH", "promotion worktree identity check failed")
            config = load_config(worktree, require_complete=True, target=target)
            selected = load_target_artifact(root, tag=tag, commit=commit, target=target, required=False)
            if selected is None:
                artifact_file = artifact_path(root, tag, target)
            else:
                artifact_file, artifact = selected
            values = {"version": version, "tag": tag, "target": target, "worktree": str(worktree), "artifact_manifest": str(artifact_file)}
            env = hook_env(root, version=version, tag=tag, target=target, worktree=worktree, artifact=artifact_file)
            for index, gate in enumerate(config["gates"]):
                emit("promotion_gate_started", index=index, executable=gate[0])
                run_hook(gate, cwd=worktree, values=values, env=env, code="PROMOTION_GATE_FAILED")
            if selected is None:
                output = run_hook(config["artifact"]["freeze"], cwd=worktree, values=values, env=env, code="ARTIFACT_FREEZE_FAILED")
                artifact = parse_artifact_output(output, tag=tag, commit=commit, target=target)
                if git(worktree, "status", "--porcelain"):
                    raise WorkflowError("ARTIFACT_FREEZE_MUTATED_SOURCE", "artifact freeze changed tracked source")
                atomic_json_once(artifact_file, artifact)
                emit("promotion_artifact_frozen", tag=tag, commit=commit, target=target, artifactManifest=str(artifact_file))
            state = {"version": version, "tag": tag, "target": target, "candidateCommit": commit}
            execute_deployment(root, config=config, state=state, worktree=worktree, artifact=artifact, artifact_file=artifact_file, migration=migration)
            emit("release_promoted", tag=tag, commit=commit, target=target, artifactManifest=str(artifact_file), releaseBoundary=release_boundary())
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=root, check=False, capture_output=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation",
        choices=(
            "inspect",
            "sync-main-plan",
            "sync-main",
            "plan",
            "bootstrap-plan",
            "bootstrap",
            "prepare-plan",
            "prepare",
            "repair-prepare-plan",
            "repair-prepare",
            "hotfix-inspect",
            "hotfix-prepare-plan",
            "hotfix-prepare",
            "hotfix-plan",
            "hotfix-run",
            "run",
            "repair",
            "promote-plan",
            "promote",
            "retry",
        ),
    )
    parser.add_argument("--target")
    parser.add_argument("--version")
    parser.add_argument("--base-tag")
    parser.add_argument("--base-commit")
    parser.add_argument("--evidence-digest")
    parser.add_argument("--tag")
    parser.add_argument("--preset", default="auto", choices=("auto", "node-pnpm", "python-uv", "flutter-fvm"))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--migration", action="store_true")
    args = parser.parse_args(argv)
    root = repo_root(Path.cwd())
    try:
        if args.operation == "inspect":
            return release_inspect(root, args.target)
        if args.operation == "sync-main-plan":
            return sync_main(root, dry_run=True)
        if args.operation == "sync-main":
            return sync_main(root, dry_run=False)
        if args.operation == "bootstrap-plan":
            return bootstrap_plan(root, args.preset)
        if args.operation == "bootstrap":
            return bootstrap(root, args.preset)
        if args.operation == "plan":
            if not args.target:
                raise WorkflowError("TARGET_REQUIRED", "plan requires --target", exit_code=2)
            release_inspect(root, args.target)
            load_config(root, require_complete=True, target=args.target)
            return 0
        if args.operation == "hotfix-inspect":
            if not args.target:
                raise WorkflowError("TARGET_REQUIRED", "hotfix-inspect requires --target", exit_code=2)
            deployed = inspect_deployed_release(root, target=args.target)
            emit("hotfix_deployed_base_inspected", status="ready", **deployed)
            return 0
        if args.operation in {"prepare-plan", "prepare"}:
            if not args.version or not args.target:
                raise WorkflowError("RELEASE_IDENTITY_REQUIRED", f"{args.operation} requires --version and --target", exit_code=2)
            return prepare(root, version=args.version, target=args.target, base_tag=None, dry_run=args.operation.endswith("plan"), resume=args.resume)
        if args.operation in {"repair-prepare-plan", "repair-prepare"}:
            if not args.version or not args.target or not args.base_tag:
                raise WorkflowError("REPAIR_IDENTITY_REQUIRED", f"{args.operation} requires --base-tag, --version, and --target", exit_code=2)
            return prepare(root, version=args.version, target=args.target, base_tag=args.base_tag, dry_run=args.operation.endswith("plan"), resume=args.resume)
        if args.operation in {"hotfix-prepare-plan", "hotfix-prepare", "hotfix-plan"}:
            if not all((args.version, args.target, args.base_tag, args.base_commit, args.evidence_digest)):
                raise WorkflowError(
                    "HOTFIX_IDENTITY_REQUIRED",
                    f"{args.operation} requires --base-tag, --base-commit, --evidence-digest, --version, and --target",
                    exit_code=2,
                )
            if args.operation == "hotfix-plan":
                plan = plan_hotfix_prepare(
                    root,
                    version=args.version,
                    target=args.target,
                    base_tag=args.base_tag,
                    base_commit=args.base_commit,
                    evidence_digest=args.evidence_digest,
                )
                emit("hotfix_planned", **plan)
                return 0
            return hotfix_prepare(
                root,
                version=args.version,
                target=args.target,
                base_tag=args.base_tag,
                base_commit=args.base_commit,
                evidence_digest=args.evidence_digest,
                dry_run=args.operation == "hotfix-prepare-plan",
                resume=args.resume,
            )
        if args.operation == "hotfix-run":
            if not all((args.version, args.target, args.base_tag, args.base_commit, args.evidence_digest)):
                raise WorkflowError(
                    "HOTFIX_IDENTITY_REQUIRED",
                    "hotfix-run requires --base-tag, --base-commit, --evidence-digest, --version, and --target",
                    exit_code=2,
                )
            return run_hotfix(
                root,
                version=args.version,
                target=args.target,
                base_tag=args.base_tag,
                base_commit=args.base_commit,
                evidence_digest=args.evidence_digest,
            )
        if args.operation in {"run", "repair"}:
            if not args.version or not args.target:
                raise WorkflowError("RELEASE_IDENTITY_REQUIRED", f"{args.operation} requires --version and --target", exit_code=2)
            if args.operation == "repair" and not args.base_tag:
                raise WorkflowError("REPAIR_IDENTITY_REQUIRED", "repair requires --base-tag", exit_code=2)
            return run_release(root, version=args.version, target=args.target, migration=args.migration, repair_base=args.base_tag if args.operation == "repair" else None)
        if not args.tag or not args.target:
            raise WorkflowError("RELEASE_IDENTITY_REQUIRED", f"{args.operation} requires --tag and --target", exit_code=2)
        if args.operation == "promote-plan":
            return plan_promotion(root, tag=args.tag, target=args.target)
        if args.operation == "promote":
            return promote(root, tag=args.tag, target=args.target, migration=args.migration)
        return retry(root, tag=args.tag, target=args.target)
    except WorkflowError as exc:
        if args.operation in {"sync-main-plan", "sync-main"}:
            emit(
                "main_sync_failed",
                scope="integration_branch",
                status="blocked" if exc.exit_code == 2 else "failed",
                releaseStatus="unchanged",
                code=exc.code,
                message=str(exc),
            )
        else:
            emit(
                "release_failed",
                scope="release",
                status="failed",
                code=exc.code,
                message=str(exc),
            )
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
