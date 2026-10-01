"""Criterion 1 evidence for the control-library mechanism decision (M25 F1 L2).

Representative call-site snippets for each mechanism are written to ``tmp_path``
and run through ``extract_testids``: does the registry guard see every id a
call site supplies, with no manual exception? Snippets only - no component code.
"""

from __future__ import annotations

from tests._ui_guard_helpers import extract_testids, find_testid_value_violations

FACTORY_SNIPPET = """
var pane = App.ui.listPane({
  title: 'Agents',
  testid: 'agents-pane',
  filter: {label: 'Filter agents', testid: 'agents-filter'},
  items: agents.map(function (a) {
    return {id: a.name, label: a.name, href: '#studio/agents/' + a.name,
            testid: 'agents-row-' + a.name};
  })
});
var add = App.ui.button({label: 'New agent', testid: 'agents-new-btn'});
"""

# A light-DOM custom element's natural test id forms: a host attribute written
# in an HTML string, a host attribute set from script, and per-item properties
# on the element's items array (the same property the factory takes).
CUSTOM_ELEMENT_SNIPPET = """
host.appendChild(document.createRange().createContextualFragment(
  '<ui-list-pane data-testid="agents-pane"></ui-list-pane>'));
var el = document.createElement('ui-list-pane');
el.setAttribute('data-testid', 'agents-pane-b');
el.items = agents.map(function (a) {
  return {id: a.name, label: a.name, testid: 'agents-row-' + a.name};
});
"""


def _scan(tmp_path, name: str, body: str):
    d = tmp_path / name
    d.mkdir()
    (d / "snippet.js").write_text(body)
    return extract_testids(d), find_testid_value_violations(d)


def test_factory_call_site_ids_are_all_registry_visible(tmp_path) -> None:
    (literals, parametric, _), violations = _scan(tmp_path, "factory", FACTORY_SNIPPET)
    assert set(literals) == {"agents-pane", "agents-filter", "agents-new-btn"}
    assert set(parametric) == {"agents-row-"}  # per-item rows: one parametric family, no literal
    assert violations == []  # nothing needs a manual exception


def test_custom_element_call_site_ids_are_all_registry_visible(tmp_path) -> None:
    (literals, parametric, _), violations = _scan(tmp_path, "ce", CUSTOM_ELEMENT_SNIPPET)
    # Both mechanisms are visible: the HTML-string attribute form and the
    # per-item property form use patterns the extractor already has. The host
    # attribute set from script is visible only because it is a literal
    # setAttribute call; an attribute computed elsewhere would not be.
    assert {"agents-pane", "agents-pane-b"} <= set(literals)
    assert set(parametric) == {"agents-row-"}
    assert violations == []
