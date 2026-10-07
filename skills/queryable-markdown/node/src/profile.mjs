// Port of mdq.py lines 36-127, 442-735 (non-dataclass part) and 823-1720 (parse_profile .. validate_profile).
import { existsSync, realpathSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as YAML from "yaml";
import {
  diagnostic,
  sha256,
  normalized_json,
  line_set,
  set_union,
  py_strip,
  py_lstrip,
  py_isspace,
  utf8_len,
  casefold,
  compile_py,
  PyRegexError,
  PyRegexUnsupported,
} from "./common.mjs";
import { ProfileLoad } from "./types.mjs";

// normalized_json / sha256 are defined in common.mjs (mdq.py 442-449); re-exported, not redefined.
export { normalized_json, sha256 };

// ---------------------------------------------------------------------------
// Constants (mdq.py 36-80)
// ---------------------------------------------------------------------------
export const INDEX_SCHEMA = 1;
export const MAX_PROFILE_BYTES = 64 * 1024;
export const MAX_PATTERN_LENGTH = 512;
export const MAX_REGEX_LINE = 8 * 1024;
export const REGEX_TIMEOUT_SECONDS = 0.05;

// Python \s (str patterns) whitespace set, used instead of JS \s.
const PY_WS = "\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
// Python \b/\w for str patterns is Unicode aware (letters, numbers, underscore).
const PY_W = "\\p{L}\\p{N}_";

// NOTE: These are non-global RegExp objects (Python compiled patterns are stateless).
// Callers needing finditer must clone with a "g" flag: new RegExp(RE.source, RE.flags + "g").
// Python `$` (no MULTILINE) matches at end or before a final "\n": emulated with (?=\n?$).
// Python `.` excludes only "\n": emulated with [^\n].
export const PROFILE_COMMENT_RE = /<!--[ \t]*mdq[ \t]*\r?\n(?<body>.*?)(?:\r?\n)?[ \t]*-->/s;
export const MARKER_RE = new RegExp(
  `<!--[ \\t]*mdq:record[ \\t]+id[ \\t]*=[ \\t]*(?:"([^"]+)"|'([^']+)'|([^${PY_WS}>]+))[ \\t]*-->`,
  "i",
);
export const ATX_HEADING_RE = /^[ \t]{0,3}(#{1,6})[ \t]+([^\n]+?)[ \t]*#*[ \t]*(?=\n?$)/;
export const SETEXT_RE = /^[ \t]{0,3}(=+|-+)[ \t]*(?=\n?$)/;
export const GENERIC_ID_PATTERN = "[A-Za-z][A-Za-z0-9_.]*(?:-[A-Za-z0-9_.]+)*-[0-9]+";
export const GENERIC_ID_RE = new RegExp(
  `(?<![${PY_W}])(${GENERIC_ID_PATTERN})(?![${PY_W}])`,
  "u",
);
export const TEMPORARY_PROFILE_PREFIX = "temporary-";
export const SHARED_PROFILE_PREFIX = "shared-profile:";
export const PROFILE_REFERENCE_RE =
  /^(?<namespace>[a-z][a-z0-9-]*)\/(?<name>[a-z][a-z0-9._-]*-v(?<version>[1-9][0-9]*))$/;
// Python-syntax pattern string (goes through compile_py later), so it stays in Python syntax.
export const TEMPORARY_GENERIC_KEY_PATTERN =
  `^[ \\t]*(?P<id>${GENERIC_ID_PATTERN})` + "(?=$|[ \\t:：—–-])";
export const YAML_MDQ_DECLARATION_RE = /(?<=^|\n)mdq[ \t]*:/; // Python (?m)^ : only after "\n"
export const TOML_MDQ_DECLARATION_RE = /(?<=^|\n)(?:mdq[ \t]*=|\[mdq(?:\.|\]))/;
export const INFERRED_KEY_LABELS = new Set([
  "id",
  "key",
  "identifier",
  "recordid",
  "requirementid",
  "reqid",
  "ticketid",
  "编号",
  "标识",
  "标识符",
  "需求id",
  "需求编号",
  "唯一键",
]);

// ---------------------------------------------------------------------------
// Python-ish helpers (local)
// ---------------------------------------------------------------------------
export class YAMLError extends Error {}
export class ValueError extends Error {}
export class PyTypeError extends Error {}

const has = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
const is_dict = (v) =>
  v !== null && typeof v === "object" && !Array.isArray(v) && !(v instanceof Date) &&
  !(v instanceof Map) && !(v instanceof Set) && !(v instanceof Uint8Array);
const dict_get = (obj, key, dflt = null) => (has(obj, key) ? obj[key] : dflt); // dict.get
const setdefault = (obj, key, dflt) => {
  if (!has(obj, key)) obj[key] = dflt;
  return obj[key];
};
const is_int = (v) => typeof v === "number" && Number.isInteger(v); // type(v) is int
const py_truthy = (v) => {
  if (v === null || v === undefined || v === false || v === 0 || v === "") return false;
  if (Array.isArray(v)) return v.length > 0;
  if (is_dict(v)) return Object.keys(v).length > 0;
  return true;
};
const count_newlines = (text, start, end) => {
  let n = 0;
  for (let i = start; i < Math.min(end, text.length); i++) if (text.charCodeAt(i) === 10) n++;
  return n;
};
// Python slicing text[:N] counts code points, JS counts UTF-16 units.
const cp_prefix = (text, n) => {
  if (text.length <= n) return text;
  const arr = Array.from(text);
  return arr.length <= n ? text : arr.slice(0, n).join("");
};
const cp_len = (text) => Array.from(text).length;

// repr() for the value shapes that reach diagnostics.
export function py_repr(value) {
  if (value === null || value === undefined) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(value);
  if (typeof value === "string") {
    const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
    let out = quote;
    for (const ch of value) {
      const cp = ch.codePointAt(0);
      if (ch === "\\") out += "\\\\";
      else if (ch === quote) out += "\\" + quote;
      else if (ch === "\n") out += "\\n";
      else if (ch === "\r") out += "\\r";
      else if (ch === "\t") out += "\\t";
      else if (cp < 0x20 || cp === 0x7f) out += "\\x" + cp.toString(16).padStart(2, "0");
      else out += ch;
    }
    return out + quote;
  }
  if (Array.isArray(value)) return "[" + value.map(py_repr).join(", ") + "]";
  if (is_dict(value)) {
    return "{" + Object.keys(value).map((k) => `${py_repr(k)}: ${py_repr(value[k])}`).join(", ") + "}";
  }
  return String(value);
}

// ---------------------------------------------------------------------------
// DuplicateKeyLoader / load_yaml (mdq.py 81-127, 452-453)
// PyYAML SafeLoader + alias ban + duplicate-key ban, via the `yaml` package.
// ---------------------------------------------------------------------------
// PyYAML's bool resolver only knows yes/no/true/false/on/off in these exact case variants;
// the `yaml` package's YAML 1.1 schema additionally maps bare y/Y/n/N to booleans (diverges), so the
// bool tags are replaced.
const BOOL_TAG = "tag:yaml.org,2002:bool";
const PY_TRUE_RE = /^(?:yes|Yes|YES|true|True|TRUE|on|On|ON)$/;
const PY_FALSE_RE = /^(?:no|No|NO|false|False|FALSE|off|Off|OFF)$/;
function pyyaml_bool_tags(tags) {
  const kept = tags.filter((t) => t.tag !== BOOL_TAG);
  const make = (test, value) => ({
    identify: (v) => v === value,
    default: true,
    tag: BOOL_TAG,
    test,
    resolve: () => new YAML.Scalar(value),
    stringify: (item) => (item.source ? item.source : String(value)),
  });
  return [...kept, make(PY_TRUE_RE, true), make(PY_FALSE_RE, false)];
}

export function load_yaml(text) {
  let doc;
  try {
    doc = YAML.parseDocument(text, {
      version: "1.1",
      uniqueKeys: true,
      maxAliasCount: 0,
      prettyErrors: false,
      customTags: pyyaml_bool_tags,
    });
  } catch (error) {
    throw new YAMLError(String(error.message ?? error));
  }
  if (doc.errors.length) throw new YAMLError(String(doc.errors[0].message));
  // Unknown/unsafe tags: SafeLoader raises ConstructorError, `yaml` only warns.
  if (doc.warnings.length) throw new YAMLError(String(doc.warnings[0].message));
  let alias = null;
  YAML.visit(doc, {
    Alias(_key, node) {
      alias = node;
      return YAML.visit.BREAK;
    },
  });
  if (alias !== null) {
    throw new YAMLError("while composing a profile: YAML aliases are not allowed in mdq profiles");
  }
  try {
    return doc.toJS({ maxAliasCount: 0 });
  } catch (error) {
    if (error instanceof RangeError) throw error; // RecursionError equivalent
    throw new YAMLError(String(error.message ?? error));
  }
}

// ---------------------------------------------------------------------------
// shared profiles (mdq.py 456-565)
// ---------------------------------------------------------------------------
let _skills_root_override = null;
// Python: Path(__file__).resolve().parents[2], i.e. the directory that contains `queryable-markdown/`.
// Bundled at <skills>/queryable-markdown/scripts/mdq.mjs or unbundled at <skills>/queryable-markdown/node/src/*.mjs:
// walk up to the `queryable-markdown` directory and take its parent. set_skills_root() overrides.
export function set_skills_root(root) {
  _skills_root_override = root === null ? null : path.resolve(root);
}
function default_skills_root() {
  let dir = path.dirname(realpathSync(fileURLToPath(import.meta.url)));
  for (let i = 0; i < 6; i++) {
    if (path.basename(dir) === "queryable-markdown") return path.dirname(dir);
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  // Fallback: bundled layout <skills>/queryable-markdown/scripts/<file>
  return path.dirname(path.dirname(path.dirname(realpathSync(fileURLToPath(import.meta.url)))));
}

export function shared_profile_path(reference) {
  const match = PROFILE_REFERENCE_RE.exec(reference);
  if (match === null) return null;
  // Shared profiles are shipped as sibling skill assets. A document can
  // select a versioned name, but it cannot provide an arbitrary filesystem
  // path, URL, import, or executable source.
  const skills_root = _skills_root_override ?? default_skills_root();
  let resolved = path.resolve(
    skills_root,
    match.groups.namespace,
    "assets",
    "mdq-profiles",
    `${match.groups.name}.yaml`,
  );
  try {
    resolved = realpathSync(resolved); // Path.resolve() follows symlinks when they exist
  } catch {
    /* non-existent: keep lexical resolution (strict=False) */
  }
  let root_real = skills_root;
  try {
    root_real = realpathSync(skills_root);
  } catch {
    /* keep */
  }
  const rel = path.relative(root_real, resolved);
  if (rel === ".." || rel.startsWith(".." + path.sep) || path.isAbsolute(rel)) return null;
  return resolved;
}

function is_file(p) {
  try {
    return statSync(p).isFile();
  } catch {
    return false;
  }
}

export function load_shared_profile(reference, diagnostics) {
  const match = PROFILE_REFERENCE_RE.exec(reference);
  if (match === null) {
    diagnostics.push(
      diagnostic("profile_reference_invalid", "error", "shared mdq profile references must use namespace/name-vN", {
        details: { reference },
      }),
    );
    return null;
  }

  const p = shared_profile_path(reference);
  if (p === null || !is_file(p)) {
    diagnostics.push(
      diagnostic("profile_reference_missing", "error", `shared mdq profile ${py_repr(reference)} was not found`, {
        details: { reference },
      }),
    );
    return null;
  }

  const local_diagnostics = [];
  let root;
  try {
    const raw = readFileSync(p);
    if (raw.length > MAX_PROFILE_BYTES) throw new ValueError(`profile exceeds ${MAX_PROFILE_BYTES} bytes`);
    // ignoreBOM keeps a leading U+FEFF like Python's bytes.decode("utf-8"); fatal = UnicodeDecodeError.
    const decoded = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(raw);
    const loaded = load_yaml(decoded);
    root = py_truthy(loaded) ? loaded : {};
  } catch (exc) {
    if (
      exc instanceof YAMLError || exc instanceof ValueError || exc instanceof PyTypeError ||
      exc instanceof RangeError || exc instanceof TypeError || (exc && exc.code && typeof exc.code === "string" && exc.syscall)
    ) {
      diagnostics.push(
        diagnostic(
          "profile_reference_invalid",
          "error",
          `shared mdq profile ${py_repr(reference)} could not be loaded: ${exc.message}`,
          { details: { reference, path: String(p) } },
        ),
      );
      return null;
    }
    throw exc;
  }

  if (!is_dict(root)) {
    diagnostics.push(
      diagnostic("profile_reference_invalid", "error", "shared mdq profile must contain a mapping", {
        details: { reference, path: String(p) },
      }),
    );
    return null;
  }

  const expected_version = parseInt(match.groups.version, 10);
  const metadata = { "x-profile-id": reference, "x-profile-version": expected_version };
  for (const [key, expected] of Object.entries(metadata)) {
    if (dict_get(root, key) !== expected) {
      local_diagnostics.push(
        diagnostic(
          "profile_reference_invalid",
          "error",
          `shared mdq profile field ${py_repr(key)} does not match its reference`,
          { details: { reference, path: String(p), expected, actual: dict_get(root, key) } },
        ),
      );
    }
  }
  diagnostics.push(...local_diagnostics);
  if (local_diagnostics.some((item) => item.severity === "error")) return null;
  return root;
}

// ---------------------------------------------------------------------------
// JSON front matter helpers (mdq.py 568-654)
// Python json.JSONDecoder(object_pairs_hook=unique_json_object).raw_decode, ported by hand because
// JSON.parse neither reports the end offset nor rejects duplicate keys. Accepts NaN/Infinity like Python.
// ---------------------------------------------------------------------------
export class JSONDecodeError extends ValueError {}

export function unique_json_object(pairs) {
  const result = {};
  for (const [key, value] of pairs) {
    if (has(result, key)) throw new ValueError(`duplicate JSON key ${py_repr(key)}`);
    result[key] = value;
  }
  return result;
}

function json_error(msg, doc, pos) {
  const lineno = count_newlines(doc, 0, pos) + 1;
  const last = doc.lastIndexOf("\n", pos - 1);
  return new JSONDecodeError(`${msg}: line ${lineno} column ${last < 0 ? pos + 1 : pos - last} (char ${pos})`);
}

const JSON_WS = " \t\n\r";
function json_skip_ws(s, i) {
  while (i < s.length && JSON_WS.includes(s[i])) i++;
  return i;
}

function json_scan_string(s, begin) {
  // begin points just after the opening quote; returns [value, endIndexAfterClosingQuote]
  let i = begin;
  while (i < s.length) {
    const c = s[i];
    if (c === '"') {
      const token = s.slice(begin - 1, i + 1);
      try {
        return [JSON.parse(token), i + 1];
      } catch {
        throw json_error("Invalid \\escape", s, begin - 1);
      }
    }
    if (c === "\\") {
      i += 2;
      continue;
    }
    if (s.charCodeAt(i) < 0x20) throw json_error("Invalid control character at", s, i);
    i++;
  }
  throw json_error("Unterminated string starting at", s, begin - 1);
}

const JSON_NUMBER = /-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?/y;
function json_scan_value(s, i, depth) {
  if (depth > 900) throw new RangeError("maximum recursion depth exceeded");
  const c = s[i];
  if (c === '"') return json_scan_string(s, i + 1);
  if (c === "{") {
    const pairs = [];
    let j = json_skip_ws(s, i + 1);
    if (s[j] === "}") return [unique_json_object(pairs), j + 1];
    for (;;) {
      if (s[j] !== '"') throw json_error("Expecting property name enclosed in double quotes", s, j);
      let key;
      [key, j] = json_scan_string(s, j + 1);
      j = json_skip_ws(s, j);
      if (s[j] !== ":") throw json_error("Expecting ':' delimiter", s, j);
      j = json_skip_ws(s, j + 1);
      let value;
      [value, j] = json_scan_value(s, j, depth + 1);
      pairs.push([key, value]);
      j = json_skip_ws(s, j);
      if (s[j] === "}") return [unique_json_object(pairs), j + 1];
      if (s[j] !== ",") throw json_error("Expecting ',' delimiter", s, j);
      j = json_skip_ws(s, j + 1);
    }
  }
  if (c === "[") {
    const out = [];
    let j = json_skip_ws(s, i + 1);
    if (s[j] === "]") return [out, j + 1];
    for (;;) {
      let value;
      [value, j] = json_scan_value(s, j, depth + 1);
      out.push(value);
      j = json_skip_ws(s, j);
      if (s[j] === "]") return [out, j + 1];
      if (s[j] !== ",") throw json_error("Expecting ',' delimiter", s, j);
      j = json_skip_ws(s, j + 1);
    }
  }
  if (s.startsWith("null", i)) return [null, i + 4];
  if (s.startsWith("true", i)) return [true, i + 4];
  if (s.startsWith("false", i)) return [false, i + 5];
  if (s.startsWith("NaN", i)) return [NaN, i + 3];
  if (s.startsWith("Infinity", i)) return [Infinity, i + 8];
  if (s.startsWith("-Infinity", i)) return [-Infinity, i + 9];
  JSON_NUMBER.lastIndex = i;
  const m = JSON_NUMBER.exec(s);
  if (m) return [Number(m[0]), i + m[0].length];
  throw json_error("Expecting value", s, i);
}

function raw_decode(s) {
  return json_scan_value(s, 0, 0);
}

export function top_level_json_key_present(text, wanted) {
  // Conservatively find a top-level key even when the JSON is malformed.
  let cursor = 0;
  while (cursor < text.length && py_isspace(text[cursor])) cursor += 1;
  if (cursor >= text.length || text[cursor] !== "{") return false;
  let brace_depth = 1;
  let bracket_depth = 0;
  let expecting_key = true;
  cursor += 1;
  while (cursor < text.length) {
    const char = text[cursor];
    if (py_isspace(char)) {
      cursor += 1;
      continue;
    }
    if (char === '"' || char === "'") {
      const quote = char;
      const start = cursor;
      cursor += 1;
      let escaped = false;
      while (cursor < text.length) {
        const current = text[cursor];
        if (escaped) escaped = false;
        else if (current === "\\") escaped = true;
        else if (current === quote) break;
        cursor += 1;
      }
      if (cursor >= text.length) return false;
      const token = text.slice(start, cursor + 1);
      let value = null;
      if (quote === '"') {
        try {
          const decoded = JSON.parse(token);
          value = typeof decoded === "string" ? decoded : null;
        } catch {
          value = token.slice(1, -1);
        }
      } else {
        value = token.slice(1, -1);
      }
      cursor += 1;
      let lookahead = cursor;
      while (lookahead < text.length && py_isspace(text[lookahead])) lookahead += 1;
      if (
        brace_depth === 1 && bracket_depth === 0 && expecting_key &&
        lookahead < text.length && text[lookahead] === ":"
      ) {
        if (value === wanted) return true;
        expecting_key = false;
      }
      continue;
    }
    if (char === "{") {
      brace_depth += 1;
    } else if (char === "}") {
      brace_depth -= 1;
      if (brace_depth <= 0) return false;
    } else if (char === "[") {
      bracket_depth += 1;
    } else if (char === "]" && bracket_depth) {
      bracket_depth -= 1;
    } else if (char === "," && brace_depth === 1 && bracket_depth === 0) {
      expecting_key = true;
    } else if (expecting_key && brace_depth === 1 && bracket_depth === 0) {
      let end = cursor;
      while (end < text.length && !":,{}[]\r\n".includes(text[end])) end += 1;
      if (end < text.length && text[end] === ":") {
        if (py_strip(text.slice(cursor, end)) === wanted) return true;
        expecting_key = false;
        cursor = end;
      }
    }
    cursor += 1;
  }
  return false;
}

// ---------------------------------------------------------------------------
// label/regex helpers (mdq.py 657-735)
// ---------------------------------------------------------------------------
export function normalize_label(value) {
  value = py_strip(value);
  // re.sub(r"^(?:\*\*|__|`)+|(?:\*\*|__|`)+$", "", value): `$` also matches before a final "\n",
  // but value was stripped so it cannot end with "\n".
  value = py_strip(value.replace(/^(?:\*\*|__|`)+|(?:\*\*|__|`)+$/g, ""));
  // re.sub(r"\s+", "", ...) uses Unicode \s
  return casefold(value.replace(new RegExp(`[${PY_WS}]+`, "g"), ""));
}

export function field_name_from_header(value, position) {
  // Python .strip("_") / .lower()
  const name = py_strip_underscores(value_strip_replace(value)).toLowerCase();
  return name || `column_${position + 1}`;
}
function value_strip_replace(value) {
  return py_strip(value).replace(/[^A-Za-z0-9]+/g, "_");
}
function py_strip_underscores(v) {
  return v.replace(/^_+/, "").replace(/_+$/, "");
}

export function safe_compile(pattern, where, diagnostics) {
  if (typeof pattern !== "string") {
    diagnostics.push(diagnostic("profile_invalid", "error", `${where} must be a string`));
    return null;
  }
  if (cp_len(pattern) > MAX_PATTERN_LENGTH) {
    diagnostics.push(diagnostic("profile_invalid", "error", `${where} exceeds ${MAX_PATTERN_LENGTH} characters`));
    return null;
  }
  try {
    return compile_py(pattern); // profile_regex.VERSION0
  } catch (exc) {
    if (exc instanceof PyRegexUnsupported) {
      // Fail closed: the Python tool may accept this syntax, the Node port cannot evaluate it.
      diagnostics.push(
        diagnostic("profile_invalid", "error", `${where} is invalid: unsupported regex syntax in mdq.mjs: ${exc.message}`),
      );
      return null;
    }
    if (exc instanceof PyRegexError) {
      diagnostics.push(diagnostic("profile_invalid", "error", `${where} is invalid: ${exc.message}`));
      return null;
    }
    throw exc;
  }
}

export function validate_group(compiled, group, where, diagnostics) {
  if (group === null || group === undefined || compiled === null) return;
  if (typeof group === "string" && /^[0-9]+$/.test(group)) group = parseInt(group, 10); // str.isdigit()
  if (is_int(group)) {
    if (group < 0 || group > compiled.groups) {
      diagnostics.push(
        diagnostic(
          "profile_invalid",
          "error",
          `${where} references capture group ${group}, but pattern has ${compiled.groups}`,
        ),
      );
    }
  } else if (!has(compiled.groupindex, group)) {
    diagnostics.push(
      diagnostic("profile_invalid", "error", `${where} references missing named capture group ${py_repr(group)}`),
    );
  }
}

export function match_group(match, group) {
  if (group === null || group === undefined) return py_strip(match.group(0));
  if (typeof group === "string" && /^[0-9]+$/.test(group)) group = parseInt(group, 10);
  let value;
  try {
    value = match.group(group); // IndexError/KeyError -> RangeError in PyMatch
  } catch (exc) {
    if (exc instanceof RangeError) return null;
    throw exc;
  }
  return value !== null && value !== undefined ? py_strip(value) : null;
}

// ---------------------------------------------------------------------------
// parse_profile (mdq.py 823-1019)
// ---------------------------------------------------------------------------
export function parse_profile(text, lines) {
  const diagnostics = [];
  let excluded = new Set();
  const found = [];
  const allowed_comment_anchors = [0];

  const first = lines.length ? py_strip(py_lstrip(lines[0], "﻿")) : "";
  if (first === "---" || first === "+++") {
    const delimiter = first;
    let closing = null;
    for (let index = 1; index < lines.length; index++) {
      const valid_closers = delimiter === "---" ? ["---", "..."] : ["+++"];
      if (valid_closers.includes(py_strip(lines[index]))) {
        closing = index;
        break;
      }
    }
    if (closing === null) {
      diagnostics.push(
        diagnostic("frontmatter_incomplete", "warning", `${delimiter} frontmatter has no closing delimiter`, { line: 1 }),
      );
      if (delimiter === "---" && YAML_MDQ_DECLARATION_RE.test(cp_prefix(lines.slice(1).join(""), MAX_PROFILE_BYTES))) {
        diagnostics.push(
          diagnostic(
            "profile_invalid",
            "error",
            "incomplete YAML frontmatter appears to declare mdq; refusing temporary inference",
            { line: 1 },
          ),
        );
      } else if (
        delimiter === "+++" && TOML_MDQ_DECLARATION_RE.test(cp_prefix(lines.slice(1).join(""), MAX_PROFILE_BYTES))
      ) {
        diagnostics.push(
          diagnostic("profile_unsupported", "error", "mdq contracts must use YAML Front Matter delimited by ---", {
            line: 1,
          }),
        );
      }
    } else {
      set_union(excluded, line_set(0, closing + 1));
      allowed_comment_anchors.push(lines.slice(0, closing + 1).reduce((acc, line) => acc + line.length, 0));
      if (delimiter === "---") {
        try {
          const loaded = load_yaml(lines.slice(1, closing).join(""));
          const root = py_truthy(loaded) ? loaded : {};
          if (is_dict(root) && has(root, "mdq")) {
            const declaration = root["mdq"];
            if (is_dict(declaration)) {
              if (has(declaration, "profile")) {
                const decl_keys = Object.keys(declaration);
                if (!(decl_keys.length === 1 && decl_keys[0] === "profile")) {
                  diagnostics.push(
                    diagnostic(
                      "profile_reference_invalid",
                      "error",
                      "a shared mdq profile reference cannot contain inline overrides",
                      { line: 1 },
                    ),
                  );
                } else if (typeof declaration["profile"] !== "string") {
                  diagnostics.push(
                    diagnostic("profile_reference_invalid", "error", "frontmatter mdq.profile must be a string", {
                      line: 1,
                    }),
                  );
                } else {
                  const reference = declaration["profile"];
                  const profile = load_shared_profile(reference, diagnostics);
                  if (profile !== null) found.push([`${SHARED_PROFILE_PREFIX}${reference}`, profile]);
                }
              } else {
                found.push(["yaml-frontmatter", declaration]);
              }
            } else {
              diagnostics.push(
                diagnostic("profile_invalid", "error", "frontmatter mdq value must be a mapping", { line: 1 }),
              );
            }
          }
        } catch (exc) {
          if (!(exc instanceof YAMLError || exc instanceof PyTypeError || exc instanceof ValueError || exc instanceof RangeError)) {
            throw exc;
          }
          diagnostics.push(
            diagnostic("frontmatter_invalid", "warning", `frontmatter could not be parsed: ${exc.message}`, { line: 1 }),
          );
          if (YAML_MDQ_DECLARATION_RE.test(lines.slice(1, closing).join(""))) {
            diagnostics.push(
              diagnostic(
                "profile_invalid",
                "error",
                "invalid YAML frontmatter appears to declare mdq; refusing temporary inference",
                { line: 1 },
              ),
            );
          }
        }
      } else if (TOML_MDQ_DECLARATION_RE.test(lines.slice(1, closing).join(""))) {
        diagnostics.push(
          diagnostic("profile_unsupported", "error", "mdq contracts must use YAML Front Matter delimited by ---", {
            line: 1,
          }),
        );
      }
    }
  } else {
    const stripped = py_lstrip(text, "﻿ \t\r\n");
    if (stripped.startsWith("{")) {
      const leading = text.length - stripped.length;
      try {
        const [root, end] = raw_decode(stripped);
        if (!is_dict(root)) throw new ValueError("JSON frontmatter must be an object");
        const closing_char = leading + end;
        const closing_line = count_newlines(text, 0, closing_char);
        set_union(excluded, line_set(0, closing_line + 1));
        allowed_comment_anchors.push(closing_char);
        if (has(root, "mdq")) {
          diagnostics.push(
            diagnostic("profile_unsupported", "error", "mdq contracts must use YAML Front Matter delimited by ---", {
              line: 1,
            }),
          );
        }
      } catch (exc) {
        if (!(exc instanceof ValueError || exc instanceof PyTypeError || exc instanceof RangeError)) throw exc;
        diagnostics.push(
          diagnostic("frontmatter_invalid", "warning", `JSON frontmatter could not be parsed: ${exc.message}`, { line: 1 }),
        );
        if (top_level_json_key_present(cp_prefix(stripped, MAX_PROFILE_BYTES), "mdq")) {
          diagnostics.push(
            diagnostic(
              "profile_invalid",
              "error",
              "invalid JSON frontmatter appears to declare mdq; refusing temporary inference",
              { line: 1 },
            ),
          );
        }
      }
    }
  }

  const prefix = cp_prefix(text, MAX_PROFILE_BYTES);
  const comment_re = new RegExp(PROFILE_COMMENT_RE.source, PROFILE_COMMENT_RE.flags + "g");
  let match;
  while ((match = comment_re.exec(prefix)) !== null) {
    if (match[0] === "") comment_re.lastIndex += 1;
    const m_start = match.index;
    const m_end = match.index + match[0].length;
    const allowed = allowed_comment_anchors.some(
      (anchor) => anchor <= m_start && !py_strip(py_lstrip(text.slice(anchor, m_start), "﻿")),
    );
    if (!allowed) continue;
    const start_line = count_newlines(text, 0, m_start);
    const end_line = count_newlines(text, 0, m_end) + 1;
    set_union(excluded, line_set(start_line, end_line));
    diagnostics.push(
      diagnostic(
        "profile_unsupported",
        "error",
        "mdq HTML comment contracts are unsupported; move the profile to YAML Front Matter",
        { line: start_line + 1 },
      ),
    );
  }

  if (found.length > 1) {
    diagnostics.push(
      diagnostic(
        "profile_conflict",
        "error",
        "multiple mdq profiles are present; remove one instead of relying on precedence",
        { details: { sources: found.map(([source]) => source) } },
      ),
    );
    return new ProfileLoad({ profile: null, source: null, excluded_lines: excluded, diagnostics });
  }
  if (!found.length) {
    if (!diagnostics.some((item) => item.code === "profile_invalid" || item.code === "profile_unsupported")) {
      diagnostics.push(
        diagnostic("profile_missing", "info", "no mdq profile found; profile-free read-only queries remain available"),
      );
    }
    return new ProfileLoad({ profile: null, source: null, excluded_lines: excluded, diagnostics });
  }
  const [source, profile] = found[0];
  const validated = validate_profile(profile, diagnostics);
  return new ProfileLoad({ profile: validated, source, excluded_lines: excluded, diagnostics });
}

// ---------------------------------------------------------------------------
// validators (mdq.py 1022-1720)
// ---------------------------------------------------------------------------
export function _unknown_keys(mapping, allowed, where, diagnostics) {
  for (const key of Object.keys(mapping)) {
    if (typeof key !== "string" || (!allowed.has(key) && !key.startsWith("x-"))) {
      diagnostics.push(diagnostic("profile_invalid", "error", `unknown key ${where}.${key}`));
    }
  }
}

export function _string_list(value, where, diagnostics) {
  if (!Array.isArray(value) || !value.length || !value.every((item) => typeof item === "string" && item)) {
    diagnostics.push(diagnostic("profile_invalid", "error", `${where} must be a non-empty string list`));
    return null;
  }
  return value;
}

export function _positive_int(value, where, diagnostics) {
  if (!is_int(value) || value < 1) {
    diagnostics.push(diagnostic("profile_invalid", "error", `${where} must be a positive integer`));
  }
}

export function _validate_queries(queries, fields, diagnostics) {
  if (!is_dict(queries) || !Object.keys(queries).length) {
    diagnostics.push(diagnostic("profile_invalid", "error", "queries must be a non-empty mapping"));
    return;
  }
  for (const [name, spec] of Object.entries(queries)) {
    const where = `mdq.queries.${name}`;
    if (typeof name !== "string" || !name || !is_dict(spec)) {
      diagnostics.push(diagnostic("profile_invalid", "error", `${where} must be a named mapping`));
      continue;
    }
    _unknown_keys(spec, new Set(["when", "match", "select", "expect"]), where, diagnostics);
    const when = dict_get(spec, "when");
    if (when !== null) {
      if (!is_dict(when)) {
        diagnostics.push(diagnostic("profile_invalid", "error", `${where}.when must be a mapping`));
      } else {
        _unknown_keys(when, new Set(["pattern"]), `${where}.when`, diagnostics);
        if (!has(when, "pattern")) {
          diagnostics.push(diagnostic("profile_invalid", "error", `${where}.when.pattern is required`));
        } else {
          safe_compile(when["pattern"], `${where}.when.pattern`, diagnostics);
        }
      }
    }
    const match = dict_get(spec, "match");
    if (!is_dict(match)) {
      diagnostics.push(diagnostic("profile_invalid", "error", `${where}.match must be a mapping`));
    } else {
      _unknown_keys(match, new Set(["source", "field", "operator"]), `${where}.match`, diagnostics);
      const source = dict_get(match, "source");
      const operator = dict_get(match, "operator", "eq");
      if (source !== "key" && source !== "field") {
        diagnostics.push(diagnostic("profile_invalid", "error", `${where}.match.source must be key or field`));
      }
      if (operator !== "eq" && operator !== "contains") {
        diagnostics.push(diagnostic("profile_invalid", "error", `${where}.match.operator must be eq or contains`));
      }
      if (source === "field") {
        const field_name = dict_get(match, "field");
        if (typeof field_name !== "string" || !has(fields, field_name)) {
          diagnostics.push(
            diagnostic("profile_invalid", "error", `${where}.match.field must name a declared field`),
          );
        }
      } else if (has(match, "field")) {
        diagnostics.push(
          diagnostic("profile_invalid", "error", `${where}.match.field is only valid for field queries`),
        );
      }
    }
    if (has(spec, "select")) {
      const selected = _string_list(spec["select"], `${where}.select`, diagnostics);
      if (selected && selected.length) {
        const unknown = selected.filter((item) => !has(fields, item));
        if (unknown.length) {
          diagnostics.push(
            diagnostic("profile_invalid", "error", `${where}.select references undeclared fields`, {
              details: { fields: unknown },
            }),
          );
        }
      }
    }
    const expect = dict_get(spec, "expect", {});
    if (!is_dict(expect)) {
      diagnostics.push(diagnostic("profile_invalid", "error", `${where}.expect must be a mapping`));
    } else {
      const active_limits = ["max_record_lines", "max_record_bytes", "max_total_bytes"];
      const allowed = new Set([...active_limits, "max_matches", "structured", "min_confidence"]);
      _unknown_keys(expect, allowed, `${where}.expect`, diagnostics);
      // Python iterates a set here (hash-randomized order); a fixed order is used instead.
      for (const key of [...active_limits, "max_matches"]) {
        if (has(expect, key)) _positive_int(expect[key], `${where}.expect.${key}`, diagnostics);
      }
      if (has(expect, "max_matches")) {
        diagnostics.push(
          diagnostic(
            "query_max_matches_deprecated",
            "info",
            `${where}.expect.max_matches is ignored; use payload limits for result-size budgets`,
          ),
        );
      }
      if (has(expect, "structured") && typeof expect["structured"] !== "boolean") {
        diagnostics.push(diagnostic("profile_invalid", "error", `${where}.expect.structured must be boolean`));
      }
      if (
        has(expect, "min_confidence") &&
        (typeof expect["min_confidence"] !== "number" ||
          !(0 <= Number(expect["min_confidence"]) && Number(expect["min_confidence"]) <= 1))
      ) {
        diagnostics.push(
          diagnostic("profile_invalid", "error", `${where}.expect.min_confidence must be between 0 and 1`),
        );
      }
    }
  }
}

// json.dumps(profile, ensure_ascii=False) equivalent with Python's type errors for non-JSON values.
function json_dumps_checked(value) {
  const check = (v, depth) => {
    if (depth > 900) throw new RangeError("maximum recursion depth exceeded");
    if (v === null || typeof v === "string" || typeof v === "boolean") return;
    if (typeof v === "number") {
      if (!Number.isFinite(v)) throw new ValueError("non-finite float is not supported by the Node port");
      return;
    }
    if (Array.isArray(v)) {
      for (const item of v) check(item, depth + 1);
      return;
    }
    if (v instanceof Date) {
      // PyYAML yields datetime.date for date-only scalars (approximated: midnight UTC) and datetime otherwise.
      const midnight = v.getTime() % 86400000 === 0;
      throw new PyTypeError(`Object of type ${midnight ? "date" : "datetime"} is not JSON serializable`);
    }
    if (v instanceof Uint8Array) throw new PyTypeError("Object of type bytes is not JSON serializable");
    if (v instanceof Set) throw new PyTypeError("Object of type set is not JSON serializable");
    if (v instanceof Map) throw new PyTypeError("Object of type dict is not JSON serializable");
    if (typeof v === "object") {
      for (const k of Object.keys(v)) check(v[k], depth + 1);
      return;
    }
    throw new PyTypeError(`Object of type ${typeof v} is not JSON serializable`);
  };
  check(value, 0);
  return JSON.stringify(value);
}

export function validate_profile(profile, diagnostics) {
  if (!is_dict(profile)) {
    diagnostics.push(diagnostic("profile_invalid", "error", "profile must be a mapping"));
    return null;
  }
  try {
    const serialized_profile = json_dumps_checked(profile);
    if (utf8_len(serialized_profile) > MAX_PROFILE_BYTES) {
      diagnostics.push(
        diagnostic("profile_invalid", "error", `expanded profile exceeds ${MAX_PROFILE_BYTES} bytes`),
      );
      return null;
    }
    profile = JSON.parse(serialized_profile);
  } catch (exc) {
    if (!(exc instanceof PyTypeError || exc instanceof ValueError || exc instanceof RangeError || exc instanceof TypeError)) {
      throw exc;
    }
    diagnostics.push(
      diagnostic("profile_invalid", "error", `profile values must be JSON-compatible: ${exc.message}`),
    );
    return null;
  }
  const version = dict_get(profile, "version");
  const allowed_top = new Set(["version", "dialect", "records", "fields", "tolerance", "index"]);
  if (version === 2) for (const k of ["actors", "queries", "maintenance"]) allowed_top.add(k);
  _unknown_keys(profile, allowed_top, "mdq", diagnostics);
  if (!is_int(version) || (version !== 1 && version !== 2)) {
    diagnostics.push(diagnostic("profile_unsupported", "error", "only mdq versions 1 and 2 are supported"));
  }

  const dialect = setdefault(profile, "dialect", "commonmark");
  if (dialect !== "commonmark" && dialect !== "gfm") {
    diagnostics.push(diagnostic("profile_invalid", "error", "dialect must be commonmark or gfm"));
  }

  let key_pattern_compiled = null;
  let boundary_source = null;
  const records = dict_get(profile, "records");
  if (!is_dict(records)) {
    diagnostics.push(diagnostic("profile_invalid", "error", "records must be a mapping"));
  } else {
    _unknown_keys(records, new Set(["boundary", "key"]), "mdq.records", diagnostics);
    const boundary = dict_get(records, "boundary");
    if (!is_dict(boundary)) {
      diagnostics.push(diagnostic("profile_invalid", "error", "records.boundary must be a mapping"));
    } else {
      boundary_source = setdefault(boundary, "source", "heading");
      const boundary_keys = new Set(["source", "levels", "level_tolerance", "pattern"]);
      if (version === 2) {
        boundary_keys.add("under_heading");
        boundary_keys.add("columns");
      }
      _unknown_keys(boundary, boundary_keys, "mdq.records.boundary", diagnostics);
      if (version === 1 && boundary_source !== "heading") {
        diagnostics.push(diagnostic("profile_invalid", "error", "v1 boundary source must be heading"));
      }
      if (version === 2 && boundary_source !== "heading" && boundary_source !== "table-row") {
        diagnostics.push(diagnostic("profile_invalid", "error", "v2 boundary source must be heading or table-row"));
      }
      if (boundary_source === "heading") {
        const levels = dict_get(boundary, "levels");
        if (!Array.isArray(levels) || !levels.length || !levels.every((x) => is_int(x) && 1 <= x && x <= 6)) {
          diagnostics.push(
            diagnostic("profile_invalid", "error", "records.boundary.levels must contain heading levels 1..6"),
          );
        }
        const tolerance = setdefault(boundary, "level_tolerance", 0);
        if (!is_int(tolerance) || !(0 <= tolerance && tolerance <= 5)) {
          diagnostics.push(diagnostic("profile_invalid", "error", "records.boundary.level_tolerance must be 0..5"));
        }
        if (has(boundary, "pattern")) safe_compile(boundary["pattern"], "records.boundary.pattern", diagnostics);
      } else if (boundary_source === "table-row") {
        if (dialect !== "gfm") {
          diagnostics.push(diagnostic("profile_invalid", "error", "table-row boundaries require dialect: gfm"));
        }
        const columns = _string_list(dict_get(boundary, "columns"), "records.boundary.columns", diagnostics);
        if (columns && columns.length && new Set(columns).size !== columns.length) {
          diagnostics.push(diagnostic("profile_invalid", "error", "records.boundary.columns must be unique"));
        }
        const under_heading = dict_get(boundary, "under_heading");
        if (under_heading !== null && (typeof under_heading !== "string" || !py_strip(under_heading))) {
          diagnostics.push(
            diagnostic("profile_invalid", "error", "records.boundary.under_heading must be non-empty text"),
          );
        }
        // Python iterates {"levels","level_tolerance","pattern"} & set(boundary): hash order; sorted here.
        for (const incompatible of ["level_tolerance", "levels", "pattern"]) {
          if (has(boundary, incompatible)) {
            diagnostics.push(
              diagnostic("profile_invalid", "error", `records.boundary.${incompatible} is unavailable for table-row`),
            );
          }
        }
      }
    }

    const key = dict_get(records, "key");
    if (!is_dict(key)) {
      diagnostics.push(diagnostic("profile_invalid", "error", "records.key must be a mapping"));
    } else {
      _unknown_keys(key, new Set(["source", "pattern", "group", "labels", "column"]), "mdq.records.key", diagnostics);
      const source = dict_get(key, "source", "heading");
      key["source"] = source;
      const supported_key_sources = new Set(["heading", "label", "marker"]);
      if (version === 2) supported_key_sources.add("column");
      if (!supported_key_sources.has(source)) {
        diagnostics.push(diagnostic("profile_invalid", "error", "records.key.source is unsupported"));
      }
      if (has(key, "pattern")) key_pattern_compiled = safe_compile(key["pattern"], "records.key.pattern", diagnostics);
      if (source === "label") _string_list(dict_get(key, "labels"), "records.key.labels", diagnostics);
      if (source === "column" && (typeof dict_get(key, "column") !== "string" || !py_strip(key["column"]))) {
        diagnostics.push(diagnostic("profile_invalid", "error", "records.key.column must be non-empty text"));
      }
      if (source === "column" && boundary_source !== "table-row") {
        diagnostics.push(diagnostic("profile_invalid", "error", "column keys require a table-row boundary"));
      }
      if (
        source === "column" && is_dict(dict_get(records, "boundary")) &&
        Array.isArray(records["boundary"]["columns"]) &&
        !records["boundary"]["columns"].includes(dict_get(key, "column"))
      ) {
        diagnostics.push(
          diagnostic("profile_invalid", "error", "records.key.column must be declared in boundary.columns"),
        );
      }
      if (has(key, "group") && !(typeof key["group"] === "string" || is_int(key["group"]))) {
        diagnostics.push(diagnostic("profile_invalid", "error", "records.key.group must be a name or number"));
      } else if (has(key, "group")) {
        if (key_pattern_compiled === null) {
          diagnostics.push(
            diagnostic("profile_invalid", "error", "records.key.group requires records.key.pattern"),
          );
        } else {
          validate_group(key_pattern_compiled, key["group"], "records.key.group", diagnostics);
        }
      }
    }
  }

  const fields = setdefault(profile, "fields", {});
  if (!is_dict(fields)) {
    diagnostics.push(diagnostic("profile_invalid", "error", "fields must be a mapping"));
  } else {
    for (const [name, spec] of Object.entries(fields)) {
      if (typeof name !== "string" || !name || !is_dict(spec)) {
        diagnostics.push(diagnostic("profile_invalid", "error", `field ${py_repr(name)} must be a named mapping`));
        continue;
      }
      _unknown_keys(
        spec,
        new Set(["source", "pattern", "group", "labels", "headings", "column"]),
        `mdq.fields.${name}`,
        diagnostics,
      );
      const source = dict_get(spec, "source");
      const supported_field_sources = new Set(["heading", "label", "section", "body", "regex"]);
      if (version === 2) supported_field_sources.add("column");
      if (!supported_field_sources.has(source)) {
        diagnostics.push(diagnostic("profile_invalid", "error", `field ${name} has unsupported source`));
      }
      let field_pattern_compiled = null;
      if (has(spec, "pattern")) {
        field_pattern_compiled = safe_compile(spec["pattern"], `fields.${name}.pattern`, diagnostics);
      }
      if (source === "regex" && !has(spec, "pattern")) {
        diagnostics.push(diagnostic("profile_invalid", "error", `field ${name} regex source needs pattern`));
      }
      if (source === "label") _string_list(dict_get(spec, "labels"), `fields.${name}.labels`, diagnostics);
      if (source === "section") _string_list(dict_get(spec, "headings"), `fields.${name}.headings`, diagnostics);
      if (source === "column" && (typeof dict_get(spec, "column") !== "string" || !py_strip(spec["column"]))) {
        diagnostics.push(diagnostic("profile_invalid", "error", `fields.${name}.column must be non-empty text`));
      }
      if (source === "column" && boundary_source !== "table-row") {
        diagnostics.push(
          diagnostic("profile_invalid", "error", `field ${name} column source requires a table-row boundary`),
        );
      }
      if (
        source === "column" && is_dict(records) && is_dict(dict_get(records, "boundary")) &&
        Array.isArray(records["boundary"]["columns"]) &&
        !records["boundary"]["columns"].includes(dict_get(spec, "column"))
      ) {
        diagnostics.push(
          diagnostic("profile_invalid", "error", `fields.${name}.column must be declared in boundary.columns`),
        );
      }
      if (has(spec, "group") && !(typeof spec["group"] === "string" || is_int(spec["group"]))) {
        diagnostics.push(diagnostic("profile_invalid", "error", `field ${name} group must be a name or number`));
      } else if (has(spec, "group")) {
        const effective_pattern =
          source === "heading" && !has(spec, "pattern") ? key_pattern_compiled : field_pattern_compiled;
        if (effective_pattern === null) {
          diagnostics.push(
            diagnostic("profile_invalid", "error", `field ${name} group requires an effective pattern`),
          );
        } else {
          validate_group(effective_pattern, spec["group"], `fields.${name}.group`, diagnostics);
        }
      }
    }
  }

  if (version === 2 && has(profile, "actors")) {
    const actors = profile["actors"];
    if (!is_dict(actors)) {
      diagnostics.push(diagnostic("profile_invalid", "error", "actors must be a mapping"));
    } else {
      _unknown_keys(actors, new Set(["read", "write"]), "mdq.actors", diagnostics);
      for (const action of ["read", "write"]) {
        if (has(actors, action) && !["human", "machine", "mixed"].includes(actors[action])) {
          diagnostics.push(
            diagnostic("profile_invalid", "error", `actors.${action} must be human, machine, or mixed`),
          );
        }
      }
    }
  }

  if (version === 2 && has(profile, "queries")) {
    _validate_queries(profile["queries"], is_dict(fields) ? fields : {}, diagnostics);
  }

  if (version === 2 && has(profile, "maintenance")) {
    const maintenance = profile["maintenance"];
    if (!is_dict(maintenance)) {
      diagnostics.push(diagnostic("profile_invalid", "error", "maintenance must be a mapping"));
    } else {
      _unknown_keys(maintenance, new Set(["query_contract"]), "mdq.maintenance", diagnostics);
      const policy = dict_get(maintenance, "query_contract");
      if (!is_dict(policy)) {
        diagnostics.push(diagnostic("profile_invalid", "error", "maintenance.query_contract must be a mapping"));
      } else {
        _unknown_keys(
          policy,
          new Set(["mode", "allow", "max_changes_per_run"]),
          "mdq.maintenance.query_contract",
          diagnostics,
        );
        const mode = dict_get(policy, "mode", "propose");
        if (!["locked", "propose", "auto"].includes(mode)) {
          diagnostics.push(
            diagnostic(
              "profile_invalid",
              "error",
              "maintenance.query_contract.mode must be locked, propose, or auto",
            ),
          );
        }
        if (mode === "auto" && !has(policy, "allow")) {
          diagnostics.push(
            diagnostic("profile_invalid", "error", "maintenance.query_contract.allow is required in auto mode"),
          );
        }
        if (has(policy, "allow")) {
          const allowed = _string_list(policy["allow"], "maintenance.query_contract.allow", diagnostics);
          if (allowed && allowed.length) {
            const invalid = allowed.filter((item) => !["queries", "fields", "records"].includes(item));
            if (invalid.length) {
              diagnostics.push(
                diagnostic(
                  "profile_invalid",
                  "error",
                  "maintenance.query_contract.allow has unsupported scopes",
                  { details: { scopes: invalid } },
                ),
              );
            }
          }
        }
        if (has(policy, "max_changes_per_run")) {
          _positive_int(
            policy["max_changes_per_run"],
            "maintenance.query_contract.max_changes_per_run",
            diagnostics,
          );
        }
      }
    }
  }

  const tolerance = setdefault(profile, "tolerance", { incomplete: false });
  if (!is_dict(tolerance)) {
    diagnostics.push(diagnostic("profile_invalid", "error", "tolerance must be a mapping"));
  } else {
    _unknown_keys(tolerance, new Set(["incomplete"]), "mdq.tolerance", diagnostics);
    const incomplete = setdefault(tolerance, "incomplete", false);
    if (typeof incomplete !== "boolean") {
      diagnostics.push(diagnostic("profile_invalid", "error", "tolerance.incomplete must be boolean"));
    }
  }

  if (has(profile, "index") && (typeof profile["index"] !== "string" || !py_strip(profile["index"]))) {
    diagnostics.push(diagnostic("profile_invalid", "error", "index must be a non-empty relative path"));
  }

  if (diagnostics.some((item) => item.severity === "error")) return null;
  return profile;
}
