# Cloudflare Control

Use this reference for Cloudflare accounts, zones, DNS, Terraform-managed
resources, tunnels, security settings, and other provider resources.

For a public hostname backed by Cloudflare Tunnel and protected by Access,
also read [cloudflare-tunnel.md](cloudflare-tunnel.md) from the skill root.

## Authority and authentication

- Keep desired managed resources in the host infrastructure repository.
- Treat Cloudflare API responses and infrastructure state as runtime evidence.
- Prefer scoped API Tokens over a Global API Key. Separate read-only discovery,
  ordinary resource writes, and registrar/billing permissions.
- Resolve every project-declared environment and secret-store source before
  proposing interactive Dashboard or browser authentication. Verify the
  selected token against Cloudflare and probe the exact required read surfaces;
  report invalid authentication separately from missing product permission.
- Never commit token values, R2 backend credentials, Terraform state, request
  bodies containing secrets, or provider environment files.

## Inspect and plan

1. Resolve the exact account, zone, resource type, external resource ID, and
   current manager (Terraform, dashboard, API, or another controller).
2. Do not let two controllers manage the same resource.
3. Import pre-existing resources into the selected infrastructure state before
   applying matching declarative configuration.
4. Review create, update, replace, and destroy actions separately. Treat an
   unexpected replace or destroy as a blocker.
5. Keep state isolation aligned with the repository's account/zone/product
   ownership boundaries.

## High-risk domains

Domain registration, transfer, renewal, contact changes, billing changes, zone
deletion, DNSSEC transitions, nameserver changes, and bulk DNS deletion require
separate explicit authorization. A normal deployment request does not authorize
purchase, registrar mutation, or deletion.

## Verify

Re-read the remote resource after apply, inspect the final plan/state mapping,
and test DNS or service behavior through the intended resolvers and network
path. Distinguish propagation delay from an incorrect desired state and do not
retry mutations blindly.

Retrieve current API, provider, and permission details from
<https://developers.cloudflare.com/> before relying on exact syntax or feature
availability.
