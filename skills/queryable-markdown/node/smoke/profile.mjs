// Smoke test for src/profile.mjs.
//   node smoke/profile.mjs                 -> shared profiles + a handful of real documents (human readable)
//   node smoke/profile.mjs --dump FILE...  -> JSON {path: {profile,source,excluded,diagnostics}} (sorted keys) for diffing with Python
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { load_shared_profile, validate_profile, parse_profile } from "../src/profile.mjs";
import { splitlines_keepends } from "../src/common.mjs";

function parseDoc(file) {
  const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(readFileSync(file));
  let lines = splitlines_keepends(text);
  if (!lines.length) lines = [""];
  const loaded = parse_profile(text, lines);
  return {
    profile: loaded.profile,
    source: loaded.source,
    excluded: [...loaded.excluded_lines].sort((a, b) => a - b),
    diagnostics: loaded.diagnostics,
  };
}
const sortKeys = (v) =>
  Array.isArray(v) ? v.map(sortKeys)
    : v && typeof v === "object" ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sortKeys(v[k])])) : v;

const args = process.argv.slice(2);
if (args[0] === "--dump") {
  const out = {};
  for (const f of args.slice(1)) {
    try { out[f] = parseDoc(f); } catch (e) { out[f] = { error: String(e) }; }
  }
  process.stdout.write(JSON.stringify(sortKeys(out)));
} else {
  const dir = "/home/claude/skills/skills/project-governance/assets/mdq-profiles";
  for (const f of readdirSync(dir).sort()) {
    const ref = `project-governance/${f.replace(/\.yaml$/, "")}`;
    const diags = [];
    const prof = load_shared_profile(ref, diags);
    const validated = prof ? validate_profile(prof, diags) : null;
    console.log(ref, "->", validated ? "valid" : "INVALID", JSON.stringify(diags));
  }
  const docs = args.length ? args : [
    "/home/claude/friday-relay/docs/defects/DEF-20260806-admin-runtime-config-trace-expansion.md",
    "/home/claude/friday-relay/docs/plans/context-tiered-pricing.md",
    "/home/claude/friday-relay/docs/plans/usage-budget-safety-implementation.md",
  ];
  for (const f of docs) {
    const r = parseDoc(f);
    console.log("\n==", path.basename(f), r.source, JSON.stringify(r.diagnostics));
    console.log(JSON.stringify(r.profile)?.slice(0, 300));
  }
}
