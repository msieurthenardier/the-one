# Leg: intents-ux

**Status**: completed
**Flight**: [Daily-driver validation gate](../flight.md)
**Type**: injected (UI subtraction + small backend) — L3 once-over Leg B. **Ships with Leg A** (reuses A's connect-error surface). Visual acceptance: `connector-editor-ux` step 4.

## Objective

Delete the three operator-facing "Receive messages from" intent checkboxes; the-one **always requests all three gateway intents** (message_content, members, guilds). The removed escape hatch (uncheck to dodge `PrivilegedIntentsRequired`) is replaced by Leg A's actionable connect-error (status = Error → "enable privileged intents in the Developer Portal" + link).

## Context

- Operator decision (subtractive): a knob whose only correct position is "all on" is a trap. The three intents are effectively mandatory for a working bot; unchecking Message content silently half-breaks it. `connector-form-discord.js:170-196` (`_renderRuntimeConfigBody`) renders the `discord-intents-row` + the 3 checkboxes (`discord-intent-message_content|members|guilds`).
- Backend: `_discord.py:832` builds `intents = discord.Intents.default()` then applies `account.config["intents"]`. Message content + members are **privileged** → must be enabled in the Discord Developer Portal too; requesting one not enabled there → `PrivilegedIntentsRequired` (`_discord.py:1308`).
- **Leg A already wired** `_map_connect_error` (PrivilegedIntentsRequired → portal link) into the `GET …/status` endpoint + live status. B relies on that surface — no new error UI.
- **Ship-together with A:** removing the checkboxes removes the only in-app workaround, so the actionable error MUST be present (it is, via A).

## Resolved at design review (implement to these)

- **Remove ALL intent code, not just the checkboxes** (`connector-form-discord.js`): the render block (`:172-199`), the `collect()` intents block (`:375-387`), the `snapshot()` intents block (`:434-437`), and the `wireEvents()` intent listeners (`:557-559`). Leaving `collect()`/`snapshot()` in place would keep re-emitting `config.intents` for accounts that had the key (`_readIntentChecked` falls back to True), contradicting "field inert." Remove all four.
- **Two backend connect paths** must force always-on, not one: `connect()` `_discord.py:832-858` AND `_probe_gateway_connect()` `_discord.py:1684-1705` (the doctor/Validate probe). Replace the config-driven `intents_cfg.get(...)` lines with `intents.message_content = intents.members = intents.guilds = True` in both; delete the now-dead message_content-disabled warning (`:847-858`). (Set all 3 explicitly — the test stub's `Intents.default()` has `guilds=False`.)
- **Tests:** REWRITE (don't just delete) `test_connectors_discord.py::test_intents_from_config_honored` (`:483`) + `::test_probe_gateway_intents_from_config_honored` (`:510`) to assert all-3-True **regardless of** `config["intents"]`. REMOVE the form intent-toggle browser tests (`test_flow_studio_connector_discord_form.py` `:83`, `:120`, `:200`); REFRAME `test_flow_studio_connector_invite_section.py:166` (URL stable without a toggle). Keep `:136`/`:169` (no-intents-key round-trip).
- **B↔C coordination:** C also edits `collect()` (to add kv-table collection). Implement B first; C's implementer reads B's diff before touching `collect()` so B's intent-removal isn't clobbered.

## Acceptance Criteria

- [x] **The 3 intent checkboxes are removed** from the connector editor (`_renderRuntimeConfigBody`, `connector-form-discord.js:170-196`). No operator-facing intent toggles remain. (Behavior test `connector-editor-ux` step 4: the `discord-intent-*` checkboxes are absent.)
- [x] **The-one always requests all three intents at connect** — `message_content`, `members`, `guilds` are forced True regardless of `account.config["intents"]` (`_discord.py:832`). A unit test asserts that even with `config["intents"]` disabling one, the constructed `discord.Intents` has all three True.
- [x] **`config["intents"]` field kept for back-compat but inert** (no migration): the connect path no longer lets it *disable* an intent. (Decision: keep the field defaulted/ignored rather than a migration to remove it.)
- [x] **PrivilegedIntentsRequired surfaces via A's error path** — when an always-requested privileged intent isn't portal-enabled, the connect fails and the live status (Leg A) shows the actionable portal-link message. Verified `_map_connect_error` covers it (direct + as-cause, tested in `test_connector_status_endpoint.py`).
- [x] No regression: browser tests asserting the intent row are updated/removed; full backend + browser suites green.

## Verification Steps

- Backend: unit test — build intents with `config["intents"]={"message_content": False}` → constructed intents still have message_content True (always-on).
- Frontend: the editor renders no `discord-intents-row` / `discord-intent-*` checkboxes.
- Error path: a stubbed `PrivilegedIntentsRequired` connect → `/status` returns `state=error` + the portal `last_error_link` (A's mapping).
- Suites: backend (`docker exec the-one pytest …`), browser connector-editor subset.

## Implementation Guidance

1. **Backend (`_discord.py:832`):** after `intents = discord.Intents.default()`, force `intents.message_content = intents.members = intents.guilds = True` and stop applying `config["intents"]` disables (or apply only enables — net: the 3 are always on). Keep the existing `message_content`-disabled warning path dead/removed since it can't trigger now.
2. **Frontend:** remove the `discord-intents-row` block (`connector-form-discord.js:170-196`) from `_renderRuntimeConfigBody`; remove the now-unused intent-axis constants + the "Receive messages from:" label. Leave the rest of the runtime-config body (presence etc.) intact.
3. **Confirm A's error mapping** handles `PrivilegedIntentsRequired` (it does) — no new error UI in B.
4. Tests: backend always-on intents; browser intent-row-absent (update `test_flow_studio_connector_*` that assert intent checkboxes).

## Edge Cases

- **A connector whose `config["intents"]` currently disables an intent:** after B it's ignored — the bot requests all 3 on next connect. If that triggers `PrivilegedIntentsRequired` (portal not enabled), A's status surfaces the actionable error. This is the intended migration of the escape hatch from "uncheck" to "enable in portal."
- **Don't break the runtime-config body layout** when removing the intent row.

## Files Affected

- `the_one/connectors/_discord.py` (~`:832`) — always-on intents.
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` (`:170-196`) — remove the intent checkbox row.
- `tests/…` — backend always-on intents test; browser tests updated to assert no intent row.

---

## Post-Completion Checklist
- [x] All acceptance criteria verified
- [x] Tests passing (backend + browser)
- [x] Flight log updated; leg status `landed` (→ `completed` at editor-cluster commit)
- [x] Ships with A — verified PrivilegedIntentsRequired portal error covered by A's `_map_connect_error`
- [x] Commit deferred to editor-cluster batch (after the `connector-editor-ux` behavior test)
