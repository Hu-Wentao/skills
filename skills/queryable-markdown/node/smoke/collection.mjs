// Compares `scan` (and a few usage/error paths) of the Node port against Python mdq.py as parsed JSON.
import { spawnSync } from "node:child_process";
import { isDeepStrictEqual } from "node:util";
import { fileURLToPath } from "node:url";

const main = fileURLToPath(new URL("../src/main.mjs", import.meta.url));
const py = fileURLToPath(new URL("../../scripts/mdq.py", import.meta.url));
const relay = process.env.RELAY_DOCS ?? "/home/claude/friday-relay/docs";

const cases = [
  ["scan", `${relay}/defects`, "--output", "json"],
  ["scan", `${relay}/plans`, "--output", "json"],
  ["scan", `${relay}/defects`, "--glob", "*.md", "--output", "json"],
  ["scan", `${relay}`, "--glob", "plans/**/*.md", "--glob", "defects/*.md", "--output", "json"],
  ["scan", `${relay}/defects`, "--text", "a", "--limit", "3", "--output", "json"],
  ["scan", `${relay}/defects`, "--glob", "../x", "--output", "json"],
  ["scan", `${relay}/defects`, "--require-contract", "--output", "json"],
  ["scan", "/nonexistent-dir", "--output", "json"],
];

let failures = 0;
const run = (cmd, args) => spawnSync(cmd, args, { encoding: "utf-8", maxBuffer: 1 << 30 });
for (const args of cases) {
  const a = run("node", [main, ...args]);
  const b = run("uv", ["run", py, ...args]);
  let ja, jb;
  try { ja = JSON.parse(a.stdout); jb = JSON.parse(b.stdout); } catch (e) { ja = a.stdout; jb = b.stdout; }
  const same = isDeepStrictEqual(ja, jb) && a.status === b.status;
  if (!same) failures++;
  console.log(`${same ? "OK  " : "DIFF"} exit node=${a.status} py=${b.status}  ${args.join(" ")}`);
  if (!same && typeof ja === "object" && typeof jb === "object") {
    for (const key of new Set([...Object.keys(ja), ...Object.keys(jb)])) {
      if (!isDeepStrictEqual(ja[key], jb[key])) console.log(`     differs: ${key}`);
    }
  }
}
process.exitCode = failures ? 1 : 0;
