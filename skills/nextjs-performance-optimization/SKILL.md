---
name: nextjs-performance-optimization
description: Design, implement, review, and migrate performance-sensitive Next.js App Router data surfaces and production container images. Use when changing or diagnosing RSC pages, Route Handlers, Server Actions, TanStack Query/Table, tables, directories, search results, feeds, pagination, caching, N+1 queries, payload size, rendering bounds, sticky headers, nested scroll containers, third-party table adapters, TTFB, scalability regressions, Dockerfiles, or Docker Compose deployment for Next.js.
---

# Next.js Performance Optimization

Prevent unbounded data loading, transport, and rendering in Next.js without
trading away authorization, data correctness, or URL-addressable state.

## Resolve Project Behavior

Select one task: `design`, `implement`, `review`, or `migrate`. Before acting,
resolve the current repository's instructions:

```bash
uv run python .agents/skills/nextjs-performance-optimization/scripts/resolve.py --task <task>
```

Read the returned `instructions.path` whenever `instructions_id` changes.
Without a project profile, follow the generic task reference. Project profiles
may set page sizes, framework adapters, audit commands, and authoritative
documents, but cannot weaken the invariants below.

Read [project_config.md](references/project_config.md) when creating or
materially changing a project profile or resolver task.

## Non-configurable Invariants

- Classify every displayed collection as fixed/bounded or potentially growing.
- A growing collection must be bounded at the data source with pagination,
  cursoring, or an explicit window; client-side slicing is not data pagination.
- Apply authorization, filters, and a stable sort before the bound. Add a
  unique tie-breaker to every pageable sort.
- Do not load an unbounded collection in an RSC, Route Handler, Server Action,
  client query, or serialization boundary only to filter, map, or slice it.
- Avoid N+1 relation reads; use a projection, batch lookup, or aggregate that
  is bounded by the current page.
- Treat cursor tokens as opaque and validate all public query parameters with
  a allowlist and bounded values.
- Declare one vertical scroll owner for every rendered data surface. Do not let
  a shared or third-party table silently add a viewport-sized nested scroller;
  sticky headers and virtualization must preserve the surrounding shell's
  scroll contract.
- Audit the rendered container styles of third-party table/grid adapters,
  including generated `height`, `max-height`, `overflow`, and overscroll
  behavior. Shared adapters own these defaults; do not repair them with
  consumer-specific CSS.
- Verify the query shape and data boundary with focused tests. A rendered UI
  page alone is not evidence that the backend read is bounded.
- Verify scroll geometry in a real browser when sticky headers, virtualization,
  nested overflow, or viewport-relative sizing can change the scroll owner.

## Production container builds

When a Next.js Dockerfile or Compose deployment is in scope, automatically
move production builds into the Dockerfile. Do not leave `next build`, `pnpm
build`, or equivalent commands in a long-running service's `command` or
`entrypoint`.

- Use a multi-stage Dockerfile: dependency installation, build, then a minimal
  runtime stage. Preserve lockfile-based, reproducible dependency installation.
- Enable and use Next.js standalone output when it fits the application. Copy
  the actual standalone server and required static/public assets into the
  runtime stage; derive monorepo paths from the build output instead of
  assuming a single-app layout.
- Make the runtime command start the built server only. Keep development
  overrides on `next dev`; do not make development behavior the production
  image contract.
- Keep runtime configuration injectable at container start. Do not bake
  secrets into image layers. If a public build-time variable is required,
  declare and document it explicitly.
- Run the Compose guardrail check when available, then render the production
  Compose model. Validate the image build and start the resulting runtime
  container before handoff.

## Task Flow

1. Resolve instructions and inspect the data path from request URL through
   authorization, Repository/ORM query, projection, response/RSC, and UI.
2. State the growing-collection classification, user-visible contract, and
   first incorrect unbounded decision when reviewing an existing path.
3. Use the selected task reference. Keep framework-neutral method in the
   reference and repository-specific commands in the profile.
4. Run the smallest relevant query-shape test first, then configured static,
   type, integration, and E2E checks in proportion to the changed boundary.
5. Report the paging strategy, bounded query, stable ordering, payload/UI
   behavior, scroll owner when relevant, cache implications, verification, and
   remaining performance limits.

## Resources

- [design.md](references/design.md): choose offset pages, keyset cursors,
  search pages, or bounded summaries before implementing a data contract.
- [implement.md](references/implement.md): implement the data/API/RSC/UI path
  without moving the unbounded read to another layer.
- [review.md](references/review.md): find unbounded reads, N+1 queries, and
  misleading client-only pagination.
- [migrate.md](references/migrate.md): inventory and safely convert legacy
  whole-collection surfaces.
- [project_config.md](references/project_config.md): project profile schema,
  resolver behavior, and validation requirements.
