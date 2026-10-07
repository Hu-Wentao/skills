// Smoke: compare extract_current/records_for_query against Python mdq.py on friday-relay docs.
// Usage: node smoke/records.mjs [docs_root] [max_files]
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { read_document } from "../src/document.mjs";
import { extract_current, records_for_query } from "../src/records.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = process.argv[2] ?? "/home/claude/friday-relay/docs";
const max = Number(process.argv[3] ?? 150);
const mdq_py = path.resolve(here, "../../scripts/mdq.py");

const files = [];
(function walk(d) {
  for (const e of fs.readdirSync(d, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1))) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.name.endsWith(".md") && /<!--[ \t]*mdq/.test(fs.readFileSync(p, "utf-8"))) files.push(p);
  }
})(root);
const sample = files.filter((_, i) => i % Math.max(1, Math.ceil(files.length / max)) === 0).slice(0, max);

const tmp = path.join(process.env.TMPDIR ?? "/tmp", `records_py_${process.pid}.json`);
execFileSync("uv", ["run", path.join(here, "records_py.py"), mdq_py, tmp, ...sample], { stdio: "inherit" });
const py = JSON.parse(fs.readFileSync(tmp, "utf-8"));

function canon(v) {
  if (Array.isArray(v)) return v.map(canon);
  if (v && typeof v === "object") return Object.fromEntries(Object.keys(v).sort().map((k) => [k, canon(v[k])]));
  return v;
}
const same = (a, b) => JSON.stringify(canon(a)) === JSON.stringify(canon(b));

let bad = 0;
for (const p of sample) {
  let got;
  try {
    const doc = read_document(p);
    const [records, diagnostics] = extract_current(doc);
    const [query, query_diagnostics] = records_for_query(doc);
    got = { records, diagnostics, query, query_diagnostics };
  } catch (e) {
    console.log(`THROW ${p}: ${e.stack}`);
    bad++;
    continue;
  }
  for (const k of Object.keys(py[p])) {
    if (!same(got[k], py[p][k])) {
      bad++;
      console.log(`MISMATCH ${p} [${k}]`);
      const a = JSON.stringify(canon(got[k])), b = JSON.stringify(canon(py[p][k]));
      let i = 0; while (a[i] === b[i]) i++;
      console.log(`  node:   ...${a.slice(Math.max(0, i - 80), i + 120)}`);
      console.log(`  python: ...${b.slice(Math.max(0, i - 80), i + 120)}`);
    }
  }
}
console.log(`${sample.length} files, ${bad} mismatches`);
process.exit(bad ? 1 : 0);
