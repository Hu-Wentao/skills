#!/usr/bin/env node

import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const OVERLAY_MANIFEST_SCHEMA = "nextjs-overlay-contracts.v1";
const DEFAULT_IGNORED_DIRECTORIES = new Set([
  ".git",
  ".next",
  "coverage",
  "dist",
  "node_modules"
]);

export async function auditOverlayContracts({ root = process.cwd(), manifestPath }) {
  const findings = [];
  const projectRoot = path.resolve(root);
  const manifestFile = resolveInside(projectRoot, manifestPath, "manifest");
  const manifest = await readJson(manifestFile, findings);

  if (!manifest) return { contracts: 0, cssFiles: 0, findings };
  if (manifest.schema !== OVERLAY_MANIFEST_SCHEMA) {
    findings.push(`manifest: schema must be ${OVERLAY_MANIFEST_SCHEMA}`);
  }
  if (!Array.isArray(manifest.contracts) || manifest.contracts.length === 0) {
    findings.push("manifest: contracts must be a non-empty array");
    return { contracts: 0, cssFiles: 0, findings };
  }

  const ids = new Set();
  const selectors = new Set();
  for (const [index, contract] of manifest.contracts.entries()) {
    const label = contract?.id ? `contract ${contract.id}` : `contract[${index}]`;
    if (!contract || typeof contract !== "object" || Array.isArray(contract)) {
      findings.push(`${label}: must be an object`);
      continue;
    }
    if (!isNonEmptyString(contract.id)) {
      findings.push(`${label}: id must be a non-empty string`);
    } else if (ids.has(contract.id)) {
      findings.push(`${label}: duplicate id`);
    } else {
      ids.add(contract.id);
    }

    const owner = await auditRequiredFile({
      projectRoot,
      relativePath: contract.owner,
      requiredText: contract.ownerRequiredText,
      label: `${label} owner`,
      findings
    });
    await auditRequiredFile({
      projectRoot,
      relativePath: contract.focusedTest,
      requiredText: contract.testRequiredText,
      label: `${label} focusedTest`,
      findings
    });

    if (owner && isNonEmptyString(contract.symbol) && !owner.includes(contract.symbol)) {
      findings.push(`${label} owner: missing symbol ${JSON.stringify(contract.symbol)}`);
    }

    if (contract.geometry !== undefined) {
      auditGeometry(contract.geometry, label, findings);
    }
    for (const selector of stringArray(contract.forbiddenCssSelectors, `${label} forbiddenCssSelectors`, findings)) {
      selectors.add(selector);
    }
  }

  const cssFiles = [];
  for (const cssRoot of stringArray(manifest.forbiddenCssRoots, "manifest forbiddenCssRoots", findings)) {
    const absoluteRoot = resolveInside(projectRoot, cssRoot, "forbiddenCssRoot");
    await collectFiles(absoluteRoot, (name) => name.endsWith(".css"), cssFiles, findings);
  }
  for (const cssFile of cssFiles) {
    const source = await readFile(cssFile, "utf8");
    for (const selector of selectors) {
      if (source.includes(selector)) {
        findings.push(`${relative(projectRoot, cssFile)}: forbidden overlay selector ${JSON.stringify(selector)}`);
      }
    }
  }

  return {
    contracts: manifest.contracts.length,
    cssFiles: cssFiles.length,
    findings
  };
}

async function auditRequiredFile({ projectRoot, relativePath, requiredText, label, findings }) {
  if (!isNonEmptyString(relativePath)) {
    findings.push(`${label}: path must be a non-empty string`);
    return null;
  }
  const file = resolveInside(projectRoot, relativePath, label);
  let source;
  try {
    source = await readFile(file, "utf8");
  } catch (error) {
    findings.push(`${label}: cannot read ${relativePath}: ${error.message}`);
    return null;
  }
  for (const text of stringArray(requiredText, `${label}RequiredText`, findings)) {
    if (!source.includes(text)) {
      findings.push(`${relativePath}: missing required overlay evidence ${JSON.stringify(text)}`);
    }
  }
  return source;
}

function auditGeometry(geometry, label, findings) {
  if (!geometry || typeof geometry !== "object" || Array.isArray(geometry)) {
    findings.push(`${label} geometry: must be an object`);
    return;
  }
  for (const field of ["overlaySelector", "triggerSelector", "portalSelector", "position", "focus"]) {
    if (!isNonEmptyString(geometry[field])) {
      findings.push(`${label} geometry: ${field} must be a non-empty string`);
    }
  }
  if (!["overlay", "trigger", "overlay-or-trigger", "none"].includes(geometry.focus)) {
    findings.push(`${label} geometry: focus must be overlay, trigger, overlay-or-trigger, or none`);
  }
  if (!Array.isArray(geometry.viewports) || geometry.viewports.length === 0) {
    findings.push(`${label} geometry: viewports must be a non-empty array`);
    return;
  }
  for (const [index, viewport] of geometry.viewports.entries()) {
    if (!Number.isFinite(viewport?.width) || viewport.width <= 0
      || !Number.isFinite(viewport?.height) || viewport.height <= 0) {
      findings.push(`${label} geometry: viewports[${index}] must have positive width and height`);
    }
  }
}

async function readJson(file, findings) {
  try {
    return JSON.parse(await readFile(file, "utf8"));
  } catch (error) {
    findings.push(`manifest: cannot read ${file}: ${error.message}`);
    return null;
  }
}

async function collectFiles(directory, predicate, output, findings) {
  let entries;
  try {
    entries = await readdir(directory, { withFileTypes: true });
  } catch (error) {
    findings.push(`forbiddenCssRoot: cannot read ${directory}: ${error.message}`);
    return;
  }
  for (const entry of entries) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      if (DEFAULT_IGNORED_DIRECTORIES.has(entry.name)) continue;
      await collectFiles(entryPath, predicate, output, findings);
    } else if (entry.isFile() && predicate(entry.name)) {
      output.push(entryPath);
    }
  }
}

function stringArray(value, label, findings) {
  if (!Array.isArray(value) || value.some((item) => !isNonEmptyString(item))) {
    findings.push(`${label}: must be an array of non-empty strings`);
    return [];
  }
  return value;
}

function resolveInside(root, value, label) {
  if (!isNonEmptyString(value)) throw new Error(`${label} path must be a non-empty string`);
  const resolved = path.resolve(root, value);
  const relation = path.relative(root, resolved);
  if (relation === ".." || relation.startsWith(`..${path.sep}`) || path.isAbsolute(relation)) {
    throw new Error(`${label} path escapes project root: ${value}`);
  }
  return resolved;
}

function relative(root, file) {
  return path.relative(root, file).split(path.sep).join("/");
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function parseArgs(argv) {
  const result = { root: process.cwd() };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--manifest") result.manifestPath = argv[++index];
    else if (argument === "--root") result.root = argv[++index];
    else throw new Error(`unknown argument: ${argument}`);
  }
  if (!result.manifestPath) throw new Error("--manifest is required");
  return result;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const report = await auditOverlayContracts(options);
  if (report.findings.length > 0) {
    console.error(`Overlay contract audit failed with ${report.findings.length} finding(s):`);
    for (const finding of report.findings) console.error(`- ${finding}`);
    process.exitCode = 1;
    return;
  }
  console.log(`Overlay contract audit passed: ${report.contracts} contract(s), ${report.cssFiles} CSS file(s).`);
}

const isMain = process.argv[1]
  && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
