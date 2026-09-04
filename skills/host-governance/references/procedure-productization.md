# Productize a Host Procedure

Use this workflow only when the current user explicitly asks for a host procedure—such as installing specific software, configuring a service, or performing recurring maintenance—to become a reusable host-governance function. The outcome is a tested, contracted operation that future invocations execute directly.

## Admission Gate

Productization requires explicit current-request intent to create, automate, contract, retain, or support a reusable long-term capability. A request to perform one operation, recover one incident, clean up one target, migrate current state, or execute steps in a chosen order remains one-time work. "Use governance", repeated historical need, a selected plan, a conversation summary, or an assistant-proposed implementation does not cross this gate.

For one-time work, compose existing contracted operations without changing repository code, contracts, tests, documentation, versions, or installed capabilities. If no existing operation can safely complete the task, report the missing capability as a blocker. Use a manual path only under the explicit one-round exception in [authorization-and-safety.md](authorization-and-safety.md); never productize merely to unblock the current operation.

## Reuse Before Building

Resolve the project-owned `control` task and search its operation names and
descriptions for the requested capability. Inspect the referenced controller
and tests when an exact function exists. Execute its `inspect`, `plan`,
authorized mutation, and `verify` operations instead of reconstructing remote
commands.

Extend the existing controller when the requested behavior is the same domain
with one legitimate new variation. Create a new controller only when ownership,
state, recovery, or verification differs materially. Never create a generic
arbitrary-command, arbitrary-package, or shell-fragment executor.

## Extract the Reusable Method

After inspecting live state and completing any necessary discovery, separate:

- stable method: ordering, safety gates, locks, snapshots, mutation steps,
  verification, negative checks, recovery, and terminal states;
- target facts: device identity, SSH alias, platform, package/service names,
  paths, versions, ports, and expected runtime state;
- variable choices: supported package source, optional modules, versions,
  service enablement, configuration modes, and bounded timeouts;
- one-time evidence: transient generations, timestamps, current counts,
  temporary URLs, and runtime observations that must not become defaults;
- secrets: credential requirements and approved sources, never values.

Summarize the experience as durable policy only when it generalizes. Keep
project identities, topology, exact defaults, commands, and authoritative
desired state in the host repository. Keep runtime evidence in transaction
journals or ignored artifacts.

## Implement the Function

Place the deterministic controller in the authoritative host repository. Use
the repository's prescribed runtime—normally Python through `uv`—and expose a
small CLI with separate operations:

- `inspect`: read authoritative and live state and emit secret-safe facts plus
  a stable generation;
- `plan`: compute the bounded actions, desired digest, effects, recovery, and
  required authorization without writing;
- `apply` or another precise mutation verb: acquire the host-owned lock,
  re-read state, reject generation drift, snapshot, mutate, verify, journal,
  and compensate only within the declared recovery boundary;
- `verify`: independently prove the requested outcome and negative paths;
- `rollback`: add only when exact ownership and safe restoration are known;
  destructive removal remains separately authorized.

Register every operation in the project-owned
`host-governance.task-contract.v1` contract. Declare exact argv, mutability,
authorization, typed parameters, sensitive environment requirements, output
schema, exit states, and allowed next states. Run it only through the resolver
and validated runner.

## Parameterize Deliberately

Turn real, reviewed variations into typed contract parameters. Use booleans,
integers, enums, bounded strings, exact identifiers, and manifest-derived
targets. Validate parameters both in the contract and controller. Prefer safe,
stable defaults and make exposure, deletion, privilege expansion, billing,
identity change, and weakened verification separate operations or explicit
authorization boundaries.

Do not parameterize:

- executable paths, raw commands, shell fragments, or unrestricted package names;
- credentials, private configuration, or secret values;
- target hosts that should come from authoritative manifests;
- arbitrary file paths outside a fixed owned root;
- options observed only once without a supported semantic contract.

When variations require substantially different validation or recovery, use
separate operations or controllers rather than a mode flag that hides distinct
transactions.

## Test and Adopt

Add focused tests for parameter validation, desired-state derivation,
generation drift, locking, snapshots, journaling, verification, redaction,
recovery limits, and prohibited broad behavior. Run static validation, the
focused tests, applicable full repository checks, and a dry-run or read-only
plan.

Use the newly contracted controller for the current request only when that same request also authorizes the corresponding live operation and effects. Otherwise stop at the requested implementation or publication boundary. Do not call the underlying script directly after the contract exists. Record stable verified facts only when repository writes are authorized; do not promote transient output.

Future calls must start with the existing controller. A successful no-op plan
and verify is the correct fast path when the desired state already holds.

## Report

Report the new function and operation names, controller and contract paths,
parameters and defaults, tests, transaction evidence, reusable lessons,
project-specific facts, compatibility, recovery limits, and unsupported
variations. State explicitly whether the current task was executed through the
new function and what later calls can invoke directly.
