# Review

Trace the full path from URL to database and rendered rows. Report facts
separately from hypotheses.

Flag these failure patterns:

- whole-collection Repository/ORM reads in page, handler, action, or client
  query code;
- JavaScript `filter`, `sort`, or `slice` after a whole-collection read;
- limit proportional to requested page number;
- filters or authorization applied after pagination;
- pageable sort without a unique tie-breaker;
- row-by-row relation reads or serializers;
- unbounded select options, cached payloads, or RSC props;
- UI-only pagination with no server page contract;
- a shared or third-party table that introduces an implicit vertical scroller,
  especially a viewport-relative `height` or `max-height`;
- sticky headers or virtualization that change the scroll owner from the page
  or application shell to a nested container;
- scroll chaining from a table into the shell or root document, including a
  moving fixed sidebar/header or blank document overflow;
- a menu, popover, combobox, tooltip, or other floating descendant mounted
  inside an overflow-clipping ancestor when it must cross that boundary;
- an absolute in-cell popup or a larger `z-index` used as a substitute for a
  shared overlay primitive, portal, collision handling, or scroll positioning;
- consumer-specific CSS that compensates for a shared adapter's container
  defaults;
- absolute latency assertions that are likely to flake instead of query-shape
  tests.

For every confirmed issue, specify the smallest recurrence-ending change and
test the next unseen page, filter value, newly inserted row, or maximum-size
rendered page. Use browser geometry rather than jsdom assertions for scroll
ownership and overlay clipping. When a clipping or scroll contract changes,
inventory every floating-content class opened from the affected surface and
exercise triggers near container and viewport edges.

If the repository provides an overlay contract manifest, run
`scripts/audit-overlay-contract.mjs` to detect removed portal/focus evidence or
consumer CSS repairs, then use `scripts/overlay-geometry-probe.mjs` for the
real-browser geometry verdict. Treat the static audit as recurrence prevention,
not as proof of layout: viewport containment and clipping remain browser facts.
