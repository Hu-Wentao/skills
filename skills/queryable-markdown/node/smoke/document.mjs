// Usage: node smoke/document.mjs file... > out.json   (SRC=dir overrides ../src)
import { createHash } from "node:crypto";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
const src = process.env.SRC || path.join(path.dirname(fileURLToPath(import.meta.url)), "../src");
const D = await import(pathToFileURL(path.join(src, "document.mjs")).href);
const plain = (x) => JSON.parse(JSON.stringify(x));
const out = {};
for (const p of process.argv.slice(2)) {
  const d = D.read_document(p);
  const [h, code, m, diag] = D.analyze_markdown(d, "gfm");
  const [t, tdiag] = D.analyze_tables(d, h);
  const kc = t.map((x) => D.table_key_candidates(x));
  out[p] = {
    lines: d.lines.length,
    masked_hash: createHash("sha256").update(d.masked_text).digest("hex"),
    masked_lines_hash: createHash("sha256").update(JSON.stringify(d.masked_lines)).digest("hex"),
    byte_offsets: d.byte_offsets,
    lexical_code_lines: [...d.lexical_code_lines].sort((a, b) => a - b),
    excluded_lines: [...d.excluded_lines].sort((a, b) => a - b),
    unclosed_fence_line: d.unclosed_fence_line,
    unclosed_comment_line: d.unclosed_comment_line,
    unclosed_opaque_blocks: d.unclosed_opaque_blocks,
    headings: plain(h), code_lines: [...code].sort((a, b) => a - b), markers: plain(m), diagnostics: diag,
    tables: plain(t), table_diagnostics: tdiag, key_candidates: kc,
    table_profiles: t.flatMap((x, i) => kc[i].slice(0, 1).map((c) => D.table_profile(x, c))),
  };
}
console.log(JSON.stringify(out));
