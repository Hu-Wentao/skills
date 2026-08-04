#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Collect one Git author's committed work for a weekly report."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence


SCHEMA = "project-weekly-report.git-work.v1"


class CollectionError(ValueError):
    """Raised when Git evidence cannot be collected."""


def run_git(
    repo: Path,
    *args: str,
    text: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=text,
        check=False,
    )
    if check and result.returncode != 0:
        stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode(
            "utf-8", errors="replace"
        )
        raise CollectionError(stderr.strip() or f"git {' '.join(args)} failed")
    return result


def resolve_repository(repo: Path) -> Path:
    candidate = repo.expanduser().resolve()
    result = run_git(candidate, "rev-parse", "--show-toplevel")
    assert isinstance(result.stdout, str)
    return Path(result.stdout.strip()).resolve()


def configured_author(repo: Path) -> tuple[str, str]:
    for key, source in (
        ("user.email", "git_config_user_email"),
        ("user.name", "git_config_user_name"),
    ):
        result = run_git(repo, "config", "--get", key, check=False)
        assert isinstance(result.stdout, str)
        value = result.stdout.strip()
        if result.returncode == 0 and value:
            return value, source
    raise CollectionError(
        "No author was provided and Git has neither user.email nor user.name configured"
    )


def default_range(now: datetime | None = None) -> tuple[str, str]:
    effective_now = now or datetime.now().astimezone()
    return (effective_now - timedelta(days=7)).isoformat(), effective_now.isoformat()


def commit_hashes(repo: Path, author: str, since: str, until: str) -> list[str]:
    result = run_git(
        repo,
        "log",
        "--all",
        "--fixed-strings",
        f"--author={author}",
        f"--since={since}",
        f"--until={until}",
        "--date-order",
        "-z",
        "--format=%H",
        text=False,
    )
    assert isinstance(result.stdout, bytes)
    return [item.decode("ascii") for item in result.stdout.split(b"\0") if item]


def parse_metadata(value: str) -> dict[str, str]:
    fields = value.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    if len(fields) != 8:
        raise CollectionError("Unexpected Git metadata record")
    full_hash, short_hash, name, email, authored_at, committed_at, subject, body = fields
    return {
        "hash": full_hash,
        "shortHash": short_hash,
        "authorName": name,
        "authorEmail": email,
        "authoredAt": authored_at,
        "committedAt": committed_at,
        "subject": subject,
        "body": body.strip(),
    }


def commit_metadata(repo: Path, commit_hash: str) -> dict[str, str]:
    result = run_git(
        repo,
        "show",
        "-s",
        "--no-show-signature",
        "--format=format:%H%x00%h%x00%an%x00%ae%x00%aI%x00%cI%x00%s%x00%b%x00",
        commit_hash,
    )
    assert isinstance(result.stdout, str)
    return parse_metadata(result.stdout)


def decode_path(value: bytes) -> str:
    return value.decode("utf-8", errors="surrogateescape")


def parse_numstat(value: bytes) -> list[dict[str, Any]]:
    records = value.split(b"\0")
    changes: list[dict[str, Any]] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        parts = record.split(b"\t", 2)
        if len(parts) != 3:
            raise CollectionError("Unexpected Git numstat record")
        added_raw, deleted_raw, path_raw = parts
        previous_path: str | None = None
        if not path_raw:
            if index + 1 >= len(records):
                raise CollectionError("Incomplete Git rename/copy numstat record")
            previous_path = decode_path(records[index])
            path = decode_path(records[index + 1])
            index += 2
        else:
            path = decode_path(path_raw)

        binary = added_raw == b"-" or deleted_raw == b"-"
        change: dict[str, Any] = {
            "path": path,
            "insertions": None if binary else int(added_raw),
            "deletions": None if binary else int(deleted_raw),
            "binary": binary,
        }
        if previous_path is not None:
            change["previousPath"] = previous_path
        changes.append(change)
    return changes


def commit_changes(repo: Path, commit_hash: str) -> list[dict[str, Any]]:
    result = run_git(
        repo,
        "show",
        "--format=",
        "--numstat",
        "--find-renames",
        "--first-parent",
        "-z",
        commit_hash,
        text=False,
    )
    assert isinstance(result.stdout, bytes)
    return parse_numstat(result.stdout)


def collect_report(
    repo: Path,
    author: str | None = None,
    since: str | None = None,
    until: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = resolve_repository(repo)
    if author:
        effective_author, author_source = author, "argument"
    else:
        effective_author, author_source = configured_author(root)

    default_since, default_until = default_range(now)
    effective_since = since or default_since
    effective_until = until or default_until

    commits: list[dict[str, Any]] = []
    changed_paths: set[str] = set()
    insertions = deletions = binary_changes = 0
    for commit_hash in commit_hashes(
        root, effective_author, effective_since, effective_until
    ):
        commit: dict[str, Any] = commit_metadata(root, commit_hash)
        files = commit_changes(root, commit_hash)
        commit["files"] = files
        commits.append(commit)
        for change in files:
            changed_paths.add(change["path"])
            if change["binary"]:
                binary_changes += 1
            else:
                insertions += change["insertions"]
                deletions += change["deletions"]

    return {
        "schema": SCHEMA,
        "generatedAt": (now or datetime.now().astimezone()).isoformat(),
        "repository": {
            "root": str(root),
            "name": root.name,
        },
        "query": {
            "author": effective_author,
            "authorSource": author_source,
            "authorMatch": "fixed_substring",
            "since": effective_since,
            "until": effective_until,
            "revisionScope": "all_refs",
        },
        "summary": {
            "commitCount": len(commits),
            "filesChanged": len(changed_paths),
            "insertions": insertions,
            "deletions": deletions,
            "binaryFileChanges": binary_changes,
        },
        "commits": commits,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Git repository or a path inside it (default: current directory)",
    )
    parser.add_argument(
        "--author",
        help="Fixed author name/email substring (default: configured Git email/name)",
    )
    parser.add_argument(
        "--since",
        help="Start date accepted by git log (default: seven days ago)",
    )
    parser.add_argument(
        "--until",
        help="End date accepted by git log (default: now)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = collect_report(args.repo, args.author, args.since, args.until)
    except (CollectionError, OSError) as exc:
        print(
            json.dumps({"schema": SCHEMA, "status": "failed", "error": str(exc)}),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
