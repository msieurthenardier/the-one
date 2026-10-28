"""Sortie 04 DD1: static pins for the shared sign-in link block."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static"
INDEX = STATIC / "index.html"
MODULE = STATIC / "js/ui/consent-link.js"


def _srcs() -> list[str]:
    return re.findall(r'<script src="/static/js/([^"]+)"></script>', INDEX.read_text())


def test_consent_link_loads_after_copy_field_and_before_its_consumers() -> None:
    srcs = _srcs()
    at = srcs.index("ui/consent-link.js")
    assert srcs.index("ui/copy.js") < at
    for consumer in (
        "areas/chat/sign-in.js",  # M31 F6 L02: the chat sign-in moved out of chat.js
        "areas/studio/mcp-oauth-consent.js",  # M31 F5 L02: the controller no longer calls it
    ):
        assert at < srcs.index(consumer), consumer


def test_module_uses_dom_apis_only_and_literal_testids() -> None:
    text = MODULE.read_text()
    assert "innerHTML" not in text and "insertAdjacentHTML" not in text
    for surface in ("chat", "mcp"):
        for part in ("url", "open", "copy"):
            assert f"'{surface}-consent-link-{part}'" in text
    assert 'target = "_blank"' in text or "target = '_blank'" in text
    assert "noopener noreferrer" in text


def test_desktop_webview_check_is_shared_from_theme_js() -> None:
    theme = (STATIC / "js/theme.js").read_text()
    assert "window.App.desktop.isWebview = function" in theme
    assert "return window.App.desktop.isWebview();" in theme


def test_http_only_rule_is_shared_by_every_open_site() -> None:
    text = MODULE.read_text()
    assert "isSafeUrl" in text and "https?:" in text
    chat = (STATIC / "js/areas/chat/sign-in.js").read_text()
    editor = (STATIC / "js/areas/studio/mcp-oauth-consent.js").read_text()
    assert chat.count("isSafeUrl(") >= 2 and chat.count("consentSafe") >= 3
    assert "isSafeUrl(consentUrl)" in editor
    body = editor[editor.index("function launchConsentPopup") :]
    body = body[: body.index("function onOAuthMessage")]
    assert "innerHTML" not in body
