# Leg: inbound-gating-pairing-and-audit

**Status**: completed
**Flight**: [Pairing, Allowlists, and Per-Agent ACLs](../flight.md)

## Objective

Wire the F6 resolver hook + pairing flow + audit-log writer into the inbound dispatcher at `the_one/connectors/_inbound.dispatch_inbound`. After account-load + plugin-resolve, the dispatcher calls `getattr(plugin, "resolve", _default_permit)(account, envelope)` and branches on the three-outcome ADT: **Permit** → continue existing path; **NeedsPairing** → parse `PAIR <code> <rest>` prefix from `envelope.text`, validate against `account.config["pairing"]["code"]`, on success strip prefix and persist `peer_id` into `account.config["allowlist"]["peers"]`, then continue with cleaned envelope; on failure, deny silently; **Deny** → log and return. Ships a new narrow primitive `ChatSessionRepository.append_to_session_metadata(session_id, key, value)` modeled on `update_last_inbound`. Audit log entries land under `session_metadata["audit"]: list[dict]` with shape `{outcome, peer_id, ts, reason?}`. Stub plugin gains a small variant for tests (or a test-side monkeypatch — design picks `register_for_test` variant for parity with F1-stub testing convention).

## Context

- **Flight In-Flight §4** (flight.md): leg 2 — dispatcher consults `getattr(plugin, "resolve", _default_permit)` after account-load + plugin-resolve. `NeedsPairing` outcome triggers pairing-prefix validation (dispatcher-side, against `account.config["pairing"]["code"]`) → on success: strip prefix, append peer_id to `account.config["allowlist"]["peers"]`, persist via account repository, append outcome to `session_metadata` via new primitive. All three outcomes log to `session_metadata` for audit. Persistence survives restart.
- **Cycle-2 finding #1 (flight log)**: leg-2 test-fixture mechanism named but not committed — three candidates: (a) `StubPluginWithResolver` variant fixture, (b) monkeypatch the `getattr` consult site, (c) parametrized stub with constructor flag. **Decision**: option (a), a `StubPluginWithResolver` variant. Rationale: matches the `register_for_test` convention already used in `tests/test_connectors_pool.py`; parametrized constructor (option c) is heavier ergonomic surface for a single test concern; monkeypatch (option b) is brittle to refactor. The variant lives next to `StubPlugin` in `tests/_connector_dispatch_helpers.py` or in a new helper module — leg-2 author's call.
- **Cycle-2 finding suggestion (flight log)**: "Verification §1 should specify the `session_metadata` audit key name explicitly (e.g. `session_metadata["audit"] = [{outcome, peer_id, ts}, ...]`). Leg-2 design call but worth flight-level pre-commitment." **Decision**: commit to `session_metadata["audit"] = list[dict]` with each entry `{"outcome": "permit"|"needs_pairing"|"deny", "peer_id": str, "ts": iso_str, "reason": str | None}`. F7 routing-decision logs will use a sibling key (`session_metadata["routing"]` per the F3 L1 hint).
- **Cycle-2 question (flight log)**: pairing-prefix validation in `_inbound.dispatch_inbound` itself OR a separately importable helper? **Decision**: separately importable helper `_validate_pairing_prefix(text, code) -> tuple[bool, str]` (returns `(success, cleaned_text)`) in `the_one/connectors/_pairing.py`. Rationale: pure function; testable in isolation; future plugins can override the prefix parsing convention by implementing their own `resolve` hook that does the parsing internally. The default convention is `PAIR <code> <message>` with a single space separator.
- **Cycle-2 question (flight log)**: F6's "first-attached or only-attached" temporary single-agent assumption — does it live in leg-2's dispatcher logic, or in a separate helper F7 replaces? **Decision**: the dispatcher CURRENTLY receives `agent_name` as an explicit parameter (per `_inbound.py:dispatch_inbound` signature L46). F7 will introduce a multi-agent routing resolver that decides which agent to dispatch to. Leg 2 does NOT change the `agent_name` parameter contract — the dispatcher continues to receive a specific agent. The "first-attached or only-attached" assumption lives upstream of `dispatch_inbound` (in F1-stub-test invocation today; in F8 Discord gateway tomorrow). Leg 2 has no code surface for this concern.
- **F1 stub plugin discipline**: leg 1a left `StubPlugin` unchanged so F1-F5 tests pass byte-identically. Leg 2's pairing tests need a stub that DOES implement `resolve` — hence the variant `StubPluginWithResolver`. The original `StubPlugin` remains unchanged.
- **`account.config["pairing"]` and `["allowlist"]` shape** is fully specified by leg 1b. The dispatcher reads `account.config.get("pairing")` and `account.config.get("allowlist")` with default-permit-on-absence semantics. Leg 1b's `_validate_config_reserved_keys` runs on `_row_to_model` direct-construction, so the dispatcher receives a validated dict.
- **Persistence path for the paired peer**: on successful pairing, the dispatcher mutates `account.config["allowlist"]["peers"]` (initializing the dict if absent — see edge case below) and persists via `ConnectorAccountRepository.update(account)`. After persistence, a fresh `account.get()` in the next inbound returns the paired state. The pool's warm-entry eviction path (post-secrets-change) is NOT triggered by config-only updates — pairing does not touch `secrets`.
- **Race on concurrent pairing**: two peers sending `PAIR <same code> <msg>` simultaneously each see the same `account.config["allowlist"]["peers"]` at read time, each appends their own peer_id, each persists. SQLite's last-writer-wins on the `connector_accounts.config` JSON column means one of the two persists overwrites the other — but since both writers are APPENDING their distinct peer_id, the final state may be missing the loser's peer_id. Documented as a known limitation; the operator can re-pair by re-issuing the prefix. F10 hardening may consider a per-account write lock.
- **Audit log retention**: the audit list is unbounded by design. Operator review is the eventual surface (leg 4 Studio Connectors detail page may render a tail). Bounded-retention is F10 territory. Documented in the validator and audit-writer docstrings.
- **`append_to_session_metadata` primitive** is the canonical writer for session-metadata mutations going forward. F7 routing-decision logs will use the same primitive with a different key. The function signature: `async def append_to_session_metadata(self, session_id: str, key: str, value: Any) -> None`. Implementation: SELECT current `session_metadata`, JSON-decode to dict (or `{}` on NULL), look up `dict.get(key, [])`, append `value`, write back the whole `session_metadata` column. Deep-merge for dict-typed existing values is OUT OF SCOPE for leg 2 (no current use case; F7 may revisit).

## Inputs

- `the_one/connectors/_inbound.py:45-251` — `dispatch_inbound` (the dispatcher; leg 2 inserts the resolver consult between account-load at L118 and session-resolve at L146)
- `the_one/connectors/base.py:Permit,NeedsPairing,Deny,ResolveOutcome,_default_permit` — leg 1a's ADT
- `the_one/db/models.py:ConnectorAccount.config` — leg 1b's pairing + allowlist schema
- `the_one/db/repositories.py:672-845` — `ChatSessionRepository` (leg 2 adds `append_to_session_metadata` after L815's `update_last_inbound`)
- `the_one/db/repositories.py:458-570` — `ConnectorAccountRepository` (leg 2 calls `update(account)` after pairing success)
- `the_one/connectors/_stub.py:StubPlugin` — UNCHANGED (regression preservation)
- `tests/_connector_dispatch_helpers.py:128,151-169` — fixture builders for `ConnectorAccount` and `InboundEnvelope`
- `tests/test_connectors_inbound.py` — F3/F4 dispatcher test suite; leg 2 extends it with pairing/allowlist/audit tests

## Outputs

- `the_one/connectors/_pairing.py` — NEW module with `_validate_pairing_prefix(text: str, code: str) -> tuple[bool, str]` (returns `(success, cleaned_text)`)
- `the_one/connectors/_inbound.py:dispatch_inbound` — insert resolver consult + three-arm branch + pairing flow + audit writes
- `the_one/db/repositories.py:ChatSessionRepository.append_to_session_metadata` — new method
- `the_one/connectors/_stub.py` — UNCHANGED
- `tests/_connector_dispatch_helpers.py` (or sibling helper) — `StubPluginWithResolver` variant that implements `resolve` returning a configurable outcome
- `tests/test_connectors_inbound.py` — new test class covering: stub-without-resolve permits (regression — F3/F4 byte-identical); Permit outcome dispatches normally; NeedsPairing + valid prefix strips + persists peer_id + appends audit + dispatches with cleaned text; NeedsPairing + invalid prefix denies silently + appends audit; NeedsPairing + no prefix denies silently + appends audit; Deny outcome logs audit + returns without dispatch; paired peer's subsequent message bypasses pairing (allowlist hit); persistence survives a fresh repo fetch
- `tests/test_db_repositories.py::TestChatSessionRepository` — new tests for `append_to_session_metadata`: appends to absent key creates list; appends to existing list grows it; preserves other keys; NULL session_metadata initializes to `{}`
- The flight log gains a leg-2 entry

## Acceptance Criteria

- [ ] `the_one/connectors/_pairing.py` exists with `_validate_pairing_prefix(text, code)` returning `(True, cleaned)` on `PAIR <code> <rest>` match and `(False, text)` on miss; whitespace handling: single-space-after-PAIR, single-space-after-code; verbatim cleaned message (no extra strip)
- [ ] `ChatSessionRepository.append_to_session_metadata(session_id, key, value)` exists in `the_one/db/repositories.py` and: raises `KeyError` on missing session; reads-decodes-appends-writes the whole `session_metadata` column; initializes NULL → `{}`; preserves all other top-level keys; appends `value` to `session_metadata[key]` (initializing to `[]` if absent)
- [ ] `dispatch_inbound` in `_inbound.py` consults `getattr(plugin, "resolve", _default_permit)(account, envelope)` AFTER `resolve_session` (the session row must exist so audit-log writes have a target) and BEFORE the per-session lock at L155 (the `agent.step` gate is the actual behavioral difference)
- [ ] `Permit` outcome: dispatcher writes a `{"outcome": "permit", "peer_id": envelope.peer_id, "ts": now_iso(), "reason": None}` audit entry and continues with the unmodified envelope (F3/F4 dispatch path unchanged behaviorally). `reason` key is always present in audit entries (null for default-permit; string for paired/denied) so leg-4's renderer can read uniformly without per-entry shape checks.
- [ ] `NeedsPairing` outcome: dispatcher calls `_validate_pairing_prefix(envelope.text, account.config["pairing"]["code"])`. On success: appends `envelope.peer_id` to `account.config["allowlist"]["peers"]` (initializing the allowlist if absent — `{"peers": [], "channels": []}`); persists via `ConnectorAccountRepository.update(account)`; appends audit `{"outcome": "permit", "peer_id": ..., "ts": ..., "reason": "paired"}`; continues dispatch with envelope text replaced by the cleaned message. On failure: appends audit `{"outcome": "deny", "peer_id": ..., "ts": ..., "reason": "<NeedsPairing reason or 'invalid_pairing'>"}`; returns without dispatching.
- [ ] `Deny` outcome: dispatcher appends audit `{"outcome": "deny", "peer_id": ..., "ts": ..., "reason": <Deny.reason>}` and returns without dispatching
- [ ] Audit writes use the new `append_to_session_metadata("audit", entry)` primitive. The session row is resolved BEFORE audit writes (the audit needs a session_id). Two ordering candidates: (a) resolve session FIRST, then audit — but `Deny` writes against a session that may not exist yet (or, more subtly, the dispatcher MUST create a session for the Deny case so audit has a target); (b) audit only on `Permit` and `NeedsPairing-success`, NOT on `Deny`/`NeedsPairing-failure` (since no session is created, no audit row). **Decision**: option (a) — the resolver consult AND the audit write both fall AFTER session-resolve. The session is created on first contact regardless of the resolver outcome, but `agent.step` is gated by the outcome. This ensures the operator can inspect every gate decision via Chat UI's session list (leg 5). Documented in the dispatcher docstring.
- [ ] Pairing persistence survives a process restart: a fresh `acc_repo.get(account_id)` after pairing returns `peer_id` in `config["allowlist"]["peers"]`
- [ ] Stub `StubPluginWithResolver` variant exists in test helpers with: configurable `resolve` outcome (default `Permit()`); class-level recording of `resolve_calls`; reset-for-test hook
- [ ] F1-F5 + leg-1a + leg-1b + leg-1c regression suites pass byte-identically. The `StubPlugin` (without `resolve`) continues to hit the `_default_permit` fallback; its tests are unchanged.
- [ ] New tests in `tests/test_connectors_inbound.py`: at minimum 8 tests covering the three outcomes, success vs failure of pairing, persistence survival, audit-log content, and the agent-step gate
- [ ] New tests in `tests/test_db_repositories.py::TestChatSessionRepository` for `append_to_session_metadata`: at minimum 5 tests (NULL-init, absent-key create, existing-list append, other-keys preserved, missing-session-raises-KeyError)
- [ ] `ruff check` clean on modified files; full test suite passes

## Verification Steps

- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py::TestChatSessionRepository` — new + existing tests pass
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_inbound.py` — F3/F4 byte-identical + new leg-2 tests pass
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_resolver.py tests/test_connectors_e2e_session.py tests/test_connectors_session.py tests/test_connectors_pool.py` — leg-1a/F1/F3/F4/F5 regression
- `docker exec the-one pytest -x --timeout 30` — full suite passes
- `grep -rn "AllowlistResolver\|# F6:" the_one/` — should show only the leg-3-deferred sites (`tools/connector_send.py:131` + `connectors/README.md:380`)

## Implementation Guidance

1. **Create `the_one/connectors/_pairing.py`** with the prefix-validation helper:

   ```python
   """DM-pairing prefix validator.

   M10 F06 L2: parses the operator-shared pairing convention
   ``PAIR <code> <message>`` from an inbound envelope's text. Single-
   space separator; the code is the operator's pre-shared one-time
   secret; the message is the cleaned text the agent will see.

   Pure function — no I/O. Dispatcher (``connectors/_inbound``) consults
   on ``NeedsPairing`` outcomes; the function returns ``(success,
   cleaned_text)`` so the dispatcher can branch.
   """
   from __future__ import annotations

   _PAIR_PREFIX = "PAIR "

   def _validate_pairing_prefix(text: str, code: str) -> tuple[bool, str]:
       """Check ``text`` for a ``PAIR <code> <rest>`` prefix.

       Returns ``(True, cleaned)`` if the prefix matches AND the code is
       non-empty (an empty code never matches; defends against an account
       whose pairing entry was malformed past validator scope). ``cleaned``
       is the text with the entire prefix stripped (including the trailing
       single space). Returns ``(False, text)`` on any mismatch — text
       unchanged.

       The PAIR keyword is case-sensitive; the code comparison is
       byte-equality (no normalization). Whitespace inside the code is
       not permitted (the prefix parser uses single-space separators).
       """
       if not code:
           return False, text
       if not text.startswith(_PAIR_PREFIX):
           return False, text
       remainder = text[len(_PAIR_PREFIX):]
       expected = code + " "
       if not remainder.startswith(expected):
           return False, text
       cleaned = remainder[len(expected):]
       return True, cleaned
   ```

2. **Add `append_to_session_metadata` to `ChatSessionRepository`** in `the_one/db/repositories.py` after `update_last_inbound` (around L845):

   ```python
   async def append_to_session_metadata(
       self, session_id: str, key: str, value: Any
   ) -> None:
       """Append ``value`` to the list at ``session_metadata[key]``.

       Initializes ``session_metadata`` from NULL to ``{}`` and the
       list at ``key`` from absent to ``[]`` as needed. Preserves all
       other top-level keys in ``session_metadata``. The whole column
       is rewritten on each call (last-writer-wins; no deep-merge or
       optimistic concurrency in leg 2 scope).

       Raises ``KeyError`` if the session doesn't exist — mirrors
       ``update_last_inbound`` not-found semantics.

       M10 F06 L2 — narrow primitive for the audit-log writer. F7's
       routing-decision logs will use the same primitive with a
       different key.
       """
       async with self.conn.execute(
           "SELECT session_metadata FROM chat_sessions WHERE id = ?",
           (session_id,),
       ) as cur:
           row = await cur.fetchone()
       if row is None:
           raise KeyError(f"Chat session not found: {session_id}")
       raw = row["session_metadata"]
       metadata: dict[str, Any] = json.loads(raw) if raw else {}
       existing = metadata.get(key)
       if not isinstance(existing, list):
           existing = []
       existing.append(value)
       metadata[key] = existing
       await self.conn.execute(
           "UPDATE chat_sessions SET session_metadata = ? WHERE id = ?",
           (json.dumps(metadata), session_id),
       )
       await self.conn.commit()
   ```

3. **Edit `dispatch_inbound` in `_inbound.py`** — insert the resolver consult + three-arm branch + pairing flow + audit writes.

   **Placement (final, single-source-of-truth)**: AFTER `resolve_session` at L146-152 (so the session row exists and audit-log writes have a target) and BEFORE the `async with session_locks[session_row.id]:` block at L155. `resolve_session` does NOT read `envelope.text` (it uses `normalize_session_key`'s key fields), so envelope substitution at that call site is unnecessary. The `working_envelope` substitution applies ONLY to `agent.step(envelope.text)` at L193 — a single-site diff.

   **`last_inbound_at` on Deny**: the existing dispatcher calls `chat_repo.update_last_inbound(...)` INSIDE the per-session lock at L158. Because the Deny + NeedsPairing-failure branches `return` BEFORE entering the lock, `last_inbound_at` is NOT bumped on denied messages. This is deliberate — denied messages should not extend the continuation window. Document in the dispatcher docstring.

   **Resolver always called**: `getattr(plugin, "resolve", _default_permit)(account, envelope)` runs for EVERY inbound (Permit, NeedsPairing, and Deny outcomes all enter the consult). The audit-log entry is therefore written for every gate decision — the operator can inspect every inbound's gate decision via the Studio Connectors detail page (leg 4). Document in the dispatcher docstring.

   Pseudocode for the inserted block (sits between L152 and L155 of the existing dispatcher):

   ```python
   # ... existing pool acquire + account load + plugin resolve ...

   # 4. Resolve session via leg-3 resolver (UNCHANGED).
   session_row = await resolve_session(...)

   # 4b. F6 L2: optional resolver consult.
   resolver = getattr(plugin, "resolve", _default_permit)
   outcome = resolver(account, envelope)
   ts = now_iso()

   if isinstance(outcome, Deny):
       await chat_repo.append_to_session_metadata(
           session_row.id,
           "audit",
           {"outcome": "deny", "peer_id": envelope.peer_id,
            "ts": ts, "reason": outcome.reason},
       )
       return

   working_envelope = envelope
   if isinstance(outcome, NeedsPairing):
       pairing = (account.config.get("pairing") or {}).get("code")
       success, cleaned = _validate_pairing_prefix(
           envelope.text, pairing or ""
       )
       if not success:
           await chat_repo.append_to_session_metadata(
               session_row.id,
               "audit",
               {"outcome": "deny", "peer_id": envelope.peer_id,
                "ts": ts, "reason": outcome.reason or "invalid_pairing"},
           )
           return
       # Success: persist the paired peer + clean the envelope.
       allowlist = account.config.get("allowlist") or {"peers": [], "channels": []}
       peers = list(allowlist.get("peers", []))
       if envelope.peer_id not in peers:
           peers.append(envelope.peer_id)
       allowlist["peers"] = peers
       allowlist.setdefault("channels", [])
       account.config["allowlist"] = allowlist
       await acc_repo.update(account)
       working_envelope = replace(envelope, text=cleaned)
       await chat_repo.append_to_session_metadata(
           session_row.id,
           "audit",
           {"outcome": "permit", "peer_id": envelope.peer_id,
            "ts": ts, "reason": "paired"},
       )
   else:
       # Permit outcome. ``reason: None`` for shape uniformity (leg-4
       # renderer reads all four keys without per-entry shape checks).
       await chat_repo.append_to_session_metadata(
           session_row.id,
           "audit",
           {"outcome": "permit", "peer_id": envelope.peer_id,
            "ts": ts, "reason": None},
       )

   # 5+. Per-session lock + update_last_inbound + agent.step + persist
   # (UNCHANGED except the agent.step argument at L193:
   # ``working_envelope.text`` instead of ``envelope.text``).
   ```

   `replace` is `dataclasses.replace`. Import the resolver outcome ADTs from `the_one.connectors.base` (canonical import, NOT `__init__.py`). Import `_validate_pairing_prefix` from `the_one.connectors._pairing`. The single-site diff at L193 changes `agent.step(envelope.text)` to `agent.step(working_envelope.text)`.

4. **Update imports in `_inbound.py`**: add `from dataclasses import replace`, `from the_one.connectors.base import Deny, NeedsPairing, _default_permit`, `from the_one.connectors._pairing import _validate_pairing_prefix`.

5. **Add the test stub** `StubPluginWithResolver` in `tests/_connector_dispatch_helpers.py` (or sibling). Shape:

   ```python
   from the_one.connectors.base import Permit, ResolveOutcome
   from the_one.connectors._stub import StubPlugin

   class StubPluginWithResolver(StubPlugin):
       """Stub variant that implements the F6 resolve hook.

       Class-level ``resolve_outcome`` knob lets tests configure the
       outcome per case. Default ``Permit()``. ``resolve_calls`` is the
       class-level recording buffer for assertions.
       """
       resolve_outcome: ClassVar[ResolveOutcome] = Permit()
       resolve_calls: ClassVar[list[tuple]] = []

       def resolve(self, account, envelope) -> ResolveOutcome:
           StubPluginWithResolver.resolve_calls.append((account.id, envelope.peer_id))
           return StubPluginWithResolver.resolve_outcome

       @classmethod
       def reset_for_test(cls) -> None:
           StubPlugin.reset_for_test()
           cls.resolve_outcome = Permit()
           cls.resolve_calls = []
   ```

   Tests use `register_for_test("stub", StubPluginWithResolver)` to swap.

6. **Write tests in `tests/test_connectors_inbound.py`**. Use the existing dispatcher test patterns; add a new test class `TestF6Gating` (or extend existing). At minimum 8 tests:
   - `test_stub_without_resolve_permits_via_default_fallback` — register `StubPlugin` (no resolve); dispatch; assert agent.step ran; audit shows `outcome=permit`
   - `test_permit_outcome_dispatches_and_writes_audit` — variant stub returning `Permit()`; assert dispatch ran + audit
   - `test_needs_pairing_with_valid_prefix_strips_persists_dispatches` — account has `config["pairing"]["code"] = "X"`; envelope text `"PAIR X hello"`; assert `peer_id` in `account.config["allowlist"]["peers"]` after; audit shows `outcome=permit, reason=paired`; agent.step received `"hello"` (NOT `"PAIR X hello"`)
   - `test_needs_pairing_with_invalid_prefix_denies_silently` — envelope text `"PAIR wrong hello"`; assert agent.step did NOT run; audit shows `outcome=deny`; `account.config["allowlist"]["peers"]` is unchanged
   - `test_needs_pairing_with_no_prefix_denies` — envelope text `"hello"`; same denial
   - `test_deny_outcome_logs_and_returns` — variant stub returning `Deny("blocked")`; assert agent.step did NOT run; audit shows `outcome=deny, reason=blocked`
   - `test_pairing_persistence_survives_restart` — pair a peer; tear down the dispatcher; rebuild repo + dispatcher; second inbound from same peer hits Permit (allowlist hit on fresh fetch). Implementation: same in-process pattern as F4 e2e tests (don't actually restart a process — just rebuild the repo from the existing DB connection)
   - `test_audit_entries_accrue_across_inbounds` — three sequential inbounds; assert `session_metadata["audit"]` is a list of 3 entries in order

7. **Write tests in `tests/test_db_repositories.py::TestChatSessionRepository`** for `append_to_session_metadata`:
   - `test_append_to_session_metadata_initializes_null_to_dict`
   - `test_append_to_session_metadata_creates_list_for_absent_key`
   - `test_append_to_session_metadata_appends_to_existing_list`
   - `test_append_to_session_metadata_preserves_other_keys`
   - `test_append_to_session_metadata_raises_keyerror_on_missing_session`

8. **Run verification budget** in order:
   1. `pytest tests/test_db_repositories.py::TestChatSessionRepository`
   2. `pytest tests/test_connectors_inbound.py` (includes new + F3/F4 regression)
   3. `pytest tests/test_connectors_resolver.py tests/test_connectors_e2e_session.py tests/test_connectors_session.py tests/test_connectors_pool.py tests/test_connectors.py`
   4. `pytest` (full suite)
   5. `ruff check the_one/connectors/_pairing.py the_one/connectors/_inbound.py the_one/db/repositories.py tests/test_connectors_inbound.py tests/test_db_repositories.py tests/_connector_dispatch_helpers.py`

9. **Update the flight log** with leg-2 entry: scope summary, pairing-prefix convention (`PAIR <code> <message>`), audit-log shape (`session_metadata["audit"] = list[dict]`), `append_to_session_metadata` primitive contract, dispatcher diff site, test counts, race-on-concurrent-pairing documented as known limitation deferred to F10.

10. **Set leg status to `landed`**. Do NOT commit.

## Edge Cases

- **`account.config["pairing"]` absent + `NeedsPairing` returned by plugin**: dispatcher reads `pairing = (account.config.get("pairing") or {}).get("code")` → `None`. `_validate_pairing_prefix` receives `code=""` (or the dispatcher passes `pairing or ""`); returns `(False, text)` immediately on the empty-code guard. Outcome: deny silently with audit `reason="invalid_pairing"` (or the NeedsPairing.reason if non-empty). Documented in `_validate_pairing_prefix` docstring.
- **`account.config["allowlist"]` absent on pairing success**: dispatcher initializes `{"peers": [], "channels": []}` before appending. Leg-1b's validator accepts a freshly-constructed allowlist on `acc_repo.update(account)` because it's well-formed.
- **`envelope.peer_id` already in `allowlist["peers"]`** when pairing succeeds (re-pair race): `if peer_id not in peers: peers.append(...)` is idempotent. Audit entry is still written.
- **Pairing code with embedded whitespace**: `_validate_pairing_prefix` uses single-space separators. A code containing a space would never match (the expected prefix `code + " "` becomes ambiguous). Documented in leg-1b's validator docstring; leg-4 Studio UI should reject codes with whitespace at generation time.
- **`replace(envelope, text=cleaned)`**: `InboundEnvelope` is `frozen=True, slots=True`. `dataclasses.replace` constructs a new instance with the substituted field. Hash and equality on the scalar fields preserve identity; `raw` is `hash=False, compare=False` per the dataclass definition (verified at design time at `connectors/base.py:65-75`).
- **Audit-log entry ordering**: list-append preserves insertion order; SQLite JSON column round-trip preserves list order. Cross-process concurrent writes don't preserve ordering globally (each writer reads-decodes-writes the whole column), but per-session locks at L155 serialize all per-session writes including audit writes. Within a single session, ordering is guaranteed.
- **`json.dumps(metadata)`** — Python `True`/`False`/`None` serialize to JSON `true`/`false`/`null`; round-trip preserves. The audit entry values are all strings + an iso timestamp; no surprises.
- **Concurrent pairing race**: documented as a known limitation. The dispatcher does NOT take an account-level lock around the read-mutate-write cycle. F10 hardening territory.
- **F8 Discord and F9 plugin authors**: a future plugin's `resolve` hook can use any prefix convention (e.g. Discord slash commands). The DEFAULT convention `PAIR <code>` is only used when the plugin returns `NeedsPairing` from its `resolve`. A plugin that wants a different prefix doesn't return `NeedsPairing` — it does its own parsing inside `resolve` and returns `Permit` (auto-pair) or `Deny` directly.
- **Permit + envelope text untouched**: the `Permit` arm does NOT modify `envelope`. `working_envelope = envelope` is preserved; `agent.step(working_envelope.text)` is identical to `agent.step(envelope.text)` in behavior.

## Files Affected

- `the_one/connectors/_pairing.py` — NEW (~30 lines including docstring)
- `the_one/connectors/_inbound.py` — extend `dispatch_inbound` with resolver consult + three-arm branch + pairing flow + audit calls + envelope replacement (~60 lines added; the existing dispatcher remains structurally intact)
- `the_one/db/repositories.py` — add `append_to_session_metadata` to `ChatSessionRepository` (~25 lines)
- `tests/_connector_dispatch_helpers.py` — add `StubPluginWithResolver` variant (~25 lines)
- `tests/test_connectors_inbound.py` — new `TestF6Gating` class with ≥8 tests (~250 lines)
- `tests/test_db_repositories.py::TestChatSessionRepository` — add ≥5 tests for `append_to_session_metadata` (~80 lines)
- `the_one/connectors/_stub.py` — UNCHANGED
- `the_one/connectors/base.py` — UNCHANGED (leg 1a's surface is consumed via canonical import)
- `the_one/db/models.py` — UNCHANGED (leg 1b's validator is consumed via persisted shape)
- `the_one/agent/config.py` — UNCHANGED (leg 1c's field is not consumed by inbound; legs 3/5 consume it for outbound/UI)
- The flight log gains a leg-2 entry

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT modify flight.md
- [ ] Do NOT commit (deferred-batched workflow)

## Citation Audit

Citations verified at design time:
- `the_one/connectors/_inbound.py:45-251` — confirmed (dispatch_inbound)
- `the_one/connectors/_inbound.py:118` — confirmed (account load)
- `the_one/connectors/_inbound.py:146-152` — confirmed (resolve_session call)
- `the_one/connectors/_inbound.py:155` — confirmed (per-session lock)
- `the_one/connectors/_inbound.py:193` — confirmed (agent.step call)
- `the_one/connectors/base.py` Permit/NeedsPairing/Deny/_default_permit — confirmed (leg 1a)
- `the_one/db/models.py:ConnectorAccount.config["pairing"]["code"]` — confirmed (leg 1b)
- `the_one/db/repositories.py:672+` — confirmed (ChatSessionRepository)
- `the_one/db/repositories.py:815-845` — confirmed (update_last_inbound; template for new primitive)
- `the_one/db/repositories.py:458-570` — confirmed (ConnectorAccountRepository)
- `tests/_connector_dispatch_helpers.py:128,151-169` — confirmed (fixture builders)

All citations verified clean.
