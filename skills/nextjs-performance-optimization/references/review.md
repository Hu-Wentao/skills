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
- absolute latency assertions that are likely to flake instead of query-shape
  tests.

For every confirmed issue, specify the smallest recurrence-ending change and
test the next unseen page, filter value, or newly inserted row.
