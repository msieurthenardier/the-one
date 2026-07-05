# Leg: markdown-hardening-and-xss-suite

**Status**: completed
**Flight**: [Chat Re-skin + Markdown Hardening](../flight.md)

## Objective

Harden `markdown.js`'s safeHref boundary, lock its no-HTML-string invariant with a guard, land the XSS regression suite, add the JS-dead-CSS-var tripwire, fix the CLAUDE.md `stream_chunks` doc drift, and re-baseline the sink freeze to 92 — WITHOUT changing the `App.markdown` facade (parse→AST/19 NodeTypes, render→DocumentFragment).

## Scope (flight DDs authoritative — "No vendoring" DD is the contract)

1. **safeHref hardening** (`markdown.js:101-108`): decide + lock the protocol-relative `//host` case (recommend force `#` — an off-site protocol-relative link is not clearly intended; if kept, lock with a test asserting the current behavior). Confirm the `lang` class-attr path (`'language-'+lang` via setAttribute, markdown.js:759) cannot inject — assert it. Keep the allowlist FAIL-CLOSED.
2. **No-HTML-string invariant guard** (new pytest, `tests/test_ui_guards.py` or a sibling): static-assert `markdown.js` contains exactly 0 of `innerHTML`/`outerHTML`/`insertAdjacentHTML` (the three literal tokens); assert `render()` returns a DocumentFragment (runtime, via the existing Playwright `page.evaluate` harness in test_markdown.py OR a unit assertion if feasible); assert every `createElement(arg)` uses a string literal OR the bounded allowlist `{'h'+lvl (h1..h6), ordered?'ol':'ul'}` — enumerate exactly those two dynamic sites with a comment; carry a one-line allowance note for the trusted-icon `DOMParser().parseFromString(...,'image/svg+xml')` line (injectIcon:614) so it isn't "tightened" into a false failure.
3. **XSS regression suite** (expand `tests/browser/test_markdown.py`'s safeHref tests, same parametrized `page.evaluate` pattern): mXSS/script/onerror/iframe/svg-onload payloads AS markdown body → inert text (assert `textContent` contains the literal, `querySelector('script,iframe,img')` is null) — framed as future-proofing tripwires (structurally impossible today, fire on any reintroduced innerHTML seam); safeHref boundary (leading-whitespace/`\t`/`\n`/control-char/mixed-case obfuscated `javascript:`/`data:`/`vbscript:`/`file:` → `#`; valid `https:`/`mailto:`/`tel:`/`/rel`/`#frag` pass; every link `rel="noopener noreferrer"`); code-fence lang-payload (`js" onmouseover="alert(1)`) → class-attr-only, no event handler, no new element; streaming-specific (a half-written `[x](javascript:` sliced at a `findSafeRenderBoundary` cut never emits a live unsafe href mid-stream).
4. **JS-dead-CSS-var tripwire** (F3 debrief rec 5): a guard grepping JS strings for `var(--token)` refs whose token is absent from tokens.css (catches the F3 Leg-1 dead-alias-in-JS miss class). Land in the guard suite.
5. **CLAUDE.md fix**: `stream_chunks` is a LIST of strings, not a number (mock.py:43,133 + all browser tests) — fix the §"Dev mode" wording.
6. **Sink re-baseline**: prune the 3 stale F3 gallery entries from `DYNAMIC_SINK_BASELINE` so it reflects the live 92/27 (removals never fail the ratchet; this makes it honest before F4's chat churn).

## Acceptance Criteria

- [x] `test_markdown.py` GREEN (facade intact — this leg must not change parse/render behavior except the safeHref hardening, which gets its own asserts)
- [x] No-HTML-string invariant guard green + probe-tested (temporarily add an `innerHTML=` to markdown.js → guard fails naming it → revert; temporarily add `createElement(userVar)` → fails → revert)
- [x] XSS suite green; every payload category present; the safeHref boundary + streaming-boundary cases included
- [x] JS-dead-CSS-var tripwire green + probe-tested (plant a `var(--nonexistent)` in a JS string → fails → revert)
- [x] `DYNAMIC_SINK_BASELINE` reflects live counts (92); guard green
- [x] CLAUDE.md stream_chunks wording corrected
- [x] `make test-unit` green; guard/token/a11y slice green; targeted `test_markdown.py` + `test_flow_markdown_chat.py` via run-tests.sh green; ruff clean

## Implementation Guidance

1. Do safeHref hardening + its asserts first (smallest, security-load-bearing).
2. The invariant guard is a static read of markdown.js (pathlib + regex/AST) — mirror the existing `_ui_guard_helpers` style; the fragment-return assertion may reuse test_markdown.py's Playwright harness.
3. XSS suite: additive to test_markdown.py's existing `@pytest.mark.parametrize` XSS cases — do not remove existing coverage.
4. Run test_markdown.py after every markdown.js touch — it's the facade net.

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry (safeHref decision, guard mechanics, XSS categories, sink re-baseline); leg `landed`; checked off in flight.md
