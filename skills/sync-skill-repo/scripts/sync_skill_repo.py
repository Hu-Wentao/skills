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

    project_root = git_root(skill_dir)
    lock_path = nearest_lock(skill_dir, project_root)
    if lock_path is None:
        raise SyncError(
            "No skills-lock.json found; pass --repo and optional --destination"
        )
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        entry = lock["skills"][skill_name]
        source_id = str(entry["source"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
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
            "--with",
            "pyyaml",
            "python",
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


def _verified_lock_hash(lock_path: Path, skill_name: str) -> str:
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        computed_hash = lock["skills"][skill_name]["computedHash"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SyncError(
            f"Refresh succeeded but {lock_path} has no usable {skill_name} hash"
        ) from exc
    if not isinstance(computed_hash, str) or not re.fullmatch(
        r"[0-9a-f]{64}", computed_hash
    ):
        raise SyncError(
            f"Refresh succeeded but {lock_path} has an invalid {skill_name} hash"
        )
    return computed_hash


def refresh_skill(args: argparse.Namespace) -> None:
    installed_skill = Path(args.skill_dir).expanduser().resolve()
    source_skill = Path(args.source_skill_dir).expanduser().resolve()
    skill_name = read_skill_name(installed_skill)
    if read_skill_name(source_skill) != skill_name:
        raise SyncError("Installed and source skill names do not match")

    pnpm = shutil.which("pnpm")
    if pnpm is None:
        raise SyncError(
            "pnpm is not available; load the repository's configured nvm runtime first"
        )
    if args.scope == "project":
        project_root = (
            Path(args.project_root).expanduser().resolve()
            if args.project_root
            else git_root(installed_skill)
        )
        scope_flag = "-p"
        lock_path = (
            Path(args.lock).expanduser().resolve()
            if args.lock
            else project_root / "skills-lock.json"
        )
    else:
        project_root = (
            Path(args.project_root).expanduser().resolve()
            if args.project_root
            else installed_skill.parent
        )
        scope_flag = "-g"
        lock_path = Path(args.lock).expanduser().resolve() if args.lock else None

    command = [pnpm, "dlx", "skills", "update", skill_name, scope_flag, "-y"]
    failures: list[str] = []
    for attempt in range(1, args.attempts + 1):
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
        if result.returncode == 0:
            if output:
                print(output)
            print(
                f"Refreshed {skill_name} with scoped command on attempt "
                f"{attempt}/{args.attempts}."
            )
            break
        failures.append(
            f"attempt {attempt}/{args.attempts}, exit {result.returncode}:\n"
            f"{output or '<no installer output>'}"
        )
        if attempt < args.attempts and args.retry_delay:
            time.sleep(args.retry_delay)
    else:
        rendered = "\n\n".join(failures)
        raise SyncError(
            "Scoped skill refresh failed after "
            f"{args.attempts} attempts. Command: {' '.join(command)}\n{rendered}"
        )

    changes, _ = copy_plan(source_skill, installed_skill)
    if changes:
        detail = ", ".join(f"{action} {path}" for action, path in changes)
        raise SyncError(
            f"Refresh succeeded but installed {skill_name} differs from source: "
            f"{detail}"
        )
    print(f"Verified installed skill matches source: {source_skill}")
    if lock_path is not None:
        computed_hash = _verified_lock_hash(lock_path, skill_name)
        print(f"Verified lock hash: {computed_hash} ({lock_path})")


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
    refresh.add_argument("--scope", choices=("project", "global"), required=True)
    refresh.add_argument("--project-root")
    refresh.add_argument("--lock")
    refresh.add_argument("--attempts", type=_positive_int, default=3)
    refresh.add_argument("--retry-delay", type=_non_negative_float, default=2.0)
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
        elif args.command == "sync":
            sync_skill(args)
        else:
            refresh_skill(args)
    except SyncError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
