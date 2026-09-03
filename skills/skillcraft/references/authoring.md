# Skill Authoring

## Frontmatter

Pi accepts only these top-level `SKILL.md` fields:

- `name` and `description`;
- `license`, `compatibility`, `metadata`, and `allowed-tools`;
- `disable-model-invocation` for an explicitly callable skill hidden from automatic model discovery.

Reject `user-invocable` and unknown fields. Keep names lowercase hyphen-case and equal to the folder name. Put all trigger conditions in the description; the body loads only after triggering.

## Default locations

Keep an established tracked source where it is. For a project-private skill, default to `<project-root>/.agents/skills/<name>`. For a user installation, default to `~/.agents/skills/<name>`. In a dedicated shared-skill source repository, use its established source layout such as `skills/<name>`. Do not default to `~/.codex/skills`.

Project specialization belongs in `<project-root>/.agents/skills-config/<name>` and generated resolver output in ignored `<project-root>/.agents/.cache/<name>`.

## Structure

A skill requires `SKILL.md` and may contain:

- `agents/openai.yaml` for interface metadata;
- `scripts/` for deterministic repeated actions;
- `references/` for details loaded only when needed;
- `assets/` for output resources.

Do not add changelogs, installation guides, or process notes inside a skill. Keep one authority for each rule.

## Progressive disclosure

Descriptions should identify concrete triggering intent without embedding workflow. Keep `SKILL.md` procedural and within its declared context budget. Move schemas, command catalogs, examples, troubleshooting, and product matrices to one-level references linked directly from `SKILL.md`. References do not count against the model-visible body budget, but every link must exist.

Use `metadata.context-budget: router` only when the body must route several distinct workflows. Use `disable-model-invocation: true` for a compatibility backend that should not consume automatic model context.

## Initialization

Run:

```bash
python <skillcraft-root>/scripts/init_skill.py <name> --path <source-or-install-root> \
  [--resources scripts,references,assets] [--project-config] \
  --interface display_name='...' \
  --interface short_description='...' \
  --interface default_prompt='Use $<name> to ...'
```

Delete placeholders, keep only needed resources, and test every added script.
