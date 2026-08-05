#!/usr/bin/env node

import { builtinModules } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCHEMA = "nextjs-build-contracts.v1";
const BUILTINS = new Set([...builtinModules, ...builtinModules.map((name) => `node:${name}`)]);
const JS_EXTENSIONS = [".js", ".mjs", ".cjs"];
const RESOLVE_EXTENSIONS = ["", ".js", ".mjs", ".cjs", ".json", ".node"];

function parseArgs(argv) {
  const options = { manifest: "", app: "", json: false };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--manifest") options.manifest = argv[++index] ?? "";
    else if (arg === "--app") options.app = argv[++index] ?? "";
    else if (arg === "--json") options.json = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  if (!options.manifest || !options.app) throw new Error("--manifest and --app are required");
  return options;
}

function inside(candidate, root) {
  const relative = path.relative(root, candidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function findRepoRoot(start) {
  for (let current = path.resolve(start); ; current = path.dirname(current)) {
    if (fs.existsSync(path.join(current, ".git"))) return current;
    if (path.dirname(current) === current) throw new Error("manifest is not inside a Git repository");
  }
}

function resolveInside(root, value, field) {
  if (typeof value !== "string" || !value) throw new Error(`${field} must be a non-empty path`);
  const resolved = path.resolve(root, value);
  if (!inside(resolved, root)) throw new Error(`${field} escapes the workspace root`);
  return resolved;
}

function importsFromSource(source) {
  const results = [];
  const patterns = [
    /(?:^|[;\n])\s*(?:import|export)\s+(?!type\b)(?:[^"'\n;]*?\sfrom\s*)?["']([^"']+)["']/gm,
    /\bimport\s*\(\s*["']([^"']+)["']\s*\)/gm,
    /\brequire\s*\(\s*["']([^"']+)["']\s*\)/gm,
  ];
  for (const pattern of patterns) for (const match of source.matchAll(pattern)) results.push(match[1]);
  return [...new Set(results)];
}

function walkFiles(root) {
  const files = [];
  const queue = [root];
  while (queue.length > 0) {
    const current = queue.pop();
    const stat = fs.lstatSync(current, { throwIfNoEntry: false });
    if (!stat) continue;
    if (stat.isSymbolicLink()) {
      const real = fs.realpathSync(current);
      if (!inside(real, root)) files.push({ path: current, escapedSymlink: real });
      continue;
    }
    if (stat.isDirectory()) {
      for (const entry of fs.readdirSync(current)) queue.push(path.join(current, entry));
    } else if (stat.isFile()) files.push({ path: current });
  }
  return files;
}

function resolveFile(base) {
  for (const extension of RESOLVE_EXTENSIONS) {
    const candidate = `${base}${extension}`;
    if (fs.statSync(candidate, { throwIfNoEntry: false })?.isFile()) return candidate;
  }
  for (const extension of RESOLVE_EXTENSIONS.slice(1)) {
    const candidate = path.join(base, `index${extension}`);
    if (fs.statSync(candidate, { throwIfNoEntry: false })?.isFile()) return candidate;
  }
  return null;
}

function packageParts(specifier) {
  const pieces = specifier.split("/");
  const packageName = specifier.startsWith("@") ? pieces.slice(0, 2).join("/") : pieces[0];
  const subpath = pieces.slice(specifier.startsWith("@") ? 2 : 1).join("/");
  return { packageName, subpath };
}

function resolveBareWithin(specifier, fromFile, standaloneRoot) {
  const { packageName, subpath } = packageParts(specifier);
  for (let current = path.dirname(fromFile); inside(current, standaloneRoot); current = path.dirname(current)) {
    const packageRoot = path.join(current, "node_modules", ...packageName.split("/"));
    if (fs.statSync(packageRoot, { throwIfNoEntry: false })?.isDirectory()) {
      if (subpath) return resolveFile(path.join(packageRoot, subpath));
      const packageJsonPath = path.join(packageRoot, "package.json");
      if (!fs.existsSync(packageJsonPath)) return null;
      const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
      const rootExport = packageJson.exports?.["."] ?? packageJson.exports;
      const target = typeof rootExport === "string"
        ? rootExport
        : rootExport?.import ?? rootExport?.require ?? rootExport?.default ?? packageJson.module ?? packageJson.main ?? "index.js";
      if (typeof target !== "string") return null;
      return resolveFile(path.join(packageRoot, target));
    }
    if (current === standaloneRoot) break;
  }
  return null;
}

export function auditStandaloneRoot(standaloneRoot, allowedMissing = []) {
  const root = fs.realpathSync(standaloneRoot);
  const allowed = new Set(allowedMissing);
  const failures = [];
  let scannedFiles = 0;
  const files = walkFiles(root);
  for (const item of files) {
    if (item.escapedSymlink) {
      failures.push(`symlink escapes standalone root: ${item.path} -> ${item.escapedSymlink}`);
      continue;
    }
    if (!JS_EXTENSIONS.includes(path.extname(item.path))) continue;
    scannedFiles += 1;
    const source = fs.readFileSync(item.path, "utf8");
    for (const specifier of importsFromSource(source)) {
      if (BUILTINS.has(specifier) || specifier.startsWith("node:")) continue;
      let resolved = null;
      if (specifier.startsWith(".")) resolved = resolveFile(path.resolve(path.dirname(item.path), specifier));
      else if (specifier.startsWith("/")) resolved = resolveFile(specifier);
      else resolved = resolveBareWithin(specifier, item.path, root);
      if (!resolved || !inside(fs.realpathSync(resolved), root)) {
        const key = `${path.relative(root, item.path)}:${specifier}`;
        if (!allowed.has(specifier) && !allowed.has(key)) failures.push(`${key} does not resolve inside the standalone artifact`);
      }
    }
  }
  return {
    schema: "nextjs-standalone-closure-audit.v1",
    status: failures.length === 0 ? "passed" : "failed",
    standaloneRoot: root,
    scannedFiles,
    failures,
  };
}

export function loadStandaloneContract(manifestPath, appId) {
  const absoluteManifest = path.resolve(manifestPath);
  const manifest = JSON.parse(fs.readFileSync(absoluteManifest, "utf8"));
  if (manifest.schema !== SCHEMA) throw new Error(`manifest schema must be ${SCHEMA}`);
  const repoRoot = findRepoRoot(path.dirname(absoluteManifest));
  const workspaceRoot = path.resolve(path.dirname(absoluteManifest), manifest.workspaceRoot ?? ".");
  if (!inside(workspaceRoot, repoRoot)) throw new Error("workspaceRoot escapes the repository");
  const app = (manifest.apps ?? []).find((candidate) => candidate.id === appId);
  if (!app) throw new Error(`app not found in manifest: ${appId}`);
  if (!app.standalone || typeof app.standalone.root !== "string") throw new Error(`${appId}.standalone.root is required`);
  const standaloneRoot = resolveInside(workspaceRoot, app.standalone.root, `${appId}.standalone.root`);
  if (!fs.statSync(standaloneRoot, { throwIfNoEntry: false })?.isDirectory()) {
    throw new Error(`standalone root does not exist: ${standaloneRoot}`);
  }
  return { app, standaloneRoot };
}

async function main() {
  try {
    const options = parseArgs(process.argv.slice(2));
    const { app, standaloneRoot } = loadStandaloneContract(options.manifest, options.app);
    const result = auditStandaloneRoot(standaloneRoot, app.standalone.allowedMissing ?? []);
    if (options.json) console.log(JSON.stringify(result, null, 2));
    else {
      console.log(`${result.status}: ${options.app} (${result.scannedFiles} runtime files)`);
      for (const failure of result.failures) console.error(`error: ${failure}`);
    }
    return result.status === "passed" ? 0 : 1;
  } catch (error) {
    console.error(`error: ${error.message}`);
    return 2;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = await main();
}
