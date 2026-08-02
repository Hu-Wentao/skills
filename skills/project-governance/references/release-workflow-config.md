---
mdq:
  version: 1
  dialect: gfm
  records:
    boundary:
      source: heading
      levels: [2]
    key:
      source: heading
  fields:
    title:
      source: heading
    raw:
      source: body
  tolerance:
    incomplete: false
---
# Managed Release Workflow Configuration

Use the managed workflow when a repository needs the universal release lineage
without copying another project's release scripts. The skill owns Git and
release identity; the repository owns only version location and deterministic
hooks.

## Bootstrap

Inspect first:

```bash
uv run python <skill-root>/scripts/project-governance.py \
  --cwd <project-root> release inspect
uv run python <skill-root>/scripts/project-governance.py \
  --cwd <project-root> release bootstrap-plan --preset auto
```

After current user authorization, `release bootstrap --preset auto` writes
`.agents/skills-config/project-governance/release-workflow.json`. It never
invents an artifact repository, deployment target, remote host, migration, or
acceptance check. The scaffold therefore remains fail-closed until those hooks
are filled in and reviewed.

Supported version presets are:

- `node-pnpm`: `package.json`; discovers existing `lint`, `typecheck`, and
  `test` package scripts.
- `python-uv`: `pyproject.toml`; leaves gates project-owned.
- `flutter-fvm`: `pubspec.yaml`; declares `fvm flutter analyze` and
  `fvm flutter test`.

## Schema

```json
{
  "schema": "project-governance.release-workflow.v1",
  "integration_branch": "main",
  "version": {
    "kind": "package-json",
    "path": "package.json"
  },
  "gates": [
    ["pnpm", "lint"],
    ["pnpm", "typecheck"],
    ["pnpm", "test"]
  ],
  "artifact": {
    "freeze": ["pnpm", "release:artifact-freeze"]
  },
  "targets": {
    "preproduction": {
      "deploy": ["pnpm", "release:deploy", "--target", "{target}"],
      "verify": ["pnpm", "release:verify", "--target", "{target}"]
    }
  }
}
```

`version.kind` is one of `package-json`, `pyproject`, or `pubspec`. Its path
must stay inside the repository and exist. Commands are argv arrays, never shell
strings. The engine substitutes `{version}`, `{tag}`, `{target}`, `{worktree}`,
and `{artifact_manifest}` in individual arguments.

The engine also exports:

```text
PROJECT_GOVERNANCE_RELEASE_VERSION
PROJECT_GOVERNANCE_RELEASE_TAG
PROJECT_GOVERNANCE_RELEASE_TARGET
PROJECT_GOVERNANCE_RELEASE_WORKTREE
PROJECT_GOVERNANCE_ARTIFACT_MANIFEST
PROJECT_GOVERNANCE_REPOSITORY
```

Do not put credentials in configuration, argv, hook output, or artifact
evidence. Hooks load credentials through the project's existing protected
runtime mechanism.

## Artifact Boundary

For the first release target, the artifact freeze hook runs before the
annotated stable tag is created. For a later target, `release promote` runs the
same hook from a clean detached checkout of the exact stable tag before that
target is deployed. In both cases the hook must build or stage the exact
target artifact and finish stdout with one JSON object:

```json
{
  "schema": "project-governance.artifact-freeze.v1",
  "artifacts": [
    {
      "name": "application",
      "digest": "sha256:0123456789abcdef"
    }
  ]
}
```

Artifact names and digests are opaque to the engine but must be immutable and
content-identifying. The engine persists manifests by `(release tag, target)`.
The deploy hook receives the selected manifest path and must consume those
artifacts. It must not rebuild, retag different bytes, or resolve a moving
branch. An existing target manifest is immutable; promotion and fixed-tag retry
reuse it. Historical single-manifest records remain readable when their
recorded target matches the requested target.

When a target uses shared host ingress, the deploy hook must delegate that
surface to the installed `host-governance` v2 task contract. It may render or
submit only the project's declared ingress intent. It must not edit or restore
the shared root configuration, invoke the shared reload directly, or duplicate
host transaction phase rules. Run the read-only host plan before application
mutation when useful, then invoke authorized host apply only after the
candidate loopback origin is ready and read-only host verify before declaring
target completion.

Persist the host transaction reference in project deployment evidence with the
stable transaction ID, base/result generation, desired declaration digest,
composed candidate digest, phase, and verification state. Do not persist the
complete host journal, rendered shared configuration, credentials, or another
project's fragment. Application and host transactions remain independently
recoverable; a host failure may leave the application deployed but
ingress-incomplete and must not trigger an automatic application rollback.

## Optional Migration Hooks

Declare migrations only when the target workflow has explicit boundaries:

```json
{
  "migration": {
    "preflight": ["pnpm", "release:migration-preflight"],
    "apply": ["pnpm", "release:migrate"],
    "verify": ["pnpm", "release:migration-verify"]
  }
}
```

`release run --migration` fails if these hooks are absent. The engine persists
`migration_started` before invoking `apply`. After that phase, it never invokes
an old-version restart or rollback path. Database restore, rollback, and live
migration remain separate current-user authority.

## Universal Behavior

- Release inspection, planning, preparation, execution, deployment, promotion,
  and retry do not inspect or report control-worktree cleanliness. They resolve
  a committed ref and operate only in a new or retained isolated worktree.
- Normal preparation freezes the committed integration ref, excludes every
  staged, unstaged, and untracked control-worktree byte, reserves
  `release/v<version>`, and creates a retained sibling worktree.
- Repair preparation reserves only the immediate next patch and roots
  `repair/v<version>` directly at the failed annotated tag.
- Only one release command runs at a time per Git common directory.
- Gates and artifact freeze run in the retained candidate worktree.
- The stable annotated tag is created only after gates and artifact evidence
  pass for the first target.
- `release promote --tag <tag> --target <target>` creates no source commit. It
  reuses an existing immutable target manifest or appends the target's first
  manifest using hooks resolved from the exact tag checkout, then deploys that
  same release commit.
- Deployment success requires the configured verify hook and creates a
  `deploy/<target>/<UTC timestamp>/v<version>` tag pointing to the same commit
  as the stable release tag.
- Retry creates a fresh detached worktree at the exact tag and reuses the frozen
  target artifact manifest.
- After preparation, release and deployment status come only from the retained
  lineage and frozen evidence. Synchronization back to the integration branch
  is a separately reported post-release operation and cannot downgrade the
  release state.

Project-owned v3 contracts remain supported for workflows that already own the
same invariants. Do not mix one lineage between managed and project-owned
executors.
