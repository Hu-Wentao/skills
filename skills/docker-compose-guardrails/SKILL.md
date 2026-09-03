---
name: docker-compose-guardrails
description: Review, change, or deploy Docker Compose services with finite container limits, host minimum-resource protection, bounded builds, and safe startup. Use for Dockerfiles, Compose files, cgroups/systemd slices, deployment configuration, or CPU, memory, PID, OOM, restart, and build-pressure incidents.
---

# Docker Compose Guardrails

Treat an omitted resource limit as a defect for every long-running service unless a documented exception names its owner and duration.

## Resolve Policy

```bash
uv run python <skill-root>/scripts/resolve.py --cwd <project-root> --task deploy
```

Read the returned instructions when `instructions_id` changes. Project resource classes, budgets, topology, and checks belong in `.agents/skills-config/docker-compose-guardrails/`; see [project_config.md](references/project_config.md). Detailed generic deployment policy is in [deploy.md](references/deploy.md).

## Enforce Boundaries

For each long-running service set finite service-level `cpus`, `mem_limit`, and `pids_limit`, plus an appropriate `restart` policy. Do not rely only on `deploy.resources`; local Compose enforcement varies. Values may be provisional when workload evidence is absent, but name the measurement that will refine them.

Allow unbounded resources only for a short-lived manual task with an explicit reason and owner. Compose limits are ceilings, not minimum guarantees. When selected workloads need minimum protection, also apply the resolved host cgroup policy and verify every relevant ancestor.

## Separate Build and Runtime

Reject build commands in a long-running service `command` or `entrypoint`. Build artifacts in the Dockerfile, normally through a multi-stage build, and start only the runtime artifact. A manual short-lived build task must have no restart policy and a documented owner.

Bound the builder daemon and executor containers at the host layer or use a reviewed remote builder. Stop when admission or pressure gates fail; client-process limits alone are insufficient.

## Validate

```bash
python3 <skill-root>/scripts/check_compose_guardrails.py -f compose.yaml
docker compose -f compose.yaml config
```

Resolve errors and review warnings. Run resolved preflight commands before live changes; resolution declares commands but never executes them.

After `docker compose up -d`, verify effective Docker HostConfig:

```bash
docker inspect <container> --format 'Memory={{.HostConfig.Memory}} NanoCPUs={{.HostConfig.NanoCpus}} PidsLimit={{.HostConfig.PidsLimit}} Restart={{.HostConfig.RestartPolicy.Name}}'
```

Constrained services require nonzero memory/CPU and a finite PID limit. For minimum-resource protection, verify the leaf and ancestor cgroups, resource class, memory controls, CPU control, and builder containment after every recreate.

## Report

For each service report resource class, configured and effective CPU/memory/PID/restart values, host-cgroup checks, admission/build boundaries, and every exception with reason, owner, and expiry.
