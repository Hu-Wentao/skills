---
name: update-wyatt-skills
description: 用于更新 'wyatt_skills'仓库包含的技能集合, 当用户需要更新skills调用.
---

# Update Wyatt Skills

## Overview

本技能提供了一个便捷的方式来更新 `wyatt_skills` 相关的技能。它通过运行一个预定义的脚本来执行官方的更新命令。

## 使用方法

直接运行 `scripts/update.sh` 脚本即可完成更新。

### 脚本说明
- **路径**: `scripts/update.sh`
- **功能**: 执行 `pnpm dlx skills add Hu-Wentao/wyatt_skills` 命令。

## 资源

### scripts/
- `update.sh`: 包含更新逻辑的 Shell 脚本。
