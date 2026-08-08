# Shared PostgreSQL Control

Use this reference for a host-owned PostgreSQL service that may serve multiple
projects.

## Ownership

- Keep the PostgreSQL runtime, disk, resource budget, network exposure,
  backups, WAL archive, PITR procedure, upgrades, and retirement under the
  authoritative host repository.
- Keep each consuming project's schema migrations and application cutover in
  that project's repository.
- Deploy one PostgreSQL server per host by default. Refuse an additional
  long-running PostgreSQL container unless the topology documents an explicit
  exception.
- Give PostgreSQL an independent Compose or systemd project. Never couple its
  start, stop, rollback, or data volume to one consuming application.
- Provision a separate database, role, schema ownership boundary, and
  connection-pool budget for each consumer. Do not share the host superuser.

## Inspect and Plan

1. Inspect every native and containerized PostgreSQL instance, listener,
   managed configuration generation, data directory, image identity, resource
   limit, health state, and backup scheduler without returning credentials.
2. Check the authoritative port allocation, host capacity, memory pressure,
   disk headroom, Docker cgroup mode, private network address, and listener
   collisions.
3. Treat an existing unowned PostgreSQL process, data directory, or listener as
   a collision. Stop before mutation rather than adopting or replacing it.
4. State the resource class, provisional ceilings, exposure paths, backup
   retention, recovery point limits, downtime, and compensation behavior.

## Apply

1. Require a current user authorization and an exact inspected generation.
2. Re-inspect under one host-owned lock and reject generation or admission
   drift before writing.
3. Generate the superuser credential on the target into a root-only secret
   source. Never pass it in argv, Compose environment values, output, journal,
   or Git.
4. Pin the PostgreSQL major and minor image tag, record the pulled image ID,
   and render the exact Compose model before start. Give every long-running
   container finite CPU, memory, PID, and restart limits.
5. Use `/var/lib/host-infra/postgres` as the default host-owned persistence
   root. Persist data, WAL archive, and base backups below it and outside the
   container lifecycle. Do not place new shared PostgreSQL state under a
   consuming project's namespace. Treat changing an existing persistence root
   as a separate data migration with explicit downtime, snapshot, rollback,
   and verification authorization. Enable checksums, SCRAM host
   authentication, WAL archiving, and a verified recurring base-backup job
   before declaring the service deployed.
6. Publish only the declared loopback or approved private-network bindings.
   Never bind PostgreSQL to a public wildcard to make a client connect.
7. Snapshot managed configuration before mutation. Compensation may restore
   configuration and stop a newly created container, but must preserve database
   data and credentials for diagnosis. Data rollback or deletion requires a
   separate destructive authorization.

## Verify

- Verify a SQL round trip, exact server version, data checksums, SCRAM, archive
  mode, archive progress, the latest base backup, and the backup timer.
- Verify Docker HostConfig reports nonzero finite memory, CPU, and PID limits
  and the intended restart policy.
- Verify exact host bindings and prove public wildcard bindings are absent.
- Verify only one governed PostgreSQL server is present and no native service
  or unmanaged container conflicts.
- Report safe paths, transaction identity, generations, image ID, backup age,
  resource values, and remaining recovery gaps. Do not report connection
  strings or secret-derived values.

Consumer provisioning, schema migration, live cutover, restoration, major
upgrade, retention reduction, and service retirement are separate transactions;
ordinary service deployment does not authorize them.
