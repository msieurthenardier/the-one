# Leg: lock-unification-and-broadcast-lift-to-neutral-module

**Status**: completed
**Flight**: [Chat UI — Unified History, Visibility Distinction, Operator Console](../flight.md)

## Objective

Extract the per-session `asyncio.Lock` and the WebSocket subscriber set —
today owned by `Session` in `the_one/interfaces/web/app.py` and by a
parallel `_session_locks` defaultdict in `the_one/connectors/_inbound.py`
— into a new neutral `the_one/sessions/` package. Both the WS handler and
the F3 dispatcher converge on a single lock registry (closing the
mission Known Issue) and a single subscribers registry (so leg 6 can
broadcast dispatcher-driven inbounds to live WS observers without any
`connectors → interfaces.web.app` import).

## Context

- **Flight slot**: F5 L2. The structural-refactor leg. No behavior
  change visible to operators; the test surface gets a NEW invariant
  ("same-session WS-typed + dispatcher-inbound serialize on the shared
  lock") that the previous structure could not test.
- **Closes mission Known Issue**: "Per-session lock unification (surfaced
  in Flight 3 planning, owned by Flight 5)" — `mission.md:101-102`.
  Today, `the_one/connectors/_inbound.py:51` owns one defaultdict-of-
  locks; `the_one/interfaces/web/app.py:201` owns `Session.processing_lock`.
  Operator-typed messages into connector-attached sessions (landing in
  leg 4) would otherwise race on `agent.messages` because the two locks
  guard distinct identity sets.
- **Flight design decision — "Per-session-lock unification via a shared
  registry module — hybrid of F3 debrief options (a)+(b)"** (flight.md
  L37-44): shared registry, NOT routing-WS-through-dispatcher. The
  rationale for the hybrid is recorded in flight.md L43-44 (WS-typed-
  into-web-native-session has no `InboundEnvelope.account_id` to
  invent).
- **Flight design decision — "Broadcast surface generalization — lift
  `_sessions` registry access AND the broadcast helper to the neutral
  module"** (flight.md L70-74): subscribers + broadcast also lift to
  the new `the_one/sessions/` package; import direction stays one-way
  (`interfaces.web.app → the_one.sessions`; `connectors._inbound →
  the_one.sessions`).
- **Architect-surfaced**: removing `Session.processing_lock` requires
  updating THREE call sites — `_spawn_message_processing` (lazy-init
  dance disappears), `_restore_session` (the `cached.processing_lock.locked()`
  check), and `_build_session_joined_ok` (the `is_processing` payload
  field). The leg consolidates all three through a single
  `is_session_processing(sid) -> bool` helper so reads don't trigger
  the defaultdict's lazy-create side effect.
- **No schema change.** This is purely an import-direction + module-
  placement refactor. The defaultdicts are in-memory state; nothing
  persists.
- **Test conventions** carry over: `docker exec the-one pytest …
  -x --timeout 30`; `make test-unit`, `make test-browser`, `make lint`
  are the canonical recipes; `make rebuild` REQUIRED after Python
  changes if a subsequent leg/test path goes through the container.
- **Memory growth flagged for F10** (carries from `_inbound.py:47-50`):
  locks accumulate monotonically with session count over process
  lifetime; subscribers come and go with WS lifecycle but the
  registry's empty-set entries persist. F10 hardening pass owns
  `WeakValueDictionary` / TTL cleanup / LRU eviction. F5 L2 inherits
  the growth profile unchanged — that is acceptable because the
  single-user local-tool session count is bounded.

## Inputs

- `the_one/interfaces/web/app.py` — current owner of:
  - `Session.processing_lock: asyncio.Lock | None` field at line 201
    (lazy-init pattern documented in lines 196-200).
  - `Session.subscribers: set[WebSocket]` field at line 195.
  - `_spawn_message_processing` at line 235; lock dance at 250-252.
  - `_restore_session` at line 358; lock-held check at 386-392.
  - `_build_session_joined_ok` at line 516; lock-held check at 525.
  - `_send_to_session` at line 555; iterates `session.subscribers`.
  - 14 call sites mutating `session.subscribers.add(ws)` /
    `.discard(ws)` between lines 562-1363.
- `the_one/connectors/_inbound.py` — current owner of:
  - `_session_locks: defaultdict[str, asyncio.Lock]` at line 51.
  - `dispatch_inbound` uses `async with _session_locks[session_row.id]:`
    at line 164.
  - `_clear_for_test` at line 263 clears `_session_locks`.
- `tests/test_ws_responsiveness.py` — tests asserting `Session.processing_lock`
  behavior at lines 51, 69, 181, 216, 235, 287, 297, 305. These must be
  rewritten/inverted against the new registry shape.
- `tests/test_connectors_inbound.py:403,416,486,498` — tests reading
  `inbound_mod._session_locks[…]` directly. These either read through
  the new module or via a thin compatibility re-export.
- THREE autouse `_clear_pool_locks_registry` fixtures (verified — the
  fourth grep hit at `tests/_connector_dispatch_helpers.py:40` is a
  docstring header, not a fixture definition):
  `tests/test_connectors_inbound.py:94`,
  `tests/test_connectors_e2e_platform_send.py:80`,
  `tests/test_connectors_e2e_session.py:103`.
  Each must call the new module's `clear_for_test()` in addition to
  the existing `pool_mod._clear_for_test()` and
  `inbound_mod._clear_for_test()`.
- `tests/test_app_websocket_pause_resume.py:372,373,592` — three
  direct `session.subscribers.add(...)` calls in pause/resume tests.
  Shape A (field removal) breaks these — they must be migrated to
  `add_subscriber(session.id, ws)` in this leg.
- `tests/test_auto_load.py:145,165` — two direct
  `session.subscribers.add(mock_ws)` calls in Ollama-load tests. Same
  migration as above.
- `the_one/connectors/__init__.py` — currently re-exports
  `OPERATOR_VISIBILITY`, `PLATFORM_SEND_OK_PREFIX` (per F4 L1). Not
  modified by this leg; named for reference.

## Outputs

- New package `the_one/sessions/` with:
  - `__init__.py` re-exporting the public surface:
    - `session_locks` (defaultdict — exposed for tests that need direct
      inspection, NOT for consumer code; consumer code uses the
      semantic helpers).
    - `is_session_processing(sid: str) -> bool`
    - `clear_locks_for_test() -> None`
    - `add_subscriber(sid: str, ws) -> None`
    - `remove_subscriber(sid: str, ws) -> None`
    - `subscribers_for(sid: str) -> set` (returns a snapshot copy
      OR the live set per implementation — documented either way).
    - `broadcast_to_session(sid: str, payload: dict, *, exclude=None) -> None`
    - `clear_subscribers_for_test() -> None`
    - `clear_for_test() -> None` (clears both registries — convenience
      for autouse fixtures).
  - `_locks.py` — lock registry + `is_session_processing` + clear.
  - `_broadcast.py` — subscribers registry + add/remove/snapshot +
    `broadcast_to_session` + clear.
- `the_one/interfaces/web/app.py` — modified:
  - `Session.processing_lock` field REMOVED.
  - `_spawn_message_processing` uses `session_locks[session.id]` instead
    of the lazy-init `session.processing_lock`.
  - `_restore_session`'s lock-held check uses `is_session_processing(session_id)`.
  - `_build_session_joined_ok`'s `is_processing` payload field uses
    `is_session_processing(session.id)`.
  - Two reasonable shapes for `Session.subscribers`:
    - **Shape A (preferred)**: REMOVE `Session.subscribers` and replace
      every `session.subscribers.add/discard` call site with
      `add_subscriber(session.id, ws)` / `remove_subscriber(session.id, ws)`.
      `_send_to_session` reads `subscribers_for(session.id)` and
      iterates — same shape as today, different source.
    - **Shape B (fallback)**: KEEP `Session.subscribers` as a back-
      reference but ALSO call `add_subscriber/remove_subscriber` at
      every mutation site so the neutral module is source-of-truth;
      `_send_to_session` reads from the neutral module.
    - **Decision**: Shape A. The field's only consumer is
      `_send_to_session`, and we're already changing `_send_to_session`
      to read from the neutral module. Removing the field eliminates a
      drift class. The leg artifact's Implementation Guidance assumes
      Shape A; if the implementer hits a snag (e.g. a callsite they
      can't easily route through `session.id`), fall back to Shape B
      and document the snag in the flight log.
- `the_one/connectors/_inbound.py` — modified:
  - Module-level `_session_locks` REMOVED.
  - `dispatch_inbound` uses `session_locks[session_row.id]` from the
    new module.
  - `_clear_for_test` becomes a thin wrapper that calls the new
    module's `clear_locks_for_test()`. (Keep the symbol exported so
    existing autouse fixtures don't need broad refactoring; document
    that it now delegates.)
- `tests/test_ws_responsiveness.py` — rewritten so the three test
  classes assert against the new registry shape instead of
  `Session.processing_lock`:
  - `TestProcessingLock` becomes `TestSharedSessionLock` — assert the
    lock is created lazily inside the neutral registry on first use;
    assert two concurrent message spawns on the same session serialize.
  - `TestRestoreSkipsRebuildDuringInflight` — replace `s.processing_lock =
    asyncio.Lock()` setup with `async with session_locks[sid]:` to
    simulate a held lock; assert `_restore_session` short-circuits.
  - `TestSessionJoinedReportsIsProcessing` — assert
    `is_session_processing(sid)` drives the payload's `is_processing`
    field; remove all `processing_lock` references.
- `tests/test_connectors_inbound.py` — point the four direct accesses
  at `inbound_mod._session_locks` to the new module
  (`the_one.sessions.session_locks`).
- The three autouse `_clear_pool_locks_registry` fixtures — add a call
  to `the_one.sessions.clear_for_test()` so the new registries don't
  leak between tests.
- New test file `tests/test_session_registry_lock_unification.py` (or
  extend `tests/test_session_registry.py` if it already exists —
  `tests/test_session_registry.py` shows up in `grep` output as a real
  file; check at implementation start):
  - **same_session_serializes_across_paths**: spawn a WS-typed
    processing task AND a dispatcher inbound for the same `session_id`
    (event-coordinated, mirror of `tests/test_connectors_inbound.py:403-416`
    pattern); assert only one is inside `agent.step` at a time.
  - **different_sessions_parallelize**: same shape but two different
    `session_id` values; assert both run concurrently.
  - **is_session_processing_does_not_create_lock**: call
    `is_session_processing("unseen-sid")` and assert the helper
    returns False AND `"unseen-sid" not in session_locks` (the helper
    must not trigger the defaultdict's lazy-create — otherwise the
    `_build_session_joined_ok` read path leaks empty entries).
  - **subscribers_zero_broadcast_is_noop**: register no subscribers
    for a session id; call `broadcast_to_session(sid, payload)`;
    assert no exception, no side effect.
  - **subscribers_add_remove_round_trip**: register two fake WSes,
    verify `subscribers_for` returns both; remove one, verify the
    other remains; remove the second, verify the set is empty.

## Acceptance Criteria

- [ ] `the_one/sessions/` package exists with `_locks.py` and
      `_broadcast.py` modules. The package's `__init__.py` re-exports
      the public surface (`session_locks`, `is_session_processing`,
      `add_subscriber`, `remove_subscriber`, `subscribers_for`,
      `broadcast_to_session`, `clear_locks_for_test`,
      `clear_subscribers_for_test`, `clear_for_test`).
- [ ] `Session.processing_lock` field is REMOVED from the dataclass at
      `the_one/interfaces/web/app.py:187`.
- [ ] `Session.subscribers` field is REMOVED from the dataclass IF
      Shape A is taken (preferred); if Shape B is taken, the field
      remains as a back-reference but every mutation site ALSO calls
      the neutral module — document the choice in the flight log.
- [ ] `_spawn_message_processing` acquires `session_locks[session.id]`
      from the neutral module; no `processing_lock` reference remains.
- [ ] `_restore_session`'s "is the lock held?" check uses
      `is_session_processing(session_id)`; the function does NOT
      trigger the defaultdict's lazy-create as a side effect (verified
      by the dedicated test).
- [ ] `_build_session_joined_ok`'s `is_processing` payload field uses
      `is_session_processing(session.id)`.
- [ ] `the_one/connectors/_inbound.py`'s module-level `_session_locks`
      is REMOVED; `dispatch_inbound` consults `session_locks[…]` from
      the neutral module.
- [ ] `connectors._inbound._clear_for_test` continues to exist and
      delegates to `the_one.sessions.clear_locks_for_test()` (or is
      called by the same autouse fixtures the existing
      `_clear_pool_locks_registry` chain calls — leg implementer's
      choice).
- [ ] The THREE existing autouse `_clear_pool_locks_registry` fixtures
      (the `_connector_dispatch_helpers.py:40` grep hit is a doc
      header, not a fixture) AND the new test file's own autouse
      cleanup call `the_one.sessions.clear_for_test()` so neither
      registry leaks across tests.
- [ ] Five additional subscriber-callsite migrations land in this leg:
      `tests/test_app_websocket_pause_resume.py:372,373,592` and
      `tests/test_auto_load.py:145,165` all switch from
      `session.subscribers.add(...)` to `add_subscriber(session.id, ...)`.
- [ ] `the_one.connectors._inbound._clear_for_test` retains its
      `async def` signature so existing `await
      inbound_mod._clear_for_test()` sites at
      `tests/test_connectors_inbound.py:98`,
      `tests/test_connectors_e2e_platform_send.py:87`,
      `tests/test_connectors_e2e_session.py:113` continue to work.
- [ ] `the_one/connectors/_inbound.py` module docstring (lines 19-23)
      is updated from future-tense F5 plan to past-tense reference to
      the now-landed neutral module.
- [ ] `_restore_session` docstring (`app.py:360` and `:438` cached-
      update branch) is updated to reflect the new
      subscriber-preservation contract (registry keyed by session id,
      not field-on-dataclass).
- [ ] `tests/test_ws_responsiveness.py`'s three test classes are
      updated to assert against the new registry shape. The intent of
      each test is preserved (the rename pattern from `/leg`
      guidelines applies: when a test asserts behavior the new design
      breaks, the test is rewritten with the assertion adjusted —
      not deleted and silently re-added).
- [ ] `tests/test_connectors_inbound.py`'s four direct accesses
      (lines 403, 416, 486, 498) point at the new module.
- [ ] New file `tests/test_session_registry_lock_unification.py` (or
      extension of `tests/test_session_registry.py`) covers:
      - same-session WS+dispatcher serialization
      - different-sessions parallelization
      - `is_session_processing` does not lazy-create
      - zero-subscriber broadcast is a no-op
      - subscriber add/remove round-trip
- [ ] `make test-unit` clean (full Python unit suite; the F5 L1
      baseline of 1952 passed grows by 5–8 for the new module + tests).
- [ ] `make lint` clean.
- [ ] No regression on F1 (pool), F2 (admin), F3 (session model + dispatcher),
      F4 (platform-send), or F5 L1 (list-sessions projection) tests —
      they all continue to pass byte-identically except for the
      explicit rewrites listed above.
- [ ] Import direction preserved: `connectors._inbound → the_one.sessions`
      and `interfaces.web.app → the_one.sessions` are the only two
      consumer imports of the new package. The new package imports
      NOTHING from `connectors` or `interfaces.web.app`. Verified by
      a one-liner grep at leg end.

## Verification Steps

- **Focused test of the new module**:
  `docker exec the-one pytest tests/test_session_registry_lock_unification.py -x --timeout 30 -v`
  — new file's tests pass.
- **WS lock regression**:
  `docker exec the-one pytest tests/test_ws_responsiveness.py -x --timeout 30 -v`
  — rewritten tests pass under the new registry shape.
- **Dispatcher lock regression**:
  `docker exec the-one pytest tests/test_connectors_inbound.py -x --timeout 30 -v`
  — direct-access tests pass against the new module.
- **F4 e2e platform-send regression**:
  `docker exec the-one pytest tests/test_connectors_e2e_platform_send.py -x --timeout 60 -v`
  — autouse cleanup wired to the new module; tests pass.
- **F1/F2/F3 connector suite**:
  `docker exec the-one pytest tests/test_connectors_pool.py tests/test_connectors.py tests/test_connectors_e2e.py tests/test_connectors_e2e_session.py tests/test_connectors_session.py tests/test_session_registry.py -x --timeout 60 -v`
  — all green; no leaked lock identity between tests.
- **Full unit-suite regression**: `make test-unit` clean.
- **Import-direction grep**:
  `grep -rn "from the_one.connectors" the_one/sessions/` returns empty.
  `grep -rn "from the_one.interfaces" the_one/sessions/` returns empty.
- **Lint**: `make lint` clean.

## Implementation Guidance

The order below is the recommended path. Each numbered step ends in a
green test-suite state so partial work is safe.

1. **Create the package scaffold**:
   - `mkdir -p the_one/sessions`
   - `the_one/sessions/__init__.py`: import + re-export the public
     symbols from `_locks` and `_broadcast`.
   - `the_one/sessions/_locks.py`:
     ```python
     """Shared per-session lock registry.

     Both the WS handler (operator-typed messages) and the F3
     dispatcher (peer-inbound messages) acquire the SAME asyncio.Lock
     per chat_sessions.id. Closes the mission Known Issue raised in
     F3 planning where the two paths owned distinct lock identities
     and would have raced on agent.messages.
     """
     from __future__ import annotations

     import asyncio
     from collections import defaultdict

     # Module-level defaultdict. Locks created lazily on first use.
     # F10 hardening flag inherited from F3 _inbound.py:46-50: locks
     # accumulate monotonically with session count over process
     # lifetime; WeakValueDictionary / TTL / LRU is deferred until
     # growth matters.
     session_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


     def is_session_processing(session_id: str) -> bool:
         """True iff a lock exists for this session AND is currently held.

         MUST NOT trigger the defaultdict's lazy-create — uses .get(),
         not the [] indexer. Consumed by the WS handler's
         _restore_session and _build_session_joined_ok read paths.
         """
         lock = session_locks.get(session_id)
         return lock is not None and lock.locked()


     def clear_locks_for_test() -> None:
         """Drop all locks. Test fixtures only — production code never
         calls this. Mirrors the pre-existing _clear_for_test on the
         connectors pool and dispatcher modules.
         """
         session_locks.clear()
     ```
   - `the_one/sessions/_broadcast.py`:
     ```python
     """Shared per-session WebSocket subscriber registry + broadcast helper.

     Today's Session dataclass owns Session.subscribers: set[WebSocket];
     the broadcast helpers in interfaces.web.app iterate it. F5 L2
     lifts BOTH to a neutral module so leg 6's dispatcher can broadcast
     inbound-driven UI events without an interfaces.web.app import.
     """
     from __future__ import annotations

     from collections import defaultdict
     from typing import Any

     # set[WebSocket] keyed by chat_sessions.id. defaultdict factory is
     # set() — every read returns at minimum an empty set so the
     # zero-subscriber broadcast path is a clean iteration over nothing.
     _subscribers: defaultdict[str, set] = defaultdict(set)


     def add_subscriber(session_id: str, ws: Any) -> None:
         _subscribers[session_id].add(ws)


     def remove_subscriber(session_id: str, ws: Any) -> None:
         # discard, not remove — safe to call when the subscriber is
         # absent (lifecycle teardown calls this defensively).
         _subscribers[session_id].discard(ws)


     def subscribers_for(session_id: str) -> set:
         """Return a SNAPSHOT copy of the subscriber set.

         Callers iterate the snapshot; mutating the live set during
         iteration (e.g. discarding a dead WS mid-broadcast) is the
         pre-F5 bug shape that lives in interfaces.web.app:562-570
         today. Snapshot semantics avoid it.
         """
         return set(_subscribers.get(session_id, ()))


     async def broadcast_to_session(
         session_id: str,
         payload: dict[str, Any],
         *,
         exclude: Any = None,
     ) -> None:
         """Send a JSON payload to every WS subscriber of this session_id.

         Mirrors interfaces.web.app._send_to_session's semantics:
         dead-WS detection + discard. Zero subscribers → clean no-op.
         """
         dead: list = []
         for ws in subscribers_for(session_id):
             if ws is exclude:
                 continue
             try:
                 await ws.send_json(payload)
             except Exception:
                 dead.append(ws)
         for ws in dead:
             remove_subscriber(session_id, ws)


     def clear_subscribers_for_test() -> None:
         _subscribers.clear()
     ```
   - `the_one/sessions/__init__.py`:
     ```python
     """Neutral session-state registries.

     Hosts cross-subsystem state that BOTH interfaces.web.app and
     connectors._inbound need to coordinate on. Import direction is
     one-way INTO this package; nothing here imports from interfaces
     or connectors. F5 L2 introduced this module to close the
     mission Known Issue about per-session lock unification.
     """
     from the_one.sessions._broadcast import (
         add_subscriber,
         broadcast_to_session,
         clear_subscribers_for_test,
         remove_subscriber,
         subscribers_for,
     )
     from the_one.sessions._locks import (
         clear_locks_for_test,
         is_session_processing,
         session_locks,
     )

     __all__ = [
         "session_locks",
         "is_session_processing",
         "clear_locks_for_test",
         "add_subscriber",
         "remove_subscriber",
         "subscribers_for",
         "broadcast_to_session",
         "clear_subscribers_for_test",
         "clear_for_test",
     ]


     def clear_for_test() -> None:
         """Convenience for autouse fixtures — clears both registries."""
         clear_locks_for_test()
         clear_subscribers_for_test()
     ```
   - Run `make lint` — green. Run `docker exec the-one pytest -x --timeout 30 -q`
     — green (no consumers yet).

2. **Wire the dispatcher to the shared lock**
   (`the_one/connectors/_inbound.py`):
   - Remove the module-level `_session_locks` defaultdict at line 51.
   - Add `from the_one.sessions import session_locks` to the imports.
   - Update the `async with _session_locks[session_row.id]:` at line 164
     to `async with session_locks[session_row.id]:`.
   - Update `_clear_for_test` at line 263. **Preserve the `async def`
     signature exactly** — the three autouse fixtures `await` this
     function (`tests/test_connectors_inbound.py:98`,
     `tests/test_connectors_e2e_platform_send.py:87`,
     `tests/test_connectors_e2e_session.py:113`), and converting it to
     sync would break them with `TypeError: object NoneType can't be
     used in 'await' expression`. The body becomes:

     ```python
     async def _clear_for_test() -> None:
         """Test seam: clear the shared per-session lock registry.

         Delegates to ``the_one.sessions.clear_locks_for_test``.
         Kept ``async def`` for back-compat with autouse fixtures that
         ``await`` this symbol.
         """
         from the_one.sessions import clear_locks_for_test
         clear_locks_for_test()
     ```

   - Update the module docstring at lines 19-23 from future tense
     ("F5 will reconcile this lock...") to past tense:

     ```
     Per-session serialization shares the SAME asyncio.Lock with
     the WS handler. The lock registry lives at
     ``the_one.sessions.session_locks``; see F5 L2 for the
     unification that closed the M10 mission Known Issue.
     ```
   - In `tests/test_connectors_inbound.py:403,416,486,498`, change
     `inbound_mod._session_locks[…]` → `from the_one.sessions import
     session_locks; session_locks[…]`. (If the test file binds
     `inbound_mod = the_one.connectors._inbound` for clarity, a small
     parallel `sessions_mod = the_one.sessions` binding at module top
     keeps the changes minimal.)
   - Run the dispatcher tests; green. Run `make test-unit`; green.

3. **Wire `interfaces/web/app.py` to the shared lock**:
   - Add `from the_one.sessions import (session_locks, is_session_processing)`
     to the imports.
   - Remove `Session.processing_lock` field at line 201 and the
     surrounding docstring lines 196-200.
   - In `_spawn_message_processing` at line 235, delete lines 250-251
     (the lazy-init); change line 252 to
     `async with session_locks[session.id]:`.
   - In `_restore_session` at line 358, replace the three-line check
     at lines 387-391
     (`cached is not None and cached.processing_lock is not None and
     cached.processing_lock.locked()`) with
     `cached is not None and is_session_processing(session_id)`.
   - In `_build_session_joined_ok` at line 516, replace the
     `is_processing = bool(session.processing_lock is not None and
     session.processing_lock.locked())` line 525 with
     `is_processing = is_session_processing(session.id)`.
   - Run `make test-unit`; the three classes in
     `tests/test_ws_responsiveness.py` fail (they assert on
     `Session.processing_lock`). Move to step 4.

4. **Rewrite `tests/test_ws_responsiveness.py`** to the new shape:
   - `TestProcessingLock` → rename class to `TestSharedSessionLock`.
     - `test_lock_lazily_created`: assert `session_locks` contains no
       entry for the session id BEFORE `_spawn_message_processing`
       runs; after the call, `session_locks[sid]` exists. Use
       `is_session_processing(sid)` to read; do not index directly
       in the assertion (would create an empty entry as a side
       effect — that's the bug shape we explicitly forbid).
     - `test_second_message_waits_for_first`: keep the test's intent
       (two concurrent calls serialize); replace the `s.processing_lock`
       setup with the shared registry. The `slow_first` fake can hold
       the shared lock by acquiring `session_locks[sid]` directly
       inside the test; the assertion is on `order` ordering.
   - `TestRestoreSkipsRebuildDuringInflight` → keep the class; replace
     each `s.processing_lock = asyncio.Lock(); async with s.processing_lock:`
     pair with `lock = session_locks[s.id]; async with lock:`. The
     asserted behavior (skip rebuild when held) is unchanged.
   - `TestSessionJoinedReportsIsProcessing` → keep; replace
     `s.processing_lock = asyncio.Lock(); async with s.processing_lock:`
     pairs with `lock = session_locks[s.id]; async with lock:`. The
     `assert s.processing_lock is None` cases become
     `assert not is_session_processing(s.id)` (since the registry
     either has no entry or has an unheld lock — both report False).
   - Add to the autouse fixture in this file:
     `from the_one.sessions import clear_for_test as _clear_session_registry`
     and call it in the yield-teardown so the shared registry doesn't
     leak between tests.
   - Run `pytest tests/test_ws_responsiveness.py -x --timeout 30 -v`;
     green.

5. **Lift subscribers to the neutral module**
   (`interfaces/web/app.py` — Shape A, preferred):
   - Add `from the_one.sessions import (add_subscriber, remove_subscriber,
     subscribers_for)` to imports.
   - Remove `Session.subscribers` field at line 195.
   - Replace every `session.subscribers.add(ws)` → `add_subscriber(session.id, ws)`.
   - Replace every `session.subscribers.discard(ws)` → `remove_subscriber(session.id, ws)`.
   - Replace `if ws not in session.subscribers:` guards with
     `if ws not in subscribers_for(session.id):` — note the snapshot
     semantics; the guard is a presence check, snapshot is fine.
   - Update `_send_to_session` at line 555:
     ```python
     async def _send_to_session(
         session: Session,
         payload: dict[str, Any],
         exclude: WebSocket | None = None,
     ) -> None:
         """Send a JSON payload to all websocket subscribers of a session."""
         dead: list[WebSocket] = []
         for ws in subscribers_for(session.id):
             if ws is exclude:
                 continue
             try:
                 await ws.send_json(payload)
             except Exception:
                 dead.append(ws)
         for ws in dead:
             remove_subscriber(session.id, ws)
     ```
     This is the surface that the dispatcher's leg-6 broadcast will
     re-use via `broadcast_to_session` — same iteration shape, just
     entered via the neutral module.
   - Audit the 14 call sites in `app.py` (the grep earlier listed
     lines 562, 570, 1041, 1225, 1232, 1233, 1248, 1249, 1264, 1265,
     1291, 1298, 1311, 1337, 1363). Each one is a single-line edit.
   - **Migrate the FIVE test-file call sites that the same field
     removal will break**:
     - `tests/test_app_websocket_pause_resume.py:372,373,592` — three
       direct `session.subscribers.add(...)` calls. Replace with
       `add_subscriber(session.id, ws)` (`type: ignore[arg-type]`
       comments stay if needed for the fake-ws shape).
     - `tests/test_auto_load.py:145,165` — two direct
       `session.subscribers.add(mock_ws)` calls. Replace with
       `add_subscriber(session.id, mock_ws)`.
     - Add the import `from the_one.sessions import add_subscriber`
       (and `remove_subscriber`/`subscribers_for` as needed by each
       test).
   - **Touch up the `_restore_session` docstring** at lines 360 and 438
     — the existing language describes "preserving subscribers and
     identity" through the cached-session-update path. Under Shape A
     the field is gone; subscriber preservation now happens implicitly
     via the registry's session-id keying. Adjust the docstring to say
     so (one or two sentences; keep the surrounding behavior contract
     intact).
   - Run `pytest -x --timeout 60 tests/test_ws_responsiveness.py
     tests/test_app_websocket_pause_resume.py tests/test_auto_load.py -v`;
     green.

6. **Update the THREE autouse `_clear_pool_locks_registry` fixtures**
   (the `tests/_connector_dispatch_helpers.py:40` grep hit is a doc
   header, not a real fixture — no edit needed there):
   - `tests/test_connectors_inbound.py:94`
   - `tests/test_connectors_e2e_platform_send.py:80`
   - `tests/test_connectors_e2e_session.py:103`
   - In each, after the existing `pool_mod._clear_for_test()` /
     `inbound_mod._clear_for_test()` calls, add a call to
     `the_one.sessions.clear_for_test()`. Mirror import shape:
     `from the_one.sessions import clear_for_test as _clear_session_registry`
     at the test-file top.

7. **Add the new test file** `tests/test_session_registry_lock_unification.py`.
   (`tests/test_session_registry.py` exists but its scope is the PTY
   session registry at `the_one.tools._session_registry` — unrelated
   to chat-session locks. Don't extend that file; create a fresh one.)
   The five test cases enumerated under Outputs land here:
   - `test_same_session_serializes_across_paths` — event-coordinated.
     The simplest shape spawns two tasks:
     1. Task A acquires `session_locks[sid]` directly and sleeps on
        an `asyncio.Event` so it stays inside the lock.
     2. Task B is spawned (a wrapper that takes the lock from the
        same registry).
     3. Assert task B is `not done` after a short `asyncio.sleep(0)`.
     4. Set the event so task A releases.
     5. Assert task B completes.
   - `test_different_sessions_parallelize` — same pattern, two
     distinct sids; assert both run concurrently.
   - `test_is_session_processing_does_not_lazy_create` — call
     `is_session_processing("unseen")`; assert returns False; assert
     `"unseen" not in session_locks`. This pins the
     `_build_session_joined_ok` read-path safety.
   - `test_zero_subscriber_broadcast_is_noop` — call
     `await broadcast_to_session("no-subs", {"type": "hello"})`;
     assert no exception.
   - `test_subscribers_round_trip` — `add_subscriber`, assert
     `subscribers_for` matches; `remove_subscriber`, assert removed;
     idempotent `remove_subscriber` of an absent ws does not raise.
   - Wire the autouse fixture: `from the_one.sessions import
     clear_for_test; …; yield; clear_for_test()`.

8. **Verify import direction**:
   - `grep -rn "from the_one.connectors" the_one/sessions/` — empty.
   - `grep -rn "from the_one.interfaces" the_one/sessions/` — empty.
   - `grep -rn "import the_one.connectors\|import the_one.interfaces"
     the_one/sessions/` — empty.

9. **Full-suite regression**:
   - `make test-unit` clean.
   - `make lint` clean.

10. **Update flight log** with this leg's outcomes — files touched,
    tests added/rewritten, the Shape A vs B choice, any deviation,
    and a note that the mission Known Issue is now closed.

## Edge Cases

- **`Session.subscribers` field is read by code outside `_send_to_session`**:
  the `grep` enumerates all 14 call sites; each is a clear `.add` /
  `.discard` / `in` check. If a callsite the grep missed exists (e.g.
  in a comment-only reference or a test that pickles/copies the
  dataclass), the leg implementer adapts on the spot. The fallback
  (Shape B: keep `subscribers` as a back-reference) covers the rare
  callsite that resists routing through `session.id`.

- **Lock identity across event-loop teardown**: `asyncio.Lock` objects
  bind to the event loop they were created on. The defaultdict's
  lazy-create happens on first `[]` access — if a test's event loop
  is torn down and a new one comes up without clearing the registry,
  the next `async with session_locks[sid]:` raises `RuntimeError`.
  Mitigation: the autouse fixtures clear the registry between tests.
  This is the SAME failure mode that already exists for
  `the_one/connectors/_inbound._session_locks` and
  `the_one/connectors/_pool._sources` — F5 L2 inherits it; F10 owns
  the structural fix.

- **`is_session_processing` race**: between the helper returning True
  and the caller acting on it, the lock-holder can release. Both
  current call sites (`_restore_session` and `_build_session_joined_ok`)
  are best-effort UI hints, not correctness barriers. Acceptable.

- **`_clear_for_test` symbol on `connectors._inbound`** still gets
  called by existing autouse fixtures — keep the function (now a
  thin wrapper). Deleting the symbol would break the four fixtures
  even if they ALSO call the new module's clear.

- **A test holds `session_locks[sid]` directly** (the same-session
  serialization test does this). Verify the held lock is released
  inside the `async with` block before the test exits, otherwise
  subsequent tests see a held lock for that sid until
  `clear_for_test` runs. The autouse fixture covers this.

- **`subscribers_for` snapshot vs. live**: `_send_to_session` iterates
  a snapshot. If a subscriber is added mid-iteration (e.g. a new WS
  joins while a broadcast is fanning out), it will not receive THAT
  broadcast — only subsequent ones. This is the SAME behavior as
  today (set iteration on a mutated set is undefined). Documenting
  the snapshot semantics in the docstring is sufficient.

- **`add_subscriber` called twice for the same `(sid, ws)`**: set
  semantics dedupe. No bug.

- **`remove_subscriber` called for an unregistered `(sid, ws)`**:
  `set.discard` is a no-op. Safe.

## Files Affected

- `the_one/sessions/__init__.py` (new)
- `the_one/sessions/_locks.py` (new)
- `the_one/sessions/_broadcast.py` (new)
- `the_one/interfaces/web/app.py` — remove `Session.processing_lock` +
  `Session.subscribers`; rewire 17+ call sites (lock x3, subscribers
  x14).
- `the_one/connectors/_inbound.py` — remove module-level
  `_session_locks`; rewire `dispatch_inbound`; delegate `_clear_for_test`.
- `tests/test_ws_responsiveness.py` — rewrite three test classes.
- `tests/test_connectors_inbound.py` — point four direct accesses at
  the new module.
- `tests/test_connectors_inbound.py`,
  `tests/test_connectors_e2e_platform_send.py`,
  `tests/test_connectors_e2e_session.py` — add
  `the_one.sessions.clear_for_test()` to autouse cleanup.
- `tests/test_app_websocket_pause_resume.py` — migrate three
  `session.subscribers.add(...)` callsites to `add_subscriber`.
- `tests/test_auto_load.py` — migrate two
  `session.subscribers.add(mock_ws)` callsites to `add_subscriber`.
- `tests/test_session_registry_lock_unification.py` (new — NOT an
  extension of `tests/test_session_registry.py`, which is for the
  unrelated PTY session registry).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`make test-unit`, `make lint` clean)
- [ ] Import-direction grep confirms `the_one/sessions/` has no
      consumer-side imports.
- [ ] Update flight-log.md with leg progress entry (files touched,
      Shape A vs B choice, mission Known Issue closure note).
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Per the agentic-workflow protocol: do NOT commit until end-of-flight
      review.

## Citation Audit

15 citations verified against current code at leg design time:

- `the_one/interfaces/web/app.py:187` — `class Session` dataclass
  (verified).
- `the_one/interfaces/web/app.py:195` — `subscribers: set[WebSocket]`
  field (verified).
- `the_one/interfaces/web/app.py:201` — `processing_lock` field
  (verified).
- `the_one/interfaces/web/app.py:220` — `_sessions: dict[str, Session]`
  module-global (verified).
- `the_one/interfaces/web/app.py:235` — `_spawn_message_processing`
  (verified; lock dance at 250-252).
- `the_one/interfaces/web/app.py:358` — `_restore_session`; lock-held
  check at 386-392 (verified).
- `the_one/interfaces/web/app.py:516` — `_build_session_joined_ok`;
  `is_processing` line 525 (verified).
- `the_one/interfaces/web/app.py:555` — `_send_to_session` (verified).
- `the_one/connectors/_inbound.py:51` — `_session_locks` defaultdict
  (verified).
- `the_one/connectors/_inbound.py:164` — `async with
  _session_locks[session_row.id]:` (verified).
- `the_one/connectors/_inbound.py:263` — `_clear_for_test` (verified).
- `tests/test_ws_responsiveness.py:51,69,181,216,235,287,297,305` —
  `processing_lock` assertions across three test classes (verified).
- `tests/test_connectors_inbound.py:403,416,486,498` — direct
  `inbound_mod._session_locks[…]` reads (verified).
- Three autouse `_clear_pool_locks_registry` fixtures (the fourth grep hit is doc-only) —
  `tests/_connector_dispatch_helpers.py:40`,
  `tests/test_connectors_e2e_platform_send.py:80`,
  `tests/test_connectors_inbound.py:94`,
  `tests/test_connectors_e2e_session.py:103` (verified — note: the
  `_connector_dispatch_helpers.py:40` ref is a header comment, not
  the fixture; verify the actual fixture location at impl start).
- `the_one/connectors/__init__.py` re-exports `OPERATOR_VISIBILITY` and
  `PLATFORM_SEND_OK_PREFIX` (verified — referenced for context only,
  not modified by this leg).
