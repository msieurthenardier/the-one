# Leg: save-and-notices

**Status**: completed
**Flight**: [Agent tool overrides](../flight.md)

## Objective
Refuse a widening or invalid new or changed agent tool override at save time with a 422 on its field, derive the clip notices on every agent response, and make a chat, a routine run or a connector message whose agent cannot be built degrade with a plain reason instead of dropping. Closes squawk 0257.

## Context
- Flight design decisions implemented here: **DD5** (save validation), **DD6** (derived notices) and **DD7's hardening bullets** (the `build_failed` restore with its client half, and the connector catch-all). Read those sections of `../flight.md` in full: they are the spec. Leg 1's flight-log entry lists the resolver helpers this leg builds on.
- **Leg 1 delivered** (`the_one/tools/resolver.py`, uncommitted in this tree): `field_marker`, `baseline_value`, `check_field(schema, field, tool_val, agent_val, *, tool_name=None)` (raises `OverrideWidensError`, `NotImplementedError` for a type mismatch, and lets path canonicalisation errors through; bounds and types are left to `model_validate`), `clip_field`, `combine_field`, `clip_override -> ClipResult(override, changes)` with `ClipChange(field, kind, dropped, effective)`, `resolve(..., *, tool_name=None)`, `NO_HOSTS`, `NarrowAnyWhenEmpty`, `MARKER_NAMES`. The build path already clips, so after leg 1 no override can make a build fail. This leg's failure paths cover every *other* build failure.
- **Leg 1 facts this leg relies on:**
  - An agent `host_allowlist: []` clipped to the app-wide list is kind `narrowed` with `dropped == []`, so it uses DD6's own "was any host" sentence.
  - A `coupled` change is never a notice.
  - Path values in `effective`/`dropped` are the stored strings, not canonical forms (see Deviation below).
- **Decisions carried from leg 1's design review** (flight log, 2026-10-31), binding here:
  1. One server predicate decides whether the agent tab renders a field: it reuses `api.py::_hidden_field_names` and mirrors the client's `allowed()` (a boolean, or a field whose marker is one of `Narrow`, `NarrowSuperset`, `NarrowPrefix`, `Substitute`, `NarrowAnyWhenEmpty`). A test pins it against the client rule.
  2. Notices read `ToolConfigRepository.list()` once per request (for `enabled` and the row), built before `list_agents`' loop.
  3. The off-loop requirement is asserted by patching `asyncio.to_thread`.
  4. The `build_failed` reason is a fixed sentence; the raw exception goes only to the log.
  5. The routine runner words `build_failed` itself with a fixed sentence, so `_RoutineTurnHost.get_or_restore`'s 2-tuple and its test fakes stay as they are.
  6. `socket.js` passes the frame's reason: `setSessionHealth(status, reason)`.
  7. `session-state.js`'s starting path uses `frame.reason` when present.
  8. The new `_restore_session` branch pops `_sessions` like the other degraded branches.
  9. `start_session` for a brand-new chat keeps today's `start_failed` frame.
  10. The memo is a `threading.Lock` around a bounded `OrderedDict`.
- **Deviation from DD6, recorded here:** notice `effective` and `dropped` path entries are the stored strings (for example `~/work`), not canonical absolute paths. Leg 4's "Use narrowed value" stores `effective` as the field's own value, and a canonical form would pin `~` to one absolute home and show the operator's home path where they typed `~`. Both forms check the same containment.
- **Not in this leg:** any UI that shows notices (legs 4 and 5), the impact route (leg 5), the redirect-hop check (leg 3).
- **Baseline:** the flight log's list; leg 1's changes are uncommitted in this tree and are part of the base for this leg.

## Inputs
- `api.py`: `_agent_response` `:208` (sync; `kb_tool_names` precedent); its five call sites `:928` (`list_agents`, a `store.load` per name), `:939` (`get_agent`), `:1087` (`create_agent` from `:1036`), `:1175` (`update_agent` from `:1091`; preserve-on-omit of `tool_overrides` at `:1147-1151`, then `AgentConfig.model_validate`, guards, `store.save`), `:1244` (`rename_agent`); `_hidden_field_names` `:547`; `_validation_detail`; the sortie 06 detail precedent `the_one/naming.py::name_rule_detail`.
- `ToolConfigRepository.list()` (`repositories.py:2456`, rows with `name`, `config`, `enabled`, `merged_config()`); `AgentConfig.is_tool_enabled` (`agent/config.py:160`); the factory's own use of both (`agent/factory.py:401-410`).
- `app.py`: `RestoredSession` `:1576` / `is_degraded` `:1589`; `_restore_session` `:1679` (catches `ProviderNotFoundError`, `ProviderNotConfiguredError`, `AgentNotFoundError`, each popping the cache and returning a degraded status); `_build_session_joined_degraded` `:2024`; the WebSocket `join` `:3336` (no try around the restore); `start_session`'s restore `:3462` (a broad catch sending `start_failed`, then the degraded branch); `POST /api/chat` `:3259-3261`.
- `routines/runner.py:266-273`; `connectors/inbound.py:419`.
- Client: `areas/chat/socket.js:237` (`ctx.setSessionHealth(data.status || 'ok')`); `areas/chat.js::setSessionHealth` `:465-472`; `areas/chat/session-state.js` `DEGRADED_REASONS` `:55-58` and the starting path `:210-219`.
- Squawk `squawks/0257-agent-tool-overrides-not-validated-on-save.md` (open).

## Outputs
- A save-validation function (new module `the_one/tools/override_validation.py`, so `api.py` grows only by its call sites) returning the 422 detail list, called from `create_agent` and `update_agent` after `AgentConfig.model_validate` and before `store.save`.
- A notices function (same module, or `the_one/tools/override_notices.py`) with the memo, and `_agent_response(cfg, kb_tool_names=None, notices=None)` always emitting a `notices` list (empty when none) on all five routes.
- `app.py`: `SESSION_STATUS_BUILD_FAILED = "build_failed"` in `is_degraded`; `_restore_session` catches any other exception from the agent build into it; the degraded frame and `RestoredSession` carry `reason`; `POST /api/chat` returns `{"error": "session_build_failed"}`.
- `routines/runner.py`: a `build_failed` reason. `connectors/inbound.py`: a catch-all that logs the agent name.
- Client: `build_failed` in `DEGRADED_REASONS` (fallback text), `setSessionHealth(status, reason)` showing the reason (set as text) with input disabled, and the starting path using `frame.reason`.
- Tests (below) and squawk 0257's Corrective Action and Verification filled in, status `in-progress` (the Flight Director closes it at the flight commit).

## Acceptance Criteria
- [ ] **AC1 — save 422 shape.** `POST /api/agents` and `PUT /api/agents/{name}` with a widening or invalid new or changed override return 422 and save nothing (read-back unchanged). `detail` is a list of `{"type": "tool_override", "loc": ["tool_overrides", tool, field], "msg": sentence}`, one per failing field, with every failing field reported, not just the first. An unknown tool name in a new or changed entry gives `loc ["tool_overrides", tool]`. A non-dict tool entry keeps today's `AgentConfig` validation 422 (pinned as it is, not reshaped).
- [ ] **AC2 — every failure type.** A test each for:
  - a widening (`OverrideWidensError`) for path, number, bool and host lists;
  - pydantic bounds or type, including squawk 0257's negative timeout;
  - `NotImplementedError` (a type mismatch, such as a string for a list);
  - an unmarked key (`redirect_cap`; the `ValueError` from `field_marker`);
  - a path canonicalisation error (`~nosuchuser`; a NUL byte);
  - a cross-field default > max, attributed to `timeout_seconds_default` when both changed, else to the one that changed.

  Catch order: `ValidationError` before `ValueError`.
- [ ] **AC3 — changed fields only.** On update, only fields new or different from the stored value by JSON-canonical comparison (`json.dumps(v, sort_keys=True)`; `5` ≠ `5.0`, `True` ≠ `1`) are checked. An unchanged stored stale or invalid entry still saves alongside an unrelated change, **including an unchanged stale or out-of-bounds field in the same tool's entry as the changed field** (a test each: a stale path, a negative timeout, `~nosuchuser`). An omitted `tool_overrides` (preserve-on-omit) checks nothing. A list edited while it still holds a stale entry is checked as a whole and refused. On create every field is checked.
- [ ] **AC4 — sentences.** Each `msg` names the tool by its name (as Settings shows it) and the field by its schema `title`, and says where to change the app-wide value, for example "`\\server\share\proj` is outside read_file's app-wide Allowed paths. Add it in Settings › Built-in tools › read_file first." or "Maximum timeout can be at most 120 for shell, the app-wide value." Tests pin one sentence per failure family, exactly. The families are: widening, bounds/type, type mismatch, unmarked key (for example `redirect_cap`: "Maximum redirects can't be changed for one agent; it is set in Settings › Built-in tools › http_request."), path that cannot be read, cross-field default > max, and unknown tool.
- [ ] **AC5 — notices on all five routes.** `GET /api/agents`, `GET /api/agents/{name}`, create, update and rename responses carry `notices` (a list; `[]` when none) of `{"kind": "tool_override_narrowed", "tool", "field", "field_title", "dropped", "effective", "message"}`. The "was any host" case has its own sentence (DD6).
- [ ] **AC6 — notice scope.** A notice is raised only for a `narrowed` or `invalid` change, on a field the server predicate says the tab renders, for a tool enabled for the agent (`is_tool_enabled`) and app-wide (`ToolConfig.enabled`, default enabled when no row). Hidden fields, disabled tools and `coupled` changes raise none. A test pins the predicate against the client's `allowed()` rule over every built-in config field.
- [ ] **AC7 — cost and freshness.** One `ToolConfigRepository.list()` per request (the list route included, counted with a spy); the clip runs inside `asyncio.to_thread` (asserted by patching it); the memo returns a recomputed result when either the override entry or the tool-config row changes, and the cached result otherwise (asserted by counting `clip_override` calls). The memo is bounded.
- [ ] **AC8 — `build_failed` degrade.** With the agent build forced to raise an exception other than the three mapped errors (monkeypatch the factory):
  - a WebSocket `join` of an existing session gets `session_joined` with `status: "build_failed"`, a fixed `reason` sentence and the stored history, and the socket stays open (a second action on it still works);
  - `start_session` with an existing session id gets the degraded frame;
  - `POST /api/chat` returns `{"error": "session_build_failed"}`;
  - the session cache entry is dropped;
  - the exception is logged once with the agent name, and its text is in no frame.
- [ ] **AC9 — routine and connector.** A routine run whose restore is `build_failed` records `failed` with its own fixed reason (not "The chat is no longer available."). Connector inbound logs a non-mapped build exception with the agent name and returns without raising (the turn-tracking context exits cleanly).
- [ ] **AC10 — the client half.** A `chats`-lane browser test shows a joined `build_failed` chat: its banner shows the server's reason, the composer is disabled, and the history renders. A start that lands on `build_failed` with an empty history returns to the pending chat with the reason. The test drives the client by rewriting the real server's `session_joined` reply (status `build_failed`, a `reason`; real history for the join case, `history: []` for the start-from-pending case) through a small local `page.route_web_socket("**/ws", ...)` helper in the test file (no `tests/browser` file uses WebSocket routing yet; `scripts/ui_capture.py:1875-1899` `SocketScript` is the pattern, not an import). It adds no product test seam, because the server half is unit-tested. The file is named `test_flow_chat_*` so it lands in `chats` by default.
- [ ] **AC11 — no regressions.** `THE_ONE_TEST_NETNS=1 make test-unit` shows only the baseline failures. The `chats`, `chats-transcript`, `agents`, `agent-tabs` and `agent-routines` lanes show only baseline failures. ruff check and format are clean, and the static JS guards pass. Any exact-dict pin of the agent response shape gains `notices`.

## Verification Steps
- AC1-AC4: new `tests/test_api_agent_tool_override_validation.py` through the credentialed app-client fixtures (`tests/_credential_helpers.py::auth_headers()`), with the database built from `tests/_schema_template.py`.
- AC5-AC7: new `tests/test_agent_notices.py` (unit over the notices function, and through the five routes).
- AC8-AC9: tests over `_restore_session`, the WebSocket `join` and `start_session` (the existing WebSocket test client patterns in `tests/test_app_*.py` / `tests/test_websocket*.py`), `POST /api/chat`, `routines/runner.py` through its fake host, and `dispatch_inbound`.
- AC10: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/<new file> -x`, and confirm the file lands in the `chats` lane (`bash scripts/run-tests.sh --lane chats --list`).
- AC11: `THE_ONE_TEST_NETNS=1 make test-unit`; the five lanes one at a time through `scripts/run-tests.sh --lane` (never beside the unit tier); `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/`; `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`; `grep -rn '"kb_tool_names"\|tool_overrides' tests/` for exact response-shape pins.

## Implementation Guidance

1. **The render predicate.** `agent_tab_renders(tool_cls, field) -> bool` beside `_hidden_field_names`. If it would need `api.py`, put the predicate in the new module and have `api.py` reuse it, so there is one copy. Pin it with a test that enumerates every built-in config field and compares it with `allowed()`'s rule written out in the test.
2. **Save validation** (`override_validation.py`):
   - **Inputs:**
     - the stored map (`existing.tool_overrides` on update, never the raw body: the preserve-on-omit at `api.py:1147-1151` runs before `model_validate`; `None` on create);
     - the validated incoming map (`cfg.tool_overrides`);
     - the tool-config rows as `{name: row.merged_config()}`, matching `factory.py:401-410` (`{}` when a tool has no row);
     - the tool classes (`_TOOL_CLASSES`).
   - **Skip what has nothing to check.** A tool whose Config is `_EmptyConfig` has no fields to check. Unknown field keys inside a known tool entry stay ignored (`extra="ignore"`); a test pins that no 422 is raised for them.
   - **Changed fields** are computed per tool and per field by JSON-canonical comparison with the stored entry.
   - **For each changed field, in this order, stopping at that field's first failure:**
     1. `field_marker(schema, field)` in its own `try`: a `ValueError` here is the unmarked-key family.
     2. `check_field(schema, field, baseline_value(schema, field, row), value, tool_name=tool)`: an `OverrideWidensError` is a widening; a `NotImplementedError` is a type mismatch; a `RuntimeError`, `OSError` or `ValueError` is the path-canonicalisation family.
     3. Pydantic bounds and types for that field alone, through `TypeAdapter(Annotated[field_info.annotation, *field_info.metadata])`, so `ge`/`le` constraints apply (with the annotation alone, squawk 0257's negative timeout would pass).

     Each failing field gets exactly one detail entry; a type error seen by both step 2 and step 3 is one entry.
   - **Cross-field rules, never re-checking unchanged fields.**
     - Build a candidate entry: the changed fields that passed, plus the unchanged stored fields **passed through `clip_override`** (total, never raises), so an unchanged stale or invalid field can never refuse the save. Strict `resolve` would run `check_field` on every key and raise on an unchanged stale one, which is exactly what AC3 forbids.
     - Then call `resolve(schema, row, candidate, tool_name=tool)` and catch only `ValidationError`. A model-level error (`loc ()`, the default > max rule) is attributed per DD5.
     - An error whose `loc` names a field the agent did not change, which can only come from an invalid app-wide row, is logged and does not refuse the save. The operator's row is out of this sortie's scope, and the build clips around it.
   - Return the detail list. Path canonicalisation blocks, so the routes run the function in `asyncio.to_thread`.
3. **Wire it** into `create_agent` and `update_agent` after the credential-override guard (`reject_surface_credential_overrides`) and before `_check_agent_provider` and, on create, before `store.exists` (so a bad override is a 422 even when the name would also 409); raise `HTTPException(422, detail=...)`. Read the tool-config rows once per request and reuse that read for the notices in the same response.
   - A non-dict tool entry never reaches this function: `AgentConfig.tool_overrides: dict[str, dict[str, Any]] | None` (`agent/config.py:119`) already 422s it through `_validation_detail`. AC1's test pins that existing shape; no new `tool_override` entry is added for it.
4. **Notices:**
   - `compute_notices(cfg, rows) -> list[dict]`; the pure part is memoised on `sha256` of the canonical JSON of (tool name, override entry, the row's `merged_config()`), so no raw secret is a dict key.
   - The scope filter (agent enabled, app-wide enabled, render predicate) is applied outside the memo.
   - Routes read the rows once, then run `asyncio.to_thread(compute_notices_for_many, cfgs, rows)` (one thread hop for the list route).
   - `_agent_response` gains `notices` and always emits the key.
5. **`build_failed`** in `app.py`:
   - The constant, `is_degraded`, and a `reason: str | None = None` field on `RestoredSession`.
   - In `_restore_session`, a final `except Exception` around the agent build (only the build, not the DB read, which keeps its own behaviour). It logs with `logger.exception` naming the agent, pops the cache, and returns `RestoredSession(None, SESSION_STATUS_BUILD_FAILED, db_session, reason=BUILD_FAILED_REASON)`.
   - `_build_session_joined_degraded` adds `"reason": restored.reason` when set.
   - Check the `join` and `start_session` branches handle the new status through `is_degraded` with no other change; add tests either way.
6. **Runner and connector.** The runner gets a `build_failed` branch with its own fixed sentence. In inbound, add `except Exception: logger.exception(... agent_name ...); return` after the three-error catch.
7. **Client:**
   - `DEGRADED_REASONS.build_failed` as a fallback sentence.
   - `setSessionHealth(status, reason)`: for `build_failed`, the banner text is the reason or the fallback, set as text; the other statuses are unchanged.
   - `socket.js:237` passes `data.reason`.
   - The starting path uses `frame.reason || DEGRADED_REASONS[...]`.
   - Grep every other `setSessionHealth(` caller (`session-flow.js:153,208` pass `'ok'`); they need no change.
8. **Squawk 0257:** set `in-progress` when starting step 2. When done, fill in the Corrective Action and Verification.

## Edge Cases
- **A PUT that omits `tool_overrides`** carries the stored map, so nothing is changed and nothing is checked.
- **A PUT with `tool_overrides: null`** clears it, so nothing is checked.
- **A field removed from an entry** returns to inheriting (narrower or equal by construction). It is not checked and not refused.
- **A changed entry for a tool disabled for the agent** is still checked: it applies if the tool is re-enabled.
- **A fixed `BUILD_FAILED_REASON`:** "This chat's agent could not be set up. Check the agent's settings; the app log has the details." It is acceptable-variation wording, one plain sentence each for the chat and the routine.
- **`list_agents` with many agents:** one rows read, one thread hop; the per-agent `store.load` loop is unchanged (not this leg's problem).
- **Notices must not include a tool name the agent's `tool_overrides` carries for a tool removed since:** skip unknown tools.
- **`POST /api/chat` carries only the code** `session_build_failed`, as for the other degraded statuses; the reason sentence is on the WebSocket frame only.
- **The memo key** is a `sha256` of canonical JSON that includes the decrypted `merged_config()`; the key is never logged, and no raw secret is held as a key.

## Files Affected
- New: `the_one/tools/override_validation.py` (and `override_notices.py` if split)
- `the_one/interfaces/web/api.py` — the predicate's home or its reuse, call sites, `_agent_response`
- `the_one/interfaces/web/app.py` — `build_failed`
- `the_one/routines/runner.py`, `the_one/connectors/inbound.py`
- `the_one/interfaces/web/static/js/areas/chat.js`, `areas/chat/socket.js`, `areas/chat/session-state.js`
- Tests: new `tests/test_api_agent_tool_override_validation.py`, `tests/test_agent_notices.py`, a new `chats`-lane browser test, plus additions to the restore, WebSocket, runner and inbound tests
- `squawks/0257-agent-tool-overrides-not-validated-on-save.md`

### Citation Audit
Checked by the Flight Director against the worktree (base `628a97dd` plus leg 1's uncommitted changes), 2026-10-31: `api.py:208,547,928,939,1036,1087,1091,1147-1151,1175,1244`; `agent/factory.py:401-410`; `repositories.py:2456`; `agent/config.py:160`; `app.py:1576,1589,1679,2024,3259-3261,3336,3462`; `routines/runner.py:266-273`; `connectors/inbound.py:419`; `socket.js:237`; `chat.js:465-472`; `session-state.js:55-58,210-219`; `resolver.py` public names from leg 1's report.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
