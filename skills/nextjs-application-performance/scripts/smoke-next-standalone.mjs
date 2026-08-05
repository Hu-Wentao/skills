#!/usr/bin/env node

import { spawn } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { auditStandaloneRoot, loadStandaloneContract } from "./audit-standalone-closure.mjs";

const OUTPUT_LIMIT = 64 * 1024;

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

async function reservePort() {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close((error) => error ? reject(error) : resolve(address.port));
    });
  });
}

function appendBounded(existing, chunk) {
  const next = `${existing}${chunk}`;
  return next.length <= OUTPUT_LIMIT ? next : next.slice(-OUTPUT_LIMIT);
}

async function stopChild(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise((resolve) => child.once("exit", resolve)),
    new Promise((resolve) => setTimeout(resolve, 5000)),
  ]);
  if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL");
}

async function fetchStatus(url) {
  const response = await fetch(url, { redirect: "manual", signal: AbortSignal.timeout(5000) });
  await response.body?.cancel();
  return response.status;
}

export async function smokeStandalone({ app, standaloneRoot }) {
  const closure = auditStandaloneRoot(standaloneRoot, app.standalone.allowedMissing ?? []);
  if (closure.status !== "passed") {
    return { schema: "nextjs-standalone-smoke.v1", app: app.id, status: "failed", reason: "closure_failed", closure };
  }
  const runtime = app.runtime;
  if (!runtime || !Array.isArray(runtime.command) || runtime.command.length === 0) {
    throw new Error(`${app.id}.runtime.command must be a non-empty array`);
  }
  if (typeof runtime.readyPath !== "string" || !runtime.readyPath.startsWith("/")) {
    throw new Error(`${app.id}.runtime.readyPath must start with /`);
  }
  if (!Array.isArray(runtime.routes) || runtime.routes.length === 0) {
    throw new Error(`${app.id}.runtime.routes must be non-empty`);
  }
  const port = runtime.port ?? await reservePort();
  const origin = `http://127.0.0.1:${port}`;
  let output = "";
  const child = spawn(runtime.command[0], runtime.command.slice(1), {
    cwd: standaloneRoot,
    env: {
      ...process.env,
      ...runtime.env,
      HOSTNAME: "127.0.0.1",
      PORT: String(port),
      NODE_ENV: "production",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", (chunk) => { output = appendBounded(output, chunk.toString("utf8")); });
  child.stderr.on("data", (chunk) => { output = appendBounded(output, chunk.toString("utf8")); });
  let earlyExit = null;
  child.once("exit", (code, signal) => { earlyExit = { code, signal }; });
  const timeoutMs = runtime.startupTimeoutMs ?? 30000;
  const deadline = Date.now() + timeoutMs;
  let readyStatus = null;
  try {
    while (Date.now() < deadline && !earlyExit) {
      try {
        readyStatus = await fetchStatus(`${origin}${runtime.readyPath}`);
        if ((runtime.readyStatuses ?? [200]).includes(readyStatus)) break;
      } catch {
        // Server startup is polled until the configured deadline.
      }
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    if (earlyExit) {
      return { schema: "nextjs-standalone-smoke.v1", app: app.id, status: "failed", reason: "runtime_exit", earlyExit, output };
    }
    if (!(runtime.readyStatuses ?? [200]).includes(readyStatus)) {
      return { schema: "nextjs-standalone-smoke.v1", app: app.id, status: "failed", reason: "startup_timeout", readyStatus, output };
    }
    const routes = [];
    for (const route of runtime.routes) {
      if (typeof route.path !== "string" || !route.path.startsWith("/") || !Array.isArray(route.statuses)) {
        throw new Error(`${app.id}.runtime.routes entries require path and statuses`);
      }
      let status;
      try {
        status = await fetchStatus(`${origin}${route.path}`);
      } catch (error) {
        routes.push({ path: route.path, status: null, passed: false, error: error.message });
        continue;
      }
      routes.push({ path: route.path, status, passed: route.statuses.includes(status) });
    }
    return {
      schema: "nextjs-standalone-smoke.v1",
      app: app.id,
      status: routes.every((route) => route.passed) ? "passed" : "failed",
      reason: routes.every((route) => route.passed) ? "success" : "route_failed",
      ready: { path: runtime.readyPath, status: readyStatus },
      routes,
      closure: { scannedFiles: closure.scannedFiles },
      output,
    };
  } finally {
    await stopChild(child);
  }
}

async function main() {
  try {
    const options = parseArgs(process.argv.slice(2));
    const contract = loadStandaloneContract(options.manifest, options.app);
    const result = await smokeStandalone(contract);
    if (options.json) console.log(JSON.stringify(result, null, 2));
    else {
      console.log(`${result.status}: ${result.app} (${result.reason})`);
      for (const route of result.routes ?? []) console.log(`${route.passed ? "ok" : "error"} ${route.path}: ${route.status}`);
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
