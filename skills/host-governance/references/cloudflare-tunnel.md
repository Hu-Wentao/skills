# Cloudflare Tunnel and Access Control

Use this reference for publishing one host application through a remotely
managed Cloudflare Tunnel and protecting the hostname with Cloudflare Access.
Treat the origin, connector, tunnel ingress, DNS record, Access application,
and Access policy as one governed public-application transaction.

## Required intent

Resolve these facts from project-owned configuration or explicit user input:

- owning project, target device, origin protocol, bind address, port, and
  health check;
- Cloudflare account and zone references, exact public hostname, and current
  resource manager;
- stable tunnel and connector identities and desired high-availability level;
- Access login method, exact allowed identities or verified IdP groups, and
  session duration;
- rollback owner and whether destructive cleanup is separately authorized.

Do not infer an email allowlist, IdP group, public hostname, or account from a
nearby resource. Repository declarations may contain stable external IDs but
must not contain API tokens, connector tokens, credentials, or Terraform state.

## Contract and credentials

Use a project-owned `host-governance.config.v2` control contract. Classify a
Cloudflare-only operation as `external_write`, a connector-host operation as
`host_write`, and a controller that changes both surfaces as
`composite_write`. Every write requires current-user authorization.

Declare required credential variable names in the operation's `environment`
mapping. Mark tokens and secrets as sensitive. The runner may resolve only the
ordered environment or macOS Keychain sources declared by the project; it
never caches, journals, or prints values. Controllers must read credentials
from the inherited child environment, never from argv, repository files, plan
files, or generated instructions.

Declare approved environment or macOS Keychain lookups as ordered credential
sources in the project contract. Before suggesting Dashboard or browser
control, exhaust those sources and classify each candidate as absent, invalid,
valid-but-insufficient, or sufficient for the exact Tunnel, DNS, and Access
operations. Do not infer write capability from a successful Zone or Tunnel
read, and do not treat a credential's label as proof of validity.

Send a connector token directly to a target-host secret file or secret store
with restrictive permissions. Redact it from API responses, logs, diffs,
journals, process arguments, and final reports. Prefer scoped API tokens over
Global API Keys and retrieve current required permissions from Cloudflare's
official API documentation before execution.

## Inspect and plan

Inspect all of the following before the first write:

1. Exact account and zone, existing tunnel names and IDs, connector health,
   and tunnel management model.
2. Existing DNS records for the hostname, including proxy state and current
   manager.
3. Existing tunnel ingress rules and their final catch-all rule.
4. Existing Access applications, policies, identity providers, selectors,
   precedence, and session settings for the hostname.
5. Target-host origin health, listeners, container networks, connector
   runtime, egress capability, and resource pressure.
6. Ownership collisions or dual management by Terraform, dashboard, API, or
   another controller.

Produce one combined plan with exact create, update, replace, and delete
actions; stable resource references; base and desired digests; validation;
rollback; and authorization state. Treat unexpected replacement, overlapping
hostnames, an existing unmanaged DNS record, or an unverified identity selector
as a blocker.

## Apply fail closed

Use the safest order supported by the selected manager:

1. Re-read authoritative and live state under the project transaction lock.
2. Create or update the remotely managed tunnel and an ingress rule for the
   exact hostname and origin. End ingress with an explicit catch-all rejection.
3. Create or update the self-hosted Access application and a narrow Allow
   policy before publishing DNS. Access is default-deny; do not use `Everyone`
   or all valid login methods as an allow selector.
4. Deliver the connector token without exposing it, start the bounded
   connector, verify local origin reachability, and confirm tunnel health.
5. Create or update one proxied DNS route to the tunnel only after Access is
   installed and the connector is healthy.
6. Re-read every Cloudflare and host resource and persist only non-secret
   transaction evidence.

For email OTP, allow exact user email addresses unless the user explicitly
authorizes a broader verified domain. For group policies, use only exact IdP or
SCIM claims observed from the configured identity provider. Never substitute
an Access Group for an IdP group.

Run `cloudflared` as a managed host service or constrained container with a
restart policy, finite CPU, memory, and PID limits, and no inbound listener.
Read the Docker Compose guardrails skill when containers are used. Use host
networking only when needed to reach an origin intentionally bound to host
loopback, and document that compatibility choice.

## Verify

Verify all relevant boundaries:

- origin health remains private and no host inbound port was broadened;
- tunnel is healthy with the intended connector count and exact ingress;
- DNS resolves through Cloudflare to the intended tunnel route;
- an unauthenticated request reaches Access rather than the origin;
- a non-allowed identity remains denied;
- an allowed identity completes login and reaches the application;
- Access audit evidence identifies the application and matching policy;
- the running connector has effective restart and resource limits;
- unrelated host services, DNS records, tunnels, and Access applications remain
  unchanged.

If interactive login prevents a complete positive test, report that test as
pending user action; do not weaken Access to make automation pass.

## Rollback

Rollback is a new authorized transaction. Prefer fail-closed recovery:

1. Remove or disable the public DNS route first when exposure must stop.
2. Restore the prior Access policy and application from exact snapshots.
3. Restore the prior tunnel ingress and connector runtime.
4. Revoke or rotate connector credentials that were exposed or retired.
5. Re-read DNS, Access, tunnel, connector, and origin state and record the
   resulting generation.

Do not delete a tunnel, Access application, DNS record, identity provider, or
credential merely because a deployment failed. Destructive cleanup requires
separate explicit authorization and must not affect resources owned by another
controller.
