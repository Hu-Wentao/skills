---
name: git-worktree
description: Manage local Git worktrees and branches with exact-HEAD safeguards; never publish or rewrite remote state.
metadata:
  context-budget: router
---
# Git Worktree

Use the bundled CLI as the state authority. Read repository instructions and status first.

## Lifecycle
```bash
uv run python <skill-root>/scripts/git_worktree.py --repo <repo> owner-status
uv run python <skill-root>/scripts/git_worktree.py --repo <repo> create --branch <branch> [--base <base>] [--path <path>] [--temporary]
uv run python <skill-root>/scripts/git_worktree.py --repo <worktree> owner-finish --validated-source-head <exact-head>
```
For maintenance, run `maintenance-audit --target <branch> --all`, review only `review_required`, then submit evidence-backed decisions to `maintenance-run`.

## Safety
- Never claim completion for dirty source, detached, conflicted, moved, unvalidated, main, or blocked state. A merge target may contain only non-overlapping, uncommitted `docs/` drafts.
- Re-audit after rescue, merge, deletion, movement, or state changes; validate the target before removing a source.
- Protect completion and no-auto-merge refs. Never push, alter remote refs, rebase, squash, stash, force-remove, or change normal tags.
- Stage or commit another owner’s changes only with that owner’s authority.

Read `references/owner-delivery.md`, `maintenance.md`, and `safety.md` when completing, maintaining, or recovering work.

## Report
Include exact source/target HEADs, ownership and delivery state, refs, validation, decisions, retained or removed worktrees, blockers, and untouched remote refs.
