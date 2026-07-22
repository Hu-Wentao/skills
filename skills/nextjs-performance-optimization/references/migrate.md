# Migrate

Inventory every growing collection by route, API, Repository method, UI
surface, current query shape, ordering, consumers, and data sensitivity.
Prioritize histories, audit/event streams, user directories, and APIs consumed
by clients before bounded configuration collections.

Add the server data contract and focused tests before changing the UI. Preserve
existing response fields during a documented compatibility window when clients
consume the endpoint. Do not silently truncate a legacy full response.

After each vertical slice, enable the project audit for that surface. Promote a
warning to an error only after all in-scope consumers migrate. Remove the
legacy whole-collection method from UI-accessible code paths once migration is
complete.
