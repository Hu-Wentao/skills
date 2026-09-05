# Contracted Markdown Editing Workflow

Use this workflow only for a valid persistent `mdq` contract or while completing
an explicitly authorized creation, conversion, or repair. The contract supplies
structure; the request supplies write authority.

## 1. Bound the Write

Classify each requested mutation independently:

- authored record content;
- record identity or boundary;
- contract profile or stable marker;
- declared sidecar index.

Authority for one class does not authorize another. An ordinary document without
a valid contract remains read-only under this skill unless conversion is
authorized. Never repair a contract merely to complete an unrelated content edit.

Before editing, require:

- a valid inline or resolved shared contract, or accepted drift that does not affect the target;
- one exact, case-sensitive structured target for update, rename, or delete;
- no exact match for a proposed new identity;
- a source-located bounded range;
- supplied business values rather than inferred content.

## 2. Preflight the Target

Use compact retrieval first:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" get <document.md> --id <exact-id>
```

If compact output reports ambiguity, warnings, or an error, rerun with
`--output json` and stop unless the evidence still proves a unique safe target.
Use `inspect` before conversion or a boundary/profile change.

For add or rename, also retrieve the proposed ID and require `not_found`. Search
the document for old and new identities before a rename or delete so remaining
references are visible. External reference maintenance is outside scope unless
the request includes it.

## 3. Apply One Source Patch

Patch source bytes directly. Never use a generic Markdown serializer.

| Mutation | Required boundary |
| --- | --- |
| Update prose or a field | Change only the smallest authored span; preserve labels, whitespace, and unrelated fields. |
| Add a record | Follow an explicit ordering rule or neighboring structure; copy layout, never business values. |
| Rename identity | Change the identity source and only authorized, semantically unambiguous references. |
| Delete a record | Delete exactly the record and its associated marker; preserve neighboring blank-line style. |
| Change contract | Patch only the top-level `mdq` control block unless separately authorized. A shared profile reference is migrated by selecting a new published version; never patch the shared asset through a consumer document. |

A `regex` field is an extractor, not a write address. Patch it only when the
containing record and exact authored span are independently clear. Never invent
a missing field style or normalize neighboring records.

## 4. Prefer the Built-In Scalar Transaction

For an existing untransformed `source: label` scalar, use `set`. Preview first:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" set <path>... \
  --where status=draft \
  --field reviewed \
  --value true
```

Repeat the exact command with `--apply` only after reviewing selected paths,
keys, old/new values, and diagnostics. The command prevalidates the complete
batch, refuses ambiguous or unsupported targets, checks source hashes, applies
same-directory atomic replacements, verifies every result, rolls back on later
failure when possible, and rebuilds declared indexes.

## 5. Run One Scripted Verification Tier

After a manual source patch, choose the smallest sufficient tier:

```bash
# Existing prose or field value.
uv run "$SKILL_DIR/scripts/mdq.py" check <document.md> \
  --tier content --id <id> --select <changed-field>

# Identity, record, heading, marker, label, ordering, or boundary.
uv run "$SKILL_DIR/scripts/mdq.py" check <document.md> \
  --tier structure --id <expected-id> --absent-id <old-or-absent-id>

# Contract, conversion, query, or index policy.
uv run "$SKILL_DIR/scripts/mdq.py" check <document.md> --tier contract
```

`content` runs validation and exact queries. `structure` also diagnoses all
records and samples first/middle/last identities. `contract` additionally
verifies declared v2 query intents. Repeat selectors for every affected identity.

Escalate when ranges move unexpectedly, new warnings appear, or governance
requires stronger evidence. If the document declares an index and the manual
edit succeeded, rebuild it with `index`, then rerun the affected exact check.
Inspect the final diff regardless of command success.

## 6. Handoff

Report the mutation class, affected and absent IDs, verification tier, compact
diagnostic codes, contract/marker/index changes, unresolved references, rollback
state for batch work, whether unrelated authored bytes changed, and breaking
impact.
