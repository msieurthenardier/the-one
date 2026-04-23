# Flight Debrief: App Shell & Navigation

**Date**: 2026-04-23
**Flight**: [App Shell & Navigation](flight.md)
**Status**: landed
**Duration**: 2026-04-22 – 2026-04-23
**Legs Completed**: 6 of 6 (logical groupings, no formal leg specs)

## Outcome Assessment

### Objectives Achieved

The single-purpose chat page was successfully transformed into an extensible multi-area workspace. The app shell provides hash-based routing, a navigation rail, and consistent sidebar + content panel layout. The Chat area preserves full feature parity with the original UI (WebSocket messaging, session management, telemetry display) while adding source-based session grouping. Studio and Admin areas are stubbed and ready for Flights 3 and 5.

The architecture is genuinely extensible — adding a new area requires only a JS file with an `App.registerArea()` call and a `<script>` tag in index.html. No framework code changes needed.

### Mission Criteria Advanced

- **Web interface organized into switchable functional areas through app-shell architecture** — achieved. Three areas (Chat, Studio, Admin) navigable via icon rail and URL hash. Area registry supports unlimited additional areas.
- **Consistent layout with sidebar + main panel and shared navigation** — achieved. Every area gets the same three-panel structure (nav, sidebar, content). Navigation rail renders from registered area descriptors.
- **Users can select which agent to converse with** — partially. Session management is in place (create, join, delete, list). Agent selection per session is deferred to Flight 4.

## What Went Well

1. **The area registration pattern is clean and extensible.** Each area is a self-contained descriptor with init/activate/deactivate callbacks. The `order` property controls menu position. No coupling between areas — Studio doesn't know Chat exists and vice versa.

2. **Full CSS rewrite was the right call.** Rather than extracting the old inline styles (which were coupled to a single-page layout), designing the CSS around the three-panel architecture from scratch produced a cleaner, more maintainable result. The custom properties design system (`--bg`, `--fg`, `--accent`, etc.) establishes a consistent visual language.

3. **Chat migration preserved all functionality.** WebSocket connection, session CRUD, message rendering by role, telemetry display — everything from the original UI works in the new area context. The WebSocket persistence across area switches means no reconnection delay.

4. **Telemetry display adds real value.** The context bar with warn (70%) and critical (90%) thresholds gives immediate visual feedback on conversation length. Token counters (in/out/ctx) provide transparency into LLM usage. This wasn't in the original flight plan but was low-cost to add.

5. **Minimal HTML scaffold.** The index.html went from ~200+ lines to ~21 lines. All structure is created dynamically by area init functions, making it trivial to add or remove areas.

6. **Lazy initialization prevents wasted work.** Areas only build their DOM on first activation. Returning to an already-initialized area just toggles CSS visibility — preserving scroll position and form state.

## What Could Be Improved

### Process

- **Same retroactive artifact issue as Flight 01.** No spec or design review before implementation. The CSS rewrite deviation (from extraction to full rewrite) would have been a good design review discussion point.
- **No JavaScript tests.** The frontend has zero automated tests. The area registration, hash routing, and message rendering logic could all be tested with a minimal test harness. This is a growing gap as the frontend becomes more complex.

### Technical

- **No Shift+Enter for multi-line input.** The chat input sends on Enter with no multi-line support. For an agent workspace where users might paste code blocks, this is a significant UX limitation.
- **No markdown or syntax highlighting in messages.** Assistant responses and tool results render as plain text with `white-space: pre-wrap`. Code blocks, lists, and links are not formatted. This will become more noticeable as agents produce richer responses.
- **Hard-coded display limits without indication.** Tool results truncated at 2000 chars and session titles at 50 chars, with no visual indicator that truncation occurred. Users may not realize they're seeing partial content.
- **No error handling UI.** WebSocket disconnect shows a status indicator but no reconnection UI or error messages. If the server goes down, the user sees a gray dot but no guidance.
- **Duplicate message handling paths.** Both `/api/chat` (REST) and `/ws` (WebSocket) process messages through slightly different code paths. The REST endpoint creates ephemeral sessions while the WebSocket uses the session registry. This divergence could lead to inconsistent behavior.
- **Session auto-selection heuristic.** On startup, Chat joins the first session in the list (newest). There's no "remember last session" or "show session picker" flow. Users returning to the app may be confused about which conversation they're in.
- **IIFE module pattern in app.js.** The `App` module uses an IIFE returning a public API object. While functional, ES6 modules would be cleaner and enable future tree-shaking. However, this would require a build step or `type="module"` script loading, which may not be worth the complexity yet.
- **No accessibility considerations.** No ARIA labels, keyboard navigation, focus management, or screen reader support. The navigation rail and session list are click-only.

### Documentation

- **No JSDoc or inline comments.** The JavaScript files have no documentation comments. The area registration API, WebSocket protocol, and message type handling are non-obvious and would benefit from brief documentation.
- **WebSocket protocol is undocumented.** The message types (`session_list`, `session_joined`, `user`, `assistant`, `tool_call`, `tool_result`, `usage`, `done`) are implicit in the code. A protocol reference would help future UI work.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Full CSS rewrite instead of extraction | Old styles coupled to single-page layout; cleaner to design for three-panel architecture | Yes — when layout fundamentally changes, rewrite CSS rather than adapt |
| Telemetry display added (not in flight plan) | Low-cost addition using existing WebSocket data; high user value | Yes — small, high-value additions during implementation are acceptable when they don't expand scope significantly |
| IIFE module pattern instead of ES6 modules | No build step required; works with simple `<script>` loading | Revisit — if frontend grows beyond 5-6 files, consider ES6 modules with `type="module"` |

## Key Learnings

1. **The area registry pattern scales well for vanilla JS.** Without a framework, a simple registry with lifecycle callbacks (init, activate, deactivate) provides sufficient structure. The pattern is familiar enough that small models can generate new areas from examples.

2. **CSS custom properties are essential for vanilla CSS at scale.** The design system variables make it trivial to adjust colors, sizing, and spacing globally. Without a preprocessor, custom properties fill the same role as Sass variables.

3. **Hash routing is the right choice for this project.** No build step, no server routing, deep-linkable areas, browser back/forward works. The simplicity aligns with the "no frontend frameworks" constraint.

4. **WebSocket persistence across areas was the right call.** Closing the WebSocket on area switch would create reconnection delays and potential message loss. The resource cost of keeping it open is negligible for a single-user app.

5. **Session source grouping was a late addition that improves UX significantly.** Distinguishing between web, API, and external sessions prevents confusion about where conversations originated. Worth doing from the start rather than retrofitting.

## Recommendations

1. **Add multi-line input support (Shift+Enter).** Critical for an agent workspace. Users will need to paste code, prompts, and structured text. Consider a `<textarea>` with auto-resize instead of `<input>`.

2. **Add basic markdown rendering for assistant messages.** Even minimal support (code blocks, bold, links) would dramatically improve readability. A lightweight library or hand-rolled regex-based renderer would suffice.

3. **Document the WebSocket protocol.** Create a protocol reference (can be a comment block in app.py or a separate doc) listing all message types, their payloads, and the expected client behavior. This becomes essential when Flight 4 adds agent selection.

4. **Add truncation indicators.** When tool results or titles are truncated, show a visual indicator ("...") and optionally a "show full" toggle.

5. **Unify REST and WebSocket message handling.** The `/api/chat` endpoint should use the same session registry as the WebSocket handler, or the divergence should be documented as intentional with clear scoping.

## Action Items

- [ ] Add multi-line input support with Shift+Enter (Flight 4 or 6)
- [ ] Add markdown rendering for assistant messages (Flight 4 or 6)
- [ ] Document WebSocket protocol (before Flight 4 begins)
- [ ] Add truncation indicators for tool results and session titles
- [ ] Consider unifying REST and WebSocket message handling (Flight 4 design decision)
- [ ] Add accessibility basics: ARIA labels, keyboard navigation for nav rail and session list
- [ ] Evaluate JavaScript testing approach before frontend grows further
