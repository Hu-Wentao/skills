#!/usr/bin/env node
// Restore skills listed in skills-lock.json into .agents/skills/ at a pinned commit.
// usage: restore-skills.mjs [--root DIR] [--pin] [--force]
//   (default)  for each entry with `commit`, fetch exactly that commit and copy skillPath; entries without a commit are
//              fetched from the default branch and reported as UNPINNED (exit 1 unless --force).
//   --pin      after restoring, write the resolved commit SHA into the lock file entries.
// Lock entry: { "source": "owner/repo", "skillPath": "skills/gov/SKILL.md" | "skills/gov", "commit": "<40-hex>" }
import { readFileSync, writeFileSync, existsSync, mkdtempSync, rmSync, cpSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";
import os from "node:os";

const argv = process.argv.slice(2);
const flag = (n) => argv.includes(n);
const root = path.resolve(argv.includes("--root") ? argv[argv.indexOf("--root") + 1] : process.cwd());
const lock_path = path.join(root, "skills-lock.json");
if (!existsSync(lock_path)) { console.error(`restore-skills: ${lock_path} not found`); process.exit(2); }
const lock = JSON.parse(readFileSync(lock_path, "utf-8"));
const entries = lock.skills ?? {};
const git = (cwd, ...args) => execFileSync("git", args, { cwd, encoding: "utf-8", stdio: ["ignore", "pipe", "pipe"] }).trim();
let unpinned = 0, failed = 0, changed = false;
const cache = new Map(); // source@commit -> checkout dir

for (const [name, entry] of Object.entries(entries)) {
  try {
    if (!/^[\w.-]+\/[\w.-]+$/.test(entry.source ?? "")) throw new Error(`unsupported source ${JSON.stringify(entry.source)} (only owner/repo on GitHub)`);
    const pinned = /^[0-9a-f]{40}$/.test(entry.commit ?? "");
    const key = `${entry.source}@${pinned ? entry.commit : "HEAD"}`;
    if (!cache.has(key)) {
      const dir = mkdtempSync(path.join(os.tmpdir(), "restore-skills-"));
      git(dir, "init", "-q");
      git(dir, "remote", "add", "origin", `https://github.com/${entry.source}`);
      git(dir, "fetch", "-q", "--depth", "1", "origin", pinned ? entry.commit : "HEAD");
      git(dir, "checkout", "-q", "FETCH_HEAD");
      cache.set(key, { dir, sha: git(dir, "rev-parse", "HEAD") });
    }
    const { dir, sha } = cache.get(key);
    if (pinned && sha !== entry.commit) throw new Error(`fetched ${sha}, expected ${entry.commit}`);
    const src = path.join(dir, (entry.skillPath ?? name).replace(/\/SKILL\.md$/, ""));
    if (!existsSync(path.join(src, "SKILL.md"))) throw new Error(`no SKILL.md at ${entry.skillPath}`);
    const dest = path.join(root, ".agents", "skills", name);
    rmSync(dest, { recursive: true, force: true });
    mkdirSync(path.dirname(dest), { recursive: true });
    cpSync(src, dest, { recursive: true, filter: (p) => !p.split(path.sep).includes(".git") });
    if (!pinned) { unpinned++; console.log(`UNPINNED ${name}: restored from ${sha.slice(0, 12)} (run with --pin to record it)`); }
    else console.log(`ok       ${name} @ ${sha.slice(0, 12)}`);
    if (flag("--pin") && !pinned) { entry.commit = sha; changed = true; }
  } catch (error) {
    failed++;
    console.error(`FAILED   ${name}: ${String(error.stderr || error.message).trim().split("\n")[0]}`);
  }
}
for (const { dir } of cache.values()) rmSync(dir, { recursive: true, force: true });
if (changed) { writeFileSync(lock_path, JSON.stringify(lock, null, 2) + "\n"); console.log("pinned commits written to skills-lock.json"); }
process.exit(failed || (unpinned && !flag("--pin") && !flag("--force")) ? 1 : 0);
