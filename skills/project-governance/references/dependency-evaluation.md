# External Dependency and Technology Evaluation

## Contents

- Preserve Authority
- Gather Evidence
- Capture the Global Resource Card
- Select the Storage Contract
- Write the Shared Upstream Assessment
- Partition Claims Before Writing Locally
- Write the Local Project-Fit Record
- Complete Local Fallback
- Verify Queryability

## Preserve Authority

Evaluate current or proposed third-party libraries, frameworks, services, and
runtimes without making adoption implicit.

Treat a request to evaluate a technology for an active writable project as
authorization to create or revise the smallest governed evidence records
defined below, unless the user explicitly requests a chat-only/read-only result
or forbids writes. When compatible shared storage is available, that authority
covers one global resource-card favorite, one reusable upstream assessment, and
one project-fit record in the active project. Complete all three records before
the final response. Upstream inspection remains read-only,
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

## Capture the Global Resource Card

When compatible `recall-resources` storage is available, preserve the evaluated
open-source project's basic facts in the global resource catalog before writing
the project-fit record:

1. Inspect the exact normalized repository URL with `show --url <repository-url> --json`.
2. If no exact catalog card exists, call `add` once with the neutral title,
   `open-source-project` type, normalized URL, concise reusable summary,
   reusable selection scenario, material reusable constraint, and the evidence-backed
   `verified` or `unverified` review status. Do not infer a personal usage
   evaluation.
3. Query it again and require exactly one result. If it already exists, preserve
   the card rather than creating a duplicate or overwriting its collection metadata.

The global card is not a shared assessment: it holds only concise general
discovery metadata. Do not put project fit, disposition, integration cost, or a
detailed upstream feature/security inventory in it. Do not rebuild the derived
index unless immediate recall is needed.

## Select the Storage Contract

Do not infer integration support from an installed directory or skill name.
When `recall-resources` is present in the active skill catalog:

1. Read that skill and invoke its bundled wrapper with `capabilities --json`.
2. Require schema `resource-memory.capabilities.v1`,
   `capabilities.resource_catalog.version >= 1`, and
   `capabilities.shared_open_source_assessment.version >= 1`.
3. If compatible, capture or reuse the global resource card as above, then run
   `evaluation get --url <repository-url> --json` before
   writing. Reuse the stable ID; upsert only the newly completed general
   assessment and capture the returned `revision` and normalized source URL.
4. If the skill is absent, capability output is incompatible, or the operation
   fails before the global-card and shared-assessment writes, use the complete
   local fallback below. Do not create a partial `TECH-FIT-*` record without a
   valid shared ID and revision.

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

## Partition Claims Before Writing Locally

Apply this section only when a compatible shared assessment was successfully
written or reused. The complete local `TECH-EVAL-*` fallback must retain both
upstream evidence and project-fit analysis.

Build a two-part claim inventory before drafting `TECH-FIT-*`:

1. Put a claim in the shared inventory when its meaning and evidence do not
   depend on the consuming project's state or policy. This includes upstream
   capabilities, mechanisms, dependencies, platform support, version and
   release facts, license, maintenance, security behavior, strengths, generic
   risks, and upstream review triggers.
2. Put a claim in the project inventory when it is supported by current
   project authority or describes a consequence unique to that project. This
   includes affected scope, existing alternatives, policy conflicts,
   integration work and ownership, migration cost, project blockers, fit,
   disposition, trial boundaries, and project review triggers.
3. Split a mixed claim into its reusable premise and project-specific
   consequence. Put the premise in the shared assessment and the consequence
   in the local record; do not copy the full premise into both.
4. Upsert the shared assessment first. Draft the local record from the project
   inventory plus the returned ID, revision, upstream ref, and normalized
   repository URL. Do not use a summary of the shared record as the local
   draft.

The local record may use a short bridge phrase that names the relevant shared
section or finding when the project consequence would otherwise be ambiguous.
The phrase must point to the pinned shared assessment and must not repeat
implementation details, version facts, evidence links, feature lists, or a
second explanation of the upstream claim.

For example, do not duplicate the reusable premise in a local fit record:

> The candidate requires `SYS_PTRACE`, uses seccomp, supports only Linux for
> its core path, and its latest release is `b390`; therefore it conflicts with
> this project's least-privilege policy.

Keep the detailed premise in the shared assessment and write the project
consequence with a bounded bridge:

> Given the pinned shared assessment's Security finding on elevated tracing
> privileges, this project's least-privilege policy blocks the candidate on
> managed hosts.

Audit every final local paragraph and list item:

- Classify it as a project fact, project consequence or decision, or a bounded
  bridge plus project consequence. Split mixed items before classifying them.
- Move an upstream-only item to the shared assessment. A statement whose only
  authority is an upstream page, source file, release, issue, or package
  registry is upstream-only.
- Use removal of the project name and local context as a secondary check: if a
  useful technology claim remains, it probably belongs in shared storage.
- Fail the handoff if any local item has no project-specific authority or
  consequence, or if either record repeats the other's complete claim.

The normalized repository URL is the only external upstream navigation link
that belongs locally; links to project-owned authority may also remain. Keep
official upstream evidence links and generic upstream review triggers in the
shared assessment. Before handoff, compare the final shared and local records,
remove duplicated upstream descriptions, and confirm that the local decision
is still understandable from its project facts, bounded bridges, and exact
shared pin. Do not report the evaluation complete until this audit passes.

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
generic risk analysis. Use only the bounded bridge allowed above when a
project consequence needs an upstream premise. The fit record's revision pin
remains unchanged until a new project evaluation explicitly adopts a newer
shared revision.

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
evaluation directory with `--require-contract`. For shared-storage evaluations,
also perform the sentence-level ownership audit above against the final shared
and local records. Structural validation cannot prove that their semantic
ownership is correct.
