// Port of mdq.py lines 128-442 (output helpers). Python names are kept.
import { writeSync } from "node:fs";
import { diagnostic, py_rstrip } from "./common.mjs";

// ---- small Python-semantics helpers (not in mdq.py; shared with query.mjs) ----

const hasOwn = (o, k) => o !== null && typeof o === "object" && Object.prototype.hasOwnProperty.call(o, k);

// dict.get(key, default): None-valued keys stay None, missing keys give the default.
export function pyget(obj, key, dflt = null) {
  if (obj === null || obj === undefined) return dflt;
  if (obj instanceof Map) return obj.has(key) ? obj.get(key) : dflt;
  return hasOwn(obj, key) ? obj[key] : dflt;
}

// Python truthiness: empty list/dict/str, 0, None, False are falsy ([] is truthy in JS).
export function py_truthy(value) {
  if (value === null || value === undefined || value === false || value === 0 || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (value instanceof Map || value instanceof Set) return value.size > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

// repr() of a str: single quotes unless the text has ' and no ".
export function py_repr(value) {
  if (value === null || value === undefined) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  if (typeof value === "number") return String(value);
  if (Array.isArray(value)) return "[" + value.map(py_repr).join(", ") + "]";
  if (typeof value === "object") {
    return "{" + Object.entries(value).map(([k, v]) => `${py_repr(k)}: ${py_repr(v)}`).join(", ") + "}";
  }
  const text = String(value);
  const quote = text.includes("'") && !text.includes('"') ? '"' : "'";
  let out = quote;
  for (const ch of text) {
    const cp = ch.codePointAt(0);
    if (ch === quote || ch === "\\") out += "\\" + ch;
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch === "\t") out += "\\t";
    else if (ch !== " " && /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}\p{Zl}\p{Zp}\p{Zs}]/u.test(ch)) {
      if (cp < 0x100) out += "\\x" + cp.toString(16).padStart(2, "0");
      else if (cp < 0x10000) out += "\\u" + cp.toString(16).padStart(4, "0");
      else out += "\\U" + cp.toString(16).padStart(8, "0");
    } else out += ch;
  }
  return out + quote;
}

// str(value)
export function py_str(value) {
  return typeof value === "string" ? value : py_repr(value);
}

// format(x, "g")
function format_g(x) {
  if (!Number.isFinite(x)) return String(x);
  if (x === 0) return "0";
  const exp = Math.floor(Math.log10(Math.abs(x)));
  if (exp < -4 || exp >= 6) {
    let [m, e] = x.toExponential(5).split("e");
    if (m.includes(".")) m = m.replace(/0+$/, "").replace(/\.$/, "");
    const sign = e[0] === "-" ? "-" : "+";
    return `${m}e${sign}${e.replace(/^[+-]/, "").padStart(2, "0")}`;
  }
  let s = x.toPrecision(6);
  if (s.includes(".")) s = s.replace(/0+$/, "").replace(/\.$/, "");
  return s;
}

// sys.stdout.write; synchronous so process.exit() right after cannot truncate output.
export function stdout_write(text) {
  const buf = Buffer.from(text, "utf-8");
  let offset = 0;
  while (offset < buf.length) {
    try {
      offset += writeSync(1, buf, offset, buf.length - offset);
    } catch (error) {
      if (error.code === "EAGAIN") continue;
      throw error;
    }
  }
}

// ---- mdq.py 128 ----

export function emit(payload) {
  // json.dump(payload, sys.stdout, ensure_ascii=False, indent=2); sys.stdout.write("\n")
  stdout_write(JSON.stringify(payload, null, 2) + "\n");
}

export const COMPACT_BULK_FIELDS = new Set(["body", "context", "raw"]);
export const COMPACT_INFORMATIONAL_DIAGNOSTICS = new Set([
  "temporary_selectors_applied",
  "temporary_selectors_inferred",
]);

export function output_fields(record, selected_fields, { compact_default } = {}) {
  const fields = { ...(pyget(record, "fields", null) || {}) };
  if (selected_fields !== null && selected_fields !== undefined) {
    const out = {};
    for (const name of selected_fields) out[name] = hasOwn(fields, name) ? fields[name] : null;
    return out;
  }
  if (!compact_default) return fields;
  const concise = {};
  for (const [name, value] of Object.entries(fields)) {
    if (!COMPACT_BULK_FIELDS.has(name)) concise[name] = value;
  }
  return Object.keys(concise).length ? concise : fields;
}

export function project_output_payload(payload, selected_fields, { compact_default = false } = {}) {
  const projected = { ...payload };
  for (const collection of ["records", "candidates"]) {
    if (!hasOwn(payload, collection)) continue;
    projected[collection] = pyget(payload, collection, []).map((record) => ({
      ...record,
      fields: output_fields(record, selected_fields, { compact_default }),
    }));
  }
  return projected;
}

export function output_selection_diagnostics(document, selected_fields) {
  if (!py_truthy(selected_fields)) return [];
  const available = new Set(Object.keys(pyget(document.profile || {}, "fields", {})));
  if (document.profile === null || document.profile === undefined) {
    for (const name of ["body", "context", "title"]) available.add(name);
  }
  return selected_fields
    .filter((name) => !available.has(name))
    .map((name) =>
      diagnostic("unknown_field", "error", `field ${py_repr(name)} is not available for output projection`)
    );
}

export function* iter_result_diagnostics(payload) {
  yield* pyget(payload, "diagnostics", []);
  for (const collection of ["records", "candidates", "documents"]) {
    for (const item of pyget(payload, collection, [])) {
      yield* pyget(item, "diagnostics", []);
    }
  }
}

export function compact_diagnostic_lines(payload) {
  const lines = [];
  const seen = new Set();
  for (const item of iter_result_diagnostics(payload)) {
    const severity = py_str(pyget(item, "severity", "info"));
    const code = py_str(pyget(item, "code", "unknown"));
    if (severity === "info" && !COMPACT_INFORMATIONAL_DIAGNOSTICS.has(code)) continue;
    const location = py_str(item.relative_path || item.document || "");
    const line = py_str(item.line || "");
    const key = JSON.stringify([severity, code, location, line]);
    if (seen.has(key)) continue;
    seen.add(key);
    let suffix = "";
    if (location) suffix += ` ${location}`;
    if (line) suffix += location ? `:${line}` : ` line=${line}`;
    lines.push(`${severity}:${code}${suffix}`);
  }
  return lines;
}

export function compact_value(value) {
  if (value === null || value === undefined) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  // NOTE: Python str(1.0) == "1.0"; JS cannot tell 1.0 from 1.
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  // json.dumps(value, ensure_ascii=False, separators=(",", ":"))
  return JSON.stringify(value);
}

export function emit_compact_field(name, value) {
  const rendered = compact_value(value);
  if (rendered.includes("\n")) {
    // rendered.rstrip(): Python whitespace, not just newlines
    stdout_write(`${name}:\n${py_rstrip(rendered)}\n`);
  } else {
    stdout_write(`${name}: ${rendered}\n`);
  }
}

export function compact_record_location(record) {
  const location = py_str(record.relative_path || record.document || "");
  const start = pyget(record, "line_start", null);
  const end = pyget(record, "line_end", null);
  if (start === null) return location;
  const span = start === end || end === null ? String(start) : `${start}-${end}`;
  return location ? `${location}:${span}` : `lines=${span}`;
}

export function emit_compact_result(payload) {
  const status = py_str(pyget(payload, "status", "unknown"));
  const count = Math.trunc(Number(pyget(payload, "count", pyget(payload, "records", []).length)));
  let summary = `${status} count=${count}`;
  if (py_truthy(payload.tier)) summary += ` tier=${py_str(payload.tier)}`;
  if (hasOwn(payload, "checks")) summary += ` checks=${pyget(payload, "checks", []).length}`;
  if (hasOwn(payload, "documents_scanned")) summary += ` documents=${py_str(pyget(payload, "documents_scanned", 0))}`;
  if (py_truthy(payload.truncated)) summary += " truncated=true";
  stdout_write(summary + "\n");

  const failed_checks = pyget(payload, "checks", [])
    .filter((item) => !pyget(item, "passed", false))
    .map((item) => py_str(pyget(item, "name", null)));
  if (failed_checks.length) stdout_write("failed_checks: " + failed_checks.join(", ") + "\n");
  if (py_truthy(payload.sample_keys)) {
    stdout_write("sample_keys: " + payload.sample_keys.map((item) => py_str(item)).join(", ") + "\n");
  }

  for (const record of pyget(payload, "records", [])) {
    const key = pyget(record, "key", null);
    const location = compact_record_location(record);
    let header = key !== null ? `record ${py_str(key)}` : "record";
    if (location) header += ` ${location}`;
    const confidence = Number(pyget(record, "confidence", 1.0));
    if (confidence < 1.0) header += ` confidence=${format_g(confidence)}`;
    stdout_write(header + "\n");
    for (const [name, value] of Object.entries(pyget(record, "fields", null) || {})) {
      emit_compact_field(name, value);
    }
  }

  for (const record of pyget(payload, "candidates", [])) {
    const key = pyget(record, "key", null);
    const location = compact_record_location(record);
    let header = key !== null ? `candidate ${py_str(key)}` : "candidate";
    if (location) header += ` ${location}`;
    stdout_write(header + "\n");
  }

  const diagnostic_lines = compact_diagnostic_lines(payload);
  if (diagnostic_lines.length) stdout_write("diagnostics: " + diagnostic_lines.join(", ") + "\n");
  if (
    ["ambiguous", "invalid", "partial", "failed"].includes(status) ||
    py_truthy(payload.candidates) ||
    diagnostic_lines.some((line) => line.startsWith("warning:") || line.startsWith("error:"))
  ) {
    stdout_write("details: rerun with --output json\n");
  }
}

export function actionable_diagnostics(payload) {
  const items = [...pyget(payload, "diagnostics", [])];
  for (const record of pyget(payload, "records", [])) items.push(...pyget(record, "diagnostics", []));
  return items.filter((item) => item.severity === "warning" || item.severity === "error");
}

export function minimal_query_payload(payload) {
  const records = pyget(payload, "records", []);
  if (
    pyget(payload, "status", null) !== "matched" ||
    pyget(payload, "count", null) !== 1 ||
    records.length !== 1 ||
    py_truthy(payload.candidates) ||
    actionable_diagnostics(payload).length
  ) {
    return null;
  }
  const record = records[0];
  const minimal = {
    status: "matched",
    count: 1,
    key: pyget(record, "key", null),
    fields: pyget(record, "fields", {}),
    line_start: pyget(record, "line_start", null),
    line_end: pyget(record, "line_end", null),
    confidence: pyget(record, "confidence", null),
  };
  const diagnostic_codes = pyget(payload, "diagnostics", [])
    .filter((item) => py_truthy(item.code))
    .map((item) => item.code);
  if (diagnostic_codes.length) minimal.diagnostics = diagnostic_codes;
  return minimal;
}

export function emit_query_result(payload, output, selected_fields = null) {
  const projected = project_output_payload(payload, selected_fields);
  if (output === "json") {
    emit(projected);
    return null;
  }
  if (output === "minimal") {
    emit(minimal_query_payload(projected) || projected);
    return null;
  }
  if (output === "compact") {
    emit_compact_result(project_output_payload(payload, selected_fields, { compact_default: true }));
    return null;
  }

  const records = pyget(projected, "records", []);
  let reason = null;
  if (pyget(payload, "status", null) !== "matched" || pyget(payload, "count", null) !== 1 || records.length !== 1) {
    reason = "raw output requires exactly one matched record";
  } else if (py_truthy(projected.candidates)) {
    reason = "raw output refuses to hide alternate candidate evidence";
  } else if (actionable_diagnostics(projected).length) {
    reason = "raw output refuses to hide warning or error diagnostics";
  } else {
    const raw = pyget(pyget(records[0], "fields", {}), "raw", null);
    if (typeof raw !== "string") {
      reason = "raw output requires the matched record to declare a string field named 'raw'";
    } else {
      stdout_write(raw);
      if (!raw.endsWith("\n")) stdout_write("\n");
      return null;
    }
  }

  const failure = { ...projected };
  failure.diagnostics = [...pyget(projected, "diagnostics", []), diagnostic("raw_output_unavailable", "error", reason)];
  emit(failure);
  return 5;
}

export function emit_collection_result(payload, output, selected_fields = null) {
  const projected = project_output_payload(payload, selected_fields);
  if (output === "json") {
    emit(projected);
    return;
  }
  emit_compact_result(project_output_payload(payload, selected_fields, { compact_default: true }));
}
