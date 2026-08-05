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
- Use the project-owned collector command declared by the profile for Docker,
  Beszel, SSH, ingress, and deployment evidence. Keep those command internals
  in tested project scripts rather than reimplementing them in the governance
  runner.

## Collection sequence

1. Run the bounded availability fast path for the exact target and incident
   window. It should collect public health, published origins, allowlisted
   container state, ingress state, deployment identity, matching deployment
   evidence, and same-window kernel OOM evidence in one bounded pass.
2. Keep current availability, deployment completeness, and resource pressure
   as separate facts.
3. Continue to historical CPU, memory, OOM, disk, or capacity evidence only
   when the user asks for it or the fast path leaves the boundary unresolved.
4. Match deployment evidence by exact target, release identity, transaction
   window, and exit status. Never select evidence by “latest”.

Stop when the evidence chain reaches a high-confidence boundary. Do not read
Provider, database, request, Capture, or broad application logs merely to add
volume to a complete resource diagnosis.

## Classification

- A container `OOMKilled=true` is direct container OOM evidence with high
  confidence.
- A same-window kernel OOM event is high-confidence kernel OOM evidence.
- Healthy origins with an ingress port mismatch, invalid configuration, or
  inactive ingress service identify an ingress boundary; current public health
  does not erase deployment drift or an invalid loaded configuration.
- A container or kernel resource threshold is pressure correlation. Host disk,
  memory, or CPU at a threshold is not by itself the causal explanation for an
  application failure.
- A non-zero process exit without OOM evidence is a process-exit finding; an
  exit code of 137 alone does not prove OOM.
- Missing collector, SSH, or Beszel evidence is an explicit evidence gap, not
  an outage classification.

## Recovery boundary

The task produces a recovery plan only. Never restart, reload, reconcile,
retry, repair, rollback, restore, deploy, migrate, clean up, or change a
resource limit from a diagnosis invocation. If ingress is invalid or
non-convergent, do not recommend a blind same-tag retry; require the separate
authorized ingress or repair workflow.

Preserve the fixed target and release identity returned by the collector. Do
not re-resolve a moving tag, select a different target, or infer mutation
authority from a healthy public response.

## Provenance and security

- Record the repository commit and dirty state, then obtain deployed manifest
  and transaction identity before making code or configuration claims.
- Treat remote source, moving tags, and floating images as drift evidence, not
  proof of the active release.
- Do not print or persist credentials, environment values, URLs/IPs, request
  bodies, headers, captures, provider secrets, raw logs, full container
  inspection, or private raw resource samples.

## Report

Return the classification, confidence, shortest complete evidence chain,
deployment identity when present, missing evidence, and the unauthorized
operations left untouched. Report current availability and deployment
completeness separately from resource findings, and include the recovery
preconditions without claiming that diagnosis authorizes recovery.

If the collector or Beszel is unavailable, retain the evidence already
collected and state the boundary explicitly. Do not turn missing monitoring
credentials into a service-outage conclusion.
