# Leg: loop-carveout-and-enabled

**Status**: completed
**Flight**: [Discord Client](../flight.md)

## Objective

Implement the two hard-to-reverse changes in isolation: the mission-amended send-tool visibility carve-out in the agent loop (DD-5, mission Resolved Question 8) and the `enabled` connector config key with its four lifecycle touch points plus the Studio checkbox (DD-6, mission Resolved Question 9).

## Context

- **The agent loop is frozen except this carve-out.** Mission constraint (amended 2026-09-01 by the mission owner): Flight 3 restores a MINIMAL baseline-visibility carve-out — the send tool's schema visible from session start when enabled for the agent; every other part of `agent/core.py` / `agent/factory.py` stays frozen. If the carve-out can't be expressed without touching more of the loop, STOP — that is a mission-owner conversation, not an implementation call (flight Adaptation Criteria).
- DD-5's settled mechanism (two flight-level Architect cycles): SEED the containers, don't append per-call. The factory already builds `loaded_schemas`/`loaded_tool_names` and passes them to `Agent(...)` (`factory.py:324-325`, `:403-404`); `_on_search_match` (`factory.py:328-338`) dedups by name against the same containers, so a pre-seeded send tool is automatically NOT duplicated by a later `search_tools` hit. `Agent._compute_visible_schemas` (`core.py:202`) returns `[SEARCH_TOOLS_SCHEMA, CONTINUE_SCHEMA] + self._loaded_schemas` — seeding the container is the entire visibility change.
- `Agent.reset()` (`core.py:646-647`) clears both containers **in place** (`.clear()`, never re-assignment — the stub search tools hold closure references to the same objects). It has no memory of any seed, so `__init__` must capture the seed on instance state and `reset()` must re-extend the containers in place from it.
- "Enabled for the agent" is already computed: a tool is registered iff it survives `tool.name not in disabled_names and config.is_tool_enabled(tool.name)` (`factory.py:377`, both the built-in and MCP loops). The seed condition is therefore: after tool registration, the registry contains `SEND_TO_PLATFORM_CHANNEL_TOOL_NAME` (`the_one/tools/connector_send.py:26`, value `"send_to_platform_channel"`).
- DD-6: `enabled` as a config key, default `true`, absent key = enabled, NO migration. The validator's allowed-set is at `db/models.py:172` (`{"default_agent", "channel_map", "allowlist", "always_listen"}`).
- Lifecycle call sites (leg 1 tree): `manager.start_all` (`manager.py:101-103`) starts every row unconditionally; `create_connector` starts on create (`api.py:2806-2808`); `update_connector` unconditionally stop+starts on every PUT (`api.py:2864-2867`); `test_connector`'s docstring currently notes "there is no `enabled` gate to check" (`api.py:2898`) — that note is superseded by this leg. **Keep `manager.start()` itself dumb** — the skip logic belongs to `start_all` and the API call sites (DD-6 assigns it there; `start()`'s contract is used by unit tests constructing in-memory accounts).
- Studio form: `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` (469 lines). Config keys are written sparsely — only when non-default (`:403-410` writes `default_agent`/`channel_map`/`always_listen` only when non-empty). The checkbox should follow: checked (default) → key absent; unchecked → `enabled: false`.
- JS budget: ≤50 lines delta this flight (~675 of 1,000 used). Python: mission connector running total 1,772 of 3,000 after leg 1.

## Inputs

- Leg 1's tree (uncommitted, on `flight/03-discord-client`): Discord subpackage registered in production, suite green at 3,711 passed.
- `the_one/agent/core.py` — `__init__` container params (`:170-171`, `:188-191`), `_compute_visible_schemas` (`:193-202`), `reset()` clear (`:646-647`).
- `the_one/agent/factory.py` — container construction + `_on_search_match` + `Agent(...)` kwargs (`:324-338`, `:398-405`).
- Existing pin tests that MUST NOT change behavior: the `tag_post_step_visibility` literals and `test_mcp_pool`'s lifespan-order test (flight DD-5 states both unaffected); `tests/test_agent_visibility_filter.py`, `tests/test_factory.py` visibility/filter suites.

## Outputs

- `the_one/agent/factory.py` — seed block after tool registration (the ONLY factory change).
- `the_one/agent/core.py` — `__init__` captures the seed; `reset()` re-seeds in place (the ONLY core changes).
- `the_one/db/models.py` — `enabled` in the validator's allowed set + bool shape check.
- `the_one/connectors/manager.py` — `start_all` skips disabled rows.
- `the_one/interfaces/web/api.py` — create honors `enabled`; PUT enable/disable transitions; doctor reports disabled distinctly.
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` — enabled checkbox.
- New/extended unit tests (locations at implementer's discretion; suggested: extend `tests/test_agent_visibility_filter.py` and/or `tests/test_factory.py` for the carve-out; `tests/test_connectors_api.py`-adjacent files for `enabled`).

## Acceptance Criteria

**Carve-out (DD-5) — the five pin tests:**

- [x] **AC-1 Present/absent**: when `send_to_platform_channel` is enabled for the agent (operator + per-agent filters both pass), `_compute_visible_schemas()` includes its schema from the FIRST iteration; when disabled at either level, it is absent. Unit-asserted through `AgentFactory.create()` (the real seed path, not hand-built containers).
- [x] **AC-2 Baseline otherwise unchanged**: with the send tool disabled, the visible set is exactly `[SEARCH_TOOLS_SCHEMA, CONTINUE_SCHEMA]` — no other schema leaks in. With it enabled, the visible set is exactly those two plus the send tool.
- [x] **AC-3 No-search-needed (live-shaped)**: a factory-built agent's first LLM call carries the send-tool schema in `tools=` without any `search_tools` invocation — asserted by capturing the schemas passed to a mock provider on step 1.
- [x] **AC-4 No duplication on search match**: after seeding, a `search_tools` call whose results include `send_to_platform_channel` does NOT produce a duplicate entry in the visible set (`_on_search_match`'s name-set dedup covers the seed because seed names are in `loaded_tool_names`). Asserted on both the schema list length and the name set.
- [x] **AC-5 Reset survival**: after `Agent.reset()`, the carve-out reappears when enabled and stays absent when disabled; the re-seed mutates the ORIGINAL container objects in place (test asserts object identity is preserved across reset — the closure-capture invariant).

**Enabled key (DD-6) — one criterion per touch point:**

- [x] **AC-6 Validator**: `_validate_connector_config` accepts `enabled` as a bool (rejects non-bool); absent key validates as before; existing configs unaffected.
- [x] **AC-7 start_all skips disabled**: a row with `config.enabled == false` gets no listener at boot; enabled and absent-key rows start. Unit-asserted at manager level.
- [x] **AC-8 API transitions — branch on the NEW effective enabled value, never on "did it change"** (design review 2026-09-01, high): new `enabled` effective `true` → today's unconditional stop+start (covers enabled→enabled config edits AND disabled→enabled); new effective `false` → `stop` only, NEVER `start` (covers enabled→disabled AND disabled→disabled). Create with `enabled: false` does NOT start a listener. Unit-asserted per transition, INCLUDING the trap case: a PUT to an already-disabled connector changing an unrelated field (e.g. `default_agent`) must not start a listener. **Trap-case payload shape**: the test PUT must be a FULL current-config resend (existing config incl. `enabled: false`, with only the unrelated field changed) — the endpoint's merge is a shallow top-level `dict.update()` (`api.py:2844-2847`), so a partial `{"config": {...}}` body would silently drop `enabled: false` and test nothing; the full-resend shape mirrors the real Studio client, whose `collectPayload()` always sends the entire form state.
- [x] **AC-9 Doctor distinct state**: `test_connector` on a disabled connector still runs the plugin doctor (diagnosis, not traffic) but the response distinctly marks the connector disabled (shape at implementer's discretion — a top-level field the UI can read; update the `api.py:2898` docstring note it supersedes). Unit-asserted.
- [x] **AC-10 Studio checkbox**: connector-editor.js renders an Enabled checkbox (default checked); unchecked saves `enabled: false`, checked omits the key (sparse-config pattern); editing a disabled connector shows it unchecked. JS delta ≤50 lines. Verified by the studio browser lane.

**Guard rails:**

- [x] **AC-11 Frozen-loop guarantee**: `git diff the_one/agent/` shows changes ONLY in the seed-capture/`reset()` re-seed lines of `core.py` and the seed block of `factory.py`; the `tag_post_step_visibility` pin literals and `test_mcp_pool` lifespan-order test pass unmodified.
- [x] **AC-12 Suite green**: `make test-unit` passes; `scripts/run-tests.sh --lane studio` green (the checkbox touches the studio surface).

## Verification Steps

- AC-1..AC-5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_agent_visibility_filter.py tests/test_factory.py <new files> -x --timeout 30` — foreground.
- AC-6..AC-9: scoped run of the touched connector/api test files, foreground.
- AC-10: `bash scripts/run-tests.sh --lane studio` (browser lane; needs `pytest -m browser` semantics per project docs), foreground.
- AC-11: `git diff --stat the_one/agent/` inspected and quoted in the flight-log entry.
- AC-12: `make test-unit` once at leg end, foreground, timeout up to 600000 ms.

## Implementation Guidance

1. **Factory seed block** (after the MCP attach loop, before `Agent(...)`): check membership via `SEND_TO_PLATFORM_CHANNEL_TOOL_NAME in registry.tool_names` (the property at `tools/base.py:199-201`) — do NOT use `registry.get(...)`, which raises `KeyError` on a filtered-out tool (design review: the disabled path AC-1 pins would crash the factory otherwise). When present, resolve via `registry.get(name)` (safe now — existence just confirmed) and append `tool.to_schema()` (the same schema source `SearchTools` uses via `registry.all_schemas()`, keeping AC-4's dedup comparison apples-to-apples — never a hand-built dict) to `loaded_schemas`, and the name to `loaded_tool_names`. Import the name constant from `the_one.tools.connector_send` — no string literal.
2. **Core seed capture**: `__init__` stores e.g. `self._seed_schemas = list(loaded_schemas)` / `self._seed_tool_names = set(loaded_tool_names)` (copies — the live containers mutate). `reset()` after the two `.clear()` calls: `self._loaded_schemas.extend(self._seed_schemas)`; `self._loaded_tool_names.update(self._seed_tool_names)`. In-place only; keep the existing comment's closure-capture warning intact and extend it to mention the seed.
3. **Validator**: add `"enabled"` to the allowed set + an `isinstance(value["enabled"], bool)` check mirroring the `default_agent` shape check.
4. **start_all**: skip rows where `account.config.get("enabled", True) is False` — one guard line; `start()` untouched.
5. **API**: create — wrap the existing `manager.start(...)` in the enabled guard. PUT — compute the NEW row's effective enabled only and branch on it (AC-8): `true` → today's stop+start; `false` → `stop` only. Doctor — add the disabled marker to the response and fix the stale docstring note.
6. **JS checkbox**: no boolean-field helper exists yet in connector-editor.js — add one alongside `_select`/`_textarea`; wire into the save path's sparse-config block at `:403-410`. **Checked-state trap**: render checked from `config.enabled !== false`, never a truthy check (`!!config.enabled` is falsy for the absent-key legacy case and would invert the default). **Save-path trap**: the generic `field(name)` reader returns `el.value` (useless for a checkbox) — read `.checked` explicitly. Also update the stale top-of-file comment (`connector-editor.js:21-26`, "there is no persisted 'enabled' field... PUT unconditionally restarts the listener") which this leg falsifies — the JS parallel of the superseded `api.py:2898` docstring note.
7. **No new Agent-invalidation path needed** (design review, verified): agents rebuild fresh via `factory.create()` on every WS session rejoin (`app.py` `_restore_session`, the existing session-bound freshness contract) — a toggled tool state reaches the next session naturally.
8. **Test-run discipline**: foreground only, explicit timeouts (up to 600000 ms), never background, never end turn mid-run; `uv sync` always with `--extra dev`; scoped iterations, full suite once at leg end.

## Edge Cases

- **Disable-while-backing-off**: PUT disable during a backoff loop must stop the task cleanly (existing `stop()` cancel semantics — verify, don't reimplement).
- **Rotation restart on a disabled connector**: the rotation hook restarts `listener_ids()` — a disabled connector has no listener, so it stays down after rotation (correct; note in a test or comment).
- **Doctor on a disabled Discord connector with a stale failure marker**: disabled never connects, so no marker is set; but a connector disabled AFTER a permanent failure retains the plugin-side marker — doctor should report both facts (disabled + last failure), not mask one with the other.
- **Seed with the send tool enabled but manager absent** (no connector configured): the schema is still visible — the tool itself returns its existing "not authorized / no manager" error on call. That is Flight 2's authorization behavior, not this leg's concern; do NOT add visibility coupling to connector rows.
- **`enabled: true` explicitly present**: valid, means enabled (not just absent-key).
- **JS editing legacy rows**: config without the key renders checked.

## Files Affected

- `the_one/agent/factory.py`, `the_one/agent/core.py` — carve-out (ONLY the named lines)
- `the_one/db/models.py` — validator
- `the_one/connectors/manager.py` — `start_all` guard
- `the_one/interfaces/web/api.py` — create/PUT/doctor
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` — checkbox
- Tests: extended visibility/factory suites + connector api/manager suites

## Citation Audit (2026-09-01)

Verified against the leg-1 working tree (drift repaired per design review): `factory.py:324-325` container construction, `:327-337` `_on_search_match` dedup, `:378` (built-in loop) + `:389` (MCP loop) enable filter, `:398-405` `Agent(...)` kwargs; `tools/base.py:191-194` `ToolRegistry.get()` raises `KeyError`, `:199-201` `tool_names` property; `core.py:170-171`/`:188-191` `__init__` params, `:193-202` `_compute_visible_schemas`, `:646-647` `reset()` in-place clear + closure-capture comment; `connector_send.py:26` `SEND_TO_PLATFORM_CHANNEL_TOOL_NAME = "send_to_platform_channel"`; `db/models.py:172` allowed-set; `manager.py:101-103` `start_all`; `api.py:2806-2808` create-start, `:2864-2867` PUT stop+start, `:2892-2900` doctor + superseded docstring note; `connector-editor.js:403-410` sparse-config save. All live.

---

## Post-Completion Checklist

**Flight-end commit model — do NOT commit and do NOT signal `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit` + studio lane, foreground)
- [x] Flight log updated (include the `git diff --stat the_one/agent/` quote and JS line delta)
- [ ] Leg status set to `landed`
- [ ] Signal `[HANDOFF:review-needed]`
