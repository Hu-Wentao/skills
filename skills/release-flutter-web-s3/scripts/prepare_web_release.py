#!/usr/bin/env python3
"""Prepare a Flutter Web release version."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path


VERSION_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?P<prerelease>-[0-9A-Za-z.-]+)?(?P<build>\+[0-9A-Za-z.-]+)?$"
)


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str
    body: str


def run_git(args: list[str], check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise SystemExit(f"git {' '.join(args)} failed: {message}")
    return result.stdout.strip()


def read_pubspec_version(pubspec: Path) -> str:
    if not pubspec.exists():
        raise SystemExit(f"pubspec.yaml not found: {pubspec}")

    for line in pubspec.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^version:\s*['\"]?([^'\"\s#]+)['\"]?", line)
        if match:
            return match.group(1)

    raise SystemExit(f"version field not found in {pubspec}")


def validate_version(version: str) -> None:
    if not VERSION_RE.match(version):
        raise SystemExit(
            "Version must be SemVer compatible for Flutter, for example 1.2.3 or 1.2.3+4: "
            f"{version}"
        )


def write_pubspec_version(pubspec: Path, version: str) -> None:
    validate_version(version)
    text = pubspec.read_text(encoding="utf-8")
    updated, count = re.subn(
        r"(?m)^version:\s*['\"]?[^'\"\s#]+['\"]?(\s*(?:#.*)?)$",
        rf"version: {version}\1",
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"Could not update version field in {pubspec}")
    pubspec.write_text(updated, encoding="utf-8")


def last_matching_tag(pattern: str) -> str | None:
    output = run_git(["describe", "--tags", "--abbrev=0", "--match", pattern], check=False)
    return output or None


def commits_since(tag: str | None) -> list[Commit]:
    revision = f"{tag}..HEAD" if tag else "HEAD"
    fmt = "%H%x1f%s%x1f%b%x1e"
    output = run_git(["log", f"--pretty=format:{fmt}", revision], check=False)
    commits: list[Commit] = []
    for raw in output.split("\x1e"):
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split("\x1f", 2)
        if len(parts) != 3:
            continue
        commits.append(Commit(sha=parts[0], subject=parts[1].strip(), body=parts[2].strip()))
    return commits


def classify_bump(commits: list[Commit]) -> str:
    if not commits:
        return "none"

    has_feature = False
    has_patch = False

    for commit in commits:
        subject = commit.subject
        body = commit.body
        if re.match(r"^[a-zA-Z]+(?:\([^)]+\))?!:", subject) or "BREAKING CHANGE" in body:
            return "major"
        if subject.startswith("feat"):
            has_feature = True
        elif subject.startswith(("fix", "perf")):
            has_patch = True

    if has_feature:
        return "minor"
    if has_patch:
        return "patch"
    return "patch"


def bump_version(version: str, bump: str) -> str:
    match = VERSION_RE.match(version)
    if not match:
        raise SystemExit(f"Current version is not SemVer compatible: {version}")

    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))

    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if bump == "none":
        return version

    raise SystemExit(f"Unsupported bump: {bump}")


def release_notes(version: str, commits: list[Commit]) -> str:
    lines = [f"## {version} {date.today().isoformat()}"]
    if not commits:
        lines.append("* No commits since last web release tag")
    else:
        for commit in commits:
            lines.append(f"* {commit.subject} ({commit.sha[:7]})")
    return "\n".join(lines)


def build_report(args: argparse.Namespace) -> dict[str, object]:
    pubspec = Path(args.pubspec)
    current_version = read_pubspec_version(pubspec)
    validate_version(current_version)

    last_tag = last_matching_tag(args.tag_match)
    commits = commits_since(last_tag)
    detected_bump = classify_bump(commits)
    bump = args.bump or detected_bump
    chosen_version = args.version or bump_version(current_version, bump)
    validate_version(chosen_version)

    tag_name = f"{args.tag_prefix}{chosen_version}"
    return {
        "pubspec": str(pubspec),
        "current_version": current_version,
        "last_tag": last_tag,
        "commit_count": len(commits),
        "detected_bump": detected_bump,
        "selected_bump": bump,
        "suggested_version": bump_version(current_version, detected_bump),
        "version": chosen_version,
        "release_id": chosen_version,
        "tag_name": tag_name,
        "commit_subjects": [commit.subject for commit in commits],
        "release_notes": release_notes(chosen_version, commits),
    }


def print_text_report(report: dict[str, object]) -> None:
    print(f"PUBSPEC: {report['pubspec']}")
    print(f"CURRENT_VERSION: {report['current_version']}")
    print(f"LAST_TAG: {report['last_tag'] or 'None'}")
    print(f"COMMIT_COUNT: {report['commit_count']}")
    print(f"DETECTED_BUMP: {report['detected_bump']}")
    print(f"SELECTED_BUMP: {report['selected_bump']}")
    print(f"SUGGESTED_VERSION: {report['suggested_version']}")
    print(f"VERSION: {report['version']}")
    print(f"RELEASE_ID: {report['release_id']}")
    print(f"TAG_NAME: {report['tag_name']}")
    print("RELEASE_NOTES_START")
    print(report["release_notes"])
    print("RELEASE_NOTES_END")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Suggest or write a Flutter Web release version from pubspec.yaml and git history."
    )
    parser.add_argument("--pubspec", default="pubspec.yaml", help="Path to pubspec.yaml")
    parser.add_argument("--tag-match", default="web-v*", help="Git tag glob for previous web releases")
    parser.add_argument("--tag-prefix", default="web-v", help="Prefix for the release tag")
    parser.add_argument("--version", help="Explicit release version to use")
    parser.add_argument("--bump", choices=["major", "minor", "patch", "none"], help="Override bump type")
    parser.add_argument("--write", action="store_true", help="Update pubspec.yaml with the selected version")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    report = build_report(args)

    if args.write:
        write_pubspec_version(Path(args.pubspec), str(report["version"]))
        report["updated"] = True
    else:
        report["updated"] = False

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text_report(report)
        if args.write:
            print(f"UPDATED: {args.pubspec}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
