"""Engine-parametrized browser fixtures and the disk harness for the
``App.ui`` control-library contract tests (M25 F1 L1, DD9).

Fixture family (names deliberately avoid every pytest-playwright 0.7.2 name:
``browser_name``, ``browser_type``, ``browser``, ``page``, ``context``,
``playwright``, ``browser_context_args``, ``browser_type_launch_args``):

- ``engine_browser`` - module-scoped, params ``chromium`` / ``webkit``. WebKit is
  launched lazily (only when a webkit param runs). After launch it runs
  ``about:blank`` + ``evaluate("1")``; a crash there is a launch failure too.
- ``engine_page`` - function-scoped page on ``engine_browser``; records the
  launched engine name and version (``record_property`` + a printed line, so it
  shows in ``-rA`` output - ``report-what-you-got``).

Every test using the family must carry ``@pytest.mark.browser``.

WebKit skip/require policy (a pure function, :func:`webkit_policy`):

- ``THE_ONE_REQUIRE_WEBKIT`` unset: a launch failure SKIPS the webkit param, with
  the failure in the reason.
- ``THE_ONE_REQUIRE_WEBKIT=1``: the same failure FAILS.
- ``THE_ONE_WEBKIT_FORCE_UNAVAILABLE=1``: TEST-ONLY seam. Makes the launch count
  as failed so the skip path can be demonstrated on a host where WebKit works.

Userland WebKit (no sudo; see ``scripts/setup-webkit-userland.sh``): when
``$THE_ONE_WEBKIT_DEPS`` (default ``~/.cache/the-one-webkit-deps``) holds the
generated ``webkit-wrapper.sh``, the WebKit launch uses it as ``executable_path``
and gets ``GST_PLUGIN_PATH`` through ``launch(env=...)``. A wrapper is needed
because Playwright's bundled MiniBrowser script overwrites ``LD_LIBRARY_PATH``.
Neither ``os.environ`` nor any chromium launch is touched.

Disk harness (:func:`load_harness`): loads static assets WITHOUT spawning the app.
Load order is derived from ``static/index.html`` (never a hardcoded file list):
the ``@layer`` order statement first, then every ``/static/css/*.css`` link, then
``icons.js``, then every ``/static/js/ui/*.js`` script, then a themed root.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import NamedTuple

import pytest
from playwright.sync_api import Browser, Page, Playwright

STATIC_DIR = Path(__file__).resolve().parents[2] / "the_one" / "interfaces" / "web" / "static"
INDEX_HTML = STATIC_DIR / "index.html"

ENGINES = ["chromium", "webkit"]

REQUIRE_ENV = "THE_ONE_REQUIRE_WEBKIT"
FORCE_UNAVAILABLE_ENV = "THE_ONE_WEBKIT_FORCE_UNAVAILABLE"
DEPS_ENV = "THE_ONE_WEBKIT_DEPS"


class PolicyResult(NamedTuple):
    kind: str  # "ok" | "skip" | "fail"
    reason: str


def webkit_policy(env: Mapping[str, str], launch_error: str | None) -> PolicyResult:
    """Pure skip/require decision for a WebKit launch.

    ``launch_error`` is None when WebKit launched and passed its smoke check, else
    the failure text. ``THE_ONE_WEBKIT_FORCE_UNAVAILABLE=1`` turns a success into a
    failure (test-only seam)."""
    if env.get(FORCE_UNAVAILABLE_ENV) == "1" and launch_error is None:
        launch_error = f"forced unavailable ({FORCE_UNAVAILABLE_ENV}=1)"
    if launch_error is None:
        return PolicyResult("ok", "")
    if env.get(REQUIRE_ENV) == "1":
        return PolicyResult(
            "fail", f"WebKit required ({REQUIRE_ENV}=1) but unavailable: {launch_error}"
        )
    return PolicyResult("skip", f"WebKit unavailable: {launch_error}")


def _deps_dir() -> Path:
    return Path(os.environ.get(DEPS_ENV) or Path.home() / ".cache" / "the-one-webkit-deps")


def _webkit_launch_kwargs() -> dict:
    """Launch kwargs for WebKit; userland wrapper + gst env only when set up."""
    deps = _deps_dir()
    wrapper = deps / "webkit-wrapper.sh"
    if not wrapper.is_file():
        return {}
    gst = next(iter(sorted((deps / "root").glob("usr/lib/*/gstreamer-1.0"))), None)
    env = dict(os.environ)
    if gst is not None:
        env["GST_PLUGIN_PATH"] = str(gst)
    return {"executable_path": str(wrapper), "env": env}


def _launch(playwright: Playwright, engine: str) -> Browser:
    if engine == "chromium":
        return playwright.chromium.launch(headless=True)
    return playwright.webkit.launch(headless=True, **_webkit_launch_kwargs())


def _smoke(browser: Browser) -> None:
    page = browser.new_page()
    try:
        page.goto("about:blank")
        assert page.evaluate("1") == 1
    finally:
        page.close()


@pytest.fixture(scope="module", params=ENGINES, ids=ENGINES)
def engine_browser(
    request: pytest.FixtureRequest, playwright_instance: Playwright
) -> Iterator[Browser]:
    """The launched engine, per param. Uses conftest's module-scoped
    ``playwright_instance`` so no second driver is started."""
    engine: str = request.param
    browser: Browser | None = None
    error: str | None = None
    if engine == "webkit" and os.environ.get(FORCE_UNAVAILABLE_ENV) == "1":
        error = None  # policy applies the force below without paying for a launch
    else:
        try:
            browser = _launch(playwright_instance, engine)
            _smoke(browser)
        except Exception as exc:  # noqa: BLE001 - any launch/smoke failure counts
            error = str(exc).strip().splitlines()[-1][:300] if str(exc).strip() else repr(exc)
            if browser is not None:
                try:
                    browser.close()
                except Exception:  # noqa: BLE001
                    pass
                browser = None
    if engine == "webkit":
        result = webkit_policy(os.environ, error if browser is None and error else None)
        if result.kind == "skip":
            pytest.skip(result.reason)
        if result.kind == "fail":
            pytest.fail(result.reason)
    elif error is not None:
        pytest.fail(f"{engine} failed to launch: {error}")
    assert browser is not None
    assert browser.browser_type.name == engine, (
        f"asked for {engine}, launched {browser.browser_type.name}"
    )
    try:
        yield browser
    finally:
        browser.close()


@pytest.fixture
def engine_page(engine_browser: Browser, record_property) -> Iterator[Page]:
    name = engine_browser.browser_type.name
    version = engine_browser.version
    record_property("engine", name)
    record_property("engine_version", version)
    print(f"[ui-engine] {name} {version}")
    context = engine_browser.new_context()
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()


# ── Disk harness ────────────────────────────────────────────────────────────


def _index_text() -> str:
    return INDEX_HTML.read_text()


def index_layer_statement() -> str:
    m = re.search(r"<style>\s*(@layer [^<]+?;)\s*</style>", _index_text())
    assert m, "no @layer order statement found in static/index.html"
    return m.group(1)


def index_css_paths() -> list[Path]:
    hrefs = re.findall(r'<link[^>]+href="/static/(css/[^"]+\.css)"', _index_text())
    return [STATIC_DIR / h for h in hrefs]


def index_ui_script_paths() -> list[Path]:
    srcs = re.findall(r'<script[^>]+src="/static/(js/ui/[^"]+\.js)"', _index_text())
    return [STATIC_DIR / s for s in srcs]


def load_harness(page: Page, theme: str = "dark") -> None:
    """Blank page + index-derived assets + a themed root ``#harness-root``.

    ``@font-face`` URLs 404 from a blank page; that is acceptable."""
    assert theme in ("dark", "light"), theme
    page.set_content("<!doctype html><html><head></head><body></body></html>")
    page.add_style_tag(content=index_layer_statement())  # must be the FIRST style tag
    for css in index_css_paths():
        page.add_style_tag(path=str(css))
    page.add_script_tag(path=str(STATIC_DIR / "js" / "icons.js"))
    for script in index_ui_script_paths():
        page.add_script_tag(path=str(script))
    page.evaluate(
        """(theme) => {
            const root = document.createElement('div');
            root.id = 'harness-root';
            root.setAttribute('data-theme', theme);
            root.style.color = 'var(--fg)';
            root.style.background = 'var(--bg)';
            document.body.appendChild(root);
        }""",
        theme,
    )
