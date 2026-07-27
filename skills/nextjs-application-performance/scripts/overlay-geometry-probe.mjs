#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

export function assessOverlayGeometry(snapshot) {
  const margin = snapshot.viewportMargin ?? 0;
  const failures = [];
  const rect = snapshot.overlayRect;
  const viewport = snapshot.viewport;
  const fullyInsideViewport = Boolean(rect && viewport
    && rect.left >= margin
    && rect.top >= margin
    && rect.right <= viewport.width - margin
    && rect.bottom <= viewport.height - margin);

  if (!fullyInsideViewport) failures.push("overlay-outside-viewport");
  if (!snapshot.portalMatches) failures.push("unexpected-portal-target");
  if (snapshot.position !== snapshot.expectedPosition) failures.push("unexpected-position");
  if (snapshot.clippingAncestors?.some((ancestor) => ancestor.clipsOverlay)) {
    failures.push("clipped-by-ancestor");
  }

  const focus = snapshot.expectedFocus ?? "none";
  const focusMatches = focus === "none"
    || (focus === "overlay" && snapshot.focusWithinOverlay)
    || (focus === "trigger" && snapshot.focusOnTrigger)
    || (focus === "overlay-or-trigger" && (snapshot.focusWithinOverlay || snapshot.focusOnTrigger));
  if (!focusMatches) failures.push("focus-outside-overlay-contract");

  return {
    ok: failures.length === 0,
    failures,
    fullyInsideViewport,
    focusMatches
  };
}

// This function is deliberately self-contained so its source can be passed
// directly to a connected browser's page-evaluation API.
export function inspectOverlayGeometry(options) {
  const overlay = document.querySelector(options.overlaySelector);
  const trigger = document.querySelector(options.triggerSelector);
  if (!overlay || !trigger) {
    return {
      ok: false,
      failures: [
        ...(!overlay ? ["overlay-not-found"] : []),
        ...(!trigger ? ["trigger-not-found"] : [])
      ],
      selectors: {
        overlay: options.overlaySelector,
        trigger: options.triggerSelector
      }
    };
  }

  const toRect = (rect) => ({
    top: rect.top,
    right: rect.right,
    bottom: rect.bottom,
    left: rect.left,
    width: rect.width,
    height: rect.height
  });
  const overlayRect = toRect(overlay.getBoundingClientRect());
  const triggerRect = toRect(trigger.getBoundingClientRect());
  const clippingAncestors = [];
  let ancestor = overlay.parentElement;
  while (ancestor) {
    const style = window.getComputedStyle(ancestor);
    const clipsX = !["visible", "unset", "initial"].includes(style.overflowX);
    const clipsY = !["visible", "unset", "initial"].includes(style.overflowY);
    if (clipsX || clipsY) {
      const ancestorRect = toRect(ancestor.getBoundingClientRect());
      clippingAncestors.push({
        element: `${ancestor.tagName.toLowerCase()}${ancestor.id ? `#${ancestor.id}` : ""}`,
        overflowX: style.overflowX,
        overflowY: style.overflowY,
        rect: ancestorRect,
        clipsOverlay: (clipsX && (overlayRect.left < ancestorRect.left || overlayRect.right > ancestorRect.right))
          || (clipsY && (overlayRect.top < ancestorRect.top || overlayRect.bottom > ancestorRect.bottom))
      });
    }
    ancestor = ancestor.parentElement;
  }

  const portalTarget = document.querySelector(options.portalSelector);
  const position = window.getComputedStyle(overlay).position;
  const activeElement = document.activeElement;
  const viewportMargin = options.viewportMargin ?? 0;
  const fullyInsideViewport = overlayRect.left >= viewportMargin
    && overlayRect.top >= viewportMargin
    && overlayRect.right <= window.innerWidth - viewportMargin
    && overlayRect.bottom <= window.innerHeight - viewportMargin;
  const portalMatches = overlay.parentElement === portalTarget;
  const focusWithinOverlay = Boolean(activeElement && overlay.contains(activeElement));
  const focusOnTrigger = activeElement === trigger;
  const expectedFocus = options.focus ?? "none";
  const focusMatches = expectedFocus === "none"
    || (expectedFocus === "overlay" && focusWithinOverlay)
    || (expectedFocus === "trigger" && focusOnTrigger)
    || (expectedFocus === "overlay-or-trigger" && (focusWithinOverlay || focusOnTrigger));
  const failures = [];
  if (!fullyInsideViewport) failures.push("overlay-outside-viewport");
  if (!portalMatches) failures.push("unexpected-portal-target");
  if (position !== options.position) failures.push("unexpected-position");
  if (clippingAncestors.some((item) => item.clipsOverlay)) failures.push("clipped-by-ancestor");
  if (!focusMatches) failures.push("focus-outside-overlay-contract");

  return {
    ok: failures.length === 0,
    failures,
    viewport: { width: window.innerWidth, height: window.innerHeight, margin: viewportMargin },
    overlay: { selector: options.overlaySelector, rect: overlayRect, position },
    trigger: { selector: options.triggerSelector, rect: triggerRect },
    portal: { selector: options.portalSelector, directParentMatches: portalMatches },
    focus: { expected: expectedFocus, withinOverlay: focusWithinOverlay, onTrigger: focusOnTrigger },
    clippingAncestors
  };
}

export function buildOverlayProbeExpression(options) {
  return `(${inspectOverlayGeometry.toString()})(${JSON.stringify(options)})`;
}

export async function loadOverlayProbeContract({ root = process.cwd(), manifestPath, contractId }) {
  const projectRoot = path.resolve(root);
  const manifestFile = resolveInside(projectRoot, manifestPath);
  const manifest = JSON.parse(await readFile(manifestFile, "utf8"));
  const contract = manifest.contracts?.find((candidate) => candidate.id === contractId);
  if (!contract) throw new Error(`overlay contract not found: ${contractId}`);
  if (!contract.geometry) throw new Error(`overlay contract has no geometry config: ${contractId}`);
  return {
    options: {
      overlaySelector: contract.geometry.overlaySelector,
      triggerSelector: contract.geometry.triggerSelector,
      portalSelector: contract.geometry.portalSelector,
      position: contract.geometry.position,
      focus: contract.geometry.focus,
      viewportMargin: contract.geometry.viewportMargin ?? 0
    },
    viewports: contract.geometry.viewports
  };
}

function resolveInside(root, value) {
  if (typeof value !== "string" || value.trim() === "") throw new Error("--manifest is required");
  const resolved = path.resolve(root, value);
  const relation = path.relative(root, resolved);
  if (relation === ".." || relation.startsWith(`..${path.sep}`) || path.isAbsolute(relation)) {
    throw new Error(`manifest path escapes project root: ${value}`);
  }
  return resolved;
}

function parseArgs(argv) {
  const result = { root: process.cwd(), format: "expression" };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--manifest") result.manifestPath = argv[++index];
    else if (argument === "--contract") result.contractId = argv[++index];
    else if (argument === "--root") result.root = argv[++index];
    else if (argument === "--describe") result.format = "describe";
    else throw new Error(`unknown argument: ${argument}`);
  }
  if (!result.manifestPath) throw new Error("--manifest is required");
  if (!result.contractId) throw new Error("--contract is required");
  return result;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const contract = await loadOverlayProbeContract(args);
  if (args.format === "describe") {
    console.log(JSON.stringify(contract, null, 2));
    return;
  }
  console.log(buildOverlayProbeExpression(contract.options));
}

const isMain = process.argv[1]
  && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
