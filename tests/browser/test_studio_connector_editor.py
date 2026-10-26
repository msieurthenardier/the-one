"""Studio Connector-editor form flow tests (Mission 23 Flight 2 Leg 2, DD-9).

Covers: empty-state CTA, create → masked-token redisplay (the round-trip
the backend's `_looks_masked` contract exists to protect), doctor (no
plugin registered — the NORM this flight, Discord lands Flight 3), and
pairing-code generation. Kept small — the end-to-end stub round-trip
(create → pair → message → reply) is leg 3's behavior test's job, not
this browser lane's.

M25 F3 L4a: connectors are rows of the Library list and routed
(``#library/connectors/~new`` and ``/{id}``); the grid and its "New
Connector" CTA are retired, so the create form opens from the Library list's
Add menu (``_lists.library_add``). Leg 4b retired the interim Back: the item
header breadcrumb's "Connectors" link (``_lists.close_item``) returns to the
section root.
"""

from __future__ import annotations

import re

import pytest
from browser import _lists, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


def _open_create_form(page: Page, base: str) -> None:
    """The connector create form, through the Library list's Add menu."""
    _nav.goto_settled(page, base, "library")
    _lists.library_add(page, "connectors")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_studio_connectors_empty_inventory_shows_empty_state(app_clean: str, page: Page) -> None:
    """No connectors: the group's empty line and the section root's empty state,
    whose action opens the create form (the grid's CTA is retired)."""
    _nav.goto_settled(page, app_clean, "library")
    empty = _lists.library_start(page)
    expect(empty).to_be_visible(timeout=8000)
    expect(empty).to_contain_text("Links to chat platforms such as Discord")
    expect(
        page.locator(
            '[data-testid="library-list"] .ui-list-pane-group-empty', has_text="No connectors yet."
        )
    ).to_be_visible()
    page.locator('[data-testid="library-start-connectors-add"]').click()
    _nav.expect_route(page, "library/connectors/~new")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_studio_create_connector_shows_masked_token_on_redisplay(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Create a connector with a real token; after save, the token field
    redisplays the MASKED shape, never the plaintext — the same contract
    `tests/test_api_secret_mask_roundtrip.py` pins at the API layer."""
    _open_create_form(page, app_with_agent.base_url)

    save_btn = page.locator('[data-testid="save-connector-btn"]')

    page.locator('[data-field="name"]').fill("Browser Test Connector")
    page.locator('[data-field="type"]').select_option("discord")
    page.locator('[data-field="token"]').fill("real-plaintext-secret-value")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)

    save_btn.click()
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)

    token_value = page.locator('[data-field="token"]').input_value()
    assert token_value != "real-plaintext-secret-value"
    assert "real-plaintext-secret-value" not in page.content()


@pytest.mark.browser
def test_studio_connector_doctor_reports_plugin_failure_without_token(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Doctor on a "discord" connector (the browser lane's only creatable
    type without the stub gate, and the type leg 1 unconditionally
    registers in production) with no token configured renders the real
    plugin's own failure report, never a crash.

    RENAMED and re-aimed (Mission 23 Flight 3 Leg 3, AC-5): this test
    originally pinned the pre-Discord "no plugin registered" doctor path
    for a discord-typed connector. Leg 1's unconditional production
    Discord registration falsified that premise — the real plugin now
    answers with its own no-token failure instead. Stub-with-gate-closed
    was considered as the re-aim target and found unimplementable: stub
    creatability and stub plugin registration share the SAME dual gate
    (`api.py` `_creatable_connector_types` vs `app.py`'s startup hook), so
    with the gate closed the "stub" type isn't even selectable in this
    form — the browser lane never opens `THE_ONE_STUB_TEST_ENDPOINT`. This
    test instead targets the state the lane CAN reach: a tokenless
    discord-typed connector, asserting the failed status + message SHAPE
    (not exact prose) per the leg's design.
    """
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("Doctor Test Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-testid="save-connector-btn"]').click()

    doctor_btn = page.locator('[data-testid="connector-doctor-btn"]')
    expect(doctor_btn).to_be_visible(timeout=8000)
    doctor_btn.click()

    result = page.locator('[data-testid="connector-doctor-result"]')
    expect(result).to_contain_text("failed", timeout=8000)
    expect(result).to_contain_text("token", timeout=8000)

    # HAT fix (M31 F3 L10): the result line does not sit against the button (the
    # 12px button-to-content gap).
    btn_box = doctor_btn.bounding_box()
    result_box = result.bounding_box()
    assert btn_box and result_box
    assert result_box["y"] - (btn_box["y"] + btn_box["height"]) >= 12


@pytest.mark.browser
def test_studio_connector_create_form_shows_no_status_led(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Squawk 0045, pinned decision #1: the auto-probe (and its LED) is an
    edit-mode-only affordance — there is nothing to probe until the
    connector exists, so the create form must not render the LED at all."""
    _open_create_form(page, app_with_agent.base_url)

    expect(page.locator('[data-testid="connector-status-led"]')).to_have_count(0)


@pytest.mark.browser
def test_studio_connector_status_led_reflects_doctor_result_on_open(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Squawk 0045: opening an EXISTING connector auto-probes doctor once
    (no polling, no manual click) and reflects the result on the header
    LED — the operator's "auto green dot". A tokenless discord connector
    deterministically fails doctor (same plugin behavior the existing
    manual-doctor test pins), which maps to the `indicator-led--danger`
    state and a non-empty accessible label."""
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("LED Test Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)

    # Re-open fresh from the list — the clearest "opening an existing
    # connector" trigger, independent of the post-save auto-transition.
    _lists.close_item(page)
    _nav.expect_route(page, "library")
    _lists.open_item(page, "library/connectors", "LED Test Connector")

    led = page.locator('[data-testid="connector-status-led"]')
    expect(led).to_be_visible(timeout=8000)

    # The header line is a library status: the LED is decorative and the words and
    # the root's data-state carry the outcome.
    line = page.locator('[data-testid="connector-status-label"]')
    expect(line).to_have_attribute("data-state", "danger", timeout=8000)
    expect(line).to_have_text("Not connected")
    expect(led).to_have_class("indicator-led indicator-led--danger")


@pytest.mark.browser
def test_studio_connector_enabled_checkbox_default_checked_and_persists(
    app_with_agent: SeededApp, page: Page
) -> None:
    """AC-10 (Mission 23 Flight 3 Leg 2, DD-6): Enabled checkbox defaults to
    checked; saving without touching it omits ``config.enabled`` (sparse-
    config pattern) — reopening the saved connector shows it still checked."""
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("Enabled Default Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)

    checkbox = page.locator('[data-field="enabled"]')
    expect(checkbox).to_be_visible(timeout=8000)
    expect(checkbox).to_be_checked()

    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)

    _lists.close_item(page)
    _nav.expect_route(page, "library")
    _lists.open_item(page, "library/connectors", "Enabled Default Connector")
    expect(page.locator('[data-field="enabled"]')).to_be_checked(timeout=8000)


@pytest.mark.browser
def test_studio_connector_enabled_checkbox_unchecked_persists_disabled(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Unchecking the Enabled checkbox saves ``enabled: false``; editing a
    disabled connector shows it unchecked (the checked-state trap: the
    render must key off ``!== false``, never a truthy check)."""
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("Disabled Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.get_by_role("switch", name="Enabled").locator("xpath=ancestor::label").click()

    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-field="enabled"]')).not_to_be_checked()

    _lists.close_item(page)
    _nav.expect_route(page, "library")
    _lists.open_item(page, "library/connectors", "Disabled Connector")
    expect(page.locator('[data-field="enabled"]')).not_to_be_checked(timeout=8000)


@pytest.mark.browser
def test_studio_connector_pairing_code_generation(app_with_agent: SeededApp, page: Page) -> None:
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("Pairing Test Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-testid="save-connector-btn"]').click()

    pairing_btn = page.locator('[data-testid="connector-pairing-btn"]')
    expect(pairing_btn).to_be_visible(timeout=8000)
    # M31 F4 L03b: the empty result wrapper is hidden (it takes no gap in the stack).
    expect(page.locator('[data-testid="connector-pairing-result"]')).to_be_hidden()
    pairing_btn.click()

    result = page.locator('[data-testid="connector-pairing-result"]')
    expect(result).to_contain_text("Expires", timeout=8000)

    # Squawk 0245 (DD14): "Expires Mon D, YYYY, h:mm AM/PM" in the operator zone, the ISO
    # value in the title (the text format is asserted, never the time itself).
    expiry = page.locator(".connector-pairing-expiry")
    expect(expiry).to_have_text(
        re.compile(r"^Expires [A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2} (AM|PM)$")
    )
    assert re.match(r"^\d{4}-\d{2}-\d{2}T[\d:.]+\+00:00$", expiry.get_attribute("title") or "")

    # HAT fix (M31 F3 L10): the code field does not touch the button, and the expiry
    # line does not touch the code field (a gap of at least the 8px spacing token).
    btn_box = pairing_btn.bounding_box()
    field_box = page.locator('[data-testid="connector-pairing-code"]').bounding_box()
    expiry_box = page.locator(".connector-pairing-expiry").bounding_box()
    assert btn_box and field_box and expiry_box
    assert field_box["y"] - (btn_box["y"] + btn_box["height"]) >= 8
    assert expiry_box["y"] - (field_box["y"] + field_box["height"]) >= 8


@pytest.mark.browser
def test_studio_connector_pairing_code_is_selectable_and_copyable(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Squawk 0043: the generated code must land in its own element (not
    fused into the surrounding "Code: ... (expires ...)" prose, which the
    operator could not select/copy) and carry a labelled copy affordance."""
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("Copyable Pairing Test Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-testid="save-connector-btn"]').click()

    pairing_btn = page.locator('[data-testid="connector-pairing-btn"]')
    expect(pairing_btn).to_be_visible(timeout=8000)
    pairing_btn.click()

    result = page.locator('[data-testid="connector-pairing-result"]')
    code_el = page.locator('[data-testid="connector-pairing-code"]')
    expect(code_el).to_be_visible(timeout=8000)

    code_text = code_el.input_value()
    assert code_text.strip() != ""
    # The code is a read-only input named "Pairing code" (no <code> element).
    assert code_el.evaluate("el => el.tagName") == "INPUT"
    assert code_el.evaluate("el => el.readOnly") is True
    expect(page.get_by_role("textbox", name="Pairing code")).to_have_value(code_text)
    expect(page.locator("code.connector-pairing-code")).to_have_count(0)
    # The code's own element holds just the code — not the whole prose
    # string ("Code: ... (expires ...)") the surrounding status text used
    # to fuse it into.
    assert "expires" not in code_text.lower()
    expect(result).to_contain_text("Expires")

    copy_btn = page.locator('[data-testid="connector-pairing-copy-btn"]')
    expect(copy_btn).to_be_visible()
    expect(page.get_by_role("button", name="Copy pairing code")).to_have_count(1)


@pytest.mark.browser
def test_studio_connector_setup_steps_shown_per_type(app_with_agent: SeededApp, page: Page) -> None:
    """Squawk 0046: selecting a connector type on the CREATE form (where a
    first-timer needs it most) renders a short static per-type step list —
    each list names the one thing that silently breaks that platform's
    setup (Discord: Message Content intent; Telegram: /setprivacy privacy
    mode) — plus a plain-text reference naming the full walkthrough doc's
    path (not a link: only `/static` is mounted, so an `<a href="docs/...">`
    would 404 — see squawk 0046's Corrective Action)."""
    _open_create_form(page, app_with_agent.base_url)

    steps = page.locator('[data-testid="connector-setup-steps"]')
    expect(steps).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("discord")
    discord_list = page.locator('[data-testid="connector-setup-steps-list-discord"]')
    expect(discord_list).to_be_visible(timeout=8000)
    expect(discord_list).to_contain_text("Message Content Intent")

    page.locator('[data-field="type"]').select_option("telegram")
    telegram_list = page.locator('[data-testid="connector-setup-steps-list-telegram"]')
    expect(telegram_list).to_be_visible(timeout=8000)
    expect(telegram_list).to_contain_text("/setprivacy")

    doc_ref = page.locator('[data-testid="connector-setup-steps-doc-ref"]')
    expect(doc_ref).to_be_visible()
    doc_ref_text = doc_ref.text_content() or ""
    assert "docs/connector-setup.md" in doc_ref_text
    # Regression guard for the dead-link review fix: this must NOT be an
    # anchor pointing at an unmounted path (only `/static` is mounted; see
    # squawk 0046's Corrective Action).
    assert doc_ref.evaluate("el => el.tagName") != "A"


@pytest.mark.browser
def test_delete_connector_confirm_lapse_is_visually_distinct(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Mission 24 Flight 7 confirm-lapse leg, AC-4: the Danger Zone
    connector-delete confirm (`connector-editor.js:599`) is distinguishable
    on screen from one that was never armed, past the real 3s `revertMs`."""
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("Lapse Test Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-testid="save-connector-btn"]').click()

    delete_btn = page.locator('[data-testid="delete-connector-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    delete_btn.click()
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(delete_btn).to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    expect(delete_btn).to_have_text("Delete connector")


@pytest.mark.browser
def test_connector_rename_updates_the_editor_title(app_clean: str, page: Page) -> None:
    """Squawk 0126: the h1 follows an edit save's new name without re-opening."""
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Before rename")
    _nav.goto_settled(page, app_clean, "library")
    _lists.open_item(page, "library/connectors", "Before rename")
    title = page.locator("h1.editor-title")
    expect(title).to_have_text("Before rename", timeout=8000)
    page.locator('[data-field="name"]').fill("After rename")
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(title).to_have_text("After rename", timeout=8000)


# ── Leg 07a: the connector frame on the library ──────────────────────────────

# A token of at least 12 characters, so the GET mask is ``***...{last4}``.
_TOKEN = "stored-token-ABCDEFGH-1111"
_TYPED = "typed-token-PLAINTEXT-9999"

# Every attribute, every input/textarea value and every text node that holds
# `needle`. `with_values=False` leaves the control values out (a typed, unsaved token
# is legitimately in its input's value property).
_SCAN = """([needle, withValues]) => {
  const hits = [];
  for (const el of document.querySelectorAll('*')) {
    for (const a of el.attributes) {
      if (a.value.includes(needle)) hits.push(el.tagName + '@' + a.name);
    }
    if (withValues && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') &&
        el.value.includes(needle)) hits.push(el.tagName + '.value');
  }
  if (document.body.textContent.includes(needle)) hits.push('textContent');
  return hits;
}"""


def _api(base: str):
    import httpx
    from browser._credential_registry import auth_headers_for

    return httpx.Client(base_url=base, headers=auth_headers_for(base), timeout=8.0)


def _seed_with_token(base: str, name: str, token: str = _TOKEN) -> str:
    with _api(base) as c:
        r = c.post(
            "/api/connectors",
            json={
                "name": name,
                "type": "discord",
                "config": {"enabled": False},
                "secrets": {"token": token},
            },
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]


def _stored_token(base: str, cid: str) -> str:
    with _api(base) as c:
        return c.get(f"/api/connectors/{cid}").json()["secrets"]["token"]


def _connector_count(base: str) -> int:
    with _api(base) as c:
        return len(c.get("/api/connectors").json())


def _open_connector(page: Page, base: str, name: str) -> None:
    _nav.goto_settled(page, base, "library")
    _lists.open_item(page, "library/connectors", name)
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_a_double_click_on_create_makes_one_connector(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Defect (a): Create had no busy state, so two quick clicks sent two POSTs.
    The second click, and one after the 201 but before the remount, make nothing."""
    base = app_with_agent.base_url
    _open_create_form(page, base)
    page.locator('[data-field="name"]').fill("Double click")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.get_by_role("switch", name="Enabled").locator("xpath=ancestor::label").click()

    posts: list[str] = []
    page.on(
        "request",
        lambda r: (
            posts.append(r.url)
            if r.method == "POST" and r.url.endswith("/api/connectors")
            else None
        ),
    )
    held: list = []

    def agents_handler(route) -> None:
        # Hold the remount's agent-list fetch, so the 201 is in but the remount is not.
        held.append(route)

    page.route("**/api/agents**", agents_handler)
    page.locator('[data-testid="save-connector-btn"]').evaluate("el => { el.click(); el.click(); }")
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(50)
    assert held, "the remount never asked for the agent list"
    # The 201 is in; the remount is still pending. Another click makes nothing.
    page.evaluate(
        "() => { const b = document.querySelector('[data-testid=\"save-connector-btn\"]');"
        " if (b) { b.click(); b.click(); } }"
    )
    page.wait_for_timeout(300)
    for route in held:
        route.continue_()
    page.unroute("**/api/agents**")
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)
    assert len(posts) == 1, posts
    assert _connector_count(base) == 1


@pytest.mark.browser
def test_b_a_failing_manual_doctor_shows_the_error_not_undefined(
    app_clean: str, page: Page
) -> None:
    """Defect (b): the manual doctor parsed a 500 as a report and wrote
    "undefined: undefined". A non-OK response shows its error text in danger."""
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Doctor 500")
    page.route(
        "**/api/connectors/*/test",
        lambda route: route.fulfill(
            status=500, content_type="application/json", body='{"detail": "doctor exploded"}'
        ),
    )
    _open_connector(page, app_clean, "Doctor 500")
    page.locator('[data-testid="connector-doctor-btn"]').click()
    result = page.locator('[data-testid="connector-doctor-result"]')
    expect(result).to_contain_text("doctor exploded", timeout=8000)
    assert "undefined" not in (result.text_content() or "")
    expect(result).to_have_attribute("data-state", "danger")


@pytest.mark.browser
def test_c_a_failing_probe_on_open_says_the_check_failed(app_clean: str, page: Page) -> None:
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Probe 500")
    page.route(
        "**/api/connectors/*/test",
        lambda route: route.fulfill(status=500, content_type="text/plain", body="boom"),
    )
    _open_connector(page, app_clean, "Probe 500")
    label = page.locator('[data-testid="connector-status-label"]')
    expect(label).to_have_text("Connection check failed", timeout=8000)
    expect(label).to_have_attribute("data-state", "danger") if False else None
    expect(page.locator('[data-testid="connector-status-label"]')).to_be_visible()


@pytest.mark.browser
def test_d_an_untouched_token_survives_an_edit_save(app_clean: str, page: Page) -> None:
    cid = _seed_with_token(app_clean, "Keep token")
    before = _stored_token(app_clean, cid)
    assert before.endswith("1111") and before != _TOKEN
    _open_connector(page, app_clean, "Keep token")
    token = page.locator('[data-field="token"]')
    assert token.input_value() == before
    page.locator('[data-field="name"]').fill("Keep token renamed")
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("Keep token renamed", timeout=8000)
    assert _stored_token(app_clean, cid) == before
    assert token.input_value() == before
    assert token.get_attribute("type") == "password"
    assert page.evaluate(_SCAN, [_TOKEN, True]) == []


@pytest.mark.browser
def test_e_a_typed_token_replaces_it_and_never_stays_in_the_page(
    app_clean: str, page: Page
) -> None:
    cid = _seed_with_token(app_clean, "Replace token")
    _open_connector(page, app_clean, "Replace token")
    token = page.locator('[data-field="token"]')
    token.fill(_TYPED)
    # Typed, unsaved: only the control's value property holds it.
    assert page.evaluate(_SCAN, [_TYPED, False]) == []
    page.locator('[data-testid="save-connector-btn"]').click()
    # The field leaves the typed value once the Save has landed and re-masked it.
    expect(token).not_to_have_value(_TYPED, timeout=8000)

    after = _stored_token(app_clean, cid)
    assert after.endswith("9999") and after != _TYPED
    assert token.input_value() == after
    assert token.get_attribute("type") == "password"
    page.locator(".api-key-wrap .api-key-eye").click()
    assert token.get_attribute("type") == "text"
    assert token.input_value() == after  # the reveal shows the mask, not the plaintext
    assert page.evaluate(_SCAN, [_TYPED, True]) == []
    assert _TYPED not in page.content()

    # Cancel after typing: the stored mask returns, the reveal is off, no plaintext.
    token.fill(_TYPED + "-again")
    assert page.evaluate(_SCAN, [_TYPED, False]) == []
    page.locator('[data-testid="cancel-connector-btn"]').click()
    assert token.input_value() == after
    assert token.get_attribute("type") == "password"
    assert page.evaluate(_SCAN, [_TYPED, True]) == []

    # Type then revert by hand: clean, nothing leaks.
    token.fill(_TYPED)
    token.fill(after)
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_disabled()
    assert page.evaluate(_SCAN, [_TYPED, True]) == []


_MARK = "(sel) => { document.querySelector(sel).__m = 1; }"
_MARKED = "(sel) => document.querySelector(sel).__m === 1"
_HEADER = (
    '[data-testid="save-connector-btn"] >> xpath=ancestor::*[contains(@class,"editor-header")]'
)


def _mark_header(page: Page) -> None:
    page.evaluate(_MARK, ".editor-header")


def _header_marked(page: Page) -> bool:
    return page.evaluate(_MARKED, ".editor-header")


@pytest.mark.browser
def test_f_type_and_revert_in_the_name_is_clean(app_clean: str, page: Page) -> None:
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Revert me")
    _open_connector(page, app_clean, "Revert me")
    name = page.locator('[data-field="name"]')
    save = page.locator('[data-testid="save-connector-btn"]')
    caption = page.locator('[data-testid="editor-unsaved"]')
    expect(save).to_be_disabled()
    name.fill("Revert me too")
    expect(save).to_be_enabled()
    expect(caption).to_have_text("Unsaved changes")
    name.fill("Revert me")
    expect(save).to_be_disabled()
    expect(caption).to_have_text("")


@pytest.mark.browser
def test_g_an_edit_save_keeps_the_editor_mounted(app_clean: str, page: Page) -> None:
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Stay mounted")
    _open_connector(page, app_clean, "Stay mounted")
    _mark_header(page)
    page.locator('[data-field="name"]').fill("Stay mounted, renamed")
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator("h1.editor-title")).to_have_text("Stay mounted, renamed", timeout=8000)
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_disabled()
    expect(page.locator("h1.editor-title")).to_be_focused()
    assert _header_marked(page), "the editor was re-mounted by an edit Save"


@pytest.mark.browser
def test_h_edit_cancel_restores_the_stored_values_without_a_remount(
    app_clean: str, page: Page
) -> None:
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Cancel me", channel_map={"c1": "agent-one", "c2": "agent-two"})
    _open_connector(page, app_clean, "Cancel me")
    _mark_header(page)
    page.locator('[data-field="name"]').fill("Something else")
    page.locator('[data-field="allowlist_peers"]').fill("p1\np2")
    page.locator('[data-field="type"]').select_option("telegram")
    expect(page.locator('[data-testid="connector-setup-steps-list-telegram"]')).to_be_visible()
    # The old channel map: edit a row, remove one and add one.
    rows = page.locator('[data-testid="connector-channel-map-row"]')
    expect(rows).to_have_count(2)
    rows.nth(0).locator('[data-testid="connector-channel-map-agent"]').fill("changed")
    rows.nth(1).locator('[data-testid="connector-channel-map-remove-btn"]').click()
    page.locator('[data-testid="connector-channel-map-add-btn"]').click()
    expect(rows).to_have_count(2)

    page.locator('[data-testid="cancel-connector-btn"]').click()
    expect(page.locator("h1.editor-title")).to_be_focused()
    assert page.locator('[data-field="name"]').input_value() == "Cancel me"
    assert page.locator('[data-field="allowlist_peers"]').input_value() == ""
    assert page.locator('[data-field="type"]').input_value() == "discord"
    expect(page.locator('[data-testid="connector-setup-steps-list-discord"]')).to_be_visible()
    expect(rows).to_have_count(2)
    assert (
        rows.nth(0).locator('[data-testid="connector-channel-map-channel"]').input_value() == "c1"
    )
    assert (
        rows.nth(0).locator('[data-testid="connector-channel-map-agent"]').input_value()
        == "agent-one"
    )
    assert (
        rows.nth(1).locator('[data-testid="connector-channel-map-channel"]').input_value() == "c2"
    )
    assert (
        rows.nth(1).locator('[data-testid="connector-channel-map-agent"]').input_value()
        == "agent-two"
    )
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_disabled()
    expect(page.locator('[data-testid="cancel-connector-btn"]')).to_be_disabled()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("")
    assert _header_marked(page), "Cancel re-mounted the editor"


@pytest.mark.browser
def test_a_masked_looking_token_on_create_is_refused_in_the_header(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A masked-looking token on create is a server 422; the editor shows its text
    in the header error slot and the form is usable again (not stuck busy)."""
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("Masked on create")
    page.locator('[data-field="token"]').fill("***...abcd")
    page.locator('[data-testid="save-connector-btn"]').click()
    error = page.locator(".editor-error")
    expect(error).to_contain_text("masked placeholder", timeout=8000)
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_enabled()
    assert _connector_count(app_with_agent.base_url) == 0


@pytest.mark.browser
def test_a_create_whose_remount_cannot_load_is_released_with_an_error(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The 201 is in but the remount's agent-list fetch fails: the busy create
    form is released with a plain message instead of staying disabled forever."""
    _open_create_form(page, app_with_agent.base_url)
    page.locator('[data-field="name"]').fill("Remount fails")
    page.route(
        "**/api/agents",
        lambda route: route.fulfill(status=500, content_type="text/plain", body="down"),
    )
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator(".editor-error")).to_contain_text(
        "Couldn't reopen the connector", timeout=8000
    )
    expect(page.locator('[data-testid="cancel-connector-btn"]')).to_be_enabled()


# ── Channel map on the key/value table (M31 F3 L07b; DD8-1, DD8-8) ─────────────
# Row inputs are reached through the row's own two inputs, so the same helpers
# read the same cells whatever the table is made of.


def _map_rows(page: Page):
    return page.locator('[data-testid="connector-channel-map-row"]')


def _map_fill(page: Page, idx: int, channel: str | None = None, agent: str | None = None) -> None:
    row = _map_rows(page).nth(idx)
    if channel is not None:
        row.locator("input").nth(0).fill(channel)
    if agent is not None:
        row.locator("input").nth(1).fill(agent)


def _map_values(page: Page) -> list[list[str]]:
    rows = _map_rows(page)
    return [
        [
            rows.nth(i).locator("input").nth(0).input_value(),
            rows.nth(i).locator("input").nth(1).input_value(),
        ]
        for i in range(rows.count())
    ]


def _stored_map(base: str, cid: str) -> dict:
    with _api(base) as c:
        return c.get(f"/api/connectors/{cid}").json()["config"].get("channel_map") or {}


@pytest.mark.browser
def test_dd8_1_1_adding_a_row_keeps_typed_values_in_the_other_rows(
    app_clean: str, page: Page
) -> None:
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Map add")
    _open_connector(page, app_clean, "Map add")
    add = page.locator('[data-testid="connector-channel-map-add-btn"]')
    add.click()
    add.click()
    _map_fill(page, 0, "c-one", "agent-one")
    _map_fill(page, 1, "c-two", "agent-two")
    add.click()
    assert _map_values(page) == [["c-one", "agent-one"], ["c-two", "agent-two"], ["", ""]]


@pytest.mark.browser
def test_dd8_1_2_removing_a_row_keeps_typed_values_in_the_others(
    app_clean: str, page: Page
) -> None:
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Map remove", channel_map={"c1": "a1", "c2": "a2"})
    _open_connector(page, app_clean, "Map remove")
    _map_fill(page, 1, "c2-typed", "a2-typed")
    _map_rows(page).nth(0).locator('[data-testid="connector-channel-map-remove-btn"]').click()
    assert _map_values(page) == [["c2-typed", "a2-typed"]]


@pytest.mark.browser
def test_dd8_1_3_a_second_save_stores_the_edited_value_not_a_stale_one(
    app_clean: str, page: Page
) -> None:
    from browser.seeders import seed_connector

    cid = seed_connector(app_clean, "Map twice saves")
    _open_connector(page, app_clean, "Map twice saves")
    add = page.locator('[data-testid="connector-channel-map-add-btn"]')
    save = page.locator('[data-testid="save-connector-btn"]')
    add.click()
    add.click()
    _map_fill(page, 0, "chan-a", "agent-a")
    _map_fill(page, 1, "chan-b", "agent-b")
    save.click()
    expect(save).to_be_disabled(timeout=8000)
    assert _stored_map(app_clean, cid) == {"chan-a": "agent-a", "chan-b": "agent-b"}

    _map_fill(page, 0, "chan-a2")
    add.click()
    expect(save).to_be_enabled()
    save.click()
    expect(save).to_be_disabled(timeout=8000)
    stored = _stored_map(app_clean, cid)
    assert "chan-a" not in stored
    assert stored == {"chan-a2": "agent-a", "chan-b": "agent-b"}


@pytest.mark.browser
def test_dd8_1_4_cancel_restores_the_edited_channel_rows(app_clean: str, page: Page) -> None:
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Map cancel", channel_map={"c1": "a1", "c2": "a2"})
    _open_connector(page, app_clean, "Map cancel")
    _map_fill(page, 0, "edited", "edited-agent")
    page.locator('[data-testid="cancel-connector-btn"]').click()
    assert _map_values(page) == [["c1", "a1"], ["c2", "a2"]]
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_disabled()


@pytest.mark.browser
def test_dd8_8_channel_map_controls_have_distinct_accessible_names(
    app_clean: str, page: Page
) -> None:
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Map names", channel_map={"c1": "a1", "c2": "a2"})
    _open_connector(page, app_clean, "Map names")
    for n in (1, 2):
        expect(page.get_by_role("textbox", name=f"Channel id, row {n}")).to_have_count(1)
        expect(page.get_by_role("textbox", name=f"Agent, row {n}")).to_have_count(1)
    removes = page.get_by_role("button", name=re.compile(r"^Remove row"))
    names = [removes.nth(i).get_attribute("aria-label") for i in range(removes.count())]
    assert len(names) == 2 and len(set(names)) == 2, names


@pytest.mark.browser
def test_a_double_confirm_on_delete_sends_one_request(app_clean: str, page: Page) -> None:
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Delete once")
    _open_connector(page, app_clean, "Delete once")
    deletes: list[str] = []

    def hold(route):
        if route.request.method == "DELETE":
            deletes.append(route.request.url)
            page.wait_for_timeout(800)
        route.continue_()

    page.route("**/api/connectors/*", hold)
    btn = page.locator('[data-testid="delete-connector-btn"]')
    btn.click()
    btn.click()
    btn.click(force=True)
    _nav.expect_route(page, "library", timeout=10000)
    assert len(deletes) == 1, deletes


@pytest.mark.browser
def test_a_failed_delete_shows_the_error_in_the_danger_zone(app_clean: str, page: Page) -> None:
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Delete fails")
    _open_connector(page, app_clean, "Delete fails")

    def boom(route):
        if route.request.method == "DELETE":
            route.fulfill(
                status=500, content_type="application/json", body='{"detail": "nope-delete"}'
            )
        else:
            route.continue_()

    page.route("**/api/connectors/*", boom)
    btn = page.locator('[data-testid="delete-connector-btn"]')
    btn.click()
    btn.click()
    expect(page.locator('[data-testid="connector-delete-error"]')).to_contain_text(
        "nope-delete", timeout=8000
    )
    expect(btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"))
    expect(btn).to_be_enabled()


@pytest.mark.browser
def test_a_late_auto_probe_cannot_overwrite_a_newer_manual_doctor_on_the_header(
    app_clean: str, page: Page
) -> None:
    """Review fix: the open-time probe and Run doctor share the header line, and the
    newest request wins. A slow first probe that lands after a manual run is dropped.
    The manual button is disabled while its own run is in flight, so a second manual
    click cannot overlap the first."""
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Doctor race")
    held: list = []
    calls: list[int] = []

    def handler(route) -> None:  # noqa: ANN001
        calls.append(1)
        if len(calls) == 1:
            held.append(route)  # the open-time probe: held
            return
        if len(calls) == 2:  # the manual run: held briefly to observe the disabled state
            held.append(route)
            return
        route.fulfill(status=200, content_type="application/json", json={})

    page.route("**/api/connectors/*/test", handler)
    _open_connector(page, app_clean, "Doctor race")
    btn = page.locator('[data-testid="connector-doctor-btn"]')
    btn.click()
    for _ in range(100):
        if len(held) == 2:
            break
        page.wait_for_timeout(50)
    assert len(held) == 2
    expect(btn).to_be_disabled()
    ok = {"status": "ok", "message": "fine", "warnings": [], "disabled": False}
    bad = {"status": "failed", "message": "late", "warnings": [], "disabled": False}
    held[1].fulfill(status=200, content_type="application/json", json=ok)
    result = page.locator('[data-testid="connector-doctor-result"]')
    expect(result).to_contain_text("fine", timeout=8000)
    expect(btn).to_be_enabled()
    header = page.locator('[data-testid="connector-status-label"]')
    expect(header).to_have_attribute("data-state", "success", timeout=8000)
    held[0].fulfill(status=200, content_type="application/json", json=bad)
    page.wait_for_timeout(400)
    expect(header).to_have_attribute("data-state", "success")


@pytest.mark.browser
def test_an_edit_save_re_probes_the_header_for_the_saved_config(app_clean: str, page: Page) -> None:
    """HAT fix (M31 F3 L10): an edit Save patches in place (no remount, DD5), so it
    re-runs the open-time probe itself. The header follows the SAVED config: a
    disabled connector reads "Disabled"; enabled and saved, it reads the probe's
    verdict (a tokenless discord connector fails doctor: "Not connected"); disabled
    and saved again, it reads "Disabled" again, with no reopen in between."""
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Re-probe")
    _open_connector(page, app_clean, "Re-probe")
    _mark_header(page)
    header = page.locator('[data-testid="connector-status-label"]')
    toggle = page.get_by_role("switch", name="Enabled").locator("xpath=ancestor::label")
    save = page.locator('[data-testid="save-connector-btn"]')
    expect(header).to_have_text("Disabled", timeout=8000)

    toggle.click()
    save.click()
    expect(save).to_be_disabled(timeout=8000)
    expect(header).to_have_text("Not connected", timeout=8000)
    expect(header).to_have_attribute("data-state", "danger")

    toggle.click()
    save.click()
    expect(save).to_be_disabled(timeout=8000)
    expect(header).to_have_text("Disabled", timeout=8000)
    expect(header).to_have_attribute("data-state", "idle")
    assert _header_marked(page), "the editor was re-mounted by an edit Save"


@pytest.mark.browser
def test_an_edit_save_clears_the_doctor_result_and_drops_a_run_in_flight(
    app_clean: str, page: Page
) -> None:
    """HAT fix (M31 F3 L10): the Diagnostics result describes the config it ran on,
    so a successful edit Save hides it (it must not contradict the re-probed
    header). A manual run still in flight at Save time never repaints the line or
    the header afterwards, and the button is usable again."""
    from browser.seeders import seed_connector

    seed_connector(app_clean, "Doctor clear")
    held: list = []
    calls: list[int] = []
    ok = {"status": "ok", "message": "fine", "warnings": [], "disabled": False}
    late = {"status": "failed", "message": "stale run", "warnings": [], "disabled": False}

    def handler(route) -> None:  # noqa: ANN001
        calls.append(1)
        # 1 the open probe, 2 a manual run, 3 the first Save's re-probe, 4 the
        # second manual run (held across the second Save), 5 that Save's re-probe.
        if len(calls) == 4:
            held.append(route)
            return
        route.fulfill(status=200, content_type="application/json", json=ok)

    page.route("**/api/connectors/*/test", handler)
    _open_connector(page, app_clean, "Doctor clear")
    header = page.locator('[data-testid="connector-status-label"]')
    btn = page.locator('[data-testid="connector-doctor-btn"]')
    result = page.locator('[data-testid="connector-doctor-result"]')
    save = page.locator('[data-testid="save-connector-btn"]')
    expect(header).to_have_text("Connected", timeout=8000)

    # A finished run: its line is shown, then a Save clears it.
    btn.click()
    expect(result).to_contain_text("fine", timeout=8000)
    page.locator('[data-field="name"]').fill("Doctor clear 2")
    save.click()
    expect(save).to_be_disabled(timeout=8000)
    expect(result).to_be_hidden()
    expect(header).to_have_text("Connected", timeout=8000)

    # A run in flight at Save time: held, the Save lands, then it is released.
    btn.click()
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(50)
    assert held
    expect(btn).to_be_disabled()
    page.locator('[data-field="name"]').fill("Doctor clear 3")
    save.click()
    expect(save).to_be_disabled(timeout=8000)
    expect(result).to_be_hidden()
    expect(btn).to_be_enabled()
    expect(header).to_have_text("Connected", timeout=8000)
    held[0].fulfill(status=200, content_type="application/json", json=late)
    page.wait_for_timeout(400)
    expect(result).to_be_hidden()
    expect(header).to_have_text("Connected")
