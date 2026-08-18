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

## Selective edge 403 and WAF Rulesets

When one SDK, User-Agent, path, or header is blocked while an equivalent request
passes, establish a bounded differential probe first. Keep the hostname, path,
method, body shape, and authorization constant; vary only the suspected request
attribute. Record only status, `cf-ray`, and a redacted response classification.
Do not place a bearer token or request body in shell history, Git, logs, or the
final report.

Use a separate Account-scoped `Account Analytics Read` Token for the Security
Events GraphQL dataset; Zone WAF inspection/write needs the corresponding
scoped Zone WAF permissions. Security Events can be sampled or delayed: an
absent Ray ID is not proof that no product blocked the request. Use the
Dashboard event for the exact Ray ID to obtain Source, Action, product/service,
Rule ID, and rule message before a security write. Do not infer the blocking
product from an aggregate event that merely shares a User-Agent and time window.

For a proven managed-WAF block, create a Skip rule only after reading the
current Cloudflare Rulesets documentation and current custom entry point. Keep
its expression bounded to the exact host, path, and client signature, and skip
only the proven phase. At the Zone Rulesets API endpoint,
`http_request_firewall_custom` requires `kind: "zone"`; do not copy a Terraform
provider `kind` value into a raw API request without verifying the API response.
If a custom entry point already exists, import and reconcile it instead of
creating over it.

Never broaden a failed Skip rule into `allow`, extra phases, other products, or
an all-path/client exception. Skip cannot bypass Bot Fight Mode. Re-read the
created ruleset and run the original blocked signature immediately. If it is
still edge-blocked, roll back only the ruleset/rule created by that transaction,
then re-read the entry point. Treat an empty HTTP `204` response to a successful
Rulesets API DELETE as success only after this re-read.

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
