# Tailnet-only private Caddy ingress

Use this reference when a hostname must be reachable through a private
Tailscale network while remaining absent from the public Caddy listener. The
host repository owns the target facts and controller; this reference defines
the reusable safety and verification method.

## Desired topology

- DNS may point the hostname at an address that is routable only from the
  Tailnet. DNS presence alone does not make the service public.
- The Caddy site binds the exact declared Tailnet address. Do not bind
  `0.0.0.0`, a wildcard IPv6 address, or the public origin address.
- Use an explicit DNS-01 TLS policy with the approved DNS provider. Do not
  depend on HTTP-01 validation against a private address.
- Reverse proxy only to the declared loopback application endpoint. Preserve
  the HTTPS scheme with an explicit `X-Forwarded-Proto https` header when the
  application needs it.
- The hostname appears on exactly one Caddy route and that route appears only
  on the Tailnet listener. A public listener must not contain the hostname or
  a wildcard that admits it.
- When direct Caddy is the selected access mode, any local Tunnel or Access
  connector for the hostname is inactive and disabled. Retain its configuration
  and credentials for recovery unless their deletion has separate
  authorization.

## Inspect and classify

Inspect the complete Caddy source and the effective Admin API configuration.
Use an independently owned begin/end marker for the route. Classify the
hostname as `absent`, `managed_current`, `managed_drift`, `legacy_current`, or
`collision`:

- `absent` has no hostname or marker and may be adopted.
- `managed_current` is the exact desired block.
- `managed_drift` has one valid owned range that can be replaced.
- `legacy_current` is one explicitly declared predecessor shape that can be
  migrated to the current marker.
- Duplicate markers, a half marker, an unmanaged hostname occurrence, an
  overlapping wildcard, or an unknown predecessor shape is a collision and
  must fail closed.

Also inspect:

- Caddy version, Cloudflare DNS module, environment-file metadata, and service
  state;
- the systemd `MainPID`, the process that actually owns the Caddy listeners,
  and its cgroup or service identity;
- the loopback upstream health response;
- the TLS automation subjects and the route's actual listeners;
- the direct connector's active/enabled state and matching process count.

Never return Caddy bytes, full command lines, environment contents, tokens,
credentials, or raw logs.

## Plan and apply

`plan` is read-only and returns a generation, desired digest, candidate digest,
bounded actions, effects, blockers, and recovery location. It may plan a
controlled systemd ownership repair when the service is inactive but exactly
one known Caddy process owns the declared listeners.

`apply` must:

1. acquire the fixed host Caddy writer locks in their declared order;
2. re-read source, live configuration, process ownership, and connector state;
3. reject generation drift, route collisions, ambiguous processes, or missing
   DNS-01 credential metadata;
4. snapshot the exact source bytes and metadata in a root-only transaction
   directory and append a secret-free journal;
5. render only the selected route, validate and adapt the complete candidate
   with the real adapter, environment contract, and modules;
6. atomically replace the source and use the established Caddy reload path;
7. if systemd ownership is broken, terminate only the re-checked exact orphan
   after validation and start the declared service;
8. stop and disable the matching local connector without deleting its config;
9. verify the positive and negative paths, compensating to the snapshot on any
   pre-completion failure.

Normal service reload is preferred. A stop/start handoff is limited to a
proven ownership conflict; it must never be used merely because a reload is
convenient.

## Verify

Independent verification must prove all of the following:

- trusted TLS and the expected Admin response through the Tailnet address;
- the upstream health response and exact loopback destination;
- exactly one route for the hostname, listening only on the declared Tailnet
  address;
- the hostname is absent from every public listener and a public-source probe
  does not receive the Admin response;
- the connector unit is inactive and disabled, with no matching process;
- Caddy is active under the declared systemd service and its `MainPID` owns the
  listeners;
- the Cloudflare DNS module and root-only credential boundary remain ready.

Do not infer private access from a `100.64.0.0/10` DNS answer, and do not infer
public exposure from a generic default-site HTTP status. Use listener-aware
running configuration and a source-specific probe.
