# Leg: rich-visuals-switch

**Status**: completed
**Flight**: [Charts in Chat](../flight.md)

## Objective
Every agent gets a stored `rich_visuals` setting, on by default for new and existing agents. It is shown and edited as a "Rich visuals" switch in the agent editor's General tab, Behavior section, and saved with the form. The chat drawer shows it as "Rich visuals: On/Off". This leg does not change the prompt; leg 4 makes the flag reach it.

## Context
- Flight decision **DD11** (all of it); approved mockup board 6 (the switch inside Behavior, with its hint, and the drawer line).
- Hint text in this flight: "Tell this agent it can answer with charts. When it's off, the agent isn't told, but any chart in its replies is still shown."
- The pattern to follow is `notes_enabled` (schema v43, repository, the API preserve). Unlike Notes, this switch is a **form field** saved by the General tab's Save, not an immediate-post toggle.
- **When a change takes effect.** Leg 3 reads the factory and session code and records the exact moment (the next turn, or the next chat) in the flight log. Leg 4 pins it in a test, because the flag only reaches the prompt there.
- Legs 1 and 2 are chart rendering; this leg is independent of them except for sharing the tree.

## Inputs
- Schema at v51 (`the_one/db/schema.py:18`). `AgentConfig` in `the_one/agent/config.py` (operator booleans at `:153-168`, `extra: "ignore"`).
- `the_one/db/repositories.py` agent `save` (`:281`, `:300`, `:319`) and `_row_to_config` (`:542`).
- `the_one/interfaces/web/api.py` `create_agent` (`:1434`) and `update_agent` (`:1493`; the `notes_enabled` preserve at `:1545-1546`).
- `general-tab.js` Behavior section (`:192-202`), `defaults()` (`:45-55`), `setAgent` patching (`:334-359`, `max_iterations` at `:353`); `agent-form-data.js` `collectFormData` (`:86-110`).
- `areas/chat/agent-drawer.js` `uses(info.row)` (`:621`), with the Self-configuration group pattern at `:580-591`.

## Outputs
- `AgentConfig.rich_visuals: bool = True`.
- Schema v52 (`CURRENT_VERSION = 52`), a guarded `ALTER TABLE agents ADD COLUMN rich_visuals INTEGER NOT NULL DEFAULT 1`.
- Repository save and read; the API preserve on PUT.
- The General tab switch; the `collectFormData` boolean branch; `defaults()` and `setAgent` treat a missing value as on.
- The drawer group `data-group="rich-visuals"`.
- Tests: migration, repository round trip, API create, update, omit and explicit false, projection exclusion, browser flow.
- A flight-log record of when a change takes effect.

## Acceptance Criteria
- [ ] AC1. `AgentConfig` has `rich_visuals: bool = True`. A config built with no value reads `True`.
- [ ] AC2. **Migration v52.**
  - A database at v51 with existing agents migrates to v52, and every existing agent reads `rich_visuals == True`.
  - A fresh database has the column, `NOT NULL DEFAULT 1`.
  - The migration is guarded: it skips when the column exists, and a second `ensure_schema` is a no-op.
  - `CURRENT_VERSION == 52`.
  - Every `51` version pin in `tests/test_db_migration.py` (eleven, `:5019` to `:6564`, grep for all) and anywhere else under `tests/` is updated, and a v51→v52 test is added in that file's style.
- [ ] AC3. The repository persists and reads the field: a save with `False` reads back `False`, a save with `True` reads back `True`. A stored `False` survives a later save of an unrelated change, a load-then-save round trip (the omit-preserve regression).
- [ ] AC4. **API.**
  - `POST /api/agents` with no `rich_visuals` creates the agent with `true`; with `false`, it creates it with `false`.
  - `PUT /api/agents/{name}` with the key omitted keeps the stored value (both `false` and `true` cases). With `false` or `true`, it sets it.
  - **Validation is lax, matching `notes_enabled` and the other flags** (decided at leg design). Pydantic coerces `"true"`, `"yes"`, `1` and `0` to booleans, which is accepted behaviour. A value it cannot coerce (`"abc"`, `[]`, `{}`, `2`) is a 422 through `_validation_detail` (`api.py:184-190`, `loc ["rich_visuals"]`, no input echo), the same as `max_iterations`, with no new code. A PUT with `"rich_visuals": null` is also a 422: the key is present, so the omit-preserve does not apply. Tests use `"abc"` and `null`.
  - Agent responses (GET list, GET one, POST, PUT) include `rich_visuals`.
- [ ] AC5. `self_configuration/projection.py`'s field list (`:64-73`) does not include `rich_visuals`. A test asserts `get_my_configuration`'s projection lacks the key.
- [ ] AC6. **General tab.**
  - Behavior shows an `App.ui.toggle` labelled "Rich visuals" with the DD11 hint, `dataset: {field: 'rich_visuals'}`, and testid `agent-rich-visuals-toggle` (on the input, or the toggle root, in the toggle's testid convention).
  - It is checked for a new agent and for an agent whose row lacks the field (`rich_visuals !== false`). `setAgent` patches it in place.
  - Flipping it marks the form dirty ("Unsaved changes", Save enabled); flipping it back makes the form clean again (the value model compares snapshots).
  - Save sends `rich_visuals` as a boolean, and after Save the switch reflects the stored value.
- [ ] AC7. `collectFormData` gains a checkbox branch (`f.type === 'checkbox'` → `f.checked`), placed **before** the final `else`. The query at `agent-form-data.js:88` already collects any `input[data-field]`, so without the branch the switch would send the string `"on"`. Design review found no other `data-field` checkbox in the agent editor; the grep confirms it. Dirty tracking compares `JSON.stringify(collectFormData())` with the snapshot (`agent-form-data.js:26-29`), so "flip back is clean" follows from the boolean branch.
- [ ] AC8. **Drawer.**
  - The chat drawer's "What it can use" shows a group `chat-drawer-group[data-group="rich-visuals"]` titled "Rich visuals" with "On" or "Off", read from `info.row` (`rich_visuals !== false` is On) with no fetch.
  - It is placed before the Self-configuration group, as on board 6.
  - Grep `tests/` for drawer group counts and label lists and update any pins (squawk 0334).
- [ ] AC9. **Timing recorded.** The flight log states when a change to the switch takes effect for a running chat: the next turn, the next chat, or after the agent is rebuilt. It cites the factory or session code that decides it (for example where an `Agent` is built or cached per session, and what invalidates it on an agent save). No test is written for it here; leg 4 pins it.
- [ ] AC10. Browser flow tests (`tests/browser/test_flow_agent_rich_visuals.py`, `agents` lane by default; it must not match the `agent-tabs` globs):
  1. A new agent's switch is on.
  2. Toggle off: dirty; Save; reload; still off; the drawer of a chat with that agent shows Off.
  3. Toggle on and back off before saving: the form returns to clean.
  4. An agent seeded through the API with `rich_visuals` omitted shows On.
- [ ] AC11. **Gate.**
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes.
  - `THE_ONE_TEST_NETNS=1` lanes `agents` (the General form, the PUT shapes) and `chats` (the drawer) pass, plus any lane whose tests a grep shows asserting on the agent response shape or drawer groups.
  - The static guards pass, and `ruff` is clean.
  - CLAUDE.md gets one sentence on the switch near the agent editor paragraphs. `the_one/agents.md` documents the field next to `notes_enabled`.

## Verification Steps
- AC1-AC5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_migration.py tests/<the agent repository and API test files> -x --timeout 60` (find the files that test `notes_enabled` and add beside them).
- AC6-AC8, AC10: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_flow_agent_rich_visuals.py -m browser -x --timeout 60`.
- AC9: read the flight-log entry and its citations.
- AC11: `THE_ONE_TEST_NETNS=1 make test-unit`; `--lane agents`; `--lane chats`.

## Implementation Guidance
1. **Backend first.**
   - Add the model field.
   - Add the v52 step in `db/schema.py`, after the v51 block (`:3284-3318`), in its guarded `PRAGMA table_info(agents)` style, and bump `CURRENT_VERSION`.
   - Repository: add the column to `save`'s INSERT column list, its `ON CONFLICT ... DO UPDATE SET` list and its params (`:281`, `:300`, `:319`), and `bool(row["rich_visuals"])` in `_row_to_config` (`:542`).
   - API: in `update_agent`, `if "rich_visuals" not in data: data["rich_visuals"] = existing.rich_visuals` beside the `notes_enabled` preserve.
   - Grep `tests/` for `notes_enabled` to find every test that pins the agent field set or a response shape (exact-dict assertions, field lists, export fixtures) and add `rich_visuals` where the shape is pinned.
2. **Migration tests:** grep `tests/` for `CURRENT_VERSION`, `== 51`, `51)` and `"51"` and update each, then add the v51→v52 test.
3. **General tab.**
   - `defaults()` gains `rich_visuals: true`.
   - Build the toggle with `App.ui.toggle({label: 'Rich visuals', hint: ..., checked: cfg.rich_visuals !== false, dataset: {field: 'rich_visuals'}, testid: 'agent-rich-visuals-toggle'})`.
     - `testid` and `dataset` both land on the native `input[role=switch]` (`js/ui/choice.js:10-20`, `:95-110`), so `collectFormData` finds it and tests locate the input by `[data-testid="agent-rich-visuals-toggle"]`, not `.ui-toggle`.
     - `setChecked` is silent, so wire dirty tracking with `own(tg.control)`. `own` (`general-tab.js:63-68`) adds the `change` listener and sets `_dirtyWired`, so the picker sweep skips it.
   - Keep the controller in a variable at the top level of `renderGeneralTab`, built before the initial `setAgent` call (`general-tab.js:~359`), and append its `el` to the Behavior section's children.
   - In `setAgent`, call `setChecked(c.rich_visuals !== false)`. Don't rely on `defaults()` alone; `!== false` covers both the missing and the create case.
   - In `collectFormData`, read `f.checked` for checkboxes.
4. **Drawer:** add the group in `uses(row)` before `selfBox`, with the same element pattern (`chat-drawer-group`, `h4.chat-drawer-group-label`, `p.chat-drawer-value`).
5. **Timing:** read where chat sessions get their `Agent` (the factory's callers in `the_one/interfaces/web/app.py` and `the_one/sessions/`) and what an agent PUT invalidates. Record the finding (AC9). The hypothesis to check: if the factory builds the `Agent` per session join rather than per turn, a change applies at the next chat or rejoin.
6. **Migration test style:** model the v52 test on `TestSchemaV51`'s replay (drop the column, delete the `schema_version` rows, run `ensure_schema` twice). Assert `PRAGMA table_info` gives `notnull=1` and `dflt_value == "1"`, like the `routines_require_approval` test near `tests/test_db_migration.py:5902`. Some of the eleven pins read `== 51 == CURRENT_VERSION`; update both halves. Model the projection test on `tests/test_prompt_layers.py:387` (`test_get_my_configuration_omits_notes_enabled`). Run `tests/test_run_tests_lanes.py` as part of the gate.

## Edge Cases
- **The `default` agent with no stored row:** the model default is `True`; the drawer and editor read missing as on.
- **An agent renamed:** the column moves with the row (`ON UPDATE CASCADE` is irrelevant here, since it is a column), and the existing rename path keeps all columns.
- **A cached agents-store row from before the migration** (the browser's `App.store` holding a row without the field until refetch): missing reads as on.
- **Old exports or agent JSON fixtures without the field:** `extra: "ignore"` plus the default means they load as on.

## Files Affected
- `the_one/agent/config.py`, `the_one/db/schema.py`, `the_one/db/repositories.py`, `the_one/interfaces/web/api.py`
- `the_one/interfaces/web/static/js/areas/studio/general-tab.js`, `.../studio/agent-form-data.js`, `.../chat/agent-drawer.js`
- `tests/test_db_migration.py` and the agent repository and API tests, a projection test
- `tests/browser/test_flow_agent_rich_visuals.py` (new)
- `CLAUDE.md`, `the_one/agents.md`, the flight log

## Citation Audit
Verified at `293a81d2` (leg 1 does not touch these files; `git status` after leg 1 confirms it):
- `the_one/db/schema.py:18`, `:3284-3318` — `CURRENT_VERSION = 51`; guarded ALTER pattern - verified (flight design, Architect re-check)
- `the_one/db/repositories.py:281`, `:300`, `:319`, `:542` - verified (flight design)
- `the_one/interfaces/web/api.py:1434` `create_agent`, `:1493` `update_agent`, `:1545-1546` the `notes_enabled` preserve - verified
- `general-tab.js:192-202` — Behavior section built from `numberInput` fields with `ui.section({title: 'Behavior', children: [...]})` - verified
- `general-tab.js:353` — `setAgent` patches `iterationsInput.value` - verified
- `agent-form-data.js:86-110` — `collectFormData` reads `input[data-field]`, branches on `max_iterations`, `chat_history_retention_days` and `provider_config_id`, else `f.value` - verified
- `chat/agent-drawer.js:580-591` (Self-configuration group pattern), `:621` (`content.appendChild(uses(info.row))`) - verified
- `self_configuration/projection.py:64-73` - verified (flight design)
- `tests/test_db_migration.py` `51` pins, eleven sites from `:5019` to `:6564` - verified (Architect, cycle 2)
