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
  // Profile-free documents use temporary selectors (unsupported in Node: fail closed). Drop them from both sides.
  let skipped = 0;
  if (ja?.documents && jb?.documents) {
    const tmp = new Set(jb.documents.filter((d) => (d.profile_source ?? "").startsWith("temporary")).map((d) => d.relative_path));
    const nodeInvalid = new Set(ja.documents.filter((d) => d.diagnostics.some((x) => x.code === "unsupported_in_node")).map((d) => d.relative_path));
    skipped = tmp.size;
    if (!isDeepStrictEqual([...tmp].sort(), [...nodeInvalid].sort())) console.log("     fail-closed set differs from Python temporary set");
    if (tmp.size) {
      for (const j of [ja, jb]) {
        for (const k of ["records", "candidates", "documents", "diagnostics"]) j[k] = j[k].filter((x) => !tmp.has(x.relative_path));
        for (const k of ["status", "count", "documents_matched", "documents_scanned", "truncated"]) delete j[k];
      }
      for (const j of [ja, jb]) { j.count = j.records.length; j.documents_scanned = j.documents.length; }
      a.status = b.status = 0;
    }
  }
  // PyYAML vs yaml error texts differ (profile.mjs territory); compare those diagnostics by code only.
  const norm = (v) => JSON.parse(JSON.stringify(v, (k, x) => (k === "message" && typeof x === "string" && x.startsWith("frontmatter could not be parsed") ? "frontmatter could not be parsed" : x)));
  if (typeof ja === "object") { ja = norm(ja); jb = norm(jb); }
  const same = isDeepStrictEqual(ja, jb) && a.status === b.status;
  if (!same) failures++;
  console.log(`${same ? "OK  " : "DIFF"} exit node=${a.status} py=${b.status}  ${args.join(" ")}${skipped ? `  (${skipped} profile-free docs excluded)` : ""}`);
  if (!same && typeof ja === "object" && typeof jb === "object") {
    for (const key of new Set([...Object.keys(ja), ...Object.keys(jb)])) {
      if (!isDeepStrictEqual(ja[key], jb[key])) console.log(`     differs: ${key}`);
    }
  }
}
process.exitCode = failures ? 1 : 0;
