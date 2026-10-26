"""Squawk 0214: the OAuth callback page is self-contained.

The page opens in the system browser, which has no session cookie, so every
``/static/`` request from it returns 401 and the page rendered unstyled. It now
carries its styles inline, with an explicit minimal subset of the design tokens;
these tests pin that the subset cannot drift from ``css/tokens.css`` and
``css/fonts.css``.
"""

from __future__ import annotations

import re
from pathlib import Path

from the_one.interfaces.web.api import _render_oauth_callback_page

CSS = Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/css"
DECL = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")


def _page() -> str:
    return _render_oauth_callback_page(
        status="success",
        heading="Login successful. You may close this tab.",
        detail_html="You can return to the app.",
        auto_close=True,
        post_message={"type": "mcp-oauth-result", "status": "success"},
    )


def _theme_tokens(path: Path) -> dict[tuple[str | None, str], str]:
    """``(theme, name) -> value``; theme is "light", "dark" or None (a theme-free block)."""
    out: dict[tuple[str | None, str], str] = {}
    theme: str | None = None
    for line in path.read_text().splitlines():
        header = re.match(r'\s*\[data-theme="(light|dark)"\]\s*\{', line)
        if header:
            theme = header.group(1)
            continue
        if re.match(r"^  \}\s*$", line):
            theme = None
            continue
        decl = DECL.search(line)
        if decl and not line.strip().startswith(("/*", "*")):
            out.setdefault((theme, decl.group(1)), decl.group(2).strip())
    return out


def _block(text: str, header: str) -> str:
    start = text.index(header)
    open_at = text.index("{", start)
    depth, i = 0, open_at
    while True:
        depth += text[i] == "{"
        depth -= text[i] == "}"
        if depth == 0:
            return text[open_at + 1 : i]
        i += 1


def test_page_references_nothing_under_static() -> None:
    html = _page()
    assert "/static/" not in html
    assert "<link" not in html
    assert not re.search(r"<script[^>]+src=", html)
    assert "@layer" not in html


def test_page_carries_inline_styles_and_the_result_message() -> None:
    html = _page()
    assert "<style>" in html
    assert "prefers-color-scheme: dark" in html
    assert "window.opener.postMessage" in html
    assert '"mcp-oauth-result"' in html
    assert "Login successful. You may close this tab." in html
    assert "window.close()" in html


def test_every_inlined_token_equals_its_value_in_the_stylesheets() -> None:
    html = _page()
    light = dict(DECL.findall(_block(html, ":root")))
    dark = dict(DECL.findall(_block(_block(html, "@media (prefers-color-scheme: dark)"), ":root")))
    tokens = _theme_tokens(CSS / "tokens.css")
    fonts = _theme_tokens(CSS / "fonts.css")
    assert light and dark
    for name, value in light.items():
        want = tokens.get(("light", name)) or tokens.get((None, name)) or fonts.get((None, name))
        assert want == value.strip(), f"{name}: page {value!r}, stylesheet {want!r}"
    for name, value in dark.items():
        want = tokens.get(("dark", name))
        assert want == value.strip(), f"dark {name}: page {value!r}, stylesheet {want!r}"
    # Every colour the light block names is overridden in dark.
    colours = {n for n in light if (("light", n) in tokens)}
    assert colours <= set(dark), colours - set(dark)


def test_every_var_the_page_uses_is_defined_in_its_own_root() -> None:
    html = _page()
    used = set(re.findall(r"var\((--[a-z0-9-]+)\)", html))
    defined = set(DECL.findall(_block(html, ":root")) and dict(DECL.findall(_block(html, ":root"))))
    assert used <= defined, used - defined


def test_main_landmark_is_plain_and_message_is_an_inner_status() -> None:
    """WCAG 4.1.3 without overriding the landmark: <main> has no role."""
    html = _page()
    assert re.search(r"<main(?![^>]*\brole=)[^>]*>", html)
    assert re.search(r'<[a-z]+ role="status">\s*<p class="oauth-callback-detail">', html)
    assert 'aria-live="polite"' not in html
