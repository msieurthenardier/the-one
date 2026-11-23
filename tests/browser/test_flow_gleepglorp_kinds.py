"""The GleepGlorp client kinds registry (M36 F4 L2, flight DD11).

``App.gleepglorpKinds`` holds one spec per proposal and fill kind; the drawer's fill applier, the
fill receipts, the proposal cards and ``App.approvals`` read it. Agent, rule and routine register
during script load (``areas/studio/agent-kinds.js``). Covers the registry and ``App.approvals``
over a stub id-targeted kind (the shape Legs 4 and 5 add), and a drawer fill whose kind has no
``fill`` spec.

Falls in the ``gleepglorp`` browser lane (an explicit entry in ``scripts/run-tests.sh``).
"""

from __future__ import annotations

from typing import Any

import pytest
from browser import _nav
from browser.test_flow_gleepglorp_fill import (
    _bworld,
    _deliver,
    _done,
    _drawer_receipt,
    _reason,
    _seed_b,
    _view,
    _wait_status,
)
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

_SCRIPT_ORDER_JS = """() => {
  const s = Array.from(document.scripts).map(e => e.getAttribute('src') || '');
  const at = (n) => s.findIndex(x => x.split('?')[0].endsWith(n));
  return {
    kinds: at('/js/gleepglorp-kinds.js'), approvals: at('/js/approvals.js'),
    frames: at('/areas/chat/window-frames.js'), agentKinds: at('/areas/studio/agent-kinds.js'),
    mcpKinds: at('/areas/studio/mcp-kinds.js'),
    providerKinds: at('/areas/studio/provider-kinds.js'),
    knowledgeKinds: at('/areas/studio/knowledge-kinds.js'),
    secretKinds: at('/areas/studio/secret-kinds.js'),
    agentsList: at('/areas/studio/agents-list.js')
  };
}"""

_REGISTRY_JS = """() => {
  const K = App.gleepglorpKinds;
  const out = {};
  out.unknown = K.get('no-such-kind');
  K.register('stub_target', {
    labels: { itemNoun: 'stub' }, store: 'stub-store',
    recordKey: (d) => (d.target_id ? { scope: 'target', id: d.target_id } : null)
  });
  out.names = K.names();
  out.same = K.get('stub_target') === K.get('stub_target') && !!K.get('stub_target');
  try { K.register('stub_target', {}); out.dupThrew = false; } catch (e) { out.dupThrew = true; }
  try { K.register('agent', {}); out.dupAgentThrew = false; }
  catch (e) { out.dupAgentThrew = true; }

  const events = [];
  document.addEventListener(App.approvals.CONFIG_CHANGED, (e) => events.push(e.detail));
  const invalidated = [];
  const realInvalidate = App.store.invalidate;
  App.store.invalidate = (n) => { invalidated.push(n); };
  try {
    out.unknownRecord = App.approvals.record(
      { kind: 'no-such-kind', agent: 'a', fields: ['x'], proposal_id: 9001 });
    out.noTarget = App.approvals.record({ kind: 'stub_target', fields: ['x'], proposal_id: 9002 });
    out.stubRecord = App.approvals.record({
      kind: 'stub_target', target_id: 't-1', fields: ['url', 'name'], session_id: 's1',
      proposal_id: 9003, at: '2026-01-02T10:00:00+00:00'
    });
    out.stubRepeat = App.approvals.record(
      { kind: 'stub_target', target_id: 't-1', fields: ['url'], proposal_id: 9003 });
    out.forTarget = App.approvals.forTarget('stub_target', 't-1');
    out.forTargetOther = App.approvals.forTarget('stub_target', 't-2');
    // For an agent kind, `agent` decides, whatever the target id (a rule's id).
    out.ruleRecord = App.approvals.record({
      kind: 'rule', agent: 'plain', target_id: 'rule-7', fields: [], proposal_id: 9004
    });
    out.forAgent = App.approvals.forAgent('plain');
    out.forTargetRule = App.approvals.forTarget('rule', 'rule-7');
    App.approvals.clear('plain');
    out.afterClear = App.approvals.forAgent('plain');
    out.targetAfterClear = App.approvals.forTarget('stub_target', 't-1');
    // The MCP server kind records under its target id; a create without one records nothing.
    out.mcpCreate = App.approvals.record(
      { kind: 'mcp_server', fields: ['name'], proposal_id: 9005 });
    out.mcpRecord = App.approvals.record({
      kind: 'mcp_server', target_id: 'srv-1', fields: ['url'], session_id: 's1',
      proposal_id: 9006, at: '2026-01-02T11:00:00+00:00'
    });
    out.mcpFor = App.approvals.forTarget('mcp_server', 'srv-1');
    // The provider kind records under its target id too, and invalidates `providers`.
    out.providerCreate = App.approvals.record(
      { kind: 'provider', fields: ['name'], proposal_id: 9007 });
    out.providerRecord = App.approvals.record({
      kind: 'provider', target_id: 'prov-1', fields: ['type'], session_id: 's1',
      proposal_id: 9008, at: '2026-01-02T12:00:00+00:00'
    });
    out.providerFor = App.approvals.forTarget('provider', 'prov-1');
  } finally {
    App.store.invalidate = realInvalidate;
  }
  out.invalidated = invalidated;
  out.events = events;
  return out;
}"""


def test_the_agent_kinds_register_during_script_load_before_any_socket_frame(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _nav.goto(page, base, "library")
    got = page.evaluate(
        "() => ({ names: App.gleepglorpKinds.names(),"
        " gg: ['get', 'peek', 'prime'].map(k => typeof App.gleepglorp[k]) })"
    )
    assert got["names"] == [
        "agent",
        "rule",
        "routine",
        "mcp_server",
        "provider",
        "knowledge_base",
        "secret",
    ]
    assert got["gg"] == ["function", "function", "function"]
    order = page.evaluate(_SCRIPT_ORDER_JS)
    assert -1 not in order.values()
    assert order["kinds"] < order["approvals"] < order["frames"]
    assert order["agentsList"] < order["agentKinds"] < order["mcpKinds"] < order["providerKinds"]
    assert order["providerKinds"] < order["knowledgeKinds"] < order["secretKinds"]
    # The agent, MCP server, provider, knowledge base and secret kinds are fillable; the labels
    # carry today's wording.
    shape = page.evaluate(
        "() => ['agent', 'rule', 'routine', 'mcp_server', 'provider', 'knowledge_base',"
        " 'secret'].map(n => {"
        " const k = App.gleepglorpKinds.get(n);"
        " return [n, !!k.fill, k.store, k.labels.editorUnavailable, k.labels.targetGone]; })"
    )
    assert shape == [
        [
            "agent",
            True,
            "agents",
            "The agent editor could not open.",
            "That agent no longer exists.",
        ],
        [
            "rule",
            False,
            "agents",
            "The agent editor could not open.",
            "That agent no longer exists.",
        ],
        [
            "routine",
            False,
            "agents",
            "The agent editor could not open.",
            "That agent no longer exists.",
        ],
        [
            "mcp_server",
            True,
            "mcp-sources",
            "The MCP server editor could not open.",
            "That MCP server no longer exists.",
        ],
        [
            "provider",
            True,
            "providers",
            "The model provider editor could not open.",
            "That model provider no longer exists.",
        ],
        [
            "knowledge_base",
            True,
            "knowledge-bases",
            "The knowledge base editor could not open.",
            "That knowledge base no longer exists.",
        ],
        [
            "secret",
            True,
            "secrets",
            "The secret editor could not open.",
            "That secret no longer exists.",
        ],
    ]


def test_the_registry_and_approvals_record_a_stub_id_targeted_kind(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _nav.goto(page, base, "library")
    out = page.evaluate(_REGISTRY_JS)

    assert out["unknown"] is None
    assert out["names"] == [
        "agent",
        "rule",
        "routine",
        "mcp_server",
        "provider",
        "knowledge_base",
        "secret",
        "stub_target",
    ]
    assert out["same"] is True
    assert out["dupThrew"] is True and out["dupAgentThrew"] is True
    # An unknown kind, or a stub detail with no target id, is not recorded.
    assert out["unknownRecord"] is False
    assert out["noTarget"] is False
    # The stub records under its target id, once per proposal id.
    assert out["stubRecord"] is True
    assert out["stubRepeat"] is False
    assert out["forTarget"] == {
        "url": {"at": "2026-01-02T10:00:00+00:00", "session_id": "s1"},
        "name": {"at": "2026-01-02T10:00:00+00:00", "session_id": "s1"},
    }
    assert out["forTargetOther"] == {}
    # An agent kind is recorded under `agent`, whatever its target id.
    assert out["ruleRecord"] is True
    assert list(out["forAgent"]) == ["rules"]
    assert out["forTargetRule"] == {}
    # `clear` empties the agent's record and leaves the target store alone.
    assert out["afterClear"] == {}
    assert list(out["targetAfterClear"]) == ["url", "name"]
    # Each recorded change invalidated its kind's store and emitted the event.
    assert out["mcpCreate"] is False and out["mcpRecord"] is True
    assert out["mcpFor"] == {"url": {"at": "2026-01-02T11:00:00+00:00", "session_id": "s1"}}
    assert out["providerCreate"] is False and out["providerRecord"] is True
    assert out["providerFor"] == {"type": {"at": "2026-01-02T12:00:00+00:00", "session_id": "s1"}}
    assert out["invalidated"] == ["stub-store", "agents", "mcp-sources", "providers"]
    stub_event, rule_event, mcp_event, provider_event = out["events"]
    assert mcp_event["kind"] == "mcp_server" and mcp_event["target_id"] == "srv-1"
    assert provider_event["kind"] == "provider" and provider_event["target_id"] == "prov-1"
    assert stub_event["kind"] == "stub_target" and stub_event["target_id"] == "t-1"
    assert "agent" not in stub_event
    assert stub_event["fields"] == ["url", "name"]
    assert rule_event["agent"] == "plain" and rule_event["target_id"] == "rule-7"
    # The agent editor's follow listener ignores an event without `agent`: nothing threw.
    assert errors == []


def test_a_fill_whose_kind_has_no_fill_spec_is_editor_unavailable_and_does_not_navigate(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _bworld(app_with_data_dir, page)
    route = _nav.current_route(page)
    fid = _seed_b(w, changes={"description": "Never written"})
    # A fake kind cannot be seeded (the server's view needs a registered kind), so take the
    # agent kind's fill spec away in the page and restore it in the `finally`.
    page.evaluate(
        "() => { window.__ggAgentFill = App.gleepglorpKinds.get('agent').fill;"
        " App.gleepglorpKinds.get('agent').fill = null; }"
    )
    try:
        _deliver(page, w, fid)
        done = _wait_status(page, w, fid, "not_filled")
        assert done["outcome"] == {"kept": [], "reason": "editor_unavailable"}
        assert _nav.current_route(page) == route
        _done(page)
        expect(_reason(page, fid)).to_have_text("The agent editor could not open.")
        expect(_drawer_receipt(page, fid)).to_have_count(1)
    finally:
        page.evaluate(
            "() => { App.gleepglorpKinds.get('agent').fill = window.__ggAgentFill;"
            " delete window.__ggAgentFill; }"
        )
    assert _view(w, fid)["status"] == "not_filled"
