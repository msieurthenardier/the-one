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


# Squawk 0130: a quoted ``'data-testid':`` key in an element-builder attrs object.
ATTRS_KEY_SNIPPET = """
var h = el('h1', {className: 'x', 'data-testid': 'root-heading', text: 'Library'});
var d = el('div', {"data-testid": 'start-page-literal'});
var p = el('div', {'data-testid': 'library-start-' + group.id});
"""

ATTRS_KEY_NEGATIVE_SNIPPET = """
var a = {data_testid: 'not-a-key'};
var b = {'data-testid-x': 'not-a-key-either'};
var c = el.getAttribute('data-testid');
var d = {'data-testid': someVar};
"""


def test_quoted_attrs_key_is_registry_visible(tmp_path) -> None:
    (literals, parametric, _), violations = _scan(tmp_path, "attrs", ATTRS_KEY_SNIPPET)
    assert set(literals) == {"root-heading", "start-page-literal"}
    assert set(parametric) == {"library-start-"}  # prefix only, never also a literal
    assert violations == []


def test_quoted_attrs_key_does_not_over_match(tmp_path) -> None:
    (literals, parametric, _), _ = _scan(tmp_path, "attrs-neg", ATTRS_KEY_NEGATIVE_SNIPPET)
    assert literals == {} and parametric == {}


def test_quoted_attrs_key_pattern_bites() -> None:
    """The new patterns are what finds the form: the pre-0130 patterns miss it."""
    from tests import _ui_guard_helpers as h

    old = [h._ATTR_LITERAL, h._SETATTR_LITERAL, h._PROP_LITERAL]
    assert not any(r.findall(ATTRS_KEY_SNIPPET) for r in old)
    assert h._KEY_LITERAL.findall(ATTRS_KEY_SNIPPET)
