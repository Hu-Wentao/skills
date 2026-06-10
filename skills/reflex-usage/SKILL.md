---
name: reflex-usage
description: >
  Proven patterns for building or refining Reflex admin dashboards, user portals,
  operations consoles, and classic sidebar-plus-content management UIs. Use when
  editing `.py` files that import `reflex as rx`, creating metric cards, left
  navigation sidebars, status panels, action forms, code or result blocks, or
  responsive dashboard pages. When bootstrapping a new Reflex app, prefer
  `reflex init --template dashboard` by default, and switch to
  `customer_data_app` or `api_admin_panel` only when the product shape matches
  those templates more closely.
---

# Reflex Usage

Build admin pages the way this repo already does: stable information hierarchy first, visual polish second.

## Workflow

1. Confirm that the target is an internal tool, admin page, or operator dashboard. Prefer this skill over a marketing-style layout.
2. If you are creating a new Reflex app or first-pass shell, initialize from a template instead of a blank app. Default to `reflex init --template dashboard` for sidebar-plus-content dashboards; use `reflex init --template customer_data_app` for CRUD or admin backoffice flows; use `reflex init --template api_admin_panel` for internal tools, API consoles, or task-management surfaces.
3. Read [references/classic_dashboard_ui.md](references/classic_dashboard_ui.md) before composing new UI. Open `web/relay_user_portal/relay_user_portal.py` if exact local examples are needed.
4. Extract or reuse module-level style tokens first. Prefer shared dicts and helper components over repeated inline styling.
5. Compose the page in four layers: background, sidebar, main panel, repeated section primitives.
6. Drive status styling from state. Prefer palette-backed state fields for status badges, borders, and panel backgrounds.
7. Validate desktop and narrow widths. Preserve readable grids with `repeat(auto-fit, minmax(...))`, `flex_wrap="wrap"`, and a sidebar capped at `max_width="320px"`.

## Layout Rules

- Keep the shell shallow. Prefer one outer `rx.box` for the page, one inner `rx.box` for the two-column layout, and one component each for sidebar and content.
- Use a classic left sidebar plus right content region. Let the sidebar stay readable and self-contained; let the content panel own metrics, forms, tables, and results.
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
- Prefer explicit style props over deeply nested theme abstractions when the page is custom and self-contained.
- Keep typography hierarchy obvious: small uppercase section label, medium title, short explanatory copy, then actionable controls or metrics.
- Keep copy short and operational. Admin pages should answer "what is happening", "what can I do", and "what changed" quickly.
- Bind derived request previews, status summaries, and read-only snippets to `@rx.var` values instead of recomputing them inline in every component tree.
- Use `rx.cond` for empty, loading, and error states so the structure remains stable while the content changes.

## Validation

- Check that the sidebar, main panel, and metric grids remain readable around 320px to 768px widths.
- Check that code blocks wrap safely and do not push the layout horizontally.
- Check that status colors come from shared palette state, not from ad hoc per-widget color decisions.
- Check that the page still feels like the same product family as `web/relay_user_portal/relay_user_portal.py`.

## Reference

Load [references/classic_dashboard_ui.md](references/classic_dashboard_ui.md) when you need the template selection guide, exact component anchors, sizing cues, or a copyable page skeleton.
