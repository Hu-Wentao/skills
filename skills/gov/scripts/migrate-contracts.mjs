#!/usr/bin/env node
// One-off: replace every defect file's mdq contract (inline or wrong profile) with a profile reference.
// usage: migrate-contracts.mjs --root DIR [--dir docs/defects] [--profile project-governance/defect-profile-v1] [--apply]
// Only the front matter `mdq:` block is rewritten. Files with no `mdq:` block or without front matter are listed and left alone.
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import path from "node:path";

const argv = process.argv.slice(2);
const opt = (n, d) => (argv.includes(n) ? argv[argv.indexOf(n) + 1] : d);
const root = path.resolve(opt("--root", process.cwd()));
const dir = path.join(root, opt("--dir", "docs/defects"));
const profile = opt("--profile", "project-governance/defect-profile-v1");
const apply = argv.includes("--apply");
const WANT = ["mdq:", `  profile: ${profile}`];

const summary = { already: 0, changed: 0, skipped: [] };
for (const name of readdirSync(dir).filter((f) => /^DEF-.*\.md$/.test(f)).sort()) {
  const full = path.join(dir, name);
  const text = readFileSync(full, "utf-8");
  const lines = text.split(/(?<=\n)/);
  const eol = text.includes("\r\n") ? "\r\n" : "\n";
  if (lines[0]?.replace(/^﻿/, "").trim() !== "---") { summary.skipped.push([name, "no front matter"]); continue; }
  let end = -1;
  for (let i = 1; i < lines.length; i++) if (["---", "..."].includes(lines[i].trim())) { end = i; break; }
  if (end < 0) { summary.skipped.push([name, "front matter not closed"]); continue; }
  const start = lines.findIndex((l, i) => i > 0 && i < end && /^mdq:\s*$/.test(l.replace(/\r?\n$/, "")));
  if (start < 0) { summary.skipped.push([name, "no mdq: block in front matter"]); continue; }
  let stop = start + 1;
  while (stop < end && /^(\s|$)/.test(lines[stop].replace(/\r?\n$/, "")) ) stop++;
  // keep trailing blank lines outside the block
  while (stop > start + 1 && lines[stop - 1].trim() === "") stop--;
  const block = lines.slice(start, stop).map((l) => l.replace(/\r?\n$/, ""));
  if (block.length === WANT.length && block.every((l, i) => l === WANT[i])) { summary.already++; continue; }
  if (/^\s*profile:\s*\S+/.test(block.slice(1).join("\n")) === false && block.length > 1 && !block.some((l) => /^\s+records:/.test(l))) {
    summary.skipped.push([name, "unrecognised mdq block shape"]); continue;
  }
  const next = [...lines.slice(0, start), ...WANT.map((l) => l + eol), ...lines.slice(stop)].join("");
  summary.changed++;
  if (apply) writeFileSync(full, next);
}
console.log(`${apply ? "applied" : "dry run"}: ${summary.changed} changed, ${summary.already} already on ${profile}, ${summary.skipped.length} skipped`);
for (const [n, why] of summary.skipped) console.log(`  skip ${n}: ${why}`);
