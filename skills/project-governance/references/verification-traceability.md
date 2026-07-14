# Verification Traceability

## Assign the Smallest Effective Owner

Map acceptance behavior to the verification layer that proves it with the least duplication:

| Behavior | Primary owner |
| --- | --- |
| Cross-service user-visible workflow | API, integration, or Docker E2E |
| UI-only interaction and rendering | Browser or UI test |
| Algorithm, validation, permission invariant | Focused unit or integration test |
| Deployment, secret rotation, recovery, runtime access | Manual or operational verification |
| Replaceable implementation detail | Code-local focused test, not product requirement coverage |

Use multiple layers only when they prove different risks. Do not reproduce every focused invariant in E2E.

## Build Traceability

For each in-scope requirement, record:

- requirement id;
- primary verification owner;
- supporting focused or UI evidence where needed;
- manual or operational responsibility when automation is inappropriate;
- known gaps or blocked evidence.

Keep exact commands, step-by-step scripts, timestamps, and run results in test or delivery artifacts rather than the stable requirement index.

## Interpret Evidence Carefully

A passing test proves only the behavior it asserts in the environment it exercised. Before changing a requirement to Active, also verify:

- all acceptance clauses, including negative constraints;
- linked baseline rules;
- relevant compatibility behavior;
- production or operational controls when required;
- absence of known partial implementations that change semantics.

An absent E2E does not always mean absent coverage. A focused test or operational check may be the correct owner.

## Review Coverage Quality

Report:

- requirements with no verification owner;
- Active requirements with incomplete evidence;
- Planned requirements incorrectly claimed as delivered;
- tests citing missing or deprecated ids;
- E2E scenarios overloaded with detailed invariants;
- UI behavior assigned only to API tests;
- operational guarantees with no named verification process;
- duplicate coverage that increases maintenance without proving a distinct risk.

Do not change product status merely to make the matrix look complete.
