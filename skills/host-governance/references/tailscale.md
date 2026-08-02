# Tailscale Control

Use this reference for tailnet grants, ACLs, policy tests, device tags,
Tailscale SSH, routes, exit nodes, Funnel, app connectors, and node preferences.

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

Verify current syntax and semantics against
<https://tailscale.com/docs/reference/syntax/grants> and
<https://tailscale.com/kb/1337/policy-syntax> before a live write.
