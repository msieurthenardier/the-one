# Mission: UI Maturity

**Status**: completed

> **Closed 2026-07-27 (retroactive).** All 6 flights landed and were debriefed by
> 2026-04-28; the mission was left `active` by oversight and is closed as of the
> F6 debrief date. All 9 success criteria were met (evidence: F1–F6 flight
> debriefs; F6 HAT verified the alignment trio end-state). The UI surface was
> subsequently reworked again by [Mission 17 — UI Redesign](../17-ui-redesign/mission.md).
> Three Known Issues below were punted and remain open backlog as of this close:
> theme generator under Settings, session-cumulative telemetry, and the
> single-line chat input (still `<input>` at `chat.js:301`) — candidates for a
> future mission's planning pool.

## Outcome

The-one's web interface graduates from a functional prototype into a polished, modern application. A coherent visual language runs through every area — consistent typography, spacing, color, and interaction patterns — backed by a theme architecture that supports easy palette and density adjustments. Navigation behaves like a real app: a persistent top bar exposes the current context and an app switcher, and the URL captures enough state that refreshing the page returns the user to where they were. Critical user flows (start a new chat, create an agent, configure a provider) progress without dead-ends or rough edges. The whole surface is exercised by automated browser tests that catch regressions during ongoing iteration. After this mission, the UI meets the quality bar of a modern web application — not "functional and acceptable," but something the user is comfortable showing to other developers.

## Context

After Mission 03, the-one is functionally complete across its three core areas (Chat, Studio, Administration), and the underlying architecture is sound. The UI itself, however, is the weakest part of the system. Specific friction the user has called out:

- **App picker placement is wrong** — currently buried; should be a real top bar with the app name on the left and a hamburger picker on the right
- **Color palette is not accessibility-friendly** and looks dated/boring relative to modern web apps
- **No consistency across areas** — "new <thing>" buttons and form-rendering conventions diverge between Studio and Administration (also flagged in M03 debrief: `studio.js` 822 LOC, `admin.js` 1188 LOC, divergent form patterns)
- **Refreshing the page loses sub-page state** — `#app` hash routing only captures the top-level area, not the entity being viewed/edited
- **Several flows feel awkward** (e.g., starting a new chat) and may need structural rework, not just cosmetic polish
- **No automated UI testing** — every UI bug discovered to date has come from manual HAT or production use

The mission addresses these in two phases. The first three flights lay groundwork: introduce Playwright-based browser testing, establish a design language and theme architecture, and restructure the app shell (top bar, deep-linking, shared form/button primitives). The remaining flights are per-app vibe-coding alignment sessions — one each for Chat, Studio, and Administration — where the user and agent collaboratively bring each area to the new bar. Patterns will emerge during these sessions rather than being prescribed up front.

## Success Criteria

- [x] The interface presents a coherent visual identity — typography, spacing, color, and interaction patterns are consistent across all areas
- [x] The color system meets accessibility contrast standards (WCAG AA) for text, interactive elements, and focus indicators
- [x] Visual themes are swappable without code changes, allowing palette and density adjustments through configuration
- [x] Navigation state (current area and active sub-view, including selected entity) is reflected in the URL and survives page refresh
- [x] A persistent top-level navigation pattern surfaces the current app identity and provides consistent access to the area switcher
- [x] Common interaction patterns (creating a new entity, editing, confirming destructive actions, displaying empty states) behave consistently across all areas
- [x] Critical user flows (start a new chat, create and configure an agent, add and verify a provider) progress without dead-ends, unexplained errors, or unclear next steps
- [x] Automated browser tests cover the critical user flows and fail on regression, runnable both locally and in CI
- [x] Each functional area (Chat, Studio, Administration) reflects the established design language and meets a quality bar suitable for showing to external developers without apology

## Stakeholders

- **Primary user**: Solo developer/operator who interacts with the interface daily and currently finds it functional but visually and ergonomically subpar
- **External developers**: People the user might show the project to — the UI should not require apology or explanation
- **Future self-modification**: The agent itself, which will eventually iterate on its own UI — established patterns and tests reduce the surface area for it to break

## Constraints

- **No frontend frameworks**: Vanilla JS, consistent with existing app-shell architecture. No React, Vue, Svelte, etc.
- **No CSS frameworks**: No Tailwind, Bootstrap, etc. Hand-rolled CSS using custom properties for theming
- **Preserve existing functionality**: All M01-M03 capabilities continue working. No regression in agent CRUD, provider management, model lifecycle, chat persistence, etc.
- **Minimal new dependencies**: Playwright (Python binding, `playwright` PyPI package) is approved for browser testing. No other new runtime dependencies beyond what's already installed
- **Backend-stable**: The mission is primarily frontend. Backend changes are allowed where flows demand restructuring (e.g., new-chat endpoint reshape) but should not be the focus
- **Build on existing seams**: Shared utilities land on the existing `App` namespace (`app.js:128`), not in parallel modules. Per-area CSS continues to use the `.area-{id}` scoping convention; theme tokens must compose with this scoping rather than break it
- **Respect known runtime contracts**: Chat-area changes that touch session lifecycle must respect the C-lite contract (config edits propagate at next rejoin, not mid-message — `app.py:178-243`). The singleton aiosqlite connection (`db/connection.py`) and unbounded `_sessions` dict (`app.py:99`) are known constraints carried forward from M03; flights that touch DB writes or session-join churn must coordinate with them
- **Python 3.11+, async throughout**: Unchanged
- **Small-model friendly**: Patterns established here should remain navigable by 7B-class models when the agent self-modifies
- **Accessibility is a hard requirement**, not a nice-to-have — the existing palette failing WCAG AA is one of the motivating problems

## Environment Requirements

- Local Python 3.11+ with editable install (`pip install -e ".[all-llms,dev]"`)
- Playwright Python binding (`pip install playwright`) and browsers installed via `playwright install` — chosen over the JS binding to keep the toolchain unified with existing pytest infrastructure
- Docker and docker-compose for container testing
- ruff for linting and formatting

## Open Questions

- **Theme system primitive choice**: CSS custom properties are the obvious vanilla-CSS approach, but the boundary between "theme" (palette, typography) and "layout" (spacing, density) needs to be drawn. Resolved in Flight 2 design.
- **Routing scheme for deep-linking**: Hash-based with sub-paths (e.g., `#chat/sessions/abc123`, `#studio/agents/coder`) is the natural extension of current `#chat`/`#studio`/`#admin`. History API (real URLs) is the alternative — requires server-side route handling. Resolved in Flight 3 design.
- **Playwright integration with Concourse pipeline**: Run on every deploy or only locally? If in CI, how does the pipeline launch the app and browsers? Time-boxed in Flight 1 with local-only fallback.
- **Design language anchor**: Without a reference (e.g., Linear, Stripe, terminal-aesthetic, brutalist), vibe-coding flights converge on "whatever the agent thinks looks good." Flight 2 includes design experiments to converge on a direction before committing — committed reference is a flight exit criterion.
- **Persisted UI state location**: Theme selection and "last viewed entity" can live in localStorage (no backend touch) or DB (durable across browsers). localStorage is the lower-risk default; DB persistence inherits the M03 schema-migration-test gap. Resolved in Flight 2 (theme) / Flight 3 (last-viewed) design.

## Known Issues

- **Theme generator under Settings** (HAT follow-up, 2026-04-26) — User suggested a future feature: a Settings UI that exposes load-bearing tokens (palette, glow intensities, alpha values, gradient stops) per theme with live preview, persisted to localStorage or per-user config. Punted from F2 (HAT scope was aesthetic feedback on the designed defaults, not a token editor). Worth a small flight or absorbed into a later mission.

- **Telemetry overlay is per-message, not session-cumulative** (F4 HAT, 2026-04-27) — The telemetry overlay shows the most recent message's input/output token counts and the model's `last_input` as context, replacing each value on every new turn. Per-message `Message.usage` IS persisted in the DB (codec.py:33-35), but the server's `_process_and_broadcast` (app.py:408-410) initializes `total_input = 0` per user-message turn and broadcasts only that turn's totals — never accumulates across the session, never broadcasts a cumulative usage event on session join. Pre-existing F1-F3 behavior; F4 only patched the cross-session bleed-through (telemetry now resets to 0 on session join via `App.chat.resetTelemetry`). To deliver session-cumulative telemetry: walk `session.events`, sum each assistant `Message.usage`, broadcast a cumulative `usage` event on session_joined, and change per-turn initialization to load from session state. Worth a small flight or absorbed into a future telemetry flight.

- **Chat input is single-line `<input>`, not multi-line `<textarea>`** (F4 HAT, 2026-04-27) — The chat input element at `chat.js:66` is `<input data-testid="chat-input" />`. `<input>` elements don't support newlines, so Shift+Enter has no effect (default browser behavior is "ignore"). This is pre-existing F1-F3 behavior — chat has always been single-line. To support multi-line: convert to `<textarea>` with auto-grow on input, set max-height, handle Enter (send) vs Shift+Enter (newline) explicitly, adjust CSS for the new height behavior, audit tests pinning to `[data-testid="chat-input"]` for element-type assumptions. Worth a small flight or absorbed into a future chat-UX polish flight.

### Closed Issues

- **Pre-existing keyboard-operability debt** (surfaced by F2 a11y review, 2026-04-26; closed by F3, 2026-04-27) — Multiple primary navigation/selection elements were rendered as `<div>`/`<span>` with click-only handlers, failing WCAG 2.1.1. Sites: nav rail items (`app.js`), session list items (`chat.js`), agent list items (`studio.js`), admin category items (`admin.js`), inline session/agent delete affordances, inline chip-remove (`studio.js`). **Closed by F3 App Shell Restructure**: leg 02 added semantic landmarks + skip-link + replaced the nav rail with the new top-bar picker (the worst offender went away with the rail itself); leg 03 converted the surviving sites to `<button>` / `role="option"` with keydown handlers, added `:focus-within` reveal for hover-only deletes, and shipped 5 keyboard-state browser tests as the regression guard. See [F3 flight debrief](flights/03-app-shell-restructure/flight-debrief.md).

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [x] Flight 1: **Browser Test Foundation** — Stand up Playwright (Python binding) with a structure for tests that can grow with the mission. Cover the existing critical flows (start a chat, create an agent, configure a provider) as baseline tests and regression guards. Decide and document patterns for visual snapshots, fixtures, and a `@pytest.mark.browser` marker (parallel to the existing `live` marker). CI integration is time-boxed to one leg — fall back to local-only if Concourse-side complexity exceeds the budget. After this flight, every subsequent flight can add tests for its area without re-litigating tooling decisions.

- [x] Flight 2: **Design Language & Theme Architecture** — Run a small set of visual experiments to converge on a design direction with the user. Commit to a concrete reference direction as a flight exit criterion (not just "we tried things"). Implement a theme architecture using CSS custom properties (palette, typography scale, spacing tokens, density) that composes with the existing `.area-{id}` CSS scoping. Replace the current emoji icons (`💬`/`🎨`/`⚙️`) with a coherent icon system. Land an initial accessibility-compliant default theme that meets WCAG AA. Document the design system enough that subsequent vibe-coding flights have shared vocabulary.

- [x] Flight 3: **App Shell Restructure** — Replace the current app picker with a persistent top bar (app name left, area switcher right). Extend hash routing to capture sub-page state so refresh preserves location, with a per-area `serializeState`/`hydrateState` contract. Extract shared form-rendering and "new <thing>" button primitives onto the existing `App` namespace (not as parallel modules), with explicit out-of-scope for provider-type-specific polymorphism (e.g., `__MASKED__` sentinel handling stays in Admin). Restructure new-chat and similar flows where structural rework is required (cosmetic polish belongs in the per-app flights). **May split during flight design** — the form primitive extraction is the riskiest piece and may benefit from isolation in a separate flight.

- [x] Flight 4: **Chat Restructure: Components, Streaming & Markdown** — chat.js component split + shared component CSS lift + hand-rolled markdown library + streaming across all four providers + HAT-style final pass. Re-scoped from the original "Chat Alignment" framing per the F3 debrief (F3 absorbed agent-name header, telemetry overlay, attribution, history bucketing, thinking indicator). See [F4 flight spec](flights/04-chat-restructure/flight.md).

- [x] Flight 5: **Studio Alignment** — Three-section sidebar (Agents/Knowledge/Tools with stub destinations), agent tile grid with header "+ New Agent" button, tabbed agent editor (General/Knowledge/Tools) with save/back/delete action cluster, dirty-state confirm modal, and HAT close. Establishes the codebase's first tab idiom (`App.tabs` with manual activation + roving tabindex), extracts F4-debrief-queued helpers (`App.confirmDelete` for two-step in-place destructive confirm; `App.confirmDialog` for modal blocking decisions). See [F5 flight spec](flights/05-studio-alignment/flight.md).

- [x] Flight 6: **Administration Alignment** — Two-category sidebar (System merges General; LLM Providers stays), provider tile grid mirroring studio (`.entity-tile` lift), provider editor restructure with `[Back] [Cancel] [Save\|Create] [Test]` action cluster + linear `.editor-section` blocks (Connection / Models / Danger Zone), hash routing for `#admin/providers/{id}` and `#admin/providers/new`, `App.confirmDialog` dirty gates on all four routes, editor-Delete migration to `App.confirmDelete` (closes F5 debrief Recommendation 5; helper at 3 permanent consumers). Breaking renames: `.agent-tile` → `.entity-tile`, `.studio-page-header` → `.page-header`, etc. (lift to canonical, no aliases). Closes the alignment trio. See [F6 flight spec](flights/06-administration-alignment/flight.md).
