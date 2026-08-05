#!/usr/bin/env node

import { createRequire, builtinModules } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const SCHEMA = "nextjs-build-contracts.v1";
const SOURCE_EXTENSIONS = ["", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"];
const BUILTINS = new Set([...builtinModules, ...builtinModules.map((name) => `node:${name}`)]);

export class ContractError extends Error {}

function parseArgs(argv) {
  const options = { manifest: "", app: "", json: false };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--manifest") options.manifest = argv[++index] ?? "";
    else if (arg === "--app") options.app = argv[++index] ?? "";
    else if (arg === "--json") options.json = true;
    else throw new ContractError(`unknown argument: ${arg}`);
  }
  if (!options.manifest) throw new ContractError("--manifest is required");
  if (!options.app) throw new ContractError("--app is required");
  return options;
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    throw new ContractError(`cannot read JSON ${file}: ${error.message}`);
  }
}

function inside(candidate, root) {
  const relative = path.relative(root, candidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function findRepoRoot(start) {
  for (let current = path.resolve(start); ; current = path.dirname(current)) {
    if (fs.existsSync(path.join(current, ".git"))) return current;
    if (path.dirname(current) === current) throw new ContractError("manifest is not inside a Git repository");
  }
}

function resolveInside(root, value, field, { mustExist = true } = {}) {
  if (typeof value !== "string" || !value) throw new ContractError(`${field} must be a non-empty path`);
  const resolved = path.resolve(root, value);
  if (!inside(resolved, root)) throw new ContractError(`${field} escapes the workspace root`);
  if (mustExist && !fs.existsSync(resolved)) throw new ContractError(`${field} does not exist: ${resolved}`);
  return resolved;
}

function packageNameFromSpecifier(specifier) {
  if (specifier.startsWith("@")) return specifier.split("/").slice(0, 2).join("/");
  return specifier.split("/")[0];
}

function exportSpecifier(packageName, exportName) {
  if (exportName === ".") return packageName;
  if (!exportName.startsWith("./")) throw new ContractError(`invalid package export key: ${exportName}`);
  return `${packageName}/${exportName.slice(2)}`;
}

function sourceCandidate(base) {
  const extensionAliases = {
    ".js": [".ts", ".tsx", ".js", ".jsx"],
    ".mjs": [".mts", ".mjs"],
    ".cjs": [".cts", ".cjs"],
  };
  const requestedExtension = path.extname(base);
  if (extensionAliases[requestedExtension]) {
    const withoutExtension = base.slice(0, -requestedExtension.length);
    for (const extension of extensionAliases[requestedExtension]) {
      const candidate = `${withoutExtension}${extension}`;
      if (fs.statSync(candidate, { throwIfNoEntry: false })?.isFile()) return candidate;
    }
  }
  for (const extension of SOURCE_EXTENSIONS) {
    const candidate = `${base}${extension}`;
    if (fs.statSync(candidate, { throwIfNoEntry: false })?.isFile()) return candidate;
  }
  for (const extension of SOURCE_EXTENSIONS.slice(1)) {
    const candidate = path.join(base, `index${extension}`);
    if (fs.statSync(candidate, { throwIfNoEntry: false })?.isFile()) return candidate;
  }
  return null;
}

function importSpecifiers(source) {
  const results = [];
  const patterns = [
    /(?:^|[;\n])\s*(?:import|export)\s+(?!type\b)(?:[^"'\n;]*?\sfrom\s*)?["']([^"']+)["']/gm,
    /\bimport\s*\(\s*["']([^"']+)["']\s*\)/gm,
    /\brequire\s*\(\s*["']([^"']+)["']\s*\)/gm,
  ];
  for (const pattern of patterns) {
    for (const match of source.matchAll(pattern)) results.push(match[1]);
  }
  return [...new Set(results)];
}

export function scanEntrypoint(entrypoint, packageRoot) {
  const canonicalRoot = fs.realpathSync(packageRoot);
  const visited = new Set();
  const signals = new Set();
  const queue = [entrypoint];
  while (queue.length > 0) {
    const current = fs.realpathSync(queue.pop());
    if (visited.has(current)) continue;
    if (!inside(current, canonicalRoot)) continue;
    visited.add(current);
    const source = fs.readFileSync(current, "utf8");
    if (/^\s*["']use client["'];?/m.test(source)) signals.add("client");
    for (const specifier of importSpecifiers(source)) {
      if (specifier === "server-only") signals.add("server");
      if (specifier === "next/navigation") signals.add("client");
      if (BUILTINS.has(specifier)) signals.add("server");
      if (!specifier.startsWith(".")) continue;
      const candidate = sourceCandidate(path.resolve(path.dirname(current), specifier));
      if (candidate) queue.push(candidate);
    }
  }
  return { files: [...visited].sort(), signals: [...signals].sort() };
}

function validateEvidenceException(app, workspaceRoot, id, failures) {
  const exception = app.evidenceExceptions?.[id];
  if (!exception || typeof exception !== "object") {
    failures.push(`${app.id}: ${id} requires measured evidence; no evidenceExceptions.${id} was declared`);
    return;
  }
  let evidenceFile;
  try {
    evidenceFile = resolveInside(workspaceRoot, exception.evidenceFile, `${app.id}.evidenceExceptions.${id}.evidenceFile`);
  } catch (error) {
    failures.push(error.message);
    return;
  }
  if (typeof exception.requiredText !== "string" || !exception.requiredText) {
    failures.push(`${app.id}: evidenceExceptions.${id}.requiredText must be non-empty`);
    return;
  }
  if (!fs.readFileSync(evidenceFile, "utf8").includes(exception.requiredText)) {
    failures.push(`${app.id}: evidence for ${id} is missing required marker ${JSON.stringify(exception.requiredText)}`);
  }
}

function inspectPolicyFiles(app, workspaceRoot, failures) {
  const text = (app.policyFiles ?? []).map((file, index) => {
    const resolved = resolveInside(workspaceRoot, file, `${app.id}.policyFiles[${index}]`);
    return `${resolved}\n${fs.readFileSync(resolved, "utf8")}`;
  }).join("\n");
  if (/resolve\s*\.\s*symlinks\s*=\s*false|symlinks\s*:\s*false/.test(text)) {
    validateEvidenceException(app, workspaceRoot, "resolveSymlinksFalse", failures);
  }
  if (/optimizePackageImports\s*:/.test(text)) {
    validateEvidenceException(app, workspaceRoot, "optimizePackageImports", failures);
  }
  const memory = app.memory;
  if (!memory || !Number.isInteger(memory.containerLimitMiB) || memory.containerLimitMiB <= 0) {
    failures.push(`${app.id}: memory.containerLimitMiB must be a positive integer`);
    return;
  }
  if (memory.heapLimitMiB !== undefined && (!Number.isInteger(memory.heapLimitMiB) || memory.heapLimitMiB <= 0)) {
    failures.push(`${app.id}: memory.heapLimitMiB must be a positive integer when declared`);
  }
  if (memory.baselineHeapLimitMiB !== undefined &&
      (!Number.isInteger(memory.baselineHeapLimitMiB) || memory.baselineHeapLimitMiB <= 0)) {
    failures.push(`${app.id}: memory.baselineHeapLimitMiB must be a positive integer when declared`);
  }
  if (Number.isInteger(memory.heapLimitMiB) && memory.heapLimitMiB > memory.containerLimitMiB) {
    failures.push(`${app.id}: heapLimitMiB ${memory.heapLimitMiB} exceeds the ${memory.containerLimitMiB} MiB container gate`);
  }
  if (Number.isInteger(memory.heapLimitMiB) && Number.isInteger(memory.baselineHeapLimitMiB) &&
      memory.heapLimitMiB > memory.baselineHeapLimitMiB) {
    validateEvidenceException(app, workspaceRoot, "heapIncrease", failures);
  }
}

function findLexicalPackage(appRoot, workspaceRoot, packageName) {
  for (const nodeModules of [path.join(appRoot, "node_modules"), path.join(workspaceRoot, "node_modules")]) {
    const candidate = path.join(nodeModules, ...packageName.split("/"));
    if (fs.lstatSync(candidate, { throwIfNoEntry: false })) return candidate;
  }
  return null;
}

function normalizeConfig(configExport) {
  if (typeof configExport === "function") return configExport("phase-production-build", { defaultConfig: {} });
  return configExport;
}

async function callExternalFunction(external, request, appRoot) {
  return await new Promise((resolve, reject) => {
    let settled = false;
    const finish = (error, result) => {
      if (settled) return;
      settled = true;
      if (error) reject(error);
      else resolve(result);
    };
    try {
      const returned = external({ context: appRoot, request, dependencyType: "esm" }, finish);
      if (returned && typeof returned.then === "function") returned.then((value) => finish(null, value), finish);
      else if (returned !== undefined) finish(null, returned);
      else queueMicrotask(() => {
        if (!settled) finish(null, undefined);
      });
    } catch (error) {
      reject(error);
    }
  });
}

async function externalMatches(external, request, appRoot) {
  if (typeof external === "function") return (await callExternalFunction(external, request, appRoot)) !== undefined;
  if (typeof external === "string") return external === request;
  if (external instanceof RegExp) return external.test(request);
  if (Array.isArray(external)) {
    for (const item of external) if (await externalMatches(item, request, appRoot)) return true;
    return false;
  }
  return Boolean(external && typeof external === "object" && Object.hasOwn(external, request));
}

async function inspectNextConfig(app, workspaceRoot, appRoot, packageContracts, failures) {
  const nextConfigPath = resolveInside(workspaceRoot, app.nextConfig, `${app.id}.nextConfig`);
  let config;
  try {
    const imported = await import(`${pathToFileURL(nextConfigPath).href}?contract-audit=${Date.now()}`);
    config = await normalizeConfig(imported.default ?? imported);
  } catch (error) {
    failures.push(`${app.id}: cannot evaluate Next config: ${error.message}`);
    return { detected: [] };
  }
  if (!config || typeof config !== "object") {
    failures.push(`${app.id}: Next config did not evaluate to an object`);
    return { detected: [] };
  }

  let externals = [];
  if (typeof config.webpack === "function") {
    try {
      const webpackConfig = await config.webpack(
        { externals: [], resolve: {} },
        { buildId: "contract-audit", dev: false, dir: appRoot, isServer: true, nextRuntime: "nodejs", webpack: {} },
      );
      externals = webpackConfig?.externals ?? [];
    } catch (error) {
      failures.push(`${app.id}: cannot evaluate server webpack config: ${error.message}`);
    }
  }
  if (!Array.isArray(externals)) externals = [externals];
  const standard = new Set(config.serverExternalPackages ?? []);
  const allowed = Array.isArray(app.allowedExternalPackages) ? app.allowedExternalPackages : [];
  const allowedSpecifiers = new Set(allowed.map((entry) => entry.specifier));
  const probes = new Set([...standard, ...allowedSpecifiers]);
  for (const contract of packageContracts.values()) {
    probes.add(contract.name);
    probes.add(`${contract.name}/__next_boundary_probe__`);
    for (const entrypoint of contract.entrypoints) probes.add(exportSpecifier(contract.name, entrypoint.export));
  }
  const detected = new Set(standard);
  for (const request of probes) {
    try {
      if (await externalMatches(externals, request, appRoot)) detected.add(request);
    } catch (error) {
      failures.push(`${app.id}: webpack external probe for ${request} failed: ${error.message}`);
    }
  }

  for (const specifier of detected) {
    const packageName = packageNameFromSpecifier(specifier);
    const contract = packageContracts.get(packageName);
    const wholePackage = specifier === packageName || detected.has(`${packageName}/__next_boundary_probe__`);
    if (!allowedSpecifiers.has(specifier) && !(wholePackage && allowedSpecifiers.has(packageName))) {
      failures.push(`${app.id}: ${specifier} is externalized but not admitted by allowedExternalPackages`);
    }
    if (!contract) continue;
    if (wholePackage && contract.classification !== "server") {
      failures.push(`${app.id}: whole-package externalization is forbidden for ${contract.classification} package ${packageName}`);
      continue;
    }
    if (!wholePackage) {
      const entrypoint = contract.entrypoints.find((entry) => exportSpecifier(packageName, entry.export) === specifier);
      if (!entrypoint || entrypoint.surface !== "server") {
        failures.push(`${app.id}: externalized subpath ${specifier} is not a declared server entrypoint`);
      }
    }
  }
  for (const entry of allowed) {
    if (!entry || typeof entry.specifier !== "string" || !entry.specifier) {
      failures.push(`${app.id}: every allowedExternalPackages entry requires specifier`);
      continue;
    }
    const packageName = packageNameFromSpecifier(entry.specifier);
    const used = detected.has(entry.specifier) || detected.has(packageName) || detected.has(`${packageName}/__next_boundary_probe__`);
    if (!used) failures.push(`${app.id}: admitted external ${entry.specifier} was not detected in the production Next config`);
  }
  return { detected: [...detected].sort() };
}

function inspectPackages(app, workspaceRoot, appRoot, failures) {
  const appPackagePath = resolveInside(workspaceRoot, app.packageJson, `${app.id}.packageJson`);
  const appPackage = readJson(appPackagePath);
  const directWorkspace = new Set(
    Object.entries({ ...appPackage.dependencies, ...appPackage.optionalDependencies })
      .filter(([, version]) => typeof version === "string" && version.startsWith("workspace:"))
      .map(([name]) => name),
  );
  const contracts = new Map();
  for (const [index, contract] of (app.workspacePackages ?? []).entries()) {
    if (!contract || typeof contract.name !== "string") {
      failures.push(`${app.id}: workspacePackages[${index}].name is required`);
      continue;
    }
    if (contracts.has(contract.name)) {
      failures.push(`${app.id}: duplicate workspace package contract ${contract.name}`);
      continue;
    }
    if (!["server", "client", "hybrid"].includes(contract.classification)) {
      failures.push(`${app.id}: ${contract.name} classification must be server, client, or hybrid`);
    }
    const packageRoot = resolveInside(workspaceRoot, contract.root, `${app.id}.${contract.name}.root`);
    const packageJson = readJson(path.join(packageRoot, "package.json"));
    if (packageJson.name !== contract.name) failures.push(`${app.id}: ${contract.root} is ${packageJson.name}, expected ${contract.name}`);
    const lexical = findLexicalPackage(appRoot, workspaceRoot, contract.name);
    if (!lexical) failures.push(`${app.id}: ${contract.name} cannot be located through pnpm node_modules links`);
    else {
      const realpath = fs.realpathSync(lexical);
      if (realpath !== fs.realpathSync(packageRoot)) {
        failures.push(`${app.id}: ${contract.name} resolves to ${realpath}, not declared root ${packageRoot}`);
      }
      contract.resolution = { lexical, realpath };
    }
    if (!Array.isArray(contract.entrypoints) || contract.entrypoints.length === 0) {
      failures.push(`${app.id}: ${contract.name} requires at least one public entrypoint`);
      contract.entrypoints = [];
    }
    const declaredExports = new Set(contract.entrypoints.map((entrypoint) => entrypoint.export));
    const publicExports = typeof packageJson.exports === "string"
      ? ["."]
      : Object.keys(packageJson.exports ?? {}).filter((key) => key === "." || key.startsWith("./"));
    for (const exportName of publicExports) {
      if (exportName.includes("*")) continue;
      if (!declaredExports.has(exportName)) {
        failures.push(`${app.id}: ${contract.name} public export ${exportName} is not classified as an entrypoint`);
      }
    }
    const surfaces = new Set();
    for (const [entryIndex, entrypoint] of contract.entrypoints.entries()) {
      if (!["server", "client", "shared"].includes(entrypoint.surface)) {
        failures.push(`${app.id}: ${contract.name} entrypoint ${entryIndex} has invalid surface`);
        continue;
      }
      surfaces.add(entrypoint.surface);
      let source;
      try {
        source = resolveInside(packageRoot, entrypoint.path, `${app.id}.${contract.name}.entrypoints[${entryIndex}].path`);
      } catch (error) {
        failures.push(error.message);
        continue;
      }
      const scan = scanEntrypoint(source, packageRoot);
      entrypoint.scan = scan;
      if (entrypoint.surface === "server" && scan.signals.includes("client")) {
        failures.push(`${app.id}: server entrypoint ${exportSpecifier(contract.name, entrypoint.export)} reaches a client-only signal`);
      }
      if (entrypoint.surface === "client" && scan.signals.includes("server")) {
        failures.push(`${app.id}: client entrypoint ${exportSpecifier(contract.name, entrypoint.export)} reaches a server-only signal`);
      }
      if (entrypoint.export === "." && scan.signals.includes("server") && scan.signals.includes("client")) {
        failures.push(`${app.id}: root barrel ${contract.name} crosses server/client boundaries`);
      }
    }
    if (contract.classification === "server" && surfaces.has("client")) {
      failures.push(`${app.id}: server package ${contract.name} declares a client entrypoint`);
    }
    if (contract.classification === "client" && surfaces.has("server")) {
      failures.push(`${app.id}: client package ${contract.name} declares a server entrypoint`);
    }
    if (contract.classification === "hybrid" && !(surfaces.has("server") && surfaces.has("client"))) {
      failures.push(`${app.id}: hybrid package ${contract.name} must declare separate server and client entrypoints`);
    }
    contracts.set(contract.name, contract);
  }
  for (const name of directWorkspace) {
    if (!contracts.has(name)) failures.push(`${app.id}: direct workspace dependency ${name} is not classified`);
  }
  for (const name of contracts.keys()) {
    if (!directWorkspace.has(name)) failures.push(`${app.id}: ${name} is classified but is not a direct workspace dependency`);
  }
  return contracts;
}

export async function auditContract(manifestPath, appId) {
  const absoluteManifest = path.resolve(manifestPath);
  const manifest = readJson(absoluteManifest);
  if (manifest.schema !== SCHEMA) throw new ContractError(`manifest schema must be ${SCHEMA}`);
  const manifestRoot = path.dirname(absoluteManifest);
  const repoRoot = findRepoRoot(manifestRoot);
  const workspaceRoot = path.resolve(manifestRoot, manifest.workspaceRoot ?? ".");
  if (!inside(workspaceRoot, repoRoot)) throw new ContractError("workspaceRoot escapes the repository");
  if (!fs.statSync(workspaceRoot, { throwIfNoEntry: false })?.isDirectory()) {
    throw new ContractError(`workspaceRoot does not exist: ${workspaceRoot}`);
  }
  const app = (manifest.apps ?? []).find((candidate) => candidate.id === appId);
  if (!app) throw new ContractError(`app not found in manifest: ${appId}`);
  const appRoot = resolveInside(workspaceRoot, app.root, `${app.id}.root`);
  const failures = [];
  inspectPolicyFiles(app, workspaceRoot, failures);
  const packages = inspectPackages(app, workspaceRoot, appRoot, failures);
  const next = await inspectNextConfig(app, workspaceRoot, appRoot, packages, failures);
  return {
    schema: "nextjs-build-contract-audit.v1",
    app: app.id,
    status: failures.length === 0 ? "passed" : "failed",
    failures,
    externalized: next.detected,
    resolutions: [...packages.values()].map((entry) => ({
      name: entry.name,
      classification: entry.classification,
      lexicalPath: entry.resolution?.lexical,
      realpath: entry.resolution?.realpath,
      entrypoints: entry.entrypoints.map((entrypoint) => ({
        export: entrypoint.export,
        surface: entrypoint.surface,
        signals: entrypoint.scan?.signals ?? [],
      })),
    })),
  };
}

async function main() {
  try {
    const options = parseArgs(process.argv.slice(2));
    const result = await auditContract(options.manifest, options.app);
    if (options.json) console.log(JSON.stringify(result, null, 2));
    else {
      console.log(`${result.status}: ${result.app}`);
      for (const resolution of result.resolutions) {
        console.log(`resolution ${resolution.name}: ${resolution.lexicalPath} -> ${resolution.realpath} (${resolution.classification})`);
      }
      for (const specifier of result.externalized) console.log(`external ${specifier}`);
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
