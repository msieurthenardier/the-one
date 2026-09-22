"""Tests for cache-busting of front-end static assets on ``GET /`` (F09-07).

The packaged app's WebView was serving stale cached ``/static`` JS/CSS after an
in-place upgrade because index.html referenced assets with stable URLs and the
HTML document carried no cache-control. ``index()`` now:

  - appends ``?v={__version__}`` to every ``/static/*.js`` and ``/static/*.css``
    reference (server-side rewrite; index.html on disk is untouched), and
  - returns the HTML with a ``Cache-Control: no-store`` response header.

The ``/static`` mount ignores the ``?v=`` query string, so versioned URLs still
resolve.

Uses starlette.testclient.TestClient (already transitive via FastAPI).
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from tests._credential_helpers import auth_headers
from the_one import __version__
from the_one.interfaces.web.app import STATIC_DIR, app

# ``with TestClient(app)`` drives the REAL lifespan to shutdown, which
# latches ``_shutting_down = True`` in the PTY session registry, MCP pool,
# and connector pool. Reset those process-globals after each test so later
# modules don't inherit the latch (M17 F1 L4 ordering-flake fix; fixture
# lives in tests/conftest.py).
pytestmark = pytest.mark.usefixtures("reset_lifespan_singletons")


def test_index_appends_version_to_static_asset_refs() -> None:
    """Every /static JS/CSS ref carries ?v={__version__}; none stay bare."""
    with TestClient(app, headers=auth_headers()) as client:
        response = client.get("/")

    assert response.status_code == 200
    body = response.text

    # A known asset is versioned...
    assert f'src="/static/js/areas/chat.js?v={__version__}"' in body
    # ...and the bare (un-versioned) form is gone.
    assert 'src="/static/js/areas/chat.js"' not in body

    # A CSS ref is versioned too.
    assert f'href="/static/css/base.css?v={__version__}"' in body

    # All 55 /static js/css refs are versioned and none are double-suffixed.
    # (Mission 23 Flight 1 Leg 2 deleted the 9 connector-subsystem script
    # tags, dropping the count from 62 to 53; Mission 23 Flight 2 Leg 2 adds
    # the ONE new connector-editor.js script tag back, to 54; Mission 24
    # Flight 6 Leg 4 adds ONE new knowledge-settings-page.js script tag, to
    # 55.)
    import re

    refs = re.findall(r'(?:src|href)="/static/[^"]*?\.(?:js|css)[^"]*"', body)
    assert len(refs) == 55
    for ref in refs:
        assert f"?v={__version__}" in ref
        assert "?v=" in ref and "&v=" not in ref  # single query, no double-suffix
        assert ref.count("?v=") == 1


def test_index_disk_file_unchanged() -> None:
    """The rewrite is server-side only — index.html on disk keeps bare URLs."""
    disk_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert 'src="/static/js/areas/chat.js"' in disk_html
    assert f"?v={__version__}" not in disk_html


def test_index_sends_no_store_cache_control() -> None:
    """GET / sends Cache-Control: no-store so the HTML is always fresh."""
    with TestClient(app, headers=auth_headers()) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_versioned_static_url_resolves() -> None:
    """The static mount ignores ?v= — a versioned asset URL returns 200."""
    with TestClient(app, headers=auth_headers()) as client:
        response = client.get(f"/static/js/areas/chat.js?v={__version__}")

    assert response.status_code == 200
    assert response.content  # actually serves the file body
