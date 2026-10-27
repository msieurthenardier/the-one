"""A name refusal lands on the name field of every form that names something
(sortie 06 leg 3), and a failed agent load is a toast plus a header line.

The server's wording is shown verbatim (``App.api.fieldErrors``); no client copy of the
rule exists. Falls in the ``shared`` lane (the complement).
"""

from __future__ import annotations

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_knowledge_base, seed_mock_agent
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

RULE = "A name can't contain / or \\."
CONFLICT = "An agent with this name already exists."
SAVE = '[data-testid="save-agent-btn"]'
FIELD_ERROR = ".field-error"
HEADER_ERROR = ".editor-header .editor-error"


def _get(base: str, path: str) -> httpx.Response:
    return httpx.get(f"{base}{path}", headers=auth_headers_for(base), timeout=5.0)


def _agent_names(base: str) -> list[str]:
    return sorted(a["name"] for a in _get(base, "/api/agents").json())


def _expect_name_error(page: Page, control: str, text: str) -> None:
    expect(page.locator(FIELD_ERROR)).to_have_count(1, timeout=8000)
    expect(page.locator(FIELD_ERROR)).to_have_text(text)
    expect(page.locator(control)).to_have_attribute("aria-invalid", "true")
    expect(page.locator(HEADER_ERROR)).to_have_text("")


def _open_agent(page: Page, base: str, agent: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/general")
    expect(page.locator("#studio-name")).to_have_value(agent, timeout=8000)
    expect(page.locator('[data-testid="agent-load-error"]')).to_have_count(0)


def test_agent_create_refusal_and_conflict_on_the_name_field(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _nav.goto_settled(page, base, "agents")
    _lists.agents_new(page)
    name = page.locator("#studio-name")
    page.locator("#studio-description").fill("x")
    name.fill("a/b")
    page.locator(SAVE).click()
    _expect_name_error(page, "#studio-name", RULE)
    expect(name).to_be_focused()
    _nav.expect_route(page, "agents/~new")
    assert _agent_names(base) == [agent]
    # The error clears on the next keystroke in the field.
    name.press_sequentially("c")
    expect(page.locator(FIELD_ERROR)).to_have_count(0)

    name.fill(agent)
    page.locator(SAVE).click()
    _expect_name_error(page, "#studio-name", CONFLICT)
    assert _agent_names(base) == [agent]


def test_agent_rename_refusal_makes_no_put_and_conflict_is_shown(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    other = seed_mock_agent(base, app_with_agent.provider_id, name="other-agent")
    methods: list[str] = []

    def watch(route) -> None:  # noqa: ANN001
        methods.append(route.request.method)
        route.continue_()

    page.route("**/api/agents/**", watch)
    _open_agent(page, base, agent)
    methods.clear()
    name = page.locator("#studio-name")
    name.fill("a/b")
    page.locator(SAVE).click()
    _expect_name_error(page, "#studio-name", RULE)
    page.wait_for_timeout(300)
    assert "PUT" not in methods
    assert _agent_names(base) == sorted([agent, other])

    name.fill(other)
    page.locator(SAVE).click()
    _expect_name_error(page, "#studio-name", CONFLICT)
    assert "PUT" not in methods

    # Cancel puts the stored name back and drops the error.
    page.locator('[data-testid="cancel-agent-btn"]').click()
    expect(name).to_have_value(agent)
    expect(page.locator(FIELD_ERROR)).to_have_count(0)


def test_agent_rename_invalidates_connectors(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_agent(page, base, agent)
    page.evaluate(
        """() => {
          window.__invalidated = [];
          const orig = App.store.invalidate;
          App.store.invalidate = function () {
            window.__invalidated.push(Array.prototype.slice.call(arguments).join(','));
            return orig.apply(this, arguments);
          };
        }"""
    )
    page.locator("#studio-name").fill("renamed-agent")
    page.locator(SAVE).click()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("", timeout=8000)
    assert {"agents", "sessions", "connectors"} <= set(page.evaluate("window.__invalidated"))
    assert "renamed-agent" in _agent_names(base)


def test_provider_editor_refusal_on_the_name_field(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    _nav.goto_settled(page, base, "library")
    _lists.library_add(page, "providers")
    name = page.locator("#pf-name")
    page.locator("#pf-type").select_option("mock")
    name.fill("a/b")
    page.locator('[data-testid="save-provider-btn"]').click()
    _expect_name_error(page, "#pf-name", RULE)
    name.press_sequentially("c")
    expect(page.locator(FIELD_ERROR)).to_have_count(0)
    assert [p["name"] for p in _get(base, "/api/providers").json()] == ["mock"]


def test_provider_edit_refusal_on_the_name_field(app_with_provider: SeededApp, page: Page) -> None:
    base = app_with_provider.base_url
    _nav.goto(page, base, f"library/providers/{_nav.seg(app_with_provider.provider_id)}")
    name = page.locator("#pf-name")
    expect(name).to_have_value("mock", timeout=8000)
    name.fill("a\\b")
    page.locator('[data-testid="save-provider-btn"]').click()
    _expect_name_error(page, "#pf-name", RULE)
    page.locator('[data-testid="cancel-provider-btn"]').click()
    expect(page.locator(FIELD_ERROR)).to_have_count(0)
    names = [p["name"] for p in _get(base, "/api/providers").json()]
    assert names == ["mock"]


def test_knowledge_base_create_refusal_on_the_name_field(app_clean: str, page: Page) -> None:
    base = app_clean
    _nav.goto_settled(page, base, "library")
    _lists.library_add(page, "knowledge")
    name = page.locator('[data-testid="kb-create-name-input"]')
    name.fill("a/b")
    page.locator('[data-testid="kb-create-submit-btn"]').click()
    _expect_name_error(page, '[data-testid="kb-create-name-input"]', RULE)
    expect(page.locator('[data-testid="kb-create-error"]')).to_have_text("")
    assert _get(base, "/api/knowledge-bases").json() == []


def test_knowledge_base_edit_refusal_on_the_name_field(app_clean: str, page: Page) -> None:
    base = app_clean
    kb_id = seed_knowledge_base(base, "Docs")
    _nav.goto(page, base, f"library/knowledge/{_nav.seg(kb_id)}")
    edit = page.locator('[data-testid="kb-name-input"]')
    expect(edit).to_have_value("Docs", timeout=8000)
    edit.fill("a/b")
    page.locator('[data-testid="save-knowledge-btn"]').click()
    _expect_name_error(page, '[data-testid="kb-name-input"]', RULE)
    edit.press_sequentially("c")
    expect(page.locator(FIELD_ERROR)).to_have_count(0)
    assert [k["name"] for k in _get(base, "/api/knowledge-bases").json()] == ["Docs"]


def test_mcp_editor_refusal_on_the_name_field(app_clean: str, page: Page) -> None:
    base = app_clean
    _nav.goto_settled(page, base, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="name"]').fill("a/b")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command-runtime"]').select_option("__custom__")
    page.locator('[data-field="command"]').fill("x")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    _expect_name_error(page, '[data-field="name"]', RULE)
    assert _get(base, "/api/mcp-sources").json() == []


def test_load_failure_is_a_toast_and_a_header_line(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    failing = {"on": True}
    methods: list[str] = []

    def handler(route) -> None:  # noqa: ANN001
        methods.append(route.request.method)
        if route.request.method == "GET" and failing["on"]:
            route.abort()
        else:
            route.continue_()

    page.route(f"**/api/agents/{agent}", handler)
    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/general")
    line = page.locator('[data-testid="agent-load-error"]')
    expect(line).to_have_text(
        "Save is off because this agent’s settings didn’t load. Reopen the agent to try again.",
        timeout=8000,
    )
    expect(line).not_to_have_attribute("role", "alert")
    toast = page.locator(".app-flash.error")
    expect(toast).to_have_count(1)
    expect(toast).to_have_text("Couldn’t load this agent’s settings.")
    expect(page.locator(SAVE)).to_be_disabled()
    # Save's description resolves to the header line.
    described = page.locator(SAVE).get_attribute("aria-describedby")
    assert described and described == page.locator(HEADER_ERROR).get_attribute("id")
    assert page.locator(f"#{described}").get_attribute("data-testid") == "agent-load-error"

    # A re-render of the same editor neither adds a toast nor drops the line.
    page.locator('[data-field="description"]').fill("edit")
    page.locator('[data-testid="cancel-agent-btn"]').click()
    expect(line).to_be_visible()
    expect(page.locator(".app-flash.error")).to_have_count(1)

    # A script-driven Save does nothing and keeps the line.
    methods.clear()
    page.locator(SAVE).evaluate("(el) => { el.disabled = false; el.click(); }")
    page.wait_for_timeout(300)
    expect(line).to_be_visible()
    assert "PUT" not in methods and "POST" not in methods

    # Reopening the agent after the fetch recovers clears the line.
    failing["on"] = False
    _nav.goto(page, base, "agents")
    _lists.open_item(page, "agents", agent)
    expect(page.locator("#studio-name")).to_have_value(agent, timeout=8000)
    expect(line).to_have_count(0)
    assert page.locator(SAVE).get_attribute("aria-describedby") is None
    expect(page.locator(HEADER_ERROR)).to_have_text("")
    assert page.locator(HEADER_ERROR).get_attribute("data-empty") is not None
