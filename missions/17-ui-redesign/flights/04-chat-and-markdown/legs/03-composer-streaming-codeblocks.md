# Leg: composer-streaming-codeblocks

**Status**: completed
**Flight**: [Chat Re-skin + Markdown Hardening](../flight.md)

## Objective

Re-skin the composer + stop affordance, code-block well + copy button, inline code, and the tool-trace/thinking disclosure chrome to the v3 vocabulary — with composite-a11y gates for the new washed surfaces. *(Fattest leg — split into `composer+stop` | `code+disclosures` if it balloons; log the split.)*

## Scope (flight DDs "Composer + stop affordance", "Code blocks + copy button", "Tool-trace + thinking disclosures" authoritative)

- **Composer + stop** (SC4/SC5): composer input → `.field`/vocabulary input styling; send button already `.btn-filled-primary` (keep); the `chat-stop-btn` (mission preserve-item — `chat.js:168`, `data-testid="chat-stop-btn"`, `aria-label="Stop"`, visibility via `isCurrentBusy()`, CSS `chat.css:566-572`) → a vocabulary variant (`.btn-muted-destructive` or ghost-stop) — stopping stays first-class, keyboard-operable, pinned focus. **If it sits on `--*-danger-soft` → composite-a11y gate (stop-on-danger-soft, the F3 headline genre).** Scroll-position awareness (auto-scroll only at bottom; "jump to latest" when scrolled up) if achievable within the leg — else log as follow-up.
- **Code blocks + copy** : `--code-block-bg`/`--code-block-fg` well → quiet code surface, both themes; **composite/solid-a11y gate: code fg-on-bg both themes**. The `.markdown-copy-btn` (components.css:1145-1177, currently hover/focus-opacity-reveal) → per the F3 CTA lesson, make it always-visible-but-quiet OR at minimum keyboard-reachable (no hover-reveal-only). Inline `<code>` pill → vocabulary. NOTE: the copy button + code-well markup is produced by `markdown.js`'s `renderCodeBlock` (DOM-built) — CSS-only changes preferred; if markup changes, keep the no-HTML-string invariant (guard from Leg 1 will catch a regression) and keep `test_markdown.py` green.
- **Disclosures**: the `<details>` trace shell (trace-shell.js) + thinking disclosure → vocabulary disclosure treatment (quiet summary, hairline, no alien effects); preserve "tool activity out of the reading flow"; keep `test_flow_chat_thinking_disclosure.py` green.
- Button vocabulary consumed directly (no per-area variants); any form control uses `.field-group` with full label-association.
- Guard bookkeeping: sink baseline expected unchanged/down; state direction; justify any JS diff. Keep the Leg-1 invariant guard + XSS suite green (any markdown.js touch).

## Acceptance Criteria

- [x] Composer input + send + stop in the vocabulary, both themes; stop first-class + keyboard-operable + pinned focus (CDP focus evidence); stop-on-danger-soft a11y gate green if applicable
- [x] Code-block well + copy button in the vocabulary; copy button NOT hover-reveal-only (discoverable/keyboard-reachable); code fg-on-bg a11y gate green both themes; inline code pill vocabulary
- [x] Trace + thinking disclosures in the vocabulary; tool activity stays out of the reading flow; `test_flow_chat_thinking_disclosure.py` green
- [x] `test_markdown.py` (facade) + invariant guard + XSS suite green (markdown.js NOT touched this leg — copy button was CSS-only); chat-flow browser slice green via run-tests.sh
- [x] `make test-unit` green; guard/token/a11y slice green; ruff clean; sink baseline honest (no JS sink delta — only class strings changed); pixel snapshots regenerated locally (not committed)

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry (composer/stop/code/disclosure decisions, a11y gates, no leg split — leg stayed one commit's worth); leg `landed`; checked off in flight.md
