# Mission: GleepGlorp AI Rebrand & UX Polish

**Status**: active

## Outcome

The project's user-facing identity is rebranded from "the-one" to **GleepGlorp AI**, anchored to a new mascot-led purple visual identity. Every surface a user actually sees — browser tab title, top bar wordmark, favicon, page metadata, welcome screens, empty states, FastAPI docs title — reads as GleepGlorp AI. The repository name (`the-one`) and Python module (`the_one`) are deliberately untouched; this is a product-identity change, not a code rename.

On top of the rebrand, each of the three functional areas (Chat, Studio, Administration) is taken page-by-page through a polish pass that brings every screen to a professional bar. The bulk of the polish is cosmetic — typography, spacing, color application, micro-interactions, empty/loading/error states — building on the design system established by Mission 04. One area gets a structural change: in Chat, the **tool-call** and **tool-result** events that today appear as inline messages in the conversation stream are lifted into a per-response *trace* attached to the assistant turn, and the live "thinking" indicator becomes part of that trace shell rather than a sibling chat element. The conversation reads as a clean dialog while the underlying execution remains inspectable on demand. (Adding extended-thinking content from Anthropic's `thinking_blocks` is out of scope for this mission — that's a future provider-shape change.)

Finally, a professional README replaces the project's missing top-level documentation: a clear statement of what GleepGlorp AI is, screenshots of the rebranded UI, install/run instructions, an architecture overview, and a link to the security model.

After this mission, the project looks and reads like a serious product rather than a developer prototype, and the chat surface in particular feels closer to mature LLM clients (Linear-style traces, clean message stream) than to a debug log.

## Context

Mission 04 (UI Maturity) landed the design infrastructure: design tokens, light/dark themes meeting WCAG AA, a persistent top bar, hash-routed deep links, shared form/button primitives, accessibility baseline, and visual-snapshot regression tests. Missions 05 (Built-in Tool Admin), 06 (Maintenance), and 07 (MCP Integration) added new admin surfaces and back-end capability on top of that foundation. The May 2026 maintenance pass found the codebase in healthy shape — no critical debt blocking aesthetic or UX work.

What's left is the gap between "the system has a design language" and "the system has a *brand*", and the gap between "every area works" and "every page is polished." The user has generated a new mascot-based logo (purple-led, friendly robot in a circular emblem) and chosen the product name **GleepGlorp AI**. The domain `gleepglorp.ai` is registered but explicitly out of scope for this mission — no DNS, deployment, or external-hosting work.

A separate motivating concern: today's chat surface treats tool-call and tool-result events as full inline messages in the conversation stream (broadcast and persisted via `session.history`, replayed on rejoin through `db/codec.py::messages_to_ui_events`). For agents that call several tools per turn, this drowns the actual reply in execution noise. The user wants those events to become part of a *trace* attached to the assistant's response — visible on demand, but not cluttering the main message stream — and crucially, the trace must persist across page reload so history hydration renders the same trace structure as live broadcast (otherwise refreshing un-fixes the change).

Bug fixing during this mission is **opportunistic**: anything noticed during polish that's a quick win gets fixed inline; larger issues get logged for a future flight. There is no dedicated bug-bash flight. There is also no dedicated alignment flight — alignment is done as a **leg per flight**, so each area's polish flight ends with a hands-on review pass.

## Success Criteria

- [ ] The product's user-facing identity reads as "GleepGlorp AI" consistently across every screen, browser-level surface (tab title, favicon), and server-rendered metadata
- [ ] A coherent visual identity anchored to the new logo and a purple-led palette is present and consistent across all three areas, in both light and dark themes
- [ ] The visual identity has a deliberate aesthetic direction (robot / control-panel) documented in a live design-language gallery page that's reachable in dev mode and shows tokens, typography, every component variant, controls, indicators, and motion samples in concentrated form
- [ ] Color contrast meets WCAG AA across the rebranded palette for text, interactive elements, and focus indicators
- [ ] Each functional area (Chat, Studio, Administration) has been reviewed page-by-page and every screen meets a professional polish bar — empty states, loading states, error states, and primary-task flows all feel intentional
- [ ] Per-area routing and navigation behaves correctly across every page within an area: deep links resolve, page refresh restores the visible state, browser back/forward moves through history sensibly, and there are no dead routes, broken back targets, or routes that bounce the user somewhere unexpected
- [ ] Browser-side performance has been measured under realistic use (long chat sessions, many agents, repeated area switching) and meets an established memory and responsiveness budget — no unbounded growth across normal interaction, no blocking work that freezes the UI
- [ ] In Chat, tool-call and tool-result events are presented as part of a per-response trace attached to the assistant turn, rather than as inline messages in the conversation stream, and the same trace structure renders on session rejoin from persisted history (not just live broadcast)
- [ ] The M07 OAuth `auth_required` pause-and-replay flow (consent button surfaced in Chat, pause snapshot on rejoin) continues to work after the chat trace restructure
- [ ] All existing functionality (M01–M07 capabilities) continues working after the rebrand and polish passes — no regression in agent CRUD, provider management, chat persistence, MCP integration, etc.
- [ ] The project's top-level documentation introduces GleepGlorp AI as a product — what it is, what it does, how to run it, how it is structured, and where to read the security model — without requiring the reader to dig through code or per-mission artifacts
- [ ] Automated browser tests pass after the rebrand and polish work; local visual-snapshot baselines regenerate cleanly post-palette-swap and snapshot tests fail meaningfully on subsequent regression (baselines are gitignored per project convention — they are a local regression net, not a committed artifact)

## Stakeholders

- **Primary user / operator**: Daily user of the application; wants the system to feel like a finished product rather than a personal prototype
- **External developers**: People shown the project (README, repo, screenshots) — should perceive a serious, polished tool
- **Future self-modification**: The agent itself, which will iterate on its own UI in later missions — a consistent identity and clean component vocabulary reduce the surface area for self-edits to drift

## Constraints

- **Repo and Python module names unchanged**: `the-one` (repo) and `the_one` (Python package) stay as-is. Rebrand is product-identity-only; code-level renames are out of scope
- **No domain / deployment work**: `gleepglorp.ai` DNS, hosting, or public-internet exposure are deferred to a later mission
- **No frontend frameworks / no CSS frameworks**: Vanilla JS + hand-rolled CSS with custom properties, consistent with the M04 architecture
- **Preserve M04 design-system seams**: Theme tokens, `.area-{id}` CSS scoping, the `App` namespace, `App.tabs` / `App.confirmDialog` / `App.confirmDelete` primitives, and the existing visual-snapshot test harness all continue to be the substrate
- **Accessibility is a hard requirement**: New palette must continue to meet WCAG AA; existing keyboard-operability and focus-management guarantees from M04 F3 must not regress
- **Backend-mostly-stable**: The chat trace restructure will require backend event-shape changes (broadcast in `_process_and_broadcast` / `_broadcast_one` in `app.py`, plus the persisted-history hydration path in `db/codec.py::messages_to_ui_events` so rejoin matches live broadcast). The M07 OAuth pause snapshot path (`_send_pause_snapshot_if_needed` in `app.py`) must continue to find the last tool-with-`auth_required` after the event-shape change. Other rebrand and polish work should stay frontend
- **Decouple color from semantic button class names**: The existing `btn-filled-cyan` / `btn-outlined-cyan` class names are baked into ~8 JS files (`dialog.js`, `chat.js`, `admin/provider-models.js`, `studio/agent-editor.js`, etc.) and are *not* theme tokens. Flight 1 mechanically renames them to semantic names (e.g., `btn-filled-primary` / `btn-outlined-primary`) so subsequent polish flights aren't re-litigating color in code
- **Opportunistic bug fixes only**: No dedicated bug-bash flight. Quick wins surface during polish; non-trivial issues are logged as Known Issues here or in the per-flight debriefs
- **No alignment flight**: Each polish flight includes an alignment leg as its closing step; mission-level alignment is folded into per-flight execution
- **Python 3.11+, async throughout**: Unchanged
- **Small-model friendly**: Patterns established here remain navigable by 7B-class models when the agent self-modifies

## Environment Requirements

- Local Python 3.11+ with editable install (`pip install -e ".[all-llms,dev]"`)
- Docker and docker-compose for container testing; `make rebuild` after JS/CSS/Python edits per the project's serving model
- Playwright Python binding installed for browser tests and visual-snapshot regeneration
- An image-processing tool sufficient to resize the source PNG mascot and produce favicon sizes (ImageMagick, `pillow`, or equivalent — flight design picks the specific tool)
- ruff for linting and formatting

## Open Questions

- **Wordmark form**: "GleepGlorp AI" with space and capital `AI` — adopted as the working assumption. Confirm or correct during Flight 1 design.
- **Palette transition**: Default working assumption is purple-led with the existing cyan accent retired. Open: does cyan stay anywhere as a secondary accent, or is it fully replaced? Resolved in Flight 1.
- **Logo derivatives**: The provided PNGs (`gleepglorp_med.png`, `gleepglorp_small.png`) are emblem-style with the wordmark baked into the artwork. Open: do we trace to SVG, extract an icon-only mark from the badge, and/or commission a separate text wordmark for the top bar? Resolved in Flight 1 (brand foundation).
- **Chat trace presentation**: Per-response collapsible inline trace (Linear / Cursor-style — trace folds beneath the assistant message) vs side-panel debugger view vs hybrid. Resolved during the Chat trace flight's design phase.
- **Trace event-shape design**: Two viable shapes — (a) a new top-level `trace` event keyed by parent assistant message id, persisted alongside existing events; (b) discriminator metadata on existing `tool_call` / `tool_result` events plus a frontend grouping layer. Both must round-trip through `messages_to_ui_events` so rejoin matches live broadcast, and both must preserve the M07 `auth_required` pause-snapshot walk. Resolved during the Chat trace flight's design phase.
- **Visual-snapshot baseline regeneration cadence**: Regenerate locally at each flight's close (catches palette regressions early) or once at mission end. Default working assumption is per-flight. Baselines are gitignored — this is a local-workflow question, not a commit cadence.
- **Brand-text sweep scope**: Flight 1 grep-sweeps user-visible references to "the-one" — confirmed surfaces include `index.html:6` `<title>`, `app.py:123` FastAPI title, `app.js:17` topbar wordmark. Need to also audit CLI Rich panel titles, FastAPI route docstring exposure (the auto-generated `/docs` page), and the `agent_name` defaults stored in DB. Decide per-surface what changes and what stays as the internal code label.

- **Specific routing/navigation issues**: Known to exist across pages but enumerated during the per-area polish flights' design phases, not in this mission spec. Each polish flight captures its own catalog and addresses it in scope; cross-area issues that don't fit any single flight roll into the UI Performance Audit flight for triage.

- **Performance budget**: The UI Performance Audit flight's design phase establishes a concrete budget (memory ceiling under representative load, frame budget for interaction-blocking work, time-to-interactive for area switches). The mission asserts the budget must be met but does not pre-commit specific numbers — those are picked from observed baselines in that flight.

## Known Issues

> Emergent blockers and issues discovered during execution. Add items here as flights surface problems that affect the broader mission.

- [ ] **`app_with_agent` browser-test fixture's `.session-agent-badge` doesn't populate** — discovered in Flight 01 Leg 05 HAT during snapshot baseline regeneration. The `app_with_agent` Playwright fixture creates an agent and navigates to chat, but the auto-session-join flow leaves the `<h2 class="session-agent-badge">` element empty (it should contain the agent name once `session_joined` arrives over WebSocket). Blocks the `test_snapshot_chat_with_messages` baselines (dark + light) from regenerating. Pre-existing — pixel tests are excluded from default `pytest` runs (`-m 'not pixel'` in `addopts`) so this rotted silently. Likely root cause: timing race between fixture-created session vs WebSocket connect, OR auto-session-creation path skipping the badge populate when the session is created without a user message yet. Scope: test infrastructure fix, NOT a runtime user-facing bug. Suggested follow-up: assign to a future maintenance pass or include in the chat-area flight (Flight 5 Chat Response Trace or Flight 6 Chat Polish) since they'll touch the same WebSocket / session-join code path.
- [ ] **Stale `.admin-category-item` selector in visual-snapshot test** — discovered in Flight 01 Leg 05 and fixed inline. The class was renamed to `.section-nav-item` during M04/M05 admin-sidebar unification but `tests/browser/test_visual_snapshots.py` was missed because the pixel suite is excluded from default runs. Fix shipped in Flight 01. Documenting here so future similar drift gets flagged: when renaming an HTML class that's referenced from any test path, search both default-run and gated-by-marker test suites (`pytest --collect-only -m pixel` to enumerate the pixel suite).

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [x] Flight 1: **Brand Foundation** — Process the provided mascot PNGs into the asset set the UI actually needs (resized variants, favicon set, possibly an SVG trace and an icon-only mark). Define a starter purple-led palette as theme tokens (light + dark), retire or repurpose the cyan accent, verify WCAG AA across the new token table. Sweep user-visible "the-one" references (`index.html`, topbar wordmark, FastAPI title, CLI Rich panels, auto-generated `/docs`) and rename to `GleepGlorp AI` where appropriate; preserve internal `the_one` package and `the-one` CLI binary names. Mechanically rename `btn-filled-cyan` / `btn-outlined-cyan` CSS class names across all JS call sites to semantic equivalents so subsequent flights don't re-litigate color in code. This flight is the substrate every later flight builds on; nothing else starts until the palette, wordmark, and button rename are committed. (Note: the palette landed here is a *starting point* — Flight 2 may retune it once the aesthetic direction is informing what works.)

- [ ] Flight 2: **Design Language: Robot / Control Panel** — Establish a deliberate aesthetic direction beyond the palette swap. Build a dev-mode-only design-language gallery page under Admin that mirrors current tokens / typography / component variants, then iterate the aesthetic toward a robot / control-panel look (surface treatments, panel chrome, bevels, glow/scanline accents, micro-textures, motion). Apply the chosen direction back into the canonical components (`components.css`, `tokens.css`) so it shows up everywhere, and introduce net-new component primitives only as downstream polish flights actually need them (segmented controls, telemetry strips, status indicators, dial/meter analogues). Retune the Flight 1 palette in context if the aesthetic surfaces hex values that don't work. Re-run the WCAG audit; regenerate visual-snapshot baselines. Closes with an alignment leg. The gallery page persists as live infrastructure that the per-area polish flights align against.

- [ ] Flight 3: **Administration Polish** — Page-by-page pass across the Admin area: System page (general settings, theme toggle, encryption rotation, base prompt), LLM Providers (tile grid + editor including Test connection), Built-in Tools (grid + per-tool editor), and the new dev-mode Design Language category from Flight 2 (cosmetic-only — no structural change to the gallery itself). Cosmetic refinement, consistency tightening against the design language, **routing and navigation fixes** for any deep-link, refresh-state, or back-button issues surfaced on these pages, and opportunistic bug fixes. Closes with an alignment leg.

- [ ] Flight 4: **Studio Polish** — Page-by-page pass across the Studio area: Agents tile grid, Agent editor tabs (General / Knowledge / Tools / MCPs), MCP Sources grid + editor. The MCPs tab is in-scope for *cosmetic* consistency only — no structural change to M07-landed MCP UI. Includes **routing and navigation fixes** for any deep-link, refresh-state, or back-button issues surfaced on these pages. Opportunistic bug fixes. Closes with an alignment leg.

- [ ] Flight 5: **Chat Response Trace** — The mission's one structural change. Lift tool-call / tool-result events out of the inline chat-message stream and present them as part of a per-response trace attached to the assistant turn; reposition the live thinking-indicator as part of the trace shell. Scope explicitly excludes adding extended-thinking content from Anthropic (`thinking_blocks` would be a future provider-shape change). Includes the necessary backend event-shape work spanning live broadcast (`_process_and_broadcast` / `_broadcast_one`) and persisted-history hydration (`db/codec.py::messages_to_ui_events`), with explicit verification that the M07 OAuth pause-and-replay path (`_send_pause_snapshot_if_needed`) continues to find the last tool-with-`auth_required` after the shape change. This flight will likely split during flight design into a design-and-backend leg plus a frontend-presentation leg.

- [ ] Flight 6: **Chat Polish** — Page-by-page pass across the rest of the Chat surface now that tool calls have moved into the trace: welcome screen (with mascot placement), session list and history bucketing, agent selector, telemetry overlay, markdown rendering, message bubbles, input field, and the M07 OAuth consent button. Includes **routing and navigation fixes** for any deep-link, refresh-state, or back-button issues surfaced in Chat. Opportunistic bug fixes. Closes with an alignment leg.

- [ ] Flight 7: **UI Performance Audit** — Now that the rebrand and polish work has landed, evaluate browser-side performance against realistic usage: long-running chat sessions with many turns, large session-history lists, many agents in Studio, repeated area switching, and memory behavior across `App.areas.activate` / `deactivate` cycles. Establish a measurement methodology (DevTools heap snapshots, allocation timeline, performance trace), capture baselines, identify hotspots and leaks, and apply fixes for anything that violates the established budget. Cross-area routing/navigation issues that surfaced during polish flights and weren't fixed in-place get triaged here. Closes with the final local visual-snapshot baseline regeneration for the mission.

- [ ] Flight 8: **Professional README** — Now that every screen reflects the new identity and the app is performant, write a top-level `README.md` that introduces GleepGlorp AI as a product. Capture screenshots of the polished UI in both light and dark themes, include a clear one-paragraph "what this is", an install/run quickstart, an architecture overview (CLAUDE.md and `agents.md` are reference depth; README is product depth), a link to `SECURITY-MODEL.md`, and a pointer to the mission/flight artifact system for contributors. Closes the mission.
