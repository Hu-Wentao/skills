---
name: sync-skill-repo
description: Publish a local Codex skill to GitHub, then automatically reinstall that exact skill and refresh its project or global lock metadata. If the skill is already in its source repository, validate it, commit only the intended skill changes, and push the current branch. If it is a project-local installed copy, synchronize it to its registered source repository first. Use when the user asks to publish a skill, `publish-skill`, "发布技能", push, return, or synchronize skill changes. A publish request includes the post-push reinstall; a plain sync or push request may stop after GitHub.
---

# Publish or Sync a Skill

Publish one local skill to its GitHub source repository without mixing unrelated work.

## Meaning of Publish

Treat `publish-skill`, "发布技能", and equivalent requests as instructions to:

1. push the local skill to GitHub;
2. automatically reinstall that exact skill from the pushed source; and
3. refresh and verify its matching project or global lock entry.

Publishing is complete only when both the GitHub push and post-push refresh
succeed. A request that says only sync or push may stop after GitHub.

## Source registry

Keep machine-specific repository locations in
`${CODEX_HOME:-$HOME/.codex}/skill-source-repositories.json`. Never add this
file to a project repository.

Resolve `<skill-dir>` from this active skill's `SKILL.md` location before
running its bundled script; do not assume the current project is the skill
installation directory.

Register each local source checkout once:

```bash
uv run python <skill-dir>/scripts/sync_skill_repo.py register <repository-path>
```

Use `--source <id>` when the repository has no usable `origin`, and repeat
`--alias <id>` for historical or alternate `skills-lock.json` source names.
Registration validates that the path is a Git worktree root.

## Workflow

### 1. Resolve the local skill

Accept an absolute or project-relative directory containing `SKILL.md`. Verify
that its frontmatter `name` equals the folder name.

Determine whether the skill is already inside its source Git checkout:

- If its Git worktree has a GitHub upstream and the skill is tracked there,
  use the direct-source workflow.
- Otherwise, treat it as a project-local installed copy and resolve its
  registered source checkout.

Never infer that a non-GitHub remote satisfies a request to publish to GitHub.
Before pushing, identify the post-publish installation scope: prefer the
originating project with a matching `skills-lock.json` entry; otherwise use the
matching globally tracked installation. Do not update unrelated skills.

### 2. Resolve an Installed Copy's Source Checkout

Skip this step for the direct-source workflow.

Run a dry run first:

```bash
uv run python <skill-dir>/scripts/sync_skill_repo.py sync <project-skill-dir> --dry-run
```

By default, resolve the destination deterministically:

1. Find the nearest `skills-lock.json` within the project Git worktree.
2. Read the matching skill's `source` and optional `skillPath`.
3. Match `source` against the local registry.
4. Use the directory containing `skillPath`, or `skills/<skill-name>` when the
   lock entry omits `skillPath`.

If the lock entry is absent, require both `--repo <path>` and, when the source
repository does not use `skills/<skill-name>`, `--destination <relative-path>`.
Never guess between repositories or accept a destination escaping its Git root.

### 3. Inspect Git State

Inspect the relevant worktrees and the exact GitHub upstream URL.

- In the direct-source workflow, inspect all worktree changes and stage only
  the intended skill paths. Follow repository governance for unrelated work.
- For an installed copy, inspect the dry-run changes. If it has uncommitted
  changes, confirm that this is the version to publish, then use
  `--allow-source-dirty`.
- If the source repository has unrelated changes, follow its `AGENTS.md` and
  ask the user to choose `先提交` or `先忽略`.
- For `先忽略`, use `--allow-dirty`; never allow existing dirty changes that
  overlap the destination skill.
- Report existing unpushed source-repository commits because the final push
  will publish them too.

Installed-copy synchronization preserves destination-only files. Remove an
obsolete destination-only file explicitly only after reviewing it. Exclude Git
metadata, secrets, caches, dependency folders, and build output.

### 4. Validate, Commit, and Push

For a skill already in its source checkout:

1. Validate it with the installed `skillcraft` validator.
2. Inspect the diff and stage only the intended skill files.
3. Commit the staged skill changes when any exist.
4. Report every existing unpushed commit that the push will also publish. Ask
   before pushing when those commits are outside the user's approved scope.
5. Push the current branch to its configured GitHub upstream without force.
6. Verify that local `HEAD` equals the upstream branch after the push.

The bundled sync command retries a transient `git push` failure three times by
default and retains every attempt's stdout/stderr. Do not create another commit
or switch to an unscoped workflow after the first network failure. Use
`--push-attempts` and `--push-retry-delay` only when the repository requires a
different bounded retry policy.

For a project-local installed copy, synchronize and publish with:

After resolving preflight findings, run:

```bash
uv run python <skill-dir>/scripts/sync_skill_repo.py sync <project-skill-dir>
```

Optional flags:

```text
--repo <path>
--destination <relative-path>
--registry <path>
--message <commit-message>
--allow-source-dirty
--allow-dirty
--dry-run
--push-attempts <count>
--push-retry-delay <seconds>
```

The script copies the skill, validates it with the installed `skillcraft`,
stages only the destination skill, commits it, and pushes the current branch.
It never force-pushes. If content is unchanged, it creates no commit; push any
already-approved unpushed commits separately when needed.

### 5. Reinstall and Refresh After Publish

Run this step automatically after a successful `publish-skill` or "发布技能"
push. Do not run it for a plain sync or push request.

Follow the owning repository's Node instructions and load its configured nvm
runtime. Never probe the Skills CLI with `skills update --help`: some released
versions interpret it as an unscoped update and may refresh unrelated skills.
Use the bundled deterministic refresh command, which always names exactly one
skill, retries transient installer failures, preserves every attempt's output,
compares installed paths and file contents with the pushed source while
allowing installer-normalized executable bits, and verifies the lock hash:

```bash
# Project installation and project skills-lock.json. Run from the project root.
uv run python <skill-dir>/scripts/sync_skill_repo.py refresh \
  <project-installed-skill-dir> \
  --source-skill-dir <source-repo-skill-dir> \
  --scope project --project-root .

# Globally tracked installation. Pass --lock when a global lock file exists.
uv run python <skill-dir>/scripts/sync_skill_repo.py refresh \
  <global-installed-skill-dir> \
  --source-skill-dir <source-repo-skill-dir> \
  --scope global [--lock <global-lock-path>]
```

The helper runs only `pnpm dlx skills update <skill-name> <-p|-g> -y` and
defaults to three attempts with a two-second delay. A failed attempt is not a
reason to run an unscoped update. If all attempts fail, report the exact
command and complete per-attempt output emitted by the helper.

If the skill is not yet tracked in either scope, install only that skill from
the pushed GitHub repository into the intended scope:

```bash
pnpm dlx skills add <owner>/<repo> --skill <skill-name> -g -y
```

Never run an unscoped `skills update`; it can update unrelated skills. After
the command succeeds, compare the installed skill with the pushed source,
excluding generated caches, and verify that the matching lock entry contains
the refreshed content hash. Preserve unrelated worktree changes.

If the push succeeds but reinstall or lock refresh fails, report the outcomes
separately and do not claim that publishing completed.

### 6. Report

Report source and destination paths, registry/lock resolution, validation,
changed and preserved files, commit SHA and message, pushed branch/upstream,
breaking changes, and compatibility configuration. For publishing, also report
the scoped installer command, installed/source comparison, refreshed lock hash,
and any consuming-repository changes or commit.

## Resources

- `scripts/sync_skill_repo.py`: register source checkouts and safely synchronize
  one skill, then retry and verify its scoped post-publish refresh.
- `scripts/tests/test_sync_skill_repo.py`: focused registry, resolution, and
  copy-plan tests.
