# Generic Infrastructure Control Workflow

Use these instructions when the consuming repository has no project-specific
profile. They define workflow and safety, not permission to modify a host or
provider.

## Locate the control repository

Resolve the host infrastructure repository in this order:

1. an exact path supplied by the user for the current task;
2. the current Git root when its governed scope declares it as the host
   infrastructure authority;
3. `HOST_INFRA_ROOT` when it resolves to a Git repository with the required
   governance documents;
4. `repository_root` in `~/.host-infra/control.yaml`.

During a governed repository rename, accept the prior identity only when the
repository documents the migration and still satisfies the required authority
contract. Names alone are not proof: validate the root scope and module
documents. If no candidate is authoritative, stop and ask for the exact
repository path. Never crawl unrelated directories looking for credentials or
infrastructure repositories.

## Collect deployment intent

Establish at minimum:

- stable service ID and owning project;
- target environment and device ID;
- application protocol, bind address, port, and health check;
- requested hostname and exposure (`private`, `tailnet`, or `public`);
- required source-to-destination flows;
- affected Cloudflare account/zone when DNS is involved;
- deployment and rollback commands owned by the consuming project.

Unknown intent stays unknown. Do not infer public exposure from the presence of
a web server, container port, domain name, or existing broad network rule.

## Build the change matrix

For each component, record:

| Field | Requirement |
| --- | --- |
| Owner | Repository or external system owning the desired fact |
| Target | Exact device, file, policy, zone, or record identity |
| Current | Timestamped live observation and source |
| Desired | Authorized end state |
| Executor | CLI, API, product skill, or operator |
| Validate | Preflight, syntax, live, and negative checks |
| Rollback | Snapshot and exact restoration method |
| Authority | Read-only, authorized write, or blocked |

Plan the whole transaction before applying its first write. Prefer the order
that keeps the service inaccessible until its application and intended access
controls are ready. DNS publication and public ingress usually come after the
private application health check; project facts may require a different order.

## Apply and verify

- Preserve the pre-change snapshot and validation output.
- Apply one bounded component change at a time.
- Verify that component before continuing.
- Stop on drift, ownership collision, failed validation, unexpected exposure,
  or a changed plan.
- Roll back only when the current request authorizes it or the previously
  authorized transaction explicitly included automatic restoration.
- After success, verify the request path from every relevant network boundary
  and verify at least one forbidden path remains denied.

Do not commit, push, deploy, reload, save policy, mutate DNS, or alter a remote
system merely because a profile declares a command.
