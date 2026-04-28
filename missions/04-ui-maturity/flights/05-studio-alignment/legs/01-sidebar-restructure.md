# Leg: 01-sidebar-restructure

**Status**: completed
**Flight**: [Studio Alignment](../flight.md)

## Objective

Replace the agents-only Studio sidebar with a titled three-section navigation (Agents / Knowledge / Tools) that is hash-routable, restructure `serializeState()` so the F3 router performs the `#studio` → `#studio/agents` redirect for free, and ship one-liner stub pages for the Knowledge and Tools sections.

## Context

- F5's first leg lays the navigation skeleton that legs 02-04 build on top of. The agent list (today the entire sidebar) lands inside the Agents section without changing testids; the editor stays mounted in the content area unchanged.
- Two open questions resolved in the flight spec drive this leg: **Sidebar Knowledge/Tools section scope** (stub one-liner empty states) and **Sidebar section nav idiom** (vertical list of `<button>` elements with `aria-current="page"`, Up/Down arrows + Enter).
- The hash-routing extension is the design's load-bearing decision: `serializeState()` returns `'agents'` (NOT `null`) when no agent is selected, which makes the F3 `replaceState` path at `app.js:179-185` perform the `#studio` → `#studio/agents` redirect with zero new redirect logic in studio.js. F5 must NOT add a new redirect path.
- Section change (Agents → Knowledge → Tools) is unconditional in this leg. Leg 04 adds the dirty-state confirm dialog gate.
- F4's `.list-item` and `.empty-state` vocabulary in `components.css` is consumed; new `.section-nav` + `.section-nav-item` primitives land here for F6 admin (currently using `.list-item` + `.admin-category-item` for an analogous nav) to migrate to in F6.

## Inputs

What exists before this leg runs:

- `the_one/interfaces/web/static/js/areas/studio.js` (892 LOC) with the agents-only sidebar at `studio.js:42-138` (`.studio-sidebar-header`, `.agent-list`, `.agent-item`, `.agent-empty`, `new-agent-btn`).
- `studio.js:8-19` `serializeState()` returns `'agents/<encoded-name>'` if agent selected, else `null`; `hydrateState(sub)` parses `'agents/<name>'` only.
- `the_one/interfaces/web/static/css/studio.css` (69 LOC).
- `the_one/interfaces/web/static/css/components.css` (325 LOC, F4 vocabulary).
- `the_one/interfaces/web/static/index.html` script-load section at lines 26-36.
- `tests/browser/test_flow_hash_routing.py:89-124` — `test_hash_routing_studio_agent_persists_on_refresh` asserts `#studio/agents/<encoded-name>` and `aria-selected="true"` on `.agent-item[data-name="..."]`.
- `tests/browser/test_flow_agent_crud.py` — references `agent-empty`, `new-agent-btn`, `agent-item`, `save-agent-btn`, `data-field="name"`, `data-field="description"`.

## Outputs

What exists after this leg completes:

- New directory `the_one/interfaces/web/static/js/areas/studio/` with three new files:
  - `section-nav.js` — `App.studio.renderSectionNav(container, active, callbacks)`
  - `stub-knowledge.js` — `App.studio.renderKnowledgeStub(container)`
  - `stub-tools.js` — `App.studio.renderToolsStub(container)`
- `studio.js` restructured: the sidebar contains the section nav at top + a content area that swaps among Agents (existing list), Knowledge (stub), Tools (stub). The current agents-list content keeps every existing testid; the editor remains in the area's content panel as today, but is hidden when the active section is Knowledge or Tools.
- `serializeState()` returns `'agents'` when no agent is selected (still under Agents section); `'agents/<encoded-name>'` when agent selected; `'knowledge'` when Knowledge section active; `'tools'` when Tools section active.
- `hydrateState(sub)` accepts `null`, `'agents'`, `'agents/<encoded-name>'`, `'knowledge'`, `'tools'` and dispatches.
- `components.css` grows by `.section-nav` + `.section-nav-item` + `.section-nav-header` (or equivalent title style) — canonical vocabulary; ~30-50 LOC. The new `.section-nav-item` composes with F4's `.list-item` if it shares the same base interaction primitives, or stands alone with explicit comment if a button-as-section-item warrants its own visual treatment (developer's call during implementation; document in `agents.md`).
- `studio.css` shrinks or stays neutral — no new area-specific CSS for the section nav itself; only any genuinely studio-specific layout (e.g., sidebar header padding) stays per-area.
- `index.html` gains three `<script>` tags between line 34 (`chat.js`) and line 35 (`studio.js`):
  ```html
  <script src="/static/js/areas/studio/section-nav.js"></script>
  <script src="/static/js/areas/studio/stub-knowledge.js"></script>
  <script src="/static/js/areas/studio/stub-tools.js"></script>
  ```
- `tests/browser/test_flow_studio_navigation.py` — NEW. Covers section-nav keyboard + click + URL refresh.
- `tests/browser/test_flow_hash_routing.py` — extended with assertions for `#studio` → `#studio/agents` redirect, `#studio/knowledge`, `#studio/tools`.
- All existing F1-F4 tests still pass (407 + 123 baseline preserved).

## Acceptance Criteria

- [x] Navigating to `#studio` produces an immediate `replaceState` redirect to `#studio/agents` (verified via the F3 router's existing `replaceState` path at `app.js:179-185`; **no new redirect logic added in studio.js**).
- [x] The Studio sidebar contains a section-nav at the top with three `<button>` elements: "Agents", "Knowledge", "Tools". The active section's button has `aria-current="page"` and a visual treatment indicating active state.
- [x] Tab moves focus into the section-nav. Up/Down arrows move focus between section buttons (`role="group"` with arrow-key handling, NOT `role="tablist"` — sections are not tabs in the W3C ARIA sense). Home/End jump to first/last. Enter (or Space, or click) activates the focused section.
- [x] Activating a section button: (a) updates the area's internal `_activeSection` state, (b) calls `App.router.replaceSub(this.serializeState())` (the single canonical URL-write call site for studio; **section button does NOT call `history.replaceState` directly**), (c) re-renders the sidebar's content area showing the section's content, (d) updates each section button's `aria-current` and `tabindex` (roving tabindex: only the active button has `tabindex="0"`; the other two have `tabindex="-1"`).
- [x] Tab from the active section-nav button moves focus into the active section's content pane (the agent list when Agents is active; the empty-state region when Knowledge/Tools is active). The two non-active section buttons are NOT in the Tab order (`tabindex="-1"`).
- [x] **Single URL-write call path**: studio.js routes ALL URL writes through one helper (e.g., `_writeUrl()` calling `App.router.replaceSub(this.serializeState())`). The three call sites — section-button click, `selectAgent`, `enterCreateMode` — all funnel through this helper. No site calls `App.router.replaceSub(...)` with hand-built strings.
- [x] `#studio/knowledge` renders a centered `.empty-state` with the exact text: "Knowledge bases will be created and managed here in a future mission."
- [x] `#studio/tools` renders a centered `.empty-state` with the exact text: "MCP servers and built-in tools will be configured here in a future mission."
- [x] Refreshing the browser on `#studio/agents`, `#studio/agents/<name>`, `#studio/knowledge`, or `#studio/tools` returns the user to the exact same view (the section is restored, the agent is restored if any, the editor is hidden when Knowledge/Tools are active).
- [x] When the active section is Knowledge or Tools, the studio editor (`.studio-editor`) is hidden — either via `display: none` or by detaching from the layout — so the empty-state is the only content in the right pane. When the active section returns to Agents, the editor is re-shown in its prior state (selected agent or empty editor).
- [x] Section change is unconditional in this leg — clicking any section button immediately changes section. (Leg 04 will gate this behind `App.confirmDialog` when dirty.)
- [x] All existing data-testids preserved on their original elements: `new-agent-btn`, `agent-list`, `agent-item`, `agent-empty`, `save-agent-btn`, `delete-agent-btn`, `data-field="name"`, `data-field="description"`. Compose new classes; do NOT rename selectors.
- [x] `aria-selected="true"` continues to live on the active `.agent-item` (`data-name="..."`) — `test_flow_hash_routing.py:119` continues to pass without modification.
- [x] New canonical vocabulary in `components.css`: `.section-nav` (vertical list container), `.section-nav-item` (button), and one of `.section-nav-header` / `.section-nav-title` for the "Studio" header above the buttons. NEW selectors only — do NOT modify existing F4 vocabulary. Document each new selector in `agents.md`'s design-system section.
- [x] `studio.css` does not gain any rules for the section-nav primitives themselves. Studio-specific overrides (if any) are explicitly justified inline (`/* studio override: <reason> */`).
- [x] New tests: `tests/browser/test_flow_studio_navigation.py` covers (a) section nav keyboard navigation (Tab in, Up/Down moves focus, Enter activates, roving `tabindex`), (b) click navigation, (c) URL hash updates on activation (`#studio/knowledge`, `#studio/tools`), (d) refresh on each section URL returns to that section, (e) `aria-current="page"` on the active section button.
- [x] `tests/browser/test_flow_hash_routing.py` extended with three new assertions or test cases:
  - Navigating to `#studio` ends up at `#studio/agents` after the route resolves.
  - Navigating to `#studio/knowledge` shows the knowledge stub (text match) and the URL stays at `#studio/knowledge` after refresh.
  - Navigating to `#studio/tools` shows the tools stub and survives refresh.
- [x] All existing tests pass: `pytest --timeout=60 tests/` returns exactly 407 (this leg adds zero unit tests), `pytest --timeout=120 -m browser tests/browser/` returns ≥ 123 + the new tests added by this leg (target 5-8 new browser tests).
- [x] Flight log updated with leg progress entry under `## Leg Progress`.
- [x] Leg status set to `landed` (not `completed`; commit happens at flight-end review per agentic-workflow contract).

## Verification Steps

- `pytest --timeout=60 tests/` — passes baseline (exactly 407; no unit-test additions in this leg).
- `pytest --timeout=120 -m browser tests/browser/test_flow_studio_navigation.py` — new file, passes.
- `pytest --timeout=120 -m browser tests/browser/test_flow_hash_routing.py` — passes including new section assertions; the existing `test_hash_routing_studio_agent_persists_on_refresh` MUST pass with NO modification (the `page.goto(f"{base_url}#studio")` step now triggers the redirect to `#studio/agents`, then the test clicks an agent → URL becomes `#studio/agents/<name>`, which is what the existing assertion expects).
- `pytest --timeout=120 -m browser tests/browser/test_flow_agent_crud.py` — passes unchanged (testid preservation).
- `pytest --timeout=120 -m browser tests/browser/` — overall browser suite passes (target ≥ 128, baseline 123 + this leg's 5-8 new tests).
- Manual browser check: open the app, click `#studio`, observe URL becomes `#studio/agents`. Click each section nav button, observe URL changes to `#studio/agents`, `#studio/knowledge`, `#studio/tools`. Refresh on each. Verify keyboard: Tab into section nav, Up/Down moves focus, Enter activates.
- `wc -l the_one/interfaces/web/static/css/components.css` shows growth (~30-50 LOC).
- `wc -l the_one/interfaces/web/static/css/studio.css` shows neutral or shrinkage from baseline 69.
- `grep -E "data-testid=\"(agent-item|agent-empty|new-agent-btn|save-agent-btn|delete-agent-btn)\"" the_one/interfaces/web/static/js/areas/studio.js` finds every original testid.

## Implementation Guidance

1. **Add three new helper sub-modules under `the_one/interfaces/web/static/js/areas/studio/`** — mirror the chat sub-module convention (`areas/chat/`).
   - `section-nav.js`: exports `App.studio.renderSectionNav(container, active, {onSelect})`. Renders the section-nav: a header element with text "Studio", below it three `<button class="section-nav-item">` elements ("Agents", "Knowledge", "Tools") with `aria-current="page"` and `tabindex="0"` on the active one (others get `tabindex="-1"`). Wires Up/Down/Home/End/Enter/Space keyboard handlers (focus moves on arrow keys; activation triggers `onSelect(section)`). Click also triggers `onSelect(section)`. The helper does NOT mutate URL state — that's studio.js's job.
   - `stub-knowledge.js`: exports `App.studio.renderKnowledgeStub(container)`. Renders one centered `.empty-state` div with text "Knowledge bases will be created and managed here in a future mission."
   - `stub-tools.js`: exports `App.studio.renderToolsStub(container)`. Renders one centered `.empty-state` div with text "MCP servers and built-in tools will be configured here in a future mission."
   - All three follow the `App.studio.<name>` namespace pattern and attach to `window.App` lazily (`window.App = window.App || {}; window.App.studio = window.App.studio || {};`).

2. **Restructure `studio.js` sidebar layout in `init(sidebar, content)`** (today at `studio.js:42-138`):
   - Build the sidebar as: section-nav container (top, owns the "Studio" title) + section-content container (below). The section-content container is what swaps among the three sections.
   - **Replace the existing `.studio-sidebar-header`** (which today carries the title + `+ New Agent` button at `studio.js:43-46`) — its title role is taken over by the new `.section-nav-header`. The `+ New Agent` button (`data-testid="new-agent-btn"`) does NOT move to the content-pane header in this leg (that's leg 02's job); instead, it relocates to the top of the **Agents section content area** (above `.agent-list`) so its testid + behavior continue to work without ambiguity. Visually, this means the Agents section content is: `[+ New Agent button]` then `[.agent-list]` (or `.agent-empty` when no agents). Leg 02 will move the button to the agent-grid's header (`.new-chat-header`-style).
   - Move the existing agents-list rendering (`.agent-list`, `.agent-item`, `.agent-empty`) into a function `renderAgentsSection(container)` that fills section-content when active section is `'agents'`.
   - Add `renderKnowledgeSection(container)` and `renderToolsSection(container)` that delegate to the stub helpers.
   - Add `setActiveSection(section, {writeUrl = true} = {})`: updates `_activeSection`, calls `renderSectionNav(...)` to update active state on buttons, calls the appropriate `render<X>Section()` to fill the content, shows/hides the editor pane (`.studio-editor`) based on whether section is Agents, and **writes the URL only when `writeUrl === true`** (calls the single `_writeUrl()` helper described in step 4). The hydrate path passes `{writeUrl: false}` because the F3 router writes the URL after `hydrateState` returns; click handlers use the default `writeUrl: true`.

3. **Extend `serializeState()` and `hydrateState(sub)`** (today at `studio.js:8-19`):
   - `serializeState()` — explicit branch order, including create-mode:
     - If `_activeSection === 'knowledge'`: return `'knowledge'`.
     - If `_activeSection === 'tools'`: return `'tools'`.
     - If `_activeSection === 'agents'` and an agent is selected and `createMode` is false: return `'agents/' + encodeURIComponent(this._selectedAgent.name)`.
     - If `_activeSection === 'agents'` (any other case — no agent, OR `createMode === true`): return `'agents'`. **CRITICAL #1**: this makes the F3 router perform the `#studio` → `#studio/agents` redirect for free. **CRITICAL #2**: the create-mode branch now returns `'agents'` (NOT `null`). The current code at `studio.js:9` returns `null` whenever `createMode` is true; that has to change. Otherwise `enterCreateMode` would write `#studio` then the F3 serialize-after-hydrate would rewrite to `#studio/agents`, causing a visible flicker.
   - `hydrateState(sub)`:
     - If `sub === null` or `sub === undefined`: set `_activeSection = 'agents'`, defer agent-select logic as before.
     - If `sub === 'agents'`: set `_activeSection = 'agents'`, clear `_pendingSelectName`.
     - If `sub.startsWith('agents/')`: set `_activeSection = 'agents'`, parse name, set `_pendingSelectName`, call `_tryConsumePendingSelect()` as today.
     - If `sub === 'knowledge'`: set `_activeSection = 'knowledge'`.
     - If `sub === 'tools'`: set `_activeSection = 'tools'`.
     - Defensive: any unrecognized string defaults to `_activeSection = 'agents'`. Do NOT throw.
   - After `hydrateState`, call `setActiveSection(_activeSection, {writeUrl: false})` to render. The `{writeUrl: false}` flag is the loop-prevention mechanism: hydrate never writes URL because the F3 router writes URL after hydrate returns (only if `serializeState() !== sub`, which is idempotent).

4. **Wire all URL writes through a single `_writeUrl()` helper**:
   - **Closure-vs-`this` reconciliation (latent bug)**: today's `serializeState` at `studio.js:9` reads `this._selectedAgent` and `this._createMode`, but neither field is ever assigned anywhere in studio.js — the actual state lives as closure locals (`selectedAgent`, `createMode`) inside `init()`. As a result, `serializeState` currently returns `null` unconditionally (latent bug, never surfaced because the only caller, the F3 router, treats `null` as no-sub and the redirect is consequently absent today). This leg fixes it by **promoting closure locals to `this._selectedAgent`, `this._createMode`, and `this._activeSection`** so `serializeState()` works correctly. All read sites in `init` switch to `this.<name>`; all write sites do the same.
   - Add a helper `_writeUrl()` (closure helper or `this`-method, either is fine post-promotion) that calls `App.router.replaceSub(this.serializeState())`. This is THE only studio call site for `App.router.replaceSub`.
   - Every URL-mutating action funnels through it. Enumerated current sites and their migrations:
     - Section-button activation → `_writeUrl()`.
     - `selectAgent(agent)` at `studio.js:174-186` → migrate the existing `App.router.replaceSub('agents/' + encodeURIComponent(agent.name))` at line 184 to `_writeUrl()`.
     - `enterCreateMode()` at `studio.js:188-198` → migrate `App.router.replaceSub(null)` at line 197 to `_writeUrl()` (which now returns `'agents'` per the create-mode branch above).
     - **Post-delete `replaceSub(null)` at `studio.js:148`** → migrate to `_writeUrl()` (after the delete clears `_selectedAgent`, `_writeUrl` correctly serializes to `'agents'`).
   - When `onSelect(section)` fires from `renderSectionNav`: set `this._activeSection = section`, call `setActiveSection(section)` (default `{writeUrl: true}` → triggers `_writeUrl()` internally). Pick this single pattern (setActiveSection-writes-URL); document it in agents.md. Click handlers do NOT call `_writeUrl()` separately. (Even if both fired, `replaceSub` is idempotent at `app.js:253` — `if (location.hash === newHash) return` — so no hazard.)
   - Switching FROM Agents to Knowledge/Tools: leave `this._selectedAgent` mounted (don't tear down) so a return to Agents preserves selection. `serializeState()` returns `'knowledge'`/`'tools'` based on `this._activeSection` alone; agent selection is independent state. Editor pane is hidden via `setActiveSection`.
   - Switching FROM Knowledge/Tools BACK to Agents: `serializeState()` returns `'agents'` or `'agents/<name>'` depending on whether the prior agent selection is still mounted. The URL upgrades back to `#studio/agents/<name>` automatically through `_writeUrl()`.

5. **Add canonical CSS to `components.css`**:
   - `.section-nav` — vertical flex/grid container; gap; padding.
   - `.section-nav-header` — the "Studio" title (uppercase or display-font sizing using F4 tokens).
   - `.section-nav-item` — `<button>` reset (no default border / background), full-width text-aligned-left, `:hover` and `:focus-visible` states using F4 tokens (`--color-cyan-500` etc.), `:active` (clicked) state, `aria-current="page"` (or `[aria-current="page"]` selector) for the active state.
   - Use `@layer components` block, matching F4 convention.
   - Document each new selector in `agents.md`'s design-system section.

6. **Update `index.html`** — insert three `<script>` tags as listed in Outputs. Order among themselves does not matter (no inter-dependencies); they all must precede `studio.js`.

7. **Write `tests/browser/test_flow_studio_navigation.py`** — pytest + Playwright; use the existing `@pytest.mark.browser` marker and the existing fixture pattern from `test_flow_hash_routing.py`. Cover the criteria above (5-8 tests).

8. **Extend `tests/browser/test_flow_hash_routing.py`**:
   - New test: `test_studio_root_redirects_to_agents` — `page.goto(...)#studio`, wait for routing settle, assert `page.evaluate("() => location.hash") == "#studio/agents"`.
   - New test: `test_studio_knowledge_section_persists_on_refresh` — navigate to `#studio/knowledge`, assert the empty-state text is visible, refresh, assert URL still `#studio/knowledge` and text still visible.
   - New test: `test_studio_tools_section_persists_on_refresh` — same shape for `#studio/tools`.
   - The existing `test_hash_routing_studio_agent_persists_on_refresh` should continue passing — verify by reading it; if its initial `page.goto(f"{base_url}#studio")` step is followed by an assertion that depends on the URL still being `#studio` (with no agent), update that step OR if it just clicks an agent next, leave it alone.

9. **Run the full test suite** with the project's pytest timeout flag (per the leg-execution phase prompt: "Run tests with a timeout flag appropriate to this project's test runner — fail fast"). Check `pyproject.toml` or existing test runs in `flights/04-chat-restructure/flight-log.md` for the pattern. Common: `pytest --timeout=60 tests/`.

10. **Update `agents.md`** — add a "Section navigation" entry under §Design system → "Affordance vocabulary" (the shared class catalog at ~line 250) documenting `.section-nav`, `.section-nav-item`, `.section-nav-header`, the `aria-current="page"` semantics, and the keyboard contract (Tab in, Up/Down move focus, Enter activates, roving tabindex). Also add a brief note that admin's `renderCategoryList` (admin.js:101-140) is an imminent F6 consumer.

11. **Update flight log** — add a `### 01-sidebar-restructure` entry under `## Leg Progress` with status, started/completed timestamps, summary of changes, and any notes (e.g., LOC delta on components.css and studio.css, test count delta).

12. **Set leg status to `landed`** in this leg artifact's header. Do NOT mark `completed` (commit happens at flight review per agentic-workflow). Do NOT commit. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`_tryConsumePendingSelect()` race**: today the agent-select dispatch defers until the agents fetch completes. The new `_activeSection` flag must coordinate: if the user lands on `#studio/agents/<name>` but `_activeSection` is hydrated as `'agents'` and `_pendingSelectName` is set, the agent selection should activate as before once agents load. If the user lands on `#studio/knowledge`, the editor is hidden and `_pendingSelectName` (if any) sits dormant; if the user later switches to Agents, the deferred select can fire. Simplest: clear `_pendingSelectName` when activating Knowledge/Tools.
- **`hydrateState` called multiple times**: F3's router calls hydrate on every cross-area entry. Ensure `setActiveSection` is idempotent and does not re-render the entire sidebar from scratch on every call (just update the active button's `aria-current` and re-render the section content).
- **No `replaceSub` write loop possible**: `setActiveSection({writeUrl: false})` from hydrate guarantees no studio-side URL write during hydrate; the F3 router's serialize-after-hydrate at `app.js:179-185` is idempotent (only writes when `serialized !== sub`). The single-call-path discipline (step 4) ensures every studio URL write is identical to `serializeState()`.
- **Section change deliberately bypasses existing `window.confirm` dirty-checks**: the current studio.js has synchronous `window.confirm` dirty-checks at `studio.js:175-176` (in `selectAgent`) and `studio.js:189-190` (in `enterCreateMode`). Section-button clicks in this leg do NOT honor these — clicking Knowledge with an unsaved agent silently abandons the unsaved state. **This is deliberate**; leg 04 will gate section change behind `App.confirmDialog`. Do NOT wire the existing confirm into the section-button click handler in this leg — leg 04 restructures these checks to async and adds the section-change gate then.
- **Editor stays mounted across Knowledge/Tools round-trip**: when a user switches from Agents (with an agent selected, possibly with unsaved changes) to Knowledge or Tools and back, the editor's DOM and any closure state (including the dirty flag once leg 04 lands) is preserved. The editor pane is hidden via `display: none` (or equivalent), not detached. In leg 01 there is no dirty-tracking yet, so this is just "selected agent persists across section round-trip" — verifiable by selecting an agent, switching to Knowledge, switching back to Agents, and observing the same agent is still selected.
- **Empty agents on Agents section**: `agent-empty` testid still must render when there are no agents AND active section is Agents. Knowledge/Tools sections do not render `agent-empty`.
- **Existing studio test `test_hash_routing_studio_agent_persists_on_refresh`** uses `page.goto(f"{base_url}#studio")` at line 96 and asserts `expected_hash = f"#studio/agents/{quote(agent_name)}"` at line 109 after clicking an agent. With the new redirect, `#studio` resolves to `#studio/agents` BEFORE the agent click, then the click selects the agent → URL becomes `#studio/agents/<name>`, which is exactly what the existing assertion expects. **The test MUST pass without modification**. If any change is needed, that's a deviation requiring root-cause investigation, not a routine update.
- **Browser back/forward**: section changes use `replaceState` (per F3 contract) so they do not pollute history. Browser back from `#studio/tools` skips back to whatever was before the studio entry. Acceptable.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio.js` — refactor sidebar build, extend serialize/hydrate, add `setActiveSection`. Estimated delta: +60 to +120 LOC (some growth; legs 02-04 will reduce as helpers extract).
- `the_one/interfaces/web/static/js/areas/studio/section-nav.js` — NEW (~50-80 LOC).
- `the_one/interfaces/web/static/js/areas/studio/stub-knowledge.js` — NEW (~10-15 LOC).
- `the_one/interfaces/web/static/js/areas/studio/stub-tools.js` — NEW (~10-15 LOC).
- `the_one/interfaces/web/static/css/components.css` — +30 to +50 LOC for `.section-nav` family.
- `the_one/interfaces/web/static/css/studio.css` — neutral or small shrinkage; remove any rules superseded by the new section-nav vocabulary.
- `the_one/interfaces/web/static/index.html` — +3 `<script>` lines.
- `tests/browser/test_flow_studio_navigation.py` — NEW (~80-120 LOC, 5-8 tests).
- `tests/browser/test_flow_hash_routing.py` — +3 tests.
- `the_one/agents.md` — `+~15 LOC` under §Design system → "Affordance vocabulary" (~line 250) documenting the section-nav primitives and keyboard contract.
- `missions/04-ui-maturity/flights/05-studio-alignment/flight-log.md` — leg progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`. The Flight Director defers commit to flight-end review per agentic-workflow.**

- [x] All acceptance criteria verified
- [x] All existing tests passing (`pytest tests/`, `pytest -m browser tests/browser/`)
- [x] New tests passing (`test_flow_studio_navigation.py` + extensions to `test_flow_hash_routing.py`)
- [x] `agents.md` updated with section-nav documentation
- [x] Flight log updated with `### 01-sidebar-restructure` progress entry
- [x] This leg's status set to `landed`
- [x] Do NOT check off this leg in flight.md yet (Flight Director handles at flight commit)
- [x] Do NOT commit (Flight Director commits all autonomous legs at flight-end review)
- [x] Signal `[HANDOFF:review-needed]`
