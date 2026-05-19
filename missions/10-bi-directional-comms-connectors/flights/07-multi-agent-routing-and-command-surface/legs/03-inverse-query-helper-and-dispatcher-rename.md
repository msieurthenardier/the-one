# Leg: inverse-query-helper-and-dispatcher-rename

**Status**: landed
**Flight**: [Multi-Agent Routing and the Platform-Side Command Surface](../flight.md)

## Objective

Land two atomic primitives that L4 (routing engine) and L5 (dispatcher integration) need: (i) `SQLiteAgentStore.list_by_connector_account(account_id) -> list[AgentConfig]` (the flight.md spec calls the class `AgentConfigRepository` — that was a planning-time naming error; the actual class is `SQLiteAgentStore` at `the_one/db/repositories.py:69`. L3 uses the correct name; flight.md will be updated retroactively in the flight debrief.) — the inverse-query helper that scans `agents` rows whose `connector_account_ids` JSON list contains the given account id, returns the list alphabetically ordered by agent name; (ii) mechanical rename of `connectors/_inbound.dispatch_inbound` to drop the `agent_name` first parameter, introduce a transitional helper `_resolve_single_attached_agent_or_first_alphabetical(account_id)` that derives the target agent via the new repository helper, and migrate all ~55 test-fixture call sites mechanically. Migrate the `_seed_provider_and_agent` test helper's default so the helper finds the agent without per-call kwarg additions. The transitional helper lands now and is REMOVED in L5 when the routing engine replaces it. F1–F7 (post-L2) regression suite passes byte-identically.

## Context

This is the third F7 leg. Per Design Decisions in `flight.md`:

- **"Drop `agent_name` from `dispatch_inbound` signature — mechanical rename leg lands first"** — the dispatcher's contract becomes "given an account_id and an envelope, dispatch correctly." The caller (the plugin's inbound adapter; today only tests) no longer needs to know agent topology. F7 L5 will replace the transitional helper with the routing engine's decision.
- **"Inverse-query mechanism for attached agents — `SQLiteAgentStore.list_by_connector_account`"** — adding a repository method lifts the iteration to the repository layer; the routing engine and dispatcher stay pure. One method, one test.
- **"Fixture-audit step in L3 design (NOT optional)"** — the flight spec demands an audit of all ~55 dispatch_inbound call sites partitioned into three buckets:
  - (a) single-attached fixture where alphabetical-first picks the same agent the test passed → helper is byte-correct
  - (b) multi-attached fixture where the test-passed agent IS the alphabetical-first → helper is byte-correct
  - (c) multi-attached fixture where the test-passed agent is NOT the alphabetical-first → fixture must be migrated (set `session_metadata["routing_override"]` or reduce to single-attached)
- **Fixture audit result** (verified at leg design time via grep):
  - **Bucket (a): 53 call sites.** All pass `"agent-inbound"` as the first arg; the seeded agent name is `"agent-inbound"`; the only attached agent. After fixture migration (see below), alphabetical-first picks `"agent-inbound"`. Helper produces byte-identical agent selection.
  - **Bucket (b): 0 call sites.** No test fixtures seed multiple agents on a single account.
  - **Bucket (c): 0 call sites.** No migration of `session_metadata["routing_override"]` needed.
  - **Special: 2 failure-path call sites** (`acct-mystery` unknown connector type; `non-existent` account-not-found). The current tests assert observable behavior — `dispatch_inbound` returns gracefully and no session row is created — not the specific error path. After L3, these tests still satisfy the same observable assertions, but the failure mode shifts from "pool.acquire raises KeyError" to "no attached agents for this account → dispatcher logs and returns." Tests do NOT need migration; observable behavior is preserved.
- **Fixture default update** — `tests/_connector_dispatch_helpers._seed_provider_and_agent`'s default `connector_account_ids: list[str] | None = None` becomes `connector_account_ids: list[str] | None = None` with `None` resolving to `["acct-test"]` (matches `_seed_stub_account`'s default `account_id="acct-test"` and `_envelope()`'s default `account_id="acct-test"`). The 14 tests that already pass `connector_account_ids=["acct-test"]` explicitly continue to work (redundant but byte-identical); the 29 tests that bare-call `_seed_provider_and_agent()` now get the attachment for free. Tests that need a different account (`acct-A`) still pass it explicitly.
- **L3 unblocks L4 / L5** — L4 consumes `list_by_connector_account` for "eligible attached agents"; L5 replaces the transitional helper with the routing-engine pick.

Key learnings from prior legs (from the flight log):

- L1: `runtime_checkable` Protocol stdlib check is NAME-only — L3 does NOT depend on this, but the `dispatch_inbound` signature change is a hard contract break for any future plugin that imports the function with the old signature (production currently has zero callers; only tests).
- L2: The reason-string vocabulary is "reachable" outbound (F6 verbatim) / "admitted" inbound (new). L3 introduces NO new operator-facing strings — the transitional helper's error path is internal (logged, not surfaced).
- F6: per-axis tri-state semantic for `connector_acls` — L3 does NOT touch this; the inverse-query helper returns the full `AgentConfig`, callers (L5) consult `.connector_acls` themselves.
- F4 L5: `agents.connector_account_ids` persisted via v17 migration; round-trip via `_row_to_config` at `db/repositories.py:216`. The new repository helper consumes the same column.

## Inputs

What exists before this leg runs:

- `the_one/db/repositories.py:75-85` — `SQLiteAgentStore.list_agents()` and `list_by_provider(provider_config_id)` precedents. The new helper mirrors `list_by_provider`'s style: SQL → row decode → return list. Differs only in that the filter is on a JSON-list column (Python-side post-filter, not a WHERE clause).
- `the_one/db/repositories.py:216` — `_row_to_config(row)` decodes `agents.connector_account_ids` as `json.loads(row["connector_account_ids"] or "[]")`. The new helper reuses this method.
- `the_one/connectors/_inbound.py:77-200` — `dispatch_inbound(agent_name, account_id, envelope, *, factory)` current signature; pool acquires for `(agent_name, account_id)`; existing failure paths return silently on pool acquire / account-load / plugin-resolve errors via try/except blocks at lines 110-128 / 149-156 / 166-175.
- `tests/_connector_dispatch_helpers.py:76-115` — `_seed_provider_and_agent(*, agent_name="agent-inbound", provider_id="mock-provider", response_content="ok", connector_account_ids=None)`. Default `connector_account_ids or []` → seeds with `[]`.
- `tests/_connector_dispatch_helpers.py:118-142` — `_seed_stub_account(account_id="acct-test", ...)`.
- `tests/_connector_dispatch_helpers.py:156-174` — `_envelope(..., account_id="acct-test", ...)`.
- 55 test fixture call sites of `dispatch_inbound` (verified via `grep -rn "dispatch_inbound\s*(" tests/ | wc -l`).
- 42 test fixture call sites of `_seed_provider_and_agent` (verified via grep); 29 of which bare-call without `connector_account_ids` kwarg.
- F1–F7 (post-L2) test suite green: `docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py -x --timeout 30'` returns 267 passed.

## Outputs

What exists after this leg completes:

- `the_one/db/repositories.py` with new method `SQLiteAgentStore.list_by_connector_account(account_id: str) -> list[AgentConfig]`. Returns the list alphabetically ordered by agent name (mirrors `list_by_provider`'s `ORDER BY name`). Empty list for unknown account.
- `the_one/connectors/_inbound.py` with:
  - `dispatch_inbound` signature changed from `(agent_name, account_id, envelope, *, factory)` to `(account_id, envelope, *, factory)`.
  - New helper `_resolve_single_attached_agent_or_first_alphabetical(account_id)` that consults the new repository helper, returns the first alphabetical agent name, or `None` if no agents attached.
  - Dispatcher early-returns silently when the helper returns `None` (no attached agents — observable parity with the existing "no exception, no session" failure paths).
- `tests/_connector_dispatch_helpers.py` with `_seed_provider_and_agent`'s default `connector_account_ids` updated to `["acct-test"]` (resolved when caller passes `None`). Docstring updated to document the new default + rationale.
- All 55 dispatch_inbound test-fixture call sites migrated to the new signature (mechanical; first arg dropped).
- `tests/test_db_repositories.py` extended with tests for `list_by_connector_account` (empty / single attached / multiple attached / alphabetical / unknown account).
- F1–F7 (post-L2) regression suite passes byte-identically; the 267-test count stays the same except for the new repository-helper tests added.

## Acceptance Criteria

- [ ] `SQLiteAgentStore.list_by_connector_account(account_id: str) -> list[AgentConfig]` ships at `the_one/db/repositories.py` adjacent to `list_by_provider` (lines 79-85). Behavior:
  - SQL: `SELECT * FROM agents ORDER BY name` (mirror `list_by_provider`'s ORDER BY).
  - Python-side filter: for each row, decode via `_row_to_config`; keep rows where `account_id in config.connector_account_ids`.
  - Returns the filtered list (alphabetical by virtue of the SQL ORDER BY).
  - Returns `[]` for unknown account (no rows with that account in their list); does NOT raise.
  - Docstring mirrors `list_by_provider`'s tone; cites M10 F7 L3.
- [ ] `connectors/_inbound.dispatch_inbound` signature changed:
  - From: `async def dispatch_inbound(agent_name: str, account_id: str, envelope: InboundEnvelope, *, factory: AgentFactory) -> None`
  - To: `async def dispatch_inbound(account_id: str, envelope: InboundEnvelope, *, factory: AgentFactory) -> None`
  - Docstring updated: dispatcher's contract is now "given an account_id and an envelope, dispatch correctly"; F7 L3 transitional helper derives the agent_name until F7 L5's routing engine takes over.
- [ ] New helper `_resolve_single_attached_agent_or_first_alphabetical(account_id: str) -> str | None` at module-private scope in `connectors/_inbound.py`. Behavior:
  - Loads the connection + creates `SQLiteAgentStore`; consults `list_by_connector_account(account_id)`.
  - Returns the first element's `name` if non-empty; returns `None` if empty.
  - Docstring documents: "transitional — F7 L3 only; F7 L5 replaces with routing-engine pick."
  - Function-local imports for `the_one.db.connection`, `the_one.db.repositories` (same pattern as `tools/connector_send.py:153-156`'s cycle-break).
- [ ] Dispatcher body wires the helper at the entry point — BEFORE pool.acquire — and handles the `None` case via early silent return + log entry. Mirror the existing failure-path style at `_inbound.py:99-107`:
  ```python
  agent_name = await _resolve_single_attached_agent_or_first_alphabetical(account_id)
  if agent_name is None:
      logger.info(
          "dispatch_inbound: no agents attached to account_id=%s; "
          "ignoring inbound",
          account_id,
      )
      return
  ```
- [ ] `tests/_connector_dispatch_helpers._seed_provider_and_agent` default updated:
  - Signature: same as before; `connector_account_ids: list[str] | None = None`.
  - Resolution: when `connector_account_ids is None`, the helper uses `["acct-test"]` (NOT `[]`).
  - Existing explicit-`[]` callers, if any, are byte-identical pre/post (no change in semantics for explicit empty list).
  - Existing explicit-non-default-account callers (`["acct-test"]`, `["acct-A"]`) are byte-identical pre/post.
  - Docstring updated to document the new default + rationale (matches `_seed_stub_account`'s default account id + `_envelope`'s default account id).
- [ ] All 55 `dispatch_inbound` test-fixture call sites migrate to the new signature mechanically:
  - Drop the first arg (always `"agent-inbound"` per audit; the `non-existent`/`acct-mystery` cases passed `"agent-inbound"` as the first arg too — they drop just like the rest).
  - Multi-line call sites are updated to the new 3-arg-plus-kwarg shape.
  - No semantic changes to test bodies beyond the signature migration.
- [ ] `tests/test_db_repositories.py:101` `TestSQLiteAgentStore` class extended with:
  - `test_list_by_connector_account_empty_for_unknown_account` — returns `[]`.
  - `test_list_by_connector_account_single_attached` — seed one agent attached to `acct-1`, returns 1-element list.
  - `test_list_by_connector_account_multi_attached_alphabetical_order` — seed `zebra`, `alpha`, `marlin` attached to same account; returns `[alpha, marlin, zebra]`.
  - `test_list_by_connector_account_filters_by_account` — seed `alice` attached to `acct-1`, `bob` attached to `acct-2`; `list_by_connector_account("acct-1")` returns `[alice]` only.
  - `test_list_by_connector_account_round_trips_full_config` — seed an agent with `connector_account_ids=["acct-1"]` and various other config fields populated; the returned `AgentConfig` round-trips through `_row_to_config` byte-identically.
  - `test_list_by_connector_account_single_agent_multi_attached` — seed one agent with `connector_account_ids=["acct-1", "acct-2"]`; assert it appears in BOTH `list_by_connector_account("acct-1")` AND `list_by_connector_account("acct-2")`. (Pins the Edge Cases bullet on multi-account-attached agents.)
- [ ] Refactor `the_one/interfaces/web/api.py:list_attached_agents_for_connector_account` (lines 2331-2389) to call the new `SQLiteAgentStore.list_by_connector_account` helper instead of the inline `store.list_agents() → load each → filter` pattern. The endpoint's response shape (`{name, peers, channels, peers_count, channels_count}` per agent) and HTTP test coverage are unchanged — only the iteration source moves to the helper. Confirms reuse + validates the helper under existing integration tests on the same commit.
- [ ] F1–F7 (post-L2) regression suite passes byte-identically PLUS the new repository tests pass:
  ```
  docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py -x --timeout 30'
  ```
  Expected: 267 (post-L2 connector + tool tests) + 5 new repository tests + existing `test_db_repositories.py` tests = previous total + 5.
- [ ] No new files outside `tests/test_db_repositories.py` extensions (which add tests, not files). NO change to `the_one/connectors/__init__.py` re-exports (transitional helper is private; new repository method is on an existing class). No schema migration. No documentation drift — `agents.md`'s connector subsystem section already describes the inverse relationship; no new convention.

## Verification Steps

How to confirm each criterion is met:

**Repository helper** (in `tests/test_db_repositories.py`):

- Test that builds 1 agent with `connector_account_ids=["acct-1"]` + 1 agent with `connector_account_ids=["acct-2"]`. Asserts `list_by_connector_account("acct-1") == [<agent attached to acct-1>]`.
- Test that builds 3 agents with same account attached, names `zebra`, `alpha`, `marlin`. Asserts return is `[alpha, marlin, zebra]` (alphabetical).
- Test that builds 0 agents (or builds agents attached to other accounts). Asserts `list_by_connector_account("nonexistent") == []`.
- Test that builds 1 agent with multiple `connector_account_ids` (e.g. `["acct-1", "acct-2"]`). Asserts the agent appears in both `list_by_connector_account("acct-1")` AND `list_by_connector_account("acct-2")`.
- Round-trip test: build an agent with non-default fields populated (`description`, `tool_overrides`, `connector_acls`); confirm the returned `AgentConfig` carries every field through.

**Dispatcher signature** (regression):

- All 55 migrated dispatch_inbound call sites compile (test collection succeeds).
- All migrated test bodies pass (the new helper picks `"agent-inbound"` because the fixture default attaches the agent to `acct-test` and `"agent-inbound"` is the only attached agent).
- `test_dispatch_inbound_account_not_found_returns_gracefully` still asserts no exception + no session. The failure now triggers on the new helper's empty-attachment branch instead of pool.acquire — but the observable outcome is byte-identical.
- `test_dispatch_inbound_unknown_connector_type_returns_gracefully` same as above.
- Sentinel grep: `grep -n "def dispatch_inbound" the_one/connectors/_inbound.py` shows the new 3-param signature; no remnants of the old 4-param shape.
- `grep -rn "dispatch_inbound\s*(.*agent-inbound" tests/` returns zero hits (no test still passes "agent-inbound" as a first arg to dispatch_inbound).

**Fixture-helper default**:

- `python -c 'from inspect import signature; from tests._connector_dispatch_helpers import _seed_provider_and_agent; print(signature(_seed_provider_and_agent))'` shows `connector_account_ids: list[str] | None = None` (signature unchanged; only resolution semantic changed).
- New test `test_seed_provider_and_agent_default_attaches_to_acct_test` in `tests/test_db_repositories.py`'s `TestSQLiteAgentStore` class: bare-call `_seed_provider_and_agent()`; assert `(await store.load("agent-inbound")).connector_account_ids == ["acct-test"]`. Pins the new default semantic in a stable location (not the helper module itself).

**Regression**:

- `docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py -x --timeout 30'` — full suite green. Connector test count stays at 267 (or matches the post-L2 baseline + the L3 repository tests).

## Implementation Guidance

### 1. New repository helper

Add to `the_one/db/repositories.py` adjacent to `list_by_provider` (current lines 79-85). Place after `list_by_provider`:

```python
    async def list_by_connector_account(
        self, account_id: str
    ) -> list[AgentConfig]:
        """Return agent configs attached to ``account_id``.

        M10 F7 L3: inverse-query for the routing engine (F7 L4) and the
        dispatcher integration (F7 L5). Returns the list alphabetically
        ordered by ``AgentConfig.name`` (via the SQL ``ORDER BY``).

        ``connector_account_ids`` is a JSON-encoded list column (F4 L5
        v17 migration). Filtering is Python-side after a full table
        scan — the agents table is operator-scale (tens, not millions),
        so the linear scan is acceptable. If this becomes a hot path
        a later mission can add a join table (or use SQLite's JSON1
        ``json_each``).

        Returns ``[]`` for unknown account; does NOT raise.
        """
        async with self.conn.execute(
            "SELECT * FROM agents ORDER BY name"
        ) as cur:
            rows = await cur.fetchall()
        result: list[AgentConfig] = []
        for row in rows:
            config = self._row_to_config(row)
            if account_id in config.connector_account_ids:
                result.append(config)
        return result
```

### 2. Dispatcher rename + transitional helper

Update `the_one/connectors/_inbound.py`. Add the transitional helper just above `dispatch_inbound`:

```python
async def _resolve_single_attached_agent_or_first_alphabetical(
    account_id: str,
) -> str | None:
    """Transitional agent-selection helper — F7 L3 only.

    Consults :meth:`SQLiteAgentStore.list_by_connector_account` and
    returns the first (alphabetically-ordered) attached agent's name.
    Returns ``None`` when no agents are attached — the dispatcher
    treats this as a silent-ignore case (no exception, no session).

    F7 L5 will replace this helper with the routing engine's pick
    (override → rule-walk → default → first-eligible → no-eligible).
    The helper is removed in L5 once the routing engine is wired.

    Function-local imports break a connectors→db cycle the same way
    ``tools/connector_send.py`` does.
    """
    from the_one.db.connection import get_connection
    from the_one.db.repositories import SQLiteAgentStore

    conn = await get_connection()
    repo = SQLiteAgentStore(conn)
    attached = await repo.list_by_connector_account(account_id)
    if not attached:
        return None
    return attached[0].name
```

Change `dispatch_inbound`'s signature and insert the helper call at the top of the body:

```python
async def dispatch_inbound(
    account_id: str,
    envelope: InboundEnvelope,
    *,
    factory: AgentFactory,
) -> None:
    """Dispatch a single inbound envelope through the full pipeline.

    M10 F7 L3 rename: the dispatcher's contract is "given an
    ``account_id`` and an ``envelope``, dispatch correctly." The
    caller (the plugin's inbound adapter; today only tests) no longer
    needs to know agent topology — the dispatcher resolves the target
    agent via the L3 transitional helper, which F7 L5 will replace
    with the routing engine's pick.

    ... [rest of existing docstring, with the ``agent_name`` param doc
    removed and the new flow noted]
    """
    agent_name = await _resolve_single_attached_agent_or_first_alphabetical(account_id)
    if agent_name is None:
        logger.info(
            "dispatch_inbound: no agents attached to account_id=%s; "
            "ignoring inbound",
            account_id,
        )
        return

    # ... existing body unchanged from here ...
```

The rest of the body (pool.acquire, account load, plugin resolve, session resolve, resolver consult, per-session lock, agent.step) uses the locally-derived `agent_name` exactly as today.

### 3. Test-fixture helper default update

Update `tests/_connector_dispatch_helpers.py:76-115`:

```python
async def _seed_provider_and_agent(
    *,
    agent_name: str = "agent-inbound",
    provider_id: str = "mock-provider",
    response_content: str = "ok",
    connector_account_ids: list[str] | None = None,
) -> None:
    """Seed an LLM provider + agent config so ``AgentFactory.create()``
    has something to build against. Uses ``type='mock'`` so the LLM
    registry resolves to :class:`the_one.llm.mock.MockProvider`.

    ``connector_account_ids`` opts the agent into the F4 L3 connector
    carve-out (loads ``send_to_platform_channel`` into the baseline-
    visible tool set + injects the connector-aware system-prompt
    directive). F4 L5 v17 migration persists this list; ``factory.create``
    now sees it on every invocation without a monkeypatch.

    M10 F7 L3: the default (when ``connector_account_ids`` is ``None``)
    is ``["acct-test"]`` — matches :func:`_seed_stub_account`'s default
    ``account_id="acct-test"`` and :func:`_envelope`'s default
    ``account_id="acct-test"``. The default attachment is required for
    F7 L3's transitional dispatcher helper to find the agent via
    :meth:`SQLiteAgentStore.list_by_connector_account`. Tests that
    need an empty attachment list pass ``connector_account_ids=[]``.
    """
    if connector_account_ids is None:
        connector_account_ids = ["acct-test"]
    # ... rest unchanged ...
```

The inline assignment replaces the old `connector_account_ids or []` resolver inside the `AgentConfig(...)` constructor. (Inline before, so the rest of the body uses the resolved list verbatim.)

### 4. Mechanical migration of 55 call sites

Each call site changes:
- `await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)` → `await dispatch_inbound("acct-test", envelope, factory=factory)`.
- Multi-line call sites: drop the first positional argument.

Files affected (all in `tests/`):
- `tests/test_connectors_inbound.py` — 34 call sites.
- `tests/test_connectors_inbound_broadcast.py` — 10 call sites.
- `tests/test_connectors_e2e_session.py` — 3 call sites.
- `tests/test_connectors_e2e_platform_send.py` — 8 call sites.
- (`tests/test_connectors_e2e_ws_into_connector.py` has 0 `dispatch_inbound` call sites — does not import the function; not affected.)

Total: 55 call sites.

No semantic changes to test bodies. Single-pass sed or careful Edit calls.

### 5. New repository tests

Add to `tests/test_db_repositories.py` adjacent to existing `TestSQLiteAgentStore` (or wherever the file groups `SQLiteAgentStore` tests). 5 tests per Acceptance Criteria. Use the existing `isolated_db` fixture (or whatever fixture the file uses for SQLite isolation).

### 6. Order of file edits

1. `the_one/db/repositories.py` — add `list_by_connector_account`.
2. `tests/test_db_repositories.py` — add 5 tests; confirm they pass standalone via `docker exec the-one pytest tests/test_db_repositories.py::TestSQLiteAgentStore::test_list_by_connector_account_empty_for_unknown_account -v`.
3. `tests/_connector_dispatch_helpers.py` — update `_seed_provider_and_agent` default.
4. `the_one/connectors/_inbound.py` — add transitional helper + rename + early-return.
5. Mechanical fixture migration: `tests/test_connectors_inbound.py`, `tests/test_connectors_inbound_broadcast.py`, `tests/test_connectors_e2e_session.py`, `tests/test_connectors_e2e_platform_send.py`, `tests/test_connectors_e2e_ws_into_connector.py`. Run after each file for quick feedback: `docker exec the-one pytest tests/<file> -x --timeout 30`.
6. Full regression: `docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py -x --timeout 30'`.

### 7. Function-local imports note

`_resolve_single_attached_agent_or_first_alphabetical` is a module-level function ABOVE `dispatch_inbound`. The existing `dispatch_inbound` body has its own function-local imports for `get_connection` / repositories at `_inbound.py:137-142` — those do NOT migrate to the new helper. The new helper carries its own function-local imports per the cycle-break convention. Two functions, two import blocks, same convention.

### 8. Things NOT in scope for this leg

- Routing engine (L4 — `connectors/_routing.py` lands in L4).
- Routing-rule consultation in the dispatcher (L5).
- Command parser / handler integration in the dispatcher (L5).
- Per-agent ACL inbound check via `admits_inbound` in the dispatcher (L5).
- Removal of the transitional helper (L5).
- Studio editor (L7).
- The repository helper is NOT re-exported from any package's `__init__.py` — it's a method on the existing class, accessed via the canonical `from the_one.db.repositories import SQLiteAgentStore`.

## Edge Cases

- **Agent with empty `connector_account_ids`**: the new helper does NOT return it for any account. This is the pre-L3 default state for 29 fixture-tests; after the fixture default update they all attach to `"acct-test"`.
- **Agent attached to multiple accounts**: appears in `list_by_connector_account` results for each. Pinned by test 4 above.
- **Account doesn't exist in the accounts table but is listed in some agent's `connector_account_ids`**: the helper returns the agent anyway (it's filtering by the agent's denormalized list, not joining to accounts). This is OK — `dispatch_inbound`'s subsequent `pool.acquire` will fail on the missing account and return silently via the existing error path. No special handling needed in L3.
- **Concurrent agent attachment changes**: the helper is read-only and snapshots at call time. If an attachment is added mid-dispatch, the in-flight dispatch uses the snapshot; the next dispatch sees the updated state. No locking required — same pattern as F4's `connector_account_ids` resolution.
- **Special tests (`non-existent`, `acct-mystery`)**: the helper returns `None`; dispatcher early-returns silently. Observable behavior (`no exception, no session created`) preserved. NOTE: the existing failure-path tests at `tests/test_connectors_inbound.py:935-990` may have docstrings that mention "pool.acquire raises KeyError" — the docstring is no longer accurate post-L3 since the dispatcher returns BEFORE pool.acquire on the no-attached-agents path. The docstrings should be updated to reflect the new failure source ("no attached agents → dispatcher logs and returns"), but the test bodies themselves don't change.
- **Transitional helper's empty-list signal**: returning `None` vs raising. The leg picks `None` because the caller (the dispatcher) needs to log a single message and silently return — `None` keeps the error path narrow and matches the existing failure-path style (no exception, no session row).

## Files Affected

- `the_one/db/repositories.py` — add `SQLiteAgentStore.list_by_connector_account`.
- `the_one/interfaces/web/api.py` — refactor `list_attached_agents_for_connector_account` (lines 2331-2389) to call the new helper instead of the inline `list_agents() → load each → filter` pattern. Endpoint response shape unchanged; existing HTTP test coverage validates the refactor.
- `the_one/connectors/_inbound.py` — add `_resolve_single_attached_agent_or_first_alphabetical`; rename `dispatch_inbound` signature; insert early-return guard.
- `tests/_connector_dispatch_helpers.py` — update `_seed_provider_and_agent` default for `connector_account_ids` (None → `["acct-test"]`).
- `tests/test_connectors_inbound.py` — migrate dispatch_inbound call sites; update failure-path test docstrings to reflect new failure source.
- `tests/test_connectors_inbound_broadcast.py` — migrate dispatch_inbound call sites.
- `tests/test_connectors_e2e_session.py` — migrate dispatch_inbound call sites.
- `tests/test_connectors_e2e_platform_send.py` — migrate dispatch_inbound call sites.
- `tests/test_connectors_e2e_ws_into_connector.py` — migrate dispatch_inbound call sites.
- `tests/test_db_repositories.py` — add 5 tests for `list_by_connector_account`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)

## Citation Audit

Citations verified against current code at leg design time:

| Citation | Status | Notes |
|----------|--------|-------|
| `the_one/db/repositories.py:75-85` (`list_agents` + `list_by_provider`) | OK | Style precedent confirmed via Read |
| `the_one/db/repositories.py:216` (`_row_to_config` connector_account_ids decode) | OK | `connector_account_ids=json.loads(row["connector_account_ids"] or "[]")` confirmed |
| `the_one/connectors/_inbound.py:77-200` (dispatch_inbound) | OK | Signature `(agent_name, account_id, envelope, *, factory)` confirmed |
| `the_one/connectors/_inbound.py:99-107` (failure-path silent return pattern) | OK | Existing try/except returning silently on pool.acquire/account-load errors |
| `tests/_connector_dispatch_helpers.py:76-115` (`_seed_provider_and_agent`) | OK | Signature + default-resolution-via-`connector_account_ids or []` confirmed |
| `tests/_connector_dispatch_helpers.py:118-142` (`_seed_stub_account`) | OK | Default `account_id="acct-test"` confirmed |
| `tests/_connector_dispatch_helpers.py:156-174` (`_envelope`) | OK | Default `account_id="acct-test"` confirmed |
| 55 dispatch_inbound call sites in `tests/` | OK | `grep -rn "dispatch_inbound\s*(" tests/ | wc -l` returns 55; bucket-(a) all-`"agent-inbound"` confirmed via greps |
| 43 `_seed_provider_and_agent` invocations in `tests/` (29 bare; 14 with explicit `connector_account_ids`) | OK | Confirmed via grep |
| `tests/test_connectors_inbound.py:935-990` (failure-path tests) | OK | `test_dispatch_inbound_account_not_found_returns_gracefully` + `test_dispatch_inbound_unknown_connector_type_returns_gracefully` confirmed; assert observable behavior (no exception, no session) — preserved post-L3 |

10 in-leg-artifact code-location citations verified against current code at leg design time.
