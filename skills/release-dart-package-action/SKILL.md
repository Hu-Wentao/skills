---
name: release-dart-package-action
description: Release a Dart or Flutter package through SemVer, pubspec and changelog updates, dry-run validation, an immutable Git tag, and GitHub Actions. Use when the user asks to release, publish, or version a package, including workspace packages.
---

# Release Dart Package with GitHub Actions

Operate from the Git root containing the workspace `pubspec.yaml`. A release request authorizes the selected package workflow, but version choice and any ambiguous workflow selection still require confirmation.

## Preflight

1. Read root `pubspec.yaml`; expand `workspace:` entries and select one package when several exist.
2. Run `scripts/pre_check.py`. Stop for uncommitted changes or a branch behind upstream; report ahead commits that the release push will include.
3. Detect FVM and prefix Dart/Flutter commands with `fvm` when configured.
4. Run `scripts/inspect_workflows.py [package-name]`. Select a workflow using `dart-lang/setup-dart/.github/workflows/publish.yml` and record its tag pattern. If none exists, read [github_action_template.md](references/github_action_template.md).

## Prepare Version

Run:

```bash
python <skill-root>/scripts/prepare_release.py <current-version> \
  [--tag-match <pattern>] [--package-path <relative-package-path>]
```

Present the SemVer suggestion and changelog entry. Use the suggestion only when the user provides no alternative. Preserve the project’s changelog convention.

Update only the selected package `pubspec.yaml` and `CHANGELOG.md`, then commit exact paths with `chore(release): <version>`.

## Validate, Tag, and Push

From the selected package directory run:

```bash
dart pub publish --dry-run
# or: fvm dart pub publish --dry-run
```

Proceed only on success. Create one new tag matching the selected workflow pattern and pointing to the validated commit. Never move or reuse an existing release tag.

Push through:

```bash
python <skill-root>/scripts/push_tag_and_print_actions.py <tag>
```

The script pushes the current branch, then the exact tag, and prints the GitHub Actions URL when the remote is recognizable. A push or workflow failure is not a completed publication; preserve the commit and immutable tag for diagnosis.

## Report

Report package path, prior and new version, workflow and tag pattern, changed files, dry-run result, exact commit and tag, push result, Actions URL, and any remaining publication verification.
