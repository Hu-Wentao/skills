---
name: project-weekly-report
description: Generate evidence-based project weekly reports from Git commits for the current or specified author and date range. Use for 项目周报, weekly status reports, Git work summaries, or author/date-filtered committed-work accounts.
---

# Project Weekly Report

Generate a concise Chinese report from committed Git evidence. Git history is not a complete activity record.

## Collect Evidence

Run from the target repository:

```bash
uv run <skill-root>/scripts/collect_git_work.py --repo <repository> \
  [--author <name-or-email>] [--since <date>] [--until <date>]
```

Defaults: current repository; configured Git email then name; exactly seven days before collection through collection time; all visible refs. Author matching is a fixed substring. Git date expressions are accepted.

If collection fails, report the error and do not draft. If no commits match, state the exact repository, author, and range without inventing work.

## Draft

Use Chinese unless requested otherwise. Resolve options explicitly:

- `include_stats=false`; enable only when requested.
- `include_risks=false`; enable only when requested.

```markdown
# 项目周报（<since> — <until>）

## 本周概览
<1–3 sentences on main outcomes>

## 完成事项
- <group related commits into outcome-oriented work>

<!-- only when include_stats=true -->
## 变更统计
- 提交：<count>
- 涉及文件：<count>
- 代码变更：+<insertions> / -<deletions>

<!-- only when include_risks=true -->
## 风险与待确认
- <evidence-backed risk, gap, or “无明确风险记录”>
```

Group related subjects and paths instead of listing every commit. Preserve useful issue IDs, package names, and short hashes. Distinguish fixes, maintenance, docs, and tests only when evidence supports it.

Never infer deployment, business impact, review completion, meetings, uncommitted work, or next-week plans. Add plans only when supplied by the user. Mention the committed-work limitation when material.

The collector emits `project-weekly-report.git-work.v1` JSON with resolved query, commits, per-file numstat, and aggregates. Binary changes affect `binaryFileChanges`, not line totals; merge commits compare with the first parent.
