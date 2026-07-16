# Project Skill Design

## Decide Whether to Create a Skill

Create a project-level skill when one or more conditions hold:

- execution is repeated and requires the same rediscovery;
- ordering mistakes can cause data loss, security exposure, an invalid release, or costly recovery;
- project terminology or topology is difficult to reconstruct from code;
- a workflow crosses several tools or systems;
- completion and failure handling require project-specific judgment;
- deterministic scripts can safely encode fragile steps.

Do not create a skill for a one-time plan, ordinary coding convention, isolated command, unstable proposal, generic knowledge Codex already has, or content better expressed as a short repository instruction.

## Separate Universal and Project Knowledge

Keep universal governance in `project-governance`. Put these in project skills:

- exact commands and package-manager rules;
- environment names, topology, hosts, ports, and worktree conventions;
- domain terminology and project-specific safety boundaries;
- authoritative files that must be read;
- recovery behavior and completion criteria;
- scripts that implement deterministic operations.

Do not copy unrelated product baselines into a workflow skill. Link to project sources and state when they must be read.

## Set the Degree of Freedom

- Use high freedom for review heuristics and design choices with several valid outcomes.
- Use medium freedom for preferred workflows with project-specific branches.
- Use low freedom and tested scripts for releases, migrations, destructive operations, credential handling, and other narrow safety-critical paths.

Ensure the skill does not broaden user authorization. A workflow skill may explain how to deploy, but it must not deploy unless the user explicitly asks.

## Structure the Skill

Keep `SKILL.md` concise and procedural. Put trigger conditions in its frontmatter description. Move detailed schemas, troubleshooting, and domain knowledge into directly linked `references/`. Put deterministic repeated operations in `scripts/` and test them. Add only output resources to `assets/`.

Use `skillcraft` as the replacement for `skill-creator` to initialize, write metadata, separate reusable behavior from optional project configuration, validate, and forward-test a new or substantially revised skill.

## Review an Existing Skill

Check that it:

- triggers on concrete user intents;
- reads project instructions and dirty-worktree state before editing;
- identifies authoritative project sources;
- protects secrets and external mutations;
- distinguishes read-only diagnosis from authorized implementation;
- states failure and recovery behavior for risky operations;
- avoids stale duplicate facts;
- tests bundled scripts;
- reports breaking changes and compatibility provisions;
- remains narrow enough to load only when relevant.
