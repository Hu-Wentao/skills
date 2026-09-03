import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { validateSkill } from "../quick_validate.mjs";

function fixture(frontmatter = "name: example-skill\ndescription: Exercise validation.", body = "# Example\n") {
  const root = mkdtempSync(join(tmpdir(), "skillcraft-validate-"));
  const skill = join(root, "example-skill");
  mkdirSync(join(skill, "references"), { recursive: true });
  mkdirSync(join(skill, "scripts"));
  writeFileSync(join(skill, "SKILL.md"), `---\n${frontmatter}\n---\n\n${body}`);
  return { root, skill };
}

function configuredFixture(resolver) {
  const value = fixture();
  writeFileSync(join(value.skill, "references", "project_config.md"), "# Project Configuration\n");
  writeFileSync(join(value.skill, "scripts", "resolve.py"), resolver);
  return value;
}

function withFixture(value, callback) {
  try { callback(value); } finally { rmSync(value.root, { recursive: true, force: true }); }
}

test("uses a dependency-free Node validator", () => {
  const source = readFileSync(new URL("../quick_validate.mjs", import.meta.url), "utf8");
  assert.match(source, /^#!\/usr\/bin\/env node/);
  assert.doesNotMatch(source, /PyYAML|from ["']yaml|import yaml/);
});

test("project-private revisions publish through the owning project", () => {
  const skill = readFileSync(new URL("../../SKILL.md", import.meta.url), "utf8");
  const ownership = readFileSync(new URL("../../references/ownership-and-publication.md", import.meta.url), "utf8");
  for (const text of [skill, ownership]) {
    assert.match(text, /local-only or no-push/);
    assert.match(text, /validation, tests, commit, and remote push/);
  }
  assert.match(skill, /Do not invoke the shared publication runner/);
  assert.match(ownership, /Never use the shared publication runner/);
});

test("accepts the supported Pi frontmatter fields", () => withFixture(fixture(
  "name: example-skill\ndescription: Exercise validation.\nlicense: MIT\ncompatibility: Pi\nallowed-tools: [read, bash]\ndisable-model-invocation: false\nmetadata:\n  context-budget: router"
), ({ skill }) => {
  const [valid, message] = validateSkill(skill);
  assert.equal(valid, true, message);
}));

test("rejects user-invocable and unknown fields", () => withFixture(fixture(
  "name: example-skill\ndescription: Exercise validation.\nuser-invocable: false"
), ({ skill }) => {
  const [valid, message] = validateSkill(skill);
  assert.equal(valid, false);
  assert.match(message, /Unexpected key.*user-invocable/);
}));

test("enforces normal, router, and hidden context budgets", () => {
  for (const [label, frontmatter, lines, expected] of [
    ["normal", "name: example-skill\ndescription: Exercise validation.", 81, false],
    ["router", "name: example-skill\ndescription: Exercise validation.\nmetadata: {context-budget: router}", 81, true],
    ["hidden", "name: example-skill\ndescription: Exercise validation.\ndisable-model-invocation: true", 61, false],
  ]) withFixture(fixture(frontmatter, Array.from({ length: lines }, (_, index) => `line ${index}`).join("\n")), ({ skill }) => {
    const [valid, message] = validateSkill(skill);
    assert.equal(valid, expected, `${label}: ${message}`);
  });
});

test("rejects missing and nested reference links", () => {
  for (const target of ["references/missing.md", "references/nested/detail.md"]) {
    withFixture(fixture(undefined, `# Example\n\n[detail](${target})\n`), ({ skill }) => {
      const [valid, message] = validateSkill(skill);
      assert.equal(valid, false);
      assert.match(message, /Reference links|does not exist/);
    });
  }
});

test("rejects a literal project profile branch", () => withFixture(configuredFixture(
  "profile = 'generic'\nif profile == 'customer-a':\n    print('customer behavior')\n"
), ({ skill }) => {
  const [valid, message] = validateSkill(skill);
  assert.equal(valid, false);
  assert.match(message, /branches on a concrete project profile/);
  assert.match(message, /skills-config\/example-skill/);
}));

test("accepts profile as an opaque manifest value", () => withFixture(configuredFixture(
  "profile = load_config().get('profile', 'generic')\nprint(f'profile: {profile}')\n"
), ({ skill }) => {
  const [valid, message] = validateSkill(skill);
  assert.equal(valid, true, message);
}));
