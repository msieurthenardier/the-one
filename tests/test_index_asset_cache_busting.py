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

import re

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

    check_static_refs(body)


_REF_RE = re.compile(r'(?:src|href)="(/static/[^"?]*?\.(?:js|css))([^"]*)"')


def check_static_refs(body: str) -> None:
    """Assert the served index's static refs are well formed (squawk 0233).

    Pins existence, a single ``?v=``, no duplicates and the relative load order
    of the scripts; never an exact count (git log holds the history of the count).
    """
    refs = _REF_RE.findall(body)
    assert refs, "no /static refs found"
    paths = [path for path, _ in refs]
    assert len(paths) == len(set(paths)), (
        f"duplicate refs: {sorted({p for p in paths if paths.count(p) > 1})}"
    )
    for path, query in refs:
        assert (STATIC_DIR / path.removeprefix("/static/")).is_file(), f"{path} not on disk"
        assert query == f"?v={__version__}", f"{path} has query {query!r}"

    js = [p.removeprefix("/static/") for p in paths if p.endswith(".js")]

    def first(pred) -> int:
        return next(i for i, p in enumerate(js) if pred(p))

    def last(pred) -> int:
        return max(i for i, p in enumerate(js) if pred(p))

    assert "js/ui/core.js" in js
    core = js.index("js/ui/core.js")
    for i, p in enumerate(js):
        if p.startswith("js/ui/") and p != "js/ui/core.js":
            assert core < i, f"js/ui/core.js must load before {p}"
    last_ui = last(lambda p: p.startswith("js/ui/"))
    first_area = first(lambda p: p.startswith("js/areas/"))
    assert last_ui < first_area, "every js/ui/*.js must load before any js/areas/**"
    for shell, prefix in (
        ("js/areas/studio.js", "js/areas/studio/"),
        ("js/areas/chat.js", "js/areas/chat/"),
        ("js/areas/admin.js", "js/areas/admin/"),
    ):
        assert shell in js, shell
        for i, p in enumerate(js):
            if p.startswith(prefix):
                assert i < js.index(shell), f"{p} must load before the shell {shell}"


def test_static_ref_check_rejects_a_missing_script() -> None:
    with TestClient(app, headers=auth_headers()) as client:
        body = client.get("/").text
    bad = body.replace("js/ui/tabs.js?v=", "js/ui/no-such-file.js?v=", 1)
    with pytest.raises(AssertionError, match="not on disk"):
        check_static_refs(bad)


def test_static_ref_check_rejects_an_area_script_above_ui_core() -> None:
    with TestClient(app, headers=auth_headers()) as client:
        body = client.get("/").text
    core = f'<script src="/static/js/ui/core.js?v={__version__}"></script>'
    area = f'<script src="/static/js/areas/chat/composer.js?v={__version__}"></script>'
    assert core in body and area in body
    bad = body.replace(area, "", 1).replace(core, area + core, 1)
    with pytest.raises(AssertionError, match="must load before"):
        check_static_refs(bad)


def test_static_ref_check_rejects_a_duplicate_ref() -> None:
    with TestClient(app, headers=auth_headers()) as client:
        body = client.get("/").text
    tag = f'<script src="/static/js/ui/tabs.js?v={__version__}"></script>'
    with pytest.raises(AssertionError, match="duplicate"):
        check_static_refs(body.replace(tag, tag + tag, 1))


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
