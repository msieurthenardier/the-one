"""The provider models panel is mounted once and patched by key (M31 F1 L6, flight DD1).

A refresh (the Refresh button, a Load/Unload/Delete on another row, a pull finishing, the
editor's Test) re-fetches and reconciles the list; it never rebuilds the panel's shell. These
tests prove what that buys: a pull in progress survives, the pull select keeps its choice,
focus stays on a row's action, cached library models show while the library fills (squawk
0139), the row Delete arms with the library's armed style, and the non-Ollama list is reconciled
without a rebuild.

Every Ollama endpoint the panel reads is stubbed with ``page.route``; the library search and size
routes fall through to the app's default catalog seam (``conftest.py``).

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

# ── Module-scoped app + providers ─────────────────────────────────────────


@pytest.fixture(scope="module")
def patch_app(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, str]]:
    """One shared app with an Ollama provider and an openai-compatible one."""
    tmp_path = tmp_path_factory.mktemp("the-one-data-models-patch")
    base_url, proc, _credential, _data_dir = _spawn_app(tmp_path)
    try:
        r = httpx.post(
            f"{base_url}/api/providers",
            json={
                "name": "Basic Provider",
                "type": "openai-compatible",
                "base_url": "http://localhost:1/v1",
                "api_key": "k",
            },
            headers=auth_headers_for(base_url),
            timeout=5.0,
        )
        assert r.status_code == 201, r.text
        yield {
            "base_url": base_url,
            "ollama": _seed_ollama_provider(base_url),
            "basic": r.json()["id"],
        }
    finally:
        _unregister_credential(base_url)
        _teardown_proc(proc)


class Ollama:
    """A stubbed Ollama server holding rows, with a record of what the page asked for."""

    def __init__(self, page: Page) -> None:
        self.all = ["alpha:1b", "beta:2b"]
        self.running: list[str] = []
        self.models_hits = 0
        self.pulls: list[dict] = []
        self.held_pull: list[Route] = []
        self.held_actions: list[tuple[str, Route]] = []
        self.hold_actions = False
        self.pull_response: str | None = None  # None: hold the request open
        page.route("**/api/providers/*/models", self._models)
        page.route("**/api/providers/*/models/status", self._status)
        page.route("**/api/providers/*/models/pull", self._pull)
        for action in ("load", "unload", "delete"):
            page.route(f"**/api/providers/*/models/{action}", self._action(action))

    def _models(self, route: Route) -> None:
        self.models_hits += 1
        route.fulfill(
            json=[
                {"name": n, "size": 1_300_000_000, "capabilities": ["completion"]} for n in self.all
            ]
        )

    def _status(self, route: Route) -> None:
        route.fulfill(json=[{"name": n, "size_vram": 900_000_000} for n in self.running])

    def _pull(self, route: Route) -> None:
        self.pulls.append(json.loads(route.request.post_data or "{}"))
        if self.pull_response is None:
            self.held_pull.append(route)
        else:
            route.fulfill(status=200, content_type="text/event-stream", body=self.pull_response)

    def _action(self, action: str):
        def handler(route: Route) -> None:
            if self.hold_actions:
                self.held_actions.append((action, route))
            else:
                self.apply(action, route)

        return handler

    def apply(self, action: str, route: Route) -> None:
        model = json.loads(route.request.post_data or "{}")["model"]
        if action == "load" and model not in self.running:
            self.running.append(model)
        elif action == "unload" and model in self.running:
            self.running.remove(model)
        elif action == "delete":
            self.all.remove(model)
        route.fulfill(json={"ok": True})

    def release_actions(self) -> None:
        held, self.held_actions = self.held_actions, []
        for action, route in held:
            self.apply(action, route)

    def release_pull(self) -> None:
        for route in self.held_pull:
            try:
                route.fulfill(
                    status=200,
                    content_type="text/event-stream",
                    body='data: {"status": "success"}\n\n',
                )
            except Exception:  # the page already aborted it
                pass
        self.held_pull.clear()


@pytest.fixture
def ollama(page: Page) -> Iterator[Ollama]:
    o = Ollama(page)
    try:
        yield o
    finally:
        o.release_pull()


def wait_until(page: Page, predicate, timeout_ms: int = 8000) -> None:
    """Poll a Python predicate (the stub's state) while Playwright keeps serving routes."""
    waited = 0
    while not predicate():
        assert waited < timeout_ms, "timed out waiting for the stub"
        page.wait_for_timeout(50)
        waited += 50


def open_ollama(page: Page, app: dict[str, str]) -> None:
    _nav.goto(page, app["base_url"], f"library/providers/{_nav.seg(app['ollama'])}")
    expect(page.get_by_test_id("admin-pf-pull-select")).to_be_enabled(timeout=15000)
    expect(page.locator(".admin-pf-model-row")).to_have_count(2, timeout=10000)


def row(page: Page, name: str):
    return page.locator(".admin-pf-model-row").filter(has=page.get_by_text(name, exact=True))


def refresh_btn(page: Page):
    return page.locator(".admin-pf-models-refresh")


def select(page: Page):
    return page.get_by_test_id("admin-pf-pull-select")


def start_pull(page: Page, model: str = "llama3.2:3b") -> None:
    select(page).select_option(value=model)
    page.get_by_test_id("admin-pf-pull-btn").click()
    page.get_by_test_id("admin-pf-pull-confirm-go").click()
    expect(page.get_by_test_id("admin-pf-pull-progress")).to_be_visible()


# ── (a) a pull survives a refresh ─────────────────────────────────────────


@pytest.mark.browser
def test_refresh_during_a_pull_keeps_the_progress_node_value_and_cancel(
    page: Page, ollama: Ollama, patch_app: dict[str, str]
) -> None:
    ollama.pull_response = None  # hold the pull open
    open_ollama(page, patch_app)
    start_pull(page)
    page.evaluate(
        "() => { window.__pp = document.querySelector('[data-testid=admin-pf-pull-progress]'); }"
    )
    hits = ollama.models_hits

    # A Load on another row refreshes the panel while the pull is in progress.
    row(page, "alpha:1b").get_by_role("button", name="Load").click()
    expect(page.locator(".admin-pf-model-row[data-section=running]")).to_have_count(1)
    assert ollama.models_hits > hits

    same = page.evaluate(
        "() => document.querySelector('[data-testid=admin-pf-pull-progress]') === window.__pp"
    )
    assert same, "the progress node was replaced by the refresh"
    progress = page.get_by_test_id("admin-pf-pull-progress")
    expect(progress).to_be_visible()
    expect(progress.get_by_role("progressbar", name="Pull progress")).to_have_count(1)
    expect(select(page)).to_be_disabled()
    expect(refresh_btn(page)).to_be_disabled()

    page.get_by_test_id("admin-pf-pull-cancel").click()
    expect(progress).to_be_hidden()
    expect(select(page)).to_be_enabled()
    expect(refresh_btn(page)).to_be_enabled()


# ── (b) the pull select's choice survives a refresh ───────────────────────


@pytest.mark.browser
def test_pull_select_choice_survives_a_refresh(
    page: Page, ollama: Ollama, patch_app: dict[str, str]
) -> None:
    open_ollama(page, patch_app)
    select(page).select_option(value="llama3.2:3b")
    page.evaluate(
        "() => { window.__sel = document.querySelector('[data-testid=admin-pf-pull-select]'); }"
    )
    hits = ollama.models_hits

    refresh_btn(page).click()
    wait_until(page, lambda: ollama.models_hits > hits)
    page.wait_for_timeout(300)  # the library fetch lands too

    assert page.evaluate(
        "() => document.querySelector('[data-testid=admin-pf-pull-select]') === window.__sel"
    )
    expect(select(page)).to_have_value("llama3.2:3b")
    expect(page.get_by_test_id("admin-pf-pull-btn")).to_have_text("Pull · 2.0 GB")
    expect(page.get_by_test_id("admin-pf-pull-size")).to_have_text(
        "Download: 2.0 GB, from the Ollama registry."
    )


@pytest.mark.browser
def test_test_success_refreshes_the_panel_in_place(
    page: Page, ollama: Ollama, patch_app: dict[str, str]
) -> None:
    page.route(
        "**/api/providers/*/test",
        lambda r: r.fulfill(json={"status": "ok", "detail": "Connected"}),
    )
    open_ollama(page, patch_app)
    select(page).select_option(value="llama3.2:1b")
    page.evaluate(
        "() => { window.__shell = document.querySelector('.provider-models').firstElementChild; }"
    )
    hits = ollama.models_hits

    page.get_by_test_id("test-connection-btn").click()
    wait_until(page, lambda: ollama.models_hits > hits)
    assert page.evaluate(
        "() => document.querySelector('.provider-models').firstElementChild === window.__shell"
    )
    expect(select(page)).to_have_value("llama3.2:1b")


# ── (c) focus on a row's action survives a refresh ────────────────────────


@pytest.mark.browser
def test_focus_on_a_rows_load_survives_a_refresh(
    page: Page, ollama: Ollama, patch_app: dict[str, str]
) -> None:
    open_ollama(page, patch_app)
    ollama.hold_actions = True
    row(page, "beta:2b").get_by_role("button", name="Load").click()
    wait_until(page, lambda: len(ollama.held_actions) == 1)

    alpha_load = row(page, "alpha:1b").get_by_role("button", name="Load")
    alpha_load.focus()
    expect(alpha_load).to_be_focused()
    hits = ollama.models_hits

    ollama.release_actions()  # beta loads, the panel refreshes: beta moves to Running
    expect(page.locator(".admin-pf-model-row[data-section=running]")).to_have_count(1)
    assert ollama.models_hits > hits
    expect(row(page, "alpha:1b").get_by_role("button", name="Load")).to_be_focused()


@pytest.mark.browser
def test_focus_follows_a_row_that_changes_section(
    page: Page, ollama: Ollama, patch_app: dict[str, str]
) -> None:
    open_ollama(page, patch_app)
    load = row(page, "alpha:1b").get_by_role("button", name="Load")
    load.click()
    unload = row(page, "alpha:1b").get_by_role("button", name="Unload")
    expect(unload).to_be_visible()
    expect(unload).to_be_enabled()
    expect(unload).to_be_focused()
    assert [page.locator(".admin-pf-section-label").nth(i).inner_text() for i in range(2)] == [
        "Running",
        "Available",
    ]


# ── (d) squawk 0139: cached models show while the library fills ───────────


@pytest.mark.browser
def test_loading_response_with_models_shows_them_while_polling(
    page: Page, ollama: Ollama, patch_app: dict[str, str]
) -> None:
    calls = {"n": 0}

    def search(route: Route) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            route.fulfill(
                json={
                    "loading": True,
                    "models": [{"name": "cached:1b", "size": 1_000_000_000, "status": "ok"}],
                }
            )
        else:
            route.continue_()

    page.route("**/api/ollama-library/search", search)
    _nav.goto(page, patch_app["base_url"], f"library/providers/{_nav.seg(patch_app['ollama'])}")
    expect(select(page)).to_be_enabled(timeout=15000)
    # The cached model is offered, not the loading copy, while the poll continues.
    options = select(page).locator("option")
    expect(options).to_have_text(["Select a model…", "cached:1b (1.0 GB)"], timeout=1500)
    expect(select(page)).not_to_contain_text("Loading models and sizes")
    # The poll asks again after 2 s and the real list replaces the cached one.
    expect(options).to_have_count(7, timeout=10000)
    assert calls["n"] >= 2


# ── (e) the row Delete arms, then commits ─────────────────────────────────


@pytest.mark.browser
def test_row_delete_arms_with_the_library_style_then_commits(
    page: Page, ollama: Ollama, patch_app: dict[str, str]
) -> None:
    open_ollama(page, patch_app)
    delete = row(page, "alpha:1b").get_by_role("button", name="Delete")
    delete.click()
    armed = row(page, "alpha:1b").get_by_role("button", name="Confirm delete?")
    expect(armed).to_be_visible()
    expect(armed).to_have_class(re.compile(r"\bconfirm-delete\b"))
    assert ollama.all == ["alpha:1b", "beta:2b"]  # arming deletes nothing

    # A refresh while armed keeps the armed state: the row node is the same one.
    refresh_btn(page).click()
    page.wait_for_timeout(300)
    expect(armed).to_be_visible()

    armed.click()
    expect(row(page, "alpha:1b")).to_have_count(0)
    assert ollama.all == ["beta:2b"]
    # The deleted row's focus goes to the neighbouring row's first action.
    expect(row(page, "beta:2b").get_by_role("button", name="Load")).to_be_focused()


# ── Pull success shows the new model ──────────────────────────────────────


@pytest.mark.browser
def test_pull_success_refreshes_and_lists_the_new_model(
    page: Page, ollama: Ollama, patch_app: dict[str, str]
) -> None:
    ollama.pull_response = None
    open_ollama(page, patch_app)
    start_pull(page, "llama3.2:1b")
    ollama.all.append("llama3.2:1b")
    ollama.release_pull()
    expect(row(page, "llama3.2:1b")).to_be_visible()
    expect(row(page, "llama3.2:1b").get_by_role("button", name="Load")).to_be_visible()
    expect(page.get_by_test_id("admin-pf-pull-progress")).to_be_hidden()
    expect(select(page)).to_have_value("")  # reset after a pull finishes


# ── (f) the basic list is reconciled, not rebuilt ─────────────────────────


@pytest.mark.browser
def test_basic_list_refresh_reconciles_without_rebuilding(
    page: Page, patch_app: dict[str, str]
) -> None:
    models = {"names": ["one", "two"]}
    page.route(
        "**/api/providers/*/models",
        lambda r: r.fulfill(json=[{"id": n} for n in models["names"]]),
    )
    _nav.goto(page, patch_app["base_url"], f"library/providers/{_nav.seg(patch_app['basic'])}")
    items = page.locator(".admin-pf-model-item")
    expect(items).to_have_text(["one", "two"], timeout=10000)
    page.evaluate(
        """() => {
          window.__shell = document.querySelector('.admin-pf-models-list');
          window.__two = [...document.querySelectorAll('.admin-pf-model-item')][1];
        }"""
    )

    models["names"] = ["two", "three"]
    refresh_btn(page).click()
    expect(items).to_have_text(["two", "three"])
    assert page.evaluate(
        """() => document.querySelector('.admin-pf-models-list') === window.__shell &&
                [...document.querySelectorAll('.admin-pf-model-item')][0] === window.__two"""
    )

    models["names"] = []
    refresh_btn(page).click()
    expect(page.locator(".admin-pf-models-empty")).to_be_visible()
    expect(page.locator(".admin-pf-models-empty")).to_contain_text("No models found.")
    expect(items).to_have_count(0)


@pytest.mark.browser
def test_basic_list_error_shows_a_status_line(page: Page, patch_app: dict[str, str]) -> None:
    page.route(
        "**/api/providers/*/models",
        lambda r: r.fulfill(status=502, json={"detail": "upstream down"}),
    )
    _nav.goto(page, patch_app["base_url"], f"library/providers/{_nav.seg(patch_app['basic'])}")
    status = page.locator(".admin-pf-models-list .ui-status")
    expect(status).to_have_text("upstream down", timeout=10000)
    expect(status).to_have_attribute("data-state", "danger")
