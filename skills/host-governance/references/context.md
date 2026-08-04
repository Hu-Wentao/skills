# Generic Shared Host Context

Use this workflow only for repository-declared shared host information. It does
not inspect live hosts, networks, services, or provider APIs.

## Locate the authority

Prefer a current user-provided path, an authority already established in the
task, or `HOST_INFRA_ROOT`. Otherwise read
`~/.host-infra/control.yaml` when it exists. The locator may contain only a
mechanical pointer such as `repository_root`; it is local runtime configuration
and must not be copied into this skill, another repository, or a response.

Resolve the path, require it to be a Git repository, and require its own
`.agents/skills-config/host-governance/config.yaml` to declare a contracted
`context` task. Stop on a missing, invalid, or ambiguous locator. Never scan the
user's filesystem to guess a repository.

## Query the project contract

- `catalog`: list available device and record metadata when IDs are unknown.
- `search`: return candidate metadata for a bounded query, without record bodies.
- `get`: return one exact device or record selected by stable ID.
- `current-device`: match the local host only when the project contract exposes
  the operation; do not infer identity from a nearby name or address.

Run operations through the validated host-governance runner. Follow the
repository profile's limits and output schema. A search result is not final
authority; use its exact kind and ID with `get` when content is required.

## Preserve evidence boundaries

- Report the repository root, branch, HEAD, dirty state, source paths, content
  digest, read time, and freshness when the project output provides them.
- Treat `local-working-tree` as the newest content currently on disk, not proof
  that the checkout matches a remote branch.
- Never fetch, pull, switch branches, or edit the authority as part of a read.
- Never run SSH, network probes, provider APIs, or service health checks from a
  context query. Fields marked as requiring live verification remain unverified.
- Never return credentials, tokens, private keys, passwords, secret values, or
  environment dumps. Do not store query output as a second inventory.
- Resolve `control` under its own contract and authorization rules for live
  inspection, host writes, external writes, or rollback.
