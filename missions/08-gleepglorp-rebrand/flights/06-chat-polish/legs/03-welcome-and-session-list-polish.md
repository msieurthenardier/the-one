# Leg: welcome-and-session-list-polish

**Status**: completed
**Flight**: [Chat Polish](../flight.md)

## Objective

Polish the chat surface's pre-conversation affordances: place the GleepGlorp mascot on the welcome canvas (per mission criterion: "welcome screen with mascot placement"), introduce an empty-state placeholder for the session list (currently renders nothing when zero sessions exist), and tighten focus / accessibility states on the welcome-list agent picker and session-list items. Out of scope: the native `<select>` agent dropdown popup chrome (deferred per Mission KI #3 — operator skipped at F4) and aesthetic iteration beyond the conservative defaults (vibe iteration deferred to L06 HAT where the operator can review live).

## Context

- **Design Decision (flight.md)**: "Mascot placement on welcome canvas → resolved: F6's first polish leg picks the placement during the vibe iteration — operator-driven aesthetic decision, not pre-committed." Autonomous-mode default chosen here: mascot centered above the existing greeting heading. Operator can iterate at HAT (L06) — placement is a one-line CSS change to revisit.
- **Mission scope (mission.md F6 description)**: "welcome screen (with mascot placement), session list and history bucketing, agent selector". History bucketing was landed in F3 / F4 and already renders `Today / Yesterday / Last 7 Days / Last 30 Days / Older` correctly per `the_one/interfaces/web/static/js/areas/chat/history-buckets.js:6-13` — no structural change needed there. Agent selector is a native `<select>` (Mission KI #3) — leave the dropdown popup alone.
- **Recon (flight-log.md row #8)**: chat surface page-by-page scope distributed across L03 (welcome + session list + agent selector), L04 (message stream), L05 (OAuth + routing).
- **Current welcome canvas DOM** (`the_one/interfaces/web/static/js/areas/chat.js:67-73`): `<div class="chat-welcome"><div class="chat-welcome-inner"><h2 class="chat-welcome-greeting">Hello.</h2><p class="chat-welcome-prompt">…</p><div class="chat-welcome-list">…</div></div></div>`. No mascot element exists today.
- **Current session-list empty handling** (`the_one/interfaces/web/static/js/areas/chat/history-buckets.js:85-86`): `if (!sessions.length) return;` — renders nothing. New users land on chat and see an empty sidebar list with no hint that "Chat History" is below the agent picker.
- **Available mascot assets** (`the_one/interfaces/web/static/brand/`):
  - `gleepglorp_med.png` (1.75 MB; emblem with wordmark)
  - `gleepglorp_small.png` (1.75 MB; emblem with wordmark)
  - `gleepglorp_icon.png` (350 KB; icon-only, NO wordmark — best for welcome canvas since the canvas already has a text greeting)
  - `icon-192.png` (35 KB; smaller icon variant)
  - `gleepglorp_banner.png` (435 KB; already used as `<img class="app-topbar-banner">` per `app.js:29` — wordmark-baked, reserved for top bar)
- **Design tokens available**: `--bezel-shadow-mini`, `--glass-gleam`, `--accent-glow`, `--accent`, `--panel-radius`. The mascot's `drop-shadow` uses `var(--accent-glow)` to echo the focus-visible accent glow already in use on welcome items (`chat.css:217 — "box-shadow: inset 0 0 0 3px var(--accent-glow)"`), keeping the welcome canvas's lighting vocabulary coherent without competing with the welcome-item hover's `--bezel-shadow-mini` box-shadow family.
- **F5 carry-forward**: F5 L02 added the `parent_message_id` discriminator infrastructure. L03 does NOT touch the message stream or trace shell — those are L04 scope.
- **Test infrastructure**: `tests/browser/test_visual_snapshots.py` covers welcome-canvas pixel baselines (`test_snapshot_chat_welcome_*`); the suite is gated by `-m pixel` and excluded from default runs. Pixel baselines are gitignored — regen at HAT (L06), not per-leg, per the flight's pixel-baseline cadence decision.

## Inputs

Files that exist before this leg runs:
- `the_one/interfaces/web/static/js/areas/chat.js` — chat-area init, welcome canvas innerHTML scaffolding at lines 67-73
- `the_one/interfaces/web/static/js/areas/chat/welcome.js` — `renderWelcomeList(welcomeEl, welcomeListEl, agents, setupState, callbacks)` (lines 18-87); the mascot must live in the canvas chrome (chat.js) NOT in this list-renderer (welcome.js is per-render and would re-create the mascot DOM on every state change)
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js` — `renderSessionList(sessionListEl, sessions, currentSessionId, callbacks)` (line 84); current `if (!sessions.length) return;` short-circuits the empty case
- `the_one/interfaces/web/static/css/chat.css` — chat-area styles including `.chat-welcome-inner` (line 211), `.chat-welcome-greeting` (line 212)
- `the_one/interfaces/web/static/brand/gleepglorp_icon.png` — icon-only mascot variant (no wordmark; best fit for welcome canvas)

State that must be true:
- L02 (`tool-result-content-alignment`) landed; broad pytest exits 0 with 1627 passed (per L02 report — L01-baseline 1622 + 5 new tests)
- Container `the-one` running; `make rebuild` available
- Welcome canvas renders correctly in both light + dark themes pre-edit (sanity-check before mascot insertion)

## Outputs

Files modified:
- `the_one/interfaces/web/static/js/areas/chat.js` — adds `<img class="chat-welcome-mascot" src="/static/brand/gleepglorp_icon.png" alt="">` element inside `.chat-welcome-inner` above `.chat-welcome-greeting`. (alt="" intentional — the mascot is decorative; the adjacent `<h2>` provides the semantic anchor.)
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js` — replaces the bare `return` for empty `sessions` with rendering the `// CHAT HISTORY` section title plus a small empty-state placeholder so the heading anchor + empty cue stay consistent with the populated state
- `the_one/interfaces/web/static/css/chat.css` — adds `.chat-welcome-mascot { ... }` rule (size, centering, drop-shadow, light/dark-friendly); adds `.session-list-empty { ... }` rule for the empty-state placeholder

State after:
- Welcome canvas shows the mascot centered above "Hello." greeting in both themes; mascot does not regress accessibility (decorative `alt=""`, focus order unchanged)
- Empty session list renders the `Chat History` heading + a single muted-tone line ("No conversations yet.") rather than nothing — the section title is now consistent across empty + populated states (purely visual / sectional consistency; there is no aria-labelledby relationship between the section title and the per-bucket `role="group"` items, which retain their own per-bucket label anchors)
- All existing browser tests continue to pass; pixel suite NOT re-baselined this leg (regen at L06 HAT per flight's cadence decision — pixel pass-fail will diverge until baselines regen, which is expected; default broad runs exclude pixel via `-m 'not pixel'` in `addopts` per the project's pytest config)
- No regression in welcome-canvas keyboard navigation, agent-picker behavior, or session-join flow

## Acceptance Criteria

- [ ] `the_one/interfaces/web/static/js/areas/chat.js` welcome canvas innerHTML at line ~70 inserts `<img class="chat-welcome-mascot" src="/static/brand/gleepglorp_icon.png" alt="" aria-hidden="true" loading="eager" data-testid="chat-welcome-mascot">` as the first child of `<div class="chat-welcome-inner">`, BEFORE `<h2 class="chat-welcome-greeting">`
- [ ] The mascot `<img>` uses `alt=""` AND `aria-hidden="true"` (decorative — the adjacent greeting provides the semantic label; aria-hidden is belt-and-suspenders against legacy SR behavior that announces empty-alt images by filename) and `loading="eager"` (above-the-fold; explicit eager-load is friendlier than relying on the default) and a `data-testid` for browser-test selectors
- [ ] `the_one/interfaces/web/static/js/areas/chat/history-buckets.js` `renderSessionList` no longer early-returns on empty `sessions`; instead it renders the `Chat History` section title + a single `<div class="session-list-empty">No conversations yet.</div>` placeholder
- [ ] The empty-state placeholder is NOT keyboard-focusable (no `tabindex`, no `role`) — it's purely informational; aria-live not needed because empty→populated transition reloads the whole list
- [ ] `the_one/interfaces/web/static/css/chat.css` adds a `.area-chat .chat-welcome-mascot { ... }` rule with: width/height ~96px (square), `margin: 0 auto 16px auto` (centered, gap to greeting), `display: block`, `filter: drop-shadow(0 4px 12px var(--accent-glow))` or equivalent glass-family shadow, `border-radius: var(--panel-radius)` if the icon's transparent background reveals jaggies (otherwise omit)
- [ ] `the_one/interfaces/web/static/css/chat.css` adds a `.area-chat .session-list-empty { ... }` rule: `padding: 8px 16px`, `color: var(--fg-muted)`, `font-size: var(--font-size-body-sm)`, `font-style: italic` — visually quiet, sibling-aligned to bucket labels
- [ ] Both light AND dark themes render the mascot legibly (the mascot PNG has a transparent background; drop-shadow color must work in both themes — use `var(--accent-glow)` which is theme-aware)
- [ ] Welcome canvas focus order is unchanged: Tab from "Select Agent" picker should still reach the first welcome-list item, NOT the mascot (the `<img>` is not in the tab order by default; verify no regression)
- [ ] No existing browser test selector breaks — `grep -n "chat-welcome\|session-list" tests/browser/*.py` baseline preserved (mascot adds a new test-id, no existing selectors changed)
- [ ] Broad pytest (`docker exec the-one pytest -x --timeout 30`) exits code 0; pass count unchanged from L02 baseline (1627 passed, 4 skipped, 370 deselected) — no NEW failures, no NEW skips
- [ ] Browser suite preserved at 315 passing / 35 skipped (no regression from welcome-canvas DOM addition)
- [ ] No `<select>` popup styling changed — `grep -n "agent-select" the_one/interfaces/web/static/css/chat.css` shows the same 3 rules as pre-edit (lines 16-18 in current file)

## Verification Steps

- **DOM inspection (visual)**: open chat area in both themes after `make rebuild`; confirm mascot appears centered above "Hello." greeting; confirm empty session list shows "No conversations yet." under "Chat History" heading
- **Mascot is decorative**: inspect-element shows `alt=""` on the `<img>`; screen-reader (NVDA / VoiceOver dry-run via DevTools accessibility tree) does NOT announce the image
- **Tab order**: open chat, click sidebar header to focus the agent `<select>`, then press Tab repeatedly. First tab → new-chat button (if visible) / agent picker first item. Mascot is NOT in the tab order.
- **Empty state appears**: in a fresh test container with zero sessions, navigate to chat; the empty-state line renders. Create a session; the placeholder disappears and the bucket structure renders.
- **Light + dark themes**: toggle theme via admin > system > theme; mascot drop-shadow remains visible in both; greeting + prompt + welcome items all retain WCAG contrast (already verified in F1/F3.5, unchanged this leg).
- **Empty-state contrast (new WCAG check)**: verify `.session-list-empty` text (`color: var(--fg-muted)` at `font-size-body-sm`) meets WCAG AA contrast (4.5:1 for body text, since body-sm is below the 18pt "large text" threshold) against the session-list panel background in BOTH themes. If `--fg-muted` fails AA, swap to `var(--fg-secondary)` (the next-darker tier) and re-verify. Use a browser devtools contrast picker or `axe-core` to confirm.
- **Targeted browser tests**: `docker exec the-one pytest tests/browser/test_flow_chat.py -x --timeout 60 -v` — confirm the welcome-canvas flow tests still pass with the new DOM child.
- **Broad pytest**: `docker exec the-one pytest -x --timeout 30` exits 0 with 1627p/4s/370d (L02 baseline preserved).
- **Browser suite**: `docker exec the-one pytest -m browser --timeout 60 --tb=line` exits with 315/35 unchanged. (If any browser test selector breaks due to a `:first-child` selector that now matches the `<img>` instead of the `<h2>`, fix in scope.)
- **`agent-select` untouched**: `grep -c "agent-select" the_one/interfaces/web/static/css/chat.css` returns 3 (same as pre-edit — the 3 rules at lines 16-18). No new occurrences added.

## Implementation Guidance

1. **Edit `the_one/interfaces/web/static/js/areas/chat.js`** (line ~67-73) — insert the mascot `<img>` inside `.chat-welcome-inner`:

   ```javascript
   // BEFORE
   content.innerHTML =
     '<div class="chat-welcome" data-testid="chat-welcome" hidden>' +
       '<div class="chat-welcome-inner">' +
         '<h2 class="chat-welcome-greeting">Hello.</h2>' +
         '<p class="chat-welcome-prompt">Which agent would you like to chat with?</p>' +
         '<div class="chat-welcome-list" role="listbox" aria-label="Available agents"></div>' +
       '</div></div>' +
     '<div class="chat-chrome">' +
     // ... rest unchanged

   // AFTER
   content.innerHTML =
     '<div class="chat-welcome" data-testid="chat-welcome" hidden>' +
       '<div class="chat-welcome-inner">' +
         '<img class="chat-welcome-mascot" src="/static/brand/gleepglorp_icon.png" alt="" aria-hidden="true" loading="eager" data-testid="chat-welcome-mascot">' +
         '<h2 class="chat-welcome-greeting">Hello.</h2>' +
         '<p class="chat-welcome-prompt">Which agent would you like to chat with?</p>' +
         '<div class="chat-welcome-list" role="listbox" aria-label="Available agents"></div>' +
       '</div></div>' +
     '<div class="chat-chrome">' +
     // ... rest unchanged
   ```

2. **Edit `the_one/interfaces/web/static/js/areas/chat/history-buckets.js`** — replace the early-return with empty-state rendering. The `Chat History` heading appears at line 108-111 of current code; lift the heading insertion BEFORE the `if (!sessions.length)` check, then render the empty-state placeholder. Pattern:

   ```javascript
   function renderSessionList(sessionListEl, sessions, currentSessionId, callbacks) {
     sessionListEl.innerHTML = '';

     // Heading always renders so the empty + populated states share an anchor.
     var headingEl = document.createElement('div');
     headingEl.className = 'section-title';
     headingEl.textContent = 'Chat History';
     sessionListEl.appendChild(headingEl);

     if (!sessions.length) {
       var emptyEl = document.createElement('div');
       emptyEl.className = 'session-list-empty';
       emptyEl.textContent = 'No conversations yet.';
       sessionListEl.appendChild(emptyEl);
       return;
     }

     // ... rest of the existing function body (sort, bucket, render groups) —
     // BUT remove the existing in-loop heading append (lines 108-111 in current file)
     // since the heading is now rendered up-front.
   }
   ```

   Verify only ONE `section-title` heading is added (not two — the original code path added it inside the populated branch; that code must be removed in this edit).

3. **Edit `the_one/interfaces/web/static/css/chat.css`** — append two new rules at the end of the existing chat area:

   ```css
   /* Welcome-canvas mascot — decorative, centered above greeting. Drop-shadow
      uses --accent-glow so it sits in the same lighting family as the welcome
      items' hover bezel without competing for prominence. */
   .area-chat .chat-welcome-mascot {
     display: block;
     width: 96px;
     height: 96px;
     margin: 0 auto 16px auto;
     filter: drop-shadow(0 4px 12px var(--accent-glow));
     user-select: none;
     -webkit-user-drag: none;
   }

   /* Session-list empty state — sibling-aligned to the section title, visually
      quiet so it cannot be confused with a session item. */
   .area-chat .session-list-empty {
     padding: 8px 16px;
     color: var(--fg-muted);
     font-size: var(--font-size-body-sm);
     font-style: italic;
   }
   ```

   Place these inside the existing `@layer areas { ... }` block, near the other `.area-chat .chat-welcome-*` rules (around line 224, before the closing `}` of the `@layer`).

4. **Run `make rebuild`** so the JS / CSS changes are picked up by the live container.

5. **Run targeted browser tests first**, then broader suite:

   ```bash
   docker exec the-one pytest tests/browser/test_flow_chat.py -x --timeout 60 -v
   docker exec the-one pytest -x --timeout 30
   docker exec the-one pytest -m browser --timeout 60 --tb=line
   ```

6. **Update flight log** — append a Leg Progress entry for L03 with: mascot placement chosen (centered above greeting, 96px, accent-glow drop-shadow), empty-state pattern landed, default test counts.

7. **Do NOT commit** — Flight Director batches commits after L05.

## Edge Cases

- **Mascot file size**: `gleepglorp_icon.png` is 350 KB — larger than ideal for a welcome-canvas inline asset. The browser caches per `Cache-Control` headers from the FastAPI static mount; first paint is the main concern. Acceptable for this leg (one-time first-visit cost, then cached). A future optimization-flight could trace to SVG or produce a smaller PNG, but it's out of scope here.
- **Mascot in light theme**: the icon PNG is dark-purple on transparent; against the light theme's pale surface it should read clearly. If it doesn't (verify visually in step 4), the fallback is to drop a faint light-tone halo via the drop-shadow rather than swap the asset. Do NOT introduce a theme-conditional asset swap — that's per-theme image variants, out of scope.
- **Welcome-canvas `:first-child` selectors**: `chat.css:169` (`.area-chat .msg.assistant > :first-child { margin-top: 0; }`) is inside `.msg.assistant`, not `.chat-welcome-inner` — unaffected. Verify no other `:first-child` rule under `.chat-welcome-inner` exists before adding the mascot. (Grep `:first-child` in chat.css if uncertain.)
- **Browser test that checks "first child is greeting"**: verified at design time via cycle-1 review — no such assertion exists. `grep` for `chat-welcome-greeting` in `tests/browser/` returns only `tests/browser/test_flow_new_chat.py:39`, which uses the class selector `.chat-welcome-greeting` (not `:first-child` or sibling-position selectors). Mascot insertion is safe. Leaving this edge case noted as confirmed-not-applicable rather than removing it, so a future maintainer who adds such an assertion finds it pre-considered.
- **Session list empty state during fixture race**: in `test_app_websocket_pause_resume.py` and similar fixtures, the session list may briefly be empty between `app.areas.activate('chat')` and the `session_list` event arriving. The empty-state should NOT cause a flake — verify with `tests/browser/test_flow_chat.py` which already exercises the welcome → first-message flow.
- **Heading deduplication**: if step 2's edit accidentally leaves BOTH the up-front heading AND the in-loop heading, the populated state would render two `Chat History` titles. Reviewer should flag if grep `Chat History` in `history-buckets.js` returns more than one literal after the edit.

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat.js` — add mascot `<img>` to welcome canvas innerHTML (~line 70)
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js` — lift `Chat History` heading out of the populated branch; add empty-state placeholder
- `the_one/interfaces/web/static/css/chat.css` — add `.chat-welcome-mascot` and `.session-list-empty` rules

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

7 source-code citations verified against current code at leg design time:
- `the_one/interfaces/web/static/js/areas/chat.js:67-73` (welcome-canvas innerHTML scaffolding) — OK, matches Read output
- `the_one/interfaces/web/static/js/areas/chat/welcome.js:18-87` (`renderWelcomeList` body) — OK
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js:84-86` (`renderSessionList` empty-return) — OK, line 86 contains `if (!sessions.length) return;`
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js:108-111` (`Chat History` heading insertion inside populated branch) — OK
- `the_one/interfaces/web/static/css/chat.css:211-213` (`.chat-welcome-inner` / `.chat-welcome-greeting` rules) — OK
- `the_one/interfaces/web/static/css/chat.css:16` (`.agent-select` rule, NOT to be modified) — OK
- `the_one/interfaces/web/static/js/app.js:29` (`gleepglorp_banner.png` already used for top-bar — reserved, NOT for welcome canvas) — OK
