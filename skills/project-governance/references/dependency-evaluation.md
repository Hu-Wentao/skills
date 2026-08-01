# External Dependency and Technology Evaluation

## Preserve Authority

Evaluate current or proposed third-party libraries, frameworks, services, and
runtimes without making adoption implicit.

Treat a request to evaluate a technology for an active writable project as
authorization to create or revise only its smallest governed evaluation record,
unless the user explicitly requests a chat-only/read-only result or forbids
local writes. Complete that record before the final response. Upstream
inspection remains read-only, and this default does not authorize changes to a
Plan, Baseline, manifest, lockfile, code, infrastructure, release, or
deployment. If no active writable project exists, return the evaluation without
inventing a documentation destination.

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

## Write the Smallest Queryable Record

Follow an existing repository convention. Otherwise create one governed record
under `docs/evaluations/<slug>.md` with a stable `TECH-EVAL-<SLUG>` identity.
Expose only these five lifecycle and discovery fields through its persistent
mdq contract:

- `status`: `researching`, `assessed`, `trial`, `adopted`, `rejected`,
  `stale`, or `superseded`;
- `kind`: a concise technology class such as `library`, `framework`,
  `service`, `runtime`, or a project-established specialization;
- `scope`: the affected project, module, or product surface;
- `disposition`: `undecided`, `adopt`, `trial`, `watch`, or `reject`;
- `evaluated`: the evidence date in `YYYY-MM-DD` form.

Keep license, maturity, upstream version or commit, source URLs, strengths,
risks, and detailed compatibility findings in bounded prose. Promote one to a
declared field only after a repeated cross-document query requires it. Do not
create a sidecar index for a small collection; use mdq collection scanning.

Include a concise conclusion, scope and authority boundary, project fit,
material gaps or risks, recommendation, official evidence, and review
triggers. Use one record for the current assessment instead of accumulating
dated snapshots. Mark it `stale` or revise it when upstream maturity, license,
security posture, compatibility, or the relevant project boundary changes.

If the disposition becomes `adopt` or `trial`, obtain separate implementation
authorization and update the applicable Plan, Baseline, manifest, lockfile, and
verification ownership. The evaluation record remains evidence, not the
adoption authority.

## Verify Queryability

Use `queryable-markdown` to validate and diagnose the document, query its exact
ID and an absent ID, query representative declared fields, and scan the
evaluation directory with `--require-contract`.
