# Flight Log: Chat Polish

**Flight**: [Chat Polish](flight.md)

## Summary

Brief overview of execution status and key outcomes. (Populated as legs land.)

---

## Reconnaissance Report

Performed during flight planning (2026-05-14). Source artifacts inspected: F5 debrief Recommendations section + Action Items + L03 carry-forwards documented for F6; mission `08-gleepglorp-rebrand/mission.md` Flight 6 description + Known Issues.

| # | Source | Item | Classification | Evidence | Recommendation |
|---|---|---|---|---|---|
| 1 | F5 debrief rec #1 | Lazy `Settings()` to retire L01.5 singleton-mutation workaround | confirmed-live → L01 | `the_one/config.py:33` still eager-instantiates `settings = Settings()`; `tests/conftest.py:54-70` contains the L01.5 singleton-mutation workaround | Scope into Flight 6 Leg 01 (`settings-lazy-refactor`) |
| 2 | F5 debrief rec #4 | `tool_result.content` truncation divergence — worse than originally diagnosed (THREE distinct values across consumers, not two) | confirmed-live → L02 | `app.py:720` truncates to 2000 (`_broadcast_one`); `app.py:853` truncates to 2000 (`_process_and_broadcast` WS); `app.py:863` truncates to 4000 (`_process_and_broadcast` HTTP API consumer); `db/codec.py:144` no truncation (replay projection) | Scope into Flight 6 Leg 02 (`tool-result-content-alignment`); choose ONE constant for all projection sites |
| 3 | F5 debrief L03 carry-forward (a) | `parent_message_id` namespace contract is binding; do NOT unify live vs replay prefixes | confirmed-live → DESIGN NOTE | L02's live (`{session.id}-msg-N`) vs replay (`replay-msg-N`) prefix split is intentional | Captured as Design Note in flight spec; F6 polish legs do NOT touch the namespace contract |
| 4 | F5 debrief L03 carry-forward (b) | In-flight rejoin namespace-disjoint split is an accepted limitation | confirmed-live → DESIGN NOTE | L04 HAT Scenario 7 operator-confirmed tolerable | Same as #3; do NOT regress against the accepted limitation |
| 5 | F5 debrief L03 carry-forward (c) | OAuth `auth_required` auto-open trace shell deferred decision | confirmed-live → L05 / HAT | L04 HAT Scenario 8 deferred "tolerable as-is, no auto-open" with reviewer-flagged visibility concern | Scope into Flight 6 Leg 05 (`oauth-and-routing-polish`) for HAT-time reconsideration |
| 6 | F5 debrief L03 carry-forward (d) | `tool_result.content[:2000]` truncation divergence is open | duplicate of #2 | Same evidence | Resolved by #2 |
| 7 | F5 debrief AI #5 | F6 HAT design should add "network blip mid-turn" scenario | confirmed-live → L06 HAT | L03's WS-reconnect DOM-lookup self-heal at `chat.js:402-417` is defensive but unexercised in F5 HAT | Scope into Flight 6 Leg 06 (`chat-alignment-hat`) |
| 8 | Mission F6 description | Welcome screen with mascot placement, session list and history bucketing, agent selector, telemetry overlay, markdown rendering, message bubbles, input field, M07 OAuth consent button + routing/navigation fixes | confirmed-live → L03 + L04 + L05 | Mission spec | Distributed across Legs 03, 04, 05 |
| 9 | Mission KI #1 (`.session-agent-badge` race) | RESOLVED in F5 L04 | already-satisfied | `mission.md:86` marked `[x]`; `test_snapshot_chat_with_messages` updated in F5 | Retire — informational only |
| 10 | Mission KI #3 (native `<select>` popup) | Operator-skipped at F4; no F6-scope chat-surface consumer | NOT F6 scope | No `<select>` in chat surface | Carry forward; revisit when a real dropdown UX need surfaces |
| 11 | Mission KI: Broad pytest teardown wedge | RESOLVED in F5 L01.5 | already-satisfied | `mission.md:103` marked `[x]`; conftest changes landed in F5 | Retire — informational only |
| 12 | Mission KI: F6-A5-deadlock sandbox tests | Confirmed-live → NOT F6 scope | `tests/test_mcp_sandbox_integration.py` skips remain | Carry forward; defer to MCP cleanup flight |
| 13 | Mission KI #4 (F4 L07 deferred Studio test files), KI #5 (agent rename PTY keys), KI: post-rebrand browser regressions | Confirmed-live → NOT F6 chat scope | Studio surface | Carry forward |
| 14 | F5 debrief AI #6 | CI invariant: `os.environ["THE_ONE_DATA_DIR"] == str(settings.data_dir)` at session start | confirmed-live → COULD fold into L01 | Defensive check against future import-chain regression of L01.5 fix | Decision: operator explicitly said "no need to pull in anything else" at planning. Carry forward for a future maintenance flight. |
| 15 | F5 debrief AI #7 + #8 | Document structural-assertion pattern + "discriminator at projection time" in agents.md | confirmed-live → NOT F6 scope | Methodology documentation | Carry forward |
| 16 | F5 debrief AI #9 | Extract `_build_tool_event` helper | confirmed-live → NOT F6 scope | Refactor; current duplication readable | Carry forward |
| 17 | F5 debrief AI #10 | Methodology note: revisit prior flights' KI diagnoses during fix-cycles | informational | Process pattern, not code work | Note — applied implicitly by this flight's recon |
| 18 | F5 debrief AI #11 | Spawn-prompt template: time-budget + progress-checkpoint instructions | informational → carry forward | Skill-level update, not project work | Carry forward |

**Summary**: 2 items in F6 scope (rec #1 → L01, rec #4 → L02), 4 items distributed across polish legs (L03, L04, L05) + the HAT (L06), 3 items already-satisfied (mission KIs resolved by F5), 7 items carry-forward to future flights or skill updates. Operator confirmed "no need to pull anything else in" at planning, so AIs #6, #7, #8, #9, #11 are explicitly scoped OUT of F6.

**Open for operator confirmation**: any items where the classification should be overridden — particularly whether AI #6 (CI invariant assertion) should fold into L01 opportunistically since L01 is already refactoring `Settings()` and adding a 1-line assertion is trivial.

---

## Flight Director Notes

### 2026-05-14 — Flight start

- Branch `flight/06-chat-polish` created from `main` (commit `8d80545`)
- Flight status updated to `in-flight`
- Phase file loaded: `the-one/.flightops/agent-crews/leg-execution.md` (project-owned, not the default fallback) — Developer = Sonnet, Reviewer = Haiku. All 5 prompt subsections present with fenced blocks. Structure valid.

### 2026-05-14 — L01 design + design review cycle 1

- L01 (`settings-lazy-refactor`) artifact drafted from flight spec design decisions + recon row #1
- Design review cycle 1: spawned general-purpose Developer agent (Sonnet) for design review
- Findings: 1 high, 1 medium, 1 low + 2 suggestions
  - **[high]** Edge Case #2 incorrectly claimed "every consumer accesses settings.X inside a function body or fixture." Reality: `the_one/interfaces/web/app.py:131` calls `build_default_allowlist(settings.host, settings.port)` at module import time. **Fix applied**: rewrote Edge Case #2 to acknowledge `app.py:131`, justify why it's safe for env-var isolation (pytest_configure runs before collection, before any test imports `web.app`), and added explicit verification list of test modules known to import `web.app` at collection time (`test_ws_responsiveness`, `test_agent_context`, `test_session_lifecycle`, `test_mcp_pool`).
  - **[medium]** Add verification that `from the_one.config import Settings` (the class symbol) still works without invoking `__getattr__`. **Fix applied**: added a new verification step explicitly asserting `Settings.__name__ == "Settings"`.
  - **[low]** REPL check `"settings" in dir(c)` returns False under PEP 562 — `dir()` does NOT enumerate `__getattr__`-only names. **Fix applied**: rewrote verification to probe the cache slot directly (`c._settings is None` before access, not-None after).
  - **Suggestion accepted**: tightened the `tests/conftest.py` import-cleanup language — confirmed the two function-scoped imports (lines 68-69) vanish with the L01.5 block; top-of-file `Path` import at line 8 stays.
- **Cycle-2 decision**: skipped per agentic-workflow Phase 2a step 4. All cycle-1 changes are documentation-clarifications and additive verification steps — no structural change to acceptance criteria, implementation guidance, or files affected. The Edge Case #2 fix is the most substantive and is a documentation enrichment (acknowledging a known module-import-time access and justifying its safety), not a design pivot.
- L01 status → `ready`

### 2026-05-14 — L01 implementation landed

- Spawned general-purpose Developer (Sonnet) to implement L01
- Result: 2 source files changed (config.py +15/-1, conftest.py +1/-15), broad pytest 1622p/4s/370d exit 0 in 97.14s, browser suite 315p/35s preserved at 264.33s — exact F5 baseline match
- No anomalies. All Acceptance Criteria verified including the cycle-1-added Settings-class direct-import check
- L01 status → `landed`. NOT committed per agentic-workflow batched-review protocol; commit batch deferred to post-L05

### 2026-05-14 — L02 design + design review cycle 1

- L02 (`tool-result-content-alignment`) artifact drafted from flight spec design decisions + recon row #2
- Design review cycle 1: spawned general-purpose Developer agent for design review
- Findings: 0 high, 0 medium, 2 low + 3 suggestions
  - **[low]** Acceptance criterion's grep exclusion needed tightening — the leg artifact itself contains literal `tool_result.content[:` strings, so the grep MUST be scoped to `the_one/` not repo root. **Fix applied**: clarified the AC bullet's grep scoping.
  - **[low]** Citation line numbers verified — `app.py:39, :720, :853, :863` and `codec.py:144` are all current. F5 L02's discriminator code did NOT rot the line positions.
  - **Suggestion accepted (locked in)**: cycle-1 reviewer confirmed the cross-projection-site integration test IS realistically constructible from `tests/test_app_websocket_pause_resume.py`'s `StubAgent` + `monkeypatch.setattr(web_app, "_send_to_session", capture)` fixture in ~30 lines. **Fix applied**: removed the "unit-style fallback" escape hatch from both the AC bullet and Implementation Guidance step 4 — full `_process_and_broadcast` path exercise is now required, not preferred. The unit-style fallback would silently hide regressions where `_process_and_broadcast` rewires its own truncation path bypassing the helper.
  - **Suggestion accepted**: pinned the expected pytest count more precisely (1624 passed = L01-landed 1622 + 2 new tests). Helps the implementer catch unexpected count drift.
  - **Reviewer-confirmed**: no other projection sites exist beyond the 4 identified. `_build_session_joined` (app.py:469) emits already-truncated `session.history`; `_build_session_joined_degraded` (app.py:488) routes through `messages_to_ui_events` (the codec.py:144 site, already in scope). Provider sites and CLI site correctly scoped OUT per Edge Cases.
- **Cycle-2 decision**: skipped per agentic-workflow Phase 2a step 4. All cycle-1 changes are low-severity clarifications and one suggestion-driven tightening of the integration-test contract — no structural rework, no changes to file paths or projection-site list.
- L02 status → `ready`

### 2026-05-14 — L02 implementation landed

- Spawned general-purpose Developer (Sonnet) to implement L02
- Result: 4 files touched (codec.py +23/-1, app.py +9/-4, test_db_codec.py +70, new test_tool_result_truncation_alignment.py +136)
- Broad pytest 1627p/4s/370d exit 0 in 93.27s — landed 3 above the predicted 1624 because the Developer split the codec truncation assertion into 4 granular methods (over-cap, at-cap, under-cap, DB-fidelity) instead of one combined. Granularity is acceptable; runtime cost is 0.07s for the file. Browser suite 315p/35s preserved at 259.72s
- Cosmetic line drift in `app.py`: extending the codec import to a multi-line form shifted the three truncation sites from 720/853/863 to 725/858/868. Symbol context (`_broadcast_one`, `_process_and_broadcast` WS branch, `_process_and_broadcast` HTTP API branch) anchors the cites — no semantic drift
- L02 status → `landed`. NOT committed per agentic-workflow batched-review protocol

### 2026-05-14 — L03 design + design review cycle 1

- L03 (`welcome-and-session-list-polish`) artifact drafted with conservative-default scope: mascot on welcome canvas (centered above greeting, 96px, accent-glow drop-shadow); empty-state placeholder on session list; tighten focus / accessibility states. Operator-driven aesthetic iteration deferred to L06 HAT per flight spec's "vibe iteration" framing.
- Design review cycle 1: spawned general-purpose Developer agent for design review
- Findings: 0 high, 2 medium, 2 low + 4 suggestions
  - **[medium]** Context's "same shadow family for consistency" rationale was imprecise — `--bezel-shadow-mini` is a `box-shadow` token, `--accent-glow` flows through `drop-shadow`/`box-shadow`/`inset` glow contexts, and the welcome-item hover's `glass-gleam` is applied as `background-image` not shadow. **Fix applied**: rewrote the Context bullet to cite `chat.css:217`'s `box-shadow: inset 0 0 0 3px var(--accent-glow)` focus-visible glow as the actual consistency anchor, making the lighting-vocabulary rationale precise.
  - **[medium]** No verification step explicitly checked WCAG AA contrast for the new `.session-list-empty` (`--fg-muted` at body-sm size). **Fix applied**: added a new verification step requiring contrast verification against both themes with a documented fallback (swap to `--fg-secondary` if AA fails).
  - **[low]** Outputs language about "section title consistent across empty + populated states" was misleading by implying an aria-labelledby anchor relationship. Reviewer confirmed (via `history-buckets.js:121-127`) that each `<div class="session-group" role="group" aria-labelledby="...">` is labelled by its OWN per-bucket label, not by the `Chat History` title — the title is purely visual/sectional. **Fix applied**: clarified Outputs bullet to make the relationship explicit (visual consistency, no aria coupling).
  - **[low]** Edge case about a hypothetical "first-child is greeting" browser assertion — reviewer verified via grep that NO such assertion exists in `tests/browser/`. **Fix applied**: downgraded the edge case to "confirmed-not-applicable" with the verification evidence inline, kept it noted for future maintainers.
  - **Suggestions accepted**:
    - Add `loading="eager"` to the mascot `<img>` — explicit above-the-fold treatment vs default lazy/auto.
    - Add `aria-hidden="true"` to the mascot `<img>` as belt-and-suspenders against legacy SR behavior that announces empty-alt images by filename.
  - **Suggestions noted (no change needed)**: aesthetic conservatism (96px / centered / accent-glow / one-line CSS revisit at L06 HAT) approved as designed; data-testid future-proofs HAT iteration. Mascot accessibility decision (`alt=""` decorative) defensible — WCAG AA contrast applies to text/interactive elements/focus indicators, not to decorative-image drop-shadow halos.
- **Cycle-2 decision**: skipped per agentic-workflow Phase 2a step 4. All cycle-1 changes are documentation-clarifications + one verification-step addition + two accessibility attributes (`aria-hidden`, `loading`) — additive only, no structural rework.
- L03 status → `ready`

### 2026-05-14 — L03 implementation landed

- Spawned general-purpose Developer (Sonnet) to implement L03
- Result: 3 files touched (chat.js +1, history-buckets.js +16/-9, chat.css +26) for total +43/-9
- Broad pytest 1627p/4s/370d exit 0 in 93.46s — UNCHANGED from L02 baseline. Browser suite 315p/35s preserved at 259.42s
- **WCAG decision (leg-authorized fallback path triggered)**: `--fg-muted` failed AA contrast in light theme (`#64748b` on `#cbd5e1` ≈ 3.1:1 < 4.5:1). Swapped to `--fg-secondary` per the leg's pre-specified fallback. New rule reads `color: var(--fg-secondary)`. Dark `#888` on `#0a0a0a` ≈ 5.6:1; light `#334155` on `#cbd5e1` ≈ 6.8:1. Both pass AA
- Operational note: the orchestrator prompt suggested `docker exec the-one make rebuild` but `make` is host-only. Implementer ran `make rebuild` on host (and `make _ensure-playwright` to restore Chromium after the rebuild target's cache wipe). Future leg prompts should call this out
- L03 status → `landed`. NOT committed per agentic-workflow batched-review protocol

### 2026-05-14 — L04 design + design review cycle 1

- L04 (`message-stream-polish`) artifact drafted with conservative-default scope: 4 surgical polish items deferring vibe iteration to L06 HAT
  - Replace hardcoded `#000` background in `.area-chat .msg.assistant pre` with theme-aware `--code-block-bg` / `--code-block-fg` tokens + add `1px solid var(--border)` framing to match the canonical `.code-block` primitive
  - Add inline `<code>` pill treatment for assistant messages (subtle background, 1-5px padding, 3px radius) — `App.markdown.render` emits inline code but it had no theme-aware styling
  - Telemetry overlay: surface the warn/crit color on `.t-ctx-pct` text alongside the existing context-bar fill class, so the at-a-glance signal works in collapsed-ghost state
  - Chat input gains `enterkeyhint="send"` (mobile semantic); send button gains `aria-keyshortcuts="Enter"` (SR-discoverable shortcut documentation for existing Enter-to-send wiring at chat.js:857-858)
- Design review cycle 1: spawned general-purpose Developer agent for design review
- Findings: 0 high, 0 medium, 2 low + 3 suggestions
  - **[low]** AC wording on the `.area-chat .msg.assistant pre code` reset was ambiguous about which properties are new vs preserved. **Fix applied**: rewrote the AC bullet to make explicit that `padding: 0` and `border-radius: 0` are NEW additions (resisting inheritance from the new inline-code rule), while `background: transparent` is preserved from the existing rule.
  - **[low]** AC "no structural change" wording could be tightened with an explicit verification command. **Fix applied**: rewrote to require `git diff --stat` confinement to the three explicitly-listed files + the leg artifact + flight-log.md.
  - **Reviewer-confirmed (no change needed)**:
    - Specificity math (0,2,1 inline vs 0,2,2 code-in-pre) is correct; source-order also gives a tie-breaker. Override is double-safe.
    - No `tests/browser/` test pins `#000` / `code-block-bg` / `msg.assistant pre` styling. 315/35 preservation realistic.
    - `--border` exists in both themes (`tokens.css:48` dark `#2a2a2a`, `tokens.css:238` light `#e5e7eb`) — the leg's fallback rationale isn't needed but harmless.
    - Enter-to-send wiring confirmed at `chat.js:857-858`. `aria-keyshortcuts="Enter"` accurately documents existing behavior, NOT new wiring.
    - No precedent conflicts for `enterkeyhint` or `aria-keyshortcuts` anywhere in repo.
    - Conservative-scope picked set (4 items) is defensible as the "polish bar" deliverable — no glaring omission.
  - **Suggestions accepted**:
    - Implementer to note which theme(s) used for visual spot-check of warn/crit telemetry color in the flight-log entry.
- **Cycle-2 decision**: skipped per agentic-workflow Phase 2a step 4. Both fixes are wording clarifications; no structural rework.
- L04 status → `ready`

### 2026-05-14 — L06 HAT execution

Operator drove all 11 scenarios in sequence. Final tallies: broad pytest 1627p/4s/370d, browser suite 315p/35s, pixel suite 12/12 on clean rerun after baseline regen. All within F5 baseline.

**Scenario results**:

| # | Scenario | Disposition |
|---|---|---|
| 1 | Mascot placement (both themes) | pass — accept as-is; operator-aesthetic verdict honored |
| 2 | Empty session-list state | pass |
| 3 | Code blocks (themes) + inline pill | pass |
| 4 | Telemetry warn/crit | **deferred to F6.5** — CSS rule fires correctly via DevTools class-flip; underlying token math has a denominator bug that makes real-data exercise unreliable. F6.5 fixes the math, then this scenario can be re-validated organically. |
| 5 | Input field accessibility hints (`enterkeyhint`, `aria-keyshortcuts`) | pass |
| 6 | OAuth `auth_required` consent affordance | pass + **inline copy edit** — operator noted that with the new attribution line ABOVE the button, the button text "Login required for {source_name}" reads as a duplicate statement rather than an action. Changed to "Log in to {source_name}" (1-line edit at chat.js:534; also updated the 2 test assertions in `tests/browser/test_oauth_modal_flow.py:124,144`). Technical deviation from flight spec's "does NOT restyle the button itself" — defensible interpretation: text label is meaning-carrying, not visual styling, so this is a copy edit within polish scope, not a restyle. |
| 7 | Auto-open trace shell on auth_required | **stay as-is** — operator confirmed the Login button rendered visibly in their MCP setup (the direct-mount path, NOT the trace-mounted path). Their MCP emits `auth_required` without a `parent_message_id`, so `getOrCreateTrace` returns null and the wrapper mounts directly to `.messages` via L05's fallback path. The trace auto-open question is moot for their setup. If a different MCP someday emits `auth_required` WITH a parent_message_id (trace-mounted) and surfaces visibility issues, the 1-line `details.open = true` fix in `getOrCreateTrace` is still available for a future flight. |
| 8 | WS-reconnect mid-turn (per F5 debrief AI #5) | **skipped** — DevTools Network → Offline didn't reliably reproduce in operator's setup, and the heavier alternatives (docker network disconnect, docker restart) have unwanted side effects. F5 AI #5's "exercise the defensive WS-reconnect path" remains unexercised, same as F5 HAT. Carry-forward target: a dedicated reliability flight, F7 perf audit, or a future debrief that owns reproducing the network drop as part of its test plan. |
| 9 | Routing — deep link + hard refresh + back/forward | pass + **inline fix** — operator found that hard-refresh or deep-link to a session loaded history but left the scroll at the top instead of the bottom (where the most recent messages are). Root cause: `renderHistory()` runs BEFORE `showChrome()` at `chat.js:739,754` so the messages container has `clientHeight=0` during history append → smart-scroll's pin check evaluates wrong AND any unconditional `scrollHeight` assignment is 0 while hidden. Fix: added an unconditional `messagesEl.scrollTop = messagesEl.scrollHeight` immediately AFTER `showChrome()` in the `session_joined` handler — by then the chrome is visible and scrollHeight reflects the populated history. Verified live: deep-link and hard-refresh both land at the most recent message. |
| 10 | Pixel baseline regeneration | pass — 12/12 baselines regenerated via `UPDATE_SNAPSHOTS=1 docker exec the-one pytest -m pixel` (the `--snapshot-update` CLI flag is registered in `tests/browser/conftest.py` but doesn't reach top-level pytest invocation); subsequent clean rerun without env var also 12/12. Playwright Chromium was wiped by earlier `make rebuild` calls during HAT-cycle fixes; `make _ensure-playwright` restored cleanly. |
| 11 | Broad pytest + browser suite stability | pass — broad 1627p/4s/370d; browser 315p/35s after fixing the 2 `test_oauth_modal_flow.py` assertions broken by the Scenario 6 copy edit |

**Inline fixes landed during HAT** (3 items):

1. **Smart-scroll helper** (chat.js) — Operator surfaced finding #4 from the initial multi-bug report: "auto-scroll forces user down while output is streaming." Added `scrollToBottomIfPinned()` helper with an 80px pin threshold at chat.js:108; replaced 7 unconditional `messagesEl.scrollTop = messagesEl.scrollHeight` callsites with the helper. Smart-scroll only pins to bottom when the user is already near it; if they've scrolled up to read history, leaves them where they are.
2. **Log-in button copy edit** (chat.js + test assertions) — see Scenario 6 above.
3. **Scroll-to-bottom after `showChrome()`** (chat.js) — see Scenario 9 above.

**Other findings raised by the operator during HAT** (5 mission-level KIs added to `mission.md`):

1. `max_context_tokens` hardcoded per provider class, not per model — **blocks F7** until F6.5 fixes
2. Ollama `prompt_tokens` may undercount for some models — pairs with #1 in F6.5
3. No stop / cancel button during active turn — feature work, dedicated flight
4. Long-running conversation loops on local models (qwen via Ollama) — agent-loop investigation, dedicated flight; pairs with #3
5. Telemetry `usage` event fires only after step completion, not during streaming — defer to F6.5 or F7

**F6.5 spawned** (operator-confirmed): a bridging "telemetry-accuracy" flight to fix items #1, #2, and #5 above before F7 can start. Will be planned in a separate session.

### 2026-05-14 — L04 implementation landed

- Spawned general-purpose Developer (Sonnet) to implement L04
- Result: 3 files touched (chat.css +44/-5, telemetry-overlay.js +8/-3, chat.js +2/-2). `git diff --stat` confirmed scope confinement
- Broad pytest 1627p/4s/370d exit 0 in 95.47s — UNCHANGED from L03 baseline. Browser suite 315p/35s preserved at 268.65s
- Visual spot-check: dark theme (default) used for token resolution; light-theme path confirmed by construction-symmetry against the existing `.context-bar.warn`/`.crit` rules that use the same tokens
- L04 status → `landed`. NOT committed per agentic-workflow batched-review protocol

### 2026-05-14 — L05 design + design review cycle 1

- L05 (`oauth-and-routing-polish`) artifact drafted as a tight tie-up-loose-ends leg:
  - Add `<div class="login-required-group">` wrapper around the OAuth Login button with a small attribution line "Authorization required to continue." above the button
  - Wrapper preserves the trace-count semantics (one trace-body child per auth_required event, regardless of how many sub-elements the group contains)
  - Auto-open trace shell question stays DEFERRED to L06 HAT per flight spec
  - Routing/nav fixes: no defects surfaced during L03/L04 polish work; HAT verifies the surface
  - Opportunistic bug fixes: none surfaced
  - Document all three dispositions in flight-log.md FD Notes so L06 HAT has a clear "remaining decisions" surface
- Design review cycle 1: spawned general-purpose Developer agent for design review
- Findings: 2 high, 0 medium, 0 low + 3 suggestions (1 accepted as new AC)
  - **[high]** Citation drift on `chat.css:156-158` → actual current positions are `chat.css:158-160` after L04 edits. **Fix applied**: replace-all across the leg artifact (Context, Inputs, Outputs, Acceptance, Implementation Guidance step 3, Citation Audit) — `156-158` → `158-160`. The `chat.css:214` cite for the `.messages .login-required-btn` rule is unchanged from current code (reviewer verified).
  - **[high]** The cycle-1 implementation snippet for `clearLoginRequiredButton` would have ERASED real existing logic. The actual current body (chat.js:370-391, verified at FD review-incorporation time) uses `querySelectorAll` + a for-loop AND contains the L03 empty-trace-shell cleanup at lines 380-389 (drops the enclosing `.trace-shell` and clears `traceShells[key]` when the trace-body becomes empty). My original `querySelector` + one-shot snippet would have regressed both. **Fix applied**: rewrote Implementation Guidance step 2 as a full BEFORE/AFTER diff against the current 22-line function body; the AFTER preserves the loop, preserves the empty-shell cleanup verbatim, and only changes WHAT is removed (`closest('.login-required-group') || btn`). Also updated the AC bullet for `clearLoginRequiredButton` to make the loop preservation + empty-shell cleanup explicit requirements.
  - **Suggestion accepted as new AC**: added an explicit acceptance criterion "Empty-trace-shell cleanup (chat.js:380-389) still fires after wrapper removal — when the wrapper was the only child of `.trace-body`, the enclosing `.trace-shell` is removed AND `traceShells[key]` is cleared from the registry." Verification pattern documented inline.
  - **Reviewer-confirmed (no change needed)**:
    - Math check on `appendToTrace` wrapper claim is CORRECT — `body.children.length` counts direct children; one wrapper containing two children = 1 direct child = count increments by 1.
    - Routing deferral defensible — `serializeState` (chat.js:8-10) + `hydrateState` (chat.js:11-25) show no obvious defects readable from source alone. The "WS not yet open on cold entry" case is already handled via `_pendingJoinId`. L06 HAT verifies deep-link / refresh / back-button behavior in the live browser.
    - NO OAuth popup-cleanup logic in current `clearLoginRequiredButton` body — my pre-emptive caveat about "preserve popup cleanup" was a false alarm but harmless. **Fix applied**: updated the Edge Case bullet to reflect cycle-1's verified-empty finding.
    - L02 line-drift caveat: the Citation Audit's "implementer should grep if line number rotted" disclaimer is no longer needed — reviewer verified the `chat.css:214` line is stable. **Fix applied**: removed the "may have drifted" disclaimer.
  - **Suggestion noted (no change)**: Implementation step 1's BEFORE snippet ellipses (`// ... (label / textContent / click handler unchanged)`) elide the `tool_call_id`/`resource_metadata_url`/`consent_url` dataset assignments. The AFTER snippet shows them in full, so no functional risk — leaving as-is for brevity.
- **Cycle-2 decision**: skipped per agentic-workflow Phase 2a step 4. Both [high] fixes are CORRECTIONS to align the leg artifact with the actual codebase state (line drift + faithful reproduction of existing function body), NOT design pivots. The leg's design conclusion (wrap in group, mount the group, retarget `clearLoginRequiredButton` to remove wrapper-or-button while preserving the empty-shell cleanup) is unchanged. The new AC bullet on empty-shell cleanup is an additive verification requirement, not a structural design change.
- L05 status → `ready`

### 2026-05-14 — L05 dispositions on HAT-deferred items

- **Auto-open trace shell on auth_required**: stays deferred to L06 HAT per flight spec's "default: leave behavior as-is per L04 HAT Scenario 8" disposition. L05 does NOT change `getOrCreateTrace`'s auth_required path. If the operator surfaces a real visibility concern at HAT, the 1-line `details.open = true` fix can land inline during the HAT cycle.
- **Chat-surface routing/nav fixes**: no defects surfaced during L03 / L04 autonomous-mode polish or implementation. The autonomous-leg surface area cannot exercise deep-link / refresh / back-button behavior the way a human HAT can. L06 HAT enumerates the verification surface (deep-link to `#chat/sessions/{id}` resolves; hard-refresh on a session preserves visible state; browser back/forward through sessions is sensible; new-session URL clear and re-set works). Any defects surfaced at HAT get inline fixes or KI'd to F7 per the flight spec's "Routing fixes scoped to chat surface only" decision.
- **Opportunistic bug fixes**: none surfaced during L03 / L04 polish work. Scope at HAT is the standard "fix-in-scope if quick, log as KI otherwise" pattern.

---

## Leg Progress

### 2026-05-14 — L01 (`settings-lazy-refactor`) landed

- **Changes**:
  - `the_one/config.py`: replaced eager `settings = Settings()` with PEP 562 `__getattr__` + module-level `_settings: Settings | None = None` cache slot. `Settings` class symbol still resolved by normal attribute lookup; only `settings` is routed through the lazy accessor. Unknown attributes raise `AttributeError` with the standard Python-format message.
  - `tests/conftest.py`: removed the F5 L01.5 singleton-mutation block (the `# F5 L01.5: …` comment through `settings.data_dir = Path(_test_data_dir)` line). The `os.environ.setdefault("THE_ONE_DATA_DIR", …)` env-var seed line stays. The autouse session-scoped `_close_db_singleton_at_session_end` fixture is unchanged (unrelated aiosqlite-thread cleanup).
- **Verification**:
  - Lazy construction check (`c._settings is None` pre-access; not-None post-access): PASS
  - Symbol identity check (`s1 is s2`): PASS — caching works
  - `Settings` class directly importable: PASS
  - `grep -n "settings\.data_dir = Path" tests/conftest.py` returns empty: PASS
  - `tests/test_auto_load.py`: 8/8 pass in 1.24s — env-var-derived data_dir honored
  - Broad pytest (`docker exec the-one pytest -x --timeout 30`): **1622 passed, 4 skipped, 370 deselected in 97.14s** — exit 0, matches F5 baseline exactly
  - Browser suite (`pytest -m browser --timeout 60 --tb=line`): **315 passed, 35 skipped, 1646 deselected in 264.33s** — matches F5 baseline exactly (no new skips)
- **Wall time**: ~6.5 min total (broad pytest 1m39 + browser suite 4m27 + setup/verification).
- **Anomalies**: none. The lazy refactor is a clean drop-in; no test code or call site needed changes.
- **Status**: `landed` (final-status flip + flight.md checkbox + commit deferred to post-L05 batch per agentic-workflow protocol).

### 2026-05-14 — L03 (`welcome-and-session-list-polish`) landed

- **Changes** (3 files, +43/-9):
  - `the_one/interfaces/web/static/js/areas/chat.js` (+1): inserted `<img class="chat-welcome-mascot" src="/static/brand/gleepglorp_icon.png" alt="" aria-hidden="true" loading="eager" data-testid="chat-welcome-mascot">` as the first child of `.chat-welcome-inner`, immediately before `<h2 class="chat-welcome-greeting">`.
  - `the_one/interfaces/web/static/js/areas/chat/history-buckets.js` (+16/-9): lifted the `Chat History` `section-title` heading insertion out of the populated branch to the top of `renderSessionList`, then short-circuited the empty case with a `<div class="session-list-empty">No conversations yet.</div>` placeholder. Single `Chat History` literal confirmed by grep post-edit.
  - `the_one/interfaces/web/static/css/chat.css` (+26): added `.area-chat .chat-welcome-mascot` (96px square, centered, accent-glow drop-shadow, no user-select) and `.area-chat .session-list-empty` (8px/16px padding, `--fg-secondary` color, body-sm italic). Inserted at the end of the `@layer areas { ... }` block, after the `.chat-welcome-*` family.
- **WCAG contrast decision** for `.session-list-empty`: leg's first choice was `--fg-muted`. Resolved values from `tokens.css`:
  - Dark theme: `--fg-muted = #a8a8a8` against `--sidebar-bg = --bg = #0a0a0a` → ~8.4:1 (AA pass).
  - Light theme: `--fg-muted = #64748b` against `--sidebar-bg = #cbd5e1` → ~3.1:1 (**AA fail** for body-sm 4.5:1 threshold).
  - Per leg authorization, swapped to `--fg-secondary`: dark `#888888` on `#0a0a0a` → ~5.6:1 (pass); light `#334155` on `#cbd5e1` → ~6.8:1 (pass). Both themes now pass AA. Rationale documented inline in the CSS rule comment.
- **Verification**:
  - `make rebuild` succeeded; static assets refreshed. `_ensure-playwright` re-installed chromium (cache wiped by container rebuild).
  - `grep -c "agent-select" chat.css`: 3 (pre-edit baseline preserved — no select-popup styling touched).
  - `grep "Chat History" history-buckets.js`: 1 occurrence (heading-dedup verified per Edge Case in leg spec).
  - `grep "chat-welcome\|session-list" tests/browser/*.py`: pre-edit selector set (`.chat-welcome-item`, `.chat-welcome-greeting`, `.chat-welcome-prompt`, `.chat-welcome-link`, `[data-testid="chat-welcome"]`, `.session-list`) all preserved — mascot adds NEW `data-testid="chat-welcome-mascot"`, no existing selector changed.
  - Targeted `tests/browser/test_flow_chat.py -m browser`: 2/2 pass in 2.85s.
  - Broad pytest (`docker exec the-one pytest -x --timeout 30`): **1627 passed, 4 skipped, 370 deselected in 93.46s** — exit 0. Pass count UNCHANGED from L02 baseline as predicted.
  - Browser suite (`pytest -m browser --timeout 60 --tb=line`): **315 passed, 35 skipped, 1651 deselected in 259.42s** — matches L01/L02 baseline exactly. No new skips, no new failures.
- **Wall time**: ~9 min total (rebuild + playwright reinstall + targeted + broad pytest + browser suite).
- **Anomalies**:
  - `--fg-muted → --fg-secondary` color swap on `.session-list-empty` (leg-authorized fallback exercised due to light-theme AA failure). The swap matches the leg's pre-specified fallback path; rationale captured inline in the CSS rule.
  - Playwright browser cache was wiped by `make rebuild` (expected per Makefile's `_ensure-playwright` target comment) — required a one-time `make _ensure-playwright` before the browser suite could run. Not a leg regression.
- **Status**: `landed` (final-status flip + flight.md checkbox + commit deferred to post-L05 batch per agentic-workflow protocol).

### 2026-05-14 — L02 (`tool-result-content-alignment`) landed

- **Changes**:
  - `the_one/db/codec.py`: added `MAX_TOOL_RESULT_INLINE_CONTENT = 4000` module-level constant + `truncate_for_event(content: str) -> str` helper (after imports, before `_tool_call_to_dict`). Applied `truncate_for_event` at the `messages_to_ui_events` `tool_result` projection branch. `_tool_result_to_dict`, `message_to_dict`, `message_from_dict`, `encode_messages`, `decode_messages` all UNCHANGED — DB persistence stays full-fidelity.
  - `the_one/interfaces/web/app.py`: extended the existing codec import at line 39 to include `truncate_for_event`. Replaced the three bare slice expressions (`_broadcast_one` `[:2000]`, `_process_and_broadcast` WS `[:2000]`, `_process_and_broadcast` HTTP API `result_messages` `[:4000]`) with `truncate_for_event(msg.tool_result.content)`.
  - `tests/test_db_codec.py`: added a new `TestMessagesToUiEventsTruncation` test class (4 tests): truncate >cap to exact cap, at-cap unchanged, under-cap unchanged, and a DB-round-trip full-fidelity check that proves truncation is projection-only.
  - `tests/test_tool_result_truncation_alignment.py` (new file, 122 lines): exercises the FULL `_process_and_broadcast` path with a `StubAgent` + `monkeypatch.setattr(web_app, "_send_to_session", capture)` fixture; constructs a 5000-char `ToolResult.content`; captures WS-broadcast event, HTTP-API `result_messages` entry, and `messages_to_ui_events` replay projection; asserts all three `content` strings are byte-equal AND exactly `MAX_TOOL_RESULT_INLINE_CONTENT` (4000) long.
- **Verification**:
  - `grep -rn "tool_result\.content\[:" the_one/`: empty (no bare slices remain).
  - Constant + helper smoke: `MAX_TOOL_RESULT_INLINE_CONTENT == 4000`; `truncate_for_event('x' * 5000)` returns `'x' * 4000`; `truncate_for_event('short')` returns `'short'`.
  - `tests/test_db_codec.py`: 26/26 pass in 0.07s — includes the 4 new truncation tests AND the existing `test_tool_result_metadata_round_trip` (DB persistence regression net).
  - `tests/test_tool_result_truncation_alignment.py`: 1/1 pass in 0.20s — cross-projection-site alignment proven.
  - `tests/test_app_websocket_pause_resume.py`: 6/6 pass — adjacent broadcast-path fixture not regressed.
  - Broad pytest (`docker exec the-one pytest -x --timeout 30`): **1627 passed, 4 skipped, 370 deselected in 93.27s** — exit 0. Pass count = L01-landed 1622 + 5 new tests (4 codec class + 1 alignment integration test).
  - Browser suite (`pytest -m browser --timeout 60 --tb=line`): **315 passed, 35 skipped, 1651 deselected in 259.72s** — matches F5/L01 baseline exactly (no new skips).
- **Wall time**: ~7 min total (broad pytest 1m33 + browser suite 4m20 + impl + verification).
- **Anomalies**:
  - Broad pytest landed at **1627**, not the leg-artifact-predicted 1624. Cause: I split the codec truncation assertion into four granular methods inside `TestMessagesToUiEventsTruncation` (truncate, at-cap, under-cap, DB-fidelity) instead of folding all three input regimes into a single method as the Implementation Guidance sketch suggested. Net delta is +3 tests vs the predicted +2, all green, all in the same class — no skips, no failures, no semantic deviation. Granular tests give better failure messages if a future change breaks one regime; opted to keep them split.
  - `_process_and_broadcast` line positions shifted by ~5 (725/858/868) after extending the codec import to multi-line; this is cosmetic and the citation audit anchors the sites by symbol/context, not line.
- **Status**: `landed` (final-status flip + flight.md checkbox + commit deferred to post-L05 batch per agentic-workflow protocol).

### 2026-05-14 — L04 (`message-stream-polish`) landed

- **Changes**:
  - `the_one/interfaces/web/static/css/chat.css`: replaced hardcoded `background: #000; color: var(--status-warning)` in `.area-chat .msg.assistant pre` with theme-aware `var(--code-block-bg)` / `var(--code-block-fg)` tokens; added `border: 1px solid var(--border)` to match the canonical `.code-block` "code well" framing. Added new `.area-chat .msg.assistant code` inline-pill rule (`background: var(--surface-elevated)`, `padding: 1px 5px`, `border-radius: 3px`, mono font, 0.92em). Updated `.area-chat .msg.assistant pre code` to add `padding: 0` and `border-radius: 0` resets so the new inline pill doesn't leak into fenced code blocks. Added `.area-chat .telemetry-overlay .t-ctx-pct.warn { color: var(--status-warning); }` and `.t-ctx-pct.crit { color: var(--status-danger); }` adjacent to the existing `.t-ctx-pct` rule.
  - `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js`: refactored `updateTelemetry` to compute `stateClass` once and apply it to both `.context-bar` (existing) and `.t-ctx-pct` (new). Updated `resetTelemetry` to reset `.t-ctx-pct` className back to its construction-time `'value t-ctx-pct'` base.
  - `the_one/interfaces/web/static/js/areas/chat.js`: chat input gained `enterkeyhint="send"`; send button gained `aria-keyshortcuts="Enter"`. All existing attributes (`data-testid`, `placeholder`, `autocomplete`, `aria-label`, `class`) preserved.
- **Verification**:
  - `git diff --stat` confined to chat.css (+30/-5), telemetry-overlay.js (+8/-3), chat.js (+2/-2) for L04 — confirmed no markdown.js / message-bubble.js / trace-shell.js drift.
  - `grep -n 'enterkeyhint="send"' chat.js` and `grep -n 'aria-keyshortcuts="Enter"' chat.js` both return the expected lines.
  - Targeted browser tests (`pytest tests/browser/test_flow_chat.py -m browser -x --timeout 60`): **2 passed in 2.91s**.
  - Broad pytest (`docker exec the-one pytest -x --timeout 30`): **1627 passed, 4 skipped, 370 deselected in 95.47s** — exit 0, unchanged from L03.
  - Browser suite (`pytest -m browser --timeout 60 --tb=line`): **315 passed, 35 skipped, 1651 deselected in 268.65s** — matches L01-L03 baseline exactly (no new skips, no new failures).
  - Visual spot-check: `var(--status-warning)` resolves to `#f5a623` (dark theme) / `#a16207` (light theme); `var(--status-danger)` resolves to `#ff4a4a` (dark) / `#dc2626` (light). The new `.t-ctx-pct.warn` / `.t-ctx-pct.crit` rules reuse the same tokens already in use by `.context-bar.warn` / `.context-bar.crit`, so percent text and bar fill will render in matching theme-aware colors. Token-resolution check performed against the **dark theme** (default) — symmetry with the existing bar rules confirms the light-theme path by construction. Served chat.css verified via `curl http://localhost:8484/static/css/chat.css` to confirm the new rules made it through the rebuild + container restart.
- **Wall time**: ~12 min total (impl ~2 min + `make rebuild` ~2 min + `_ensure-playwright` restore ~30s + targeted tests 3s + broad pytest 1m35 + browser suite 4m29).
- **Anomalies**:
  - `make rebuild` wiped Playwright Chromium as predicted by the leg artifact's "If rebuild wipes Playwright Chromium" guard; ran `make _ensure-playwright` to restore before the full browser suite — non-issue, just expected docker-image-rebuild churn.
  - No structural deviations from the leg Implementation Guidance. Counts match exactly (1627p/4s/370d broad; 315/35 browser).
- **Status**: `landed` (final-status flip + flight.md checkbox + commit deferred to post-L05 batch per agentic-workflow protocol).

### 2026-05-14 — L05 (`oauth-and-routing-polish`) landed

- **Changes**:
  - `the_one/interfaces/web/static/js/areas/chat.js`: `renderLoginRequiredButton` now constructs a `<div class="login-required-group" data-source-id="...">` wrapper, appends a `<div class="login-required-attribution">Authorization required to continue.</div>` line as the first child, then the existing `<button class="btn-filled-primary login-required-btn">` (text / data-* attributes / click handler preserved verbatim). The wrapper — not the bare button — is mounted via `App.chat.appendToTrace(authTrace, group)` (trace path) or `messagesEl.appendChild(group)` (legacy direct-append path), so `.trace-count` increments by 1 per auth_required event. `clearLoginRequiredButton` (chat.js:370-394) was updated minimally: inside the existing `querySelectorAll` for-loop, capture `var group = btn.closest('.login-required-group')` and let `toRemove = group || btn`; the L03 empty-trace-shell cleanup at the tail of the loop is preserved byte-for-byte (still checks `parent.classList.contains('trace-body')` and drops the `.trace-shell` + clears `traceShells[key]`).
  - `the_one/interfaces/web/static/css/chat.css`: added three new rules — `.area-chat .trace-shell .trace-body .login-required-group` and `.area-chat .messages .login-required-group` (both `align-self: flex-start; display: flex; flex-direction: column; gap: 4px;`) plus `.area-chat .login-required-attribution { color: var(--fg-secondary); font-size: var(--font-size-body-sm); font-style: italic; }`. The pre-existing `.area-chat .trace-shell .trace-body .login-required-btn` (line 158-160) and `.area-chat .messages .login-required-btn` (now line 222) bare-button rules are unchanged.
- **WCAG decision**: swapped to `var(--fg-secondary)` (NOT `--fg-muted`). Calculation: `--fg-muted = #64748b` over the page background `--bg = #fafbfc` (light theme; trace-shell has no own background and inherits up through `.messages` to the page bg-gradient) measures **4.60:1** — passes AA only by 0.10. L03 found `--fg-muted` failed empirically against the same effective background (`--sidebar-bg = var(--bg)`), so the safer, consistent decision is the leg-authorized fallback to `--fg-secondary`. Dark theme: `--fg-muted = #a8a8a8` over `#0a0a0a` → ~8.4:1 (passes AAA), but using `--fg-secondary = #888888` there gives ~6.0:1 which still comfortably passes AA and keeps both themes consistent with one token. Mirrors L03's pattern.
- **Verification**:
  - `git diff --stat` for L05-specific edits confined to: `chat.js` (~17 line-delta to `renderLoginRequiredButton` + ~4 line-delta inside `clearLoginRequiredButton`), `chat.css` (+20 lines for three new rules), `flight-log.md` (FD-Notes disposition entry + this leg-progress entry), and the L05 leg artifact (status flip).
  - Targeted: `tests/test_app_websocket_pause_resume.py` → **6 passed in 0.33s**. `tests/browser/test_flow_chat.py -m browser` → **2 passed in 2.84s**. `tests/browser/test_oauth_modal_flow.py -m browser` → **6 passed in 7.33s** (covers the live OAuth Login-button click path — `.login-required-btn` locator still resolves; click handler still wired to `startLoginFlow`).
  - Broad pytest (`docker exec the-one pytest --timeout 30`): **1627 passed, 4 skipped, 370 deselected in 93.62s** — exit 0, unchanged from L04 baseline.
  - Browser suite (`docker exec the-one pytest -m browser --timeout 60 --tb=line`): **315 passed, 35 skipped, 1651 deselected in 260.03s** — matches L01-L04 baseline exactly.
  - `grep -rn "login-required-btn\|login-required-group\|login-required-attribution" tests/` → only `tests/browser/test_oauth_modal_flow.py` references `.login-required-btn` (6 sites); none use `.firstChild` / sibling-position assertions — the wrapper is transparent to all current test queries.
  - Trace-count semantic verification: by construction, the wrapper is ONE direct child of `.trace-body`, so `appendToTrace` increments `.trace-count` by 1 per auth_required event (matches L05 design intent). `test_app_websocket_pause_resume.py` asserts event presence + `tool_call_id` plumbing, not trace-count values, so no test churn from the count semantic.
  - Empty-trace-shell cleanup verification: the loop body now removes `toRemove = group || btn`, captures `parent = toRemove.parentNode` (which is `.trace-body` in the trace-mount path — same as pre-L05 since the wrapper sits where the bare button used to), and the tail-of-loop cleanup at the next 8 lines is unchanged → still fires when the wrapper was the only `.trace-body` child.
- **Wall time**: ~13 min total (impl ~3 min + `make rebuild` ~2 min + `_ensure-playwright` restore ~30s + targeted tests ~15s + broad pytest 1m34 + browser suite 4m20).
- **Anomalies**:
  - `make rebuild` again wiped Playwright Chromium (predictable docker-image-rebuild churn); `make _ensure-playwright` restored before the full browser suite.
  - No structural deviations from the leg Implementation Guidance. Counts match exactly (1627p/4s/370d broad; 315/35 browser). WCAG decision swapped to `--fg-secondary` per leg-authorized fallback.
- **Status**: `landed` (flight.md checkbox + commit deferred to the post-L05 batch the Flight Director runs after this leg lands).

---

## Decisions

Runtime decisions not in original plan.

---

## Deviations

Departures from planned approach.

---

## Anomalies

Unexpected issues encountered.

---

## Session Notes

Chronological notes from work sessions.

### 2026-05-14 — Architect design-review cycle 1

Spawned Architect (Sonnet) for cycle-1 design review of the F6 spec. Tight time budget (~10 min target) honored — review completed in ~130s.

**Result**: approve with changes. 1 medium + 1 low + 3 non-blocking suggestions + 2 clarifying questions. No high-severity items.

**Cycle-1 changes incorporated**:

- **[medium] Module placement for the shared truncation constant created a backwards layer-import.** Original spec proposed `the_one/interfaces/web/event_shapes.py`. But one of the four projection sites is `the_one/db/codec.py:144`, and `db` must not import from `interfaces`. **Fix**: relocated the constant + helper into `the_one/db/codec.py` itself. The codec IS already the canonical "Message → event dict" projector via `messages_to_ui_events`; placing the constant there acknowledges that. `app.py` already imports from `the_one.db.codec` so the direction is correct. Pre-fix risk caught BEFORE L02 design started — saved a potentially-painful refactor at impl time.
- **[low] PEP 562 blast-radius framing overstated.** Spec said "dozens of files" — actual count is ~11 source-tree imports + ~5 test imports. Conclusion stands (PEP 562 still right) but for stronger reasons: (a) preserves symbol identity for multi-reference call sites, (b) zero-touch for test code. **Fix**: rewrote rationale to lead with these two stronger arguments and dropped the "dozens of files" line.

**Suggestions applied**:
- L02 automated cross-projection-site assertion: added as an explicit Checkpoint sub-item. Single best regression-net against future per-site truncation drift.
- L06 WS-reconnect-mid-turn trigger pinned: Chrome DevTools Network → Offline → wait → Online. Documented heavier fallbacks (`docker network disconnect`, server-side `ws.close()` from a debug endpoint) in case DevTools doesn't reproduce reliably.
- L03 surface-area question: reviewer flagged that "agent selector dropdown" could split out into its own leg vs staying with welcome/session-list. Reviewer's own read was "keep with L03 — it's the last pre-turn affordance the user touches." No change applied; framing stands.

**Suggestions NOT applied (operator-explicit)**:
- L05 OAuth auto-open re-decision framing — reviewer confirmed the "default: stay as-is, revisit only if HAT discovers visibility issues" wording is defensible and does not re-litigate F5 L04 HAT Scenario 8. No change needed.
- F7 scope-boundary protection — reviewer confirmed the spec doesn't accidentally scope performance work into F6. Boundary held.

**Cycle decision**: skipping cycle-2. The cycle-1 changes are confined to (a) module-placement correction (impacts L02 implementation but not flight design shape), (b) docstring tightening, and (c) checkpoint clarifications. No structural rework, no high-severity items. Per agentic-workflow Phase 2a step 4: "Skip if only minor/cosmetic fixes were applied" — applies here.

**Sign-off**: ready for crew sign-off. F6 status → `ready`.

---

### 2026-05-14 — Flight planning

- Read F5 debrief in full; identified 2 user-explicit recommendations to scope in (rec #1 lazy `Settings()`, rec #4 `tool_result.content` truncation)
- Recon verified both items confirmed-live; recon also caught that rec #4 is THREE-way divergence (2000/4000/untruncated) rather than two-way
- Operator confirmed leg breakdown (6 legs) and "no need to pull anything else in" — autonomous-mode decisions on architectural details
- Design Decisions pre-committed in spec: (a) `MAX_TOOL_RESULT_INLINE_CONTENT = 4000` shared constant at all projection sites, DB stays untruncated; (b) PEP 562 `__getattr__` for lazy `Settings()` — preserves `from the_one.config import settings` import surface; (c) OAuth auto-open revisited at HAT (default: stay as-is); (d) ≤2 new browser-suite skips cap; (e) pixel baselines regen at HAT close only
- Reconnaissance report compiled (see above)
