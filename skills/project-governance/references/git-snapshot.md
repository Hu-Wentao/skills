# Git Snapshot Policy

Collect repository root, current branch or detached state, full commit,
upstream divergence, worktree cleanliness, staged and unstaged paths, worktree
topology, and relevant immutable tags without changing Git state.

Treat the snapshot as time-bound evidence. Revalidate it immediately before a
commit, integration, tag, release, deployment, retry, or history-changing
operation. Do not infer authorization from a clean worktree or an existing
branch, tag, or release worktree.
