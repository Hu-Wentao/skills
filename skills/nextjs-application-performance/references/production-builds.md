# Production Builds

## Contract

Use a project-owned `nextjs-build-contracts.v1` manifest. Do not infer durable
admission lists from a one-off build log. Each app entry declares:

- app root, package manifest, Next config, standalone directory, and files
  containing build-policy knobs;
- every direct pnpm workspace dependency with package root, one of `server`,
  `client`, or `hybrid`, and its public entrypoints;
- the exact package or subpath imports admitted to Next/webpack server
  externalization;
- an exact `containerLimitMiB`, the current and baseline V8 heap limits, a
  cold-output path, and runtime smoke command/routes;
- any measured exception for a heap increase, `resolve.symlinks=false`, or
  `optimizePackageImports`, including an evidence file and required marker.

Run:

```bash
node scripts/audit-next-build-contract.mjs --manifest <manifest> --app <id>
node scripts/audit-standalone-closure.mjs --manifest <manifest> --app <id>
node scripts/run-build-memory-probe.mjs --manifest <manifest> --app <id> \
  --evidence <output.json> -- <cold-build-command...>
node scripts/smoke-next-standalone.mjs --manifest <manifest> --app <id>
```

When a Docker runtime stage supplements raw Next standalone output, run the
last two commands inside that final image with `--standalone-root /app` (or its
actual runtime root). Do not allowlist a dependency merely because an earlier
build stage omits bytes that the final runtime stage intentionally supplies.

Docker build contexts normally exclude `.git`. For a memory probe in such a
context, pass `--workspace-root /app` (or the actual copied project root). The
override must exactly equal the manifest's resolved `workspaceRoot`; it is not
an escape hatch for moving the cold path or command outside the declared tree.

The container and heap limits are distinct: the probe verifies the actual
cgroup `memory.max`, while the source audit rejects a heap limit above the
container or an increase over the declared baseline without measured evidence.

Run the memory probe only in the process whose cgroup namespace exposes that
exact finite limit. A Docker BuildKit `RUN` sandbox can report
`memory.max=max` even when the outer BuildKit daemon container is limited. Do
not treat the daemon's limit, a build argument, or a claimed host limit as
equivalent evidence. Use a regular container with an explicit memory limit for
the cold build (for example `docker run --memory=4g ...`) or an external monitor
that reads the exact worker cgroup. Keep final-artifact closure and runtime
smoke as a separate gate; they may still run in the final Docker stage.

The project may invoke the installed copies under
`.agents/skills/nextjs-application-performance/scripts/`. Repository CI must
own its manifest and commands; an installed skill on a developer machine is
not a CI dependency contract.

## pnpm Resolution and Package Boundaries

Resolve each direct `workspace:*` dependency from the Next app. Preserve the
lexical `node_modules` link and the package realpath. A realpath outside the app
is normal in pnpm and is exactly why a fix based only on apparent
`node_modules` location is unreliable.

Classify public behavior, not folder names:

- `server`: public entrypoints are safe only in the server graph;
- `client`: public entrypoints reach `"use client"`, `next/navigation`, or
  another client-only module;
- `hybrid`: separate public entrypoints serve both graphs.

`server-only` is a server signal. `"use client"` and `next/navigation` are
client signals. A root barrel that recursively re-exports both signals is
invalid even if the package is declared hybrid. Split it into explicit
subpaths. Do not externalize an entire hybrid package: a server compiler can
admit only an explicitly server-classified subpath.

Evaluate the production Next config and its server webpack externals against
the manifest. `serverExternalPackages` and custom webpack callbacks are both
admission surfaces. Every detected external must be declared, every declared
workspace external must be server-only at that exact scope, and unused
allowlist entries fail closed.

## Standalone Closure

Audit the standalone output in isolation from Next's production `.nft.json`
trace manifests. Every declared runtime entrypoint and traced file must exist,
and every traced realpath and symlink target must remain inside the standalone
root. A path that exists only through the parent source workspace is a missing
production dependency, not a passing artifact. Do not regex-scan every copied
JavaScript file: over-traced development and optional packages contain dynamic
or example imports that are not part of the selected runtime closure.

Run runtime smoke after the closure audit. Start the produced server, wait on
the declared readiness route, and fetch every declared route with its exact
allowed status. Smoke proves startup and selected route loading; it does not
replace authentication, database, or browser E2E coverage.

## Constrained Cold Build Evidence

Run the build probe inside the actual cgroup v2 container. The probe refuses
to run unless `memory.max` exactly matches the manifest limit and the declared
cold-output path is absent or empty. It samples the process tree RSS and
cgroup memory, records cgroup `oom`/`oom_kill` deltas, and classifies:

- `success`;
- `v8_heap_oom` from Node fatal heap evidence;
- `cgroup_oom` only from a positive cgroup OOM delta;
- `external_sigkill` for `SIGKILL` without OOM evidence;
- `process_exit_137` for exit 137 without OOM evidence;
- `process_exit`, `signal_exit`, or `spawn_error` otherwise.

Keep the full build command, exact limit, cold-path result, peak RSS, peak
cgroup memory, exit status, and reason in the evidence file. Do not raise the
heap or disable symlink semantics to make the probe pass. If one of the three
discouraged knobs is experimentally justified, record before/after evidence
and keep the production memory gate fixed.
