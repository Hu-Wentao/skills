---
name: project-compose-resource-diagnostics
description: Diagnose friday-relay instance outages, HTTP 502/503/504, ingress-to-Compose port drift, partial deployments, container health/restart/exit, CPU, memory, OOM, disk pressure, and deployment-capacity risk through the governed resource-diagnosis workflow. Use when llm or llm-dev is offline, interrupted, unreachable, unhealthy, returning gateway errors, or suspected of resource exhaustion; use the single-shot availability fast path before Provider/request diagnosis when no exact req_ id or Provider evidence exists.
---

# Project Compose Resource Diagnostics

## Enter Through Project Governance

For a configured Friday Relay repository, resolve the project-governance
`resource-diagnosis` task before collecting evidence:

```bash
uv run python <project-governance-skill-root>/scripts/resolve.py \
  --cwd <project-root> --task resource-diagnosis --operation collect --format json
```

Consume the resolved target parameters, output schema, mutability,
authorization, and next states. Run the declared `resource diagnose` operation
through the governance runner when the project exposes that alias. If the
project has no resource-diagnosis contract, use the generic fast path below,
report the governance gap, and do not infer project targets or mutation
authority.

When the fast path or the user's question requires historical CPU, memory, OOM,
disk, or capacity evidence, resolve the contract's resource-evidence operation
and run it through the same read-only boundary. Do not bypass the contract by
inventing target flags, Beszel systems, or recovery commands.

## Start With Runtime Evidence

Keep diagnosis read-only. Resolve the exact `llm` or `llm-dev` target, then run
the fast path before reading broad documentation or querying Beszel:

```bash
pnpm ops:diagnose-instance -- --target llm --since 30m
```

Use `--json` for machine-readable evidence and exact ISO `--since` / `--until`
when the incident window is known. The command collects the public endpoint,
published origins, allowlisted Docker state, ingress state, deployment manifest,
deployment transaction, exact matching deployment-resource summaries, and kernel
OOM count in one bounded pass.

Do not make Beszel a prerequisite for instance availability. The command queries
Beszel only when the public/origin/ingress/deployment evidence cannot identify a
failure boundary and readonly credentials are available.

Stop collecting unrelated evidence when the command returns a high-confidence
classification. Do not continue to Provider, database, Capture, or broad log
searches merely to add volume to a complete evidence chain.

## Interpret Fast-Path Classifications

- `partial_deployment_ingress_drift`: runtime and ingress identities diverged
  after a failed deployment crossed `runtime_started`; high confidence.
- `ingress_upstream_mismatch`: published origins are healthy while the loaded
  ingress uses different ports; high confidence.
- `ingress_config_invalid`: origins are healthy but the ingress candidate is
  invalid or has duplicate site blocks; high confidence.
- `ingress_service_unavailable`: origins are healthy but Caddy or the configured
  tunnel service is inactive; high confidence.
- `origin_unavailable`: the public endpoint and at least one published origin
  are unavailable; continue to resource evidence.
- `container_unhealthy`, `container_oom`, `kernel_oom`: continue only with the
  smallest evidence needed to identify the responsible service and window.
- `healthy`: public and origin checks pass and no higher-priority deployment or
  ingress inconsistency remains.
- `inconclusive`: required evidence is missing or no rule matches; state the gap.

Treat current availability and deployment completeness as separate facts. A
public `200` does not erase a failed deployment transaction, stale deployment
manifest, invalid ingress configuration, or loaded stale upstream.

## Plan Recovery Without Broadening Authority

The fast path returns a read-only recovery plan and the fixed deployment
identity when available:

- `inspect_contracted_fixed_tag_retry`: inspect the release contract and frozen
  identity before a same-tag retry.
- `reconcile_ingress_or_patch_repair`: do not retry blindly; the ingress is not
  convergent and requires an authorized reconciliation or a patch repair from
  the failed immutable tag.
- `reconcile_ingress`: use only an authorized deterministic candidate,
  validation, atomic install, reload, and public verification flow.
- `inspect_before_mutation`: evidence is insufficient for a safe mutation.

Never restart, reload, reconcile, retry, repair, rollback, restore, deploy, or
migrate without current explicit authorization. After authorization, resolve
the project-governance release/deployment contract and preserve its exact
tag/commit/artifact/target identity. A diagnosis is not deployment authority.

## Continue With Resource Evidence Only When Needed

For CPU, memory, OOM, disk, capacity, or an inconclusive origin failure, read:

- `docs/baseline/compose-resource-diagnostics.md`;
- `docs/baseline/performance-monitoring.md` when Gateway runtime samples matter;
- the deployed version of `docker-compose.yml` and the relevant scripts.

Provide Beszel access through environment only. Prefer `BESZEL_TOKEN`; otherwise
use `BESZEL_EMAIL` and `BESZEL_PASSWORD`. Never print credentials.

```bash
BESZEL_URL="$BESZEL_URL" \
BESZEL_TOKEN="$BESZEL_TOKEN" \
BESZEL_SYSTEM="$BESZEL_SYSTEM" \
pnpm ops:diagnose-compose -- --target llm --since 30m
```

Use `--service`, `--json`, or `--beszel-only` only for the narrowed question.
Classify resource evidence as follows:

- Docker `OOMKilled=true`: `container_oom`, high confidence.
- Kernel OOM in the same window: `kernel_oom`, high confidence.
- Memory/CPU/disk thresholds: pressure correlation, medium confidence.
- Nonzero exit without OOM evidence: `process_exit`; exit 137 alone is not OOM.
- No matching direct or correlated evidence: `inconclusive`.

For a deployment failure or capacity assessment, match the private
`summary.json` by exact target, release commit/tag, transaction attempt window,
and exit status. Never select “latest”. Read compressed samples only when the
summary cannot answer the exact phase or sequence question.

## Preserve Provenance

Record the current workspace commit and dirty state. Obtain the deployed
manifest and transaction identity before interpreting current-workspace code.
Treat remote source files, moving tags, and floating images as drift evidence,
not proof of the active release. Use the deployed version for causal code/config
claims and current source only for the delta or intended repair.

## Security and Failure Boundaries

- Never run full `docker inspect`; use only allowlisted formats.
- Never output environment values, complete Caddy/Tunnel configuration, raw
  journal or container logs, URLs/IPs, credentials, headers, bodies, Capture, or
  private raw deployment samples.
- If SSH is unavailable, retain the public result and lower confidence.
- If Beszel is unavailable, retain fast-path evidence; do not turn that absence
  into a failed availability diagnosis.
- If multiple Beszel systems are accessible, require exact `BESZEL_SYSTEM`.
- If deployed provenance is unknown, label code-level attribution uncertain.

Report the classification, confidence, shortest complete evidence chain,
deployment completeness, missing evidence, fixed recovery identity, recovery
preconditions, and unauthorized operations left untouched.
