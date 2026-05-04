# Leg: 09-docs-refresh

**Status**: landed
**Flight**: [Tools Admin Section](../flight.md)

## Objective

Post-Reviewer documentation refresh. Updates `CLAUDE.md` (Tool Authorship Contract addendums for the F6 surfaces), `agents.md` (new Tools admin section description + the Studio per-agent override UI documentation), and any other doc surface that references tools-admin / tool_overrides. Doc author works from the AS-BUILT code (post-first-Reviewer-pass), NOT from the leg specs — eliminating the doc-drift class that affected F4/F5 doc passes (per F5 debrief recommendation 2 / F6 Decision 12). After L9 lands, a SECOND Reviewer pass verifies docs match the code; only then does the F6 batch get committed and PR'd.

## Context

- **F5 debrief recommendation 2**: doc author works from as-built code (post-pass-1), not from spec. F4/F5 had recurring 4-claim doc drift in their L8 doc passes; F6 fixes this by deferring docs to L9 + adding a second Reviewer pass.
- **F6 Decision 12**: docs go in their own leg AFTER first Reviewer signs off.
- **Reviewer's first-pass result**: `[HANDOFF:confirmed]` with one trivial fix (3 leg statuses flipped — done). All code/correctness/test criteria satisfied. The doc author can trust the code.
- **Surfaces to document**:
  - `CLAUDE.md` "Tool Authorship Contract" — add F6-introduced patterns: schema migration v9 pattern, marker enrichment helper for admin UI, REPLACE-not-merge PUT contract, named-tool isolation in test endpoint, server-side `_enrich_schema_with_markers`, agent-mode marker dispatch (Narrow ceiling, NarrowSuperset locked chips, Substitute free-form, unmarked HIDDEN), `tool_overrides` dict shape on `AgentConfig`, the iOS-toggle CSS positioning trap (absolute vs relative).
  - `agents.md` — new "Tools admin section" subsection describing operator workflow (enable/disable, narrow constraints, run connection test). Studio Tools tab section gets an "Agent-level overrides" subsection.
  - `README.md` — only if F6 introduced a user-facing CLI command or env var; verify (it didn't — no README update needed).
  - Mission Known Issues are already current (chip-list UI polish entry added in L6).
- **What L9 does NOT touch**:
  - Source code (no implementation changes — verified by the first Reviewer).
  - Tests (no test changes — already covered).
  - Leg artifacts (frozen post-landing).
  - Flight log (frozen post-L8 entry, except for L9's own progress entry).
- **Second Reviewer pass scope** (after L9 lands): verifies (a) every doc claim references real code at the claimed line/symbol, (b) no stale references to F1-F5 patterns that F6 superseded, (c) examples actually work, (d) doc structure matches the existing `CLAUDE.md`/`agents.md` style.

## Inputs

- `CLAUDE.md` — current "Tool Authorship Contract" section (the canonical reference for tool-implementation patterns).
- `agents.md` — current Tools / Studio sections (verify exact location during implementation; section headings may have shifted).
- All L0-L8 source files as the as-built ground truth.
- Flight log Decisions / Deviations sections — capture the runtime decisions that shaped the as-built (e.g., L0 stale-version-assertion update, L3 cancel re-mount option, L5 helper extraction).

## Outputs

### `CLAUDE.md` "Tool Authorship Contract" — F6 addendum subsection

Append a new sub-section under the existing "Tool Authorship Contract" header. Suggested heading: `### F6 admin UI patterns`. Content:

1. **Operator-set kill switch** — `tool_configs.enabled` (schema v9). All tool authors must declare a Pydantic Config (existing) AND understand that `ToolConfig.enabled = False` removes the tool from `AgentFactory.create()`'s registry build, independent of per-agent `enabled_tools`/`disabled_tools` whitelisting. The introspection path (`BuiltinToolProvider.get_tools()` no-arg) returns ALL tools regardless — admin surfaces (the L2 grid, the L1 `GET /api/tools/configs`) need to render disabled tools as such, so the filter lives ONLY at the factory boundary, NOT inside `get_tools`.

2. **Marker enrichment for admin UI** — Pydantic v2's `Model.model_json_schema()` strips marker classes (`Narrow`/`NarrowPrefix`/`NarrowSuperset`/`Substitute`). Server-side helper `_enrich_schema_with_markers(schema, config_class)` at `the_one/interfaces/web/api.py` walks `field_info.metadata` with identity checks (`m is Narrow`, etc.) and injects `x_marker` per top-level property. Tool authors who add new marker classes MUST extend this helper's `marker_map`.

3. **REPLACE-not-merge PUT contract** — `PUT /api/tools/configs/{name}` with body `{enabled?, config?}` REPLACES `config` wholesale when present, preserves when omitted. Top-level `enabled` is preserved when omitted (asymmetric with `config`). Wipe to defaults: send `{"config": {}}`. The L3 form always submits the full state, so REPLACE matches its actual behaviour.

4. **Named-tool isolation in test endpoint** — `BuiltinToolProvider.get_tools` builds `cross_configs[Config]` by walking `_TOOL_CLASSES` in declared order and resolving from the FIRST tool name carrying that Config. The test endpoint (`POST /api/tools/configs/{name}/test`) re-keys EVERY tool sharing the named tool's Config class to use the named tool's saved row, so `cross_configs[NamedConfig]` carries the tested tool's saved config regardless of declaration order. This differs from the agent runtime, where the FIRST-declared-tool semantics intentionally apply.

5. **Agent-mode marker dispatch** (Studio Tools tab override panels):
   - `Narrow` (int) → `<input type=number min={prop.minimum} max={operator_value}>` (operator's value as ceiling, schema floor preserved).
   - `Narrow` (list[str]) → chip-list constrained to subset of operator's items.
   - `NarrowSuperset` (list[str]) → chip-list with operator's items as locked chips (rendered WITHOUT `<button class="chip-remove">` element entirely — not just CSS-hidden — for keyboard focus + screen reader correctness).
   - `NarrowPrefix` (list[str]) → chip-list (prefix semantic is server-side validation only).
   - `Substitute` (any) → free-form input.
   - Unmarked field (e.g., `redirect_cap`) → HIDDEN from agent override surface (resolver raises on agent override of unmarked fields).

6. **`tool_overrides` shape** — `AgentConfig.tool_overrides: dict[str, dict[str, Any]] | None`. Empty dict = no overrides; per-tool entries are validated by `resolve()` at AgentFactory.create(). Save path (`studio.js::collectFormData`) walks `[data-tool-override-tool][data-tool-override-field]` inputs, drops empty per-tool entries, returns `null` (not `{}`) for empty top-level.

7. **Schema migration v9 pattern** — idempotent `ALTER TABLE ... ADD COLUMN` guarded by `PRAGMA table_info`; individual `await conn.execute(...)` (NOT `executescript`); `INSERT OR IGNORE INTO schema_version` LAST. New columns must be `NOT NULL` with explicit DEFAULT to avoid orphaned NULL rows on existing data.

8. **iOS-toggle CSS positioning trap** — the grid tile's `.tool-enable-switch` is `position: absolute; bottom: 12px; right: 12px;` (designed for a `position: relative` tile container). Reusing the same widget inside an editor row requires an `unpinning` override (`position: relative; bottom: auto; right: auto;`) — without this, the toggle floats to the document body's bottom-right.

9. **Validation-error JSON-encoding** — Pydantic v2's `ValidationError.errors()` may carry a raw exception in `ctx['error']` for `model_validator` paths. FastAPI's JSONResponse cannot serialize raw exceptions → 500 instead of 422. Always pass `include_context=False` to `e.errors()` when constructing the `HTTPException(detail=...)`.

10. **Shared form helpers** — `App.adminFormHelpers` (at `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js`) is the canonical form-rendering substrate, consumed by both admin (L3 editor) and Studio (L5 override panels). Future flights extending tool config UI should use these helpers with a `context = {mode: 'admin' | 'agent', operatorValue?, attrPrefix, toolName?}` object.

### `agents.md` — new "Tools admin section" subsection

Locate the existing Tools section in `agents.md` (verify exact heading during implementation). Append or insert:

```markdown
### Built-in tools admin (F6)

Operators manage built-in tool defaults via `Settings → Built-in Tools` in the web UI. Each tool tile shows a category badge (filesystem / execution / python / web), the tool's prompt, and an enable/disable toggle. Disabled tools are excluded from every agent's runtime registry.

Click a tile to open the per-tool editor:

- **Configuration section**: enable/disable toggle plus typed widgets for each Config field (number inputs, dropdowns, chip-lists for list[str], free-form text for Substitute fields). Hover the `ⓘ` icon next to any field for the description.
- **Test connection** (web_search and fetch_url only): runs the tool against a configurable input (defaults to a fixture query / URL) using the operator's currently-saved configuration. Use this to verify a narrow / denylist actually refuses, or to confirm a network change still works.

### Per-agent tool overrides (F6)

The Studio agent editor's Tools tab surfaces operator-disabled tools with a strikethrough name + dim row + "Disabled by operator" tooltip; the agent's existing on/off state is preserved across operator toggle cycles.

For each enabled tool with a non-empty Config, a collapsible "Narrow constraints" panel below the row exposes the agent override surface:

- `Narrow` (int) fields surface a number input capped at the operator's saved value.
- `Narrow` (list[str]) fields surface a chip-list constrained to the operator's items.
- `NarrowSuperset` (list[str]) fields surface a chip-list with the operator's items as locked chips (no remove button) plus an input for the agent to ADD entries.
- `Substitute` fields surface a free-form text input.
- Unmarked operator-only fields (e.g., `WebConfig.redirect_cap`) are HIDDEN from the agent override surface.

Saved overrides land in `AgentConfig.tool_overrides: dict[str, dict[str, Any]] | None`.
```

### `README.md` — verify only

Read README.md to confirm F6 introduces no new CLI commands or env vars. If it does, add. (F6 is admin UI + endpoints; no expected README impact.)

### Other docs

- Mission Known Issues — already current (L6 added the chip-list UI polish entry).
- Flight log — only the L9 progress entry gets added.
- No leg artifacts touched (frozen post-landing).

## Acceptance Criteria

- [ ] `CLAUDE.md` "Tool Authorship Contract" section gains the F6 addendum (10 patterns above).
- [ ] `agents.md` gets the "Built-in tools admin" + "Per-agent tool overrides" subsections; existing tools/studio sections updated with cross-references.
- [ ] `README.md` verified untouched (no F6 user-facing CLI/env changes); OR updated if F6 actually introduced any.
- [ ] Every doc claim points to a real code file/symbol/line that exists post-L0-L8.
- [ ] No L0-L8 source/test/leg-artifact changes — L9 is doc-only.
- [ ] Flight log L9 progress entry written.
- [ ] Leg status `landed` after all doc updates.

## Verification Steps

```bash
# 1. Doc edits made
git diff --stat CLAUDE.md agents.md 2>/dev/null
# Expect: only those two files modified for L9 (plus the leg artifact + flight log)

# 2. Cross-reference doc claims against code (spot-check a few)
grep -n "tool_configs.enabled\|_enrich_schema_with_markers\|tool_overrides" the_one/db/schema.py the_one/interfaces/web/api.py the_one/agent/config.py | head -10

# 3. No source/test changes
git diff --name-only the_one/ tests/ 2>&1 | head -5
# Expect: empty (L9 is doc-only)

# 4. Lint clean (no Python touched, but verify markdown if a linter is configured)
# (Skip if no markdown linter is part of the project tooling.)
```

## Implementation Guidance

1. **Read the as-built code FIRST** — do NOT work from the leg specs. Open `the_one/db/schema.py`, `the_one/interfaces/web/api.py`, `the_one/agent/factory.py`, and the JS modules at `the_one/interfaces/web/static/js/areas/admin/` and `the_one/interfaces/web/static/js/areas/studio/`. Verify each doc claim against actual code.
2. **Read `CLAUDE.md` "Tool Authorship Contract"** — locate the existing structure (is it bullet list? subsections? code-fenced examples?) and match the addendum's style.
3. **Read `agents.md`** — locate the existing Tools / Studio sections; append at the right depth in the doc tree.
4. **Verify `README.md`** — should be untouched; quick read confirms no F6 user-facing CLI changes.
5. **Write the doc edits** — keep prose concise; cross-reference code locations (e.g., "see `_enrich_schema_with_markers` at `the_one/interfaces/web/api.py:75-115`").
6. **No examples that aren't tested** — every code snippet in the docs should be runnable / round-trip via the existing test suite.
7. **Flag any doc drift discovered** — e.g., if CLAUDE.md still references a pre-F2 pattern that's no longer canonical, fix it as part of the F6 doc pass.
8. **Flight log L9 entry** — list each doc file touched + the new/modified sections.
9. **Set leg status to `landed`** — same protocol as other legs.

## Edge Cases

- **CLAUDE.md "Tool Authorship Contract" doesn't exist yet** — verify; if absent, the F6 addendum becomes the FIRST entry under a newly-created section.
- **agents.md location ambiguity** — verify the doc actually lives at `agents.md` (project root) vs `docs/agents.md` vs elsewhere. Adjust the L9 plan if needed.
- **Doc style mismatch** — if existing CLAUDE.md uses prose paragraphs and L9's plan uses numbered bullets, conform to the existing style.
- **Stale F1-F5 references** — if any doc claims a pre-F6 pattern that F6 changed (e.g., "tools always run for every agent" pre-L1 enforcement), update those too.

## Files Affected

- `CLAUDE.md` — F6 addendum to "Tool Authorship Contract".
- `agents.md` — Tools admin + Per-agent overrides subsections.
- `README.md` — verify (likely untouched).
- Flight log — L9 progress entry.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] L9 doc edits present in `CLAUDE.md` + `agents.md`
- [ ] No source/test changes
- [ ] Update flight-log.md with L9 progress entry
- [ ] Set this leg's status to `landed`
- [ ] **SECOND Reviewer pass over the docs comes NEXT** — flag in flight log that L9 is ready for review
- [ ] (NOT final commit yet — second Reviewer + commit + PR are after L9)
