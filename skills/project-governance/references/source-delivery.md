# Source Delivery Modes

Release and deployment workflows may use exactly one of these source-delivery
modes:

1. `archive`
2. `github`

No third mode, ad hoc file list, direct worktree copy, `rsync`-based source
acquisition, server-side `git pull`, floating branch, or moving tag is allowed.

## Archive

The executor must script the complete operation for one frozen full commit:

1. Resolve the full commit and tree from the retained release or repair
   lineage.
2. Create one archive from that commit with `git archive`; do not archive the
   current worktree and do not enumerate files manually.
3. Compute the archive byte count and SHA-256 once and persist a commit/tree/
   archive manifest.
4. Stream the exact archive through the contracted transport into a private,
   commit-scoped receiver path.
5. Verify the received byte count and SHA-256 before extraction.
6. Extract into a fresh private directory with path-traversal checks, then
   verify the manifest's commit and tree identity.
7. Execute every source-verification, build, and deployment helper from that
   verified tree. Relative imports must resolve inside the same tree; do not
   copy a helper or its dependencies into a second manually maintained
   directory.
8. Propagate archive, extraction, verification, child-process, and cleanup
   failures. Do not write an artifact manifest or success marker after any
   failed child command.
9. Remove the temporary archive and extracted tree after the transaction, or
   retain them only under the governed failure-evidence policy.

The deterministic source-preparation command owns steps 1-3 and produces the
only archive and manifest accepted by the deployment controller. The
deterministic deployment controller owns steps 4-9; one shared receiver
implementation must perform steps 4-6 for every admission, artifact-freeze,
and deployment path before the controller performs steps 7-9. Do not require a
local `prepare` process to perform remote execution, and do not let AI reproduce
either boundary as shell snippets.

## GitHub

The source-preparation command must use a deterministic project script or the
approved GitHub client to obtain one exact full commit from one canonical
GitHub repository.
The script must:

- accept an owner/repository and full commit SHA, never a branch, `main`,
  `latest`, or an unqualified tag;
- resolve and verify the GitHub commit and tree identity before execution;
- download a commit-pinned archive or immutable release asset, hash it before
  extraction, and bind that digest to the manifest;
- keep GitHub tokens in the existing secret-file or protected environment
  mechanism, never argv, logs, manifests, or generated control scripts;
- propagate every fetch, digest, extraction, and preparation failure.

The deployment controller must pass the resulting archive through the same
receiver and source-execution boundary as archive mode. It must execute only
from the verified extracted tree and propagate every receiver and child-process
failure.

The server must not run `git clone`, `git fetch`, or `git pull` against a moving
ref as a deployment operation. GitHub is a source/artifact authority, not a
license to read repository state implicitly.

## Selection and evidence

The project profile declares the default mode, the exact source-preparation
command, and the deployment controller that owns transport, receiver
verification, extraction, execution, and cleanup. A per-run override is valid
only when the task contract declares the enum `archive|github`; every
mode-specific required input must also be expressible through that contract.
Record the selected mode, repository or commit identity, tree identity,
archive/asset digest, and receiver verification result as safe evidence. Never
include credentials, request bodies, or Capture payloads. A post-verification
installation sync from the verified extracted tree is not a third source-
delivery mode.
