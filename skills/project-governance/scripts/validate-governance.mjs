#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, isAbsolute, join, normalize, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

function parseArgs(argv) {
  const args = { root: process.cwd(), docs: "docs", json: false, mdqScript: null };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--root" || value === "--docs" || value === "--mdq-script") {
      const next = argv[index + 1];
      if (!next) throw new Error(`${value} requires a value`);
      const key = value === "--mdq-script" ? "mdqScript" : value.slice(2);
      args[key] = next;
      index += 1;
    } else if (value === "--json") {
      args.json = true;
    } else if (value === "--help" || value === "-h") {
      args.help = true;
    } else {
      throw new Error(`unknown argument: ${value}`);
    }
  }
  return args;
}

function resolveMdqScript(configured) {
  const skillRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const candidates = [
    configured,
    join(dirname(skillRoot), "queryable-markdown", "scripts", "mdq.py"),
    join(homedir(), ".codex", "skills", "queryable-markdown", "scripts", "mdq.py"),
    join(homedir(), ".agents", "skills", "queryable-markdown", "scripts", "mdq.py"),
  ].filter(Boolean);
  return candidates.find((candidate) => existsSync(candidate)) ?? null;
}

const excludedDirectoryNames = new Set([
  ".git",
  ".next",
  ".nuxt",
  ".output",
  ".turbo",
  ".venv",
  "__pycache__",
  "build",
  "coverage",
  "dist",
  "node_modules",
  "target",
  "vendor",
]);

function runMdqScan(paths, mdqScript, globs = []) {
  if (paths.length === 0) return { report: null, error: null };
  const command = ["run", mdqScript, "scan", ...paths, "--require-contract", "--limit", "1"];
  for (const pattern of globs) command.push("--glob", pattern);
  const completed = spawnSync("uv", command, {
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
  if (completed.error) {
    return {
      report: null,
      error: `persistent mdq validation could not run: ${completed.error.message}`,
    };
  }
  try {
    return { report: JSON.parse(completed.stdout), error: null };
  } catch (error) {
    const detail = completed.stderr.trim() || completed.stdout.trim();
    return {
      report: null,
      error: `persistent mdq validation returned invalid JSON: ${error.message}${detail ? `; ${detail}` : ""}`,
    };
  }
}

function repositoryBffFiles(root, docs) {
  const files = [];
  function visit(directory) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      if (entry.isSymbolicLink()) continue;
      const path = join(directory, entry.name);
      if (entry.isDirectory()) {
        if (excludedDirectoryNames.has(entry.name)) continue;
        if (entry.name === ".cache" && basename(directory) === ".agents") continue;
        visit(path);
      } else if (entry.isFile() && entry.name.endsWith(".bff.md")) {
        const fromDocs = relative(docs, path);
        if (fromDocs === "" || (!fromDocs.startsWith("..") && !isAbsolute(fromDocs))) {
          continue;
        }
        files.push(path);
      }
    }
  }
  if (existsSync(root) && statSync(root).isDirectory()) visit(root);
  return files.sort();
}

function validatePersistentMdqContracts(root, docs, mdqScript) {
  const globs = [
    "requirements.md",
    "requirements/**/*.md",
    "baseline/**/*.md",
    "plans/**/*.md",
    "evaluations/**/*.md",
    "defects/**/*.md",
    "archive/**/*.md",
    "*coverage*.md",
    "*verification*.md",
    "*traceability*.md",
  ];
  const scans = [];
  if (existsSync(docs) && statSync(docs).isDirectory()) {
    scans.push(runMdqScan([docs], mdqScript, globs));
  }
  const embeddedContracts = repositoryBffFiles(root, docs);
  if (embeddedContracts.length > 0) {
    scans.push(runMdqScan(embeddedContracts, mdqScript));
  }
  return scans;
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
    console.log("Usage: validate-governance.mjs [--root PROJECT] [--docs RELATIVE_OR_ABSOLUTE_PATH] [--mdq-script PATH] [--json]");
    return 0;
  }

  const root = resolve(args.root);
  const docs = isAbsolute(args.docs) ? normalize(args.docs) : resolve(root, args.docs);
  const issues = [];
  if (!existsSync(docs) || !statSync(docs).isDirectory()) {
    issues.push({ level: "warning", message: `governance docs directory not found: ${docs}` });
  }

  const files = markdownFiles(docs);
  const mdqScript = resolveMdqScript(args.mdqScript);
  const blockingMdqDiagnostics = new Set([
    "duplicate_key",
    "field_conflict",
    "incomplete_record",
    "key_conflict",
    "marker_conflict",
    "missing_key",
    "no_records",
  ]);
  if (!mdqScript) {
    issues.push({
      level: "error",
      message: "queryable-markdown mdq.py is required to validate governed Markdown contracts",
    });
  } else {
    for (const { report, error } of validatePersistentMdqContracts(root, docs, mdqScript)) {
      if (error) {
        issues.push({ level: "error", message: error });
        continue;
      }
      if (!report) continue;
      for (const item of report.diagnostics ?? []) {
        if (
          item.document
          && basename(resolve(item.document)) === "README.md"
        ) continue;
        if (
          item.severity !== "error"
          && !blockingMdqDiagnostics.has(item.code)
        ) continue;
        issues.push({
          level: "error",
          file: item.document ? resolve(item.document) : undefined,
          line: item.line ?? null,
          message: `[${item.code}] ${item.message}`,
        });
      }
    }
  }
  const declarations = new Map();
  const references = [];
  const defectRecords = new Map();
  const defectReferences = [];
  const verificationReferences = new Set();
  let hasVerificationDocument = false;
  const reqPattern = /\bREQ-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{3,}\b/g;
  const reqIdPattern = /^REQ-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{3,}$/;
  const headingPattern = /^#{2,6}\s+(REQ-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{3,})\b/gm;
  const defectIdPattern = /^DEF-\d{8}-[a-z0-9]+(?:-[a-z0-9]+)*$/;
  const requiredDefectFields = ["id", "status", "date", "requirements", "recurrence", "prior-defects"];
  const allowedDefectStatuses = ["pending_repair", "implemented", "superseded"];
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
    const relativeFile = relative(docs, file);
    if (/(?:verification|coverage|traceability)/i.test(relativeFile)) {
      hasVerificationDocument = true;
    }
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
      if (/(?:verification|coverage|traceability)/i.test(relativeFile)) {
        verificationReferences.add(match[0]);
      }
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
    if (
      dirname(file) === defectDirectory
      && !["README.md", "INDEX.md"].includes(basename(file))
    ) {
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
        if (status && !allowedDefectStatuses.includes(status)) issues.push({ level: "error", file, line: 1, message: `unsupported defect status: ${status}` });
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
  const plansIndex = join(plans, "INDEX.md");
  if (existsSync(plans) && !existsSync(plansIndex)) {
    issues.push({ level: "warning", file: plans, message: "plans directory has no INDEX.md status index" });
  } else if (existsSync(plansIndex)) {
    const index = readFileSync(plansIndex, "utf8");
    for (const plan of markdownFiles(plans)) {
      if (plan === plansIndex || basename(plan) === "README.md") continue;
      const relativePlan = relative(plans, plan).replaceAll("\\", "/");
      if (!index.includes(relativePlan) && !index.includes(basename(relativePlan))) {
        issues.push({
          level: "warning",
          file: plan,
          message: "plan is not referenced by the plans lifecycle index",
        });
      }
    }
  }
  const defects = join(docs, "defects");
  const defectsIndex = join(defects, "INDEX.md");
  if (existsSync(defects) && !existsSync(defectsIndex)) {
    issues.push({ level: "warning", file: defects, message: "defects directory has no INDEX.md policy" });
  }

  for (const [id, declaration] of declarations) {
    if (hasVerificationDocument && !verificationReferences.has(id)) {
      issues.push({
        level: "warning",
        file: declaration.file,
        line: declaration.line,
        message: `requirement ${id} has no reference in a verification, coverage, or traceability document`,
      });
    }
  }

  const errors = issues.filter((issue) => issue.level === "error").length;
  const warnings = issues.filter((issue) => issue.level === "warning").length;
  if (args.json) {
    console.log(JSON.stringify({
      schema: "project-governance.document-audit.v1",
      status: errors > 0 ? "failed" : "ready",
      state: errors > 0 ? "structural_errors" : "audit_completed",
      root,
      docs,
      counts: {
        files: files.length,
        requirementDeclarations: declarations.size,
        defectRecords: defectRecords.size,
        errors,
        warnings,
      },
      issues: issues.map((issue) => ({
        level: issue.level,
        file: issue.file ? relative(root, issue.file) : ".",
        line: issue.line ?? null,
        message: issue.message,
      })),
      allowedNextActions: errors > 0
        ? ["repair_mechanical_drift_if_authorized", "request_semantic_decision"]
        : ["semantic_review"],
    }, null, 2));
  } else {
    for (const issue of issues) console.log(formatIssue(issue, root));
    console.log(`Checked ${files.length} Markdown files, ${declarations.size} requirement declarations, ${defectRecords.size} defect records: ${errors} error(s), ${warnings} warning(s).`);
  }
  return errors > 0 ? 1 : 0;
}

try {
  process.exitCode = main();
} catch (error) {
  console.error(`ERROR . ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 2;
}
