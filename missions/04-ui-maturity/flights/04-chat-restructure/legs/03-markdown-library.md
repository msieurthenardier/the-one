# Leg: 03-markdown-library

**Status**: completed
**Flight**: [Chat Restructure — Components, Streaming & Markdown](../flight.md)

## Objective

Replace the 1-line `App.markdown = {}` stub at `static/js/markdown.js` with a hand-rolled CommonMark-subset markdown library exposing `App.markdown.parse(text) → AST`, `App.markdown.render(text) → DocumentFragment`, and `App.markdown.NodeType` constants. Renderer constructs DOM via `document.createElement` + `textContent` only — never `innerHTML`. Ship a parametrized browser-test corpus locking in the supported subset, including the v1 nested-emphasis non-recursive contract, and add a `copy` icon to `App.icons` plus a copy-to-clipboard affordance on rendered code blocks.

## Context

- F4 design decision (flight.md "Open Questions"): hand-rolled markdown over vendored libraries (Snarkdown / Marked) — supply-chain risk + extension flexibility outweighs the ~300-500 LOC cost.
- F4 design decision (flight.md "Design Decisions"): renderer uses `document.createElement` + `textContent` exclusively — XSS-safety is a structural property of the library, not a runtime policy. Future contributors cannot accidentally introduce HTML-string injection because the renderer never accepts HTML strings as input.
- F4 design decision: nested-emphasis is **non-recursive in v1**. Input `***word***` renders as `<em><strong>word</strong></em>` (outer-em-first, inner-strong). Full CommonMark "left/right flanking delimiter run" algorithm is v2+ scope. The test corpus locks this in.
- F4 design decision: code blocks render as `<pre><code class="language-{lang}">{text}</code></pre>` plus a copy-to-clipboard `<button>` overlay (top-right). Lucide `copy` icon added to `App.icons`. Button a11y: `aria-label="Copy code"`, `aria-hidden="true"` on the icon, "Copied!" announcement via the existing `App.showFlash(container, msg)` helper.
- F4 design decision: subset is paragraphs, ATX headers (`#` to `######`), fenced code blocks (triple backtick + optional language tag), blockquotes, ordered + unordered lists (one nesting level), horizontal rules (`---`/`***`), emphasis (`*` / `_`), strong (`**`), inline code (`` ` ``), links (`[text](url)`), soft breaks (single `\n`), hard breaks (trailing two spaces + `\n`).
- Out of subset (explicit non-goals for v1): tables, footnotes, definition lists, autolinks (bare URLs), reference-style links, HTML passthrough, recursive nested emphasis.
- Leg 01 created the stub at `static/js/markdown.js` (1 line). This leg replaces the file content. Script tag in `index.html` already loads it before the chat helpers — no script-order change.
- Leg 05 will integrate the library into chat (assistant-message rendering on `done`). Leg 03 ships the library standalone — the chat integration is leg 05's responsibility.
- `App.icons` ships Lucide icons (icons.js:11+). Adding a `copy` icon follows the existing pattern: paste the Lucide v0.265.0 SVG inline, add a key to the `Icons` object. `App.icon('copy')` will then return the SVG string, consumed by `el.innerHTML = App.icon('copy')` at the call site (the icon strings themselves are TRUSTED — they're our own constants, not user input — so this `innerHTML` use is safe; the markdown library never uses `innerHTML`).
- `App.showFlash(container, msg, isError?)` lives in app.js:209. It builds a `.app-flash` div with `role="status"` + `aria-live="polite"` (or `role="alert"` if `isError`), appends to the container, fades in/out over ~2.3s. Reusable for "Copied!" announcements.

## Inputs

- `static/js/markdown.js` exists with the leg-01 1-line stub: `(function () { window.App = window.App || {}; window.App.markdown = {}; })();`.
- `static/js/icons.js` exists with the Lucide icon catalog. `App.icons` and `App.icon(name)` are available at runtime.
- `static/index.html` loads `markdown.js` at line 28 — before any chat helper. No load-order change needed.
- `static/css/components.css` (post-leg-02, 287 LOC) — leg 03 may add small rules for the code-block copy-button overlay; or use existing tokens.
- All F1-F3 + F4-leg-01 + F4-leg-02 tests pass: 393 unit + 32 browser.
- `tests/browser/conftest.py` provides `app_clean`, `app_with_provider`, `app_with_agent` fixtures. `app_clean` is sufficient for markdown library tests — no agent/provider seeding needed since the tests load the app and call `page.evaluate("App.markdown.render(...)")` directly.
- `App.showFlash` available globally from app.js.

## Outputs

- `static/js/markdown.js` becomes the full library (~300-500 LOC). Public API:
  - `App.markdown.NodeType` — frozen object of node-type string constants: `PARAGRAPH`, `HEADING`, `CODE_BLOCK`, `BLOCKQUOTE`, `LIST`, `LIST_ITEM`, `HORIZONTAL_RULE`, `TEXT`, `EMPHASIS`, `STRONG`, `INLINE_CODE`, `LINK`, `SOFT_BREAK`, `HARD_BREAK`.
  - `App.markdown.parse(text: string) → AST` — returns `{type: 'document', children: Node[]}`. Each block-level node is a child of `document`. Inline nodes are children of paragraphs / headings / list items.
  - `App.markdown.render(text: string) → DocumentFragment` — returns a `DocumentFragment` containing the rendered DOM tree. Caller appends to a parent. Pipeline internally: `parse` → AST → DOM construction.
  - AST node shape: `{type: NodeType_value, children?: Node[], value?: string, meta?: object}`. Examples:
    - Paragraph: `{type: 'paragraph', children: [...inline]}`
    - Heading: `{type: 'heading', meta: {level: 1..6}, children: [...inline]}`
    - Code block: `{type: 'codeBlock', meta: {lang: string|null}, value: string}` (no children — value is the raw code)
    - Blockquote: `{type: 'blockquote', children: [...block]}`
    - List: `{type: 'list', meta: {ordered: bool, start: number|null}, children: [...listItem]}`
    - List item: `{type: 'listItem', children: [...block]}` (the children are block-level — typically paragraphs)
    - HR: `{type: 'horizontalRule'}` (no children)
    - Text: `{type: 'text', value: string}`
    - Emphasis: `{type: 'emphasis', children: [...inline]}`
    - Strong: `{type: 'strong', children: [...inline]}`
    - Inline code: `{type: 'inlineCode', value: string}`
    - Link: `{type: 'link', meta: {href: string}, children: [...inline]}`
    - Soft break: `{type: 'softBreak'}` (no children)
    - Hard break: `{type: 'hardBreak'}` (no children)
  - Renderer maps each node type to DOM construction:
    - `paragraph` → `<p>` (children rendered into it)
    - `heading` → `<h1>`..`<h6>` (level from meta)
    - `codeBlock` → `<pre><code class="language-{lang}">{value via textContent}</code></pre>` plus a `<button class="markdown-copy-btn" aria-label="Copy code" type="button">{copy icon}</button>` positioned via CSS top-right; click handler copies `code.textContent` via `navigator.clipboard.writeText(...)` and calls `App.showFlash(<the pre's parent or a containing element>, 'Copied!')`. The `<pre>` is wrapped in a `<div class="markdown-code-wrap">` so the button can be positioned absolutely without leaking out.
    - `blockquote` → `<blockquote>` (children rendered into it)
    - `list` → `<ul>` or `<ol>` (depends on meta.ordered); if `ol` and meta.start != null, set the `start` attribute via `setAttribute`.
    - `listItem` → `<li>` (children rendered into it)
    - `horizontalRule` → `<hr>`
    - `text` → text node via `document.createTextNode(value)`
    - `emphasis` → `<em>` (children rendered into it)
    - `strong` → `<strong>` (children rendered into it)
    - `inlineCode` → `<code>` with `textContent = value`
    - `link` → `<a>` with `setAttribute('href', meta.href)`; `setAttribute('rel', 'noopener noreferrer')` because the href may be a user-provided URL; if href starts with `javascript:` or `data:`, **strip to `#` (or omit)** to prevent script-injection via crafted markdown — the `a:href` is the one place that accepts user-controlled URL strings, so it gets a tiny allow-list (`http:`, `https:`, `mailto:`, relative `/`, fragment `#`) check. Document this in the library header comment.
    - `softBreak` → text node containing a single space (CommonMark's "soft line break" semantic — renders as a space, not a `<br>`)
    - `hardBreak` → `<br>`
- `static/js/icons.js` gains a `copy` entry (Lucide `copy` icon at v0.265.0 — paste the SVG inline matching the existing pattern).
- `static/css/components.css` gains rules for the code-block copy affordance: `.markdown-code-wrap { position: relative; }`, `.markdown-copy-btn { position: absolute; top: 8px; right: 8px; ... }` plus hover/focus-visible accent ring matching the existing button family. Total addition ~10-15 LOC.
- `tests/browser/test_markdown.py` — NEW test module with parametrized cases (target: ~50-80 cases). Loads any page that boots the app, calls `page.evaluate` against `App.markdown.parse` and `App.markdown.render`. Asserts AST shape OR rendered HTML structure as appropriate per case. **Test count net delta: +1 file, +50-80 cases.** Updates the leg-02 baseline of 32 browser tests to a new baseline (the leg's acceptance criteria document the exact post-leg count).
- `tests/browser/test_markdown.py` also includes a small e2e case verifying the copy-to-clipboard path: render a code block in a fixture page, click the copy button, assert clipboard contains the code text and the "Copied!" flash appears.
- `the_one/agents.md` gains a "Markdown rendering" subsection under the Design system / a new top-level subsection — designer's choice — documenting:
  - Public API (`App.markdown.parse`, `App.markdown.render`, `App.markdown.NodeType`)
  - AST node shape contract
  - Supported subset (the 13 constructs)
  - Out-of-subset list (tables, footnotes, autolinks, reference-style links, HTML passthrough, recursive nested emphasis)
  - XSS guarantee (no innerHTML; href allow-list)
  - Extension contract: new node type + parser case + renderer branch + test cases land together
  - Nested-emphasis v1 contract (non-recursive; outer-em-first)
  - Code-block copy-button a11y contract

## Acceptance Criteria

- [x] `static/js/markdown.js` exposes `App.markdown.parse`, `App.markdown.render`, `App.markdown.NodeType` (the latter is a frozen object with all 14 node-type string constants).
- [x] `App.markdown.render` returns a `DocumentFragment` instance; the entire returned tree is built via `document.createElement`, `document.createTextNode`, `setAttribute`, `appendChild`, and `textContent`. **No `innerHTML` writes** anywhere in markdown.js (verified by `grep -n 'innerHTML' static/js/markdown.js` returning zero hits — including the icon injection on the copy button, which uses `DOMParser().parseFromString(svg, 'image/svg+xml').documentElement` instead).
- [x] Code-block copy button: clicking it copies `code.textContent` via `navigator.clipboard.writeText` and emits an "Copied!" flash via `App.showFlash`. The button has `aria-label="Copy code"` and the `<svg>` icon inside has `aria-hidden="true"` (already true via the icons.js Lucide template).
- [x] Link href safety: a markdown input of `[click me](javascript:alert(1))` renders as `<a href="#">click me</a>` (or similar — the `javascript:` URL is stripped, NOT executed). Same for `data:` URLs. Allowed schemes: `http`, `https`, `mailto`, plus relative paths starting with `/` or fragments starting with `#`.
- [x] Nested-emphasis v1 contract: `***word***` parses to `{type:'emphasis', children:[{type:'strong', children:[{type:'text', value:'word'}]}]}` and renders to `<em><strong>word</strong></em>`. Confirmed by an explicit test case.
- [x] All 13 user-authored constructs have at least 3 parametrized test cases each (~40 tests minimum) plus boundary-case tests (empty input, paragraph with multiple inline emphasis runs, list-item with code, etc.) bringing the total to ~50-80. (`text` is the 14th `NodeType` constant but is not user-authored markdown — it appears as inline content inside paragraphs, headings, list items, and other inline-bearing nodes; coverage is implicit through those tests.)
- [x] `tests/browser/test_markdown.py` collects + passes. New baseline browser-test count is `32 + N` where `N` is the number of `test_markdown.py` cases (single test file, all parametrized — exact count documented in the flight log).
- [x] `pytest --timeout=60 tests/` passes 393/393 (no unit-test regression).
- [x] `pytest --timeout=120 -m browser tests/browser/` passes (32 + N)/(32 + N) — no regressions in the existing 32 cases.
- [x] `static/css/components.css` LOC grows by ~10-15 (target: ≤ 305 total post-leg, was 287) for the copy-button rules.
- [x] `static/js/icons.js` has a new `copy` entry. `App.icon('copy')` returns a non-empty SVG string at runtime.
- [x] `static/js/markdown.js` total LOC ≤ 600 (leeway target: ~300-500 per the flight spec; cap is generous to allow for the test-driven completeness without forcing premature compression).
- [x] `the_one/agents.md` contains a "Markdown rendering" subsection documenting the public API, AST shape, supported subset, out-of-subset list, XSS guarantee, extension contract, nested-emphasis v1 contract, and copy-button a11y contract.
- [x] No new external dependencies introduced (`pyproject.toml` unchanged).
- [x] `App.markdown.parse('')` returns `{type: 'document', children: []}` (empty input is well-defined). `App.markdown.render('')` returns an empty `DocumentFragment`.
- [x] `App.markdown.parse(undefined)` and `App.markdown.parse(null)` **coerce to empty string** (not throw) — robust against partial-state passes during streaming. Same for `render(undefined)` / `render(null)` — return an empty `DocumentFragment`. Document the choice in agents.md.
- [x] Code-block with no language tag (` ``` ` only): renders as `<pre><code>...</code></pre>` with NO `class` attribute on the `<code>` element. Locked in by a render-test case.
- [x] Single trailing space + `\n` (e.g., `"a \nb"`) is a soft break, not a hard break — consistent with the "trailing TWO spaces" hard-break trigger. Locked in by a render-test case.

## Verification Steps

- File presence: `cat static/js/markdown.js | head -1` shows the new IIFE opener (not the 1-line stub).
- API check: `grep -E 'App\.markdown\.(parse|render|NodeType)' static/js/markdown.js` returns hits.
- innerHTML grep: `grep -n innerHTML static/js/markdown.js` returns 0 hits (excluding comments).
- Tests: `pytest --timeout=60 tests/` passes 393/393. `pytest --timeout=120 -m browser tests/browser/` passes the new baseline `(32 + N)`/`(32 + N)`.
- Manual test (Flight Director or human): run the dev server, open the browser console at `http://localhost:8080/`, paste:
  ```js
  var f = App.markdown.render("# Hello\n\nThis is **strong** and *em* and `code`.\n\n```js\nconsole.log(1);\n```\n\n- a\n- b");
  document.body.appendChild(f);
  ```
  Confirm the rendered DOM looks correct: `<h1>` heading, paragraph with `<strong>`/`<em>`/`<code>`, code block with copy button, unordered list. Click the copy button — the code copies; the "Copied!" flash appears.
- XSS structural check: paste `App.markdown.render('[evil](javascript:alert(1))')` — the link's href should be `#` (or the link should be omitted), NOT `javascript:alert(1)`. There should be no JS execution.

## Implementation Guidance

This leg is the largest of the flight by raw LOC count. The work breaks into 6 sub-pieces; treat them as independent commits-equivalent (but DO NOT commit per the deferred-commit model — the whole flight commits at the end).

### 1. NodeType constants

At the top of the IIFE, declare:

```js
var NodeType = Object.freeze({
  DOCUMENT: 'document',
  PARAGRAPH: 'paragraph',
  HEADING: 'heading',
  CODE_BLOCK: 'codeBlock',
  BLOCKQUOTE: 'blockquote',
  LIST: 'list',
  LIST_ITEM: 'listItem',
  HORIZONTAL_RULE: 'horizontalRule',
  TEXT: 'text',
  EMPHASIS: 'emphasis',
  STRONG: 'strong',
  INLINE_CODE: 'inlineCode',
  LINK: 'link',
  SOFT_BREAK: 'softBreak',
  HARD_BREAK: 'hardBreak'
});
```

`Object.freeze` prevents mutation. Note: the AST node `type` field uses the string VALUES (`'paragraph'`, etc.) — `NodeType.PARAGRAPH === 'paragraph'`. This makes node-type comparisons in tests both ergonomic (`node.type === 'paragraph'`) and namespace-safe (`node.type === NodeType.PARAGRAPH`).

### 2. Tokenizer / block-level parser

Walk the input line-by-line. The block-level recogniser:

```
1. Split on \n → array of lines.
2. State machine: walk lines; when a block starts (per the rules below), consume until the block ends.
3. Block start rules:
   - `^#{1,6}\s+` → heading (one line; consume line; remainder of line is heading content)
   - `^```(.*)$` → fenced code block start; consume lines until `^```$`; the captured (.*) is the language tag (or null if empty); the consumed text is the code value
   - `^\s*>(.*)$` → blockquote start; consume consecutive `>`-prefixed lines; recursively parse the unprefixed content
   - `^(\s*)([-*+]|\d+\.)\s+` → list start; ordered if `\d+\.`, unordered if `[-*+]`; consume consecutive list-marker lines; each list item's content is recursively parsed (block-level — typically a paragraph)
   - `^\s*(---+|\*\*\*+)\s*$` → horizontal rule (one line)
   - blank line → paragraph terminator
   - default → paragraph (consume consecutive non-blank, non-block-start lines)
```

**One-level list nesting**: a list-item's content can include a NESTED list ONLY if the nested list-marker line is indented with at least 2 spaces relative to the parent marker. This is the "one nesting level" cap. Deeper nesting is parsed as a paragraph (intentional v1 limitation).

The parser returns `{type: 'document', children: [Node, ...]}`.

### 3. Inline parser

For each block whose content is inline (`paragraph`, `heading`, `listItem`'s paragraph children), run the inline parser:

```
Walk the text character-by-character. Recognise:
- ` ` (single space at end of line followed by \n): hard break (emit hardBreak node, skip past the \n)
- \n inside a paragraph (not preceded by 2+ spaces): soft break (emit softBreak node)
- ** (or __): strong delimiter
- *  (or _): emphasis delimiter
- `: inline code delimiter (consume up to next `, value is the text between)
- [: link start; scan for matching ](url) — if found, emit link node with the url (after scheme allow-list); else treat the [ as literal text
- All other text: collected into text nodes
```

**Nested-emphasis non-recursive contract** — the parser carries an `inEmphasisRun: bool` flag while walking inline content:

1. When scanning a fresh inline run (`inEmphasisRun = false`), recognise emphasis/strong delimiters by length: `***` opens `<em><strong>` (BOTH levels at once — emit a `strong` node nested inside an `emphasis` node, both consuming `***...***` as their content boundary); `**` opens `<strong>`; `*` opens `<em>`. (Same for `_`/`__`/`___`.)
2. When scanning content INSIDE an emphasis or strong run (`inEmphasisRun = true`), emphasis/strong delimiters are **NOT recognised** — they are emitted as literal text. Inline code, links, soft breaks, hard breaks, and plain text continue to be recognised.

This produces:
- `***word***` → `{type:'emphasis', children:[{type:'strong', children:[{type:'text', value:'word'}]}]}` — the `***` opens BOTH levels (length-3 case), and `word` is parsed under `inEmphasisRun = true` (no further emphasis nesting needed since the inner content is just text).
- `**bold *with em***` → `{type:'strong', children:[{type:'text', value:'bold *with em*'}]}` — the leading `**` opens strong; inside (with `inEmphasisRun = true`) the `*with em*` substring is literal text, not emphasis; the trailing `**` closes strong; the trailing `*` is consumed as part of the closing scan or emitted as literal.

The boundary case `**bold *with em***` is locked in by an explicit AST_CASE and RENDER_CASE in the test corpus — both confirming the inner `*with em*` is literal text. (Recursive emphasis is v2 scope; the suppression flag is the structural mechanism that produces v1's contract.)

### 4. Renderer (DOM construction)

Walk the AST. For each node, build the DOM via `document.createElement` etc. NEVER `innerHTML`. The renderer is pure — given the same AST, returns the same DOM (modulo identity).

Code-block special case: wrap in `.markdown-code-wrap` div, build the `<pre><code>` inside, append a `<button class="markdown-copy-btn">` overlay. The button's icon is constructed via `DOMParser` to keep the no-innerHTML invariant intact:

```js
function injectIcon(parent, name) {
  var doc = new DOMParser().parseFromString(App.icon(name), 'image/svg+xml');
  parent.appendChild(doc.documentElement);
}
injectIcon(copyBtn, 'copy');
```

This parses the trusted icons.js SVG string into a real `<svg>` element and appends it. Same end result as `innerHTML = svgString` but the `grep -n innerHTML markdown.js` invariant holds literally.

**Null-lang code-block rendering**: when `meta.lang` is null, omit the `class` attribute entirely (do NOT emit `class="language-null"` or `class=""`). Concretely: `if (node.meta.lang) codeEl.setAttribute('class', 'language-' + node.meta.lang);` — only set when truthy.

Click handler:

```js
copyBtn.addEventListener('click', function () {
  navigator.clipboard.writeText(codeEl.textContent).then(function () {
    App.showFlash(wrap, 'Copied!');
  }).catch(function () {
    App.showFlash(wrap, 'Copy failed', true);
  });
});
```

`wrap` = the `.markdown-code-wrap` div. The flash positioning is fine — `App.showFlash` uses `position: fixed` so it doesn't matter which container it's appended to.

### 5. Link href allow-list

Inline parser, link case:

```js
function safeHref(href) {
  // Allow http(s):, mailto:, tel:, relative paths, and fragments.
  if (/^(https?:|mailto:|tel:|\/|#)/i.test(href)) return href;
  return '#';
}
```

Apply in the inline parser when constructing the link node. The renderer trusts the AST's href value as already-safe. `tel:` is included because chat assistants commonly produce phone-number links. Other schemes (notably `javascript:`, `data:`, `vbscript:`, `file:`) fall through to `#`.

**Link parens in URL**: implement a paren-balance counter inside the URL parser so `[wiki](https://en.wikipedia.org/wiki/Foo_(bar))` correctly captures the full URL including the inner `(bar)`. Track the open-paren depth as the URL parser consumes characters; only treat `)` as the URL terminator when the depth reaches zero. Cost: ~5 LOC; saves a real chat-content failure mode that would bite users.

### 6. CSS for the copy button

Add to `static/css/components.css` under `@layer components`:

```css
.markdown-code-wrap {
  position: relative;
}
.markdown-copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--panel-radius-sm);
  padding: 4px 6px;
  color: var(--fg-muted);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s, border-color 0.15s;
}
.markdown-code-wrap:hover .markdown-copy-btn,
.markdown-code-wrap:focus-within .markdown-copy-btn {
  opacity: 1;
}
.markdown-copy-btn:hover {
  opacity: 1;          /* defence-in-depth: hover on the button itself stays visible even if pointer leaves the wrap */
  color: var(--fg);
  border-color: var(--accent);
}
.markdown-copy-btn:focus-visible {
  opacity: 1;
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  box-shadow: 0 0 0 3px var(--accent-glow);
}
.markdown-copy-btn svg {
  width: 14px;
  height: 14px;
  display: block;
}
```

Note the `:focus-within` reveal on the wrapper — keyboard users can Tab to the copy button and it becomes visible. This matches the F3 keyboard-operability convention.

### 7. Lucide `copy` icon

Add to `static/js/icons.js` `Icons` object (insert in the existing alphabetical-ish ordering — near `download`, line 37):

```js
copy: '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>',
```

(Source: Lucide v0.265.0 `copy` icon, MIT License.)

### 8. Browser test corpus

Create `tests/browser/test_markdown.py`. Use a single fixture-loaded page (no agent/provider seeding needed — the `app_clean` fixture suffices) and parametrize across input/expected pairs.

```python
import pytest
from playwright.sync_api import Page

@pytest.fixture(scope='module')
def page_with_app(app_clean: str, browser):
    """A single page loaded for the markdown-corpus parametrized tests.

    `clipboard-read`/`clipboard-write` permissions are granted so the
    code-block copy-button e2e tests the success path (not the error
    fallback). Headless Chromium needs explicit permission to satisfy
    `navigator.clipboard.writeText`.
    """
    context = browser.new_context(permissions=['clipboard-read', 'clipboard-write'])
    page = context.new_page()
    page.goto(app_clean)
    # Wait for App.markdown to be defined (script-load order guarantees this).
    page.wait_for_function("typeof App !== 'undefined' && typeof App.markdown !== 'undefined' && typeof App.markdown.render === 'function'", timeout=5000)
    yield page
    context.close()


# AST-shape tests
AST_CASES = [
    ('# Hello', {'type': 'document', 'children': [{'type': 'heading', 'meta': {'level': 1}, 'children': [{'type': 'text', 'value': 'Hello'}]}]}),
    ('## A *b* c', ...),
    # ... ~30 cases covering each block + inline construct
]

@pytest.mark.browser
@pytest.mark.parametrize('source, expected', AST_CASES)
def test_markdown_parse_ast(page_with_app: Page, source: str, expected: dict) -> None:
    result = page_with_app.evaluate("(src) => App.markdown.parse(src)", source)
    assert result == expected


# Rendered-DOM-shape tests (via outerHTML strings — XSS-safety property is structural)
RENDER_CASES = [
    ('# Hi', '<h1>Hi</h1>'),
    ('**bold**', '<p><strong>bold</strong></p>'),
    ('***word***', '<p><em><strong>word</strong></em></p>'),  # nested-emphasis v1 contract
    ('[click me](javascript:alert(1))', '<p><a href="#" rel="noopener noreferrer">click me</a></p>'),  # XSS hardening
    ('[ok](https://example.com)', '<p><a href="https://example.com" rel="noopener noreferrer">ok</a></p>'),
    # ... ~30 cases
]

@pytest.mark.browser
@pytest.mark.parametrize('source, expected', RENDER_CASES)
def test_markdown_render_html(page_with_app: Page, source: str, expected: str) -> None:
    """Render to a temp container; assert outerHTML matches expected.

    Note: `expected` is the inner HTML of the document fragment (since
    DocumentFragment has no outerHTML). We reattach via a host div.
    """
    result = page_with_app.evaluate(
        """(src) => {
            const host = document.createElement('div');
            host.appendChild(App.markdown.render(src));
            return host.innerHTML;
        }""",
        source
    )
    assert result == expected


# Code-block copy-button e2e
@pytest.mark.browser
def test_markdown_copy_button(page_with_app: Page) -> None:
    # Module-scoped page accumulates DOM across tests; clean before this case.
    page_with_app.evaluate("() => { document.body.innerHTML = ''; }")
    page_with_app.evaluate(
        """() => {
            const host = document.createElement('div');
            host.id = 'md-test-host';
            host.appendChild(App.markdown.render('```js\\nconsole.log(1);\\n```'));
            document.body.appendChild(host);
        }"""
    )
    btn = page_with_app.locator('#md-test-host .markdown-copy-btn')
    btn.click(force=True)  # force=True bypasses the opacity check (button is visible-on-hover)
    # Assert the SUCCESS flash appeared — context has clipboard permissions, so the
    # writeText() promise resolves and the success path runs. (If permissions were
    # absent, the catch path would emit "Copy failed" — and this assertion would
    # rightly fail.)
    flash = page_with_app.locator('.app-flash').filter(has_text='Copied!')
    flash.wait_for(state='visible', timeout=2000)
    # Verify clipboard contents — round-trips via the granted clipboard-read permission.
    clipboard_text = page_with_app.evaluate("() => navigator.clipboard.readText()")
    assert clipboard_text == 'console.log(1);\n'
```

**Target test count**: AST_CASES + RENDER_CASES + ~5 boundary cases + 1 copy-button case ≈ **60-80 cases**. Document the exact post-leg browser test count in the flight log (e.g., `32 + 67 = 99`).

The corpus should cover EACH of the 13 constructs with at least 3 cases (basic, edge, boundary). Specifically:

- **paragraph**: simple text, paragraph with soft break, paragraph with hard break
- **heading**: h1-h6 (6 cases), heading with inline emphasis, heading-must-have-space-after-hash boundary
- **codeBlock**: with language tag, without language tag, multiline content
- **blockquote**: single line, multi-line, with inline emphasis
- **list (unordered)**: dashes, asterisks, plus signs (3 cases), nested 2-space-indent list
- **list (ordered)**: 1., starting at 5., with multi-line items
- **horizontalRule**: `---`, `***`, `------`
- **emphasis**: `*x*`, `_x_`, mid-word `*x*y` boundary
- **strong**: `**x**`, `__x__`, mixed delimiters
- **inlineCode**: simple, with characters that look like markdown
- **link**: simple, with title-attribute (NOT supported in v1 — verify graceful), with relative href, with javascript: (XSS-hardened), with mailto:
- **softBreak**: paragraph with internal newline
- **hardBreak**: trailing-2-spaces newline

Plus the v1 nested-emphasis contract case.

### 9. agents.md update

Add a top-level subsection. Suggested placement: after the existing "Design system" section, as a new sibling section "Markdown rendering". Content:

```markdown
## Markdown rendering

Hand-rolled CommonMark-subset library at `static/js/markdown.js`. Public API:

- `App.markdown.parse(text) → AST` — `{type: 'document', children: Node[]}`. Walk the tree to inspect or transform.
- `App.markdown.render(text) → DocumentFragment` — caller appends the fragment to a parent.
- `App.markdown.NodeType` — frozen object with the string constants for all 14 node types.

### AST node shape

`{type: NodeType_value, children?: Node[], value?: string, meta?: object}`. Specific shapes documented in markdown.js header comment.

### Supported subset (v1)

paragraphs, ATX headers (`#` to `######`), fenced code blocks with optional language tag, blockquotes (single level), unordered + ordered lists (one nesting level), horizontal rules (`---` / `***`), emphasis (`*` or `_`), strong (`**` or `__`), inline code (`` ` ``), links (`[text](url)` — including URLs with balanced parens like Wikipedia citations), soft breaks (single `\n`), hard breaks (trailing TWO spaces + `\n`; a single trailing space + `\n` is a soft break, not hard).

### Out of subset (v1 non-goals)

tables, footnotes, definition lists, autolinks (bare URLs), reference-style links, HTML passthrough, recursive nested emphasis. The test corpus locks v1 in; adding any of these requires a new flight or leg with a corresponding test-case expansion.

### Nested-emphasis v1 contract

`***word***` renders as `<em><strong>word</strong></em>` (outer-em-first, inner-strong). Recursive nested emphasis (the full CommonMark "left/right flanking delimiter run" algorithm) is v2 scope. `**bold *with em***` renders as `<strong>bold *with em*</strong>` — the inner `*with em*` is literal text since recursive emphasis is off.

### XSS guarantee

Renderer constructs DOM via `document.createElement` + `textContent` exclusively. The library NEVER uses `innerHTML` — `grep -n innerHTML markdown.js` returns zero hits. The icons.js SVG string injection on the code-block copy button is done via `DOMParser().parseFromString(svg, 'image/svg+xml').documentElement` to keep the no-innerHTML invariant intact. Link `href` values pass through a scheme allow-list (`http`, `https`, `mailto`, `tel`, `/`, `#`); other schemes (notably `javascript:`, `data:`, `vbscript:`, `file:`) are stripped to `#`. Future contributors cannot accidentally introduce XSS via crafted markdown — the structural property of "no innerHTML anywhere in the markdown pipeline" makes this a compile-time guarantee.

### Streaming + flash attachment contract

Callers must attach the rendered `DocumentFragment` (or its host element) to the document tree BEFORE user interaction with the rendered DOM. The code-block copy button's "Copied!" flash uses `App.showFlash(container, msg)` which appends the flash element to the container; if the container is detached, the flash never becomes visible to the user. In leg 05's chat integration, this is naturally satisfied (rendered messages are appended to `.messages` which is in the document); test cases must explicitly attach via `document.body.appendChild(host)` before clicking.

### Extension contract

Adding a new construct: (1) add a NodeType constant, (2) add the tokeniser/parser case, (3) add the renderer branch, (4) add at least 3 parametrized test cases. All four land together in the same leg or flight. PRs that add a parser case without test cases (or vice versa) fail review.

### Code-block copy-button a11y

`<button class="markdown-copy-btn" aria-label="Copy code" type="button">` with `aria-hidden="true"` on the SVG icon. On click, copies `<code>.textContent` via `navigator.clipboard.writeText`; on success, emits a "Copied!" flash via `App.showFlash`; on failure (clipboard permission denied), emits a "Copy failed" error flash. Keyboard-reachable via Tab (the button is in the natural tab order); `:focus-within` on the `.markdown-code-wrap` reveals the button so keyboard users see it before activating.
```

### 10. Run tests

```bash
pytest --timeout=60 tests/                          # 393/393 expected
pytest --timeout=120 -m browser tests/browser/      # (32 + N)/(32 + N) expected
```

If any test fails: investigate. The library is new code, so failing test cases mean genuine library bugs — not refactor regressions. Fix the library, not the tests.

### 11. Update flight log

Append a `### markdown-library` block under `## Leg Progress` summarising: status `landed`, started/completed timestamps, markdown.js LOC, components.css LOC delta, exact post-leg browser test count, the icons.js `copy` addition, and any deviations.

## Edge Cases

- **Empty input**: `parse('')` returns `{type: 'document', children: []}`; `render('')` returns an empty DocumentFragment. Verified by a test case.
- **Whitespace-only input**: same as empty — no document children.
- **Unbalanced emphasis**: `*hello` (no closing `*`) — treat the `*` as literal text. Same for unbalanced `**`, `_`, `**_`. Test cases lock this in.
- **Code fence with no closing**: treat the rest of the input as code-block content. (Be lenient — common in interactive streaming use.)
- **List-item content with multiple paragraphs**: v1 supports a list-item containing a SINGLE paragraph. Multi-paragraph list items are out of scope; the second paragraph becomes a sibling of the list. Document this in agents.md.
- **Link with no closing `)`**: treat the entire `[text](...` as literal text.
- **Link with parentheses inside the URL**: SUPPORTED via paren-balance counter in the URL parser. E.g., `[wiki](https://en.wikipedia.org/wiki/Foo_(bar))` correctly captures the full URL including the inner `(bar)`. Test case locks this in.
- **`navigator.clipboard.writeText` rejected**: catch path emits an error flash. Test case is optional (the success path is what users hit).
- **Multiple emphasis on one line**: `*a* and *b*` — both should render as `<em>a</em>` and `<em>b</em>` independently.
- **Heading followed by paragraph with no blank line**: CommonMark requires a blank line; v1 follows. `# H\nparagraph` renders the `paragraph` as part of the heading's text. Acceptable; document.
- **Very long input**: no specific length cap. The library is O(n) in input size. Performance is fine for chat messages of any realistic size.
- **Locked-down clipboard environment** (e.g., Playwright's headless with no clipboard permissions): `navigator.clipboard.writeText` may reject. The leg's test fixture grants `clipboard-read`/`clipboard-write` permissions on the browser context so the success path runs and the test asserts both the "Copied!" flash AND the clipboard contents.
- **Detached fragment + flash interaction**: `App.showFlash(container, msg)` calls `container.appendChild` then sets a visible-class via setTimeout. If the wrapper div is not attached to the document at click time, the flash element is appended to a detached node and is never visible to the user. Solution: callers always attach the rendered fragment before user interaction. Document in agents.md.

## Files Affected

- `the_one/interfaces/web/static/js/markdown.js` — REWRITE (1-line stub → full library, ~300-500 LOC; cap 600)
- `the_one/interfaces/web/static/js/icons.js` — UPDATE (add `copy` Lucide icon)
- `the_one/interfaces/web/static/css/components.css` — UPDATE (add `.markdown-code-wrap` + `.markdown-copy-btn` rules; ~10-15 LOC; total ≤ 305)
- `tests/browser/test_markdown.py` — NEW (~60-80 parametrized cases + 1 copy-button e2e)
- `the_one/agents.md` — UPDATE (new "Markdown rendering" subsection)
- `missions/04-ui-maturity/flights/04-chat-restructure/flight-log.md` — UPDATE (leg progress entry)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] `pytest --timeout=60 tests/` passes (393/393)
- [x] `pytest --timeout=120 -m browser tests/browser/` passes ((32 + N)/(32 + N) with N documented)
- [x] `grep -n innerHTML static/js/markdown.js` returns zero hits (excluding comments)
- [x] Update flight-log.md with leg progress entry under `## Leg Progress` (`### markdown-library` heading)
- [x] Set this leg's status to `landed` (in this file's header) — DO NOT set to `completed` and DO NOT commit; the flight-level review and commit run after the last autonomous leg per `/agentic-workflow`.
- [x] Signal `[HANDOFF:review-needed]`
