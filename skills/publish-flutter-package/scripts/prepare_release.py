import subprocess
import re
import argparse
from datetime import datetime


def get_last_tag(match_pattern=None):
    try:
        cmd = ["git", "describe", "--tags", "--abbrev=0"]
        if match_pattern:
            cmd.extend(["--match", match_pattern])
        tag = (
            subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            .decode("utf-8")
            .strip()
        )
        return tag
    except subprocess.CalledProcessError:
        return None


def get_commits_since(tag, package_path=None):
    if tag:
        range_str = f"{tag}..HEAD"
    else:
        # If no tag exists, get all commits
        range_str = "HEAD"

    try:
        cmd = ["git", "log", "--pretty=format:%s", range_str]
        if package_path:
            cmd.extend(["--", package_path])

        commits = subprocess.check_output(cmd).decode("utf-8").splitlines()
        return commits
    except subprocess.CalledProcessError:
        # Fallback if range is invalid
        return []


def parse_semver(version_str):
    # Matches common formats: v1.2.3, 1.2.3, my-pkg-1.2.3, etc.
    # It looks for the last occurrence of X.Y.Z in the string
    match = re.search(r"(\d+)\.(\d+)\.(\d+)$", version_str)
    if match:
        return [int(x) for x in match.groups()]

    # Try searching anywhere in the string if it doesn't end with it
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", version_str)
    if match:
        return [int(x) for x in match.groups()]

    return [0, 0, 0]


def suggest_version(current_version, commits):
    major, minor, patch = parse_semver(current_version)

    if not commits:
        return f"{major}.{minor}.{patch}"

    has_breaking = False
    has_feat = False
    has_fix = False

    for commit in commits:
        # Simple conventional commits check
        if "!" in commit or "BREAKING CHANGE" in commit:
            has_breaking = True
        elif commit.startswith("feat"):
            has_feat = True
        elif commit.startswith("fix"):
            has_fix = True

    if has_breaking:
        major += 1
        minor = 0
        patch = 0
    elif has_feat:
        minor += 1
        patch = 0
    elif has_fix:
        patch += 1
    else:
        # If no clear signal, default to patch
        patch += 1

    return f"{major}.{minor}.{patch}"


def format_changelog_entry(version, commits):
    date = datetime.now().strftime("%Y-%m-%d")
    header = f"## {version} {date}"
    entries = []
    for commit in commits:
        clean_commit = commit.strip()
        if clean_commit:
            entries.append(f"* {clean_commit}")

    if not entries:
        entries.append("* Miscellaneous updates")

    return f"{header}\n" + "\n".join(entries) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prepare release by suggesting version and generating changelog."
    )
    parser.add_argument(
        "current_version",
        help="The current version of the package (e.g., from pubspec.yaml)",
    )
    parser.add_argument(
        "--tag-match", help='Glob pattern for git tags to match (e.g., "my-pkg-*")'
    )
    parser.add_argument(
        "--package-path", help='Filter commits by package path (e.g., "pkgs/my_pkg")'
    )

    args = parser.parse_args()

    last_tag = get_last_tag(args.tag_match)
    commits = get_commits_since(last_tag, args.package_path)

    # If no commits since last tag, we might still want to publish if it's the first release
    # but usually this script is called when there are changes.

    suggested = suggest_version(args.current_version, commits)
    changelog_entry = format_changelog_entry(suggested, commits)

    print(f"LAST_TAG: {last_tag if last_tag else 'None'}")
    print(f"SUGGESTED_VERSION: {suggested}")
    print(f"PACKAGE_PATH: {args.package_path if args.package_path else 'Root'}")
    print("CHANGELOG_ENTRY_START")
    print(changelog_entry)
    print("CHANGELOG_ENTRY_END")
