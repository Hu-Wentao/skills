#!/usr/bin/env node

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { parseFrontmatter, FrontmatterError } from "./lib/frontmatter.mjs";

export const MAX_SKILL_NAME_LENGTH = 64;

export function findLiteralProfileBranch(skillPath) {
  const scripts = join(skillPath, "scripts");
  if (!isDirectory(scripts)) return null;
  for (const path of walkFiles(scripts).filter((item) => item.endsWith(".py")).sort()) {
    if (path.split("/").includes("tests")) continue;
    let source;
    try { source = readFileSync(path, "utf8"); } catch { continue; }
    const comparison = findProfileComparison(source);
    if (comparison) return { path, line: comparison.line };
    const matchCase = findProfileMatchCase(source);
    if (matchCase) return { path, line: matchCase.line };
  }
  return null;
}

export function validateSkill(skillPathInput) {
  const skillPath = resolve(skillPathInput);
  const skillMd = join(skillPath, "SKILL.md");
  if (!isFile(skillMd)) return [false, "SKILL.md not found"];

  const content = readFileSync(skillMd, "utf8");
  if (!content.startsWith("---")) return [false, "No YAML frontmatter found"];

  let frontmatter;
  try { frontmatter = parseFrontmatter(content); }
  catch (error) {
    const message = error instanceof FrontmatterError ? error.message : String(error);
    return [false, message];
  }

  const allowedProperties = new Set(["name", "description", "license", "allowed-tools", "metadata"]);
  const unexpected = Object.keys(frontmatter).filter((key) => !allowedProperties.has(key)).sort();
  if (unexpected.length > 0) {
    return [false, `Unexpected key(s) in SKILL.md frontmatter: ${unexpected.join(", ")}. Allowed properties are: ${[...allowedProperties].sort().join(", ")}`];
  }
  if (!("name" in frontmatter)) return [false, "Missing 'name' in frontmatter"];
  if (!("description" in frontmatter)) return [false, "Missing 'description' in frontmatter"];

  const name = frontmatter.name;
  if (typeof name !== "string") return [false, `Name must be a string, got ${typeName(name)}`];
  const normalizedName = name.trim();
  if (normalizedName) {
    if (!/^[a-z0-9-]+$/.test(normalizedName)) return [false, `Name '${normalizedName}' should be hyphen-case (lowercase letters, digits, and hyphens only)`];
    if (normalizedName.startsWith("-") || normalizedName.endsWith("-") || normalizedName.includes("--")) return [false, `Name '${normalizedName}' cannot start/end with hyphen or contain consecutive hyphens.`];
    if (normalizedName.length > MAX_SKILL_NAME_LENGTH) return [false, `Name is too long (${normalizedName.length} characters). Maximum is ${MAX_SKILL_NAME_LENGTH} characters.`];
  }

  const description = frontmatter.description;
  if (typeof description !== "string") return [false, `Description must be a string, got ${typeName(description)}`];
  const normalizedDescription = description.trim();
  if (normalizedDescription.includes("<") || normalizedDescription.includes(">")) return [false, "Description cannot contain angle brackets (< or >)"];
  if (normalizedDescription.length > 1024) return [false, `Description is too long (${normalizedDescription.length} characters). Maximum is 1024 characters.`];

  if (isFile(join(skillPath, "references", "project_config.md"))) {
    const literalBranch = findLiteralProfileBranch(skillPath);
    if (literalBranch) {
      return [false, `${relative(skillPath, literalBranch.path)}:${literalBranch.line} branches on a concrete project profile. Treat profile names as opaque and move project behavior to .agents/skills-config/${normalizedName}.`];
    }
  }
  return [true, "Skill is valid!"];
}

function findProfileComparison(source) {
  const profile = String.raw`(?:[A-Za-z_]\w*\.)*profile`;
  const string = String.raw`(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')`;
  const literal = String.raw`(?:${string}|\[[^\]\n]*${string}[^\]\n]*\])`;
  const pattern = new RegExp(String.raw`${profile}\s*(?:==|!=|\b(?:not\s+in|in)\b)\s*${literal}|${literal}\s*(?:==|!=|\b(?:not\s+in|in)\b)\s*${profile}`);
  let offset = 0;
  for (const line of source.split(/\r?\n/)) {
    if (pattern.test(line)) return { line: offset + 1 };
    offset += 1;
  }
  return null;
}

function findProfileMatchCase(source) {
  const profile = String.raw`(?:[A-Za-z_]\w*\.)*profile`;
  const matchPattern = new RegExp(String.raw`^\s*match\s+${profile}\s*:`);
  const casePattern = /^\s*case\s+(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')\s*:/;
  const lines = source.split(/\r?\n/);
  let inProfileMatch = false;
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (matchPattern.test(line)) { inProfileMatch = true; continue; }
    if (!inProfileMatch || !line.trim()) continue;
    if (casePattern.test(line)) return { line: index + 1 };
    if (!/^\s+/.test(line)) inProfileMatch = false;
  }
  return null;
}

function walkFiles(directory) {
  const result = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) result.push(...walkFiles(path));
    else if (entry.isFile()) result.push(path);
  }
  return result;
}

function isFile(path) { try { return statSync(path).isFile(); } catch { return false; } }
function isDirectory(path) { try { return statSync(path).isDirectory(); } catch { return false; } }
function typeName(value) { if (value === null) return "null"; if (Array.isArray(value)) return "array"; return typeof value; }

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (process.argv.length !== 3) {
    console.error("Usage: node scripts/quick_validate.mjs <skill_directory>");
    process.exitCode = 1;
  } else {
    const [valid, message] = validateSkill(process.argv[2]);
    console.log(message);
    process.exitCode = valid ? 0 : 1;
  }
}
