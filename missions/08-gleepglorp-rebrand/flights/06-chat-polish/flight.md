# Flight: Chat Polish

**Status**: in-flight
**Mission**: [GleepGlorp AI Rebrand & UX Polish](../../mission.md)

## Contributing to Criteria

- [ ] Each functional area (Chat, Studio, Administration) has been reviewed page-by-page and every screen meets a professional polish bar — empty states, loading states, error states, and primary-task flows all feel intentional
- [ ] Per-area routing and navigation behaves correctly across every page within an area: deep links resolve, page refresh restores the visible state, browser back/forward moves through history sensibly, and there are no dead routes, broken back targets, or routes that bounce the user somewhere unexpected
- [ ] Color contrast meets WCAG AA across the rebranded palette for text, interactive elements, and focus indicators
- [ ] Automated browser tests pass after the rebrand and polish work; local visual-snapshot baselines regenerate cleanly post-palette-swap and snapshot tests fail meaningfully on subsequent regression
- [ ] All existing functionality (M01–M07 capabilities) continues working after the rebrand and polish passes — no regression in agent CRUD, provider management, chat persistence, MCP integration, etc.

---

## Pre-Flight

### Objective

Polish the rest of the Chat surface page-by-page now that L03's structural change has moved tool-call/tool-result events out of the conversation stream into per-turn trace shells: welcome canvas (with mascot placement), session list and history bucketing, agent selector, message bubbles, markdown rendering, input field, telemetry overlay, and the M07 OAuth consent button. Resolve routing / refresh-state / back-button issues encountered across these pages. Take opportunistic bug fixes that surface during the polish pass. Along the way, retire two pieces of technical debt explicitly carried forward from F5: (rec #1) refactor `the_one.config.Settings()` to lazy construction so the L01.5 conftest singleton-mutation workaround can be removed, and (rec #4) collapse the three-way `tool_result.content` truncation divergence (live 2000-char vs HTTP-API 4000-char vs replay untruncated) into a single documented contract. Closes with an alignment HAT.

### Open Questions

- [x] **Truncation alignment policy for `tool_result.content` (rec #4)** → Resolved: introduce a single `MAX_TOOL_RESULT_INLINE_CONTENT = 4000` constant in a shared module; apply at every event-projection site (`_broadcast_one`, `_process_and_broadcast`, `messages_to_ui_events`); the HTTP-API `result_messages` consumer continues to use the same constant (already 4000-char today). DB persistence (`encode_messages` / `decode_messages`) stays full-fidelity — the truncation is a PROJECTION concern, not a STORAGE concern. See Design Decisions.
- [x] **Settings lazy-construction shape (rec #1)** → Resolved: introduce a `_get_settings()` lazy accessor in `the_one/config.py` (with internal caching); migrate `from the_one.config import settings` callers to use the accessor or a module-level lazy property; verify the L01.5 singleton-mutation workaround in `tests/conftest.py` can be safely retired post-refactor. See Design Decisions.
- [x] **OAuth `auth_required` auto-open trace shell** → Resolved: REVISIT during F6 HAT (mission convention is operator-judgment for visibility-of-affordance questions). Default: leave behavior as-is per L04 HAT Scenario 8. If F6 HAT discovers real visibility issues, apply the 1-line `details.open = true` fix in `getOrCreateTrace`'s `auth_required` path.
- [x] **OAuth consent button visual treatment** → Resolved: the existing `btn-filled-primary` styling continues to suffice; F6's polish leg may iterate on placement within the trace shell (e.g., spacing, attribution near it) but does NOT restyle the button itself.
- [x] **Closing alignment HAT** → Resolved: included per mission convention (every polish flight closes with an alignment leg).
- [x] **WS-reconnect mid-turn HAT scenario** → Resolved: included in the alignment HAT per F5 debrief Action Item #5 (defensive but unexercised in F5 HAT).
- [x] **Markdown rendering scope** → Resolved: F6's polish leg evaluates the existing `App.markdown.render` output for typography, code-block treatment, table rendering, blockquote, list semantics. Does NOT introduce new markdown extensions (e.g., syntax highlighting, math) — those are future-flight scope.
- [x] **Mascot placement on welcome canvas** → Resolved: F6's first polish leg picks the placement (e.g., above the greeting heading, beside it, or as a watermark) during the vibe iteration — operator-driven aesthetic decision, not pre-committed.

### Design Decisions

**Tool-result truncation: single shared constant + projection-time truncation only**
- Choice: introduce `MAX_TOOL_RESULT_INLINE_CONTENT = 4000` (matches the existing HTTP-API consumer's value). Apply at every PROJECTION site that surfaces tool content to a client: `_broadcast_one` (`app.py:720`), `_process_and_broadcast` (`app.py:853` for WS broadcast; `app.py:863` for HTTP API), and `messages_to_ui_events` (`db/codec.py:144`). DB persistence (`message_to_dict`, `encode_messages`) stays untruncated — full content remains in the SQLite store; truncation is a "what we hand to clients" concern, not a "what we keep" concern.
- Rationale: the current three-way split (2000 / 4000 / untruncated) is vestigial and produces visible inconsistency (refresh shows different content than live). A single constant at projection time gives consistent client-side rendering regardless of which path served the event. 4000 is the larger of the existing values and matches what the HTTP-API consumer already receives — choosing it minimizes the chance of regressing a downstream caller that relied on the higher cap. Codec-untruncated DB storage preserves the option for future "expand to full content" affordances without DB churn.
- Trade-off: a tool that emits a 10KB result still gets truncated client-side, no scroll-to-full UI in this flight. Acceptable — F7 or a follow-up flight can add a "show full content" affordance if the cap proves limiting.
- **Location**: put the constant `MAX_TOOL_RESULT_INLINE_CONTENT = 4000` + a `truncate_for_event(content)` helper in `the_one/db/codec.py`. **Layer-direction constraint**: `the_one/db/codec.py` MUST NOT import from `the_one/interfaces/web/` (db is a lower layer than interfaces). The codec is ALREADY the canonical "Message → event dict" projector via `messages_to_ui_events`; placing the constant there acknowledges that codec.py IS the projection module, and `app.py`'s live broadcast sites call into it. `app.py` already imports from `the_one.db` (e.g., `from the_one.db.codec import encode_messages, decode_messages, messages_to_ui_events` at `app.py:32`), so the import direction is correct. Cycle-1 reviewer caught a pre-fix risk: the original spec proposed `the_one/interfaces/web/event_shapes.py` which would have forced a backwards db→interfaces import. Corrected here.

**Settings lazy construction: module-level lazy property, NOT a get_settings() function**
- Choice: refactor `the_one/config.py` to expose `settings` as a lazy module attribute via `__getattr__` (PEP 562), so the existing `from the_one.config import settings` call sites continue to work but the actual `Settings()` instantiation is deferred to first attribute access. The L01.5 conftest singleton-mutation workaround is retired in the same leg.
- Rationale: an explicit-getter refactor (`_get_settings()` / `get_settings()`) would touch ~11 source-tree call sites in `the_one/` plus ~5 test-file lazy-imports — meaningfully smaller than originally framed but still enough that PEP 562 wins on two grounds: (a) preserves the identity of the `settings` symbol so multiple `settings.X` references within one call site stay valid without rewrites, and (b) zero-touch for the existing test infra (test code keeps `from the_one.config import settings`). The L01.5 singleton-mutation workaround in `tests/conftest.py:54-70` becomes unnecessary because `pytest_configure` sets `THE_ONE_DATA_DIR` BEFORE any test module triggers the first attribute access (verified during F5 L01.5 bisection — `the_one.config` IS imported transitively at conftest load time, but no test code touches `settings.data_dir` at COLLECTION time; access happens later, after `pytest_configure` has run).
- Trade-off: PEP 562 `__getattr__` is slightly more magic than an explicit getter, but it's a well-established Python pattern (used by `logging`, `numpy`, and others for similar deferred-init concerns). Static analyzers (mypy, ruff) handle it cleanly.
- Verification: the conftest fixture `_close_db_singleton_at_session_end` (which closes the aiosqlite singleton at session-end) STAYS — that fix is unrelated to lazy `Settings()` (it's about aiosqlite's `daemon=False` background thread). Only the singleton-mutation block in `pytest_configure` is removed.

**Routing fixes scoped to chat surface only**
- Choice: routing/navigation issues SURFACED during F6's polish legs are fixed in scope; cross-area issues that touch other surfaces get logged as KIs for the F7 UI Performance Audit flight's triage.
- Rationale: F6 is a polish flight, not a routing-refactor flight. Mission-criterion-level routing correctness is a cross-flight responsibility; F6 covers the chat slice.

**Browser-test discipline**
- Choice: per F5's pattern, NO new `pytest.mark.skip` markers added in F6 unless an explicit Known Issue surfaces during HAT and the operator approves. Cap at ≤2 new skips above the F5 baseline.
- Rationale: F5 hit 0 new browser-suite skips (315p/35s baseline preserved exactly). F6's smaller surface area should comfortably hit the same bar. Tight cap keeps the suite drift-free.

**Pixel baselines: regen at flight close in HAT leg**
- Choice: pixel baselines regenerated once at HAT close (mission convention); F6's polish legs do NOT pause for per-leg baseline regen.
- Rationale: matches the L04 cadence. Baselines are local-only (gitignored) regression artifacts, not commit-cadence-relevant.

### Prerequisites

- [ ] F5 merged to main (✓ — commit `8d80545` on origin/main)
- [ ] Broad pytest reliably exits with code 0 (✓ — verified at F5 debrief: 1622 passed in ~91s, exit 0)
- [ ] Browser suite baseline 315p/35s (✓ — verified at F5 debrief)
- [ ] Container `the-one` running and reachable via `docker exec`
- [ ] `make rebuild` available for JS/CSS/Python edits

### Pre-Flight Checklist

- [ ] All open questions resolved
- [ ] Design decisions documented
- [ ] Prerequisites verified
- [ ] Validation approach defined (per-leg automated tests + closing HAT with operator + post-leg browser regression smoke after any leg touching globally-rendered chat chrome)
- [ ] Legs defined

---

## In-Flight

### Technical Approach

**Phase 1 — Infrastructure cleanup (Legs 01 + 02)**. Refactor `Settings()` to lazy via PEP 562 `__getattr__`, then retire the L01.5 conftest singleton-mutation workaround. Verify broad pytest still exits 0. Then collapse the three-way `tool_result.content` truncation into a single shared `MAX_TOOL_RESULT_INLINE_CONTENT = 4000` constant, apply at all 4 projection sites (3 in `app.py`, 1 in `codec.py`), update F5's codec round-trip + WS broadcast integration tests to assert against the constant.

**Phase 2 — Page-by-page polish (Legs 03 + 04 + 05)**. Welcome canvas + session list (with mascot placement decided during vibe iteration); message stream (bubbles, markdown render, input field, telemetry overlay); OAuth consent button + routing/navigation fixes. Each polish leg follows the mission's "vibe leg + operator-driven aesthetic iteration" pattern from F4 / F3.5 / F3 — build aesthetic iterations as gallery scaffolding if needed, graduate the chosen direction back into canonical components, regenerate styles to compose with F3.5 shell chrome + F2 design-language tokens.

**Phase 3 — Alignment HAT (Leg 06)**. Operator HAT across the chat surface in both themes. New scenario: "WS reconnect mid-turn" (per F5 debrief Action Item #5) — operator triggers a network blip mid-tool-turn and verifies the WS-reconnect DOM-lookup self-heal at `chat.js:402-417` actually fires (defensive but unexercised in F5 HAT). **Trigger mechanism pre-committed (cycle-1 reviewer suggestion)**: use Chrome DevTools Network → Offline → wait ~3s → back to Online. Lowest-friction trigger, kills WebSocket fast, matches what F5 debrief AI #5 implicitly assumed. The heavier alternatives (`docker network disconnect` against the container, server-side `await ws.close()` from a debug endpoint) are documented as fallbacks if DevTools-Offline doesn't reproduce the reconnect flow reliably. Plus the standard inheritance from L04 HAT scenarios. Pixel baselines regenerated at HAT close. Mission KIs that surface during HAT get inline-fix-or-logged decisions.

### Checkpoints

- [ ] L01: PEP 562 `__getattr__` lazy-`Settings()` lands; conftest singleton-mutation removed; broad pytest exits code 0 unchanged
- [ ] L02: `MAX_TOOL_RESULT_INLINE_CONTENT = 4000` applied at all 4 projection sites; F5 codec round-trip tests updated to assert truncation; live and replay event streams produce equal `content` strings on equal inputs. **Automated cross-projection-site assertion** (cycle-1 reviewer suggestion): add an integration test that sends a tool whose `ToolResult.content` exceeds the cap and asserts the truncated content is identical across all three projection consumers (WS broadcast event, `session.history` replay, HTTP API `result_messages`). This is the single best regression-net for "did anyone re-introduce per-site truncation drift?"
- [ ] L03: welcome canvas + mascot placement operator-confirmed in both themes; session list / history bucketing / agent selector polished
- [ ] L04: message bubbles, markdown rendering, input field, telemetry overlay all polished to professional bar in both themes
- [ ] L05: OAuth consent button placement decided (revisited from L04 HAT Scenario 8); routing/navigation fixes for chat surface landed
- [ ] L06: HAT scenarios all passing including new WS-reconnect-mid-turn scenario; pixel baselines 12/12 on clean re-run; browser suite ≥ 315p/35s preserved
- [ ] Post-each-leg: broad pytest exits 0 and browser suite preserved (regression smoke per F4 debrief recommendation #5)

### Adaptation Criteria

**Divert if**:
- L01 reveals that PEP 562 `__getattr__` has a hidden incompatibility with the project's static-analysis tooling or with `pydantic-settings` semantics — back out to the explicit-getter alternative, accepting the broader blast radius
- L02 alignment to 4000 chars uncovers a downstream consumer (e.g., a test, a CLI output, a frontend renderer) that relied on the 2000-char cap specifically and breaks — narrow scope, document, schedule consumer fix as separate work
- F6 HAT surfaces a non-trivial chat-surface defect that can't be inline-fixed in the HAT cycle — log as a KI for a follow-up flight, do NOT block F6 close
- New skip count exceeds ≤2 above F5 baseline — pause for operator review

**Acceptable variations**:
- L03 / L04 / L05's vibe iteration sequence is operator-driven; the legs' acceptance criteria are operator-judgment polish-bar checks plus the standard structural assertions (browser suite preserved, pixel regen clean)
- L05's OAuth auto-open re-decision is operator-judgment at HAT — either "stay as-is" or "apply 1-line auto-open fix" is acceptable
- Mascot placement on the welcome canvas is operator-aesthetic
- Markdown polish scope: opportunistic — if a markdown surface (e.g., GFM table styling) is visibly broken, fix in scope; if it's tolerable, leave for a future flight
- Per-flight rule (from F5 debrief): apply enumeration scope-down with operator concurrence if any leg's methodology step becomes theatre once a higher-level criterion is met

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `settings-lazy-refactor` — refactor `Settings()` to lazy via PEP 562 `__getattr__`; retire L01.5 conftest singleton-mutation workaround; broad pytest exit 0 preserved (F5 debrief recommendation #1)
- [x] `tool-result-content-alignment` — single shared `MAX_TOOL_RESULT_INLINE_CONTENT = 4000` constant; apply at 4 projection sites; align F5 codec round-trip tests; resolve live-vs-replay divergence (F5 debrief recommendation #4)
- [x] `welcome-and-session-list-polish` — welcome canvas (with mascot placement), session list and history bucketing, agent selector dropdown
- [x] `message-stream-polish` — message bubbles, markdown rendering, input field, telemetry overlay
- [x] `oauth-and-routing-polish` — M07 OAuth consent button placement (revisit auto-open question), chat-surface routing/navigation fixes, opportunistic bug fixes
- [ ] `chat-alignment-hat` — operator HAT across all polished surfaces; new WS-reconnect-mid-turn scenario; pixel baseline regeneration; browser-suite regression smoke

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged to main
- [ ] Broad pytest exits code 0
- [ ] Browser suite ≥ 315 passing / ≤ 37 skipped (F5 baseline ± 2 new-skip cap)
- [ ] Pixel suite 12/12 on clean re-run
- [ ] L01.5 conftest singleton-mutation workaround removed
- [ ] `tool_result.content` truncation divergence resolved (single constant, projection-time only)
- [ ] agents.md updated to reflect the truncation contract + any L05 routing fixes worth codifying

### Verification

How to confirm the flight achieved its objective:

1. **Settings lazy**: `grep -n "settings\.data_dir = Path" tests/conftest.py` returns empty (the L01.5 singleton-mutation block is gone). Broad pytest still exits 0.
2. **Truncation alignment**: send a tool that emits a 5000-char result; verify the WS broadcast event, the `session.history` rejoin event, AND the HTTP API `result_messages` consumer all show the SAME truncated content (capped at the shared constant).
3. **Chat surface polish bar**: every page (welcome, session list, message stream, OAuth flow) operator-confirmed at HAT in BOTH themes.
4. **Routing**: deep links resolve, hard refresh preserves state, browser back/forward works sensibly across chat pages (HAT verifies; specific failures fixed inline or logged).
5. **WS-reconnect mid-turn**: HAT scenario verifies the DOM-lookup self-heal at `chat.js:402-417` fires correctly (no shell duplication).
6. **No regression in M01–M07**: browser suite 315p/35s exact match (or ≤+2 new skips with documented KI).
7. **Pixel suite clean**: 12/12 on rerun after baseline regen (extends F5's KI #1 closure to F6's restructure).
8. **agents.md current**: the truncation contract is documented; any new patterns (e.g., new helper for projection-time truncation) appear in the WS event-shape contract subsection.
