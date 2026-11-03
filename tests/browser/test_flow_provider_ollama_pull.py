"""Ollama Pull Model: exact download size first, then an explicit confirmation.

Runs against the shared app's default catalog seam (``OLLAMA_LIBRARY_TEST_CATALOG`` in
``conftest.py``), so no test reaches ollama.com or the registry. Only the Ollama server
endpoints (``/api/providers/*/models``, ``/models/status``, ``/models/pull``) are
stubbed with ``page.route``; the search route is stubbed only for the "loading" case and
the size route only for the 4xx case.

Falls in the ``providers`` lane (``test_flow_provider_*``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser._credential_registry import unregister as _unregister_credential
from browser.conftest import _seed_ollama_provider, _spawn_app, _teardown_proc
from playwright.sync_api import Page, Route, expect

# ── Module-scoped app + provider ──────────────────────────────────────────


@pytest.fixture(scope="module")
def pull_app(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, str]]:
    """One shared app with the default seam and one Ollama provider ("Local Ollama")."""
    tmp_path = tmp_path_factory.mktemp("the-one-data-ollama-pull")
    base_url, proc, _credential, _data_dir = _spawn_app(tmp_path)
    try:
        yield base_url, _seed_ollama_provider(base_url)
    finally:
        _unregister_credential(base_url)
        _teardown_proc(proc)


class Server:
    """The stubbed Ollama server endpoints, with a record of what the page asked for."""

    def __init__(self, page: Page) -> None:
        self.pulls: list[dict] = []
        self.held: list[Route] = []
        self.pull_response: str | None = None  # None: hold the request open
        page.route("**/api/providers/*/models", lambda r: r.fulfill(json=[]))
        page.route("**/api/providers/*/models/status", lambda r: r.fulfill(json=[]))
        page.route("**/api/providers/*/models/pull", self._pull)

    def _pull(self, route: Route) -> None:
        self.pulls.append(json.loads(route.request.post_data or "{}"))
        if self.pull_response is None:
            self.held.append(route)
        else:
            route.fulfill(status=200, content_type="text/event-stream", body=self.pull_response)

    def release(self) -> None:
        for route in self.held:
            try:
                route.fulfill(
                    status=200,
                    content_type="text/event-stream",
                    body='data: {"status": "success"}\n\n',
                )
            except Exception:  # the page already aborted it
                pass
        self.held.clear()


@pytest.fixture
def server(page: Page) -> Iterator[Server]:
    s = Server(page)
    try:
        yield s
    finally:
        s.release()


def open_panel(page: Page, app: tuple[str, str]) -> None:
    base_url, provider_id = app
    _nav.goto(page, base_url, f"library/providers/{_nav.seg(provider_id)}")
    expect(page.get_by_test_id("admin-pf-pull-select")).to_be_enabled(timeout=15000)


def select(page: Page):
    return page.get_by_test_id("admin-pf-pull-select")


def pull_btn(page: Page):
    return page.get_by_test_id("admin-pf-pull-btn")


def choose(page: Page, name: str) -> None:
    select(page).select_option(value=name)


# ── The list ──────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_flat_list_labels_order_and_disabled_entries(
    page: Page, server: Server, pull_app: tuple[str, str]
) -> None:
    open_panel(page, pull_app)
    options = select(page).locator("option")
    labels = [options.nth(i).inner_text() for i in range(options.count())]
    assert labels == [
        "Select a model…",
        "kimi-k3 (cloud only, not downloadable)",
        "llama3.2:1b (1.3 GB)",  # 1b before 3b
        "llama3.2:3b (2.0 GB)",
        "nomic-embed-text (274 MB)",
        "shaky:7b (size unknown)",
        "wizardlm (not downloadable)",
    ]
    disabled = {
        options.nth(i).get_attribute("value"): options.nth(i).is_disabled()
        for i in range(1, options.count())
    }
    assert disabled == {
        "kimi-k3": True,
        "llama3.2:1b": False,
        "llama3.2:3b": False,
        "nomic-embed-text": False,
        "shaky:7b": False,
        "wizardlm": True,
    }


@pytest.mark.browser
def test_pull_button_states_and_status_line(
    page: Page, server: Server, pull_app: tuple[str, str]
) -> None:
    open_panel(page, pull_app)
    size_line = page.get_by_test_id("admin-pf-pull-size")
    expect(size_line).to_have_attribute("aria-live", "polite")

    # (selection, label, enabled, status line)
    expect(pull_btn(page)).to_have_text("Pull")
    expect(pull_btn(page)).to_be_disabled()  # nothing selected
    expect(size_line).to_have_text("")

    choose(page, "llama3.2:3b")
    expect(pull_btn(page)).to_have_text("Pull · 2.0 GB")
    expect(pull_btn(page)).to_be_enabled()
    expect(size_line).to_have_text("Download: 2.0 GB, from the Ollama registry.")
    expect(size_line).not_to_have_attribute("data-state", "warn")

    choose(page, "nomic-embed-text")
    expect(pull_btn(page)).to_have_text("Pull · 274 MB")

    choose(page, "shaky:7b")
    expect(pull_btn(page)).to_have_text("Pull")
    expect(pull_btn(page)).to_be_enabled()
    expect(size_line).to_have_text(
        "Size unknown: the Ollama registry couldn't be reached. Pull will ask before it starts."
    )
    expect(size_line).to_have_class("admin-pf-pull-size admin-pf-pull-size--warn")
    expect(size_line).to_have_attribute("data-state", "warn")

    choose(page, "")
    expect(pull_btn(page)).to_be_disabled()
    expect(size_line).to_have_text("")


@pytest.mark.browser
def test_loading_response_keeps_select_disabled_then_the_list_appears(
    page: Page, server: Server, pull_app: tuple[str, str]
) -> None:
    calls = {"n": 0}

    def search(route: Route) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            route.fulfill(json={"loading": True, "models": []})
        else:
            route.continue_()  # falls through to the seam

    page.route("**/api/ollama-library/search", search)
    base_url, provider_id = pull_app
    _nav.goto(page, base_url, f"library/providers/{_nav.seg(provider_id)}")
    expect(select(page)).to_be_disabled()
    expect(select(page).locator("option")).to_have_text(
        "Loading models and sizes. The first load takes a little while…", timeout=8000
    )
    expect(pull_btn(page)).to_be_disabled()
    # The panel re-requests every 2 s; the second answer is the real list.
    expect(select(page)).to_be_enabled(timeout=10000)
    expect(select(page).locator("option")).to_have_count(7)
    assert calls["n"] >= 2


# ── The Pull click: re-check, then confirm ────────────────────────────────


@pytest.mark.browser
def test_confirmation_names_the_size_and_cancel_sends_no_pull(
    page: Page, server: Server, pull_app: tuple[str, str]
) -> None:
    open_panel(page, pull_app)
    choose(page, "llama3.2:3b")
    pull_btn(page).click()

    dialog = page.get_by_test_id("admin-pf-pull-confirm")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("heading")).to_have_text("Pull llama3.2:3b?")
    expect(dialog).to_contain_text("This downloads 2.0 GB to Local Ollama (localhost:11434).")
    expect(dialog).not_to_contain_text("undefined")
    expect(page.get_by_test_id("admin-pf-pull-confirm-go")).to_have_text("Pull 2.0 GB")
    cancel = page.get_by_test_id("admin-pf-pull-confirm-cancel")
    expect(cancel).to_be_focused()

    cancel.click()
    expect(dialog).to_have_count(0)
    expect(pull_btn(page)).to_be_focused()  # focus returns to the opener
    page.wait_for_timeout(300)
    assert server.pulls == []

    # Escape agrees with Cancel.
    pull_btn(page).click()
    expect(dialog).to_be_visible()
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    page.wait_for_timeout(300)
    assert server.pulls == []


@pytest.mark.browser
def test_confirm_sends_the_pull_and_focuses_the_progress_cancel(
    page: Page, server: Server, pull_app: tuple[str, str]
) -> None:
    open_panel(page, pull_app)
    choose(page, "llama3.2:3b")
    pull_btn(page).click()
    page.get_by_test_id("admin-pf-pull-confirm-go").click()

    # The pull request is held open, so the panel has not re-rendered yet.
    expect(page.get_by_test_id("admin-pf-pull-confirm")).to_have_count(0)
    expect(page.get_by_test_id("admin-pf-pull-progress")).to_be_visible()
    expect(page.get_by_test_id("admin-pf-pull-cancel")).to_be_focused()
    assert server.pulls == [{"model": "llama3.2:3b"}]
    # While a pull runs: Pull and Refresh are disabled, the list is locked.
    expect(pull_btn(page)).to_be_disabled()
    expect(page.locator(".admin-pf-models-refresh")).to_be_disabled()
    expect(select(page)).to_be_disabled()


@pytest.mark.browser
def test_pull_stays_disabled_after_cancel_with_nothing_selected(
    page: Page, server: Server, pull_app: tuple[str, str]
) -> None:
    open_panel(page, pull_app)
    choose(page, "llama3.2:1b")
    pull_btn(page).click()
    page.get_by_test_id("admin-pf-pull-confirm-go").click()
    expect(page.get_by_test_id("admin-pf-pull-progress")).to_be_visible()

    page.get_by_test_id("admin-pf-pull-cancel").click()
    expect(page.get_by_test_id("admin-pf-pull-progress")).to_be_hidden()
    expect(select(page)).to_have_value("")
    expect(pull_btn(page)).to_be_disabled()
    expect(page.locator(".admin-pf-models-refresh")).to_be_enabled()


@pytest.mark.browser
def test_pull_error_text_is_not_double_escaped(
    page: Page, server: Server, pull_app: tuple[str, str]
) -> None:
    server.pull_response = 'data: {"error": "disk & space <full>"}\n\n'
    open_panel(page, pull_app)
    choose(page, "llama3.2:1b")
    pull_btn(page).click()
    page.get_by_test_id("admin-pf-pull-confirm-go").click()
    error = page.get_by_test_id("admin-pf-pull-error")
    expect(error).to_have_text("disk & space <full>")
    expect(pull_btn(page)).to_be_enabled()  # the selection is kept after an error


@pytest.mark.browser
def test_unknown_size_asks_to_pull_anyway(
    page: Page, server: Server, pull_app: tuple[str, str]
) -> None:
    open_panel(page, pull_app)
    choose(page, "shaky:7b")
    pull_btn(page).click()

    dialog = page.get_by_test_id("admin-pf-pull-confirm")
    expect(dialog.get_by_role("heading")).to_have_text("Pull shaky:7b without knowing its size?")
    expect(dialog).to_contain_text(
        "The Ollama registry couldn't be reached, so the download size is unknown. "
        "It could be very large."
    )
    go = page.get_by_test_id("admin-pf-pull-confirm-go")
    expect(go).to_have_text("Pull anyway")
    expect(page.get_by_test_id("admin-pf-pull-confirm-cancel")).to_be_focused()
    go.click()
    expect(page.get_by_test_id("admin-pf-pull-progress")).to_be_visible()
    assert server.pulls == [{"model": "shaky:7b"}]


@pytest.mark.browser
def test_recheck_4xx_shows_an_error_and_no_modal(
    page: Page, server: Server, pull_app: tuple[str, str]
) -> None:
    release: list[Route] = []

    def size(route: Route) -> None:
        release.append(route)  # hold, so the "Checking size…" state is observable

    page.route("**/api/ollama-library/size*", size)
    open_panel(page, pull_app)
    choose(page, "llama3.2:3b")
    pull_btn(page).click()
    expect(pull_btn(page)).to_have_text("Checking size…")
    expect(pull_btn(page)).to_be_disabled()
    assert "llama3.2%3A3b" in release[0].request.url or "llama3.2:3b" in release[0].request.url

    release[0].fulfill(status=422, json={"detail": "invalid model name: 'x'"})
    expect(page.get_by_test_id("admin-pf-pull-error")).to_have_text("invalid model name: 'x'")
    expect(page.get_by_test_id("admin-pf-pull-confirm")).to_have_count(0)
    expect(pull_btn(page)).to_have_text("Pull · 2.0 GB")
    expect(pull_btn(page)).to_be_enabled()
    assert server.pulls == []


@pytest.mark.browser
def test_recheck_that_finds_the_model_gone_refreshes_the_list_only(
    page: Page, server: Server, pull_app: tuple[str, str]
) -> None:
    page.route(
        "**/api/ollama-library/size*",
        lambda r: r.fulfill(json={"name": "llama3.2:3b", "size": None, "status": "missing"}),
    )
    open_panel(page, pull_app)
    choose(page, "llama3.2:3b")
    pull_btn(page).click()
    expect(page.get_by_test_id("admin-pf-pull-confirm")).to_have_count(0)
    expect(page.get_by_test_id("admin-pf-pull-size")).to_have_text(
        "llama3.2:3b is no longer downloadable."
    )
    expect(select(page)).to_have_value("")
    assert server.pulls == []


@pytest.mark.browser
def test_no_request_reaches_ollama_com(
    page: Page, server: Server, pull_app: tuple[str, str]
) -> None:
    seen: list[str] = []
    page.on("request", lambda req: seen.append(req.url))
    open_panel(page, pull_app)
    choose(page, "llama3.2:3b")
    pull_btn(page).click()
    expect(page.get_by_test_id("admin-pf-pull-confirm")).to_be_visible()
    assert not [u for u in seen if "ollama.com" in u or "registry.ollama.ai" in u], seen
    # The backend itself is on the seam too: the search route answers from the catalog.
    base_url, _ = pull_app
    r = httpx.get(
        f"{base_url}/api/ollama-library/search", headers=auth_headers_for(base_url), timeout=5
    )
    assert r.status_code == 200 and r.json()["loading"] is False
    assert [m["name"] for m in r.json()["models"]][:2] == ["kimi-k3", "llama3.2:1b"]


@pytest.mark.browser
def test_empty_list_says_use_pull(page: Page, server: Server, pull_app: tuple[str, str]) -> None:
    """A12: the Ollama empty state points at the Pull control by its real name."""
    open_panel(page, pull_app)
    empty = page.locator(".admin-pf-models-empty")
    expect(empty).to_be_visible(timeout=10000)
    expect(empty).to_contain_text("Use Pull to download one.")
    expect(empty).not_to_contain_text("Pull Model")


@pytest.mark.browser
def test_progress_text_is_the_apps_own_wording_with_a_percentage(
    page: Page, server: Server, pull_app: tuple[str, str]
) -> None:
    """A13: "Pulling {model}… {pct}%" from the first update, never Ollama's raw status."""
    server.pull_response = (
        'data: {"status": "pulling manifest"}\n\n'
        'data: {"status": "pulling abc123", "total": 200, "completed": 50}\n\n'
        'data: {"status": "verifying sha256 digest", "total": 200, "completed": 200}\n\n'
    )
    open_panel(page, pull_app)
    page.evaluate(
        """() => {
          window.__texts = [];
          const node = document.querySelector('[data-testid=admin-pf-pull-progress]');
          new MutationObserver(() => {
            const t = node.textContent.trim();
            if (t && window.__texts[window.__texts.length - 1] !== t) window.__texts.push(t);
          }).observe(node, {childList: true, characterData: true, subtree: true});
        }"""
    )
    choose(page, "llama3.2:3b")
    pull_btn(page).click()
    page.get_by_test_id("admin-pf-pull-confirm-go").click()
    page.wait_for_function("() => window.__texts.length >= 2", timeout=8000)
    texts = page.evaluate("() => window.__texts")
    assert texts, texts
    for t in texts:
        body = re.sub(r"\s*Cancel pull\s*$", "", t).strip()
        assert re.match(r"^Pulling llama3\.2:3b… \d+%$", body), texts
    assert not any("manifest" in t or "verifying" in t or "sha256" in t for t in texts), texts


@pytest.mark.browser
def test_installed_sizes_and_vram_line_are_decimal(
    page: Page, server: Server, pull_app: tuple[str, str]
) -> None:
    """DD8: installed-model sizes and the VRAM summary use the same decimal units as Pull."""
    page.route(
        "**/api/providers/*/models",
        lambda r: r.fulfill(
            json=[
                {"name": "big:latest", "size": 13793441244},
                {"name": "hot:latest", "size": 5000000000},
            ]
        ),
    )
    page.route(
        "**/api/providers/*/models/status",
        lambda r: r.fulfill(json=[{"name": "hot:latest", "size_vram": 2000000000}]),
    )
    open_panel(page, pull_app)
    big = page.locator('.ui-model-row[data-name="big:latest"]')
    expect(big.locator(".ui-model-size")).to_have_text("13.8 GB")
    hot = page.locator('.ui-model-row[data-name="hot:latest"]')
    expect(hot.locator(".ui-model-size")).to_have_text("2.0 GB")
    expect(page.locator(".admin-pf-vram-summary")).to_have_text("2.0 GB loaded")
