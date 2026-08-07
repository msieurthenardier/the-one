"""Browser tests for the hand-rolled markdown library at static/js/markdown.js.

Validates the public API contracts:

- ``App.markdown.parse(text) -> AST`` — well-formed dict tree (incl. empty input).
- ``App.markdown.render(text) -> DocumentFragment`` — DOM-shape via outerHTML.
- ``App.markdown.NodeType`` — frozen string constants.

The corpus covers each of the 13 user-authored markdown constructs with at
least 3 cases plus boundary cases (nested-emphasis non-recursive contract,
javascript:-href XSS hardening, balanced-paren URLs, null-lang code block,
single-trailing-space soft break, ``parse(null)`` empty document), GFM table
rendering (parser + DOM shape), and one end-to-end test of the code-block copy
button (clipboard permissions granted on the browser context).

The fixture below spawns a single app subprocess and a single Playwright
page for the entire module — parametrized cases re-use the same page via
``page.evaluate(...)``. This keeps the suite fast (one subprocess, one
browser context) while preserving DOM isolation per case (each case
renders into a fresh host div). The dedicated copy-button case clears
``document.body`` first to avoid DOM accumulation across the parametrized
runs.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from browser._credential_registry import unregister as _unregister_credential
from browser.conftest import _spawn_app, _teardown_proc, credentialed_context
from playwright.sync_api import Browser, Page

# ── Module-scoped app subprocess + page ────────────────────────────────────


@pytest.fixture(scope="module")
def app_clean_module(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Module-scoped variant of ``app_clean`` — one subprocess per test module.

    The function-scoped ``app_clean`` from conftest spawns per test, which
    would mean ~60+ subprocess spawns for the parametrized markdown corpus.
    This module-scoped fixture shares one app + one page (via
    ``page_with_app``) for the entire parametrized suite.

    Mission 20 / Flight 1 / Leg 3 (``harness-credential-plumbing``):
    consolidated onto the shared ``_spawn_app`` (imported from
    ``browser.conftest``) rather than duplicating the spawn-plus-
    readiness-poll logic here — this fixture's own module scope is
    preserved (the leg's explicit edge case): only the spawn mechanism
    moved, not this decorator.
    """
    tmp_path = tmp_path_factory.mktemp("the-one-data-md")
    base_url, proc, _credential, _data_dir = _spawn_app(tmp_path)
    try:
        yield base_url
    finally:
        _unregister_credential(base_url)
        _teardown_proc(proc)


@pytest.fixture(scope="module")
def page_with_app(app_clean_module: str, browser: Browser) -> Iterator[Page]:
    """Single page loaded for the markdown-corpus parametrized tests.

    ``clipboard-read`` / ``clipboard-write`` permissions are granted so
    the code-block copy-button e2e tests the success path (not the error
    fallback). Headless Chromium needs explicit permission to satisfy
    ``navigator.clipboard.writeText``.

    Mission 20 / Flight 1 / Leg 3: this module defines its own page
    fixture rather than consuming conftest's ``page`` (module scope vs.
    function scope), so it attaches ``app_clean_module``'s credential to
    the context directly — there is no ambiguity about which app this
    page drives, unlike the generic ``page`` fixture.

    Mission 20 / Flight 1 / Leg 4 review fix: previously only set the
    ``Authorization`` header, not the handoff session cookie — this
    happened to keep passing after the gate went live only because
    ``App.markdown`` is exercised via in-page ``page.evaluate(...)`` calls
    that never assert on chat state, so the default-area boot's bare
    ``new WebSocket('/ws')`` (``static/js/areas/chat.js``) silently
    closing with code 1008 for lack of a session cookie went unnoticed —
    the WHATWG spec forbids attaching custom headers to a WebSocket
    handshake, so the header alone was never going to authorize it (see
    ``conftest.py``'s ``page`` fixture docstring). Passing for that reason
    was incidental, not evidence the cookie is unneeded, so this is routed
    through ``credentialed_context()`` (``conftest.py``) for the same
    header + handoff-cookie treatment every other fixture gets, rather
    than left as-is.
    """
    context = credentialed_context(
        browser,
        app_clean_module,
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = context.new_page()
    page.goto(app_clean_module)
    page.wait_for_function(
        "typeof App !== 'undefined' "
        "&& typeof App.markdown !== 'undefined' "
        "&& typeof App.markdown.render === 'function'",
        timeout=5000,
    )
    try:
        yield page
    finally:
        context.close()


# ── AST-shape corpus ───────────────────────────────────────────────────────


def _doc(*children: dict) -> dict:
    return {"type": "document", "children": list(children)}


def _para(*children: dict) -> dict:
    return {"type": "paragraph", "children": list(children)}


def _text(value: str) -> dict:
    return {"type": "text", "value": value}


def _heading(level: int, *children: dict) -> dict:
    return {"type": "heading", "meta": {"level": level}, "children": list(children)}


AST_CASES: list[tuple[str, dict]] = [
    # --- empty / null robustness ---
    ("", _doc()),
    # --- paragraphs (3+) ---
    ("hello", _doc(_para(_text("hello")))),
    (
        "line1\nline2",
        _doc(_para(_text("line1"), {"type": "softBreak"}, _text("line2"))),
    ),
    (
        "a  \nb",
        _doc(_para(_text("a"), {"type": "hardBreak"}, _text("b"))),
    ),
    # --- headings (h1-h6 + emphasis-in-heading + boundary) ---
    ("# Hello", _doc(_heading(1, _text("Hello")))),
    ("## H2", _doc(_heading(2, _text("H2")))),
    ("### H3", _doc(_heading(3, _text("H3")))),
    ("#### H4", _doc(_heading(4, _text("H4")))),
    ("##### H5", _doc(_heading(5, _text("H5")))),
    ("###### H6", _doc(_heading(6, _text("H6")))),
    (
        "## A *b* c",
        _doc(
            _heading(
                2,
                _text("A "),
                {"type": "emphasis", "children": [_text("b")]},
                _text(" c"),
            )
        ),
    ),
    # --- code blocks (with lang, without lang, multiline) ---
    (
        "```js\nconsole.log(1);\n```",
        _doc(
            {
                "type": "codeBlock",
                "meta": {"lang": "js"},
                "value": "console.log(1);\n",
            }
        ),
    ),
    (
        "```\nplain text\n```",
        _doc(
            {
                "type": "codeBlock",
                "meta": {"lang": None},
                "value": "plain text\n",
            }
        ),
    ),
    (
        "```python\na = 1\nb = 2\n```",
        _doc(
            {
                "type": "codeBlock",
                "meta": {"lang": "python"},
                "value": "a = 1\nb = 2\n",
            }
        ),
    ),
    # --- blockquote (single, multiline, with emphasis) ---
    (
        "> quoted",
        _doc(
            {
                "type": "blockquote",
                "children": [_para(_text("quoted"))],
            }
        ),
    ),
    (
        "> line one\n> line two",
        _doc(
            {
                "type": "blockquote",
                "children": [_para(_text("line one"), {"type": "softBreak"}, _text("line two"))],
            }
        ),
    ),
    (
        "> *em* inside",
        _doc(
            {
                "type": "blockquote",
                "children": [
                    _para(
                        {"type": "emphasis", "children": [_text("em")]},
                        _text(" inside"),
                    )
                ],
            }
        ),
    ),
    # --- unordered lists (3 markers + nested) ---
    (
        "- a\n- b",
        _doc(
            {
                "type": "list",
                "meta": {"ordered": False, "start": None},
                "children": [
                    {"type": "listItem", "children": [_para(_text("a"))]},
                    {"type": "listItem", "children": [_para(_text("b"))]},
                ],
            }
        ),
    ),
    (
        "* a\n* b",
        _doc(
            {
                "type": "list",
                "meta": {"ordered": False, "start": None},
                "children": [
                    {"type": "listItem", "children": [_para(_text("a"))]},
                    {"type": "listItem", "children": [_para(_text("b"))]},
                ],
            }
        ),
    ),
    (
        "+ a\n+ b",
        _doc(
            {
                "type": "list",
                "meta": {"ordered": False, "start": None},
                "children": [
                    {"type": "listItem", "children": [_para(_text("a"))]},
                    {"type": "listItem", "children": [_para(_text("b"))]},
                ],
            }
        ),
    ),
    # --- ordered lists ---
    (
        "1. one\n2. two",
        _doc(
            {
                "type": "list",
                "meta": {"ordered": True, "start": None},
                "children": [
                    {"type": "listItem", "children": [_para(_text("one"))]},
                    {"type": "listItem", "children": [_para(_text("two"))]},
                ],
            }
        ),
    ),
    (
        "5. five\n6. six",
        _doc(
            {
                "type": "list",
                "meta": {"ordered": True, "start": 5},
                "children": [
                    {"type": "listItem", "children": [_para(_text("five"))]},
                    {"type": "listItem", "children": [_para(_text("six"))]},
                ],
            }
        ),
    ),
    (
        "1. alpha\n2. beta\n3. gamma",
        _doc(
            {
                "type": "list",
                "meta": {"ordered": True, "start": None},
                "children": [
                    {"type": "listItem", "children": [_para(_text("alpha"))]},
                    {"type": "listItem", "children": [_para(_text("beta"))]},
                    {"type": "listItem", "children": [_para(_text("gamma"))]},
                ],
            }
        ),
    ),
    # --- horizontal rules ---
    ("---", _doc({"type": "horizontalRule"})),
    ("***", _doc({"type": "horizontalRule"})),
    ("------", _doc({"type": "horizontalRule"})),
    # --- emphasis (3 cases incl. _) ---
    (
        "*x*",
        _doc(_para({"type": "emphasis", "children": [_text("x")]})),
    ),
    (
        "_x_",
        _doc(_para({"type": "emphasis", "children": [_text("x")]})),
    ),
    (
        "an *em* word",
        _doc(
            _para(
                _text("an "),
                {"type": "emphasis", "children": [_text("em")]},
                _text(" word"),
            )
        ),
    ),
    # --- strong (3 cases) ---
    (
        "**x**",
        _doc(_para({"type": "strong", "children": [_text("x")]})),
    ),
    (
        "__x__",
        _doc(_para({"type": "strong", "children": [_text("x")]})),
    ),
    (
        "a **bold** b",
        _doc(
            _para(
                _text("a "),
                {"type": "strong", "children": [_text("bold")]},
                _text(" b"),
            )
        ),
    ),
    # --- inline code (3 cases) ---
    (
        "`code`",
        _doc(_para({"type": "inlineCode", "value": "code"})),
    ),
    (
        "use `print()` here",
        _doc(
            _para(
                _text("use "),
                {"type": "inlineCode", "value": "print()"},
                _text(" here"),
            )
        ),
    ),
    (
        "`a*b*c`",
        _doc(_para({"type": "inlineCode", "value": "a*b*c"})),
    ),
    # --- links (basic, mailto, relative) ---
    (
        "[ok](https://example.com)",
        _doc(
            _para(
                {
                    "type": "link",
                    "meta": {"href": "https://example.com"},
                    "children": [_text("ok")],
                }
            )
        ),
    ),
    (
        "[mail](mailto:hi@example.com)",
        _doc(
            _para(
                {
                    "type": "link",
                    "meta": {"href": "mailto:hi@example.com"},
                    "children": [_text("mail")],
                }
            )
        ),
    ),
    (
        "[home](/about)",
        _doc(
            _para(
                {
                    "type": "link",
                    "meta": {"href": "/about"},
                    "children": [_text("home")],
                }
            )
        ),
    ),
    # --- soft breaks (3 cases) ---
    (
        "alpha\nbeta",
        _doc(_para(_text("alpha"), {"type": "softBreak"}, _text("beta"))),
    ),
    (
        "one\ntwo\nthree",
        _doc(
            _para(
                _text("one"),
                {"type": "softBreak"},
                _text("two"),
                {"type": "softBreak"},
                _text("three"),
            )
        ),
    ),
    (
        "a \nb",  # single trailing space + \n -> soft break (not hard)
        _doc(_para(_text("a "), {"type": "softBreak"}, _text("b"))),
    ),
    # --- hard breaks (3 cases) ---
    (
        "a  \nb",
        _doc(_para(_text("a"), {"type": "hardBreak"}, _text("b"))),
    ),
    (
        "first  \nsecond",
        _doc(_para(_text("first"), {"type": "hardBreak"}, _text("second"))),
    ),
    (
        "x  \ny  \nz",
        _doc(
            _para(
                _text("x"),
                {"type": "hardBreak"},
                _text("y"),
                {"type": "hardBreak"},
                _text("z"),
            )
        ),
    ),
    # --- boundary: nested emphasis non-recursive contract ---
    (
        "***word***",
        _doc(
            _para(
                {
                    "type": "emphasis",
                    "children": [
                        {
                            "type": "strong",
                            "children": [_text("word")],
                        }
                    ],
                }
            )
        ),
    ),
    (
        "**bold *with em***",
        _doc(
            _para(
                {
                    "type": "strong",
                    "children": [_text("bold *with em*")],
                }
            )
        ),
    ),
    # --- boundary: link href safety ---
    (
        "[click me](javascript:alert(1))",
        _doc(
            _para(
                {
                    "type": "link",
                    "meta": {"href": "#"},
                    "children": [_text("click me")],
                }
            )
        ),
    ),
    # --- boundary: balanced-paren URL ---
    (
        "[wiki](https://en.wikipedia.org/wiki/Foo_(bar))",
        _doc(
            _para(
                {
                    "type": "link",
                    "meta": {"href": "https://en.wikipedia.org/wiki/Foo_(bar)"},
                    "children": [_text("wiki")],
                }
            )
        ),
    ),
    # --- GFM tables (3 cases) ---
    # Minimal 2-column table with header and one data row.
    (
        "| a | b |\n| - | - |\n| 1 | 2 |",
        _doc(
            {
                "type": "table",
                "children": [
                    {
                        "type": "tableHead",
                        "children": [
                            {"type": "tableCell", "children": [_text("a")]},
                            {"type": "tableCell", "children": [_text("b")]},
                        ],
                    },
                    {
                        "type": "tableRow",
                        "children": [
                            {"type": "tableCell", "children": [_text("1")]},
                            {"type": "tableCell", "children": [_text("2")]},
                        ],
                    },
                ],
            }
        ),
    ),
    # Table without leading/trailing pipes (GFM relaxed form).
    (
        "Name | Age\n---- | ---\nAlice | 30",
        _doc(
            {
                "type": "table",
                "children": [
                    {
                        "type": "tableHead",
                        "children": [
                            {"type": "tableCell", "children": [_text("Name")]},
                            {"type": "tableCell", "children": [_text("Age")]},
                        ],
                    },
                    {
                        "type": "tableRow",
                        "children": [
                            {"type": "tableCell", "children": [_text("Alice")]},
                            {"type": "tableCell", "children": [_text("30")]},
                        ],
                    },
                ],
            }
        ),
    ),
    # Table with inline markup in cells.
    (
        "| **Key** | Value |\n| --- | --- |\n| `id` | 42 |",
        _doc(
            {
                "type": "table",
                "children": [
                    {
                        "type": "tableHead",
                        "children": [
                            {
                                "type": "tableCell",
                                "children": [{"type": "strong", "children": [_text("Key")]}],
                            },
                            {"type": "tableCell", "children": [_text("Value")]},
                        ],
                    },
                    {
                        "type": "tableRow",
                        "children": [
                            {
                                "type": "tableCell",
                                "children": [{"type": "inlineCode", "value": "id"}],
                            },
                            {"type": "tableCell", "children": [_text("42")]},
                        ],
                    },
                ],
            }
        ),
    ),
]


@pytest.mark.browser
@pytest.mark.parametrize("source, expected", AST_CASES)
def test_markdown_parse_ast(page_with_app: Page, source: str, expected: dict) -> None:
    """``parse(source)`` returns the expected AST tree."""
    result = page_with_app.evaluate("(src) => App.markdown.parse(src)", source)
    assert result == expected


@pytest.mark.browser
def test_markdown_parse_null_returns_empty_document(page_with_app: Page) -> None:
    """``parse(null)`` and ``parse(undefined)`` coerce to an empty document."""
    null_result = page_with_app.evaluate("() => App.markdown.parse(null)")
    undef_result = page_with_app.evaluate("() => App.markdown.parse(undefined)")
    expected = {"type": "document", "children": []}
    assert null_result == expected
    assert undef_result == expected


# ── Rendered-DOM corpus ────────────────────────────────────────────────────

RENDER_CASES: list[tuple[str, str]] = [
    # --- headings ---
    ("# Hi", "<h1>Hi</h1>"),
    ("## Two", "<h2>Two</h2>"),
    ("###### Six", "<h6>Six</h6>"),
    # --- paragraphs + inline ---
    ("plain", "<p>plain</p>"),
    ("**bold**", "<p><strong>bold</strong></p>"),
    ("*em*", "<p><em>em</em></p>"),
    ("_em_", "<p><em>em</em></p>"),
    ("__strong__", "<p><strong>strong</strong></p>"),
    ("`code`", "<p><code>code</code></p>"),
    # --- nested-emphasis v1 contract ---
    ("***word***", "<p><em><strong>word</strong></em></p>"),
    ("**bold *with em***", "<p><strong>bold *with em*</strong></p>"),
    # --- links: safe + XSS-stripped ---
    (
        "[ok](https://example.com)",
        '<p><a href="https://example.com" rel="noopener noreferrer">ok</a></p>',
    ),
    (
        "[click me](javascript:alert(1))",
        '<p><a href="#" rel="noopener noreferrer">click me</a></p>',
    ),
    (
        "[data](data:text/html,foo)",
        '<p><a href="#" rel="noopener noreferrer">data</a></p>',
    ),
    (
        "[home](/about)",
        '<p><a href="/about" rel="noopener noreferrer">home</a></p>',
    ),
    (
        "[anchor](#top)",
        '<p><a href="#top" rel="noopener noreferrer">anchor</a></p>',
    ),
    (
        "[mail](mailto:hi@example.com)",
        '<p><a href="mailto:hi@example.com" rel="noopener noreferrer">mail</a></p>',
    ),
    (
        "[call](tel:+15551234567)",
        '<p><a href="tel:+15551234567" rel="noopener noreferrer">call</a></p>',
    ),
    (
        "[wiki](https://en.wikipedia.org/wiki/Foo_(bar))",
        '<p><a href="https://en.wikipedia.org/wiki/Foo_(bar)" rel="noopener noreferrer">wiki</a></p>',  # noqa: E501
    ),
    # --- code blocks (with + without lang) ---
    # Note: the SVG icon is parsed via DOMParser then re-serialized when read
    # back as host.innerHTML — self-closing tags (`<rect/>`) come out as
    # paired tags (`<rect></rect>`). This is HTML-tree serialization, not a
    # library bug; the asserted strings match the post-serialization form.
    (
        "```js\nconsole.log(1);\n```",
        '<div class="markdown-code-wrap">'
        '<pre><code class="language-js">console.log(1);\n</code></pre>'
        '<button class="markdown-copy-btn" aria-label="Copy code" type="button">'
        '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" '
        'width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"></rect>'
        '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"></path>'
        "</svg>"
        "</button>"
        "</div>",
    ),
    (
        "```\nplain\n```",
        '<div class="markdown-code-wrap">'
        "<pre><code>plain\n</code></pre>"
        '<button class="markdown-copy-btn" aria-label="Copy code" type="button">'
        '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" '
        'width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"></rect>'
        '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"></path>'
        "</svg>"
        "</button>"
        "</div>",
    ),
    # --- blockquote ---
    ("> quoted", "<blockquote><p>quoted</p></blockquote>"),
    # --- lists ---
    ("- a\n- b", "<ul><li>a</li><li>b</li></ul>"),
    ("* a\n* b", "<ul><li>a</li><li>b</li></ul>"),
    ("1. one\n2. two", "<ol><li>one</li><li>two</li></ol>"),
    ("5. five\n6. six", '<ol start="5"><li>five</li><li>six</li></ol>'),
    # --- horizontal rule ---
    ("---", "<hr>"),
    ("***", "<hr>"),
    # --- soft + hard breaks ---
    ("a\nb", "<p>a b</p>"),
    ("a  \nb", "<p>a<br>b</p>"),
    # Single trailing space + \n is a SOFT break (not hard). The trailing
    # space stays in the preceding text run; the soft break renders as a
    # space; result = "a  b" (two spaces).
    ("a \nb", "<p>a  b</p>"),
    # --- empty input renders empty fragment (caller sees empty host) ---
    ("", ""),
    # --- GFM tables ---
    (
        "| a | b |\n| - | - |\n| 1 | 2 |",
        "<table>"
        "<thead><tr><th>a</th><th>b</th></tr></thead>"
        "<tbody><tr><td>1</td><td>2</td></tr></tbody>"
        "</table>",
    ),
    (
        "Name | Age\n---- | ---\nAlice | 30",
        "<table>"
        "<thead><tr><th>Name</th><th>Age</th></tr></thead>"
        "<tbody><tr><td>Alice</td><td>30</td></tr></tbody>"
        "</table>",
    ),
    (
        "| **Key** | Value |\n| --- | --- |\n| `id` | 42 |",
        "<table>"
        "<thead><tr><th><strong>Key</strong></th><th>Value</th></tr></thead>"
        "<tbody><tr><td><code>id</code></td><td>42</td></tr></tbody>"
        "</table>",
    ),
]


@pytest.mark.browser
@pytest.mark.parametrize("source, expected", RENDER_CASES)
def test_markdown_render_html(page_with_app: Page, source: str, expected: str) -> None:
    """``render(source)`` produces the expected DOM (verified via host innerHTML)."""
    result = page_with_app.evaluate(
        """(src) => {
            const host = document.createElement('div');
            host.appendChild(App.markdown.render(src));
            return host.innerHTML;
        }""",
        source,
    )
    assert result == expected


# ── NodeType + render-fragment-shape contracts ────────────────────────────


@pytest.mark.browser
def test_markdown_nodetype_constants(page_with_app: Page) -> None:
    """``App.markdown.NodeType`` exposes all 18 frozen string constants."""
    nt = page_with_app.evaluate("() => Object.assign({}, App.markdown.NodeType)")
    assert nt == {
        "DOCUMENT": "document",
        "PARAGRAPH": "paragraph",
        "HEADING": "heading",
        "CODE_BLOCK": "codeBlock",
        "BLOCKQUOTE": "blockquote",
        "LIST": "list",
        "LIST_ITEM": "listItem",
        "HORIZONTAL_RULE": "horizontalRule",
        "TABLE": "table",
        "TABLE_HEAD": "tableHead",
        "TABLE_ROW": "tableRow",
        "TABLE_CELL": "tableCell",
        "TEXT": "text",
        "EMPHASIS": "emphasis",
        "STRONG": "strong",
        "INLINE_CODE": "inlineCode",
        "LINK": "link",
        "SOFT_BREAK": "softBreak",
        "HARD_BREAK": "hardBreak",
    }
    is_frozen = page_with_app.evaluate("() => Object.isFrozen(App.markdown.NodeType)")
    assert is_frozen is True


@pytest.mark.browser
def test_markdown_render_returns_document_fragment(page_with_app: Page) -> None:
    """``render`` returns a DocumentFragment (per the contract)."""
    is_frag = page_with_app.evaluate(
        "() => App.markdown.render('hello') instanceof DocumentFragment"
    )
    assert is_frag is True


@pytest.mark.browser
def test_markdown_render_empty_returns_empty_fragment(page_with_app: Page) -> None:
    """``render('')`` and ``render(null)`` return an empty DocumentFragment."""
    empty = page_with_app.evaluate(
        """() => {
            const f = App.markdown.render('');
            return f.childNodes.length;
        }"""
    )
    null_count = page_with_app.evaluate(
        """() => {
            const f = App.markdown.render(null);
            return f.childNodes.length;
        }"""
    )
    assert empty == 0
    assert null_count == 0


# ── Code-block copy-button e2e ────────────────────────────────────────────


@pytest.mark.browser
def test_markdown_copy_button(page_with_app: Page) -> None:
    """Clicking the copy button writes the code text to the clipboard and flashes 'Copied!'."""
    # Module-scoped page accumulates DOM across cases — clean before the e2e.
    page_with_app.evaluate("() => { document.body.innerHTML = ''; }")
    page_with_app.evaluate(
        """() => {
            const host = document.createElement('div');
            host.id = 'md-test-host';
            host.appendChild(App.markdown.render('```js\\nconsole.log(1);\\n```'));
            document.body.appendChild(host);
        }"""
    )
    btn = page_with_app.locator("#md-test-host .markdown-copy-btn")
    # M17 F4 L03: the copy button is now always-visible-but-quiet (resting
    # opacity 0.6, no hover-reveal-only). force=True is retained as a harmless
    # belt-and-braces against any transitional opacity during the click.
    btn.click(force=True)
    flash = page_with_app.locator(".app-flash").filter(has_text="Copied!")
    flash.wait_for(state="visible", timeout=2000)
    clipboard_text = page_with_app.evaluate("() => navigator.clipboard.readText()")
    assert clipboard_text == "console.log(1);\n"


# ── XSS regression suite (M17 F4 L1) ──────────────────────────────────────────
#
# The markdown pipeline's XSS guarantee is STRUCTURAL: render() builds DOM via
# createElement/createTextNode/setAttribute only — never an HTML-string sink —
# and every link href passes the fail-closed safeHref allow-list. The cases
# below are future-proofing TRIPWIRES: the payload classes are impossible to
# execute today (untrusted markup reaches only textContent), but each fires the
# instant an inner-HTML seam is reintroduced. Same parametrized page.evaluate
# pattern as the corpus above; the no-inner-HTML static invariant lives in
# tests/test_ui_guards.py::test_markdown_no_html_string_invariant.


# Active-content payloads AS markdown body — must render as INERT TEXT (no live
# script/iframe/img/svg element; the literal survives in textContent).
XSS_BODY_PAYLOADS: list[str] = [
    "<script>alert(1)</script>",  # script injection
    "<img src=x onerror=alert(1)>",  # onerror event handler
    '<iframe src="javascript:alert(1)"></iframe>',  # framed javascript:
    "<svg onload=alert(1)>",  # svg-onload
    # mXSS-style: a namespace/parse-differential payload that only detonates if
    # the string is round-tripped through an innerHTML sink.
    '<noscript><p title="</noscript><img src=x onerror=alert(1)>">',
]


@pytest.mark.browser
@pytest.mark.parametrize("payload", XSS_BODY_PAYLOADS)
def test_markdown_xss_body_is_inert_text(page_with_app: Page, payload: str) -> None:
    """Active-content markup in the markdown BODY renders as inert text — no
    live ``script``/``iframe``/``img``/``svg`` element is created, and the
    payload's ``alert(1)`` token survives verbatim in ``textContent``."""
    result = page_with_app.evaluate(
        """(src) => {
            const host = document.createElement('div');
            host.appendChild(App.markdown.render(src));
            return {
                hasActiveEl: host.querySelector('script, iframe, img, svg') !== null,
                text: host.textContent,
            };
        }""",
        payload,
    )
    assert result["hasActiveEl"] is False, f"payload produced a live element: {payload!r}"
    assert "alert(1)" in result["text"], f"payload text was mangled: {payload!r}"


# safeHref boundary: (source, expected_href). Obfuscated dangerous schemes and
# protocol-relative URLs -> '#'; valid schemes / root-relative / fragment pass
# through unchanged. Every rendered link carries rel="noopener noreferrer".
SAFEHREF_BOUNDARY_CASES: list[tuple[str, str]] = [
    # --- obfuscated / dangerous -> '#' ---
    ("[x]( javascript:alert(1))", "#"),  # leading space
    ("[x](\tjavascript:alert(1))", "#"),  # leading tab
    ("[x](\njavascript:alert(1))", "#"),  # leading newline
    ("[x](JAVASCRIPT:alert(1))", "#"),  # upper-case scheme
    ("[x](JaVaScRiPt:alert(1))", "#"),  # mixed-case scheme
    ("[x](java\tscript:alert(1))", "#"),  # control char inside scheme
    ("[x](vbscript:msgbox(1))", "#"),  # vbscript:
    ("[x](VBScript:msgbox(1))", "#"),  # vbscript: mixed case
    ("[x](data:text/html,foo)", "#"),  # data:
    ("[x](file:///etc/passwd)", "#"),  # file:
    ("[x](//evil.com/path)", "#"),  # protocol-relative (F4 hardening)
    ("[x]( //evil.com)", "#"),  # protocol-relative w/ leading space
    # --- valid -> pass through unchanged ---
    ("[x](https://ok.com)", "https://ok.com"),
    ("[x](http://ok.com)", "http://ok.com"),
    ("[x](mailto:a@b.com)", "mailto:a@b.com"),
    ("[x](tel:+15551234567)", "tel:+15551234567"),
    ("[x](/rel/path)", "/rel/path"),  # root-relative (single slash) is safe
    ("[x](#frag)", "#frag"),
]


@pytest.mark.browser
@pytest.mark.parametrize("source, expected_href", SAFEHREF_BOUNDARY_CASES)
def test_markdown_safehref_boundary(page_with_app: Page, source: str, expected_href: str) -> None:
    """safeHref boundary: obfuscated/dangerous/protocol-relative hrefs collapse
    to ``#``; valid schemes pass through; every link is ``rel="noopener
    noreferrer"``."""
    result = page_with_app.evaluate(
        """(src) => {
            const host = document.createElement('div');
            host.appendChild(App.markdown.render(src));
            const a = host.querySelector('a');
            return a ? { href: a.getAttribute('href'), rel: a.getAttribute('rel') } : null;
        }""",
        source,
    )
    assert result is not None, f"no <a> rendered for {source!r}"
    assert result["href"] == expected_href, f"href mismatch for {source!r}"
    assert result["rel"] == "noopener noreferrer"


@pytest.mark.browser
def test_markdown_codefence_lang_is_class_attr_only(page_with_app: Page) -> None:
    """A code-fence language tag carrying an attribute-injection payload lands
    ONLY as the ``<code>`` class value (via setAttribute — no HTML parse), never
    as a real event-handler attribute or a new element."""
    source = '```js" onmouseover="alert(1)\ncode line\n```'
    result = page_with_app.evaluate(
        """(src) => {
            const host = document.createElement('div');
            host.appendChild(App.markdown.render(src));
            const code = host.querySelector('pre code');
            return {
                attrNames: Array.from(code.attributes).map((a) => a.name),
                cls: code.getAttribute('class'),
                onmouseover: code.getAttribute('onmouseover'),
            };
        }""",
        source,
    )
    # The injection is trapped inside the single class value; setAttribute does
    # not parse it into a second attribute.
    assert result["attrNames"] == ["class"]
    assert result["onmouseover"] is None
    assert result["cls"] == 'language-js" onmouseover="alert(1)'


# Streaming-boundary prefixes: what commitSafeBoundary() feeds to
# App.markdown.render() for a committed prefix mid-stream. A half-written
# javascript: link — sliced at ANY boundary — must never emit a live unsafe
# href: malformed links fall back to literal text; complete ones pass through
# safeHref. (findSafeRenderBoundary only chooses WHERE to cut; whatever prefix
# is committed still goes through render()'s safeHref chokepoint.)
STREAMING_BOUNDARY_PREFIXES: list[str] = [
    "[x](javascript:",  # link opener, no closing paren -> literal text
    "[x](javascript:alert(1)",  # unbalanced paren -> literal text
    "[x](javascript:alert(1))",  # complete -> safeHref strips to '#'
    "before\n\n[x](javascript:alert(1))",  # committed after a blank-line boundary
    "[x](java\nscript:alert(1))",  # scheme split across a stream chunk
]


@pytest.mark.browser
@pytest.mark.parametrize("prefix", STREAMING_BOUNDARY_PREFIXES)
def test_markdown_streaming_boundary_no_live_unsafe_href(page_with_app: Page, prefix: str) -> None:
    """No committed streaming prefix — however sliced — emits an anchor whose
    href is a live ``javascript:``/``data:``/``vbscript:`` scheme."""
    hrefs = page_with_app.evaluate(
        """(src) => {
            const host = document.createElement('div');
            host.appendChild(App.markdown.render(src));
            return Array.from(host.querySelectorAll('a')).map((a) => a.getAttribute('href'));
        }""",
        prefix,
    )
    for href in hrefs:
        collapsed = href.strip().lower()
        assert not collapsed.startswith(("javascript:", "data:", "vbscript:")), (
            f"live unsafe href {href!r} emitted for streaming prefix {prefix!r}"
        )
