# Git Version Governance

## Define Ref Roles

- Treat the primary integration branch, normally `main`, as the durable history of accepted changes.
- Use topic branches for bounded changes and temporary release branches for isolated release preparation.
- Use annotated `v<version>` tags as immutable release identities.
- Record a full commit id beside every deployment or retry decision.
- Derive hotfix branches from release tags so the maintenance base is stable and auditable.

Adapt names to an established project convention, but preserve these roles. Do not silently reinterpret a mutable branch as an immutable release identifier.

## Isolate a Change

1. Read repository instructions and inspect `git status --short --branch` before editing.
2. Separate in-scope changes from unrelated work. Preserve user changes and obtain any commit-or-ignore decision required by the repository.
3. Use a dedicated branch or worktree when isolation reduces collision or release risk.
4. Stage exact paths, inspect `git diff --cached`, and ensure the commit contains one coherent change.
5. Run verification appropriate to the staged scope before committing.

Do not stash, reset, restore, clean, amend, rebase, or force-update refs unless the action is authorized and its effect is understood. A clean worktree does not itself authorize a commit, push, release, or deployment.

## Create a Release

Use this ordering unless a project has an explicitly documented stronger policy:

1. Resolve and record `SOURCE_COMMIT` from clean `main`.
2. Determine the release version without mutating `main`.
3. Create an isolated worktree on `release/v<version>` at `SOURCE_COMMIT`.
4. Apply version changes and run release checks and builds there.
5. Commit the release metadata on the temporary release branch.
6. Recheck that checked-out `main` is clean and still equals `SOURCE_COMMIT`.
7. Run `git merge --ff-only <release-commit>` from the `main` worktree. If it cannot fast-forward, stop and resolve the new history deliberately.
8. Create annotated tag `v<version>` only after `main` contains the release commit.
9. Verify all of the following resolve to the same full commit id:
   - the release worktree `HEAD`;
   - the `main` worktree `HEAD`;
   - `v<version>^{commit}`.
10. Deploy only that recorded tag and commit. Reuse both for every retry.
11. Remove the clean release worktree and delete the merged temporary branch when failure artifacts are no longer needed.

The temporary worktree isolates edits and checks; it must not strand the release commit outside integration history. A tag pointing to a detached-only commit does not repair that history.

## Govern Deployment Identity

- Freeze the commit before deployment begins and report both tag and full commit id.
- Build and deploy from a clean checkout of that exact commit, or prove the current checkout and tag resolve to it.
- Re-run environment-specific gates from the same commit.
- On failure, keep the same tag and commit for retries. Do not advance, roll back, or infer another commit without explicit approval.
- Treat branch names, current `HEAD`, timestamps, package versions, and image labels as supporting evidence, not substitutes for the recorded commit id.

Release or deployment authorization applies only to the current request. Do not publish merely because code, a branch, or a tag appears ready.

## Create a Hotfix Lineage

Start from the immutable affected release:

```bash
git switch -c hotfix/v0.31.2 v0.31.2
```

Make and verify the smallest compatible fix on that branch. Give the repaired release a new version and tag according to project policy; never move `v0.31.2` to the repaired commit. Decide separately whether and how the fix returns to `main`, and preserve ancestry or an auditable cherry-pick record.

## Audit History

Check the exact invariants relevant to the task:

```bash
git merge-base --is-ancestor <release-commit> main
git cat-file -t refs/tags/v<version>
git rev-parse main^{commit}
git rev-parse v<version>^{commit}
```

An annotated release tag should report type `tag`; peel it with `^{commit}` before comparing commits. Also inspect whether a higher SemVer tag exists on divergent history, whether the version files at the tag match the release identity, and whether the deployed commit equals the recorded release commit.

If an existing release tag points to a commit outside the integration-branch ancestry, preserve the tag. With current authorization, integrate that exact tagged commit into the primary branch by fast-forward when possible or by the project's explicit merge policy when histories have diverged. Verify ancestry afterward; do not move the old tag or recreate its release commit.

## Handle Failure Safely

- If checks fail before integration, leave `main` and release tags unchanged and preserve the isolated worktree for diagnosis when useful.
- If `main` becomes dirty or moves, stop before integration. Never update its ref underneath the checked-out worktree.
- If integration succeeds but tag creation fails, report that exact partial state; do not create a different commit or version automatically.
- If deployment fails after tagging, keep the immutable tag and retry only the recorded commit.
- Never delete or move a release tag as cleanup without explicit authorization for that exact operation.
