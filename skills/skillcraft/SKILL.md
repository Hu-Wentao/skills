---
name: skillcraft
description: >-
  Create or revise reusable and project-private skills. Use for skill design, initialization, validation, progressive disclosure, profiles, forward tests, or “修订技能”. Revisions publish by default: shared skills use the canonical runner and named update; project-private skills validate, commit, and push through the owning project.
metadata:
  context-budget: router
---

# Skillcraft

Own the model-facing semantics for skill creation and revision. Keep authoring judgment here; delegate publication mechanics to the hidden `sync-skill-repo` runner.

## Classify Ownership

Inspect both the logical path and resolved path before editing:

- `<project>/.agents/skills/<name>` with a valid matching project `skills-lock.json` entry is a lock-managed shared installation.
- The same path without a matching lock entry is project-private source owned by that project.
- Tracked `skills/<name>` in an independent source repository is shared direct source.
- `<project>/.agents/skills-config/<name>` is project configuration, never a publication target.
- Invalid matching lock data is ambiguous: stop instead of falling back.

Read [ownership-and-publication.md](references/ownership-and-publication.md) for symlinks, registries, first publication, and migration cases.

## Create or Revise

1. Confirm concrete trigger examples, ownership, authority, and the smallest useful capability.
2. Inspect existing source, tests, neighboring skills, repository rules, and installed metadata.
3. Keep non-obvious workflow in `SKILL.md`; move tutorials, matrices, schemas, examples, and product details into directly linked `references/`; put deterministic repeated work in tested `scripts/`.
4. Initialize new skills with `scripts/init_skill.py`; update `agents/openai.yaml` from the final behavior.
5. Validate the exact skill and run its test runner when present.
6. Forward-test only when behavior is complex or evidence is otherwise insufficient.
7. Deliver according to ownership.

Read [authoring.md](references/authoring.md) for frontmatter, default paths, structure, and progressive disclosure. Read [validation-and-forward-testing.md](references/validation-and-forward-testing.md) for validation and evaluation rules. For repository-specific profiles, read [project_config.md](references/project_config.md). For UI metadata, read [openai_yaml.md](references/openai_yaml.md).

## Deliver by Ownership

### Shared source or lock-managed installation

A request to revise, improve, update, or “修订” authorizes the complete revision-and-publication transaction unless the user explicitly says local-only, no push, or no update. Before editing, state:

`修订技能后将推送远端并 update。`

Use the canonical runner once for every explicit skill in the same source repository:

```bash
uv run python <sync-skill-repo-root>/scripts/sync_skill_repo.py publish-batch \
  --repo <source-repository> \
  --skill <skill-name> [--skill <skill-name> ...] \
  [--include-path <explicit-index-path>] \
  [--project-root <consumer-project>] \
  [--expected-upstream-head <sha> --expected-source-head <sha>]
```

The runner owns context-budget validation, skill tests, exact-path staging, one commit and push, per-name `pnpm dlx skills update <name> -y` from a neutral cwd, installation/lock verification, and the structured receipt. Exact head arguments authorize only an already reviewed ahead range, such as a worktree merge; never replace them with a broad “allow unpushed” decision.

Do not report completion unless the receipt has `completed: true`. A successful push followed by failed update or verification is incomplete.

### Project-private source

Unless the user explicitly requests local-only or no-push, a revision authorizes validation, tests, commit, and remote push through the owning project’s own Git/worktree rules. Do not invoke the shared publication runner, source registry, Skills CLI update, or migrate the skill to shared ownership.

## Safety and Completion

- Never publish `skills-config`, generated cache, secrets, dependency trees, build output, or input resolved through `package/node_modules`.
- Stage only explicit skill and index paths; preserve unrelated work.
- Treat external mutation, first-time installation, repository creation, ownership migration, and destructive cleanup as separate authority.
- Keep references one level below `SKILL.md` and directly linked; reject missing links.
- Report modified paths, validation and tests, budget statistics, exact commit and remote heads, update scopes, compatibility or breaking effects, and any incomplete phase.
