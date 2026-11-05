# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Library > Secrets editor flows (sortie 10, leg 3 part A; flight DD1, DD3).

Covers: the Library list group and start card, create with the generated first key, a stored
edit that keeps its masks (the exact PUT body), a key rename clearing its value, each 422 on its
target and a 409 on the name, search-ahead for allowed tools (a built-in and an MCP tool from a
seeded cache, and the unavailable fallback), delete with the used-by arm text, the leave guard
(Stay and Continue), and the no-plaintext-in-the-DOM pin. Chromium; lane ``library``.
"""

from __future__ import annotations

import json

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mcp_source, seed_secret
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

DIALOG = '[data-testid="confirm-dialog-overlay"]'
STAY = '[data-testid="modal-cancel-btn"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'
SAVE = '[data-testid="save-secret-btn"]'
KEYS = '[data-testid="secret-key-input"]'
VALUES = '[data-testid="secret-value-input"]'
TOOLS_INPUT = "#secret-allowed-tools"


def _secrets(base: str) -> list[dict]:
    r = httpx.get(f"{base}/api/secrets", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _capture(page: Page) -> list[dict]:
    """Every POST/PUT body sent to /api/secrets, parsed, in order."""
    bodies: list[dict] = []

    def on_request(req) -> None:
        if req.method in ("POST", "PUT") and "/api/secrets" in req.url:
            bodies.append(json.loads(req.post_data or "{}"))

    page.on("request", on_request)
    return bodies


def _open_create(page: Page, base: str) -> None:
    _nav.goto_settled(page, base, "library")
    _lists.library_add(page, "secrets")
    expect(page.locator(SAVE)).to_be_visible(timeout=8000)


def _open_secret(page: Page, base: str, sid: str, name: str) -> None:
    _nav.goto_settled(page, base, f"library/secrets/{_nav.seg(sid)}")
    expect(page.locator(".editor-title")).to_have_text(name, timeout=8000)


def _add_tool(page: Page, text: str) -> None:
    page.locator(TOOLS_INPUT).click()
    page.locator(TOOLS_INPUT).fill(text)
    page.keyboard.press("Enter")


def _chips(page: Page) -> list[str]:
    return page.evaluate(
        "() => App.ui.chipList.valuesOf(document.querySelector('[data-testid=\"secret-allowed-tools\"]'))"
    )


# ── Library list, start card, Add menu ───────────────────────────────────────


def test_start_card_opens_the_create_form(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    _nav.goto_settled(page, base, "library")
    start = _lists.library_start(page)
    expect(start).to_contain_text("Passwords, keys and other values")
    expect(
        page.locator(
            '[data-testid="library-list"] .ui-list-pane-group-empty', has_text="No secrets yet."
        )
    ).to_be_visible()
    page.locator('[data-testid="library-start-secrets-add"]').click()
    _nav.expect_route(page, "library/secrets/~new")
    expect(page.locator(SAVE)).to_be_visible(timeout=8000)


def test_row_meta_counts_values_and_agents_and_the_bare_alias_redirects(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    sid = seed_secret(
        base, "Home address", values=[("home_a", "1"), ("home_b", "2")], allowed_tools=["shell"]
    )
    # Grant it to an agent: the meta counts values and agents.
    agent = httpx.get(
        f"{base}/api/agents/{app_with_agent.agent_name}", headers=auth_headers_for(base)
    ).json()
    agent["secret_ids"] = [sid]
    r = httpx.put(
        f"{base}/api/agents/{app_with_agent.agent_name}",
        json=agent,
        headers=auth_headers_for(base),
        timeout=5.0,
    )
    assert r.status_code == 200, r.text
    _nav.goto_settled(page, base, "library")
    row = _lists.list_row(page, "library/secrets", "Home address")
    expect(row).to_contain_text("2 values · 1 agent")
    assert row.get_attribute("href") == _nav.href(f"library/secrets/{_nav.seg(sid)}")
    # The bare section alias is the root.
    _nav.goto_settled(page, base, "library/secrets")
    _nav.expect_route(page, "library")
    _lists.library_add(page, "secrets")


# ── Create ───────────────────────────────────────────────────────────────────


def test_create_generates_first_key_adds_and_removes_pairs(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    sent = _capture(page)
    _open_create(page, base)
    # One empty row; its key follows the name through the slug rule.
    expect(page.locator(KEYS)).to_have_count(1)
    page.locator("#secret-name").fill("Home address (AU)")
    expect(page.locator(KEYS).first).to_have_value("home_address_au")
    # An edit of the key ends the following.
    page.locator(KEYS).first.fill("addr")
    page.locator("#secret-name").fill("Other name")
    expect(page.locator(KEYS).first).to_have_value("addr")
    page.locator(VALUES).first.fill("1 Main St")
    # Add a pair, then remove it.
    page.locator('[data-testid="secret-add-pair-btn"]').click()
    expect(page.locator(KEYS)).to_have_count(2)
    page.locator(KEYS).nth(1).fill("city")
    page.locator('[data-testid="secret-kv-remove-btn"]').nth(1).click()
    expect(page.locator(KEYS)).to_have_count(1)
    _add_tool(page, "shell")
    assert _chips(page) == ["shell"]
    page.locator(SAVE).click()
    # Opens the new secret at its item route, in edit mode.
    expect(page.locator('[data-testid="delete-secret-btn"]')).to_be_visible(timeout=8000)
    assert len(sent) == 1
    assert sent[0] == {
        "name": "Other name",
        "description": "",
        "values": [{"key": "addr", "value": "1 Main St"}],
        "allowed_tools": ["shell"],
    }
    created = _secrets(base)[0]
    _nav.expect_route(page, f"library/secrets/{_nav.seg(created['id'])}")
    _lists.expect_selected(page, "library/secrets", "Other name")
    # Stored values are masks again, and the editor is clean.
    expect(page.locator(VALUES).first).to_have_value("__MASKED__")
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator(".app-flash")).to_have_text("Secret created")


# ── Edit: masks kept, rename clears ──────────────────────────────────────────


def test_edit_keeps_masks_and_sends_exact_body(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    sid = seed_secret(
        base, "Bank", values=[("bank_login", "a"), ("bank_password", "b")], allowed_tools=["shell"]
    )
    ids = [v["id"] for v in _secrets(base)[0]["values"]]
    sent = _capture(page)
    _open_secret(page, base, sid, "Bank")
    expect(page.locator(SAVE)).to_be_disabled()
    page.locator("#secret-description").fill("Online banking.")
    expect(page.locator(SAVE)).to_be_enabled()
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)
    assert sent == [
        {
            "name": "Bank",
            "description": "Online banking.",
            "values": [
                {"key": "bank_login", "value": "__MASKED__", "id": ids[0]},
                {"key": "bank_password", "value": "__MASKED__", "id": ids[1]},
            ],
            "allowed_tools": ["shell"],
        }
    ]
    assert _secrets(base)[0]["description"] == "Online banking."
    expect(page.locator(VALUES).first).to_have_value("__MASKED__")


def test_renaming_a_key_clears_its_value_and_save_then_requires_it(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    sid = seed_secret(base, "Bank", values=[("bank_login", "a")], allowed_tools=["shell"])
    pair_id = _secrets(base)[0]["values"][0]["id"]
    sent = _capture(page)
    _open_secret(page, base, sid, "Bank")
    page.locator(KEYS).first.fill("bank_user")
    expect(page.locator(VALUES).first).to_have_value("")
    expect(page.locator("#main-content")).to_contain_text(
        "Sensitive values must be re-entered when the key changes."
    )
    page.locator(SAVE).click()
    err = page.locator('[data-testid="secret-kv-row"] [role="alert"]').first
    expect(err).to_have_text("A value must be non-empty text.")
    page.locator(VALUES).first.fill("new-value")
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)
    assert sent[-1]["values"] == [{"key": "bank_user", "value": "new-value", "id": pair_id}]
    assert [v["key"] for v in _secrets(base)[0]["values"]] == ["bank_user"]


# ── Errors ───────────────────────────────────────────────────────────────────


def test_each_422_lands_on_its_target(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    _open_create(page, base)
    page.locator(VALUES).first.fill("v")
    page.locator(KEYS).first.fill("k")
    page.locator("#secret-description").fill("x")  # make the form dirty
    # An empty name is refused first (the server stops at the name rule).
    page.locator(SAVE).click()
    expect(page.locator('[data-testid="secret-name-error"]')).to_be_visible(timeout=8000)
    assert page.locator("#secret-name").get_attribute("aria-invalid") == "true"
    # Typing clears the field's error.
    page.locator("#secret-name").fill("Dup keys")
    expect(page.locator('[data-testid="secret-name-error"]')).to_have_count(0)
    # No tool: the server's own sentence, on the Allowed tools field (no client pre-check).
    page.locator(SAVE).click()
    expect(page.locator('[data-testid="secret-tools-error"]')).to_have_text(
        "Choose at least one tool that may receive this secret."
    )
    # A chip with whitespace: the error names the chip.
    _add_tool(page, "bad name")
    page.locator(SAVE).click()
    expect(page.locator('[data-testid="secret-tools-error"]')).to_contain_text(
        "“bad name”: A tool name can't contain whitespace."
    )
    # Repeated key: on the second row's Key.
    page.locator('[data-testid="secret-allowed-tools"] .ui-chip-remove').click()
    _add_tool(page, "shell")
    page.locator('[data-testid="secret-add-pair-btn"]').click()
    page.locator(KEYS).nth(1).fill("k")
    page.locator(VALUES).nth(1).fill("w")
    page.locator(SAVE).click()
    err = page.locator('[data-testid="secret-kv-row"]').nth(1).locator('[role="alert"]')
    expect(err).to_have_text("This key repeats an earlier key.")
    # No pairs at all: the section-level line under the table.
    page.locator('[data-testid="secret-kv-remove-btn"]').nth(1).click()
    page.locator('[data-testid="secret-kv-remove-btn"]').nth(0).click()
    page.locator(SAVE).click()
    expect(page.locator('[data-testid="secret-values-error"]')).to_have_text(
        "Add at least one key and value."
    )
    assert _secrets(base) == []


def test_description_422_and_unmapped_errors_use_their_slots(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    sid = seed_secret(base, "Bank", values=[("bank_login", "a")], allowed_tools=["shell"])
    _open_secret(page, base, sid, "Bank")
    page.route(
        "**/api/secrets/*",
        lambda route: (
            route.fulfill(
                status=422,
                content_type="application/json",
                body=json.dumps(
                    {
                        "detail": [
                            {"type": "value_error", "loc": ["description"], "msg": "Too long."}
                        ]
                    }
                ),
            )
            if route.request.method == "PUT"
            else route.continue_()
        ),
    )
    page.locator("#secret-description").fill("x")
    page.locator(SAVE).click()
    expect(page.locator('[data-testid="secret-description-error"]')).to_have_text("Too long.")
    page.unroute("**/api/secrets/*")
    page.route(
        "**/api/secrets/*",
        lambda route: (
            route.fulfill(status=500, body="boom")
            if route.request.method == "PUT"
            else route.continue_()
        ),
    )
    page.locator(SAVE).click()
    expect(page.locator(".editor-error")).to_contain_text("boom", timeout=8000)
    expect(page.locator('[data-testid="secret-description-error"]')).to_have_count(0)


def test_duplicate_name_is_a_409_on_the_name_field(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    seed_secret(base, "Taken", values=[("taken_k", "v")])
    _open_create(page, base)
    page.locator("#secret-name").fill("taken")
    page.locator(VALUES).first.fill("v")
    _add_tool(page, "shell")
    page.locator(SAVE).click()
    expect(page.locator('[data-testid="secret-name-error"]')).to_be_visible(timeout=8000)
    assert page.locator("#secret-name").get_attribute("aria-invalid") == "true"
    assert len(_secrets(base)) == 1


# ── Search-ahead ─────────────────────────────────────────────────────────────


def test_search_ahead_adds_an_mcp_tool_and_a_builtin(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    seed_mcp_source(base, "gfinch", tools=["vaultFill", "typeText"])
    _open_create(page, base)
    page.locator(TOOLS_INPUT).click()
    page.keyboard.type("vaultF")
    option = page.get_by_role("option")
    expect(option).to_have_count(1)
    expect(option).to_contain_text("mcp__gfinch__vaultFill")
    expect(option).to_contain_text("gfinch")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    assert _chips(page) == ["mcp__gfinch__vaultFill"]
    page.keyboard.type("python_e")
    row = page.get_by_role("option")
    expect(row).to_contain_text("python_exec")
    expect(row).to_contain_text("Built-in")
    row.click()
    assert _chips(page) == ["mcp__gfinch__vaultFill", "python_exec"]
    expect(page.locator(SAVE)).to_be_enabled()
    # The hint is the approved one, with no "unavailable" line.
    expect(page.locator('[data-testid="secret-tools-hint"]')).not_to_contain_text("unavailable")


def test_search_ahead_unavailable_still_accepts_typed_names(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    page.route("**/api/tool-names", lambda route: route.abort())
    _open_create(page, base)
    expect(page.locator('[data-testid="secret-tools-hint"]')).to_contain_text(
        "Suggestions are unavailable"
    )
    _add_tool(page, "mcp__stale__gone")
    assert _chips(page) == ["mcp__stale__gone"]


# ── Delete ───────────────────────────────────────────────────────────────────


def test_delete_names_the_granting_agents_and_removes_the_row(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    sid = seed_secret(base, "Bank", values=[("bank_login", "a")], allowed_tools=["shell"])
    seed_secret(base, "Keep", values=[("keep_k", "a")], allowed_tools=["shell"])
    name = app_with_agent.agent_name
    agent = httpx.get(f"{base}/api/agents/{name}", headers=auth_headers_for(base)).json()
    agent["secret_ids"] = [sid]
    assert (
        httpx.put(
            f"{base}/api/agents/{name}", json=agent, headers=auth_headers_for(base), timeout=5.0
        ).status_code
        == 200
    )
    _open_secret(page, base, sid, "Bank")
    used = page.locator('[data-testid="secret-used-by"]')
    expect(used).to_contain_text(f"Granted to {name}.")
    link = page.locator('[data-testid="secret-used-by-link"]')
    assert link.get_attribute("href") == _nav.href(f"agents/{_nav.seg(name)}/tools")
    btn = page.locator('[data-testid="delete-secret-btn"]')
    btn.click()
    expect(btn).to_contain_text("Delete and remove from 1 agent?")
    btn.click()
    _nav.expect_route(page, "library", timeout=8000)
    expect(_lists.list_row(page, "library/secrets", "Bank")).to_have_count(0)
    expect(_lists.list_row(page, "library/secrets", "Keep")).to_have_count(1)
    after = httpx.get(f"{base}/api/agents/{name}", headers=auth_headers_for(base)).json()
    assert after["secret_ids"] == []


def test_delete_with_no_grants_uses_the_plain_confirm(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    sid = seed_secret(base, "Solo", values=[("solo_k", "a")])
    _open_secret(page, base, sid, "Solo")
    expect(page.locator('[data-testid="secret-used-by"]')).to_contain_text(
        "No agent uses this secret yet."
    )
    btn = page.locator('[data-testid="delete-secret-btn"]')
    btn.click()
    expect(btn).to_contain_text("Confirm delete?")


# ── Leave guard ──────────────────────────────────────────────────────────────


def test_leave_guard_stay_keeps_edits_and_continue_resets_to_baseline(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    a = seed_secret(base, "Alpha", values=[("alpha_k", "a")])
    b = seed_secret(base, "Bravo", values=[("bravo_k", "b")])
    _open_secret(page, base, a, "Alpha")
    desc = page.locator("#secret-description")
    desc.fill("typed but unsaved")
    # Typing then reverting is clean: no prompt on a route change.
    desc.fill("")
    expect(page.locator(SAVE)).to_be_disabled()
    desc.fill("typed but unsaved")
    expect(page.locator(SAVE)).to_be_enabled()
    _lists.item_link(page, "library/secrets", "Bravo").click()
    expect(page.locator(DIALOG)).to_be_visible()
    page.locator(STAY).click()
    expect(page.locator(DIALOG)).to_have_count(0)
    _nav.expect_route(page, f"library/secrets/{_nav.seg(a)}")
    expect(desc).to_have_value("typed but unsaved")
    # Continue: lands on the other secret, nothing dirty anywhere.
    _lists.item_link(page, "library/secrets", "Bravo").click()
    expect(page.locator(DIALOG)).to_be_visible()
    page.locator(CONTINUE).click()
    _nav.expect_route(page, f"library/secrets/{_nav.seg(b)}", timeout=8000)
    expect(page.locator(".editor-title")).to_have_text("Bravo")
    assert page.evaluate("() => App.nav.isDirty()") is False
    # Back to the first secret: its stored (baseline) description, a mounted editor.
    _lists.item_link(page, "library/secrets", "Alpha").click()
    _nav.expect_route(page, f"library/secrets/{_nav.seg(a)}")
    expect(page.locator(".editor-title")).to_have_text("Alpha", timeout=8000)
    expect(page.locator("#secret-description")).to_have_value("")
    assert _secrets(base)[0]["description"] == ""


_HOLD_JS = """() => {
  window.__n = document.querySelector('[data-testid="secret-name"]');
  window.__v = document.querySelector('[data-testid="secret-kv-table"] [data-testid="secret-value-input"]');
  window.__v0 = window.__v.value;
  return true;
}"""


def _dirty_the_open_secret(page: Page) -> None:
    page.evaluate(_HOLD_JS)
    page.locator('[data-testid="secret-name"]').fill("Renamed in flight")
    page.locator(VALUES).first.fill("typed-secret-never-saved")
    expect(page.locator(SAVE)).to_be_enabled()
    assert page.evaluate("() => App.nav.isDirty()") is True


def test_leave_guard_continue_discards_into_the_detaching_nodes(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The discard() reset runs on the still-mounted nodes before they detach: the held
    references show the baseline name and no typed secret."""
    base = app_with_agent.base_url
    a = seed_secret(base, "Alpha", values=[("alpha_k", "stored-a")])
    _open_secret(page, base, a, "Alpha")
    _dirty_the_open_secret(page)
    _nav.open_destination(page, "agents")
    expect(page.locator(DIALOG)).to_be_visible()
    page.locator(CONTINUE).click()
    _nav.expect_route(page, "agents", timeout=8000)
    out = page.evaluate(
        "() => ({gone: window.__n.isConnected === false, name: window.__n.value,"
        " vgone: window.__v.isConnected === false, value: window.__v.value, before: window.__v0})"
    )
    assert out["gone"] is True
    assert out["name"] == "Alpha"
    # The reset rebuilds the value rows, so the held input is either gone or back at its mask;
    # either way no typed secret is left in the live page.
    assert out["vgone"] or out["value"] == out["before"]
    assert page.evaluate(_SCAN_JS, "typed-secret-never-saved") == []


def test_leave_guard_stay_keeps_typed_name_and_value(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    a = seed_secret(base, "Alpha", values=[("alpha_k", "stored-a")])
    _open_secret(page, base, a, "Alpha")
    _dirty_the_open_secret(page)
    _nav.open_destination(page, "agents")
    expect(page.locator(DIALOG)).to_be_visible()
    page.locator(STAY).click()
    expect(page.locator(DIALOG)).to_have_count(0)
    out = page.evaluate(
        "() => ({live: window.__n.isConnected, name: window.__n.value, value: window.__v.value})"
    )
    assert out == {"live": True, "name": "Renamed in flight", "value": "typed-secret-never-saved"}


# ── No plaintext in the DOM ──────────────────────────────────────────────────

_SCAN_JS = """(needle) => {
  const hits = [];
  document.querySelectorAll('*').forEach((el) => {
    for (const a of Array.from(el.attributes)) if (a.value.indexOf(needle) >= 0) hits.push(el.tagName + '[' + a.name + ']');
    for (const n of Array.from(el.childNodes)) if (n.nodeType === 3 && n.data.indexOf(needle) >= 0) hits.push(el.tagName + '#text');
  });
  return hits;
}"""


def test_a_typed_value_is_never_in_an_attribute_title_aria_or_text(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    needle = "TOPSECRET-needle-7731"
    _open_create(page, base)
    page.locator("#secret-name").fill("Plain check")
    page.locator(VALUES).first.fill(needle)
    assert page.evaluate(_SCAN_JS, needle) == []
    assert needle not in page.content()
    # The eye reveals it through .value only.
    page.get_by_role("button", name="Show value, row 1").click()
    expect(page.locator(VALUES).first).to_have_value(needle)
    assert page.evaluate(_SCAN_JS, needle) == []
    _add_tool(page, "shell")
    page.locator(SAVE).click()
    expect(page.locator('[data-testid="delete-secret-btn"]')).to_be_visible(timeout=8000)
    assert page.evaluate(_SCAN_JS, needle) == []
    assert needle not in page.content()
    expect(page.locator(VALUES).first).to_have_value("__MASKED__")
