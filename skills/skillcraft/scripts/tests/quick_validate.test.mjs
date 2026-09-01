import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { validateSkill } from "../quick_validate.mjs";

function writeSkill(resolver) {
  const root = mkdtempSync(join(tmpdir(), "skillcraft-validate-"));
  const skill = join(root, "example-skill");
  mkdirSync(join(skill, "references"), { recursive: true });
  mkdirSync(join(skill, "scripts"));
  writeFileSync(join(skill, "SKILL.md"), "---\nname: example-skill\ndescription: Exercise validation.\n---\n\n# Example\n");
  writeFileSync(join(skill, "references", "project_config.md"), "# Project Configuration\n");
  writeFileSync(join(skill, "scripts", "resolve.py"), resolver);
  return { root, skill };
}

test("uses a dependency-free Node validator", () => {
  const source = readFileSync(new URL("../quick_validate.mjs", import.meta.url), "utf8");
  assert.match(source, /^#!\/usr\/bin\/env node/);
  assert.doesNotMatch(source, /PyYAML|from ["']yaml|import yaml/);
});

test("rejects a literal project profile branch", () => {
  const fixture = writeSkill("profile = 'generic'\nif profile == 'customer-a':\n    print('customer behavior')\n");
  try {
    const [valid, message] = validateSkill(fixture.skill);
    assert.equal(valid, false);
    assert.match(message, /branches on a concrete project profile/);
    assert.match(message, /skills-config\/example-skill/);
  } finally { rmSync(fixture.root, { recursive: true, force: true }); }
});

test("accepts profile as an opaque manifest value", () => {
  const fixture = writeSkill("profile = load_config().get('profile', 'generic')\nprint(f'profile: {profile}')\n");
  try {
    const [valid, message] = validateSkill(fixture.skill);
    assert.equal(valid, true, message);
  } finally { rmSync(fixture.root, { recursive: true, force: true }); }
});
