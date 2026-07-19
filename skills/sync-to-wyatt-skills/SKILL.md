---
name: sync-to-wyatt-skills
description: Sync a reusable project-level Codex skill into the local wyatt_skills repository, validate it, commit only that skill, and push the current branch. Use when the user says a skill created inside another project should be published, shared, moved, copied, or synchronized to wyatt_skills, especially requests such as “把这个项目 skill 同步到 wyatt_skills 并 push”.
---

# Sync To Wyatt Skills

Publish one reusable project skill to the `wyatt_skills` repository without mixing unrelated work.

## Defaults

- Destination repository: `/Users/wyatt/_proj/wyatt_skills`
- Destination directory: `<repo>/skills/<source-folder-name>`
- Commit message: `feat: sync <skill-name> skill`
- Push target: the current branch's configured upstream
- Excluded source files: `.git`, `.DS_Store`, `dist`, `node_modules`,
  `.ruff_cache`, `__pycache__`, and `*.pyc`

Allow the user to override the repository path or commit message explicitly. Never force-push.

## Workflow

### 1. Resolve the source

Accept an absolute or project-relative skill directory. If the user provides only a skill name, search the current project before asking:

```bash
find . -type f -name SKILL.md -path "*/<skill-name>/SKILL.md"
```

Require exactly one source directory and a `SKILL.md` inside it. Read its frontmatter and verify that `name` equals the source folder name. Stop if the source is inside the destination repository; this skill is for publishing a skill from another project.

### 2. Inspect Git state

Run the bundled script in dry-run mode first:

```bash
scripts/sync_to_wyatt_skills.sh <source-directory> --dry-run
```

Also inspect the source repository with `git status --short` when the source belongs to a Git worktree.

- If the source skill itself has uncommitted changes, tell the user and confirm that those changes are the version to publish.
- If the destination repository is dirty, follow the active project's `AGENTS.md`. For unrelated changes, ask the user to choose `先提交` or `先忽略`.
- `先提交`: commit the existing destination changes separately, then rerun the dry run.
- `先忽略`: leave them untouched and invoke the script with `--allow-dirty`; the script stages only the synchronized skill directory.
- If existing dirty changes overlap `skills/<skill-name>`, do not treat them as ignorable. Ask whether they belong to this publication or must be committed separately.

Report when the destination branch already has unpushed commits, because pushing the branch will publish those commits too.

### 3. Review synchronization

Inspect the dry-run file list and destination diff. The script copies source files without deleting destination-only files. If a destination-only file is clearly an obsolete part of the same skill, remove it explicitly with `apply_patch`; otherwise preserve it and mention it.

Do not copy project secrets, environment files, caches, dependency folders, or unrelated project documentation.

### 4. Publish

After resolving preflight findings, run:

```bash
scripts/sync_to_wyatt_skills.sh <source-directory>
```

Optional flags:

```bash
--repo <path>
--message <commit-message>
--allow-source-dirty
--allow-dirty
--dry-run
```

Use `--allow-source-dirty` only after the user confirms publishing an uncommitted source version. Use `--allow-dirty` only after the user chooses `先忽略` and no dirty file overlaps the destination skill.

The script must validate the copied skill, stage only its directory, commit it, and push the current branch. If there is no synchronized diff, report that nothing needs publishing and do not create an empty commit.

### 5. Report

Report:

- source and destination paths
- validation result
- copied or changed files
- commit SHA and message
- pushed branch and upstream
- any preserved destination-only files

List breaking changes and compatibility configuration. If there are none, say so explicitly.

## Resource

- `scripts/sync_to_wyatt_skills.sh`: preflight, copy, validate, stage, commit, and push one skill safely.
