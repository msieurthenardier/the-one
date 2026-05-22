# Leg: discoverable-entities-cache-and-api

**Status**: completed
**Flight**: [Live-Data Discoverable Dropdowns](../flight.md)

## Objective

Stand up the substrate cache + per-account REST API for live-data discoverable entities. Extend `_pool._RegistryEntry` with two new fields (latest fresh snapshot + per-axis stale-carry list), add a sibling periodic refresh sweep task (`_discoverable_refresh_loop`) running alongside the existing `_reap_loop` on its own asyncio task with a 300s interval, ship `GET /api/connector-accounts/{id}/discoverable-entities` and `POST /api/connector-accounts/{id}/discoverable-entities/refresh` endpoints, implement 1-cycle stale-entry retention semantics, and pin the contract with tests against the pool sweep mechanics, the API response shape, the stale-entry diff logic, and the lifespan wiring.

## Context

- L3 landed: `DiscoverableEntity` + `DiscoverableEntities` dataclasses in `the_one/connectors/base.py`; `_DiscordPlugin.enumerate_discoverable_entities(client) -> DiscoverableEntities` implemented as a sync hook discoverable via `getattr(plugin, "enumerate_discoverable_entities", None)`. L4 is the first consumer.
- **Design Decision — direct pool access, NOT `account_acquire`** (flight.md cache strategy): the refresh sweep iterates `_pool._entries` directly under `_lock`, captures each entry's `client` reference, releases the lock, calls `getattr(plugin, "enumerate_discoverable_entities", None)(client)` outside the lock. CRITICAL: the sweep does NOT touch `entry.last_activity`. Routing the refresh through `account_acquire` would update `last_activity` on every 5-minute sweep, and since the 5-minute refresh interval is shorter than the default 30-minute idle TTL (`_DEFAULT_TTL_SECONDS = 1800`), warm entries would never be reaped. This was caught at Architect cycle-1.
- **Design Decision — use-after-evict safety** (flight.md): when the sweep's plugin call returns, the entry may have been evicted (by the reaper sweep that ran in parallel). The implementation re-acquires `_lock` before writing back the cache + previous-cache + timestamp; it only writes if the entry is still present in `_pool` with the same identity. If the entry has been evicted in the meantime, the result is discarded.
- **Design Decision — write-side serialization via `prior_cache` read under the SAME lock acquisition as the write** (this leg's resolution to a cycle-1 race catch): the stale-carry computation MUST read `entry.discoverable_entities_cache` as `prior_cache` INSIDE the re-acquired lock, NOT snapshot it at function entry. If two refresh paths (the periodic sweep + an inline GET-triggered refresh) overlap, both serialize at the lock-write boundary; each computes `stale_carry = prior_cache (read under lock) - new_snapshot`. The result is at most one refresh-cycle behind regardless of interleaving; no mixed-cycle stale-carry can form.
- **Design Decision — shutdown-safety bail in refresh helper** (this leg's resolution): the refresh helper checks `_shutting_down` after re-acquiring the lock; if True, returns `False` without writing. Eliminates the "benign-but-untracked" cache write to an about-to-be-evicted entry.
- **Design Decision — read-side serialization via frozen-triple snapshot, NOT live entry reference** (this leg's resolution to a cycle-1 race catch): the API endpoints' read path obtains an immutable snapshot of the three cache fields under `_lock` (NOT a live `_RegistryEntry` reference). The snapshot is a small frozen dataclass `_DiscoverableCacheSnapshot { cache: DiscoverableEntities | None; stale_carry: DiscoverableEntities | None; fetched_at_monotonic: float | None; account_type: str }`. The handler reads from this immutable triple outside the lock with no consistency concerns — the snapshot was atomic under `_lock`. The helper is named `_get_account_cache_snapshot(account_id) -> _DiscoverableCacheSnapshot | None` (returns None when the account has no warm pool entry; non-None when warm regardless of whether the cache fields are populated). The handler then distinguishes "no warm entry" (None → 404) from "warm but cache empty" (non-None with `cache is None` → first-call inline refresh).
- **Design Decision — fail open on first-call empty refresh** (this leg's resolution to a cycle-1 pre-READY race catch): if the first inline refresh fires before Discord's gateway READY has populated the SDK caches, the hook returns a `DiscoverableEntities` with empty axes. The endpoint responds **200 with empty axes** rather than 503. Acceptable tradeoff: the operator's first dropdown-open immediately after Test Connection may show empty axes; they press the manual Refresh button (or the next periodic sweep fires within ≤ 5 minutes). Document in the operator-facing UX layer (L5) that empty axes immediately after a fresh connection are expected; the Refresh button is the recovery path.
- **Design Decision — entities changed-in-place between cycles use NEW form** (this leg's resolution to a cycle-1 set-diff-semantics catch): the set diff `prior_cache_axis - new_snapshot_axis` operates by `entity.id` only. An entity present in BOTH cycles with a changed label or metadata (e.g., user renames themselves) is NOT in the diff — its NEW form lives in `cache`, the old form is discarded. Only entities ABSENT from the new snapshot are carried as stale. The substrate does NOT preserve old labels.
- **Design Decision — 1-cycle stale-entry retention** (flight.md):
  - Cycle 0: snapshot {A, B, C} → `cache = {A, B, C}`, `stale_carry = {}`. API response: all three rendered fresh.
  - Cycle 1: snapshot {A, B} → `stale_carry = old_cache - new_cache = {C}`; `cache = {A, B}`. API response: A and B fresh, C marked stale.
  - Cycle 2: snapshot {A, B} → `stale_carry = old_cache - new_cache = {} = {}`; `cache = {A, B}`. API response: A and B fresh. C has been dropped (it was in `stale_carry` of cycle 1 but not in `old_cache` of cycle 2).
  - **Key invariant**: `stale_carry` is ALWAYS computed as `old_cache - new_cache`, never accumulated. Entries persist in `stale_carry` for exactly one refresh cycle.
- **Design Decision — stale flag projection at API time, NOT on the dataclass** (this leg's resolution): `DiscoverableEntity` (L3-shipped) has no `stale` field. The pool stores `cache` (DiscoverableEntities, all fresh) and `stale_carry` (DiscoverableEntities-shaped, entries removed since last refresh). At GET / POST response time, the API computes the union of `cache` + `stale_carry` and emits each entity with a top-level boolean `stale` projected into the JSON shape: entities from `cache` get `stale: false`; entities from `stale_carry` get `stale: true`. This avoids modifying L3's dataclass shape; the staleness is a render-time concern only.
- **Design Decision — Pydantic wrapper for response model** (this leg's resolution): the project precedent (`_connector_account_response` at `api.py:2269`, `_mcp_source_response` at `api.py:712`) uses helper functions that build response dicts from `model.model_dump()` calls. For `DiscoverableEntities` (frozen dataclass), the L4 API layer wraps in a small Pydantic response model `_DiscoverableEntitiesResponse` declared inline in `api.py` (mirroring the inline-helper pattern). The response model converts each axis's `list[DiscoverableEntity]` to a `list[_DiscoverableEntityOut]` where `_DiscoverableEntityOut` has the dataclass fields plus the projected `stale: bool`.
- **Design Decision — 404 with pre-probe hint on cold accounts**: if the account has no warm pool entry (it has never been pooled, OR the reaper has evicted it), the GET endpoint returns 404 with body `{"detail": "Run Test Connection first to populate the bot's discoverable view."}`. Same shape for POST refresh. Mirrors F1 L5's Invite-section pre-probe hint behavior. Operator runs Test Connection (which goes through the existing doctor probe path AND populates the pool entry via the lifespan-listener-warmup path); the dropdown then has a cached view to serve.
- **Design Decision — 503 if plugin hook absent**: if the account's connector plugin does NOT implement `enumerate_discoverable_entities` (e.g., the `stub` plugin), the endpoints return 503 with body `{"detail": "This connector type does not expose discoverable entities."}`. In practice, the Studio frontend should never reach this branch for stub-type accounts because the registry-entry hook (L5/L6) falls back to the chip-list editor first — but the API layer must be defensive for direct-API consumers.
- **Codebase recon (verified at design review)**:
  - `_pool.py:93-120` — `_RegistryEntry` dataclass with fields `ttl_seconds`, `last_activity`, `worker`, `evict_event`, `client_ready`, `client`, `failure`. Defined as `@dataclass` (NOT frozen — must accept the new fields with defaults).
  - `_pool.py:124-125` — `_pool: dict[tuple[str, str], _RegistryEntry] = {}` and `_lock: asyncio.Lock = asyncio.Lock()`. The module-level state pattern.
  - `_pool.py:143` — `_ACCOUNT_POOL_AGENT_SLOT = "__connector__"`. The refresh sweep filters to entries where `key[0] == _ACCOUNT_POOL_AGENT_SLOT` (account-keyed entries only; per-agent entries are MCP territory and don't need the discoverable cache).
  - `_pool.py:305-316` — `_ensure_reaper_running_locked()` pattern: spawns `asyncio.create_task(_reap_loop())` if `_reaper_task` is None or done. The new `_ensure_discoverable_refresh_running_locked()` follows the identical shape.
  - `_pool.py:362-388` — `_reap_loop`: sleeps on `_REAPER_INTERVAL_SECONDS`, calls `_reap_once()`, suppresses `Exception` to keep the loop alive, drains on `CancelledError`. The new `_discoverable_refresh_loop` follows the same exception-handling posture.
  - `_pool.py:390-420` — `shutdown_drain()` cancels `_reaper_task`. Extend to also cancel the new `_discoverable_refresh_task`.
  - `api.py:2317-2326` — `GET /api/connector-accounts/{account_id}` shape: `repo.get(account_id)` → `KeyError` → `HTTPException(status_code=404, detail=f"Connector account not found: {account_id}")`. Reuse this lookup pattern.
  - `api.py:2573-2638` — `POST /api/connector-accounts/{account_id}/test/connect` shape: imports `_resolve_plugin` function-locally per the section's convention; calls `plugin.doctor(...)`; returns `{status, message, details}` envelope. Reuse the function-local-import and plugin-resolve pattern.
  - `tests/test_connectors_pool.py` — uses `pool_mod._clear_for_test()` and `restore_to_baseline_for_test()` autouse fixture; monkeypatches `_REAPER_INTERVAL_SECONDS` for fast-sweep tests.
  - `tests/test_api_connector_account_config_validation.py` — uses `AsyncClient(ASGITransport(app=FastAPI))` pattern; patches `get_connection` and `get_encryptor` fixtures.

## Inputs

- L3 has landed: `DiscoverableEntity` + `DiscoverableEntities` are importable from `the_one.connectors.base`; `_DiscordPlugin.enumerate_discoverable_entities` is callable.
- `the_one/connectors/_pool.py` exists with `_RegistryEntry`, `_reap_loop`, `_ensure_reaper_running_locked`, `shutdown_drain`, `_pool`, `_lock`, `_ACCOUNT_POOL_AGENT_SLOT`.
- `the_one/interfaces/web/api.py` exists with the connector-accounts router around L2289-2638.
- `the_one/interfaces/web/app.py` (or lifespan-equivalent) exists with the FastAPI lifespan context manager that drains the connector pool at shutdown.
- F1 L1's `lifespan-wiring-same-leg-as-installation` convention applies: the new task's start + shutdown wiring lands in this leg, not a follow-up.

## Outputs

- `the_one/connectors/_pool.py` grows:
  - Two new fields on `_RegistryEntry`:
    - `discoverable_entities_cache: DiscoverableEntities | None = None` — the latest fresh snapshot, populated by the sweep on successful refresh.
    - `discoverable_entities_stale_carry: DiscoverableEntities | None = None` — entries that were in the previous fresh snapshot but absent from the latest refresh. Persists for exactly one refresh cycle (until the next refresh recomputes it).
    - `discoverable_entities_fetched_at_monotonic: float | None = None` — `time.monotonic()` at the moment of the most recent successful refresh. Used to compute `stale_seconds` in the API response.
  - One new module-level constant: `_DISCOVERABLE_REFRESH_INTERVAL_SECONDS: float = 300.0` (5 minutes; matches the `float` type of `_REAPER_INTERVAL_SECONDS = 30.0` at `_pool.py:88`). Reads from env var `THE_ONE_CONNECTOR_DISCOVERABLE_REFRESH_INTERVAL_SECONDS` as an override (mirrors `_REAPER_INTERVAL_SECONDS` env-var pattern at `_pool.py` if present, else introduce the env var alongside).
  - One new module-level state: `_discoverable_refresh_task: asyncio.Task[None] | None = None`.
  - One new async helper `_refresh_discoverable_entities_for_account(account_id: str) -> bool` (NOTE: renamed from the cycle-0 spec's `_refresh_discoverable_entities_for_account(key, entry)` per cycle-1 review — accepts `account_id` and synthesizes the pool key internally, so the API handler doesn't have to know the `_ACCOUNT_POOL_AGENT_SLOT` literal). The helper:
    - Synthesizes `key = (_ACCOUNT_POOL_AGENT_SLOT, account_id)`.
    - Under `_lock`: looks up the entry. If absent OR `entry.client is None` OR `entry.account_type == ""` (empty default — test scaffolding entry) OR `entry.client_ready is not None and not entry.client_ready.is_set()` (mid-connect; cache fields will be populated on the next sweep after READY) → returns `False`. Otherwise captures `client = entry.client` and `account_type = entry.account_type`.
    - Releases the lock. Looks up the plugin via `from the_one.connectors.registry import resolve as _resolve_plugin` (function-local import per the section's convention) using the captured `account_type`. If `enumerate_discoverable_entities` is not present (`getattr(plugin, "enumerate_discoverable_entities", None) is None`), returns `False` (no refresh performed; nothing to write back).
    - Calls the sync hook outside the lock: `new_snapshot = plugin.enumerate_discoverable_entities(client)`. Wraps in try/except — on plugin raise, logs `logger.warning("Discoverable refresh failed for account_id=%s account_type=%s: %r", account_id, account_type, exc)` and returns `False`. The entry's cache is NOT modified.
    - Re-acquires `_lock`. **Shutdown check**: if `_shutting_down`, returns `False` immediately. **Identity check**: looks up the entry by key again; if absent OR `_pool[key].client is not client` (identity, not equality), returns `False`. **Read `prior_cache` under THIS lock**: `prior_cache = _pool[key].discoverable_entities_cache` (NOT the entry snapshot from the first lock acquisition — this guards the cycle-1 write-side race).
    - Computes `stale_carry` per-axis as `prior_cache_axis - new_snapshot_axis` by `entity.id` (set difference). The retained entities are emitted from `prior_cache_axis` (preserve their old labels/metadata for the stale display). If `prior_cache` is None, `stale_carry` is an empty `DiscoverableEntities`.
    - Writes `_pool[key].discoverable_entities_cache = new_snapshot`; `_pool[key].discoverable_entities_stale_carry = stale_carry`; `_pool[key].discoverable_entities_fetched_at_monotonic = time.monotonic()`. CRITICAL: does NOT touch `_pool[key].last_activity`.
    - Returns `True`.
  - One new async helper `_discoverable_refresh_once() -> int` mirroring `_reap_once`:
    - Snapshots account_ids (under `_lock`) filtered to entries where `key[0] == _ACCOUNT_POOL_AGENT_SLOT` AND `entry.client is not None` AND `entry.account_type` is non-empty.
    - For each `account_id`, calls `_refresh_discoverable_entities_for_account(account_id)` concurrently via `asyncio.gather(..., return_exceptions=True)`. (Per-call exceptions are already absorbed inside the helper via try/except + `logger.warning`; the gather's `return_exceptions=True` is belt-and-suspenders.) The loop continues.
    - Returns the count of entries successfully refreshed (sum of helper True returns).
  - One new async loop `_discoverable_refresh_loop()` mirroring `_reap_loop`:
    - `while True: await asyncio.sleep(_DISCOVERABLE_REFRESH_INTERVAL_SECONDS); try: await _discoverable_refresh_once(); except Exception: logger.exception(...)`.
    - On `CancelledError`: just re-raise (no drain — there's nothing to drain; the cache is in-memory and clears when the pool clears).
  - One new lifecycle helper `_ensure_discoverable_refresh_running_locked()`:
    - Spawns `asyncio.create_task(_discoverable_refresh_loop())` if `_discoverable_refresh_task` is None or done. MUST be called under `_lock`.
  - Extended `shutdown_drain()`: cancel `_discoverable_refresh_task` alongside `_reaper_task`. Same pattern — `task.cancel(); contextlib.suppress(asyncio.CancelledError); await task`. Reset `_discoverable_refresh_task = None` before returning.
  - Extended `_clear_for_test()` (the existing test helper at `_pool.py:_clear_for_test`): also reset `_discoverable_refresh_task` and `_DISCOVERABLE_REFRESH_INTERVAL_SECONDS` to defaults.
  - **Call sites that spawn the refresh task**: the task is spawned lazily on **cold-entry creation** in `agent_acquire` (and the wrapping `account_acquire`), paralleling `_ensure_reaper_running_locked` at `_pool.py:488` — that helper is called inside the `if entry is None:` branch only, NOT on warm-reuse. The new `_ensure_discoverable_refresh_running_locked()` lives in the same branch, same lock block. **Warm-reuse semantics**: if the periodic refresh task somehow died (CancelledError propagation, unexpected exception), it is NOT respawned by warm-reuse calls — same posture as the reaper. The shutdown drain handles the cancel cleanly.
  - One new helper `_get_account_cache_snapshot(account_id: str) -> _DiscoverableCacheSnapshot | None` that:
    - Synthesizes `key = (_ACCOUNT_POOL_AGENT_SLOT, account_id)`.
    - Under `_lock`: returns `None` if the entry is absent or `entry.client is None`. Otherwise returns a NEW `_DiscoverableCacheSnapshot` instance carrying `cache`, `stale_carry`, `fetched_at_monotonic`, AND `account_type` — read atomically under the lock.
    - The returned snapshot is a frozen dataclass (`@dataclass(frozen=True, slots=True)`). The handler reads from it outside the lock with no consistency concern.
    - Why include `account_type` in the snapshot: the API handler uses it to resolve the plugin (for the hook-presence check that gates 503 vs 200/refresh) without a second lock acquisition.
  - One new dataclass declaration `_DiscoverableCacheSnapshot` (module-private to `_pool.py`):
    ```python
    @dataclass(frozen=True, slots=True)
    class _DiscoverableCacheSnapshot:
        """Immutable triple of cache state + account_type for the API handler.
        Captured under _lock; readable outside the lock with no consistency risk.
        """
        cache: DiscoverableEntities | None
        stale_carry: DiscoverableEntities | None
        fetched_at_monotonic: float | None
        account_type: str
    ```
- `the_one/interfaces/web/api.py` grows:
  - One Pydantic response model `_DiscoverableEntityOut`: `{id: str, label: str, group: str | None, metadata: dict[str, Any], stale: bool}`. The `stale` field is projected at response time; the underlying `DiscoverableEntity` dataclass has no `stale` field.
  - One Pydantic response model `_DiscoverableEntitiesResponse`: `{entities: {peers: list[_DiscoverableEntityOut], channels: list[...], groups: list[...], roles: list[...]}, fetched_at: str, stale_seconds: float}`. Note `entities` is a nested dict-of-lists matching the L3 dataclass shape (not flattened to top-level).
  - One new endpoint `GET /api/connector-accounts/{account_id}/discoverable-entities`:
    - Returns 404 with `{"detail": "Connector account not found: {account_id}"}` if the repo lookup fails.
    - Returns 404 with `{"detail": "Run Test Connection first to populate the bot's discoverable view."}` if `_get_account_cache_snapshot(account_id)` returns None (cold account).
    - Returns 503 with `{"detail": "This connector type does not expose discoverable entities."}` if the snapshot's `account_type` resolves to a plugin without the `enumerate_discoverable_entities` hook.
    - Returns 200 with `_DiscoverableEntitiesResponse` body when the snapshot's `cache` is populated. The `stale_seconds` field is `time.monotonic() - snapshot.fetched_at_monotonic`.
    - **Edge case — first-call inline refresh**: snapshot exists but `snapshot.cache is None` (entry just created; first periodic sweep has not yet run). The endpoint calls `_refresh_discoverable_entities_for_account(account_id)` synchronously. **If the refresh returned `True`**, re-fetches the snapshot and proceeds with normal response building. **If the refresh returned `False`** (rare: mid-connect race; the entry's `client_ready` was not set when the helper looked; OR the entry was evicted between the snapshot capture and the refresh's lock-acquire), responds **200 with empty axes** (`fetched_at = now_iso`; `stale_seconds = 0.0`; all four axes empty lists) — the fail-open posture documented in Design Decisions. The frontend's manual Refresh button is the recovery path; the next periodic sweep fires within ≤ 5 minutes.
    - **Edge case — pre-READY refresh with empty axes**: if the hook ran successfully but returned empty axes (Discord's gateway READY had not populated the SDK caches), the endpoint returns 200 with the empty `_DiscoverableEntitiesResponse`. Acceptable; documented as a known UX limitation in the L5 frontend layer.
  - One new endpoint `POST /api/connector-accounts/{account_id}/discoverable-entities/refresh`:
    - Same 404 / 503 logic as GET (uses `_get_account_cache_snapshot` for the account-exists-and-warm check; resolves plugin to check hook presence).
    - Calls `_refresh_discoverable_entities_for_account(account_id)` synchronously. If the refresh returned `False`, responds 200 with empty axes (same fail-open as GET first-call edge case). Otherwise re-fetches the snapshot and returns it.
  - Imports: `from the_one.connectors.base import DiscoverableEntities, DiscoverableEntity` (used in the Pydantic models). Add a top-level `from pydantic import BaseModel, ConfigDict, Field` import (currently `api.py:19` imports only `ValidationError` from pydantic — verify against actual line at implementation time; the import line is extended in place). Per the section's function-local-import convention, the plugin-resolve import stays function-local.
- `tests/test_connectors_pool.py` grows new tests:
  - `test_refresh_loop_populates_cache_for_warm_account_entry` — start a warm entry via `account_acquire`, monkeypatch `_DISCOVERABLE_REFRESH_INTERVAL_SECONDS = 0.01`, wait for one sweep tick, assert the entry's `discoverable_entities_cache` is populated.
  - `test_refresh_loop_does_not_touch_last_activity` — record `entry.last_activity` before/after a refresh sweep; assert they're equal (the sweep does NOT update activity).
  - `test_refresh_handles_evicted_entry_gracefully` — capture the entry's `client`, evict the entry mid-refresh (race simulation), assert the refresh helper returns False and does not raise.
  - `test_refresh_computes_stale_carry_from_diff` — populate cache with entities {A,B,C}, refresh with snapshot {A,B}, assert `stale_carry` contains C; refresh again with {A,B}, assert `stale_carry` is empty.
  - `test_refresh_skips_entries_without_hook` — register a plugin without `enumerate_discoverable_entities`, run a sweep, assert no exception, no cache populated, entry untouched.
  - `test_refresh_task_started_on_first_account_acquire` — confirm `_discoverable_refresh_task is None` before any acquire; after the first `account_acquire`, the task is running.
  - `test_shutdown_drain_cancels_refresh_task` — start refresh task, call `shutdown_drain()`, assert the task is None and cancelled.
- `tests/test_api_connector_accounts.py` (NEW file, OR extension of existing `tests/test_api_connector_account_config_validation.py` — prefer NEW file for clarity) grows tests:
  - `test_get_discoverable_entities_returns_404_for_unknown_account` — call GET against a non-existent id, assert 404 with the "Connector account not found" detail.
  - `test_get_discoverable_entities_returns_404_for_cold_account` — seed an account but do NOT warm the pool, call GET, assert 404 with the "Run Test Connection first" detail.
  - `test_get_discoverable_entities_returns_200_for_warm_account` — seed account, warm the pool (call `account_acquire` directly in the test), call GET, assert 200 with `entities` populated. The first-call edge case (no cache yet) triggers inline refresh.
  - `test_get_discoverable_entities_returns_503_for_account_type_without_hook` — seed a stub-type account, warm the pool, call GET, assert 503 with the "does not expose discoverable entities" detail.
  - `test_post_refresh_discoverable_entities_returns_200_for_warm_account` — same as GET but via POST refresh. To avoid sub-microsecond flakiness between two successive refreshes, `await asyncio.sleep(0.001)` between the two POSTs and assert `response2.json()["stale_seconds"] >= 0.0` and `response2.json()["fetched_at"] != response1.json()["fetched_at"]` (strict inequality on the ISO string).
  - `test_post_refresh_discoverable_entities_returns_404_for_cold_account` — POST against a cold account, assert 404 with the pre-probe hint.
  - `test_discoverable_entities_response_projects_stale_flag` — populate cache with {A,B,C}; refresh with {A,B}; call GET; assert the response has `peers: [{id:A, stale:false}, {id:B, stale:false}, {id:C, stale:true}]`.

## Acceptance Criteria

### Pool

- [x] `_pool.py` declares `_DISCOVERABLE_REFRESH_INTERVAL_SECONDS: float = 300.0` at module scope, readable from env var `THE_ONE_CONNECTOR_DISCOVERABLE_REFRESH_INTERVAL_SECONDS` (matches `_REAPER_INTERVAL_SECONDS: float = 30.0` precedent at `_pool.py:88`).
- [x] `_RegistryEntry` gains four new fields:
  - `account_type: str = ""` (the connector plugin type — `discord`, `stub`, etc. — populated at entry creation in `account_acquire` / `agent_acquire`).
  - `discoverable_entities_cache: DiscoverableEntities | None = None`.
  - `discoverable_entities_stale_carry: DiscoverableEntities | None = None`.
  - `discoverable_entities_fetched_at_monotonic: float | None = None`.
- [x] `_pool.py` declares `_discoverable_refresh_task: asyncio.Task[None] | None = None` at module scope alongside `_reaper_task`.
- [x] `_pool.py` exports a new async function `_discoverable_refresh_once() -> int` that snapshots `_pool` keys under `_lock` filtered to `key[0] == _ACCOUNT_POOL_AGENT_SLOT AND entry.client is not None AND entry.account_type` is non-empty, calls `_refresh_discoverable_entities_for_account` per snapshot concurrently via `asyncio.gather(..., return_exceptions=True)`, returns the count of successful refreshes. Plugin raises are logged via `logger.warning`, not propagated.
- [x] `_pool.py` exports a new async function `_refresh_discoverable_entities_for_account(account_id: str) -> bool` that:
  - Acquires `_lock`; synthesizes `key = (_ACCOUNT_POOL_AGENT_SLOT, account_id)`. Bails to `False` if entry absent OR `entry.client is None` OR `entry.account_type == ""` OR `entry.client_ready is not None and not entry.client_ready.is_set()`. Otherwise captures `client = entry.client` and `account_type = entry.account_type` and releases the lock.
  - Resolves the plugin via the function-local import `from the_one.connectors.registry import resolve as _resolve_plugin` using the captured `account_type`. Bails to `False` if `ConnectorRegistrationError` raises OR if `getattr(plugin, "enumerate_discoverable_entities", None) is None`.
  - Calls `plugin.enumerate_discoverable_entities(client)` outside the lock, wrapped in try/except. On plugin raise, logs `logger.warning("Discoverable refresh failed for account_id=%s account_type=%s: %r", account_id, account_type, exc)` and returns `False`.
  - Re-acquires `_lock`. Returns `False` if `_shutting_down`. Re-looks up the entry by key; returns `False` if absent OR `_pool[key].client is not client` (identity check, not equality).
  - Reads `prior_cache = _pool[key].discoverable_entities_cache` INSIDE the re-acquired lock (NOT snapshotted at function entry — guards the cycle-1 write-side race).
  - Computes `stale_carry` per-axis as `prior_cache_axis - new_snapshot_axis` by `entity.id`. The retained entities are emitted from `prior_cache_axis` (preserve their old labels/metadata). If `prior_cache is None`, `stale_carry` is an empty `DiscoverableEntities`.
  - Writes `_pool[key].discoverable_entities_cache`, `_pool[key].discoverable_entities_stale_carry`, `_pool[key].discoverable_entities_fetched_at_monotonic`. Does NOT modify `_pool[key].last_activity`.
  - Returns `True`.
- [x] `_pool.py` exports `_discoverable_refresh_loop()` mirroring `_reap_loop`: `while True: await asyncio.sleep(_DISCOVERABLE_REFRESH_INTERVAL_SECONDS); try: await _discoverable_refresh_once(); except Exception: logger.exception(...)`. On `CancelledError`, re-raise (no drain needed).
- [x] `_pool.py` exports `_ensure_discoverable_refresh_running_locked()` that spawns `asyncio.create_task(_discoverable_refresh_loop())` if `_discoverable_refresh_task` is None or done. MUST be called under `_lock` (same precondition as `_ensure_reaper_running_locked`).
- [x] `agent_acquire` (and the wrapping `account_acquire` by delegation) calls `_ensure_discoverable_refresh_running_locked()` inside the cold-entry-creation `if entry is None:` branch (at `_pool.py:~488`, immediately after the existing `_ensure_reaper_running_locked()` call). The refresh task is spawned on cold-entry creation only, NOT on warm-reuse — matches the reaper precedent.
- [x] `shutdown_drain` cancels `_discoverable_refresh_task` alongside `_reaper_task`, awaits it (suppressing `CancelledError`), and resets to `None`.
- [x] `_clear_for_test` (or equivalent) resets `_discoverable_refresh_task` and the cache-related entry fields.
- [x] `_pool.py` declares a new module-private frozen dataclass `_DiscoverableCacheSnapshot(cache, stale_carry, fetched_at_monotonic, account_type)` (all four fields captured atomically under `_lock`).
- [x] `_pool.py` exports a helper `_get_account_cache_snapshot(account_id: str) -> _DiscoverableCacheSnapshot | None` that under `_lock` returns `None` if no warm entry exists for the account_id; otherwise returns a NEW `_DiscoverableCacheSnapshot` with the four fields captured atomically. The handler reads from the returned snapshot outside the lock with no consistency risk.
- [x] Test fixtures that construct `_RegistryEntry` directly without `account_type` (`tests/test_oauth_start_endpoint.py:105`, `tests/test_connectors_pool.py:479`) continue to pass byte-identically — the empty-string default + sweep-filter posture (skip entries where `account_type == ""`) keeps them invisible to the sweep.
- [x] The implementation does NOT change the public signatures of `account_acquire` or `agent_acquire`; the new behavior is internal lifecycle wiring + new helper exports.

### API

- [x] `api.py` import block adds `BaseModel`, `ConfigDict`, `Field` from `pydantic` (extending the existing `from pydantic import ValidationError` line at `api.py:19` or equivalent).
- [x] `api.py` declares an inline Pydantic v2 `BaseModel` subclass `_DiscoverableEntityOut` with fields `id: str`, `label: str`, `group: str | None = None`, `metadata: dict[str, Any] = Field(default_factory=dict)`, `stale: bool = False`. Matches the inline-response-helper precedent at `_mcp_source_response` (`api.py:712`) and `_connector_account_response` (`api.py:2269`).
- [x] `api.py` declares an inline Pydantic v2 `BaseModel` subclass `_DiscoverableEntitiesResponse` with fields `entities: dict[str, list[_DiscoverableEntityOut]]` (nested dict-of-lists matching L3 dataclass shape) + `fetched_at: str` + `stale_seconds: float`.
- [x] `api.py` adds a route `GET /api/connector-accounts/{account_id}/discoverable-entities` returning the response model.
  - [x] Returns 404 with `{"detail": "Connector account not found: {account_id}"}` when the repo lookup fails.
  - [x] Returns 404 with `{"detail": "Run Test Connection first to populate the bot's discoverable view."}` when there is no warm pool entry.
  - [x] Returns 503 with `{"detail": "This connector type does not expose discoverable entities."}` when the plugin has no `enumerate_discoverable_entities` hook.
  - [x] On warm entry with empty cache (first-call edge case), triggers an inline refresh via `_refresh_discoverable_entities_for_account` before responding. **If the refresh returns False** (mid-connect race, evicted-mid-refresh, etc.), responds 200 with empty `_DiscoverableEntitiesResponse` (`fetched_at = datetime.now(UTC).isoformat()`, `stale_seconds = 0.0`, all four axes empty). Fail open per Design Decisions.
  - [x] On warm entry with populated cache, returns the cached snapshot + `stale_seconds = time.monotonic() - fetched_at_monotonic`.
  - [x] Entities from `discoverable_entities_cache` are emitted with `stale: false`; entities from `discoverable_entities_stale_carry` are emitted with `stale: true` and appended to the same axis lists.
- [x] `api.py` adds a route `POST /api/connector-accounts/{account_id}/discoverable-entities/refresh` returning the response model.
  - [x] Same 404 / 503 contracts as GET.
  - [x] On warm entry, calls `_refresh_discoverable_entities_for_account(account_id)` synchronously. If True, re-fetches the cache snapshot and returns it. If False, fails open with empty 200 response (same edge case shape as GET first-call).

### Tests

- [x] `tests/test_connectors_pool.py` grows the 7 new tests enumerated in Outputs.
- [x] `tests/test_api_connector_accounts.py` (new file OR extension of existing) grows the 7 new tests enumerated in Outputs.
- [x] All new tests pass: `docker exec the-one pytest tests/test_connectors_pool.py tests/test_api_connector_accounts.py -x --timeout 30 -q` reports 0 failures.
- [x] Existing tests continue to pass byte-identically: `docker exec the-one pytest tests/test_connectors_pool.py tests/test_connectors_inbound.py tests/test_connectors_discord.py tests/test_connectors_e2e_platform_send.py tests/test_lifespan.py -x --timeout 30 -q` reports 0 failures.

### Cross-cutting

- [x] No JavaScript / frontend code is modified.
- [x] `git diff --stat` shows changes only in `the_one/connectors/_pool.py`, `the_one/interfaces/web/api.py`, `tests/test_connectors_pool.py`, `tests/test_api_connector_accounts.py`, plus F3 sibling artifacts. The `the_one/connectors/base.py` and `the_one/connectors/_discord.py` files are NOT touched (their L3 changes are still uncommitted but L4 doesn't extend them further).
- [x] L1-codified `lifespan-wiring-same-leg-as-installation`: the new task's start (`_ensure_discoverable_refresh_running_locked` call site) AND shutdown (`shutdown_drain` extension) BOTH land in this leg.

## Verification Steps

- `grep -n "_DISCOVERABLE_REFRESH_INTERVAL_SECONDS\|_discoverable_refresh_task\|_discoverable_refresh_loop\|_refresh_discoverable_entities_for_account\|_ensure_discoverable_refresh_running_locked\|discoverable_entities_cache\|discoverable_entities_stale_carry\|discoverable_entities_fetched_at_monotonic\|account_type" the_one/connectors/_pool.py` — each name appears in the expected slot.
- `grep -n "discoverable-entities" the_one/interfaces/web/api.py` — appears in two route declarations (GET + POST refresh).
- `grep -n "_DiscoverableEntitiesResponse\|_DiscoverableEntityOut" the_one/interfaces/web/api.py` — appears in the Pydantic model declarations and endpoint response types.
- `docker exec the-one pytest tests/test_connectors_pool.py -x --timeout 30 -q` — all tests pass; the 7 new tests appear in the run.
- `docker exec the-one pytest tests/test_api_connector_accounts.py -x --timeout 30 -q` — all tests pass; the 7 new tests appear in the run.
- `docker exec the-one pytest tests/test_connectors_pool.py tests/test_connectors_inbound.py tests/test_connectors_discord.py tests/test_connectors_e2e_platform_send.py tests/test_lifespan.py -x --timeout 30 -q` — full pool/connector/lifespan suite passes.
- `git diff --stat` — confirmed surface confined to the four source files + F3 sibling artifacts.

## Implementation Guidance

1. **Read the current state of `_pool.py`** carefully. The `_RegistryEntry` dataclass (L93-120), the module-level state block (L124-145), `_ensure_reaper_running_locked` (L305-316), `_reap_once` / `_reap_loop` (L319-388), `shutdown_drain` (L390-420), and `_clear_for_test` (search for the function). Note the existing logging pattern (`logger.exception` for unexpected errors; the new sweep uses `logger.warning` for routine network errors).

2. **Extend `_RegistryEntry`** at L93-120 with the four new fields. ORDER: `account_type` first (it's existing-state-adjacent — describes the entry's type), then the three cache fields together as a block. Defaults: empty string for `account_type` (backward-compat for any test that constructs entries directly); None for the three cache fields.

3. **Find and update `account_acquire` / `agent_acquire`** at L433+. Both functions create entries — locate the entry-construction line(s) and add `account_type=account.type` to the dataclass kwargs. The `account` variable is already in scope (loaded via `_load_account`).

4. **Add module-level constant + state** alongside the existing reaper-interval block:
   ```python
   _DISCOVERABLE_REFRESH_INTERVAL_SECONDS: float = 300.0
   # Env-var override pattern mirroring _resolve_ttl_seconds — read at module
   # import? or at first-sweep? Verify the existing reaper-interval pattern.
   ```
   Read the existing `_REAPER_INTERVAL_SECONDS` declaration and env-var override pattern; mirror it for the discoverable refresh interval. If the reaper uses a `_resolve_*` function for env-var reads, add a parallel one (e.g., `_resolve_discoverable_refresh_interval()`). If it just uses an int constant with an env-var read at module scope, do the same.

5. **Implement `_refresh_discoverable_entities_for_account(account_id: str) -> bool`** per the Outputs spec. Critical points:
   - First lock acquisition: synthesize `key = (_ACCOUNT_POOL_AGENT_SLOT, account_id)`. Bail with `False` if entry absent OR `entry.client is None` OR `entry.account_type == ""` OR `entry.client_ready is not None and not entry.client_ready.is_set()`. Otherwise capture `client = entry.client` and `account_type = entry.account_type`.
   - Look up the plugin OUTSIDE the lock via `from the_one.connectors.registry import resolve as _resolve_plugin` (function-local import is the section's convention) using the captured `account_type`. Wrap in try/except for `ConnectorRegistrationError` (bail with False if unknown type).
   - Bail with `False` if `getattr(plugin, "enumerate_discoverable_entities", None) is None`.
   - Call `new_snapshot = plugin.enumerate_discoverable_entities(client)` outside the lock. SYNC call. Wrap in try/except — on plugin raise, log `logger.warning("Discoverable refresh failed for account_id=%s account_type=%s: %r", account_id, account_type, exc)` and return False.
   - Re-acquire `_lock`. **Shutdown check**: `if _shutting_down: return False`. **Identity check**: `current = _pool.get(key); if current is None or current.client is not client: return False`. (The `is not` identity check is the use-after-evict guard.)
   - Read `prior_cache = current.discoverable_entities_cache` INSIDE this re-acquired lock (NOT snapshotted from the first lock acquisition — this guards the write-side race).
   - Compute stale_carry per axis: for each of `peers`, `channels`, `groups`, `roles`, take the set of ids in `prior_cache.<axis>` minus the set of ids in `new_snapshot.<axis>`; emit the entities from `prior_cache.<axis>` whose id is in that set (retained entities preserve their old labels/metadata). If `prior_cache is None`, emit empty lists for every axis.
   - Write the three cache fields on `current`; do NOT touch `current.last_activity`. Return True.

6. **Implement `_discoverable_refresh_once()`** per the Outputs spec, mirroring `_reap_once`.

7. **Implement `_discoverable_refresh_loop()`** per the Outputs spec, mirroring `_reap_loop` (no drain on cancel).

8. **Implement `_ensure_discoverable_refresh_running_locked()`** per the Outputs spec, mirroring `_ensure_reaper_running_locked`.

9. **Wire the spawn**: in `account_acquire` (and possibly `agent_acquire` if it should also spawn — see existing `_ensure_reaper_running_locked` call site), call `await _ensure_discoverable_refresh_running_locked()` directly after the existing reaper-spawn call. Same lock block; same execution path.

10. **Wire the shutdown**: extend `shutdown_drain` to cancel `_discoverable_refresh_task` alongside `_reaper_task`. Same cancel-suppress-await-reset shape.

11. **Wire the test-clear**: extend `_clear_for_test` (or whatever the existing teardown helper is named) to also reset `_discoverable_refresh_task` and to walk all `_RegistryEntry`s resetting the new cache fields.

12. **Add the `_get_account_cache_snapshot(account_id)` helper** to `_pool.py` for the API endpoints to consume:
    ```python
    async def _get_account_cache_snapshot(
        account_id: str,
    ) -> _DiscoverableCacheSnapshot | None:
        """Return an immutable frozen-triple snapshot of the warm pool entry's
        cache fields, captured atomically under _lock. Readable outside the
        lock with no consistency risk — the snapshot is by-value, not a live
        entry reference.

        Returns None if no warm entry exists for account_id (the account is
        cold; the operator must run Test Connection first).
        """
        key = (_ACCOUNT_POOL_AGENT_SLOT, account_id)
        async with _lock:
            entry = _pool.get(key)
            if entry is None or entry.client is None:
                return None
            return _DiscoverableCacheSnapshot(
                cache=entry.discoverable_entities_cache,
                stale_carry=entry.discoverable_entities_stale_carry,
                fetched_at_monotonic=entry.discoverable_entities_fetched_at_monotonic,
                account_type=entry.account_type,
            )
    ```
    The handler reads `snapshot.cache`, `snapshot.stale_carry`, `snapshot.fetched_at_monotonic`, `snapshot.account_type` outside the lock — they are immutable fields on a frozen dataclass.

13. **In `api.py`**, declare the Pydantic response models inline near the other connector-account models. Use Pydantic 2 syntax (matches the project's existing models). The `_DiscoverableEntityOut` model converts `DiscoverableEntity` instances to JSON-friendly form; the `stale` field is projected by the endpoint handler, NOT pulled from the dataclass.

14. **Implement the GET endpoint**. Function-local import of `_resolve_plugin` per the section's convention. Logic flow:
    a. `repo.get(account_id)` → KeyError → 404 "Connector account not found".
    b. `_get_account_cache_snapshot(account_id)` → None → 404 with pre-probe hint.
    c. Resolve plugin; check for hook; if absent → 503.
    d. If `entry.discoverable_entities_cache is None` → call `_refresh_discoverable_entities_for_account` inline; bail to 503 if helper returns False after the hook check (defensive — should not happen if hook check passed).
    e. Build response: union cache + stale_carry per axis, emit each with `stale: bool` projected. Compute `stale_seconds`. Return.

15. **Implement the POST refresh endpoint**. Same 404/503 logic; always call `_refresh_discoverable_entities_for_account` (synchronous refresh, regardless of whether cache is populated).

16. **Add tests**. For pool tests, use the existing `pool_mod._clear_for_test` autouse fixture pattern. For API tests, use the `AsyncClient(ASGITransport(app=FastAPI))` pattern from `tests/test_api_connector_account_config_validation.py:24-58`.

   **Pool-warming pattern for API tests**: the new API tests need to warm the pool BEFORE hitting the endpoint. Use option (a) — call `account_acquire(account_id)` directly inside the async test after registering a stub plugin (mirror the pool-test fixture pattern at `tests/test_connectors_pool.py:130-146` for plugin registration). Option (b) — directly inserting a `_RegistryEntry` into `_pool` — bypasses the lifecycle wiring and is rejected. The plugin stub must implement `enumerate_discoverable_entities` for "warm" tests and OMIT it for "503" tests.

17. **Run tests**:
    - `docker exec the-one pytest tests/test_connectors_pool.py -x --timeout 30 -q` — pool layer.
    - `docker exec the-one pytest tests/test_api_connector_accounts.py -x --timeout 30 -q` — API layer.
    - Broader suite: `docker exec the-one pytest tests/test_connectors_pool.py tests/test_connectors_inbound.py tests/test_connectors_discord.py tests/test_connectors_e2e_platform_send.py tests/test_lifespan.py -x --timeout 30 -q`.

18. **Sibling artifact bookkeeping**. Check off L4 in flight.md; append L4 entry to flight-log.md.

19. **Update leg status**. `ready → in-flight → landed`. Do NOT commit; do NOT signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`entry.client is None`**: an entry mid-creation has no client yet. The sweep filters these out by checking `entry.client is not None` before snapshotting. The GET endpoint similarly bails with 404 (pre-probe hint) if `entry.client is None`.

- **Account type unknown to registry**: if `entry.account_type` is set to a string the registry doesn't recognize, `registry.resolve` raises `ConnectorRegistrationError`. The sweep helper catches this via the outer `asyncio.gather(..., return_exceptions=True)` mechanism + the per-call try/except inside `_refresh_discoverable_entities_for_account` (add this defensive try/except around the registry resolve). Logs `logger.warning`.

- **Plugin hook raises**: the sync hook may raise (e.g., `discord.Client` SDK objects in an unexpected state). The sweep helper catches via the same gather pattern; logs `logger.warning("Discoverable refresh failed for account_id=%s: %r", key[1], exc)`. The entry's cache is NOT modified.

- **First-call inline refresh races with the sweep**: the GET endpoint may call `_refresh_discoverable_entities_for_account` inline at the same moment the periodic sweep is running. Both call paths re-acquire `_lock` for the write-back; the second writer's `stale_carry` may overwrite the first's. This is fine — both write a structurally-consistent cache+stale_carry pair; the operator's render is at most one refresh-cycle behind regardless.

- **Stale-carry size growth**: the stale-carry is bounded by the previous cache's size. In the worst case (every entity disappears between two cycles), stale-carry equals previous cache. After one more cycle of absence, all stale entries drop. No unbounded accumulation.

- **`_DEFAULT_TTL_SECONDS` vs `_DISCOVERABLE_REFRESH_INTERVAL_SECONDS`**: at default values (1800 = 30 min idle TTL; 300 = 5 min refresh), the refresh interval is shorter than the idle TTL. This is the Architect cycle-1 race condition that the "do NOT touch last_activity" rule prevents. If an operator sets the refresh interval LONGER than the TTL via env var, the cache may be stale by the time it's read — but that's an operator-chosen tradeoff, not a correctness bug.

- **POST refresh while sweep is in flight**: same race as the first-call inline refresh edge case; same resolution. Both paths' re-acquire-lock-and-write-back is the serialization point.

- **Plugin returns DiscoverableEntities with duplicate ids within an axis**: the sweep does not de-dup at the cache level; it stores the snapshot as-returned. The plugin (L3 Discord impl) already de-dups by id for `peers`. Other plugins' contracts are their own responsibility.

- **`account_type` field added with default `""`**: tests that construct `_RegistryEntry` directly without specifying `account_type` get the empty-string default. The sweep filters these out (`entry.account_type` non-empty check). Production code always populates it.

- **F2's `account_acquire` / `agent_acquire` semantics are unchanged**: this leg DOES NOT modify the public API of the F2-shipped pool primitives. It adds internal lifecycle wiring (sibling task spawn) and new helper exports for the API endpoints. Pre-F4 callers see byte-identical behavior.

- **First-call inline refresh fires pre-READY**: see Design Decision "fail open on first-call empty refresh." If the gateway READY has not populated the SDK caches by the time the GET endpoint fires the inline refresh, the hook returns empty axes. The endpoint returns 200 with empty axes. Operator UX: first dropdown-open immediately after Test Connection may show empty axes for ≤ 5 minutes; manual Refresh button is the recovery path; periodic sweep also recovers.

## Files Affected

- `the_one/connectors/_pool.py` — extended with cache fields on `_RegistryEntry`, new sweep / loop / lifecycle functions, the API helper.
- `the_one/interfaces/web/api.py` — extended with the two new endpoints + Pydantic response models.
- `tests/test_connectors_pool.py` — extended with 7 new tests.
- `tests/test_api_connector_accounts.py` — NEW file (or extension of existing); 7 new tests.
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight.md` — L4 checkpoint + L4 leg checklist item checked off.
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight-log.md` — L4 leg-progress entry appended.
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/legs/04-discoverable-entities-cache-and-api.md` — this artifact's status header progresses.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Pool tests pass: `docker exec the-one pytest tests/test_connectors_pool.py -x --timeout 30 -q` with the 7 new tests present
- [x] API tests pass: `docker exec the-one pytest tests/test_api_connector_accounts.py -x --timeout 30 -q` with the 7 new tests present
- [x] Broader suite passes: `docker exec the-one pytest tests/test_connectors_pool.py tests/test_connectors_inbound.py tests/test_connectors_discord.py tests/test_connectors_e2e_platform_send.py tests/test_lifespan.py -x --timeout 30 -q`
- [x] Update `flight-log.md` with L4 leg-progress entry
- [x] Set this leg's status to `landed`
- [x] Check off L4 in `flight.md` (Checkpoints + Legs sections)
- [x] Do NOT commit (F3 batches review + commit at flight end)
