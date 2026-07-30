---
name: burn-tokens-fast
description: Maintain and present a catalog of development activities that consume many tokens while usually providing limited value for routine development. Use when the user asks how to quickly consume, spend, burn, or waste tokens; requests a list of token-intensive low-yield development activities; or wants to add an activity to that catalog.
---

# Burn Tokens Fast

Record and present intentionally token-intensive development activities whose routine value is usually limited.

## Use the Catalog

- Return only the catalog when the user asks how to consume tokens quickly.
- Explain an entry's cost or limited value only when requested.
- Do not start an activity merely because the user asks to view the catalog. Execute it only when the user explicitly requests that specific activity and identifies its scope.
- Do not describe an activity as universally useless. Its value can be high when a concrete upgrade, vulnerability, compliance requirement, or delivery goal exists.

## Activity Catalog

### Update Project Upstream Dependencies

- **Activity:** Inspect direct and transitive upstream dependencies, review releases and changelogs, update versions and lockfiles, migrate affected APIs, and run compatibility tests.
- **Why it consumes tokens:** It requires reading many release notes, source changes, dependency relationships, compatibility constraints, code diffs, and test failures.
- **Why routine value is limited:** Without a concrete outdated dependency, required feature, vulnerability, or compatibility problem, broad updates create substantial review work with little immediate product benefit.

### Perform a Security Review

- **Activity:** Review architecture, dependencies, authentication, authorization, secrets, configuration, CI/CD, input handling, data flows, and threat boundaries; then document and validate findings.
- **Why it consumes tokens:** Its broad scope requires inspecting much of the repository and its configuration, tracing cross-file behavior, substantiating findings, and filtering false positives.
- **Why routine value is limited:** Without a defined threat model, review boundary, compliance need, or remediation target, the result is often a long report with limited immediate impact.

## Record Another Activity

When the user explicitly supplies another activity to record, add it to the catalog with exactly these fields:

- **Activity**
- **Why it consumes tokens**
- **Why routine value is limited**

Do not invent or add activities that the user did not request.
