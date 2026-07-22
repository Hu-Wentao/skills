---
name: nextjs-performance-optimization
description: Design, implement, review, and migrate performance-sensitive Next.js App Router data surfaces. Use when changing or diagnosing RSC pages, Route Handlers, Server Actions, TanStack Query/Table, tables, directories, search results, feeds, pagination, caching, N+1 queries, payload size, rendering bounds, TTFB, or scalability regressions.
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
- Verify the query shape and data boundary with focused tests. A rendered UI
  page alone is not evidence that the backend read is bounded.

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
   behavior, cache implications, verification, and remaining performance
   limits.

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
