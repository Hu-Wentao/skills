---
name: reflex-usage
description: >
  Proven patterns for building or refining Reflex admin dashboards, user portals,
  operations consoles, and classic sidebar-plus-content management UIs. Use when
  editing `.py` files that import `reflex as rx`, creating metric cards, left
  navigation sidebars, mobile drawer or dropdown nav triggers, status panels,
  action forms, code or result blocks, or responsive dashboard pages. When
  bootstrapping a new Reflex app, prefer `reflex init --template dashboard` by
  default, and switch to `customer_data_app` or `api_admin_panel` only when the
  product shape matches those templates more closely.
---

# Reflex Usage

Build admin pages the way this repo already does: stable information hierarchy first, visual polish second.

## Workflow

1. Confirm that the target is an internal tool, admin page, or operator dashboard. Prefer this skill over a marketing-style layout.
2. If you are creating a new Reflex app or first-pass shell, initialize from a template instead of a blank app. Default to `reflex init --template dashboard` for sidebar-plus-content dashboards; use `reflex init --template customer_data_app` for CRUD or admin backoffice flows; use `reflex init --template api_admin_panel` for internal tools, API consoles, or task-management surfaces.
3. Read [references/classic_dashboard_ui.md](references/classic_dashboard_ui.md) before composing new UI.
4. If the request centers on a reusable admin navigation shell, desktop sidebar, mobile drawer, or a compact top-bar dropdown/select control, also read [references/reflex_admin_nav_shell.md](references/reflex_admin_nav_shell.md).
5. Open repo-local UI files only when exact examples are needed.
6. Extract or reuse module-level style tokens first. Prefer shared dicts and helper components over repeated inline styling.
7. Compose the page in four layers: background, sidebar, main panel, repeated section primitives.
8. Drive status styling from state. Prefer palette-backed state fields for status badges, borders, and panel backgrounds.
9. Validate desktop and narrow widths. Preserve readable grids with `repeat(auto-fit, minmax(...))`, `flex_wrap="wrap"`, and a sidebar capped at `max_width="320px"`.

## Layout Rules

- Keep the shell shallow. Prefer one outer `rx.box` for the page, one inner `rx.box` for the two-column layout, and one component each for sidebar and content.
- Use a classic left sidebar plus right content region. Let the sidebar stay readable and self-contained; let the content panel own metrics, forms, tables, and results.
- On narrow widths, replace the full sidebar with a sticky top navbar plus a drawer or menu trigger. Reuse the same nav item styling instead of inventing a second visual language.
- Use card-like panels for major regions. Prefer rounded corners, soft borders, and restrained shadows over flat admin tables glued directly to the page background.
- Use grids for repeated metrics and paired result blocks. Prefer `repeat(auto-fit, minmax(180px, 1fr))` for compact metrics and `minmax(320px, 1fr)` for larger content cards.
- Keep primary actions near the section header or directly above the affected content. Avoid scattering buttons across the whole page.
- Make long machine-readable content explicit. Render cURL, JSON, or logs in dedicated code or result blocks instead of plain text paragraphs.

## Reuse Targets In This Repo

- Reuse styling tokens from `web/relay_user_portal/relay_user_portal.py`: `AUTH_INPUT_STYLE`, `PANEL_INPUT_STYLE`, `TEXTAREA_STYLE`, `SCRIPT_BOX_STYLE`.
- Reuse composition patterns from `web/relay_user_portal/relay_user_portal.py`: `page_background`, `metric_tile`, `summary_tile`, `nav_card`, `sidebar_nav`, `usage_panel`, `api_test_panel`, `dashboard_page`, `api_test_page`.
- Reuse tone-driven status styling from `src/lm_web/portal.py`: `TonePalette` and `tone_palette()`.
- Extract new primitives when a page repeats the same visual structure three times or more.

## Implementation Notes

- When suggesting project setup commands, always include an explicit `--template` unless the user asks to start from a blank Reflex app. The default recommendation in this skill is `reflex init --template dashboard`.
- Prefer `rx.box`, `rx.text`, `rx.heading`, `rx.button`, `rx.link`, `rx.el.pre`, and simple CSS props for predictable admin layouts.
- When building navigation, extract one `nav_link` primitive and reuse it in the desktop rail and the mobile drawer so hover, active, and spacing rules stay aligned.
- Prefer explicit style props over deeply nested theme abstractions when the page is custom and self-contained.
- Keep typography hierarchy obvious: small uppercase section label, medium title, short explanatory copy, then actionable controls or metrics.
- Keep copy short and operational. Admin pages should answer "what is happening", "what can I do", and "what changed" quickly.
- Bind derived request previews, status summaries, and read-only snippets to `@rx.var` values instead of recomputing them inline in every component tree.
- Use `rx.cond` for empty, loading, and error states so the structure remains stable while the content changes.

## 模块拆分规则

- 大型 Reflex 页面按功能目录拆分，不继续保留 `*_page.py` 大文件：`feature/state.py` 放 `rx.State`，`feature/page.py` 放页面函数，`feature/helpers.py` 放纯 helper，`feature/__init__.py` 只暴露该功能的当前公开 API。
- 入口模块保持窄职责。`app.py` 只负责 `rx.App` 构造、`add_page(...)` 注册、runtime/env 初始化和 CLI 入口；如果能让启动边界更清晰，页面函数和 State class 可以下沉到 `create_app()` 内部导入。
- 路由集中放到 `routes.py`，再由 `app.py`、catalog、导航定义和访问控制定义复用。避免同一个 route 字符串散落在多层 UI 代码里。
- 如果迁移目标明确要求删除旧模块路径，不要添加 re-export shim。直接删除旧 `*_page.py` 模块，并把所有业务代码、测试和动态 import 改到新 package 路径。
- 注意 Python 模块名和 package 名冲突。如果 `web/backtest.py` 这类 helper 模块要变成 `web/backtest/` 目录，把原 helper 代码移动到 `web/backtest/helpers.py`，并直接更新 import。
- 测试 monkeypatch 要打到 State 方法实际查找全局变量的模块。若 `State` 方法引用的是 `feature/state.py` 的模块全局函数，测试应 patch `feature.state`，而不是 `feature.page`。
- 结构拆分时尽量保留 State class 名和页面函数名，除非产品语义需要改名。这样能减少 Reflex 事件绑定层面的额外变化，同时仍然移除旧文件路径。
- `__init__.py` 只导出当前功能真正需要的公开 API。可以导出 state/page 和测试明确依赖的 public hook，但不要借此重建已删除的 legacy path。

## Validation

- Check that the sidebar, main panel, and metric grids remain readable around 320px to 768px widths.
- Check that the mobile nav trigger, drawer, and any top-bar select/dropdown remain usable without horizontal overflow.
- Check that code blocks wrap safely and do not push the layout horizontally.
- Check that status colors come from shared palette state, not from ad hoc per-widget color decisions.
- Check that the page still feels like the same product family as `web/relay_user_portal/relay_user_portal.py`.
- 拆分模块后，用 `rg` 搜索已删除模块路径，例如 `*_page` 和旧 helper import；搜索无结果比只看测试通过更能证明旧路径已清理干净。
- 测试前先对受影响 package 跑 `uv run python -m compileall`，让 import 错误尽早暴露。

## Reference

Load [references/classic_dashboard_ui.md](references/classic_dashboard_ui.md) when you need the template selection guide, exact component anchors, sizing cues, or a copyable page skeleton.
Load [references/reflex_admin_nav_shell.md](references/reflex_admin_nav_shell.md) when you need the `zen_admin`-style sidebar, top navbar, drawer trigger, or context switcher pattern extracted into a reusable Reflex shell.
