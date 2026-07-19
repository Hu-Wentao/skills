#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <source-skill-dir> [--repo <path>] [--message <text>] [--allow-source-dirty] [--allow-dirty] [--dry-run]" >&2
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

source_dir=$1
shift
repo=/Users/wyatt/_proj/wyatt_skills
message=
allow_source_dirty=0
allow_dirty=0
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      repo=$2
      shift 2
      ;;
    --message)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      message=$2
      shift 2
      ;;
    --allow-source-dirty) allow_source_dirty=1; shift ;;
    --allow-dirty) allow_dirty=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

source_dir=$(cd "$source_dir" && pwd -P)
repo=$(cd "$repo" && pwd -P)

[[ -f "$source_dir/SKILL.md" ]] || { echo "Missing $source_dir/SKILL.md" >&2; exit 3; }
git -C "$repo" rev-parse --show-toplevel >/dev/null
[[ "$(git -C "$repo" rev-parse --show-toplevel)" == "$repo" ]] || { echo "Destination is not the Git worktree root: $repo" >&2; exit 3; }

case "$source_dir/" in
  "$repo"/*) echo "Source must be outside the destination repository" >&2; exit 3 ;;
esac

skill_name=$(basename "$source_dir")
[[ "$skill_name" =~ ^[a-z0-9-]+$ ]] || { echo "Invalid skill folder name: $skill_name" >&2; exit 3; }
frontmatter_name=$(awk 'BEGIN { in_yaml=0 } /^---[[:space:]]*$/ { if (in_yaml) exit; in_yaml=1; next } in_yaml && /^name:[[:space:]]*/ { sub(/^name:[[:space:]]*/, ""); print; exit }' "$source_dir/SKILL.md")
[[ "$frontmatter_name" == "$skill_name" ]] || { echo "SKILL.md name '$frontmatter_name' does not match folder '$skill_name'" >&2; exit 3; }

branch=$(git -C "$repo" branch --show-current)
[[ -n "$branch" ]] || { echo "Destination repository is in detached HEAD state" >&2; exit 4; }
upstream=$(git -C "$repo" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)
[[ -n "$upstream" ]] || { echo "Current branch '$branch' has no configured upstream" >&2; exit 4; }

source_root=$(git -C "$source_dir" rev-parse --show-toplevel 2>/dev/null || true)
if [[ -n "$source_root" ]]; then
  source_rel=$(git -C "$source_root" ls-files --full-name -- "$source_dir" >/dev/null 2>&1; realpath "$source_dir" | sed "s#^$source_root/##")
  source_status=$(git -C "$source_root" status --short -- "$source_rel")
  if [[ -n "$source_status" && $allow_source_dirty -ne 1 ]]; then
    echo "Source skill has uncommitted changes:" >&2
    echo "$source_status" >&2
    echo "Confirm the source version, then rerun with --allow-source-dirty." >&2
    exit 5
  fi
fi

dest_status=$(git -C "$repo" status --short)
if [[ -n "$dest_status" && $allow_dirty -ne 1 ]]; then
  echo "Destination repository has uncommitted changes:" >&2
  echo "$dest_status" >&2
  echo "Choose 先提交 or 先忽略; rerun with --allow-dirty only for 先忽略." >&2
  exit 6
fi

destination="$repo/skills/$skill_name"
if [[ $allow_dirty -eq 1 ]] && [[ -n "$(git -C "$repo" status --short -- "skills/$skill_name")" ]]; then
  echo "Dirty destination changes overlap skills/$skill_name; resolve them separately." >&2
  exit 6
fi

ahead=$(git -C "$repo" rev-list --count "$upstream..HEAD")
echo "Source: $source_dir"
echo "Destination: $destination"
echo "Branch: $branch -> $upstream"
echo "Existing unpushed commits: $ahead"

mkdir_args=()
[[ $dry_run -eq 1 ]] || mkdir_args=(-p)
if [[ $dry_run -eq 1 && ! -d "$destination" ]]; then
  echo "Destination directory will be created."
fi
[[ $dry_run -eq 1 ]] || mkdir "${mkdir_args[@]}" "$destination"

rsync_args=(-a --itemize-changes --exclude=.git --exclude=.DS_Store --exclude=dist --exclude=node_modules --exclude=.ruff_cache --exclude=__pycache__ --exclude='*.pyc')
[[ $dry_run -eq 1 ]] && rsync_args+=(--dry-run)
rsync "${rsync_args[@]}" "$source_dir/" "$destination/"

if [[ $dry_run -eq 1 ]]; then
  exit 0
fi

validator=/Users/wyatt/.codex/skills/.system/skill-creator/scripts/quick_validate.py
uv run --with pyyaml python "$validator" "$destination"

git -C "$repo" add -- "skills/$skill_name"
if git -C "$repo" diff --cached --quiet -- "skills/$skill_name"; then
  echo "No synchronized changes to commit."
  exit 0
fi

if [[ -z "$message" ]]; then
  message="feat: sync $skill_name skill"
fi
git -C "$repo" commit -m "$message" -- "skills/$skill_name"
commit_sha=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" push
echo "Committed: $commit_sha $message"
echo "Pushed: $branch -> $upstream"
