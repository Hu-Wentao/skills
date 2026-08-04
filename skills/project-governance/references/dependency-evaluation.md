# External Dependency and Technology Evaluation

## Preserve Authority

Evaluate current or proposed third-party libraries, frameworks, services, and
runtimes without making adoption implicit.

Treat a request to evaluate a technology for an active writable project as
authorization to create or revise the smallest governed evidence records
defined below, unless the user explicitly requests a chat-only/read-only result
or forbids writes. When compatible shared storage is available, that authority
covers one reusable upstream assessment there and one project-fit record in the
active project. It does not cover unrelated resource-memory content. Complete
both records before the final response. Upstream inspection remains read-only,
and this default does not authorize changes to a Plan, Baseline, manifest,
lockfile, code, infrastructure, release, or deployment. If no active writable
project exists, return the evaluation without inventing a documentation
destination or writing a shared assessment.

- Treat manifests, lockfiles, deployment configuration, code, and runtime
  inspection as authority for what the project currently depends on.
- Treat requirements, baselines, and accepted plans as authority for intended
  product behavior and architecture.
- Treat an evaluation record as decision-support evidence only. Creating it
  does not authorize installation, migration, deployment, or replacement.

## Gather Evidence

1. Read repository instructions and the minimum current baselines, plans,
   manifests, and code needed to identify the affected project scope.
2. Prefer current first-party sources: official documentation, source
   repository, package registry, license, security policy, and release status.
3. Record the evidence date and an exact version, tag, or commit when available.
4. Separate upstream claims, observed project facts, and project-fit inference.
5. State whether the technology concerns the project's core path, an adjacent
   capability, tooling, or a possible replacement. Do not infer adoption from
   conceptual overlap.

## Select the Storage Contract

Do not infer integration support from an installed directory or skill name.
When `recall-resources` is present in the active skill catalog:

1. Read that skill and invoke its bundled wrapper with `capabilities --json`.
2. Require schema `resource-memory.capabilities.v1` and
   `capabilities.shared_open_source_assessment.version >= 1`.
3. If compatible, run `evaluation get --url <repository-url> --json` before
   writing. Reuse the stable ID; upsert only the newly completed general
   assessment and capture the returned `revision` and normalized source URL.
4. If the skill is absent, capability output is incompatible, or the operation
   fails before a shared write, use the complete local fallback below. Do not
   create a partial `TECH-FIT-*` record without a valid shared ID and revision.

Skill availability does not broaden evaluation authority, and an evaluation
does not authorize indexing if immediate semantic recall was not requested or
needed. If the shared upsert succeeds but the local project write later fails,
preserve the valid shared evidence, report the incomplete local record, and do
not delete or roll back unrelated shared knowledge.

## Write the Shared Upstream Assessment

With a compatible capability, place all reusable upstream facts in the shared
`RESOURCE-ASSESS-*` record through `evaluation upsert`; do not directly edit its
storage path. Include:

- normalized repository URL and exact evaluated version, tag, or commit;
- evaluation date and concise general summary;
- general capabilities, architecture, compatibility, maintenance, security,
  strengths, and risks as supported by evidence;
- official evidence and explicit review triggers.

Never include the consuming project's constraints, fit, integration cost,
blockers, disposition, or adopt/reject recommendation. The returned stable ID
and `sha256` revision identify the exact authoritative Markdown evaluated by
the consuming project. A later shared update creates a different revision and
must not retroactively change a local conclusion.

## Write the Local Project-Fit Record

Follow an existing repository convention. Otherwise create one governed record
under `docs/evaluations/<slug>.md` with stable `TECH-FIT-<SLUG>` identity. Expose
only these lifecycle, decision, and evidence-pin fields through its persistent
mdq contract:

- `status`: `researching`, `assessed`, `trial`, `adopted`, `rejected`, `stale`,
  or `superseded`;
- `scope`: the affected project, module, or product surface;
- `fit`: `strong`, `partial`, `weak`, or `blocked`;
- `disposition`: `undecided`, `adopt`, `trial`, `watch`, or `reject`;
- `evaluated`: the project-fit evidence date in `YYYY-MM-DD` form;
- `shared_assessment`: the exact `RESOURCE-ASSESS-*` ID;
- `shared_revision`: the exact returned `sha256:<hex>` revision;
- `upstream_ref`: the exact evaluated version, tag, or commit.

Keep project constraints, integration cost, material gaps, blockers, fit
reasoning, and the project-specific recommendation in bounded prose. Link the
normalized shared source URL for human navigation, but do not duplicate the
shared feature inventory, architecture, license, maintenance, security, or
generic risk analysis. The fit record's revision pin remains unchanged until a
new project evaluation explicitly adopts a newer shared revision.

## Complete Local Fallback

When the shared capability is unavailable, follow the existing repository
convention. Otherwise create one complete governed record under
`docs/evaluations/<slug>.md` with a stable `TECH-EVAL-<SLUG>` identity. Expose
only these five lifecycle and discovery fields through its persistent mdq
contract:

- `status`: `researching`, `assessed`, `trial`, `adopted`, `rejected`,
  `stale`, or `superseded`;
- `kind`: a concise technology class such as `library`, `framework`,
  `service`, `runtime`, or a project-established specialization;
- `scope`: the affected project, module, or product surface;
- `disposition`: `undecided`, `adopt`, `trial`, `watch`, or `reject`;
- `evaluated`: the evidence date in `YYYY-MM-DD` form.

Keep license, maturity, upstream version or commit, source URLs, strengths,
risks, general upstream analysis, and detailed project compatibility findings
in bounded prose. Promote one to a declared field only after a repeated
cross-document query requires it. Do not create a sidecar index for a small
collection; use mdq collection scanning.

For either local record shape, include a concise conclusion, scope and
authority boundary, project fit, material gaps or risks, recommendation, and
review triggers. The complete fallback also includes official upstream
evidence. Use one record for the current assessment instead of accumulating
dated snapshots. Mark it `stale` or revise it when the pinned upstream evidence
or relevant project boundary changes.

If the disposition becomes `adopt` or `trial`, obtain separate implementation
authorization and update the applicable Plan, Baseline, manifest, lockfile, and
verification ownership. The evaluation record remains evidence, not the
adoption authority.

## Verify Queryability

Use `queryable-markdown` to validate and diagnose the document, query its exact
ID and an absent ID, query representative declared fields, and scan the
evaluation directory with `--require-contract`.
