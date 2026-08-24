---
name: git-worktree
description: Script Git worktree creation, owner-task completion, temporary delivery, local branch maintenance, rescue, merge, and cleanup with exact-HEAD and dirty-work safeguards. Use when Codex creates or enters a worktree; implements a plan or specification on a non-main task branch; must hand off a validated commit; lists, merges, retains, deletes, rescues, or cleans local branches and worktrees; or audits local development state. Keeps validation and semantic value judgments explicit while automating deterministic Git transitions. Never pushes, deletes remote refs, rebases, squashes, stashes, force-removes, or changes normal tags.
---

# Git Worktree

Use the bundled CLI as the authority for Git state and deterministic mutations.
Let the script capture exact HEADs, lock the repository, enforce preservation
rules, and return the next action. Keep project validation and semantic branch
classification outside the script.

## Start

1. Read the target repository instructions.
2. Check `git status --short`, the current branch, and
   `git worktree list --porcelain`.
3. Resolve `SKILL_DIR` to this skill directory and invoke:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" \
  --repo <repository-or-worktree> <command>
```

For any implementation task, inspect the current directory before editing:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" \
  --repo <current-worktree> owner-status
```

Treat implementation of a plan or specification in the current non-main
worktree as ownership of that task branch, even when the worktree predates the
conversation. Preserve the returned absolute path, branch, exact HEAD,
ownership kind, completion state, delivery state, blockers, and `next_action`.

## Create

List worktrees:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> list
```

Create a user-requested worktree without `--temporary`; retain it until the
user explicitly requests cleanup. Create an internal isolation worktree with
`--temporary`; it must be delivered to its recorded target and removed before
the repository update is complete.

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> create \
  --branch <new-branch> [--base <base-branch>] [--path <outside-repo-path>] \
  [--temporary]
```

Default the base to the current branch only when the user did not specify one.
Prefer the script's deterministic sibling path. Follow repository package
manager instructions when dependencies must be initialized.

## Finish Owned Work

After all authorized changes are committed, the source worktree is clean, and
source validation passes, capture its exact validated HEAD and run:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" \
  --repo <owned-worktree> owner-finish \
  --validated-source-head <exact-validated-source-head>
```

`owner-finish` is an idempotent state machine:

- For `user_owned`, it creates or confirms the completion ref and stops at a
  handoff. It never merges or removes that worktree.
- For `agent_temporary`, it creates or confirms the completion ref and safely
  merges the exact source HEAD into the recorded target. It returns
  `target_validation_required`, the target worktree, and the exact merged
  target HEAD.
- If integration already exists, it returns the current exact target HEAD
  without merging again.
- It refuses dirty, detached, main, locked, missing, prunable, conflicted,
  moved, uncompleted, or automatic-merge-blocked state.

Validate the returned target worktree at the returned exact HEAD. Then rerun
against the still-existing source worktree:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" \
  --repo <owned-worktree> owner-finish \
  --validated-target-head <exact-validated-target-head>
```

The second phase removes only a clean agent-temporary worktree whose completed
source HEAD is contained in the unchanged validated target. The ordinary local
source branch and completion ref remain. Report completion only when the JSON
status is `handoff_completed` or `completed`. Otherwise preserve the worktree
and report the script's exact blocker and `next_action`.

Use `mark-complete`, `merge`, and `remove` directly only for an explicit
low-level request or recovery. Never substitute a normal tag for
`refs/agents/completed/<branch>`.

## Block Automatic Merge

An exact request such as “禁止 `<branch>` 自动合并” authorizes the local marker:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> \
  block-auto-merge --branch <branch> --expected-head <exact-head>

uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> \
  unblock-auto-merge --branch <branch> \
  --expected-marker-head <marked-head>
```

The marker blocks skill-managed merge and temporary delivery until explicitly
removed. Maintenance automatically retains marked branches unchanged.

## Maintain Local State

Treat an unqualified “整理分支” as all-candidate local maintenance. Audit before
mutation:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> \
  maintenance-audit --target <branch> --all
```

The audit returns one stable snapshot plus:

- `decision_plan_template`: executable plan envelope for that snapshot;
- `automatic_retention_decisions`: dirty, active-operation, locked,
  uninspectable, or no-auto-merge candidates the script will retain;
- `review_required`: only candidates needing semantic `merge`, `delete`, or
  `retain` judgment;
- `rescue_required_worktrees`: detached HEADs requiring preservation first.

Inspect every `review_required` candidate's commits, diff, target code,
requirements, validation, later replacements, and review history. Add only
those decisions and non-empty evidence reasons to the template. The runner
automatically fills script-enforced retention decisions and rejects omitted
semantic decisions:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" \
  --repo <target-worktree> maintenance-run --plan <decision-plan.json>
```

Assign decisions narrowly:

- `merge`: behavior remains valuable and compatible.
- `retain`: work is active, incomplete, protected, unresolved, or unsafe.
- `delete`: behavior is contained, patch-equivalent, demonstrably superseded,
  or has no remaining value, with exact evidence.

Never treat age or a clean directory as proof of completion. Do not mutate an
active or dirty worktree. A generic maintenance request does not authorize
committing another owner's changes, remote operations, or forced cleanup.
Re-audit after any rescue, merge, deletion, target movement, or candidate state
change. Do not delete a source worktree in the same run that merges its branch;
validate the target and perform cleanup from a fresh snapshot.

### Rescue and missing registrations

Before running maintenance, rescue each clean uncontained detached HEAD that
lacks an exact ordinary local branch or tag:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> \
  rescue-detached --worktree <worktree-path> --branch <new-branch> \
  --expected-head <audited-head> --target <target-branch>
```

Rescue is preservation, not a terminal decision. Re-audit and classify the
new branch. Retain dirty detached work unchanged unless a separate exact
request authorizes rescue or commit.

Prune only the complete audited set of missing, unlocked registrations:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> prune-missing \
  --expect "<path-1>=<head-1>" [--expect "<path-2>=<head-2>"]
```

This retains ordinary branch refs.

### Protected release lineages

Do not infer that retaining or removing `release/*`, `repair/*`, or `hotfix/*`
proves its published fix is present in the target. Inspect the stable tag and
peeled commit. When release governance exists, resolve `project-governance` for
`release-deployment` and use its contracted read-only synchronization plan.
Perform its exact local synchronization only when the maintenance request
authorizes it. Never replace that contract with a generic merge of a protected
branch. Retain unresolved or untagged protected lineages.

## Explicit Low-Level Operations

Use these only when the user's request names the corresponding operation:

```bash
# Recent branch-only inventory
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> branch-audit \
  --recent-count <N> [--target <branch>]

# Exact local merge, run from the target worktree
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <target-worktree> merge \
  --source <source> --target <target> \
  --expected-source-head <head> --expected-target-head <head>

# Safe worktree removal; attached branches remain
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> remove \
  --worktree <worktree-path> --require-merged-into <target>

# Evidence-classified local branch deletion
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> branch-delete \
  --branch <branch> --target <target> --reason <evidence> \
  --expected-head <head> [--expected-target-head <head>]
```

Protected branch deletion requires separate exact authorization. Never force
remove, stash, push, delete remote refs, rebase, squash, or change normal tags
as part of this workflow.

## Report

Use the script's structured output. Report exact source and target HEADs,
completion and no-auto-merge refs, ownership and delivery status, validation
commands/results, automatic versus provided maintenance decisions, retained
active or dirty work, rescued HEADs, merges, removals, deleted local branches,
pruned registrations, blockers, remote refs remaining untouched, and breaking
or compatibility effects.

## Resource

- `scripts/git_worktree.py`: deterministic owner-finish state machine,
  worktree lifecycle, exact completion handoff, local maintenance audit and
  plan execution, automatic safe retention, mutation locking, detached rescue,
  exact pruning, merge, removal, and classified local branch deletion.
