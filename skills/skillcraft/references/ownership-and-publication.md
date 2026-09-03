# Ownership and Publication

## Classification order

Inspect logical and resolved paths before source detection. A project path remains protected when it is a symlink, and a global alias cannot hide project-private source.

1. A regular project `skills-lock.json` with a valid matching entry owns a lock-managed installation. Its source and safe relative `skillPath` identify the shared source.
2. A matching entry with invalid version, source, entry shape, or `skillPath` is ambiguous. Fail closed.
3. A project `.agents/skills/<name>` path without a matching project lock is project-private source, even when tracked or linked into a shared directory.
4. A tracked source at `skills/<name>` in an independent GitHub repository is shared direct source.
5. `.agents/skills-config/<name>` is project-owned configuration, not skill source.

A same-name global lock does not convert project-private source into shared source. Paths inside package-manager dependency trees are not authoritative source.

## Shared revision

Shared revision includes validation, tests, exact-path commit, push, named update, and verification. The canonical runner discovers global lock ownership and optionally one explicit consumer-project lock. It must update each explicit skill name independently and return a receipt.

If the source branch already contains reviewed ahead commits, require the exact fetched upstream head and exact local source head. This proves the bounded range without accepting arbitrary unpushed history.

First-time repository creation or first installation is separate. Obtain the source identity and installation scope before publishing; use `skills add` once, not as a substitute for post-publication update.

## Project-private revision

Project-private changes remain owned by their project. Unless the user explicitly requests local-only or no-push, revision includes validation, tests, commit, and remote push through that project’s own Git/worktree rules. Never use the shared publication runner, source registry, or Skills CLI update for this path. Migrating the skill to shared source requires separate user intent and a reviewed ownership change.

## Registry compatibility

The hidden backend may use `${CODEX_HOME:-$HOME/.codex}/skill-source-repositories.json` to map a lock source to an existing local source checkout. This machine-local registry is compatibility data and must not be committed to a project.
