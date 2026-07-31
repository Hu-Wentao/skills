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


OPERATION_MARKERS = {
    "merge": ("MERGE_HEAD",),
    "rebase": ("rebase-merge", "rebase-apply"),
    "cherry_pick": ("CHERRY_PICK_HEAD",),
    "revert": ("REVERT_HEAD",),
    "bisect": ("BISECT_LOG",),
}


def run_git(
    cwd: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        errors="replace",
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


def local_branch_heads(repo: Path) -> dict[str, str]:
    output = run_git(
        repo,
        "for-each-ref",
        "--format=%(refname:short)%00%(objectname)",
        "refs/heads",
    ).stdout
    return dict(line.split("\0", 1) for line in output.splitlines() if line)


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
    output = run_git(
        path, "status", "--porcelain=v1", "-z", "--untracked-files=all"
    ).stdout
    return [entry for entry in output.split("\0") if entry]


def operation_state(path: Path) -> tuple[str, ...]:
    operations: list[str] = []
    for operation, markers in OPERATION_MARKERS.items():
        for marker in markers:
            result = run_git(path, "rev-parse", "--git-path", marker)
            marker_path = Path(result.stdout.strip())
            if not marker_path.is_absolute():
                marker_path = path / marker_path
            if marker_path.exists():
                operations.append(operation)
                break
    return tuple(operations)


def ensure_no_operation(path: Path) -> None:
    operations = operation_state(path)
    if operations:
        raise WorkflowError(
            f"Git operation in progress in {path}: {', '.join(operations)}"
        )


def affected_worktrees(repo: Path, *branches: str) -> list[Worktree]:
    wanted = set(branches)
    return [worktree for worktree in parse_worktrees(repo) if worktree.branch in wanted]


def ensure_affected_worktrees_clean(repo: Path, *branches: str) -> None:
    for worktree in affected_worktrees(repo, *branches):
        path = Path(worktree.path)
        if not path.exists() or worktree.prunable:
            raise WorkflowError(
                f"Branch '{worktree.branch}' has a missing or prunable worktree: "
                f"{worktree.path}"
            )
        if worktree.locked:
            raise WorkflowError(
                f"Branch '{worktree.branch}' has a locked worktree: {worktree.path}"
            )
        ensure_no_operation(path)
        changes = status_lines(path)
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
    return branch.startswith(("release/", "repair/", "hotfix/"))


def worktree_snapshot(worktree: Worktree) -> dict[str, object]:
    path = Path(worktree.path)
    exists = path.exists()
    inspection_error: str | None = None
    try:
        changes = status_lines(path) if exists else []
        operations = operation_state(path) if exists else ()
    except WorkflowError as error:
        changes = []
        operations = ()
        inspection_error = str(error)
    return {
        "path": worktree.path,
        "head": worktree.head,
        "branch": worktree.branch,
        "detached": worktree.detached,
        "exists": exists,
        "inspectable": exists and inspection_error is None,
        "inspection_error": inspection_error,
        "dirty": bool(changes),
        "changes": changes,
        "operations": list(operations),
        "locked": worktree.locked,
        "prunable": worktree.prunable,
        "main": worktree.main,
    }


def worktree_evidence(repo: Path, branch: str) -> tuple[dict[str, object], ...]:
    return tuple(
        worktree_snapshot(worktree)
        for worktree in affected_worktrees(repo, branch)
    )


def commit_metadata(repo: Path, commit: str) -> dict[str, object]:
    output = run_git(
        repo,
        "show",
        "-s",
        "--format=%H%x00%ct%x00%cI%x00%s",
        commit,
    ).stdout.rstrip("\n")
    resolved, committed_at_unix, committed_at, subject = output.split("\0", 3)
    return {
        "head": resolved,
        "committed_at_unix": int(committed_at_unix),
        "committed_at": committed_at,
        "subject": subject,
    }


def target_relation(repo: Path, target: str, head: str) -> dict[str, object]:
    behind, ahead = (
        int(value)
        for value in run_git(
            repo, "rev-list", "--left-right", "--count", f"{target}...{head}"
        ).stdout.split()
    )
    unique_non_merge = int(
        run_git(repo, "rev-list", "--count", "--no-merges", f"{target}..{head}")
        .stdout.strip()
    )
    history_related = (
        run_git(repo, "merge-base", target, head, check=False).returncode == 0
    )
    if history_related:
        cherry_lines = [
            line
            for line in run_git(repo, "cherry", target, head).stdout.splitlines()
            if line
        ]
        equivalent = sum(line.startswith("-") for line in cherry_lines)
        unique = sum(line.startswith("+") for line in cherry_lines)
    else:
        equivalent = 0
        unique = unique_non_merge
    contained = (
        run_git(
            repo, "merge-base", "--is-ancestor", head, target, check=False
        ).returncode
        == 0
    )
    return {
        "target": target,
        "history_related": history_related,
        "contained_in_target": contained,
        "ahead": ahead,
        "behind": behind,
        "unique_non_merge_commits": unique_non_merge,
        "patch_equivalent_commits": equivalent,
        "patch_unique_commits": unique,
        "patch_equivalent_to_target": (
            not contained
            and history_related
            and unique_non_merge > 0
            and equivalent == unique_non_merge
            and unique == 0
        ),
    }


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


def decision_evidence(
    kind: str,
    relation: dict[str, object],
    worktrees: Sequence[dict[str, object]],
    protected: bool,
) -> dict[str, object]:
    dirty = any(bool(item["dirty"]) for item in worktrees)
    operations = sorted(
        {
            str(operation)
            for item in worktrees
            for operation in item.get("operations", [])
        }
    )
    locked = any(bool(item["locked"]) for item in worktrees)
    missing = any(not bool(item["exists"]) for item in worktrees)
    uninspectable = any(not bool(item["inspectable"]) for item in worktrees)
    contained = bool(relation["contained_in_target"])
    patch_equivalent = bool(relation["patch_equivalent_to_target"])

    if kind == "worktree":
        decision_scope = "worktree_only_branch_ref_retained"
        if uninspectable:
            possible = ["retain"]
        elif dirty or operations or locked:
            possible = ["merge", "retain"]
        elif contained or not worktrees[0].get("detached", False):
            possible = ["delete", "retain"]
        else:
            possible = ["merge", "delete", "retain"]
    else:
        decision_scope = "branch_and_committed_history"
        if uninspectable:
            possible = ["retain"]
        elif dirty or operations or locked:
            possible = ["merge", "retain"]
        elif contained or patch_equivalent:
            possible = ["delete", "retain"]
        else:
            possible = ["merge", "delete", "retain"]

    requirements: list[str] = []
    if dirty:
        requirements.append("commit authorization and validation before merge")
    if operations:
        requirements.append("finish or abort the active Git operation first")
    if locked:
        requirements.append("unlock only with explicit ownership evidence")
    if missing:
        requirements.append("prune only the missing registration; preserve branch refs")
    if uninspectable:
        requirements.append("repair or independently inspect the worktree before mutation")
    if kind == "worktree" and worktrees[0].get("detached", False) and (
        not contained or dirty
    ):
        requirements.append(
            "create a rescue branch at the exact HEAD before preserving changes, "
            "merge, or uncontained deletion"
        )
    if protected and kind == "branch":
        requirements.append("protected branch deletion requires separate authorization")
        possible = [item for item in possible if item != "delete"]
        if "retain" not in possible:
            possible.append("retain")

    return {
        "decision_scope": decision_scope,
        "possible_decisions": possible,
        "requirements": requirements,
        "dirty": dirty,
        "operations": operations,
        "locked": locked,
        "missing": missing,
        "uninspectable": uninspectable,
    }


def maintenance_candidates(repo: Path, target: str) -> list[dict[str, object]]:
    if not local_branch_exists(repo, target):
        raise WorkflowError(f"Target branch does not exist locally: {target}")

    worktrees = parse_worktrees(repo)
    by_branch: dict[str, list[Worktree]] = {}
    for worktree in worktrees:
        if worktree.branch:
            by_branch.setdefault(worktree.branch, []).append(worktree)

    fields = "%(refname:short)%00%(objectname)%00%(upstream:short)"
    refs = run_git(repo, "for-each-ref", f"--format={fields}", "refs/heads").stdout
    items: list[dict[str, object]] = []
    for line in refs.splitlines():
        branch, head, upstream = line.split("\0")
        if branch == target:
            continue
        metadata = commit_metadata(repo, head)
        relation = target_relation(repo, target, head)
        snapshots = [
            worktree_snapshot(worktree) for worktree in by_branch.get(branch, [])
        ]
        protected = protected_branch(branch)
        items.append(
            {
                "candidate_id": f"branch:{branch}",
                "kind": "branch",
                "branch": branch,
                "upstream": upstream or None,
                "protected": protected,
                **metadata,
                "relation": relation,
                "worktrees": snapshots,
                "decision_evidence": decision_evidence(
                    "branch", relation, snapshots, protected
                ),
            }
        )

    for worktree in worktrees:
        if worktree.main:
            continue
        if not worktree.head:
            continue
        metadata = commit_metadata(repo, worktree.head)
        relation = target_relation(repo, target, worktree.head)
        snapshots = [worktree_snapshot(worktree)]
        protected = bool(worktree.branch and protected_branch(worktree.branch))
        items.append(
            {
                "candidate_id": f"worktree:{worktree.path}",
                "kind": "worktree",
                "branch": worktree.branch,
                "detached": worktree.detached,
                "upstream": None,
                "protected": protected,
                **metadata,
                "relation": relation,
                "worktrees": snapshots,
                "decision_evidence": decision_evidence(
                    "worktree", relation, snapshots, protected
                ),
            }
        )

    return sorted(
        items,
        key=lambda item: (int(item["committed_at_unix"]), str(item["candidate_id"])),
        reverse=True,
    )


def maintenance_branch_candidate(
    repo: Path, target: str, branch: str
) -> dict[str, object]:
    candidate_id = f"branch:{branch}"
    candidate = next(
        (
            item
            for item in maintenance_candidates(repo, target)
            if item["candidate_id"] == candidate_id
        ),
        None,
    )
    if candidate is None:
        raise WorkflowError(
            f"Rescued branch was not returned by maintenance audit: {branch}"
        )
    return candidate


def main_worktree_branch(repo: Path) -> str:
    main = next((worktree for worktree in parse_worktrees(repo) if worktree.main), None)
    if main is None or not main.branch:
        raise WorkflowError(
            "The main worktree must be attached to a branch, or pass --target explicitly."
        )
    return main.branch


def unmerged_candidates(repo: Path, target: str) -> list[str]:
    return sorted(item.branch for item in branch_audits(repo, target) if item.ahead)


def emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def verify_expected_head(actual: str, expected: str | None, label: str) -> None:
    if expected and actual != expected:
        raise WorkflowError(
            f"{label} HEAD changed since audit: expected {expected}, found {actual}"
        )


def command_list(repo: Path, _args: argparse.Namespace) -> None:
    emit({"worktrees": [asdict(worktree) for worktree in parse_worktrees(repo)]})


def command_maintenance_audit(repo: Path, args: argparse.Namespace) -> None:
    target = args.target or current_branch(repo)
    items = maintenance_candidates(repo, target)
    if args.all:
        selected = items
        selection: dict[str, object] = {"kind": "all"}
    elif args.recent_count is not None:
        selected = items[: args.recent_count]
        selection = {"kind": "recent_count", "value": args.recent_count}
    else:
        cutoff = int(time.time()) - args.recent_days * 86_400
        selected = [
            item for item in items if int(item["committed_at_unix"]) >= cutoff
        ]
        selection = {
            "kind": "recent_days",
            "value": args.recent_days,
            "cutoff_unix": cutoff,
        }

    target_head = run_git(repo, "rev-parse", f"{target}^{{commit}}").stdout.strip()
    target_worktrees = [
        worktree_snapshot(worktree)
        for worktree in affected_worktrees(repo, target)
    ]
    emit(
        {
            "action": "maintenance_audit",
            "scope": "local_branches_and_worktrees",
            "target": {
                "branch": target,
                "head": target_head,
                "worktrees": target_worktrees,
            },
            "selection": selection,
            "total_candidates": len(items),
            "selected_candidates": len(selected),
            "candidates": selected,
        }
    )


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
    source_head = run_git(repo, "rev-parse", f"{source}^{{commit}}").stdout.strip()
    target_head = run_git(repo, "rev-parse", f"{target}^{{commit}}").stdout.strip()
    verify_expected_head(source_head, args.expected_source_head, f"Source '{source}'")
    verify_expected_head(target_head, args.expected_target_head, f"Target '{target}'")
    ensure_no_operation(repo)

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
    if selected.prunable or not requested.exists():
        raise WorkflowError(
            f"Missing or prunable worktree requires prune-missing: {requested}"
        )
    ensure_no_operation(requested)
    actual_head = run_git(requested, "rev-parse", "HEAD^{commit}").stdout.strip()
    if selected.detached and not args.expected_head:
        raise WorkflowError(
            "Detached worktree removal requires --expected-head from a current audit."
        )
    verify_expected_head(actual_head, args.expected_head, f"Worktree '{requested}'")
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

    if args.require_contained_in:
        if not local_branch_exists(repo, args.require_contained_in):
            raise WorkflowError(
                f"Required target branch does not exist locally: "
                f"{args.require_contained_in}"
            )
        contained = run_git(
            repo,
            "merge-base",
            "--is-ancestor",
            actual_head,
            args.require_contained_in,
            check=False,
        ).returncode
        if contained != 0:
            raise WorkflowError(
                f"Worktree HEAD {actual_head} is not contained in "
                f"'{args.require_contained_in}'."
            )

    if selected.detached and not args.require_contained_in:
        if not args.allow_uncontained_detached or not args.reason:
            raise WorkflowError(
                "Detached worktree removal requires --require-contained-in, or both "
                "--allow-uncontained-detached and --reason after evidence-based review."
            )

    run_git(repo, "worktree", "remove", str(requested))
    emit(
        {
            "action": "removed",
            "branch": selected.branch,
            "branch_retained": selected.branch is not None,
            "head": actual_head,
            "reason": args.reason,
            "worktree": str(requested),
        }
    )


def command_rescue_detached(repo: Path, args: argparse.Namespace) -> None:
    requested = Path(args.worktree).expanduser().resolve()
    selected = next(
        (
            worktree
            for worktree in parse_worktrees(repo)
            if Path(worktree.path).resolve() == requested
        ),
        None,
    )
    if selected is None:
        raise WorkflowError(f"Registered worktree not found: {requested}")
    if selected.main:
        raise WorkflowError("The main worktree cannot be rescued as detached work.")
    if not selected.detached or selected.branch:
        raise WorkflowError(f"Worktree is already attached to a branch: {requested}")
    if selected.locked or selected.prunable or not requested.exists():
        raise WorkflowError(f"Worktree is not safely attachable: {requested}")
    ensure_no_operation(requested)
    if local_branch_exists(repo, args.branch):
        raise WorkflowError(f"Branch already exists locally: {args.branch}")
    check_name = run_git(
        repo, "check-ref-format", "--branch", args.branch, check=False
    )
    if check_name.returncode != 0:
        raise WorkflowError(f"Invalid branch name: {args.branch}")

    target = args.target or main_worktree_branch(repo)
    if not local_branch_exists(repo, target):
        raise WorkflowError(f"Target branch does not exist locally: {target}")
    if target == args.branch:
        raise WorkflowError("Rescue branch and maintenance target must be different.")

    actual_head = run_git(requested, "rev-parse", "HEAD^{commit}").stdout.strip()
    verify_expected_head(actual_head, args.expected_head, f"Worktree '{requested}'")
    changes = status_lines(requested)
    run_git(requested, "switch", "-c", args.branch)
    candidate = maintenance_branch_candidate(repo, target, args.branch)
    emit(
        {
            "action": "detached_rescued",
            "branch": args.branch,
            "candidate": candidate,
            "classification_status": "pending",
            "decision_terminal": False,
            "dirty_changes_preserved": changes,
            "head": actual_head,
            "next_action": {
                "action": "classify_rescued_branch",
                "candidate_id": candidate["candidate_id"],
                "target": target,
            },
            "target": target,
            "worktree": str(requested),
        }
    )


def parse_prune_expectation(value: str) -> tuple[str, str]:
    path, separator, head = value.rpartition("=")
    if not separator or not path or not head:
        raise argparse.ArgumentTypeError("expected PATH=HEAD")
    return str(Path(path).expanduser().resolve()), head


def command_prune_missing(repo: Path, args: argparse.Namespace) -> None:
    expected = dict(args.expect)
    if len(expected) != len(args.expect):
        raise WorkflowError("Duplicate --expect worktree paths are not allowed.")

    worktrees = parse_worktrees(repo)
    locked_missing = [
        worktree.path
        for worktree in worktrees
        if not worktree.main and not Path(worktree.path).exists() and worktree.locked
    ]
    eligible = {
        str(Path(worktree.path).resolve()): worktree.head or ""
        for worktree in worktrees
        if not worktree.main
        and not Path(worktree.path).exists()
        and not worktree.locked
    }
    if expected != eligible:
        raise WorkflowError(
            "Missing-worktree set changed or was not fully reviewed. "
            f"Expected {json.dumps(expected, sort_keys=True)}, found "
            f"{json.dumps(eligible, sort_keys=True)}"
        )
    if not eligible:
        raise WorkflowError("No eligible missing worktree registrations to prune.")

    branch_heads_before = local_branch_heads(repo)
    run_git(repo, "worktree", "prune", "--expire", "now")
    branch_heads_after = local_branch_heads(repo)
    if branch_heads_after != branch_heads_before:
        raise WorkflowError(
            "Local branch refs changed while pruning missing worktrees; "
            "review concurrent repository activity."
        )
    remaining_paths = {
        str(Path(worktree.path).resolve()) for worktree in parse_worktrees(repo)
    }
    failed = sorted(path for path in eligible if path in remaining_paths)
    if failed:
        raise WorkflowError(
            "Git did not prune the reviewed worktrees: " + ", ".join(failed)
        )
    emit(
        {
            "action": "missing_worktrees_pruned",
            "branch_refs_retained": True,
            "branch_refs_verified_unchanged": True,
            "locked_missing_retained": locked_missing,
            "pruned": [
                {"path": path, "head": head}
                for path, head in sorted(eligible.items())
            ],
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
    target_commit = run_git(repo, "rev-parse", f"{target}^{{commit}}").stdout.strip()
    verify_expected_head(commit, args.expected_head, f"Branch '{branch}'")
    verify_expected_head(
        target_commit, args.expected_target_head, f"Target '{target}'"
    )
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
    if not merged and not args.expected_target_head:
        raise WorkflowError(
            "Deleting an unmerged branch requires --expected-target-head from "
            "the evidence review."
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
        ensure_no_operation(requested)
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
            "target_commit": target_commit,
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

    maintenance_audit = commands.add_parser(
        "maintenance-audit",
        help="Inventory local branches, attached worktrees, and detached work",
    )
    maintenance_audit.add_argument("--target")
    maintenance_window = maintenance_audit.add_mutually_exclusive_group(required=True)
    maintenance_window.add_argument("--all", action="store_true")
    maintenance_window.add_argument("--recent-count", type=positive_int)
    maintenance_window.add_argument("--recent-days", type=positive_int)
    maintenance_audit.set_defaults(handler=command_maintenance_audit)

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
    merge.add_argument("--expected-source-head")
    merge.add_argument("--expected-target-head")
    merge.set_defaults(handler=command_merge)

    remove = commands.add_parser("remove", help="Safely remove a worktree")
    remove.add_argument("--worktree", required=True)
    remove.add_argument("--require-merged-into")
    remove.add_argument("--require-contained-in")
    remove.add_argument("--expected-head")
    remove.add_argument("--allow-uncontained-detached", action="store_true")
    remove.add_argument("--reason")
    remove.set_defaults(handler=command_remove)

    rescue_detached = commands.add_parser(
        "rescue-detached", help="Attach a detached worktree to a new local branch"
    )
    rescue_detached.add_argument("--worktree", required=True)
    rescue_detached.add_argument("--branch", required=True)
    rescue_detached.add_argument("--expected-head", required=True)
    rescue_detached.add_argument("--target")
    rescue_detached.set_defaults(handler=command_rescue_detached)

    prune_missing = commands.add_parser(
        "prune-missing", help="Prune an exact reviewed set of missing worktrees"
    )
    prune_missing.add_argument(
        "--expect", action="append", required=True, type=parse_prune_expectation
    )
    prune_missing.set_defaults(handler=command_prune_missing)

    branch_delete = commands.add_parser(
        "branch-delete", help="Safely delete one classified local branch"
    )
    branch_delete.add_argument("--branch", required=True)
    branch_delete.add_argument("--target")
    branch_delete.add_argument("--reason", required=True)
    branch_delete.add_argument("--expected-head")
    branch_delete.add_argument("--expected-target-head")
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
