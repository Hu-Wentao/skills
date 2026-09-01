export class FrontmatterError extends Error {}

export function parseFrontmatter(content) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(content);
  if (!match) throw new FrontmatterError("Invalid frontmatter format");

  const lines = match[1].split(/\r?\n/);
  const result = Object.create(null);
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim() || line.trimStart().startsWith("#")) continue;
    if (/^\s/.test(line)) continue;

    const keyMatch = /^([A-Za-z0-9_-]+):(?:[ \t]*(.*))?$/.exec(line);
    if (!keyMatch) throw new FrontmatterError(`Invalid YAML at line ${index + 1}`);
    const [, key, rawValue = ""] = keyMatch;
    if (Object.hasOwn(result, key)) throw new FrontmatterError(`Duplicate key: ${key}`);

    if (/^(?:[|>]\+?|[|>]-?)$/.test(rawValue.trim())) {
      const blockLines = [];
      while (index + 1 < lines.length && /^\s/.test(lines[index + 1])) {
        index += 1;
        blockLines.push(lines[index].replace(/^ {1,4}/, ""));
      }
      result[key] = rawValue.trim().startsWith(">")
        ? blockLines.join(" ").trim()
        : blockLines.join("\n").trim();
      continue;
    }
    result[key] = parseScalar(rawValue.trim());
  }
  return result;
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
  if (value.startsWith("{") && value.endsWith("}")) return Object.create(null);
  return value;
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
    else if (character === "[") depth += 1;
    else if (character === "]") depth -= 1;
    else if (character === "," && depth === 0) {
      values.push(value.slice(start, index));
      start = index + 1;
    }
  }
  values.push(value.slice(start));
  return values;
}
