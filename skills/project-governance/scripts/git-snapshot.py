#!/usr/bin/env python3
"""Collect a stable read-only Git governance snapshot."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


class SnapshotError(ValueError):
    """Raised when the selected directory is not a usable Git worktree."""


def git(cwd: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise SnapshotError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def parse_worktrees(value: str) -> list[dict[str, object]]:
    worktrees: list[dict[str, object]] = []
    current: dict[str, object] = {}
    for line in value.splitlines():
        if not line:
            if current:
                worktrees.append(current)
                current = {}
            continue
        key, _, raw_value = line.partition(" ")
        if key in {"bare", "detached", "locked", "prunable"}:
            current[key] = raw_value or True
        else:
            current[key] = raw_value
    if current:
        worktrees.append(current)
    return worktrees


def snapshot(cwd: Path) -> dict[str, object]:
    root = Path(git(cwd, "rev-parse", "--show-toplevel").strip()).resolve()
    commit = git(root, "rev-parse", "HEAD").strip()
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).strip()
    upstream = git(
        root,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
        check=False,
    ).strip()
    ahead = behind = None
    if upstream:
        counts = git(root, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
        behind_text, ahead_text = counts.split()
        ahead, behind = int(ahead_text), int(behind_text)
    status = git(root, "status", "--porcelain=v1", "-z")
    entries = []
    for record in status.split("\0"):
        if not record:
            continue
        entries.append({"index": record[0], "worktree": record[1], "path": record[3:]})
    tags = git(root, "tag", "--points-at", "HEAD", "--sort=refname").splitlines()
    return {
        "schema": "project-governance.git-snapshot.v1",
        "status": "ready",
        "state": "snapshot_collected",
        "repositoryRoot": str(root),
        "branch": branch or None,
        "detached": not bool(branch),
        "commit": commit,
        "upstream": upstream or None,
        "ahead": ahead,
        "behind": behind,
        "clean": not entries,
        "changes": entries,
        "tagsAtHead": tags,
        "worktrees": parse_worktrees(git(root, "worktree", "list", "--porcelain")),
        "allowedNextActions": ["semantic_review", "revalidate_before_mutation"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        report = snapshot(args.cwd.resolve())
    except SnapshotError as exc:
        print(
            json.dumps(
                {
                    "schema": "project-governance.git-snapshot.v1",
                    "status": "failed",
                    "state": "precondition_failed",
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 3
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
