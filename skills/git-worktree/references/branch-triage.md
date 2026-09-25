# Branch Triage (整理分支)

Triage local unmerged branches toward a target (usually `main`): merge the
valuable, delete the worthless, and surface conflicts for the user. This is a
review-and-decide workflow, not an autonomous cleanup — the script supplies
evidence, the model judges value, and the user (or an explicit auto-merge
authorization) approves the destructive steps.

## Scope (read first)

- Local branches and worktrees only. Never touch remote refs, push, or rewrite
  published history.
- Protected branches (`release/`, `repair/`, `hotfix/`) are excluded from
  automatic deletion and need separate exact authority.
- The target defaults to the current branch; pass `--target main` explicitly for
  triage.

## Workflow

1. Snapshot: `maintenance-audit --target main --all`. This returns every local
   branch and worktree with evidence: `ahead`/`behind`, `contained_in_target`,
   `patch_equivalent_to_target`, completion state, auto-merge blocks, protected
   flag, and `possible_decisions`.
2. Conflict preview: `conflict-preview --target main --all`. Dry-run each merge
   against `main` without touching the working tree (requires git >= 2.38).
3. Assess each candidate. Combine the audit evidence with the conflict preview:
   - Already contained / patch-equivalent → its work is effectively already in
     `main`; `retain` only to delete after the user confirms, or delete if the
     user pre-authorized.
   - `clean` status → no merge conflict; proceed to a value decision.
   - `conflict` status → see Conflict summary below; do not auto-merge.
   - Dirty source, detached work, auto-merge block, or incomplete completion →
     `retain` until resolved or separately authorized.
4. Decide merge vs retain vs delete with a non-empty evidence reason for each.
5. Execute:
   - Clean, evidence-clear, auto-merge-authorized branches → submit the full
     decision set to `maintenance-run` in one batch (after the user approves the
     batch).
   - Conflicting or ambiguous branches → escalate with a functional conflict
     summary and let the user choose.

## Conflict preview output

`conflict-preview` emits one entry per branch:

- `status`: `conflict` | `clean` | `already_contained`.
- `conflicted_files[]`: each with `file`, `ours_sha`/`ours_mode` (target side),
  and `theirs_sha`/`theirs_mode` (source side). Fetch exact content with
  `git cat-file -p <ours_sha>` and `git cat-file -p <theirs_sha>`.
- `merge_tree_stdout` / `merge_tree_stderr`: raw diff3 for reference.

## Functional conflict summary (help the user decide)

For every `conflicted_files[]` entry, read both sides and summarize at the
function level — not line by line:

- What each side intends (feature intent vs target intent) for that path.
- Where the intents clash and whether they are mutually exclusive or merely
  divergent.
- A recommended path: merge one side, take a subset, or hand off for manual
  resolution.

Report the summary grouped by branch so the user can decide per branch. Keep it
short and behavior-focused; do not paste raw hunks.

## Hybrid execution model

- Auto (after user batch-approval): `clean` status, evidence clearly supports
  the decision, no auto-merge block, completion current.
- Escalate to the user: `conflict` status, dirty/uncontained work, auto-merge
  block, or a value judgment that is not evident from the data.

Never widen scope to satisfy a decision: if a branch is ambiguous, retain it and
ask rather than guessing.
