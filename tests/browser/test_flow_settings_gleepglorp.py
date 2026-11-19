"""Settings > GleepGlorp (M36 F1 L03, flight DD7; screen 1 of the approved board).

The page is an ``App.ui.editorShell`` page variant over a Model section (a provider and a
model select) and a Behavior section (three switches and "Keep chats for N days"). Covers:

* load: defaults on a fresh install, the nav entry, and a stored setting;
* the model select follows the provider (placeholder first, saved model kept);
* dirty state (the ``editor-unsaved`` caption), Cancel, Save and a reload that reads back;
* a 422 on retention lands on its field (a routed refusal, since the client mirrors the
  bound), and a load failure shows an error instead of an empty form;
* a removed provider shows as "Removed provider" with a warning, never a crash;
* the leave guard asks once about unsaved changes;
* the Library provider row names GleepGlorp.

Settings lane (``test_flow_settings_*`` in ``scripts/run-tests.sh``).
"""

from __future__ import annotations

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import seed_mock_provider
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

DIALOG = '[data-testid="confirm-dialog-overlay"]'
PROVIDER = '[data-testid="gleepglorp-provider"]'
MODEL = '[data-testid="gleepglorp-model"]'
RETENTION = '[data-testid="gleepglorp-retention"]'
SAVE = '[data-testid="gleepglorp-save-btn"]'
CANCEL = '[data-testid="gleepglorp-cancel-btn"]'
UNSAVED = '.area-admin [data-testid="editor-unsaved"]'


def _goto(page: Page, base: str) -> None:
    _nav.goto(page, base, "settings/gleepglorp")
    expect(page.locator(".page-title")).to_have_text("GleepGlorp", timeout=8000)
    expect(page.locator(RETENTION)).to_have_value("30", timeout=8000)


def _flip(page: Page, testid: str) -> None:
    """Click a switch through its label (the input is visually hidden)."""
    page.locator(".ui-toggle-label").filter(has=page.locator(f'[data-testid="{testid}"]')).click()


def _stored(base: str) -> dict:
    r = httpx.get(f"{base}/api/gleepglorp", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _put(base: str, body: dict) -> httpx.Response:
    return httpx.put(
        f"{base}/api/gleepglorp", json=body, headers=auth_headers_for(base), timeout=5.0
    )


def _body(**over) -> dict:
    return {
        "enabled": True,
        "provider_config_id": None,
        "model": None,
        "web_access": True,
        "memory": True,
        "retention_days": 30,
        **over,
    }


def _options(page: Page, selector: str) -> list[str]:
    return page.locator(f"{selector} option").all_text_contents()


def test_the_page_is_the_first_nav_entry_and_shows_the_defaults(app_clean: str, page: Page) -> None:
    _goto(page, app_clean)
    _nav.expect_route(page, "settings/gleepglorp")
    _lists.expect_settings_selected(page, "gleepglorp")
    expect(page.locator('[data-testid="gleepglorp-intro"]')).to_contain_text("built-in assistant")
    # Model: placeholders only, the model select waits for a provider.
    assert _options(page, PROVIDER) == ["Choose a model provider…"]
    expect(page.locator(PROVIDER)).to_have_value("")
    assert _options(page, MODEL) == ["Choose a model…"]
    expect(page.locator(MODEL)).to_be_disabled()
    expect(page.locator('[data-testid="gleepglorp-model-hint"]')).to_have_text(
        "Small local models may struggle."
    )
    # Behavior: every switch on, 30 days.
    for testid in ("gleepglorp-enabled", "gleepglorp-web", "gleepglorp-memory"):
        expect(page.locator(f'[data-testid="{testid}"]')).to_be_checked()
    expect(page.locator(RETENTION)).to_have_value("30")
    # Clean: no caption, Save and Cancel disabled, no error.
    expect(page.locator(UNSAVED)).to_be_hidden()
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator('[data-testid="gleepglorp-error"]')).to_have_count(0)
    expect(page.locator('[data-testid="gleepglorp-load-error"]')).to_have_count(0)


def test_the_model_select_follows_the_provider(app_clean: str, page: Page) -> None:
    seed_mock_provider(app_clean, "Mock one", {"models": ["m-one", "m-two"]})
    _goto(page, app_clean)
    assert _options(page, PROVIDER) == ["Choose a model provider…", "Mock one"]
    page.locator(PROVIDER).select_option(label="Mock one")
    expect(page.locator(MODEL)).to_be_enabled(timeout=8000)
    expect(page.locator(MODEL)).to_have_attribute("aria-busy", "false")
    assert _options(page, MODEL) == ["Choose a model…", "m-one", "m-two"]
    expect(page.locator(MODEL)).to_have_value("")
    # Going back to the placeholder empties and disables the model again.
    page.locator(PROVIDER).select_option(value="")
    expect(page.locator(MODEL)).to_be_disabled()
    assert _options(page, MODEL) == ["Choose a model…"]


def test_dirty_cancel_save_and_reload(app_clean: str, page: Page) -> None:
    pid = seed_mock_provider(app_clean, "Mock one", {"models": ["m-one", "m-two"]})
    _goto(page, app_clean)

    page.locator(PROVIDER).select_option(label="Mock one")
    expect(page.locator(MODEL)).to_be_enabled(timeout=8000)
    page.locator(MODEL).select_option("m-two")
    _flip(page, "gleepglorp-web")
    page.locator(RETENTION).fill("45")
    expect(page.locator(UNSAVED)).to_be_visible()
    expect(page.locator(SAVE)).to_be_enabled()

    # Cancel restores the saved values and clears the caption.
    page.locator(CANCEL).click()
    expect(page.locator(PROVIDER)).to_have_value("")
    assert _options(page, MODEL) == ["Choose a model…"]
    expect(page.locator('[data-testid="gleepglorp-web"]')).to_be_checked()
    expect(page.locator(RETENTION)).to_have_value("30")
    expect(page.locator(UNSAVED)).to_be_hidden()
    expect(page.locator(SAVE)).to_be_disabled()
    assert _stored(app_clean) == {
        **_body(),
        "state": "needs_model",
        "web_search_available": True,
    }

    # Edit again and Save: the server holds it, the page re-baselines to clean.
    page.locator(PROVIDER).select_option(label="Mock one")
    expect(page.locator(MODEL)).to_be_enabled(timeout=8000)
    page.locator(MODEL).select_option("m-two")
    page.locator(RETENTION).fill("45")
    # The notes switch (Notes section) saves at once from the last SAVED settings: the
    # unsaved Model and Retention edits above neither ride along nor are lost.
    _flip(page, "gleepglorp-memory")
    expect(page.locator('[data-testid="gleepglorp-memory"]')).not_to_be_checked()
    for _ in range(40):
        if _stored(app_clean)["memory"] is False:
            break
        page.wait_for_timeout(200)
    stored_now = _stored(app_clean)
    assert stored_now["provider_config_id"] is None and stored_now["retention_days"] == 30
    expect(page.locator(UNSAVED)).to_be_visible()
    expect(page.locator(SAVE)).to_be_enabled()
    page.locator(SAVE).click()
    expect(page.locator('[data-testid="gleepglorp-flash"]')).to_contain_text("Saved.")
    expect(page.locator(UNSAVED)).to_be_hidden()
    expect(page.locator(SAVE)).to_be_disabled()
    assert _stored(app_clean) == {
        **_body(provider_config_id=pid, model="m-two", memory=False, retention_days=45),
        "state": "ready",
        "web_search_available": True,
    }

    # A reload reads it back.
    page.reload()
    expect(page.locator(RETENTION)).to_have_value("45", timeout=8000)
    expect(page.locator(PROVIDER)).to_have_value(pid)
    expect(page.locator(MODEL)).to_have_value("m-two", timeout=8000)
    expect(page.locator('[data-testid="gleepglorp-memory"]')).not_to_be_checked()
    expect(page.locator('[data-testid="gleepglorp-web"]')).to_be_checked()
    expect(page.locator(UNSAVED)).to_be_hidden()


def test_a_saved_model_the_provider_does_not_list_stays_selectable(
    app_clean: str, page: Page
) -> None:
    pid = seed_mock_provider(app_clean, "Mock one", {"models": ["m-one"]})
    assert _put(app_clean, _body(provider_config_id=pid, model="retired-model")).status_code == 200
    _goto(page, app_clean)
    expect(page.locator(MODEL)).to_have_value("retired-model", timeout=8000)
    assert _options(page, MODEL) == ["Choose a model…", "m-one", "retired-model"]
    expect(page.locator(UNSAVED)).to_be_hidden()


def test_a_422_on_retention_lands_on_its_field(app_clean: str, page: Page) -> None:
    _goto(page, app_clean)
    page.locator(RETENTION).fill("45")

    def refuse(route):
        if route.request.method != "PUT":
            route.continue_()
            return
        route.fulfill(
            status=422,
            content_type="application/json",
            body=(
                '{"detail": [{"type": "value_error", "loc": ["retention_days"],'
                ' "msg": "Keep chats for 1 to 365 days."}]}'
            ),
        )

    page.route("**/api/gleepglorp", refuse)
    page.locator(SAVE).click()
    expect(page.locator('[data-testid="gleepglorp-retention-error"]')).to_have_text(
        "Keep chats for 1 to 365 days.", timeout=8000
    )
    # Still dirty, nothing stored, and no stray page-level error.
    expect(page.locator(UNSAVED)).to_be_visible()
    assert _stored(app_clean)["retention_days"] == 30
    expect(page.locator('[data-testid="gleepglorp-error"]')).to_have_count(0)


def test_retention_bounds_block_save_before_the_server_is_asked(app_clean: str, page: Page) -> None:
    _goto(page, app_clean)
    for bad in ("0", "366", ""):
        page.locator(RETENTION).fill(bad)
        expect(page.locator('[data-testid="gleepglorp-retention-error"]')).to_be_visible()
        expect(page.locator(SAVE)).to_be_disabled()
    page.locator(RETENTION).fill("365")
    expect(page.locator('[data-testid="gleepglorp-retention-error"]')).to_have_count(0)
    expect(page.locator(SAVE)).to_be_enabled()


def test_a_load_failure_shows_an_error_not_an_empty_form(app_clean: str, page: Page) -> None:
    page.route(
        "**/api/gleepglorp",
        lambda route: route.fulfill(
            status=500, content_type="application/json", body='{"detail": "boom"}'
        ),
    )
    _nav.goto(page, app_clean, "settings/gleepglorp")
    expect(page.locator('[data-testid="gleepglorp-load-error"]')).to_be_visible(timeout=8000)
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator(RETENTION)).to_be_disabled()


def test_a_removed_provider_shows_a_warning_not_a_crash(app_clean: str, page: Page) -> None:
    # The route refuses to delete a provider GleepGlorp uses (409 naming it); a provider that
    # vanished anyway (a database edit) is stood in for by a routed GET in the state it reports.
    pid = seed_mock_provider(app_clean, "Mock one", {"models": ["m-one"]})
    assert _put(app_clean, _body(provider_config_id=pid, model="m-one")).status_code == 200
    r = httpx.delete(
        f"{app_clean}/api/providers/{pid}", headers=auth_headers_for(app_clean), timeout=5.0
    )
    assert r.status_code == 409 and "GleepGlorp" in r.json()["detail"]

    def stored_gone(route):
        if route.request.method != "GET":
            route.continue_()
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=(
                '{"enabled": true, "provider_config_id": "gone", "model": "m-one",'
                ' "web_access": true, "memory": true, "retention_days": 30,'
                ' "state": "provider_missing"}'
            ),
        )

    page.route("**/api/gleepglorp", stored_gone)
    _goto(page, app_clean)
    assert _options(page, PROVIDER)[-1] == "Removed provider"
    expect(page.locator(PROVIDER)).to_have_value("gone")
    group = page.locator(".field-group").filter(has=page.locator(PROVIDER))
    expect(group).to_contain_text("was removed", timeout=8000)
    # The model list for a missing provider 404s: the saved model stays, with an error hint.
    expect(page.locator(MODEL)).to_have_value("m-one", timeout=8000)
    expect(page.locator('[data-testid="gleepglorp-model-hint"]')).to_contain_text(
        "Couldn't load", timeout=8000
    )
    expect(page.locator(UNSAVED)).to_be_hidden()


def test_leaving_with_unsaved_changes_asks_once(app_clean: str, page: Page) -> None:
    _goto(page, app_clean)
    page.locator(RETENTION).fill("60")
    expect(page.locator(UNSAVED)).to_be_visible()
    _lists.settings_nav_link(page, "appearance").click()
    overlay = page.locator(DIALOG)
    expect(overlay).to_be_visible(timeout=8000)
    # Stay keeps the page and the edit.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator(".page-title")).to_have_text("GleepGlorp")
    expect(page.locator(RETENTION)).to_have_value("60")
    # Continue leaves, once.
    _lists.settings_nav_link(page, "appearance").click()
    expect(overlay).to_be_visible(timeout=8000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(".page-title")).to_have_text("Appearance", timeout=8000)
    expect(overlay).to_have_count(0)
    assert _stored(app_clean)["retention_days"] == 30


def test_a_clean_page_leaves_without_a_prompt(app_clean: str, page: Page) -> None:
    _goto(page, app_clean)
    _lists.settings_nav_link(page, "appearance").click()
    expect(page.locator(".page-title")).to_have_text("Appearance", timeout=8000)
    expect(page.locator(DIALOG)).to_have_count(0)


def test_the_library_provider_row_names_gleepglorp(app_clean: str, page: Page) -> None:
    pid = seed_mock_provider(app_clean, "Mock one", {"models": ["m-one"]})
    _nav.goto(page, app_clean, "library")
    row = _lists.list_row(page, "library/providers", "Mock one")
    expect(row).to_contain_text("0 agents", timeout=8000)
    assert _put(app_clean, _body(provider_config_id=pid, model="m-one")).status_code == 200
    page.reload()  # the change was made outside this window
    row = _lists.list_row(page, "library/providers", "Mock one")
    expect(row).to_contain_text("GleepGlorp", timeout=8000)
    expect(row).not_to_contain_text("0 agents")
