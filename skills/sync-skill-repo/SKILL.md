---
name: sync-skill-repo
description: Publish a shared Codex skill to GitHub, then refresh that exact named skill through the Skills CLI update workflow and verify its project and global lock-managed installations. If the skill is already in its shared source repository, validate it, commit only the intended skill changes, and push the current branch. If it is a lock-managed project installation, synchronize it to its registered source repository first. Use when the user asks to publish a shared skill, `publish-skill`, "发布技能", push, return, or synchronize shared skill changes. Reject project-private sources and project-owned skills-config targets; ordinary project-private revisions stay in the owning project's local Git/worktree workflow.
---

# Publish or Sync a Skill

Publish one local skill to its GitHub source repository without mixing unrelated
work.

## Meaning of Revision

Use `skillcraft` to classify ownership before revision. For shared direct source
or a valid lock-managed project installation, treat a request to revise,
improve, update, or "修订" as authorization to modify and validate the skill,
then publish it with the full named-update workflow. Before taking task actions,
tell the user exactly:

`修订技能后将推送远端并 update。`

For a project-private source at
`<project-root>/.agents/skills/<skill-name>` without a matching project lock,
do not invoke this skill during ordinary revision. Keep the work in the owning
project's local Git/worktree workflow with no push and no Skills CLI update.

## Meaning of Publish

Treat `publish-skill`, "发布技能", and equivalent requests as instructions to:

1. push the local skill to GitHub;
2. run `skills update <skill-name> -y` after the push; and
3. verify every matching project or global lock-managed installation.

Use one parameterized `publish` operation. Its `push` and `reinstall` steps are
both enabled by default and may be disabled independently with `--no-push` or
`--no-reinstall`. Here, `reinstall` means the named Skills CLI update, not a
manual path-based installation. Publishing is complete only when every enabled
step succeeds. Reject `--no-push --no-reinstall`. A request that says only sync
or push may use the narrower `sync` workflow and stop after GitHub.

## Installation Ownership

Inspect both the logical input path and its resolved location before checking
GitHub upstreams. Either location can establish a protected project ownership
boundary:

- A valid matching entry in a regular, non-symlink
  `<project>/skills-lock.json` owns a project-scoped lock-managed installation
  and takes precedence over direct-source detection.
- `<project>/.agents/skills/<skill-name>` without a matching project lock entry
  is project-private source owned by that project repository. Stop before
  registry lookup, commit, push, global-lock binding, or named update and direct
  ordinary revision to the project's Git/worktree workflow.
- A raw matching project lock entry whose version, entry, or source is invalid
  or incomplete, or whose present `skillPath` is invalid, is ambiguous or
  corrupt. Fail closed instead of falling back to project-private or
  direct-source handling. A missing `skillPath` is a supported legacy fallback
  only for resolving a sync destination; it is not eligible for named update.
- `$XDG_STATE_HOME/skills/.skill-lock.json` owns a global installation when
  `XDG_STATE_HOME` is set; otherwise `~/.agents/.skill-lock.json` does.
- A same-name global lock never changes project-private ownership.
- `<project>/.agents/skills-config/<skill-name>` is project-owned configuration,
  not a skill publication target.

Do not classify a skill as global merely because discovery finds it under a
shared skill directory or because `~/.agents/skills/<name>` is a symlink. A
project-owned source linked there without a matching global lock entry is not a
global installation for this workflow: reject its publication as
project-private, and never update it through the global scope.

A named `skills update <skill-name>` checks matching entries in both the current
project lock and the global lock. This is intentional: update every tracked
installation of that exact skill, but no unrelated skill. Do not require the
caller to provide an installed-skill path or select project/global scope.

When named update is enabled and neither lock tracks a shared skill, stop before
mutating the source. A first-time installation is separate from publishing and
must be performed once with `skills add`; `skills update` must not be replaced
with a guessed path install.

## Source Registry

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

### 1. Resolve the Local Skill and Update Context

Accept an absolute or project-relative directory containing `SKILL.md`. Verify
that its frontmatter `name` equals the folder name.

Classify the logical and resolved paths before source detection:

1. If either location is a project-private source or a `skills-config` target,
   stop with the ownership guidance above, even when
   `--repo` or `--destination` is supplied. This includes a shared-directory
   alias that resolves into a project-private source.
2. If it has a valid matching project lock, use the lock-managed project-copy
   workflow even when the resolved symlink target is tracked in a GitHub repo.
3. Otherwise, if its Git worktree has a GitHub upstream and the skill is tracked
   there, use the shared direct-source workflow.
4. Otherwise, resolve a registered source checkout or require an explicit
   destination for a non-project-owned lockless copy.

Never infer that a non-GitHub remote satisfies a request to publish to GitHub.
Validate every present project-lock `skillPath` before registry lookup or copy:
require a safe relative path ending in `<skill-name>/SKILL.md` and reject every
case-insensitive `.git` path component. When named update is enabled, bind
matching lock entries
before the first source mutation and require each lock source and `skillPath` to
match the GitHub repository and skill path being pushed. Match Skills CLI's lock
eligibility: project locks require numeric `version >= 1`, global locks require
numeric `version >= 3`, and an entry without `skillPath` is not updateable.

Choose the project context in this order:

1. `--project-root`, when explicitly supplied;
2. the owning project of a lock-managed project input;
3. the caller's current working directory for a direct-source input.

The project context only selects the project lock visible to Skills CLI. The
global lock is always checked automatically.

### 2. Resolve a Lock-Managed Copy's Source Checkout

Skip this step for the direct-source workflow.

Run a dry run first:

```bash
uv run python <skill-dir>/scripts/sync_skill_repo.py sync \
  <project-skill-dir> --dry-run
```

By default, resolve the destination deterministically:

1. Find the nearest `skills-lock.json` within the project Git worktree.
2. Read the matching skill's `source` and optional `skillPath`.
3. Match `source` against the local registry.
4. Use the directory containing `skillPath`, or `skills/<skill-name>` when the
   lock entry omits `skillPath`.

If the input is a non-project-owned lockless copy, require both `--repo <path>`
and, when the source repository does not use `skills/<skill-name>`,
`--destination <relative-path>`. Never guess between repositories or accept a
destination escaping its Git root. These flags must not override project-private
ownership or a matching project lock. Extracting a project-private skill into a
shared repository is a separate explicit migration task, not `sync` or
`publish`.

### 3. Inspect Git State

Inspect the relevant worktrees and exact GitHub upstream URL.

- In the direct-source workflow, inspect all worktree changes and stage only the
  intended skill paths. Follow repository governance for unrelated work.
- For a lock-managed copy, inspect the dry-run changes. If it has uncommitted
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
2. If `scripts/tests/run.py` exists, run it with `uv run --script` before
   staging. Its PEP 723 block owns the complete test environment.
3. Inspect the diff and stage only the intended skill files.
4. Commit the staged skill changes when any exist.
5. Report every existing unpushed commit that the push will also publish. Ask
   before pushing when those commits are outside the approved scope.
6. Push the current branch to its configured GitHub upstream without force.
7. Verify that local `HEAD` equals the upstream branch after the push.

The bundled command retries a transient `git push` failure three times by
default and retains every attempt's stdout/stderr. Do not create another commit
or switch to an unscoped workflow after the first network failure.

Use the unified command after resolving preflight findings:

```bash
# Direct source; no installed path or scope is required.
uv run python <skill-dir>/scripts/sync_skill_repo.py publish \
  <source-repo-skill-dir>

# Lock-managed project input; its owning project becomes update context.
uv run python <skill-dir>/scripts/sync_skill_repo.py publish \
  <lock-managed-project-skill-dir>
```

For a direct-source publish launched outside the consuming project, identify the
project lock context without identifying an installation path:

```bash
uv run python <skill-dir>/scripts/sync_skill_repo.py publish \
  <source-repo-skill-dir> --project-root <consumer-project>
```

Step controls:

```text
--push / --no-push               # default: --push
--reinstall / --no-reinstall     # default: --reinstall (named update)
```

Use `--no-reinstall` for a push-only publication. Use `--no-push` for an
update-only recovery only when local source is clean and exactly equals the
freshly fetched upstream. The lower-level `sync` command remains available for
a plain project-copy sync and push without post-push update.

### 5. Refresh Through Skills CLI Update

The unified `publish` command runs this step automatically when reinstall is
enabled. It invokes only:

```bash
pnpm dlx skills update <skill-name> -y
```

Always name exactly one skill. Do not add `-p` or `-g`: with a skill-name
filter, Skills CLI checks both matching lock scopes and updates only that skill.
Do not use `skills add` as a post-publish reinstall and do not ask for an
installed-skill path.

Follow the owning repository's Node instructions and load its configured nvm
runtime. Retry transient installer failures with a bounded count and preserve
every attempt's output. Treat a zero exit followed by stale content or lock
verification as a failed attempt, because Skills CLI may report a fetch failure
without returning a nonzero status. Treat `EPERM`, `EACCES`, and equivalent
filesystem permission failures as non-retryable.

After update succeeds:

1. compare every lock-managed installed folder with the pushed source, excluding
   generated caches and allowing installer-normalized executable bits;
2. verify the matching lock hash;
3. preserve unrelated worktree changes.

A discovered path without a matching lock entry is outside this verification
set. If push succeeds but named update or verification fails, report the
outcomes separately and do not claim that publishing completed.

### 6. Report

Report source and destination paths, registry/lock resolution, validation,
changed and preserved files, commit SHA and message, pushed branch/upstream,
breaking changes, and compatibility configuration. For publishing, also report
the exact named update command, every refreshed lock scope, installed/source
comparison, refreshed lock hashes, and any consuming-repository changes or
commit.

## Resources

- `scripts/sync_skill_repo.py`: register source checkouts, synchronize one
  skill, publish it, run its named Skills CLI update, and verify matching locks.
- `scripts/tests/test_sync_skill_repo.py`: focused registry, resolution, publish,
  named-update, ownership, and copy-plan tests.
