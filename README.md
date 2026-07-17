## 介绍
[![skills.sh](https://skills.sh/b/Hu-Wentao/wyatt_skills)](https://skills.sh/Hu-Wentao/wyatt_skills)

常用skill集合

## 本仓库 Skills

### 项目生命周期

- [`project-design-bootstrap`](skills/project-design-bootstrap)：从产品讨论或现有代码库生成可实施的项目设计与脚手架约定。
- [`project-governance`](skills/project-governance)：治理需求、基线、计划、Git 版本、缺陷与验证追踪。

### Skill 工具

- [`skillcraft`](skills/skillcraft)：创建、更新、验证和测试可复用 Codex skill。
- [`update-wyatt-skills`](skills/update-wyatt-skills)：更新本仓库安装的 skill 集合。

### Flutter & Dart

- [`clear-flutter-env`](skills/clear-flutter-env)：清除 macOS 上的 Flutter 镜像环境变量。
- [`create-dart-bg-activity`](skills/create-dart-bg-activity)：创建由 launchd 管理的 Dart macOS 后台进程。
- [`flutter-slang-i18n`](skills/flutter-slang-i18n)：为 Flutter 项目添加和维护 Slang 国际化。
- [`release-dart-package-action`](skills/release-dart-package-action)：通过 Git tag 和 GitHub Actions 发布 Dart/Flutter package。
- [`release-flutter-web-s3`](skills/release-flutter-web-s3)：构建并发布 Flutter Web 到 S3 兼容存储。

### Git 工作流

- [`git-worktree`](skills/git-worktree)：创建和管理 Git worktree 开发环境。
- [`merge-branch-into-current`](skills/merge-branch-into-current)：使用 merge commit 将指定分支合并到当前分支。

### Python UI

- [`edit-streamlit`](skills/edit-streamlit)：构建、调试和重构 Streamlit 应用。
- [`reflex-usage`](skills/reflex-usage)：构建和优化 Reflex 管理后台与门户界面。

### 知识与文档

- [`make-markdown-queryable`](skills/make-markdown-queryable)：查询半结构化 Markdown，并按需建立持久化查询契约。

## 安装
> 方式1. 通过 pnpm dlx 临时使用 vercel agent-skills 安装本仓库技能

```bash
npx skills add Hu-Wentao/wyatt_skills
```

> 方式2. 通过 pnpm 安装 vercel agent-skills 后, 安装本仓库技能
```bash
# 全局安装 skills
pnpm add -g skills

# 再执行添加命令
skills add Hu-Wentao/wyatt_skills
```


## 其他常用Skills

### openai/anthropics/flutter 官方skill
```bash
npx skills add openai/skills
npx skills add anthropics/skills
npx skills add flutter/skills
```

### Web & 浏览器
- Next.js 网站开发
```bash
npx skills add vercel-labs/agent-skills
```
- ChromeCDP
```bash
npx skills add pasky/chrome-cdp-skill
```
- 给Agent使用的智能curl，用于替代一次性py脚本
```bash
npx skills add yusukebe/ax 
```

### 文档材料制作
- 幻灯片制作
```bash
npx skills add slidevjs/slidev
```
- 视频制作
```bash
npx skills add remotion-dev/skills
```

### Flutter
E2E测试 https://ai-dashboad.github.io/flutter-skill/
```bash
pnpm install -g flutter-skill
```

flowr-mvvm
```bash
npx skills add Hu-Wentao/flowr
```

## 常用Skills资源
- https://github.com/anthropics/skills
- https://github.com/vercel-labs/agent-skills
- https://vercel.com/docs/agent-resources/skills
