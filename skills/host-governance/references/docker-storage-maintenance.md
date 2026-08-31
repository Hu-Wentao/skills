# Governed Docker Storage Maintenance

Use this workflow for suspected Docker volume leaks, runtime storage pressure,
or stale transient containers and networks. It is a separately authorized
incident response, not routine BuildKit maintenance. Keep host- and
product-specific selectors, retention intervals, restart behavior, and data
signatures in the project profile and controller rather than this shared skill.

## Inspect

Use a project-owned `host-governance.config.v2` control with distinct
`inspect`, `plan`, `apply`, and `verify` operations. Identify one exact Docker
engine and record its generation before reasoning about candidates. Inventory
all volumes, containers, mounts, and custom networks with enough metadata to
distinguish:

- named from engine-generated anonymous volumes;
- referenced from unreferenced or dangling resources;
- creation time and age against a project-declared retention policy;
- labels, driver, ownership evidence, and container/image provenance;
- bounded data signatures that raise risk, such as database or application
  state, without returning secrets or arbitrary file contents;
- the pre-incident running-container baseline, restart policy, host mount
  responsiveness, and relevant host-integration signals.

`dangling` means unreferenced, not disposable. Preserve every named volume by
default. A data or database marker increases the required proof; it never
authorizes blanket deletion. Stop when the exact engine, owner, source defect,
or candidate classification is ambiguous.

## Plan

Fix the source lifecycle first when it is owned by a consuming project. A
transient container that creates anonymous volumes must remove those volumes in
its normal teardown, for example with `docker rm --volumes`; a cleanup job is
not a substitute for correcting the producer.

Generate one exact, secret-safe allowlist from the current engine generation.
The plan must include a fixed age cutoff, every resource ID or name, the
evidence that makes each candidate eligible, a candidate digest, the complete
preservation rules, blockers, expected service impact, and recovery limits.
Named volumes remain excluded unless a separate resource-specific request
establishes ownership, backup, and deletion intent.

Never use `docker volume prune`, `docker system prune`, a broad image or
container prune, a name glob at mutation time, or recursive Docker data-root
deletion. Do not convert one known leak signature into permission to remove
unrelated resources. State clearly that deleting a volume has no generic
rollback and require current destructive authorization for the exact plan.

If runtime or host-integration restart is proposed, treat it as a material
effect. Capture the running-container baseline and identify containers whose
restart policy will not restore them automatically. Keep the restart in the
same plan only when it is required for recovery and explicitly disclosed.

## Apply

Under the project-owned lock and transaction journal:

1. Re-inspect the exact engine and reject any generation or candidate-digest
   drift before the first mutation.
2. Remove only the immutable allowlist, using exact resource IDs or names.
   Never re-evaluate a broad selector during mutation.
3. Stop expansion on the first unexpected result. Journal completed and
   remaining exact items so a retry can safely resume or supersede the plan.
4. Perform only disclosed runtime or host-integration restarts. Restore every
   container from the running baseline that is not recovered automatically,
   without starting containers that were previously stopped.
5. Record before/after counts, result generation, command outcomes, service
   restoration, remaining blockers, and the absence of a generic data rollback.

Deleting a planned resource is not proof that the incident is resolved. Do not
continue with broader deletion when responsiveness or service recovery fails.

## Verify and Report

Run a fresh read-only verification. Prove every planned resource is absent,
every preserved named or non-candidate resource remains out of scope, and the
pre-incident running-service baseline is restored. Recheck the exact host
symptom that motivated the response, such as mount responsiveness or runtime
integration health, and report relevant interface or integration evidence when
the project controller defines it.

Report the inspected and result generations, candidate digest and fixed
cutoffs, exact deleted and preserved counts, service interruption and recovery
evidence, journal location, source-side lifecycle fix, remaining pressure, and
every unverified gap. A partial failure is a bounded incomplete transaction,
not permission to prune more broadly.
