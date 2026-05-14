# Leg: message-stream-polish

**Status**: completed
**Flight**: [Chat Polish](../flight.md)

## Objective

Polish the chat message stream: bring assistant code blocks onto the theme-aware `--code-block-bg` / `--code-block-fg` tokens that already exist for the canonical `.code-block` primitive (currently the chat-area `pre` rule hardcodes `#000` + warning-orange, which is jarring in light theme); add an inline `<code>` treatment so single-backtick inline code reads as distinct from prose; surface the context-fill warn/crit color on the percent value of the telemetry overlay so the warning carries through the collapsed-ghost state; and add the `aria-keyshortcuts="Enter"` + `enterkeyhint="send"` accessibility hints to the chat input + send button. Out of scope per flight spec's "Markdown rendering scope" resolution: new markdown extensions (syntax highlighting, math) — those are future-flight scope.

## Context

- **Design Decision (flight.md)**: "Markdown rendering scope → resolved: F6's polish leg evaluates the existing `App.markdown.render` output for typography, code-block treatment, table rendering, blockquote, list semantics. Does NOT introduce new markdown extensions (e.g., syntax highlighting, math) — those are future-flight scope."
- **Mission scope (mission.md F6 description)**: "message bubbles, input field, telemetry overlay, markdown rendering" all land here.
- **Existing `.code-block` primitive** (`the_one/interfaces/web/static/css/components.css:1044-1057`): canonical code-artifact treatment driven by `--code-block-bg` and `--code-block-fg` tokens, with a 1px border for "code well" framing. Tokens are theme-aware:
  - Dark theme (`tokens.css:121-122`): `--code-block-bg: #000`, `--code-block-fg: var(--status-warning)` (terminal aesthetic — warning-orange on black)
  - Light theme (`tokens.css:307-308`): `--code-block-bg: var(--surface-elevated)`, `--code-block-fg: var(--fg)` (pale slate-50 + slate-900, AAA contrast)
- **Current chat-area code-block defect** (`chat.css:174-181`): the `.area-chat .msg.assistant pre` rule HARDCODES `background: #000; color: var(--status-warning); padding: 12px 14px; border-radius: var(--panel-radius-sm); overflow-x: auto;`. This duplicates the dark-theme appearance of `.code-block` but does NOT track the light-theme token override — light-theme assistant code blocks render with black bg + warning-orange text against a white page, which is harsh and inconsistent with the rest of the polished design language. Aligning to the tokens fixes the light-theme regression without changing dark-theme appearance.
- **Inline `<code>` treatment is missing**: `App.markdown.render` emits `<code>` for single-backtick spans (`markdown.js:724-727` — `NodeType.INLINE_CODE` → `createElement('code')`). The chat-area CSS has NO `.msg.assistant > code` or equivalent rule (only the `pre code` rule at `chat.css:182-187` which targets code INSIDE pre, not inline). Inline code falls back to the browser's default `font-family: monospace` — no background, no padding, no visual distinction from prose. The polished bar is a subtle pill: small background, slight padding, mono font.
- **Telemetry overlay's context-bar warn/crit color is partial signal** (`chat.css:79-81`, `telemetry-overlay.js:77`): the bar fill changes color via `.context-bar.warn` / `.context-bar.crit` classes when context fills past 70% / 90%. BUT the `.t-ctx-pct` text (the most-visible signal in the collapsed-ghost state, where the bar is just 64×6px) does NOT change color — it stays at `--fg-secondary`. A user glancing at the overlay sees "47%" or "84%" but cannot distinguish at-a-glance whether they're in the warn band. Aligning the percent-text color with the bar color closes that gap.
- **Keyboard accessibility gap**: the chat input lacks `enterkeyhint="send"` (mobile-keyboard semantic that surfaces a "Send" key glyph) and the send button lacks `aria-keyshortcuts="Enter"` (screen-reader-discoverable mention that Enter on the input triggers Send). Both are 1-attribute additions that improve discoverability without affecting layout, focus order, or any existing behavior.
- **Recon (flight-log.md row #8)**: "telemetry overlay, markdown rendering, message bubbles, input field" all scoped to L04 within the chat-surface page-by-page pass.
- **F5 carry-forward**: L02's `parent_message_id` discriminator and the trace shell from F5 L03 are NOT touched by this leg. L04 stays inside `.msg.assistant` typography + telemetry + input chrome.

## Inputs

Files that exist before this leg runs:
- `the_one/interfaces/web/static/css/chat.css` — chat-area rules including the hardcoded `pre` block at lines 174-181, the (absent) inline-code treatment, and the telemetry-pct rule at line 77 (`.t-ctx-pct { font-family: var(--font-family-mono); font-variant-numeric: tabular-nums; }`)
- `the_one/interfaces/web/static/css/tokens.css` — `--code-block-bg`, `--code-block-fg`, `--status-warning`, `--status-danger` tokens defined; theme-aware
- `the_one/interfaces/web/static/css/components.css:1044` — canonical `.code-block` primitive for reference (do NOT modify)
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js:75-77` — `updateTelemetry` applies `.warn` / `.crit` classes to `.context-bar` based on `pct`; the percent text update happens at line 74 without a corresponding class flip
- `the_one/interfaces/web/static/js/areas/chat.js:83-85` — chat input innerHTML (the `<input data-testid="chat-input" ...>` + `<button class="btn-filled-primary" data-testid="chat-send-btn">Send</button>`)

State that must be true:
- L03 (`welcome-and-session-list-polish`) landed; broad pytest exits 0 with 1627p/4s/370d; browser suite 315/35 preserved
- Container `the-one` running; host `make rebuild` reachable (per L03 implementation note: `make` is host-only, not inside the container)

## Outputs

Files modified:
- `the_one/interfaces/web/static/css/chat.css`:
  - Replace hardcoded `background: #000; color: var(--status-warning)` in `.area-chat .msg.assistant pre` with the theme-aware tokens. Add a `1px solid var(--border)` border to match the canonical `.code-block`'s "code well" framing.
  - Add a new `.area-chat .msg.assistant code:not(pre code) { ... }` rule (or equivalent selector that targets ONLY inline code, NOT code inside pre) for a small inline pill: monospace, faint surface-elevated background, ~2-4px padding, subtle border-radius
  - Add `.area-chat .telemetry-overlay .t-ctx-pct.warn { color: var(--status-warning); }` and `.area-chat .telemetry-overlay .t-ctx-pct.crit { color: var(--status-danger); }` rules
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js`:
  - In `updateTelemetry`, mirror the `.warn` / `.crit` class application onto `.t-ctx-pct` alongside the existing `.context-bar` class flip
  - In `resetTelemetry`, strip the warn/crit classes from `.t-ctx-pct` alongside the existing bar reset
- `the_one/interfaces/web/static/js/areas/chat.js`:
  - Chat input gains `enterkeyhint="send"` attribute
  - Send button gains `aria-keyshortcuts="Enter"` attribute

State after:
- Assistant code blocks render correctly in BOTH themes (light + dark) using the existing canonical token pair — no more hardcoded black bg in light theme
- Inline `<code>` spans visually distinct from surrounding prose (subtle pill) in both themes
- Telemetry percent text colorizes alongside the context bar at warn (70%+) and crit (90%+) thresholds — at-a-glance signal works in collapsed-ghost state, not just expanded
- Mobile virtual keyboards surface a "Send" glyph on the Enter key when the chat input is focused; screen readers announce `Enter` as the shortcut for the Send button
- No regression in message bubble appearance, telemetry overlay's existing hover-expand behavior, or input-area layout
- No regression in broader test suite (1627p/4s/370d broad; 315/35 browser)

## Acceptance Criteria

- [ ] `the_one/interfaces/web/static/css/chat.css` — the `.area-chat .msg.assistant pre` rule's `background` value is `var(--code-block-bg)` (NOT `#000`); its `color` value is `var(--code-block-fg)` (NOT `var(--status-warning)`)
- [ ] `the_one/interfaces/web/static/css/chat.css` — the same `.area-chat .msg.assistant pre` rule adds `border: 1px solid var(--border)` so the "code well" framing matches the canonical `.code-block` primitive in both themes
- [ ] `the_one/interfaces/web/static/css/chat.css` — a new rule targets inline `<code>` ONLY (NOT inside `pre`); recommended selector form: `.area-chat .msg.assistant code` combined with the existing `.area-chat .msg.assistant pre code` rule overriding it back to the bare code-inside-pre appearance. Inline pill properties: `background: var(--surface-elevated)`, `padding: 1px 5px`, `border-radius: 3px`, `font-family: var(--font-family-mono)`, `font-size: 0.92em`, no border (subtle, not framed)
- [ ] The existing `.area-chat .msg.assistant pre code` rule at `chat.css:182-187` is updated to ADD explicit `padding: 0` and `border-radius: 0` resets (its existing `background: transparent` is preserved). The new resets are needed because the new inline-code rule introduces non-zero `padding` + `border-radius`, which would otherwise inherit-through into code-inside-pre (no double-pill nesting)
- [ ] `the_one/interfaces/web/static/css/chat.css` — adds `.area-chat .telemetry-overlay .t-ctx-pct.warn { color: var(--status-warning); }` AND `.area-chat .telemetry-overlay .t-ctx-pct.crit { color: var(--status-danger); }` rules; placed adjacent to the existing `.t-ctx-pct` rule near line 77
- [ ] `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` — `updateTelemetry` applies the warn/crit class to BOTH `.context-bar` (existing behavior) AND `.t-ctx-pct` (new). Recommended idiom: compute `var stateClass = pct >= 90 ? 'crit' : pct >= 70 ? 'warn' : '';` once, then apply to both elements.
- [ ] `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` — `resetTelemetry` strips both `.warn` and `.crit` from `.t-ctx-pct` (currently it only resets the bar). Recommended pattern: set `.t-ctx-pct` className to its base `value t-ctx-pct` form (matching the construction at line 34)
- [ ] `the_one/interfaces/web/static/js/areas/chat.js` — the chat input `<input>` element at line ~83 has `enterkeyhint="send"` added; existing attributes (`data-testid`, `placeholder`, `autocomplete`, `aria-label`) preserved
- [ ] `the_one/interfaces/web/static/js/areas/chat.js` — the send button `<button>` element at line 85 has `aria-keyshortcuts="Enter"` added; existing class + `data-testid` preserved
- [ ] No new `data-testid` attributes are added by this leg (existing test selectors stay stable)
- [ ] Browser suite preserved at 315 passing / 35 skipped — no test breakage from the CSS / attribute changes
- [ ] Broad pytest exits 0 with 1627 passed, 4 skipped, 370 deselected (unchanged from L03)
- [ ] No structural change to `markdown.js`, `message-bubble.js`, `trace-shell.js`, or any other chat-area file outside the four explicitly listed in Files Affected — verify by `git diff --stat` that the diff is confined to chat.css + telemetry-overlay.js + chat.js (and the leg artifact itself + flight-log.md)

## Verification Steps

- **Code block in dark theme**: open chat in dark theme; send a message containing a fenced code block (triple-backtick); confirm the rendered `<pre>` shows the terminal aesthetic (black bg, warning-orange text). Visual identical to pre-leg state.
- **Code block in light theme**: toggle to light theme; same fenced-code-block content now renders with pale slate-50 background + slate-900 text (AAA contrast) and a 1px border. NO MORE hardcoded black bg.
- **Inline code in both themes**: send a message containing `` `inline code` `` between regular prose; confirm the inline `<code>` renders as a subtle pill (background tone distinct from prose, ~2-4px horizontal padding) and visually distinguishable from the surrounding text. NO pill artifact appears inside fenced code blocks (verify code-inside-pre is plain mono, no nested pill).
- **Telemetry overlay percent color (warn)**: open chat, send a few messages, watch the context bar approach 70%. At >=70%, the bar fill turns to `--status-warning` AND the percent text (e.g., "73%") also turns to `--status-warning`. Even with the overlay collapsed (`opacity: 0.4`), the warn signal is visible.
- **Telemetry overlay percent color (crit)**: keep accumulating context; at >=90%, both bar and percent text turn to `--status-danger`.
- **Telemetry reset on session switch**: switch sessions; the percent text returns to the default color (`--fg-secondary`); confirm `resetTelemetry` cleared the warn/crit class.
- **Mobile enterkeyhint**: open chat on a touch device or via DevTools device emulator; focus the chat input; the mobile virtual keyboard surfaces a "Send" key glyph on the Enter position. (Browser-internal — can only validate via emulator inspector; the attribute presence in DOM is the verifiable artifact in CI.)
- **Send button aria-keyshortcuts**: inspect the send button via DevTools; `aria-keyshortcuts="Enter"` attribute is present. NVDA/VoiceOver dry-run via the DevTools accessibility tree shows the shortcut.
- **DOM-attribute presence** (CI-friendly): `grep -n 'enterkeyhint="send"' the_one/interfaces/web/static/js/areas/chat.js` returns the chat-input line; `grep -n 'aria-keyshortcuts="Enter"' the_one/interfaces/web/static/js/areas/chat.js` returns the send-button line.
- **Targeted browser tests**: `docker exec the-one pytest tests/browser/test_flow_chat.py tests/browser/test_flow_telemetry.py tests/browser/test_flow_streaming.py -x --timeout 60 -v` — adjust the file list to whichever chat-area browser tests exist; the polish changes should not break any selector.
- **Broad pytest**: `docker exec the-one pytest -x --timeout 30` exits 0 with 1627p/4s/370d.
- **Browser suite**: `docker exec the-one pytest -m browser --timeout 60 --tb=line` returns 315/35 unchanged.

## Implementation Guidance

1. **Edit `the_one/interfaces/web/static/css/chat.css`** — replace the hardcoded code-block treatment:

   ```css
   /* BEFORE */
   .area-chat .msg.assistant pre {
     margin: 0.5em 0;
     background: #000;
     color: var(--status-warning);
     padding: 12px 14px;
     border-radius: var(--panel-radius-sm);
     overflow-x: auto;
   }
   .area-chat .msg.assistant pre code {
     background: transparent;
     color: inherit;
     font-family: var(--font-family-mono);
     font-size: 0.9em;
   }

   /* AFTER */
   .area-chat .msg.assistant pre {
     margin: 0.5em 0;
     background: var(--code-block-bg);
     color: var(--code-block-fg);
     border: 1px solid var(--border);
     padding: 12px 14px;
     border-radius: var(--panel-radius-sm);
     overflow-x: auto;
   }
   /* Inline <code> (single-backtick) — subtle pill, distinct from prose. */
   .area-chat .msg.assistant code {
     background: var(--surface-elevated);
     padding: 1px 5px;
     border-radius: 3px;
     font-family: var(--font-family-mono);
     font-size: 0.92em;
   }
   /* Code inside <pre> resets the inline pill so block-level code retains the
      flat "code well" rendering with no nested pill. */
   .area-chat .msg.assistant pre code {
     background: transparent;
     padding: 0;
     border-radius: 0;
     color: inherit;
     font-family: var(--font-family-mono);
     font-size: 0.9em;
   }
   ```

2. **Edit `the_one/interfaces/web/static/css/chat.css`** — add the percent-text warn/crit color rules next to the existing `.t-ctx-pct` rule (around line 77):

   ```css
   .area-chat .telemetry-overlay .t-ctx-pct.warn { color: var(--status-warning); }
   .area-chat .telemetry-overlay .t-ctx-pct.crit { color: var(--status-danger); }
   ```

3. **Edit `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js`** `updateTelemetry`:

   ```javascript
   // BEFORE (lines 67-78 approx)
   function updateTelemetry(chromeContent, data) {
     chromeContent.querySelector('.t-in').textContent = fmtTokens(data.input_tokens);
     chromeContent.querySelector('.t-out').textContent = fmtTokens(data.output_tokens);
     chromeContent.querySelector('.t-ctx').textContent = fmtTokens(data.context_tokens);
     var pct = data.max_context_tokens > 0
       ? Math.min(100, Math.round(data.context_tokens / data.max_context_tokens * 100))
       : 0;
     chromeContent.querySelector('.t-ctx-pct').textContent = pct + '%';
     var bar = chromeContent.querySelector('.context-bar');
     bar.style.width = pct + '%';
     bar.className = 'context-bar' + (pct >= 90 ? ' crit' : pct >= 70 ? ' warn' : '');
   }

   // AFTER
   function updateTelemetry(chromeContent, data) {
     chromeContent.querySelector('.t-in').textContent = fmtTokens(data.input_tokens);
     chromeContent.querySelector('.t-out').textContent = fmtTokens(data.output_tokens);
     chromeContent.querySelector('.t-ctx').textContent = fmtTokens(data.context_tokens);
     var pct = data.max_context_tokens > 0
       ? Math.min(100, Math.round(data.context_tokens / data.max_context_tokens * 100))
       : 0;
     var stateClass = pct >= 90 ? 'crit' : pct >= 70 ? 'warn' : '';
     var pctEl = chromeContent.querySelector('.t-ctx-pct');
     pctEl.textContent = pct + '%';
     pctEl.className = 'value t-ctx-pct' + (stateClass ? ' ' + stateClass : '');
     var bar = chromeContent.querySelector('.context-bar');
     bar.style.width = pct + '%';
     bar.className = 'context-bar' + (stateClass ? ' ' + stateClass : '');
   }
   ```

4. **Edit `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js`** `resetTelemetry`:

   ```javascript
   // BEFORE (lines 82-90 approx)
   function resetTelemetry(chromeContent) {
     chromeContent.querySelector('.t-in').textContent = '0';
     chromeContent.querySelector('.t-out').textContent = '0';
     chromeContent.querySelector('.t-ctx').textContent = '0';
     chromeContent.querySelector('.t-ctx-pct').textContent = '0%';
     var bar = chromeContent.querySelector('.context-bar');
     bar.style.width = '0%';
     bar.className = 'context-bar';
   }

   // AFTER
   function resetTelemetry(chromeContent) {
     chromeContent.querySelector('.t-in').textContent = '0';
     chromeContent.querySelector('.t-out').textContent = '0';
     chromeContent.querySelector('.t-ctx').textContent = '0';
     var pctEl = chromeContent.querySelector('.t-ctx-pct');
     pctEl.textContent = '0%';
     pctEl.className = 'value t-ctx-pct';
     var bar = chromeContent.querySelector('.context-bar');
     bar.style.width = '0%';
     bar.className = 'context-bar';
   }
   ```

5. **Edit `the_one/interfaces/web/static/js/areas/chat.js`** — chat input + send button attribute additions at lines ~83-85:

   ```javascript
   // BEFORE
   '<div class="input-area">' +
     '<input data-testid="chat-input" placeholder="Type a message..." autocomplete="off" aria-label="Message" />' +
     '<button class="btn-filled-primary" data-testid="chat-send-btn">Send</button></div>' +

   // AFTER
   '<div class="input-area">' +
     '<input data-testid="chat-input" placeholder="Type a message..." autocomplete="off" enterkeyhint="send" aria-label="Message" />' +
     '<button class="btn-filled-primary" data-testid="chat-send-btn" aria-keyshortcuts="Enter">Send</button></div>' +
   ```

6. **Run `make rebuild` on the host** (NOT `docker exec the-one make rebuild` — per L03 implementation note, `make` is host-only). If `make rebuild` wipes Playwright browsers, run `make _ensure-playwright` to restore Chromium before the browser suite.

7. **Run targeted browser tests first**, then broad suite:

   ```bash
   docker exec the-one pytest tests/browser/test_flow_chat.py -x --timeout 60 -v
   # If a telemetry-specific test file exists (test_flow_telemetry.py or similar), add it
   docker exec the-one pytest -x --timeout 30
   docker exec the-one pytest -m browser --timeout 60 --tb=line
   ```

8. **Update flight log** — append a Leg Progress entry with: code-block token alignment landed, inline-code pill added, telemetry warn/crit text propagation landed, mobile/SR keyboard hints added, default test counts.

9. **Do NOT commit** — Flight Director batches commits after L05.

## Edge Cases

- **`.area-chat .msg.assistant code` selector specificity**: the selector matches inline `<code>` AND code inside `<pre>` until the more-specific `.area-chat .msg.assistant pre code` rule wins. Both rules are scoped to `.area-chat .msg.assistant`, so specificity is `0,2,1` (inline) vs `0,2,2` (code-in-pre); the pre-rule wins. Verify in DevTools after the edit — if specificity is wrong, the inline-pill background would bleed into fenced code blocks.
- **`code` outside `.msg.assistant`**: tool messages, system messages, and welcome canvas do not currently render markdown — `message-bubble.js:11-14` only applies markdown to assistant first-token. The `.area-chat .msg.assistant code` selector therefore cannot affect tool/system bubbles. Confirm by inspection.
- **Light-theme code blocks with no `--border` token**: `--border` is defined in both themes (verify via `grep -n "^[[:space:]]*--border:" tokens.css`). Should be `#333` dark / `#cbd5e1` light or similar. If absent in one theme, fall back to `1px solid var(--surface-elevated)` (always defined).
- **Streaming code blocks**: `message-bubble.js:22-33` calls `App.markdown.render(text)` only for assistant. During streaming, the chunk-accumulation path uses `textContent` (no markdown), then `finalizeStreamingBubble` re-renders the full buffer as markdown on `done`. The token-aware code-block treatment applies AFTER finalize — during streaming, the in-progress text is plain. This matches existing behavior; the leg does not change the streaming pipeline.
- **`enterkeyhint` on desktop browsers**: ignored by desktop UAs. Mobile-only attribute. No risk of regression on desktop.
- **`aria-keyshortcuts` event-handler check**: `aria-keyshortcuts` is purely declarative — the screen reader announces it. The actual Enter-on-input → click-Send wiring is in the existing `keydown` handler (search `chat.js` for the input keydown). The attribute does NOT add new wiring; it documents existing behavior. Verify by inspection that Enter-to-send is already implemented (it is — the chat has worked this way for many flights).
- **`tabular-nums` on the percent value**: the existing `.t-ctx-pct` rule uses `font-variant-numeric: tabular-nums` so the digits don't shift width as the percent changes. The new warn/crit class is purely color — doesn't affect typography. No regression.
- **Telemetry reset between sessions**: `resetTelemetry` is called on session switch (verify by `grep "resetTelemetry" the_one/interfaces/web/static/js/areas/chat.js`). The new className-reset on `.t-ctx-pct` happens at the same call site — no new wiring needed.

## Files Affected

- `the_one/interfaces/web/static/css/chat.css` — modify `.area-chat .msg.assistant pre` rule; modify `.area-chat .msg.assistant pre code` rule; add `.area-chat .msg.assistant code` rule (inline pill); add `.t-ctx-pct.warn` and `.t-ctx-pct.crit` rules
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` — modify `updateTelemetry` (line ~67-78) and `resetTelemetry` (line ~82-90) to apply warn/crit class to `.t-ctx-pct`
- `the_one/interfaces/web/static/js/areas/chat.js` — add `enterkeyhint="send"` to chat input (line ~83); add `aria-keyshortcuts="Enter"` to send button (line ~85)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (broad pytest exit 0 with 1627p/4s/370d; browser suite 315/35 preserved)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md yet — that happens during the post-L05 commit batch
- [ ] Do NOT commit — Flight Director batches commits after L05

---

## Citation Audit

8 source-code citations verified against current code at leg design time:
- `the_one/interfaces/web/static/css/chat.css:174-181` (`.area-chat .msg.assistant pre`) — OK; matches the hardcoded-bg defect description
- `the_one/interfaces/web/static/css/chat.css:182-187` (`.area-chat .msg.assistant pre code`) — OK
- `the_one/interfaces/web/static/css/components.css:1044-1057` (`.code-block` canonical primitive) — OK
- `the_one/interfaces/web/static/css/tokens.css:121-122` (dark theme `--code-block-bg` / `--code-block-fg`) — OK
- `the_one/interfaces/web/static/css/tokens.css:307-308` (light theme `--code-block-bg` / `--code-block-fg`) — OK
- `the_one/interfaces/web/static/js/markdown.js:724-727` (`INLINE_CODE` → `createElement('code')`) — OK; confirms inline-code emission shape
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js:75-77` (warn/crit class application to `.context-bar`) — OK
- `the_one/interfaces/web/static/js/areas/chat.js:83-85` (chat input + send button innerHTML) — OK
