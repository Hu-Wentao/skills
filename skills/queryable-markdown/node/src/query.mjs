// Port of mdq.py lines 3720-4269 (command_query .. sample_record_keys). Python names are kept.
// Temporary selectors are out of scope for the Node port: they fail closed via unsupported_in_node.
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { diagnostic, casefold, py_strip } from "./common.mjs";
import { TEMPORARY_PROFILE_PREFIX } from "./profile.mjs";
import { read_document, analyze_markdown, analyze_tables, table_key_candidates } from "./document.mjs";
import { regex_value, records_for_query, status_for, error_diagnostics } from "./records.mjs";
import {
  emit, emit_query_result, output_selection_diagnostics, pyget, py_truthy, py_repr, py_str,
} from "./output.mjs";

const hasOwn = (o, k) => o !== null && typeof o === "object" && Object.prototype.hasOwnProperty.call(o, k);

// getattr(args, name, None) / argparse dest lookup; a missing option is None.
const getattr = (args, name) => (args[name] === undefined ? null : args[name]);

function unsupported_in_node(feature) {
  return diagnostic("unsupported_in_node", "error", `${feature} are not supported by the Node port`);
}

// Python float(): numbers or numeric strings.
const pyfloat = (value) => Number(value);
const pyint = (value) => Math.trunc(Number(value));

// Python max(iterable, default=...) over numbers.
const max_default = (values, dflt) => (values.length ? Math.max(...values) : dflt);
const min_default = (values, dflt) => (values.length ? Math.min(...values) : dflt);

// ---- mdq.py 3720 ----

export function command_query(args) {
  const document = read_document(args.document);
  const requested = py_strip(args.id);
  // prepare_temporary_profile (mdq.py 3168): a declared profile only gains an "ignored" note;
  // a profile-free document would get an in-memory profile, which the Node port does not support.
  const select = getattr(args, "select");
  let preparation_diagnostics = [];
  let unsupported = null;
  if (document.profile !== null && document.profile !== undefined) {
    const has_selectors = ["record_level", "key_label", "key_pattern", "key_group"].some((name) =>
      py_truthy(getattr(args, name))
    );
    if (has_selectors) {
      document.diagnostics.push(
        diagnostic(
          "temporary_selectors_ignored",
          "info",
          "temporary selectors were ignored because the document declares an mdq profile"
        )
      );
    }
  } else if (!error_diagnostics(document.diagnostics)) {
    unsupported = unsupported_in_node("temporary selectors");
  }
  const selection_diagnostics = output_selection_diagnostics(document, select);
  if (selection_diagnostics.length) {
    emit_query_result(
      {
        status: "invalid",
        count: 0,
        records: [],
        candidates: [],
        diagnostics: [...document.diagnostics, ...preparation_diagnostics, ...selection_diagnostics],
      },
      args.output,
      select
    );
    return 3;
  }
  if (document.profile === null || document.profile === undefined) {
    if (error_diagnostics(document.diagnostics)) {
      emit_query_result(
        { status: "invalid", count: 0, records: [], candidates: [], diagnostics: document.diagnostics },
        args.output,
        select
      );
      return 3;
    }
    // Python continues with line_local_query_results here (temporary selectors): fail closed.
    emit_query_result(
      {
        status: "invalid",
        count: 0,
        records: [],
        candidates: [],
        diagnostics: [...document.diagnostics, ...preparation_diagnostics, unsupported],
      },
      args.output,
      select
    );
    return 3;
  }
  const [records, diagnostics] = records_for_query(document);
  if (error_diagnostics(diagnostics)) {
    emit_query_result(
      { status: "invalid", count: 0, records: [], candidates: [], diagnostics },
      args.output,
      select
    );
    return 3;
  }
  const temporary = (document.profile_source || "").startsWith(TEMPORARY_PROFILE_PREFIX);
  if (temporary) {
    // Only reachable for profiles built by prepare_temporary_profile, which this port never builds.
    emit_query_result(
      {
        status: "invalid",
        count: 0,
        records: [],
        candidates: [],
        diagnostics: [...diagnostics, unsupported_in_node("temporary selectors")],
      },
      args.output,
      select
    );
    return 3;
  }
  const structured = records.filter(
    (item) => pyget(item, "key", null) === requested && pyfloat(pyget(item, "confidence", 0)) >= 0.6
  );
  const candidates = [];
  for (const item of records) {
    const key = pyget(item, "key", null);
    const evidence = pyget(item, "identity_evidence", []);
    const case_candidate = typeof key === "string" && key !== requested && casefold(key) === casefold(requested);
    const evidence_candidate = evidence.some(
      (entry) => casefold(py_strip(py_str(pyget(entry, "value", "")))) === casefold(requested)
    );
    // `item not in structured`: structured holds the same dict objects, so identity is equivalent.
    if (!structured.includes(item) && (case_candidate || evidence_candidate)) {
      const candidate = { ...item };
      candidate.candidate = true;
      candidates.push(candidate);
    }
    // (the `temporary and ...` branch of Python is unreachable here: temporary is false)
  }
  if (!structured.length && !temporary) {
    const [headings, _code_lines, _markers, table_parse_diagnostics] = analyze_markdown(document, "gfm");
    const [tables, table_diagnostics] = analyze_tables(document, headings);
    diagnostics.push(...table_parse_diagnostics, ...table_diagnostics);
    for (const table of tables) {
      for (const key_candidate of table_key_candidates(table)) {
        const column = key_candidate.column;
        for (const row of table.rows) {
          const cell = row.cells instanceof Map ? row.cells.get(column) : row.cells[column];
          const value = regex_value(key_candidate.pattern, cell, key_candidate.group);
          if (value === requested) {
            candidates.push({
              key: null,
              fields: { [column]: cell },
              line_start: row.start + 1,
              line_end: row.end,
              byte_start: document.byte_offsets[row.start],
              byte_end: document.byte_offsets[row.end],
              confidence: 0.5,
              candidate: true,
              identity_evidence: [{ source: "table-column", column, value: requested, line: row.start + 1 }],
              diagnostics: [
                diagnostic(
                  "table_identity_candidate",
                  "warning",
                  "the requested ID is a unique table-row candidate but the contract does not declare table rows",
                  { line: row.start + 1 }
                ),
              ],
            });
          }
        }
      }
    }
    if (candidates.length) {
      diagnostics.push(
        diagnostic(
          "record_granularity_mismatch",
          "warning",
          "the requested identity is nested inside a table covered by a broader record boundary"
        )
      );
    }
  }
  if (structured.length > 1) {
    diagnostics.push(
      diagnostic("ambiguous_match", "warning", `exact key ${py_repr(requested)} matched ${structured.length} records`)
    );
  } else if (!structured.length) {
    diagnostics.push(diagnostic("no_match", "info", `no exact record key matched ${py_repr(requested)}`));
  }
  const output_status = emit_query_result(
    {
      status: status_for(structured),
      count: structured.length,
      records: structured,
      candidates,
      diagnostics,
    },
    args.output,
    select
  );
  return output_status || 0;
}

export function searchable_values(record, field_name) {
  let values;
  if (field_name === null || field_name === undefined) {
    values = [pyget(record, "key", null)];
    values.push(...Object.values(pyget(record, "fields", null) || {}));
  } else if (field_name === "key") {
    values = [pyget(record, "key", null)];
  } else {
    values = [pyget(pyget(record, "fields", null) || {}, field_name, null)];
  }
  return values.filter((value) => value !== null && value !== undefined).map((value) => py_str(value));
}

export function query_matches(records, spec, value) {
  const match = spec.match;
  const field_name = match.source === "key" ? "key" : match.field;
  const operator = pyget(match, "operator", "eq");
  const selected = [];
  for (const record of records) {
    const values = searchable_values(record, field_name);
    let matched;
    if (operator === "eq") matched = values.some((item) => item === value);
    else matched = values.some((item) => casefold(item).includes(casefold(value)));
    if (matched) selected.push(record);
  }
  return selected;
}

export function project_query_record(record, selected) {
  const projected = { ...record };
  if (selected !== null && selected !== undefined) {
    const fields = pyget(record, "fields", null) || {};
    const out = {};
    for (const name of selected) out[name] = pyget(fields, name, null);
    projected.fields = out;
  }
  return projected;
}

export function query_quality(records, expect) {
  const line_sizes = records.map((item) =>
    Math.max(0, pyint(pyget(item, "line_end", 0)) - pyint(pyget(item, "line_start", 0)) + 1)
  );
  const byte_sizes = records.map((item) =>
    Math.max(0, pyint(pyget(item, "byte_end", 0)) - pyint(pyget(item, "byte_start", 0)))
  );
  const confidences = records.map((item) => pyfloat(pyget(item, "confidence", 0)));
  const structured = records.every(
    (item) => pyget(item, "key", null) !== null && pyfloat(pyget(item, "confidence", 0)) >= 0.6
  );
  const metrics = {
    matches: records.length,
    max_record_lines: max_default(line_sizes, 0),
    max_record_bytes: max_default(byte_sizes, 0),
    total_bytes: byte_sizes.reduce((a, b) => a + b, 0),
    min_confidence: min_default(confidences, 1.0),
    structured,
  };
  const violations = [];
  const comparisons = {
    max_record_lines: [metrics.max_record_lines, "query_record_span_exceeded"],
    max_record_bytes: [metrics.max_record_bytes, "query_record_payload_exceeded"],
    max_total_bytes: [metrics.total_bytes, "query_total_payload_exceeded"],
  };
  for (const [key, [actual, code]] of Object.entries(comparisons)) {
    if (hasOwn(expect, key) && actual > expect[key]) {
      violations.push(
        diagnostic(code, "warning", `query quality limit ${key} was exceeded`, {
          details: { expected: expect[key], actual },
        })
      );
    }
  }
  if (pyget(expect, "structured", null) === true && records.length && !structured) {
    violations.push(diagnostic("query_unstructured_result", "warning", "query returned candidate-only evidence"));
  }
  if (hasOwn(expect, "min_confidence") && confidences.length && metrics.min_confidence < pyfloat(expect.min_confidence)) {
    violations.push(
      diagnostic("query_confidence_below_minimum", "warning", "query result confidence is below the declared minimum", {
        details: { expected: expect.min_confidence, actual: metrics.min_confidence },
      })
    );
  }
  return [{ status: violations.length ? "failed" : "passed", metrics }, violations];
}

export function command_run(args) {
  const document = read_document(args.document);
  if (document.profile === null || document.profile === undefined || document.profile.version !== 2) {
    emit_query_result(
      {
        schema: "mdq.query.v2",
        status: "invalid",
        count: 0,
        records: [],
        diagnostics: [
          ...document.diagnostics,
          diagnostic("query_contract_missing", "error", "named queries require an mdq v2 contract"),
        ],
      },
      args.output
    );
    return 3;
  }
  const queries = document.profile.queries || {};
  const spec = hasOwn(queries, args.query) ? queries[args.query] : null;
  if (spec === null || spec === undefined) {
    emit_query_result(
      {
        schema: "mdq.query.v2",
        status: "invalid",
        count: 0,
        records: [],
        diagnostics: [diagnostic("unknown_query", "error", `query ${py_repr(args.query)} is not declared`)],
      },
      args.output
    );
    return 3;
  }
  const when = pyget(spec, "when", null);
  if (py_truthy(when) && regex_value(when.pattern, args.value, null) === null) {
    emit_query_result(
      {
        schema: "mdq.query.v2",
        status: "invalid",
        count: 0,
        records: [],
        diagnostics: [
          diagnostic("query_input_mismatch", "error", "query value does not satisfy the declared input pattern"),
        ],
      },
      args.output
    );
    return 3;
  }
  const [records, diagnostics] = records_for_query(document);
  if (error_diagnostics(diagnostics)) {
    emit_query_result(
      { schema: "mdq.query.v2", status: "invalid", count: 0, records: [], diagnostics },
      args.output
    );
    return 3;
  }
  const matched = query_matches(records, spec, args.value);
  const [quality, violations] = query_quality(matched, pyget(spec, "expect", {}));
  diagnostics.push(...violations);
  const selected = pyget(spec, "select", null);
  emit_query_result(
    {
      schema: "mdq.query.v2",
      status: matched.length ? "matched" : "not_found",
      query: args.query,
      value: args.value,
      count: matched.length,
      records: matched.map((item) => project_query_record(item, selected)),
      quality,
      diagnostics,
    },
    args.output
  );
  return 0;
}

export function command_verify_queries(args) {
  const document = read_document(args.document);
  if (document.profile === null || document.profile === undefined || document.profile.version !== 2) {
    const diagnostics = [
      ...document.diagnostics,
      diagnostic("query_contract_missing", "error", "query verification requires an mdq v2 contract"),
    ];
    emit({ schema: "mdq.verify.v2", status: "invalid", valid: false, checks: [], diagnostics });
    return 3;
  }
  const queries = document.profile.queries || {};
  if (!Object.keys(queries).length) {
    const diagnostics = [
      ...document.diagnostics,
      diagnostic("query_contract_missing", "error", "the document declares no reusable query intents"),
    ];
    emit({ schema: "mdq.verify.v2", status: "invalid", valid: false, checks: [], diagnostics });
    return 3;
  }
  const [records, diagnostics] = records_for_query(document);
  const checks = [];
  // NOTE: JS objects order integer-like keys first; Python dicts keep insertion order.
  for (const [name, spec] of Object.entries(queries)) {
    const field_name = spec.match.source === "key" ? "key" : spec.match.field;
    const buckets = new Map();
    for (const record of records) {
      for (const value of searchable_values(record, field_name)) {
        const when = pyget(spec, "when", null);
        if (py_truthy(when) && regex_value(when.pattern, value, null) === null) continue;
        if (!buckets.has(value)) buckets.set(value, []);
        buckets.get(value).push(record);
      }
    }
    // max(buckets.items(), key=(len, max byte size)): first maximal item wins ties.
    let worst_value = null;
    let worst_records = [];
    let best = null;
    for (const [value, recs] of buckets) {
      const key = [
        recs.length,
        max_default(recs.map((r) => pyint(pyget(r, "byte_end", 0)) - pyint(pyget(r, "byte_start", 0))), 0),
      ];
      if (best === null || key[0] > best[0] || (key[0] === best[0] && key[1] > best[1])) {
        best = key;
        worst_value = value;
        worst_records = recs;
      }
    }
    const [quality, violations] = query_quality(worst_records, pyget(spec, "expect", {}));
    if (pyget(spec.match, "operator", "eq") === "contains") {
      quality.static_analysis = "exact-value lower bound; substring inputs are runtime-verified";
    }
    checks.push({
      query: name,
      distinct_values: buckets.size,
      worst_value,
      quality,
      diagnostics: violations,
    });
    diagnostics.push(...violations);
  }
  const valid = !error_diagnostics(diagnostics) && checks.every((item) => item.quality.status === "passed");
  emit({
    schema: "mdq.verify.v2",
    status: valid ? "verified" : "failed",
    valid,
    checks,
    diagnostics,
  });
  return valid ? 0 : 3;
}

export function run_internal_mdq(...$arguments) {
  // Python re-invokes itself; the Node equivalent re-invokes the Node CLI entry (src/cli.mjs).
  const cli = fileURLToPath(new URL("./cli.mjs", import.meta.url));
  const completed = spawnSync(process.execPath, [cli, ...$arguments], { encoding: "utf-8", maxBuffer: 1 << 30 });
  let payload;
  try {
    payload = JSON.parse(completed.stdout);
  } catch (exc) {
    const detail = py_strip(completed.stderr || "") || py_strip(completed.stdout || "");
    throw new Error(`internal mdq command returned invalid JSON: ${detail}`);
  }
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("internal mdq command returned a non-object JSON payload");
  }
  return [completed.status, payload];
}

export function sample_record_keys(records) {
  const keyed = records.filter((item) => pyget(item, "key", null) !== null).map((item) => py_str(item.key));
  if (!keyed.length) return [];
  const indexes = [...new Set([0, Math.floor(keyed.length / 2), keyed.length - 1])].sort((a, b) => a - b);
  return indexes.map((index) => keyed[index]);
}
