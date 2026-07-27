import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  assessOverlayGeometry,
  buildOverlayProbeExpression,
  loadOverlayProbeContract
} from "../overlay-geometry-probe.mjs";

test("accepts viewport-safe portal geometry and expected focus", () => {
  const report = assessOverlayGeometry({
    viewport: { width: 390, height: 568 },
    viewportMargin: 8,
    overlayRect: { top: 320, right: 382, bottom: 520, left: 240 },
    portalMatches: true,
    position: "fixed",
    expectedPosition: "fixed",
    clippingAncestors: [],
    expectedFocus: "overlay",
    focusWithinOverlay: true,
    focusOnTrigger: false
  });

  assert.equal(report.ok, true);
  assert.deepEqual(report.failures, []);
});

test("reports viewport, portal, clipping, position, and focus failures", () => {
  const report = assessOverlayGeometry({
    viewport: { width: 390, height: 568 },
    viewportMargin: 8,
    overlayRect: { top: 500, right: 420, bottom: 620, left: 280 },
    portalMatches: false,
    position: "absolute",
    expectedPosition: "fixed",
    clippingAncestors: [{ clipsOverlay: true }],
    expectedFocus: "trigger",
    focusWithinOverlay: false,
    focusOnTrigger: false
  });

  assert.equal(report.ok, false);
  assert.deepEqual(report.failures, [
    "overlay-outside-viewport",
    "unexpected-portal-target",
    "unexpected-position",
    "clipped-by-ancestor",
    "focus-outside-overlay-contract"
  ]);
});

test("loads project geometry by contract and emits a self-contained expression", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "overlay-probe-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  await writeFile(path.join(root, "overlay.json"), JSON.stringify({
    contracts: [{
      id: "actions",
      geometry: {
        overlaySelector: '[role="menu"]',
        triggerSelector: "#trigger",
        portalSelector: "body",
        position: "fixed",
        focus: "overlay",
        viewportMargin: 8,
        viewports: [{ width: 390, height: 568 }]
      }
    }]
  }));

  const contract = await loadOverlayProbeContract({
    root,
    manifestPath: "overlay.json",
    contractId: "actions"
  });
  const expression = buildOverlayProbeExpression(contract.options);

  assert.deepEqual(contract.viewports, [{ width: 390, height: 568 }]);
  assert.match(expression, /document\.querySelector/);
  assert.match(expression, /\[role=\\?"menu\\?"\]/);
});
