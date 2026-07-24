# Design

## Classify the Collection

Call a collection fixed only when product constraints keep it small and the
bound is independently enforced. A permissions matrix, a fixed dashboard
summary, or a controlled enum may be fixed. A record table, directory, feed,
search result, event history, selectable account list, or user-generated
collection is growing unless proven otherwise.

## Select the Contract

Use offset pages when users need stable numbered pages and an affordable total
count. Use a keyset cursor for append-only histories, high-write data, or
remote/cold storage. Use a bounded search page for dynamic candidates. Use
infinite loading only when the data source remains cursor-bounded.

Define request parameters, defaults, maxima, filters, allowed sorts, stable
tie-breaker, response metadata, empty state, and behavior for deleted or
newly inserted rows. Do not expose a cursor's internal SQL representation as a
publicly mutable contract.

## Select the Scroll Contract

Name the single vertical scroll owner for the rendered surface. Prefer the
application shell or page scroller for ordinary paged tables. Allow an internal
vertical table scroller only when the product explicitly needs a bounded grid
viewport, and define its height source, sticky-header behavior, overscroll
boundary, keyboard access, and narrow-viewport behavior.

Treat third-party table defaults as implementation input, not product policy.
The shared adapter must normalize any implicit viewport-relative height or
overflow behavior for all consumers.

## Design Review Record

Before implementation, name the data owner, authorization boundary, paging
mode, bound, sort, relation projection, UI navigation model, cache key fields,
vertical scroll owner, and verification owner. Escalate a product decision when
pagination or scrolling would change visibility, ordering semantics, URL
compatibility, keyboard reachability, or exports.
