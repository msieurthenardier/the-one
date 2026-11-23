"""GleepGlorp fills the model provider editor (M36 F4 L5b, flight DD10 and DD11).

A fill writes unsaved edits into the Library's provider create form or an existing provider's
edit form, a type change included. A fill NEVER carries a key, and an old key is never sent to a
new service: a fill that moves a provider away from a key-taking type empties the key field (Save
then sends null), a key the operator typed is never cleared, and a type the operator chose
differently is kept. Covers, as state transitions:

* the editor seam: ``setType`` does what the type select does; nothing saves, signs in or fetches
  models (AC2);
* [create form] -> [filled: anthropic, name, thinking] -> [typed + saved] (AC3);
* [anthropic with a key] -> [filled: openai | ollama | the plan type] -> Save / Cancel (AC4);
* a type-less fill leaves the key masked, and Save keeps the stored key (AC5);
* the operator's field, key and type are kept; another route asks the leave guard (AC6);
* a key in the fill's values is ignored; a deleted provider is target gone.

Seeds the fills straight into the database and delivers each real view into the drawer's socket,
as ``test_flow_gleepglorp_fill.py`` does. Lives in the ``gleepglorp`` browser lane.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from browser import _drawer, _nav
from browser._credential_registry import auth_headers_for
from browser._mcp_editor import _count, _install_counter
from browser.test_flow_gleepglorp_fill import (
    _bworld,
    _deliver,
    _done,
    _drawer_receipt,
    _seed_b,
    _wait_status,
)
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

_ED = "App.areas.find(a => a.id === 'studio')._providersSection.controller()"
NAME = "#pf-name"
TYPE = "#pf-type"
URL = "#pf-base-url"
KEY = "#pf-api-key"
KEY_LABEL = 'label[for="pf-api-key"]'
NUM_CTX = "#pf-num-ctx"
THINKING = "#pf-thinking-enabled"
EFFORT = "#pf-reasoning-effort"
UNSAVED = '[data-testid="editor-unsaved"]'
SAVE = '[data-testid="save-provider-btn"]'
CANCEL = '[data-testid="cancel-provider-btn"]'
NOTE = '[data-testid="provider-filled-note"]'
KEPT = '[data-testid="fill-receipt-kept"]'
KEY_NOTE = f'{NOTE}[data-field="api_key"]'


def _world(app_with_data_dir: tuple[str, Any], page: Page) -> SimpleNamespace:
    return _bworld(app_with_data_dir, page, route="library")


def _fill(w: SimpleNamespace, action: str, changes: dict, **kw: Any) -> int:
    return _seed_b(w, kind="provider", action=action, agent_name=None, changes=changes, **kw)


def _seed_provider(base: str, **body: Any) -> str:
    payload = {"base_url": "https://api.anthropic.com", **body}
    r = httpx.post(
        f"{base}/api/providers", json=payload, headers=auth_headers_for(base), timeout=5.0
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _anthropic(base: str, name: str = "Claude") -> str:
    return _seed_provider(
        base,
        name=name,
        type="anthropic",
        api_key="sk-ant-seedkey1234",
        config={"thinking_enabled": False},
    )


def _get(base: str, pid: str) -> dict:
    r = httpx.get(f"{base}/api/providers/{pid}", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _list(base: str) -> list[dict]:
    r = httpx.get(f"{base}/api/providers", headers=auth_headers_for(base), timeout=5.0)
    return r.json()


def _open_create(page: Page) -> None:
    _nav.set_route(page, "library/providers/~new")
    expect(page.locator(NAME)).to_be_attached(timeout=10000)
    expect(page.locator(TYPE)).to_be_attached()


def _open_edit(page: Page, pid: str) -> None:
    _nav.set_route(page, f"library/providers/{_nav.seg(pid)}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)


def _describes(page: Page, control: str, note: str) -> bool:
    nid = page.locator(note).get_attribute("id")
    return nid in (page.locator(control).get_attribute("aria-describedby") or "").split()


# ── AC2: the editor seam ─────────────────────────────────────────────────────


def test_the_editor_seam_switches_the_type_like_a_manual_change_and_never_saves_or_fetches(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    _install_counter(page)
    w = _world(app_with_data_dir, page)
    before = _list(w.base)
    _open_create(page)
    page.evaluate(f"() => {_ED}.setType('ollama')")
    expect(page.locator(NUM_CTX)).to_be_visible()
    expect(page.locator(KEY)).to_be_hidden()
    expect(page.locator(URL)).to_have_value("http://localhost:11434/v1")
    seam_rows = page.evaluate(
        "() => ['#pf-base-url', '#pf-api-key', '#pf-num-ctx', '#pf-thinking-enabled']"
        ".map(s => document.querySelector(s).closest('.ui-field, .ui-toggle, div').hidden)"
    )
    # The same state as choosing the type in the select.
    page.locator(TYPE).select_option("anthropic")
    page.locator(TYPE).select_option("ollama")
    manual_rows = page.evaluate(
        "() => ['#pf-base-url', '#pf-api-key', '#pf-num-ctx', '#pf-thinking-enabled']"
        ".map(s => document.querySelector(s).closest('.ui-field, .ui-toggle, div').hidden)"
    )
    assert seam_rows == manual_rows
    # setType to a key-taking type relabels the key row, as a manual change does; clearKey
    # empties a typed key and the key row's label returns to "API Key".
    page.evaluate(f"() => {_ED}.setType('anthropic-plan-token')")
    expect(page.locator(KEY_LABEL)).to_have_text("Token")
    expect(page.locator(KEY)).to_be_visible()
    page.locator(KEY).fill("sk-typed-by-hand")
    page.evaluate(f"() => {_ED}.clearKey()")
    expect(page.locator(KEY)).to_have_value("")
    # Nothing was sent: no write, no sign-in, no models, no Test.
    for method in ("POST", "PUT", "DELETE"):
        assert _count(page, method, "/api/providers") == 0
    reqs = page.evaluate("() => (window.__reqs || []).map(r => r.p)")
    assert not [p for p in reqs if "/oauth" in p or "/models" in p or p.endswith("/test")]
    assert _list(w.base) == before


# ── AC3: a create fill ───────────────────────────────────────────────────────


def test_a_create_fill_sets_the_type_name_and_thinking_notes_them_and_leaves_the_key(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    before = _list(w.base)
    fid = _fill(w, "create", {"name": "Claude", "type": "anthropic", "thinking_enabled": False})
    _deliver(page, w, fid)
    expect(page.locator(NAME)).to_have_value("Claude", timeout=10000)
    expect(page.locator(TYPE)).to_have_value("anthropic")
    expect(page.locator(THINKING)).not_to_be_checked()
    expect(page.locator(URL)).to_be_hidden()
    expect(page.locator(KEY)).to_have_value("")
    _nav.expect_route(page, "library/providers/~new")
    for field in ("name", "type", "thinking_enabled"):
        expect(page.locator(f'{NOTE}[data-field="{field}"]')).to_have_count(1)
    expect(page.locator(KEY_NOTE)).to_have_text("Enter the key for this type.")
    assert _describes(page, NAME, f'{NOTE}[data-field="name"]')
    assert _describes(page, KEY, KEY_NOTE)
    expect(page.locator(f"{NOTE}[role], {NOTE} [aria-live]")).to_have_count(0)
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    assert _list(w.base) == before
    done = _wait_status(page, w, fid, "filled")
    assert done["outcome"] == {"kept": [], "reason": None}
    _done(page)
    expect(_drawer_receipt(page, fid)).to_have_attribute("data-status", "filled")
    # The operator enters the key and creates it: the stored row is what the form said.
    page.locator(KEY).fill("sk-ant-operator-typed-key")
    page.locator(SAVE).click()
    page.wait_for_function("() => App.router.current().route.indexOf('~new') === -1", timeout=10000)
    made = [p for p in _list(w.base) if p["name"] == "Claude"]
    assert len(made) == 1
    stored = _get(w.base, made[0]["id"])
    assert stored["type"] == "anthropic" and stored["api_key"]
    assert stored["config"]["thinking_enabled"] is False


def test_the_token_type_asks_for_the_token_and_the_plan_type_never_signs_in(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    _install_counter(page)
    w = _world(app_with_data_dir, page)
    fid = _fill(w, "create", {"name": "Token", "type": "anthropic-plan-token"})
    _deliver(page, w, fid)
    expect(page.locator(TYPE)).to_have_value("anthropic-plan-token", timeout=10000)
    expect(page.locator(KEY_NOTE)).to_have_text("Enter the token from claude setup-token.")
    expect(page.locator(KEY_LABEL)).to_have_text("Token")
    _wait_status(page, w, fid, "filled")
    fid2 = _fill(w, "create", {"name": "Plan", "type": "anthropic-plan"}, tool_call_id="tc-2")
    _deliver(page, w, fid2)
    _wait_status(page, w, fid2, "filled")  # the first fill's type is not the operator's: replaced
    expect(page.locator(TYPE)).to_have_value("anthropic-plan")
    expect(page.locator(KEY)).to_be_hidden()
    expect(page.locator(KEY_NOTE)).to_have_count(0)
    expect(page.locator(".admin-pf-plan-signin")).to_be_visible()
    # Nothing was written and no sign-in started, whatever type was filled.
    writes = page.evaluate(
        "() => (window.__reqs || []).filter(r => r.m !== 'GET').map(r => r.m + ' ' + r.p)"
    )
    assert [w_ for w_ in writes if "/api/providers" in w_ or "oauth" in w_] == []


# ── AC4: a type change away from a key-taking type ───────────────────────────


def test_a_change_across_key_taking_types_empties_the_key_and_save_stores_none(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    pid = _anthropic(w.base)
    _open_edit(page, pid)
    masked = page.locator(KEY).input_value()
    assert masked  # the stored key shows masked
    fid = _fill(
        w,
        "change",
        {"type": "openai"},
        target_id=pid,
        base={"type": "anthropic"},
    )
    _deliver(page, w, fid)
    expect(page.locator(TYPE)).to_have_value("openai", timeout=10000)
    expect(page.locator(KEY)).to_have_value("")
    expect(page.locator(KEY_NOTE)).to_have_text("Enter the key for this type.")
    assert _describes(page, KEY, KEY_NOTE)
    assert _wait_status(page, w, fid, "filled")["outcome"] == {"kept": [], "reason": None}
    # Save without typing a key: the old key is not sent to the new service.
    page.locator(SAVE).click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    stored = _get(w.base, pid)
    assert stored["type"] == "openai" and not stored["api_key"]


def test_a_change_into_ollama_empties_the_key_and_save_stores_none(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    pid = _anthropic(w.base)
    _open_edit(page, pid)
    fid = _fill(
        w,
        "change",
        {"type": "ollama", "base_url": "http://localhost:11434/v1"},
        target_id=pid,
        base={"type": "anthropic", "base_url": "https://api.anthropic.com"},
    )
    _deliver(page, w, fid)
    expect(page.locator(TYPE)).to_have_value("ollama", timeout=10000)
    expect(page.locator(KEY)).to_have_value("")
    expect(page.locator(KEY)).to_be_hidden()
    expect(page.locator(KEY_NOTE)).to_have_count(0)  # no key row for this type
    expect(page.locator(NUM_CTX)).to_be_visible()
    _wait_status(page, w, fid, "filled")
    page.locator(SAVE).click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    stored = _get(w.base, pid)
    assert stored["type"] == "ollama" and not stored["api_key"]


def test_cancel_restores_the_stored_type_the_masked_key_the_rows_and_the_key_label(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    pid = _seed_provider(
        w.base,
        name="Token one",
        type="anthropic-plan-token",
        api_key="sk-ant-oat01-seedtoken1234",
    )
    _open_edit(page, pid)
    masked = page.locator(KEY).input_value()
    expect(page.locator(KEY_LABEL)).to_have_text("Token")
    fid = _fill(
        w, "change", {"type": "ollama"}, target_id=pid, base={"type": "anthropic-plan-token"}
    )
    _deliver(page, w, fid)
    expect(page.locator(TYPE)).to_have_value("ollama", timeout=10000)
    expect(page.locator(NUM_CTX)).to_be_visible()
    expect(page.locator(THINKING)).to_be_hidden()
    page.locator(CANCEL).click()
    expect(page.locator(TYPE)).to_have_value("anthropic-plan-token")
    expect(page.locator(KEY)).to_have_value(masked)
    expect(page.locator(KEY)).to_be_visible()
    expect(page.locator(KEY_LABEL)).to_have_text("Token")
    expect(page.locator(NUM_CTX)).to_be_hidden()
    expect(page.locator(THINKING)).to_be_visible()
    expect(page.locator(URL)).to_be_hidden()
    expect(page.locator(NOTE)).to_have_count(0)
    expect(page.locator(UNSAVED)).to_have_text("")
    assert _get(w.base, pid)["api_key"]


def test_cancel_after_a_manual_type_change_restores_the_rows_and_the_stored_address(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    """The extracted type handler also runs on Cancel, which fixes the stale rows it left."""
    w = _world(app_with_data_dir, page)
    pid = _seed_provider(
        w.base, name="Mine", type="ollama", base_url="http://gpu-box:11434/v1", api_key=""
    )
    _open_edit(page, pid)
    page.locator(TYPE).select_option("openai")
    expect(page.locator(KEY)).to_be_visible()
    expect(page.locator(NUM_CTX)).to_be_hidden()
    page.locator(CANCEL).click()
    expect(page.locator(TYPE)).to_have_value("ollama")
    expect(page.locator(KEY)).to_be_hidden()
    expect(page.locator(NUM_CTX)).to_be_visible()
    expect(page.locator(URL)).to_have_value("http://gpu-box:11434/v1")
    expect(page.locator(UNSAVED)).to_have_text("")


# ── AC5: a fill that stays on its type ───────────────────────────────────────


def test_an_options_only_fill_leaves_the_key_masked_and_save_keeps_the_stored_key(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    pid = _anthropic(w.base)
    stored_before = _get(w.base, pid)["api_key"]
    _open_edit(page, pid)
    masked = page.locator(KEY).input_value()
    fid = _fill(
        w,
        "change",
        {"thinking_enabled": True, "reasoning_effort": "high"},
        target_id=pid,
        base={"thinking_enabled": False},
    )
    _deliver(page, w, fid)
    expect(page.locator(THINKING)).to_be_checked(timeout=10000)
    expect(page.locator(EFFORT)).to_have_value("high")
    expect(page.locator(KEY)).to_have_value(masked)
    expect(page.locator(KEY_NOTE)).to_have_count(0)
    expect(page.locator(f'{NOTE}[data-field="thinking_enabled"]')).to_have_count(1)
    _wait_status(page, w, fid, "filled")
    page.locator(SAVE).click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    stored = _get(w.base, pid)
    assert stored["api_key"] == stored_before
    assert stored["config"]["thinking_enabled"] is True
    assert stored["config"]["reasoning_effort"] == "high"


# ── The operator's edits win ─────────────────────────────────────────────────


def test_a_key_the_operator_typed_is_never_cleared_and_the_note_says_to_check_it(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    pid = _anthropic(w.base)
    _open_edit(page, pid)
    page.locator(KEY).fill("sk-typed-by-the-operator")
    fid = _fill(w, "change", {"type": "openai"}, target_id=pid, base={"type": "anthropic"})
    _deliver(page, w, fid)
    expect(page.locator(TYPE)).to_have_value("openai", timeout=10000)
    expect(page.locator(KEY)).to_have_value("sk-typed-by-the-operator")
    expect(page.locator(KEY_NOTE)).to_have_text("Check the key for this type.")
    _wait_status(page, w, fid, "filled")


def test_a_type_the_operator_chose_is_kept_and_the_key_is_left_alone(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    pid = _anthropic(w.base)
    _open_edit(page, pid)
    page.locator(TYPE).select_option("openrouter")
    held = page.locator(KEY).input_value()
    fid = _fill(
        w,
        "change",
        {"type": "openai", "name": "Renamed"},
        target_id=pid,
        base={"type": "anthropic", "name": "Claude"},
    )
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "partly_filled")
    assert done["outcome"] == {"kept": ["type"], "reason": None}
    expect(page.locator(TYPE)).to_have_value("openrouter")
    expect(page.locator(NAME)).to_have_value("Renamed")
    expect(page.locator(KEY)).to_have_value(held)  # clearKey did not run
    expect(page.locator(f'{NOTE}[data-field="type"]')).to_have_count(0)
    _done(page)
    expect(_drawer_receipt(page, fid).locator(KEPT)).to_contain_text("Type")


def test_a_field_the_operator_changed_is_kept_and_an_option_the_type_hides_is_skipped(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    pid = _seed_provider(
        w.base, name="Local", type="ollama", base_url="http://localhost:11434/v1", api_key=""
    )
    _open_edit(page, pid)
    page.locator(NAME).fill("Mine")
    fid = _fill(
        w,
        "change",
        {"name": "Gg name", "num_ctx": 8192},
        target_id=pid,
        base={"name": "Local", "num_ctx": 32768},
    )
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "partly_filled")
    assert done["outcome"] == {"kept": ["name"], "reason": None}
    expect(page.locator(NAME)).to_have_value("Mine")
    expect(page.locator(NUM_CTX)).to_have_value("8192")
    expect(page.locator(f'{NOTE}[data-field="num_ctx"]')).to_have_count(1)
    expect(page.locator(f'{NOTE}[data-field="name"]')).to_have_count(0)
    # An option the type does not show is skipped: neither written nor kept.
    fid2 = _fill(
        w,
        "change",
        {"thinking_enabled": True},
        target_id=pid,
        base={},
        tool_call_id="tc-2",
    )
    _deliver(page, w, fid2)
    done2 = _wait_status(page, w, fid2, "filled")
    assert done2["outcome"] == {"kept": [], "reason": None}
    expect(page.locator(THINKING)).to_be_hidden()
    _done(page)
    expect(_drawer_receipt(page, fid).locator(KEPT)).to_contain_text("Name")


def test_a_dirty_editor_on_another_provider_asks_the_guard_and_stay_writes_nothing(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    first = _anthropic(w.base, "First")
    second = _anthropic(w.base, "Second")
    _open_edit(page, first)
    page.locator(NAME).fill("typed by me")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    fid = _fill(w, "change", {"reasoning_effort": "low"}, target_id=second, base={})
    _deliver(page, w, fid)
    expect(page.locator(_drawer.STAY)).to_be_visible(timeout=8000)
    page.locator(_drawer.STAY).click()
    done = _wait_status(page, w, fid, "not_filled")
    assert done["outcome"] == {"kept": [], "reason": "stay"}
    expect(page.locator(NAME)).to_have_value("typed by me")
    assert _get(w.base, second)["config"].get("reasoning_effort") in (None, "")


# ── A key never rides a fill ─────────────────────────────────────────────────


def test_a_key_in_the_fills_values_is_ignored_and_never_written(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    fid = _fill(
        w,
        "create",
        {"name": "Sneaky", "type": "anthropic", "api_key": "sk-ant-from-a-fill", "secrets": {}},
    )
    _deliver(page, w, fid)
    expect(page.locator(NAME)).to_have_value("Sneaky", timeout=10000)
    expect(page.locator(KEY)).to_have_value("")
    assert "sk-ant-from-a-fill" not in page.content()
    _wait_status(page, w, fid, "filled")


# ── Target gone ──────────────────────────────────────────────────────────────


def test_a_change_fill_for_a_deleted_provider_is_target_gone(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    pid = _anthropic(w.base, "Short lived")
    fid = _fill(w, "change", {"name": "Fresh"}, target_id=pid, base={})
    r = httpx.delete(f"{w.base}/api/providers/{pid}", headers=auth_headers_for(w.base), timeout=5.0)
    assert r.status_code in (200, 204), r.text
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "not_filled")
    assert done["outcome"] == {"kept": [], "reason": "target_gone"}
    _done(page)
    expect(_drawer_receipt(page, fid)).to_contain_text("no longer exists")
