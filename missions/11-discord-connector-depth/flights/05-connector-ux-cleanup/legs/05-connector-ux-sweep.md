# Leg: connector-ux-sweep

**Status**: completed
**Flight**: [Connector UX Cleanup](../flight.md)

## Objective

Element-by-element sweep of every visible UI element across the connector editor (new + edit modes, both tabs) and the agent's Connectors tab (per-agent overlay). For each element, verify it maps to either a Design Language primitive (`#admin/design-language`) OR an MCP-editor pattern (`#studio/mcp-sources/{id}`). Produce a coverage report at `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/sweep-coverage.md` enumerating the element → primitive map, with a deferral list at the bottom for elements whose visual treatment needs a primitive that does NOT yet exist (those become future-UX-mission scope, NOT F5 work). Any small inline-style cleanups discovered during the sweep land in this leg's commit. **NO new UI components built.** Chrome MCP drives the element enumeration; the operator does not click during L5.

## Context

- F5 L5 is the sweep leg per the flight's "primitives-first → section-shape → sweep last" sequencing. L1-L4 landed (form-controls re-styled; Test Connection + Invite folded; runtime-config moved + relabels; per-axis containment + empty-chips hide). L5 verifies the cumulative post-L4 state.
- F5 flight Design Decision "Sweep leg output — new artifact at flight directory root" pins the artifact path + shape: element → primitive map + deferral list.
- F5 flight Design Decision "NO new UI components built" is the binding constraint. The sweep's deferral list is the escape valve for elements that need primitives not yet in the design language; those land as future-UX-mission scope at debrief, NOT as F5 work.
- This is the n=1 application of the element-by-element coverage discipline. F4 debrief recommendation #4 ("CustomEvent cross-component pattern is sound at n=1; codify when n=2 emerges") establishes the n=1-vs-n=2 codification threshold; the sweep methodology itself may become a future-codified convention if F6+ replicates it.
- Touched-surface UX-debt folding (F4 L1 convention): the sweep IS the explicit application of this discipline at flight-end. Any element-level finding that fits in F5's scope folds inline; anything beyond becomes future-UX-mission scope on the deferral list.
- F4 L4 positive side effect (cycle-1 reviewer noted on L4): cold-pool empty state no longer renders the blank chip box — `_renderChips` now hides empty container in all callers. L5 sweep verifies this side effect on the relevant surfaces (cold-pool dropdowns, post-Test-Connection state).

## Inputs

- All L1-L4 changes landed (uncommitted; F5 batches review + commit after L5).
- Chrome MCP available; `the-one` container at `http://localhost:8484/`.
- Reference surfaces:
  - **Design Language page**: `http://localhost:8484/#admin/design-language` — canonical primitive catalog.
  - **MCP editor**: `http://localhost:8484/#studio/mcp-sources/{stdio-chrome-devtools-id}` — the working reference.
- **Target surfaces** to walk in the sweep:
  1. **New connector page**: `http://localhost:8484/#studio/connectors/new` (flat layout; no tabs).
  2. **Edit-mode connector editor (Discord) — General tab**: `http://localhost:8484/#studio/connectors/58f1fe5a833f` (Discord Constellation).
  3. **Edit-mode connector editor (Discord) — Access and Routing tab**: same URL + click A&R tab.
  4. **Edit-mode connector editor (Stub) — General tab**: navigate to Stub HAT Account.
  5. **Edit-mode connector editor (Stub) — Access and Routing tab**: click A&R tab.
  6. **Agent Connectors tab**: `http://localhost:8484/#studio/agents/Cave%20Man%20Bot/connectors` (Cave Man Bot has both Discord + Stub attached; serves both code paths).
- **Reference primitives** (the canonical catalog):
  - From Design Language page: `.field-input`, `.field-select`, `.checkbox-primary`, `.field-info-icon`, `tool-enable-switch`, `chip + chip-remove`, `indicator-led`, `app-flash`, `banner`, `entity-tile`, `section-nav`, `list-item`, `app-picker-button`, `test-result`, `empty-state`, `tabs`, `modal-dialog`, `markdown`, `field-row` / `admin-pf-row`.
  - From MCP editor (working reference): `mcp-test-row` (Connection footer-row), `editor-section` + `section-title` (section wrapper), info-icon usage pattern (`title=` + `aria-describedby` + visually-hidden), `<details>/<summary>` disclosure (single-class), `entity-tile-grid` for sources listing, `mcp-tool-item` collapsible rows.

## Outputs

- **`missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/sweep-coverage.md`** (new file). Structure:
  - Title: `# F5 Sweep Coverage Report`
  - Date + executor (agent driving Chrome MCP).
  - Methodology summary (one paragraph).
  - **Per-surface tables**: one table per target surface (the 6 listed above). Each row: `Element | Primitive / Pattern | Source (DL page or MCP) | Notes`. Cover every visible element (form controls, section titles, buttons, badges, status indicators, disclosure triangles, chips, empty-states, etc.).
  - **Cross-cutting findings**: any patterns observed across surfaces (e.g., consistent use of `field-row admin-pf-row`; sections all use `editor-section`).
  - **Deferral list** (future-UX-mission scope): elements whose visual treatment lacks a canonical primitive. Each entry includes: surface location + element description + reason (no analog in DL page or MCP editor) + suggested follow-up.
  - **Inline-fix log**: any small element-level fixes that were folded inline during L5 (e.g., a stray inline-style that contradicts a token; a missing `aria-label`; a wrong class). Each entry: file + line + before/after diff.
- Any inline-fix code changes land in `the_one/interfaces/web/static/css/studio.css`, `the_one/interfaces/web/static/js/areas/studio/*.js`, or similar as appropriate. Each inline fix is small (≤ ~5 LOC); larger findings go on the deferral list.
- Sibling artifact bookkeeping: F5 `flight.md`'s L5 Checkpoints + L5 Legs item checked off; F5 `flight-log.md`'s Leg Progress section grows an L5 entry; this leg artifact's Status header progresses through its lifecycle.

## Acceptance Criteria

- [x] `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/sweep-coverage.md` exists as a new file with title `# F5 Sweep Coverage Report`.
- [x] The report's per-surface tables cover all 6 target surfaces (new connector, edit-Discord-General, edit-Discord-A&R, edit-Stub-General, edit-Stub-A&R, agent-Connectors).
- [x] Each table enumerates EVERY visible element on its surface (form controls, section titles, buttons, badges, status indicators, disclosure triangles, chips, empty-states, etc.). The sweep is exhaustive within each surface; an element missing from the table is the sweep failing its purpose.
- [x] Each element row classifies the primitive/pattern: either (a) a Design Language primitive by name (e.g., `field-input`, `checkbox-primary`), or (b) an MCP-editor pattern by name (e.g., `mcp-test-row`, `editor-section + section-title`), or (c) marked as DEFERRED with a deferral-list entry below.
- [x] The deferral list captures every element that lacks a canonical primitive in either reference. Each entry: surface + element + reason + suggested-follow-up.
- [x] The inline-fix log captures every small fix folded inline (if any). Each entry: file:line + before/after diff. If zero inline fixes were needed, the log explicitly says "No inline fixes needed; all elements either map to existing primitives or are deferred to future-UX-mission scope."
- [x] Any inline-fix changes are small (≤ ~5 LOC each); cumulative inline changes ≤ ~30 LOC across all touched files. **Abort-threshold rule**: if cumulative inline fixes approach ~25 LOC, STOP folding inline and defer all remaining findings — do NOT push to land more inline work. The deferral list is the escape valve.
- [x] **Granularity convention** (cycle-1 catch): enumerate at the primitive level — a `field-row` is ONE row in the table with its label/input/info-icon noted in the Notes column; a `<details>/<summary>` disclosure is ONE row; a tab strip is ONE row with the per-tab buttons noted. Avoid sub-element decomposition unless the sub-element uses a different primitive than its parent (e.g., a button inside a section header may warrant its own row).
- [x] **Cross-cutting findings section** exists in the report; if no cross-cutting patterns or inconsistencies surfaced, the section explicitly says so.
- [x] **L4 cycle-1 positive side effect verified**: on the new-connector page (pre-probe-404 state) the `.discoverable-dropdown-chips` container is hidden (computed `display: none`) — confirms the L4 `hidden`-toggle + CSS override works in the cold-pool path.
- [x] **Stub A&R Runtime Config absence verified**: Stub HAT Account's Access-and-Routing tab shows Lifecycle + Allowlist + Routing Rules but NO Runtime Config section — the missing-section is visually clean (no half-rendered placeholder, no empty section-title).
- [x] **Empty deferral list handling**: if the sweep finds zero deferrals (best case — all elements map cleanly), the deferral-list section says "No deferrals — all N elements across 6 surfaces map cleanly to existing Design Language primitives or MCP-editor patterns."
- [x] No new UI components are built (operator constraint). The sweep's deferral list is the escape valve.
- [x] Chrome MCP drives the element enumeration. Snapshots + screenshots support the sweep; the operator is NOT involved in L5.
- [x] No source files beyond `sweep-coverage.md` (new) + any inline-fix targets are modified.

## Verification Steps

- `ls missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/sweep-coverage.md` confirms the file exists.
- `grep -n "^## " sweep-coverage.md` returns at least 6 surface-section headers + 1 deferral-list header + 1 inline-fix-log header + 1 cross-cutting-findings header.
- Read each per-surface table; verify each has ≥ ~8 data rows (line-count grep is too weak — read the file).
- Each deferral-list entry has a follow-up suggestion (e.g., "future UX mission could add a `.disclosure-block` primitive to the design language").
- `git diff --stat` shows changes in `sweep-coverage.md` (new) + any inline-fix files + F5 sibling artifacts.

## Implementation Guidance

1. **Read the Design Language page source** at `the_one/interfaces/web/static/js/areas/admin/design-language/*.js` to refresh the primitive catalog.

2. **Read the MCP editor source** at `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` to refresh the canonical reference patterns.

3. **For each of the 6 target surfaces**:
   - Navigate via Chrome MCP (`mcp__chrome-devtools__navigate_page` + hard-reload).
   - Take a full-page snapshot (`mcp__chrome-devtools__take_snapshot`) for the accessibility tree.
   - Take a full-page screenshot (`mcp__chrome-devtools__take_screenshot` with `fullPage: true`) for visual reference.
   - Walk the snapshot top-to-bottom; for each visible element, identify the primitive/pattern it uses.
   - If the primitive is one of the Design Language primitives, cite by name + reference DL page module.
   - If the primitive is an MCP-editor pattern, cite by name + reference `mcp-server-editor.js`.
   - If neither: mark as DEFERRED + add a deferral-list entry with the reason.
   - If a small inline-fix is needed (e.g., a missing `aria-label` on an icon button, a stray inline-style overriding a token), fold inline IF it's ≤ ~5 LOC; otherwise add to deferral list.

4. **Build the report incrementally**:
   - Start with the methodology summary + per-surface table skeletons.
   - Fill in each surface's table as the sweep progresses.
   - Add deferral-list entries inline as they arise; consolidate at end.
   - Add inline-fix log entries inline; consolidate at end.

5. **Cross-cutting check**: after all 6 surfaces are walked, review the tables for patterns:
   - Are there elements that recur across surfaces with consistent primitive usage? Note as a positive finding.
   - Are there elements that recur with INCONSISTENT primitive usage? Flag as a deferral-list candidate or inline-fix.
   - Does the agent-Connectors-tab use a different `editor-section` shape than the connector editor? If so, note.

6. **Sanity-check the deferral list**: each entry must include a reason (why no canonical primitive exists) and a follow-up suggestion (what a future UX mission would do). Vague deferrals ("looks off") are not acceptable.

7. **Run targeted browser tests** to confirm no regressions from any inline fixes:
   - `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_per_agent_overlay_dropdown.py tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py tests/browser/test_connector_test_connection_button.py tests/browser/test_flow_studio_connector_invite_section.py tests/browser/test_flow_studio_connector_directive_section.py tests/browser/test_flow_studio_connector_allowlist_dropdown.py tests/browser/test_flow_studio_connector_routing_dropdown.py tests/browser/test_flow_studio_connector_discoverable_dropdown.py -m browser -x --timeout 60 -v`

8. **Update F5 `flight.md`** — check off L5 in Checkpoints + Legs sections.

9. **Append L5 leg-progress entry** to F5 `flight-log.md` capturing: number of surfaces walked, number of elements enumerated, number of deferrals, number of inline fixes, key cross-cutting findings.

10. **Update this leg artifact's Status header** progressively: `planning` → `ready` → `in-flight` → `landed`.

## Edge Cases

- **The sweep surfaces a primitive used in a new way**: if Discord-context use of a primitive (e.g., `.field-info-icon`) reveals a styling gap (e.g., spacing next to a label feels wrong), and the fix is a small CSS rule, fold inline (≤ ~5 LOC) and log. If the fix would require a new component or substantial rework, defer.
- **The sweep surfaces a primitive in the MCP editor that DL doesn't document**: noteworthy gap. Add to deferral list as "DL page missing primitive: {name}; MCP editor uses it at {file:line}. Future UX mission could add to DL catalog."
- **Disagreement between DL page and MCP editor on a primitive's shape**: rare but possible. Document the divergence in cross-cutting findings; flag for resolution at L6 HAT or future UX mission.
- **Connectors-tab "grid" surface NOT in scope**: the operator's interactive enumeration covered the per-agent overlay + the editor pages. The Studio Connectors grid (the list of connector accounts) is OUT of scope for L5 — the L5 sweep covers the 6 surfaces enumerated, not the grid view.
- **`'stub'`-type empty Access-and-Routing tab post-L3**: Stub doesn't implement `renderRuntimeConfigFields`, so its A&R tab has Lifecycle + Allowlist + Routing Rules but NO Runtime Config. This is correct behavior (Stub has no runtime-config concept). Confirm the absence is visually clean — no empty section header, no half-rendered placeholder.
- **The L4 positive side effect**: the sweep should explicitly verify on the new-connector page (where the dropdowns initially render in pre-probe-404 state with no chips) that the chips container is hidden. Cite as confirmation of L4's side effect.
- **Inline-fix risk**: any inline fix must NOT introduce a new visual element or a new primitive. If a fix would require either, defer it.

## Files Affected

- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/sweep-coverage.md` — new file; coverage report + deferral list + inline-fix log.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/flight.md` — L5 checkpoint + L5 leg checklist item checked off.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/flight-log.md` — L5 leg-progress entry appended (with sweep statistics).
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/legs/05-connector-ux-sweep.md` — this artifact's status header updated through the lifecycle.
- Optionally: small inline-fix files (CSS, JS) if any element-level cleanup is folded inline. Each ≤ ~5 LOC.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All 6 target surfaces walked via Chrome MCP (snapshots + screenshots)
- [x] `sweep-coverage.md` exists with per-surface tables + deferral list + inline-fix log
- [x] Browser test suite passes (no regressions from inline fixes, if any)
- [x] Update `flight-log.md` with L5 leg-progress entry (sweep statistics)
- [x] Set this leg's status to `landed`
- [x] Check off L5 in `flight.md` (Checkpoints + Legs sections)
- [x] Do NOT commit (F5 batches review + commit at flight end per the agentic-workflow protocol)

---

## Citation Audit

All code-location citations in this leg artifact verified against current code at leg design time (2026-05-23, post-L4):

- Design Language page modules at `the_one/interfaces/web/static/js/areas/admin/design-language/` — confirmed (9 section modules listed earlier in F5 planning).
- MCP editor at `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` — confirmed (referenced extensively in L1-L4).
- 6 target surfaces (URLs) — all verified during F5 planning + L1-L4 Chrome MCP verification.
- The reference primitives list above is gathered from L1-L4 implementation + the F5 planning conversation; spot-check against `fields-section.js` / `surfaces-section.js` / `status-section.js` / `tabs-section.js` etc. when building the report.

No code citations to verify in this leg artifact — the L5 work IS the verification process. All references in the artifact are conceptual primitive names, not file:line citations.
