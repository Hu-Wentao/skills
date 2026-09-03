export class FrontmatterError extends Error {}

export function parseFrontmatterDocument(content) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(content);
  if (!match) throw new FrontmatterError("Invalid frontmatter format");
  return {
    attributes: parseFrontmatterLines(match[1]),
    body: content.slice(match[0].length),
  };
}

export function parseFrontmatter(content) {
  return parseFrontmatterDocument(content).attributes;
}

function parseFrontmatterLines(source) {
  const lines = source.split(/\r?\n/);
  const result = Object.create(null);
  let parent = null;

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim() || line.trimStart().startsWith("#")) continue;

    const indent = /^ */.exec(line)[0].length;
    if (indent !== 0 && indent !== 2) {
      throw new FrontmatterError(`Unsupported YAML indentation at line ${index + 1}`);
    }
    const keyMatch = /^\s*([A-Za-z0-9_-]+):(?:[ \t]*(.*))?$/.exec(line);
    if (!keyMatch) throw new FrontmatterError(`Invalid YAML at line ${index + 1}`);
    const [, key, rawValue = ""] = keyMatch;
    const target = indent === 0 ? result : parent;
    if (!target) throw new FrontmatterError(`Unexpected nested YAML at line ${index + 1}`);
    if (Object.hasOwn(target, key)) throw new FrontmatterError(`Duplicate key: ${key}`);

    if (/^(?:[|>]\+?|[|>]-?)$/.test(rawValue.trim())) {
      if (indent !== 0) throw new FrontmatterError(`Nested block scalar is unsupported at line ${index + 1}`);
      const blockLines = [];
      while (index + 1 < lines.length && /^\s/.test(lines[index + 1])) {
        index += 1;
        blockLines.push(lines[index].replace(/^ {1,4}/, ""));
      }
      target[key] = rawValue.trim().startsWith(">")
        ? blockLines.join(" ").trim()
        : blockLines.join("\n").trim();
      parent = null;
      continue;
    }

    if (indent === 0 && !rawValue.trim()) {
      target[key] = Object.create(null);
      parent = target[key];
      continue;
    }
    if (indent === 0) parent = null;
    const scalar = rawValue.trim();
    if (isPlainScalar(scalar) && /:\s/.test(scalar)) {
      throw new FrontmatterError(`Invalid YAML plain scalar at line ${index + 1}; quote it or use a block scalar`);
    }
    target[key] = parseScalar(scalar);
  }
  return result;
}

function isPlainScalar(value) {
  return value && !["'", '"', "[", "{"].includes(value[0]);
}

function parseScalar(value) {
  if (!value) return null;
  if (["null", "Null", "NULL", "~"].includes(value)) return null;
  if (["true", "True", "TRUE"].includes(value)) return true;
  if (["false", "False", "FALSE"].includes(value)) return false;
  if (/^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value)) return Number(value);
  if (value.startsWith('"') && value.endsWith('"')) {
    try { return JSON.parse(value); } catch { throw new FrontmatterError("Invalid quoted scalar"); }
  }
  if (value.startsWith("'") && value.endsWith("'")) return value.slice(1, -1).replaceAll("''", "'");
  if (value.startsWith("[") && value.endsWith("]")) return splitFlowValues(value.slice(1, -1)).map((item) => parseScalar(item.trim()));
  if (value.startsWith("{") && value.endsWith("}")) return parseFlowMapping(value.slice(1, -1));
  return value;
}

function parseFlowMapping(value) {
  const result = Object.create(null);
  if (!value.trim()) return result;
  for (const item of splitFlowValues(value)) {
    const separator = item.indexOf(":");
    if (separator < 1) throw new FrontmatterError("Invalid flow mapping");
    const key = item.slice(0, separator).trim();
    if (!/^[A-Za-z0-9_-]+$/.test(key) || Object.hasOwn(result, key)) {
      throw new FrontmatterError("Invalid flow mapping key");
    }
    result[key] = parseScalar(item.slice(separator + 1).trim());
  }
  return result;
}

function splitFlowValues(value) {
  const values = [];
  let start = 0;
  let quote = null;
  let depth = 0;
  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];
    if (quote) {
      if (character === quote && value[index - 1] !== "\\") quote = null;
      continue;
    }
    if (character === '"' || character === "'") quote = character;
    else if (character === "[" || character === "{") depth += 1;
    else if (character === "]" || character === "}") depth -= 1;
    else if (character === "," && depth === 0) {
      values.push(value.slice(start, index));
      start = index + 1;
    }
  }
  values.push(value.slice(start));
  return values;
}
