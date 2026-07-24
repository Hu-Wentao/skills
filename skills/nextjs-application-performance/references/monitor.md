# Monitor User-Perceived Performance

Measure a business action from explicit user intent until its result is visible
and usable. Use this contract for client navigation, full-document redirects,
mutations, and other user-visible workflows.

## Define the Action Contract

Give every action a stable, low-cardinality name from an allowlist. Define:

- start: the click, submit, or keyboard activation that expresses user intent;
- completion: the specific business result rendered and ready for its primary
  interaction;
- terminal results: `success`, `failed`, `cancelled`, and `timeout`;
- timeout: a bounded lifetime after which the measurement is closed;
- owner: the component or workflow responsible for closing every started
  measurement.

Do not end a successful action at URL change, component mount, request
completion, generic loading-state removal, or `networkidle`. Those signals can
precede the business result the user is waiting for.

For a list, complete when the first bounded page or the real empty state is
visible and its primary controls are usable. For a detail page, complete when
the primary record content and intended actions are usable. For a mutation,
complete when the server-confirmed result is reflected in the UI.

## Carry Timing Across Navigation

Keep an in-memory measurement for same-document client navigation. When an
action can cross a reload or redirect, persist only a minimal envelope in
`sessionStorage`: action name, absolute start timestamp, release, and timeout.
Use an absolute high-resolution timestamp such as
`performance.timeOrigin + performance.now()` because `performance.now()` alone
resets for a new document.

Validate the restored action against the allowlist and timeout. Remove it after
any terminal result. Starting a mutually exclusive replacement action must
cancel or supersede the earlier measurement so stale actions cannot be reported
as later navigations.

## Report a Minimal Event

Report only:

- stable action name;
- non-negative bounded duration;
- terminal result;
- application or service name when more than one app shares the collector;
- release or commit identifier.

Never derive an action name or metric label from a record ID, account, user,
full URL, query string, free text, request body, credential, or authorization
value. Treat route templates and other optional dimensions as allowlisted,
low-cardinality metadata.

Make reporting best-effort and non-blocking. A monitoring failure must not fail
the business action. Deduplicate terminal reports and sample only through an
explicit stable policy; do not selectively discard slow or failed actions.

## Verify the Measurement

Use focused browser coverage to prove:

- the action starts on the actual user activation;
- success closes only after the declared business-ready condition;
- real empty states count as successful completion where appropriate;
- failures, cancellation, supersession, and timeout close exactly once;
- reloads and redirects preserve valid timing without reviving stale actions;
- dynamic or sensitive values cannot enter action names or reported metadata.

Review percentile distributions and failure rates by action and release.
Use deeper server timing, tracing, or profiling only after this measurement
identifies a slow workflow; the business-action duration remains the
user-perceived outcome metric.
