# Leg: additional-config-advanced-section

**Status**: completed
**Flight**: [Daily-driver validation gate](../flight.md)
**Type**: injected (UI relocation + kv-table save round-trip fix) — L3 once-over Leg C. Visual acceptance: `connector-editor-ux` step 5.

## Objective

Keep the generic "Additional Config" key-value table (legitimate advanced/escape-hatch use — `ingest_bots`, forward-compat for not-yet-typed keys) but **demote it to its own clearly-labeled "Advanced" section at the bottom** of the connector editor, visually separated from the everyday typed fields so it reads as "you usually don't need this."

## Context

- Operator decision: *keep, don't delete* — demote. The kv-table (`renderConfigKvTable`, mounted at `connector-form-discord.js:253-277` under an "Additional Config" subheading in the Access-and-Routing/runtime-config body) is the last vestige of M10's generic-kv-config substrate; it stays for advanced use but should not compete with the typed controls.
- Purely frontend — no backend/config change. The kv-table component (`window.App.studio.renderConfigKvTable`) is reused as-is; only its placement + framing change.
- `ingest_bots` (the test/advanced seam) remains reachable here for those who need it (set via the API by the HAT; via this Advanced section by an advanced operator).

## Resolved at design review (implement to these)

- **BLOCKING — the kv-table is currently display-only for Discord (pre-existing bug):** `collectFormData` (`connector-editor.js:1675-1693`) takes the typed-fields branch for Discord (`cfdCollected` truthy) and **skips** the `else` branch (`:1694-1723`) that scans `.connector-config-row` inputs. The Discord `collect()` (`connector-form-discord.js:370-428`) never reads the kv-table → **adding a key + Save silently loses it.** To honor "keep it (working)", **Leg C must FIX the round-trip**: extend the Discord `collect()` to also scan the kv-table rows and merge **non-reserved** keys into `config` (exclude the typed/reserved keys — `token`, `intents` (post-B inert), `presence`, `allowlist`, `routing`, `application_id`, etc., per the existing `reservedConfigKeys`/`renderConfigKvTable` filter). Add a browser test: add-key → Save → key persists in the PUT payload + round-trips on reload.
- **Relocation is within `_renderRuntimeConfigBody`** (`connector-form-discord.js`): move the Additional Config block (`:265-277`) to be the LAST element of that function's return, wrapped in a `<details>`-style disclosure / distinct "Advanced" section heading (restoring the demoted-visibility shape the `:255-264` comment says was previously removed). The section orchestration in `connector-editor.js:719` does NOT need touching.
- **B↔C coordination:** both edit `collect()`. Implement **after Leg B**; read B's diff first so adding kv-collection doesn't clobber B's intent-block removal.
- **Tests:** `test_flow_studio_connector_discord_form.py:292` (row attached) survives relocation; `_create_and_test.py:229` (0 in create-mode) unaffected. No test asserts vertical position — the `connector-editor-ux` behavior test (step 5) covers placement; add the new save-round-trip test for the collect fix.

## Acceptance Criteria

- [ ] The "Additional Config" kv-table is **relocated to its own "Advanced" section at the BOTTOM** of the connector editor form (below all typed fields), with a clear section heading. Visually de-emphasized (its own section; consider a collapsed-by-default disclosure or a quiet heading — design picks, but it must not sit among the everyday typed fields).
- [ ] The kv-table **functionality is unchanged** — add/edit/remove ad-hoc config keys still works; values still round-trip through save.
- [ ] A **stable `data-testid`** identifies the Advanced section + the kv-table in its new location (keep/relocate `discord-additional-config-row` or add an `connector-advanced-section` testid) so the behavior test (`connector-editor-ux` step 5) can assert it's at the bottom.
- [ ] No regression: browser tests asserting the Additional Config row/location are updated; full browser suite green. No backend change.

## Verification Steps

- The Additional Config kv-table appears in a bottom "Advanced" section, after the typed fields; adding a key + saving round-trips.
- Behavior test `connector-editor-ux` step 5: the `discord-additional-config-row` (or new testid) resolves within a bottom Advanced section.
- Suites: browser connector-editor subset green.

## Implementation Guidance

1. Move the Additional Config block (`connector-form-discord.js:253-277`) out of its current inline position to a dedicated bottom section — either a new `editor-section` ("Advanced") appended last, or relocate within the existing tab structure so it renders below the typed fields. Keep the `renderConfigKvTable(account)` mount + wiring intact.
2. Frame it: clear "Advanced" heading; de-emphasize (collapsed disclosure or quiet styling). Don't build new components — reuse existing section/disclosure primitives.
3. Preserve/relocate the `discord-additional-config-row` testid (or add `connector-advanced-section`) for the behavior test.
4. Update browser tests asserting the old placement.

## Edge Cases

- **Save round-trip:** ensure the relocated kv-table's inputs are still collected by `collectFormData`/the save handler (it resolves by testid/selector — confirm the move doesn't orphan the inputs).
- **Don't change the kv-table component** itself — relocation/framing only.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` (`:253-277`) — relocate the Additional Config block to a bottom Advanced section.
- (possibly `connector-editor.js` if the section mount is orchestrated there.)
- `tests/…` — browser tests updated for the new placement.

---

## Post-Completion Checklist
- [x] All acceptance criteria verified
- [x] Tests passing (browser; no backend change)
- [x] Flight log updated; leg status `landed` (→ `completed` at editor-cluster commit)
- [x] Commit deferred to editor-cluster batch (after the `connector-editor-ux` behavior test)
