// Smoke: command_query (get) in Node vs scripts/mdq.py. Run: node smoke/query.mjs
import { spawnSync } from "node:child_process";
import { deepStrictEqual } from "node:assert";
import { fileURLToPath } from "node:url";
import { command_query } from "../src/query.mjs";

const mdq = fileURLToPath(new URL("../../scripts/mdq.py", import.meta.url));
const docs = "/home/claude/friday-relay/docs";
const cases = [
  [`${docs}/defects/DEF-20260716-admin-invite-public-url.md`, "DEF-20260716-admin-invite-public-url"],
  [`${docs}/plans/access-point-description.md`, "PLAN-ACCESS-POINT-DESCRIPTION"],
  [`${docs}/plans/access-point-description.md`, "NOPE-123"],
];
// run command_query in a child so stdout (fd 1) and exit code can be captured
const runner = `import {command_query} from ${JSON.stringify(new URL("../src/query.mjs", import.meta.url).href)};
const a=JSON.parse(process.argv[1]);process.exitCode=command_query(a);`;
let failed = 0;
for (const output of ["json", "compact", "minimal"]) {
  for (const [file, id] of cases) {
    const py = spawnSync("uv", ["run", mdq, "get", file, "--id", id, "--output", output], { encoding: "utf-8" });
    const args = { document: file, id, output, select: null };
    const js = spawnSync(process.execPath, ["--input-type=module", "-e", runner, JSON.stringify(args)], { encoding: "utf-8" });
    try {
      if (output === "compact") deepStrictEqual(js.stdout, py.stdout);
      else deepStrictEqual(JSON.parse(js.stdout), JSON.parse(py.stdout));
      deepStrictEqual(js.status, py.status);
      console.log("ok  ", output, id, "exit", js.status);
    } catch (e) {
      failed++;
      console.log("FAIL", output, id, "exit js/py", js.status, py.status, "\n", js.stderr.slice(0, 800), "\n", e.message.slice(0, 1500));
    }
  }
}
process.exit(failed ? 1 : 0);
