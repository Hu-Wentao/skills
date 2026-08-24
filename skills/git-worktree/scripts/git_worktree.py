#!/usr/bin/env python3
"""Deterministic Git worktree lifecycle operations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Sequence, TextIO

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None  # type: ignore[assignment]


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
    auto_merge_block: dict[str, object]
    worktrees: tuple[dict[str, object], ...]


OPERATION_MARKERS = {
    "merge": ("MERGE_HEAD",),
    "rebase": ("rebase-merge", "rebase-apply"),
    "cherry_pick": ("CHERRY_PICK_HEAD",),
    "revert": ("REVERT_HEAD",),
    "bisect": ("BISECT_LOG",),
}

COMPLETION_REF_PREFIX = "refs/agents/completed/"
AUTO_MERGE_BLOCK_REF_PREFIX = "refs/agents/no-auto-merge/"
TEMPORARY_REF_PREFIX = "refs/agents/temporary/"
TEMPORARY_TARGET_REF_PREFIX = "refs/agents/temporary-target/"
MAINTENANCE_PLAN_SCHEMA_VERSION = 1
MUTATING_COMMANDS = frozenset(
    {
        "mark-complete",
        "owner-finish",
        "block-auto-merge",
        "unblock-auto-merge",
        "maintenance-run",
        "create",
        "merge",
        "remove",
        "rescue-detached",
        "prune-missing",
        "branch-delete",
    }
)


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


def git_common_dir(repo: Path) -> Path:
    value = run_git(repo, "rev-parse", "--git-common-dir").stdout.strip()
    path = Path(value)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def repository_lock_path(repo: Path) -> Path:
    return git_common_dir(repo) / "agents-worktree.lock"


def acquire_file_lock(handle: TextIO) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    import msvcrt  # pragma: no cover - Windows-only fallback

    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write("\0")
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as error:
        raise BlockingIOError from error


def release_file_lock(handle: TextIO) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    import msvcrt  # pragma: no cover - Windows-only fallback

    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def repository_lock(repo: Path, command: str) -> Iterator[Path]:
    lock_path = repository_lock_path(repo)
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+", encoding="utf-8") as handle:
        try:
            acquire_file_lock(handle)
        except BlockingIOError as error:
            raise WorkflowError(
                "Another Agent worktree mutation holds the repository lock: "
                f"{lock_path}"
            ) from error
        handle.seek(0)
        handle.truncate()
        handle.write(
            json.dumps(
                {"command": command, "pid": os.getpid()},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        handle.flush()
        try:
            yield lock_path
        finally:
            release_file_lock(handle)


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


def completion_ref_name(branch: str) -> str:
    return f"{COMPLETION_REF_PREFIX}{branch}"


def auto_merge_block_ref_name(branch: str) -> str:
    return f"{AUTO_MERGE_BLOCK_REF_PREFIX}{branch}"


def temporary_ref_name(branch: str) -> str:
    return f"{TEMPORARY_REF_PREFIX}{branch}"


def temporary_target_ref_name(branch: str) -> str:
    return f"{TEMPORARY_TARGET_REF_PREFIX}{branch}"


def ref_object_id(repo: Path, ref: str) -> str | None:
    result = run_git(repo, "rev-parse", "--verify", "--quiet", ref, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def exact_local_preservation_refs(repo: Path, head: str) -> list[str]:
    """Return ordinary local branches and tags anchored at an exact commit."""
    fields = (
        "%(refname)%00%(objecttype)%00%(objectname)%00"
        "%(*objecttype)%00%(*objectname)"
    )
    output = run_git(
        repo,
        "for-each-ref",
        f"--format={fields}",
        "refs/heads",
        "refs/tags",
    ).stdout
    refs: list[str] = []
    for line in output.splitlines():
        ref, object_type, object_id, peeled_type, peeled_id = line.split("\0")
        commit = (
            peeled_id
            if peeled_type == "commit"
            else object_id if object_type == "commit" else None
        )
        if commit == head:
            refs.append(ref)
    return sorted(refs)


def completion_evidence(
    repo: Path,
    branch: str | None,
    head: str,
    worktrees: Sequence[dict[str, object]],
) -> dict[str, object]:
    if branch is None:
        return {
            "ref": None,
            "head": None,
            "matches_head": False,
            "worktrees_clean": False,
            "status": "not_applicable",
        }
    ref = completion_ref_name(branch)
    completed_head = ref_object_id(repo, ref)
    matches_head = completed_head == head
    worktrees_clean = all(
        bool(item["exists"])
        and bool(item["inspectable"])
        and not bool(item["dirty"])
        and not item.get("operations")
        and not bool(item["locked"])
        and not bool(item["prunable"])
        for item in worktrees
    )
    return {
        "ref": ref,
        "head": completed_head,
        "matches_head": matches_head,
        "worktrees_clean": worktrees_clean,
        "status": (
            "current"
            if matches_head and worktrees_clean
            else "blocked"
            if matches_head
            else "stale"
            if completed_head is not None
            else "absent"
        ),
    }


def auto_merge_block_evidence(
    repo: Path, branch: str | None, head: str
) -> dict[str, object]:
    if branch is None:
        return {
            "present": False,
            "ref": None,
            "marked_head": None,
            "matches_head": False,
        }
    ref = auto_merge_block_ref_name(branch)
    marked_head = ref_object_id(repo, ref)
    return {
        "present": marked_head is not None,
        "ref": ref,
        "marked_head": marked_head,
        "matches_head": marked_head == head,
    }


def clear_auto_merge_block_ref(repo: Path, branch: str) -> bool:
    ref = auto_merge_block_ref_name(branch)
    object_id = ref_object_id(repo, ref)
    if object_id is None:
        return False
    return run_git(repo, "update-ref", "-d", ref, object_id, check=False).returncode == 0


def clear_completion_ref(repo: Path, branch: str) -> bool:
    ref = completion_ref_name(branch)
    object_id = ref_object_id(repo, ref)
    if object_id is None:
        return False
    return run_git(repo, "update-ref", "-d", ref, object_id, check=False).returncode == 0


def mark_temporary_worktree(
    repo: Path,
    *,
    branch: str,
    target: str,
    base_head: str,
) -> None:
    run_git(repo, "update-ref", temporary_ref_name(branch), base_head)
    run_git(
        repo,
        "symbolic-ref",
        temporary_target_ref_name(branch),
        f"refs/heads/{target}",
    )


def clear_temporary_worktree_refs(repo: Path, branch: str) -> bool:
    temporary_ref = temporary_ref_name(branch)
    target_ref = temporary_target_ref_name(branch)
    base_head = ref_object_id(repo, temporary_ref)
    target = run_git(repo, "symbolic-ref", "--quiet", target_ref, check=False)
    removed = False
    if base_head is not None:
        run_git(repo, "update-ref", "-d", temporary_ref, base_head)
        removed = True
    if target.returncode == 0:
        run_git(repo, "symbolic-ref", "--delete", target_ref)
        removed = True
    return removed


def worktree_ownership(repo: Path, branch: str | None) -> dict[str, object]:
    if branch is None:
        return {
            "kind": "not_applicable",
            "base_head": None,
            "target": None,
            "valid": True,
        }
    base_head = ref_object_id(repo, temporary_ref_name(branch))
    target_result = run_git(
        repo,
        "symbolic-ref",
        "--quiet",
        temporary_target_ref_name(branch),
        check=False,
    )
    target_ref = target_result.stdout.strip() if target_result.returncode == 0 else None
    if base_head is None and target_ref is None:
        return {
            "kind": "user_owned",
            "base_head": None,
            "target": None,
            "valid": True,
        }
    target = (
        target_ref.removeprefix("refs/heads/")
        if target_ref and target_ref.startswith("refs/heads/")
        else None
    )
    return {
        "kind": "agent_temporary",
        "base_head": base_head,
        "target": target,
        "valid": base_head is not None and target is not None,
    }


def completion_refs(repo: Path) -> list[dict[str, str]]:
    output = run_git(
        repo,
        "for-each-ref",
        "--format=%(refname)%00%(objectname)",
        COMPLETION_REF_PREFIX,
    ).stdout
    refs: list[dict[str, str]] = []
    for line in output.splitlines():
        ref, head = line.split("\0", 1)
        refs.append(
            {
                "branch": ref.removeprefix(COMPLETION_REF_PREFIX),
                "head": head,
                "ref": ref,
            }
        )
    return refs


def orphan_completion_refs(repo: Path) -> list[dict[str, str]]:
    return [
        item
        for item in completion_refs(repo)
        if not local_branch_exists(repo, item["branch"])
    ]


def prune_orphan_completion_refs(repo: Path) -> list[dict[str, str]]:
    removed: list[dict[str, str]] = []
    for item in orphan_completion_refs(repo):
        run_git(repo, "update-ref", "-d", item["ref"], item["head"])
        removed.append(item)
    return removed


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


def worktree_mutation_blockers(
    worktrees: Sequence[dict[str, object]],
) -> list[str]:
    blockers: list[str] = []
    for worktree in worktrees:
        path = str(worktree["path"])
        if not worktree["exists"]:
            blockers.append(f"{path}:missing")
        if not worktree["inspectable"]:
            blockers.append(f"{path}:uninspectable")
        if worktree["dirty"]:
            blockers.append(f"{path}:dirty")
        if worktree["operations"]:
            blockers.append(
                f"{path}:operation={','.join(worktree['operations'])}"
            )
        if worktree["locked"]:
            blockers.append(f"{path}:locked")
        if worktree["prunable"]:
            blockers.append(f"{path}:prunable")
    return blockers


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
                auto_merge_block=auto_merge_block_evidence(repo, branch, commit),
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
    completion: dict[str, object],
    auto_merge_block: dict[str, object],
    preservation_refs: Sequence[str] = (),
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
    detached_uncontained = bool(
        kind == "worktree"
        and worktrees[0].get("detached", False)
        and not contained
    )
    rescue_required = bool(detached_uncontained and not preservation_refs)
    retention_reasons: list[str] = []
    if dirty:
        retention_reasons.append("dirty_worktree_presumed_active")
    if operations:
        retention_reasons.append("active_git_operation")
    if locked:
        retention_reasons.append("locked_worktree")
    if missing:
        retention_reasons.append("missing_worktree")
    if uninspectable:
        retention_reasons.append("uninspectable_worktree")
    mutation_blocked = bool(retention_reasons)
    automatic_merge_blocked = bool(auto_merge_block["present"])
    if automatic_merge_blocked:
        retention_reasons.append("automatic_merge_blocked")

    if mutation_blocked:
        decision_scope = (
            "worktree_only_branch_ref_retained"
            if kind == "worktree"
            else "branch_and_committed_history"
        )
        possible = ["retain"]
    elif kind == "worktree":
        decision_scope = "worktree_only_branch_ref_retained"
        if contained or not worktrees[0].get("detached", False):
            possible = ["delete", "retain"]
        else:
            possible = ["merge", "delete", "retain"]
    else:
        decision_scope = "branch_and_committed_history"
        if contained or patch_equivalent:
            possible = ["delete", "retain"]
        else:
            possible = ["merge", "delete", "retain"]

    requirements: list[str] = []
    if dirty:
        requirements.append(
            "retain without mutation; a separate exact request must name this "
            "candidate before rescue, commit, merge, deletion, or removal"
        )
    if operations:
        requirements.append("finish or abort the active Git operation first")
    if locked:
        requirements.append("unlock only with explicit ownership evidence")
    if missing:
        requirements.append("prune only the missing registration; preserve branch refs")
    if uninspectable:
        requirements.append("repair or independently inspect the worktree before mutation")
    if rescue_required:
        if mutation_blocked:
            requirements.append(
                "stop maintenance and obtain a separate exact request before "
                "rescuing this active or unsafe detached worktree"
            )
        else:
            requirements.append(
                "create a rescue branch at the exact HEAD before any terminal "
                "maintenance decision"
            )
    if protected and kind == "branch":
        requirements.append("protected branch deletion requires separate authorization")
        possible = [item for item in possible if item != "delete"]
        if "retain" not in possible:
            possible.append("retain")
    if automatic_merge_blocked:
        requirements.append(
            "retain this branch and its attached worktrees unchanged during "
            "maintenance; clear the no-auto-merge ref before integration"
        )
        possible = ["retain"]

    return {
        "decision_scope": decision_scope,
        "possible_decisions": possible,
        "requirements": requirements,
        "dirty": dirty,
        "operations": operations,
        "locked": locked,
        "missing": missing,
        "uninspectable": uninspectable,
        "mutation_blocked": mutation_blocked,
        "automatic_merge_blocked": automatic_merge_blocked,
        "default_decision": (
            "retain" if mutation_blocked or automatic_merge_blocked else None
        ),
        "retention_reasons": retention_reasons,
        "owner_handoff_completed": completion["status"] == "current",
        "preservation_refs": list(preservation_refs),
        "rescue_required": rescue_required,
    }


def automatic_retention_decision(
    candidate: dict[str, object],
) -> dict[str, object] | None:
    evidence = candidate["decision_evidence"]
    if (
        evidence["default_decision"] != "retain"
        or evidence["possible_decisions"] != ["retain"]
    ):
        return None
    reasons = [str(item) for item in evidence["retention_reasons"]]
    return {
        "candidate_id": candidate["candidate_id"],
        "decision": "retain",
        "reason": "script-enforced retain: " + ", ".join(reasons),
        "automatic": True,
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
        completion = completion_evidence(repo, branch, head, snapshots)
        auto_merge_block = auto_merge_block_evidence(repo, branch, head)
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
                "completion": completion,
                "auto_merge_block": auto_merge_block,
                "decision_evidence": decision_evidence(
                    "branch",
                    relation,
                    snapshots,
                    protected,
                    completion,
                    auto_merge_block,
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
        preservation_refs = (
            exact_local_preservation_refs(repo, worktree.head)
            if worktree.detached and not relation["contained_in_target"]
            else []
        )
        completion = completion_evidence(
            repo, worktree.branch, worktree.head, snapshots
        )
        auto_merge_block = auto_merge_block_evidence(
            repo, worktree.branch, worktree.head
        )
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
                "completion": completion,
                "auto_merge_block": auto_merge_block,
                "decision_evidence": decision_evidence(
                    "worktree",
                    relation,
                    snapshots,
                    protected,
                    completion,
                    auto_merge_block,
                    preservation_refs,
                ),
            }
        )

    return sorted(
        items,
        key=lambda item: (int(item["committed_at_unix"]), str(item["candidate_id"])),
        reverse=True,
    )


def stable_json_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def maintenance_snapshot(
    repo: Path,
    target: str,
    candidates: Sequence[dict[str, object]] | None = None,
) -> dict[str, object]:
    items = (
        list(candidates)
        if candidates is not None
        else maintenance_candidates(repo, target)
    )
    target_head = run_git(repo, "rev-parse", f"{target}^{{commit}}").stdout.strip()
    target_worktrees = [
        worktree_snapshot(worktree)
        for worktree in affected_worktrees(repo, target)
    ]
    basis = {
        "target": {
            "branch": target,
            "head": target_head,
            "worktrees": target_worktrees,
        },
        "candidates": items,
        "orphan_completion_refs": orphan_completion_refs(repo),
    }
    return {**basis, "snapshot_id": stable_json_hash(basis)}


def candidate_stability_evidence(candidate: dict[str, object]) -> dict[str, object]:
    return {
        "candidate_id": candidate["candidate_id"],
        "kind": candidate["kind"],
        "branch": candidate.get("branch"),
        "head": candidate["head"],
        "worktrees": candidate["worktrees"],
        "completion": candidate["completion"],
        "auto_merge_block": candidate["auto_merge_block"],
        "preservation_refs": candidate["decision_evidence"]["preservation_refs"],
        "rescue_required": candidate["decision_evidence"]["rescue_required"],
    }


def verify_candidate_unchanged(
    expected: dict[str, object], actual: dict[str, object]
) -> None:
    if candidate_stability_evidence(expected) != candidate_stability_evidence(actual):
        raise WorkflowError(
            f"Candidate changed since audit: {expected['candidate_id']}"
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


def emit_command_result(
    args: argparse.Namespace, payload: dict[str, object]
) -> dict[str, object]:
    if not getattr(args, "suppress_emit", False):
        emit(payload)
    return payload


def verify_expected_head(actual: str, expected: str | None, label: str) -> None:
    if expected and actual != expected:
        raise WorkflowError(
            f"{label} HEAD changed since audit: expected {expected}, found {actual}"
        )


def command_list(repo: Path, _args: argparse.Namespace) -> None:
    emit({"worktrees": [asdict(worktree) for worktree in parse_worktrees(repo)]})


def owner_status_payload(repo: Path) -> dict[str, object]:
    current_path = repo.resolve()
    worktree = next(
        (
            item
            for item in parse_worktrees(repo)
            if Path(item.path).resolve() == current_path
        ),
        None,
    )
    if worktree is None:
        raise WorkflowError(
            f"Current repository path is not a registered worktree: {current_path}"
        )
    snapshot = worktree_snapshot(worktree)
    blockers: list[str] = []
    if worktree.main:
        blockers.append("main_worktree")
    if worktree.detached or not worktree.branch:
        blockers.append("detached_head")
    blockers.extend(worktree_mutation_blockers([snapshot]))
    completion = completion_evidence(
        repo,
        None if worktree.main or worktree.detached else worktree.branch,
        worktree.head or "",
        [snapshot],
    )
    auto_merge_block = auto_merge_block_evidence(
        repo,
        None if worktree.main or worktree.detached else worktree.branch,
        worktree.head or "",
    )
    ownership = worktree_ownership(
        repo,
        None if worktree.main or worktree.detached else worktree.branch,
    )
    delivery: dict[str, object] = {
        "status": "not_applicable",
        "target": ownership["target"],
        "target_head": None,
        "source_contained": False,
    }
    if ownership["kind"] == "agent_temporary":
        if not ownership["valid"]:
            blockers.append("invalid_temporary_ownership_metadata")
            delivery["status"] = "ownership_metadata_invalid"
        else:
            target = str(ownership["target"])
            if not local_branch_exists(repo, target):
                blockers.append(f"delivery_target_missing:{target}")
                delivery["status"] = "target_missing"
            else:
                target_head = run_git(
                    repo, "rev-parse", f"{target}^{{commit}}"
                ).stdout.strip()
                contained = (
                    run_git(
                        repo,
                        "merge-base",
                        "--is-ancestor",
                        worktree.head or "",
                        target,
                        check=False,
                    ).returncode
                    == 0
                )
                delivery.update(
                    {
                        "status": (
                            "completion_required"
                            if completion["status"] != "current"
                            else "target_validation_and_cleanup_required"
                            if contained
                            else "automatic_merge_blocked"
                            if auto_merge_block["present"]
                            else "integration_required"
                        ),
                        "target_head": target_head,
                        "source_contained": contained,
                    }
                )
    if blockers:
        next_action = "resolve_or_report_blockers"
    elif ownership["kind"] == "agent_temporary":
        next_action = {
            "completion_required": "mark_complete_after_semantic_completion",
            "integration_required": "merge_to_recorded_target",
            "target_validation_and_cleanup_required": (
                "validate_target_then_remove_temporary_worktree"
            ),
            "automatic_merge_blocked": "clear_auto_merge_block_or_handoff",
        }[str(delivery["status"])]
    elif completion["status"] != "current":
        next_action = "mark_complete_after_semantic_completion"
    else:
        next_action = "handoff_completed_owner_retains_worktree"
    return {
        "action": "owner_status_inspected",
        "git_common_dir": str(git_common_dir(repo)),
        "worktree": snapshot,
        "completion": completion,
        "auto_merge_block": auto_merge_block,
        "ownership": ownership,
        "delivery": delivery,
        "completion_eligible": not blockers,
        "completion_blockers": blockers,
        "next_action": next_action,
    }


def command_owner_status(repo: Path, _args: argparse.Namespace) -> None:
    emit(owner_status_payload(repo))


def command_mark_complete(
    repo: Path, args: argparse.Namespace
) -> dict[str, object]:
    requested = Path(args.repo).expanduser().resolve()
    branch = args.branch or current_branch(requested)
    if not local_branch_exists(repo, branch):
        raise WorkflowError(f"Local branch does not exist: {branch}")
    worktrees = affected_worktrees(repo, branch)
    if len(worktrees) != 1:
        raise WorkflowError(
            f"Branch '{branch}' must be checked out in exactly one registered worktree."
        )
    if worktrees[0].main:
        raise WorkflowError("The main worktree branch cannot be marked as task-complete.")
    ensure_affected_worktrees_clean(repo, branch)
    head = run_git(repo, "rev-parse", f"{branch}^{{commit}}").stdout.strip()
    verify_expected_head(head, args.expected_head, f"Branch '{branch}'")
    ref = completion_ref_name(branch)
    previous = ref_object_id(repo, ref)
    null_object_id = "0" * len(head)
    run_git(repo, "update-ref", ref, head, previous or null_object_id)
    return emit_command_result(
        args,
        {
            "action": "branch_marked_complete",
            "branch": branch,
            "completion_ref": ref,
            "head": head,
            "previous_completion_head": previous,
            "remote_refs_untouched": True,
        },
    )


def command_owner_finish(repo: Path, args: argparse.Namespace) -> None:
    """Advance one owned task through the next safe scripted phase."""
    status = owner_status_payload(repo)
    blockers = [str(item) for item in status["completion_blockers"]]
    if blockers:
        raise WorkflowError(
            "Owned worktree is not safe to finish: " + ", ".join(blockers)
        )

    worktree = status["worktree"]
    branch = str(worktree["branch"])
    source_head = str(worktree["head"])
    if args.validated_source_head:
        verify_expected_head(
            source_head,
            args.validated_source_head,
            f"Validated source '{branch}'",
        )

    completion_updated = False
    completion = status["completion"]
    if completion["status"] != "current":
        if not args.validated_source_head:
            raise WorkflowError(
                "Creating the completion handoff requires "
                "--validated-source-head for the exact source commit that passed "
                "validation."
            )
        command_mark_complete(
            repo,
            argparse.Namespace(
                repo=str(repo),
                branch=branch,
                expected_head=args.validated_source_head,
                suppress_emit=True,
            ),
        )
        completion_updated = True
        status = owner_status_payload(repo)
        completion = status["completion"]

    ownership = status["ownership"]
    completion_ref = completion["ref"]
    if ownership["kind"] == "user_owned":
        if args.validated_target_head:
            raise WorkflowError(
                "--validated-target-head is only valid for an agent-temporary "
                "worktree delivery."
            )
        emit(
            {
                "action": "owner_finish",
                "status": "handoff_completed",
                "source": {
                    "branch": branch,
                    "head": source_head,
                    "worktree": worktree["path"],
                },
                "completion_ref": completion_ref,
                "completion_updated": completion_updated,
                "ownership": "user_owned",
                "next_action": "handoff_completed_owner_retains_worktree",
                "remote_refs_untouched": True,
            }
        )
        return

    if ownership["kind"] != "agent_temporary" or not ownership["valid"]:
        raise WorkflowError("Owned worktree has invalid temporary ownership metadata.")

    target = str(ownership["target"])
    target_worktrees = affected_worktrees(repo, target)
    if len(target_worktrees) != 1:
        raise WorkflowError(
            f"Recorded target branch '{target}' must be checked out in exactly one "
            "registered worktree."
        )
    target_worktree = target_worktrees[0]
    target_path = Path(target_worktree.path)
    ensure_affected_worktrees_clean(repo, branch, target)
    target_head = run_git(repo, "rev-parse", f"{target}^{{commit}}").stdout.strip()
    source_contained = (
        run_git(
            repo,
            "merge-base",
            "--is-ancestor",
            source_head,
            target,
            check=False,
        ).returncode
        == 0
    )

    if not source_contained:
        if args.validated_target_head:
            raise WorkflowError(
                "The source is not integrated yet; validate the target HEAD returned "
                "after this command merges it."
            )
        merge = command_merge(
            target_path,
            argparse.Namespace(
                source=branch,
                target=target,
                expected_source_head=source_head,
                expected_target_head=target_head,
                suppress_emit=True,
            ),
        )
        target_head = str(merge["commit"])
        emit(
            {
                "action": "owner_finish",
                "status": "target_validation_required",
                "source": {
                    "branch": branch,
                    "head": source_head,
                    "worktree": worktree["path"],
                },
                "target": {
                    "branch": target,
                    "head": target_head,
                    "worktree": str(target_path),
                },
                "merge": merge,
                "completion_ref": completion_ref,
                "completion_updated": completion_updated,
                "ownership": "agent_temporary",
                "next_action": (
                    "validate_target_then_rerun_owner_finish_with_exact_head"
                ),
                "remote_refs_untouched": True,
            }
        )
        return

    if not args.validated_target_head:
        emit(
            {
                "action": "owner_finish",
                "status": "target_validation_required",
                "source": {
                    "branch": branch,
                    "head": source_head,
                    "worktree": worktree["path"],
                },
                "target": {
                    "branch": target,
                    "head": target_head,
                    "worktree": str(target_path),
                },
                "merge": None,
                "completion_ref": completion_ref,
                "completion_updated": completion_updated,
                "ownership": "agent_temporary",
                "next_action": (
                    "validate_target_then_rerun_owner_finish_with_exact_head"
                ),
                "remote_refs_untouched": True,
            }
        )
        return

    verify_expected_head(
        target_head,
        args.validated_target_head,
        f"Validated target '{target}'",
    )
    removal = command_remove(
        target_path,
        argparse.Namespace(
            worktree=str(worktree["path"]),
            require_merged_into=target,
            require_contained_in=None,
            expected_head=source_head,
            allow_uncontained_detached=False,
            reason="owner-finish after exact target validation",
            suppress_emit=True,
        ),
    )
    emit(
        {
            "action": "owner_finish",
            "status": "completed",
            "source": {
                "branch": branch,
                "head": source_head,
                "worktree": worktree["path"],
            },
            "target": {
                "branch": target,
                "head": target_head,
                "worktree": str(target_path),
            },
            "cleanup": removal,
            "completion_ref": completion_ref,
            "completion_updated": completion_updated,
            "ownership": "agent_temporary",
            "next_action": "report_completed_delivery",
            "remote_refs_untouched": True,
        }
    )


def command_block_auto_merge(repo: Path, args: argparse.Namespace) -> None:
    branch = args.branch
    if not local_branch_exists(repo, branch):
        raise WorkflowError(f"Local branch does not exist: {branch}")
    head = run_git(repo, "rev-parse", f"{branch}^{{commit}}").stdout.strip()
    verify_expected_head(head, args.expected_head, f"Branch '{branch}'")
    ref = auto_merge_block_ref_name(branch)
    previous = ref_object_id(repo, ref)
    null_object_id = "0" * len(head)
    run_git(repo, "update-ref", ref, head, previous or null_object_id)
    emit(
        {
            "action": "automatic_merge_blocked",
            "branch": branch,
            "head": head,
            "no_auto_merge_ref": ref,
            "previous_marked_head": previous,
            "remote_refs_untouched": True,
        }
    )


def command_unblock_auto_merge(repo: Path, args: argparse.Namespace) -> None:
    branch = args.branch
    ref = auto_merge_block_ref_name(branch)
    marked_head = ref_object_id(repo, ref)
    if marked_head is None:
        raise WorkflowError(f"Automatic merge is not blocked for branch '{branch}'.")
    if marked_head != args.expected_marker_head:
        raise WorkflowError(
            f"No-auto-merge marker changed: expected {args.expected_marker_head}, "
            f"found {marked_head}."
        )
    run_git(repo, "update-ref", "-d", ref, marked_head)
    emit(
        {
            "action": "automatic_merge_unblocked",
            "branch": branch,
            "marked_head": marked_head,
            "no_auto_merge_ref": ref,
            "remote_refs_untouched": True,
        }
    )


def command_maintenance_audit(repo: Path, args: argparse.Namespace) -> None:
    target = args.target or current_branch(repo)
    items = maintenance_candidates(repo, target)
    snapshot = maintenance_snapshot(repo, target, items)
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

    retained_worktrees: dict[str, dict[str, object]] = {}
    rescue_required_worktrees = [
        {
            "candidate_id": candidate["candidate_id"],
            "head": candidate["head"],
            "path": candidate["worktrees"][0]["path"],
            "dirty": candidate["decision_evidence"]["dirty"],
            "operations": candidate["decision_evidence"]["operations"],
            "preservation_refs": candidate["decision_evidence"][
                "preservation_refs"
            ],
            "requirements": candidate["decision_evidence"]["requirements"],
        }
        for candidate in selected
        if candidate["decision_evidence"]["rescue_required"]
    ]
    for candidate in selected:
        evidence = candidate["decision_evidence"]
        if (
            evidence["default_decision"] != "retain"
            or not evidence["mutation_blocked"]
        ):
            continue
        for worktree in candidate["worktrees"]:
            retained_worktrees[str(worktree["path"])] = {
                "path": worktree["path"],
                "branch": worktree["branch"],
                "detached": worktree["detached"],
                "head": worktree["head"],
                "dirty": worktree["dirty"],
                "changes": worktree["changes"],
                "operations": worktree["operations"],
                "locked": worktree["locked"],
                "exists": worktree["exists"],
                "inspectable": worktree["inspectable"],
                "completion": candidate["completion"],
                "retention_reasons": evidence["retention_reasons"],
                "mutations_skipped": [
                    "modify",
                    "stage",
                    "commit",
                    "switch",
                    "merge",
                    "delete",
                    "remove",
                    "rescue",
                ],
            }
    automatic_retention = [
        decision
        for candidate in selected
        if (decision := automatic_retention_decision(candidate)) is not None
    ]
    automatic_ids = {
        str(decision["candidate_id"]) for decision in automatic_retention
    }
    review_required = [
        {
            "candidate_id": candidate["candidate_id"],
            "head": candidate["head"],
            "possible_decisions": candidate["decision_evidence"][
                "possible_decisions"
            ],
            "requirements": candidate["decision_evidence"]["requirements"],
        }
        for candidate in selected
        if str(candidate["candidate_id"]) not in automatic_ids
    ]
    emit(
        {
            "action": "maintenance_audit",
            "scope": "local_branches_and_worktrees",
            "plan_schema_version": MAINTENANCE_PLAN_SCHEMA_VERSION,
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_scope": "all_candidates",
            "maintenance_run_eligible": bool(
                args.all and not rescue_required_worktrees
            ),
            "target": snapshot["target"],
            "selection": selection,
            "total_candidates": len(items),
            "selected_candidates": len(selected),
            "candidates": selected,
            "decision_plan_template": (
                {
                    "schema_version": MAINTENANCE_PLAN_SCHEMA_VERSION,
                    "snapshot_id": snapshot["snapshot_id"],
                    "target": snapshot["target"]["branch"],
                    "decisions": [],
                }
                if args.all
                else None
            ),
            "automatic_retention_decisions": automatic_retention,
            "review_required": review_required,
            "owner_handoff_missing": [
                {
                    "branch": candidate["branch"],
                    "candidate_id": candidate["candidate_id"],
                    "head": candidate["head"],
                    "status": candidate["completion"]["status"],
                }
                for candidate in selected
                if candidate["kind"] == "branch"
                and candidate["completion"]["status"] != "current"
            ],
            "orphan_completion_refs": snapshot["orphan_completion_refs"],
            "rescue_required_worktrees": rescue_required_worktrees,
            "retained_no_auto_merge_branches": [
                {
                    "branch": candidate["branch"],
                    "candidate_id": candidate["candidate_id"],
                    "head": candidate["head"],
                    "ref": candidate["auto_merge_block"]["ref"],
                }
                for candidate in selected
                if candidate["kind"] == "branch"
                and candidate["auto_merge_block"]["present"]
            ],
            "retained_active_or_dirty_worktrees": sorted(
                retained_worktrees.values(), key=lambda item: str(item["path"])
            ),
        }
    )


def read_maintenance_plan(value: str) -> dict[str, object]:
    if value == "-":
        raw = sys.stdin.read()
        source = "stdin"
    else:
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            raise WorkflowError(f"Maintenance plan does not exist: {path}")
        raw = path.read_text(encoding="utf-8")
        source = str(path)
    if not raw.strip():
        raise WorkflowError(f"Maintenance plan from {source} is empty.")
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as error:
        raise WorkflowError(
            f"Maintenance plan from {source} is not valid JSON: {error}"
        ) from error
    if not isinstance(plan, dict):
        raise WorkflowError("Maintenance plan must be a JSON object.")
    return plan


def validate_maintenance_plan(
    plan: dict[str, object], snapshot: dict[str, object]
) -> dict[str, dict[str, object]]:
    if plan.get("schema_version") != MAINTENANCE_PLAN_SCHEMA_VERSION:
        raise WorkflowError(
            "Maintenance plan schema_version must be "
            f"{MAINTENANCE_PLAN_SCHEMA_VERSION}."
        )
    target = snapshot["target"]
    if plan.get("target") != target["branch"]:
        raise WorkflowError(
            f"Maintenance plan target must be '{target['branch']}'."
        )
    if plan.get("snapshot_id") != snapshot["snapshot_id"]:
        raise WorkflowError(
            "Maintenance snapshot changed; run maintenance-audit again and "
            "rebuild the decision plan."
        )
    raw_decisions = plan.get("decisions")
    if not isinstance(raw_decisions, list):
        raise WorkflowError("Maintenance plan decisions must be a JSON array.")

    candidates = {
        str(candidate["candidate_id"]): candidate
        for candidate in snapshot["candidates"]
    }
    rescue_required = sorted(
        candidate_id
        for candidate_id, candidate in candidates.items()
        if candidate["decision_evidence"]["rescue_required"]
    )
    if rescue_required:
        raise WorkflowError(
            "Maintenance plan is blocked by unrescued detached worktree(s): "
            + ", ".join(rescue_required)
            + ". Run rescue-detached for each exact candidate, re-audit, then "
            "build a terminal decision plan. A retain decision or internal "
            "snapshot ref does not satisfy rescue."
        )
    decisions: dict[str, dict[str, object]] = {}
    for raw in raw_decisions:
        if not isinstance(raw, dict):
            raise WorkflowError("Every maintenance decision must be a JSON object.")
        candidate_id = raw.get("candidate_id")
        decision = raw.get("decision")
        reason = raw.get("reason")
        if not isinstance(candidate_id, str) or candidate_id not in candidates:
            raise WorkflowError(f"Unknown maintenance candidate: {candidate_id}")
        if candidate_id in decisions:
            raise WorkflowError(f"Duplicate maintenance decision: {candidate_id}")
        if decision not in {"merge", "delete", "retain"}:
            raise WorkflowError(
                f"Decision for {candidate_id} must be merge, delete, or retain."
            )
        if not isinstance(reason, str) or not reason.strip():
            raise WorkflowError(
                f"Decision for {candidate_id} requires a non-empty reason."
            )
        candidate = candidates[candidate_id]
        if (
            decision == "merge"
            and candidate["kind"] == "branch"
            and candidate["auto_merge_block"]["present"]
        ):
            raise WorkflowError(
                f"Automatic merge is blocked for {candidate_id} by "
                f"{candidate['auto_merge_block']['ref']}."
            )
        possible = candidate["decision_evidence"]["possible_decisions"]
        if decision not in possible:
            raise WorkflowError(
                f"Decision '{decision}' is not allowed for {candidate_id}; "
                f"allowed: {', '.join(possible)}."
            )
        if decision == "merge" and candidate["kind"] == "worktree":
            raise WorkflowError(
                f"Rescue detached worktree {candidate_id} before planning its merge."
            )
        if (
            decision == "delete"
            and candidate["kind"] == "branch"
            and candidate["protected"]
            and raw.get("allow_protected") is not True
        ):
            raise WorkflowError(
                f"Protected branch {candidate_id} requires allow_protected=true."
            )
        if (
            decision == "delete"
            and candidate["kind"] == "worktree"
            and candidate.get("detached")
            and not candidate["relation"]["contained_in_target"]
            and raw.get("allow_uncontained_detached") is not True
        ):
            raise WorkflowError(
                f"Uncontained detached worktree {candidate_id} requires "
                "allow_uncontained_detached=true."
            )
        decisions[candidate_id] = raw

    missing = sorted(set(candidates) - set(decisions))
    for candidate_id in missing:
        automatic = automatic_retention_decision(candidates[candidate_id])
        if automatic is not None:
            decisions[candidate_id] = automatic
    missing = sorted(set(candidates) - set(decisions))
    if missing:
        raise WorkflowError(
            "Maintenance plan must classify every review-required candidate; missing: "
            + ", ".join(missing)
        )

    will_mutate = any(
        decision["decision"] != "retain" for decision in decisions.values()
    ) or bool(snapshot["orphan_completion_refs"])
    target_blockers = worktree_mutation_blockers(snapshot["target"]["worktrees"])
    if will_mutate and target_blockers:
        raise WorkflowError(
            "Target worktree is not safe for maintenance mutations: "
            + ", ".join(target_blockers)
        )

    branch_decisions = {
        str(candidates[candidate_id]["branch"]): decision
        for candidate_id, decision in decisions.items()
        if candidates[candidate_id]["kind"] == "branch"
    }
    for candidate_id, decision in decisions.items():
        candidate = candidates[candidate_id]
        if candidate["kind"] != "worktree" or not candidate.get("branch"):
            continue
        branch_decision = branch_decisions.get(str(candidate["branch"]))
        if branch_decision is None:
            continue
        if branch_decision["decision"] == "merge" and decision["decision"] == "delete":
            raise WorkflowError(
                "Do not delete a source worktree in the same run that merges its "
                f"branch: {candidate_id}. Validate the merge, then audit again."
            )
        if branch_decision["decision"] == "delete" and decision["decision"] == "retain":
            raise WorkflowError(
                f"Cannot retain {candidate_id} while deleting its branch."
            )
    return decisions


def current_candidate(
    repo: Path, target: str, candidate_id: str
) -> dict[str, object] | None:
    return next(
        (
            candidate
            for candidate in maintenance_candidates(repo, target)
            if candidate["candidate_id"] == candidate_id
        ),
        None,
    )


def command_maintenance_run(repo: Path, args: argparse.Namespace) -> None:
    plan = read_maintenance_plan(args.plan)
    planned_target = plan.get("target")
    if not isinstance(planned_target, str) or not planned_target:
        raise WorkflowError("Maintenance plan requires a target branch.")
    if not local_branch_exists(repo, planned_target):
        raise WorkflowError(f"Target branch does not exist locally: {planned_target}")
    if current_branch(repo) != planned_target:
        raise WorkflowError(
            f"Run maintenance-run from the target worktree '{planned_target}'."
        )

    initial_snapshot = maintenance_snapshot(repo, planned_target)
    decisions = validate_maintenance_plan(plan, initial_snapshot)
    initial_candidates = {
        str(candidate["candidate_id"]): candidate
        for candidate in initial_snapshot["candidates"]
    }
    results: list[dict[str, object]] = []
    expected_target_head = str(initial_snapshot["target"]["head"])

    def ensure_target_unchanged() -> None:
        actual = run_git(
            repo, "rev-parse", f"{planned_target}^{{commit}}"
        ).stdout.strip()
        verify_expected_head(actual, expected_target_head, f"Target '{planned_target}'")

    def record(
        candidate_id: str,
        operation: dict[str, object] | None = None,
        *,
        outcome: str | None = None,
    ) -> None:
        decision = decisions[candidate_id]
        item: dict[str, object] = {
            "candidate_id": candidate_id,
            "decision": decision["decision"],
            "reason": decision["reason"],
            "decision_source": (
                "automatic" if decision.get("automatic") is True else "provided"
            ),
        }
        if operation is not None:
            item["operation"] = operation
        if outcome is not None:
            item["outcome"] = outcome
        results.append(item)

    try:
        branch_merges = sorted(
            candidate_id
            for candidate_id, decision in decisions.items()
            if initial_candidates[candidate_id]["kind"] == "branch"
            and decision["decision"] == "merge"
        )
        for candidate_id in branch_merges:
            expected = initial_candidates[candidate_id]
            actual = current_candidate(repo, planned_target, candidate_id)
            if actual is None:
                raise WorkflowError(f"Candidate disappeared since audit: {candidate_id}")
            verify_candidate_unchanged(expected, actual)
            ensure_target_unchanged()
            operation = command_merge(
                repo,
                argparse.Namespace(
                    source=actual["branch"],
                    target=planned_target,
                    expected_source_head=expected["head"],
                    expected_target_head=expected_target_head,
                    suppress_emit=True,
                ),
            )
            expected_target_head = str(operation["commit"])
            record(candidate_id, operation)

        branch_deletes = sorted(
            candidate_id
            for candidate_id, decision in decisions.items()
            if initial_candidates[candidate_id]["kind"] == "branch"
            and decision["decision"] == "delete"
        )
        deleted_worktrees: set[str] = set()
        for candidate_id in branch_deletes:
            expected = initial_candidates[candidate_id]
            actual = current_candidate(repo, planned_target, candidate_id)
            if actual is None:
                raise WorkflowError(f"Candidate disappeared since audit: {candidate_id}")
            verify_candidate_unchanged(expected, actual)
            ensure_target_unchanged()
            decision = decisions[candidate_id]
            operation = command_branch_delete(
                repo,
                argparse.Namespace(
                    branch=actual["branch"],
                    target=planned_target,
                    reason=decision["reason"],
                    expected_head=expected["head"],
                    expected_target_head=expected_target_head,
                    allow_unmerged=not bool(
                        actual["relation"]["contained_in_target"]
                    ),
                    allow_protected=decision.get("allow_protected") is True,
                    remove_worktree=bool(actual["worktrees"]),
                    suppress_emit=True,
                ),
            )
            deleted_worktrees.update(str(path) for path in operation["removed_worktrees"])
            record(candidate_id, operation)

        worktree_deletes = sorted(
            candidate_id
            for candidate_id, decision in decisions.items()
            if initial_candidates[candidate_id]["kind"] == "worktree"
            and decision["decision"] == "delete"
        )
        for candidate_id in worktree_deletes:
            expected = initial_candidates[candidate_id]
            path = str(expected["worktrees"][0]["path"])
            if path in deleted_worktrees:
                record(candidate_id, outcome="removed_with_branch_delete")
                continue
            actual = current_candidate(repo, planned_target, candidate_id)
            if actual is None:
                raise WorkflowError(f"Candidate disappeared since audit: {candidate_id}")
            verify_candidate_unchanged(expected, actual)
            ensure_target_unchanged()
            decision = decisions[candidate_id]
            detached = bool(actual.get("detached"))
            contained = bool(actual["relation"]["contained_in_target"])
            operation = command_remove(
                repo,
                argparse.Namespace(
                    worktree=path,
                    require_merged_into=(
                        planned_target if not detached and contained else None
                    ),
                    require_contained_in=(
                        planned_target if detached and contained else None
                    ),
                    expected_head=expected["head"],
                    allow_uncontained_detached=(
                        decision.get("allow_uncontained_detached") is True
                    ),
                    reason=decision["reason"],
                    suppress_emit=True,
                ),
            )
            record(candidate_id, operation)

        for candidate_id, decision in sorted(decisions.items()):
            if decision["decision"] == "retain":
                record(candidate_id, outcome="retained_without_mutation")

        removed_orphan_refs = prune_orphan_completion_refs(repo)
        final_snapshot = maintenance_snapshot(repo, planned_target)
        emit(
            {
                "action": "maintenance_run",
                "status": "completed",
                "initial_snapshot_id": initial_snapshot["snapshot_id"],
                "final_snapshot_id": final_snapshot["snapshot_id"],
                "target": final_snapshot["target"],
                "terminal_decisions": results,
                "removed_orphan_completion_refs": removed_orphan_refs,
                "retained_no_auto_merge_branches": [
                    {
                        "branch": initial_candidates[candidate_id]["branch"],
                        "candidate_id": candidate_id,
                        "head": initial_candidates[candidate_id]["head"],
                        "ref": initial_candidates[candidate_id][
                            "auto_merge_block"
                        ]["ref"],
                    }
                    for candidate_id, decision in sorted(decisions.items())
                    if initial_candidates[candidate_id]["kind"] == "branch"
                    and initial_candidates[candidate_id]["auto_merge_block"][
                        "present"
                    ]
                    and decision["decision"] == "retain"
                ],
                "remaining_candidates": [
                    candidate["candidate_id"]
                    for candidate in final_snapshot["candidates"]
                ],
                "remote_refs_untouched": True,
                "repository_lock": str(repository_lock_path(repo)),
            }
        )
    except WorkflowError as error:
        target_head = run_git(
            repo, "rev-parse", f"{planned_target}^{{commit}}"
        ).stdout.strip()
        emit(
            {
                "action": "maintenance_run",
                "status": "paused",
                "error": str(error),
                "initial_snapshot_id": initial_snapshot["snapshot_id"],
                "completed_decisions": results,
                "target_state": {
                    "branch": planned_target,
                    "head": target_head,
                    "dirty": bool(status_lines(repo)),
                    "operations": list(operation_state(repo)),
                },
                "remote_refs_untouched": True,
                "repository_lock": str(repository_lock_path(repo)),
            }
        )
        raise


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
    try:
        destination.relative_to(repo.resolve())
    except ValueError:
        pass
    else:
        raise WorkflowError(
            "Worktree path must be outside the repository root: "
            f"{destination}. Omit --path to use the managed sibling path."
        )
    if destination.exists():
        raise WorkflowError(f"Worktree path already exists: {destination}")

    base_head = run_git(repo, "rev-parse", f"{base}^{{commit}}").stdout.strip()
    run_git(repo, "worktree", "add", "-b", branch, str(destination), base_head)
    if args.temporary:
        mark_temporary_worktree(
            repo,
            branch=branch,
            target=base,
            base_head=base_head,
        )
    emit(
        {
            "action": "created",
            "base": base,
            "base_head": base_head,
            "branch": branch,
            "ownership": "agent_temporary" if args.temporary else "user_owned",
            "target": base if args.temporary else None,
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


def command_merge(repo: Path, args: argparse.Namespace) -> dict[str, object]:
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
    auto_merge_block = auto_merge_block_evidence(repo, source, source_head)
    if auto_merge_block["present"]:
        raise WorkflowError(
            f"Automatic merge is blocked for branch '{source}' by "
            f"{auto_merge_block['ref']}; run unblock-auto-merge first."
        )
    source_ownership = worktree_ownership(repo, source)
    if source_ownership["kind"] == "agent_temporary":
        if not source_ownership["valid"]:
            raise WorkflowError(
                f"Agent-temporary branch '{source}' has invalid ownership metadata."
            )
        if source_ownership["target"] != target:
            raise WorkflowError(
                f"Agent-temporary branch '{source}' must be delivered to recorded "
                f"target '{source_ownership['target']}', not '{target}'."
            )
        if not args.expected_source_head or not args.expected_target_head:
            raise WorkflowError(
                "Agent-temporary delivery requires --expected-source-head and "
                "--expected-target-head from the latest owner-status result."
            )
        source_worktrees = [
            worktree_snapshot(item) for item in affected_worktrees(repo, source)
        ]
        completion = completion_evidence(
            repo,
            source,
            source_head,
            source_worktrees,
        )
        if completion["status"] != "current":
            raise WorkflowError(
                f"Agent-temporary branch '{source}' must have a current completion "
                "ref before delivery."
            )
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

    return emit_command_result(
        args,
        {
            "action": "merged",
            "commit": run_git(repo, "rev-parse", "HEAD").stdout.strip(),
            "source": source,
            "target": target,
        },
    )


def command_remove(repo: Path, args: argparse.Namespace) -> dict[str, object]:
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
    ownership = worktree_ownership(repo, selected.branch)
    if ownership["kind"] == "agent_temporary":
        if not ownership["valid"]:
            raise WorkflowError(
                f"Agent-temporary worktree has invalid ownership metadata: {requested}"
            )
        if args.require_merged_into != ownership["target"]:
            raise WorkflowError(
                "Agent-temporary cleanup requires --require-merged-into "
                f"{ownership['target']}."
            )
        if not args.expected_head:
            raise WorkflowError(
                "Agent-temporary cleanup requires --expected-head from the latest "
                "owner-status result."
            )
        completion = completion_evidence(
            repo,
            selected.branch,
            actual_head,
            [worktree_snapshot(selected)],
        )
        if completion["status"] != "current":
            raise WorkflowError(
                "Agent-temporary cleanup requires a current completion ref."
            )
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
    temporary_refs_removed = (
        clear_temporary_worktree_refs(repo, selected.branch)
        if selected.branch
        else False
    )
    return emit_command_result(
        args,
        {
            "action": "removed",
            "branch": selected.branch,
            "branch_retained": selected.branch is not None,
            "head": actual_head,
            "reason": args.reason,
            "temporary_ownership_removed": temporary_refs_removed,
            "worktree": str(requested),
        },
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


def command_branch_delete(repo: Path, args: argparse.Namespace) -> dict[str, object]:
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
    completion_ref_removed = clear_completion_ref(repo, branch)
    auto_merge_block_ref_removed = clear_auto_merge_block_ref(repo, branch)
    temporary_refs_removed = clear_temporary_worktree_refs(repo, branch)
    return emit_command_result(
        args,
        {
            "action": "branch_deleted",
            "branch": branch,
            "commit": commit,
            "completion_ref_removed": completion_ref_removed,
            "no_auto_merge_ref_removed": auto_merge_block_ref_removed,
            "temporary_ownership_removed": temporary_refs_removed,
            "merged_into_target": merged,
            "reason": args.reason,
            "remote_branch_untouched": True,
            "removed_worktrees": removed_worktrees,
            "target": target,
            "target_commit": target_commit,
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", default=os.getcwd(), help="Repository or worktree path (default: cwd)"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    list_parser = commands.add_parser("list", help="List registered worktrees")
    list_parser.set_defaults(handler=command_list)

    owner_status = commands.add_parser(
        "owner-status",
        help="Inspect the current worktree's owner-completion eligibility",
    )
    owner_status.set_defaults(handler=command_owner_status)

    mark_complete = commands.add_parser(
        "mark-complete", help="Mark one clean task branch's exact HEAD as completed"
    )
    mark_complete.add_argument("--branch")
    mark_complete.add_argument("--expected-head", required=True)
    mark_complete.set_defaults(handler=command_mark_complete)

    owner_finish = commands.add_parser(
        "owner-finish",
        help="Advance an owned task through completion, delivery, and cleanup",
    )
    owner_finish.add_argument(
        "--validated-source-head",
        help="Exact source HEAD that passed source-worktree validation",
    )
    owner_finish.add_argument(
        "--validated-target-head",
        help="Exact integrated target HEAD that passed target-worktree validation",
    )
    owner_finish.set_defaults(handler=command_owner_finish)

    block_auto_merge = commands.add_parser(
        "block-auto-merge",
        help="Block skill-managed merge of one local branch",
    )
    block_auto_merge.add_argument("--branch", required=True)
    block_auto_merge.add_argument("--expected-head", required=True)
    block_auto_merge.set_defaults(handler=command_block_auto_merge)

    unblock_auto_merge = commands.add_parser(
        "unblock-auto-merge",
        help="Remove one local branch's automatic-merge block",
    )
    unblock_auto_merge.add_argument("--branch", required=True)
    unblock_auto_merge.add_argument("--expected-marker-head", required=True)
    unblock_auto_merge.set_defaults(handler=command_unblock_auto_merge)

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

    maintenance_run = commands.add_parser(
        "maintenance-run",
        help="Apply one exact, fully classified maintenance snapshot",
    )
    maintenance_run.add_argument(
        "--plan",
        default="-",
        help="Decision-plan JSON path, or - for stdin (default: stdin)",
    )
    maintenance_run.set_defaults(handler=command_maintenance_run)

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
    create.add_argument(
        "--temporary",
        action="store_true",
        help="Record an agent-created temporary worktree that must be delivered and removed",
    )
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
        if args.command in MUTATING_COMMANDS:
            with repository_lock(repo, args.command):
                args.handler(repo, args)
        else:
            args.handler(repo, args)
    except WorkflowError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
