---
name: git-worktree
description: Manage local Git worktree and branch lifecycles with exact-HEAD safeguards. Use to create, inspect, complete, hand off, merge, retain, rescue, remove, or audit local worktrees and branches. This skill never pushes, changes remote refs, rebases, squashes, stashes, force-removes, or manages publication.
metadata:
  context-budget: router
---

# Git Worktree

Own only local worktree and branch lifecycle. Keep project validation, publication, release semantics, and remote operations with their domain owners.

## Start

Read repository instructions, inspect status and topology, then use the bundled CLI as the authority for deterministic Git state:

```bash
uv run python <skill-root>/scripts/git_worktree.py \
  --repo <repository-or-worktree> owner-status
```

Preserve returned absolute paths, branch, exact HEAD, ownership kind, completion and delivery state, blockers, and `next_action`. Read [owner-delivery.md](references/owner-delivery.md) before completing an owned task.

## Create and Complete

```bash
uv run python <skill-root>/scripts/git_worktree.py --repo <repo> create \
  --branch <branch> [--base <base>] [--path <outside-repo-path>] [--temporary]

uv run python <skill-root>/scripts/git_worktree.py --repo <worktree> owner-finish \
  --validated-source-head <exact-head>
```

A user-requested worktree is retained. An internal `--temporary` worktree follows the exact delivery state machine and may require target validation before cleanup. Never claim completion for dirty, detached, main, conflicted, moved, unvalidated, or blocked state.

## Maintain Local State

Audit before any maintenance mutation:

```bash
uv run python <skill-root>/scripts/git_worktree.py --repo <repo> \
  maintenance-audit --target <branch> --all
```

Review only candidates returned in `review_required`; supply evidence-backed `merge`, `retain`, or `delete` decisions in the returned plan template, then run `maintenance-run`. Script-enforced dirty, active, locked, uninspectable, or no-auto-merge retention remains automatic.

Read [maintenance.md](references/maintenance.md) for semantic decisions, detached rescue, missing registrations, protected lineages, and low-level recovery commands.

## Safety

- Stage and commit another owner’s changes only with that task’s authority.
- Never infer completion from age, cleanliness, or containment alone.
- Re-audit after any rescue, merge, deletion, target movement, or state change.
- Do not remove a source worktree in the same run that merges it; validate the target first.
- Protect `refs/agents/no-auto-merge/<branch>` and exact completion refs.
- Never push, delete remote refs, rebase, squash, stash, force-remove, or alter normal tags.

Read [safety.md](references/safety.md) for exact-head gates and prohibited operations.

## Report

Report exact source and target HEADs, ownership and delivery status, completion/no-auto-merge refs, validation results, automatic and semantic decisions, retained work, rescues, local merges/removals/deletions, blockers, and remote refs left untouched.

## Resource

- `scripts/git_worktree.py`: deterministic local worktree, completion, maintenance, rescue, merge, and cleanup state machine.
