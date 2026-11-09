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
                "meta": {"lang": "js", "closed": True},
                "value": "console.log(1);\n",
            }
        ),
    ),
    (
        "```\nplain text\n```",
        _doc(
            {
                "type": "codeBlock",
                "meta": {"lang": None, "closed": True},
                "value": "plain text\n",
            }
        ),
    ),
    (
        "```python\na = 1\nb = 2\n```",
        _doc(
            {
                "type": "codeBlock",
                "meta": {"lang": "python", "closed": True},
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
        '<p><a href="https://example.com" rel="noopener noreferrer" target="_blank">ok</a></p>',
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
        '<p><a href="https://en.wikipedia.org/wiki/Foo_(bar)" rel="noopener noreferrer" target="_blank">wiki</a></p>',  # noqa: E501
    ),
    # --- code blocks: exact markup is asserted structurally in
    # test_markdown_code_block_structure (the copy button is the library control) ---
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
        '<div class="markdown-table-wrap" tabindex="0" role="region" aria-label="Table">'
        "<table>"
        "<thead><tr><th>a</th><th>b</th></tr></thead>"
        "<tbody><tr><td>1</td><td>2</td></tr></tbody>"
        "</table></div>",
    ),
    (
        "Name | Age\n---- | ---\nAlice | 30",
        '<div class="markdown-table-wrap" tabindex="0" role="region" aria-label="Table">'
        "<table>"
        "<thead><tr><th>Name</th><th>Age</th></tr></thead>"
        "<tbody><tr><td>Alice</td><td>30</td></tr></tbody>"
        "</table></div>",
    ),
    (
        "| **Key** | Value |\n| --- | --- |\n| `id` | 42 |",
        '<div class="markdown-table-wrap" tabindex="0" role="region" aria-label="Table">'
        "<table>"
        "<thead><tr><th><strong>Key</strong></th><th>Value</th></tr></thead>"
        "<tbody><tr><td><code>id</code></td><td>42</td></tr></tbody>"
        "</table></div>",
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
    """``App.markdown.NodeType`` exposes all 20 frozen string constants."""
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
        "STRIKE": "strike",
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
def test_markdown_code_block_structure(page_with_app: Page) -> None:
    """wrap > pre > code, one named library copy button, no inline SVG string or flash."""
    result = page_with_app.evaluate(
        """() => {
            const host = document.createElement('div');
            host.appendChild(App.markdown.render('```js\\nconsole.log(1);\\n```'));
            const wrap = host.firstElementChild;
            const btns = wrap.querySelectorAll('button.markdown-copy-btn[aria-label="Copy code"]');
            return {
                wrapClass: wrap.className,
                kids: Array.from(wrap.children).map((c) => c.tagName.toLowerCase()),
                preKid: wrap.querySelector(':scope > pre > code').className,
                buttons: btns.length,
                libButton: btns[0].classList.contains('btn-icon'),
                svgs: btns[0].querySelectorAll('svg').length,
                hasUiCopy: wrap.querySelector('.ui-copy') !== null,
            };
        }"""
    )
    assert result["wrapClass"] == "markdown-code-wrap"
    assert result["kids"][0] == "pre"
    assert result["preKid"] == "language-js"
    assert result["buttons"] == 1
    assert result["libButton"] is True
    assert result["svgs"] == 1
    assert result["hasUiCopy"] is False


@pytest.mark.browser
def test_markdown_copy_button(page_with_app: Page) -> None:
    """Clicking Copy code writes the code text to the clipboard and confirms in place."""
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
    assert btn.get_attribute("aria-label") == "Copy code"
    before = btn.inner_html()
    btn.click(force=True)
    page_with_app.wait_for_function(
        "() => document.querySelector('#md-test-host .markdown-copy-btn')"
        ".getAttribute('aria-label') === 'Copied'",
        timeout=2000,
    )
    assert btn.inner_html() != before  # the check icon replaced the copy icon
    status = page_with_app.locator("#md-test-host .markdown-code-wrap [role=status]")
    assert status.text_content() == "Copied"
    clipboard_text = page_with_app.evaluate("() => navigator.clipboard.readText()")
    assert clipboard_text == "console.log(1);\n"
    assert page_with_app.locator(".app-flash").count() == 0


@pytest.mark.browser
def test_markdown_copy_status_is_per_block_without_the_option_and_shared_with_it(
    page_with_app: Page,
) -> None:
    """No option: a role=status span in the wrap. With copyLiveEl: that node, no span."""
    page_with_app.evaluate("() => { document.body.innerHTML = ''; }")
    result = page_with_app.evaluate(
        """async () => {
            const md = '```\\nx\\n```';
            const plain = document.createElement('div');
            plain.appendChild(App.markdown.render(md));
            const shared = document.createElement('div');
            shared.setAttribute('role', 'status');
            const host = document.createElement('div');
            host.appendChild(App.markdown.render(md, {copyLiveEl: shared}));
            document.body.append(plain, shared, host);
            Object.defineProperty(navigator, 'clipboard', {configurable: true,
              value: {writeText: () => Promise.resolve()}});
            host.querySelector('.markdown-copy-btn').click();
            await new Promise(r => setTimeout(r, 200));
            return {
                plainSpans: plain.querySelectorAll('.markdown-code-wrap [role=status]').length,
                sharedSpans: host.querySelectorAll('[role=status]').length,
                sharedText: shared.textContent,
            };
        }"""
    )
    assert result == {"plainSpans": 1, "sharedSpans": 0, "sharedText": "Copied"}


@pytest.mark.browser
def test_markdown_code_wrap_adds_no_height(page_with_app: Page) -> None:
    """The copy control adds no inline box: the wrap is exactly the pre's height."""
    page_with_app.evaluate("() => { document.body.innerHTML = ''; }")
    result = page_with_app.evaluate(
        """() => {
            const host = document.createElement('div');
            host.className = 'ui-message ui-message--assistant';
            host.appendChild(App.markdown.render('```\\nx\\n```'));
            document.body.appendChild(host);
            const wrap = host.querySelector('.markdown-code-wrap');
            const pre = wrap.querySelector('pre');
            // The pre's vertical margins collapse through the wrap, so the wrap's own
            // height is exactly the pre's box when nothing else flows inside it.
            return {
                wrap: wrap.getBoundingClientRect().height,
                pre: pre.getBoundingClientRect().height,
            };
        }"""
    )
    assert abs(result["wrap"] - result["pre"]) < 1.0


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
    """A code-fence info string carrying an attribute-injection payload yields NO
    language class and no extra attribute or element.

    Rewritten in M31 F6 L07 (it used to pin ``cls == 'language-js" onmouseover=...'``,
    the whole info string landing in the class): the language is now the first
    whitespace token, kept only if it matches ``^[A-Za-z0-9_+#.-]{1,32}$``. The
    token here is ``js"`` (a quote), so it is rejected and the block has no class.
    A clean ``js`` still gives ``language-js`` (test_markdown_fence_class_is_one_valid_token).
    """
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
    assert result["attrNames"] == []
    assert result["onmouseover"] is None
    assert result["cls"] is None


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
    "see https://exa",  # URL cut mid-host -> at most a safe http(s) link
    "see https://example.com/a\\",  # cut right at a backslash -> stops before it
    "~~half",  # unclosed strike -> literal text
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


# ── Leg 07 hardening: negative tests (written before the fixes) ───────────────
#
# Each helper renders into a detached host so nothing leaks between cases.

_RENDER_JS = """(src) => {
    const host = document.createElement('div');
    host.appendChild(App.markdown.render(src));
    return host.innerHTML;
}"""

_ANCHORS_JS = """(src) => {
    const host = document.createElement('div');
    host.appendChild(App.markdown.render(src));
    return Array.from(host.querySelectorAll('a')).map((a) => ({
        href: a.getAttribute('href'),
        text: a.textContent,
        nested: a.querySelector('a') !== null,
    }));
}"""

# Backslash / whitespace / control paths: a browser URL parser treats `\` as `/` and drops
# tab/LF, so `/\evil` and `/<TAB>/evil` resolve to `//evil` (off-site). All collapse to '#'.
# Marked FAILING TODAY (they pass the old `^/` allow-list).
SAFEHREF_PATH_ESCAPE_CASES: list[tuple[str, str]] = [
    ("[x](/\\evil.example)", "#"),
    ("[x](/\t/evil.example)", "#"),
    ("[x](/\n/evil.example)", "#"),
    ("[x](\\/evil.example)", "#"),
    ("[x](https://ok.com/a\\b)", "#"),
    ("[x](https://ok.com/a\x01b)", "#"),
    ("[x](#a\x7fb)", "#"),
    ("[x](mailto:a@b.com\t)", "#"),
]


@pytest.mark.browser
@pytest.mark.parametrize("source, expected_href", SAFEHREF_PATH_ESCAPE_CASES)
def test_markdown_safehref_rejects_backslash_and_controls(
    page_with_app: Page, source: str, expected_href: str
) -> None:
    anchors = page_with_app.evaluate(_ANCHORS_JS, source)
    assert len(anchors) == 1, f"expected one anchor for {source!r}"
    assert anchors[0]["href"] == expected_href


# Regression guards (pass today): attribute injection and encoded schemes.
@pytest.mark.browser
@pytest.mark.parametrize(
    "source",
    [
        '[x](https://ok.com" onclick="alert(1))',
        "[x](javascript&colon;alert(1))",
        "[x](%6Aavascript:alert(1))",
        "[x](&#106;avascript:alert(1))",
    ],
)
def test_markdown_href_injection_and_encoded_schemes_regression(
    page_with_app: Page, source: str
) -> None:
    result = page_with_app.evaluate(
        """(src) => {
            const host = document.createElement('div');
            host.appendChild(App.markdown.render(src));
            const a = host.querySelector('a');
            return {
                attrs: Array.from(a.attributes).map((x) => x.name).sort(),
                href: a.getAttribute('href'),
            };
        }""",
        source,
    )
    assert result["attrs"] in (["href", "rel"], ["href", "rel", "target"])
    assert not result["href"].lower().startswith(("javascript", "%6a"))


@pytest.mark.browser
def test_markdown_same_origin_links_survive(page_with_app: Page) -> None:
    """A same-origin /path and #anchor still render as links with the original href."""
    anchors = page_with_app.evaluate(_ANCHORS_JS, "[a](/about?x=1#y) [b](#top)")
    assert [a["href"] for a in anchors] == ["/about?x=1#y", "#top"]


@pytest.mark.browser
@pytest.mark.parametrize(
    "source, cls",
    [
        ("```js is-hidden\nx\n```", "language-js"),
        ("```js\tis-hidden\nx\n```", "language-js"),
        ("```c++\nx\n```", "language-c++"),
        ("```objective-c\nx\n```", "language-objective-c"),
        ("```c#\nx\n```", "language-c#"),
        ('```js" onmouseover="alert(1)\nx\n```', None),
        ("```" + "a" * 33 + "\nx\n```", None),
        ("```\nx\n```", None),
    ],
)
def test_markdown_fence_class_is_one_valid_token(
    page_with_app: Page, source: str, cls: str | None
) -> None:
    """The fence info string yields at most one class token, from a strict charset."""
    result = page_with_app.evaluate(
        """(src) => {
            const host = document.createElement('div');
            host.appendChild(App.markdown.render(src));
            const code = host.querySelector('pre code');
            return {
                cls: code.getAttribute('class'),
                attrs: Array.from(code.attributes).map((a) => a.name),
            };
        }""",
        source,
    )
    assert result["cls"] == cls
    assert result["attrs"] == (["class"] if cls else [])


@pytest.mark.browser
@pytest.mark.parametrize(
    "source",
    [
        "[a [b](https://x.example)](https://y.example)",
        "[https://a.example](https://a.example)",
        "[see https://a.example now](https://b.example)",
    ],
)
def test_markdown_no_nested_anchors(page_with_app: Page, source: str) -> None:
    """A link label never holds another anchor (nested links and label autolinks)."""
    anchors = page_with_app.evaluate(_ANCHORS_JS, source)
    assert len(anchors) == 1
    assert anchors[0]["nested"] is False


# Autolink negatives (0.4).
@pytest.mark.browser
@pytest.mark.parametrize(
    "source",
    [
        "javascript:alert(1)",
        "see javascript:alert(1) here",
        "http://",
        "https:// alone",
        "foohttp://x.example",
        "`https://a.example`",
        "```\nhttps://a.example\n```",
        "mailto:a@b.com and www.example.com",
        "https://a.example/a\\b",
        "https://a.example/a\x01b",
    ],
)
def test_markdown_autolink_negatives(page_with_app: Page, source: str) -> None:
    """Text that must not become a link, and an autolink never emits href="#"."""
    anchors = page_with_app.evaluate(_ANCHORS_JS, source)
    for a in anchors:
        assert a["href"] != "#", f"autolink emitted '#' for {source!r}"
    assert anchors == [] or source.startswith("https://a.example/a")


@pytest.mark.browser
@pytest.mark.parametrize(
    "source, href, text, tail",
    [
        ("see (https://a.example/x).", "https://a.example/x", "https://a.example/x", ")."),
        ("go https://a.example/x, then", "https://a.example/x", "https://a.example/x", ", then"),
        ("https://a.example/x?", "https://a.example/x", "https://a.example/x", "?"),
        (
            "https://en.wikipedia.org/wiki/Foo_(bar)",
            "https://en.wikipedia.org/wiki/Foo_(bar)",
            "https://en.wikipedia.org/wiki/Foo_(bar)",
            "",
        ),
        (
            "(https://en.wikipedia.org/wiki/Foo_(bar))",
            "https://en.wikipedia.org/wiki/Foo_(bar)",
            "https://en.wikipedia.org/wiki/Foo_(bar)",
            ")",
        ),
        ("HTTP://A.EXAMPLE/x_y_z", "HTTP://A.EXAMPLE/x_y_z", "HTTP://A.EXAMPLE/x_y_z", ""),
    ],
)
def test_markdown_autolink_positive(
    page_with_app: Page, source: str, href: str, text: str, tail: str
) -> None:
    anchors = page_with_app.evaluate(_ANCHORS_JS, source)
    assert len(anchors) == 1, source
    assert anchors[0]["href"] == href
    assert anchors[0]["text"] == text
    html = page_with_app.evaluate(_RENDER_JS, source)
    assert html.endswith(tail + "</p>")


@pytest.mark.browser
def test_markdown_autolink_contexts(page_with_app: Page) -> None:
    """Autolinks work in headings, table cells, emphasis and list items."""
    for src in [
        "# see https://a.example",
        "| a | b |\n| - | - |\n| https://a.example | x |",
        "**see https://a.example**",
        "- https://a.example",
    ]:
        anchors = page_with_app.evaluate(_ANCHORS_JS, src)
        assert [a["href"] for a in anchors] == ["https://a.example"], src


@pytest.mark.browser
@pytest.mark.parametrize(
    "source, expected",
    [
        ("~~gone~~", "<p><del>gone</del></p>"),
        ("a ~~b~~ c", "<p>a <del>b</del> c</p>"),
        ("**~~x~~**", "<p><strong><del>x</del></strong></p>"),
        ("~~**x**~~", "<p><del><strong>x</strong></del></p>"),
        ("~single~", "<p>~single~</p>"),
        ("~~unclosed", "<p>~~unclosed</p>"),
        ("`~~code~~`", "<p><code>~~code~~</code></p>"),
        ("~~a `~~` b~~", "<p><del>a <code>~~</code> b</del></p>"),
        ("~~a\nb~~", "<p><del>a b</del></p>"),
        ("~~a\n\nb~~", "<p>~~a</p><p>b~~</p>"),
    ],
)
def test_markdown_strikethrough(page_with_app: Page, source: str, expected: str) -> None:
    assert page_with_app.evaluate(_RENDER_JS, source) == expected


@pytest.mark.browser
def test_markdown_strike_ast(page_with_app: Page) -> None:
    ast = page_with_app.evaluate("() => App.markdown.parse('~~x~~')")
    assert ast == _doc(_para({"type": "strike", "children": [_text("x")]}))


@pytest.mark.browser
def test_markdown_link_label_with_code_bracket(page_with_app: Page) -> None:
    anchors = page_with_app.evaluate(_ANCHORS_JS, "[`]`](https://a.example)")
    assert len(anchors) == 1
    assert anchors[0]["text"] == "]"


# ── Task lists (0.4) ──────────────────────────────────────────────────────────


def _task_summary(page: Page, src: str) -> list[dict]:
    return page.evaluate(
        """(src) => {
            const host = document.createElement('div');
            host.appendChild(App.markdown.render(src));
            return Array.from(host.querySelectorAll('li')).map((li) => {
                const box = li.querySelector(':scope > input');
                return {
                    cls: li.getAttribute('class'),
                    box: box ? {
                        type: box.type, disabled: box.disabled, checked: box.checked,
                        name: box.getAttribute('aria-label'),
                    } : null,
                    links: li.querySelectorAll(':scope > a').length,
                };
            });
        }""",
        src,
    )


@pytest.mark.browser
def test_markdown_task_list_ast(page_with_app: Page) -> None:
    ast = page_with_app.evaluate("() => App.markdown.parse('- [ ] a\\n- [x] b\\n- [X] c\\n- d')")
    items = ast["children"][0]["children"]
    assert [i.get("meta") for i in items] == [
        {"task": {"checked": False}},
        {"task": {"checked": True}},
        {"task": {"checked": True}},
        None,
    ]
    assert items[0]["children"] == [_para(_text("a"))]


@pytest.mark.browser
def test_markdown_task_list_render(page_with_app: Page) -> None:
    rows = _task_summary(page_with_app, "- [ ] write\n- [x] **ship** it\n- plain")
    assert rows[0] == {
        "cls": "markdown-task",
        "box": {"type": "checkbox", "disabled": True, "checked": False, "name": "write"},
        "links": 0,
    }
    assert rows[1]["box"] == {
        "type": "checkbox",
        "disabled": True,
        "checked": True,
        "name": "ship it",
    }
    assert rows[2] == {"cls": None, "box": None, "links": 0}


@pytest.mark.browser
def test_markdown_task_list_edge_cases(page_with_app: Page) -> None:
    # A link at the start of an item is not a task.
    rows = _task_summary(page_with_app, "- [x](https://a.example)")
    assert rows[0]["box"] is None and rows[0]["links"] == 1
    # No whitespace after the marker: not a task.
    assert _task_summary(page_with_app, "- [x]done")[0]["box"] is None
    # Ordered lists behave the same.
    rows = _task_summary(page_with_app, "1. [x] one\n2. [ ] two")
    assert [r["box"]["checked"] for r in rows] == [True, False]
    # Empty label: still a task, named "Task".
    rows = _task_summary(page_with_app, "- [ ]")
    assert rows[0]["box"]["name"] == "Task"
    # The name is the first paragraph only, never a nested sublist.
    rows = _task_summary(page_with_app, "- [ ] parent\n  - child")
    assert rows[0]["box"]["name"] == "parent"
    assert rows[1]["box"] is None


# ── A1 (reply headings) and B1 (wide tables) ──────────────────────────────────


@pytest.mark.browser
def test_markdown_reply_headings_on_type_tokens(page_with_app: Page) -> None:
    """h1..h6 in an assistant bubble: h1 <= --font-size-h1 (18px), and h1 >= ... >= h6."""
    page_with_app.evaluate("() => { document.body.innerHTML = ''; }")
    sizes = page_with_app.evaluate(
        """() => {
            const host = document.createElement('div');
            host.className = 'ui-message ui-message--assistant';
            host.appendChild(App.markdown.render(
                '# a\\n\\n## b\\n\\n### c\\n\\n#### d\\n\\n##### e\\n\\n###### f'));
            document.body.appendChild(host);
            const cap = parseFloat(getComputedStyle(document.documentElement)
                .getPropertyValue('--font-size-h1'));
            return {
                cap,
                sizes: ['h1','h2','h3','h4','h5','h6'].map(
                    (t) => parseFloat(getComputedStyle(host.querySelector(t)).fontSize)),
            };
        }"""
    )
    s = sizes["sizes"]
    assert s[0] <= (sizes["cap"] or 18)
    assert s == sorted(s, reverse=True)
    assert s[0] == 18 and s[1] == 16 and s[2] == 15


@pytest.mark.browser
def test_markdown_wide_table_scrolls_in_wrapper(page_with_app: Page) -> None:
    """A wide table scrolls inside its focusable region; the bubble does not overflow."""
    page_with_app.evaluate("() => { document.body.innerHTML = ''; }")
    long_cell = "x" * 160
    src = f"| a | b |\n| - | - |\n| {long_cell} | {long_cell} |"
    result = page_with_app.evaluate(
        """(src) => {
            const col = document.createElement('div');
            col.style.cssText = 'display:flex;flex-direction:column;width:420px';
            const host = document.createElement('div');
            host.className = 'ui-message ui-message--assistant';
            host.appendChild(App.markdown.render(src));
            col.appendChild(host);
            document.body.appendChild(col);
            const w = host.querySelector('.markdown-table-wrap');
            return {
                wrapScroll: w.scrollWidth, wrapClient: w.clientWidth,
                bubbleScroll: host.scrollWidth, bubbleClient: host.clientWidth,
                overflowX: getComputedStyle(w).overflowX,
                role: w.getAttribute('role'), label: w.getAttribute('aria-label'),
                tabindex: w.getAttribute('tabindex'),
            };
        }""",
        src,
    )
    assert result["wrapScroll"] > result["wrapClient"]
    assert result["bubbleScroll"] <= result["bubbleClient"]
    assert result["overflowX"] == "auto"
    assert (result["role"], result["label"], result["tabindex"]) == ("region", "Table", "0")


@pytest.mark.browser
@pytest.mark.parametrize(
    "url",
    [
        "https:\\\\evil.example",
        "https://ok.example/\\@evil",
        "https://ok.example\\path",
        "https://ok.exa\tmple/",
        "https://ok.example/\npath",
        "https://ok.example/\rpath",
        "https://ok.example/\x00",
        "https://ok.example/\x01",
        "https://ok.example/\x1f",
        "https://ok.example/\x7f",
        "\thttps://ok.example/",
        "\nhttps://ok.example/",
        " https://ok.example/",
        "//evil.example/",
        "javascript:alert(1)",
        "",
    ],
)
def test_safe_url_rejects_backslash_controls_and_other_schemes(
    page_with_app: Page, url: str
) -> None:
    """Squawk 0275: ``App.safeUrl`` fails closed on ``\\``, C0 controls and DEL."""
    assert page_with_app.evaluate("(u) => App.safeUrl(u)", url) is None


@pytest.mark.browser
@pytest.mark.parametrize(
    "url",
    [
        "https://ok.example/",
        "http://ok.example:8080/a/b?q=1&r=2#frag",
        "HTTPS://OK.EXAMPLE/Path",
        "https://ok.example/a%20b",
        "https://ok.example/path with space",
    ],
)
def test_safe_url_passes_ordinary_http_urls_unchanged(page_with_app: Page, url: str) -> None:
    assert page_with_app.evaluate("(u) => App.safeUrl(u)", url) == url


# ── codeBlockRenderers, re-entrancy and meta.closed (M35 F1 L2) ────────────────


@pytest.mark.browser
def test_code_block_renderers_replace_the_well_for_the_exact_lang(page_with_app: Page) -> None:
    """AC1: a renderer gets (source, {lang, closed}); the lang is the parser's first token."""
    result = page_with_app.evaluate(
        """() => {
          var calls = [];
          var opts = { codeBlockRenderers: { chart: function (src, meta) {
            calls.push([src, meta.lang, meta.closed]);
            var d = document.createElement('div');
            d.setAttribute('data-x', 'drawn');
            return d;
          } } };
          function html(t, o) {
            var host = document.createElement('div');
            host.appendChild(App.markdown.render(t, o));
            return host;
          }
          var a = html('```chart\\n{"a":1}\\n```\\n', opts);
          var b = html('```chart extra\\n{}\\n```\\n', opts);
          var c = html('```Chart\\n{}\\n```\\n', opts);
          var d = html('```python\\nx\\n```\\n', opts);
          var plain = '```chart\\n{"a":1}\\n```\\nafter\\n';
          return {
            a: a.querySelectorAll('[data-x]').length, aWell: a.querySelectorAll('pre').length,
            b: b.querySelectorAll('[data-x]').length,
            c: c.querySelectorAll('[data-x]').length, cWell: c.querySelectorAll('pre').length,
            d: d.querySelectorAll('[data-x]').length, dWell: d.querySelectorAll('pre').length,
            calls: calls,
            sameHtml: html(plain).innerHTML === html(plain, {}).innerHTML
          };
        }"""
    )
    assert result["a"] == 1 and result["aWell"] == 0
    assert result["b"] == 1
    assert result["c"] == 0 and result["cWell"] == 1
    assert result["d"] == 0 and result["dWell"] == 1
    assert result["calls"][0] == ['{"a":1}\n', "chart", True]
    assert result["sameHtml"] is True


@pytest.mark.browser
def test_code_block_renderer_falsy_non_node_and_throw_fall_back(page_with_app: Page) -> None:
    """AC1: a falsy or non-Node return, or a throw, gives the normal code well with its copy."""
    result = page_with_app.evaluate(
        """() => {
          var src = '```chart\\nx\\n```\\n';
          var out = [];
          [function () { return null; }, function () { return 'text'; },
           function () { return {}; }, function () { throw new Error('boom'); }
          ].forEach(function (fn) {
            var host = document.createElement('div');
            host.appendChild(App.markdown.render(src, { codeBlockRenderers: { chart: fn } }));
            out.push([host.querySelectorAll('pre').length,
                      host.querySelectorAll('.markdown-copy-btn').length]);
          });
          return out;
        }"""
    )
    assert result == [[1, 1]] * 4


@pytest.mark.browser
def test_code_block_renderers_ignore_inherited_names(page_with_app: Page) -> None:
    result = page_with_app.evaluate(
        """() => {
          var host = document.createElement('div');
          host.appendChild(App.markdown.render('```constructor\\nx\\n```\\n',
            { codeBlockRenderers: {} }));
          return host.querySelectorAll('pre').length;
        }"""
    )
    assert result == 1


@pytest.mark.browser
def test_render_restores_outer_options_when_a_renderer_renders(page_with_app: Page) -> None:
    """AC2: a renderer that calls render with other options leaves the outer options in force."""
    result = page_with_app.evaluate(
        """() => {
          var inner = 0;
          var opts = { codeBlockRenderers: { chart: function () {
            App.markdown.render('```x\\ny\\n```\\n', { copyLiveEl: null });
            inner++;
            var d = document.createElement('div');
            d.setAttribute('data-x', '1');
            return d;
          } } };
          var host = document.createElement('div');
          host.appendChild(App.markdown.render(
            '```chart\\na\\n```\\n\\n```chart\\nb\\n```\\n\\n```chart\\nc\\n```\\n', opts));
          return { drawn: host.querySelectorAll('[data-x]').length, inner: inner,
                   wells: host.querySelectorAll('pre').length };
        }"""
    )
    assert result == {"drawn": 3, "inner": 3, "wells": 0}


@pytest.mark.browser
@pytest.mark.parametrize(
    ("text", "closed"),
    [
        ("```chart\nx\n```\n", True),
        ("```chart\nx\n```", True),
        ("```chart\nx\n", False),
        ("```chart\n", False),
        ("- item\n  ```python\n  x = 1\n\nafter\n", False),
    ],
)
def test_parse_marks_whether_a_fence_closed(page_with_app: Page, text: str, closed: bool) -> None:
    """AC3: meta.closed is true only when a closing fence line was consumed."""
    result = page_with_app.evaluate(
        """(t) => {
          var found = [];
          (function walk(n) {
            if (n.type === 'codeBlock') found.push(n.meta.closed);
            (n.children || []).forEach(walk);
          })(App.markdown.parse(t));
          return found;
        }""",
        text,
    )
    assert result == [closed]
