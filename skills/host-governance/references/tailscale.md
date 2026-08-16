# Tailscale Control

Use this reference for client installation and update readiness, tailnet grants,
ACLs, policy tests, device tags, Tailscale SSH, routes, exit nodes, Funnel, app
connectors, node preferences, and same-device VPN or proxy coexistence.

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

## Diagnose same-device VPN and proxy conflicts

Treat intermittent access from a device running another VPN, packet tunnel, or
local HTTP/SOCKS proxy as a client dataplane incident until evidence proves a
host failure. Tailscale cannot reliably coexist with every VPN-style product,
and some operating systems limit how multiple network extensions register
routes or DNS handlers.

Before changing either endpoint:

1. Record the operating system, Tailscale version, proxy or VPN application
   version, enabled network extensions, and current connection state.
2. Identify which single component is intended to own tailnet traffic: the
   official Tailscale client or an embedded Tailscale module in the proxy app.
   Prefer one active owner. If both products are installed, prove that only the
   chosen owner is connected rather than assuming installation implies use.
3. Capture the effective route table, compiled rule result, active proxy
   environment, application proxy settings, and relevant tunnel logs. Redact
   auth keys, node credentials, proxy credentials, headers, and private request
   content.
4. Do not infer that both Tailscale implementations were active solely from a
   UDP `41641` bind conflict. A tunnel reload or stale socket handoff can produce
   the same symptom; correlate it with process state and timestamps.

### Assign `100.64.0.0/10` to the intended owner

Keep route exclusion, proxy bypass, and rule policy as separate concepts:

- `tun-excluded-routes` bypasses the packet tunnel. Do not place
  `100.64.0.0/10` or the Tailscale IPv6 range `fd7a:115c:a1e0::/48` there when
  the tunnel is expected to reach the tailnet. On macOS, an exclusion can
  materialize as a route through a physical interface such as `en0` and can
  divert unmatched or fallback traffic. Treat that route as a risk signal, not
  standalone proof that an embedded `TAILSCALE` action was bypassed; verify the
  effective rule modifiers and end-to-end result.
- `skip-proxy` skips an application's proxy interface and hands traffic to its
  TUN processing. It does not necessarily mean plain Internet `DIRECT`.
  Therefore, a proxy app that documents these semantics can keep
  `100.64.0.0/10` in `skip-proxy` while removing it from
  `tun-excluded-routes`.
- `DIRECT` and an embedded `TAILSCALE` policy are not interchangeable. Select
  them according to the actual tailnet owner.

When the official Tailscale client owns the tailnet and the other application
is only a proxy, bypass that proxy for exact tailnet domains and addresses. Use
the proxy application's `DIRECT` policy where that means returning traffic to
the operating-system route table, and add exact custom tailnet hostnames and IP
addresses to CLI `NO_PROXY` configuration. Remove unnecessary HTTP/SOCKS
`ProxyCommand` directives from direct Tailscale SSH aliases.

When Shadowrocket's embedded Tailscale module owns the tailnet, route both the
address range and any custom hostname that resolves to a Tailscale address to
its `TAILSCALE` policy. A minimal rule shape is:

```text
DOMAIN,admin.example.internal,TAILSCALE
IP-CIDR,100.64.0.0/10,TAILSCALE,no-resolve
```

In Shadowrocket's rule editor, explicitly enable **No Resolve** for every
`IP-CIDR` rule that dispatches to the embedded `TAILSCALE` module. This UI
checkbox emits the `no-resolve` modifier; the policy name alone is not enough.
Verify the compiled rule contains the complete form shown above. A log result
such as `IP-CIDR,100.107.15.35/10,TAILSCALE,` proves that `TAILSCALE` was
selected but also reveals that `no-resolve` is absent. In observed failures,
that omission allowed hostname resolution to occur before the embedded route
handoff, followed by `tailscale route unavailable`, local proxy `503`, or
browser `ERR_CONNECTION_CLOSED`; enabling **No Resolve** restored the path.

Prefer a canonical network prefix in the rule: use `100.64.0.0/10` for the
whole Tailscale IPv4 range or an exact `/32` for one node. Do not use a node
address with `/10`, such as `100.107.15.35/10`, even if the application masks
it to the same network; the noncanonical form obscures the intended scope.

Remove or override any competing
`IP-CIDR,100.64.0.0/10,DIRECT,no-resolve` rule. Keep
`100.64.0.0/10` out of `tun-excluded-routes`; retaining it in `skip-proxy` is
compatible with Shadowrocket's documented distinction between proxy bypass and
TUN route exclusion. Treat these names and rule actions as version-specific:
inspect the active version's compiled configuration and logs after every
change.

### Isolate the failing layer

Use repeated probes instead of a single successful request. Test these paths
independently and preserve timestamps:

1. On the server, probe the loopback upstream and the listener bound to the
   server's Tailscale address. Confirm the expected listener, certificate,
   reverse-proxy status, and application response. A redirect such as HTTP
   `307` can be a healthy application response when it matches the service
   contract.
2. On the client, bypass explicit proxies and pin the hostname to its real
   Tailscale address. Then repeat the same request through the configured local
   HTTP or SOCKS proxy. A clean direct series with intermittent proxy failures
   localizes the incident to the client proxy or tunnel path.
3. Inspect `route -n get <tailscale-ip>` and the full route table. The selected
   route should terminate at the intended Tailscale or embedded tunnel. When an
   embedded policy intercepts before operating-system routing, correlate a
   physical-interface route with the compiled `TAILSCALE,no-resolve` rule and
   actual request log instead of declaring the route causal by itself.
4. Compare public or authoritative DNS with the system resolver. A packet
   tunnel can return a synthetic address from a Fake-IP range such as
   `198.18.0.0/15`; this is not a root cause by itself. Verify the tunnel's
   internal mapping, matched rule, and final real destination.
5. Inspect shell `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY`
   behavior separately from browser traffic. Also inspect SSH configuration
   for an explicit local proxy command. Browser success does not prove a CLI
   request avoided a local proxy, and the reverse is also true.

Correlate failures with client logs. High-value signatures include:

- network-setting reassertion or tunnel reload followed by embedded Tailscale
  stop/start events;
- repeated `tailscale route unavailable` or equivalent route-readiness errors;
- UDP `41641` bind failure followed by fallback to an ephemeral port;
- `magicsock`, STUN, UDP-path, control-plane reconnect, or DERP transition
  failures; and
- local proxy `CONNECT` or SOCKS timeouts for a tailnet destination.

These signatures indicate a client tunnel handoff, routing, or proxy problem;
they do not prove that the remote service is down. If server-side loopback and
Tailscale-listener probes remain clean during the same window, do not repair or
redeploy the host merely to address the client symptom.

### Recover and verify

Change supported UI or plain-text configuration rather than editing an
application's compiled database. Saving network settings can reload an
embedded Tailscale module, so make one coherent change, restart the owning
application once when required, and wait for route readiness before testing.
Repeatedly saving partial changes can extend the outage window.

After recovery, verify all of the following:

- every Shadowrocket `IP-CIDR` rule targeting embedded Tailscale includes the
  effective `no-resolve` modifier, not only a `TAILSCALE` policy label;
- tailnet traffic reaches the intended owner; any physical-interface route is
  either removed or proven not to apply to the matched embedded flow;
- compiled rules select the intended `TAILSCALE` or operating-system `DIRECT`
  owner for both exact domains and addresses;
- direct, browser, CLI, and explicitly proxied paths behave as designed across
  repeated requests;
- no prolonged route-unavailable, socket-handoff, or proxy timeout sequence
  appears after the final reload; and
- custom hostnames still resolve to the intended Tailscale address when checked
  outside any Fake-IP resolver.

Consult Tailscale's
[software interoperability](https://tailscale.com/docs/reference/interoperability)
and [DERP routing troubleshooting](https://tailscale.com/docs/reference/troubleshooting/network-configuration/derp-routing)
guidance for current platform behavior. For Shadowrocket-specific settings,
verify the active release against its community-maintained
[configuration wiki](https://github.com/LOWERTOP/Shadowrocket/wiki), especially
the documented difference between `skip-proxy`, `tun-excluded-routes`, and the
embedded Tailscale module.

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
