# Leg: chat-alignment-hat

**Status**: completed
**Flight**: [Chat Polish](../flight.md)

## Objective

Operator-driven HAT (human acceptance test) across all polish surfaces landed in L03 / L04 / L05, plus the L01 / L02 infrastructure work. Verifies polish-bar quality in BOTH themes, exercises the WS-reconnect-mid-turn defensive path (per F5 debrief Action Item #5), regenerates pixel baselines for the local regression net, and resolves the deferred decisions (auto-open trace shell on auth_required; chat-surface routing).

## Context

This is a HAT leg — the Flight Director guides the human through verification steps one at a time. No autonomous Developer / Reviewer agents are spawned for execution. Inline fixes happen during the HAT cycle when the operator surfaces a defect.

L01-L05 are committed to the flight branch (commit `ee72326`); draft PR #52 is open. Broad pytest 1627p/4s/370d and browser suite 315p/35s — both at L05-landed state. Pixel suite baselines are gitignored — regen at HAT close.

## Acceptance Criteria

- [ ] All HAT scenarios pass in BOTH light and dark themes
- [ ] WS-reconnect-mid-turn scenario verifies the `chat.js:402-417` DOM-lookup self-heal works (no duplicate trace shells; no orphaned login-required wrappers)
- [ ] Auto-open trace shell decision resolved (default: stays as-is unless operator surfaces a real visibility concern → 1-line `details.open = true` fix in `getOrCreateTrace`'s auth_required path)
- [ ] Chat-surface routing verification: deep-link `#chat/sessions/{id}` resolves; hard-refresh preserves visible state; back/forward through sessions is sensible
- [ ] Pixel baselines regenerated cleanly post-polish-pass; pixel suite passes 12/12 on a clean re-run after regen
- [ ] Browser suite preserved at 315 / 35 (or ≤ +2 new skips with documented KI)
- [ ] Broad pytest still exits 0 at HAT close

## HAT Scenarios

Each scenario gets walked through one at a time. Operator reports pass / fail / observed; Flight Director either advances or coordinates an inline fix.

### Scenario 1: Welcome canvas mascot placement (BOTH themes)

1. Hard-refresh on `#chat` with no current session (or clear the URL fragment after the session list loads).
2. Verify the GleepGlorp mascot renders centered above the "Hello." greeting at 96px with a subtle drop-shadow.
3. Toggle theme (admin > system > theme); confirm the mascot remains legible and the drop-shadow doesn't disappear or wash out in either theme.
4. Tab from outside the welcome canvas → focus advances to the agent picker / first welcome item. Mascot is NOT in the tab order (decorative, alt="").
5. **Operator decision**: aesthetic acceptable as-is, OR request a one-line CSS revisit (size, margin, drop-shadow tint).

### Scenario 2: Session-list empty state (BOTH themes)

1. With zero sessions, observe the sidebar's `Chat History` heading + the muted "No conversations yet." line.
2. Start a session; placeholder disappears, bucket structure renders.
3. Delete all sessions; placeholder returns under the heading.
4. Toggle theme; verify the empty-state line retains AA contrast in both themes.

### Scenario 3: Code-block and inline-code rendering (BOTH themes)

1. Send a chat message containing both a fenced code block (triple-backtick) and inline `` `code` ``.
2. Verify: fenced block uses theme-aware tokens (dark = terminal black/warning-orange; light = pale slate + dark text with 1px border). Inline code renders as a subtle pill (background tone, ~5px padding, 3px radius). No double-pill nesting inside the fenced block.
3. Toggle theme; both renderings re-paint correctly.

### Scenario 4: Telemetry overlay warn/crit propagation (BOTH themes)

1. Open the chat overlay (hover or focus); accumulate context past 70% (e.g., paste a long passage and chat with an agent that has a low context window — or directly fill via repeated turns).
2. At >=70%: both the context bar AND the `.t-ctx-pct` percent text turn to `--status-warning`.
3. At >=90%: both turn to `--status-danger`.
4. Switch session; both reset to neutral. Toggle theme; colors track tokens.

### Scenario 5: Input field accessibility hints

1. Inspect-element on the chat input → `enterkeyhint="send"` present.
2. Inspect-element on the send button → `aria-keyshortcuts="Enter"` present.
3. (Mobile-only) Verify the virtual keyboard surfaces a "Send" key glyph when chat input is focused.

### Scenario 6: OAuth `auth_required` consent affordance

1. Trigger an MCP auth_required scenario (provider with a configured OAuth flow; trigger a tool that requires consent).
2. Verify the trace body renders: attribution line "Authorization required to continue." (muted, italic, body-sm) ABOVE the existing `btn-filled-primary` button "Login required for {source_name}".
3. The trace-count value in the summary is 1 (NOT 2) for this single auth_required event.
4. Click the button; OAuth popup opens; consent succeeds; the wrapper is removed and the trace shell cleans up if it becomes empty.
5. Reload mid-pause (or trigger a WS reconnect); the wrapper re-renders idempotently — no duplicate buttons, no orphaned attribution lines.

### Scenario 7: Auto-open trace shell on auth_required (DEFERRED DECISION)

1. In Scenario 6, observe whether the trace shell is collapsed (default) or open when the auth_required event fires.
2. **Operator decision**: is the collapsed default acceptable, OR does the affordance need to be auto-revealed when an auth_required event arrives?
3. If auto-reveal is needed, apply the 1-line fix inline: in `getOrCreateTrace`'s caller (or directly in `renderLoginRequiredButton`), set `trace.querySelector('details').open = true` when the appended item is an auth_required group. Re-test Scenario 6 to verify.

### Scenario 8: WS-reconnect-mid-turn (per F5 debrief AI #5)

1. Start a chat turn that takes a few seconds to complete (a tool call with a non-trivial result).
2. Open Chrome DevTools → Network tab → Offline checkbox.
3. Wait ~3 seconds for the WS to close.
4. Uncheck Offline. WS reconnects.
5. Verify: no duplicate trace shell for the in-flight turn; the `getOrCreateTrace` DOM-lookup self-heal (`chat.js:402-417`) re-seeded the bucket from the existing DOM rather than minting a duplicate; the turn either completes normally or a clear status banner explains why it didn't.
6. **Fallback triggers (if DevTools-Offline doesn't kill the WS reliably)**: try `docker network disconnect bridge the-one` from a separate terminal; or `docker stop the-one; docker start the-one`. Document which trigger worked in the flight log.

### Scenario 9: Routing — deep link

1. From a populated session list, copy the URL of an active conversation (`http://localhost:8484/#chat/sessions/{id}`).
2. Open in a new tab. Verify the chat loads the right session.
3. Hard-refresh (Cmd+R / Ctrl+R) on the same URL. Verify visible state is preserved.
4. Browser back (after switching sessions). Verify history navigation behaves sensibly.

### Scenario 10: Pixel baseline regeneration

1. Inside the container: `docker exec the-one pytest -m pixel --snapshot-update --timeout 60` to regen baselines.
2. Re-run: `docker exec the-one pytest -m pixel --timeout 60`. Should pass 12/12.

### Scenario 11: Broad pytest + browser-suite stability

1. `docker exec the-one pytest -x --timeout 30` — exit 0, 1627 passed, 4 skipped, 370 deselected.
2. `docker exec the-one pytest -m browser --timeout 60 --tb=line` — 315 passed, 35 skipped.

## Implementation Guidance

This is a HAT leg — no autonomous Developer is spawned. The Flight Director walks the operator through each scenario in sequence. Inline fixes (CSS tweaks, 1-line JS edits, etc.) happen during the HAT cycle. Larger issues get KI'd to a follow-up flight rather than blocking F6 close.

After HAT closes:
1. Operator commits any HAT-cycle inline fixes (or Flight Director does, per protocol).
2. Flight Director updates this leg's status to `completed` and checks off in flight.md.
3. Flight Director updates flight.md status to `landed` and checks off F6 in mission.md.
4. PR #52 transitions from draft → ready for review.
5. Flight Director signals `[COMPLETE:flight]`.

## Files Affected

Likely none (HAT is verification-only). Inline fixes that surface during HAT are added to whatever file the operator and FD agree on.

---

## Post-Completion Checklist

- [ ] All HAT scenarios resolved (pass / inline-fixed / KI'd)
- [ ] Auto-open decision recorded in flight log
- [ ] Routing verification recorded
- [ ] WS-reconnect scenario recorded (which trigger worked)
- [ ] Pixel baselines regenerated; 12/12 clean rerun
- [ ] Broad pytest + browser suite still preserved
- [ ] flight-log.md updated with HAT findings
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg + flight in artifacts
- [ ] Flight.md status → `landed`
- [ ] PR #52 → ready for review
- [ ] `[COMPLETE:flight]` signal

---

## Citation Audit

3 source-code citations verified against current code at leg design time (post-L05-commit state):
- `the_one/interfaces/web/static/js/areas/chat.js:402-417` — WS-reconnect DOM-lookup self-heal — citation tracked from flight spec; verified at recon and at L05 design review
- `the_one/interfaces/web/static/js/areas/chat/trace-shell.js` — `renderTrace` / `appendToTrace` shape used by Scenario 6's trace-count assertion — OK
- `getOrCreateTrace` in `chat.js:407-424` — target for the optional auto-open 1-line fix at Scenario 7 — OK
