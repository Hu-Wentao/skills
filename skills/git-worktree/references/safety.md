# Local Git Safety

All mutations must bind the reviewed source and target to exact heads. Refuse dirty worktrees, unresolved operations, changed heads, locked or prunable registrations, and automatic-merge blocks.

`refs/agents/completed/<branch>` records exact local completion. `refs/agents/no-auto-merge/<branch>` prevents skill-managed merge and temporary delivery until explicitly removed with its expected marked head. Do not substitute ordinary tags.

A generic cleanup or maintenance request never authorizes remote operations, forced cleanup, another owner’s commit, or destructive history changes. Never push, delete remote refs, rebase, squash, stash, force-remove, or change normal tags. Keep publication and release identity outside this skill.
