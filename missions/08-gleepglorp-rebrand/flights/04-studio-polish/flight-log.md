# Flight Log: Studio Polish

**Flight**: [Studio Polish](flight.md)

## Summary

Flight log for Flight 4 of Mission 08 (GleepGlorp Rebrand). Flight design completed on 2026-05-12; awaiting kickoff via `/agentic-workflow flight 04 for the-one mission 08`.

---

## Reconnaissance Report

Source artifacts: Flight 3 debrief (`missions/.../03-administration-polish/flight-debrief.md`) and Flight 3.5 debrief (`missions/.../03.5-shell-chrome-polish/flight-debrief.md`). All cited items + carry-forwards verified mechanically.

| Item | Source | Classification | Evidence | Recommendation |
|---|---|---|---|---|
| Extend reduced-transparency `@media` block for shell tokens | F3.5 debrief rec #1 | `confirmed-live` | `tokens.css:394` has the existing block; no override for `--shell-chrome-bg` / shell sheen / `--shell-frame-glow` present | Leg 01 prep |
| WCAG audit gap on `--shell-chrome-bg` base colors | F3.5 debrief rec #2 | `confirmed-live` | `tests/test_design_tokens_a11y.py:152-185` test_text_on_color has parametrize block; no `shell_chrome_bg` rows | Leg 01 prep |
| Lift theme-generalization-via-tokenization convention to F2 | F3.5 debrief rec #3 | `confirmed-live` | `agents.md:577-619` F2 subsection lacks the convention as a canonical rule (rule is in prose, scattered across flights) | Leg 01 prep |
| Lift "land dark, port light" cadence | F3.5 debrief rec #4 | `confirmed-live` | No flight-design-conventions section exists in agents.md; cadence documented only in F3.5 debrief narrative | Leg 01 prep |
| Cross-reference F3 carry-forward docs items | F3.5 debrief rec #5 | `confirmed-live` | F3 affordance vocabulary doesn't pointer to F3.5 placement of topbar `<img>` CLS + legacy-class-as-JS-handle | Leg 01 prep |
| Rename `--bg-gradient` → `--shell-bg` | F3.5 debrief rec #6 | `confirmed-live` | `tokens.css` has `--bg-gradient: var(--shell-chrome-bg)` in both themes; rename will improve semantic clarity | Leg 01 prep |
| `--shell-chrome-bg` cascade-override comment | F3.5 debrief rec #7 | `confirmed-live` | Token definition in `tokens.css` lacks the cascade-caveat comment | Leg 01 prep |
| Shell-inheritance shaves Flight 4 vibe scope | F3.5 debrief rec #8 | `confirmed-live` | Per-page polish operates on `.content-panel` interior only; baked into Flight 4 scope above | Recorded in Design Decisions |
| Playwright B2 regression test (carry-forward from F3) | F3 debrief Action Item #1 | `confirmed-live` | Flight 3's `confirmLeave` hook + stale-then guard in admin.js ship in production; no Playwright test covers the cross-area path | Leg 05 |
| Carry chip-list UX + LED wire-up + confirmLeave + stale-then guard to Studio | F3 debrief Action Item #11 | `confirmed-live` | Studio area at `static/js/areas/studio.js` + sub-modules; chip-list ships via shared `wireChipListEditor` automatically (no work needed); LED wire-up + confirmLeave + stale-then-guard are real Studio work | Legs 03 (LED) + 05 (confirmLeave + stale-then + Playwright test) |
| Native `<select>` custom dropdown component | Mission Known Issue | `confirmed-live` | 4 Studio sites (`general-tab.js:52, :77`; `mcp-server-editor.js:506, :533`) + 2-3 Admin sites; no `App.dropdown` helper exists | Leg 04 |

All items remain in Flight 4 scope. No retirements.

---

## Leg Progress

### Leg 01 — Prep + Debrief Debt Close (landed 2026-05-12)

**Status**: landed. All 7 Flight 3.5 debrief items closed in a single autonomous pass per the leg's "Order matters" guidance (token rename FIRST, then sheen extraction + reduced-transparency block, so the block writes against the new token names).

**Implemented**:

- **`--bg-gradient` → `--shell-bg` hard rename** (5 sites — confirmed per design-review's correction from "1 site" to "5 sites"):
  - `tokens.css:166` (dark theme definition) + `tokens.css` light theme definition (now `:365` after token additions): renamed; value unchanged (`var(--shell-chrome-bg)`); no alias retained.
  - `base.css:10` body bg consumer: `var(--bg-gradient)` → `var(--shell-bg)`.
  - `api.py:1519` OAuth callback inline CSS: `var(--bg-gradient)` → `var(--shell-bg)`. Caught by the broadened `grep -rn ... the_one/` sentinel (would have been invisible to `test_token_definitions.py`'s `.css`-only scan).
  - `agents.md:682` token-table row: renamed.
  - `agents.md:698` F3.5 composition rule #6 prose: renamed inline reference.

- **`--shell-topbar-sheen` token extracted** (dark + light both define identical value: `linear-gradient(180deg, rgba(255, 255, 255, 0.06) 0%, transparent 6px)` — same white sheen reads on gunmetal + silver chrome). `base.css` `#app-topbar` rule consumes `var(--shell-topbar-sheen)` instead of the inlined gradient. Preserved the sheen-first / chrome-bg-second order in the topbar background stack per design-review note.

- **`--shell-chrome-bg` cascade-override caveat comment** added immediately above each token definition (dark + light); placed adjacent to the existing comment block without disrupting the grain-alternates list.

- **Reduced-transparency `@media` block extended** for both themes. Each theme gains 3 overrides: `--shell-chrome-bg` collapses to its solid base color (`#20202a` dark, `#d4d8df` light), `--shell-frame-glow: transparent`, `--shell-topbar-sheen: none`. Sync-with-base-color comment added per Edge Cases.

- **WCAG audit gap closed (partially — fg_muted variants DROPPED per design review)**:
  - 2 new parametrizations in `tests/test_design_tokens_a11y.py`: `("dark", "fg", "shell_chrome_bg", 4.5)` (12.22:1 measured) + `("light", "fg", "shell_chrome_bg", 4.5)` (12.49:1 measured).
  - `fg_muted` variants intentionally deferred: light `--fg-muted` is `#64748b` (slate-500, NOT `#94a3b8` as originally cited) → 3.33:1 on `#d4d8df` → FAILS body AA. No production muted-text-on-chrome consumer today; documented as Known Issue inline near the new parametrizations.
  - `shell_chrome_bg` key added to both `DARK` and `LIGHT` dicts in `tests/browser/design_tokens.py`.

- **agents.md documentation lift** (3 edits):
  - F2 Design Language Layer subsection — appended new composition rule #5: "Theme generalization via tokenization."
  - New `### Vibe-leg conventions` subsection inserted between `### Affordance patterns` and `### Mission 08 Flight 02`. Documents (a) "Land dark, port light" cadence; (b) "Gallery-as-iteration-substrate" pattern.
  - F3 affordance vocabulary section — appended one bullet cross-referencing F3.5's topbar-`<img>` CLS contract + legacy-class-as-JS-handle pattern.

**Verification (sentinel sweep)**:

| Sentinel | Expected | Actual |
|---|---|---|
| `grep -rn "var(--bg-gradient)\|--bg-gradient" the_one/` | 0 matches | 0 matches |
| `grep -n "var(--shell-bg)" the_one/interfaces/web/static/css/base.css` | 1 | 1 (line 10) |
| `grep -n "var(--shell-bg)" the_one/interfaces/web/api.py` | 1 | 1 (line 1519) |
| `grep -nE "^\s*--shell-bg" the_one/interfaces/web/static/css/tokens.css` | 2 | 2 (lines 166, 365) |
| `grep -n "shell-bg\|--shell-bg" the_one/agents.md` | ≥2 | 2 |
| `grep -c "shell-topbar-sheen" the_one/interfaces/web/static/css/tokens.css` | ≥4 | 4 |
| `grep -c "var(--shell-topbar-sheen)" the_one/interfaces/web/static/css/base.css` | 1 | 1 |
| `grep -E "shell_chrome_bg" tests/test_design_tokens_a11y.py` | 2 | 2 |
| `grep -n "shell_chrome_bg" tests/browser/design_tokens.py` | 2 | 2 (lines 57, 90) |
| `grep -nE "Theme generalization\|Vibe-leg conventions\|see F3\.5\|see.*F3\.5" the_one/agents.md` | ≥3 | 3 |

**Test gates** (in container, narrow scope per leg spec):

- WCAG audit: `docker exec the-one pytest tests/test_design_tokens_a11y.py -v --timeout 30` → **47 passed** (45 prior + 2 new fg-on-shell_chrome_bg). Matches edge-case-adjusted expectation.
- Narrow 4-module gate: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 30` → **58 passed** (within the 56-60 expected range).

**Deviations**: None of substance. Two minor adjustments worth noting:

- The F3 cross-reference bullet was authored as `documented under F3.5 — see F3.5's section \`### Mission 08 Flight 3.5 — ...\`` (rather than `documented under F3.5 — see \`### Mission 08 Flight 3.5...\``). The original phrasing satisfied the intent but missed the leg's literal `see F3.5` / `see.*F3.5` regex sentinel because the regex expects the `F3.5` token to appear after `see` within the line. Adjusted the phrasing to include `see F3.5` literally without altering the reference's meaning.
- Light theme `--shell-bg` definition now lives at line 365 of tokens.css (was 349 before this leg) because the new `--shell-topbar-sheen` token + cascade-override comment lines pushed it down ~16 lines.

**Anomalies**: None. No additional `--bg-gradient` consumers discovered beyond the 5 sites the design review identified.

**Flight Director follow-up**: visual smoke check (`make rebuild` + dark/light page-load) deferred to Flight Director per leg spec.

### Leg 02 — Agents-area polish (landed 2026-05-12)

**Status**: landed. Vibe iteration covered the Agents tile grid + Agent editor (General / Tools / MCPs tabs). Knowledge tab stub-deferred per flight spec. Theme port (dark → light) verified by operator with no light-specific issues.

**Vibe iteration outcomes** (CSS in `components.css` + `studio.css`; JS in `mcps-tab.js` + `tools-tab.js` + `general-tab.js`):

- **Agents tile grid**: padded out `.entity-tile-grid` from `8px`→`20px` outer + gap `8px`→`16px` for breathing room. Affects Admin's provider grid identically (canonical primitive, single edit site).
- **Sidebar nav contrast**: `.section-nav-item` base color `--fg-secondary` → `--fg` (low contrast on the F3.5 metallic chrome was the trigger); active item gains `font-weight: bold`. Cascades site-wide across Chat / Studio / Admin sidebars.
- **Agent-editor tablist**: dropped editor-header + tablist bottom borders; selected tab gets an accent L-stripe (left + bottom + 5px chamfer diagonal) painted via a `::before` polygon clip-path on `.tab` (echoes `#main-content` L-bracket aesthetic).
- **General tab**: name field always renders (was create-only — see Agent Rename functional batch); `Advanced` collapsible (stub temp/top_p/max_tokens) removed; `.model-loading:empty { display: none }` to recover the 8px flex-gap that was eating the Model `<select>` width.
- **MCPs tab restructure**: native `<details>` per source → tile-shape echoing `.entity-tile` (`mcp-source-tile` — glass + gleam + bezel; no click-state since controls live inside). Row 1: `[toggle] name [protocol badge] [↻ Refresh]`. Subtitle (F4 L2 functional batch) shows server-declared identity. Row 2: `[X / Y enabled] chicklet` (matches built-in Tools category chicklet) + expand button `[N tools ▸]`. Inside expansion: per-tool tiles with `[checkbox] name — description` (100-char + ellipsis; full text on `title=` tooltip). Refresh icon inline via `App.icon('refresh')`.
- **Tools tab restructure**: same shape as MCPs tab. Categories (Filesystem / Execution / Web) render as `tools-category-tile` (echo `.mcp-source-tile`). Row 1: master iOS-pill toggle + name + `X / Y enabled` chicklet. Tristate via `:indeterminate` pseudo (accent-translucent track + thumb at midpoint). Click master → all-on or all-off. Expand button reveals tool tiles. Each tool = a `<details class="tool-tile">` with summary = `[checkbox] name — description [Overrides ▸]`; body holds the schema-driven override form (lazy-loaded by `wireOverridePanel` on first toggle; preserves `tool_overrides` JSON via DOM-roundtrip on save). All / None page-level buttons removed (per-category master toggle subsumes them).
- **Inline checkbox visibility fix**: dropped the `.tool-toggle` class from the inner tool checkboxes (that primitive is `display: none` for the iOS-pill pattern). Switched `studio.js:1471`'s collector query from `.tool-toggle[data-tool]` → `input[type="checkbox"][data-tool]` so the visible `.checkbox-primary` inputs still round-trip on save.
- **CSS specificity fix**: agent-editor `.mcp-tool-description` was inheriting the source-editor's `padding: 4px 12px 12px 32px` (same class, different consumer). Re-scoped via `.mcp-tool-text .mcp-tool-description` selector.

**Functional batches** (full detail in sub-sections below): agent rename (separate Developer agent); MCP `serverInfo` + `instructions` capture and tile display (separate Developer agent); per-tool override-schema config UX deferred (data-roundtrip preserved via DOM, but new overrides not yet settable via UI in the new structure — captured as a follow-up in the leg's functional-batch section).

**No new design tokens introduced** this leg (`--surface-elevated` + `--accent-translucent` + existing chrome/glass tokens were sufficient).

**Verification**: WCAG audit (47/47) + agent-rename (9/9) + MCPClient (70/70) all pass — narrow gate `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_agent_rename.py tests/test_mcp_client.py -x -q --timeout 30` → **126 passed**. Manual smoke: console clean across Studio → Agents → open agent → tab-switch flow; theme toggle exercised both directions.



Vibe iteration on Agents-area styling is driven by the Flight Director in real-time against `components.css` + `studio.css`. The progress entry below is for an opportunistic functional batch that landed during the vibe leg.

#### Functional Batch — Agent Rename (landed 2026-05-12)

**Context**: Operator requested the ability to rename agents (currently name is the DB primary key and immutable post-create). Landed as a functional batch within the Leg 02 vibe iteration; the vibe CSS work continues in parallel.

**Implemented**:

- **Store layer** (`the_one/db/repositories.py`, `the_one/agent/store.py`):
  - Added `async def rename(old, new)` to the `AgentConfigStore` Protocol.
  - `SQLiteAgentStore.rename` performs an atomic `UPDATE agents SET name=?, updated_at=?` plus manual cascade `UPDATE chat_sessions SET agent_name=?` in a single transaction. The FK on `chat_sessions.agent_name` was already dropped in schema v5 (`schema.py:188`), so the cascade is explicit in code.
  - `FilesystemConfigStore.rename` (sync legacy) added for protocol parity: moves `{old}.json` → `{new}.json` and rewrites the `name` field inside.
  - Error contract: `KeyError` on source-missing (matches `delete()`), `ValueError` on target-exists (mapped to 409).

- **API endpoint** (`the_one/interfaces/web/api.py`):
  - `POST /api/agents/{name}/rename` accepts `{"new_name": "..."}`.
  - 422 on empty/missing/whitespace-only `new_name` or `new_name == name`.
  - Validation reuses `AgentConfig.model_validate` against the existing agent's full payload with `name` swapped (no duplicate name-validation rules; future name constraints picked up automatically).
  - 404 on missing source, 409 on target collision, 200 returning the renamed agent's full config dump.

- **Frontend wiring**:
  - `general-tab.js`: Name field is now rendered for both create AND edit modes (was create-only). The `data-field="name"` hook + `studio-name` id are preserved so `collectFormData` already picks it up.
  - `studio.js` save path (line ~1651): existing-agent branch detects `formData.name !== oldName`, POSTs to `/api/agents/{old}/rename` FIRST, then proceeds with PUT against the new name. On rename failure, surfaces the error to the editor and aborts the save. On success, re-binds `self._selectedAgent` to the renamed payload, refreshes the agent list, re-renders the editor, and calls `writeUrl_()` so refresh / back-button targets the new name.

- **Mission known issue**: Appended a bullet to `missions/08-gleepglorp-rebrand/mission.md` `## Known Issues` documenting the stale in-memory PTY tool-session registry keys after rename. Workaround: close active chat sessions before renaming. Follow-up: registry-rebind hook (~10-20 LOC) deferred from Leg 02 to keep functional batch scoped.

**Tests** (`tests/test_agent_rename.py`, new file):

| Case | Status |
|---|---|
| Happy path: rename → new-name 200, old-name 404 | PASS |
| Conflict on existing new_name → 409 | PASS |
| Source not found → 404 | PASS |
| Same name → 422 | PASS |
| Empty new_name → 422 | PASS |
| Whitespace-only new_name → 422 | PASS |
| Missing `new_name` field → 422 | PASS |
| Non-name fields preserved across rename | PASS |
| `chat_sessions.agent_name` cascade verified | PASS |

`docker exec the-one pytest tests/test_agent_rename.py -x --timeout 30 -v` → **9 passed in 1.42s**.

Related-regression sweep: `docker exec the-one pytest tests/test_agent_tool_overrides_round_trip.py tests/test_db_repositories.py tests/test_db_api.py tests/test_filesystem_config.py -x --timeout 30 -q` → **106 passed in 10.83s**. No regression in agent-store / agent-API / DB repo / filesystem store paths.

**Files touched**: `the_one/agent/store.py`, `the_one/db/repositories.py`, `the_one/interfaces/web/api.py`, `the_one/interfaces/web/static/js/areas/studio/general-tab.js`, `the_one/interfaces/web/static/js/areas/studio.js`, `missions/08-gleepglorp-rebrand/mission.md`, `tests/test_agent_rename.py` (new). CSS files under active vibe iteration (`components.css`, `studio.css`, `tokens.css`) deliberately untouched.

**Anomalies**: None.

---

## Decisions

### Reconnaissance carry-forward classification

**Context**: Flight 3 + Flight 3.5 debriefs surfaced 11 cumulative action items + the mission's native-`<select>` Known Issue. All items in scope for Flight 4 per operator directive ("roll in all of those recommendations").
**Decision**: 7 Flight 3.5 debrief items consolidate into Leg 01 prep (autonomous, mechanical). 4 items split across Legs 03 / 04 / 05. Knowledge-tab polish deferred (stub).
**Impact**: Leg 01 absorbs the technical-debt close so polish legs (02, 03) operate on a clean substrate. Leg 04 (custom dropdown) + Leg 05 (Studio dirty-gate parity + B2 regression test) handle infrastructure work. Legs 06 (routing sweep) + 07 (alignment close) follow the established Flight 3 template.

### Design-review (Architect) feedback incorporated

**Context**: Phase 5b Architect review returned `approve with changes` with 2 high + 3 medium + 1 low severity issues + 3 suggestions + 3 questions.
**Decision**: All 6 issues addressed in the flight artifact before Phase 6 closure. Specifically:

- **(high) Stale-then guard scope misframed**: original Leg 05 scope listed `fetchAgent` per-agent detail as needing a guard; this function doesn't exist (agents load only via `loadAll()` at init, already guarded). Studio also already guards `fetchMcpSources_()` (lines 470/475/484) + `fetchMcpSourceTypes()` (line 355). Reframed Leg 05 as "verify + gap-fill," not infrastructure-from-scratch.

- **(high) Chat `#chat-agent-select` (chat.js:55) omitted from dropdown migration**: high-traffic on-shell native select. Leaving it native creates a visible inconsistency post-Flight-4 that Flight 6 would have to revisit. Added to Leg 04 migration scope (opportunistically; not gating Flight 6).

- **(medium) Studio confirmLeave is smaller than initial framing**: Studio already has inline `dirty + inEditor` gate at studio.js:301-303 in sidebar setActiveSection. Leg 05's work is EXTRACTION + EXPOSURE (closure + descriptor method), not from-scratch implementation. Updated Design Decisions to reflect ~20 LOC instead of ~30+.

- **(medium) Leg 04 conflates 3 work shapes** (helper-build / popover-vibe / migration): added explicit migration checkpoint before vibe-close. Acceptance criterion: grep verifies all 7-8 migration sites swapped before vibe-close.

- **(medium) Leg 03 MCP Server editor (1654 LOC) + LED wire-up is heaviest leg**: added pre-leg LED-site audit so the wire-up sub-task has a known-finite consumer-site list pinned in the leg artifact before vibe kickoff. Isolates LED from the open-ended polish vibe.

- **(low) `--bg-gradient` alias is over-engineered**: only 1 internal consumer. Hard rename, no alias. Updated Design Decisions.

3 suggestions applied:
- agents.md F4 subsection will be lean (only `App.dropdown` is an F4-original pattern).
- "Vibe-leg conventions" subsection name (vs. "flight-design conventions") — narrower and more accurate.
- Playwright B2 test: keep parametrized one-file approach.

3 questions resolved with explicit decisions:
- `#chat-agent-select` → included in Leg 04 migration (not deferred).
- Routing sweep covers all Studio sub-routes including Knowledge stubs (routing correctness is structural, not cosmetic).
- Studio `inEditor` predicate covers BOTH editor mount contexts: `(activeSection === 'agents' && _selectedAgent)` AND `(activeSection === 'mcp-sources' && mcpSourceFormMode)`.

**Impact**: Flight 4 enters Phase 6 with a codebase-validated spec. Leg 05 scope correctly framed. Migration scope corrected to 8 sites (including Chat agent-select). No re-review needed.

---

## Deviations

*Populated during execution.*

---

## Anomalies

*Populated during execution.*

---

## Session Notes

### 2026-05-12 — Leg 02 functional batch: surface MCP serverInfo + instructions

Opportunistic functional batch executed alongside the Flight Director's vibe iteration on the agent-editor Tools tab. Scope: capture spec-optional `serverInfo` and `instructions` from the MCP `initialize()` response and surface them on the agent-editor MCPs tab tile as a subtitle line + hover tooltip.

**Files touched**:
- `the_one/mcp/client.py`: Added `_server_info` / `_instructions` slots; capture from `result.serverInfo` / `result.instructions` after the version + capability gates pass (line 432 commit-state block). Public properties `server_info` (returns `model_dump(mode="json", exclude_none=True)`) and `instructions` (raw str) mirror the `server_capabilities` guard pattern. Disconnect clears both for fresh reconnect repopulation.
- `the_one/interfaces/web/api.py`: Extended all three `_cache` write sites — `_build_and_test_no_auth_mcp` (~line 1078), `_build_and_test_stdio_mcp` (~line 1160), and the Phase A oauth path in `/test/connect` (~line 1371) — to snapshot `client.server_info` + `client.instructions` inside the async-with and persist them as `_cache.server_info` / `_cache.instructions`.
- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js`: Added subtitle slot between row1 and the expand button. Reads `source.config._cache.server_info` (skips when absent — create-mode tiles stay clean); renders `{title||name} · v{version}`; hangs `instructions` off the subtitle as `title=` tooltip with a `.has-instructions` modifier for the help-cursor affordance. Existing tile structure preserved (no restructuring).
- `the_one/interfaces/web/static/css/admin.css`: Appended `.area-studio .mcp-source-tile-subtitle` rule inside the existing `@layer areas` block (studio.css off-limits per vibe iteration; admin.css is layer-equivalent, so the `.area-studio` selector lands correctly in the cascade). Subdued caption-size text with dotted-underline hover cue when instructions are present.
- `tests/test_mcp_client.py`: Extended `_make_init_result` with `server_info_dump` + `instructions` kwargs; added `test_connect_captures_server_info_and_instructions` locking the property contract (pre-connect raises, post-connect returns dict/str, post-disconnect raises). Also extended `test_connect_happy_path` to assert defaults when the server omits the fields.
- `tests/test_mcp_stdio_test_connect.py`, `tests/test_mcp_connection_reset.py`, `tests/test_oauth_test_connection_endpoint.py`: Added `server_info` + `instructions` properties (returning None) to every `_MockMCPClient` (12 mocks total) so the cache-write paths can snapshot them without AttributeError.

**Where the cache-write happens**: three sites in `api.py`. The no-auth-http helper writes `auth_posture: "no_auth"` alongside the new fields; the stdio helper omits `auth_posture` (HTTP-path concept); the Phase A oauth-test path mirrors the stdio shape minus the auth_posture omission rationale. All three sites snapshot `client.server_info` / `client.instructions` INSIDE the `async with MCPClient(...)` block — properties raise post-disconnect, so the snapshot ordering matters.

**Test results**: 70 MCPClient tests pass (new test included). 8 stdio test-connect tests pass. 10 connection-reset tests pass. 8 oauth test-connect tests pass. 48 broader MCP integration + pool + oauth tests pass. No regressions across 144 MCP-related tests.

**Anomalies**: None. The Flight Director's parallel vibe edits on `tools-tab.js` + studio.css + components.css + tokens.css were untouched per the leg scope.

**Manual verification path** (not autonomously exercised — requires a live MCP server with populated serverInfo/instructions; Cloudflare Docs MCP is the canonical case):
1. Add a Cloudflare Docs MCP source in Studio → MCP Sources.
2. Click Test/Connect on the source-edit page; observe `_cache.server_info` and `_cache.instructions` populate in the persisted config (visible in the GET response).
3. Open an agent in Agents → edit → MCPs tab; the source tile should show a subtitle line `Cloudflare Docs MCP · v<version>` with a dotted-underline hover affordance.
4. Hover the subtitle; the full instructions prose should appear in the native browser tooltip.

---

## Flight Director Notes

### Flight design (2026-05-12)

- Loaded flight-design phase file from `/home/cprch/projects/the-one/.flightops/agent-crews/flight-design.md` (project file present).
- Reconnaissance verified 11 carry-forward items (8 from Flight 3.5 debrief + 3 from Flight 3 debrief + 1 mission Known Issue). All `confirmed-live`. No retirements.
- Flight scoped as 7 legs: 1 autonomous prep (7-item debt close from Flight 3.5 debrief), 2 vibe page-polish (Agents + MCP Sources), 1 mixed leg for custom dropdown (autonomous helper + vibe popover treatment), 1 autonomous infrastructure (Studio confirmLeave + stale-then + B2 Playwright test), 1 mixed routing-sweep, 1 closing alignment.
- Scope shaving applied per Flight 3.5 debrief recommendation #8: shell housing inherited from F3.5 → per-page polish operates on `.content-panel` interior only. Saved ~1 vibe leg vs. originally-planned size. Knowledge tab polish-deferred (21-line stub).
- Custom dropdown component (mission Known Issue → F3 deferred → F4) gets its own leg with autonomous helper-building + vibe popover treatment. Migrates 4 Studio sites + 2-3 Admin sites.
- Studio cross-area dirty-gate parity + B2 regression test consolidated into one leg — implementing both atomically because the test verifies the hook (no point shipping the hook without the test that locks it in).
- "Land dark, port light" cadence applies to vibe legs 02 + 03 per Flight 3.5 debrief recommendation #4.
- All open questions resolved with working assumptions documented inline.
