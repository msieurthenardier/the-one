# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Agents list column and detail pane (M25 F3 L3, flight DD1-DD4, DD8).

The Agents destination is an alphabetical ``App.ui.listPane`` in the aside
(testid ``agents-list``) beside the detail pane: the tabbed agent editor with an
"Agents" breadcrumb and no Back control, or a pane-size empty state when no agent
is open. ``#agents/~new`` is the create route.

* AC1 -- order, count, filter (name, model, provider TYPE slug) and row anatomy,
  run in Chromium AND WebKit (``engine_browser`` + ``credentialed_context``
  against the running app);
* AC2 -- selection, breadcrumb, no Back, a filtered-out selection, the cold
  deep link scroll; the breadcrumb's "Agents" link closes the agent and
  focuses its row, asking once when dirty (M25 F3 L4b);
* AC3 -- the two empty-state copies;
* AC4 -- create: entry points, focus, a repeated "New", the leave guard,
  save-create (replace + announce; no replace for a user who moved on while
  it was in flight, the flight-end review), Cancel (enabled on the create form
  from first render, typed into or not, and disabled on a clean open agent:
  the behavior-gate fix), names that look like create;
* AC5 -- the unsaved indicator;
* AC6 -- delete: the root, the row, focus, the announcement.

Rewrites ``test_flow_agent_tile.py`` (the retired tile grid) as list-row tests.
Falls in the ``agents`` lane (``test_flow_agents_*`` in ``scripts/run-tests.sh``).
"""

from __future__ import annotations

import re

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.conftest import credentialed_context
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_agents
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

DIALOG = '[data-testid="confirm-dialog-overlay"]'
STAY = '[data-testid="modal-cancel-btn"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'
ROWS = '[data-testid="agent-item"]'
COUNT = '[data-testid="agents-list"] .ui-list-pane-total'


def _seed_openrouter(base: str, name: str) -> str:
    """An openrouter-TYPE provider (created only; nothing ever calls it here)."""
    r = httpx.post(
        f"{base}/api/providers",
        json={
            "name": name,
            "type": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-or-test",
        },
        headers=auth_headers_for(base),
        timeout=5.0,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _visible_labels(page: Page) -> list[str]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll(
            '[data-testid="agents-list"] li:not([hidden]) .ui-list-pane-label'))
            .map((el) => el.textContent)"""
    )


def _announcer(page: Page) -> str:
    return page.locator('[data-testid="route-announcer"]').inner_text()


def _open_editor(page: Page, base: str, name: str) -> None:
    _nav.goto_settled(page, base, "agents")
    _lists.open_item(page, "agents", name)
    expect(page.locator(".editor-title")).to_have_text(name, timeout=8000)
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_disabled(timeout=8000)


# ── AC1: order, count, filter, anatomy (both engines) ───────────────────────


def test_agents_list_order_count_filter_and_anatomy(
    engine_browser, app_with_provider: SeededApp
) -> None:
    base = app_with_provider.base_url
    mock_id = app_with_provider.provider_id  # a mock provider named "mock"
    router_id = _seed_openrouter(base, "Router Prime")
    seed_mock_agents(base, mock_id, 31, prefix="agent")
    seed_mock_agent(base, mock_id, name="Zeta research", model="zeta-model-x")
    seed_mock_agent(base, router_id, name="alpha router", model="gpt-like-1")
    seed_mock_agent(base, router_id, name="Mid router", model="gpt-like-2")
    seed_mock_agent(base, mock_id, name="beta", model="mock-default")
    context = credentialed_context(engine_browser, base, viewport={"width": 1440, "height": 900})
    page = context.new_page()
    try:
        _nav.goto_settled(page, base, "agents")
        expect(page.locator(ROWS)).to_have_count(35, timeout=8000)
        expect(page.locator(COUNT)).to_have_text("35 of 35")

        # Order: flat A-Z by localeCompare on the name.
        labels = _visible_labels(page)
        want = page.evaluate("(l) => l.slice().sort((a, b) => a.localeCompare(b))", labels)
        assert labels == want, labels
        assert (
            labels[0] == "agent 01" and "alpha router" in labels and labels[-1] == "Zeta research"
        )

        # Filter by name fragment: the count follows.
        _lists.filter_agents(page, "agent 1")
        expect(page.locator(COUNT)).to_have_text("10 of 35")
        assert _visible_labels(page) == [f"agent {i}" for i in range(10, 20)]

        # Filter by model fragment.
        _lists.filter_agents(page, "ZETA-MODEL")
        expect(page.locator(COUNT)).to_have_text("1 of 35")
        assert _visible_labels(page) == ["Zeta research"]

        # Filter by provider TYPE slug (A16); the display name does not match.
        _lists.filter_agents(page, "openrouter")
        expect(page.locator(COUNT)).to_have_text("2 of 35")
        assert _visible_labels(page) == ["alpha router", "Mid router"]
        _lists.filter_agents(page, "prime")
        expect(page.locator(COUNT)).to_have_text("0 of 35")
        _lists.filter_agents(page, "  MOCK ")  # trimmed, case-insensitive
        expect(page.locator(COUNT)).to_have_text("33 of 35")

        # No match: the empty line names the query; the count reads 0 of N.
        _lists.filter_agents(page, "nomatch-xyz")
        expect(page.locator(COUNT)).to_have_text("0 of 35")
        empty = page.locator('[data-testid="agents-list"] .ui-list-pane-empty')
        expect(empty).to_be_visible()
        expect(empty).to_have_text('No agents match "nomatch-xyz".')
        _lists.filter_agents(page, "")
        expect(page.locator(COUNT)).to_have_text("35 of 35")

        # Row anatomy: dot (aria-hidden, a badge--{type} disc), name, mono model.
        row = _lists.list_row(page, "agents", "Mid router")
        anatomy = row.evaluate(
            """(a) => {
              const kids = Array.from(a.children).map((c) => c.className);
              const dot = a.querySelector('.badge-dot');
              const meta = a.querySelector('.ui-list-pane-meta');
              const mono = getComputedStyle(document.documentElement)
                .getPropertyValue('--font-family-mono').trim();
              const r = dot.getBoundingClientRect();
              return {tag: a.tagName, kids, dotHidden: dot.getAttribute('aria-hidden'),
                      dotClass: dot.className, dotW: r.width, dotH: r.height,
                      radius: getComputedStyle(dot).borderTopLeftRadius,
                      meta: meta.textContent, metaFont: getComputedStyle(meta).fontFamily, mono,
                      href: a.getAttribute('href'), suffix: a.querySelector('.visually-hidden').textContent};
            }"""
        )
        assert anatomy["tag"] == "A", anatomy
        assert anatomy["kids"] == ["ui-list-pane-lead", "ui-list-pane-text"], anatomy
        assert anatomy["dotHidden"] == "true" and "badge--openrouter" in anatomy["dotClass"], (
            anatomy
        )
        assert (anatomy["dotW"], anatomy["dotH"], anatomy["radius"]) == (8, 8, "50%"), anatomy
        assert anatomy["meta"] == "gpt-like-2", anatomy
        assert "Mono" in anatomy["metaFont"] and "Mono" in anatomy["mono"], anatomy
        assert anatomy["href"] == _nav.href(f"agents/{_nav.seg('Mid router')}"), anatomy
        # A trailing separator: the model follows (the flight-end review).
        assert anatomy["suffix"] == ", Router Prime,", anatomy
        # The accessible name carries the provider name (A31), then the model:
        # "Mid router, Router Prime, gpt-like-2".
        expect(
            page.get_by_role(
                "link", name=re.compile(r"^Mid router\s*, Router Prime,\s*gpt-like-2$")
            )
        ).to_have_count(1)
    finally:
        context.close()


def test_agent_with_a_deleted_provider_gets_a_neutral_dot(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Edge case: a provider missing for an agent -- the dot is neutral, the
    accessible-name suffix reads "no provider" and no type slug matches. The
    API refuses to delete a provider agents use, so the provider list is
    stubbed empty (the shape a deleted provider leaves)."""
    base = app_with_provider.base_url
    seed_mock_agent(base, app_with_provider.provider_id, name="orphan", model="zz-model")

    def no_providers(route) -> None:  # noqa: ANN001
        if route.request.method == "GET":
            route.fulfill(status=200, content_type="application/json", body="[]")
        else:
            route.continue_()

    page.route("**/api/providers", no_providers)
    _nav.goto_settled(page, base, "agents")
    row = _lists.list_row(page, "agents", "orphan")
    expect(row).to_be_visible(timeout=8000)
    assert row.locator(".badge-dot").get_attribute("class") == "badge badge-dot badge-dot--none"
    expect(row.locator(".visually-hidden")).to_have_text(", no provider,")
    _lists.filter_agents(page, "mock")
    expect(page.locator(COUNT)).to_have_text("0 of 1")


# ── AC2: selection and detail ───────────────────────────────────────────────


def test_open_agent_selects_row_with_breadcrumb_and_no_back(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    seed_mock_agent(base, app_with_agent.provider_id, name="other-agent")
    _nav.goto_settled(page, base, "agents")
    _lists.open_item(page, "agents", name)
    _nav.expect_route(page, f"agents/{_nav.seg(name)}/general")
    _lists.expect_selected(page, "agents", name)
    expect(page.locator(".editor-title")).to_have_text(name, timeout=8000)
    # The list stays visible beside the editor.
    expect(page.locator('[data-testid="agents-list"]')).to_be_visible()
    expect(_lists.list_row(page, "agents", "other-agent")).to_be_visible()

    # Breadcrumb "Agents": the first child of .editor-header-text. One h1.
    crumb = page.evaluate(
        """() => { const t = document.querySelector('.studio-editor .editor-header-text');
                   const f = t.firstElementChild;
                   return {cls: f.className, text: f.textContent,
                           underline: getComputedStyle(f.querySelector('a')).textDecorationLine,
                           h1: document.querySelectorAll('#main-content .content-panel.active h1').length}; }"""
    )
    # The link is underlined at rest: not told from text by colour alone.
    assert crumb == {
        "cls": "editor-breadcrumb",
        "text": "Agents",
        "underline": "underline",
        "h1": 1,
    }, crumb
    # No Back control in the editor header (DD2; its testid is retired).
    expect(page.locator(".studio-editor .back-btn")).to_have_count(0)
    expect(page.get_by_role("button", name=re.compile("^Back"))).to_have_count(0)

    # Filtering the open agent out keeps the editor showing (section 10 item 7).
    _lists.filter_agents(page, "other")
    expect(_lists.list_row(page, "agents", name)).to_be_hidden()
    expect(page.locator(".editor-title")).to_have_text(name)
    expect(page.locator(".studio-editor")).not_to_have_class(re.compile(r"\bis-hidden\b"))
    _lists.filter_agents(page, "")
    _lists.expect_selected(page, "agents", name)


def test_breadcrumb_link_closes_the_agent_and_focuses_its_row(
    app_with_agent: SeededApp, page: Page
) -> None:
    """M25 F3 L4b (AC2, AC5b; the DD2 refinement): the "Agents" crumb is a link
    to ``#agents`` (``editor-breadcrumb-link``). It closes the open agent to the
    empty detail state and focus goes to the agent's row (DD8). With a dirty
    editor it asks once: Stay keeps the edit and returns focus to the link;
    Continue closes and focuses the row."""
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    seed_mock_agent(base, app_with_agent.provider_id, name="other-agent")
    _open_editor(page, base, name)
    link = _lists.breadcrumb_link(page)
    expect(link).to_have_text("Agents")
    expect(link).to_have_attribute("href", _nav.href("agents"))
    before = page.evaluate("history.length")
    _lists.close_item(page)
    _nav.expect_route(page, "agents")
    expect(page.locator('[data-testid="agent-select-empty"]')).to_be_visible(timeout=8000)
    expect(page.locator(".studio-editor")).to_have_class(re.compile(r"\bis-hidden\b"))
    row = _lists.list_row(page, "agents", name)
    expect(row).to_be_focused(timeout=8000)
    expect(page.locator(f'{ROWS}[aria-current="page"]')).to_have_count(0)
    assert page.evaluate("history.length") == before + 1  # a pushed go(), like a row click
    expect(page.locator(DIALOG)).to_have_count(0)

    _lists.open_item(page, "agents", name)
    desc = page.locator('[data-field="description"]')
    expect(desc).to_be_visible(timeout=8000)
    desc.fill("dirty edit")
    page.wait_for_function("() => App.nav.isDirty()")
    route = _nav.current_route(page)
    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    page.wait_for_timeout(300)
    expect(page.locator(DIALOG)).to_have_count(0)
    _nav.expect_route(page, route)
    expect(desc).to_have_value("dirty edit")
    expect(_lists.breadcrumb_link(page)).to_be_focused()
    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _nav.expect_route(page, "agents")
    expect(row).to_be_focused(timeout=8000)
    page.wait_for_timeout(300)
    expect(page.locator(DIALOG)).to_have_count(0)
    assert page.evaluate("App.nav.isDirty()") is False


def test_cold_deep_link_scrolls_the_selected_row_into_view(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    names = seed_mock_agents(base, app_with_provider.provider_id, 35, prefix="agent")
    target = names[24]  # the 25th, below the fold of a 900px-tall list
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto_settled(page, base, f"agents/{_nav.seg(target)}/general")
    expect(page.locator(".editor-title")).to_have_text(target, timeout=8000)
    _lists.expect_selected(page, "agents", target)
    geo = """(n) => {
          const body = document.querySelector('[data-testid="agents-list"] .ui-list-pane-body');
          const row = Array.from(body.querySelectorAll('.ui-list-pane-row'))
            .find((r) => r.querySelector('.ui-list-pane-label').textContent === n);
          const b = body.getBoundingClientRect();
          const r = row.getBoundingClientRect();
          return {scrollTop: body.scrollTop, row: [r.top, r.bottom], body: [b.top, b.bottom],
                  winY: scrollY, docH: document.documentElement.scrollHeight};
        }"""
    try:
        page.wait_for_function(
            f"(n) => {{ const g = ({geo})(n); return g.scrollTop > 0 &&"
            " g.row[0] >= g.body[0] - 0.5 && g.row[1] <= g.body[1] + 0.5; }",
            arg=target,
            timeout=8000,
        )
    except Exception as exc:
        raise AssertionError(page.evaluate(geo, target)) from exc


# ── AC3: empty states ───────────────────────────────────────────────────────


def test_empty_detail_state_with_agents_offers_new(app_with_agent: SeededApp, page: Page) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    state = page.locator('[data-testid="agent-select-empty"]')
    expect(state).to_be_visible(timeout=8000)
    expect(state).to_contain_text("Pick an agent from the list to edit it.")
    expect(page.locator('[data-testid="agent-empty"]')).to_have_count(0)
    expect(page.locator(".studio-editor")).to_have_class(re.compile(r"\bis-hidden\b"))
    page.locator('[data-testid="agent-empty-new"]').click()
    _nav.expect_route(page, "agents/~new")
    expect(page.locator(".editor-title")).to_have_text("New Agent", timeout=8000)
    expect(page.locator("#studio-name")).to_be_focused(timeout=8000)
    expect(state).to_be_hidden()


def test_empty_detail_state_with_no_agents(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto_settled(page, app_with_provider.base_url, "agents")
    state = page.locator('[data-testid="agent-empty"]')
    expect(state).to_be_visible(timeout=8000)
    expect(state).to_contain_text("No agents yet.")
    expect(state.locator('[data-testid="agent-empty-new"]')).to_be_visible()
    expect(page.locator(".studio-editor")).to_have_class(re.compile(r"\bis-hidden\b"))
    expect(page.locator(COUNT)).to_have_text("")
    expect(page.locator('[data-testid="agents-list"] .ui-list-pane-empty')).to_have_text(
        "No agents yet."
    )


# ── AC4: create ─────────────────────────────────────────────────────────────


def test_new_opens_create_route_and_repeat_new_is_a_noop(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    _lists.agents_new(page)
    name = page.locator("#studio-name")
    expect(name).to_be_focused(timeout=8000)
    expect(page.locator(ROWS + '[aria-current="page"]')).to_have_count(0)
    expect(page.locator('[data-testid="agents-list"]')).to_be_visible()

    # A repeated "New" with the clean form open re-renders nothing: the same
    # editor node stays, nothing is pushed, and focus returns to the name.
    page.evaluate("document.querySelector('.studio-editor .editor-title').dataset.mark = '1'")
    before = page.evaluate("history.length")
    page.locator('[data-testid="agents-filter"]').focus()
    page.locator('[data-testid="new-agent-btn"]').click()
    expect(name).to_be_focused()
    assert (
        page.evaluate("document.querySelector('.studio-editor .editor-title').dataset.mark") == "1"
    )
    assert page.evaluate("history.length") == before
    _nav.expect_route(page, "agents/~new")


def test_new_from_a_dirty_agent_asks_once_and_stay_keeps_edit_and_url(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_editor(page, base, agent)
    route = _nav.current_route(page)
    page.locator('[data-field="description"]').fill("half an edit")
    page.locator('[data-testid="new-agent-btn"]').click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    page.wait_for_timeout(300)  # negative window: no second dialog
    expect(page.locator(DIALOG)).to_have_count(0)
    _nav.expect_route(page, route)
    expect(page.locator('[data-field="description"]')).to_have_value("half an edit")


def test_save_create_replaces_the_route_selects_and_announces(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    _lists.agents_new(page)
    length = page.evaluate("history.length")
    page.locator('[data-field="name"]').fill("Fresh agent")
    expect(page.locator('#studio-model option[value="mock-default"]')).to_be_attached(timeout=8000)
    page.locator("#studio-model").select_option("mock-default")
    page.locator('[data-testid="save-agent-btn"]').click()
    _nav.expect_route(page, f"agents/{_nav.seg('Fresh agent')}/general", timeout=8000)
    expect(page.locator(".editor-title")).to_have_text("Fresh agent", timeout=8000)
    _lists.expect_selected(page, "agents", "Fresh agent")
    assert page.evaluate("history.length") == length  # replaced, not pushed
    page.wait_for_function(
        "() => document.querySelector('[data-testid=\"route-announcer\"]').textContent"
        " === 'Agents — Fresh agent'"
    )


@pytest.mark.parametrize("move_to", ["agent", "destination"])
def test_save_create_does_not_pull_back_a_user_who_moved_on(
    app_with_agent: SeededApp, page: Page, move_to: str
) -> None:
    """Flight-end review: the save-create's list reload (``GET /api/agents``,
    after the POST) is held while the user opens another agent, or another
    destination. On release the user stays where they went (no bypass replace
    onto the new agent, no dialog), and the list still gains the new row."""
    base, other = app_with_agent.base_url, app_with_agent.agent_name
    _nav.goto_settled(page, base, "agents")
    _lists.agents_new(page)
    page.locator('[data-field="name"]').fill("Late agent")
    expect(page.locator('#studio-model option[value="mock-default"]')).to_be_attached(timeout=8000)
    page.locator("#studio-model").select_option("mock-default")

    held: list = []
    release = {"done": False}

    def hold_list(route) -> None:  # noqa: ANN001
        if route.request.method == "GET" and not release["done"]:
            held.append(route)
        else:
            route.continue_()

    page.route("**/api/agents", hold_list)
    page.locator('[data-testid="save-agent-btn"]').click()
    # The POST went through (the agent exists); its list reload is held.
    for _ in range(160):
        if held:
            break
        page.wait_for_timeout(50)
    assert held, "the save-create list reload never reached the route handler"
    r = httpx.get(f"{base}/api/agents", headers=auth_headers_for(base), timeout=5.0)
    assert "Late agent" in [a["name"] for a in r.json()]

    if move_to == "agent":
        _lists.open_item(page, "agents", other)
        expect(page.locator(".editor-title")).to_have_text(other, timeout=8000)
        where = f"agents/{_nav.seg(other)}/general"
    else:
        _nav.open_destination(page, "settings")
        expect(_nav.destination_panel(page, "settings")).to_be_visible(timeout=8000)
        where = _nav.current_route(page)
        assert where.startswith("settings/"), where
    _nav.expect_route(page, where)
    expect(page.locator(DIALOG)).to_have_count(0)

    release["done"] = True
    while held:
        held.pop(0).continue_()
    # The reload landed: the new agent is in Studio's list copy.
    page.wait_for_function(
        "() => (App.areas.find((a) => a.id === 'studio')._agents || [])"
        ".some((a) => a.name === 'Late agent')",
        timeout=8000,
    )
    page.wait_for_timeout(300)  # negative window: no late replace onto the new agent
    _nav.expect_route(page, where)
    expect(page.locator(DIALOG)).to_have_count(0)
    if move_to == "agent":
        expect(page.locator(".editor-title")).to_have_text(other)
        _lists.expect_selected(page, "agents", other)
        expect(_lists.list_row(page, "agents", "Late agent")).to_be_visible()
    else:
        _nav.open_destination(page, "agents")
        expect(_lists.list_row(page, "agents", "Late agent")).to_be_visible(timeout=8000)


def test_cancel_on_the_create_form_returns_to_the_root_and_focuses_a_row(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    _lists.agents_new(page)
    page.locator('[data-field="name"]').fill("never saved")
    cancel = page.locator('[data-testid="cancel-agent-btn"]')
    expect(cancel).to_be_enabled()
    cancel.click()
    expect(page.locator(DIALOG)).to_have_count(0)
    _nav.expect_route(page, "agents")
    expect(_lists.agents_empty_state(page)).to_be_visible(timeout=8000)
    expect(_lists.list_row(page, "agents", app_with_agent.agent_name)).to_be_focused()


def test_cancel_on_the_create_form_with_no_agents_focuses_new(
    app_with_provider: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_provider.base_url, "agents")
    _lists.agents_new(page)
    page.locator('[data-field="name"]').fill("never saved")
    page.locator('[data-testid="cancel-agent-btn"]').click()
    _nav.expect_route(page, "agents")
    expect(page.locator('[data-testid="agent-empty"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="new-agent-btn"]')).to_be_focused()


@pytest.mark.parametrize("with_agent", [True, False], ids=["focuses-first-row", "focuses-new"])
def test_cancel_on_a_pristine_create_form_abandons_it(
    app_with_provider: SeededApp, page: Page, with_agent: bool
) -> None:
    """Behavior-gate fix (list-and-detail L6): on `#agents/~new` with nothing
    typed, Cancel is enabled and abandons creation (DD8) -- no dialog, a replace
    to `#agents`, the empty state, and focus on the first row, else "New"."""
    base = app_with_provider.base_url
    if with_agent:
        seed_mock_agent(base, app_with_provider.provider_id, name="Existing agent")
    _nav.goto_settled(page, base, "agents")
    _lists.agents_new(page)
    cancel = page.locator('[data-testid="cancel-agent-btn"]')
    expect(cancel).to_be_enabled()  # nothing typed
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("")
    assert page.evaluate("App.nav.isDirty()") is False
    before = page.evaluate("history.length")
    cancel.click()
    _nav.expect_route(page, "agents")
    expect(_lists.agents_empty_state(page)).to_be_visible(timeout=8000)
    expect(page.locator(".editor-title")).to_have_count(0)
    _lists.expect_none_selected(page, "agents")
    if with_agent:
        expect(_lists.list_row(page, "agents", "Existing agent")).to_be_focused()
    else:
        expect(page.locator('[data-testid="agent-empty"]')).to_be_visible()
        expect(page.locator('[data-testid="new-agent-btn"]')).to_be_focused()
    assert page.evaluate("history.length") == before  # replaced, not pushed
    expect(page.locator("dialog[open]")).to_have_count(0)
    expect(page.locator(DIALOG)).to_have_count(0)


def test_create_form_cancel_stays_enabled_when_the_form_is_clean_again(
    app_with_provider: SeededApp, page: Page
) -> None:
    """An edit undone on the create form leaves it clean (Create disabled, no
    caption) but Cancel enabled: it abandons creation, dirty or not."""
    _nav.goto_settled(page, app_with_provider.base_url, "agents")
    _lists.agents_new(page)
    name = page.locator('[data-field="name"]')
    cancel = page.locator('[data-testid="cancel-agent-btn"]')
    unsaved = page.locator('[data-testid="editor-unsaved"]')
    name.fill("x")
    expect(unsaved).to_have_text("Unsaved changes")
    expect(cancel).to_be_enabled()
    name.fill("")
    expect(unsaved).to_have_text("")
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_disabled()
    expect(cancel).to_be_enabled()
    cancel.click()
    _nav.expect_route(page, "agents")
    expect(page.locator(".editor-title")).to_have_count(0, timeout=8000)
    expect(page.locator("dialog[open]")).to_have_count(0)


def test_cancel_on_a_clean_open_agent_stays_disabled(app_with_agent: SeededApp, page: Page) -> None:
    """Edit mode is unchanged: Cancel reverts, so it is disabled while the open
    agent is clean, enabled by an edit, and disabled again after the revert."""
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _open_editor(page, base, name)
    cancel = page.locator('[data-testid="cancel-agent-btn"]')
    expect(cancel).to_be_disabled()
    desc = page.locator('[data-field="description"]')
    original = desc.input_value()
    route = _nav.current_route(page)
    desc.fill("an edit")
    expect(cancel).to_be_enabled()
    cancel.click()
    expect(desc).to_have_value(original)
    expect(cancel).to_be_disabled()
    _nav.expect_route(page, route)  # reverted in place: the agent stays open


def test_names_that_look_like_the_create_segment_round_trip(
    app_with_provider: SeededApp, page: Page
) -> None:
    """`agents/~new` is create; `agents/%7Enew/general` is the agent named `~new`;
    `agents/new/general` is the agent named `new` (DD8 sentinel round trip)."""
    base = app_with_provider.base_url
    seed_mock_agent(base, app_with_provider.provider_id, name="new")
    seed_mock_agent(base, app_with_provider.provider_id, name="~new")

    _nav.goto_settled(page, base, "agents/new/general")
    expect(page.locator(".editor-title")).to_have_text("new", timeout=8000)
    assert page.evaluate("location.hash") == _nav.href("agents/new/general")
    _lists.expect_selected(page, "agents", "new")

    tilde_row = _lists.list_row(page, "agents", "~new")
    tilde = _nav.seg("~new")
    assert tilde == "%7Enew"
    assert tilde_row.get_attribute("href") == _nav.href(f"agents/{tilde}")
    _lists.open_item(page, "agents", "~new")
    expect(page.locator(".editor-title")).to_have_text("~new", timeout=8000)
    assert page.evaluate("location.hash") == _nav.href(f"agents/{tilde}/general")
    _lists.expect_selected(page, "agents", "~new")
    # A reload of the escaped name stays on the agent (never the create form).
    page.reload()
    expect(page.locator(".editor-title")).to_have_text("~new", timeout=10000)
    assert page.evaluate("location.hash") == _nav.href(f"agents/{tilde}/general")

    _nav.set_route(page, "agents/~new")
    expect(page.locator(".editor-title")).to_have_text("New Agent", timeout=8000)
    assert page.evaluate("App.areas.find((a) => a.id === 'studio')._createMode") is True


# ── AC5: the unsaved indicator ──────────────────────────────────────────────


def test_unsaved_indicator_follows_the_dirty_flag(app_with_agent: SeededApp, page: Page) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _open_editor(page, base, name)
    unsaved = page.locator('[data-testid="editor-unsaved"]')
    expect(unsaved).to_have_text("")  # never while clean
    expect(unsaved).to_have_attribute("role", "status")
    desc = page.locator('[data-field="description"]')

    # Edit -> shown; Save -> gone.
    desc.fill("first edit")
    expect(unsaved).to_have_text("Unsaved changes")
    node_mark = page.evaluate(
        "() => { const u = document.querySelector('[data-testid=\"editor-unsaved\"]');"
        " u.dataset.mark = '1'; return u.parentElement.firstElementChild === u; }"
    )
    assert node_mark is True  # the first child of .form-actions
    save = page.locator('[data-testid="save-agent-btn"]')
    save.click()
    expect(save).to_be_disabled(timeout=8000)
    expect(unsaved).to_have_text("")

    # Edit -> Cancel -> gone (the same span: toggled, never re-created).
    desc.fill("second edit")
    expect(unsaved).to_have_text("Unsaved changes")
    page.evaluate(
        "() => { document.querySelector('[data-testid=\"editor-unsaved\"]').dataset.mark = '2'; }"
    )
    page.locator('[data-testid="cancel-agent-btn"]').click()
    expect(unsaved).to_have_text("")

    # Edit -> leave via "New" -> Continue -> the create form starts clean.
    desc.fill("third edit")
    expect(unsaved).to_have_text("Unsaved changes")
    page.locator('[data-testid="new-agent-btn"]').click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _nav.expect_route(page, "agents/~new")
    expect(page.locator(".editor-title")).to_have_text("New Agent", timeout=8000)
    expect(unsaved).to_have_text("")
    # Create mode: shown once any field differs from the defaults.
    page.locator('[data-field="name"]').fill("x")
    expect(unsaved).to_have_text("Unsaved changes")


def test_unsaved_span_is_toggled_not_recreated(app_with_agent: SeededApp, page: Page) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _open_editor(page, base, name)
    page.evaluate(
        "() => { document.querySelector('[data-testid=\"editor-unsaved\"]').dataset.mark = 'k'; }"
    )
    desc = page.locator('[data-field="description"]')
    desc.fill("edit")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    desc.fill("")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("")
    assert (
        page.evaluate(
            "() => document.querySelector('[data-testid=\"editor-unsaved\"]').dataset.mark"
        )
        == "k"
    )


# ── AC6: delete ─────────────────────────────────────────────────────────────


def _delete_open_agent(page: Page) -> None:
    btn = page.locator('[data-testid="delete-agent-btn"]')
    expect(btn).to_be_visible(timeout=8000)
    btn.click()
    expect(btn).to_have_text("Confirm delete?")
    with page.expect_response(lambda r: "/api/agents/" in r.url and r.request.method == "DELETE"):
        btn.click()


def test_delete_lands_on_the_root_and_focuses_the_nearest_row(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    for n in ("a-agent", "b-agent", "c-agent"):
        seed_mock_agent(base, app_with_provider.provider_id, name=n)

    # Middle row: focus goes to the NEXT row.
    _open_editor(page, base, "b-agent")
    _delete_open_agent(page)
    _nav.expect_route(page, "agents")
    expect(page.locator('[data-testid="agent-select-empty"]')).to_be_visible(timeout=8000)
    expect(page.locator(ROWS)).to_have_count(2)
    expect(_lists.list_row(page, "agents", "b-agent")).to_have_count(0)
    expect(_lists.list_row(page, "agents", "c-agent")).to_be_focused()
    page.wait_for_function(
        "() => document.querySelector('[data-testid=\"route-announcer\"]').textContent === 'Agents'"
    )

    # Last row: focus goes to the PREVIOUS row.
    _lists.open_item(page, "agents", "c-agent")
    expect(page.locator(".editor-title")).to_have_text("c-agent", timeout=8000)
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_disabled(timeout=8000)
    _delete_open_agent(page)
    _nav.expect_route(page, "agents")
    expect(page.locator(ROWS)).to_have_count(1)
    expect(_lists.list_row(page, "agents", "a-agent")).to_be_focused()

    # The only row: focus goes to "New"; the zero-agents copy shows.
    _lists.open_item(page, "agents", "a-agent")
    expect(page.locator(".editor-title")).to_have_text("a-agent", timeout=8000)
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_disabled(timeout=8000)
    _delete_open_agent(page)
    _nav.expect_route(page, "agents")
    expect(page.locator(ROWS)).to_have_count(0)
    expect(page.locator('[data-testid="agent-empty"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="new-agent-btn"]')).to_be_focused()
