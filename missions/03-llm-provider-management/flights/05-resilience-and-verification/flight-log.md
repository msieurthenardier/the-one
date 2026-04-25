# Flight Log: Resilience & Verification

**Flight**: [Resilience & Verification](flight.md)

## Summary

Flight in progress. Branch `flight/05-resilience-and-verification` created from `main` at `0005128`. Mission Control orchestrating via `/agentic-workflow` (single review + commit at end of flight, per fast-variant workflow).

---

## Leg Progress

### `key-rotation-atomicity` — landed
- Rewrote `POST /api/encryption/rotate` to commit re-encrypted rows BEFORE persisting the new key file via temp-file + `os.replace`; key file is now the last thing to change.
- Added `Encryptor.install_key(new_key)` and a public `Encryptor.key_path` property; existing `rotate_key()` retained unchanged for non-API callers.
- New failure-injection test (`TestEncryptionRotation.test_rotate_preserves_key_on_db_failure`) patches `aiosqlite.Connection.commit` and asserts key file bytes, cached encryptor decrypt, and on-disk ciphertext are all unchanged on failure.
- Tests: `pytest tests/test_encryption.py -v` (21 passed), `pytest tests/test_provider_api.py::TestEncryptionRotation -v` (4 passed), `pytest -q --ignore=tests/test_tool_registry.py --ignore=workspace/test_agent.py` (318 passed). Two pre-existing collection errors per anomaly above are still scoped to leg 04.
- Ruff `check` and `format --check` clean for the three touched files.

### `session-health-frontend` — landed
- Closed the backend protocol gap: replaced the two hand-rolled `session_joined` dicts in `the_one/interfaces/web/app.py` (the `new_session` action handler and the auto-join fallback) with `_build_session_joined_ok(session)` calls. After this leg, every `session_joined` payload uniformly carries `status`. Verified via `grep -n '"type": "session_joined"' the_one/interfaces/web/app.py` — only the two helper internals (lines 274, 292) match.
- Refactored `bannerEl` semantics in `the_one/interfaces/web/static/js/areas/chat.js`: introduced a dedicated `setupIncomplete` boolean as the SOLE source of truth for "is setup incomplete". `bannerEl` is now purely a DOM reference used in `checkSetupState` (create/remove) and as an insertion anchor in `setSessionHealth` (`bannerEl ? bannerEl.nextSibling : messagesEl`). The two prior truthiness usages (session_list auto-create branch and newChatBtn click handler) now read `setupIncomplete`.
- Added `sessionBannerEl` DOM-ref variable and `setSessionHealth(status)` helper with three branches (`agent_deleted`, `provider_missing`, default→ok). Helper toggles `inputEl.disabled` and `sendBtn.disabled` in lockstep. Banner text matches the design decision exactly. Banner inserted after the setup banner if both are present, otherwise immediately above `messagesEl`.
- Updated the `session_joined` handler with a stale-join guard `if (currentSessionId && currentSessionId !== data.session_id) return;` (AND-form preserves first-bind cases where `currentSessionId === null`) and a `setSessionHealth(data.status || 'ok')` call after `renderHistory(data.history)`.
- Updated `session_deleted` handler to call `setSessionHealth('ok')` before sending the auto-`new_session`, preventing a stale-banner flash.
- Guarded the `done` and `system` re-enable paths: `sendBtn.disabled = false` is now gated on `!sessionBannerEl` so a degraded session banner can't be re-enabled mid-message-send.
- Added `.area-chat .chat-session-banner` rule to `the_one/interfaces/web/static/styles.css` immediately after `.chat-no-providers`. Uses `#f5a623` to match the project's existing amber convention (`.context-bar.warn`, `.studio-vram-warning`, `.admin-system-warning`). No `--warn` variable introduced (out of scope per the leg).
- Tests: `pytest -q --ignore=tests/test_tool_registry.py --ignore=workspace/test_agent.py --timeout=30` → 324 passed, 8 deselected (matches Leg 02's baseline). `ruff check the_one/interfaces/web/app.py` clean. JS bracket balance verified via Python; `node -c` invocation was sandbox-denied so true syntax check is deferred to the manual smoke / HAT leg.

### `session-health-backend` — landed
- Added `RestoredSession` dataclass and four module-level status constants (`SESSION_STATUS_OK`, `SESSION_STATUS_NOT_FOUND`, `SESSION_STATUS_AGENT_DELETED`, `SESSION_STATUS_PROVIDER_MISSING`) to `the_one/interfaces/web/app.py`.
- Rewrote `_restore_session` to classify health into four states and **removed the silent default-agent fallback** that was masking deleted-agent sessions. `KeyError("Unknown agent: ...")` → `agent_deleted`; `KeyError("Provider not found: ...")` and `ValueError("...has no provider configured...")` → `provider_missing`. Unrecognized `ValueError`s propagate. Degraded states are NOT cached in `_sessions`.
- Rewrote `_get_or_restore_session` to return `RestoredSession`; cache hits return ok without re-running health checks (per design decision: health is a join-time concept).
- Added module-level `_build_session_joined_ok` and `_build_session_joined_degraded` helpers near `_send_to_session` so the WS handler stays compact and payloads are unit-testable.
- Updated WS `join` handler to surface `status` for all four sub-cases. Preserved the idempotent re-bind for the no-`session_id`-with-existing-`session` case. After a degraded join, the WS-loop `session` is set to `None` so subsequent message actions don't operate on a degraded session.
- Updated HTTP `/api/chat` to return `{"error": "session_<status>"}` for `agent_deleted`/`provider_missing`. `not_found` still falls through to `_create_session`.
- `_create_session`, the `new_session` action, and the bare-message auto-join branch are unchanged per leg scope.
- Tests: `tests/test_session_lifecycle.py` updated for the new return shape; added 7 new tests (agent_deleted, provider_missing-via-ValueError, provider_missing-via-KeyError, no caching of degraded, propagation of unrecognized ValueError, get_or_restore returns not_found, cached-session-skips-health-check). `pytest tests/test_session_lifecycle.py -v --timeout=30` → 21/21 passing. `pytest -q --timeout=30 --ignore=tests/test_tool_registry.py --ignore=workspace/test_agent.py` → 324 passed (up from 318 in leg 01).
- Ruff `check` clean and `format --check` clean for `tests/test_session_lifecycle.py`. For `the_one/interfaces/web/app.py`, ruff `check` is clean; `ruff format --check` reports preexisting formatting drift in regions not touched by this leg — see Deviations.

### `backend-cleanup` — landed
- Dropped the `qwen2.5:7b` default in `the_one/llm/ollama_provider.py:24` (now `model: str = ""`). No callers relied on the default; verified with `grep -rn "OllamaProvider("` (only the class declaration matches).
- Switched the masked-API-key check in `the_one/interfaces/web/api.py` from `startswith("***")` to `incoming_key == _MASKED_API_KEY_SENTINEL` ("__MASKED__"). Added module-level `_MASKED_API_KEY_SENTINEL` constant near `_mask_api_key`.
- Restructured `test_provider` error handling per the new taxonomy: per-branch catches for `openai.OpenAIError` / `anthropic.AnthropicError`, outer `except httpx.HTTPError` for upstream-connection errors, `except HTTPException: raise` pass-through, and a final `except Exception` that maps to `HTTPException(500)`. Expected upstream failures keep the 200-with-`status:"error"` contract; unexpected ones now surface as 500.
- Frontend `wireProviderFormEvents` (`admin.js`) captures the pre-filled masked API-key on form open into `originalMaskedApiKey`; on submit, an unchanged value is replaced with the `MASKED_SENTINEL` string before POST/PUT. Create-mode is unaffected.
- Critical test fix: `tests/test_provider_api.py::test_update_preserves_masked_key` now sends `"__MASKED__"` (was sending the literal mask `"***...9999"`, which would silently corrupt the stored key under the new sentinel) and asserts the GET round-trip returns the ORIGINAL key's mask. Added a parallel `test_update_replaces_key_when_not_masked` that confirms the non-sentinel path actually swaps the stored key (mask transitions from `***...9999` to `***...7777`).
- Updated four pre-existing connection-test failure tests (`test_ollama_failure`, `test_openai_compatible_failure`, `test_openai_failure`, `test_anthropic_failure`) to use the proper exception types (`httpx.ConnectError`, stub `OpenAIError`/`AnthropicError`). Without this, the new taxonomy correctly classifies them as 500-unexpected; with the fix they exercise the 200-expected path. Added `_StubOpenAIError` / `_StubAnthropicError` exception classes attached to the openai/anthropic mock modules so the per-branch `except` clauses get a real class to match.
- `tests/test_tool_registry.py:7` import fixed: `from conftest import StubTool` (matches sibling-test convention; previous `from tests.conftest import StubTool` failed at collection because `tests/` is not a package).
- `pyproject.toml` `[tool.pytest.ini_options]` now includes `norecursedirs = ["workspace", ".worktrees", "node_modules", ".git"]`, excluding the workspace scratch dir from default discovery and resolving the `workspace/test_agent.py` basename collision with `tests/test_agent.py`.
- One-shot `ruff format` pass on `the_one/interfaces/web/app.py` cleared the drift Leg 02 deferred. Diff is whitespace-only (verified via independent `ruff format /tmp/app_head.py` against HEAD's version — same shape of changes: line wrapping, dict expansion, no logical edits). The Leg 03 invariant `grep -n '"type": "session_joined"' app.py` still shows only the two helper internals (lines 276 and 294 post-format).
- `the_one/agents.md:70` updated to drop the `qwen2.5:7b default` mention.
- Tests: `pytest -q --timeout=30` (no `--ignore` flags) → **333 passed, 8 deselected, 0 collection errors**. `pytest --collect-only -q` shows 333/341 tests collected, none from `workspace/`.
- Ruff `check` clean for `the_one/llm/ollama_provider.py`, `the_one/interfaces/web/api.py`, `tests/test_tool_registry.py`, `tests/test_provider_api.py`. Ruff `format --check` clean for those plus `the_one/interfaces/web/app.py`.

---

## Decisions

### Orphan policy on temp-file write failure
If a write or fsync error occurs after `os.open` succeeds but before `os.replace`, the temp file (`encryption.key.tmp.<hex>`) is left on disk. No cleanup code is added — operators may safely delete `*.key.tmp.*` siblings of `encryption.key`. Successful rotations leave no temp files (guaranteed by `os.replace` semantics).

### API rotation no longer flows through `Encryptor.rotate_key`
The public `Encryptor.rotate_key(callback)` method remains in place and is still exercised by `tests/test_encryption.py::TestKeyRotation`, but production code no longer calls it. The API handler now manages the rotation sequence directly so the key file is the last thing to change. If a future flight wants to remove `rotate_key`, this is the entry point — no production callers remain.

### DB rollback on commit failure (impl detail beyond the leg snippet)
The leg's reference snippet did not include explicit rollback handling. Added a `try/except` that calls `await conn.rollback()` if the UPDATE+commit block raises, then re-raises. Required because the API uses a singleton aiosqlite connection: without rollback, subsequent requests on that connection would observe uncommitted ciphertext encrypted with the new (not-yet-on-disk) key, masking the failure rather than surfacing it cleanly.

### Concourse autopilot (`ci/pipeline.yml`) accepts the new degraded-error response as breaking
With the silent default-agent fallback removed, if the autopilot session's agent is deleted the every-30-minutes POST to `/api/chat` will receive `200 OK` with `{"error": "session_agent_deleted"}` (or `session_provider_missing`) and `messages` absent. The pipeline currently calls `result.get("messages", [])` and will silently no-op forever in that state. This is intentional — the silent fallback was hiding the operational issue this leg is meant to surface. Out of scope for this leg; the operator must either (a) recreate the autopilot session via `new_session` with a valid agent, or (b) update `ci/pipeline.yml` to surface `result.get("error")`. Flagging here so a future operator finds it.

### Cached sessions are not re-health-checked
Per the design decision, session health is a join-time concept. `_get_or_restore_session` returns cached sessions with `status: "ok"` without consulting the factory. If a provider is deleted mid-conversation, the next LLM call will fail with whatever raw error the provider raises; the user will not see a banner. Acceptable trade-off — re-classification on send-time errors is out of scope for this leg.

---

## Deviations

### Ruff `format --check` not clean on full `app.py`
The leg AC specifies `ruff format --check` clean for `the_one/interfaces/web/app.py`. The leg's own implementation guidance (step 8) says: "The `app.py` file is large — only check, don't aggressively reformat unrelated regions." `ruff format --check` was already failing on `main` (commit `0005128`) before this leg started — there is preexisting formatting drift in roughly ten regions (e.g., `_save_session_to_db`, `_ensure_ollama_model_loaded`, `_process_and_broadcast`, `chat_reset`, the WS `list_sessions`/`new_session`/auto-join branches). The author of this leg's snippet would have triggered the same drift. I followed the implementation guidance: ruff `check` is clean, my added regions match the file's existing style, and the format-check noise is preexisting and out of scope. A focused reformat pass for `app.py` belongs in leg 04 (backend-cleanup) where it can be reviewed without entangling logic changes.

### Post-review fixes (flight-level review feedback)
After all four autonomous legs landed, the flight-level Reviewer flagged two issues that were addressed before commit:

1. **chat.js `newChatBtn` interacted badly with the Leg 03 stale-join guard.** When `currentSessionId` was already bound to a session, clicking "+ new" sent `new_session` but did not clear `currentSessionId`. The backend created a fresh session and replied `session_joined` with the new id, but the new guard `if (currentSessionId && currentSessionId !== data.session_id) return;` then dropped the response — the user appeared stuck on the old session while the server retained an orphan subscriber. Fix: set `currentSessionId = null` before `ws.send(...)` in the `newChatBtn` handler, mirroring the existing pattern in the `session_deleted` handler.
2. **`rotate_encryption_key` ordering of the `key_path is None` guard.** The original Leg 01 implementation raised `HTTPException(500, "encryptor not file-backed")` AFTER the DB commit had already replaced ciphertext with the new key. The cached encryptor still held the old key, so subsequent decrypts would fail until process restart. The path is unreachable in production (`get_encryptor()` always returns a file-backed encryptor), but reordering the check turns a half-rotation into a clean no-op. Fix: hoist the `if encryptor.key_path is None` check (and the `key_path = encryptor.key_path` assignment) to immediately after `encryptor = get_encryptor(...)`, before the connection acquire and any DB reads.

Verification after both fixes: `pytest -q --timeout=30` → 333 passed, 8 deselected (unchanged from Leg 04 baseline). `ruff check the_one/interfaces/web/api.py` and `ruff format --check the_one/interfaces/web/api.py` both clean.

---

## Anomalies

### HAT Block B caught schema FK CASCADE foreclosing the `agent_deleted` health state
**Observed**: During HAT Block B (verifying the `agent_deleted` session-health banner from Leg 02), deleting an agent via the UI made the chat session disappear from the session list entirely instead of showing the "This agent has been deleted. Chat history is preserved..." banner. Root cause: the v1 schema declared `agent_name TEXT REFERENCES agents(name) ON DELETE CASCADE`, and the v2 migration kept the FK CASCADE while only relaxing `NOT NULL`. So deleting an agent cascade-deleted its sessions before `_restore_session` could ever classify them.

**Severity**: bug — forecloses Leg 02's `agent_deleted` health state in production. Leg 02's design decision explicitly required sessions to survive agent deletion ("user explicitly wants old sessions to remain visible with actionable guidance, not silently deleted or auto-redirected"). The unit tests in `tests/test_session_lifecycle.py` exercised the classification logic in isolation but did not exercise the FK behavior; `tests/test_db_repositories.py::test_cascade_delete_agent` actively asserted the buggy CASCADE behavior.

**Resolution**: Added schema migration v5 to `the_one/db/schema.py` that rebuilds `chat_sessions` without the FK on `agent_name` (table-rebuild dance, mirroring the v3 agents-table rebuild pattern). The column stays as `TEXT` so the deleted agent's name persists as a free-text value — `_restore_session` then calls `factory.create("<deleted-name>")` which raises `KeyError("Unknown agent: ...")` and the classifier returns `agent_deleted` as designed. Did NOT use `ON DELETE SET NULL` because that would null `agent_name` and silently fall back to the default agent (the exact bug Leg 02 was supposed to fix).

Test changes:
- `tests/test_schema.py`: bumped `CURRENT_VERSION` expectation to 5; added 3 v5-specific tests (`test_fresh_db_chat_sessions_no_fk_on_agent_name`, `test_fresh_db_chat_sessions_index_recreated`, `test_v5_agent_delete_does_not_cascade_to_sessions`).
- `tests/test_db_repositories.py`: renamed `test_cascade_delete_agent` to `test_agent_delete_does_not_cascade_to_sessions` and inverted its assertion — it's now the regression guard at the repository layer.

Verification: `pytest -q --timeout=30` → 336 passed (333 baseline + 3 new), 8 deselected. Ruff `check` and `format --check` clean for all touched files. `docker compose up -d --build` against the user's existing v4 DB applied the migration: `schema_version` now `[1,2,3,4,5]`; `chat_sessions` schema shows `agent_name TEXT,` with no `REFERENCES agents(name)` clause; `idx_chat_sessions_agent` recreated.

### Test collection errors on flight start
**Observed**: `pytest --co` on `main` (commit `0005128`) reports 2 collection errors before any flight work begins:
1. `workspace/test_agent.py` — already on cleanup leg's todo list (flight spec, leg 4)
2. `tests/test_tool_registry.py` — `ModuleNotFoundError: No module named 'tests.conftest'` (new finding — `from tests.conftest import StubTool` import fails)

**Severity**: degraded — flight prerequisite "All 325 tests passing on current main" is not strictly met (317/325 collected, 8 deselected, 2 collection errors). Both are fixable in the cleanup leg without blocking other legs.

**Resolution**: Folded `tests/test_tool_registry.py` fix into Leg 04 (`backend-cleanup`) scope alongside the existing `workspace/test_agent.py` item.

---

## Flight Director Notes

### Phase file loading
Loaded project-specific `leg-execution.md` from `.flightops/agent-crews/`. Crew: Developer (Sonnet) + Reviewer (Haiku), with optional Accessibility Reviewer (Sonnet). All required sections (`## Crew`, `## Interaction Protocol`, `## Prompts`) present and well-formed.

### Prerequisite verification
Ran `pytest --co -q` to verify "all 325 tests passing on main" — found 2 collection errors. Decision: proceed with flight rather than block. Rationale: one error is already in scope for Leg 04; the second is an import-path issue clearly fixable in the same leg. Recorded as anomaly.

### Leg execution order
Following flight spec leg order verbatim:
1. `key-rotation-atomicity` (highest-risk, goes first for max scrutiny)
2. `session-health-backend`
3. `session-health-frontend`
4. `backend-cleanup` (cleanup, plus the new `tests/test_tool_registry.py` fix)
5. `hat-and-alignment` (optional, interactive — handled separately)

Per `/agentic-workflow` fast variant: design + implement each leg, then a SINGLE flight-level review + commit covering all autonomous legs at the end.

---

## Session Notes

_(no session notes yet)_
