# Authorization and Host Safety

## Contracted writes

Treat `inspect`, `plan`, and `verify` as read-only. Every remote write, reload, policy save, DNS mutation, migration, or rollback normally requires a project-configured operation and current authority for its exact target. `--authorized` is a mechanical runner gate, not proof of intent. Keep billable, destructive, privileged, identity-changing, and materially broader effects as separate boundaries.

A project contract may require sensitive environment variables from approved environment or keychain sources. Resolve values only into the child process. Never place them in argv, output, cache, journal, logs, or responses.

## One-round emergency manual authorization

When the current user explicitly states `授权手动进行紧急操作` or an unambiguous equivalent, grant one emergency manual-operation round for the current bounded task. Multiple tool calls needed for that same task are covered, but the exception ends when the task completes, blocks, or control returns to the user.

Limit the round to the exact target, actions, and material effects in the request and accepted plan. Prefer an available governed operation. Never turn the exception into a persistent arbitrary-command capability. Before mutation, inspect exact state, establish recovery, preserve secret-safe evidence, verify each effect, and report every manual change. A later turn or new task requires the authorization again.

## Conversation-scoped SSH

When the user states `本次对话允许执行SSH读写` or equivalent, treat it as standing SSH authorization for the current conversation, task, and established targets. Do not request per-command or per-turn SSH approval. Preserve contracts, alias and target validation, locks, secret handling, verification, and rollback requirements.

SSH authorization does not independently authorize a provider API or console, browser credential access, local identity change, release, deployment, billable action, destructive outcome, different host, or new task. Ask only when target, task boundary, or material effect remains ambiguous. Expire the authorization when the task completes, the conversation ends, or the user narrows it.

## Identity and bootstrap

Treat device ID, hostname, direct target, SSH alias, port, and jump alias as distinct. Use only authoritative manifest or fixed-contract values. Never guess an SSH alias or bypass a declared jump route.

Password bootstrap must use a hidden prompt or approved secret source for the first connection only. Never persist, echo, recover from browser state, or place a password in argv. If unavailable, report blocked; do not imply authentication was attempted. Disable remote PTY allocation, wait for an authenticated remote-ready marker, send an explicit remote exit, and distinguish pre-auth closure from rejected credentials.

Keep the old listener and key until a fresh administrator-key connection succeeds on the desired port and password/prohibited root login rejection is verified. Include `ssh.socket` overrides when systemd socket activation owns listeners. Local SSH config and key changes are explicit local operations; report filesystem permission blockers instead of implying success.

## Product invariants

- Tailscale interactive enrollment must return the exact `https://login.tailscale.com/a/...` URL immediately, retain `awaiting-tailnet-auth`, never persist the URL, and resume only after live node identity verification. A missing contracted interactive operation is a blocker.
- PostgreSQL parameters require the hardware-aware workflow in `postgresql.md`; a shared host defaults to the conservative eligible option. Startup success alone never selects a larger profile.
- Docker installation must verify package ownership, daemon and Compose readiness, cgroups, smoke cleanup, listeners, firewall exposure, bounded BuildKit cleanup, and recovery. Docker group membership is root-equivalent access.
- Docker storage cleanup is a separately authorized incident workflow. `dangling` never proves disposable; preserve named volumes and prohibit broad prune or data-root deletion.
- Jenkins host state includes controller, plugins, agents, credentials, jobs, backups, upgrades, and shared runtime. Never adopt another application’s signing identity to make a build pass.
- A public Cloudflare application is one coupled origin, connector, tunnel, proxied DNS, Access application, and policy transaction. Partial configuration is not published or protected.

## Transaction integrity

Use one host-owned serialized transaction for each shared-resource mutation. Record a stable transaction ID, owner, target, base/result generation, desired and candidate digests, phase, and verification state without private configuration. Re-read authority and live state under lock. Reject stale plans, overlapping hostnames/listeners/routes/selectors/resource IDs, and changed candidates.

Generate the complete combined plan before mutation. Snapshot the exact current resource and tested recovery path. Apply one bounded component at a time, stop forward progress on failure, and resume only through the recorded transaction state. Verify required flows positively and forbidden flows negatively. Never broaden access merely to make verification pass.
