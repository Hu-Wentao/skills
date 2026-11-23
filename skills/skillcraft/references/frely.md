# Frely

Read only when the skill is installed from, or will be published to, Frely (`frely` CLI, `frely item …`). Skip it for every other delivery path.

## Contents

- Detect a Frely install
- Publish to Frely
- Calling Frely from a skill
- Project configuration with cloud parts
- Never publish

## Detect a Frely install

Frely installs skills to `<project>/.agents/skills/<owner>-<name>` (or a user-level agent directory) without writing a lock file or any marker, so the folder looks like project-private source. Before revising anything under `.agents/skills/`, run:

```bash
frely item status <folder> --json
```

If it reports a Frely-managed item, the folder is a purchased or marketplace copy: do not edit, commit, or push it. Customize behavior through `.agents/skills-config/<name>/`. To change the skill itself, revise its source (the author's repository or folder) and publish a new version, then run `frely item update <folder>`. A modified managed copy is refused by `frely item update` (`managed_item_modified`), and paid files inside it must never be committed to a project repository.

If the `frely` command is missing or the status call fails, treat the folder as ambiguous and stop instead of falling back to project-private.

## Publish to Frely

Frely is where these skills are uploaded; nothing here goes through `sync-skill-repo` or a Git remote. A revision request authorizes publishing the new version of a slug that is already published (unless the user says local-only); the first publication of a new slug is outward-facing and needs the user's explicit ask.

```bash
frely item publish <source-folder> [--slug <slug>] [--premium <path>]... [--json]
```

- The command packages only the skill folder and excludes dotfiles, `.agents/.cache`, and `skills-config`. Publishing the same slug creates a new version.
- `--premium <path>` marks files that buyers receive only after purchase; leave everything else free. Free-tier package limits apply (64 files, 64 KB per file, 128 KB total).
- The result prints the version and the install command `frely item install <owner>/<slug>`. Afterwards run `frely item update <folder>` on any installed copy of your own.
- Run the skill's validator and tests first; do not ship a failing skill.
- Every new slug takes one of the author's Skill slots (Free: 100 in all, any level; 1 may be shown on the profile page). A revision of an existing slug takes none and creates a new version. If publish answers `creator_skill_limit_reached`, tell the user to delete a skill they no longer need or upgrade; never delete anything on their behalf.

## Calling Frely from a skill

Use the CLI rather than reimplementing it: `frely item call <owner>/<slug>` for cloud-hosted parts, `frely api call <method>` for platform methods, `frely put` / `frely get` for files, `frely result` for long-running results. Run `frely --help` for the current surface.

## Project configuration with cloud parts

A cloud part (hosted or sandboxed) cannot read the project workspace. Resolve locally first (`node <skill-root>/scripts/resolve.mjs --task <task> --emit instructions`) and pass the resolved text in `frely item call --input`. Do not grant the cloud part read access to the whole workspace for this.

## Never publish

`skills-config`, `.agents/.cache`, secrets, `node_modules`, build output, or the project's own files.
