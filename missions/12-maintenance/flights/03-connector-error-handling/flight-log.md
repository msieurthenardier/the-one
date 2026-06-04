# Flight Log: Connector Error-Handling Correctness

**Flight**: [Connector Error-Handling Correctness](flight.md)

## Summary
In progress. Three independent error-taxonomy fixes, each with a regression test: T2 (narrow the collapsed broad-except in `api.py`), T1 (map the ephemeral-followup non-401 path to a typed error in `_discord.py`), Q2 (resolve dead `ConnectorAuthRequired` — **disposition: DELETE**).

---

## Leg Progress

### Leg 1 — narrow-broad-except (`api.py`) — 2026-06-04

**Status**: landed

**Changes:**
- `the_one/interfaces/web/api.py` (`_save_warm_background`, line ~2455): split `except (ConnectorClientError, Exception) as exc:` into two clauses — `except ConnectorClientError as exc:` (records connection errors as before) and `except Exception:` (logs with `account_id` context via `logger.exception` then re-raises without writing to `_connect_error_store`).
- `tests/test_connector_status_endpoint.py`: added `test_save_warm_background_unexpected_error_not_recorded` — patches `the_one.connectors._pool.account_acquire` to raise `AttributeError`, calls `_save_warm_background("acct")` directly inside `pytest.raises(AttributeError)`, and asserts `"acct" not in _connect_error_store`.

**Test result:** `docker exec the-one pytest tests/test_connector_status_endpoint.py -q --timeout 60` → 29 passed in 3.40s. Lint gate: `ruff check` → 0 errors; `ruff format --check` → clean.

### Leg 2 — map-ephemeral-followup-error (`_discord.py`) — 2026-06-04

**Status**: landed

**Changes:**
- `the_one/connectors/_discord.py` (line ~551): replaced bare `raise` in the non-401/non-NotFound `else` branch of the ephemeral-followup `except (NotFound, HTTPException)` block with `raise ConnectorConnectionError(f"Discord send failed: {exc}") from exc`, matching the channel-ladder generic-HTTPException mapping at line 619. Updated the aspirational comment at ~539–541 to accurately describe the new typed-raise behavior.
- `tests/test_connectors_discord.py`: added `test_send_ephemeral_followup_non_401_http_error_raises_connection_error` — builds `discord.errors.HTTPException` with `status=500` via `_make_http_exception`, attaches via `webhook.send = AsyncMock(side_effect=...)` + `monkeypatch.setattr(discord.Webhook, "from_state", ...)`, asserts `pytest.raises(ConnectorConnectionError)` and that `channel.send` was NOT called (no fallback).

**Test result:** `docker exec the-one pytest tests/test_connectors_discord.py -q -k ephemeral --timeout 60` → 7 passed (6 pre-existing + 1 new) in 0.05s. Lint gate: `ruff check` → 0 errors; `ruff format --check` → clean.

### Leg 3 — resolve-connector-auth-required (deletion) — 2026-06-04

**Status**: landed

**Changes:**
- `the_one/connectors/errors.py`: deleted `ConnectorAuthRequired` class block (lines 34–51, including `# noqa: N818`).
- `the_one/connectors/__init__.py`: removed `ConnectorAuthRequired,` from the `from the_one.connectors.errors import (...)` block and `"ConnectorAuthRequired",` from `__all__`.
- `the_one/connectors/base.py`: removed the `:class:`ConnectorAuthRequired`` clause from the `connect()` docstring's Raises section; changed the preceding `ConnectorConnectionError` clause's trailing `;` to `.` for grammatical correctness.
- `the_one/agents.md` (line 773): updated count from "6 producer-side types" to "5"; removed `ConnectorAuthRequired` from the inline list.
- `tests/test_connectors.py`: removed `ConnectorAuthRequired,` import; updated `TestConnectorExceptions` docstring "6-type" → "5-type"; removed `ConnectorAuthRequired` from the `test_subclassing_chain` tuple; deleted `test_auth_required_carries_account_id` and `test_auth_required_account_name_optional`.

**Verification:**
- `grep -rn "ConnectorAuthRequired" the_one/ tests/` → zero results
- `ruff check the_one/ tests/` → 0 errors
- `ruff format --check the_one/ tests/` → clean (322 files already formatted)
- `docker exec the-one pytest tests/test_connectors.py tests/test_connectors_discord.py -q --timeout 60 -x` → 126 passed in 0.62s

---

## Flight Director Notes

### 2026-06-04 — Flight start
- Invoked via `/agentic-workflow` for `the-one` mission 12, flight 03 (Connector Error-Handling Correctness). Branched `flight/03-connector-error-handling` off `main` (Flights 01 + 02 merged: PRs #88, #89; main at 00b0076).
- Loaded phase file `.flightops/agent-crews/leg-execution.md` (Developer=Sonnet, Reviewer=Haiku) — structure valid. **This flight: pass `model: sonnet` explicitly on Developer spawns** (Flight 02 Leg 2 inadvertently ran on Opus).
- **Q2 disposition resolved — DELETE** (operator-confirmed). Evidence: no caller branches on connector error subtype (`grep` for `except ConnectorConfigError`/`isinstance(..., ConnectorAuthRequired)` → none); the `app.py` `auth_required` surface is the unrelated MCP tool-call OAuth pause, not connector login. Wiring would add a `raise` for a type nothing consumes → still dead. Deletion resolves Q2 honestly and moots the Flight 02 N818 concern.
- **Line-number drift from Flight 02:** Flight 02 reformatted `api.py` and `_discord.py`, so the leg specs' line refs are stale. T2 broad-except relocated to `api.py:2455` (was :2463); its `# noqa: BLE001` is ALREADY removed (Flight 02 Leg 1), so Leg 1 only needs the narrowing. Design reviews must re-locate T1 (`_discord.py` ephemeral non-401) and the mapping ladder by content, not line number.
- Three legs are independent (T2 in `api.py`, T1 in `_discord.py`, Q2 deletion across `errors.py`/`__init__.py`/`base.py`/tests). Running the three design reviews in parallel (read-only), then implementing sequentially (shared flight-log writes). Flight `ready` → `in-flight`.

### 2026-06-04 — Leg design reviews (3× Developer agents, Sonnet, parallel) + revisions
All three approve-with-changes; revisions applied (corrections + the relocations forced by Flight 02's reformat), no new scope → no second cycles:
- **Leg 1 (T2):** [high] after narrowing to `except ConnectorClientError`, a propagating programming error becomes a GC-time "Task exception never retrieved" warning with no context (the task has no exception-retrieving callback / no global asyncio handler) — so a **dedicated `except Exception:` log-with-account_id-and-reraise path is now required** (not optional). The noqa criterion was stale (Flight 02 already removed it) → dropped. Test made explicit: call `_save_warm_background` directly with `account_acquire` patched to raise `AttributeError`, assert `pytest.raises` + store empty. Site relocated to `api.py:2455`.
- **Leg 2 (T1):** [med] the test must NOT use `_StubErrors.HTTPException` (no `status` attr → can't drive the non-401 branch); use `_make_http_exception(discord.errors.HTTPException, status=500)` + `monkeypatch`, modeled on `test_send_ephemeral_token_expired_falls_back_to_channel`. Bare `raise` relocated to `_discord.py:551`; ladder at 568/581/607/619; aspirational comment at ~539–541 to be updated. Confirmed contract-correctness (latent, not a live bug — callers swallow via broad except).
- **Leg 3 (Q2 delete):** [high] the original checklist MISSED `the_one/agents.md:773` ("6 producer-side types" list — always-loaded manual) and [med] the `test_subclassing_chain` tuple entry + `TestConnectorExceptions` "6-type" docstring + the `base.py` semicolon→period prose fix. Leg rewritten deletion-only with the complete 10-edit/5-file checklist. Runtime-safety confirmed: no `except`/`isinstance` on the type anywhere.
- Proceeding to sequential implementation (Leg 1 → 2 → 3), Developer spawns pinned to `model: sonnet`.

### 2026-06-04 — Flight 03 code review (Reviewer agent, Haiku) → confirmed + full suite
- Reviewer evaluated all uncommitted changes across the three legs. Verdict: **[HANDOFF:confirmed]** — Leg 1 except correctly split (record vs log-and-reraise), Leg 2 typed-raise with no token leak and 401/NotFound untouched, Leg 3 deletion complete (`grep` zero, base.py semicolon→period applied, agents.md count 6→5, `test_subclassing_chain` preserved for the other types, no historical artifacts touched). Lint gate clean; focused suites green (155 passed).
- Single review cycle, no fixes required.
- **Flight Director full-suite gate** (`docker exec the-one pytest tests/ -q --timeout 60`): **2935 passed, 4 skipped, 538 deselected** in 287.80s. Net test count unchanged (Legs 1+2 added 2 tests, Leg 3 removed 2). 3 warnings = the known benign aiosqlite teardown ResourceWarning. No regression from the now-propagating programming errors (Leg 1) or the deleted type (Leg 3). Proceeding to commit.

---

## Decisions

### Q2 resolved by deletion, not wiring
**Context**: Flight design recommended wiring `ConnectorAuthRequired`; flight-start investigation found nothing consumes a connector error-subtype distinction.
**Decision**: Delete the type (operator-confirmed) rather than wire a `raise` no caller acts on.
**Impact**: Dead signal removed honestly; the Flight 02 N818 concern is mooted (the type + its noqa are gone). If a future feature needs a distinct "needs re-auth" surface, it should be (re)introduced with a consumer, per YAGNI.

---

## Deviations

_None._

---

## Anomalies

### Benign aiosqlite teardown warning (carried)
**Observed**: 3× `aiosqlite` event-loop-teardown `ResourceWarning`/`RuntimeError('Event loop is closed')` during the full-suite run.
**Severity**: cosmetic
**Resolution**: Pre-existing, unrelated to this flight (carried since F11; flagged across M12 flights). No test failed. Disposition deferred to routine maintenance (noted in Flight 01 debrief action items).

---

## Session Notes
