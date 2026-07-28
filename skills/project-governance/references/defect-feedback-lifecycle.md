# Defect Feedback Lifecycle

Use this workflow to coordinate a user-reported defect from submission through
triage, optional reward, governed repair, immutable release identity, runtime
verification, and user-visible closure.

## Keep Collaboration State Non-Authoritative

Treat a collaboration tracker as a projection of reviewed evidence. It may
coordinate status, ownership, and stable references, but it must not replace:

- product requirements, current baselines, code, or tests;
- the governed defect record and repair commit;
- the authoritative reward or transfer system;
- immutable Git commits and release tags; or
- deployment health and acceptance evidence.

Use stable feedback identities and append-only transition events when the
tracker supports them. Keep one automation writer, require an observed
revision for transitions, and audit projection drift after writes. Never
rewrite history merely to make the current projection look consistent.

## Separate the State Gates

Use a project-defined state machine whose gates preserve these distinctions:

1. Submission and triage record the report without claiming it is a defect.
2. Confirmation requires evidence-backed review.
3. Reward approval is a human decision; reward completion requires an
   authoritative transfer reference.
4. Repair starts only after entering Defect Governance and assigning the
   project's required defect identity.
5. Release readiness requires a committed repair reference and verification
   evidence.
6. Release requires a human-authorized immutable release identity.
7. A successful deployment command remains unverified until the required
   runtime acceptance evidence passes.
8. Closure requires every project-selected repair, reward, release,
   deployment, and user communication obligation to be complete.

Do not let one successful gate advance another automatically. In particular,
AI confirmation does not approve a reward, passing tests do not authorize a
release, and a zero deployment exit code does not prove runtime acceptance.

## Preserve Authority and Recovery

- Keep reporter identity to the minimum stable product identifier needed for
  the workflow; do not use a collaboration sheet as a user directory.
- Store only allowlisted evidence references in transition events. Exclude
  credentials, authorization headers, prompts, bodies, captures, provider
  responses, and unrestricted error text.
- Make mutating commands check-only by default and require an explicit execute
  mode plus current authorization.
- After a partial reward, query the authoritative transfer by idempotency or
  reference before retrying.
- When repair begins, resolve the repository's `defect-diagnosis` instructions.
- When release or deployment is authorized, separately resolve
  `release-deployment`, freeze the exact commit and tag, and keep every retry
  fixed to that identity.
- If the collaboration projection drifts, stop downstream handoffs and rebuild
  it from reviewed append-only events or authoritative references. Do not
  mutate product facts to match the tracker.

Project profiles may define the tracker, identities, commands, state names,
reward mechanism, required evidence, and closure criteria. They cannot make a
tracker authoritative, remove human-only gates, broaden mutation authority,
weaken secret protection, or override Defect and Release Governance.
