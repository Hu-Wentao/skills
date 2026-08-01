# Domain Knowledge Governance

Use this protocol to preserve project-specific terminology without turning architecture,
requirements, plans, and implementation evidence into competing sources of truth.

## Authority Boundary

Domain knowledge owns:

- preferred terms and stable concept identifiers;
- definitions, aliases, and anti-definitions;
- bounded-context ownership and semantic relationships;
- citations to the documents that own behavioral or delivery facts.

It does not own:

- product scope or acceptance criteria, which belong in requirements;
- currently effective behavior, which belongs in governed baseline documents;
- future behavior, which belongs in plans;
- implementation truth, which belongs in code and tests.

Use `semantic_status` only for the lifecycle of the meaning: `proposed`, `accepted`, or
`deprecated`. Do not encode implementation status in concept records.

## One Protocol, Three Profiles

Projects use one stable identifier and query protocol. A project can add structure without
renaming existing concept identifiers.

| Profile | Use when | Required fields | Additional checks |
| --- | --- | --- | --- |
| `lite` | A small project needs a shared vocabulary in one file. | `title`, `semantic_status`, `definition`, `sources` | Unique IDs and preferred terms. |
| `catalog` | A product has several feature areas or recurring terminology disputes. | `lite` plus `kind`, `scope_note` | Alias uniqueness and valid relationship targets. |
| `bounded` | Multiple bounded contexts, teams, integrations, or white-label surfaces use overlapping language. | `catalog` plus `context` | Context-scoped term uniqueness and cross-context relationship validation. |

`bounded` combines DDD ubiquitous language and bounded contexts with the arc42 glossary and
cross-cutting-concept separation. Its fields are a deliberately small SKOS-inspired subset:
preferred label (`title`), alternative labels (`aliases`), definition, broader/narrower/related
relationships, and semantic status. MDQ supplies deterministic discovery and validation; it is
not the semantic model itself.

## Default Location

The managed task uses `docs/domain-concepts.md` by default. A project may point `--docs` at a
different Markdown file or a directory containing concept-record Markdown files. Keep index or
narrative files outside a directory scanned as concept records unless they declare the same MDQ
contract.

Use a single file for `lite`. A catalog may remain in one file until ownership or review becomes
awkward. Split a `bounded` catalog by bounded context, while keeping identifiers globally stable.

## Stable Record Shape

Each record heading contains a stable ID and preferred term:

```markdown
## CONCEPT-TEAM — Team
```

IDs must match `CONCEPT-[A-Z0-9-]+`. Never recycle an ID for a different meaning. Deprecate and
link a replacement instead.

The following queryable-Markdown contract supports all three profiles. Fields not required by the
selected profile may be empty or omitted from an individual record, but keep the field declarations
stable so queries remain portable.

```yaml
---
mdq:
  version: 1
  dialect: gfm
  records:
    boundary:
      source: heading
      levels: [1, 2]
      pattern: '^(?P<id>CONCEPT-[A-Z0-9-]+)(?:[ ：—-]+(?P<title>.+))$'
    key:
      source: heading
      pattern: '^(?P<id>CONCEPT-[A-Z0-9-]+)(?:[ ：—-]+(?P<title>.+))$'
      group: id
  fields:
    title:
      source: heading
      pattern: '^(?P<id>CONCEPT-[A-Z0-9-]+)(?:[ ：—-]+(?P<title>.+))$'
      group: title
    semantic_status:
      source: label
      labels: [Semantic Status, 语义状态]
    kind:
      source: label
      labels: [Kind, 类型]
    context:
      source: label
      labels: [Context, 限界上下文]
    aliases:
      source: label
      labels: [Aliases, 别名]
    scope_note:
      source: section
      headings: [Scope Note, 范围说明]
    definition:
      source: section
      headings: [Definition, 定义]
    anti_definition:
      source: section
      headings: [Not This, 非此概念]
    broader:
      source: label
      labels: [Broader, 上位概念]
    narrower:
      source: label
      labels: [Narrower, 下位概念]
    related:
      source: label
      labels: [Related, 相关概念]
    sources:
      source: section
      headings: [Sources, 权威来源]
---
```

Example:

```markdown
## CONCEPT-PARTNER — Partner

Semantic Status: accepted
Kind: role
Context: tenancy
Aliases: 合作商, reseller
Related: CONCEPT-TEAM, CONCEPT-CUSTOM-DOMAIN

### Definition

A registered user whose purchased entitlement permits ownership of a team and use of a
verified custom domain for that team.

### Scope Note

Partner describes the commercial and tenant-owner role. It does not imply that partner members
know or interact with the platform brand.

### Not This

It is not a generic affiliate, upstream model provider, or ordinary team administrator.

### Sources

- [Current team behavior](baseline/team-membership.md)
- [Custom-domain requirement](requirements.md#custom-domain)
```

## Workflow

Run domain operations through the project-governance dispatcher:

```text
project-governance domain inspect
project-governance domain get --id CONCEPT-PARTNER
project-governance domain search --text custom-domain
project-governance domain plan --mode bounded
project-governance domain maintain --mode bounded
project-governance domain verify --mode bounded
```

`inspect`, `get`, `search`, `plan`, and `verify` are read-only. `maintain` is a governed
repository-write preflight: it resolves the scope and source snapshot but deliberately does not
edit prose. The caller applies the approved semantic change, then runs `verify`.

If the default concept location does not exist, managed operations return `not_configured` rather
than breaking governance for an existing project. Choose a profile with stakeholder judgment, use
`plan` to inspect its requirements, then create the contracted document before treating domain
verification as a required project gate.

## Profile Changes

Upgrade incrementally:

1. Keep every existing concept ID.
2. Add the fields required by the next profile.
3. Split files only after the records validate in their current location.
4. Add bounded contexts and explicit relationships.
5. Update project governance configuration only after the new catalog verifies.

Downgrading removes validation guarantees, not meaning. Do not delete fields or relationships just
to satisfy a simpler profile.
