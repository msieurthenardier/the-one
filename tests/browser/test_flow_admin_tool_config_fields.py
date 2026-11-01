# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""Contract tests for ``App.toolConfigFields`` (M31 F4 L05b, flight DD13).

The shared tool-settings field module renders one Config field for the Settings
tool editor (admin mode) and the agent Tools tab (agent mode). It is tested on a
harness page in Chromium and WebKit through ``engine_page``: the DOM hooks, every
field kind, ``setError``, ``setVisible``, ``showIf``, ``value()`` and the number
parsing rules. Nothing consumes admin mode yet (leg 07a); agent mode moves in 05c.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import STATIC_DIR, load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

_RENDER = """([name, prop, value, opts]) => {
  window.__fired = window.__fired || 0;
  opts = Object.assign({onChange: () => { window.__fired++; }}, opts || {});
  const h = App.toolConfigFields.render(name, prop, value, opts);
  if (!h) return null;
  document.getElementById('harness-root').appendChild(h.el);
  window.__h = window.__h || {};
  window.__h[name] = h;
  window.__last = h;
  return true;
}"""

_RESET = "() => { document.getElementById('harness-root').replaceChildren(); window.__h = {}; window.__fired = 0; }"


def _setup(page: Page) -> None:
    load_harness(page)
    page.add_script_tag(path=str(STATIC_DIR / "js" / "areas" / "shared" / "tool-config-fields.js"))
    # Agent mode decorates each field with its inherited/own state (sortie 07).
    page.add_script_tag(path=str(STATIC_DIR / "js" / "areas" / "shared" / "tool-override-state.js"))


def _render(page: Page, name: str, prop: dict, value, opts: dict | None = None):
    return page.evaluate(_RENDER, [name, prop, value, opts or {}])


def _admin(page: Page, name: str, prop: dict, value):
    assert _render(page, name, prop, value, {"mode": "admin"})


def _agent(page: Page, name: str, prop: dict, value, **opts):
    assert _render(page, name, prop, value, {"mode": "agent", "toolName": "http_request", **opts})


def _info(page: Page) -> dict:
    return page.evaluate(
        """() => {
          const h = window.__last, c = h.control;
          return {
            value: h.value(), tag: c.tagName, inputType: c.type || null,
            id: c.id || null, dataField: c.dataset.field || null,
            tool: c.dataset.toolOverrideTool || null, toolField: c.dataset.toolOverrideField || null,
            fieldType: c.dataset.fieldType || null, marker: c.dataset.marker || null,
            rowName: h.el.getAttribute('data-field-name'),
            rowAdmin: h.el.classList.contains('tools-editor-field'),
            rowAgent: h.el.classList.contains('tool-override-field'),
            rowHasOverrideAttr: h.el.hasAttribute('data-tool-override-field'),
            inputmode: c.getAttribute('inputmode'), max: c.getAttribute('max'), min: c.getAttribute('min'),
            short: c.classList.contains('ui-input--short')
          };
        }"""
    )


# ── admin mode: hooks and every field kind ──────────────────────────────


def test_admin_boolean_is_an_inline_labelled_checkbox_with_the_hooks(engine_page: Page) -> None:
    _setup(engine_page)
    _admin(
        engine_page,
        "allow_binary_files",
        {"type": "boolean", "title": "Allow binary files", "description": "Binary reads."},
        True,
    )
    out = _info(engine_page)
    assert (out["tag"], out["inputType"], out["value"]) == ("INPUT", "checkbox", True)
    assert out["id"] == "tef-allow_binary_files"
    assert out["dataField"] == "allow_binary_files"
    assert out["fieldType"] is None
    assert (out["rowName"], out["rowAdmin"], out["rowAgent"]) == ("allow_binary_files", True, False)
    # The label sits inline with the input (one label wrapping both), not stacked in a field group.
    assert engine_page.locator("#harness-root .field-group").count() == 0
    label = engine_page.locator("#harness-root label")
    assert label.inner_text().strip() == "Allow binary files"
    assert label.locator("input").count() == 1
    assert engine_page.locator("#harness-root button.field-info-icon").count() == 1
    engine_page.locator("#harness-root input[type=checkbox]").uncheck()
    assert engine_page.evaluate("() => window.__last.value()") is False
    assert engine_page.evaluate("() => window.__fired") >= 1
    engine_page.evaluate("() => window.__last.setValue(true)")
    assert engine_page.evaluate("() => window.__last.value()") is True


def test_admin_integer_dropdown_hooks_custom_label_and_set_value(engine_page: Page) -> None:
    _setup(engine_page)
    prop = {
        "type": "integer",
        "x_marker": "Narrow",
        "ui_hint": "dropdown",
        "title": "Maximum read size",
        "ui_choices": [
            {"value": 1_048_576, "label": "1MB (default)"},
            {"value": 5_242_880, "label": "5MB"},
        ],
    }
    # Admin mode never filters the choices (no operator value).
    _admin(engine_page, "read_size_cap_bytes", prop, 4_194_304)
    out = _info(engine_page)
    assert (out["tag"], out["value"], out["fieldType"]) == ("SELECT", 4_194_304, "integer")
    assert (out["id"], out["dataField"]) == ("tef-read_size_cap_bytes", "read_size_cap_bytes")
    opts = engine_page.evaluate(
        "() => [...window.__last.control.options].map((o) => [o.value, o.textContent, o.selected])"
    )
    assert ["4194304", "4MB (custom)", True] in opts
    assert len(opts) == 3
    engine_page.evaluate("() => window.__last.setValue(5242880)")
    assert engine_page.evaluate("() => window.__last.value()") == 5_242_880
    engine_page.evaluate("() => window.__last.setValue(1500000)")
    opts = engine_page.evaluate(
        "() => [...window.__last.control.options].map((o) => [o.value, o.textContent])"
    )
    assert ["1500000", "1500000 B (custom)"] in opts


@pytest.mark.parametrize(
    ("name", "value", "label"),
    [
        ("read_size_cap_bytes", 4_194_304, "4MB (custom)"),
        ("output_cap_bytes", 300_000 - 300_000 % 1024, "292KB (custom)"),
        ("output_cap_bytes", 1_500_000, "1500000 B (custom)"),
        ("timeout_seconds_default", 45, "45s (custom)"),
        ("timeout_seconds_max", 7200, "2h (custom)"),
        ("timeout_seconds_max", 150, "150s (custom)"),
        ("pty_session_idle_ttl_seconds", 600, "10m (custom)"),
        ("max_concurrent_sessions", 7, "7 (custom)"),
    ],
)
def test_custom_preset_values_are_humanised_from_the_field_name_unit(
    engine_page: Page, name: str, value: int, label: str
) -> None:
    _setup(engine_page)
    prop = {
        "type": "integer",
        "ui_hint": "dropdown",
        "ui_choices": [{"value": 1, "label": "one"}],
    }
    _admin(engine_page, name, prop, value)
    opts = engine_page.evaluate(
        "() => [...window.__last.control.options].map((o) => [o.textContent, o.selected])"
    )
    assert [label, True] in opts


def test_admin_integer_is_a_short_numeric_text_input_and_parses_per_the_contract(
    engine_page: Page,
) -> None:
    _setup(engine_page)
    _admin(
        engine_page,
        "redirect_cap",
        {"type": "integer", "minimum": 0, "maximum": 20, "title": "Redirect limit"},
        5,
    )
    out = _info(engine_page)
    assert (out["tag"], out["inputType"], out["inputmode"]) == ("INPUT", "text", "numeric")
    assert (out["short"], out["min"], out["max"], out["value"]) == (True, "0", "20", 5)
    assert (out["id"], out["dataField"], out["fieldType"]) == (
        "tef-redirect_cap",
        "redirect_cap",
        "integer",
    )
    inp = engine_page.locator("#harness-root input")
    for typed, expected in [
        ("12", 12),
        ("", ""),
        ("  7 ", 7),
        ("1.5", "1.5"),
        ("12abc", "12abc"),
        ("-3", -3),
    ]:
        inp.fill(typed)
        assert engine_page.evaluate("() => window.__last.value()") == expected, typed
    # Admin mode shows no client error: the tools PUT's 422 lands on the field (leg 07a).
    inp.fill("12abc")
    assert engine_page.evaluate("() => window.__last.validate()") is None
    assert engine_page.locator("#harness-root .field-error").count() == 0
    engine_page.evaluate("() => window.__last.setValue(9)")
    assert engine_page.evaluate("() => window.__last.value()") == 9


def test_admin_string_kinds(engine_page: Page) -> None:
    _setup(engine_page)
    dropdown = {
        "type": "string",
        "ui_hint": "dropdown",
        "ui_choices": [
            {"value": "duckduckgo", "label": "DuckDuckGo"},
            {"value": "brave", "label": "Brave"},
        ],
    }
    _admin(engine_page, "search_backend", dropdown, "brave")
    out = _info(engine_page)
    assert (out["tag"], out["value"], out["fieldType"], out["id"]) == (
        "SELECT",
        "brave",
        "string",
        "tef-search_backend",
    )
    engine_page.evaluate(_RESET)
    _admin(engine_page, "default_user_agent", {"type": "string"}, "bot/1")
    out = _info(engine_page)
    assert (out["inputType"], out["value"], out["fieldType"], out["dataField"]) == (
        "text",
        "bot/1",
        "string",
        "default_user_agent",
    )
    engine_page.evaluate(_RESET)
    _admin(engine_page, "brave_api_key", {"type": "string", "ui_hint": "password"}, "s3cret")
    out = _info(engine_page)
    assert (out["inputType"], out["value"], out["id"]) == (
        "password",
        "s3cret",
        "tef-brave_api_key",
    )
    assert engine_page.evaluate("() => window.__last.control.getAttribute('value')") is None
    assert engine_page.locator("#harness-root .api-key-eye").count() == 1
    engine_page.evaluate(_RESET)
    _admin(engine_page, "weird", {"type": "object"}, {"a": 1})
    out = _info(engine_page)
    assert (out["fieldType"], out["value"]) == ("unknown", {"a": 1})


def test_admin_array_is_a_chip_list_with_the_hooks_on_root_and_input(engine_page: Page) -> None:
    _setup(engine_page)
    _admin(
        engine_page,
        "host_allowlist",
        {
            "type": "array",
            "x_marker": "Narrow",
            "title": "Allowed hosts",
            "items": {"type": "string"},
        },
        ["a.example", "b.example"],
    )
    out = _info(engine_page)
    assert out["value"] == ["a.example", "b.example"]
    assert (out["dataField"], out["fieldType"], out["marker"]) == (
        "host_allowlist",
        "array",
        "Narrow",
    )
    assert out["rowName"] == "host_allowlist" and out["rowAdmin"] is True
    # The id is on the inner input, and the label's for-target points at it.
    assert (
        engine_page.locator("#tef-host_allowlist")
        .evaluate("(e) => e.className")
        .find("chip-list-input")
        >= 0
    )
    assert engine_page.locator("#harness-root label").get_attribute("for") == "tef-host_allowlist"
    inp = engine_page.locator("#tef-host_allowlist")
    inp.fill("c.example")
    inp.press("Enter")
    assert engine_page.evaluate("() => window.__last.value()") == [
        "a.example",
        "b.example",
        "c.example",
    ]
    engine_page.evaluate("() => window.__last.setValue(['z'])")
    assert engine_page.evaluate("() => window.__last.value()") == ["z"]
    # No marker -> no data-marker attribute.
    engine_page.evaluate(_RESET)
    _admin(engine_page, "extra", {"type": "array", "items": {"type": "string"}}, [])
    assert _info(engine_page)["marker"] is None
    assert engine_page.evaluate("() => window.__last.control.hasAttribute('data-marker')") is False


def test_admin_renders_unmarked_fields(engine_page: Page) -> None:
    _setup(engine_page)
    assert _render(engine_page, "redirect_cap", {"type": "integer"}, 5, {"mode": "admin"})
    assert _render(engine_page, "mode_default", {"type": "integer"}, 5)  # no mode -> admin


# ── setError / setVisible ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("prop", "value"),
    [
        ({"type": "integer", "title": "N", "description": "d"}, 5),
        ({"type": "string", "title": "S"}, "x"),
        ({"type": "array", "title": "A", "items": {"type": "string"}}, ["a"]),
        ({"type": "boolean", "title": "B"}, False),
        (
            {
                "type": "integer",
                "ui_hint": "dropdown",
                "ui_choices": [{"value": 1, "label": "one"}],
                "title": "D",
            },
            1,
        ),
    ],
)
def test_set_error_wires_the_message_to_the_control(engine_page: Page, prop: dict, value) -> None:
    _setup(engine_page)
    _admin(engine_page, "f", prop, value)
    engine_page.evaluate("() => window.__last.setError('Value is wrong')")
    info = engine_page.evaluate(
        """() => {
          const h = window.__last;
          // The control the error belongs to: a chip list's input, else the control.
          const target = h.control.classList.contains('chip-list-editor')
            ? h.control.querySelector('input') : h.control;
          const err = h.el.querySelector('.field-error, .ui-status');
          return {
            invalid: target.getAttribute('aria-invalid'),
            text: err && err.textContent,
            role: err && err.getAttribute('role'),
            described: (target.getAttribute('aria-describedby') || '').split(' ').includes(err && err.id)
          };
        }"""
    )
    assert info == {"invalid": "true", "text": "Value is wrong", "role": "alert", "described": True}
    engine_page.evaluate("() => window.__last.setError(null)")
    assert engine_page.locator("#harness-root .field-error, #harness-root .ui-status").count() == 0
    cleared = engine_page.evaluate(
        """() => {
          const h = window.__last;
          const target = h.control.classList.contains('chip-list-editor')
            ? h.control.querySelector('input') : h.control;
          return target.hasAttribute('aria-invalid');
        }"""
    )
    assert cleared is False


def test_set_visible_hides_the_row_but_keeps_the_value(engine_page: Page) -> None:
    _setup(engine_page)
    _admin(engine_page, "tavily_api_key", {"type": "string", "ui_hint": "password"}, "k")
    engine_page.evaluate("() => window.__last.setVisible(false)")
    row = engine_page.locator("#harness-root .tools-editor-field")
    assert row.get_attribute("aria-hidden") == "true"
    assert not row.is_visible()
    assert engine_page.evaluate("() => window.__last.value()") == "k"
    engine_page.evaluate("() => window.__last.setVisible(true)")
    assert row.get_attribute("aria-hidden") is None
    assert row.is_visible()


# ── showIf ────────────────────────────────────────────────────────────────

_ENGINE_PROPS = {
    "search_backend": {
        "type": "string",
        "ui_hint": "dropdown",
        "ui_choices": [
            {"value": "duckduckgo", "label": "DuckDuckGo"},
            {"value": "searxng", "label": "SearXNG"},
            {"value": "brave", "label": "Brave"},
        ],
    },
    "searxng_base_url": {"type": "string", "show_if": {"search_backend": "searxng"}},
    "brave_api_key": {
        "type": "string",
        "ui_hint": "password",
        "show_if": {"search_backend": "brave"},
    },
}


def _render_engine_form(page: Page, drop: tuple[str, ...] = ()) -> None:
    _setup(page)
    for name, prop in _ENGINE_PROPS.items():
        if name in drop:
            continue
        _admin(page, name, prop, "duckduckgo" if name == "search_backend" else "")


def test_show_if_toggles_rows_with_the_controlling_field(engine_page: Page) -> None:
    _render_engine_form(engine_page)
    engine_page.evaluate(
        "(props) => { window.__sif = App.toolConfigFields.showIf(props, window.__h); }",
        _ENGINE_PROPS,
    )
    vis = lambda n: engine_page.evaluate(  # noqa: E731
        "(n) => !window.__h[n].el.classList.contains('is-hidden')", n
    )
    assert vis("search_backend") and not vis("searxng_base_url") and not vis("brave_api_key")
    engine_page.locator("#tef-search_backend").select_option("searxng")
    assert vis("searxng_base_url") and not vis("brave_api_key")
    engine_page.locator("#tef-search_backend").select_option("brave")
    assert not vis("searxng_base_url") and vis("brave_api_key")
    # A hidden row is still read.
    engine_page.evaluate("() => window.__h.searxng_base_url.setValue('https://x')")
    assert engine_page.evaluate("() => window.__h.searxng_base_url.value()") == "https://x"
    # destroy() stops following the controlling field.
    engine_page.evaluate("() => window.__sif.destroy()")
    engine_page.locator("#tef-search_backend").select_option("searxng")
    assert not vis("searxng_base_url")


def test_show_if_with_an_absent_controlling_field_leaves_the_row_shown(engine_page: Page) -> None:
    # config_fields hid search_backend: its handle does not exist, so the condition is absent.
    _render_engine_form(engine_page, drop=("search_backend",))
    engine_page.evaluate(
        "(props) => { window.__sif = App.toolConfigFields.showIf(props, window.__h); }",
        _ENGINE_PROPS,
    )
    for name in ("searxng_base_url", "brave_api_key"):
        assert (
            engine_page.evaluate("(n) => window.__h[n].el.classList.contains('is-hidden')", name)
            is False
        )


# ── agent mode ────────────────────────────────────────────────────────────


def test_agent_mode_puts_the_override_hooks_on_the_control_not_the_row(engine_page: Page) -> None:
    _setup(engine_page)
    _agent(
        engine_page,
        "timeout_seconds_default",
        {"type": "integer", "x_marker": "Narrow", "minimum": 1, "maximum": 3600},
        60,
        operatorValue=60,
    )
    out = _info(engine_page)
    assert (out["tool"], out["toolField"], out["fieldType"]) == (
        "http_request",
        "timeout_seconds_default",
        "integer",
    )
    assert out["dataField"] is None and out["id"] != "tef-timeout_seconds_default"
    assert (out["rowName"], out["rowAgent"], out["rowAdmin"], out["rowHasOverrideAttr"]) == (
        "timeout_seconds_default",
        True,
        False,
        False,
    )
    assert (out["inputmode"], out["short"], out["min"], out["max"], out["value"]) == (
        "numeric",
        False,
        "1",
        "60",
        60,
    )


def test_agent_mode_hides_unmarked_fields_and_admin_does_not(engine_page: Page) -> None:
    _setup(engine_page)
    assert (
        _render(
            engine_page, "redirect_cap", {"type": "integer"}, 5, {"mode": "agent", "toolName": "t"}
        )
        is None
    )
    assert (
        _render(
            engine_page,
            "x",
            {"type": "array", "items": {"type": "string"}},
            [],
            {"mode": "agent", "toolName": "t"},
        )
        is None
    )
    assert engine_page.evaluate("() => App.toolConfigFields.allowed({type: 'boolean'})") is True
    assert engine_page.evaluate("() => App.toolConfigFields.allowed({type: 'integer'})") is False


@pytest.mark.parametrize(
    ("typed", "message"),
    [
        ("1.5", "Enter a whole number."),
        ("12abc", "Enter a whole number."),
        ("abc", "Enter a whole number."),
        ("12", None),
        ("", None),
        (" 30 ", None),
    ],
)
def test_agent_number_validation_is_live_and_states_one_message(
    engine_page: Page, typed: str, message: str | None
) -> None:
    _setup(engine_page)
    _agent(
        engine_page,
        "timeout_seconds_default",
        {"type": "integer", "x_marker": "Narrow"},
        60,
        operatorValue=60,
    )
    inp = engine_page.locator("#harness-root input")
    inp.fill(typed)
    err = engine_page.locator("#harness-root .field-error")
    if message:
        assert err.inner_text() == message
        assert inp.get_attribute("aria-invalid") == "true"
        assert engine_page.evaluate("() => window.__last.validate()") == message
    else:
        assert err.count() == 0
        assert inp.get_attribute("aria-invalid") is None
        assert engine_page.evaluate("() => window.__last.validate()") is None
    # A bad value clears when it becomes valid.
    if message:
        inp.fill("15")
        assert err.count() == 0
        assert inp.get_attribute("aria-invalid") is None


def test_agent_narrow_dropdown_is_filtered_and_keeps_a_humanised_custom_value(
    engine_page: Page,
) -> None:
    _setup(engine_page)
    prop = {
        "type": "integer",
        "x_marker": "Narrow",
        "ui_hint": "dropdown",
        "ui_choices": [{"value": v, "label": f"{v}s"} for v in (10, 30, 60, 120)],
    }
    _agent(engine_page, "timeout_seconds_max", prop, 45, operatorValue=60)
    opts = engine_page.evaluate(
        "() => [...window.__last.control.options].map((o) => [o.value, o.textContent, o.selected])"
    )
    assert [o[0] for o in opts] == ["10", "30", "60", "45"]  # 120 > 60 is dropped
    assert ["45", "45s (custom)", True] in opts
    assert engine_page.evaluate("() => window.__last.value()") == 45


def test_agent_narrow_superset_locks_the_operator_chips_and_reads_the_union(
    engine_page: Page,
) -> None:
    _setup(engine_page)
    _agent(
        engine_page,
        "command_denylist",
        {
            "type": "array",
            "x_marker": "NarrowSuperset",
            "items": {"type": "string"},
            "title": "Blocked commands",
        },
        ["rm", "extra"],
        operatorValue=["rm", "dd"],
        toolName="shell",
    )
    out = _info(engine_page)
    assert out["value"] == ["rm", "dd", "extra"]
    assert (out["fieldType"], out["marker"], out["tool"]) == ("array", "NarrowSuperset", "shell")
    chips = engine_page.evaluate(
        "() => [...window.__last.control.querySelectorAll('.chip')].map((c) => [c.dataset.locked || null, c.querySelectorAll('button').length])"
    )
    assert chips == [["true", 0], ["true", 0], [None, 1]]
    engine_page.locator("#harness-root .chip-list-input").press("Backspace")
    engine_page.locator("#harness-root .chip-list-input").press("Backspace")
    assert engine_page.evaluate("() => window.__last.value()") == ["rm", "dd"]


def test_agent_boolean_is_inline_and_carries_the_override_hooks(engine_page: Page) -> None:
    _setup(engine_page)
    _agent(
        engine_page,
        "sandbox_network_allowed",
        {
            "type": "boolean",
            "x_marker": "Narrow",
            "title": "Allow network in the sandbox",
            "description": "d",
        },
        True,
    )
    out = _info(engine_page)
    assert (out["inputType"], out["value"], out["tool"], out["toolField"]) == (
        "checkbox",
        True,
        "http_request",
        "sandbox_network_allowed",
    )
    assert out["rowHasOverrideAttr"] is False and out["rowAgent"] is True
    assert engine_page.locator("#harness-root .field-group").count() == 0
    assert (
        engine_page.locator("#harness-root label").inner_text().strip()
        == "Allow network in the sandbox"
    )


def test_read_value_dispatches_on_the_control(engine_page: Page) -> None:
    _setup(engine_page)
    _admin(engine_page, "n", {"type": "integer"}, 4)
    assert engine_page.evaluate("() => App.toolConfigFields.readValue(window.__h.n.control)") == 4
    _admin(engine_page, "c", {"type": "array", "items": {"type": "string"}}, ["a" * 80, "b"])
    # A long value is read in full, never from its truncated text.
    assert engine_page.evaluate("() => App.toolConfigFields.readValue(window.__h.c.control)") == [
        "a" * 80,
        "b",
    ]
