#!/usr/bin/env python3
"""Deterministic Git worktree lifecycle operations."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
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


@dataclass(frozen=True)
class BranchAudit:
    branch: str
    commit: str
    committed_at: str
    committed_at_unix: int
    subject: str
    upstream: str | None
    ahead: int
    behind: int
    unique_non_merge_commits: int
    patch_equivalent_commits: int
    patch_unique_commits: int
    patch_equivalent_to_target: bool
    protected: bool
    worktrees: tuple[dict[str, object], ...]


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


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def protected_branch(branch: str) -> bool:
    return branch.startswith(("release/", "hotfix/"))


def worktree_evidence(repo: Path, branch: str) -> tuple[dict[str, object], ...]:
    evidence: list[dict[str, object]] = []
    for worktree in affected_worktrees(repo, branch):
        path = Path(worktree.path)
        exists = path.exists()
        changes = status_lines(path) if exists else []
        evidence.append(
            {
                "path": worktree.path,
                "dirty": bool(changes),
                "changes": changes,
                "locked": worktree.locked,
                "prunable": worktree.prunable,
                "main": worktree.main,
            }
        )
    return tuple(evidence)


def branch_audits(repo: Path, target: str) -> list[BranchAudit]:
    if not local_branch_exists(repo, target):
        raise WorkflowError(f"Target branch does not exist locally: {target}")

    fields = (
        "%(refname:short)%00%(objectname)%00%(committerdate:unix)%00"
        "%(committerdate:iso8601-strict)%00%(subject)%00%(upstream:short)"
    )
    output = run_git(
        repo, "for-each-ref", f"--format={fields}", "refs/heads"
    ).stdout
    audits: list[BranchAudit] = []
    for line in output.splitlines():
        branch, commit, unix, committed_at, subject, upstream = line.split("\0")
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

        behind, ahead = (
            int(value)
            for value in run_git(
                repo, "rev-list", "--left-right", "--count", f"{target}...{branch}"
            ).stdout.split()
        )
        unique_non_merge = int(
            run_git(
                repo, "rev-list", "--count", "--no-merges", f"{target}..{branch}"
            ).stdout
        )
        cherry_lines = [
            item
            for item in run_git(repo, "cherry", target, branch).stdout.splitlines()
            if item
        ]
        equivalent = sum(item.startswith("-") for item in cherry_lines)
        unique = sum(item.startswith("+") for item in cherry_lines)
        audits.append(
            BranchAudit(
                branch=branch,
                commit=commit,
                committed_at=committed_at,
                committed_at_unix=int(unix),
                subject=subject,
                upstream=upstream or None,
                ahead=ahead,
                behind=behind,
                unique_non_merge_commits=unique_non_merge,
                patch_equivalent_commits=equivalent,
                patch_unique_commits=unique,
                patch_equivalent_to_target=(
                    unique_non_merge > 0
                    and equivalent == unique_non_merge
                    and unique == 0
                ),
                protected=protected_branch(branch),
                worktrees=worktree_evidence(repo, branch),
            )
        )
    return sorted(
        audits,
        key=lambda item: (item.committed_at_unix, item.branch),
        reverse=True,
    )


def unmerged_candidates(repo: Path, target: str) -> list[str]:
    return sorted(item.branch for item in branch_audits(repo, target) if item.ahead)


def emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def command_list(repo: Path, _args: argparse.Namespace) -> None:
    emit({"worktrees": [asdict(worktree) for worktree in parse_worktrees(repo)]})


def command_branch_audit(repo: Path, args: argparse.Namespace) -> None:
    target = args.target or current_branch(repo)
    audits = branch_audits(repo, target)
    if args.recent_count is not None:
        selected = audits[: args.recent_count]
        selection = {"kind": "recent_count", "value": args.recent_count}
    else:
        cutoff = int(time.time()) - args.recent_days * 86_400
        selected = [item for item in audits if item.committed_at_unix >= cutoff]
        selection = {
            "kind": "recent_days",
            "value": args.recent_days,
            "cutoff_unix": cutoff,
        }
    emit(
        {
            "action": "branch_audit",
            "target": target,
            "scope": "local_unmerged",
            "selection": selection,
            "total_unmerged": len(audits),
            "branches": [asdict(item) for item in selected],
        }
    )


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


def command_branch_delete(repo: Path, args: argparse.Namespace) -> None:
    branch = args.branch
    target = args.target or current_branch(repo)
    if branch == target:
        raise WorkflowError("The target branch cannot be deleted.")
    for name in (branch, target):
        if not local_branch_exists(repo, name):
            raise WorkflowError(f"Local branch does not exist: {name}")
    if protected_branch(branch) and not args.allow_protected:
        raise WorkflowError(
            f"Protected branch '{branch}' requires --allow-protected."
        )

    commit = run_git(repo, "rev-parse", f"{branch}^{{commit}}").stdout.strip()
    merged = (
        run_git(
            repo,
            "merge-base",
            "--is-ancestor",
            branch,
            target,
            check=False,
        ).returncode
        == 0
    )
    if not merged and not args.allow_unmerged:
        raise WorkflowError(
            f"Branch '{branch}' is not merged into '{target}'; "
            "use --allow-unmerged only after evidence-based maintenance analysis."
        )

    removed_worktrees: list[str] = []
    for worktree in affected_worktrees(repo, branch):
        requested = Path(worktree.path)
        if worktree.main:
            raise WorkflowError(
                "A branch checked out in the main worktree cannot be deleted."
            )
        if worktree.locked:
            raise WorkflowError(f"Locked worktree cannot be removed: {requested}")
        if worktree.prunable or not requested.exists():
            raise WorkflowError(
                f"Prunable or missing worktree requires separate review: {requested}"
            )
        if merge_in_progress(requested):
            raise WorkflowError(f"A merge is in progress in worktree: {requested}")
        changes = status_lines(requested)
        if changes:
            raise WorkflowError(
                f"Worktree is dirty and cannot be removed: {requested}\n"
                + "\n".join(changes)
            )
        if not args.remove_worktree:
            raise WorkflowError(
                f"Branch '{branch}' is checked out in {requested}; "
                "pass --remove-worktree to remove the clean worktree."
            )
        run_git(repo, "worktree", "remove", str(requested))
        removed_worktrees.append(str(requested))

    run_git(repo, "branch", "-d" if merged else "-D", "--", branch)
    emit(
        {
            "action": "branch_deleted",
            "branch": branch,
            "commit": commit,
            "merged_into_target": merged,
            "reason": args.reason,
            "remote_branch_untouched": True,
            "removed_worktrees": removed_worktrees,
            "target": target,
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

    branch_audit = commands.add_parser(
        "branch-audit", help="Inventory recent unmerged local branches"
    )
    branch_audit.add_argument("--target")
    branch_window = branch_audit.add_mutually_exclusive_group(required=True)
    branch_window.add_argument("--recent-count", type=positive_int)
    branch_window.add_argument("--recent-days", type=positive_int)
    branch_audit.set_defaults(handler=command_branch_audit)

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

    branch_delete = commands.add_parser(
        "branch-delete", help="Safely delete one classified local branch"
    )
    branch_delete.add_argument("--branch", required=True)
    branch_delete.add_argument("--target")
    branch_delete.add_argument("--reason", required=True)
    branch_delete.add_argument("--allow-unmerged", action="store_true")
    branch_delete.add_argument("--allow-protected", action="store_true")
    branch_delete.add_argument("--remove-worktree", action="store_true")
    branch_delete.set_defaults(handler=command_branch_delete)
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
