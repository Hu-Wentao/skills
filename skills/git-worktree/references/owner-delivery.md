# Owner Delivery

Inspect `owner-status` before editing an eligible non-main worktree. Treat a pre-existing task worktree as owned when the current implementation request clearly names its plan or specification.

After authorized changes are committed, the source worktree is clean, and source checks pass, call `owner-finish --validated-source-head <sha>`.

- `user_owned` creates or confirms the completion ref and stops at handoff. It never merges or removes the worktree.
- `agent_temporary` creates or confirms completion, merges the exact source head into its recorded local target when safe, and returns `target_validation_required`.
- Validate the returned target at its exact head, then call `owner-finish --validated-target-head <sha>` from the still-existing source worktree.
- Cleanup is allowed only when the completed source is contained in the unchanged validated target and the temporary worktree is clean.

Report completion only for `handoff_completed` or `completed`. Preserve the worktree and report exact blockers for every other state. Use low-level `mark-complete`, `merge`, or `remove` only for explicit recovery.
