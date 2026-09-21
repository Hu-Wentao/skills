---
name: sync-skill-repo
description: Hidden compatibility backend for publishing explicitly selected shared skills. Deterministic batch validation, testing, exact-path commit and push, named Skills CLI updates, and lock verification. Private-host mode publishes project-private skills to a designated private source repository.
disable-model-invocation: true
---

# Sync Skill Repo Backend

Use `skillcraft` for ownership and revision decisions. This hidden skill preserves explicit compatibility and owns only deterministic publication mechanics.

## Canonical batch command

```bash
uv run python <skill-root>/scripts/sync_skill_repo.py publish-batch \
  --repo <source-repository> \
  --skill <name> [--skill <name> ...] \
  [--include-path <explicit-path>] \
  [--project-root <consumer-project>] \
  [--expected-upstream-head <sha> --expected-source-head <sha>]
```

The runner validates budgets and references, runs each `scripts/tests/run.py`, stages only explicit paths, creates at most one commit, pushes once, runs `pnpm dlx skills update <name> -y` once per name from a neutral cwd, verifies matching installations and locks, and emits `sync-skill-repo.publish-receipt.v2` JSON.

Existing ahead commits require both exact head arguments. Input under `package/node_modules`, project-private source, `skills-config`, ambiguous locks, unrelated dirty paths, non-GitHub upstreams, stale heads, or missing update locks fails closed. A push followed by update failure returns `completed: false`.

## Private-host mode

```bash
uv run python <skill-root>/scripts/sync_skill_repo.py publish-batch \
  --repo <private-source-checkout> \
  --skill <name> [--skill <name> ...] \
  --private-host <git-host> \
  [--install-root <project>/.agents/skills]
```

`--private-host` authorizes exactly one non-GitHub Git host (for example an internal GitLab). The source repository origin and pushable upstream must both live on that host; anything else still fails closed. This mode exists for project-private skills whose owning project designates an independent private source repository tracked at `skills/<name>`. The Skills CLI update and lock verification are structurally unavailable on private hosts, so `--reinstall` semantics change: each `--install-root` receives an exact mirror of every published skill, verified entry by entry. Without `--install-root` the receipt records `not_managed_private` updates. `--project-root` cannot combine with `--private-host`.

## Compatibility commands

- `register <repo>`: register a local shared source checkout.
- `publish <skill-dir>`: one-skill compatibility publication.
- `sync <skill-dir>`: copy a valid lock-managed skill to registered source.
- `refresh` and `install`: explicit recovery/first-install compatibility operations.

Do not use compatibility commands to bypass `skillcraft` ownership classification.

## Resource

- `scripts/sync_skill_repo.py`: canonical publisher and compatibility backend.
- `scripts/tests/run.py`: complete backend test entry point.
