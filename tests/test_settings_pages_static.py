"""Static pins for the shared Settings page table (M25 F4 L7, flight DD10, leg AC9).

``static/js/settings-pages.js`` (``App.settingsPages``) is the one table the Settings
nav (``areas/admin.js``), the router's spoken labels (``router.js``) and the jump-to
palette (``jump-to.js``) read. These checks keep it the ONE copy:

* it loads before ``router.js`` in ``index.html`` (the router reads it lazily, but
  the table must exist before any route is described);
* the router's Settings ``SECTIONS`` routes equal the table's sections, in order;
* ``admin.js`` and ``router.js`` hold no copy of a page label or a group name.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "the_one" / "interfaces" / "web" / "static"
JS = STATIC / "js"

_ROW = re.compile(r"\{ section: '([^']+)', label: '([^']+)', group: '([^']+)' \}")
_SETTINGS_SECTION = re.compile(
    r"\{ dest: 'settings', area: 'admin', route: '([^']+)', sub: '[^']+', "
    r"create: (?:true|false) \}"
)


def table() -> list[tuple[str, str, str]]:
    return _ROW.findall((JS / "settings-pages.js").read_text())


def _code(path: Path) -> str:
    """The file without its comment lines (a comment may name a page)."""
    out = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue
        out.append(line)
    return "\n".join(out)


def test_the_table_is_the_six_settings_pages_in_nav_order() -> None:
    assert table() == [
        ("appearance", "Appearance", "General"),
        ("date-and-time", "Date and time", "General"),
        ("prompts", "Prompts", "General"),
        ("encryption", "Encryption", "General"),
        ("tools", "Built-in tools", "Defaults for agents"),
        ("knowledge-indexing", "Knowledge indexing", "Defaults for agents"),
    ]
    # Providers moved to Library (sortie 02): no Providers page, no Models group.
    assert "providers" not in [s for s, _, _ in table()]
    assert "Models" not in {g for _, _, g in table()}
    # Each group's pages are contiguous (the nav builds its groups in table order).
    groups = [g for _, _, g in table()]
    seen: list[str] = []
    for g in groups:
        if not seen or seen[-1] != g:
            assert g not in seen, f"group {g!r} is split in the table"
            seen.append(g)


def test_settings_pages_loads_before_the_router() -> None:
    index = (STATIC / "index.html").read_text()
    scripts = re.findall(r'<script src="/static/js/([^"]+)"', index)
    assert "settings-pages.js" in scripts and "router.js" in scripts
    assert scripts.index("settings-pages.js") < scripts.index("router.js")
    # The palette's module is on the page too, after the store it reads.
    assert scripts.index("store.js") < scripts.index("jump-to.js")


def test_router_settings_routes_equal_the_table_sections() -> None:
    router = (JS / "router.js").read_text()
    routes = _SETTINGS_SECTION.findall(router)
    assert routes == [s for s, _, _ in table()]


def test_admin_and_router_hold_no_copy_of_the_labels() -> None:
    names = {label for _, label, _ in table()} | {group for _, _, group in table()}
    for path in (
        JS / "areas" / "admin.js",
        JS / "areas" / "admin" / "tools-page.js",
        JS / "router.js",
    ):
        code = _code(path)
        dupes = sorted(n for n in names if f"'{n}'" in code or f'"{n}"' in code)
        assert not dupes, f"{path.name} repeats Settings labels from settings-pages.js: {dupes}"


def test_admin_nav_and_router_labels_read_the_table() -> None:
    admin = _code(JS / "areas" / "admin.js")
    assert "App.settingsPages" in admin
    # The route-section mapping and the 'knowledge' category alias stay internal.
    assert "var ROUTE_SECTION = { knowledge: 'knowledge-indexing' };" in admin
    router = _code(JS / "router.js")
    assert "App.settingsPages" in router
    palette = _code(JS / "jump-to.js")
    assert "App.settingsPages" in palette
    assert "#settings/" not in palette  # links are built with App.router.href


def test_tools_page_reaches_the_area_only_through_ctx() -> None:
    """M31 F4 L02a AC5: the tools page uses no admin.js closure name."""
    code = _code(JS / "areas" / "admin" / "tools-page.js")
    banned = re.compile(
        r"(?<!ctx\.)\b(currentCategory|contentEl|editorGen|editorDomStale|settingsNav)\b"
    )
    bare_self = re.compile(r"(?<!ctx\.)\bself\b")
    assert not banned.findall(code), banned.findall(code)
    assert not bare_self.findall(code)
