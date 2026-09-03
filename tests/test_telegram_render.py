"""Tests for ``the_one.connectors.telegram._render`` -- the deterministic
markdown -> Telegram HTML converter (Mission 23 Flight 4, HAT step 8:
Telegram formatted rendering, promoted through a scoped review). Pure
unit tests, no network, no fixture.
"""

from __future__ import annotations

import pytest

from the_one.connectors.telegram._render import render_telegram_html

# ── plain prose / escaping ──────────────────────────────────────────────


def test_plain_text_passes_through_unchanged():
    assert render_telegram_html("just a plain sentence") == "just a plain sentence"


def test_escapes_angle_brackets_and_ampersand_in_prose():
    assert render_telegram_html("a < b & c > d") == "a &lt; b &amp; c &gt; d"


def test_adversarial_pre_escaped_text_is_escaped_again():
    # Deterministic converter: it does not try to detect or preserve
    # pre-existing HTML entities. A literal "&amp;" in the source is a
    # literal ampersand-a-m-p-semicolon sequence, escaped like any other
    # "&" -- this is intentional, not a bug (see module docstring).
    assert render_telegram_html("already &amp; escaped") == "already &amp;amp; escaped"
    assert render_telegram_html("<b>fake tag</b>") == "&lt;b&gt;fake tag&lt;/b&gt;"


# ── bold / italic ────────────────────────────────────────────────────────


def test_bold_double_star():
    assert render_telegram_html("this is **bold** text") == "this is <b>bold</b> text"


def test_italic_single_star():
    assert render_telegram_html("this is *italic* text") == "this is <i>italic</i> text"


def test_italic_underscore():
    assert render_telegram_html("this is _italic_ text") == "this is <i>italic</i> text"


def test_bold_and_nested_italic():
    assert (
        render_telegram_html("**bold *and italic* text**") == "<b>bold <i>and italic</i> text</b>"
    )


def test_italic_requires_nonwhitespace_adjacent_to_delimiters():
    # A space right after the opening delimiter (or right before the
    # closing one) disqualifies it -- left as literal text.
    assert render_telegram_html("a * spaced * star") == "a * spaced * star"
    assert render_telegram_html("a _ spaced _ underscore") == "a _ spaced _ underscore"


def test_bullet_vs_italic_collision_explicit():
    # The reviewer's collision rule: a line-start "* " bullet marker must
    # never be read as an opening italic delimiter, while a genuine
    # italic span elsewhere on the SAME line still converts normally.
    text = "* first item\n* second item with *emphasis* inside"
    expected = "* first item\n* second item with <i>emphasis</i> inside"
    assert render_telegram_html(text) == expected


def test_bullet_only_lines_are_untouched():
    text = "* apple\n* banana\n* cherry"
    assert render_telegram_html(text) == text


# ── links ────────────────────────────────────────────────────────────────


def test_link_basic():
    assert (
        render_telegram_html("see [the docs](https://example.com/x)")
        == 'see <a href="https://example.com/x">the docs</a>'
    )


def test_link_href_escapes_quote_and_ampersand():
    out = render_telegram_html('[click](https://example.com/x?a=1&b="q")')
    assert 'href="https://example.com/x?a=1&amp;b=&quot;q&quot;"' in out
    assert '"q"' not in out  # the raw quote never survives into the attribute


def test_link_text_is_escaped():
    out = render_telegram_html("[<script>](https://example.com)")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


# ── code spans / fences protect markdown chars ─────────────────────────────


def test_inline_code_protects_markdown_syntax():
    out = render_telegram_html("use `**not bold**` literally")
    assert out == "use <code>**not bold**</code> literally"


def test_inline_code_escapes_angle_brackets_and_ampersand():
    out = render_telegram_html("run `a < b & c`")
    assert out == "run <code>a &lt; b &amp; c</code>"


def test_fenced_code_block_protects_and_escapes():
    text = 'before\n```\nif a < b:\n    print("*not bold*")\n```\nafter'
    out = render_telegram_html(text)
    assert "<pre>if a &lt; b:\n    print(&quot;" not in out  # no quote-escaping outside href
    assert '<pre>if a &lt; b:\n    print("*not bold*")</pre>' in out
    assert "before" in out and "after" in out
    assert "<i>" not in out and "<b>" not in out


def test_fenced_code_with_language_tag_still_protected():
    text = "```python\n**still literal**\n```"
    out = render_telegram_html(text)
    assert out == "<pre>**still literal**</pre>"


# ── degrade: tables / headings / list markers ───────────────────────────


def test_table_degrades_to_pre():
    text = "| A | B |\n|---|---|\n| 1 | 2 |"
    out = render_telegram_html(text)
    assert out.startswith("<pre>") and out.endswith("</pre>")
    assert "| A | B |" in out
    assert "<b>" not in out and "<i>" not in out


def test_stray_pipe_sentence_is_not_treated_as_a_table():
    # No separator row -> not a table -- ordinary prose escaping applies.
    text = "cost is a | b per unit"
    assert render_telegram_html(text) == text


def test_heading_becomes_bold_line():
    assert render_telegram_html("# Title") == "<b>Title</b>"
    assert render_telegram_html("### Sub Heading") == "<b>Sub Heading</b>"


def test_heading_content_still_gets_inline_formatting():
    assert render_telegram_html("## a *heading* with emphasis") == (
        "<b>a <i>heading</i> with emphasis</b>"
    )


def test_list_markers_stay_literal_text():
    text = "1. first\n2. second\n- dash item"
    assert render_telegram_html(text) == text


# ── never raises on malformed / unbalanced markdown ─────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "**unclosed bold",
        "*unclosed italic",
        "_unclosed underscore",
        "[unclosed link(https://example.com",
        "```unclosed fence\nsome code",
        "`unclosed inline code",
        "*** triple star mess ***",
        "**_*mixed __ delimiters* _**",
        "#" * 500,
        "*" * 500,
        "\x00\x01\x02\x03\x04 control chars in input",
        "",
    ],
)
def test_malformed_markdown_never_raises_and_degrades(text: str):
    result = render_telegram_html(text)
    assert isinstance(result, str)
    # Degraded output must never leak Telegram's own sentinel/token
    # control characters -- confirms restoration always completes.
    assert not any(ch in result for ch in "\x00\x01\x02\x03\x04")
