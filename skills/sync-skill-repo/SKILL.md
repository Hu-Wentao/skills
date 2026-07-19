---
name: sync-skill-repo
description: Sync a Codex skill updated inside a consuming project back to its registered local source repository, validate it with skillcraft, commit only that skill, and push the source branch. Use when the user asks to publish, return, or synchronize project-local skill changes to the skill's source repository, including skills installed through skills-lock.json.
---

# Sync Skill Repo

Synchronize one project-local skill back to its local source checkout without mixing unrelated work.

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

### 1. Resolve the project skill

Accept an absolute or project-relative directory containing `SKILL.md`. Verify
that its frontmatter `name` equals the folder name.

### 2. Resolve its source checkout

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

### 3. Inspect Git state

Inspect the dry-run changes and both worktrees.

- If the project skill has uncommitted changes, confirm that this is the
  version to publish, then use `--allow-source-dirty`.
- If the source repository has unrelated changes, follow its `AGENTS.md` and
  ask the user to choose `先提交` or `先忽略`.
- For `先忽略`, use `--allow-dirty`; never allow existing dirty changes that
  overlap the destination skill.
- Report existing unpushed source-repository commits because the final push
  will publish them too.

Synchronization copies new and changed files while preserving destination-only
files. Remove an obsolete destination-only file explicitly only after reviewing
it. Exclude Git metadata, secrets, caches, dependency folders, and build output.

### 4. Synchronize

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
```

The script copies the skill, validates it with the installed `skillcraft`,
stages only the destination skill, commits it, and pushes the current branch.
It never force-pushes. If content is unchanged, it creates no commit.

### 5. Report

Report source and destination paths, registry/lock resolution, validation,
changed and preserved files, commit SHA and message, pushed branch/upstream,
breaking changes, and compatibility configuration.

## Resources

- `scripts/sync_skill_repo.py`: register source checkouts and safely synchronize
  one skill.
- `scripts/tests/test_sync_skill_repo.py`: focused registry, resolution, and
  copy-plan tests.
