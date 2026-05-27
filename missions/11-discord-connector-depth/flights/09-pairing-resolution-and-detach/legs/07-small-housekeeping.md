# Leg: small-housekeeping

**Status**: completed
**Flight**: [Pairing Resolution + Connectors-Screen Detach](../flight.md)

## Objective

Three small fold-ins, none of which warrant their own leg:

1. **F7 Rec #3(a)** — Flip `.tool-enable-switch` default from `position: absolute` (tile-corner placement) to `position: relative` (inline placement), since the override-to-relative consumers (5+ sites) outnumber the original tile-corner consumers (~2 sites). Add a `.tool-enable-switch--corner` opt-in modifier for tile-corner consumers.
2. **F8 action item** — Extend `provider-shape-portability` convention in `agents.md:134-151` with a one-paragraph operator runbook covering legacy-row `AssertionError` triage.
3. **L5 regression fix** — `tests/browser/test_flow_studio_connector_discord_vocabulary.py::test_discord_account_attached_agents_header_renders_substituted_labels` asserts the attached-agents table has 3 columns (`["Agent", "Users", "Channels"]`) but L5 added a 4th column (the empty `<th>` for the Detach action). Update the test's expected headers to include the empty 4th column.

## Context

**Why L7 fold-in vs separate legs.** All three are sub-50-LOC, no architectural risk, share no inter-axis dependencies, and each is "complete or not" without intermediate state. The flight's "small-housekeeping" naming makes the bundling intent explicit. F4 debrief's atomic-leg pattern still applies: if any one axis turns out to need >50 LOC of investigation, split it out.

### Axis 1: `.tool-enable-switch` default flip

**Inventory** (verified at design time via cycle-1 reviewer grep):

Default rule at `admin.css:197-205` — `.area-admin .tool-enable-switch, .area-studio .tool-enable-switch { position: absolute; bottom: 12px; right: 12px; ... }`.

Live override-to-relative sites (4 total):
1. `admin.css:278-283` — `.area-admin .tools-editor-enabled-row .tool-enable-switch, .area-studio .mf-sandbox-network-row .tool-enable-switch { position: relative; ... }`
2. `admin.css:284-288` — `.area-studio .field-row.cf-auto-relay-row .tool-enable-switch { position: relative; ... }`
3. `admin.css:296-301` — `.area-studio .field-row.connector-account-always-listen-row .tool-enable-switch, .area-studio .field-row.cf-always-listen-row .tool-enable-switch { position: relative; ... }`
4. `studio.css:760-766` — `.area-studio .mcp-kv-sensitive-cell .tool-enable-switch { position: relative; ... }`

Plus one **orphaned rule** at `studio.css:1111-1117` — `.area-studio .tool-enable-switch.connector-allowlist-switch { ... }`. The `connector-allowlist-switch` class is NEVER emitted in the codebase (grep-verified at design time). L7 deletes this dead rule outright — matches the agents.md "rewrite or delete; don't leave stale" convention.

Plus one **unrelated `position: static` override** at `admin.css:644` — `.design-language-toggle-sample .tool-enable-switch { position: static; }`. STAYS — this is `static`, not `relative`, and serves a different purpose (the design-language demo). L7 does NOT touch it.

**Tile-corner consumers** (sites that NEED `position: absolute`, verified by reviewer grep):
- ONLY ONE site: `the_one/interfaces/web/static/js/areas/admin/tools-grid.js:67` (inside `<div class="entity-tile tool-tile">` at line 61).

All other `.tool-enable-switch` emit sites are inline contexts: `tools-editor.js:218`, `mcp-server-editor.js:531`, `mcp-server-editor.js:836`, `connector-account-editor.js:476`, `connectors-tab.js:500`, `surfaces-section.js:92, :97` (the design-language demo). The Studio MCP-source tiles and connector-account tiles use a SEPARATE `mcp-source-tile-toggle` primitive, NOT `tool-enable-switch` — they don't enter L7's scope.

**Refactor**:
- Flip the default rule at `admin.css:197-205` to `position: relative; display: inline-block;` (the latter to preserve sizing semantics that `absolute` provided). Drop the `bottom: 12px; right: 12px;` properties from the default (move them to the new `--corner` modifier).
- Add a new modifier rule `.area-admin .tool-enable-switch--corner, .area-studio .tool-enable-switch--corner { position: absolute; bottom: 12px; right: 12px; }`.
- Update the ONE tile-corner consumer at `tools-grid.js:67` to emit `<label class="tool-enable-switch tool-enable-switch--corner">`.
- Remove the 4 override-to-relative rules (per inventory above). Delete `studio.css:1111-1117` (orphaned rule) as well.

**Risk** is low: only one tile-corner consumer exists; browser tests for the admin tools grid (`test_flow_admin_tools_grid.py`) are the regression net.

### Axis 2: `provider-shape-portability` runbook extension

Current convention at `agents.md:134-151` documents the mechanism and motivating case. F8's action item asks for an operator-facing runbook: what does the operator do when a legacy-row `AssertionError` surfaces in production at decode-time? The convention text already alludes to this ("Legacy rows whose stored content is non-str ... surface as `AssertionError` at decode-time — an intentional signal of underlying corruption") but doesn't tell the operator HOW to recover.

**Runbook addition** — append a paragraph after the "When this matters" list, before the "Anti-pattern" paragraph:

```markdown
**Operator runbook for legacy-row AssertionError**: when a session-replay or codec-decode path surfaces `AssertionError` in `Message.__post_init__` with non-str content, the offending row is a pre-L2 storage artifact. Triage:

1. Identify the chat_sessions row via the traceback's session_id (the dispatcher logs it in the surrounding context). Run `sqlite3 var/the_one.db "SELECT id, agent_name, length(messages) FROM chat_sessions WHERE id = '<id>'"` to confirm the row exists.
2. Decide: delete the row (loses the chat history) OR repair the row (recover the history by manually editing the messages JSON to coerce non-str content to str). For single-user local-tool use, delete is usually fine — the operator can recreate the conversation.
3. If multiple rows trigger the AssertionError, batch via `UPDATE chat_sessions SET messages = '[]' WHERE ...` (loses history) or write a one-off migration script that walks the JSON and stringifies non-str content keys.
4. After cleanup, restart the app — the storage layer is now consistent and the AssertionError stops firing.

This is intentionally manual: the rare and structurally-illegal nature of the AssertionError means we DO NOT add a fallback at the dataclass layer (would silently mask future provider-parser defects).
```

Single paragraph in the existing convention text. ~10-20 lines added.

### Axis 3: L5 vocab-test fix

The L5 implementer's flight-log L5 entry flagged: `tests/browser/test_flow_studio_connector_discord_vocabulary.py::test_discord_account_attached_agents_header_renders_substituted_labels` asserts `header_cells == ["Agent", "Users", "Channels"]` (3 columns) but L5's `renderAttachedAgentsList` now emits 4 columns (the empty `<th></th>` for the Detach action).

**Fix**: locate the assertion (likely a list comparison or `expect(...).to_have_count(3)` on the table header `<th>` elements); update to expect 4 columns with the 4th being empty (or whatever placeholder L5 emits — verify).

**Why in L7 not L5**: L5's flight-log entry deferred this to L7 since L7 already touches `agents.md` and minor test/CSS fixes; folding it in keeps the L5 review surface tight to the detach-end-to-end semantic.

## Inputs

- `the_one/interfaces/web/static/css/admin.css:197-205, 278-301` — default rule + 3 of the 5 override sites.
- `the_one/interfaces/web/static/css/studio.css:760-766, 1111-...` — 2 of the 5 override sites.
- `the_one/agents.md:134-151` — `provider-shape-portability` convention.
- `tests/browser/test_flow_studio_connector_discord_vocabulary.py::test_discord_account_attached_agents_header_renders_substituted_labels` — failing test.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:2869-2895` (L5 modified) — current attached-agents table render shape (4 columns).
- HTML/JS sites that emit `<label class="tool-enable-switch">` — need grep at implementation time.
- Browser tests for admin tools grid, studio MCP-source tiles, etc. — regression net for the CSS flip.

## Outputs

- `the_one/interfaces/web/static/css/admin.css` — default rule flipped; new `.tool-enable-switch--corner` modifier added; 3 override-to-relative rules removed (5-, 4-, 3- depending on count).
- `the_one/interfaces/web/static/css/studio.css` — 2 override-to-relative rules removed.
- HTML/JS sites that need the `--corner` modifier — updated to emit the new class.
- `the_one/agents.md` — `provider-shape-portability` runbook paragraph appended.
- `tests/browser/test_flow_studio_connector_discord_vocabulary.py` — header assertion updated to expect 4 columns.
- `missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/flight-log.md` — append L7 progress entry.

## Acceptance Criteria

- [ ] `.tool-enable-switch` default in `admin.css:197-205` is `position: relative` (NOT `absolute`). The `bottom`/`right` properties are removed from the default; the `display: inline-block` (or equivalent) preserves the sizing.
- [ ] New rule `.tool-enable-switch--corner` (selector covers both admin + studio areas) restores `position: absolute; bottom: 12px; right: 12px;` for tile-corner consumers.
- [ ] All 5 (or so) override-to-relative sites in `admin.css` and `studio.css` are removed.
- [ ] HTML/JS sites that need tile-corner positioning emit `class="tool-enable-switch tool-enable-switch--corner"` (NOT just `class="tool-enable-switch"`).
- [ ] All existing browser tests pass — particularly any tests for the admin tools grid, studio MCP tiles, and any tile that uses `tool-enable-switch`. Focus on `test_flow_admin_tools_grid.py`, `test_flow_admin_tools_editor.py`, `test_flow_admin_navigation.py` if relevant.
- [ ] `the_one/agents.md`'s `provider-shape-portability` convention has a new "Operator runbook for legacy-row AssertionError" paragraph between the "When this matters" list and the "Anti-pattern" paragraph.
- [ ] `tests/browser/test_flow_studio_connector_discord_vocabulary.py::test_discord_account_attached_agents_header_renders_substituted_labels` passes — assertion updated to expect 4 columns matching L5's `renderAttachedAgentsList` output.
- [ ] No new tests (L7 is mechanical refactor + doc + test-assertion update).

## Verification Steps

```bash
# Grep: confirm no remaining override-to-relative rules in admin.css / studio.css
docker exec the-one bash -lc "grep -nE 'position: ?relative' the_one/interfaces/web/static/css/admin.css the_one/interfaces/web/static/css/studio.css | grep -v 'corner\|kv-sensitive-cell\|connector-allowlist'"
# Expected: should see only the bus-related rules (or unrelated non-tool-enable-switch rules).

# Run the previously-failing vocab test
docker exec the-one pytest tests/browser/test_flow_studio_connector_discord_vocabulary.py -x --timeout 120 -v

# Browser tests covering the .tool-enable-switch surfaces
docker exec the-one pytest tests/browser/test_flow_admin_tools_grid.py tests/browser/test_flow_admin_tools_editor.py tests/browser/test_flow_admin_navigation.py -x --timeout 120 -v

# All studio/connector browser tests
docker exec the-one pytest tests/browser -k "connector or studio" -x --timeout 120 -v

# Full backend suite (post-L6 baseline: 2721)
docker exec the-one pytest --timeout 60 -q
```

Expected: green; suite count unchanged.

## Implementation Guidance

### Sub-step A — CSS default flip

1. **Tile-corner consumer is known** (per cycle-1 reviewer grep): ONLY `tools-grid.js:67` (inside `<div class="entity-tile tool-tile">` at line 61). Update that ONE class-string to append `tool-enable-switch--corner`. All other `.tool-enable-switch` emit sites are inline and need NO change.

2. **Flip the default rule** at `admin.css:197-205`:

```css
.area-admin .tool-enable-switch,
.area-studio .tool-enable-switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  cursor: pointer;
  /* L7 (F7 Rec #3(a)): default flipped from absolute (tile-corner) to
     relative (inline). Tile-corner consumers opt in via the
     .tool-enable-switch--corner modifier below. */
}
```

3. **Add the `--corner` modifier** immediately after the default rule:

```css
.area-admin .tool-enable-switch--corner,
.area-studio .tool-enable-switch--corner {
  position: absolute;
  bottom: 12px;
  right: 12px;
}
```

4. **Remove the 4 live override-to-relative rules** at `admin.css:278-283`, `admin.css:284-288`, `admin.css:296-301`, `studio.css:760-766`. Replace each with a brief one-line comment if context was useful, e.g.:

```css
/* L7: default is now position: relative; no override needed for
   .mf-sandbox-network-row .tool-enable-switch. */
```

5. **Delete the orphaned rule** at `studio.css:1111-1117` (`.tool-enable-switch.connector-allowlist-switch` — the class is never emitted; verified by grep). Removing dead code matches the agents.md "rewrite or delete; don't leave stale" convention.

6. **Leave `admin.css:644` (`.design-language-toggle-sample .tool-enable-switch { position: static; }`) ALONE** — it's `static`, not `relative`, and serves the design-language demo (intentional override after the flip too).

7. **Update the ONE tile-corner emit site** at `tools-grid.js:67`. Append `tool-enable-switch--corner` to the class list.

### Sub-step B — agents.md runbook

Edit `the_one/agents.md`. Find the `provider-shape-portability` convention at line 134. Insert the runbook paragraph between the "When this matters" list (ending ~line 147) and the "Anti-pattern" paragraph (~line 149). Match the surrounding paragraph tone — operator-facing, action-oriented, no "as a security-sensitive..." preamble.

Copy verbatim from the Context > Axis 2 section above.

### Sub-step C — Vocab test fix

Edit `tests/browser/test_flow_studio_connector_discord_vocabulary.py:213-218`. The actual assertion (per cycle-1 reviewer read) is:

```python
header_cells = page.locator(
    '[data-testid="connector-attached-agents-table"] thead th'
).evaluate_all("els => els.map(e => e.textContent.trim())")
assert header_cells == ["Agent", "Users", "Channels"], (
    f"Discord attached-agents headers drifted; got: {header_cells!r}"
)
```

Update the expected list to include the empty 4th column (the JS-side `.trim()` already normalizes whitespace to `""`):

```python
assert header_cells == ["Agent", "Users", "Channels", ""], (
    f"Discord attached-agents headers drifted; got: {header_cells!r}"
)
```

**Opportunistic a11y polish** (per cycle-1 reviewer suggestion, optional): update L5's empty `<th>` at `connector-account-editor.js:2880` to `<th aria-label="Actions"></th>`, matching the sibling pattern at lines 845, 891, 2351 in the same file. If you make this change, the test's expected 4th value stays `""` (`aria-label` is not in `textContent`). Single-line change. Skip if it slows the leg; not required for L7's primary acceptance criteria.

Re-run the test to confirm green.

### Sub-step D — Flight log

```
### {date} — L7 small-housekeeping (landed)

**Status**: ready → in-flight → landed

**Changes made**:
- Axis 1 (F7 Rec #3(a)): `admin.css:197-205` default flipped to `position: relative`; new `.tool-enable-switch--corner` modifier added; 5 override-to-relative rules removed; N HTML/JS sites updated to emit `--corner` modifier.
- Axis 2 (F8 action item): `agents.md` `provider-shape-portability` convention extended with operator runbook paragraph.
- Axis 3 (L5 vocab regression): `test_discord_account_attached_agents_header_renders_substituted_labels` assertion updated to expect 4 columns.

**Test outcomes**: vocab test passes; admin tools grid + tools editor + studio browser tests pass unchanged. Backend suite count: 2721 → 2721 (no new tests).

**Anomalies**: {document any}
```

## Edge Cases

- **CSS flip breaks an unidentified tile** — browser tests are the regression net. Run the full browser-test suite after the flip; any new failure points to a missing `--corner` modifier site.
- **Tile-corner consumer is in a Studio JS file the leg's grep missed** — re-run grep after the flip; check for any visual regressions in tile-corner placements via manual page navigation if browser tests are insufficient.
- **`provider-shape-portability` runbook paragraph conflicts with the surrounding tone** — the convention's existing paragraphs already mix prescriptive + descriptive. Match the existing style; no preamble needed.
- **The vocab test assertion was checking column count separately from text content** — if the assertion is `expect(table.locator("thead th")).to_have_count(3)`, update the count to 4. If it's `to_have_text(["Agent", "Users", "Channels"])`, expand. Match the actual assertion shape, not the leg's guess.
- **5+ override rules become 0 — risk of leaking the `bottom`/`right` properties** — verify by inspecting the new default rule; if `bottom: 12px; right: 12px;` are absent (per Sub-step A step 2), no leak.

## Files Affected

- `the_one/interfaces/web/static/css/admin.css` — flip default + add `--corner` modifier + remove 3 override sites (~20 LOC net).
- `the_one/interfaces/web/static/css/studio.css` — remove 1-2 override sites (~10 LOC removed).
- HTML / JS sites emitting `tool-enable-switch` inside tile-corner contexts — update class lists.
- `the_one/agents.md` — +1 paragraph in `provider-shape-portability` convention (~10 LOC).
- `tests/browser/test_flow_studio_connector_discord_vocabulary.py` — 1-line assertion fix.
- `missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/flight-log.md` — L7 entry.

Estimated total: ~40-80 LOC of net change.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] CSS-touch browser tests pass
- [ ] Vocab test passes
- [ ] Update flight-log.md with L7 progress entry (template above)
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (deferred to Phase 2d commit)
- [ ] Do NOT commit (deferred to Phase 2d batch commit)
- [ ] Signal `[HANDOFF:review-needed]` to the Flight Director

## Citation Audit

6 citations verified against current code at leg design time (post-L6):
- `admin.css:197-205` (default `.tool-enable-switch` rule) — OK
- `admin.css:278-301` (3 override sites) — OK
- `studio.css:760-766` (one override site) — OK
- `studio.css:1111` (`.connector-allowlist-switch` site — needs implementer verification of its actual `position:` value) — partial.
- `agents.md:134-151` (`provider-shape-portability` convention) — OK
- `tests/browser/test_flow_studio_connector_discord_vocabulary.py::test_discord_account_attached_agents_header_renders_substituted_labels` — exists; assertion shape needs implementer-time verification.
