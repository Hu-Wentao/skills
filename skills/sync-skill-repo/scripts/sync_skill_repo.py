#!/usr/bin/env python3
"""Register local skill repositories and sync project skill changes back."""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


SCHEMA = "sync-skill-repo.sources.v1"
EXCLUDED_DIRS = {
    ".git",
    ".ruff_cache",
    "__pycache__",
    "dist",
    "node_modules",
}
EXCLUDED_FILES = {".DS_Store", ".env"}


class SyncError(RuntimeError):
    """Raised for expected preflight and configuration failures."""


@dataclass(frozen=True)
class Target:
    repo: Path
    destination: Path
    destination_relative: Path
    source_id: str | None
    lock_path: Path | None


@dataclass(frozen=True)
class InstallationScope:
    name: str
    project_root: Path
    lock_path: Path
    expected_skill: Path
    context_project_root: Path | None


@dataclass(frozen=True)
class SourceContext:
    repo: Path
    skill_dir: Path
    skill_relative: Path
    branch: str
    upstream: str
    upstream_remote: str
    upstream_branch: str
    upstream_push_url: str


@dataclass(frozen=True)
class UpdateTarget:
    scope: str
    lock_path: Path
    installed_skill: Path


@dataclass(frozen=True)
class PublishReceipt:
    source: SourceContext
    update_root: Path | None
    update_targets: tuple[UpdateTarget, ...]
    push_enabled: bool
    reinstall_enabled: bool


def default_registry_path() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return codex_home.expanduser() / "skill-source-repositories.json"


def run_git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SyncError(f"git {' '.join(args)} failed in {repo}: {detail}")
    return result.stdout.strip()


def normalize_source(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise SyncError("Source identifier cannot be empty")

    if value.startswith("git@") and ":" in value:
        host, path = value[4:].split(":", 1)
        value = f"{host}/{path}"
    elif "://" in value:
        parsed = urlparse(value)
        if not parsed.hostname:
            raise SyncError(f"Invalid source URL: {raw}")
        value = f"{parsed.hostname}/{parsed.path.lstrip('/')}"
    elif value.count("/") == 1:
        value = f"github.com/{value}"

    value = value.rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    parts = value.split("/")
    if len(parts) < 3 or not all(parts[:3]):
        raise SyncError(f"Invalid source identifier: {raw}")
    return value.lower()


def empty_registry() -> dict[str, object]:
    return {"schema": SCHEMA, "repositories": []}


def load_registry(path: Path, *, allow_missing: bool = False) -> dict[str, object]:
    if not path.is_file():
        if allow_missing:
            return empty_registry()
        raise SyncError(
            f"Source registry not found: {path}. Register the source repository first."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"Cannot read source registry {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise SyncError(f"Registry must use schema {SCHEMA}: {path}")
    repositories = data.get("repositories")
    if not isinstance(repositories, list):
        raise SyncError(f"Registry repositories must be a list: {path}")
    for entry in repositories:
        if not isinstance(entry, dict):
            raise SyncError(f"Invalid repository entry in {path}")
        if set(entry) != {"source", "path", "aliases"}:
            raise SyncError(
                f"Repository entries require source, path, and aliases: {path}"
            )
        if not isinstance(entry["path"], str) or not isinstance(entry["aliases"], list):
            raise SyncError(f"Invalid repository path or aliases in {path}")
        normalize_source(str(entry["source"]))
        for alias in entry["aliases"]:
            if not isinstance(alias, str):
                raise SyncError(f"Repository aliases must be strings: {path}")
            normalize_source(alias)
    return data


def save_registry(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    temporary.replace(path)


def git_root(path: Path) -> Path:
    root = run_git(path, "rev-parse", "--show-toplevel")
    return Path(root).resolve()


def register_repository(
    repo_input: Path,
    registry_path: Path,
    source_override: str | None,
    aliases: list[str],
) -> dict[str, object]:
    repo = repo_input.expanduser().resolve()
    if not repo.is_dir() or git_root(repo) != repo:
        raise SyncError(f"Repository path must be a Git worktree root: {repo}")

    origin = run_git(repo, "remote", "get-url", "origin", check=False)
    if not source_override and not origin:
        raise SyncError("Repository has no origin; pass --source <id>")
    source = normalize_source(source_override or origin)
    normalized_aliases = {normalize_source(alias) for alias in aliases}
    normalized_aliases.discard(source)

    data = load_registry(registry_path, allow_missing=True)
    repositories = data["repositories"]
    assert isinstance(repositories, list)
    match: dict[str, object] | None = None
    for entry in repositories:
        assert isinstance(entry, dict)
        known = {normalize_source(str(entry["source"]))}
        known.update(normalize_source(str(alias)) for alias in entry["aliases"])
        if Path(str(entry["path"])).expanduser().resolve() == repo or source in known:
            if match is not None and match is not entry:
                raise SyncError(f"Registry contains conflicting entries for {source}")
            match = entry

    if match is not None:
        normalized_aliases.add(normalize_source(str(match["source"])))
        normalized_aliases.update(
            normalize_source(str(alias)) for alias in match["aliases"]
        )
        normalized_aliases.discard(source)
    replacement = {
        "source": source,
        "path": str(repo),
        "aliases": sorted(normalized_aliases),
    }
    if match is None:
        repositories.append(replacement)
    else:
        match.clear()
        match.update(replacement)
    repositories.sort(key=lambda item: str(item["source"]))
    save_registry(registry_path, data)
    return replacement


def resolve_registered_repo(registry: dict[str, object], source: str) -> Path:
    wanted = normalize_source(source)
    matches: list[Path] = []
    repositories = registry["repositories"]
    assert isinstance(repositories, list)
    for entry in repositories:
        assert isinstance(entry, dict)
        identifiers = {normalize_source(str(entry["source"]))}
        identifiers.update(normalize_source(str(alias)) for alias in entry["aliases"])
        if wanted in identifiers:
            matches.append(Path(str(entry["path"])).expanduser().resolve())
    if not matches:
        raise SyncError(f"No local source repository is registered for {source}")
    if len(set(matches)) != 1:
        raise SyncError(f"Multiple local source repositories match {source}")
    repo = matches[0]
    if not repo.is_dir() or git_root(repo) != repo:
        raise SyncError(f"Registered path is not a Git worktree root: {repo}")
    return repo


def read_skill_name(skill_dir: Path) -> str:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        raise SyncError(f"Missing {skill_file}")
    text = skill_file.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        raise SyncError(f"Invalid YAML frontmatter in {skill_file}")
    name_match = re.search(r"(?m)^name:\s*([^\s#]+)\s*$", match.group(1))
    if not name_match:
        raise SyncError(f"Missing frontmatter name in {skill_file}")
    name = name_match.group(1).strip("'\"")
    if name != skill_dir.name:
        raise SyncError(
            f"SKILL.md name '{name}' does not match folder '{skill_dir.name}'"
        )
    if not re.fullmatch(r"[a-z0-9-]+", name):
        raise SyncError(f"Invalid skill name: {name}")
    return name


def nearest_lock(skill_dir: Path, project_root: Path) -> Path | None:
    current = skill_dir.resolve()
    project_root = project_root.resolve()
    while True:
        candidate = current / "skills-lock.json"
        if candidate.is_file():
            return candidate
        if current == project_root:
            return None
        if project_root not in current.parents:
            return None
        current = current.parent


def contained_path(repo: Path, relative: Path) -> tuple[Path, Path]:
    if relative.is_absolute():
        raise SyncError(f"Destination must be relative to its repository: {relative}")
    destination = (repo / relative).resolve()
    try:
        normalized = destination.relative_to(repo)
    except ValueError as exc:
        raise SyncError(f"Destination escapes its repository: {relative}") from exc
    if not normalized.parts or normalized.parts[0] == ".git":
        raise SyncError(f"Invalid destination inside repository: {relative}")
    return destination, normalized


def resolve_target(
    skill_dir: Path,
    skill_name: str,
    registry_path: Path,
    repo_override: Path | None,
    destination_override: Path | None,
) -> Target:
    if repo_override is not None:
        repo = repo_override.expanduser().resolve()
        if not repo.is_dir() or git_root(repo) != repo:
            raise SyncError(
                f"Destination repository must be a Git worktree root: {repo}"
            )
        relative = destination_override or Path("skills") / skill_name
        destination, normalized = contained_path(repo, relative)
        return Target(repo, destination, normalized, None, None)

    if destination_override is not None:
        raise SyncError(
            "--destination requires --repo when no lock-derived repository is used"
        )

    logical_skill = _absolute_path(skill_dir)
    logical_project_root = _project_root_from_installed_path(
        logical_skill, skill_name
    )
    if logical_project_root is not None and skill_name in _cli_lock_skills(
        logical_project_root / "skills-lock.json", "project"
    ):
        project_root = logical_project_root
        lock_path = project_root / "skills-lock.json"
    else:
        project_root = git_root(skill_dir)
        lock_path = nearest_lock(skill_dir, project_root)
    if lock_path is None:
        raise SyncError(
            "No skills-lock.json found; pass --repo and optional --destination"
        )
    try:
        entry = _cli_lock_skills(lock_path, "project")[skill_name]
        source_id = str(entry["source"])
    except (KeyError, TypeError) as exc:
        raise SyncError(
            f"No usable lock entry for {skill_name}; pass --repo and optional --destination"
        ) from exc

    registry = load_registry(registry_path)
    repo = resolve_registered_repo(registry, source_id)
    skill_path = entry.get("skillPath")
    if skill_path is None:
        relative = Path("skills") / skill_name
    elif isinstance(skill_path, str) and Path(skill_path).name == "SKILL.md":
        relative = Path(skill_path).parent
    else:
        raise SyncError(f"Invalid skillPath for {skill_name} in {lock_path}")
    destination, normalized = contained_path(repo, relative)
    return Target(repo, destination, normalized, source_id, lock_path)


def _source_context_in_repo(
    repo: Path, skill_dir: Path, *, require_tracked: bool
) -> SourceContext:
    repository = repo.expanduser().resolve()
    skill = skill_dir.expanduser().resolve()
    try:
        relative = skill.relative_to(repository)
    except ValueError as exc:
        raise SyncError(f"Skill is outside its source repository: {skill}") from exc
    tracked = run_git(
        repository,
        "ls-files",
        "--error-unmatch",
        str(relative / "SKILL.md"),
        check=False,
    )
    if require_tracked and not tracked:
        raise SyncError(f"Skill is not tracked in its source repository: {skill}")
    origin = run_git(repository, "remote", "get-url", "origin", check=False)
    if not origin or not normalize_source(origin).startswith("github.com/"):
        raise SyncError(
            f"Skill source repository has no GitHub origin: {repository}"
        )
    branch = run_git(repository, "branch", "--show-current")
    if not branch:
        raise SyncError(
            f"Source repository is in detached HEAD state: {repository}"
        )
    upstream = run_git(
        repository,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
        check=False,
    )
    if not upstream:
        raise SyncError(f"Current branch '{branch}' has no configured upstream")
    upstream_remote = run_git(
        repository, "config", f"branch.{branch}.remote", check=False
    )
    merge_ref = run_git(
        repository, "config", f"branch.{branch}.merge", check=False
    )
    if (
        not upstream_remote
        or upstream_remote == "."
        or not merge_ref.startswith("refs/heads/")
    ):
        raise SyncError(
            f"Current branch '{branch}' has no pushable remote branch upstream"
        )
    upstream_push_url = run_git(
        repository,
        "remote",
        "get-url",
        "--push",
        upstream_remote,
        check=False,
    )
    if not upstream_push_url or not normalize_source(
        upstream_push_url
    ).startswith("github.com/"):
        raise SyncError(
            f"Configured upstream remote is not GitHub: {upstream_remote}"
        )
    upstream_branch = merge_ref.removeprefix("refs/heads/")
    expected_upstream = f"{upstream_remote}/{upstream_branch}"
    if upstream != expected_upstream:
        raise SyncError(
            f"Resolved upstream {upstream} does not match branch configuration "
            f"{expected_upstream}"
        )
    return SourceContext(
        repository,
        skill,
        relative,
        branch,
        upstream,
        upstream_remote,
        upstream_branch,
        upstream_push_url,
    )


def _source_context(skill_dir: Path) -> SourceContext:
    skill = skill_dir.expanduser().resolve()
    return _source_context_in_repo(
        git_root(skill), skill, require_tracked=True
    )


def _direct_source_context(skill_dir: Path) -> SourceContext | None:
    skill = skill_dir.expanduser().resolve()
    try:
        repo = git_root(skill)
        relative = skill.relative_to(repo)
    except (SyncError, ValueError):
        return None
    tracked = run_git(
        repo,
        "ls-files",
        "--error-unmatch",
        str(relative / "SKILL.md"),
        check=False,
    )
    origin = run_git(repo, "remote", "get-url", "origin", check=False)
    if (
        not tracked
        or not origin
        or not normalize_source(origin).startswith("github.com/")
    ):
        return None
    return _source_context_in_repo(repo, skill, require_tracked=True)


def _git_changed_paths(repo: Path) -> set[Path]:
    commands = (
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    )
    changed: set[Path] = set()
    for command in commands:
        output = run_git(repo, *command)
        changed.update(Path(line) for line in output.splitlines() if line)
    return changed


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _refresh_source_upstream(context: SourceContext) -> None:
    run_git(
        context.repo,
        "fetch",
        "--quiet",
        context.upstream_push_url,
        f"+refs/heads/{context.upstream_branch}:"
        f"refs/remotes/{context.upstream_remote}/{context.upstream_branch}",
    )


def _source_ahead(context: SourceContext) -> int:
    return int(
        run_git(
            context.repo,
            "rev-list",
            "--count",
            f"{context.upstream}..HEAD",
        )
    )


def _source_behind(context: SourceContext) -> int:
    return int(
        run_git(
            context.repo,
            "rev-list",
            "--count",
            f"HEAD..{context.upstream}",
        )
    )


def _check_source_repo(
    context: SourceContext,
    *,
    allow_dirty: bool,
    allow_unpushed: bool,
    allow_skill_changes: bool,
) -> None:
    unmerged = run_git(
        context.repo, "diff", "--name-only", "--diff-filter=U"
    )
    if unmerged:
        raise SyncError(
            "Source repository has unresolved merge conflicts; publishing must "
            f"not stage them:\n{unmerged}"
        )
    changed = _git_changed_paths(context.repo)
    outside = sorted(
        path for path in changed if not _inside(path, context.skill_relative)
    )
    if outside and not allow_dirty:
        rendered = "\n".join(str(path) for path in outside)
        raise SyncError(
            "Source repository has unrelated changes; choose 先提交 or 先忽略. "
            f"Use --allow-dirty only for 先忽略:\n{rendered}"
        )
    skill_changes = sorted(
        path for path in changed if _inside(path, context.skill_relative)
    )
    if skill_changes and not allow_skill_changes:
        rendered = "\n".join(str(path) for path in skill_changes)
        raise SyncError(
            "--no-push cannot reinstall unpublished source changes:\n"
            f"{rendered}"
        )
    behind = _source_behind(context)
    if behind:
        raise SyncError(
            f"Source branch is behind or diverged from {context.upstream} by "
            f"{behind} commit(s); reconcile it before publishing"
        )
    ahead = _source_ahead(context)
    if ahead and not allow_unpushed:
        raise SyncError(
            f"Source repository has {ahead} existing unpushed commit(s); "
            "review them and rerun with --allow-unpushed"
        )


def _commit_skill(context: SourceContext, message: str) -> str | None:
    run_git(context.repo, "add", "--", str(context.skill_relative))
    staged = run_git(
        context.repo,
        "diff",
        "--cached",
        "--name-only",
        "--",
        str(context.skill_relative),
    )
    if not staged:
        return None
    run_git(
        context.repo,
        "commit",
        "-m",
        message,
        "--",
        str(context.skill_relative),
    )
    return run_git(context.repo, "rev-parse", "HEAD")


def excluded(relative: Path) -> bool:
    return (
        any(part in EXCLUDED_DIRS for part in relative.parts)
        or relative.name in EXCLUDED_FILES
        or relative.suffix == ".pyc"
        or relative.name.startswith(".env.")
    )


def source_entries(skill_dir: Path) -> dict[Path, Path]:
    entries: dict[Path, Path] = {}
    for path in skill_dir.rglob("*"):
        relative = path.relative_to(skill_dir)
        if excluded(relative):
            continue
        if path.is_symlink():
            target = (path.parent / os.readlink(path)).resolve()
            try:
                target.relative_to(skill_dir)
            except ValueError as exc:
                raise SyncError(f"Symlink escapes source skill: {path}") from exc
        entries[relative] = path
    return entries


def same_entry(source: Path, destination: Path) -> bool:
    if source.is_symlink():
        return destination.is_symlink() and os.readlink(source) == os.readlink(
            destination
        )
    if source.is_dir():
        return destination.is_dir() and not destination.is_symlink()
    if not destination.is_file() or destination.is_symlink():
        return False
    same_content = filecmp.cmp(source, destination, shallow=False)
    same_mode = (source.stat().st_mode & 0o111) == (destination.stat().st_mode & 0o111)
    return same_content and same_mode


def copy_plan(
    skill_dir: Path, destination: Path
) -> tuple[list[tuple[str, Path]], list[Path]]:
    source = source_entries(skill_dir)
    changes: list[tuple[str, Path]] = []
    for relative, path in source.items():
        target = destination / relative
        if not target.exists() and not target.is_symlink():
            changes.append(("ADD", relative))
        elif not same_entry(path, target):
            changes.append(("UPDATE", relative))

    preserved: list[Path] = []
    if destination.is_dir():
        for path in destination.rglob("*"):
            relative = path.relative_to(destination)
            if not excluded(relative) and relative not in source:
                preserved.append(relative)
    return sorted(changes), sorted(preserved)


def installed_content_changes(
    source_skill: Path, installed_skill: Path
) -> list[tuple[str, Path]]:
    """Compare installed content while allowing installer-normalized file modes."""

    source = source_entries(source_skill)
    changes: list[tuple[str, Path]] = []
    for relative, source_path in source.items():
        installed = installed_skill / relative
        if not installed.exists() and not installed.is_symlink():
            changes.append(("ADD", relative))
        elif source_path.is_symlink():
            if not installed.is_symlink() or os.readlink(
                source_path
            ) != os.readlink(installed):
                changes.append(("UPDATE", relative))
        elif source_path.is_dir():
            if not installed.is_dir() or installed.is_symlink():
                changes.append(("UPDATE", relative))
        elif (
            not installed.is_file()
            or installed.is_symlink()
            or not filecmp.cmp(source_path, installed, shallow=False)
        ):
            changes.append(("UPDATE", relative))
    if installed_skill.is_dir():
        for installed_path in installed_skill.rglob("*"):
            relative = installed_path.relative_to(installed_skill)
            if not excluded(relative) and relative not in source:
                changes.append(("REMOVE", relative))
    return sorted(changes)


def replace_entry(source: Path, destination: Path) -> None:
    if source.is_dir() and not source.is_symlink():
        if destination.is_symlink() or (
            destination.exists() and not destination.is_dir()
        ):
            destination.unlink()
        destination.mkdir(parents=True, exist_ok=True)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    if source.is_symlink():
        destination.symlink_to(os.readlink(source))
    else:
        shutil.copy2(source, destination)


def apply_copy(skill_dir: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for relative, source in sorted(source_entries(skill_dir).items()):
        replace_entry(source, destination / relative)


def find_validator() -> Path:
    skills_root = Path(__file__).resolve().parents[2]
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    candidates = [
        skills_root / "skillcraft" / "scripts" / "quick_validate.py",
        Path.home()
        / ".agents"
        / "skills"
        / "skillcraft"
        / "scripts"
        / "quick_validate.py",
        codex_home / "skills" / "skillcraft" / "scripts" / "quick_validate.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SyncError("Cannot find skillcraft/scripts/quick_validate.py")


def validate_skill(destination: Path) -> None:
    result = subprocess.run(
        [
            "uv",
            "run",
            "--script",
            str(find_validator()),
            str(destination),
        ],
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise SyncError(f"skillcraft validation failed for {destination}")


def push_with_retry(repo: Path, attempts: int, retry_delay: float) -> None:
    command = ["git", "-C", str(repo), "push"]
    failures: list[str] = []
    for attempt in range(1, attempts + 1):
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        output = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        if result.returncode == 0:
            if output:
                print(output)
            print(f"Pushed on attempt {attempt}/{attempts}.")
            return
        failures.append(
            f"attempt {attempt}/{attempts}, exit {result.returncode}:\n"
            f"{output or '<no git output>'}"
        )
        if attempt < attempts and retry_delay:
            time.sleep(retry_delay)
    rendered = "\n\n".join(failures)
    raise SyncError(
        f"git push failed after {attempts} attempts. "
        f"Command: {' '.join(command)}\n{rendered}"
    )


def push_source_with_retry(
    context: SourceContext, attempts: int, retry_delay: float
) -> None:
    remote_ref = f"refs/heads/{context.upstream_branch}"
    command = [
        "git",
        "-C",
        str(context.repo),
        "push",
        context.upstream_push_url,
        f"HEAD:{remote_ref}",
    ]
    failures: list[str] = []
    for attempt in range(1, attempts + 1):
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        output = "\n".join(
            part.strip()
            for part in (result.stdout, result.stderr)
            if part.strip()
        )
        if result.returncode == 0:
            if output:
                print(output)
            print(f"Pushed on attempt {attempt}/{attempts}.")
            break
        failures.append(
            f"attempt {attempt}/{attempts}, exit {result.returncode}:\n"
            f"{output or '<no git output>'}"
        )
        if attempt < attempts and retry_delay:
            time.sleep(retry_delay)
    else:
        rendered = "\n\n".join(failures)
        raise SyncError(
            f"git push failed after {attempts} attempts. "
            f"Command: {' '.join(command)}\n{rendered}"
        )

    local_head = run_git(context.repo, "rev-parse", "HEAD")
    remote_output = run_git(
        context.repo,
        "ls-remote",
        "--heads",
        context.upstream_push_url,
        remote_ref,
    )
    remote_head = remote_output.split(maxsplit=1)[0] if remote_output else ""
    if remote_head != local_head:
        raise SyncError(
            f"Push returned success but {context.upstream_push_url} "
            f"{context.upstream_branch} "
            f"is {remote_head or '<missing>'}, expected {local_head}"
        )
    run_git(
        context.repo,
        "update-ref",
        f"refs/remotes/{context.upstream_remote}/{context.upstream_branch}",
        local_head,
    )


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _compute_skill_folder_hash(skill_dir: Path) -> str:
    node = shutil.which("node")
    if node is None:
        raise SyncError("node is required to verify the Skills CLI folder hash")
    script = r"""
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const root = process.argv[1];
const files = [];
function collect(current) {
  for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
    const full = path.join(current, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === ".git" || entry.name === "node_modules") continue;
      collect(full);
    } else if (entry.isFile()) {
      files.push({
        relativePath: path.relative(root, full).split("\\").join("/"),
        content: fs.readFileSync(full),
      });
    }
  }
}
collect(root);
files.sort((left, right) => left.relativePath.localeCompare(right.relativePath));
const hash = crypto.createHash("sha256");
for (const file of files) {
  hash.update(file.relativePath);
  hash.update(file.content);
}
process.stdout.write(hash.digest("hex"));
"""
    result = subprocess.run(
        [node, "-e", script, str(skill_dir.resolve())],
        check=False,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{64}", value):
        detail = result.stderr.strip() or result.stdout.strip() or "<no output>"
        raise SyncError(f"Cannot compute Skills CLI folder hash: {detail}")
    return value


def _verified_lock_hash(
    lock_path: Path,
    skill_name: str,
    installed_skill: Path | None = None,
    expected_git_tree_hash: str | None = None,
) -> str:
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        entry = lock["skills"][skill_name]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SyncError(
            f"Refresh succeeded but {lock_path} has no usable {skill_name} hash"
        ) from exc
    if not isinstance(entry, dict):
        raise SyncError(
            f"Refresh succeeded but {lock_path} has no usable {skill_name} hash"
        )
    for field, lengths in (
        ("computedHash", (64,)),
        ("skillFolderHash", (40, 64)),
    ):
        value = entry.get(field)
        if value is None:
            continue
        if isinstance(value, str) and any(
            re.fullmatch(rf"[0-9a-f]{{{length}}}", value)
            for length in lengths
        ):
            if installed_skill is not None and len(value) == 64:
                actual = _compute_skill_folder_hash(installed_skill)
                if value != actual:
                    raise SyncError(
                        f"Refresh succeeded but {lock_path} records stale "
                        f"{skill_name} {field}: {value}, expected {actual}"
                    )
            if len(value) == 40 and expected_git_tree_hash is not None:
                if value != expected_git_tree_hash:
                    raise SyncError(
                        f"Refresh succeeded but {lock_path} records stale "
                        f"{skill_name} {field}: {value}, expected "
                        f"{expected_git_tree_hash}"
                    )
            return value
        raise SyncError(
            f"Refresh succeeded but {lock_path} has an invalid "
            f"{skill_name} {field}"
        )
    raise SyncError(
        f"Refresh succeeded but {lock_path} has no usable {skill_name} hash"
    )


def _run_installer_with_retry(
    command: list[str],
    *,
    cwd: Path,
    attempts: int,
    retry_delay: float,
    action: str,
) -> None:
    failures: list[str] = []
    for attempt in range(1, attempts + 1):
        result = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
        output = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        if result.returncode == 0:
            if output:
                print(output)
            print(f"{action} on attempt {attempt}/{attempts}.")
            return
        rendered_output = output or "<no installer output>"
        failures.append(
            f"attempt {attempt}/{attempts}, exit {result.returncode}:\n"
            f"{rendered_output}"
        )
        normalized_output = rendered_output.lower()
        if any(
            marker in normalized_output
            for marker in (
                "eperm",
                "eacces",
                "operation not permitted",
                "permission denied",
            )
        ):
            raise SyncError(
                f"{action} failed with a non-retryable filesystem permission "
                f"error. Command: {' '.join(command)}\n{failures[-1]}\n"
                "Run the exact command in a terminal that can write the target "
                "skill directory."
            )
        if attempt < attempts and retry_delay:
            time.sleep(retry_delay)
    rendered = "\n\n".join(failures)
    raise SyncError(
        f"{action} failed after {attempts} attempts. "
        f"Command: {' '.join(command)}\n{rendered}"
    )


def _verify_installed_skill(
    source_skill: Path,
    installed_skill: Path,
    lock_path: Path | None,
    expected_git_tree_hash: str | None = None,
) -> None:
    skill_name = read_skill_name(source_skill)
    if read_skill_name(installed_skill) != skill_name:
        raise SyncError("Installed and source skill names do not match")
    changes = installed_content_changes(source_skill, installed_skill)
    if changes:
        detail = ", ".join(f"{action} {path}" for action, path in changes)
        raise SyncError(
            f"Installed {skill_name} differs from source after installer success: "
            f"{detail}"
        )
    print(f"Verified installed skill matches source: {source_skill}")
    if lock_path is not None:
        computed_hash = _verified_lock_hash(
            lock_path,
            skill_name,
            installed_skill,
            expected_git_tree_hash,
        )
        print(f"Verified lock hash: {computed_hash} ({lock_path})")


def _shared_global_skills_root() -> Path:
    return Path.home() / ".agents" / "skills"


def _global_skill_lock_path(global_skills_root: Path | None = None) -> Path:
    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home).expanduser() / "skills" / ".skill-lock.json"
    skills_root = global_skills_root or _shared_global_skills_root()
    return _absolute_path(skills_root).parent / ".skill-lock.json"


def _lock_skills(lock_path: Path) -> dict[str, object]:
    if not lock_path.is_file():
        return {}
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        skills = data["skills"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SyncError(f"Cannot inspect skill lock {lock_path}: {exc}") from exc
    if not isinstance(skills, dict):
        raise SyncError(f"Skill lock has no skills object: {lock_path}")
    return skills


def _lock_tracks_skill(lock_path: Path, skill_name: str) -> bool:
    return skill_name in _lock_skills(lock_path)


def _cli_lock_skills(lock_path: Path, scope: str) -> dict[str, object]:
    if not lock_path.is_file():
        return {}
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    minimum_version = 1 if scope == "project" else 3
    version = data.get("version") if isinstance(data, dict) else None
    skills = data.get("skills") if isinstance(data, dict) else None
    if (
        isinstance(version, bool)
        or not isinstance(version, (int, float))
        or version < minimum_version
        or not isinstance(skills, dict)
    ):
        return {}
    return skills


def _validate_installation_source(
    lock_path: Path,
    skill_name: str,
    source: SourceContext,
) -> None:
    entry = _lock_skills(lock_path).get(skill_name)
    if not isinstance(entry, dict):
        raise SyncError(f"Lock has no usable {skill_name} entry: {lock_path}")
    raw_source = entry.get("source") or entry.get("sourceUrl")
    if not isinstance(raw_source, str) or not raw_source.strip():
        raise SyncError(
            f"Lock entry for {skill_name} has no source identity: {lock_path}"
        )
    locked_source = normalize_source(raw_source)
    push_source = normalize_source(source.upstream_push_url)
    if locked_source != push_source:
        raise SyncError(
            f"Installation source {locked_source} does not match actual push "
            f"endpoint {push_source}"
        )
    locked_skill_path = entry.get("skillPath")
    if not isinstance(locked_skill_path, str) or not locked_skill_path:
        raise SyncError(
            f"Skills CLI cannot update {skill_name} from {lock_path}: "
            "the lock entry has no skillPath"
        )
    expected_skill_path = (source.skill_relative / "SKILL.md").as_posix()
    if locked_skill_path != expected_skill_path:
        raise SyncError(
            f"Installation skillPath {locked_skill_path!r} does not match publish "
            f"skill path {expected_skill_path!r}"
        )


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _same_location(left: Path, right: Path) -> bool:
    left_absolute = _absolute_path(left)
    right_absolute = _absolute_path(right)
    if left_absolute == right_absolute:
        return True
    return (
        left_absolute.name == right_absolute.name
        and left_absolute.parent.resolve() == right_absolute.parent.resolve()
    )


def _project_root_from_installed_path(
    installed_skill: Path, skill_name: str
) -> Path | None:
    if installed_skill.name != skill_name:
        return None
    skills_root = installed_skill.parent
    agents_root = skills_root.parent
    if skills_root.name != "skills" or agents_root.name != ".agents":
        return None
    return _absolute_path(agents_root.parent)


def _active_installation(
    skill_dir: Path, lock_path: Path, skill_name: str
) -> bool:
    return skill_dir.is_dir() and _lock_tracks_skill(lock_path, skill_name)


def resolve_installation_scope(
    installed_skill: Path,
    skill_name: str,
    requested_scope: str,
    project_root: Path | None,
    lock_override: Path | None,
    *,
    require_tracked: bool,
    allow_no_project_context: bool = False,
) -> InstallationScope:
    installed_skill = _absolute_path(installed_skill)
    global_skills_root = _absolute_path(_shared_global_skills_root())
    global_skill = global_skills_root / skill_name
    global_lock = _global_skill_lock_path(global_skills_root)

    path_project_root = _project_root_from_installed_path(installed_skill, skill_name)
    if installed_skill == global_skill:
        inferred_scope = "global"
    elif path_project_root is not None:
        inferred_scope = "project"
    else:
        raise SyncError(
            "Cannot infer installation scope from path; expected "
            f"{global_skill} or <project>/.agents/skills/{skill_name}, not "
            f"{installed_skill}"
        )

    if requested_scope not in {"auto", inferred_scope}:
        raise SyncError(
            f"Requested {requested_scope} scope conflicts with installed path "
            f"for {inferred_scope} scope: {installed_skill}"
        )

    context_root = _absolute_path(project_root) if project_root else None
    if (
        inferred_scope == "global"
        and context_root is None
        and not allow_no_project_context
    ):
        raise SyncError(
            "Global installation requires --project-root for duplicate detection "
            "or explicit --no-project-context for a purely global operation"
        )
    if inferred_scope == "project":
        assert path_project_root is not None
        if context_root is not None and not _same_location(
            context_root, path_project_root
        ):
            raise SyncError(
                f"Project root {context_root} does not own installed skill "
                f"{installed_skill}"
            )
        context_root = _absolute_path(path_project_root)

    project_skill: Path | None = None
    canonical_project_lock: Path | None = None
    if context_root is not None:
        project_skill = context_root / ".agents" / "skills" / skill_name
        canonical_project_lock = context_root / "skills-lock.json"

    if inferred_scope == "project":
        assert context_root is not None
        expected_skill = context_root / ".agents" / "skills" / skill_name
        canonical_lock = context_root / "skills-lock.json"
        working_root = context_root
    else:
        expected_skill = global_skill
        canonical_lock = global_lock
        working_root = context_root or global_skills_root

    if lock_override is not None and not _same_location(
        lock_override, canonical_lock
    ):
        raise SyncError(
            f"Lock {lock_override.expanduser()} does not belong to "
            f"{inferred_scope} installation {expected_skill}; expected "
            f"{canonical_lock}"
        )

    project_lock = canonical_project_lock
    selected_global_lock = global_lock
    project_active = bool(
        project_skill is not None
        and project_lock is not None
        and _active_installation(project_skill, project_lock, skill_name)
    )
    global_active = _active_installation(
        global_skill, selected_global_lock, skill_name
    )
    if project_active and global_active:
        assert project_skill is not None and project_lock is not None
        raise SyncError(
            f"Conflicting project and global installations for {skill_name}: "
            f"{project_skill} ({project_lock}) and {global_skill} "
            f"({selected_global_lock}). Remove one scope before install or refresh."
        )
    if not require_tracked and (
        (inferred_scope == "project" and global_active)
        or (inferred_scope == "global" and project_active)
    ):
        opposite_scope = "global" if inferred_scope == "project" else "project"
        raise SyncError(
            f"Cannot create {inferred_scope} installation for {skill_name}; an "
            f"active {opposite_scope} installation already exists. Remove the "
            "unintended scope first."
        )

    selected_lock = canonical_lock
    if not _same_location(installed_skill, expected_skill):
        raise SyncError(
            f"Expected {inferred_scope} installation at {expected_skill}, "
            f"not {installed_skill}"
        )
    if require_tracked and not _lock_tracks_skill(selected_lock, skill_name):
        raise SyncError(
            f"{inferred_scope.capitalize()} refresh requires {skill_name} in "
            f"{selected_lock}"
        )
    return InstallationScope(
        inferred_scope,
        working_root,
        selected_lock,
        _absolute_path(expected_skill),
        context_root,
    )


def install_skill(args: argparse.Namespace) -> None:
    installed_skill = _absolute_path(Path(args.skill_dir))
    source_skill = Path(args.source_skill_dir).expanduser().resolve()
    skill_name = read_skill_name(source_skill)
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        raise SyncError(
            "pnpm is not available; load the repository's configured nvm runtime first"
        )
    if args.agent == "*":
        raise SyncError("Install requires one explicit agent; '*' is not allowed")

    scope = resolve_installation_scope(
        installed_skill,
        skill_name,
        args.scope,
        Path(args.project_root) if args.project_root else None,
        Path(args.lock) if args.lock else None,
        require_tracked=False,
        allow_no_project_context=getattr(args, "no_project_context", False),
    )
    scope_arguments = [] if scope.name == "project" else ["--global"]

    command = [
        pnpm,
        "dlx",
        "skills",
        "add",
        args.source,
        "--skill",
        skill_name,
        "--agent",
        args.agent,
        *scope_arguments,
        "--yes",
    ]
    _run_installer_with_retry(
        command,
        cwd=scope.project_root,
        attempts=args.attempts,
        retry_delay=args.retry_delay,
        action=f"Installed {skill_name} for agent {args.agent}",
    )
    _verify_installed_skill(source_skill, installed_skill, scope.lock_path)


def refresh_skill(args: argparse.Namespace) -> None:
    installed_skill = _absolute_path(Path(args.skill_dir))
    source_skill = Path(args.source_skill_dir).expanduser().resolve()
    skill_name = read_skill_name(installed_skill)
    if read_skill_name(source_skill) != skill_name:
        raise SyncError("Installed and source skill names do not match")

    pnpm = shutil.which("pnpm")
    if pnpm is None:
        raise SyncError(
            "pnpm is not available; load the repository's configured nvm runtime first"
        )
    scope = resolve_installation_scope(
        installed_skill,
        skill_name,
        args.scope,
        Path(args.project_root) if args.project_root else None,
        Path(args.lock) if args.lock else None,
        require_tracked=True,
        allow_no_project_context=getattr(args, "no_project_context", False),
    )
    scope_flag = "-p" if scope.name == "project" else "-g"

    command = [pnpm, "dlx", "skills", "update", skill_name, scope_flag, "-y"]
    _run_installer_with_retry(
        command,
        cwd=scope.project_root,
        attempts=args.attempts,
        retry_delay=args.retry_delay,
        action=f"Refreshed {skill_name} with scoped command",
    )
    _verify_installed_skill(source_skill, installed_skill, scope.lock_path)


def resolve_named_update_targets(
    project_root: Path,
    skill_name: str,
    source: SourceContext,
) -> tuple[UpdateTarget, ...]:
    """Resolve Skills CLI ownership from lock entries, never from discovered paths."""

    root = _absolute_path(project_root)
    if not root.is_dir():
        raise SyncError(f"Update project context is not a directory: {root}")

    targets: list[UpdateTarget] = []
    project_lock = root / "skills-lock.json"
    project_skills = _cli_lock_skills(project_lock, "project")
    if skill_name in project_skills:
        _validate_installation_source(project_lock, skill_name, source)
        targets.append(
            UpdateTarget(
                "project",
                project_lock,
                root / ".agents" / "skills" / skill_name,
            )
        )

    global_skills = _absolute_path(_shared_global_skills_root())
    global_lock = _global_skill_lock_path(global_skills)
    global_skills_lock = _cli_lock_skills(global_lock, "global")
    if skill_name in global_skills_lock:
        global_entry = global_skills_lock[skill_name]
        if not isinstance(global_entry, dict) or not global_entry.get(
            "skillFolderHash"
        ):
            raise SyncError(
                f"Skills CLI cannot update {skill_name} from {global_lock}: "
                "the global lock entry has no skillFolderHash"
            )
        _validate_installation_source(global_lock, skill_name, source)
        targets.append(
            UpdateTarget(
                "global",
                global_lock,
                global_skills / skill_name,
            )
        )

    if not targets:
        raise SyncError(
            f"{skill_name} is not tracked by Skills CLI in {project_lock} or "
            f"{global_lock}; install it once with 'skills add' before publishing "
            "with automatic reinstall"
        )
    return tuple(targets)


def _source_git_tree_hash(source_skill: Path) -> str:
    source = source_skill.expanduser().resolve()
    repo = git_root(source)
    relative = source.relative_to(repo)
    value = run_git(repo, "rev-parse", f"HEAD:{relative.as_posix()}")
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise SyncError(f"Cannot resolve Git tree hash for published skill: {source}")
    return value


def refresh_named_skill(
    source_skill: Path,
    project_root: Path,
    targets: tuple[UpdateTarget, ...],
    *,
    attempts: int,
    retry_delay: float,
) -> None:
    """Refresh one named skill in every matching lock-managed scope."""

    skill_name = read_skill_name(source_skill)
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        raise SyncError(
            "pnpm is not available; load the repository's configured nvm runtime first"
        )
    command = [pnpm, "dlx", "skills", "update", skill_name, "-y"]
    expected_git_tree_hash = (
        _source_git_tree_hash(source_skill)
        if any(target.scope == "global" for target in targets)
        else None
    )
    failures: list[str] = []
    for attempt in range(1, attempts + 1):
        result = subprocess.run(
            command,
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
        )
        output = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        normalized_output = output.lower()
        if any(
            marker in normalized_output
            for marker in (
                "eperm",
                "eacces",
                "operation not permitted",
                "permission denied",
            )
        ):
            raise SyncError(
                "Named skill update failed with a non-retryable filesystem "
                f"permission error. Command: {' '.join(command)}\n"
                f"attempt {attempt}/{attempts}:\n"
                f"{output or '<no installer output>'}"
            )

        if result.returncode == 0:
            try:
                for target in targets:
                    _verify_installed_skill(
                        source_skill,
                        target.installed_skill,
                        target.lock_path,
                        (
                            expected_git_tree_hash
                            if target.scope == "global"
                            else None
                        ),
                    )
            except SyncError as exc:
                failures.append(
                    f"attempt {attempt}/{attempts}, verification failed:\n{exc}\n"
                    f"{output or '<no installer output>'}"
                )
            else:
                if failures:
                    print("Previous named update attempts failed:")
                    for failure in failures:
                        print(failure)
                if output:
                    print(output)
                print(
                    f"Refreshed tracked {skill_name} installations on attempt "
                    f"{attempt}/{attempts}."
                )
                return
        else:
            rendered_output = output or "<no installer output>"
            failures.append(
                f"attempt {attempt}/{attempts}, exit {result.returncode}:\n"
                f"{rendered_output}"
            )

        normalized_failure = failures[-1].lower()
        if any(
            marker in normalized_failure
            for marker in (
                "eperm",
                "eacces",
                "operation not permitted",
                "permission denied",
            )
        ):
            raise SyncError(
                "Named skill update failed with a non-retryable filesystem "
                f"permission error. Command: {' '.join(command)}\n"
                f"{failures[-1]}"
            )
        if attempt < attempts and retry_delay:
            time.sleep(retry_delay)

    raise SyncError(
        f"Named skill update failed after {attempts} attempts. "
        f"Command: {' '.join(command)}\n" + "\n\n".join(failures)
    )


def _resolve_publish_receipt(
    args: argparse.Namespace,
) -> tuple[PublishReceipt, Path, Target | None]:
    local_skill = _absolute_path(Path(args.skill_dir))
    skill_name = read_skill_name(local_skill)
    logical_project_root = _project_root_from_installed_path(
        local_skill, skill_name
    )
    is_project_installation = bool(
        logical_project_root is not None
        and local_skill.is_dir()
        and skill_name
        in _cli_lock_skills(
            logical_project_root / "skills-lock.json", "project"
        )
    )
    direct_source = (
        None
        if is_project_installation
        else _direct_source_context(local_skill.resolve())
    )
    target: Target | None = None
    automatic_project_root: Path | None = None
    if direct_source is not None:
        source = direct_source
    else:
        registry_path = Path(args.registry).expanduser().resolve()
        target = resolve_target(
            local_skill,
            skill_name,
            registry_path,
            Path(args.repo) if args.repo else None,
            Path(args.destination) if args.destination else None,
        )
        source = _source_context_in_repo(
            target.repo, target.destination, require_tracked=False
        )
        automatic_project_root = logical_project_root

    update_root: Path | None = None
    update_targets: tuple[UpdateTarget, ...] = ()
    if args.reinstall:
        update_root = _absolute_path(
            Path(args.project_root) if args.project_root else (
                automatic_project_root or Path.cwd()
            )
        )
        update_targets = resolve_named_update_targets(
            update_root,
            skill_name,
            source,
        )

    receipt = PublishReceipt(
        source=source,
        update_root=update_root,
        update_targets=update_targets,
        push_enabled=args.push,
        reinstall_enabled=args.reinstall,
    )
    print(f"Publish source: {source.skill_dir}")
    print(f"Source repository: {source.repo}")
    print(f"Push enabled: {str(args.push).lower()}")
    print(f"Reinstall enabled: {str(args.reinstall).lower()}")
    if update_root is not None:
        print(f"Update context: {update_root}")
        for update_target in update_targets:
            print(
                f"Tracked {update_target.scope} update: "
                f"{update_target.lock_path}"
            )
    return receipt, local_skill, target


def _publish_direct_source(args: argparse.Namespace, receipt: PublishReceipt) -> None:
    context = receipt.source
    _refresh_source_upstream(context)
    _check_source_repo(
        context,
        allow_dirty=args.allow_dirty,
        allow_unpushed=args.allow_unpushed if args.push else False,
        allow_skill_changes=args.push,
    )
    validate_skill(context.skill_dir)
    if not args.push:
        print("Push skipped; verified source matches its upstream state.")
        return
    commit = _commit_skill(
        context, args.message or f"feat: publish {context.skill_dir.name} skill"
    )
    push_source_with_retry(
        context, args.push_attempts, args.push_retry_delay
    )
    if commit:
        print(f"Committed source skill: {commit}")
    print(f"Pushed: {context.branch} -> {context.upstream}")


def _check_project_copy_worktree(local_skill: Path) -> None:
    project_root = _project_root_from_installed_path(
        _absolute_path(local_skill), local_skill.name
    )
    if project_root is None:
        return
    try:
        repo = git_root(project_root)
    except SyncError:
        return
    unmerged = run_git(repo, "diff", "--name-only", "--diff-filter=U")
    if unmerged:
        raise SyncError(
            "Originating project has unresolved merge conflicts; publishing must "
            f"not copy them:\n{unmerged}"
        )


def _publish_project_copy(
    args: argparse.Namespace,
    receipt: PublishReceipt,
    local_skill: Path,
    target: Target,
) -> None:
    _check_project_copy_worktree(local_skill)
    context = receipt.source
    _refresh_source_upstream(context)
    _check_source_repo(
        context,
        allow_dirty=args.allow_dirty,
        allow_unpushed=args.allow_unpushed if args.push else False,
        allow_skill_changes=False,
    )
    changes, preserved = copy_plan(local_skill, target.destination)
    for action, relative in changes:
        print(f"{action}: {relative}")
    for relative in preserved:
        print(f"PRESERVE: {relative}")
    if changes and not args.push:
        raise SyncError(
            "--no-push cannot reinstall a project copy that differs from its "
            "published source"
        )
    if args.push and changes:
        apply_copy(local_skill, target.destination)
    validate_skill(target.destination)
    if not args.push:
        print("Push skipped; verified project copy matches published source.")
        return
    commit = _commit_skill(
        context, args.message or f"feat: sync {local_skill.name} skill"
    )
    push_source_with_retry(
        context, args.push_attempts, args.push_retry_delay
    )
    if commit:
        print(f"Committed source skill: {commit}")
    print(f"Pushed: {context.branch} -> {context.upstream}")


def publish_skill(args: argparse.Namespace) -> None:
    if not args.push and not args.reinstall:
        raise SyncError("Publish requires at least one of push or reinstall")
    receipt, local_skill, target = _resolve_publish_receipt(args)
    if target is None:
        _publish_direct_source(args, receipt)
    elif local_skill.resolve() == receipt.source.skill_dir.resolve():
        _check_project_copy_worktree(local_skill)
        _publish_direct_source(args, receipt)
    else:
        _publish_project_copy(args, receipt, local_skill, target)

    if not args.reinstall:
        print("Reinstall skipped by --no-reinstall.")
        return
    assert receipt.update_root is not None
    refresh_named_skill(
        receipt.source.skill_dir,
        receipt.update_root,
        receipt.update_targets,
        attempts=args.attempts,
        retry_delay=args.retry_delay,
    )
    print("Publish completed: requested push and reinstall steps succeeded.")


def sync_skill(args: argparse.Namespace) -> None:
    skill_dir = Path(args.skill_dir).expanduser().resolve()
    skill_name = read_skill_name(skill_dir)
    registry_path = Path(args.registry).expanduser().resolve()
    target = resolve_target(
        skill_dir,
        skill_name,
        registry_path,
        Path(args.repo) if args.repo else None,
        Path(args.destination) if args.destination else None,
    )
    source_root = git_root(skill_dir)
    if source_root == target.repo:
        raise SyncError(
            "Project skill is already inside its resolved source repository"
        )

    branch = run_git(target.repo, "branch", "--show-current")
    if not branch:
        raise SyncError(f"Source repository is in detached HEAD state: {target.repo}")
    upstream = run_git(
        target.repo,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
        check=False,
    )
    if not upstream:
        raise SyncError(f"Current branch '{branch}' has no configured upstream")

    source_relative = skill_dir.relative_to(source_root)
    source_status = run_git(
        source_root, "status", "--short", "--", str(source_relative)
    )
    if source_status and not args.allow_source_dirty:
        raise SyncError(
            "Project skill has uncommitted changes; confirm this version and rerun "
            f"with --allow-source-dirty:\n{source_status}"
        )

    destination_status = run_git(target.repo, "status", "--short")
    if destination_status and not args.allow_dirty:
        raise SyncError(
            "Source repository has uncommitted changes; choose 先提交 or 先忽略. "
            f"Use --allow-dirty only for 先忽略:\n{destination_status}"
        )
    overlap = run_git(
        target.repo,
        "status",
        "--short",
        "--",
        str(target.destination_relative),
    )
    if overlap:
        raise SyncError(
            f"Dirty source-repository changes overlap {target.destination_relative}:\n{overlap}"
        )

    ahead = run_git(target.repo, "rev-list", "--count", f"{upstream}..HEAD")
    changes, preserved = copy_plan(skill_dir, target.destination)
    print(f"Project skill: {skill_dir}")
    print(f"Source repository: {target.repo}")
    print(f"Destination: {target.destination}")
    if target.source_id:
        print(f"Resolved source: {target.source_id} via {target.lock_path}")
    else:
        print("Resolved source: explicit --repo/--destination")
    print(f"Branch: {branch} -> {upstream}")
    print(f"Existing unpushed commits: {ahead}")
    for action, relative in changes:
        print(f"{action}: {relative}")
    for relative in preserved:
        print(f"PRESERVE: {relative}")
    if not changes:
        print("No content changes to synchronize.")
        return
    if args.dry_run:
        return

    apply_copy(skill_dir, target.destination)
    validate_skill(target.destination)
    run_git(target.repo, "add", "--", str(target.destination_relative))
    staged = run_git(
        target.repo,
        "diff",
        "--cached",
        "--name-only",
        "--",
        str(target.destination_relative),
    )
    if not staged:
        print("No synchronized Git changes to commit.")
        return
    message = args.message or f"feat: sync {skill_name} skill"
    run_git(
        target.repo,
        "commit",
        "-m",
        message,
        "--",
        str(target.destination_relative),
    )
    commit_sha = run_git(target.repo, "rev-parse", "HEAD")
    push_with_retry(target.repo, args.push_attempts, args.push_retry_delay)
    print(f"Committed: {commit_sha} {message}")
    print(f"Pushed: {branch} -> {upstream}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Register local skill repositories and sync project skill changes back"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    register = subparsers.add_parser(
        "register", help="register a local source repository"
    )
    register.add_argument("repo")
    register.add_argument("--source")
    register.add_argument("--alias", action="append", default=[])
    register.add_argument("--registry", default=str(default_registry_path()))

    publish = subparsers.add_parser(
        "publish",
        help="push and refresh one named skill through its matching CLI locks",
    )
    publish.add_argument("skill_dir", help="source skill or project-installed copy")
    publish.add_argument("--repo")
    publish.add_argument("--destination")
    publish.add_argument("--registry", default=str(default_registry_path()))
    publish.add_argument("--message")
    publish.add_argument(
        "--push", action=argparse.BooleanOptionalAction, default=True
    )
    publish.add_argument(
        "--reinstall", action=argparse.BooleanOptionalAction, default=True
    )
    publish.add_argument(
        "--project-root",
        help="project context whose lock is checked together with the global lock",
    )
    publish.add_argument("--allow-dirty", action="store_true")
    publish.add_argument("--allow-unpushed", action="store_true")
    publish.add_argument("--push-attempts", type=_positive_int, default=3)
    publish.add_argument(
        "--push-retry-delay", type=_non_negative_float, default=2.0
    )
    publish.add_argument("--attempts", type=_positive_int, default=3)
    publish.add_argument("--retry-delay", type=_non_negative_float, default=2.0)

    sync = subparsers.add_parser(
        "sync", help="sync a project skill to its source repository"
    )
    sync.add_argument("skill_dir")
    sync.add_argument("--repo")
    sync.add_argument("--destination")
    sync.add_argument("--registry", default=str(default_registry_path()))
    sync.add_argument("--message")
    sync.add_argument("--allow-source-dirty", action="store_true")
    sync.add_argument("--allow-dirty", action="store_true")
    sync.add_argument("--dry-run", action="store_true")
    sync.add_argument("--push-attempts", type=_positive_int, default=3)
    sync.add_argument("--push-retry-delay", type=_non_negative_float, default=2.0)

    refresh = subparsers.add_parser(
        "refresh", help="retry and verify one scoped post-publish skill refresh"
    )
    refresh.add_argument("skill_dir", help="installed skill directory")
    refresh.add_argument(
        "--source-skill-dir",
        required=True,
        help="pushed source skill directory used for exact comparison",
    )
    refresh.add_argument(
        "--scope", choices=("auto", "project", "global"), default="auto"
    )
    refresh.add_argument("--project-root")
    refresh.add_argument("--no-project-context", action="store_true")
    refresh.add_argument("--lock")
    refresh.add_argument("--attempts", type=_positive_int, default=3)
    refresh.add_argument("--retry-delay", type=_non_negative_float, default=2.0)

    install = subparsers.add_parser(
        "install", help="install and verify one skill for one explicit agent"
    )
    install.add_argument("source", help="Skills CLI repository source")
    install.add_argument("skill_dir", help="expected installed skill directory")
    install.add_argument(
        "--source-skill-dir",
        required=True,
        help="pushed source skill directory used for exact comparison",
    )
    install.add_argument(
        "--scope", choices=("auto", "project", "global"), default="auto"
    )
    install.add_argument("--agent", default="codex")
    install.add_argument("--project-root")
    install.add_argument("--no-project-context", action="store_true")
    install.add_argument("--lock")
    install.add_argument("--attempts", type=_positive_int, default=3)
    install.add_argument("--retry-delay", type=_non_negative_float, default=2.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "register":
            entry = register_repository(
                Path(args.repo),
                Path(args.registry).expanduser().resolve(),
                args.source,
                args.alias,
            )
            print(json.dumps(entry, ensure_ascii=False, indent=2))
        elif args.command == "publish":
            publish_skill(args)
        elif args.command == "sync":
            sync_skill(args)
        elif args.command == "refresh":
            refresh_skill(args)
        else:
            install_skill(args)
    except SyncError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
