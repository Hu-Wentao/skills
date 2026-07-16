#!/usr/bin/env node

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { basename, dirname, isAbsolute, join, normalize, relative, resolve } from "node:path";

function parseArgs(argv) {
  const args = { root: process.cwd(), docs: "docs" };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--root" || value === "--docs") {
      const next = argv[index + 1];
      if (!next) throw new Error(`${value} requires a value`);
      args[value.slice(2)] = next;
      index += 1;
    } else if (value === "--help" || value === "-h") {
      args.help = true;
    } else {
      throw new Error(`unknown argument: ${value}`);
    }
  }
  return args;
}

function markdownFiles(directory) {
  if (!existsSync(directory)) return [];
  const files = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...markdownFiles(path));
    else if (entry.isFile() && entry.name.endsWith(".md")) files.push(path);
  }
  return files;
}

function lineNumber(content, offset) {
  return content.slice(0, offset).split("\n").length;
}

function localMarkdownLinks(content) {
  const links = [];
  const pattern = /\[[^\]]*\]\(([^)]+)\)/g;
  for (const match of content.matchAll(pattern)) {
    let target = match[1].trim();
    if (target.startsWith("<") && target.endsWith(">")) target = target.slice(1, -1);
    target = target.split("#", 1)[0];
    if (!target || /^(?:[a-z]+:|#)/i.test(target)) continue;
    links.push({ target, offset: match.index ?? 0 });
  }
  return links;
}

function formatIssue(issue, root) {
  const location = issue.file
    ? `${relative(root, issue.file)}${issue.line ? `:${issue.line}` : ""}`
    : ".";
  return `${issue.level.toUpperCase()} ${location} ${issue.message}`;
}

function parseFrontmatter(content) {
  const match = content.match(/^---\n([\s\S]*?)\n---(?:\n|$)/);
  if (!match) return null;
  const fields = new Map();
  for (const line of match[1].split("\n")) {
    const separator = line.indexOf(":");
    if (separator < 1) continue;
    fields.set(line.slice(0, separator).trim(), line.slice(separator + 1).trim());
  }
  return fields;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log("Usage: validate-governance.mjs [--root PROJECT] [--docs RELATIVE_OR_ABSOLUTE_PATH]");
    return 0;
  }

  const root = resolve(args.root);
  const docs = isAbsolute(args.docs) ? normalize(args.docs) : resolve(root, args.docs);
  const issues = [];
  if (!existsSync(docs) || !statSync(docs).isDirectory()) {
    issues.push({ level: "warning", message: `governance docs directory not found: ${docs}` });
  }

  const files = markdownFiles(docs);
  const declarations = new Map();
  const references = [];
  const defectRecords = new Map();
  const defectReferences = [];
  const reqPattern = /\bREQ-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{3,}\b/g;
  const reqIdPattern = /^REQ-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{3,}$/;
  const headingPattern = /^#{2,6}\s+(REQ-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{3,})\b/gm;
  const defectIdPattern = /^DEF-\d{8}-[a-z0-9]+(?:-[a-z0-9]+)*$/;
  const requiredDefectFields = ["id", "status", "date", "requirements", "recurrence", "prior-defects"];
  const requiredDefectHeadings = [
    "Observed and Expected",
    "Failure Family",
    "Causes and Ownership",
    "Repair and Next Unseen Case",
    "Verification and Test Escape",
    "Compatibility",
  ];

  for (const file of files) {
    const content = readFileSync(file, "utf8");
    for (const match of content.matchAll(headingPattern)) {
      const id = match[1];
      const declaration = { file, line: lineNumber(content, match.index ?? 0) };
      if (declarations.has(id)) {
        const first = declarations.get(id);
        issues.push({
          level: "error",
          file,
          line: declaration.line,
          message: `duplicate requirement ${id}; first declared at ${relative(root, first.file)}:${first.line}`,
        });
      } else {
        declarations.set(id, declaration);
      }
    }
    for (const match of content.matchAll(reqPattern)) {
      references.push({ id: match[0], file, line: lineNumber(content, match.index ?? 0) });
    }
    for (const link of localMarkdownLinks(content)) {
      const decoded = decodeURIComponent(link.target);
      const destination = resolve(dirname(file), decoded);
      if (!existsSync(destination)) {
        issues.push({
          level: "error",
          file,
          line: lineNumber(content, link.offset),
          message: `broken local link: ${link.target}`,
        });
      }
    }

    const defectDirectory = resolve(docs, "defects");
    if (dirname(file) === defectDirectory && file !== join(defectDirectory, "README.md")) {
      const filenameId = basename(file, ".md");
      const frontmatter = parseFrontmatter(content);
      if (!defectIdPattern.test(filenameId)) {
        issues.push({ level: "error", file, message: "defect filename must be DEF-YYYYMMDD-slug.md" });
      }
      if (!frontmatter) {
        issues.push({ level: "error", file, line: 1, message: "defect record requires YAML-like frontmatter" });
      } else {
        for (const field of requiredDefectFields) {
          if (!frontmatter.get(field)) issues.push({ level: "error", file, line: 1, message: `defect record missing frontmatter field: ${field}` });
        }
        const id = frontmatter.get("id");
        if (id && id !== filenameId) issues.push({ level: "error", file, line: 1, message: `defect id ${id} does not match filename ${filenameId}` });
        if (id) {
          if (defectRecords.has(id)) issues.push({ level: "error", file, line: 1, message: `duplicate defect id ${id}` });
          else defectRecords.set(id, { file });
        }
        const status = frontmatter.get("status");
        if (status && !["implemented", "superseded"].includes(status)) issues.push({ level: "error", file, line: 1, message: `unsupported defect status: ${status}` });
        const recurrence = frontmatter.get("recurrence");
        if (recurrence && !["first", "suspected", "confirmed"].includes(recurrence)) issues.push({ level: "error", file, line: 1, message: `unsupported defect recurrence: ${recurrence}` });
        const date = frontmatter.get("date");
        if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) issues.push({ level: "error", file, line: 1, message: `invalid defect date: ${date}` });
        const requirements = frontmatter.get("requirements");
        if (requirements && requirements !== "none") {
          for (const requirementId of requirements.split(",").map((value) => value.trim()).filter(Boolean)) {
            if (!reqIdPattern.test(requirementId)) issues.push({ level: "error", file, line: 1, message: `invalid defect requirement id: ${requirementId}` });
          }
        }
        const priorDefects = frontmatter.get("prior-defects");
        if (priorDefects && priorDefects !== "none") {
          for (const priorId of priorDefects.split(",").map((value) => value.trim()).filter(Boolean)) {
            if (!defectIdPattern.test(priorId)) issues.push({ level: "error", file, line: 1, message: `invalid prior defect id: ${priorId}` });
            defectReferences.push({ id: priorId, file, line: 1 });
          }
        }
      }
      if (!new RegExp(`^#\\s+${filenameId}\\b`, "m").test(content)) {
        issues.push({ level: "error", file, message: `defect title must start with # ${filenameId}` });
      }
      for (const heading of requiredDefectHeadings) {
        if (!content.includes(`## ${heading}`)) issues.push({ level: "error", file, message: `defect record missing heading: ${heading}` });
      }
    }
  }

  for (const reference of references) {
    if (!declarations.has(reference.id)) {
      issues.push({
        level: "error",
        file: reference.file,
        line: reference.line,
        message: `requirement ${reference.id} is referenced but not declared in ${relative(root, docs)}`,
      });
    }
  }

  for (const reference of defectReferences) {
    if (!defectRecords.has(reference.id)) {
      issues.push({ level: "error", file: reference.file, line: reference.line, message: `prior defect ${reference.id} is not declared in ${relative(root, docs)}/defects` });
    }
  }

  const plans = join(docs, "plans");
  const plansIndex = join(plans, "README.md");
  if (existsSync(plans) && !existsSync(plansIndex)) {
    issues.push({ level: "warning", file: plans, message: "plans directory has no README.md status index" });
  }
  const defects = join(docs, "defects");
  const defectsIndex = join(defects, "README.md");
  if (existsSync(defects) && !existsSync(defectsIndex)) {
    issues.push({ level: "warning", file: defects, message: "defects directory has no README.md policy" });
  }

  for (const issue of issues) console.log(formatIssue(issue, root));
  const errors = issues.filter((issue) => issue.level === "error").length;
  const warnings = issues.filter((issue) => issue.level === "warning").length;
  console.log(`Checked ${files.length} Markdown files, ${declarations.size} requirement declarations, ${defectRecords.size} defect records: ${errors} error(s), ${warnings} warning(s).`);
  return errors > 0 ? 1 : 0;
}

try {
  process.exitCode = main();
} catch (error) {
  console.error(`ERROR . ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 2;
}
