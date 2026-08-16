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
4. Collect the inputs required by `scripts/postgres_sizing.py`: host memory,
   currently available memory, CPU count, free disk, current PostgreSQL RSS,
   other-service memory budget, memory PSI, storage class, aggregate pool
   limit, observed WAL rate, archive-filesystem free space, archive retention,
   and accepted archive RPO. Define the other-service budget as the larger of
   declared critical minima or observed p95 plus reviewed growth margin; never
   subtract only current idle usage from host memory.
5. Run the sizing tool before proposing PostgreSQL or container parameters:

   ```bash
   uv run python <skill-root>/scripts/postgres_sizing.py \
     --host-memory-mib <total> \
     --host-available-memory-mib <available-now> \
     --cpu-count <logical-cpus> \
     --other-services-budget-mib <non-postgres-budget> \
     --disk-free-mib <free-on-pg-filesystem> \
     --current-postgres-rss-mib <rss-reclaimed-on-restart> \
     --current-shared-buffers-mib <current-shared-buffers> \
     --pool-max-connections <aggregate-pool-limit> \
     --wal-rate-mib-per-hour <observed-or-declared-peak> \
     --archive-free-mib <free-on-archive-filesystem> \
     --archive-retention-hours <accepted-retention> \
     --archive-filesystem shared \
     --psi-some-avg10 <memory-some-avg10> \
     --psi-full-avg10 <memory-full-avg10> \
     --archive-rpo-minutes <accepted-rpo> \
     --workload mixed \
     --storage ssd
   ```

   Use `--mode dedicated` only when the authoritative topology proves that no
   unrelated long-running workload shares the host. Supply
   `--historical-available-p10-mib` before considering the balanced option.
6. State the selected option, every input, derived host reserve, other-service
   budget, hard PostgreSQL ceiling, blockers, exposure paths, backup retention,
   recovery point limits, downtime, and compensation behavior. Persist a hash
   of the sizing result in the project-owned desired state so later apply can
   reject stale capacity evidence.

## Hardware-aware Defaults

Treat the sizing output as starting configuration, not a benchmark result.
Select `shared-conservative` by default on a shared host. Select
`shared-balanced` only with an explicit user choice, historical memory
headroom, and no admission blocker. Select `dedicated` only for a verified
database-only host.

The calculator enforces these boundaries:

- Reserve 25% of shared-host RAM, with at least 1 GiB, for the kernel, page
  cache, host daemons, and transient pressure. Subtract the reviewed budget for
  every other service before computing the PostgreSQL hard ceiling.
- Cap a conservative PostgreSQL container near 30% of host RAM and a balanced
  shared-host container near 40%, subject to the smaller hard ceiling. Raising
  a cgroup maximum does not justify increasing PostgreSQL allocations.
- Start `shared_buffers` at 25% of the PostgreSQL container budget. PostgreSQL
  documents 25% of system memory as a reasonable starting point for a
  dedicated server and says more than 40% is unlikely to perform better; a
  shared container must remain at least as conservative.
- Treat `effective_cache_size` only as a planner estimate. It does not reserve
  memory and must not be counted as available capacity.
- Derive `max_connections` from CPU and the aggregate external pool budget.
  Reject a pool larger than the hardware option instead of raising server
  connections to match it.
- Derive `work_mem` from the remaining private-memory budget, active pooled
  concurrency, and multiple concurrent sort/hash operations. Never multiply a
  per-query value by only `max_connections`; one query can allocate it several
  times and parallel workers can multiply it again.
- Keep `checkpoint_completion_target=0.9`. Size `max_wal_size` to at least
  twice `shared_buffers` and to the observed peak WAL generated across two
  checkpoint windows. PostgreSQL describes `max_wal_size` as a soft limit and
  warns that too-small values cause frequent, expensive checkpoints.
- Derive `archive_timeout` from the accepted recovery-point objective, not RAM
  or CPU. Short timeouts force partially filled 16 MiB segments and can bloat
  archive storage. Check archive capacity against the larger of observed WAL
  rate or the forced 16 MiB segment-switch rate, using the full accepted
  retention period and no assumed compression saving. When archive and data
  share a filesystem, require their combined headroom rather than validating
  both budgets independently. Retention must remain anchored to verified
  base-backup chains.

Parameter semantics and the shared-buffer starting point come from the
[PostgreSQL resource-consumption documentation](https://www.postgresql.org/docs/current/runtime-config-resource.html).
Checkpoint and WAL behavior come from the
[WAL configuration guide](https://www.postgresql.org/docs/current/wal-configuration.html)
and [WAL parameter reference](https://www.postgresql.org/docs/current/runtime-config-wal.html).

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
   Require the rendered limits and PostgreSQL parameters to equal one eligible
   sizing option. Recompute under the executor lock and reject a changed sizing
   hash, failed blocker, or undocumented manual override.
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
- Verify every effective PostgreSQL memory, connection, checkpoint, and WAL
  value against the selected sizing result. Report the post-start RSS,
  available memory, memory PSI, checkpoint frequency, WAL rate, and archive
  failure count; successful startup alone is not sizing evidence.
- Verify exact host bindings and prove public wildcard bindings are absent.
- Verify only one governed PostgreSQL server is present and no native service
  or unmanaged container conflicts.
- Report safe paths, transaction identity, generations, image ID, backup age,
  resource values, and remaining recovery gaps. Do not report connection
  strings or secret-derived values.

Consumer provisioning, schema migration, live cutover, restoration, major
upgrade, retention reduction, and service retirement are separate transactions;
ordinary service deployment does not authorize them.
