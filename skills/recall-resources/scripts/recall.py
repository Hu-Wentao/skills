#!/usr/bin/env -S uv run --script
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

SOURCE_ID = "github.com/hu-wentao/resource-memory"


def _is_source_root(path: Path) -> bool:
    return (
        (path / "pyproject.toml").is_file()
        and (path / "src" / "resource_memory" / "cli.py").is_file()
    )


def _configured_source() -> Path | None:
    configured = os.environ.get("RESOURCE_MEMORY_SOURCE")
    if not configured:
        return None
    candidate = Path(configured).expanduser().resolve()
    if not _is_source_root(candidate):
        raise SystemExit(
            f"RESOURCE_MEMORY_SOURCE is not a resource-memory checkout: {candidate}"
        )
    return candidate


def _source_from_skill_checkout() -> Path | None:
    script = Path(__file__).resolve()
    for candidate in script.parents:
        if _is_source_root(candidate):
            return candidate
    return None


def _source_from_registry() -> Path | None:
    registry = Path.home() / ".codex" / "skill-source-repositories.json"
    if not registry.is_file():
        return None
    try:
        payload = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for entry in payload.get("repositories", []):
        if not isinstance(entry, dict):
            continue
        identities = [entry.get("source"), *(entry.get("aliases") or [])]
        if SOURCE_ID not in {
            str(identity).lower().removeprefix("https://").removeprefix("http://")
            for identity in identities
            if identity
        }:
            continue
        candidate = Path(str(entry.get("path", ""))).expanduser().resolve()
        if _is_source_root(candidate):
            return candidate
    return None


def resolve_source_root() -> Path:
    source = (
        _configured_source()
        or _source_from_skill_checkout()
        or _source_from_registry()
    )
    if source is None:
        raise SystemExit(
            "resource-memory source checkout was not found; set RESOURCE_MEMORY_SOURCE"
        )
    return source


def main() -> None:
    project_root = resolve_source_root()
    data_root = Path(
        os.environ.get("RESOURCE_MEMORY_HOME", str(project_root))
    ).expanduser().resolve()
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv is required to run resource-memory")
    arguments = [uv, "run", "--project", str(project_root), "resource-memory"]
    if "--root" not in sys.argv[1:]:
        arguments.extend(["--root", str(data_root)])
    arguments.extend(sys.argv[1:])
    os.execv(
        uv,
        arguments,
    )


if __name__ == "__main__":
    main()
