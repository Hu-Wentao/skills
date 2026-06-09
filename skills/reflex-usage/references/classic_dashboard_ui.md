# Classic Dashboard UI

## Local Anchors

- Inspect `web/relay_user_portal/relay_user_portal.py` for the concrete Reflex implementation used in this repo.
- Search with:

```bash
rg -n "def page_background|def metric_tile|def summary_tile|def nav_card|def sidebar_nav|def usage_panel|def api_test_panel|def dashboard_page|def api_test_page" web/relay_user_portal/relay_user_portal.py
```

- Inspect `src/lm_web/portal.py` for tone-to-palette mapping:

```bash
rg -n "def tone_palette|class TonePalette" src/lm_web/portal.py
```

## Visual Direction

- Use a calm slate base with one warm accent. In this repo the accent leans orange or teal while text stays in the slate family.
- Use layered surfaces instead of a flat white page. Prefer a soft gradient background plus elevated cards.
- Use generous radii. The established range is roughly `18px` to `30px`.
- Use shadows sparingly. They should separate cards from the background, not dominate the page.
- Keep the hierarchy operational: badge, section label, title, one short explanatory paragraph, then controls or metrics.

## Proven Component Map

- `page_background()`: paint the ambient page layer with radial and linear gradients.
- `nav_card(...)`: render one sidebar navigation entry with active and inactive variants.
- `sidebar_nav(active_page)`: build the left rail; keep it at `max_width="320px"` and stack brand, page links, current identity, and logout action.
- `metric_tile(...)`: render a compact KPI card; use it in responsive grids.
- `summary_tile(...)`: render a larger explanatory card with a title row and status pill.
- `usage_panel()`: combine refresh actions, status copy, metric grids, and summary tiles into the main dashboard surface.
- `api_test_panel()`: combine form controls, action buttons, code blocks, and result blocks into a second dashboard surface.
- `dashboard_page()` and `api_test_page()`: assemble background plus a two-column shell with `display="flex"`, `gap="24px"`, and `flex_wrap="wrap"`.

## Composition Recipe

1. Define shared style dictionaries before defining page components. Keep inputs, textareas, and code blocks consistent across the page.
2. Define repeated primitives such as metric cards, summary cards, code blocks, or result blocks before composing the main panels.
3. Build the sidebar as its own component. Put navigation and account identity there instead of duplicating that information inside the content panel.
4. Build the content panel from top to bottom: badge and main action row, section label, title, explanatory copy, alerts, metrics, secondary blocks.
5. Assemble the final page shell last. Keep the outer wrapper responsible only for background, padding, and the two-column layout.

## Responsive Rules

- Use `grid_template_columns="repeat(auto-fit, minmax(180px, 1fr))"` for dense metric cards.
- Use `grid_template_columns="repeat(auto-fit, minmax(260px, 1fr))"` or `minmax(320px, 1fr)` for richer content blocks.
- Use `flex="1 1 720px"` on the main panel so the content grows without forcing the sidebar to collapse first.
- Use `flex_wrap="wrap"` on action rows and the outer layout to prevent overflow on narrow widths.
- Treat code blocks as overflow-prone elements. Set `whiteSpace="pre-wrap"`, `wordBreak="break-all"`, and `overflowX="auto"`.

## State and Data Rules

- Keep request previews, raw JSON text, and other derived read-only views in `@rx.var` methods.
- Keep runtime styling in state when severity or tone changes with the data. The repo pattern stores `scope_badge_background`, `scope_badge_color`, `current_surface_background`, and `current_border_color` on state.
- Keep event handlers narrow. Let each handler update one concern such as refresh, logout, copy, or one form field.
- Use `rx.cond` for loading, empty, and error states so the panel structure does not jump around.

## Copyable Shell

```python
import reflex as rx


def dashboard_page() -> rx.Component:
    return rx.box(
        page_background(),
        rx.box(
            sidebar_nav("overview"),
            overview_panel(),
            position="relative",
            z_index="1",
            display="flex",
            flex_wrap="wrap",
            gap="24px",
            align_items="stretch",
            width="100%",
        ),
        min_height="100vh",
        position="relative",
        overflow="hidden",
        padding="28px",
    )
```

## Avoid

- Avoid landing-page hero patterns for operator workflows.
- Avoid hard-coded multi-column layouts without `auto-fit` or wrapping.
- Avoid repeating inline styles across ten or more controls when a shared dict would do.
- Avoid rendering JSON, cURL, or logs in plain `rx.text`.
- Avoid mixing unrelated actions into the sidebar just because space is available there.
