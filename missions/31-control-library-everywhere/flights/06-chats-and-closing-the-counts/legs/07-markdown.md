# Leg: markdown

**Status**: ready
**Flight**: [Chats, and closing every count to zero](../flight.md)

## Objective
Harden and finish the markdown renderer (`js/markdown.js`), negative tests first:
- **Security (DD9):**
  - close the link escape (`\` and control characters, and the same-origin rule for `/` and `#`, D3 (a));
  - close the code-fence class injection (the first token only);
  - add the missing negative tests.
- **Presentation:**
  - A1: reply headings on the type tokens;
  - B1: wide tables in a sideways-scrolling wrapper.
- **0.4:** strikethrough, task lists and bare-URL links, each with negative cases.
- **The code-block Copy** becomes `App.ui.copyButton` icon-only with D1's confirmation (A2). That removes `injectIcon`'s SVG-string parse, `markdown.js`'s `App.icon` and `App.showFlash` calls and its two ownership rows.

## Context
- **Flight decisions:** DD8 (0.4), DD9 (the tests and fixes), DD7 (A1, A2, B1; ledger rows 1, 2, 19, 29 and 33), DD13 and DD15 (re-read `discord-markdown-links`).
- **The renderer** (`js/markdown.js`, 830 lines):
  - `NodeType` (`:62-82`) includes `TEXT`, `EMPHASIS`, `STRONG`, `INLINE_CODE`, `LINK`, `SOFT_BREAK`, `HARD_BREAK`, `LIST`/`LIST_ITEM`, `TABLE*`, `CODE_BLOCK`;
  - `safeHref` (`:104-122`): reject `^\s*\/\/`, then allow `^(https?:|mailto:|tel:|\/|#)/i`, else `#`;
  - `parseBlocks` (`:126`): the fence at `:151-154` keeps the **whole** remainder after the backticks as `lang`;
  - `parseList` (`:251`);
  - `parseInline` / `scanInline` (`:341-515`): characters `` ` ``, `[`, `*` and `_`; `findClosingDelim`, `parseLink` (`:548`), whose link label is parsed with `scanInline`, so a nested link is possible;
  - `injectIcon` (`:621-632`): `window.App.icon(name)` → `DOMParser` → append, with no `parsererror` check;
  - `renderNodes` (`:634`), `renderCodeBlock` (`:771-810`): `div.markdown-code-wrap`, `pre > code[class=language-…]`, and `button.markdown-copy-btn[aria-label="Copy code"]` with the icon. The click is `navigator.clipboard.writeText`, then `App.showFlash(wrap, 'Copied!' | 'Copy failed', …)`. Since leg 03a the toast goes to the page;
  - `render` (`:812`) returns a fragment; `App.markdown = {NodeType, parse, render}`.
- **Where it runs.** Untrusted model text reaches it through the message control's area renderer: the transcript renders assistant markdown and hands the bubble a Node (leg 05c), and streaming commits rendered prefixes at safe boundaries. A link in a reply navigates the **app's own window** (the desktop webview) unless it has `target=_blank` (only `^https?:` gets it).
- **The guards and tests:**
  - **The invariant:** `tests/test_ui_guards.py` `test_markdown_no_html_string_invariant` requires zero HTML-sink tokens in `markdown.js`, and `createElement` arguments that are literals (or `'h'+lvl`, `ol`/`ul`). `del` and `input` are literals.
  - **`tests/browser/test_markdown.py`** (`shared` lane):
    - AST and render cases (`:587`, `:732`), including the exact serialised copy-button markup at about `:654-680`;
    - `test_markdown_copy_button` (`:809`), which asserts the "Copied!" toast;
    - the XSS body payloads (`:859`);
    - `SAFEHREF_BOUNDARY_CASES` (`:881-924`);
    - `test_markdown_codefence_lang_is_class_attr_only` (`:926-948`), which **pins** `cls == 'language-js" onmouseover="alert(1)'`;
    - the streaming boundary (`:968`).
  - **`tests/browser/test_flow_markdown_chat.py`** (`chats-transcript`) uses `.markdown-copy-btn` (`:129`, `:226`). Leg 03a added "no `.app-flash` inside `.messages`".
- **The copy-button CSS** is `components.css:1640-1676`: `.markdown-code-wrap` positioning, and `.markdown-copy-btn`'s absolute top-right placement, the hover/focus reveal, its own hover and focus styles, and the svg size. These are markdown-owned classes (no library row owns them).
- **The heading and table rules** for reply content live with the message control's assistant descendants after leg 05c (`components.css`, under `.ui-message--assistant`). A1's and B1's rules go there, or in a markdown section beside `.markdown-code-wrap`. Say which in the leg's flight-log entry.
- **The ownership rows** for `js/markdown.js` are `api:App.icon(` ×1 and `api:App.showFlash(` ×3.

## Inputs
- Batch B3 (the chat migration, including leg 05c's message control) landed and committed. Leg 06 may land in the same batch (B4); this leg touches no file of leg 06.

## Outputs
- **Negative tests first** (`tests/browser/test_markdown.py`, both written and seen failing where marked, recorded in the flight log):
  1. **Backslash and whitespace paths:** `[x](/\evil.example)`, `[x](/<TAB>/evil.example)`, `[x](/<LF>/evil.example)` and `[x](\/evil.example)` render with `href="#"`, or resolve to the page's origin — **failing today**.
  2. **The fence class:** ```` ```js is-hidden ```` gives `<code class="language-js">`, with exactly one class token — **failing today**. The `:948` pin is **rewritten** to the safe expectation (`cls == 'language-js'`), with the reason in its docstring.
  3. **Nested links:** `[a [b](https://x)](https://y)` gives no `a a` (check the current behaviour; fix if it nests).
  4. **Attribute injection** in an href stays one attribute.
  5. **Encoded schemes:** `javascript&colon;…` and `%6Aavascript:…` render `#`.
  6. **Autolink negatives (0.4):**
     - bare `javascript:alert(1)` text is not linked;
     - a bare URL followed by `).` links only the URL;
     - a bare URL inside link text, inline code or a fence is not autolinked;
     - `~~` inside a code span does not strike.
- **`safeHref`** (D3 (a)):
  - reject any `\` or any C0 control, tab or newline anywhere in the href;
  - keep `http:`, `https:`, `mailto:` and `tel:`;
  - for a `/` or `#` link, resolve `new URL(href, location.href)` and keep it only when the origin equals `location.origin`;
  - everything else becomes `#`;
  - `SAFEHREF_BOUNDARY_CASES` gains the new cases, and every existing case keeps its expectation.
- **The fence language:** the first whitespace-separated token, kept only if it matches `^[A-Za-z0-9_+#.-]{1,32}$`, else no class.
- **A1:** h1-h6 inside a reply map to the type tokens. The largest reply heading is no larger than the app's page heading (`--font-size-h1` or the cap the leg's Developer measures). A computed-style test asserts h1 ≤ the page `h1`'s size and h1 ≥ h2 ≥ h3.
- **B1:** a markdown table renders inside `div.markdown-table-wrap` (`overflow-x: auto`), so a wide table scrolls inside the bubble. A test asserts the wrapper scrolls (its `scrollWidth` is greater than its `clientWidth`) and the bubble does not overflow.
- **0.4:**
  - **Strikethrough:** `~~text~~` becomes a `STRIKE` node rendered as `<del>`.
  - **Task lists:** a list item starting `[ ] ` or `[x] ` / `[X] ` becomes a `LIST_ITEM` with `meta.task = {checked}`, rendered with a leading `<input type="checkbox" disabled>`, `checked` as given, and an accessible name from the item's text (`aria-label`, or the input inside a `label`).
  - **Autolinks:** a bare `http://` or `https://` URL in text (not inside a link, inline code or a fence) becomes a `LINK` through `safeHref`. A trailing `.,;:!?` and an unbalanced `)` stay outside it.
  - Each gets AST and render cases in `test_markdown.py`, and the streaming boundary test keeps passing (an autolink must not create a live unsafe href at any slice).
- **The code-block Copy (A2, D1):**
  - `renderCodeBlock` builds the button with `App.ui.copyButton({iconOnly: true, label: 'Copy code', text: function () { return code.textContent; }, className: 'markdown-copy-btn'})`. It places `.el` in the wrap. The button confirms in place (check icon, "Copied") and announces once under the `role=log` transcript (leg 03a's contract);
  - `injectIcon` is deleted, and so are `markdown.js`'s calls to `App.icon` and `App.showFlash`. Its two ownership rows go from `OWNERSHIP_ALLOWANCE`, and `TOTAL_USES` is lowered;
  - `.markdown-copy-btn` keeps only placement and the hover/focus reveal; the button's own look comes from the library icon button. Any visible difference in the button itself (beyond the confirmation) is a ledger row;
  - the exact-markup cases (`:654-680`) and `test_markdown_copy_button` (`:809`) are retargeted to the library button's contract: the name "Copy code", the check icon after a click, the clipboard text equal to the code, no `.app-flash`;
  - `test_flow_markdown_chat.py`'s `.markdown-copy-btn` locators keep working.
- **Behavior spec:** `tests/behavior/discord-markdown-links.md` (draft) is re-read. If it relies on root-relative or `#` links rendering, it is re-authored for D3's same-origin rule.
- **Catalogue and docs:**
  - `docs/ui-control-inventory.md`: the Copy row now names the markdown code block as a consumer, and the Markdown section (if any) notes 0.4 and D3;
  - `the_one/agents.md`'s markdown renderer notes: link policy, the fence token, 0.4, and the `injectIcon` removal;
  - the markdown module's header comment (`:1-57`, the scope notes) is updated for 0.4.
- **Ledger rows 1, 2, 19, 29 and 33** confirmed in the flight log.

## Acceptance Criteria
- [ ] **The negative tests** in Outputs exist. Those marked "failing today" were seen failing before the fix, recorded in the flight log, and all pass now, in Chromium (the `shared` lane's engine).
- [ ] **`safeHref`:** every new boundary case passes, every existing `SAFEHREF_BOUNDARY_CASES` expectation is unchanged, and a same-origin `/path` and a `#anchor` still render as links.
- [ ] **The fence:** `test_markdown_codefence_lang_is_class_attr_only` is rewritten to the safe expectation, and ```` ```c++ ```` / ```` ```objective-c ```` still get their class.
- [ ] **A1 and B1:** the computed-style and scroll tests pass (`chats-transcript` or `shared`).
- [ ] **0.4:** the AST and render cases pass. The task-list checkbox is disabled, has the item's name and reflects `[x]`. The streaming boundary test passes.
- [ ] **Copy:**
  - `git grep -n "App.icon\b\|App.showFlash\|injectIcon" -- the_one/interfaces/web/static/js/markdown.js` finds nothing;
  - the two `js/markdown.js` ownership rows are gone, and `tests/test_ui_ownership.py` passes;
  - the retargeted copy tests pass, and `test_flow_markdown_chat.py` passes.
- [ ] `tests/test_ui_guards.py` (including the markdown invariant), `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` pass.
- [ ] **Lanes:** `shared`, `chats-transcript` and `contracts-controls` (if the copy contract is touched) pass.
- [ ] `make test-unit` passes after the browser runs. `ruff` is clean.

## Verification Steps
1. `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_markdown.py -m browser -x --timeout 60`, first with only the new tests added (expect the marked failures), then after the fixes.
2. `--lane chats-transcript`, then `--lane shared`.
3. `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -q -x --timeout 120`.
4. `make test-unit`; `ruff check`; `ruff format --check`.

## Implementation Guidance
1. **The negative tests**, run against today's renderer, with the failures recorded.
2. **`safeHref` and the fence token**, then the nested-link check.
3. **0.4:** strikethrough (the inline scan), task lists (`parseList` and the render), then autolinks (the inline scan, with the punctuation rule). Each comes with its AST and render cases.
4. **A1 and B1:** the renderer's wrapper, then the CSS, then the tests.
5. **The Copy migration:** the button, the deletions, the retargeted tests, the allowance.
6. **The spec re-read, catalogue and docs,** then the lanes and `make test-unit`.

## Edge Cases
- **`new URL` in `safeHref`** needs `location`. The renderer only runs in a browser page; guard for a missing `location` anyway (treat it as not same-origin, so `#`).
- **The desktop webview's origin** is the app's loopback origin, so the same-origin rule holds there too.
- **A bare URL with balanced parentheses** (`https://en.wikipedia.org/wiki/Foo_(bar)`) keeps its closing `)`. Only an unbalanced trailing `)` is dropped.
- **Task lists in ordered lists** (`1. [ ] x`) get the same treatment.
- **Streaming and autolinks:** a URL cut at a chunk boundary must not render a partial link that later changes target unsafely. The safe-boundary commit already holds back inside a paragraph; the streaming test proves it.
- **The copy button under `role=log`:** leg 03a's contract covers announcing once. Re-check it inside an assistant bubble (`test_flow_markdown_chat.py`).
- **A heading inside a list item or blockquote** uses the same token rule.

## Files Affected
- `the_one/interfaces/web/static/js/markdown.js`, `css/components.css` (the markdown and assistant-content rules).
- `tests/browser/test_markdown.py`, `tests/browser/test_flow_markdown_chat.py`, possibly `tests/browser/test_ui_copy_contract.py`.
- `tests/_ui_ownership_allowance.py`, `docs/ui-control-inventory.md`, `the_one/agents.md`, `tests/behavior/discord-markdown-links.md` (if re-authored), the flight log.

## Citation Audit
- `markdown.js:62-82` (`NodeType`), `:104-122` (`safeHref`), `:151-154` (the fence remainder), `:251` (`parseList`), `:341-515` (`scanInline`), `:548` (`parseLink`), `:621-632` (`injectIcon`), `:771-810` (`renderCodeBlock`), `:812` (`render`). FD read (2026-10-27).
- `tests/browser/test_markdown.py:587`, `:654-680`, `:732`, `:809`, `:859`, `:881-924`, `:926-948` (the `:948` pin), `:968`. FD grep.
- `components.css:1640-1676` (the copy-button CSS). FD grep.
- **Line numbers will drift** only if a leg before this one edits `markdown.js`. None is planned to; re-derive anyway.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review Amendments (cycle 1, 2026-10-27; these take precedence over the Outputs above)
- **Inline context becomes an object.** `scanInline(text, inEmphasisRun)` takes a ctx instead of the boolean, for example `{noEmphasis, noLinks}`; every call site is in `markdown.js`.
  - **Link labels** are parsed with `noLinks`. No autolink and no nested link inside a label, so `[https://a.com](https://a.com)` and `[a [b](https://x)](https://y)` give one anchor each. **The nested link is real today; the fix is unconditional.**
  - **Emphasis bodies** keep autolinks and strike (`**see https://x.com**`, `**~~x~~**`).
  - **Order in the char-walk:** the autolink and `~~` branches come **before** the `*`/`_` branch, so `_`/`*` inside a URL are not eaten.
  - **Autolink trigger:** at `h`/`H` with `/^https?:\/\//i`, only at a boundary (index 0 or a non-alphanumeric previous character, so `foohttp://x` does not link). The URL ends at whitespace or `<>`. A trailing `.,;:!?*_~` and an unbalanced `)` are trimmed. Content after the scheme is required (so `http://` alone is text).
  - **An autolink never emits `href="#"`:** stop the URL at `\` and control characters, and emit plain text whenever `safeHref(raw) !== raw`. Negative test included.
  - **Strike is `~~` only** (a single `~` stays literal). Its closer search skips code spans (a new helper; `findClosingDelim` skips them only for `*`/`_`). An unmatched `~~` stays literal, and `~~` does not pair across a paragraph break.
  - `parseLink` counting a `]` inside a code span in its label is fixed if it is small, with a negative case (`` [`]`](u) ``); otherwise it is recorded as deferred.
  - The renderer has no backslash-escape handling today, so there is no escape interaction to preserve.
- **Which negative tests fail today:** the backslash and whitespace paths, the fence class and the nested link. Attribute injection, `javascript&colon;` and `%6Aavascript:` pass today and are labelled **regression guards**.
  - **Extra cases:** `~~a\nb~~` across a soft break; a bare URL in a heading and in a table cell (links); `http://` alone (no link). `mailto:`, `www.` and `<https://…>` are not autolinked and are listed as out of the subset in the module header.
- **`safeHref` details:**
  - return the **original** href string on success (existing cases expect `/rel/path` and `#frag` unchanged);
  - reject `\x7f` too;
  - treat an opaque `location.origin` of `"null"` as not same-origin;
  - the new rejection applies to `http(s):`, `mailto:` and `tel:` hrefs too.
  - Same-origin `/path` and `#hash` links keep navigating the app window, as the operator's D3 (a) decided.
- **The fence language** is sanitised in the parser (`meta.lang` is the valid token or null), with a defensive check in `renderCodeBlock`.
- **The copy button's shape:** markdown creates its own `span.visually-hidden[role=status]` in the wrap and passes it as `liveEl`, so `copyButton`'s root is the bare button and no `span.ui-copy` inline box adds blank space under the code. A test asserts the wrap's height equals the `pre`'s height plus margins.
  - Pass the library size that keeps today's footprint (check `button.js`'s `SIZE_CLASS`); any remaining size difference is a ledger row.
  - `.markdown-copy-btn` keeps only `position/top/right`, the resting `opacity: 0.6`, its hover/focus reveal and the focus-visible opacity. Its background, border, radius, padding, colour, svg size and hover border go. The reveal opacity is not a disabled state, so the no-opacity rule for disabled buttons does not apply; the flight log notes this.
- **Tests the leg did not list:**
  - `test_markdown_nodetype_constants` (`:~745`) gains `STRIKE`, and the counts in its docstring and the module header are corrected;
  - every table case in `RENDER_CASES` changes to the B1 wrapper;
  - the exact copy-markup cases (`:654-680`) become **structural** assertions: wrap > pre > code, exactly one `button.markdown-copy-btn[aria-label="Copy code"]`, no inline SVG string;
  - `AST_CASES` list items gain `meta.task` only when a task marker is present (no `meta: {}` on plain items);
  - the `injectIcon` / DOMParser seam text in `tests/test_ui_guards.py` (`:~451`) and `tests/_ui_guard_helpers.py` is updated;
  - the streaming test gains the prefixes `see https://exa` and `~~half`.
- **A1:** the cap is `--font-size-h1` (18px, `fonts.css:37`), not the chat header's 13px.
  - h1, h2 and h3 use the h1-h3 tokens (18/16/15); h4-h6 are body-lg/body semibold, with `0.5em` margins like `p` (the existing first-child and last-child resets apply);
  - the test asserts h1 ≥ h2 ≥ … ≥ h6 and h1 ≤ `--font-size-h1`.
- **B1:** `div.markdown-table-wrap` gets `tabindex="0"`, `role="region"` and `aria-label="Table"`, so keyboard users can scroll it. Its CSS lets the table overflow (`width: max-content; min-width: 100%` if needed). The test uses long unbreakable cell text, and `min-width: 0` goes on the flex ancestors if the bubble overflows.
- **Task lists:**
  - detect `/^\[([ xX])\]\s+/` on the item's first line in `parseList` (the required whitespace keeps `- [x](https://a)` a link) and strip it before `parseBlocks`;
  - the render appends the `<input>` before the tight-list inline children;
  - the accessible name comes from the item's **first paragraph** text only, never `li.textContent`, so a nested sublist is not pulled in;
  - an empty-label item is specified and tested;
  - ordered lists behave the same;
  - a `markdown-task` class on the `li` (`list-style: none`) uses tokens only.
- **Where the CSS lives:** A1, B1 and task-list rules go beside the assistant-content rules that leg 05c leaves (under `.ui-message--assistant`). The exact file is confirmed once 05c lands; `components.css` is not hard-coded.
- **The counts:** `TOTAL_USES` is lowered by `markdown.js`'s 4 uses, computed against the tree after legs 04-06. Both places in `tests/_ui_ownership_allowance.py` that list the two keys are updated. CLAUDE.md's and `agents.md`'s control-library totals are refreshed in leg 09a.
- **`discord-markdown-links.md`** is about the web rendering of connector-session replies, not Discord output, and does not rely on root-relative or `#` links, so D3 needs no re-authoring. A bare-URL variant is **added** to its step 4, since autolinks now make the `a[href]` expectation hold for a bare URL.
- **Sibling found:** `App.safeUrl` (`app.js:260-273`) has the same blind spot for `\` and control characters on http(s) URLs. Out of scope; logged as **squawk 0275** (deferred).

## Design Review
- **Developer design review, cycle 1 (Sonnet, 2026-10-27, read-only): approve with changes.** Applied as the amendments above. FD answers:
  - single `~` stays literal;
  - the copy button uses `liveEl` (a bare button root);
  - the A1 cap is 18px;
  - same-origin links keep navigating the app window (the operator's D3 (a));
  - the Discord spec gains a bare-URL variant rather than a re-author.
- **No second cycle.** The amendments specify the parser and test changes inside the leg's existing scope.
