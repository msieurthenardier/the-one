"""The agent editor's Tools-tab Secrets section and the chat drawer's Secrets group
(sortie 10, leg 3 part B: B1-B3).

B1: the section sits before MCP servers with the approved intro, a toggle per secret
(name label, "{description} · N tool(s)" described-by, no keys or tool names), an empty
state with a Library link, and a load-failure danger status with no loaded marker.
B2: Save sends ``secret_ids`` (the checked ids, Library order) only when the section
loaded; open-and-close stays clean; a 422 on ``["secret_ids", i]`` shows on the section.
B3: the drawer's read-only Secrets group follows the store. Lane ``agent-tabs``.
"""

from __future__ import annotations

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_secret
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

SECTION = '[data-testid="agent-tools-secrets-section"]'
ROOT = '[data-testid="agent-secrets-root"]'


def _get_agent(base: str, name: str) -> dict:
    r = httpx.get(f"{base}/api/agents/{name}", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _grant(base: str, name: str, ids: list[str]) -> None:
    body = _get_agent(base, name)
    body["secret_ids"] = ids
    r = httpx.put(
        f"{base}/api/agents/{name}", json=body, headers=auth_headers_for(base), timeout=5.0
    )
    assert r.status_code == 200, r.text


def _open_tools(page: Page, base: str) -> None:
    _nav.goto(page, base, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    _lists.first_row(page, "agents").click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="tab-tools"]').click()
    expect(page.locator(SECTION)).to_be_visible(timeout=8000)


def _reselect(page: Page) -> None:
    _nav.open_destination(page, "agents")
    expect(page.locator('[data-testid="tab-general"]')).to_have_count(0, timeout=8000)
    _lists.first_row(page, "agents").click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="tab-tools"]').click()
    expect(page.locator(SECTION)).to_be_visible(timeout=8000)


def _click_switch(locator) -> None:  # noqa: ANN001
    locator.locator("xpath=ancestor::label").click()


def _save(page: Page) -> None:
    save = page.locator('[data-testid="save-agent-btn"]')
    expect(save).to_be_enabled(timeout=5000)
    save.click()
    expect(save).to_be_disabled(timeout=5000)


def _capture_puts(page: Page, agent: str) -> list[dict]:
    bodies: list[dict] = []

    def handler(route) -> None:  # noqa: ANN001
        if route.request.method == "PUT":
            bodies.append(route.request.post_data_json)
        route.continue_()

    page.route(f"**/api/agents/{agent}", handler)
    return bodies


@pytest.mark.browser
def test_section_sits_before_mcp_with_intro_rows_and_no_keys_or_tools(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    a = seed_secret(
        base, "Home address", [("home_city", "Springfield")], ["shell", "glob"], "Where I live"
    )
    b = seed_secret(base, "Bare", [("bare_key", "zzz-hidden-value")], ["shell"])
    _open_tools(page, base)

    # Order: Secrets, MCP servers, Built-in tools.
    order = page.evaluate(
        """() => Array.from(document.querySelectorAll(
          '[data-testid="agent-tools-secrets-section"], [data-testid="agent-tools-mcp-section"],'
          + ' [data-testid="agent-tools-builtin-section"]')).map((e) => e.dataset.testid)"""
    )
    assert order == [
        "agent-tools-secrets-section",
        "agent-tools-mcp-section",
        "agent-tools-builtin-section",
    ], order
    expect(page.locator(f"{SECTION} h2")).to_have_text("Secrets")
    expect(page.locator('[data-testid="agent-secrets-intro"]')).to_have_text(
        "Secrets this agent can pass to its tools. It never sees their values. "
        "Manage them in Library › Secrets."
    )
    toggle_a = page.locator(f'[data-testid="agent-secret-toggle-{a}"]')
    expect(toggle_a).not_to_be_checked()
    expect(page.locator(f'[data-testid="agent-secret-meta-{a}"]')).to_have_text(
        "Where I live · 2 tools"
    )
    expect(page.locator(f'[data-testid="agent-secret-meta-{b}"]')).to_have_text("1 tool")
    # Accessible name is the secret's name; the meta text describes it.
    expect(toggle_a).to_have_accessible_name("Home address")
    expect(toggle_a).to_have_accessible_description("Where I live · 2 tools")
    # No keys, values or tool names anywhere in the section.
    text = page.locator(SECTION).inner_text()
    for leaked in ("home_city", "Springfield", "bare_key", "zzz-hidden-value", "glob"):
        assert leaked not in text, leaked
    html = page.locator(SECTION).inner_html()
    assert "zzz-hidden-value" not in html and "Springfield" not in html


@pytest.mark.browser
def test_empty_state_links_to_the_library(app_with_agent: SeededApp, page: Page) -> None:
    _open_tools(page, app_with_agent.base_url)
    empty = page.locator('[data-testid="agent-secrets-empty-state"]')
    expect(empty).to_contain_text("No secrets yet.")
    expect(empty.locator("a")).to_have_attribute("href", _nav.href("library"))
    # A genuinely empty list still counts as loaded.
    expect(page.locator(f'{ROOT}[data-secret-list-loaded="true"]')).to_have_count(1)


@pytest.mark.browser
def test_grant_save_exact_body_library_order_and_clean_open_close(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    assert agent is not None
    s1 = seed_secret(base, "Alpha", [("alpha_k", "v1")])
    s2 = seed_secret(base, "Beta", [("beta_k", "v2")])
    s3 = seed_secret(base, "Gamma", [("gamma_k", "v3")])
    library = [
        s["id"]
        for s in httpx.get(
            f"{base}/api/secrets", headers=auth_headers_for(base), timeout=5.0
        ).json()
    ]
    _grant(base, agent, [s2])

    _open_tools(page, base)
    expect(page.locator(f'[data-testid="agent-secret-toggle-{s2}"]')).to_be_checked()
    # Open-and-close stays clean: Save is disabled with nothing touched.
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_disabled()

    bodies = _capture_puts(page, agent)
    # Check s3 then s1 (so a click order differs from the Library order).
    _click_switch(page.locator(f'[data-testid="agent-secret-toggle-{s3}"]'))
    _click_switch(page.locator(f'[data-testid="agent-secret-toggle-{s1}"]'))
    _save(page)
    assert len(bodies) == 1, bodies
    expected = [i for i in library if i in {s1, s2, s3}]
    assert bodies[0]["secret_ids"] == expected, (bodies[0]["secret_ids"], expected)
    assert sorted(_get_agent(base, agent)["secret_ids"]) == sorted([s1, s2, s3])

    # Uncheck everything: the legitimate empty list is sent.
    for sid in (s1, s2, s3):
        _click_switch(page.locator(f'[data-testid="agent-secret-toggle-{sid}"]'))
    _save(page)
    assert bodies[-1]["secret_ids"] == []
    assert _get_agent(base, agent)["secret_ids"] == []


@pytest.mark.browser
def test_load_failure_shows_danger_status_and_omits_secret_ids(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    assert agent is not None
    sid = seed_secret(base, "Kept", [("kept_k", "v")])
    _grant(base, agent, [sid])

    _open_tools(page, base)
    expect(page.locator(f'[data-testid="agent-secret-toggle-{sid}"]')).to_be_checked()

    page.route(
        "**/api/secrets",
        lambda route: route.fulfill(status=500, content_type="text/plain", body="err"),
    )
    _reselect(page)
    expect(page.locator('[data-testid="agent-secrets-load-error"]')).to_be_visible(timeout=5000)
    expect(page.locator('[data-secret-list-loaded="true"]')).to_have_count(0)
    page.unroute("**/api/secrets")

    bodies = _capture_puts(page, agent)
    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').fill("save while the secrets list is broken")
    _save(page)
    assert len(bodies) == 1, bodies
    assert "secret_ids" not in bodies[0], bodies[0].get("secret_ids")
    # The server kept the stored grant.
    page.unroute(f"**/api/agents/{agent}")
    assert _get_agent(base, agent)["secret_ids"] == [sid]


@pytest.mark.browser
def test_a_422_on_secret_ids_shows_on_the_section(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    assert agent is not None
    sid = seed_secret(base, "Doomed", [("doomed_k", "v")])
    _open_tools(page, base)
    _click_switch(page.locator(f'[data-testid="agent-secret-toggle-{sid}"]'))
    # Another tab deletes the secret before this Save.
    r = httpx.delete(f"{base}/api/secrets/{sid}", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code in (200, 204), r.text
    page.locator('[data-testid="save-agent-btn"]').click()
    err = page.locator('[data-testid="agent-secrets-error"]')
    expect(err).to_be_visible(timeout=5000)
    expect(err).not_to_have_text("")


@pytest.mark.browser
def test_section_error_is_a_permanent_live_region_linked_to_the_switches(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    doomed = seed_secret(base, "Doomed", [("doomed_k", "v")])
    other = seed_secret(base, "Other", [("other_k", "v")])
    _open_tools(page, base)
    err = page.locator('[data-testid="agent-secrets-error"]')
    # A live region from mount: present, visible-to-AT (not hidden), empty.
    expect(err).to_have_attribute("role", "status")
    assert err.evaluate("e => e.hidden") is False
    expect(err).to_have_text("")
    err_id = err.get_attribute("id")
    assert err_id
    # The switch list is a group labelled by the section heading.
    group = page.locator('[data-testid="agent-secrets-list"]')
    expect(group).to_have_attribute("role", "group")
    label_id = group.get_attribute("aria-labelledby")
    assert label_id
    expect(page.locator(f"#{label_id}")).to_have_text("Secrets")

    def described(sid: str) -> str:
        return (
            page.locator(f'[data-testid="agent-secret-toggle-{sid}"]').get_attribute(
                "aria-describedby"
            )
            or ""
        )

    assert err_id not in described(doomed).split()
    _click_switch(page.locator(f'[data-testid="agent-secret-toggle-{doomed}"]'))
    r = httpx.delete(f"{base}/api/secrets/{doomed}", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code in (200, 204), r.text
    page.locator('[data-testid="save-agent-btn"]').click()
    expect(err).not_to_have_text("", timeout=5000)
    assert err.evaluate("e => e.hidden") is False
    assert err.get_attribute("id") == err_id
    for sid in (doomed, other):
        assert err_id in described(sid).split(), described(sid)
        assert len(described(sid).split()) == 2
    # Any toggle clears the error and the reference.
    _click_switch(page.locator(f'[data-testid="agent-secret-toggle-{other}"]'))
    expect(err).to_have_text("")
    for sid in (doomed, other):
        assert err_id not in described(sid).split()


@pytest.mark.browser
def test_drawer_secrets_group_follows_grants_and_is_read_only(
    app_with_agent: SeededApp, page: Page
) -> None:
    from browser import _chats

    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    assert agent is not None
    zed = seed_secret(base, "Zed token", [("zed_k", "v")])
    abe = seed_secret(base, "Abe token", [("abe_k", "v")])
    seed_secret(base, "Not granted", [("ng_k", "v")])
    _grant(base, agent, [zed, abe])

    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    group = page.locator('[data-testid="chat-drawer-uses"] [data-group="secrets"]')
    expect(group.locator("h4")).to_have_text("Secrets")
    expect(group.locator("li")).to_have_count(2, timeout=8000)
    items = group.locator("li .chat-drawer-item-name").all_inner_texts()
    assert items == ["Abe token", "Zed token"], items
    expect(group.locator("a, button")).to_have_count(0)
    # The group sits between MCP servers and Built-in tools.
    labels = page.locator('[data-testid="chat-drawer-uses"] h4').all_inner_texts()
    assert labels.index("MCP servers") + 1 == labels.index("Secrets")
    assert labels.index("Secrets") + 1 == labels.index("Built-in tools")
    # Values never reach the drawer.
    assert "zed_k" not in page.locator("#chat-drawer").inner_text()
