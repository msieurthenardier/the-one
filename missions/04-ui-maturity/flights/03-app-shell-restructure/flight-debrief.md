# Flight Debrief: App Shell Restructure

**Date**: 2026-04-27
**Flight**: [App Shell Restructure](flight.md)
**Status**: landed
**Duration**: 2026-04-26 → 2026-04-27 (~2 days, including the F2 prerequisite-merge wait)
**Legs Completed**: 7 of 7 (leg 07 absorbed into leg 05's discovery-via-HAT pass)

---

## Outcome Assessment

### Objectives Achieved

- **Top bar replaces the vertical nav rail.** `#app-topbar` ships with the app name on the left and a hamburger picker on the right, keyboard-accessible (Enter/Space/Escape, click-outside dismissal). The existing `--nav-*` palette island carries through; the cyan `::before` left-border accent ports to the active picker option.
- **Hash routing extends to `#area/sub`.** Per-area `serializeState()` / `hydrateState(sub)` contract on the area descriptor. Refresh on `#admin/providers`, `#chat/sessions/<id>`, `#studio/agents/<name>` returns the user where they were. `replaceState` for view-state, `location.hash =` for cross-area; back button exits the area instead of walking sub-views (verified by a `history.length` invariant test).
- **Keyboard operability rebuild closes the M04-known-issue WCAG 2.1.1 debt.** All click-only `<div>`/`<span>` interactive elements (chat sessions, studio agents, admin categories, inline deletes) converted to `<button>` or `role="option"` with keydown activation. `:focus-within` reveals hover-only deletes. Skip-link reaches `#main-content` from the first Tab.
- **New-chat flow restructured via discovery-via-HAT.** Three pain points the user named on first walkthrough: passive sidebar dropdown, "+ new" in the wrong context, silent cold-entry auto-create. Replaced with a state-aware welcome canvas (4 states: no-providers / no-agents / both / ready), dropdown-as-action semantics ("changing the dropdown starts a new conversation"), and a header-mounted "New Chat" affordance bound to the current agent.
- **Server-side resilience improvements** that emerged from a real Sonnet 4.6 chat during HAT: `_process_and_broadcast` always emits `done` (try/except wrapper), `AnthropicProvider` retries without `temperature` on the deprecation `BadRequestError`, WS join handler discards subscribers from the prior session (subscriber leak fix), `ws.onclose` clears the thinking indicator client-side.

### Mission Criteria Advanced

| Mission criterion | Contribution |
|---|---|
| Critical user flows progress without dead-ends | Welcome canvas + new-chat flow restructure + server-side fixes for stuck-on-Thinking |
| Navigation state survives refresh | Per-area `serializeState`/`hydrateState`; refresh verified for chat / studio / admin |
| Persistent top-level navigation pattern | `#app-topbar` with picker + skip-link + landmarks |
| All interactive controls keyboard-reachable | Closes the F2-flagged WCAG 2.1.1 debt |
| Common interaction patterns consistent across areas | Welcome canvas, listbox conventions, dropdown-as-action — partially generalized; F5/F6 will close the rest |
| Automated browser tests cover critical flows | +12 net browser tests (393 + 32 vs 391 + 20 baseline) |

Mission known-issue **"Pre-existing keyboard-operability debt"** (mission.md lines 70-71) is closed by F3. Recommended follow-up action: edit `mission.md` to mark it closed with a citation to this flight.

---

## What Went Well

- **Pre-flight design-review cycles caught real bugs before implementation.** Leg 02 caught the `#main-content` skip-link colliding with the unconditional hashchange listener. Leg 04 caught the `joinSession` optimistic-assignment race and surfaced the `pendingJoinId`/`pendingSelectName` cold-entry pattern. Without those catches, both bugs would have shipped silently.
- **`replaceState` invariant test** (`tests/browser/test_flow_hash_routing.py::test_hash_routing_replacestate_no_history_growth`) is the cleanest acceptance-criterion-to-test mapping in the flight: it asserts the *design property* (back button exits the area) directly via `history.length`, not a surface symptom. Will hold up under refactor.
- **Discovery-via-HAT pattern (leg 05) elicited dropdown-semantics flip.** No autonomous spec could have produced "switching agents from the dropdown starts a new conversation" — the pre-leg dropdown was passive in a way that wasn't visible from the code. The HAT walkthrough surfaced it within minutes.
- **Server-side fix sweep on a real Sonnet 4.6 chat** caught three independent issues (AnthropicProvider temperature deprecation, WS subscriber leak, no-`done`-on-exception path) that no unit/browser test would have surfaced. The interactive HAT pass was the only path to discover them in this flight.
- **Snapshot-policy pivot absorbed cleanly.** Mid-flight policy change ("baselines are gitignored, never committed") invalidated leg 06's planned scope. The replacement scope (pixel marker split + `importorskip` + workflow docs + 3 a11y polish items) is a better fit than the original plan and shipped without disrupting the flight cadence.
- **Architectural seam discovery in leg 04.** The `App.router` namespace was a deferred suggestion at flight design ("reassess after leg 04"); it landed naturally once `parseHash` + `replaceSub` had two real callsites. Right-sized, well-documented, testable invariant.
- **Convention adherence is uniform.** Vanilla JS rules (`var`/`function`, no `let`/`const`/arrow), per-area CSS scoping, `@layer` ordering, affordance vocabulary, `:focus-visible` pattern — all hold across the diff.

---

## What Could Be Improved

### Process

- **Discovery-via-HAT legs need scope guardrails.** Leg 05 absorbed 11 cosmetic tweaks plus 5 server-side fixes plus area renames plus theme-toggle removal — much of it F4 (Chat Alignment) territory. The user explicitly acknowledged it: *"I jumped the gun a little bit and we did a bit of the chat alignment that is supposed to be in flight 4."* (flight-log.md). When the user surfaces "while we're here..." additions during HAT, the Flight Director should weigh divert-to-F4 explicitly rather than absorb. This is a methodology pattern, not a one-off.
- **Mid-flight scope-changing decisions should retrigger flight-level re-plan, not just leg-rewrite.** The snapshot-policy decision invalidated leg 06's scope, leg 02's "failing baselines" inventory, and the flight's "20 baselines committed" exit criterion. The methodology response was to rewrite leg 06 in place. Better practice: when a foundational assumption changes, re-walk the flight checkpoints + open questions + prerequisites and document any reopened items.
- **No screen-reader spot-check recorded.** flight.md verification step ("Manual screen-reader spot-check (NVDA / VoiceOver)") is not documented as having occurred. Functional + automated a11y tests cover landmarks/roles, but the welcome-canvas state machine and chat-history bucket grouping (`role=group` + `aria-labelledby` + conditionally-toggled `role=listbox`) are exactly the kind of thing screen-reader smoke-testing catches.
- **Cross-theme verification of leg 05 cosmetic sweep is uneven.** The 11-tweak sweep (telemetry overlay, attribution, history grouping, thinking indicator) shipped without enumerated per-theme verification.

### Technical

- **`chat.js` LOC growth is the same critical-mass trajectory `admin.js` was on at M03 close.** 423 → 802 lines (+90%). The view-state machine, welcome canvas, telemetry overlay wiring, history bucketing, attribution, thinking indicator, and dropdown-semantics flip all live in one IIFE. **Important.** F4 must not assume chat.js can absorb streaming + markdown rendering without splitting first. Recommended split candidates (each ~50-150 LOC, self-contained): `welcomeCanvas` rendering (chat.js:198-312), `telemetryOverlay` (chat.js:104-121), `historyBuckets` (the date-grouping render), `thinkingIndicator` lifecycle.
- **The `Object.defineProperty` closure-bridge pattern is now an architectural precedent.** Used six times across chat.js / studio.js / admin.js to expose closure state to the descriptor's `serializeState`/`hydrateState`. The flight log notes it as a "deviation"; it's more architectural than that — the design assumed the descriptor was the natural seam, and the implementation reveals descriptor and closure are different scopes glued with `Object.defineProperty`. Acceptable today; document explicitly so future areas know the pattern.
- **`pendingJoinId` / `pendingSelectName` async-hydration pattern is duplicated in chat + studio.** Two copies of the same idiom: stash a target on cold entry, consume in the async-completion handler. Documented as prose in `agents.md`'s Hash routing section, but not lifted into a shared helper. Two-area duplicate doesn't yet justify extraction; if a fourth area arrives or admin grows async sub-state, lift to `App.areas.makePendingState(name)`.
- **AnthropicProvider temperature-retry uses substring match `"temperature" in str(exc).lower()`.** Robust to model-family churn but brittle if Anthropic changes the error wording. Better long-term shape: detect by API-error code / type, or maintain a per-provider parameter-allowlist by model family.
- **Theme `theme-preference-changed` event channel is now dead code.** Compact-variant + multi-mount-sync was deleted in leg 05 when the user moved the theme toggle out of the topbar. The event-broadcast machinery in `theme.js` (lines 90, 153-156) and the `container._themeListenerCleanup` contract still ship but have zero subscribers other than the single Settings mount. Either remove the event plumbing entirely, or accept it as a future-mount affordance and document it as such.
- **chat.js view-state machine is implicit.** At least 4 states (no-providers, no-agents, ready-no-session, in-session) with transitions spread across `checkSetupState`, `session_list`, `session_joined`, `session_deleted`, `startSessionWith`. Tests cover the states; no named state machine or diagram. F4 will add a 5th state (streaming) — name the machine before then.
- **Telemetry overlay test couples to CSS implementation.** `test_flow_new_chat.py:263-269` asserts `getComputedStyle(...).maxWidth in ('0px', '0%')`. If a future refactor uses `display: none` or `opacity: 0` for collapse, the test fails despite identical user-facing behavior. Re-target to user-visible behavior (e.g., assert that telemetry-detail text is hidden via `expect(...).not_to_be_visible()`).
- **Visual snapshots demoted to local-only `pixel` marker — net regression-net loss.** Pre-F3, 12 baselines lived in CI; post-F3, zero do. The agents.md write-up of the "capture per-build artifact, compare against previous build" CI design is excellent but unimplemented. Mitigated by `tests/test_design_tokens_a11y.py` (token regressions) and functional browser tests (DOM-shape regressions); a layout/theme regression would only be caught by humans running `pytest -m pixel` locally until F4-F6 land their visual-stability work.

### Documentation

- **`Object.defineProperty` closure-bridge pattern** is not in agents.md. Add to the Hash routing → Async hydration subsection.
- **Server-side resilience pattern** ("long-running WS handlers must always emit closing events, even on exception") belongs in a new agents.md section. The bug class will recur.
- **Welcome-canvas state-machine pattern** is undocumented. If F5 / F6 reuse it (Studio's empty-editor state would benefit), lift to an agents.md "Patterns" subsection.
- **Mock provider `delay_ms` config knob** belongs in agents.md "Browser test fixtures" — it's the standard way to exercise async UI states (thinking indicator, etc.) deterministically.
- **AnthropicProvider temperature-retry quirk** — comment in code is sufficient, but a "Provider quirks" agents.md subsection would aggregate this kind of model-family vendor wart.

---

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Snapshot baselines gitignored, never committed | User-directed mid-flight policy change | Yes — already captured as user-global instruction |
| Leg 06 scope rewritten in place (snapshot policy invalidated original) | Original "regenerate 12 + add 8 = 20 committed" plan moot | No — but methodology should re-trigger flight-level re-plan when foundational assumptions change |
| Leg 07 absorbed into leg 05 | Discovery-via-HAT serves as continuous HAT throughout | Yes — when discovery-HAT runs end-to-end interactively, separate verification-HAT is rarely additive |
| `Object.defineProperty` closure-bridge for area descriptors | Design assumed descriptor is the natural seam; closure-vs-descriptor mismatch surfaced at impl | Document the pattern; don't standardize the workaround — lift state to descriptor properties when next area justifies refactor |
| `hydrateState` calling convention `areas[areaId].hydrateState(sub)` (preserves `this`) vs spec's `hydrate(sub)` | Method extraction drops `this` | Document as the canonical invocation form |
| Compact theme toggle + multi-mount sync deleted | User moved toggle to Settings only | Sound rejection — theme event plumbing is the residual that should follow |
| Server-side fixes (Anthropic temperature, WS subscriber leak, exception path) absorbed into leg 05 | All three caught during HAT on real Sonnet 4.6 chat | These were unscoped runtime discoveries; no leg-05 acceptance criterion would have caught them. Pattern note: HAT on a real model is a regression-net the test suite cannot replace |
| Listbox-with-button-children deviation accepted (not strict ARIA) | NVDA + VoiceOver both handle it; functionally operable | Documented in agents.md; revisit if a strict-ARIA-conforming AT surfaces issues |
| Roving tabindex dropped in favor of `tabindex="0"` on every option (leg 03) | WCAG-compliant for ~5-20 items; simpler | Re-evaluate when any list grows past ~50 items |

---

## Key Learnings

- **Discovery-via-HAT is the only viable mode for "fix the awkward X flow"** when the awkwardness isn't visible from the code (the F3 dropdown-semantics flip is the canonical case). Cosmetic sweep absorption is a recurring side-effect — guardrails matter.
- **Real-model HAT catches different bugs than test-model HAT.** The Anthropic `temperature` deprecation, WS subscriber leak, and exception-path-no-`done` bug all surfaced from one Sonnet 4.6 chat. The mock provider's new `delay_ms` knob makes the thinking-indicator E2E test deterministic but won't reproduce vendor-side rejections.
- **Pre-flight design-review cycles consistently catch race conditions and listener-collision bugs.** Worth keeping the cap at 2 rounds; round 1 caught the `#main-content` collision (leg 02), round 1 caught the `joinSession` race (leg 04), round 2 was usually documentation cleanup.
- **`replaceState` for view-state vs `pushState` for navigation** is a cleanly testable invariant. The `history.length` test pattern generalizes — any view-state update worth not polluting history is worth this test.
- **`App.router` shape (parseHash + replaceSub)** is an extraction sweet-spot. Two callsites + a clear invariant made it natural; one callsite would have been premature.
- **Architectural debt grows where files cross critical mass.** chat.js mirrors admin.js's M03-era trajectory. Splitting before the next feature wave (F4) is meaningfully cheaper than after.

---

## Recommendations

1. **Re-scope F4 (Chat Alignment) at design time.** F3 absorbed substantial F4 territory: agent-name-as-header, telemetry overlay, attribution, history grouping, thinking indicator. F4's actual scope is narrower — response streaming, markdown / code-block rendering, any HAT-surfaced chat polish. Original mission spec is stale; F4's design should explicitly enumerate what's already done and what remains.

2. **Split chat.js before F4 adds streaming + markdown.** Self-contained extraction candidates: welcome canvas (chat.js:198-312), telemetry overlay (chat.js:104-121), history bucketing, thinking indicator lifecycle. Splitting before the next feature wave avoids the admin.js trajectory. F4 design should include the split as leg 1.

3. **Close M04 known issue "keyboard-operability debt" in `mission.md`.** Edit Known Issues section: strike through (or move to a "Closed Issues" subsection) the keyboard-operability item with a one-line citation to F3. The "Theme generator under Settings" item remains open. One-line edit, debrief follow-up.

4. **Add the patterns surfaced this flight to `agents.md`.** Specifically: (a) the `Object.defineProperty` closure-bridge for area descriptors under Hash routing → Async hydration; (b) the welcome-canvas state-machine pattern under a new Patterns subsection; (c) the server-side "always emit closing event" pattern under Error handling; (d) the mock provider `delay_ms` knob under Browser test fixtures.

5. **Adopt scope guardrails for future discovery-via-HAT legs.** When the user surfaces additions during HAT walkthrough, the Flight Director should weigh divert-to-next-flight explicitly. Pattern: *"That's an F4 item — capturing it in the F4 design notes; want to absorb it now or save it?"* The user can still say "absorb it"; the question forces the explicit choice.

---

## Action Items

- [ ] Edit `mission.md` Known Issues: mark keyboard-operability debt closed with F3 citation
- [ ] Open PR for `flight/03-app-shell-restructure` → `main`; merge after CI green
- [ ] Add `Object.defineProperty` closure-bridge note to `agents.md` Hash routing → Async hydration
- [ ] Add server-side "always emit closing event" pattern note to `agents.md`
- [ ] Add welcome-canvas state-machine pattern note to `agents.md` Patterns subsection
- [ ] Add mock provider `delay_ms` knob note to `agents.md` Browser test fixtures
- [ ] (F4 design phase) Re-scope F4 explicitly given F3's absorbed work; plan chat.js split as F4 leg 1
- [ ] (F4 design phase) Decide markdown rendering library or hand-rolled subset
- [ ] (F4 or later) Replace AnthropicProvider substring-match temperature-retry with structured detection
- [ ] (Optional follow-up) Remove `theme-preference-changed` event plumbing or document the second-mount affordance it preserves
- [ ] (Optional follow-up) Re-target `test_flow_new_chat.py:263-269` telemetry-overlay assertion to user-visible behavior, not CSS specifics
- [ ] (F5/F6 design phase) Run the passive-control audit lens across studio + admin areas; promote dropdown-as-action semantics to a documented project principle if more offenders surface
- [ ] (Future) When pixel regression detection becomes a CI requirement, implement the per-build-artifact comparison design noted in `agents.md`
