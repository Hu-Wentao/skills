#!/usr/bin/env node

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, isAbsolute, join, normalize, relative, resolve } from "node:path";

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
  const reqPattern = /\bREQ-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{3,}\b/g;
  const headingPattern = /^#{2,6}\s+(REQ-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{3,})\b/gm;

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

  const plans = join(docs, "plans");
  const plansIndex = join(plans, "README.md");
  if (existsSync(plans) && !existsSync(plansIndex)) {
    issues.push({ level: "warning", file: plans, message: "plans directory has no README.md status index" });
  }

  for (const issue of issues) console.log(formatIssue(issue, root));
  const errors = issues.filter((issue) => issue.level === "error").length;
  const warnings = issues.filter((issue) => issue.level === "warning").length;
  console.log(`Checked ${files.length} Markdown files, ${declarations.size} requirement declarations: ${errors} error(s), ${warnings} warning(s).`);
  return errors > 0 ? 1 : 0;
}

try {
  process.exitCode = main();
} catch (error) {
  console.error(`ERROR . ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 2;
}
