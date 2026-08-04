---
name: project-weekly-report
description: Generate evidence-based project weekly reports from Git commits for the current or a specified author over the last seven days or a custom time range. Use when Codex needs to create a 项目周报, weekly status report, Git work summary, or author-and-date-filtered account of committed repository work.
---

# Project Weekly Report

Generate a concise Chinese weekly report from structured Git evidence. Treat Git
history as evidence of committed work, not as a complete record of every activity.

## Collect Git evidence

1. Resolve the directory containing this `SKILL.md` as `<skill-dir>`.
2. Run the collector from the target Git repository:

   ```bash
   uv run <skill-dir>/scripts/collect_git_work.py --repo <repository>
   ```

3. Add filters only when requested:

   ```bash
   uv run <skill-dir>/scripts/collect_git_work.py \
     --repo <repository> \
     --author <git-name-or-email> \
     --since <start-date> \
     --until <end-date>
   ```

Use these defaults unless the user specifies otherwise:

- repository: current working directory
- author: `git config user.email`, falling back to `git config user.name`
- since: exactly seven days before collection time
- until: collection time
- revisions: all refs visible in the repository

Accept Git date expressions such as `2026-07-28`, `2026-07-28T09:00:00+08:00`,
or `last Monday`. Match `--author` as a fixed substring of the Git author header,
so either an author name or email is valid.

If the command fails, report its error without drafting a report. If it returns
zero commits, state the repository, author, and time range that were checked; do
not invent work items.

## Draft the report

Read the collector's JSON and write the report in Chinese unless the user asks
for another language. Resolve the optional rendering parameters before
drafting:

- `include_stats`: boolean, default `false`. Set to `true` only when the user
  explicitly requests the `变更统计` section or passes
  `include_stats=true`.
- `include_risks`: boolean, default `false`. Set to `true` only when the user
  explicitly requests the `风险与待确认` section or passes
  `include_risks=true`.

Treat an omitted parameter as `false`; do not infer either option from the
amount or type of Git changes. When an option is `false`, omit its heading and
all of its data from the final report. The collector JSON may still contain the
aggregate evidence needed to render an explicitly requested section.

Use this compact structure, including the two conditional sections only when
their corresponding parameter is `true`:

```markdown
# 项目周报（<since> — <until>）

## 本周概览
<1–3 sentences covering the main themes and result>

## 完成事项
- <group related commits into outcome-oriented work items>

<!-- include only when include_stats=true -->
## 变更统计
- 提交：<count>
- 涉及文件：<count>
- 代码变更：+<insertions> / -<deletions>

<!-- include only when include_risks=true -->
## 风险与待确认
- <only evidence-backed risks, gaps, or “无明确风险记录”>
```

Apply these rules:

- Group related commit subjects and file paths into outcomes instead of listing
  every commit mechanically.
- Preserve meaningful issue IDs, package names, and short commit hashes when
  they improve traceability.
- Separate completed work from fixes, maintenance, documentation, and tests
  only when the evidence supports those distinctions.
- Never infer deployment status, business impact, review completion, meetings,
  uncommitted work, or next-week plans from Git history alone.
- Add a next-week plan only when the user supplies one; otherwise omit it.
- Mention that the report covers committed Git work when that limitation matters.

## Collector output

The script emits `project-weekly-report.git-work.v1` JSON containing the resolved
repository, effective query, commit metadata, per-file numstat data, and aggregate
counts. A binary file change contributes to `binaryFileChanges` but not to line
totals. Merge commits use the diff against their first parent.
