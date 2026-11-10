# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Browser tests for the streaming boundary planner ``App.chat.visualStream`` (M35 F2 L2,
flight DD12 and DD14). The planner is pure logic over a streaming tail: it finds the candidate
commit offsets and reports an open top-level block of one of its ``tags`` (a chart, later a
widget). It is tag-driven: only a column-0 opener whose first word is a tag counts, confirmed by
the real ``App.markdown.parse``. Runs in both engines against a blank page that loads the real
``markdown.js`` and ``visual-stream.js``; no app spawn. Lives in the ``chats`` lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import STATIC_DIR, load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser


def _load(page: Page) -> None:
    load_harness(page)
    page.add_script_tag(path=str(STATIC_DIR / "js" / "markdown.js"))
    page.evaluate("() => { window.App.chat = window.App.chat || {}; }")
    page.add_script_tag(path=str(STATIC_DIR / "js" / "areas" / "chat" / "visual-stream.js"))


def _plan(page: Page, tags: list[str], text: str) -> dict:
    return page.evaluate(
        "([tags, text]) => App.chat.visualStream.create({tags: tags}).plan(text)", [tags, text]
    )


def test_a_tagged_opener_at_column_zero_is_reported_with_its_lang(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    text = 'Before.\n\n```widget\n{"x": 1'
    plan = _plan(page, ["chart", "widget"], text)
    assert plan["open"] == {"offset": text.index("```widget"), "lang": "widget"}
    # the blank line before the opener ends at the opener's offset: that is the boundary
    assert plan["boundary"] == text.index("```widget")

    chart = 'Intro\n\n```chart\n{"type": "bar"'
    assert _plan(page, ["chart", "widget"], chart)["open"] == {
        "offset": chart.index("```chart"),
        "lang": "chart",
    }


def test_a_longer_word_with_the_tag_as_prefix_is_not_an_opener(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    text = "Before.\n\n```widgets\nsome text"
    plan = _plan(page, ["chart", "widget"], text)
    assert plan["open"] is None


def test_only_the_listed_tags_open(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    text = "Before.\n\n```widget\nbody"
    assert _plan(page, ["chart"], text)["open"] is None
    assert _plan(page, [], text)["open"] is None
    assert _plan(page, ["widget"], text)["open"]["lang"] == "widget"


def test_an_indented_opener_and_a_closed_block_are_not_open(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    assert _plan(page, ["widget"], "- item\n\n  ```widget\n  body")["open"] is None
    closed = "Before.\n\n```widget\nbody\n```\nAfter"
    plan = _plan(page, ["widget"], closed)
    assert plan["open"] is None
    # the closing fence line's end is a confirmed boundary
    assert plan["boundary"] == closed.index("```\nAfter") + 4
