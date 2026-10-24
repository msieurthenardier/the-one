# ruff: noqa: E501
"""`App.api.fetchJson` error properties, `fieldErrors`, `humanizeMessage` (M31 F4 L03a).

Runs in a harness page with `api.js` loaded and routed responses, in Chromium and
WebKit. The 422 bodies are copies of the real API's (provenance:
`tests/test_api_error_shapes.py` proves each shape against the live handlers).
"""

from __future__ import annotations

import pytest
from browser._ui_engines import STATIC_DIR, load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

URL = "http://api-errors.test/x"


def _setup(page: Page, status: int, body: str, content_type: str = "application/json") -> None:
    load_harness(page)
    page.add_script_tag(path=str(STATIC_DIR / "js" / "api.js"))
    page.route(
        URL,
        lambda route: route.fulfill(
            status=status,
            body=body,
            headers={"content-type": content_type, "access-control-allow-origin": "*"},
        ),
    )


_CATCH = (
    """async () => {
  try { await App.api.fetchJson('%s'); return {ok: true}; }
  catch (e) { return {message: e.message, status: e.status, detail: e.detail === undefined ? '__undef__' : e.detail, body: e.body}; }
}"""
    % URL
)


@pytest.mark.parametrize(
    ("status", "body", "ctype", "message", "detail"),
    [
        (
            409,
            '{"detail": "Folder overlaps"}',
            "application/json",
            "Folder overlaps",
            "Folder overlaps",
        ),
        (
            422,
            '{"detail": [{"loc": ["body", "a"], "msg": "bad"}, {"loc": [], "msg": "worse"}]}',
            "application/json",
            "body.a: bad | worse",
            [{"loc": ["body", "a"], "msg": "bad"}, {"loc": [], "msg": "worse"}],
        ),
        (
            500,
            "<html>boom</html>",
            "text/html",
            "Server error 500 : <html>boom</html>",
            "__undef__",
        ),
        (500, "", "text/plain", "Server error 500 ", "__undef__"),
    ],
)
def test_fetch_json_error_properties(
    engine_page: Page, status, body, ctype, message, detail
) -> None:  # noqa: ANN001
    _setup(engine_page, status, body, ctype)
    out = engine_page.evaluate(_CATCH)
    assert out["status"] == status
    assert out["body"] == body
    assert out["detail"] == detail
    if status == 500:
        # statusText is engine-dependent for a fulfilled route; the rest is fixed.
        assert out["message"].startswith("Server error 500")
        if body:
            assert out["message"].endswith(": " + body.strip())
        else:
            assert ":" not in out["message"]
    else:
        assert out["message"] == message


def test_fetch_json_success_unchanged(engine_page: Page) -> None:
    _setup(engine_page, 200, '{"a": 1}')
    assert engine_page.evaluate("() => App.api.fetchJson('%s')" % URL) == {"a": 1}


def _fe(page: Page, err: str, names: list[str]) -> dict:
    return page.evaluate(
        "([err, names]) => { const e = Object.assign(new Error('m'), eval('(' + err + ')')); return App.api.fieldErrors(e, names); }",
        [err, names],
    )


def test_field_errors_tools_shape(engine_page: Page) -> None:
    _setup(engine_page, 200, "{}")
    out = _fe(
        engine_page,
        '{status: 422, detail: [{type: "greater_than_equal", loc: ["timeout_seconds_max"], msg: "Input should be greater than or equal to 1"}]}',
        ["timeout_seconds_max"],
    )
    assert out == {"fields": {"timeout_seconds_max": "Must be 1 or more"}, "rest": [], "text": ""}


def test_field_errors_leading_body_dropped_and_index_segments(engine_page: Page) -> None:
    _setup(engine_page, 200, "{}")
    out = _fe(
        engine_page,
        '{status: 422, detail: [{loc: ["body", "path_denylist", 0], msg: "Value error, bad entry"}]}',
        ["path_denylist"],
    )
    assert out["fields"] == {"path_denylist": "bad entry"} and out["rest"] == []


def test_field_errors_knowledge_settings_shape(engine_page: Page) -> None:
    _setup(engine_page, 200, "{}")
    out = _fe(
        engine_page,
        '{status: 422, detail: [{loc: ["size_chars"], msg: "Input should be greater than or equal to 200"}]}',
        ["size_chars", "overlap_chars"],
    )
    assert out["fields"] == {"size_chars": "Must be 200 or more"}


def test_field_errors_overlap_model_validator_is_editor_level(engine_page: Page) -> None:
    _setup(engine_page, 200, "{}")
    out = _fe(
        engine_page,
        '{status: 422, detail: [{loc: [], msg: "Value error, overlap_chars (900) must not exceed 50% of size_chars (1000)"}]}',
        ["size_chars", "overlap_chars"],
    )
    assert out == {
        "fields": {},
        "rest": ["overlap_chars (900) must not exceed 50% of size_chars (1000)"],
        "text": "overlap_chars (900) must not exceed 50% of size_chars (1000).",
    }


def test_field_errors_string_detail_is_unmatched(engine_page: Page) -> None:
    _setup(engine_page, 200, "{}")
    out = _fe(engine_page, '{status: 409, detail: "Folder overlaps"}', ["path"])
    assert out == {"fields": {}, "rest": ["Folder overlaps"], "text": "Folder overlaps."}
    out = _fe(engine_page, "{status: 500, detail: undefined}", ["path"])
    assert out == {"fields": {}, "rest": [], "text": "m"}


def test_field_errors_no_substring_match_first_segment_wins_and_junk_skipped(
    engine_page: Page,
) -> None:
    _setup(engine_page, 200, "{}")
    out = _fe(
        engine_page,
        '{status: 422, detail: [{loc: ["size_chars"], msg: "x"}, null, {loc: ["a", "b"], msg: "one"}, {loc: ["b", "a"], msg: "two"}, {loc: "no"}]}',
        ["size", "a", "b"],
    )
    assert out["fields"]["a"] == "one" and out["fields"]["b"] == "two"
    assert out["rest"] == ["x"]  # size_chars is not "size"


def test_field_errors_mixed_text_and_period_rule(engine_page: Page) -> None:
    _setup(engine_page, 200, "{}")
    out = _fe(
        engine_page,
        '{status: 422, detail: [{loc: ["a"], msg: "bad"}, {loc: [], msg: "Value error, First."}, {loc: [], msg: "Second"}]}',
        ["a"],
    )
    assert out["fields"] == {"a": "bad"}
    assert out["text"] == "First. Second."


def test_field_errors_network_error_never_throws(engine_page: Page) -> None:
    _setup(engine_page, 200, "{}")
    out = engine_page.evaluate("() => App.api.fieldErrors(new TypeError('Failed to fetch'), ['a'])")
    assert out == {"fields": {}, "rest": [], "text": "Failed to fetch"}


@pytest.mark.parametrize(
    ("msg", "plain"),
    [
        ("Input should be greater than or equal to 1", "Must be 1 or more"),
        ("Input should be greater than or equal to -1", "Must be -1 or more"),
        ("Input should be greater than 0.5", "Must be more than 0.5"),
        ("Input should be less than or equal to 10", "Must be at most 10"),
        ("Input should be less than 3", "Must be less than 3"),
        (
            "Input should be a valid integer, unable to parse string as an integer",
            "Must be a whole number",
        ),
        ("Input should be a valid number, unable to parse string as a number", "Must be a number"),
        ("String should have at least 3 characters", "String should have at least 3 characters"),
        ("Value error, Something custom", "Something custom"),
        ("Field required", "Field required"),
    ],
)
def test_humanize_message(engine_page: Page, msg: str, plain: str) -> None:
    _setup(engine_page, 200, "{}")
    assert engine_page.evaluate("(m) => App.api.humanizeMessage(m)", msg) == plain
