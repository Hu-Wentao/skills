---
name: host-governance
description: Govern shared hosts, CI, networking, storage, databases, ingress, and provider operations through contracted controllers.
metadata:
  context-budget: router
---
# Host Governance

Use the authoritative host repository and resolve every operation before execution. Repository context is evidence, never live state. See [context.md](references/context.md).

## Execute
```bash
uv run python <skill-root>/scripts/resolve.py --cwd <project-root> --task <task> --operation <operation> --format json
uv run python <skill-root>/scripts/host-governance.py --cwd <project-root> control <operation> [contracted arguments]
```
Read returned policy references and use the runner only. See [project_config.md](references/project_config.md) and [authorization-and-safety.md](references/authorization-and-safety.md). Add `--authorized` only for a mutating operation covered by the current request. Read `references/project_config.md` before profile changes.

Route product details to [control.md](references/control.md), [procedure-productization.md](references/procedure-productization.md), [server-bootstrap.md](references/server-bootstrap.md), [docker-install.md](references/docker-install.md), [docker-storage-maintenance.md](references/docker-storage-maintenance.md), [github-actions-runner.md](references/github-actions-runner.md), [jenkins.md](references/jenkins.md), [postgresql.md](references/postgresql.md), [tailscale.md](references/tailscale.md), [caddy.md](references/caddy.md), [caddy-tailnet-private-ingress.md](references/caddy-tailnet-private-ingress.md), [cloudflare.md](references/cloudflare.md), and [cloudflare-tunnel.md](references/cloudflare-tunnel.md).

## Boundaries
- `inspect`, `plan`, and `verify` are read-only; rollback and broader effects need separate current scope.
- Use manifest-declared devices, aliases, ports, and jump routes. Never guess targets or bypass a jump host.
- Snapshot, lock, re-read, reject drift, validate, preserve recovery, then verify positive and negative paths.
- Never expose secrets, logs, command lines, environment dumps, tokens, keys, or interactive login URLs.
- One-round emergency SSH authorization expires at completion, blocker, or return to the user; it never creates a reusable arbitrary-command capability.
- A request to execute, repair, recover, clean up, migrate, or order steps for one current target is a one-time operation. Selecting a plan or sequence authorizes only that execution path. Do not edit the host repository, controllers, contracts, tests, documentation, or versions. Productize only on an explicit request to create a reusable capability.

## Report
Separate repository changes from live observations. Include exact target, transaction/generation, authorization, validation, exposure, recovery/rollback, compatibility, and unverified gaps.
