// Port of mdq.py lines 1720-2305 (markdown_literal_regions .. table_profile).
import { readFileSync } from "node:fs";
import path from "node:path";
import MarkdownIt from "markdown-it";
import {
  diagnostic, line_set, py_strip, py_rstrip, splitlines_keepends, utf8_len, compile_py,
} from "./common.mjs";
import { SourceDocument, Heading, Marker, TableRow, MarkdownTable } from "./types.mjs";
import {
  MARKER_RE, ATX_HEADING_RE, SETEXT_RE, GENERIC_ID_PATTERN, parse_profile, field_name_from_header,
} from "./profile.mjs";

// NOTE on positions: columns/indexes used only inside this module (inline code ranges, comment
// positions, literal_comment_positions) are UTF-16 units consistently on both producer and consumer
// sides, so results equal Python's code point arithmetic. Anything that leaves the module
// (masked text, byte_offsets) is computed code point / UTF-8 exact.

// bisect.bisect_right
function bisect_right(a, x) {
  let lo = 0;
  let hi = a.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (x < a[mid]) hi = mid;
    else lo = mid + 1;
  }
  return lo;
}

function escape_re(value) {
  // re.escape equivalent for JS (no "-" escaping: invalid outside classes under the u flag).
  return value.replace(/[.*+?^${}()|[\]\\\/]/g, "\\$&");
}

// Python's \b is Unicode-aware (\w = alnum + "_"); JS \b is ASCII only.
const WORD = "[\\p{L}\\p{N}_]";
const PY_B = `(?:(?<=${WORD})(?!${WORD})|(?<!${WORD})(?=${WORD}))`;

// Python Pattern.search(text, pos) for a "g" regex.
function search_from(re, text, pos = 0) {
  re.lastIndex = pos;
  return re.exec(text);
}

// Adapter for profile.mjs regex objects: PyPattern (preferred) or a native RegExp.
function pm_match(re, text) {
  if (typeof re.match === "function") return re.match(text);
  const m = new RegExp(re.source, re.flags.replace(/[gy]/g, "")).exec(text);
  return m && m.index === 0 ? m : null;
}
function pm_fullmatch(re, text) {
  if (typeof re.fullmatch === "function") return re.fullmatch(text);
  const m = new RegExp(`^(?:${re.source})$`, re.flags.replace(/[gym]/g, "")).exec(text);
  return m;
}
function pm_group(m, k) {
  if (typeof m.group === "function") return m.group(k);
  const v = m[k];
  return v === undefined ? null : v;
}
function pm_groups(m) {
  if (typeof m.groups_ === "function") return m.groups_();
  return Array.from(m).slice(1).map((v) => (v === undefined ? null : v));
}

export function markdown_literal_regions(text, lines) {
  const parser = new MarkdownIt("commonmark", { html: false });
  const tokens = parser.parse(text, {});
  let block_code_lines = new Set();
  let unclosed_fence_line = null;
  const literal_comment_positions = new Set(); // keys "line,column"

  for (const token of tokens) {
    if ((token.type === "fence" || token.type === "code_block") && token.map) {
      const [start, end] = token.map;
      for (const v of line_set(start, end)) block_code_lines.add(v);
      if (token.type === "fence" && end > start) {
        const raw_closing = lines[end - 1];
        if (raw_closing === undefined) throw new RangeError("list index out of range"); // IndexError
        const closing_line = py_rstrip(raw_closing, "\r\n");
        const marker = escape_re(Array.from(token.markup)[0]);
        const closing_re = new RegExp(`${marker}{${Array.from(token.markup).length},}[ \\t]*$`);
        if (!closing_re.test(closing_line)) {
          unclosed_fence_line = unclosed_fence_line === null ? start : Math.min(unclosed_fence_line, start);
        }
      }
    }
    if (token.type !== "inline" || !token.map) continue;
    const [start, end] = token.map;
    const segment_lines = lines.slice(start, end);
    const segment = segment_lines.join("");
    const offsets = [0];
    for (const line of segment_lines) offsets.push(offsets[offsets.length - 1] + line.length);
    const code_ranges = inline_code_ranges(segment);
    let cursor = 0;
    while (true) {
      const position = segment.indexOf("<!--", cursor);
      if (position < 0) break;
      if (code_ranges.some(([begin, finish]) => begin <= position && position < finish)) {
        const local_line = Math.max(0, bisect_right(offsets, position) - 1);
        literal_comment_positions.add(`${start + local_line},${position - offsets[local_line]}`);
      }
      cursor = position + 4;
    }
  }
  return [block_code_lines, unclosed_fence_line, literal_comment_positions];
}

export function parse_document(file_path, raw) {
  // raw.decode("utf-8"): strict, BOM preserved (ignoreBOM keeps U+FEFF in the text).
  const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(raw);
  let lines = splitlines_keepends(text);
  if (lines.length === 0) lines = [""];
  let [lexical_code, unclosed_fence_line, literal_comments] = markdown_literal_regions(text, lines);
  const [masked_text, masked_lines, lexical_code2, unclosed_comment_line, unclosed_opaque_blocks] =
    scan_source_layers(lines, lexical_code, literal_comments);
  lexical_code = lexical_code2;
  const offsets = [0];
  for (const line of lines) offsets.push(offsets[offsets.length - 1] + utf8_len(line));
  const loaded = parse_profile(text, lines);
  return new SourceDocument({
    path: path.resolve(file_path),
    raw,
    text,
    lines,
    masked_text,
    masked_lines,
    lexical_code_lines: lexical_code,
    unclosed_fence_line,
    unclosed_comment_line,
    unclosed_opaque_blocks,
    byte_offsets: offsets,
    profile: loaded.profile,
    profile_source: loaded.source,
    excluded_lines: loaded.excluded_lines,
    diagnostics: loaded.diagnostics,
  });
}

export function read_document(file_path) {
  return parse_document(file_path, readFileSync(file_path));
}

export function inline_code_ranges(line) {
  const ranges = [];
  let cursor = 0;
  while (cursor < line.length) {
    if (line[cursor] !== "`") {
      cursor += 1;
      continue;
    }
    let end = cursor;
    while (end < line.length && line[end] === "`") end += 1;
    const length = end - cursor;
    let search = end;
    let closing = -1;
    const ticks = "`".repeat(length);
    while (search < line.length) {
      const candidate = line.indexOf(ticks, search);
      if (candidate < 0) break;
      const before_same = candidate > 0 && line[candidate - 1] === "`";
      const after_same = candidate + length < line.length && line[candidate + length] === "`";
      if (!before_same && !after_same) {
        closing = candidate;
        break;
      }
      search = candidate + length;
    }
    if (closing < 0) {
      cursor = end;
      continue;
    }
    ranges.push([cursor, closing + length]);
    cursor = closing + length;
  }
  return ranges;
}

export function position_is_literal(line, position, code_ranges) {
  if (code_ranges.some(([start, end]) => start <= position && position < end)) return true;
  let backslashes = 0;
  let cursor = position - 1;
  while (cursor >= 0 && line[cursor] === "\\") {
    backslashes += 1;
    cursor -= 1;
  }
  return backslashes % 2 === 1;
}

// Replace every code point in line[a, b) except "\r"/"\n" by one space (Python mutates a list of
// code points; JS strings are UTF-16, so an astral character must collapse to a single space).
function apply_mask(line, ranges) {
  if (ranges.length === 0) return line;
  let out = "";
  let at = 0;
  for (const [a, b] of ranges) {
    out += line.slice(at, a);
    for (const ch of line.slice(a, b)) out += ch === "\r" || ch === "\n" ? ch : " ";
    at = b;
  }
  return out + line.slice(at);
}

export function scan_source_layers(lines, block_code_lines, literal_comment_positions) {
  const masked_lines = [];
  const excluded_lines = new Set(block_code_lines);
  let opaque = null; // [kind, closing RegExp (g), index]
  let comment_start = null;
  const html_open = new RegExp(`^ {0,3}<(pre|code|script|style)${PY_B}[^>]*>`, "iu");
  const mdx_open = new RegExp(`^ {0,3}<([A-Z][A-Za-z0-9_.:-]*)${PY_B}[^>]*>`, "u");
  const hugo_open = new RegExp(`^ {0,3}\\{\\{[<%][ \\t]*highlight${PY_B}.*[>%]\\}\\}`, "iu");

  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];
    if (opaque !== null) {
      excluded_lines.add(index);
      if (!block_code_lines.has(index) && search_from(opaque[1], line, 0)) opaque = null;
      masked_lines.push(line);
      continue;
    }

    if (comment_start === null) {
      if (block_code_lines.has(index)) {
        masked_lines.push(line);
        continue;
      }

      let opaque_match = html_open.exec(line);
      if (opaque_match) {
        const tag = opaque_match[1];
        const closing = new RegExp(`</${escape_re(tag)}[ \\t]*>`, "giu");
        excluded_lines.add(index);
        if (!search_from(closing, line, opaque_match.index + opaque_match[0].length)) {
          opaque = [`html:${tag.toLowerCase()}`, closing, index];
        }
        masked_lines.push(line);
        continue;
      }
      opaque_match = mdx_open.exec(line);
      if (opaque_match && !py_rstrip(line).endsWith("/>")) {
        const tag = opaque_match[1];
        const closing = new RegExp(`</${escape_re(tag)}[ \\t]*>`, "gu");
        excluded_lines.add(index);
        if (!search_from(closing, line, opaque_match.index + opaque_match[0].length)) {
          opaque = [`mdx:${tag}`, closing, index];
        }
        masked_lines.push(line);
        continue;
      }
      opaque_match = hugo_open.exec(line);
      if (opaque_match) {
        const closing = new RegExp("\\{\\{[<%][ \\t]*/highlight[ \\t]*[>%]\\}\\}", "giu");
        excluded_lines.add(index);
        if (!search_from(closing, line, opaque_match.index + opaque_match[0].length)) {
          opaque = ["hugo:highlight", closing, index];
        }
        masked_lines.push(line);
        continue;
      }
    }

    const mask_ranges = [];
    let cursor = 0;
    if (comment_start !== null) {
      const closing = line.indexOf("-->");
      const stop = closing < 0 ? line.length : closing + 3;
      mask_ranges.push([0, stop]);
      if (closing < 0) {
        masked_lines.push(apply_mask(line, mask_ranges));
        continue;
      }
      comment_start = null;
      cursor = stop;
    }

    const code_ranges = inline_code_ranges(line);
    while (true) {
      let opening = line.indexOf("<!--", cursor);
      while (
        opening >= 0 &&
        (literal_comment_positions.has(`${index},${opening}`) || position_is_literal(line, opening, code_ranges))
      ) {
        opening = line.indexOf("<!--", opening + 4);
      }
      if (opening < 0) break;
      const closing = line.indexOf("-->", opening + 4);
      const stop = closing < 0 ? line.length : closing + 3;
      mask_ranges.push([opening, stop]);
      if (closing < 0) {
        comment_start = index;
        break;
      }
      cursor = stop;
    }
    masked_lines.push(apply_mask(line, mask_ranges));
  }

  const unclosed_opaque = opaque !== null ? [[opaque[2], opaque[0]]] : [];
  const masked_text = masked_lines.join("");
  return [masked_text, masked_lines, excluded_lines, comment_start, unclosed_opaque];
}

export function analyze_markdown(document, dialect = "commonmark") {
  const diagnostics = [];
  const lexical_code = new Set(document.lexical_code_lines);
  const unclosed_line = document.unclosed_fence_line;
  const unclosed_opaque = document.unclosed_opaque_blocks;
  const code_lines = new Set(lexical_code);
  if (unclosed_line !== null) {
    diagnostics.push(
      diagnostic("unclosed_fence", "warning",
        "an unclosed code fence makes the remaining lines non-structural candidates",
        { line: unclosed_line + 1 }),
    );
  }
  if (document.unclosed_comment_line !== null) {
    diagnostics.push(
      diagnostic("unclosed_html_comment", "warning",
        "an unclosed HTML comment makes the remaining lines non-structural candidates",
        { line: document.unclosed_comment_line + 1 }),
    );
  }
  for (const [line, kind] of unclosed_opaque) {
    diagnostics.push(
      diagnostic("unclosed_opaque_block", "warning",
        `an unclosed ${kind} block makes the remaining lines non-structural candidates`,
        { line: line + 1 }),
    );
  }

  const headings = [];
  try {
    const parser = new MarkdownIt("commonmark", { html: false });
    if (dialect === "gfm") parser.enable("table");
    const tokens = parser.parse(document.masked_text, {});
    for (let index = 0; index < tokens.length; index++) {
      const token = tokens[index];
      if ((token.type === "fence" || token.type === "code_block") && token.map) {
        for (const v of line_set(token.map[0], token.map[1])) code_lines.add(v);
      }
      if (token.type === "heading_open" && token.map) {
        const [start, end] = token.map;
        if (document.excluded_lines.has(start) || code_lines.has(start)) continue;
        const level = parseInt(token.tag[1], 10);
        let content = "";
        if (index + 1 < tokens.length && tokens[index + 1].type === "inline") {
          content = py_strip(tokens[index + 1].content);
        }
        headings.push(new Heading({ start, end, level, text: content, source: "ast" }));
      }
    }
  } catch (exc) {
    // markdown-it should be total, but recovery must remain available.
    diagnostics.push(diagnostic("parser_failed", "warning", `Markdown token parsing failed: ${exc}`));
  }

  const known_starts = new Set(headings.map((heading) => heading.start));
  for (let index = 0; index < document.masked_lines.length; index++) {
    const raw_line = document.masked_lines[index];
    if (known_starts.has(index) || code_lines.has(index) || document.excluded_lines.has(index)) continue;
    const line = py_rstrip(raw_line, "\r\n");
    const match = pm_match(ATX_HEADING_RE, line);
    if (match) {
      headings.push(
        new Heading({
          start: index,
          end: index + 1,
          level: Array.from(pm_group(match, 1)).length,
          text: py_strip(pm_group(match, 2)),
          source: "scan",
        }),
      );
      diagnostics.push(
        diagnostic("fallback_scan_used", "warning", "source scan recovered a heading", { line: index + 1 }),
      );
      continue;
    }
    if (index + 1 < document.lines.length && !code_lines.has(index + 1)) {
      const underline = pm_match(SETEXT_RE, py_rstrip(document.masked_lines[index + 1], "\r\n"));
      if (underline && py_strip(line)) {
        headings.push(
          new Heading({
            start: index,
            end: index + 2,
            level: pm_group(underline, 1).startsWith("=") ? 1 : 2,
            text: py_strip(line),
            source: "scan",
          }),
        );
        diagnostics.push(
          diagnostic("fallback_scan_used", "warning", "source scan recovered a Setext heading",
            { line: index + 1 }),
        );
      }
    }
  }

  // list.sort is stable in both languages.
  headings.sort((a, b) => a.start - b.start || a.level - b.level);
  const markers = [];
  const text = document.text;
  const count_nl = (upto) => {
    let n = 0;
    for (let i = text.indexOf("\n"); i >= 0 && i < upto; i = text.indexOf("\n", i + 1)) n += 1;
    return n;
  };
  for (const comment of text.matchAll(/<!--.*?-->/gs)) {
    const marker_match = pm_fullmatch(MARKER_RE, py_strip(comment[0]));
    if (marker_match === null) continue;
    const start_line = count_nl(comment.index);
    const end_line = count_nl(comment.index + comment[0].length);
    if (
      start_line !== end_line ||
      code_lines.has(start_line) ||
      document.excluded_lines.has(start_line) ||
      py_strip(document.masked_lines[start_line])
    ) {
      continue;
    }
    const key = py_strip(pm_groups(marker_match).find((value) => value !== null));
    markers.push(new Marker({ line: start_line, key }));
  }
  return [headings, code_lines, markers, diagnostics];
}

export function analyze_tables(document, headings) {
  const diagnostics = [];
  const tables = [];
  let tokens;
  try {
    tokens = new MarkdownIt("commonmark", { html: false }).enable("table").parse(document.masked_text, {});
  } catch (exc) {
    return [[], [diagnostic("parser_failed", "warning", `Markdown table parsing failed: ${exc}`)]];
  }

  let index = 0;
  while (index < tokens.length) {
    const token = tokens[index];
    if (token.type !== "table_open" || !token.map) {
      index += 1;
      continue;
    }
    const [table_start, table_end] = token.map;
    let cursor = index + 1;
    let headers = [];
    const raw_rows = [];
    while (cursor < tokens.length && tokens[cursor].type !== "table_close") {
      const row_token = tokens[cursor];
      if (row_token.type !== "tr_open" || !row_token.map) {
        cursor += 1;
        continue;
      }
      const [row_start, row_end] = row_token.map;
      const cells = [];
      let header_row = false;
      cursor += 1;
      while (cursor < tokens.length && tokens[cursor].type !== "tr_close") {
        const current = tokens[cursor];
        if (current.type === "th_open") header_row = true;
        if (current.type === "inline") cells.push(py_strip(current.content));
        cursor += 1;
      }
      if (header_row) headers = cells;
      else raw_rows.push([row_start, row_end, cells]);
      cursor += 1;
    }

    if (headers.length === 0) {
      diagnostics.push(
        diagnostic("table_header_missing", "warning", "a GFM table has no recoverable header",
          { line: table_start + 1 }),
      );
      index = cursor + 1;
      continue;
    }
    if (new Set(headers).size !== headers.length) {
      diagnostics.push(
        diagnostic("table_header_duplicate", "warning", "a GFM table has duplicate column names",
          { line: table_start + 1, details: { columns: headers } }),
      );
    }
    const rows = [];
    for (const [row_start, row_end, values] of raw_rows) {
      if (row_end - row_start !== 1) {
        diagnostics.push(
          diagnostic("table_row_multiline", "warning",
            "a table row spans multiple physical lines and is not a stable record",
            { line: row_start + 1 }),
        );
        continue;
      }
      if (values.length !== headers.length) {
        diagnostics.push(
          diagnostic("table_row_width_mismatch", "warning",
            "a table row does not match the declared header width",
            { line: row_start + 1, details: { expected: headers.length, actual: values.length } }),
        );
        continue;
      }
      // dict(zip(headers, values, strict=True)); defineProperty keeps "__proto__" a plain key.
      const cells = {};
      headers.forEach((h, i) => Object.defineProperty(cells, h, { value: values[i], enumerable: true, writable: true, configurable: true }));
      rows.push(new TableRow({ start: row_start, end: row_end, values, cells }));
    }
    const preceding = headings.filter((heading) => heading.start < table_start);
    tables.push(
      new MarkdownTable({
        start: table_start,
        end: table_end,
        header_line: table_start,
        headers,
        rows,
        under_heading: preceding.length ? preceding[preceding.length - 1].text : null,
      }),
    );
    index = cursor + 1;
  }
  return [tables, diagnostics];
}

export function table_key_candidates(table) {
  const candidates = [];
  const id_re = compile_py(String.raw`^(?P<id>${GENERIC_ID_PATTERN})(?:\s+.*)?$`);
  table.headers.forEach((header, position) => {
    const ids = [];
    for (const row of table.rows) {
      const value = py_strip(row.values[position]);
      const match = id_re.match(value);
      if (match !== null) ids.push(match.group("id"));
    }
    if (ids.length >= 2 && ids.length === table.rows.length && new Set(ids).size === ids.length) {
      candidates.push({
        column: header,
        pattern: String.raw`^(?P<id>${GENERIC_ID_PATTERN})(?:\s+.*)?$`,
        group: "id",
        count: ids.length,
        unique: true,
        samples: ids.slice(0, 3),
      });
    }
  });
  return candidates;
}

export function table_profile(table, key_candidate) {
  const key_column = key_candidate.column;
  const fields = {};
  const used = new Set();
  table.headers.forEach((header, position) => {
    let name;
    let spec;
    if (header === key_column) {
      name = "title";
      spec = {
        source: "column",
        column: header,
        pattern: String.raw`^(?:${GENERIC_ID_PATTERN})(?:\s+(?P<title>.*))?$`,
        group: "title",
      };
    } else {
      name = field_name_from_header(header, position);
      const base = name;
      let suffix = 2;
      while (used.has(name) || name === "title") {
        name = `${base}_${suffix}`;
        suffix += 1;
      }
      spec = { source: "column", column: header };
    }
    used.add(name);
    fields[name] = spec;
  });
  const names = Object.keys(fields);
  const selected = names.slice(0, Math.min(6, names.length));
  const boundary = { source: "table-row", columns: table.headers };
  if (table.under_heading) boundary.under_heading = table.under_heading;
  return {
    version: 2,
    dialect: "gfm",
    records: {
      boundary,
      key: {
        source: "column",
        column: key_column,
        pattern: key_candidate.pattern,
        group: key_candidate.group,
      },
    },
    fields,
    queries: {
      by_id: {
        when: { pattern: String.raw`^${GENERIC_ID_PATTERN}$` },
        match: { source: "key", operator: "eq" },
        select: selected,
        expect: { max_record_lines: 1, max_record_bytes: 16384, structured: true },
      },
    },
    maintenance: {
      query_contract: { mode: "propose", allow: ["queries", "fields", "records"], max_changes_per_run: 1 },
    },
    tolerance: { incomplete: true },
  };
}
