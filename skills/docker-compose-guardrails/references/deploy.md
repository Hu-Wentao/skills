# Generic Deployment Resource Policy

## Classify workloads

Classify every long-running service and build workload before deployment:

- `critical`: must retain an explicitly justified minimum during host pressure.
- `standard`: bounded production workload without a hard minimum.
- `best-effort`: development, build, batch, and disposable work that yields
  first under pressure.

Fail closed when a service has no class. Keep project service names, topology,
host size, and numeric budgets in the project profile.

## Protect minimum resources on the host

Use the host's cgroup v2 hierarchy, normally through persistent systemd slices,
for minimum-resource protection:

- Give critical leaf cgroups an explicit `memory.min` and finite `memory.max`.
- Use `memory.low` only as soft reclaim protection; do not report it as a hard
  minimum.
- Set compatible protection on relevant ancestors. An unprotected or
  overcommitted parent can weaken the intended leaf guarantee.
- Use higher `cpu.weight` for priority under contention. Do not report
  `cpu.weight` as a hard CPU minimum; use exclusive cpusets or equivalent
  capacity isolation when a strict CPU floor is required.
- Give standard and best-effort workloads finite maxima. Give builders no
  protected memory minimum.

Docker recreates container cgroups. Make placement and leaf settings durable
through `cgroup_parent`, managed systemd units, an idempotent lifecycle
reconciler, or an orchestrator with equivalent verified behavior. Do not rely
on a one-time manual write.

## Admit only feasible deployments

Before build or deployment, read actual host capacity and current workload
state. Reject the operation unless all configured invariants hold:

```text
host reserve + sum(critical memory.min) <= protectable host memory
current protected commitments + proposed protected commitments <= policy budget
```

The host reserve must cover the kernel, Docker, networking, ingress, monitoring,
and operational headroom. Treat swap as emergency latency capacity, not as
protected service memory. A project profile may impose a stricter worst-case
limit using service maxima.

Do not start work merely because `MemAvailable` currently looks sufficient.
Also evaluate the project's declared memory-pressure signal, such as PSI, and
any existing OOM or cgroup pressure condition. Return a stable, actionable
error naming the failed invariant and observed versus allowed values.

## Isolate builds

Place BuildKit and its executor containers in a bounded best-effort cgroup or
use a remote builder. Limit memory, CPU, and process count for the whole build
execution tree. Placing only the CLI client in a slice does not constrain a
separate BuildKit daemon.

Reject a build that fails admission. During a build, cancel its complete solve
when the project pressure gate crosses its threshold, preserve the original
build failure output, and report that resource protection stopped the build.
Do not stop critical runtime services to make room for a build.

## Verify effective state

After container creation, verify both Docker HostConfig and host cgroups:

- every long-running container has finite memory, CPU, and PID bounds;
- every container is in its declared resource class;
- critical leaf and ancestor cgroups expose the configured `memory.min`;
- effective `memory.max`, CPU controls, and restart policy match the profile;
- BuildKit daemon and executor cgroups are inside the declared builder boundary;
- the sum of observed protected minima remains within the admission budget.

Fail the deployment when effective state differs from resolved policy. Report
observed values, not only configuration text.
