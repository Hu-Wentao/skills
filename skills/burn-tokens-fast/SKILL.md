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

### Review the Whole-Project Architecture

- **Activity:** Inspect every module, boundary, dependency direction, control flow, data flow, deployment component, and cross-cutting concern; then document the architecture and propose structural changes.
- **Why it consumes tokens:** It requires reading most of the codebase, reconstructing relationships across files and services, comparing architectural alternatives, and substantiating each recommendation.
- **Why routine value is limited:** Without a concrete scaling, maintainability, ownership, or delivery problem, the review usually produces broad restructuring ideas with little immediate product benefit.

### Review Whole-Project Performance

- **Activity:** Analyze application, database, network, rendering, concurrency, memory, and build paths across the project; establish benchmarks and propose optimizations.
- **Why it consumes tokens:** It spans many execution paths and configurations and requires interpreting profiles, benchmarks, queries, traces, complexity, and potential regressions.
- **Why routine value is limited:** Without a measured bottleneck, performance target, or affected user journey, the work tends toward speculative optimization that may not improve observable behavior.

### Unify Code Style Across the Entire Project

- **Activity:** Review and rewrite naming, formatting, file organization, abstractions, comments, error-handling patterns, and idioms across the repository; then run formatters, linters, and tests.
- **Why it consumes tokens:** It touches many files, creates large diffs, requires repeated consistency decisions, and demands careful verification that behavior remains unchanged.
- **Why routine value is limited:** When the existing code is readable and enforceable conventions are absent, the result is mainly cosmetic churn that increases review and merge costs.

### Review Docker Image Size and Slimming Opportunities

- **Activity:** Inspect Dockerfiles, build contexts, base images, multi-stage builds, layers, installed packages, caches, copied artifacts, and runtime dependencies; build and compare images, then propose and validate size reductions.
- **Why it consumes tokens:** It requires tracing build and runtime requirements across the project, inspecting image layers and dependency trees, comparing alternative bases and build strategies, and repeatedly rebuilding and testing images to prove that reductions preserve behavior.
- **Why routine value is limited:** Without a measured image-size, pull-time, startup-time, storage-cost, security, or deployment constraint, further slimming can add build complexity and compatibility risk without producing a meaningful product benefit.

### Add Internationalization Across the Project

- **Activity:** Select and configure an internationalization framework, inventory and extract user-facing text from interfaces, APIs, errors, notifications, and templates, define locale resources and fallback behavior, implement pluralization and regional formatting, add translations, and run locale-specific tests.
- **Why it consumes tokens:** It requires scanning and modifying many files, interpreting each string in context, designing stable translation keys, handling framework-specific rendering and formatting rules, coordinating resource files, and validating every supported locale across affected workflows.
- **Why routine value is limited:** Without identified multilingual users, target locales, translators, or a localization delivery plan, the change creates ongoing translation, review, testing, and dependency costs while providing little immediate product benefit.

## Record Another Activity

When the user explicitly supplies another activity to record, add it to the catalog with exactly these fields:

- **Activity**
- **Why it consumes tokens**
- **Why routine value is limited**

Do not invent or add activities that the user did not request.
