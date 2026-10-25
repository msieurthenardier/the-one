# Leg: connection-check-record

**Status**: ready
**Flight**: [The MCP server editor on the library](../flight.md)

## Objective
Make the server record the outcome of every Studio connection check of a saved MCP server (`_cache.last_check`), merged into `_cache` without losing any other key. Add one client-side derivation of a server's connection state, `App.usage.mcpState`, which the editor (leg 08b) and the Library list (leg 11) both read. The client sends a Test body only when the form is dirty, and refreshes its MCP list after every outcome.

## Context
- **Flight decision:** DD6, as reworked at Architect cycles 1 and 2:
  - **one write point**, a wrapper whose inner function returns `(result, recordable)`;
  - **`merge_cache`**, a config-only, merging write that does not bump `updated_at`;
  - **only a body-less Test of the saved server is recorded**, and the client sends a body only when dirty;
  - **both Studio callers record**: the editor's Test and the agent MCPs tab's tools load;
  - **the inverted pin**, `tests/test_mcp_stdio_test_connect.py:275` ("No cache should land on a failure"), renamed and inverted, never deleted;
  - **the precedence of `mcpState`**, verbatim (corrected at the leg's design review), where `lc` is `_cache.last_check` (or null):
    1. `signin` when `!has_access_token && (oauth_active || lc?.status === 'auth_required')`;
    2. `error` when `lc?.status === 'error'`;
    3. `connected` when `Array.isArray(_cache.tools)`, which is reached only when `lc` is null, `ok`, or an `auth_required` superseded by a token;
    4. `none` otherwise.

    So a stale `auth_required` with a token and cached tools reads `connected`. `checkedAt` is `lc.at`, falling back to `_cache.last_updated`, **in seconds** (legs 08b and 11 multiply by 1000);
  - **the two posture helpers** move onto `merge_cache`.
- **The route** (`the_one/interfaces/web/api.py::test_mcp_connection`, `:3723`):
  - 404 when the source is missing;
  - an optional body (`{type, config, secrets}`) overrides the saved source;
  - `override_applied` (`:3825`) compares type and config, without `_cache`;
  - it dispatches to `_build_and_test_stdio_mcp` (stdio) or to the streamable-HTTP phases;
  - about 15 return points, with `{status: "ok"|"auth_required"|"error", …}`.
- **Today's `_cache` writes:** the ok branches (`:3544`, `:3650`, `:3965`, each replacing `_cache` wholesale with tools, capabilities, server info, instructions, meta, protocol version and `last_updated`, and, on one path, `auth_posture`), plus `_persist_oauth_posture` and `_clear_auth_posture` (`:3432-3466`, each a `repo.get` then `repo.update`).
- **The other `_cache` users:**
  - `the_one/mcp/_pool.py:203` (reads `auth_posture`);
  - `the_one/mcp/_tool_provider.py:284` (reads `tools`);
  - `update_mcp_source` pins `_cache` across a PUT (about `:3218-3221`);
  - Reset (`DELETE .../connection`, about `:3393-3420`) drops `_cache`;
  - `create_mcp_source` keeps a client-sent `_cache`, which the browser seeders rely on (`tests/browser/seeders.py:195-201`). That asymmetry is a known squawk candidate, out of scope.
- **The repository:** `MCPSourceRepository.update` (`the_one/db/repositories.py:1210-1226`) rewrites every column and stamps `updated_at`, inside `write_transaction`. Architect cycle 2 confirmed that a config-only re-read and write in one `write_transaction` works (one module-level write lock, one connection), and that nothing reads `updated_at` for MCP sources.
- **The clients:**
  - the editor posts through `mcp-connection-status.js::handleTestConnection` (`formData` becomes the body when given, about `:225-229`) and invalidates only on `ok`;
  - `agent-data.js::fetchMcpSourceTools` (about `:365-390`) posts with no body and invalidates only on `ok`;
  - `tests/test_store_static.py` `INVALIDATION_ROWS` pins the editor's and the agent tab's test-connect rows to `('mcp-sources',)` on the success path.
- **`App.usage`** is in `static/js/store.js`, with `mcpToolCount` at `:176`.

## Inputs
- Batch B2 committed (legs 03-05). Legs 06 and 07 landed, or this leg runs before them: it touches `api.py`, `repositories.py`, `store.js`, `agent-data.js` and `mcp-connection-status.js`'s request and invalidation lines only, with no overlap with legs 06 and 07's field modules.

## Outputs
- **`the_one/db/repositories.py`:** `MCPSourceRepository.merge_cache(source_id, fields: dict, delete: Iterable[str] = ()) -> None`. One `write_transaction`:
  - read `config` for the id (`KeyError` if missing);
  - `config["_cache"] = {**(config.get("_cache") or {}), **fields}`, then remove each key named in `delete`;
  - a `None` value in `fields` is **stored as `null`**, never treated as a delete. The ok payloads carry legitimate `None`s (`server_info`, `instructions`, `meta`);
  - write `config` only. No `updated_at` change, and the other columns are untouched.
- **`the_one/interfaces/web/api.py`:**
  - **The wrapper.** The current body of `test_mcp_connection` becomes `_test_mcp_connection_inner(source_id, request) -> tuple[dict, bool]`. The bool is `recordable`: true only when the request had **no** body and the run was a connection check. It is false at the invalid-JSON and non-object-body returns, and at the "Test only supports streamable-http and stdio" return (a config-shape problem, not a connection check). A missing source still raises 404 before anything is recorded.
    - `recordable` (no body at all) and `record_era` (type or config differs) are deliberately different gates: a dirty body that changes only secrets still records the era but not `last_check`. `agents.md` says so, so nobody unifies them.
    - The DD2 comment at about `api.py:3819-3827` ("the editor sends its form body on every Test …") is updated, because the editor now sends a body only when dirty.
  - **The route** calls the inner function, and when `recordable` and `result["status"]` is one of `ok`, `error` or `auth_required`, it calls `repo.merge_cache(source_id, {"last_check": {"status": …, "at": time.time()}})`, best-effort (an exception is logged at debug and swallowed, like today's cache writes). It then returns `result` unchanged. The 404 still raises before anything is recorded.
  - **The three ok-branch cache writes** (`:3544`, `:3650`, `:3965`) switch to `merge_cache` with their full field set. That drops their `repo.get`/`repo.update` round trip and keeps `last_check` and `auth_posture` automatically.
    - The `:3544` write still sets `auth_posture: "no_auth"`, as today.
    - The stdio write (`:3650`) adds no `auth_posture`, so a stdio source that never had one stays without one (the tests at `test_mcp_stdio_test_connect.py:246, :509` assert this).
    - **Behaviour change, intended:** the Phase A/B ok write (`:3965`) wrote no `auth_posture` and so dropped it on every Phase A ok. Under the merge it keeps an existing `oauth` posture, which the pool reads (`_pool.py:203`). This is recorded in the flight log and `agents.md`.
  - **The posture helpers** call `merge_cache(id, {"auth_posture": "oauth"})` and `merge_cache(id, {}, delete=("auth_posture",))`.
- **`tests/test_mcp_stdio_test_connect.py`:** the test at about `:262-275` is renamed (for example `test_stdio_test_connect_error_records_last_check_only`) and inverted: a failed Test leaves `_cache == {"last_check": {"status": "error", "at": …}}`, and no tools.
- **New unit tests** (in the existing MCP API test files, or a new `tests/test_mcp_last_check.py`):
  - **each outcome recorded:** `ok` (stdio and HTTP), `error`, `auth_required` (the HTTP sign-in path, stubbed as the existing OAuth tests do);
  - **nothing recorded for:** a Test with a body (a clean body too: any body means not the saved server), a 404, an invalid JSON body, a non-object body, and an unsupported type;
  - **key survival:** after an error Test, the earlier `tools`, `server_info`, `capabilities` and `auth_posture` are all still present; after an ok Test, `last_check` is `ok` and `auth_posture` survives;
  - **`updated_at` is unchanged** by `merge_cache`;
  - **the PUT pin:** a PUT after a recorded check keeps `last_check`; **Reset** drops it;
  - **`merge_cache`'s `None`-deletes rule.**
- **`static/js/store.js`:** `App.usage.mcpState(source) -> {state: 'signin'|'error'|'connected'|'none', tools: number|null, checkedAt: number|null}`, with DD6's precedence, beside `mcpToolCount`. The labels ("Sign-in needed", …) are leg 08b's and 11's.
- **The clients:**
  - **the editor:**
    - the dirty check comes **first**. On a clean form `runTest` posts no body and does not call `collectFormData` at all (that call validates and writes `.editor-error`, about `mcp-server-editor.js:564`). On a dirty form it collects and sends, as today;
    - **`rerun` after a sign-in keeps the original decision** (it re-sends the captured `formData` or none). A sign-in started from a dirty form therefore never records `ok`. That is one reason `mcpState`'s rule 3 lets a token supersede a stale `auth_required`;
    - the auto-run after create is clean, so it posts no body and records;
  - **both clients** call `App.store.invalidate('mcp-sources')` on every outcome (`ok`, `error`, `auth_required`), including a result that arrives after the editor is torn down: today's `if (!live && data.status !== 'ok') return;` (about `mcp-connection-status.js:250`) runs the invalidation and `onListStale` before returning. The editor calls `onListStale()` **once** per outcome, never twice (once through the status module and once through the editor callback). `agent-data.js` has no `onListStale`;
  - **`tests/test_store_static.py`:**
    - the editor row (`'/test/connect', fetchOpts)` to `renderToolsListHtml(data.tools)`, inside the ok branch) and the agent row (ending at `return data;`, also inside the ok branch) get new end anchors placed before the `status === 'ok'` check, so they pin the every-outcome invalidation. Name the anchors in the leg's flight-log entry;
    - `test_mcp_list_stale_callback_follows_the_non_save_invalidations` (`:256-273`) still passes, and a new assertion covers the `onListStale` call on error and `auth_required`.
- **Browser tests** for `mcpState`, in a new `tests/browser/test_store_mcp_state.py`, which the `routing` lane's `test_store*` glob picks up: a table over `has_access_token` × `oauth_active` × `last_check` ∈ {none, ok, error, auth_required} × tools cached or not, each row's expected state written out, including the stale-`auth_required`-with-token case (`connected`), a source with no `_cache`, and a pre-flight source (`_cache.tools`, no `last_check`).
- **Docs:** `the_one/agents.md` gets the `last_check` contract (what records it, what does not, the merge rule, "the last connection check from Studio"). `CLAUDE.md` gets nothing (no new route).

## Acceptance Criteria
- [ ] The inverted pin and the new unit tests pass. The old assertion "no `_cache` on a failure" is replaced, never deleted.
- [ ] **No key is lost:** after any sequence of an ok Test, an error Test, a posture write, a PUT and an auth-required Test, the keys `tools`, `server_info`, `capabilities`, `instructions`, `meta`, `protocol_version`, `last_updated` and `auth_posture` survive whenever they were present (tested). Reset drops all of them (tested).
- [ ] **`updated_at` is unchanged** by a recorded check (tested).
- [ ] **Only body-less Tests record** (tested both ways), and the editor sends a body only when dirty: a browser test intercepts the request on a clean and on a dirty form.
- [ ] **Invalidation on every outcome:** a browser test shows that the Library list's MCP row meta refreshes after an error Test. Today it says "Tools not loaded" either way; with leg 11 not yet landed, assert the `mcp-sources` refetch, not the text.
- [ ] **`App.usage.mcpState`** passes every precedence case.
- [ ] **Existing behaviour holds:**
  - `tests/test_mcp_*.py` and `tests/test_oauth_*.py` pass;
  - the lanes `mcp`, `library`, `agents` (the MCPs tab) and `routing` pass;
  - `test_oauth_modal_flow.py` passes;
  - `make test-unit` passes.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_mcp_stdio_test_connect.py tests/test_mcp_last_check.py tests/test_oauth_test_connection_endpoint.py tests/test_store_static.py -q -x --timeout 120` (with the new file name if it differs).
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane routing -x`, then the other lanes, at most 3 at a time.
- `make test-unit` (not alongside the lanes).

## Implementation Guidance
1. **`merge_cache` and its unit tests.**
2. **The inner/wrapper split.** First run the existing test-connect unit tests unchanged against the pure refactor (with no record yet), so the split is proven behaviour-free before recording is added.
3. **Recording**, the ok-branch key carry-over, the posture helpers and the inverted pin; then the survival tests.
4. **`mcpState`** and its browser tests.
5. **The clients:** the body only when dirty; invalidation on every outcome; the store pins.
6. **Docs and the flight log.**

## Edge Cases
- **A Test while a sign-in is pending:** `auth_required` is recorded. When the token lands and the re-POST (no body, clean form) returns ok, `ok` is recorded.
- **Two concurrent Tests:** the last write wins for `last_check`, which is acceptable for a hint.
- **The OAuth token write** (`the_one/mcp/oauth/storage.py:119-132`: `repo.get`, then the secrets mutated, then a whole-row `repo.update`, with an `await` between) can overwrite a `merge_cache` landing in that gap. DD6 accepts this lost-update in writing. An optional unit test interleaving the two documents it.
- **A failing source in the agent MCPs tab** invalidates `mcp-sources` on every expand. Check that this does not cause a refetch loop; it should not, since nothing re-expands on a list change.
- **The agent tab's tools load** records too (DD6), and `agents.md` says so.
- **A recorded check on a source deleted mid-Test:** `merge_cache` raises `KeyError`, and the wrapper swallows it (best-effort).
- **`time.time()`** is seconds, matching `last_updated`. The client multiplies by 1000 where it needs milliseconds.

## Files Affected
- `the_one/db/repositories.py`, `the_one/interfaces/web/api.py`.
- `static/js/store.js`, `static/js/areas/studio/mcp-connection-status.js` (the body rule and invalidation), `mcp-server-editor.js` (passing `formData` only when dirty), `agent-data.js`.
- `tests/test_mcp_stdio_test_connect.py`, a new or extended unit test file, `tests/test_store_static.py`, `tests/browser/test_store_mcp_state.py` (new), and a browser test for the body rule in `test_flow_studio_mcp_editor.py`.
- `the_one/agents.md`; the flight log.

## Citation Audit
- `api.py:3723` (the route), `:3781-3783` (the JSON errors), `:3825` (`override_applied`), `:3432-3466` (the posture helpers), `:3544`, `:3650`, `:3965` (the ok writes), `:3559-3583`, `:3664-3683`, `:4015-4048` (error returns). FD grep at `ebf3ef6` plus the working tree.
- `repositories.py:1166, :1210-1226`. FD read.
- `test_mcp_stdio_test_connect.py:262-275`. FD read. `agent-data.js:365-390`. FD read. `store.js:176`. Grep.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Developer design review, cycle 1 (2026-10-25): approve with changes.** Applied in place:
  - `mcpState`'s predicates written verbatim, with a full test table (H);
  - `recordable` false for an unsupported type and the body errors (M);
  - `rerun` keeps the original body decision, and a clean Test skips `collectFormData` (M);
  - the ok writes through `merge_cache`, with an explicit `delete` parameter instead of `None`-deletes, and the Phase A posture keep stated as intended (M);
  - the DD2 comment, the two gates, the store-pin end anchors, a single `onListStale`, and the invalidation for a torn-down editor (L);
  - the OAuth lost-update edge (L).
  - FD answers: no record for an unsupported type; a torn-down editor still invalidates; `None` is stored, never deleted.

  Clarifications within the design, so there is no second cycle. Status `ready`.
