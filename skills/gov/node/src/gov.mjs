#!/usr/bin/env node
// gov — read-only lifecycle view over governed Markdown (plans, defects) built on the Node mdq engine.
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { read_document } from "../../../queryable-markdown/node/src/document.mjs";
import { extract_current } from "../../../queryable-markdown/node/src/records.mjs";
import { load_yaml, set_skills_root } from "../../../queryable-markdown/node/src/profile.mjs";

// ---- defaults (overridable by --config / .agents/skills-config/gov/config.yaml) ----
const DEFAULT_CONFIG = {
  schema: "gov.config.v1",
  kinds: {
    plan: {
      paths: ["docs/plans"],
      glob: "**/*.md",
      exclude: ["README.md", "INDEX.md"],
      status_from: ["field"],
      vocabulary: ["draft", "planned", "partial", "implemented", "verified", "archived", "superseded"],
      aliases: {},
    },
    defect: {
      paths: ["docs/defects"],
      glob: "DEF-*.md",
      exclude: [],
      status_from: ["frontmatter", "field"],
      vocabulary: ["confirmed", "fixing", "fixed", "verified", "superseded"],
      aliases: { pending_repair: "confirmed", in_progress: "fixing", implemented: "fixed" },
      expected_profile: "project-governance/defect-profile-v1",
    },
  },
};

function find_skills_root() {
  // The shared mdq profiles ship in the sibling `project-governance` skill; walk up until we see it.
  let dir = path.dirname(fileURLToPath(import.meta.url));
  for (let i = 0; i < 6; i++) {
    if (existsSync(path.join(dir, "project-governance", "assets", "mdq-profiles"))) return dir;
    dir = path.dirname(dir);
  }
  return null;
}

function walk(root, out = []) {
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const full = path.join(root, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (entry.isFile()) out.push(full);
  }
  return out;
}

function glob_to_regex(glob) {
  // supports **/ , * , ?  — enough for the config globs
  let re = "";
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === "*" && glob[i + 1] === "*") {
      i += 1;
      if (glob[i + 1] === "/") { i += 1; re += "(?:.*/)?"; } else re += ".*";
    } else if (c === "*") re += "[^/]*";
    else if (c === "?") re += "[^/]";
    else re += c.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp(`^${re}$`);
}

function load_config(root, explicit) {
  const candidate = explicit ?? path.join(root, ".agents", "skills-config", "gov", "config.yaml");
  if (!existsSync(candidate)) return { config: DEFAULT_CONFIG, source: "built-in defaults" };
  const parsed = load_yaml(readFileSync(candidate, "utf-8")) ?? {};
  if (parsed.schema !== "gov.config.v1") throw new Error(`unsupported config schema in ${candidate}: ${parsed.schema}`);
  return { config: parsed, source: candidate };
}

// ---- status normalisation ----
export function normalize_status(raw, kind) {
  if (raw === null || raw === undefined) return { canonical: null, how: "missing" };
  let text = String(raw).trim();
  text = text.replace(/^(?:\*\*|__|`)+/, "").replace(/^(?:状态|status)[：:]\s*/i, "").replace(/^(?:\*\*|__|`)+/, "");
  const head = text.split(/[（(，,。;；:：—–]|\s-\s|\s*#/)[0].trim().toLowerCase();
  const key = head.replace(/[\s_-]+/g, " ");
  const vocabulary = new Map(kind.vocabulary.map((v) => [v.replace(/[\s_-]+/g, " "), v]));
  const aliases = new Map(Object.entries(kind.aliases ?? {}).map(([a, v]) => [a.toLowerCase().replace(/[\s_-]+/g, " "), v]));
  if (vocabulary.has(key)) return { canonical: vocabulary.get(key), how: head === vocabulary.get(key) && text === head ? "exact" : "normalized" };
  if (aliases.has(key)) return { canonical: aliases.get(key), how: "alias" };
  // longest alias / vocabulary word at the start of the text
  const words = key.split(" ");
  for (let n = Math.min(words.length - 1, 4); n >= 1; n--) {
    const prefix = words.slice(0, n).join(" ");
    if (aliases.has(prefix)) return { canonical: aliases.get(prefix), how: "alias-prefix" };
    if (vocabulary.has(prefix)) return { canonical: vocabulary.get(prefix), how: "prefix" };
  }
  return { canonical: null, how: "unknown" };
}

function frontmatter_of(document) {
  const lines = document.lines;
  if (!lines.length || lines[0].replace(/^﻿/, "").trim() !== "---") return null;
  for (let i = 1; i < lines.length; i++) {
    if (["---", "..."].includes(lines[i].trim())) {
      try { return load_yaml(lines.slice(1, i).join("")) ?? null; } catch { return null; }
    }
  }
  return null;
}

export function collect(root, config) {
  const rows = [];
  const findings = [];
  for (const [kind_name, kind] of Object.entries(config.kinds)) {
    const matcher = glob_to_regex(kind.glob ?? "**/*.md");
    const excluded = new Set(kind.exclude ?? []);
    const seen = new Map();
    for (const rel_dir of kind.paths) {
      const base = path.join(root, rel_dir);
      if (!existsSync(base) || !statSync(base).isDirectory()) {
        findings.push({ level: "error", code: "path_missing", kind: kind_name, path: rel_dir, message: `configured path ${rel_dir} does not exist` });
        continue;
      }
      for (const full of walk(base).sort()) {
        const rel_in_dir = path.relative(base, full).split(path.sep).join("/");
        if (!full.endsWith(".md") || !matcher.test(rel_in_dir) || excluded.has(rel_in_dir)) continue;
        const rel = path.relative(root, full).split(path.sep).join("/");
        let document;
        try { document = read_document(full); } catch (error) {
          findings.push({ level: "error", code: "unreadable", kind: kind_name, path: rel, message: String(error.message ?? error) });
          continue;
        }
        const fm = frontmatter_of(document);
        const [records, diagnostics] = extract_current(document);
        for (const d of diagnostics) {
          if (d.severity === "error") findings.push({ level: "error", code: `mdq_${d.code}`, kind: kind_name, path: rel, message: d.message });
        }
        const source = document.profile_source ?? null;
        const stem = path.basename(full, ".md");
        const entries = records.length ? records : [null];
        for (const record of entries) {
          const id = record?.key ?? fm?.id ?? stem;
          const field_status = record?.fields?.status ?? null;
          const fm_status = fm?.status ?? null;
          const candidates = { frontmatter: fm_status, field: field_status };
          let raw = null; let raw_from = null;
          for (const origin of kind.status_from ?? ["field"]) {
            if (candidates[origin] !== null && candidates[origin] !== undefined) { raw = String(candidates[origin]); raw_from = origin; break; }
          }
          const norm = normalize_status(raw, kind);
          const row = { kind: kind_name, id, path: rel, status: norm.canonical, raw_status: raw, status_from: raw_from, normalization: norm.how, contract: source };
          rows.push(row);
          const add = (level, code, message) => findings.push({ level, code, kind: kind_name, id, path: rel, message });
          if (!records.length) add("warning", "no_record", "no mdq record could be extracted (missing or unusable contract)");
          if (raw === null) add("warning", "status_missing", "no status found in any configured source");
          else if (norm.canonical === null) add("error", "status_unknown", `status ${JSON.stringify(raw.slice(0, 60))} is not in the ${kind_name} vocabulary or alias table`);
          else if (["alias", "alias-prefix"].includes(norm.how)) add("info", "status_alias", `${JSON.stringify(raw.slice(0, 40))} maps to ${norm.canonical} (legacy spelling)`);
          else if (["normalized", "prefix"].includes(norm.how)) add("info", "status_text", `status text ${JSON.stringify(raw.slice(0, 60))} reads as ${norm.canonical}`);
          // A file-level frontmatter status only describes single-record files.
          if (records.length === 1 && fm_status !== null && field_status !== null) {
            const a = normalize_status(String(fm_status), kind).canonical;
            const b = normalize_status(String(field_status), kind).canonical;
            if (a !== b) add("error", "status_conflict", `frontmatter says ${JSON.stringify(fm_status)} but the record says ${JSON.stringify(field_status.slice(0, 40))}`);
          }
          if (kind.expected_profile && source && source !== `shared-profile:${kind.expected_profile}`) {
            add("warning", source.startsWith("shared-profile:") ? "profile_wrong" : "profile_inline", `contract is ${source}; expected shared-profile:${kind.expected_profile}`);
          }
          if (kind_name === "defect" && record?.key && record.key !== stem) add("warning", "id_filename_mismatch", `record id ${record.key} differs from file name ${stem}`);
          const dup = seen.get(id);
          if (dup) add("error", "duplicate_id", `id also used in ${dup}`); else seen.set(id, rel);
        }
      }
    }
  }
  return { rows, findings };
}

// ---- CLI ----
function parse_args(argv) {
  const args = { command: argv[0], rest: [], root: process.cwd(), config: null, json: false, kind: null, status: null, level: "warning" };
  for (let i = 1; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--root") args.root = path.resolve(argv[++i]);
    else if (a === "--config") args.config = path.resolve(argv[++i]);
    else if (a === "--json") args.json = true;
    else if (a === "--kind") args.kind = argv[++i];
    else if (a === "--status") args.status = argv[++i];
    else if (a === "--level") args.level = argv[++i];
    else args.rest.push(a);
  }
  return args;
}

const USAGE = `usage: gov <ls|show|check> [--root DIR] [--config FILE] [--kind plan|defect] [--status S] [--json]
  ls                 list governed records with canonical status
  show <ID>          one record with raw status, source and findings
  check [--level L]  report vocabulary, alias, contract and conflict findings (exit 1 on errors)`;

export function main(argv) {
  if (!argv.length || ["-h", "--help", "help"].includes(argv[0])) { console.log(USAGE); return 0; }
  const args = parse_args(argv);
  const skills_root = find_skills_root();
  if (skills_root) set_skills_root(skills_root);
  let loaded;
  try { loaded = load_config(args.root, args.config); } catch (error) { console.error(`gov: ${error.message}`); return 2; }
  const { rows, findings } = collect(args.root, loaded.config);
  const select = (r) => (!args.kind || r.kind === args.kind) && (!args.status || r.status === args.status || r.raw_status === args.status);
  if (args.command === "ls") {
    const out = rows.filter(select);
    if (args.json) console.log(JSON.stringify({ config: loaded.source, count: out.length, records: out }, null, 2));
    else for (const r of out) console.log(`${r.kind.padEnd(6)} ${(r.status ?? "?").padEnd(12)} ${r.id}  ${r.path}`);
    return 0;
  }
  if (args.command === "show") {
    const id = args.rest[0];
    const hit = rows.filter((r) => r.id === id);
    if (!hit.length) { console.error(`gov: no record ${id}`); return 3; }
    const out = hit.map((r) => ({ ...r, findings: findings.filter((f) => f.id === r.id && f.path === r.path) }));
    console.log(JSON.stringify(out.length === 1 ? out[0] : out, null, 2));
    return 0;
  }
  if (args.command === "check") {
    const order = { info: 0, warning: 1, error: 2 };
    const shown = findings.filter((f) => order[f.level] >= order[args.level] && (!args.kind || f.kind === args.kind));
    const counts = {};
    for (const f of findings) counts[`${f.level}:${f.code}`] = (counts[`${f.level}:${f.code}`] ?? 0) + 1;
    if (args.json) console.log(JSON.stringify({ config: loaded.source, records: rows.length, counts, findings: shown }, null, 2));
    else {
      console.log(`config: ${loaded.source}; records: ${rows.length}`);
      for (const [k, v] of Object.entries(counts).sort()) console.log(`  ${String(v).padStart(4)}  ${k}`);
      for (const f of shown) console.log(`${f.level.toUpperCase().padEnd(7)} ${f.code} ${f.id ?? ""} ${f.path}: ${f.message}`);
    }
    return findings.some((f) => f.level === "error") ? 1 : 0;
  }
  console.error(USAGE);
  return 2;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) process.exitCode = main(process.argv.slice(2));
