#!/usr/bin/env node
// Port of mdq.py build_parser (6094-6346) and main (6346-end), restricted to:
// inspect, validate, diagnose, query, get, run, verify, check, search, scan, find.
// `diagnose` is included because command_check re-invokes it through run_internal_mdq.
// optimize / set / index fail closed with an mdq.error.v1 `unsupported_in_node` JSON error (exit 2).
// argparse is imitated by hand (prefix abbreviations, --opt=value, `--`, negative numbers, mutual exclusion,
// choices/int errors, required arguments, exit status 2 on usage errors).
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { diagnostic } from "./common.mjs";
import { emit, py_repr } from "./output.mjs";
import {
  command_inspect, command_validate, command_check, command_search, command_scan,
  is_os_error, is_decode_error, is_timeout_error, os_error_message, decode_error_message,
} from "./collection.mjs";
import { command_query, command_run, command_verify_queries } from "./query.mjs";

const PROG = "mdq.py";
const ALL_COMMANDS = [
  "inspect", "validate", "diagnose", "query", "get", "run", "verify", "check",
  "optimize", "search", "scan", "find", "set", "index",
];
const UNSUPPORTED_COMMANDS = new Set(["optimize", "set", "index"]);

class ArgumentError extends Error {
  constructor(message, parser) {
    super(message);
    this.parser = parser;
  }
}

// ---- add_temporary_selector_options (6071) ----
function temporary_selector_options() {
  return [
    { flags: ["--record-level"], dest: "record_level", action: "append", type: "int", choices: [1, 2, 3, 4, 5, 6] },
    { flags: ["--key-label"], dest: "key_label", action: "append" },
    { flags: ["--key-pattern"], dest: "key_pattern", action: "store" },
    { flags: ["--key-group"], dest: "key_group", action: "store" },
  ];
}

const opt = (flags, extra = {}) => ({
  flags: [flags],
  dest: flags.replace(/^--/, "").replace(/-/g, "_"),
  action: "store",
  ...extra,
});

// ---- build_parser (6094) ----
function build_parser() {
  const COMMON_SCAN = (limit, output_default) => [
    opt("--glob", { action: "append" }),
    opt("--id", { action: "append", group: "selectors" }),
    opt("--text", { group: "selectors" }),
    opt("--field"),
    opt("--limit", { type: "int", default: limit }),
    opt("--select", { action: "append" }),
    opt("--output", { choices: ["compact", "json"], default: output_default }),
    opt("--require-contract", { action: "store_true", default: false }),
    ...temporary_selector_options(),
  ];
  return {
    inspect: { positionals: [{ dest: "document", nargs: 1 }], options: [], handler: command_inspect },
    validate: { positionals: [{ dest: "document", nargs: 1 }], options: [], handler: command_validate },
    diagnose: { positionals: [{ dest: "document", nargs: 1 }], options: [], handler: command_validate },
    query: {
      positionals: [{ dest: "document", nargs: 1 }],
      options: [
        opt("--id", { required: true }),
        opt("--output", { choices: ["raw", "compact", "minimal", "json"], default: "json" }),
        opt("--select", { action: "append" }),
        ...temporary_selector_options(),
      ],
      handler: command_query,
    },
    get: {
      positionals: [{ dest: "document", nargs: 1 }],
      options: [
        opt("--id", { required: true }),
        opt("--select", { action: "append" }),
        opt("--output", { choices: ["raw", "compact", "minimal", "json"], default: "compact" }),
        ...temporary_selector_options(),
      ],
      handler: command_query,
    },
    run: {
      positionals: [{ dest: "document", nargs: 1 }],
      options: [
        opt("--query", { required: true }),
        opt("--value", { required: true }),
        opt("--output", { choices: ["compact", "json"], default: "json" }),
      ],
      handler: command_run,
    },
    verify: { positionals: [{ dest: "document", nargs: 1 }], options: [], handler: command_verify_queries },
    check: {
      positionals: [{ dest: "document", nargs: 1 }],
      options: [
        opt("--tier", { choices: ["content", "structure", "contract"], required: true }),
        opt("--id", { action: "append" }),
        opt("--absent-id", { action: "append" }),
        opt("--select", { action: "append" }),
        opt("--output", { choices: ["compact", "json"], default: "compact" }),
      ],
      handler: command_check,
    },
    search: {
      positionals: [{ dest: "document", nargs: 1 }],
      options: [
        opt("--text", { required: true }),
        opt("--field"),
        opt("--limit", { type: "int", default: 20 }),
        ...temporary_selector_options(),
      ],
      handler: command_search,
    },
    scan: {
      positionals: [{ dest: "path", nargs: "+" }],
      options: COMMON_SCAN(1000, "json"),
      handler: command_scan,
    },
    find: {
      positionals: [{ dest: "path", nargs: "+" }],
      options: COMMON_SCAN(100, "compact"),
      handler: command_scan,
    },
  };
}

// ---- usage text ----
function option_usage(o) {
  const name = o.flags[0];
  const metavar = o.choices ? `{${o.choices.join(",")}}` : o.dest.toUpperCase();
  const text = o.action === "store_true" ? name : `${name} ${metavar}`;
  return o.required ? text : `[${text}]`;
}
function usage_for(name, spec) {
  if (name === null) {
    return `usage: ${PROG} [-h]\n              {${ALL_COMMANDS.join(",")}}\n              ...`;
  }
  const parts = [`usage: ${PROG} ${name} [-h]`];
  const grouped = spec.options.filter((o) => o.group);
  const seen_group = new Set();
  for (const o of spec.options) {
    if (o.group) {
      if (seen_group.has(o.group)) continue;
      seen_group.add(o.group);
      parts.push(`[${grouped.filter((g) => g.group === o.group).map((g) => `${g.flags[0]} ${g.dest.toUpperCase()}`).join(" | ")}]`);
    } else parts.push(option_usage(o));
  }
  for (const p of spec.positionals) parts.push(p.nargs === "+" ? `${p.dest} [${p.dest} ...]` : p.dest);
  return parts.join(" ");
}

function help_for(name, spec) {
  const lines = [usage_for(name, spec), ""];
  if (name === null) {
    lines.push(
      "Inspect, query, and safely update imperfect Markdown through a declared or temporary in-memory mdq profile.",
      "",
      "positional arguments:",
      `  {${ALL_COMMANDS.join(",")}}`,
      "",
      "options:",
      "  -h, --help  show this help message and exit"
    );
  } else {
    lines.push("positional arguments:");
    for (const p of spec.positionals) lines.push(`  ${p.dest}`);
    lines.push("", "options:", "  -h, --help  show this help message and exit");
    for (const o of spec.options) lines.push(`  ${o.flags[0]}${o.action === "store_true" ? "" : " " + o.dest.toUpperCase()}`);
  }
  return lines.join("\n") + "\n";
}

// ---- argparse emulation ----
const NEGATIVE_NUMBER = /^-\d+$|^-\d*\.\d+$/;

function py_int(text) {
  // int(str): optional sign, digits with single underscores, surrounding whitespace.
  const m = /^\s*([+-]?)(\d+(?:_\d+)*)\s*$/.exec(text);
  if (!m) return null;
  const value = Number(m[1] + m[2].replace(/_/g, ""));
  return value;
}

function parse_subcommand(name, spec, argv) {
  const long_options = new Map();
  for (const o of spec.options) long_options.set(o.flags[0], o);
  const error = (message) => {
    throw new ArgumentError(message, name);
  };
  const arg_name = (o) => `argument ${o.flags.join("/")}`;

  // _parse_optional equivalent: returns null (positional) or {option, explicit, unknown}
  const classify = (arg) => {
    if (!arg.startsWith("-")) return null;
    if (arg === "-h" || arg === "--help") return { help: true };
    if (long_options.has(arg)) return { option: long_options.get(arg), explicit: null };
    if (arg.length === 1) return null;
    if (arg.includes("=")) {
      const [flag, ...rest] = arg.split("=");
      const value = arg.slice(flag.length + 1);
      if (long_options.has(flag)) return { option: long_options.get(flag), explicit: value };
      if (flag === "--help") return { help: true };
    }
    if (arg.startsWith("--")) {
      const flag = arg.includes("=") ? arg.split("=")[0] : arg;
      const explicit = arg.includes("=") ? arg.slice(flag.length + 1) : null;
      const matches = [...long_options.keys()].filter((f) => f.startsWith(flag));
      if ("--help".startsWith(flag)) matches.push("--help");
      if (matches.length > 1) {
        error(`ambiguous option: ${flag} could match ${matches.join(", ")}`);
      }
      if (matches.length === 1) {
        if (matches[0] === "--help") return { help: true };
        return { option: long_options.get(matches[0]), explicit };
      }
    }
    if (NEGATIVE_NUMBER.test(arg)) return null;
    if (arg.includes(" ")) return null;
    return { unknown: true };
  };

  const namespace = { command: name };
  for (const p of spec.positionals) namespace[p.dest] = null;
  for (const o of spec.options) namespace[o.dest] = o.default !== undefined ? o.default : null;

  const kinds = [];
  let after_separator = false;
  const classified = argv.map((arg) => {
    if (after_separator) { kinds.push("A"); return null; }
    if (arg === "--") { after_separator = true; kinds.push("-"); return null; }
    const info = classify(arg);
    kinds.push(info === null ? "A" : "O");
    return info;
  });

  const extras = [];
  const seen = new Set();
  const seen_non_default = new Set();
  const remaining = [...spec.positionals];
  let i = 0;
  while (i < argv.length) {
    if (kinds[i] === "-") { i += 1; continue; }
    if (kinds[i] === "A") {
      let j = i;
      while (j < argv.length && (kinds[j] === "A" || kinds[j] === "-")) j += 1;
      const run = [];
      for (let k = i; k < j; k++) if (kinds[k] === "A") run.push(argv[k]);
      let offset = 0;
      while (remaining.length && offset < run.length) {
        const p = remaining.shift();
        if (p.nargs === "+") {
          namespace[p.dest] = run.slice(offset);
          offset = run.length;
        } else {
          namespace[p.dest] = run[offset];
          offset += 1;
        }
        seen.add(p.dest);
      }
      extras.push(...run.slice(offset));
      i = j;
      continue;
    }
    const info = classified[i];
    if (info.help) return { help: true };
    if (info.unknown) { extras.push(argv[i]); i += 1; continue; }
    const o = info.option;
    let value;
    if (o.action === "store_true") {
      if (info.explicit !== null) error(`${arg_name(o)}: ignored explicit argument ${py_repr(info.explicit)}`);
      value = true;
      i += 1;
    } else if (info.explicit !== null) {
      value = info.explicit;
      i += 1;
    } else if (i + 1 < argv.length && kinds[i + 1] === "A") {
      value = argv[i + 1];
      i += 2;
    } else {
      error(`${arg_name(o)}: expected one argument`);
    }
    if (o.type === "int") {
      const converted = py_int(value);
      if (converted === null) error(`${arg_name(o)}: invalid int value: ${py_repr(value)}`);
      value = converted;
    }
    if (o.choices && !o.choices.includes(value)) {
      const shown = o.type === "int" ? String(value) : py_repr(value);
      error(`${arg_name(o)}: invalid choice: ${shown} (choose from ${o.choices.map((c) => (typeof c === "number" ? String(c) : py_repr(c))).join(", ")})`);
    }
    if (o.group) {
      for (const other of spec.options) {
        if (other.group === o.group && other !== o && seen_non_default.has(other.dest)) {
          error(`${arg_name(o)}: not allowed with argument ${other.flags.join("/")}`);
        }
      }
    }
    if (o.action === "append") namespace[o.dest] = [...(namespace[o.dest] || []), value];
    else namespace[o.dest] = value;
    seen.add(o.dest);
    seen_non_default.add(o.dest);
  }
  const missing = [
    ...spec.positionals.filter((p) => !seen.has(p.dest)).map((p) => p.dest),
    ...spec.options.filter((o) => o.required && !seen.has(o.dest)).map((o) => o.flags.join("/")),
  ];
  if (missing.length) error(`the following arguments are required: ${missing.join(", ")}`);
  return { namespace, extras };
}

function parse_args(argv, parsers) {
  // top-level parser: optional -h, then the required subcommand
  const extras = [];
  let index = 0;
  while (index < argv.length) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help" || (arg.startsWith("--") && "--help".startsWith(arg.split("=")[0]) && arg.length > 2 && !arg.includes("="))) {
      return { help: true, name: null };
    }
    if (arg.startsWith("-") && arg.length > 1 && !NEGATIVE_NUMBER.test(arg) && !arg.includes(" ")) {
      extras.push(arg);
      index += 1;
      continue;
    }
    break;
  }
  if (index >= argv.length) throw new ArgumentError("the following arguments are required: command", null);
  const name = argv[index];
  if (!ALL_COMMANDS.includes(name)) {
    throw new ArgumentError(
      `argument command: invalid choice: ${py_repr(name)} (choose from ${ALL_COMMANDS.map((c) => py_repr(c)).join(", ")})`,
      null
    );
  }
  if (UNSUPPORTED_COMMANDS.has(name)) return { unsupported: name };
  const spec = parsers[name];
  const parsed = parse_subcommand(name, spec, argv.slice(index + 1));
  if (parsed.help) return { help: true, name };
  extras.push(...parsed.extras);
  if (extras.length) throw new ArgumentError(`unrecognized arguments: ${extras.join(" ")}`, null);
  return { namespace: parsed.namespace, handler: spec.handler, name };
}

function print_usage_error(error, parsers) {
  const spec = error.parser ? parsers[error.parser] : null;
  const prog = error.parser ? `${PROG} ${error.parser}` : PROG;
  process.stderr.write(`${usage_for(error.parser, spec)}\n${prog}: error: ${error.message}\n`);
}

// ---- main (6346) ----
export async function main(argv) {
  const parsers = build_parser();
  let parsed;
  try {
    parsed = parse_args(argv, parsers);
  } catch (error) {
    if (!(error instanceof ArgumentError)) throw error;
    print_usage_error(error, parsers);
    return 2;
  }
  if (parsed.help) {
    process.stdout.write(help_for(parsed.name, parsed.name ? parsers[parsed.name] : null));
    return 0;
  }
  if (parsed.unsupported) {
    process.stdout.write(
      JSON.stringify({
        schema: "mdq.error.v1",
        code: "unsupported_in_node",
        message: `command ${py_repr(parsed.unsupported)} is not supported by the Node port; use the Python mdq.py`,
      }) + "\n"
    );
    return 2;
  }
  const { namespace: args, handler } = parsed;
  try {
    if (args.limit !== undefined && args.limit !== null && args.limit < 1) {
      throw new ArgumentError("--limit must be at least 1", null);
    }
    if (args.text === "") throw new ArgumentError("--text must not be empty", null);
  } catch (error) {
    print_usage_error(error, parsers);
    return 2;
  }
  try {
    return Number(await handler(args));
  } catch (exc) {
    if (is_timeout_error(exc)) {
      emit({
        status: "invalid",
        diagnostics: [diagnostic("regex_timeout", "error", "a profile regex exceeded the matching time limit")],
      });
      return 3;
    }
    if (is_decode_error(exc)) {
      emit({
        status: "invalid",
        diagnostics: [diagnostic("encoding_invalid", "error", `document must be UTF-8: ${decode_error_message(exc)}`)],
      });
      return 2;
    }
    if (is_os_error(exc)) {
      const code = exc.code === "ENOENT" ? "file_not_found" : "io_error";
      emit({ status: "invalid", diagnostics: [diagnostic(code, "error", os_error_message(exc))] });
      return 2;
    }
    throw exc;
  }
}

// Direct execution (run_internal_mdq spawns this file).
try {
  if (process.argv[1] && fs.realpathSync(process.argv[1]) === fs.realpathSync(fileURLToPath(import.meta.url))) {
    main(process.argv.slice(2)).then((code) => {
      process.exitCode = code;
    });
  }
} catch {
  /* imported as a module */
}
