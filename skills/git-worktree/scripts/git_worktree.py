#!/usr/bin/env python3
"""Deterministic Git worktree lifecycle operations."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


class WorkflowError(RuntimeError):
    """A safe, user-actionable workflow failure."""


@dataclass(frozen=True)
class Worktree:
    path: str
    head: str | None = None
    branch: str | None = None
    detached: bool = False
    locked: bool = False
    prunable: bool = False
    main: bool = False


def run_git(
    cwd: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown Git error"
        raise WorkflowError(f"git {' '.join(args)} failed: {detail}")
    return result


def repository_root(path: str) -> Path:
    candidate = Path(path).expanduser().resolve()
    if not candidate.exists():
        raise WorkflowError(f"Repository path does not exist: {candidate}")
    result = run_git(candidate, "rev-parse", "--show-toplevel")
    return Path(result.stdout.strip()).resolve()


def current_branch(repo: Path) -> str:
    branch = run_git(repo, "branch", "--show-current").stdout.strip()
    if not branch:
        raise WorkflowError("Detached HEAD is not supported for this operation.")
    return branch


def local_branch_exists(repo: Path, branch: str) -> bool:
    return (
        run_git(
            repo,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
            check=False,
        ).returncode
        == 0
    )


def parse_worktrees(repo: Path) -> list[Worktree]:
    output = run_git(repo, "worktree", "list", "--porcelain").stdout
    records: list[dict[str, object]] = []
    current: dict[str, object] = {}

    for line in [*output.splitlines(), ""]:
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["path"] = value
        elif key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key in {"detached", "locked", "prunable"}:
            current[key] = True

    return [
        Worktree(
            path=str(record["path"]),
            head=record.get("head") if isinstance(record.get("head"), str) else None,
            branch=(
                record.get("branch") if isinstance(record.get("branch"), str) else None
            ),
            detached=bool(record.get("detached", False)),
            locked=bool(record.get("locked", False)),
            prunable=bool(record.get("prunable", False)),
            main=index == 0,
        )
        for index, record in enumerate(records)
    ]


def status_lines(path: Path) -> list[str]:
    output = run_git(path, "status", "--porcelain=v1", "--untracked-files=all").stdout
    return [line for line in output.splitlines() if line]


def merge_in_progress(path: Path) -> bool:
    return (
        run_git(
            path, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False
        ).returncode
        == 0
    )


def affected_worktrees(repo: Path, *branches: str) -> list[Worktree]:
    wanted = set(branches)
    return [worktree for worktree in parse_worktrees(repo) if worktree.branch in wanted]


def ensure_affected_worktrees_clean(repo: Path, *branches: str) -> None:
    for worktree in affected_worktrees(repo, *branches):
        changes = status_lines(Path(worktree.path))
        if changes:
            rendered = "\n".join(changes)
            raise WorkflowError(
                f"Branch '{worktree.branch}' is dirty in {worktree.path}:\n{rendered}"
            )


def unmerged_candidates(repo: Path, target: str) -> list[str]:
    branches = run_git(
        repo, "for-each-ref", "--format=%(refname:short)", "refs/heads"
    ).stdout.splitlines()
    candidates: list[str] = []
    for branch in branches:
        if branch == target:
            continue
        if (
            run_git(
                repo,
                "merge-base",
                "--is-ancestor",
                branch,
                target,
                check=False,
            ).returncode
            == 0
        ):
            continue
        ahead = int(run_git(repo, "rev-list", "--count", f"{target}..{branch}").stdout)
        if ahead >= 1:
            candidates.append(branch)
    return sorted(candidates)


def emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def command_list(repo: Path, _args: argparse.Namespace) -> None:
    emit({"worktrees": [asdict(worktree) for worktree in parse_worktrees(repo)]})


def command_create(repo: Path, args: argparse.Namespace) -> None:
    branch = args.branch
    base = args.base or current_branch(repo)
    if not local_branch_exists(repo, base):
        raise WorkflowError(f"Base branch does not exist locally: {base}")
    if local_branch_exists(repo, branch):
        raise WorkflowError(f"Branch already exists locally: {branch}")

    main_path = Path(parse_worktrees(repo)[0].path)
    safe_branch = branch.replace("/", "-")
    destination = (
        Path(args.path).expanduser().resolve()
        if args.path
        else main_path.parent / f"{main_path.name}-T-{safe_branch}"
    )
    if destination.exists():
        raise WorkflowError(f"Worktree path already exists: {destination}")

    run_git(repo, "worktree", "add", "-b", branch, str(destination), base)
    emit(
        {
            "action": "created",
            "base": base,
            "branch": branch,
            "worktree": str(destination),
        }
    )


def resolve_source(repo: Path, source: str | None, target: str) -> str:
    if source:
        return source
    candidates = unmerged_candidates(repo, target)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise WorkflowError(
            f"No unmerged local branch is ahead of target '{target}'; specify --source."
        )
    raise WorkflowError(
        "Multiple unmerged branches are ahead of "
        f"'{target}': {', '.join(candidates)}; specify --source."
    )


def command_merge(repo: Path, args: argparse.Namespace) -> None:
    target = args.target or current_branch(repo)
    if current_branch(repo) != target:
        raise WorkflowError(
            f"Current worktree must be checked out on target branch '{target}'."
        )
    source = resolve_source(repo, args.source, target)
    if source == target:
        raise WorkflowError("Source and target branches must be different.")
    for branch in (source, target):
        if not local_branch_exists(repo, branch):
            raise WorkflowError(f"Local branch does not exist: {branch}")
    if merge_in_progress(repo):
        raise WorkflowError("A merge is already in progress in the target worktree.")

    ensure_affected_worktrees_clean(repo, source, target)
    result = run_git(repo, "merge", "--no-ff", "--no-edit", source, check=False)
    if result.returncode != 0:
        conflicts = run_git(
            repo, "diff", "--name-only", "--diff-filter=U", check=False
        ).stdout.splitlines()
        if conflicts:
            raise WorkflowError(
                "Merge paused with conflicts: "
                + ", ".join(conflicts)
                + ". Resolve them in the target worktree and continue the merge."
            )
        detail = result.stderr.strip() or result.stdout.strip() or "unknown Git error"
        raise WorkflowError(f"Merge failed: {detail}")

    emit(
        {
            "action": "merged",
            "commit": run_git(repo, "rev-parse", "HEAD").stdout.strip(),
            "source": source,
            "target": target,
        }
    )


def command_remove(repo: Path, args: argparse.Namespace) -> None:
    requested = Path(args.worktree).expanduser().resolve()
    worktrees = parse_worktrees(repo)
    selected = next(
        (item for item in worktrees if Path(item.path).resolve() == requested), None
    )
    if selected is None:
        raise WorkflowError(f"Registered worktree not found: {requested}")
    if selected.main:
        raise WorkflowError("The main worktree cannot be removed.")
    if selected.locked:
        raise WorkflowError(f"Locked worktree cannot be removed: {requested}")
    if merge_in_progress(requested):
        raise WorkflowError(f"A merge is in progress in worktree: {requested}")
    changes = status_lines(requested)
    if changes:
        raise WorkflowError(
            f"Worktree is dirty and cannot be removed: {requested}\n"
            + "\n".join(changes)
        )

    if args.require_merged_into:
        if not selected.branch:
            raise WorkflowError(
                "Detached worktree cannot satisfy a merged-branch check."
            )
        if not local_branch_exists(repo, args.require_merged_into):
            raise WorkflowError(
                f"Required target branch does not exist locally: {args.require_merged_into}"
            )
        merged = run_git(
            repo,
            "merge-base",
            "--is-ancestor",
            selected.branch,
            args.require_merged_into,
            check=False,
        ).returncode
        if merged != 0:
            raise WorkflowError(
                f"Branch '{selected.branch}' is not merged into "
                f"'{args.require_merged_into}'."
            )

    run_git(repo, "worktree", "remove", str(requested))
    emit(
        {
            "action": "removed",
            "branch": selected.branch,
            "branch_retained": True,
            "worktree": str(requested),
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", default=os.getcwd(), help="Repository or worktree path (default: cwd)"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    list_parser = commands.add_parser("list", help="List registered worktrees")
    list_parser.set_defaults(handler=command_list)

    create = commands.add_parser("create", help="Create a branch and worktree")
    create.add_argument("--branch", required=True)
    create.add_argument("--base")
    create.add_argument("--path")
    create.set_defaults(handler=command_create)

    merge = commands.add_parser("merge", help="Merge a source branch into the target")
    merge.add_argument("--source")
    merge.add_argument("--target")
    merge.set_defaults(handler=command_merge)

    remove = commands.add_parser("remove", help="Safely remove a worktree")
    remove.add_argument("--worktree", required=True)
    remove.add_argument("--require-merged-into")
    remove.set_defaults(handler=command_remove)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        repo = repository_root(args.repo)
        args.handler(repo, args)
    except WorkflowError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
