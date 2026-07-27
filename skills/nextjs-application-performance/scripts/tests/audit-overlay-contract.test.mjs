import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  auditOverlayContracts,
  OVERLAY_MANIFEST_SCHEMA
} from "../audit-overlay-contract.mjs";

test("accepts a complete project-owned overlay contract", async (context) => {
  const root = await fixture(context);
  await writeFile(path.join(root, "owner.tsx"), 'createPortal(menu, document.body)\nrole="menu"\nposition: "fixed"\n');
  await writeFile(path.join(root, "owner.test.tsx"), "expect(menu.parentElement).toBe(document.body)\n");
  await mkdir(path.join(root, "app", ".next"));
  await writeFile(path.join(root, "app", ".next", "compiled.css"), ".action-menu-content { display: grid; }\n");

  const report = await auditOverlayContracts({ root, manifestPath: "overlay.json" });

  assert.deepEqual(report.findings, []);
  assert.equal(report.contracts, 1);
  assert.equal(report.cssFiles, 1);
});

test("reports missing source evidence and project CSS overrides", async (context) => {
  const root = await fixture(context);
  await writeFile(path.join(root, "owner.tsx"), 'role="menu"\n');
  await writeFile(path.join(root, "owner.test.tsx"), "render(menu)\n");
  await writeFile(path.join(root, "app", "styles.css"), ".action-menu-content { overflow: visible; }\n");

  const report = await auditOverlayContracts({ root, manifestPath: "overlay.json" });

  assert.ok(report.findings.some((finding) => finding.includes("createPortal(menu, document.body)")));
  assert.ok(report.findings.some((finding) => finding.includes("parentElement")));
  assert.ok(report.findings.some((finding) => finding.includes("forbidden overlay selector")));
});

async function fixture(context) {
  const root = await mkdtemp(path.join(os.tmpdir(), "overlay-contract-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, "app"));
  await writeFile(path.join(root, "app", "styles.css"), "body { margin: 0; }\n");
  await writeFile(path.join(root, "overlay.json"), JSON.stringify({
    schema: OVERLAY_MANIFEST_SCHEMA,
    forbiddenCssRoots: ["app"],
    contracts: [{
      id: "actions",
      symbol: "menu",
      owner: "owner.tsx",
      focusedTest: "owner.test.tsx",
      ownerRequiredText: [
        "createPortal(menu, document.body)",
        'role="menu"',
        'position: "fixed"'
      ],
      testRequiredText: [
        "expect(menu.parentElement).toBe(document.body)"
      ],
      forbiddenCssSelectors: [".action-menu-content"],
      geometry: {
        overlaySelector: '[role="menu"]',
        triggerSelector: '[aria-label="Actions"]',
        portalSelector: "body",
        position: "fixed",
        focus: "overlay",
        viewportMargin: 8,
        viewports: [{ width: 390, height: 568 }]
      }
    }]
  }));
  return root;
}
