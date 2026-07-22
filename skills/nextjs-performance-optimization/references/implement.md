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
