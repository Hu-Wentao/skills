# Reflex Admin Nav Shell

Use this reference when the user wants a Reflex admin navigation shell that feels like the `zen_admin/web/layout.py` pattern from the `zen_trader` repo: a restrained desktop sidebar, a sticky mobile top bar, and one reusable nav-row style across both.

## Load This Reference For

- Left-rail admin navigation in Reflex.
- Mobile menu buttons, drawer triggers, or compact nav dropdown/select controls.
- A reusable app shell that wraps multiple admin pages with one shared navigation layout.
- Requests like "match the zen admin sidebar", "reuse this admin nav UI", or "give me the same sidebar plus mobile menu in another project".

## Design Intent

- Keep the shell operational rather than decorative.
- Let the sidebar own brand, navigation, and a small amount of environment context.
- Keep the main content area visually lighter and wider than the sidebar.
- Reuse one `nav_link` primitive for desktop and mobile so the active state never diverges.
- On mobile, preserve access to the same destinations with a top bar plus drawer instead of collapsing everything into tabs.

## Component Map

- `nav_link(...)`: icon, primary label, secondary slug or meta label, active background, restrained hover state.
- `context_switcher(...)`: optional `rx.select` for environment, workspace, tenant, or scope.
- `sidebar(...)`: desktop-only left rail with brand block, nav stack, switcher, and a small policy or environment card at the bottom.
- `drawer(...)`: mobile-only menu container that reuses `nav_link(...)`.
- `mobile_navbar(...)`: sticky top bar with the menu button, active page title, and optional inline select/dropdown.
- `admin_shell(...)`: page wrapper that combines mobile navbar, sidebar, and the right-side content column.

## Styling Tokens To Extract First

Keep these as module-level tokens before building any page components:

```python
import reflex as rx

BASE_STYLESHEETS = [
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap",
]

BASE_STYLE = {
    "font_family": "Inter",
}

BORDER_RADIUS = "var(--radius-3)"
BORDER = f"1px solid {rx.color('gray', 5)}"
TEXT_COLOR = rx.color("gray", 12)
MUTED_TEXT_COLOR = rx.color("gray", 11)
GRAY_BG_COLOR = rx.color("gray", 2)
ACCENT_TEXT_COLOR = rx.color("accent", 10)
ACCENT_BG_COLOR = rx.color("accent", 3)
SIDEBAR_WIDTH = "28em"
SIDEBAR_CONTENT_WIDTH = "16.5em"
MAX_CONTENT_WIDTH = "1480px"
BOX_SHADOW = "0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)"
```

These tokens are enough to preserve the visual feel without overfitting to one product.

## Structure Rules

1. Keep the sidebar visually quiet: badge, heading, one short descriptive sentence, nav items, switcher, then a small footer card.
2. Make nav rows dense but readable: icon on the left, label stack in the middle, full-width click target, subtle active background.
3. Use `display=[..., "flex"]` or the equivalent responsive arrays to swap desktop and mobile chrome cleanly.
4. Make the sidebar `position="sticky"` on desktop and the top bar `position="sticky"` on mobile.
5. Keep the drawer narrow enough to feel like navigation, not a full-screen modal. The extracted pattern uses roughly `20em`.
6. Put context or environment switching in the shell, not in every page body.

## Copyable Shell

Adapt names and copy, but keep the shape intact:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import reflex as rx


@dataclass(frozen=True)
class NavItem:
    slug: str
    label: str
    href: str
    meta: str
    icon: str


def nav_link(item: NavItem, active_slug: str) -> rx.Component:
    is_active = item.slug == active_slug
    return rx.link(
        rx.hstack(
            rx.icon(item.icon, size=18),
            rx.vstack(
                rx.text(item.label, size="3", weight="medium"),
                rx.text(
                    item.meta,
                    size="1",
                    color=(ACCENT_TEXT_COLOR if is_active else MUTED_TEXT_COLOR),
                ),
                align="start",
                spacing="0",
            ),
            color=(ACCENT_TEXT_COLOR if is_active else TEXT_COLOR),
            align="center",
            spacing="2",
            width="100%",
            padding="0.45rem 0.55rem",
            border_radius=BORDER_RADIUS,
            background_color=(ACCENT_BG_COLOR if is_active else "transparent"),
            opacity=("1" if is_active else "0.92"),
            _hover={
                "background_color": (ACCENT_BG_COLOR if is_active else GRAY_BG_COLOR),
                "opacity": "1",
            },
        ),
        href=item.href,
        underline="none",
        width="100%",
    )


def context_switcher(
    *,
    label: str,
    options: list[str],
    value: str | rx.Var[str],
    on_change: Callable,
    help_text: str,
) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="2", weight="medium", color=MUTED_TEXT_COLOR),
        rx.select(
            options,
            value=value,
            on_change=on_change,
            width="100%",
        ),
        rx.text(help_text, size="1", color=MUTED_TEXT_COLOR),
        align="start",
        spacing="2",
        width="100%",
    )


def sidebar(
    *,
    brand: str,
    title: str,
    description: str,
    items: list[NavItem],
    active_slug: str,
    switcher: rx.Component | None = None,
    footer: rx.Component | None = None,
) -> rx.Component:
    content_children: list[rx.Component] = [
        rx.vstack(
            rx.badge(brand, color_scheme="cyan", radius="full", variant="soft"),
            rx.heading(title, size="5"),
            rx.text(description, size="2", color=MUTED_TEXT_COLOR),
            align="start",
            spacing="2",
            width="100%",
        ),
        rx.vstack(
            *[nav_link(item, active_slug) for item in items],
            spacing="1",
            width="100%",
        ),
    ]
    if switcher is not None:
        content_children.append(switcher)
    content_children.append(rx.spacer())
    if footer is not None:
        content_children.append(footer)

    return rx.flex(
        rx.vstack(
            *content_children,
            justify="start",
            align="start",
            width=SIDEBAR_CONTENT_WIDTH,
            height="100dvh",
            padding="1.1rem",
            spacing="4",
        ),
        display=["none", "none", "none", "none", "none", "flex"],
        max_width=SIDEBAR_WIDTH,
        width="auto",
        height="100%",
        position="sticky",
        top="0px",
        left="0px",
        flex="1",
        justify="start",
        bg=rx.color("gray", 2),
        border_right=BORDER,
    )


def mobile_drawer(
    *,
    brand: str,
    items: list[NavItem],
    active_slug: str,
    switcher: rx.Component | None = None,
    footer_text: str | None = None,
) -> rx.Component:
    drawer_children: list[rx.Component] = [
        rx.hstack(
            rx.badge(brand, color_scheme="cyan", radius="full", variant="soft"),
            rx.spacer(),
            rx.drawer.close(rx.button(rx.icon("x", size=18), variant="ghost", size="2")),
            justify="between",
            align="center",
            width="100%",
        ),
        rx.divider(),
        *[nav_link(item, active_slug) for item in items],
    ]
    if switcher is not None:
        drawer_children.append(switcher)
    drawer_children.append(rx.spacer())
    if footer_text:
        drawer_children.append(rx.text(footer_text, size="2", color=MUTED_TEXT_COLOR))

    return rx.drawer.root(
        rx.drawer.trigger(
            rx.button(
                rx.icon("align-justify", size=18),
                variant="soft",
                size="2",
            )
        ),
        rx.drawer.overlay(z_index="5"),
        rx.drawer.portal(
            rx.drawer.content(
                rx.vstack(
                    *drawer_children,
                    spacing="4",
                    width="100%",
                    height="100%",
                ),
                height="100%",
                width="20em",
                padding="1rem",
                bg=rx.color("gray", 1),
            ),
            width="100%",
        ),
        direction="left",
    )


def mobile_navbar(
    *,
    brand: str,
    active_title: str,
    drawer: rx.Component,
    compact_switcher: rx.Component | None = None,
) -> rx.Component:
    return rx.el.nav(
        rx.hstack(
            drawer,
            rx.vstack(
                rx.text(brand, size="2", weight="bold", color=MUTED_TEXT_COLOR),
                rx.text(active_title, size="4", weight="medium"),
                align="start",
                spacing="0",
            ),
            rx.spacer(),
            rx.cond(
                compact_switcher is not None,
                rx.box(
                    compact_switcher,
                    display=["none", "block", "block", "block", "block", "none"],
                ),
                rx.fragment(),
            ),
            align="center",
            width="100%",
            padding_y="1rem",
            padding_x=["1rem", "1rem", "1.5rem"],
        ),
        display=["block", "block", "block", "block", "block", "none"],
        position="sticky",
        top="0px",
        z_index="5",
        background_color=rx.color("gray", 1),
        border_bottom=BORDER,
    )


def admin_shell(
    *,
    brand: str,
    active_slug: str,
    active_title: str,
    items: list[NavItem],
    title: str,
    description: str,
    content: list[rx.Component],
    switcher: rx.Component | None = None,
    compact_switcher: rx.Component | None = None,
    footer: rx.Component | None = None,
    footer_text: str | None = None,
) -> rx.Component:
    drawer = mobile_drawer(
        brand=brand,
        items=items,
        active_slug=active_slug,
        switcher=switcher,
        footer_text=footer_text,
    )
    body = rx.flex(
        mobile_navbar(
            brand=brand,
            active_title=active_title,
            drawer=drawer,
            compact_switcher=compact_switcher,
        ),
        sidebar(
            brand=brand,
            title=title,
            description=description,
            items=items,
            active_slug=active_slug,
            switcher=switcher,
            footer=footer,
        ),
        rx.flex(
            rx.vstack(
                *content,
                align="start",
                spacing="6",
                width="100%",
                padding="1.25rem",
                min_height="90vh",
            ),
            width="100%",
            padding_x=["0", "0", "1.5rem"],
            padding_y=["0", "0", "1.25rem"],
            max_width=["100%", "100%", "100%", "100%", "100%", MAX_CONTENT_WIDTH],
        ),
        flex_direction=["column", "column", "column", "column", "column", "row"],
        width="100%",
        margin="auto",
        position="relative",
    )
    return rx.theme(
        body,
        has_background=True,
        accent_color="cyan",
        gray_color="slate",
        radius="large",
        scaling="100%",
    )
```

## How To Adapt It

- Replace `brand`, `title`, `description`, and `footer_text` with product-specific copy.
- Replace `meta` with route slug, environment label, org key, or another short secondary identifier.
- Swap icons per destination, but keep their size consistent.
- Use the same switcher component in the sidebar and a narrower variant in the mobile navbar.
- Keep page-specific actions out of the shell unless they truly apply to every page.

## Validation Checklist

- Confirm the nav items read clearly in both active and inactive states.
- Confirm the drawer shows the same destinations as the desktop sidebar.
- Confirm the top bar still works at narrow widths without wrapping into two messy rows.
- Confirm the shell does not force horizontal scrolling when page content contains tables or code.
- Confirm the active page title in the mobile navbar always matches the current route.

## Avoid

- Avoid building separate desktop and mobile nav item styles by hand.
- Avoid putting forms, filters, or per-page primary actions into the sidebar.
- Avoid using a full-screen drawer when the app only needs a narrow navigation panel.
- Avoid hiding the current page identity on mobile; keep the active title visible in the top bar.
