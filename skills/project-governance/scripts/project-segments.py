#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "PyYAML>=6,<7",
# ]
# ///
"""Manage the machine-local PPISS project-segment registry."""

from __future__ import annotations

import argparse
import fcntl
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import yaml


SCHEMA = "project-governance.project-segments.v1"
MIN_SEGMENT = 10
MAX_SEGMENT = 64


class RegistryError(ValueError):
    """Raised when the project-segment registry is invalid or inconsistent."""


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    raise RegistryError("no Git repository found from the selected working directory")


def default_registry_path() -> Path:
    return (
        Path.home()
        / ".agents"
        / "skills-config"
        / "project-governance"
        / "project-segments.yaml"
    )


def normalize_segment(value: Any, field: str = "project segment") -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        segment = f"{value:02d}"
    elif isinstance(value, str) and re.fullmatch(r"[0-9]{2}", value):
        segment = value
    else:
        raise RegistryError(f"{field} must be exactly two digits")
    if not MIN_SEGMENT <= int(segment) <= MAX_SEGMENT:
        raise RegistryError(f"{field} must be between 10 and 64")
    return segment


def load_registry(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RegistryError(f"failed to read registry {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RegistryError("registry must contain a mapping")
    unknown = sorted(set(raw) - {"schema", "allocations"})
    if unknown:
        raise RegistryError(
            f"registry contains unsupported key(s): {', '.join(unknown)}"
        )
    if raw.get("schema") != SCHEMA:
        raise RegistryError(f"registry schema must be {SCHEMA}")
    allocations = raw.get("allocations")
    if not isinstance(allocations, dict):
        raise RegistryError("registry allocations must be a mapping")

    normalized: dict[str, str] = {}
    owners: dict[str, str] = {}
    for raw_root, raw_segment in allocations.items():
        if not isinstance(raw_root, str) or not Path(raw_root).is_absolute():
            raise RegistryError("registry project roots must be absolute paths")
        root = str(Path(raw_root).resolve())
        if root != raw_root:
            raise RegistryError(f"registry project root is not normalized: {raw_root}")
        segment = normalize_segment(
            raw_segment, f"registry allocation for {raw_root}"
        )
        if segment in owners:
            raise RegistryError(
                f"project segment {segment} is assigned to both "
                f"{owners[segment]} and {raw_root}"
            )
        normalized[root] = segment
        owners[segment] = root
    return normalized


def write_registry(path: Path, allocations: dict[str, str]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    document = {
        "schema": SCHEMA,
        "allocations": dict(sorted(allocations.items())),
    }
    text = yaml.safe_dump(
        document,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


@contextmanager
def locked_registry(path: Path) -> Iterator[dict[str, str]]:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield load_registry(path)


def owner_for(allocations: dict[str, str], segment: str) -> str | None:
    return next(
        (root for root, assigned in allocations.items() if assigned == segment),
        None,
    )


def allocate(path: Path, project_root: str) -> tuple[str, str]:
    with locked_registry(path) as allocations:
        existing = allocations.get(project_root)
        if existing is not None:
            return "existing", existing
        used = set(allocations.values())
        segment = next(
            (
                f"{number:02d}"
                for number in range(MIN_SEGMENT, MAX_SEGMENT + 1)
                if f"{number:02d}" not in used
            ),
            None,
        )
        if segment is None:
            raise RegistryError("all project segments from 10 through 64 are allocated")
        allocations[project_root] = segment
        write_registry(path, allocations)
        return "allocated", segment


def claim(path: Path, project_root: str, segment: str) -> str:
    with locked_registry(path) as allocations:
        existing = allocations.get(project_root)
        if existing is not None:
            if existing != segment:
                raise RegistryError(
                    f"{project_root} already owns project segment {existing}, "
                    f"not {segment}"
                )
            return "existing"
        owner = owner_for(allocations, segment)
        if owner is not None:
            raise RegistryError(f"project segment {segment} is already owned by {owner}")
        allocations[project_root] = segment
        write_registry(path, allocations)
        return "claimed"


def check(path: Path, project_root: str, segment: str) -> None:
    allocations = load_registry(path)
    existing = allocations.get(project_root)
    if existing is None:
        owner = owner_for(allocations, segment)
        if owner is None:
            raise RegistryError(
                f"{project_root} is not registered; claim project segment {segment}"
            )
        raise RegistryError(f"project segment {segment} is owned by {owner}")
    if existing != segment:
        raise RegistryError(
            f"{project_root} owns project segment {existing}, not {segment}"
        )


def print_result(
    status: str, project_root: str, segment: str, registry_path: Path
) -> None:
    print(f"status: {status}")
    print(f"project_root: {project_root}")
    print(f"project_segment: {segment}")
    print(f"registry: {registry_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage machine-local PPISS project-segment allocations."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("allocate", "list"):
        command_parser = subparsers.add_parser(command)
        if command == "allocate":
            command_parser.add_argument("--cwd", type=Path, default=Path.cwd())
    for command in ("claim", "check"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--cwd", type=Path, default=Path.cwd())
        command_parser.add_argument("--segment", required=True)
    args = parser.parse_args()

    registry_path = default_registry_path()
    try:
        if args.command == "list":
            allocations = load_registry(registry_path)
            print(f"registry: {registry_path}")
            print("allocations:")
            for project_root, segment in sorted(
                allocations.items(), key=lambda item: (item[1], item[0])
            ):
                print(f"  {segment}: {project_root}")
            return 0

        project_root = str(find_repo_root(args.cwd))
        if args.command == "allocate":
            status, segment = allocate(registry_path, project_root)
        else:
            segment = normalize_segment(args.segment)
            if args.command == "claim":
                status = claim(registry_path, project_root, segment)
            else:
                check(registry_path, project_root, segment)
                status = "consistent"
        print_result(status, project_root, segment, registry_path)
        return 0
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
