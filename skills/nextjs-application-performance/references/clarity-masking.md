# Microsoft Clarity Masking

Use this reference when adding or reviewing Clarity session replay in an
authenticated application, especially a console that renders identity,
credentials, billing, requests, or user-authored content.

## Set the project policy

- Keep the Clarity project at **Balanced** unless a separate privacy review
  authorizes another mode. Balanced masks values Clarity classifies as
  sensitive, including numbers and email addresses.
- Treat the dashboard mode as external configuration. Record it in handoff
  notes; do not claim that repository code enforces it.
- Do not select Relaxed merely to make recordings readable. Inputs and
  dropdowns remain masked in every mode, but other rendered business data
  needs an explicit local boundary.

## Keep explicit masking local

- Search every rendered ancestor for `data-clarity-mask` and
  `data-clarity-unmask` before editing a leaf component:

  ```bash
  rg -n 'data-clarity-(mask|unmask)' apps packages
  ```

- Remove `data-clarity-mask` from `<html>`, `<body>`, the application shell,
  or another broad ancestor when the goal is a readable Balanced recording.
  Do not replace it with `data-clarity-mask="false"`.
- Do not compensate for a masked root with scattered
  `data-clarity-unmask="true"` descendants. Explicit element masking affects
  the node and its DOM children and overrides the Clarity website setting, so
  correct the broad ancestor first.
- Place `data-clarity-mask="true"` on the smallest stable value element or
  value-only wrapper. Avoid masking a whole card, table, dialog, or page when
  it also contains static headings, instructions, or action controls.

## Classify rendered content

Explicitly mask:

- user names, email addresses, account IDs, Team names, and membership facts;
- API key names, IDs, prefixes, scopes, and any one-time raw key;
- balances, prices, costs, budgets, ledger facts, payment references, and
  recipient details;
- request IDs, paths, models, errors, payloads, responses, captures, and test
  results;
- user-authored notes, messages, prompts, query text, uploaded-file metadata,
  and server errors that may echo submitted values.

Keep static navigation labels, product terminology, page and section headings,
button labels, empty-state guidance, and explanatory copy visible. Split mixed
sentences so only the dynamic value is masked.

Do not rely only on automatic input masking. Audit every place where a form
value is later rendered as confirmation, history, success feedback, or error
text.

## Audit detached rendering

- Treat masking inheritance as a DOM-tree rule. Inspect dialogs, tooltips,
  menus, toast regions, and other portals separately because their rendered
  nodes may sit outside the masked trigger or source component.
- Mask the sensitive value again at each detached rendering site. Keep the
  surrounding title, explanation, and action button outside the mask.
- Do not place sensitive content in CSS generated content, style sheets, or
  style tags; Clarity does not mask those locations.
- Avoid copying a sensitive value into an unmasked `title`, accessibility
  label, telemetry tag, or free-text analytics field. Prefer a stable static
  label while keeping the visible value in a masked child.

## Verify the boundary

- Add a root-layout contract proving `<body>` has no explicit mask and no
  `data-clarity-mask="false"` workaround.
- Add focused component coverage proving representative identity, Team, API
  key, billing, request-result, and user-authored values carry
  `data-clarity-mask="true"`.
- Assert that representative headings, navigation labels, instructions, and
  buttons do not inherit or carry a mask.
- Exercise sensitive success, error, confirmation, raw-response, and
  portal-rendered states rather than testing only the initial empty form.
- Run the configured focused tests, static audit, and typecheck. Use a real
  consented test recording when release validation explicitly authorizes
  external Clarity verification.

Masking changes affect only new recordings, cannot restore older recordings,
and can take up to one hour to appear. Use the
[Microsoft Clarity masking documentation](https://learn.microsoft.com/en-us/clarity/setup-and-installation/clarity-masking)
as the platform source of truth.
