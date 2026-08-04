# Tailscale Control

Use this reference for client installation and update readiness, tailnet grants,
ACLs, policy tests, device tags, Tailscale SSH, routes, exit nodes, Funnel, app
connectors, and node preferences.

## Delegate when possible

Use a specialized Tailscale control skill when it is installed and covers the
requested operation. Supply the exact device identity, current policy evidence,
required flow matrix, and authorization. Reconcile its result into the shared
infrastructure transaction rather than treating it as a separate deployment.

## Inspect

- Resolve each node by stable device ID, current node name, and current
  Tailscale identity; do not rely on an old IP alone.
- Snapshot the complete saved policy, tags, ownership, key expiry, routes,
  route acceptance, exit-node state, Tailscale SSH, Funnel, and relevant app
  capabilities.
- Find every broad selector and rule that already matches the target.
- Record exact source, destination, protocol/port or application capability,
  direction, and intended result.

For installation or update work, also inspect the operating system, CPU
architecture, init system, current client version, installation source,
package manager, selected release track, effective automatic-update
preference, and whether every required package endpoint is reachable. Do not
assume that an online node can download client updates: control-plane or DERP
connectivity does not prove package-repository reachability.

## Install with an update path

Treat automatic-update readiness as part of installation, not optional
follow-up work:

1. Select the official installation method supported by the target platform
   and record whether the client is package-managed or a static binary.
2. Install and authenticate the client without replacing its state identity
   during an ordinary upgrade.
3. Verify the current version, daemon health, tailnet connectivity, and required
   application capabilities.
4. Run the platform-supported non-mutating update check, such as
   `tailscale update --dry-run`. Use `--track=stable` only when the installed
   client and platform expose that flag.
5. Enable the native updater with `tailscale set --auto-update` only when the
   platform supports applying updates and its required repositories are
   reachable. Re-inspect effective preferences rather than trusting command
   success alone.
6. Install a governed scheduler when the native updater cannot be given a
   narrowly scoped network path. Stagger critical or redundant nodes and add
   randomized delay so they do not restart together.
7. Verify one real update or a no-op latest-version check, then record failure
   visibility, the last known successful check, and the recovery path.

Do not declare installation complete merely because `tailscale up` succeeds.
Treat unsupported updaters on platforms such as system-managed immutable or
rolling distributions as a requirement to use that platform's supported
system update mechanism.

## Restore update reachability

Choose the smallest compatible method in this order:

1. Allow direct HTTPS only to the exact official package endpoints used by the
   inspected installation source.
2. Route only the update command through a restricted HTTP CONNECT proxy. Bind
   the proxy to the intended management network, restrict its client sources,
   allow only the inspected package domains and TCP 443, do not intercept TLS,
   and deny every other destination.
3. Use a signed package mirror or a controller-initiated package push when the
   node cannot receive a safe outbound exception. Preserve package-manager
   signature verification or verify the publisher-provided digest before
   installation.

For a command-scoped proxy, set `HTTPS_PROXY` only on the one-shot updater or
its scheduler. Do not apply a package-only proxy to `tailscaled.service`, where
it could also capture control-plane and relay traffic. A typical systemd timer
should be persistent, have randomized delay, serialize against other package
operations, and invoke the supported noninteractive update command.

Do not enable a general exit node, subnet route, unrestricted proxy, or broad
trusted-network grant merely to make updates succeed. If an isolated node must
reach an update proxy, model the exact node-to-proxy TCP flow as an intentional
compatibility exception, add positive and negative policy tests, and verify
that trusted management ports and lateral isolated nodes remain unreachable.

An in-band client upgrade can briefly drop the same Tailscale path used to
manage the host. Keep the previous install artifact or version available,
preserve an out-of-band console, and use a detached host-local install job when
a controller pushes an update over Tailscale.

## Plan and apply

- Treat grants and ACLs as additive. A narrower grant does not override an
  older broad match.
- Prefer Grants for new policy where compatible with the established policy,
  but do not mix or migrate syntax incidentally.
- Add positive and negative policy tests before saving policy.
- Preserve a recovery path before applying a tag that changes node identity.
- Scope temporary maintenance access to exact source, destination, protocol,
  port, and duration; remove and verify it within the transaction.
- Do not enable routes, route acceptance, exit-node behavior, Funnel, app
  connectors, or key-expiry exemptions unless explicitly required.

## Verify

Validate the complete policy, save it, then test from real source nodes. Required
flows must succeed and forbidden initiation/lateral paths must fail. Re-inspect
the final saved policy and node preferences; a successful policy save alone is
not enforcement proof.

After installation or update, also verify the installed version, daemon
restart, control-plane connection, required services, advertised capabilities,
and the next scheduled update. Exercise the proxy or mirror negative path: a
permitted package fetch must succeed while an unrelated HTTPS destination must
fail. Report any platform whose repository can supply only an older client as
not yet capable of reaching the requested release.

Verify current syntax and semantics against
<https://tailscale.com/docs/reference/syntax/grants> and
<https://tailscale.com/kb/1337/policy-syntax> before a live write.
