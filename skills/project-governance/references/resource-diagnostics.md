# Resource Diagnostics

Use `resource-diagnosis` for current instance, host, or Compose resource
incidents. This is an operational evidence workflow, not a defect ledger and
not deployment authority.

## Contract boundary

- Resolve the task contract before collecting evidence.
- Treat the project profile as authoritative for target names, topology,
  collector commands, evidence schemas, and required baseline documents.
- Keep collection read-only by default. A resource diagnosis never authorizes
  restart, reload, cleanup, quota changes, deployment, rollback, restore,
  migration, or host configuration changes.
- Use the specialized project collector for Docker, Beszel, SSH, ingress, and
  deployment evidence; do not reproduce its command internals in governance.

## Evidence sequence

1. Run the bounded availability fast path for the exact target and incident
   window.
2. Keep current availability, deployment completeness, and resource pressure
   as separate facts.
3. Continue to historical CPU, memory, OOM, disk, or capacity evidence only
   when the user asks for it or the fast path leaves the boundary unresolved.
4. Match deployment evidence by exact target, release identity, transaction
   window, and exit status. Never select evidence by “latest”.

## Report

Return the classification, confidence, shortest complete evidence chain,
deployment identity when present, missing evidence, and the unauthorized
operations left untouched. Distinguish direct OOM evidence from threshold
pressure correlation; disk or memory reaching a threshold is not by itself a
causal explanation for an application failure.

If the collector or Beszel is unavailable, retain the evidence already
collected and state the boundary explicitly. Do not turn missing monitoring
credentials into a service-outage conclusion.
