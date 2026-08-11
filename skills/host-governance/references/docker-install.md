# Governed Docker Installation

Install Docker only through project-owned `host-governance.config.v2` control
operations. Require separate `inspect`, `plan`, `apply`, and `verify`
operations; add `rollback` only when the project can define a bounded removal
or restoration contract that preserves unrelated containers and data.

## Inspect

Resolve one exact device manifest and use only its declared SSH alias and route.
Collect secret-safe facts before selecting packages:

- operating system, release, architecture, init system, kernel, and cgroup version;
- installed and candidate Docker Engine, CLI, containerd, runc, Buildx, and
  Compose packages, including package holds and mixed-source conflicts;
- rootful, rootless, distribution, Snap, and Docker CE installations;
- daemon/socket active and enabled states, server and client versions, cgroup
  driver, storage driver, Docker root directory, and bounded image/container counts;
- `/etc/docker/daemon.json` presence and digest without returning its contents;
- Docker-owned TCP listeners, firewall state, free disk and inode capacity, and
  any existing service that owns the requested runtime or data directory.

Stop on an unsupported platform, mixed package ownership, an active unmanaged
daemon, insufficient capacity, a held required package, or an unexplained
listener or data-root collision. Do not infer a target or scan the network.

## Plan

Let the host repository declare the accepted package source and version policy.
Prefer distribution packages when their lifecycle and version satisfy the host
policy. Use Docker's official repository only when explicitly selected and
contract its signing key, repository identity, conflicting-package removals,
update channel, and recovery behavior. Never pipe a remote install script to a
shell as the governed installation path.

Define the complete desired state and digest before writing. At minimum include
package identities, daemon/socket lifecycle, Compose and Buildx requirements,
cgroup driver/version, storage root, daemon-config policy, network exposure,
and whether a container smoke test may pull an image. Default to:

- no TCP Docker API listener or firewall change;
- no registry mirror, insecure registry, proxy, or daemon configuration rewrite;
- no user addition to the root-equivalent `docker` group;
- no migration or deletion of `/var/lib/docker`;
- no automatic package-source replacement or removal of another runtime.

Report downloads, service starts/restarts, expected downtime, disk impact,
external registry access, irreversible package/data effects, and recovery
limits before apply. Snapshot installed package versions/selections, service and
socket states, daemon-config metadata, bounded runtime counts, and existing
smoke-test image ownership. Test the recovery commands without removing data.

## Apply

Require current authorization for the exact host. Under one remote host lock:

1. Re-read authoritative and live state and reject generation drift.
2. Persist a secret-safe transaction record and snapshot.
3. Refresh only the selected package source and install the declared packages
   non-interactively without silently replacing a conflicting installation.
4. Validate any daemon-config candidate before atomically installing it. Merge
   with the current owned configuration; never overwrite unknown keys.
5. Enable/start or restart only the declared service and socket.
6. Verify the daemon API, server version, Compose/Buildx commands, storage and
   cgroup state before continuing.
7. Run the contracted container smoke test when authorized. Remove the test
   container and remove its image only when the transaction introduced it.
8. Record result generation, package versions, transaction phase, verification,
   snapshot path, and every deliberately preserved change.

On failure, stop forward progress. Restore prior daemon configuration and
service/socket enable/active states when safe. Preserve newly installed packages
and `/var/lib/docker` unless a separately authorized rollback contract proves
they were absent, unused, and owned only by this transaction. Never compensate
with broad package purge, `docker system prune`, or Docker data-root deletion.

## Verify and Report

Run a fresh read-only verification after apply. Prove the declared packages and
versions, active/enabled daemon, Docker API response, Compose/Buildx readiness,
expected cgroup driver/version, unchanged daemon configuration when no change
was planned, and zero leftover smoke-test containers/images introduced by the
transaction. Compare effective TCP listeners and firewall exposure with the
baseline; a Unix socket is not a public listener, and a new unexplained TCP
listener is a finding even when bound to loopback.

Report the transaction ID, base and result generations, package source and
versions, journal/snapshot locations, smoke-test result, exposure result,
reboot requirement, recovery state, and unverified gaps. Record stable desired
runtime facts in the host repository only when the current request authorizes
that repository write; do not promote transient counts or live observations.
