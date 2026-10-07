// Port of mdq.py lines 2306-3090 (regex_value .. error_diagnostics).
import fs from "node:fs";
import path from "node:path";
import {
  ENGINE, diagnostic, normalized_json, py_strip, py_rstrip, py_strip_chars,
  compile_py,
} from "./common.mjs";
import { Record } from "./types.mjs";
import {
  normalize_label, match_group, MAX_REGEX_LINE, INDEX_SCHEMA, TEMPORARY_PROFILE_PREFIX,
} from "./profile.mjs";
import { analyze_markdown, analyze_tables } from "./document.mjs";

// NOTE: Python uses `regex` with timeout=REGEX_TIMEOUT_SECONDS (0.05s) per search.
// JS RegExp has no per-match timeout, so none exists here; only the MAX_REGEX_LINE
// length guard (code points) is reproduced. Catastrophic patterns may hang in Node.

const has = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
const get = (obj, key, dflt = null) => (obj && has(obj, key) && obj[key] !== undefined ? obj[key] : dflt);
const cp_slice = (text, n) => {
  // Python text[:n] counts code points.
  if (text.length <= n) return text;
  const arr = Array.from(text);
  return arr.length > n ? arr.slice(0, n).join("") : text;
};
const cp_len = (text) => Array.from(text).length;

export function unsupported_in_node(feature) {
  return diagnostic("unsupported_in_node", "error", `${feature} are not supported by the Node port`);
}

export function regex_value(pattern, text, group) {
  if (pattern === null || pattern === undefined) return py_strip(text);
  if (cp_len(text) > MAX_REGEX_LINE) text = cp_slice(text, MAX_REGEX_LINE);
  const match = compile_profile_pattern(pattern).search(text);
  return match ? match_group(match, group ?? null) : null;
}

const _pattern_cache = new Map();
export function compile_profile_pattern(pattern) {
  let compiled = _pattern_cache.get(pattern);
  if (compiled === undefined) {
    compiled = compile_py(pattern);
    if (_pattern_cache.size >= 128) _pattern_cache.delete(_pattern_cache.keys().next().value);
    _pattern_cache.set(pattern, compiled);
  }
  return compiled;
}

export function strip_label_prefix(line) {
  let value = py_strip(line);
  value = value.replace(/^(?:>[ \t]*)+/, "");
  value = value.replace(/^[-*+][ \t]+/, "");
  return py_strip(value);
}

const LABEL_RE = /^(?<label>(?:\*\*|__|`)?[^:：|]+?(?:\*\*|__|`)?)[ \t]*[:：][ \t]*(?<value>.*)$/u;

export function label_occurrences(document, start, end, labels, code_lines) {
  const wanted = new Set(Array.from(labels, (label) => normalize_label(label)));
  const found = [];
  for (let index = start; index < Math.min(end, document.lines.length); index++) {
    if (code_lines.has(index) || document.excluded_lines.has(index)) continue;
    const line = py_rstrip(document.masked_lines[index], "\r\n");
    const stripped = strip_label_prefix(line);
    if (stripped.startsWith("|") && stripped.split("|").length - 1 >= 2) {
      const cells = py_strip_chars(stripped, "|").split("|").map((cell) => py_strip(cell));
      if (cells.length >= 2 && wanted.has(normalize_label(cells[0]))) {
        found.push({ value: py_strip(cells[1]), line: index + 1 });
        continue;
      }
    }
    const match = LABEL_RE.exec(stripped);
    if (match && wanted.has(normalize_label(match.groups.label))) {
      found.push({ value: py_strip(match.groups.value), line: index + 1 });
    }
  }
  return found;
}

export function resolve_scalar(field_name, values, record_diagnostics) {
  const non_empty = values.filter((item) => {
    const v = get(item, "value");
    return v !== null && v !== "";
  });
  const distinct = new Map();
  const originals = new Map();
  for (const item of non_empty) {
    const key = String(item.value);
    if (!distinct.has(key)) distinct.set(key, []);
    distinct.get(key).push(get(item, "line"));
    originals.set(key, item.value);
  }
  if (distinct.size === 0) {
    record_diagnostics.push(diagnostic("missing_field", "info", `field ${field_name} is absent or incomplete`));
    return null;
  }
  if (distinct.size > 1) {
    record_diagnostics.push(diagnostic(
      "field_conflict", "warning", `field ${field_name} has conflicting values`,
      {
        details: {
          field: field_name,
          values: Array.from(distinct, ([k, v]) => ({ value: originals.get(k), lines: v })),
        },
      },
    ));
    return null;
  }
  return originals.get(distinct.keys().next().value);
}

export function key_from_heading(heading, spec) {
  if (heading === null || heading === undefined) return null;
  return regex_value(get(spec, "pattern"), heading.text, get(spec, "group"));
}

export function heading_is_boundary(heading, boundary, has_marker) {
  const levels = boundary.levels;
  const expected = levels.includes(heading.level);
  const distance = Math.min(...levels.map((level) => Math.abs(heading.level - level)));
  const within = expected || distance <= get(boundary, "level_tolerance", 0);
  if (!within) return [false, 0.0];
  const pattern_ok = regex_value(get(boundary, "pattern"), heading.text, null) !== null;
  if (get(boundary, "pattern") && !pattern_ok && !has_marker) return [false, 0.0];
  if (!expected && !has_marker) return [true, 0.8];
  return [
    true,
    heading.source === "ast" && expected ? 1.0 : heading.source === "scan" ? 0.6 : 0.8,
  ];
}

export function nearest_marker(markers, heading) {
  const candidates = markers.filter((marker) => {
    const d = heading.start - marker.line;
    return d >= 0 && d <= 3;
  });
  if (candidates.length === 0) return null;
  // Python max() returns the first maximal element.
  let best = candidates[0];
  for (const c of candidates) if (c.line > best.line) best = c;
  return best;
}

export class BoundaryCandidate {
  constructor(start, heading, marker, confidence, diagnostics, table_row = null, fixed_end = null) {
    this.start = start;
    this.heading = heading;
    this.marker = marker;
    this.confidence = confidence;
    this.diagnostics = diagnostics;
    this.table_row = table_row;
    this.fixed_end = fixed_end;
  }
}

const same_list = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);

export function collect_boundaries(document, profile, headings, code_lines, markers, tables) {
  const boundary_spec = profile.records.boundary;
  const key_spec = profile.records.key;
  let candidates = [];
  const used_markers = new Set();

  if (get(boundary_spec, "source") === "table-row") {
    const declared_columns = boundary_spec.columns;
    const wanted_heading = get(boundary_spec, "under_heading");
    const matching_tables = tables.filter((table) =>
      same_list(table.headers, declared_columns)
      && (wanted_heading === null || table.under_heading === wanted_heading)
      && new Set(table.headers).size === table.headers.length);
    if (matching_tables.length > 1) return [];
    if (matching_tables.length) {
      for (const row of matching_tables[0].rows) {
        candidates.push(new BoundaryCandidate(row.start, null, null, 1.0, [], row, row.end - 1));
      }
    }
  } else {
    for (const heading of headings) {
      const marker = nearest_marker(markers, heading);
      const [accepted, confidence] = heading_is_boundary(heading, boundary_spec, marker !== null);
      if (!accepted) continue;
      if (!boundary_spec.levels.includes(heading.level) && marker === null) {
        // Heading drift needs identity evidence, not level proximity alone.
        let evidence = null;
        if (get(key_spec, "source") === "heading") {
          evidence = key_from_heading(heading, key_spec);
        } else if (get(key_spec, "source") === "label") {
          let provisional_end = document.lines.length;
          for (const later of headings) {
            if (later.start > heading.start && later.level <= heading.level) {
              provisional_end = later.start;
              break;
            }
          }
          let values = label_occurrences(document, heading.end, provisional_end, key_spec.labels, code_lines);
          values = apply_value_pattern(values, key_spec);
          const distinct = new Set();
          for (const item of values) {
            // `if item.get("value")` truthiness: None and "" are falsy
            if (get(item, "value")) distinct.add(py_strip(String(item.value)));
          }
          evidence = distinct.size === 1 ? distinct.values().next().value : null;
        }
        if (evidence === null) continue;
      }
      const item_diagnostics = [];
      if (!boundary_spec.levels.includes(heading.level)) {
        item_diagnostics.push(diagnostic(
          "heading_level_drift", "warning",
          `record heading level ${heading.level} differs from declared levels`,
          { line: heading.start + 1 },
        ));
      }
      const start = marker !== null ? marker.line : heading.start;
      if (marker !== null) used_markers.add(marker.line);
      candidates.push(new BoundaryCandidate(start, heading, marker, confidence, item_diagnostics));
    }
  }

  for (const marker of markers) {
    if (used_markers.has(marker.line)) continue;
    candidates.push(new BoundaryCandidate(
      marker.line, null, marker, 0.8,
      [diagnostic(
        "marker_fallback", "warning",
        "record identity and boundary recovered from an explicit marker",
        { line: marker.line + 1 },
      )],
    ));
  }

  // Array.prototype.sort is stable, as is Python's list.sort.
  candidates.sort((a, b) => a.start - b.start);
  const deduplicated = [];
  for (const candidate of candidates) {
    if (deduplicated.length && candidate.start === deduplicated[deduplicated.length - 1].start) {
      const existing = deduplicated[deduplicated.length - 1];
      if (existing.heading === null && candidate.heading !== null) existing.heading = candidate.heading;
      if (existing.marker === null && candidate.marker !== null) existing.marker = candidate.marker;
      existing.confidence = Math.max(existing.confidence, candidate.confidence);
      existing.diagnostics.push(...candidate.diagnostics);
    } else {
      deduplicated.push(candidate);
    }
  }
  return deduplicated;
}

export function section_values(document, record_start, record_end, headings, names) {
  const wanted = new Set(Array.from(names, (name) => normalize_label(name)));
  const inside = headings.filter((heading) => record_start < heading.start && heading.start <= record_end);
  const values = [];
  for (let position = 0; position < inside.length; position++) {
    const heading = inside[position];
    if (!wanted.has(normalize_label(heading.text))) continue;
    const content_start = heading.end;
    let content_end = record_end + 1;
    for (const later of inside.slice(position + 1)) {
      if (later.level <= heading.level) {
        content_end = Math.min(content_end, later.start);
        break;
      }
    }
    const value = py_strip(document.lines.slice(content_start, Math.max(content_start, content_end)).join(""));
    values.push({ value, line: heading.start + 1 });
  }
  return values;
}

export function regex_field_values(document, start, end, spec, code_lines) {
  const pattern = spec.pattern;
  const group = get(spec, "group");
  const values = [];
  for (let index = start; index < Math.min(end, document.lines.length); index++) {
    if (code_lines.has(index) || document.excluded_lines.has(index)) continue;
    const line = cp_slice(py_rstrip(document.masked_lines[index], "\r\n"), MAX_REGEX_LINE);
    const match = compile_profile_pattern(pattern).search(line);
    if (match) {
      const value = match_group(match, group);
      values.push({ value, line: index + 1 });
    }
  }
  return values;
}

export function apply_value_pattern(values, spec) {
  if (!has(spec, "pattern")) return values;
  const transformed = [];
  for (const item of values) {
    const value = regex_value(spec.pattern, String(item.value), get(spec, "group"));
    if (value !== null) transformed.push({ value, line: get(item, "line") });
  }
  return transformed;
}

export function extract_fields(document, profile, record, headings, code_lines) {
  const key_spec = profile.records.key;
  let body_start = record.start;
  if (record.marker !== null && body_start === record.marker.line) body_start = record.marker.line + 1;
  if (record.heading !== null) body_start = Math.max(body_start, record.heading.end);

  for (const [name, spec] of Object.entries(get(profile, "fields", {}))) {
    const source = spec.source;
    let values = [];
    if (source === "heading") {
      if (record.heading !== null) {
        const pattern = has(spec, "pattern") ? spec.pattern : get(key_spec, "pattern");
        const value = regex_value(pattern, record.heading.text, get(spec, "group"));
        if (value !== null) values.push({ value, line: record.heading.start + 1 });
      }
    } else if (source === "label") {
      values = label_occurrences(document, body_start, record.end + 1, spec.labels, code_lines);
      values = apply_value_pattern(values, spec);
    } else if (source === "section") {
      values = section_values(document, body_start, record.end, headings, spec.headings);
    } else if (source === "body") {
      const value = py_strip(document.lines.slice(body_start, Math.max(body_start, record.end + 1)).join(""));
      if (value) values.push({ value, line: body_start + 1 });
    } else if (source === "regex") {
      values = regex_field_values(document, body_start, record.end + 1, spec, code_lines);
    } else if (source === "column" && record.table_row !== null) {
      const value = get(record.table_row.cells, spec.column);
      if (value !== null) {
        const extracted = regex_value(get(spec, "pattern"), value, get(spec, "group"));
        if (extracted !== null) values.push({ value: extracted, line: record.table_row.start + 1 });
      }
    }
    record.fields[name] = resolve_scalar(name, values, record.diagnostics);
  }
}

export function declared_key(document, profile, start, end, heading, marker, table_row, code_lines) {
  const spec = profile.records.key;
  const source = spec.source;
  if (source === "heading") {
    const value = key_from_heading(heading, spec);
    return [value, value ? { source: "heading", value, line: heading.start + 1 } : null];
  }
  if (source === "marker") {
    const value = marker ? py_strip(marker.key) : null;
    return [value, value ? { source: "marker", value, line: marker.line + 1 } : null];
  }
  if (source === "column") {
    const raw = table_row !== null ? get(table_row.cells, spec.column) : null;
    const value = raw !== null ? regex_value(get(spec, "pattern"), raw, get(spec, "group")) : null;
    return [
      value,
      value !== null && table_row !== null
        ? { source: "column", column: spec.column, value, line: table_row.start + 1 }
        : null,
    ];
  }
  let occurrences = label_occurrences(document, start, end + 1, spec.labels, code_lines);
  occurrences = apply_value_pattern(occurrences, spec);
  const unique = new Set();
  for (const item of occurrences) {
    const v = get(item, "value");
    if (v !== null && v !== "") unique.add(py_strip(String(item.value)));
  }
  if (unique.size === 1) {
    const value = unique.values().next().value;
    const first = occurrences.find((item) => py_strip(String(item.value)) === value);
    return [value, { source: "label", value, line: first.line }];
  }
  return [null, occurrences.length ? { source: "label-conflict", values: occurrences } : null];
}

export function build_records(document, profile, headings, code_lines, markers, tables) {
  const diagnostics = [];
  const boundaries = collect_boundaries(document, profile, headings, code_lines, markers, tables);
  const records = [];
  const allow_incomplete = get(get(profile, "tolerance", {}), "incomplete", false);

  if (boundaries.length === 0) {
    diagnostics.push(diagnostic("no_records", "warning", "no record boundaries matched the current profile"));
  }

  for (let position = 0; position < boundaries.length; position++) {
    const boundary = boundaries[position];
    let end = boundary.fixed_end;
    if (end === null) {
      end = position + 1 < boundaries.length ? boundaries[position + 1].start - 1 : document.lines.length - 1;
    }
    const item_diagnostics = [...boundary.diagnostics];
    let [value, evidence] = declared_key(
      document, profile, boundary.start, end, boundary.heading, boundary.marker,
      boundary.table_row, code_lines,
    );
    const identity_evidence = [];
    const key_conflict = Boolean(evidence && evidence.source === "label-conflict");
    if (evidence) {
      if (key_conflict) {
        for (const item of get(evidence, "values", [])) {
          identity_evidence.push({ source: "label", value: get(item, "value"), line: get(item, "line") });
        }
        item_diagnostics.push(diagnostic(
          "key_conflict", "warning",
          "declared key labels contain conflicting values; record is candidate-only",
          { line: boundary.start + 1, details: { evidence: identity_evidence } },
        ));
      } else {
        identity_evidence.push(evidence);
      }
    }
    const marker_value = boundary.marker ? py_strip(boundary.marker.key) : null;
    if (marker_value && !identity_evidence.some(
      (item) => item.source === "marker" && item.value === marker_value,
    )) {
      identity_evidence.push({ source: "marker", value: marker_value, line: boundary.marker.line + 1 });
    }

    const declared_values = new Set();
    if (value) declared_values.add(value);
    if (marker_value) declared_values.add(marker_value);
    let confidence;
    if (key_conflict) {
      value = null;
      confidence = Math.min(boundary.confidence, 0.4);
    } else if (declared_values.size > 1) {
      item_diagnostics.push(diagnostic(
        "marker_conflict", "warning",
        "marker and declared key evidence disagree; record is a candidate only",
        { line: boundary.start + 1, details: { evidence: identity_evidence } },
      ));
      value = null;
      confidence = Math.min(boundary.confidence, 0.4);
    } else if (value === null && marker_value) {
      value = marker_value;
      confidence = Math.min(boundary.confidence, 0.8);
    } else {
      confidence = boundary.confidence;
    }

    if (value === null) {
      item_diagnostics.push(diagnostic(
        "missing_key", "warning", "record has no recoverable key", { line: boundary.start + 1 },
      ));
    }
    if (!allow_incomplete && value !== null && boundary.heading === null && boundary.table_row === null) {
      item_diagnostics.push(diagnostic(
        "incomplete_record", "warning",
        "marker-only record is candidate-only because tolerance.incomplete is false",
        { line: boundary.start + 1 },
      ));
      confidence = Math.min(confidence, 0.4);
    }

    const record = new Record({
      key: value,
      start: boundary.start,
      end: Math.max(boundary.start, end),
      heading: boundary.heading,
      marker: boundary.marker,
      table_row: boundary.table_row,
      fields: {},
      confidence,
      diagnostics: item_diagnostics,
      identity_evidence,
    });
    extract_fields(document, profile, record, headings, code_lines);
    records.push(record);
  }

  const by_key = new Map();
  for (const record of records) {
    if (record.key !== null && record.confidence >= 0.6) {
      if (!by_key.has(record.key)) by_key.set(record.key, []);
      by_key.get(record.key).push(record);
    }
  }
  for (const [key, matches] of by_key) {
    if (matches.length > 1) {
      const locations = matches.map((item) => ({ line: item.start + 1, confidence: item.confidence }));
      diagnostics.push(diagnostic(
        "duplicate_key", "warning", `key ${py_repr(key)} identifies ${matches.length} records`,
        { details: { key, locations } },
      ));
    }
  }
  for (const record of records) diagnostics.push(...record.diagnostics);
  return [records, diagnostics];
}

// Python repr() of a str, as used by f"{key!r}".
function py_repr(s) {
  const quote = s.includes("'") && !s.includes('"') ? '"' : "'";
  let out = quote;
  for (const ch of s) {
    const c = ch.codePointAt(0);
    if (ch === quote || ch === "\\") out += "\\" + ch;
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch === "\t") out += "\\t";
    else if (c < 0x20 || c === 0x7f) out += "\\x" + c.toString(16).padStart(2, "0");
    else out += ch; // non-ASCII printable kept; exotic non-printables (e.g. \x85) not escaped (UNSURE)
  }
  return out + quote;
}

// Python round(x, 2) for the confidence values used here (0.4/0.6/0.8/1.0 and mins thereof).
function round2(x) {
  return Number((Math.round(x * 100 + Number.EPSILON * 0) / 100).toFixed(2));
}

export function serialize_record(document, record) {
  const line_start = record.start + 1;
  const line_end = record.end + 1;
  const offsets = document.byte_offsets;
  const byte_start = offsets[Math.min(record.start, offsets.length - 1)];
  const byte_end_index = Math.min(record.end + 1, offsets.length - 1);
  const payload = {
    key: record.key,
    fields: record.fields,
    line_start,
    line_end,
    byte_start,
    byte_end: offsets[byte_end_index],
    confidence: round2(record.confidence),
    diagnostics: record.diagnostics,
  };
  if (record.identity_evidence.length) payload.identity_evidence = record.identity_evidence;
  return payload;
}

export function extract_current(document) {
  if (document.profile === null || document.profile === undefined) return [[], [...document.diagnostics]];
  const [headings, code_lines, markers, parse_diagnostics] = analyze_markdown(
    document, get(document.profile, "dialect", "commonmark"),
  );
  const [tables, table_diagnostics] = analyze_tables(document, headings);
  const [records, record_diagnostics] = build_records(
    document, document.profile, headings, code_lines, markers, tables,
  );
  const serialized = records.map((record) => serialize_record(document, record));
  return [
    serialized,
    [...document.diagnostics, ...parse_diagnostics, ...table_diagnostics, ...record_diagnostics],
  ];
}

function resolve_nonstrict(p) {
  // pathlib.Path.resolve(strict=False): realpath of the longest existing prefix + remainder.
  const abs = path.resolve(p);
  const rest = [];
  let cur = abs;
  for (;;) {
    try {
      const real = fs.realpathSync(cur);
      return path.join(real, ...rest.reverse());
    } catch {
      const parent = path.dirname(cur);
      if (parent === cur) return abs;
      rest.push(path.basename(cur));
      cur = parent;
    }
  }
}

export function index_path(document) {
  if (document.profile === null || document.profile === undefined || !has(document.profile, "index")) {
    return [null, diagnostic("index_missing", "info", "profile does not declare an index path")];
  }
  const configured = String(document.profile.index);
  if (path.isAbsolute(configured)) {
    return [null, diagnostic("index_unsafe", "error", "index path must be relative to the document")];
  }
  const base = resolve_nonstrict(path.dirname(String(document.path)));
  // String join (not path.join) so ".." is resolved physically by the OS like pathlib does.
  const unresolved = configured === "" ? base : `${base}/${configured}`;
  let lst = null;
  try { lst = fs.lstatSync(unresolved); } catch { lst = null; }
  if (lst && lst.isSymbolicLink()) {
    return [null, diagnostic("index_unsafe", "error", "index path must not be a symlink")];
  }
  let st = null;
  try { st = fs.statSync(unresolved); } catch { st = null; }
  if (st && !st.isFile()) {
    return [null, diagnostic("index_unsafe", "error", "index path must name a regular file")];
  }
  const candidate = resolve_nonstrict(unresolved);
  if (!(candidate === base || candidate.startsWith(base.endsWith("/") ? base : base + "/"))) {
    return [null, diagnostic("index_unsafe", "error", "index path escapes the document directory")];
  }
  const doc_path = String(document.path);
  let same_as_source = candidate === doc_path;
  if (fs.existsSync(candidate) && !same_as_source) {
    try {
      const a = fs.statSync(candidate);
      const b = fs.statSync(doc_path);
      same_as_source = a.ino === b.ino && a.dev === b.dev;
    } catch {
      same_as_source = false;
    }
  }
  if (same_as_source) {
    return [null, diagnostic("index_unsafe", "error", "index path must not overwrite the source")];
  }
  return [candidate, null];
}

export function load_valid_index(document) {
  const [index_file, problem] = index_path(document);
  if (problem) return [null, [problem]];
  if (!fs.existsSync(index_file)) {
    return [null, [diagnostic("index_missing", "info", `index does not exist: ${index_file}`)]];
  }
  let payload;
  try {
    payload = JSON.parse(fs.readFileSync(index_file, "utf-8"));
  } catch (exc) {
    // Message text differs from Python's OSError/JSONDecodeError text (not reproducible).
    return [null, [diagnostic("index_invalid", "warning", `index could not be read: ${exc.message}`)]];
  }
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    return [null, [diagnostic("index_invalid", "warning", "index root must be an object")]];
  }
  const expected = {
    index_schema: INDEX_SCHEMA,
    engine: ENGINE,
    protocol_version: document.profile.version,
    source: String(document.path),
    source_sha256: document.source_hash,
    profile_sha256: document.profile_hash,
  };
  const mismatches = {};
  for (const [key, value] of Object.entries(expected)) {
    const actual = has(payload, key) ? payload[key] : null;
    if (actual !== value) mismatches[key] = { expected: value, actual };
  }
  if (Object.keys(mismatches).length) {
    const code = has(mismatches, "source_sha256") || has(mismatches, "profile_sha256")
      ? "index_stale" : "index_invalid";
    return [null, [diagnostic(
      code, "warning",
      "index metadata does not match the current document; current source will be parsed",
      { details: mismatches },
    )]];
  }
  const records = get(payload, "records");
  if (!Array.isArray(records)) {
    return [null, [diagnostic("index_invalid", "warning", "index records must be an array")]];
  }
  return [records, []];
}

export function records_for_query(document) {
  if (document.profile === null || document.profile === undefined) return [[], [...document.diagnostics]];
  if ((document.profile_source || "").startsWith(TEMPORARY_PROFILE_PREFIX)) {
    const [records, diagnostics] = extract_current(document);
    const confidence_cap = document.profile_source.endsWith("explicit") ? 0.9 : 0.8;
    for (const item of records) {
      item.confidence = Math.min(confidence_cap, Number(get(item, "confidence", 0.0)));
    }
    return [records, diagnostics];
  }
  const [cached, index_diagnostics] = load_valid_index(document);
  const [records, diagnostics] = extract_current(document);
  if (cached !== null) {
    if (normalized_json(cached).equals(normalized_json(records))) {
      index_diagnostics.push(diagnostic("index_verified", "info", "index matched a fresh source extraction"));
    } else {
      index_diagnostics.push(diagnostic(
        "index_invalid", "warning",
        "index records differ from current source extraction and were ignored",
      ));
    }
  }
  return [records, [...diagnostics, ...index_diagnostics]];
}

export function status_for(records, { invalid = false } = {}) {
  if (invalid) return "invalid";
  if (!records.length) return "not_found";
  return records.length === 1 ? "matched" : "ambiguous";
}

export function error_diagnostics(items) {
  return items.some((item) => get(item, "severity") === "error");
}
