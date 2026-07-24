# Migrate

Inventory every growing collection by route, API, Repository method, UI
surface, current query shape, ordering, consumers, data sensitivity, table
adapter, and vertical scroll owner.
Prioritize histories, audit/event streams, user directories, and APIs consumed
by clients before bounded configuration collections.

Add the server data contract and focused tests before changing the UI. Preserve
existing response fields during a documented compatibility window when clients
consume the endpoint. Do not silently truncate a legacy full response.

After each vertical slice, enable the project audit for that surface. Promote a
warning to an error only after all in-scope consumers migrate. Remove the
legacy whole-collection method from UI-accessible code paths once migration is
complete.

When replacing a table implementation, compare the rendered container styles
before and after migration. Audit every consumer of sticky headers,
virtualization, or internal overflow together; do not accept a page-local patch
that leaves the same shared adapter default active for the next table.
