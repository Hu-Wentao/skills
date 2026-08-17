import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { auditContract } from "../audit-next-build-contract.mjs";
import { auditStandaloneRoot, formatFailures } from "../audit-standalone-closure.mjs";
import { classifyBuildExit, loadProbeContract, runProbe } from "../run-build-memory-probe.mjs";
import { smokeStandalone } from "../smoke-next-standalone.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = path.resolve(HERE, "../fixtures/build-boundaries");

function setupFixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "next-build-contract-"));
  fs.mkdirSync(path.join(root, ".git"));
  fs.cpSync(FIXTURE, root, { recursive: true });
  for (const name of ["server", "hybrid"]) {
    const link = path.join(root, "app/node_modules/@fixture", name);
    fs.mkdirSync(path.dirname(link), { recursive: true });
    fs.symlinkSync(path.relative(path.dirname(link), path.join(root, "packages", name)), link, "dir");
  }
  return root;
}

function manifestFor(root) {
  return {
    schema: "nextjs-build-contracts.v1",
    workspaceRoot: ".",
    applicationRoots: ["app"],
    apps: [{
      id: "fixture",
      root: "app",
      packageJson: "app/package.json",
      nextConfig: "app/next.config.mjs",
      policyFiles: ["app/next.config.mjs"],
      workspacePackages: [
        {
          name: "@fixture/server",
          root: "packages/server",
          classification: "server",
          entrypoints: [{ export: ".", path: "src/index.js", surface: "server" }],
        },
        {
          name: "@fixture/hybrid",
          root: "packages/hybrid",
          classification: "hybrid",
          entrypoints: [
            { export: "./server", path: "src/server.js", surface: "server" },
            { export: "./client", path: "src/client.js", surface: "client" },
          ],
        },
      ],
      allowedExternalPackages: [{ specifier: "@fixture/server" }],
      standalone: {
        root: "standalone",
        entrypoints: ["server.js"],
        traceRoots: ["traces"],
      },
      memory: { containerLimitMiB: 640, baselineHeapLimitMiB: 512, heapLimitMiB: 512, coldPath: "app/.next" },
      runtime: {
        command: ["node", "server.js"],
        readyPath: "/ready",
        readyStatuses: [200],
        routes: [{ path: "/ready", statuses: [200] }, { path: "/missing", statuses: [404] }],
      },
    }],
  };
}

function writeManifest(root, manifest = manifestFor(root)) {
  const pathname = path.join(root, "build-contract.json");
  fs.writeFileSync(pathname, `${JSON.stringify(manifest, null, 2)}\n`);
  return pathname;
}

test("audits pnpm symlink realpaths and separate server-only and next/navigation entrypoints", async (t) => {
  const root = setupFixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const result = await auditContract(writeManifest(root), "fixture");
  assert.equal(result.status, "passed", result.failures.join("\n"));
  const server = result.resolutions.find((entry) => entry.name === "@fixture/server");
  assert.notEqual(server.lexicalPath, server.realpath);
  assert.equal(server.classification, "server");
});

test("rejects whole-package externalization of a hybrid package", async (t) => {
  const root = setupFixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const configPath = path.join(root, "app/next.config.mjs");
  fs.writeFileSync(configPath, fs.readFileSync(configPath, "utf8").replace(
    'new Set(["@fixture/server"])',
    'new Set(["@fixture/server", "@fixture/hybrid"])',
  ));
  const manifest = manifestFor(root);
  manifest.apps[0].allowedExternalPackages.push({ specifier: "@fixture/hybrid" });
  const result = await auditContract(writeManifest(root, manifest), "fixture");
  assert.equal(result.status, "failed", JSON.stringify(result, null, 2));
  assert.ok(result.failures.some((failure) => failure.includes("whole-package externalization is forbidden for hybrid package")));
});

test("rejects a root barrel that crosses server-only and next/navigation boundaries", async (t) => {
  const root = setupFixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const packagePath = path.join(root, "packages/hybrid/package.json");
  const packageJson = JSON.parse(fs.readFileSync(packagePath, "utf8"));
  packageJson.exports["."] = "./src/index.js";
  fs.writeFileSync(packagePath, `${JSON.stringify(packageJson, null, 2)}\n`);
  const manifest = manifestFor(root);
  manifest.apps[0].workspacePackages[1].entrypoints.unshift({ export: ".", path: "src/index.js", surface: "shared" });
  const result = await auditContract(writeManifest(root, manifest), "fixture");
  assert.equal(result.status, "failed", JSON.stringify(result, null, 2));
  assert.ok(result.failures.some((failure) => failure.includes("root barrel @fixture/hybrid crosses server/client boundaries")));
});

test("rejects unevidenced symlink and optimizePackageImports workarounds", async (t) => {
  const root = setupFixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const configPath = path.join(root, "app/next.config.mjs");
  fs.appendFileSync(configPath, "\n// fixture policy\nconst forbidden = { resolve: { symlinks: false }, optimizePackageImports: ['x'] };\n");
  const result = await auditContract(writeManifest(root), "fixture");
  assert.equal(result.status, "failed");
  assert.ok(result.failures.some((failure) => failure.includes("resolveSymlinksFalse requires measured evidence")));
  assert.ok(result.failures.some((failure) => failure.includes("optimizePackageImports requires measured evidence")));
});

test("rejects runtime source imports from a sibling application", async (t) => {
  const root = setupFixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, "other-app"));
  fs.writeFileSync(path.join(root, "other-app/package.json"), '{"name":"@fixture/other-app"}\n');
  fs.mkdirSync(path.join(root, "app/lib"));
  fs.writeFileSync(
    path.join(root, "app/lib/runtime-version.js"),
    'import siblingVersion from "../../other-app/package.json";\nexport default siblingVersion;\n',
  );
  const manifest = manifestFor(root);
  manifest.applicationRoots.push("other-app");
  const result = await auditContract(writeManifest(root, manifest), "fixture");
  assert.equal(result.status, "failed", JSON.stringify(result, null, 2));
  assert.equal(result.runtimeBoundary.mode, "declared");
  assert.ok(result.failures.some((failure) => failure.includes("runtime application boundary violation")));
});

test("infers package-bearing sibling applications for v1 migration", async (t) => {
  const root = setupFixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, "other-app"));
  fs.writeFileSync(path.join(root, "other-app/package.json"), '{"name":"@fixture/other-app"}\n');
  fs.mkdirSync(path.join(root, "app/lib"));
  fs.writeFileSync(
    path.join(root, "app/lib/runtime-version.js"),
    'export { default } from "@fixture/other-app/package.json";\n',
  );
  const manifest = manifestFor(root);
  delete manifest.applicationRoots;
  const result = await auditContract(writeManifest(root, manifest), "fixture");
  assert.equal(result.status, "failed", JSON.stringify(result, null, 2));
  assert.equal(result.runtimeBoundary.mode, "inferred-siblings");
  assert.ok(result.runtimeBoundary.applicationRoots.includes("other-app"));
});

test("standalone closure rejects a production dependency missing from the artifact", (t) => {
  const root = setupFixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const traces = path.join(root, "standalone/traces");
  fs.mkdirSync(traces);
  fs.renameSync(path.join(root, "standalone/missing-dependency.cjs"), path.join(traces, "server.js.nft.json"));
  const result = auditStandaloneRoot(path.join(root, "standalone"), {
    entrypoints: ["server.js"],
    traceRoots: ["traces"],
  });
  assert.equal(result.status, "failed");
  assert.equal(result.failureCount, 1);
  assert.equal(result.omittedFailures, 0);
  assert.ok(result.failures.some((failure) => failure.includes("traced dependency is missing")));
  assert.deepEqual(formatFailures(["one", "two", "three"], 2), [
    "error: one",
    "error: two",
    "error: 1 additional failures omitted",
  ]);
});

test("standalone closure bounds deterministic failure output", (t) => {
  const root = setupFixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const traces = path.join(root, "standalone/traces");
  fs.mkdirSync(traces);
  fs.writeFileSync(path.join(traces, "server.js.nft.json"), JSON.stringify({
    version: 1,
    files: Array.from({ length: 80 }, (_, index) => `../missing-${index}.js`),
  }));
  const result = auditStandaloneRoot(path.join(root, "standalone"), {
    entrypoints: ["server.js"],
    traceRoots: ["traces"],
  });
  assert.equal(result.status, "failed");
  assert.equal(result.failureCount, 80);
  assert.equal(result.failures.length, 50);
  assert.equal(result.omittedFailures, 30);
  assert.equal(formatFailures(result.failures, 50, result.failureCount).at(-1), "error: 30 additional failures omitted");
});

test("standalone closure rejects copied and traced sibling applications", (t) => {
  const root = setupFixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const sibling = path.join(root, "standalone/other-app");
  fs.mkdirSync(sibling);
  fs.writeFileSync(path.join(sibling, "package.json"), '{"name":"@fixture/other-app"}\n');
  const traces = path.join(root, "standalone/traces");
  fs.mkdirSync(traces);
  fs.writeFileSync(path.join(traces, "server.js.nft.json"), JSON.stringify({
    version: 1,
    files: ["../server.js", "../other-app/package.json"],
  }));
  const result = auditStandaloneRoot(path.join(root, "standalone"), {
    entrypoints: ["server.js"],
    traceRoots: ["traces"],
    forbiddenApplicationRoots: ["other-app"],
  });
  assert.equal(result.status, "failed");
  assert.ok(result.failures.some((failure) => failure.includes("contains sibling application root")));
  assert.ok(result.failures.some((failure) => failure.includes("traces sibling application")));
});

test("runtime smoke starts the isolated standalone tree and checks declared routes", async (t) => {
  const root = setupFixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const traces = path.join(root, "standalone/traces");
  fs.mkdirSync(traces);
  fs.writeFileSync(path.join(traces, "server.js.nft.json"), '{"version":1,"files":["../server.js"]}\n');
  fs.rmSync(path.join(root, "standalone/missing-dependency.cjs"));
  const app = manifestFor(root).apps[0];
  const result = await smokeStandalone({ app, standaloneRoot: path.join(root, "standalone") });
  assert.equal(result.status, "passed", JSON.stringify(result, null, 2));
});

test("runtime smoke enforces the project-declared route deadline", async (t) => {
  const root = setupFixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const traces = path.join(root, "standalone/traces");
  fs.mkdirSync(traces);
  fs.writeFileSync(path.join(traces, "server.js.nft.json"), '{"version":1,"files":["../server.js"]}\n');
  fs.rmSync(path.join(root, "standalone/missing-dependency.cjs"));
  fs.writeFileSync(path.join(root, "standalone/server.js"), `
    import http from "node:http";
    http.createServer((request, response) => {
      const finish = () => { response.statusCode = 200; response.end("fixture"); };
      if (request.url === "/slow") setTimeout(finish, 100);
      else finish();
    }).listen(Number(process.env.PORT), process.env.HOSTNAME);
  `);
  const app = manifestFor(root).apps[0];
  app.runtime.routeTimeoutMs = 25;
  app.runtime.routes = [{ path: "/slow", statuses: [200] }];
  const result = await smokeStandalone({ app, standaloneRoot: path.join(root, "standalone") });
  assert.equal(result.status, "failed", JSON.stringify(result, null, 2));
  assert.equal(result.reason, "route_failed");
  assert.equal(result.routes[0].timeoutMs, 25);
  assert.equal(result.routes[0].status, null);
  assert.match(result.routes[0].error, /timeout|aborted/iu);
});

test("build exit classification distinguishes cgroup OOM, V8 heap OOM, and bare 137", () => {
  assert.equal(classifyBuildExit({ code: 137, signal: null, output: "", oomDelta: 1, oomKillDelta: 1 }), "cgroup_oom");
  assert.equal(classifyBuildExit({ code: 134, signal: null, output: "FATAL ERROR: Reached heap limit", oomDelta: 0, oomKillDelta: 0 }), "v8_heap_oom");
  assert.equal(classifyBuildExit({ code: 137, signal: null, output: "", oomDelta: 0, oomKillDelta: 0 }), "process_exit_137");
  assert.equal(classifyBuildExit({ code: null, signal: "SIGKILL", output: "", oomDelta: 0, oomKillDelta: 0 }), "external_sigkill");
});

test("memory probe accepts an explicit workspace root in a Git-free container context", (t) => {
  const root = setupFixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.rmSync(path.join(root, ".git"), { recursive: true });
  const manifestPath = writeManifest(root);
  const contract = loadProbeContract(manifestPath, "fixture", root);
  assert.equal(contract.workspaceRoot, root);
  assert.throws(
    () => loadProbeContract(manifestPath, "fixture", path.dirname(root)),
    /manifest declares/,
  );
});

test("memory probe requires the exact cgroup v2 limit and persists exit evidence", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "next-build-memory-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const cgroupRoot = path.join(root, "cgroup");
  fs.mkdirSync(cgroupRoot);
  fs.writeFileSync(path.join(cgroupRoot, "cgroup.controllers"), "memory cpu\n");
  fs.writeFileSync(path.join(cgroupRoot, "memory.max"), String(640 * 1024 * 1024));
  fs.writeFileSync(path.join(cgroupRoot, "memory.current"), String(32 * 1024 * 1024));
  fs.writeFileSync(path.join(cgroupRoot, "memory.events"), "oom 0\noom_kill 0\n");
  const evidencePath = path.join(root, "evidence/result.json");
  const result = await runProbe({
    app: { id: "fixture", memory: { containerLimitMiB: 640, heapLimitMiB: 512 } },
    workspaceRoot: root,
    coldPath: path.join(root, "cold-output"),
    command: [process.execPath, "-e", "setTimeout(() => {}, 150)"],
    evidencePath,
    cgroupRoot,
  });
  assert.equal(result.status, "passed");
  assert.equal(result.reason, "success");
  assert.equal(result.containerLimitMiB, 640);
  assert.deepEqual(JSON.parse(fs.readFileSync(evidencePath, "utf8")), result);
  fs.writeFileSync(path.join(cgroupRoot, "memory.max"), "max\n");
  await assert.rejects(
    runProbe({
      app: { id: "fixture", memory: { containerLimitMiB: 640, heapLimitMiB: 512 } },
      workspaceRoot: root,
      coldPath: path.join(root, "another-cold-output"),
      command: [process.execPath, "-e", "process.exit(0)"],
      evidencePath,
      cgroupRoot,
    }),
    /not a finite numeric cgroup value/,
  );
});
