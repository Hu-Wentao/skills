#!/usr/bin/env bash

set -euo pipefail

source_branch="${1:-}"
target_branch="${2:-}"

die() {
  echo "Error: $*" >&2
  exit 1
}

ensure_git_repo() {
  git rev-parse --show-toplevel >/dev/null 2>&1 || die "Current directory is not a Git repository."
}

branch_exists() {
  local branch="$1"
  git show-ref --verify --quiet "refs/heads/${branch}"
}

current_branch() {
  git branch --show-current
}

count_unique_unmerged_branches_from_target() {
  local target="$1"

  git for-each-ref --format='%(refname:short)' refs/heads \
    | while IFS= read -r branch; do
        [[ "$branch" == "$target" ]] && continue

        if git merge-base --is-ancestor "$branch" "$target"; then
          continue
        fi

        ahead_count="$(git rev-list --count "${target}..${branch}")"
        if [[ "$ahead_count" -ge 1 ]]; then
          printf '%s\n' "$branch"
        fi
      done
}

resolve_branches() {
  local current candidate
  local candidates=()
  current="$(current_branch)"
  [[ -n "$current" ]] || die "Detached HEAD is not supported for this workflow."

  if [[ -z "$target_branch" ]]; then
    target_branch="$current"
  fi

  if [[ -n "$source_branch" ]]; then
    return 0
  fi

  while IFS= read -r candidate; do
    candidates+=("$candidate")
  done < <(count_unique_unmerged_branches_from_target "$target_branch")
  if [[ "${#candidates[@]}" -eq 1 ]]; then
    source_branch="${candidates[0]}"
    echo "Auto-selected source branch: ${source_branch}"
    echo "Auto-selected target branch: ${target_branch}"
    return 0
  fi

  if [[ "${#candidates[@]}" -gt 1 ]]; then
    printf 'Multiple branches have commits after %s:\n' "$target_branch" >&2
    printf '  %s\n' "${candidates[@]}" >&2
    die "Specify the source branch explicitly."
  fi

  die "Missing source branch. Provide it explicitly, or run this workflow when exactly one unmerged local branch is ahead of the current branch."
}

ensure_on_target_branch() {
  local current
  current="$(current_branch)"
  [[ "$current" == "$target_branch" ]] || die "Current worktree is on '${current}', not target branch '${target_branch}'. Switch to the target branch first."
}

check_branch_exists() {
  branch_exists "$1" || die "Branch '$1' does not exist locally."
}

collect_branch_worktrees() {
  local wanted_branch="$1"
  local line path branch_ref

  git worktree list --porcelain | while IFS= read -r line; do
    case "$line" in
      worktree\ *)
        path="${line#worktree }"
        ;;
      branch\ refs/heads/*)
        branch_ref="${line#branch refs/heads/}"
        if [[ "$branch_ref" == "$wanted_branch" ]]; then
          printf '%s\n' "$path"
        fi
        ;;
    esac
  done
}

check_worktree_clean() {
  local worktree_path="$1"
  local branch_name="$2"
  local status_output

  status_output="$(git -C "$worktree_path" status --short)"
  if [[ -n "$status_output" ]]; then
    echo "Dirty branch detected: ${branch_name}" >&2
    echo "Worktree: ${worktree_path}" >&2
    echo "$status_output" >&2
    die "Please clean, commit, or stash changes on branch '${branch_name}' before merging."
  fi
}

check_branch_cleanliness() {
  local branch_name="$1"
  local found=0
  local worktree_path

  while IFS= read -r worktree_path; do
    [[ -n "$worktree_path" ]] || continue
    found=1
    check_worktree_clean "$worktree_path" "$branch_name"
  done < <(collect_branch_worktrees "$branch_name")

  if [[ "$found" -eq 0 ]]; then
    echo "No active worktree found for branch '${branch_name}'. Treating it as clean."
  fi
}

list_conflicted_files() {
  git diff --name-only --diff-filter=U
}

has_conflicted_files() {
  local conflicted_files

  conflicted_files="$(list_conflicted_files)"
  [[ -n "$conflicted_files" ]]
}

run_merge() {
  if git merge --no-ff "$source_branch"; then
    echo "Merge completed successfully."
    echo "Source branch: ${source_branch}"
    echo "Target branch: ${target_branch}"
    echo "Merge commit: $(git rev-parse HEAD)"
    return 0
  fi

  echo "Merge failed. Current git status:" >&2
  git status --short >&2 || true

  if has_conflicted_files; then
    echo "Conflicted files:" >&2
    list_conflicted_files >&2 || true
    die "The merge is paused with conflicts. Resolve them in this worktree, stage the files, and finish with 'git commit --no-edit' or 'git merge --continue'."
  fi

  die "git merge --no-ff '${source_branch}' failed without leaving conflicted files."
}

main() {
  ensure_git_repo
  resolve_branches

  check_branch_exists "$source_branch"
  check_branch_exists "$target_branch"
  [[ "$source_branch" != "$target_branch" ]] || die "Source branch and target branch must be different."

  ensure_on_target_branch

  check_branch_cleanliness "$source_branch"
  check_branch_cleanliness "$target_branch"

  run_merge
}

main "$@"
