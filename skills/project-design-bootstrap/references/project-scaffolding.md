# Project Scaffolding Rules

Use these rules when bootstrapping or documenting a project's initial engineering shape.

## Contents

- Package And Runtime Managers
- Project Scripts
- Docker And Compose
- Node/pnpm Docker Caching
- Compatibility Notes

## Package And Runtime Managers

- Python projects use `uv`.
- Node projects use `nvm` plus `pnpm`.
- Flutter projects use `fvm`.
- Prefer the repository's existing package manager when extending an existing project.
- Keep lockfiles committed and treat lockfile drift as a build failure unless the user explicitly asks for a dependency update.

## Project Scripts

- Place project scripts under the repository root `scripts/` directory.
- Name development runtime entry scripts as `dev-<module-name>.sh`.
- Keep `dev-*` scripts as thin entrypoints that select the module/profile and delegate to a shared script or library.
- Put cross-module behavior in the shared script: dependency profiles, environment defaults, build/no-build decisions, and startup flags.
- For dev scripts that start a module plus dependencies, document the module as the target and the other modules as dependencies.
- If dependency containers are already running, the shared script should prefer starting without `--build`; if required dependencies are not running, it should build and start them.
- Name release/production runtime scripts and other operational scripts with the `run-` prefix.
- Treat `run-*` scripts as release-mode runs unless the repo explicitly defines another convention; after startup, they usually do not hot reload when source files change.

Example: `scripts/dev-lab.sh` delegates to a shared compose runner with target `lab`. The shared runner knows `data-srv` and `worker` are dependencies; when both dependency containers are running, it starts `lab` without `--build`, otherwise it builds and starts the required profile set.

## Docker And Compose

- Do not assume Docker build can use host package caches or runtime volumes.
- Remember that compose `volumes` apply when containers run, not while `docker build` executes.
- Keep build-time dependency cache decisions in `Dockerfile`; keep runtime source mounts and data volumes in compose files.
- Prefer BuildKit cache mounts for dependency stores when the package manager supports a stable store path.
- Copy lockfiles and workspace manifests before source files so dependency layers do not rebuild on ordinary source edits.

## Node/pnpm Docker Caching

Use this pattern for pnpm workspaces in Docker builds:

```dockerfile
# syntax=docker/dockerfile:1.7

FROM node:24-bookworm-slim AS base
WORKDIR /app
RUN corepack enable
ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm fetch --store-dir /pnpm/store --frozen-lockfile

COPY tsconfig.base.json eslint.config.js ./
COPY packages ./packages
COPY apps ./apps
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --store-dir /pnpm/store --frozen-lockfile --offline
```

Key points:

- First build may still download packages because the Docker BuildKit cache starts empty.
- Later builds can reuse the `pnpm-store` cache and the `pnpm fetch` layer.
- `pnpm install --offline` should not access the registry; if it fails, the fetch layer did not fully populate the store.
- Use `--frozen-lockfile` in image builds. Do not use `--frozen-lockfile=false` to hide lockfile drift.
- Runtime `node_modules` volumes can speed local dev containers, but they do not make build-time `pnpm install` reuse the host store.

## Compatibility Notes

- BuildKit syntax requires a Docker builder that supports Dockerfile frontend `1.7` or compatible behavior.
- If a repo cannot require BuildKit, document the fallback explicitly and expect slower dependency installs.
- List breaking changes and compatibility/configuration decisions after modifying scaffolding.
