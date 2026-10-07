// Port of mdq.py: command_inspect/command_validate (3553-3720), command_check (4269-4401),
// command_search (4867-5014), collection_diagnostic/collection_paths/collection_record/command_scan (5014-5362).
// Temporary selectors (prepare_temporary_profile inference, line_local_*, visible_record_text) are not ported:
// they fail closed with an `unsupported_in_node` diagnostic.
import fs from "node:fs";
import nodePath from "node:path";
import { diagnostic, codepoint_compare, py_strip, py_rstrip, casefold } from "./common.mjs";
import { TEMPORARY_PROFILE_PREFIX, GENERIC_ID_RE } from "./profile.mjs";
import {
  read_document, analyze_markdown, analyze_tables, table_key_candidates, table_profile,
} from "./document.mjs";
import {
  strip_label_prefix, records_for_query, extract_current, index_path, error_diagnostics,
} from "./records.mjs";
import {
  emit, emit_compact_result, emit_collection_result, output_selection_diagnostics,
  project_output_payload, iter_result_diagnostics, pyget, py_truthy, py_repr,
} from "./output.mjs";
import { searchable_values, run_internal_mdq, sample_record_keys } from "./query.mjs";

const hasOwn = (o, k) => o !== null && typeof o === "object" && Object.prototype.hasOwnProperty.call(o, k);
// getattr(args, name, None)
const getattr = (args, name) => (args[name] === undefined ? null : args[name]);

function unsupported_in_node(feature) {
  return diagnostic("unsupported_in_node", "error", `${feature} are not supported by the Node port`);
}

// Python `\s` for str patterns (differs from JS \s: no U+FEFF, but \x1c-\x1f and \x85).
const PY_S = "\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";

// ---- OS / decode error helpers (Python OSError / UnicodeDecodeError equivalents) ----
const ERRNO_TEXT = {
  ENOENT: [2, "No such file or directory"],
  EACCES: [13, "Permission denied"],
  EISDIR: [21, "Is a directory"],
  ENOTDIR: [20, "Not a directory"],
  EPERM: [1, "Operation not permitted"],
  ELOOP: [40, "Too many levels of symbolic links"],
  ENAMETOOLONG: [36, "File name too long"],
};
export function is_os_error(error) {
  return error instanceof Error && typeof error.code === "string" && /^E[A-Z0-9]+$/.test(error.code);
}
export function is_decode_error(error) {
  return error instanceof Error && (error.code === "ERR_ENCODING_INVALID_ENCODED_DATA" || error.name === "UnicodeDecodeError");
}
export function is_timeout_error(error) {
  return error instanceof Error && error.name === "TimeoutError";
}
// str(OSError) as Python prints it: "[Errno 2] No such file or directory: 'path'"
export function os_error_message(error) {
  const known = ERRNO_TEXT[error.code];
  const number = known ? known[0] : (error.errno !== undefined ? Math.abs(error.errno) : 0);
  const text = known ? known[1] : String(error.message ?? error.code).replace(/^[A-Z]+: /, "").replace(/,.*$/, "");
  return error.path !== undefined ? `[Errno ${number}] ${text}: ${py_repr(error.path)}` : `[Errno ${number}] ${text}`;
}
export function decode_error_message(error) {
  // Python: "'utf-8' codec can't decode byte 0x.. in position N: ..."; Node does not expose byte/position.
  return error.name === "UnicodeDecodeError" ? error.message : "'utf-8' codec can't decode bytes: invalid utf-8 data";
}

// ---- pathlib helpers ----
function py_parts(p) {
  // PurePath parsing: drop empty and "." components.
  return p.split("/").filter((part) => part !== "" && part !== ".");
}
function py_path_str(p) {
  const absolute = p.startsWith("/");
  const body = py_parts(p).join("/");
  return absolute ? "/" + body : body === "" ? "." : body;
}
function py_name(p) {
  const parts = py_parts(p);
  return parts.length ? parts[parts.length - 1] : "";
}
// PurePath.suffix
function py_suffix(p) {
  const name = py_name(p);
  const i = name.lastIndexOf(".");
  return 0 < i && i < name.length - 1 ? name.slice(i) : "";
}
function is_symlink(p) {
  try { return fs.lstatSync(p).isSymbolicLink(); } catch { return false; }
}
function is_file(p) {
  try { return fs.statSync(p).isFile(); } catch { return false; }
}
function is_dir(p) {
  try { return fs.statSync(p).isDirectory(); } catch { return false; }
}
// Path.resolve(strict=False)
function py_resolve(p) {
  const abs = nodePath.resolve(p);
  const rest = [];
  let cur = abs;
  for (;;) {
    try {
      return nodePath.join(fs.realpathSync(cur), ...rest.reverse());
    } catch {
      const parent = nodePath.dirname(cur);
      if (parent === cur) return abs;
      rest.push(nodePath.basename(cur));
      cur = parent;
    }
  }
}
// os.path.commonpath for absolute paths
function py_commonpath(paths) {
  const split = paths.map((p) => py_parts(p));
  let common = split[0];
  for (const parts of split.slice(1)) {
    let n = 0;
    while (n < common.length && n < parts.length && common[n] === parts[n]) n++;
    common = common.slice(0, n);
  }
  return "/" + common.join("/");
}
// Path ordering compares the part lists, not the joined string.
function compare_paths(a, b) {
  const x = py_parts(a);
  const y = py_parts(b);
  const n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i++) {
    const d = codepoint_compare(x[i], y[i]);
    if (d !== 0) return d;
  }
  return x.length - y.length;
}
function relative_to(p, root) {
  // Path.relative_to(root); returns null (ValueError) when p is not under root.
  const a = py_parts(p);
  const b = py_parts(root);
  if (a.length < b.length) return null;
  for (let i = 0; i < b.length; i++) if (a[i] !== b[i]) return null;
  return a.slice(b.length);
}

// fnmatch.translate (POSIX, case-sensitive) -> anchored RegExp
function fnmatch_regex(pat) {
  let out = "";
  const chars = Array.from(pat);
  const n = chars.length;
  let i = 0;
  const esc = (c) => c.replace(/[\\^$.*+?()[\]{}|\/-]/g, "\\$&");
  while (i < n) {
    const c = chars[i++];
    if (c === "*") out += ".*";
    else if (c === "?") out += ".";
    else if (c === "[") {
      let j = i;
      if (j < n && chars[j] === "!") j++;
      if (j < n && chars[j] === "]") j++;
      while (j < n && chars[j] !== "]") j++;
      if (j >= n) out += "\\[";
      else {
        let stuff = chars.slice(i, j).join("");
        i = j + 1;
        let negate = false;
        if (stuff[0] === "!") { negate = true; stuff = stuff.slice(1); }
        stuff = stuff.replace(/[\\[\]]/g, "\\$&").replace(/^\^/, "\\^");
        // fnmatch drops empty/reversed ranges; a plain class is the common case
        out += stuff === "" ? (negate ? "[^]" : "(?!)") : `[${negate ? "^" : ""}${stuff}]`;
      }
    } else out += esc(c);
  }
  return new RegExp(`^(?:${out})$`, "su");
}

// pathlib.Path.glob (Python 3.11) restricted to a relative pattern. Yields path strings (unresolved).
function pathlib_glob(base, pattern) {
  if (!pattern) throw new Error(`Unacceptable pattern: ${py_repr(pattern)}`);
  const parts = py_parts(pattern);
  for (const part of parts) {
    if (part !== "**" && part.includes("**")) {
      throw new Error("Invalid pattern: '**' can only be an entire path component");
    }
  }
  const seen = new Set();
  const results = [];
  const child = (parent, name) => (parent === "/" ? "/" + name : parent + "/" + name);
  const scandir = (dir) => {
    try { return fs.readdirSync(dir, { withFileTypes: true }); } catch { return []; }
  };
  const iterate_directories = function* (dir) {
    yield dir;
    for (const entry of scandir(dir)) {
      let entry_is_dir = false;
      try { entry_is_dir = entry.isDirectory() || (entry.isSymbolicLink() && is_dir(child(dir, entry.name))); } catch { /* ignore */ }
      if (entry_is_dir && !entry.isSymbolicLink()) yield* iterate_directories(child(dir, entry.name));
    }
  };
  const select = function* (index, parent) {
    if (index >= parts.length) { yield parent; return; }
    const pat = parts[index];
    const dironly = index + 1 < parts.length;
    if (pat === "**") {
      const yielded = new Set();
      for (const start of iterate_directories(parent)) {
        for (const p of select(index + 1, start)) {
          if (!yielded.has(p)) { yielded.add(p); yield p; }
        }
      }
    } else if (/[*?[]/.test(pat)) {
      if (!is_dir(parent)) return;
      const re = fnmatch_regex(pat);
      for (const entry of scandir(parent)) {
        if (dironly && !is_dir(child(parent, entry.name))) continue;
        if (re.test(entry.name)) yield* select(index + 1, child(parent, entry.name));
      }
    } else {
      const next = child(parent, pat);
      const present = dironly ? is_dir(next) : fs.existsSync(next);
      if (present) yield* select(index + 1, next);
    }
  };
  for (const p of select(0, base)) {
    if (!seen.has(p)) { seen.add(p); results.push(p); }
  }
  return results;
}

// Python: attaches an in-memory profile when the source has none. Only the non-inferring branches are ported.
function has_temporary_selector_arguments(args) {
  return (
    (getattr(args, "record_level") || []).length > 0 ||
    (getattr(args, "key_label") || []).length > 0 ||
    py_truthy(getattr(args, "key_pattern")) ||
    py_truthy(getattr(args, "key_group"))
  );
}
function prepare_temporary_profile(document, args) {
  if (document.profile !== null && document.profile !== undefined) {
    if (has_temporary_selector_arguments(args)) {
      document.diagnostics.push(
        diagnostic(
          "temporary_selectors_ignored",
          "info",
          "temporary selectors were ignored because the document declares an mdq profile"
        )
      );
    }
    return [];
  }
  if (error_diagnostics(document.diagnostics)) return [];
  // Inference / explicit temporary selectors for profile-free documents: fail closed.
  return [unsupported_in_node("temporary selectors")];
}

// search the first capture group of a compiled pattern (PyPattern or RegExp)
function search_group1(re, text) {
  if (typeof re.search === "function") {
    const m = re.search(text);
    return m ? m.group(1) : null;
  }
  const m = new RegExp(re.source, re.flags.replace("g", "")).exec(text);
  return m ? m[1] : null;
}

// Counter.most_common(n): stable by first insertion, count descending
function most_common(counter, n = null) {
  const items = [...counter.entries()].sort((a, b) => b[1] - a[1]);
  return n === null ? items : items.slice(0, n);
}

// ---- mdq.py 3553 ----
export function command_inspect(args) {
  const document = read_document(args.document);
  const dialect = document.profile ? pyget(document.profile, "dialect", "commonmark") : "commonmark";
  const [headings, code_lines, markers, parse_diagnostics] = analyze_markdown(document, dialect);
  const [tables, table_diagnostics] = analyze_tables(document, headings);
  const level_counts = new Map();
  for (const item of headings) {
    const k = String(item.level);
    level_counts.set(k, (level_counts.get(k) ?? 0) + 1);
  }
  const label_counts = new Map();
  const label_re = new RegExp(`^(?:\\*\\*|__|\`)?([^:：|]+?)(?:\\*\\*|__|\`)?[${PY_S}]*[:：]`, "u");
  document.masked_lines.forEach((line, index) => {
    if (code_lines.has(index) || document.excluded_lines.has(index)) return;
    const stripped = strip_label_prefix(py_rstrip(line, "\r\n"));
    const match = label_re.exec(stripped);
    if (match) {
      const label = py_strip(match[1].replace(/[*_`]/g, ""));
      const length = Array.from(label).length;
      if (0 < length && length <= 40) label_counts.set(label, (label_counts.get(label) ?? 0) + 1);
    }
  });
  const id_headings = [];
  for (const item of headings) {
    const found = search_group1(GENERIC_ID_RE, item.text);
    if (found !== null) {
      id_headings.push({ id: found, line: item.start + 1, level: item.level, text: item.text });
    }
  }

  const table_summaries = [];
  let suggested_table = null;
  for (const table of tables) {
    const key_candidates = table_key_candidates(table);
    table_summaries.push({
      line_start: table.start + 1,
      line_end: table.end,
      under_heading: table.under_heading,
      columns: table.headers,
      row_count: table.rows.length,
      candidate_keys: key_candidates,
    });
    if (suggested_table === null && key_candidates.length === 1) suggested_table = [table, key_candidates[0]];
  }

  let suggestion = null;
  if (suggested_table !== null) {
    suggestion = table_profile(...suggested_table);
  } else if (id_headings.length) {
    const counts = new Map();
    for (const entry of id_headings) counts.set(entry.level, (counts.get(entry.level) ?? 0) + 1);
    const preferred_level = most_common(counts, 1)[0][0];
    suggestion = {
      version: 1,
      dialect,
      records: {
        boundary: { source: "heading", levels: [preferred_level], level_tolerance: 0 },
        key: {
          source: "heading",
          pattern: "^(?P<id>[A-Za-z][A-Za-z0-9_.]*-[0-9]+)(?:\\s*[-:：]\\s*|\\s+)?(?P<title>.*)$",
          group: "id",
        },
      },
      fields: { title: { source: "heading", group: "title" } },
      tolerance: { incomplete: true },
    };
  }
  const diagnostics = [...document.diagnostics, ...parse_diagnostics, ...table_diagnostics];
  if (document.profile !== null && document.profile !== undefined && tables.length) {
    const [records, existing_diagnostics] = records_for_query(document);
    const structured_count = records.filter(
      (item) => pyget(item, "key", null) !== null && pyget(item, "confidence", 0) >= 0.6
    ).length;
    let table_identity_count = 0;
    for (const summary of table_summaries) for (const candidate of summary.candidate_keys) table_identity_count += candidate.count;
    if (table_identity_count >= Math.max(2, structured_count * 2)) {
      diagnostics.push(
        diagnostic(
          "record_granularity_mismatch",
          "warning",
          "the current contract exposes far fewer records than stable table-row identities",
          { details: { structured_records: structured_count, table_row_identities: table_identity_count } }
        )
      );
    }
    diagnostics.push(...existing_diagnostics);
  }
  const sorted_levels = {};
  for (const key of [...level_counts.keys()].sort(codepoint_compare)) sorted_levels[key] = level_counts.get(key);
  emit({
    status: error_diagnostics(diagnostics) ? "invalid" : "inspected",
    document: String(document.path),
    profile: { present: document.profile !== null && document.profile !== undefined, source: document.profile_source },
    heading_levels: sorted_levels,
    candidate_headings: id_headings.slice(0, 50),
    common_labels: most_common(label_counts, 30).map(([label, count]) => ({ label, count })),
    tables: table_summaries,
    markers: markers.map((item) => ({ key: item.key, line: item.line + 1 })),
    suggested_profile: suggestion,
    diagnostics,
  });
  return 0;
}

export function command_validate(args) {
  const document = read_document(args.document);
  if (document.profile === null || document.profile === undefined) {
    emit({
      status: "invalid",
      valid: false,
      document: String(document.path),
      record_count: 0,
      diagnostics: document.diagnostics,
    });
    return 3;
  }
  const [records, diagnostics] = extract_current(document);
  if (hasOwn(document.profile, "index")) {
    const [, index_problem] = index_path(document);
    if (index_problem !== null) diagnostics.push(index_problem);
  }
  const structured = records.filter(
    (item) => pyget(item, "key", null) !== null && pyget(item, "confidence", 0) >= 0.6
  );
  const valid = !error_diagnostics(diagnostics);
  const payload = {
    status: valid ? "validated" : "invalid",
    valid,
    document: String(document.path),
    profile_source: document.profile_source,
    record_count: structured.length,
    candidate_count: records.length - structured.length,
    diagnostics,
  };
  if (args.command === "diagnose") payload.records = records;
  emit(payload);
  return valid ? 0 : 3;
}

// ---- mdq.py 4269 ----
export function command_check(args) {
  const expected_ids = [...new Set(args.id || [])];
  const absent_ids = [...new Set(args.absent_id || [])];
  if (args.tier === "content" && !expected_ids.length) {
    const payload = {
      schema: "mdq.check.v1",
      status: "invalid",
      tier: args.tier,
      count: 0,
      checks: [],
      records: [],
      candidates: [],
      diagnostics: [diagnostic("selector_invalid", "error", "content checks require at least one --id")],
    };
    if (args.output === "json") emit(payload);
    else emit_compact_result(payload);
    return 3;
  }

  const checks = [];
  const diagnostics = [];
  const matched_records = [];
  const candidates = [];
  let sample_keys = [];

  const add_step = (name, command, predicate) => {
    const [returncode, result] = run_internal_mdq(...command);
    const passed = Boolean(predicate(returncode, result));
    checks.push({ name, passed, returncode, result });
    for (const item of iter_result_diagnostics(result)) diagnostics.push({ ...item, check: name });
    return result;
  };

  const validate_result = add_step(
    "validate",
    ["validate", args.document],
    (returncode, result) => returncode === 0 && result.valid === true
  );

  if (validate_result.valid === true && (args.tier === "structure" || args.tier === "contract")) {
    const diagnose_result = add_step(
      "diagnose",
      ["diagnose", args.document],
      (returncode, result) => returncode === 0 && result.valid === true
    );
    sample_keys = sample_record_keys(pyget(diagnose_result, "records", []));
  }

  if (validate_result.valid === true) {
    for (const identifier of expected_ids) {
      const command = ["query", args.document, "--id", identifier, "--output", "json"];
      for (const field_name of args.select || []) command.push("--select", field_name);
      const result = add_step(
        `query:${identifier}`,
        command,
        (returncode, value) =>
          returncode === 0 && value.status === "matched" && value.count === 1 && !py_truthy(pyget(value, "candidates", null))
      );
      matched_records.push(...pyget(result, "records", []));
      candidates.push(...pyget(result, "candidates", []));
    }

    for (const identifier of absent_ids) {
      const result = add_step(
        `absent:${identifier}`,
        ["query", args.document, "--id", identifier, "--output", "json"],
        (returncode, value) => returncode === 0 && value.status === "not_found" && value.count === 0
      );
      candidates.push(...pyget(result, "candidates", []));
    }

    const document = read_document(args.document);
    if (
      args.tier === "contract" &&
      document.profile !== null && document.profile !== undefined &&
      pyget(document.profile, "version", null) === 2 &&
      py_truthy(pyget(document.profile, "queries", null))
    ) {
      add_step("verify-queries", ["verify", args.document], (returncode, result) => returncode === 0 && result.valid === true);
    }
  }

  const passed = checks.length > 0 && checks.every((item) => item.passed);
  const payload = {
    schema: "mdq.check.v1",
    status: passed ? "passed" : "failed",
    tier: args.tier,
    document: py_resolve(args.document),
    count: matched_records.length,
    sample_keys,
    checks,
    records: matched_records,
    candidates,
    diagnostics,
  };
  if (args.output === "json") emit(payload);
  else emit_compact_result(project_output_payload(payload, args.select, { compact_default: true }));
  return passed ? 0 : 3;
}

// ---- mdq.py 4867 ----
export function command_search(args) {
  const document = read_document(args.document);
  const preparation_diagnostics = prepare_temporary_profile(document, args);
  if (document.profile === null || document.profile === undefined) {
    if (error_diagnostics(document.diagnostics)) {
      emit({ status: "invalid", count: 0, records: [], candidates: [], diagnostics: document.diagnostics });
      return 3;
    }
    if (![null, "body", "context"].includes(args.field)) {
      const diagnostics = [
        ...document.diagnostics,
        ...preparation_diagnostics,
        diagnostic("unknown_field", "error", `field ${py_repr(args.field)} is unavailable without a record boundary`),
      ];
      emit({ status: "invalid", count: 0, records: [], candidates: [], diagnostics });
      return 3;
    }
    // Python continues with line_local_search_records (temporary selectors): fail closed.
    emit({
      status: "invalid",
      count: 0,
      records: [],
      candidates: [],
      diagnostics: [...document.diagnostics, ...preparation_diagnostics],
    });
    return 3;
  }
  const temporary = (document.profile_source || "").startsWith(TEMPORARY_PROFILE_PREFIX);
  if (args.field && args.field !== "key" && !hasOwn(pyget(document.profile, "fields", {}), args.field)) {
    const diagnostics = [
      ...document.diagnostics,
      diagnostic("unknown_field", "error", `field ${py_repr(args.field)} is not declared`),
    ];
    emit({ status: "invalid", count: 0, records: [], candidates: [], diagnostics });
    return 3;
  }
  const [records, diagnostics] = records_for_query(document);
  if (error_diagnostics(diagnostics)) {
    emit({ status: "invalid", count: 0, records: [], candidates: [], diagnostics });
    return 3;
  }
  if (temporary) {
    // Only reachable for profiles built by prepare_temporary_profile, which this port never builds.
    emit({
      status: "invalid", count: 0, records: [], candidates: [],
      diagnostics: [...diagnostics, unsupported_in_node("temporary selectors")],
    });
    return 3;
  }
  const needle = casefold(args.text);
  const matched = [];
  const candidates = [];
  for (const item of records) {
    const values = searchable_values(item, args.field);
    if (values.some((value) => casefold(value).includes(needle))) {
      if (Number(pyget(item, "confidence", 0)) >= 0.6 && pyget(item, "key", null) !== null) matched.push(item);
      else candidates.push({ ...item, candidate: true });
    }
    if (matched.length + candidates.length >= args.limit) break;
  }
  if (!matched.length && !candidates.length) {
    diagnostics.push(diagnostic("no_match", "info", `literal text ${py_repr(args.text)} was not found`));
  }
  emit({
    status: matched.length ? "matched" : "not_found",
    count: matched.length,
    records: matched,
    candidates,
    diagnostics,
  });
  return 0;
}

export function collection_diagnostic(item, document, relative_path) {
  return { ...item, document: String(document), relative_path };
}

// targets: list of path strings (Python passes Path objects). Returns [root, ordered [path, relative], diagnostics].
export function collection_paths(targets, patterns, { reject_matched_symlinks = false } = {}) {
  const diagnostics = [];
  const candidates = new Map();
  const roots = [];

  for (const raw_target of targets) {
    const target = py_path_str(raw_target);
    if (is_symlink(target)) {
      diagnostics.push(diagnostic("collection_path_unsafe", "error", `collection path must not be a symlink: ${target}`));
      continue;
    }
    const resolved = py_resolve(target);
    if (is_file(resolved)) {
      if (casefold(py_suffix(resolved)) !== ".md") {
        diagnostics.push(
          diagnostic("collection_path_invalid", "error", `collection file must use the .md extension: ${target}`)
        );
        continue;
      }
      roots.push(nodePath.dirname(resolved));
      candidates.set(resolved, null);
      continue;
    }
    if (!is_dir(resolved)) {
      diagnostics.push(
        diagnostic("collection_path_invalid", "error", `collection path must be a Markdown file or directory: ${target}`)
      );
      continue;
    }

    roots.push(resolved);
    for (const pattern of patterns) {
      const pattern_parts = py_parts(pattern);
      if (pattern.startsWith("/") || pattern_parts.includes("..")) {
        diagnostics.push(
          diagnostic("collection_glob_unsafe", "error", `collection glob must stay inside the target directory: ${pattern}`)
        );
        continue;
      }
      let matches;
      try {
        matches = pathlib_glob(resolved, pattern);
      } catch (exc) {
        // Python's Path.glob is a generator, so these ValueErrors actually escape the try block there
        // (traceback, exit 1); the intended collection_glob_invalid diagnostic is emitted instead.
        diagnostics.push(
          diagnostic("collection_glob_invalid", "error", `collection glob ${py_repr(pattern)} is invalid: ${exc.message}`)
        );
        continue;
      }
      for (const candidate of matches) {
        if (is_symlink(candidate)) {
          if (reject_matched_symlinks && casefold(py_suffix(candidate)) === ".md") {
            diagnostics.push(
              diagnostic("collection_path_unsafe", "error", `matched Markdown path must not be a symlink: ${candidate}`)
            );
          }
          continue;
        }
        if (!is_file(candidate) || casefold(py_suffix(candidate)) !== ".md") continue;
        const actual = py_resolve(candidate);
        if (relative_to(actual, resolved) === null) {
          diagnostics.push(
            diagnostic("collection_path_unsafe", "error", `matched document escapes the collection root: ${candidate}`)
          );
          continue;
        }
        candidates.set(actual, null);
      }
    }
  }

  const root = roots.length ? py_commonpath(roots) : py_resolve(process.cwd());
  const ordered = [...candidates.keys()]
    .sort(compare_paths)
    .map((p) => [p, p !== root ? relative_to(p, root).join("/") : py_name(p)]);
  return [root, ordered, diagnostics];
}

export function collection_record(record, { document, relative_path, field_name, selected_fields }) {
  const item = { ...record };
  item.document = String(document.path);
  item.relative_path = relative_path;
  if (selected_fields !== null && selected_fields !== undefined) {
    const fields = record.fields || {};
    const out = {};
    for (const name of selected_fields) out[name] = hasOwn(fields, name) ? fields[name] : null;
    item.fields = out;
  } else if (field_name !== null && field_name !== undefined && field_name !== "key") {
    const fields = record.fields || {};
    item.fields = { [field_name]: hasOwn(fields, field_name) ? fields[field_name] : null };
  } else if (field_name === "key") {
    item.fields = {};
  }
  return item;
}

// ---- mdq.py 5014 ----
export function command_scan(args) {
  const patterns = args.glob && args.glob.length ? [...args.glob] : ["**/*.md"];
  const [root, paths, diagnostics] = collection_paths([...args.path], patterns);
  const select = getattr(args, "select");
  if (error_diagnostics(diagnostics)) {
    emit_collection_result(
      {
        schema: "mdq.collection.v1",
        status: "invalid",
        root: String(root),
        globs: patterns,
        documents_scanned: 0,
        documents_matched: 0,
        count: 0,
        truncated: false,
        records: [],
        candidates: [],
        documents: [],
        diagnostics,
      },
      args.output,
      select
    );
    return 3;
  }

  const requested_ids = new Set((args.id || []).map((item) => py_strip(item)));
  const matched_records = [];
  const candidates = [];
  const document_summaries = [];
  let invalid_documents = 0;
  let documents_matched = 0;
  let truncated = false;

  for (const [path, relative_path] of paths) {
    let document;
    try {
      document = read_document(path);
    } catch (exc) {
      const decode = is_decode_error(exc);
      if (!decode && !is_os_error(exc)) throw exc;
      const item = diagnostic(decode ? "encoding_invalid" : "io_error", "error", decode ? decode_error_message(exc) : os_error_message(exc));
      diagnostics.push(collection_diagnostic(item, path, relative_path));
      document_summaries.push({
        document: String(path),
        relative_path,
        status: "invalid",
        profile_source: null,
        record_count: 0,
        matched_count: 0,
        diagnostics: [item],
      });
      invalid_documents += 1;
      continue;
    }

    let preparation_diagnostics = [];
    let document_diagnostics = [...document.diagnostics];
    const no_profile = document.profile === null || document.profile === undefined;
    if (args.require_contract && no_profile) {
      document_diagnostics.push(
        diagnostic(
          "persistent_contract_required",
          "error",
          "collection query requires a valid persistent mdq contract",
          { line: 1 }
        )
      );
    } else if (no_profile) {
      preparation_diagnostics = prepare_temporary_profile(document, args);
      document_diagnostics = [...document.diagnostics];
    }

    document_diagnostics.push(...output_selection_diagnostics(document, select));

    if (
      !no_profile &&
      args.field !== null && args.field !== undefined && args.field !== "key" &&
      !hasOwn(pyget(document.profile, "fields", {}), args.field)
    ) {
      document_diagnostics.push(
        diagnostic("unknown_field", "error", `field ${py_repr(args.field)} is not declared`)
      );
    }

    let records = [];
    let all_document_diagnostics;
    if (!no_profile && !error_diagnostics(document_diagnostics)) {
      let extracted_diagnostics;
      try {
        [records, extracted_diagnostics] = records_for_query(document);
      } catch (exc) {
        if (!is_timeout_error(exc)) throw exc;
        extracted_diagnostics = [
          diagnostic("regex_timeout", "error", "a profile regex exceeded the matching time limit"),
        ];
      }
      all_document_diagnostics = [...document_diagnostics, ...preparation_diagnostics, ...extracted_diagnostics];
    } else {
      all_document_diagnostics = [...document_diagnostics, ...preparation_diagnostics];
    }
    const document_invalid = error_diagnostics(all_document_diagnostics);
    if (document_invalid) invalid_documents += 1;

    const structured = [];
    const document_candidates = [];
    for (const record of records) {
      const confidence = Number(pyget(record, "confidence", 0.0));
      const key = pyget(record, "key", null);
      let selected = key !== null && confidence >= 0.6;
      if (requested_ids.size) selected = selected && requested_ids.has(key);
      if (args.text !== null && args.text !== undefined) {
        const values = searchable_values(record, args.field);
        const needle = casefold(args.text);
        selected = selected && values.some((value) => casefold(value).includes(needle));
      }
      const item = collection_record(record, {
        document,
        relative_path,
        field_name: getattr(args, "field"),
        selected_fields: select,
      });
      if (selected) structured.push(item);
      else if (key === null || confidence < 0.6) {
        item.candidate = true;
        document_candidates.push(item);
      }
    }

    if (structured.length) documents_matched += 1;
    for (const item of structured) {
      if (matched_records.length < args.limit) matched_records.push(item);
      else truncated = true;
    }
    for (const item of document_candidates) {
      if (candidates.length < args.limit) candidates.push(item);
      else truncated = true;
    }

    const document_status = document_invalid ? "invalid" : structured.length ? "matched" : "not_found";
    document_summaries.push({
      document: String(document.path),
      relative_path,
      status: document_status,
      profile_source: document.profile_source,
      record_count: records.filter(
        (item) => pyget(item, "key", null) !== null && Number(pyget(item, "confidence", 0.0)) >= 0.6
      ).length,
      matched_count: structured.length,
      diagnostics: all_document_diagnostics,
    });
    for (const item of all_document_diagnostics) {
      diagnostics.push(collection_diagnostic(item, document.path, relative_path));
    }
  }

  let collection_status;
  if (invalid_documents) collection_status = matched_records.length ? "partial" : "invalid";
  else collection_status = matched_records.length ? "matched" : "not_found";
  emit_collection_result(
    {
      schema: "mdq.collection.v1",
      status: collection_status,
      root: String(root),
      globs: patterns,
      documents_scanned: paths.length,
      documents_matched,
      count: matched_records.length,
      truncated,
      records: matched_records,
      candidates,
      documents: document_summaries,
      diagnostics,
    },
    args.output,
    select
  );
  return invalid_documents ? 3 : 0;
}
