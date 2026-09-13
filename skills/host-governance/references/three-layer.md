# Three-layer routing

Host Governance has three deliberately small layers. Choose one route for a
task and stop when its boundary is satisfied.

## 1. Facts

Facts answer **where** and **who owns it**. Use the authoritative host
repository's `context` contract when a device, service, alias, port, or resource
identity is unknown. A context result is repository evidence; live health and
runtime state still require a separate read.

If the task already supplies an exact target and the current conversation has
established its SSH alias and jump route, do not reopen the locator merely to
repeat the same lookup. Keep the target and route in the task record.

## 2. Contract

Contracts answer **what operation is allowed**. When the consuming project has
an exact `control` operation, resolve that operation and execute it through the
validated runner. The contract owns parameters, authorization, locks,
snapshots, recovery, and verification. A missing project contract is not a
reason to invent one during a one-time incident.

## 3. One-time manual

Manual execution answers **how to finish one bounded action now** when the
contract layer is absent or cannot express the already-authorized action. It is
admitted only when all of these are true:

- the user explicitly authorizes the current SSH operation;
- the exact host, SSH alias, jump route, and affected path are known;
- the command is bounded to that target and action, with no shell fragment or
  user-controlled command interpolation;
- a secret-safe snapshot or recovery path exists before mutation; and
- the result is verified, including a required negative or access-boundary
  check when exposure can change.

Do not inspect unrelated governance configuration, add a reusable controller,
or broaden the target during this route. The authorization expires when the
operation completes, blocks, or returns to the user. A repeated need is a
separate request to productize the stable method under the contract layer; it
never becomes an arbitrary-command capability.

## Decision rule

Use facts only for read-only identity lookup. Use the contract layer when an
exact operation exists. Use the one-time manual layer only for the explicit,
bounded exception above. Never combine a manual mutation with an unplanned
provider, database, Caddy, or second-host change.
