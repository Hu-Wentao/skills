#!/usr/bin/env node
// Parity harness: runs the Python mdq.py and the Node port with the same arguments and compares parsed JSON.
// Usage: node parity/compare.mjs [--py <mdq.py>] [--node <src/main.mjs>] [--cwd <dir>] -- <mdq args...>
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const sep = argv.indexOf("--");
const opts = argv.slice(0, sep < 0 ? argv.length : sep);
const mdqArgs = sep < 0 ? [] : argv.slice(sep + 1);
const get = (name, dflt) => { const i = opts.indexOf(name); return i >= 0 ? opts[i + 1] : dflt; };
const py = get("--py", resolve(here, "../../scripts/mdq.py"));
const nodeMain = get("--node", resolve(here, "../src/main.mjs"));
const cwd = get("--cwd", process.cwd());

function run(cmd, args) {
  const r = spawnSync(cmd, args, { cwd, encoding: "utf-8", maxBuffer: 1 << 30 });
  let json = null;
  try { json = JSON.parse(r.stdout); } catch { /* keep null */ }
  return { code: r.status, json, stdout: r.stdout, stderr: r.stderr };
}
const a = run("uv", ["run", py, ...mdqArgs]);
const b = run("node", [nodeMain, ...mdqArgs]);
console.log(`exit python=${a.code} node=${b.code}`);
if (a.json === null || b.json === null) {
  console.log("non-JSON output", a.json === null ? "python" : "", b.json === null ? "node" : "");
  console.log("python stdout head:", a.stdout.slice(0, 300));
  console.log("node stdout head:", b.stdout.slice(0, 300), "\nnode stderr:", b.stderr.slice(0, 600));
  process.exit(2);
}

const stable = (v) => JSON.stringify(v, (_, x) => (x && typeof x === "object" && !Array.isArray(x)
  ? Object.fromEntries(Object.keys(x).sort().map((k) => [k, x[k]])) : x));
let diffs = 0;
const report = [];
function walk(path, x, y) {
  if (stable(x) === stable(y)) return;
  if (Array.isArray(x) && Array.isArray(y) && x.length === y.length) {
    x.forEach((item, i) => walk(`${path}[${i}]`, item, y[i]));
    return;
  }
  if (x && y && typeof x === "object" && typeof y === "object" && !Array.isArray(x) && !Array.isArray(y)) {
    for (const k of new Set([...Object.keys(x), ...Object.keys(y)])) walk(`${path}.${k}`, x[k], y[k]);
    return;
  }
  diffs++;
  if (report.length < Number(get("--max", 25))) report.push(`${path}\n  py:   ${stable(x)?.slice(0, 200)}\n  node: ${stable(y)?.slice(0, 200)}`);
}
walk("$", a.json, b.json);
console.log(diffs === 0 ? "PARITY OK" : `DIFFS: ${diffs}`);
for (const line of report) console.log(line);
process.exit(diffs === 0 ? 0 : 1);
