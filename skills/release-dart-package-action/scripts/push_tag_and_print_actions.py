import argparse
import re
import subprocess
import sys


def run_command(cmd):
    subprocess.run(cmd, check=True)


def get_remote_url(remote_name):
    result = subprocess.run(
        ["git", "remote", "get-url", remote_name],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def derive_github_actions_url(remote_url):
    match = re.match(
        r"^(?:git@github\.com:|https://github\.com/)(?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$",
        remote_url,
    )
    if not match:
        return None

    owner = match.group("owner")
    repo = match.group("repo")
    return f"https://github.com/{owner}/{repo}/actions"


def push_tag_and_print_actions_url(tag_name, remote_name="origin"):
    run_command(["git", "push"])
    run_command(["git", "push", remote_name, tag_name])

    remote_url = get_remote_url(remote_name)
    actions_url = derive_github_actions_url(remote_url)
    if actions_url:
        print(actions_url)
        return 0

    print(
        f"Tag push succeeded, but could not derive a GitHub Actions URL from remote '{remote_name}': {remote_url}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Push the current branch and tag, then print the GitHub Actions URL."
    )
    parser.add_argument("tag_name", help="The git tag to push")
    parser.add_argument(
        "--remote",
        default="origin",
        help="The git remote to use for pushing the tag (default: origin)",
    )
    args = parser.parse_args()

    raise SystemExit(push_tag_and_print_actions_url(args.tag_name, args.remote))
