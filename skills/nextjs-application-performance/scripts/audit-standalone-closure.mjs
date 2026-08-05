#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCHEMA = "nextjs-build-contracts.v1";

function parseArgs(argv) {
  const options = { manifest: "", app: "", standaloneRoot: "", json: false };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--manifest") options.manifest = argv[++index] ?? "";
    else if (arg === "--app") options.app = argv[++index] ?? "";
    else if (arg === "--standalone-root") options.standaloneRoot = argv[++index] ?? "";
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

function walk(root, predicate) {
  const matches = [];
  const queue = [root];
  while (queue.length > 0) {
    const current = queue.pop();
    const stat = fs.lstatSync(current, { throwIfNoEntry: false });
    if (!stat) continue;
    if (stat.isSymbolicLink()) continue;
    if (stat.isDirectory()) {
      for (const entry of fs.readdirSync(current)) queue.push(path.join(current, entry));
    } else if (stat.isFile() && predicate(current)) matches.push(current);
  }
  return matches.sort();
}

function inspectSymlinks(root, failures) {
  const queue = [root];
  let symlinkCount = 0;
  while (queue.length > 0) {
    const current = queue.pop();
    const stat = fs.lstatSync(current, { throwIfNoEntry: false });
    if (!stat) continue;
    if (stat.isSymbolicLink()) {
      symlinkCount += 1;
      let realpath;
      try {
        realpath = fs.realpathSync(current);
      } catch (error) {
        failures.push(`broken standalone symlink: ${path.relative(root, current)} (${error.message})`);
        continue;
      }
      if (!inside(realpath, root)) {
        failures.push(`standalone symlink escapes artifact: ${path.relative(root, current)} -> ${realpath}`);
      }
      continue;
    }
    if (stat.isDirectory()) for (const entry of fs.readdirSync(current)) queue.push(path.join(current, entry));
  }
  return symlinkCount;
}

export function formatFailures(failures, limit = 50) {
  const lines = failures.slice(0, limit).map((failure) => `error: ${failure}`);
  if (failures.length > limit) lines.push(`error: ${failures.length - limit} additional failures omitted`);
  return lines;
}

export function auditStandaloneRoot(standaloneRoot, contract = {}) {
  const root = fs.realpathSync(standaloneRoot);
  const failures = [];
  const entrypoints = contract.entrypoints ?? [];
  if (!Array.isArray(entrypoints) || entrypoints.length === 0) {
    failures.push("standalone.entrypoints must declare at least one runtime entrypoint");
  } else {
    for (const [index, entrypoint] of entrypoints.entries()) {
      const resolved = path.resolve(root, entrypoint);
      if (!inside(resolved, root)) failures.push(`standalone.entrypoints[${index}] escapes the artifact`);
      else if (!fs.statSync(resolved, { throwIfNoEntry: false })?.isFile()) {
        failures.push(`runtime entrypoint is missing: ${entrypoint}`);
      }
    }
  }

  const traceRoots = contract.traceRoots ?? [];
  if (!Array.isArray(traceRoots) || traceRoots.length === 0) {
    failures.push("standalone.traceRoots must declare at least one Next trace root");
  }
  const manifests = [];
  for (const [index, traceRoot] of traceRoots.entries()) {
    const resolved = path.resolve(root, traceRoot);
    if (!inside(resolved, root)) {
      failures.push(`standalone.traceRoots[${index}] escapes the artifact`);
      continue;
    }
    if (!fs.statSync(resolved, { throwIfNoEntry: false })?.isDirectory()) {
      failures.push(`Next trace root is missing: ${traceRoot}`);
      continue;
    }
    manifests.push(...walk(resolved, (file) => file.endsWith(".nft.json")));
  }
  if (manifests.length === 0) failures.push("no Next .nft.json trace manifests were found");

  let tracedFiles = 0;
  for (const manifestPath of [...new Set(manifests)].sort()) {
    let manifest;
    try {
      manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    } catch (error) {
      failures.push(`invalid trace manifest ${path.relative(root, manifestPath)}: ${error.message}`);
      continue;
    }
    if (manifest.version !== 1 || !Array.isArray(manifest.files)) {
      failures.push(`unsupported trace manifest ${path.relative(root, manifestPath)}`);
      continue;
    }
    for (const [index, tracedFile] of manifest.files.entries()) {
      tracedFiles += 1;
      if (typeof tracedFile !== "string" || !tracedFile) {
        failures.push(`${path.relative(root, manifestPath)} files[${index}] is not a path`);
        continue;
      }
      const resolved = path.resolve(path.dirname(manifestPath), tracedFile);
      if (!inside(resolved, root)) {
        failures.push(`${path.relative(root, manifestPath)} trace escapes artifact: ${tracedFile}`);
        continue;
      }
      const stat = fs.lstatSync(resolved, { throwIfNoEntry: false });
      if (!stat) {
        failures.push(`${path.relative(root, manifestPath)} traced dependency is missing: ${tracedFile}`);
        continue;
      }
      try {
        if (!inside(fs.realpathSync(resolved), root)) {
          failures.push(`${path.relative(root, manifestPath)} traced dependency resolves outside artifact: ${tracedFile}`);
        }
      } catch (error) {
        failures.push(`${path.relative(root, manifestPath)} traced dependency cannot resolve: ${tracedFile} (${error.message})`);
      }
    }
  }
  const symlinkCount = inspectSymlinks(root, failures);
  return {
    schema: "nextjs-standalone-closure-audit.v1",
    status: failures.length === 0 ? "passed" : "failed",
    standaloneRoot: root,
    traceManifests: [...new Set(manifests)].length,
    tracedFiles,
    symlinkCount,
    failures,
  };
}

export function loadStandaloneContract(manifestPath, appId, standaloneRootOverride = "") {
  const absoluteManifest = path.resolve(manifestPath);
  const manifest = JSON.parse(fs.readFileSync(absoluteManifest, "utf8"));
  if (manifest.schema !== SCHEMA) throw new Error(`manifest schema must be ${SCHEMA}`);
  const app = (manifest.apps ?? []).find((candidate) => candidate.id === appId);
  if (!app) throw new Error(`app not found in manifest: ${appId}`);
  if (!app.standalone || typeof app.standalone.root !== "string") throw new Error(`${appId}.standalone.root is required`);
  let standaloneRoot;
  if (standaloneRootOverride) {
    standaloneRoot = path.resolve(standaloneRootOverride);
  } else {
    const repoRoot = findRepoRoot(path.dirname(absoluteManifest));
    const workspaceRoot = path.resolve(path.dirname(absoluteManifest), manifest.workspaceRoot ?? ".");
    if (!inside(workspaceRoot, repoRoot)) throw new Error("workspaceRoot escapes the repository");
    standaloneRoot = resolveInside(workspaceRoot, app.standalone.root, `${appId}.standalone.root`);
  }
  if (!fs.statSync(standaloneRoot, { throwIfNoEntry: false })?.isDirectory()) {
    throw new Error(`standalone root does not exist: ${standaloneRoot}`);
  }
  return { app, standaloneRoot };
}

async function main() {
  try {
    const options = parseArgs(process.argv.slice(2));
    const { app, standaloneRoot } = loadStandaloneContract(options.manifest, options.app, options.standaloneRoot);
    const result = auditStandaloneRoot(standaloneRoot, app.standalone);
    if (options.json) console.log(JSON.stringify(result, null, 2));
    else {
      console.log(`${result.status}: ${options.app} (${result.traceManifests} trace manifests, ${result.tracedFiles} traced files)`);
      for (const line of formatFailures(result.failures)) console.error(line);
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
