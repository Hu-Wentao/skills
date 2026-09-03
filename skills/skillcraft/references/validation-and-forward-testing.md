# Validation and Forward Testing

## Required checks

Validate each changed skill directly:

```bash
node <skillcraft-root>/scripts/quick_validate.mjs <skill-directory>
```

The validator checks supported Pi frontmatter, names, description and body budgets, direct one-level reference links, missing paths, and project-profile boundaries.

When `<skill>/scripts/tests/run.py` exists, run:

```bash
uv run --script <skill>/scripts/tests/run.py
```

The runner’s PEP 723 block owns its test environment. Also run focused native tests for changed scripts and repository checks required by the source project.

## Forward testing

Forward-test complex or fragile behavior when static checks and unit tests do not provide sufficient evidence. Give a fresh agent the skill and a realistic task or raw artifact, not the intended answer, suspected defect, or patch rationale. Keep live, destructive, billable, or credentialed systems out of an evaluation unless separately authorized.

Use independent cases, remove test artifacts between runs, and revise the skill when success depends on leaked context. Forward testing supplements deterministic validation; it does not authorize publication or external mutation.

## Completion evidence

Record exact checked paths, commands, outcomes, context-budget statistics, and unresolved gaps. For shared publication, the canonical receipt is authoritative: `completed: true` requires validation, tests, enabled Git phases, every named update, and installation/lock verification to succeed.
