# Caddy Control

Use this reference for Caddyfile, native JSON, reverse-proxy, TLS, listener, and
admin API changes.

## Inspect

1. Identify the target device, installation type, running version, service
   manager, effective configuration source, import graph, and admin endpoint.
2. Read the complete effective configuration and locate every existing owner of
   the requested hostname and listener.
3. Confirm the upstream bind address, protocol, port, and health response from
   the Caddy host. Do not expose an application that is only accidentally
   reachable.
4. Snapshot the exact source configuration and current live configuration
   without printing secrets or environment values.

## Plan

- Give each service an independently owned fragment when the existing layout
  supports imports. Do not let a consuming project own the shared root file.
- Preserve the established file-based or API-based workflow. Do not mix control
  methods without an explicit migration plan.
- Detect duplicate site addresses, wildcard overlap, listener collision,
  redirect loops, certificate ownership conflicts, and incompatible matchers.
- State whether automatic HTTPS requires public DNS, a DNS challenge provider,
  or a private trust path.

## Apply

1. Acquire the host-owned transaction lock and re-read the authoritative
   declarations, effective source configuration, and live generation. Never
   reuse the complete candidate produced by an earlier unlocked plan.
2. Update only the selected owner's independently identified fragment or
   declaration, then render and review the complete candidate configuration.
3. Run `caddy adapt --validate` or `caddy validate` with the same adapter,
   environment-file contract, modules, paths, and runtime identity as the real
   service. Successful adaptation alone is insufficient.
4. Apply through the established zero-downtime reload or admin API workflow.
   Do not stop and restart Caddy merely to load configuration.
5. If the reload fails, restore the transaction's prior source generation,
   preserve the active prior configuration, record the failed phase, and
   diagnose before another mutation.

The application deployer must not write or restore the shared root file, reload
Caddy directly, or hold a historical monolithic Caddyfile as its rollback
artifact. Rollback submits the prior project declaration through a new
host-owned transaction that recomposes every current owner.

## Verify

- Inspect the running configuration after reload.
- Probe the intended hostname with correct DNS, SNI, scheme, and network source.
- Check the upstream health path and relevant logs without dumping secrets.
- Verify an unintended hostname or unauthorized network source is not accepted.
- Confirm certificate issuance or trust separately from HTTP routing.

Official behavior changes over time. Verify exact command and API syntax against
<https://caddyserver.com/docs/command-line> and
<https://caddyserver.com/docs/api> before a live write.
