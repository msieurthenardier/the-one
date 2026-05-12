# Leg: 02-agents-polish

**Status**: landed
**Flight**: [Studio Polish](../flight.md)
**Mode**: Vibe (interactive, operator-driven)

## Objective

Polish the Agents area of Studio — tile grid + Agent editor (General / Tools / MCPs tabs) — composing the alien-dashboard design-language vocabulary (V3b chamfered surfaces, accent-translucent active state, mini-glass treatments, indicator-led primitive where applicable) onto the `.content-panel` interior. Knowledge tab is stub-polish-deferred per flight spec. MCPs tab is cosmetic-consistency-only (no structural change to M07 UI).

## Mode: Vibe Leg

This is an interactive leg. The operator iterates on aesthetic choices in the browser; the Flight Director makes edits in real-time and reloads. No autonomous Developer spawn for the vibe rounds. Cadence per Flight 3.5: "land dark, port light" — anchor dark first, port light at leg close as a value-swap exercise.

Acceptance is qualitative ("operator approves") rather than mechanical. The surfaces below are the *axes* to cover — the iteration *path* is operator-driven.

## Surfaces in Scope

1. **Agents tile grid** — `static/js/areas/studio.js:856 renderAgentList()` + `.entity-tile-grid` / `.entity-tile` styles. Composed of name, description, provider · model meta line, tool-count + MCP-tool-count lines, capability chips.
2. **Agent editor — General tab** — `static/js/areas/studio/general-tab.js`. Identity section (name/description) + LLM Configuration (provider, model, max_iterations) + VRAM warning + Test button + Advanced collapsible.
3. **Agent editor — Tools tab** — `static/js/areas/studio/tools-tab.js`. Tool rows with iOS-style toggle + override panels + chip-list (NarrowSuperset).
4. **Agent editor — MCPs tab** — `static/js/areas/studio/mcps-tab.js`. Cosmetic-consistency only: chip-list + per-attachment editor visual parity with Tools tab. **No structural change.**

Out of scope:
- Knowledge tab (stub-polish-deferred)
- Native `<select>` migration (Leg 04)
- Studio dirty-gate parity (Leg 05)
- Routing fixes (Leg 06)

## Opportunistic Functional Batch (operator-directed mid-leg)

Per operator directive: "jam in all functional things we find in this leg into it." This extends Leg 02's mission-scoped charter (mission.md:55 — "opportunistic bug fixes only — no dedicated bug-bash flight") to absorb functional gaps surfaced during the Agents-area polish vibe. Items added as discovered:

1. **Agent rename** — `agents.name` is currently immutable (PK; only the create flow exposes the Name input). Vibe surfaced visual asymmetry (Name doesn't render in Identity for existing agents). Implementing real rename support: backend rename endpoint + DB cascade onto `chat_sessions.agent_name` (FK dropped at schema v5 — manual cascade required) + frontend wire to detect Name changes and call rename pre-PUT.
   - Edge case: active in-memory PTY tool sessions keyed on `(agent_name, session_id)` in `tools/sessions.py` go stale on rename. Accepted as v1 limitation; will surface as transient error on next tool call. Log as Known Issue.

2. **MCP server-info capture and display** — Surfaced during MCPs-tab vibe iteration. The MCP `initialize()` response carries `serverInfo` (name/version/title) + `instructions` (free-form usage prose, often substantial — e.g. Cloudflare). `the_one/mcp/client.py:432` captures only `result.capabilities` and `result.protocolVersion`; serverInfo and instructions get dropped on the floor. Implement: backend capture into `source.config._cache.server_info` + `.instructions` (same cache the tools list uses); ensure cache survives in GET responses; surface on the agent-editor MCPs tab tile (subtitle line under name; instructions accessible via tooltip or expand) AND on the MCP Sources grid/editor in a later leg.

3. **Per-tool override-config UX (Tools tab)** — The agent-editor Tools tab tile restructure (this leg's vibe) drops the per-tool `<details class="tool-row-overrides">` panel that operators used to set schema-driven override values. The data still persists in saved agent JSON (existing per-agent overrides survive), but new overrides cannot be set via UI. Functional leg: re-add override-config UX. Options: (a) modal popover triggered by per-tile "configure" button; (b) secondary expand-on-tile-click (chevron) restoring the prior schema-form treatment. Defer choice to operator direction.

## Iteration Axes (cover at least)

- Tile grid visual weight + spacing rhythm
- Active-tile treatment (currently `.active` class; verify accent-translucent + V3b chamfer compose well on top of `.content-panel` mask-image fade)
- Editor section dividers + section-title typography
- Field-row visual hierarchy (label vs input contrast)
- Tool-row toggle treatment (track + thumb on chrome bg)
- Chip styling on Tools + MCPs tab (`.chip-attached` accent fill)
- Empty states (`.empty-canvas` on agents grid when no agents)
- VRAM warning banner — fits design language?

## Acceptance Criteria

- [ ] Operator-approved on all 4 surfaces (tile grid + General + Tools + MCPs) — dark theme landed first
- [ ] Light theme ported via token value-swaps only; no `[data-theme="light"]` selector-level overrides introduced
- [ ] All existing data-testid + `data-field` + id hooks preserved (no behavior regression)
- [ ] No new native `<select>` introduced (Leg 04 will migrate the existing 4 sites; do not add more)
- [ ] Browser smoke check: navigate to Studio → Agents, open an existing agent, switch tabs (General → Tools → MCPs), confirm no console errors, no visual regressions on the unchanged areas (sidebar, topbar, chat)
- [ ] Reduced-transparency posture preserved (no new fixed gradients/glows that bypass shell tokens)

## Implementation Notes

- All polish targets sit inside `.area-studio .content-panel` — do not retreat the chrome (Flight 3.5 settled that). Surfaces compose on `var(--shell-content-fill)` (or its computed inset paint via `#main-content::before`).
- When introducing new tokens for studio-specific values, define them in both `[data-theme="dark"]` AND `[data-theme="light"]` blocks at `tokens.css` to preserve the theme-generalization-via-tokenization convention (F2 rule #5).
- Studio's existing CSS lives in `static/css/studio.css` `@layer areas`. New rules go here, scoped under `.area-studio`.
- Component-level rules that have any chance of being reused elsewhere (admin, chat) should land in `static/css/components.css` instead. Default: studio-scoped first, lift later if a second consumer emerges.
- "Land dark, port light": iterate on dark theme until operator confirms; switch to light, port via value-swap; iterate on light only to resolve theme-specific value choices.

## Verification (qualitative)

- Operator walks through Studio area with dev server running
- Each surface visited; operator confirms or directs further iteration
- Theme toggle exercised at leg close (port-light pass)
- Console clean (no errors / warnings)
- Browser console: open dev tools → Console tab → confirm no red errors on Studio nav + agent-open + tab-switch

## Edge Cases

- **`.content-panel` mask-image fade at top**: any new sticky/elevated treatment at the top of the panel may interact with the 8px mask. Visually verify, don't introduce hard-cut elements that fight the fade.
- **VRAM warning visibility toggle**: `.studio-vram-warning.visible` displays only on Ollama provider with high-VRAM model. Won't typically appear during iteration — verify visually only if operator switches to an Ollama agent.
- **Empty agents grid**: `.empty-canvas` CTA appears when no agents exist. Operator may or may not exercise this — check at vibe-close if not already touched.
- **Tools tab override panels**: nested `<details>` per enabled tool. Override panel polish is in-scope; the locked-chip-omission (NarrowSuperset) is structural, do not change.

## Vibe-Close Checklist

When operator says "good":

1. Theme toggle exercised both directions; light port complete; no dark-only or light-only regressions.
2. Smoke check console clean on Studio → Agents → open agent → tab-switch flow.
3. Any new tokens added to BOTH theme blocks in tokens.css.
4. studio.css edits scoped under `.area-studio` (no leak to other areas).
5. No native `<select>` added (count grep pre + post — should be unchanged at 4 Studio sites pending Leg 04).
6. Update flight log with summary of surfaces touched + token additions + any patterns discovered.
7. Update leg status to `landed`.
8. Flight Director commits per Flight 3+ per-leg cadence.
