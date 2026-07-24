# Implement

Implement one path end to end: URL/API input, authorization, data query,
projection, RSC or response, and pagination UI. Reuse the same list loader for
an RSC and its Route Handler when both expose the same collection.

The data query must apply authorization, filters, and stable ordering before
`LIMIT`/cursor predicate. Fetch page-size-plus-one when a cursor response needs
`nextCursor`; do not fetch page-number-times-page-size. Batch relation reads
using only ids from the current page.

Keep pagination/filter/sort state in URL allowlisted parameters for RSC
navigation. Include only response-affecting stable values in client query keys.
Invalidate or refresh after a mutation according to the application's cache
policy; do not optimistic-update append-only or financially sensitive facts.

Use the project's shared pagination/table components. Do not claim compliance
because a client table hides all but one local page.

Keep the shared table adapter as the owner of third-party table container
defaults. Explicitly normalize generated viewport-relative height, overflow,
sticky-header, and overscroll behavior there instead of adding page-specific
CSS. Preserve one vertical scroll owner unless the design explicitly calls for
a bounded internal grid viewport.

When scroll ownership can change, verify representative full and maximum page
sizes in a real browser. Assert that the intended container scrolls, the root
document does not gain accidental overflow, and fixed shell regions do not move
when the table reaches its boundary.
