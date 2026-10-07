// Shared helpers for the Node port of mdq.py. Names mirror the Python source.
import { createHash } from "node:crypto";

export const ENGINE = "mdq.mjs/1";

export function diagnostic(code, severity, message, { line = null, details = null } = {}) {
  const item = { code, severity, message };
  if (line !== null && line !== undefined) item.line = line;
  if (details !== null && details !== undefined) item.details = details;
  return item;
}

export function sha256(data) {
  return createHash("sha256").update(data).digest("hex");
}

// Python: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
export function normalized_json(value) {
  const sort = (v) => {
    if (Array.isArray(v)) return v.map(sort);
    if (v && typeof v === "object" && !(v instanceof Set)) {
      const out = {};
      for (const key of Object.keys(v).sort(codepoint_compare)) out[key] = sort(v[key]);
      return out;
    }
    return v;
  };
  return Buffer.from(JSON.stringify(sort(value)), "utf-8");
}

// Python sorts str by code point; JS default sorts by UTF-16 unit. Differs only for astral chars.
export function codepoint_compare(a, b) {
  const x = Array.from(a);
  const y = Array.from(b);
  const n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i++) {
    const d = x[i].codePointAt(0) - y[i].codePointAt(0);
    if (d !== 0) return d;
  }
  return x.length - y.length;
}

export function line_set(start, end) {
  const out = new Set();
  const lo = Math.max(0, start);
  for (let i = lo; i < Math.max(start, end); i++) out.add(i);
  return out;
}

export function set_union(target, other) {
  for (const v of other) target.add(v);
  return target;
}

// ---- Python str helpers -------------------------------------------------

const PY_WHITESPACE = "\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const PY_WS_CLASS = `[${PY_WHITESPACE}]`;
const PY_STRIP_LEFT = new RegExp(`^${PY_WS_CLASS}+`);
const PY_STRIP_RIGHT = new RegExp(`${PY_WS_CLASS}+$`);

export function py_isspace(ch) {
  return new RegExp(`^${PY_WS_CLASS}$`).test(ch);
}

// str.strip() with no argument.
export function py_strip(value) {
  return value.replace(PY_STRIP_LEFT, "").replace(PY_STRIP_RIGHT, "");
}
export function py_lstrip(value, chars = null) {
  if (chars === null) return value.replace(PY_STRIP_LEFT, "");
  let i = 0;
  const set = new Set(Array.from(chars));
  const arr = Array.from(value);
  while (i < arr.length && set.has(arr[i])) i++;
  return arr.slice(i).join("");
}
export function py_rstrip(value, chars = null) {
  if (chars === null) return value.replace(PY_STRIP_RIGHT, "");
  const set = new Set(Array.from(chars));
  const arr = Array.from(value);
  let j = arr.length;
  while (j > 0 && set.has(arr[j - 1])) j--;
  return arr.slice(0, j).join("");
}
export function py_strip_chars(value, chars) {
  return py_rstrip(py_lstrip(value, chars), chars);
}

// str.splitlines(keepends=True): splits on \n \r\n \r \v \f \x1c \x1d \x1e \x85
export function splitlines_keepends(text) {
  const out = [];
  let start = 0;
  const n = text.length;
  let i = 0;
  while (i < n) {
    const c = text[i];
    if (c === "\r" && text[i + 1] === "\n") {
      out.push(text.slice(start, i + 2));
      i += 2;
      start = i;
    } else if ("\n\r\v\f\x1c\x1d\x1e\x85  ".includes(c)) {
      out.push(text.slice(start, i + 1));
      i += 1;
      start = i;
    } else {
      i += 1;
    }
  }
  if (start < n) out.push(text.slice(start));
  return out;
}

export function utf8_len(text) {
  return Buffer.byteLength(text, "utf-8");
}

// str.casefold() approximation: full case folding differs from toLowerCase for a few characters (e.g. ß).
export function casefold(value) {
  return value.toLowerCase().replace(/ß/g, "ss").replace(/ς/g, "σ");
}

// ---- Python `regex`/`re` compatibility ------------------------------------
// Profiles are written in Python syntax. Only a small, well-understood subset is translated;
// anything else raises PyRegexUnsupported so callers can fail closed instead of misreading it.

export class PyRegexUnsupported extends Error {}
export class PyRegexError extends Error {}

function translate_pattern(pattern) {
  let out = "";
  let i = 0;
  let inClass = false;
  const names = [];
  let groups = 0;
  while (i < pattern.length) {
    const c = pattern[i];
    if (c === "\\") {
      const nxt = pattern[i + 1];
      if (nxt === undefined) throw new PyRegexError("bad escape (end of pattern)");
      if (nxt === "A") { out += "^"; i += 2; continue; }
      if (nxt === "Z") { out += "$"; i += 2; continue; }
      if (nxt === "z") throw new PyRegexUnsupported("\\z");
      if (nxt === "G") throw new PyRegexUnsupported("\\G");
      if ("pPXRKkh".includes(nxt) && !inClass) throw new PyRegexUnsupported(`\\${nxt}`);
      out += c + nxt;
      i += 2;
      continue;
    }
    if (inClass) {
      if (c === "]") inClass = false;
      if (c === "[" && pattern[i + 1] === ":") throw new PyRegexUnsupported("POSIX class");
      out += c;
      i += 1;
      continue;
    }
    if (c === "[") {
      inClass = true;
      out += c;
      i += 1;
      if (pattern[i] === "^") { out += "^"; i += 1; }
      if (pattern[i] === "]") { out += "\\]"; i += 1; }
      continue;
    }
    if (c === "(") {
      if (pattern[i + 1] === "?") {
        const rest = pattern.slice(i + 2);
        const named = /^P<([A-Za-z_][A-Za-z0-9_]*)>/.exec(rest);
        if (named) {
          groups += 1;
          names.push([named[1], groups]);
          out += `(?<${named[1]}>`;
          i += 2 + named[0].length;
          continue;
        }
        const backref = /^P=([A-Za-z_][A-Za-z0-9_]*)\)/.exec(rest);
        if (backref) { out += `\\k<${backref[1]}>`; i += 2 + backref[0].length; continue; }
        if (/^(?::|=|!|<=|<!)/.test(rest)) { out += "(?"; i += 2; continue; }
        if (/^<[A-Za-z_]/.test(rest)) {
          const m = /^<([A-Za-z_][A-Za-z0-9_]*)>/.exec(rest);
          groups += 1;
          names.push([m[1], groups]);
          out += `(?<${m[1]}>`;
          i += 2 + m[0].length;
          continue;
        }
        throw new PyRegexUnsupported(`group construct (?${rest.slice(0, 3)}`);
      }
      groups += 1;
      out += "(";
      i += 1;
      continue;
    }
    // possessive quantifiers and atomic groups are unsupported in JS
    if ((c === "+" && /[*+?}]/.test(pattern[i - 1] ?? "") && pattern[i - 2] !== "\\")) {
      throw new PyRegexUnsupported("possessive quantifier");
    }
    out += c;
    i += 1;
  }
  return { source: out, groups, names };
}

export class PyMatch {
  constructor(match, text) {
    this._m = match;
    this.string = text;
  }
  group(key = 0) {
    let value;
    if (typeof key === "string" && !/^[0-9]+$/.test(key)) {
      if (!this._m.groups || !(key in this._m.groups)) throw new RangeError(`no such group ${key}`);
      value = this._m.groups[key];
    } else {
      const index = Number(key);
      if (!(index in this._m) || index >= this._m.length) throw new RangeError(`no such group ${key}`);
      value = this._m[index];
    }
    return value === undefined ? null : value;
  }
  start(key = 0) {
    const indices = this._m.indices;
    if (typeof key === "string" && !/^[0-9]+$/.test(key)) return indices.groups[key]?.[0] ?? -1;
    return indices[Number(key)]?.[0] ?? -1;
  }
  end(key = 0) {
    const indices = this._m.indices;
    if (typeof key === "string" && !/^[0-9]+$/.test(key)) return indices.groups[key]?.[1] ?? -1;
    return indices[Number(key)]?.[1] ?? -1;
  }
  span(key = 0) { return [this.start(key), this.end(key)]; }
  groups_() { return Array.from(this._m).slice(1).map((v) => (v === undefined ? null : v)); }
}

export class PyPattern {
  constructor(pattern, { ignorecase = false, multiline = false, dotall = false } = {}) {
    // Leading global inline flags, e.g. (?i) or (?is): Python applies them to the whole pattern.
    const lead = /^\(\?([aiLmsux]+)\)/.exec(pattern);
    if (lead) {
      for (const f of lead[1]) {
        if (f === "i") ignorecase = true;
        else if (f === "m") multiline = true;
        else if (f === "s") dotall = true;
        else if (f !== "u" && f !== "a") throw new PyRegexUnsupported(`inline flag ${f}`);
      }
      pattern = pattern.slice(lead[0].length);
    }
    const t = translate_pattern(pattern);
    this.pattern = pattern;
    this.groups = t.groups;
    this.groupindex = Object.fromEntries(t.names);
    let flags = "du";
    if (ignorecase) flags += "i";
    if (multiline) flags += "m";
    if (dotall) flags += "s";
    try {
      this._search = new RegExp(t.source, flags);
      this._global = new RegExp(t.source, flags + "g");
      this._sticky = new RegExp(t.source, flags + "y");
    } catch (error) {
      throw new PyRegexError(String(error.message ?? error));
    }
  }
  search(text, pos = 0) {
    const re = new RegExp(this._global.source, this._global.flags);
    re.lastIndex = pos;
    const m = re.exec(text);
    return m ? new PyMatch(m, text) : null;
  }
  match(text, pos = 0) {
    const re = new RegExp(this._sticky.source, this._sticky.flags);
    re.lastIndex = pos;
    const m = re.exec(text);
    return m ? new PyMatch(m, text) : null;
  }
  fullmatch(text) {
    const wrapped = new RegExp(`^(?:${this._search.source})$`, this._search.flags.replace("m", ""));
    const m = wrapped.exec(text);
    return m ? new PyMatch(m, text) : null;
  }
  *finditer(text) {
    const re = new RegExp(this._global.source, this._global.flags);
    let m;
    while ((m = re.exec(text)) !== null) {
      yield new PyMatch(m, text);
      if (m[0] === "") re.lastIndex += 1;
    }
  }
}

export function compile_py(pattern, options = {}) {
  return new PyPattern(pattern, options);
}
