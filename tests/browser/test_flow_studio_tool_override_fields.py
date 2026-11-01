# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""Contract tests for the agent-mode fields of ``App.toolConfigFields`` (M31 F2 L08b, flight
DD3/DD8; retargeted from ``App.studio.toolOverrideFields`` in M31 F4 L05c).

The renderer builds one per-agent tool-override field as library DOM. Every test
runs in Chromium and WebKit through ``engine_page`` and reads the control back with
``readValue`` (the function ``collectFormData`` uses), so the
attributes and value shapes the Save path depends on are what is asserted.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import STATIC_DIR, load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

_RENDER = """([name, prop, value, ctx]) => {
  window.__fired = 0;
  ctx = Object.assign({mode: 'agent', toolName: 'http_request', onChange: () => { window.__fired++; }}, ctx || {});
  const r = App.toolConfigFields.render(name, prop, value, ctx);
  if (!r) return null;
  document.getElementById('harness-root').appendChild(r.el);
  window.__r = r;
  return true;
}"""

_READ = """() => {
  const c = window.__r.control;
  return {
    value: App.toolConfigFields.readValue(c),
    tool: c.dataset.toolOverrideTool, field: c.dataset.toolOverrideField,
    type: c.dataset.fieldType || null, marker: c.dataset.marker || null,
    tag: c.tagName, inputType: c.type || null, max: c.getAttribute('max'), min: c.getAttribute('min'),
    wrapperHasAttrs: window.__r.el.hasAttribute('data-tool-override-field')
  };
}"""


def _setup(page: Page) -> None:
    load_harness(page)
    page.add_script_tag(path=str(STATIC_DIR / "js" / "areas" / "shared" / "tool-config-fields.js"))
    # Agent mode decorates each field with its inherited/own state (sortie 07).
    page.add_script_tag(path=str(STATIC_DIR / "js" / "areas" / "shared" / "tool-override-state.js"))


def _render(page: Page, name: str, prop: dict, value, ctx: dict | None = None):
    return page.evaluate(_RENDER, [name, prop, value, ctx or {}])


def test_boolean_is_a_checkbox_with_the_markers_on_the_control(engine_page: Page) -> None:
    _setup(engine_page)
    assert _render(engine_page, "follow", {"type": "boolean", "title": "Follow"}, True)
    out = engine_page.evaluate(_READ)
    assert (out["tag"], out["inputType"], out["value"]) == ("INPUT", "checkbox", True)
    assert (out["tool"], out["field"]) == ("http_request", "follow")
    assert out["wrapperHasAttrs"] is False
    engine_page.locator("#harness-root input[type=checkbox]").uncheck()
    assert engine_page.evaluate(_READ)["value"] is False
    assert engine_page.evaluate("() => window.__fired") >= 1


_DESCRIBED = """() => {
  const c = window.__r.control;
  return (c.getAttribute('aria-describedby') || '').split(/\\s+/).filter(Boolean)
    .map((id) => { const n = document.getElementById(id); return [id, n ? n.textContent : null]; });
}"""


def test_boolean_state_line_and_note_are_in_aria_describedby(engine_page: Page) -> None:
    _setup(engine_page)
    assert _render(engine_page, "follow", {"type": "boolean", "title": "Follow"}, True)
    described = engine_page.evaluate(_DESCRIBED)
    assert described and all(t is not None for _id, t in described)
    assert any("Inherited from Settings" in t for _id, t in described)
    engine_page.evaluate("() => window.__r.setNote('Paths are limited')")
    described = engine_page.evaluate(_DESCRIBED)
    assert all(t is not None for _id, t in described)
    assert any(t == "Paths are limited" for _id, t in described)
    # An error rewrites the attribute wholesale; the state line and note stay.
    engine_page.evaluate("() => window.__r.setError('Nope')")
    described = engine_page.evaluate(_DESCRIBED)
    assert all(t is not None for _id, t in described)
    assert {"Nope", "Paths are limited"} <= {t for _id, t in described}
    assert any("Inherited from Settings" in t for _id, t in described)
    # The note leaving takes its id with it.
    engine_page.evaluate("() => window.__r.setNote(null)")
    described = engine_page.evaluate(_DESCRIBED)
    assert all(t is not None for _id, t in described)
    assert not any(t == "Paths are limited" for _id, t in described)


def test_narrow_integer_uses_the_operator_value_as_max(engine_page: Page) -> None:
    _setup(engine_page)
    prop = {"type": "integer", "x_marker": "Narrow", "minimum": 1, "maximum": 3600}
    assert _render(engine_page, "timeout", prop, 60, {"operatorValue": 60})
    out = engine_page.evaluate(_READ)
    # A text input with inputmode numeric (a type=number input reads "12abc" as '').
    assert (out["inputType"], out["min"], out["max"], out["value"], out["type"]) == (
        "text",
        "1",
        "60",
        60,
        "integer",
    )
    # Without an operator number the schema maximum is the ceiling.
    engine_page.evaluate("() => document.getElementById('harness-root').replaceChildren()")
    assert _render(engine_page, "timeout", prop, 5, {"operatorValue": None})
    assert engine_page.evaluate(_READ)["max"] == "3600"


def test_integer_dropdown_is_filtered_to_the_operator_value_with_a_custom_option(
    engine_page: Page,
) -> None:
    _setup(engine_page)
    prop = {
        "type": "integer",
        "x_marker": "Narrow",
        "ui_hint": "dropdown",
        "ui_choices": [{"value": v, "label": f"{v} s"} for v in (10, 30, 60, 120)],
    }
    assert _render(engine_page, "t", prop, 30, {"operatorValue": 60})
    out = engine_page.evaluate(
        "() => ({v: window.__r.control.value, opts: [...window.__r.control.options].map((o) => o.value)})"
    )
    assert out == {"v": "30", "opts": ["10", "30", "60"]}  # 120 > 60 is dropped
    assert engine_page.evaluate(_READ)["value"] == 30
    # An unknown current value stays selectable as "(custom)".
    engine_page.evaluate("() => document.getElementById('harness-root').replaceChildren()")
    assert _render(engine_page, "t", prop, 45, {"operatorValue": 60})
    opts = engine_page.evaluate(
        "() => [...window.__r.control.options].map((o) => [o.value, o.textContent, o.selected])"
    )
    assert ["45", "45 (custom)", True] in opts


def test_string_dropdown_and_custom_option(engine_page: Page) -> None:
    _setup(engine_page)
    prop = {
        "type": "string",
        "x_marker": "Substitute",
        "ui_hint": "dropdown",
        "ui_choices": [
            {"value": "brave", "label": "Brave"},
            {"value": "tavily", "label": "Tavily"},
        ],
    }
    assert _render(engine_page, "search_backend", prop, "tavily")
    out = engine_page.evaluate(_READ)
    assert (out["tag"], out["value"], out["type"]) == ("SELECT", "tavily", "string")
    engine_page.evaluate("() => document.getElementById('harness-root').replaceChildren()")
    assert _render(engine_page, "search_backend", prop, "legacy")
    opts = engine_page.evaluate(
        "() => [...window.__r.control.options].map((o) => [o.value, o.textContent, o.selected])"
    )
    assert ["legacy", "legacy (custom)", True] in opts


def test_string_and_password_and_unknown_inputs(engine_page: Page) -> None:
    _setup(engine_page)
    assert _render(engine_page, "user_agent", {"type": "string", "x_marker": "Substitute"}, "bot/1")
    out = engine_page.evaluate(_READ)
    assert (out["inputType"], out["value"], out["type"]) == ("text", "bot/1", "string")

    engine_page.evaluate("() => document.getElementById('harness-root').replaceChildren()")
    assert _render(
        engine_page,
        "api_key",
        {"type": "string", "x_marker": "Substitute", "ui_hint": "password"},
        "s3cret",
    )
    out = engine_page.evaluate(_READ)
    assert (out["inputType"], out["value"], out["type"]) == ("password", "s3cret", "string")
    # The secret is only ever the input's value property, never an attribute.
    assert engine_page.evaluate("() => window.__r.control.getAttribute('value')") is None, (
        "the secret must not be written to the value attribute"
    )
    assert engine_page.locator("#harness-root .api-key-eye").count() == 1

    engine_page.evaluate("() => document.getElementById('harness-root').replaceChildren()")
    assert _render(engine_page, "weird", {"type": "object", "x_marker": "Narrow"}, {"a": 1})
    out = engine_page.evaluate(_READ)
    assert (out["type"], out["value"]) == ("unknown", {"a": 1})


def test_unmarked_non_boolean_fields_are_hidden(engine_page: Page) -> None:
    _setup(engine_page)
    assert _render(engine_page, "redirect_cap", {"type": "integer"}, 5) is None
    assert _render(engine_page, "x", {"type": "array", "items": {"type": "string"}}, []) is None
    assert engine_page.evaluate("() => App.toolConfigFields.allowed({type: 'boolean'})") is True


def test_narrow_superset_locks_operator_chips_and_sends_the_union(engine_page: Page) -> None:
    _setup(engine_page)
    prop = {
        "type": "array",
        "x_marker": "NarrowSuperset",
        "items": {"type": "string"},
        "title": "Denylist",
    }
    assert _render(
        engine_page,
        "command_denylist",
        prop,
        ["rm", "extra"],
        {"operatorValue": ["rm", "dd"], "toolName": "shell"},
    )
    out = engine_page.evaluate(_READ)
    # Operator items lead (locked); the agent's addition follows; the union is what is read back.
    assert out["value"] == ["rm", "dd", "extra"]
    assert (out["type"], out["marker"], out["tool"]) == ("array", "NarrowSuperset", "shell")
    chips = engine_page.evaluate(
        "() => [...window.__r.control.querySelectorAll('.chip')].map((c) => [c.dataset.locked || null, c.querySelectorAll('button').length])"
    )
    assert chips == [["true", 0], ["true", 0], [None, 1]]
    # A locked chip cannot be removed: Backspace on the empty input removes only the editable one.
    engine_page.locator("#harness-root .chip-list-input").press("Backspace")
    assert engine_page.evaluate(_READ)["value"] == ["rm", "dd"]
    engine_page.locator("#harness-root .chip-list-input").press("Backspace")
    assert engine_page.evaluate(_READ)["value"] == ["rm", "dd"]


def test_narrow_any_when_empty_host_allowlist_is_agent_overridable(engine_page: Page) -> None:
    """Sortie 07 DD4: the server marks `host_allowlist` `NarrowAnyWhenEmpty`; the
    client must still render, read and save it (an unlisted marker is flagged
    dead and dropped on Save)."""
    _setup(engine_page)
    prop = {
        "type": "array",
        "x_marker": "NarrowAnyWhenEmpty",
        "items": {"type": "string"},
        "title": "Allowed hosts",
    }
    assert engine_page.evaluate("(p) => App.toolConfigFields.allowed(p)", prop) is True
    assert _render(engine_page, "host_allowlist", prop, ["a.com"], {"operatorValue": []})
    out = engine_page.evaluate(_READ)
    assert (out["value"], out["field"]) == (["a.com"], "host_allowlist")


@pytest.mark.parametrize(
    "marker", ["Narrow", "NarrowAnyWhenEmpty", "NarrowPrefix", "NarrowSuperset"]
)
def test_array_chip_rules_per_marker(engine_page: Page, marker: str) -> None:
    """Each array marker's client rule, exactly as the string path had it.

    Narrow (subset) and NarrowPrefix are checked by the SERVER (a 422 on Save), so the
    client accepts any non-empty, non-duplicate entry; NarrowSuperset additionally locks
    the operator's items. Empty entries and duplicates are rejected for every marker.
    """
    _setup(engine_page)
    prop = {"type": "array", "x_marker": marker, "items": {"type": "string"}}
    operator = ["a"] if marker == "NarrowSuperset" else ["a", "b"]
    assert _render(
        engine_page,
        "hosts",
        prop,
        None if marker != "Narrow" else ["a"],
        {"operatorValue": operator},
    )
    inp = engine_page.locator("#harness-root .chip-list-input")
    before = engine_page.evaluate(_READ)["value"]
    # Accept: a value outside the operator's set is taken (the server decides).
    inp.fill("outside")
    inp.press("Enter")
    assert "outside" in engine_page.evaluate(_READ)["value"]
    # Reject: a duplicate adds nothing.
    inp.fill("outside")
    inp.press("Enter")
    assert engine_page.evaluate(_READ)["value"].count("outside") == 1
    # Reject: an empty entry adds nothing.
    n = len(engine_page.evaluate(_READ)["value"])
    inp.press("Enter")
    assert len(engine_page.evaluate(_READ)["value"]) == n
    assert before is not None
    assert engine_page.evaluate("() => window.__fired") >= 1


def test_field_wrapper_has_label_and_info_toggletip(engine_page: Page) -> None:
    _setup(engine_page)
    prop = {
        "type": "string",
        "x_marker": "Substitute",
        "title": "User agent",
        "description": "Sent on every request.",
    }
    assert _render(engine_page, "user_agent", prop, "")
    wrapper = engine_page.locator("#harness-root .field-group")
    assert wrapper.locator("label").inner_text() == "User agent"
    assert wrapper.locator("button.field-info-icon").count() == 1
    # The wrapper keeps the field name for error rendering; the markers stay on the control.
    assert wrapper.get_attribute("data-field-name") == "user_agent"
