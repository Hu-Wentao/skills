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

Use one parameterized `publish` operation. Its `push` and `reinstall` steps are
both enabled by default and may be disabled independently with `--no-push` or
`--no-reinstall`. Publishing is complete only when every enabled step succeeds.
Reject `--no-push --no-reinstall`. A request that says only sync or push may
use the narrower `sync` workflow and stop after GitHub.

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
When reinstall is enabled, resolve and bind the installation receipt before the
first source mutation. The receipt includes the source repository identity,
installed path, project or global scope, project context, and canonical lock.
Require the lock's source to match the GitHub repository being pushed. A
project installation must be `<project>/.agents/skills/<skill-name>` with a
matching `skills-lock.json` entry. A global installation must be under
`~/.agents/skills/` with a matching shared lock entry. If both installations
are active, stop and remove the unintended scope before publishing. Do not
update unrelated skills.

A project-installed input binds itself automatically. A direct source checkout
must use `--installed-skill <existing-installation>` whenever reinstall remains
enabled. Never infer a global target or create a new installation as a publish
fallback.

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
2. If `scripts/tests/run.py` exists, run it with `uv run --script` before
   staging. Its PEP 723 block owns the complete test environment; do not replace
   it with `uv run python -m unittest discover` or ad hoc `--with` dependencies.
3. Inspect the diff and stage only the intended skill files.
4. Commit the staged skill changes when any exist.
5. Report every existing unpushed commit that the push will also publish. Ask
   before pushing when those commits are outside the user's approved scope.
6. Push the current branch to its configured GitHub upstream without force.
7. Verify that local `HEAD` equals the upstream branch after the push.

The bundled sync command retries a transient `git push` failure three times by
default and retains every attempt's stdout/stderr. Do not create another commit
or switch to an unscoped workflow after the first network failure. Use
`--push-attempts` and `--push-retry-delay` only when the repository requires a
different bounded retry policy.

After resolving preflight findings, use the unified command:

```bash
# Project-installed input: installation ownership is automatic.
uv run python <skill-dir>/scripts/sync_skill_repo.py publish \
  <project-installed-skill-dir>

# Direct source input: bind the existing consumer before pushing.
uv run python <skill-dir>/scripts/sync_skill_repo.py publish \
  <source-repo-skill-dir> \
  --installed-skill <project-installed-skill-dir>
```

Step controls:

```text
--push / --no-push               # default: --push
--reinstall / --no-reinstall     # default: --reinstall
```

Use `--no-reinstall` for a push-only publication. Use `--no-push` for a
reinstall-only recovery only when the local source is clean and exactly equals
the freshly fetched upstream. The command rejects behind, diverged, dirty,
unpushed, source-mismatched, conflicted, unknown, or ambiguous states unless a
narrow documented override applies. It pushes an explicit GitHub upstream ref
and verifies the remote head equals local `HEAD` before reinstalling.

The lower-level `sync` command remains available for a plain project-copy sync
and push without post-push reinstall. Its existing flags and behavior remain
compatible.

### 5. Reinstall and Refresh After Publish

The unified `publish` command runs this step automatically when `reinstall` is
enabled. Use standalone `refresh` only for recovery or maintenance after a
separately verified push. Do not run it for a plain sync or push request.

Follow the owning repository's Node instructions and load its configured nvm
runtime. Never probe the Skills CLI with `skills update --help`: some released
versions interpret it as an unscoped update and may refresh unrelated skills.
Use the bundled deterministic refresh command, which always names exactly one
skill, infers scope from the installed path by default, cross-checks any
explicit scope, rejects active project/global duplicates, retries transient
installer failures, preserves every attempt's output, compares installed paths
and file contents with the pushed source while allowing installer-normalized
executable bits, and verifies the lock hash:

```bash
# Project installation and project skills-lock.json. Run from the project root.
uv run python <skill-dir>/scripts/sync_skill_repo.py refresh \
  <project-installed-skill-dir> \
  --source-skill-dir <source-repo-skill-dir> \
  --scope project --project-root .

# Globally tracked installation. The shared global lock is required.
uv run python <skill-dir>/scripts/sync_skill_repo.py refresh \
  <global-installed-skill-dir> \
  --source-skill-dir <source-repo-skill-dir> \
  --scope global --no-project-context --lock <global-lock-path>
```

Omit `--scope` to use the safe `auto` default. Keep an explicit `--scope` when
recording the intended owner in automation; the helper rejects it when it does
not match the installed path. Pass `--project-root` whenever the operation originates in a consuming project
so duplicate detection can inspect that project even for a requested global
action. A purely global operation with no consuming project must say
`--no-project-context`; global actions without either declaration fail closed.

The helper runs only `pnpm dlx skills update <skill-name> <-p|-g> -y` and
defaults to three attempts with a two-second delay. A failed attempt is not a
reason to run an unscoped update. If all attempts fail, report the exact
command and complete per-attempt output emitted by the helper. Accept the
project lock's 64-character SHA-256 `computedHash` and verify it against the
installed folder contents. Apply the same content verification to a
64-character global `skillFolderHash`; accept a legacy 40-character Git tree
`skillFolderHash` only together with the exact installed/source comparison.

If the skill is not yet tracked in either scope, use the deterministic install
command. Its default `auto` scope follows the expected installed path; an
explicit scope is accepted only when it matches that path. It defaults to the
`codex` agent, never selects every detected agent, and never passes `--copy`,
so global installations remain in the shared `~/.agents/skills` directory:

```bash
# Project installation. Run from the project root.
uv run python <skill-dir>/scripts/sync_skill_repo.py install \
  <owner>/<repo> <project-installed-skill-dir> \
  --source-skill-dir <source-repo-skill-dir> \
  --scope project --project-root .

# Global installation in ~/.agents/skills. Pass the shared global lock.
uv run python <skill-dir>/scripts/sync_skill_repo.py install \
  <owner>/<repo> ~/.agents/skills/<skill-name> \
  --source-skill-dir <source-repo-skill-dir> \
  --scope global --no-project-context --lock ~/.agents/.skill-lock.json
```

Use `--agent <agent-id>` only when the user explicitly requests a consumer
other than Codex. Never use `--agent '*'`. A PromptScript global-install error
means the agent target was left implicit or broadened incorrectly. Treat
`EPERM`, `EACCES`, and equivalent filesystem permission failures as
non-retryable; report the exact command for execution in a terminal that can
write the target directory.

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
