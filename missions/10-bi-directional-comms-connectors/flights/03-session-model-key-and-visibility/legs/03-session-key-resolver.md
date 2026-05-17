# Leg: session-key-resolver

**Status**: completed
**Flight**: [Session Model — Schema, Key Normalization, Visibility](../flight.md)

## Objective

Land the pure (envelope, account, plugin, repo) → `ChatSession` resolver in a new `the_one/connectors/_session.py` module. The resolver maps an `InboundEnvelope` to its `chat_sessions` row by:

1. Asking the plugin for the canonical `SessionKey` via the existing `ConnectorPlugin.normalize_session_key(envelope)` Protocol method (already in `connectors/base.py` from F1 — leg 3 does NOT widen the Protocol; it consumes the existing method).
2. Deriving the 4-tuple lookup `(platform, account_id, channel_id, thread_id)` from the SessionKey (the `peer_id` field on `SessionKey` is preserved for audit but NOT in the lookup tuple — per the flight's design decision).
3. Looking up the most recent matching `chat_sessions` row via a new `ChatSessionRepository.find_most_recent_by_external_key(...)` method.
4. If the row exists AND its `last_inbound_at` is within the per-account `session_continuation_seconds` window (resolver: account override → env var → 86400 default) → return that row (reuse).
5. Else → create a new row with the external-key columns populated, `agent_name` from the parameter, `last_inbound_at = _now_iso()`, and a derived title via the optional `plugin.display_channel(envelope)` hook (accessed via `getattr` with a sentinel default — NOT a Protocol widening). Return the new row.

Leg 3 also adds `display_channel` as a class-level method on `StubPlugin` (good citizen) and documents the optional-hook convention in `connectors/README.md`. It does NOT add `display_channel` to the `ConnectorPlugin` Protocol — the architect-revised design decision.

## Context

- **Parent flight design decisions** (see `flight.md`):
  - Lookup key is the 4-tuple `(platform, account_id, channel_id, thread_id)`. `peer_id` is stored on the row at creation but NOT in the lookup tuple. Threads get distinct sessions; DMs are encoded by `channel_id`.
  - Continuation window: per-account `session_continuation_seconds` (added to `connector_accounts` in leg 1) with default 86400 seconds (24h). Resolver mirrors `connectors/_pool.py:_resolve_ttl_seconds` shape — explicit override → env var (`THE_ONE_SESSION_CONTINUATION_SECONDS`, read at call time) → default constant.
  - Stale-supersede semantics: when the most-recent matching row is OUTSIDE the continuation window, create a new row. The old row is preserved untouched (queryable in Chat UI as historical session for the same external location). Non-unique partial expression index on `(platform, connector_account_id, channel_id, COALESCE(thread_id, ''))` makes the lookup fast over many historical rows per external key.
  - `display_channel` is an OPTIONAL hook accessed via `getattr(plugin, "display_channel", None)` with the sentinel-None default. NOT a Protocol widening. Plugins that don't implement it fall back to `envelope.channel_id`. Plugins that do MUST tolerate exceptions — the resolver catches and falls back, keeping resolver resilience independent of plugin authorship.
  - `last_inbound_at` is parsed via `datetime.fromisoformat` for the window check; do NOT rely on string `<` comparison of ISO timestamps.
- **`ConnectorPlugin.normalize_session_key` is the existing Protocol method** (`the_one/connectors/base.py:231`) that delegates key shape to the plugin. The resolver consumes this method's return value rather than re-deriving the key from the envelope directly — preserving plugin authority over key shape (e.g. a future plugin could choose to collapse threads into the parent channel by returning a SessionKey with `thread_id=None`).
- **F2's resolver shape is the template** (`connectors/_pool.py:_resolve_ttl_seconds` at lines 122-154): `int | None` override → env var → constant default. Live-read at call time. Pool's resolver is the canonical pattern the codebase has already converged on.
- **`_now_iso()` write helper** lives at `the_one/db/models.py:13` — `datetime.now(timezone.utc).isoformat()`. Used by all other timestamp writes in models.py and repositories.py.
- **F1 `last_activity` ratification is a leg-4 concern**, NOT leg 3. Leg 3 is pure resolver — no pool acquire, no per-session lock, no dispatch. Leg 4 composes pool + resolver + lock + agent.step into the full dispatcher.

## Inputs

State that must exist before this leg runs:

- Legs 1 + 2 of this flight are `landed` (schema v16 in place; ChatSession has the 7 external-key columns; ConnectorAccount has `session_continuation_seconds`; both repositories round-trip; `Message.visibility` field + codec round-trip + `OPERATOR_VISIBILITY` constant published from `the_one.connectors`).
- `the_one/connectors/base.py:231 — "def normalize_session_key(self, inbound: InboundEnvelope) -> SessionKey:"` (the existing Protocol method).
- `the_one/connectors/base.py:89 — "class SessionKey:"` (frozen + slots dataclass with 5 fields: `platform, account_id, channel_id, thread_id, peer_id`).
- `the_one/connectors/_pool.py:122 — "def _resolve_ttl_seconds(override: int | None = None) -> int:"` (template for `_resolve_continuation_seconds`).
- `the_one/connectors/_pool.py:69 — "_DEFAULT_TTL_SECONDS = 1800"` (template for `_DEFAULT_CONTINUATION_SECONDS = 86400`).
- `the_one/connectors/_stub.py:171 — "def normalize_session_key(self, inbound: InboundEnvelope) -> SessionKey:"` (StubPlugin already implements the Protocol method; leg 3 adds `display_channel` as a new method on this class).
- `the_one/db/repositories.py:658 — "class ChatSessionRepository:"` (extended in leg 1 with the 7 new columns on `create` and `_row_to_model`).
- `the_one/db/models.py:181 — "class ChatSession(BaseModel):"` (extended in leg 1 with the 7 new fields).
- `the_one/db/models.py:13 — "def _now_iso() -> str:"` (UTC ISO write helper).
- `the_one/db/models.py:118 — "class ConnectorAccount(BaseModel):"` (extended in leg 1 with `session_continuation_seconds`).
- `the_one/connectors/README.md` — extant package-level documentation; leg 3 adds an optional-hook convention paragraph.
- `tests/test_connectors.py`, `tests/test_connectors_pool.py`, `tests/test_connectors_e2e.py` — extant test files; leg 3 adds a new `tests/test_connectors_session.py`.
- Leg 2's uncommitted changes are in the working tree on branch `flight/03-session-model-key-and-visibility`.

## Outputs

State that must exist after this leg completes:

- New module `the_one/connectors/_session.py` with three public symbols:
  - `_DEFAULT_CONTINUATION_SECONDS = 86400` (module-level constant — mirrors `_DEFAULT_TTL_SECONDS` pattern from `_pool.py:69`).
  - `_resolve_continuation_seconds(override: int | None = None) -> int` (free function — mirrors `_pool.py:_resolve_ttl_seconds`).
  - `async def resolve_session(envelope: InboundEnvelope, account: ConnectorAccount, repo: ChatSessionRepository, *, agent_name: str, plugin: ConnectorPlugin) -> ChatSession` (the resolver).
- New method `ChatSessionRepository.find_most_recent_by_external_key(platform: str, connector_account_id: str, channel_id: str, thread_id: str | None) -> ChatSession | None` in `the_one/db/repositories.py`. SQL uses `COALESCE(thread_id, '') = COALESCE(?, '')` to mirror the partial-index expression and handle NULL-distinct semantics.
- New class method `StubPlugin.display_channel(envelope: InboundEnvelope) -> str` returning `f"stub:{envelope.channel_id}"` — good-citizen demonstration of the optional-hook convention.
- `the_one/connectors/README.md` gains a "§N. Optional hooks" section (numbering decided at implementation per the README's existing structure) documenting the `getattr(plugin, "<hook>", None)` discovery pattern, citing `display_channel` as the first instance, and noting the convention applies to additive plugin extension that doesn't warrant a Protocol method.
- New test file `tests/test_connectors_session.py` covering:
  - `_resolve_continuation_seconds` resolution order (override beats env var beats default).
  - Env var read at call time (monkeypatch changes resolution without process restart).
  - Non-int env var falls back to default with a warning (mirror of `_resolve_ttl_seconds` behavior).
  - `resolve_session` no-match path → new row created with all external-key columns populated, `agent_name` set, `last_inbound_at ≈ now`, title derived via `plugin.display_channel`.
  - `resolve_session` within-window match → existing row returned, no new row created.
  - `resolve_session` outside-window match → new row created, old row preserved untouched.
  - `resolve_session` per-thread distinct: envelopes with `thread_id="A"` and `thread_id="B"` (same channel) produce distinct sessions.
  - `resolve_session` DM-shaped envelope (no thread, channel encodes peer pair) — session created with `thread_id=None`.
  - `resolve_session` `display_channel` fallback when hook is missing (a plugin without the method → title is `envelope.channel_id`).
  - `resolve_session` `display_channel` fallback when hook raises (plugin's method throws → resolver catches and uses `envelope.channel_id`).
  - `resolve_session` plugin's `normalize_session_key` decides key shape — if a plugin returns a SessionKey with `thread_id=None` despite envelope having a thread, the resolver respects the plugin's choice (uses None for lookup AND for the new row's stored `thread_id` column).
- `ChatSessionRepository.find_most_recent_by_external_key` is unit-tested in `tests/test_db_repositories.py` (or wherever the existing ChatSessionRepository tests live):
  - Returns None when no match.
  - Returns the most recent matching row by `updated_at DESC`.
  - COALESCE handling: rows with `thread_id=NULL` match a query with `thread_id=None`; rows with `thread_id="A"` don't match a query with `thread_id=None`.
- Flight log gains a "Leg Progress: session-key-resolver" entry.
- Leg status flipped to `landed` in this file's header.
- This leg ticked off in `flight.md` under `### Legs`.

## Acceptance Criteria

- [ ] `the_one/connectors/_session.py` exists as a new module (private; underscore-prefixed).
- [ ] `_DEFAULT_CONTINUATION_SECONDS = 86400` is a module-level constant.
- [ ] `_resolve_continuation_seconds(override: int | None = None) -> int` function exists with resolution order: explicit override → `THE_ONE_SESSION_CONTINUATION_SECONDS` env var → `_DEFAULT_CONTINUATION_SECONDS`. Env var is read at call time (NOT cached). Non-int env var → fallback to default with `logger.warning(...)` (mirror of `_resolve_ttl_seconds:148-153`).
- [ ] `async def resolve_session(envelope, account, repo, *, agent_name, plugin) -> ChatSession` exists with the signature exactly as in Inputs/Outputs.
- [ ] The resolver calls `plugin.normalize_session_key(envelope)` to obtain the `SessionKey` (delegates to the existing Protocol method).
- [ ] The lookup tuple consumed by the SQL is `(key.platform, key.account_id, key.channel_id, key.thread_id)` — the 4-tuple, with `peer_id` NOT participating in the lookup.
- [ ] When `repo.find_most_recent_by_external_key(...)` returns a row AND `(now - parsed(row.last_inbound_at)).total_seconds() < continuation_seconds` → resolver returns that row (reuse path).
- [ ] When the lookup returns None OR the row is outside the window → resolver creates a new `ChatSession` with: `id = uuid.uuid4().hex` (full hex; the truncated-to-12 pattern at `the_one/interfaces/web/app.py:323` is for UI-shortener ephemeral ids, NOT primary keys), `agent_name = agent_name` (the parameter), `title = derived_title(envelope, plugin)`, `messages = "[]"` (explicit empty-history JSON — matches `ChatSession.messages` default at the model layer and avoids relying on Pydantic's default to populate it), `created_at = updated_at = last_inbound_at = now_iso` (single timestamp value reused — see Implementation Guidance for the inline `datetime.now(timezone.utc).isoformat()` pattern; do NOT import the private `_now_iso` helper), and all 5 external-key columns populated from the SessionKey: `platform, connector_account_id (= key.account_id), channel_id, thread_id, peer_id` (peer_id IS stored on the row, just not in the lookup tuple), with `session_metadata = None`. Calls `await repo.create(new_session)` and returns it.
- [ ] Title derivation: the resolver accesses `getattr(plugin, "display_channel", None)`. If non-None, calls `plugin.display_channel(envelope)` inside a `try / except Exception` — on any exception (or empty-string return), falls back to `envelope.channel_id`. Logs the exception (`logger.warning(...)`) on the catch path so plugin bugs surface in test/operator-side logs without breaking the resolver.
- [ ] `datetime.fromisoformat(row.last_inbound_at)` is the parse helper used for the window check; do NOT compare ISO timestamps as strings.
- [ ] `StubPlugin` gains a class-level method `display_channel(self, envelope: InboundEnvelope) -> str` returning `f"stub:{envelope.channel_id}"`. The method goes in `the_one/connectors/_stub.py` alongside `normalize_session_key`.
- [ ] `ChatSessionRepository.find_most_recent_by_external_key(platform, connector_account_id, channel_id, thread_id) -> ChatSession | None` exists at `the_one/db/repositories.py`. SQL: `SELECT * FROM chat_sessions WHERE platform = ? AND connector_account_id = ? AND channel_id = ? AND COALESCE(thread_id, '') = COALESCE(?, '') ORDER BY updated_at DESC LIMIT 1`. Uses `self._row_to_model(...)` if a row is found; returns None otherwise.
- [ ] `connectors/README.md` gains a clearly-titled section (e.g. "§N. Optional hooks") explaining the `getattr(plugin, "<hook>", None)` discovery pattern, citing `display_channel` as the first example, and noting:
  1. Optional hooks do NOT widen the `ConnectorPlugin` Protocol.
  2. Plugins that implement an optional hook MUST tolerate the resolver's exception-catching behavior — raising is treated as "use fallback."
  3. Future flights (notably F4's `ConnectorClient` outbound-send extension if it lands as optional) may use the same pattern.
- [ ] New test file `tests/test_connectors_session.py` covers all eleven scenarios in "Outputs" above. Each test is named descriptively (`test_resolve_session_creates_new_row_on_first_contact`, `test_resolve_session_reuses_row_within_window`, etc.).
- [ ] `tests/test_db_repositories.py` gains tests for `find_most_recent_by_external_key` (the three scenarios in Outputs).
- [ ] `make test` clean (no regressions; new test count is added).
- [ ] `make lint` clean (no new ruff findings).
- [ ] Flight log updated with leg-completion entry citing test counts before/after, deviations encountered (if any), any unforeseen findings.
- [ ] Leg status flipped to `landed`.
- [ ] This leg ticked off in `flight.md` under `### Legs`.

## Verification Steps

- **Module exists** — `ls the_one/connectors/_session.py` shows the new file.
- **Constants + functions** — `grep -n "_DEFAULT_CONTINUATION_SECONDS\|_resolve_continuation_seconds\|async def resolve_session" the_one/connectors/_session.py` shows all three.
- **Plugin authority** — `grep -n "normalize_session_key\|display_channel" the_one/connectors/_session.py` shows the plugin-method calls.
- **`getattr` discovery for display_channel** — `grep -n "getattr.*display_channel" the_one/connectors/_session.py` shows the sentinel-default access.
- **Datetime parsing** — `grep -n "fromisoformat" the_one/connectors/_session.py` shows explicit parsing (NOT string compare).
- **Repository method** — `grep -n "find_most_recent_by_external_key" the_one/db/repositories.py` shows the new method.
- **StubPlugin hook** — `grep -n "display_channel" the_one/connectors/_stub.py` shows the new class method.
- **README updated** — `grep -n "Optional hooks\|optional hook" the_one/connectors/README.md` shows the new section.
- **Scoped tests** — `docker exec the-one pytest tests/test_connectors_session.py tests/test_db_repositories.py -x --timeout 30 -v` passes.
- **Full suite** — `docker exec the-one pytest -x --timeout 30` shows green (~1845 + new tests).
- **Lint** — `docker exec the-one ruff check the_one/ tests/` clean.

## Implementation Guidance

1. **Create `the_one/connectors/_session.py`** as a new module:

   ```python
   """Session-key normalization and continuation-window resolver.

   M10 F03 L03: pure (envelope, account, plugin, repo) → ChatSession
   resolver. Composes the plugin's :meth:`ConnectorPlugin.normalize_session_key`
   (the existing F1 Protocol method) with a repository lookup and a
   continuation-window check, creating a new chat_sessions row on first
   contact or after the window elapses; reusing the most-recent matching
   row when within the window.

   The continuation window resolver mirrors
   :func:`the_one.connectors._pool._resolve_ttl_seconds`'s shape: explicit
   override → env var (read at call time) → default constant. The override
   is the per-account ``ConnectorAccount.session_continuation_seconds``
   (leg 1 added the column + Pydantic field); the env var is
   ``THE_ONE_SESSION_CONTINUATION_SECONDS``; the default is 86400 (24h).

   Title derivation uses an OPTIONAL plugin hook ``display_channel``
   accessed via ``getattr(plugin, "display_channel", None)``. This is NOT a
   widening of the :class:`ConnectorPlugin` Protocol — see
   ``the_one/connectors/README.md`` "Optional hooks" section.
   """

   from __future__ import annotations

   import logging
   import os
   import uuid
   from datetime import datetime, timezone

   from the_one.connectors.base import ConnectorPlugin, InboundEnvelope
   from the_one.db.models import ChatSession, ConnectorAccount
   from the_one.db.repositories import ChatSessionRepository

   # NOTE: `_now_iso` in `the_one/db/models.py:13-14` is private (underscore-
   # prefixed). Rather than make this resolver the first cross-package
   # consumer of a leading-underscore symbol, inline the canonical write
   # form. If a future module needs this pattern more than twice, promote
   # `_now_iso` → `now_iso` and update the two existing call sites.
   def _utc_now_iso() -> str:
       return datetime.now(timezone.utc).isoformat()

   logger = logging.getLogger(__name__)

   _DEFAULT_CONTINUATION_SECONDS = 86400  # 24 hours


   def _resolve_continuation_seconds(override: int | None = None) -> int:
       """Resolve the per-account chat-session continuation window in seconds.

       Resolution order: explicit ``override`` (if not None) → env var
       ``THE_ONE_SESSION_CONTINUATION_SECONDS`` (if set + parseable) →
       ``_DEFAULT_CONTINUATION_SECONDS`` (86400). Env var is read at call
       time so test monkeypatching works; mirrors
       :func:`the_one.connectors._pool._resolve_ttl_seconds`.

       The override is the per-account
       ``ConnectorAccount.session_continuation_seconds`` value, passed
       through by :func:`resolve_session`. The resolver stays ignorant of
       which model field drives the override; the model owns the field
       name, the resolver owns the precedence. The ``override is not None``
       guard short-circuits BEFORE the env-var read by design — the
       operator's explicit per-account choice always wins.

       Non-int env-var values fall back to the default with a warning —
       matches the pool resolver's "fail open, don't crash" stance.
       """
       if override is not None:
           return override
       raw = os.environ.get("THE_ONE_SESSION_CONTINUATION_SECONDS")
       if raw is None:
           return _DEFAULT_CONTINUATION_SECONDS
       try:
           return int(raw)
       except ValueError:
           logger.warning(
               "THE_ONE_SESSION_CONTINUATION_SECONDS=%r is not an int; falling back to %d",
               raw,
               _DEFAULT_CONTINUATION_SECONDS,
           )
           return _DEFAULT_CONTINUATION_SECONDS


   def _derive_title(envelope: InboundEnvelope, plugin: ConnectorPlugin) -> str:
       """Derive a human-readable session title for first-contact session creation.

       Calls the OPTIONAL ``plugin.display_channel(envelope)`` hook via
       :func:`getattr` with a sentinel-None default. Catches any exception
       from the hook AND any empty-string return; falls back to
       ``envelope.channel_id`` so the resolver is independent of plugin
       authorship discipline. Logs caught exceptions so plugin bugs surface
       without breaking inbound dispatch.

       NOT a widening of :class:`ConnectorPlugin`. See
       ``the_one/connectors/README.md`` "Optional hooks" section for the
       convention.
       """
       hook = getattr(plugin, "display_channel", None)
       if hook is None:
           return envelope.channel_id
       try:
           result = hook(envelope)
       except Exception:
           logger.warning(
               "plugin.display_channel raised; falling back to channel_id",
               exc_info=True,
           )
           return envelope.channel_id
       if not result:
           return envelope.channel_id
       return result


   async def resolve_session(
       envelope: InboundEnvelope,
       account: ConnectorAccount,
       repo: ChatSessionRepository,
       *,
       agent_name: str,
       plugin: ConnectorPlugin,
   ) -> ChatSession:
       """Map an inbound envelope to its chat_sessions row.

       Steps:

       1. Ask the plugin for the canonical :class:`SessionKey` via
          :meth:`ConnectorPlugin.normalize_session_key`. The plugin
          decides which envelope fields participate in the key; the
          resolver respects that decision.
       2. Derive the 4-tuple lookup ``(platform, account_id, channel_id,
          thread_id)`` from the SessionKey. ``peer_id`` is NOT in the
          lookup tuple (per flight design — stored on the row at creation
          for audit, but doesn't participate in matching).
       3. Look up the most recent matching row via
          :meth:`ChatSessionRepository.find_most_recent_by_external_key`.
       4. If a row exists AND its ``last_inbound_at`` is within the
          per-account continuation window → return that row (reuse path).
          The dispatcher in F3 L4 calls
          :meth:`ChatSessionRepository.update_last_inbound` to bump the
          timestamp; F3 L3 does NOT touch the existing row.
       5. Else (no match OR outside the window) → create a new row with
          the external-key columns populated, ``agent_name`` set, title
          derived via the optional ``display_channel`` hook,
          ``last_inbound_at = _now_iso()``. Returns the new row.

       Pure function — no pool acquire, no lock, no agent.step. F3 L4's
       dispatcher composes this with the pool and per-session lock.
       """
       key = plugin.normalize_session_key(envelope)
       continuation = _resolve_continuation_seconds(
           override=account.session_continuation_seconds
       )

       existing = await repo.find_most_recent_by_external_key(
           platform=key.platform,
           connector_account_id=key.account_id,
           channel_id=key.channel_id,
           thread_id=key.thread_id,
       )

       if existing is not None and existing.last_inbound_at is not None:
           try:
               last = datetime.fromisoformat(existing.last_inbound_at)
           except ValueError:
               logger.warning(
                   "chat_sessions.last_inbound_at=%r is not ISO; treating as stale",
                   existing.last_inbound_at,
               )
               last = None
           if last is not None:
               # Normalise to UTC for the comparison — _now_iso writes UTC,
               # but a hand-built test row may write naive; if naive, treat
               # as UTC to match the canonical write helper.
               if last.tzinfo is None:
                   last = last.replace(tzinfo=timezone.utc)
               now = datetime.now(timezone.utc)
               if (now - last).total_seconds() < continuation:
                   return existing

       # Create a new row on the (no-match OR outside-window) paths.
       title = _derive_title(envelope, plugin)
       now_iso = _utc_now_iso()
       new_session = ChatSession(
           id=uuid.uuid4().hex,
           agent_name=agent_name,
           title=title,
           messages="[]",
           created_at=now_iso,
           updated_at=now_iso,
           platform=key.platform,
           connector_account_id=key.account_id,
           channel_id=key.channel_id,
           thread_id=key.thread_id,
           peer_id=key.peer_id,
           session_metadata=None,
           last_inbound_at=now_iso,
       )
       await repo.create(new_session)
       return new_session
   ```

   Note on the id-generation pattern: full `uuid.uuid4().hex` (32 hex chars). The single existing site at `the_one/interfaces/web/app.py:323` truncates to 12 chars (`uuid.uuid4().hex[:12]`) but that's a UI-shortener for ephemeral client-side ids — NOT a primary-key pattern. Test fixtures use untrimmed hex or hand-built "s1" style ids. Use full hex here.

2. **Add `ChatSessionRepository.find_most_recent_by_external_key`** to `the_one/db/repositories.py` (after `get` at line ~681 or somewhere natural for the existing method ordering):

   ```python
   async def find_most_recent_by_external_key(
       self,
       *,
       platform: str,
       connector_account_id: str,
       channel_id: str,
       thread_id: str | None,
   ) -> ChatSession | None:
       """Return the most recent connector-keyed session for the external 4-tuple.

       Uses ``COALESCE(thread_id, '')`` on both sides to mirror the
       partial-index expression at
       ``the_one/db/schema.py`` (v16 migration) and handle SQLite's
       NULL-distinct semantics — a query with ``thread_id=None`` matches
       rows where the column is NULL (treated as empty string on both
       sides by COALESCE).

       Ordered by ``updated_at DESC LIMIT 1`` — the active session for
       this external location is the most-recently-touched row. Older
       superseded sessions are preserved (per flight design: historical
       sessions remain queryable in Chat UI as distinct rows).

       M10 F03 L03 — consumed by
       :func:`the_one.connectors._session.resolve_session`.
       """
       async with self.conn.execute(
           "SELECT * FROM chat_sessions"
           " WHERE platform = ? AND connector_account_id = ?"
           " AND channel_id = ? AND COALESCE(thread_id, '') = COALESCE(?, '')"
           " ORDER BY updated_at DESC LIMIT 1",
           (platform, connector_account_id, channel_id, thread_id),
       ) as cur:
           row = await cur.fetchone()
       if row is None:
           return None
       return self._row_to_model(row)
   ```

3. **Add `display_channel` to `StubPlugin`** in `the_one/connectors/_stub.py` (after `normalize_session_key` at line 171):

   ```python
   def display_channel(self, envelope: InboundEnvelope) -> str:
       """Render a human-readable channel label for session-title derivation.

       OPTIONAL hook accessed via ``getattr`` by
       :func:`the_one.connectors._session._derive_title`. Real plugins
       can return platform-native labels (e.g. ``"#engineering"`` for
       Discord guild channels, ``"@alice"`` for Slack DMs). The stub
       returns a synthetic label encoding the channel id.

       See ``the_one/connectors/README.md`` "Optional hooks" section
       for the convention.
       """
       return f"stub:{envelope.channel_id}"
   ```

4. **Update `the_one/connectors/README.md`** with a new section documenting the optional-hook convention. Insert AFTER §3 (Protocol decomposition) — leg-3 author chooses the section number; the document's existing pattern uses `## §N. Title`. Suggested content:

   ```markdown
   ## §N. Optional hooks (additive plugin extension)

   Some plugin extensions are useful when present but not essential for the
   subsystem to function. For these, the connector subsystem uses an
   **optional-hook convention** rather than widening a Protocol:

   - The consumer accesses the hook via ``getattr(plugin, "<hook>", None)``
     and falls back to a sensible default at the call site if the attribute
     is absent.
   - The hook is documented as an optional method on plugins but is NOT
     declared on the :class:`ConnectorPlugin` Protocol at
     ``the_one/connectors/base.py``.
   - Plugins that implement an optional hook MUST tolerate the consumer's
     exception-catching behavior — the consumer catches any exception from
     the hook and uses the fallback. Plugin authors are NOT expected to
     never raise.

   First instance: **``display_channel(envelope: InboundEnvelope) -> str``**
   for session-title derivation in
   :func:`the_one.connectors._session._derive_title` (M10 F03 L03). Plugins
   that implement it return a human-readable channel label
   (e.g. ``"#engineering"``, ``"@alice"``); plugins that don't fall through
   to ``envelope.channel_id`` at the resolver layer.

   When to add a method to the Protocol vs. use the optional-hook convention:

   - **Protocol method**: every plugin MUST implement; the subsystem
     mechanically depends on it being callable (e.g.
     :meth:`ConnectorPlugin.connect`, :meth:`ConnectorPlugin.doctor`).
   - **Optional hook**: most plugins benefit from implementing it but the
     subsystem has a working fallback without it; forcing every connector
     author to write a no-op stub would be friction (e.g.
     ``display_channel``).
   ```

5. **Add tests** in `tests/test_connectors_session.py` (new file). Test against `StubPlugin` for the happy path AND against a one-off `_MinimalPlugin` that omits `display_channel` for the fallback test. Use the same test-conn pattern as `tests/test_db_repositories.py` (look up the existing fixture pattern there — likely `aiosqlite.connect(":memory:")` with `ensure_schema` applied). Cover:

   - `test_resolve_continuation_seconds_override_beats_env_and_default`
   - `test_resolve_continuation_seconds_env_beats_default`
   - `test_resolve_continuation_seconds_default_when_no_env`
   - `test_resolve_continuation_seconds_non_int_env_falls_back_to_default`
   - `test_resolve_continuation_seconds_env_read_at_call_time` (monkeypatch env after import; resolver picks up the change)
   - `test_resolve_session_creates_new_row_on_first_contact` (asserts all external-key columns populated, agent_name set, last_inbound_at ≈ now, title from `display_channel`)
   - `test_resolve_session_reuses_row_within_window`
   - `test_resolve_session_creates_new_row_outside_window` (verify old row is preserved untouched)
   - `test_resolve_session_per_thread_distinct` (thread A vs thread B → two rows)
   - `test_resolve_session_dm_shape` (thread_id=None envelope)
   - `test_resolve_session_display_channel_missing_falls_back_to_channel_id` (use a `_MinimalPlugin` class that doesn't implement `display_channel`)
   - `test_resolve_session_display_channel_raises_falls_back_to_channel_id` (use a plugin whose `display_channel` raises; assert resolver returns successfully with title from envelope)
   - `test_resolve_session_plugin_decides_key_shape` (plugin returns a SessionKey with `thread_id=None` despite envelope having a thread; resolver stores `thread_id=None` on the new row)
   - `test_resolve_session_peer_id_stored_but_not_in_lookup` (two envelopes with same channel but different peer_id resolve to the SAME session — peer_id doesn't fork the lookup; but the FIRST row's peer_id is preserved)

6. **Add `find_most_recent_by_external_key` tests** to `tests/test_db_repositories.py` (extend `TestChatSessionRepository`):
   - `test_find_most_recent_by_external_key_returns_none_on_no_match`
   - `test_find_most_recent_by_external_key_returns_most_recent_by_updated_at` (seed 3 rows for the same key with different `updated_at`; assert the most recent is returned)
   - `test_find_most_recent_by_external_key_coalesce_null_thread_id` (seed a row with `thread_id=NULL`; query with `thread_id=None` matches; query with `thread_id="A"` does NOT match)

7. **Test environment**: container test discipline applies — `docker exec the-one pytest tests/test_connectors_session.py tests/test_db_repositories.py -x --timeout 30 -v` first, then full suite.

8. **Update flight log** with a "Leg Progress: session-key-resolver" entry. Capture: timestamps, summary, test-count delta from leg 2's 1845, deviations.

9. **Flip leg status to `landed`**, tick in flight.md, signal `[HANDOFF:review-needed]`. **Do NOT commit**.

## Edge Cases

- **`last_inbound_at IS NULL` on a row** (legacy v15 row migrated to v16 via the legacy-row fixture path, OR a row created outside the resolver): the resolver treats it as "outside window" and creates a new row. The `existing.last_inbound_at is not None` guard handles this.

- **`last_inbound_at` is non-ISO**: `datetime.fromisoformat` raises `ValueError`. The resolver catches and treats as stale (creates a new row). Logged via `logger.warning`. This protects against corrupt rows or future timestamp-format changes; F3's write path always uses `_now_iso()` so this branch should be untested-by-production but tested-by-fuzz.

- **Naive vs. UTC datetime in `last_inbound_at`**: `_now_iso()` always emits UTC ISO with timezone. If a hand-built test row writes a naive timestamp (no tzinfo), the resolver treats it as UTC to match the canonical write helper (the `last.tzinfo is None` branch). Production rows should always be tz-aware; the branch exists for robust test fixtures.

- **`display_channel` returns empty string**: the resolver treats empty string as "no useful title" and falls back to `envelope.channel_id`. The `if not result:` guard handles this.

- **Concurrent first-contact for the same external key**: leg 3 is pure (no lock). Two concurrent `resolve_session` calls for the same (platform, account, channel, thread) and no existing row could BOTH create new rows. **This is acceptable for F3** because the lookup is most-recent-by-updated_at and creation order doesn't matter — both rows land, the next inbound resolves to the most recent. Leg 4's dispatcher acquires the per-session lock AFTER `resolve_session` returns, so the resolver itself doesn't need locking. If a future use case demands strict first-contact serialization, that's a leg-4 concern (the dispatcher can lock earlier in the pipeline). Documented here for forward-traceability.

- **`account.session_continuation_seconds` is None**: this is the explicit "no per-account override" case; the resolver falls through to env var → default. Pydantic validator at the model layer enforces `1 ≤ value ≤ 604800` for non-None values; the resolver does NOT re-validate.

- **`peer_id` in the SessionKey but the lookup uses 4-tuple only**: peer_id is in the SessionKey for plugin use (e.g. plugin might want to populate it for DM identification semantics) and is stored on the chat_sessions row at creation (for audit), but the SQL lookup is 4-tuple only. The flight design's "peer_id NOT in lookup key" decision is enforced at the resolver layer, not at the SessionKey-dataclass layer.

- **`uuid.uuid4().hex` vs. other id-generation patterns**: verify by reading existing chat-session creation sites in `the_one/interfaces/web/app.py` BEFORE implementing — use the project's canonical pattern.

## Files Affected

- `the_one/connectors/_session.py` — new module with the resolver
- `the_one/db/repositories.py` — add `find_most_recent_by_external_key` method to `ChatSessionRepository`
- `the_one/connectors/_stub.py` — add `display_channel` class method
- `the_one/connectors/README.md` — new "Optional hooks" section
- `tests/test_connectors_session.py` — new test file (14 tests covering all scenarios)
- `tests/test_db_repositories.py` — 3 new tests for `find_most_recent_by_external_key`
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/flight-log.md` — leg-completion entry
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/flight.md` — tick leg 3 under `### Legs`
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/legs/03-session-key-resolver.md` — this file's status → `landed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (scoped + full suite)
- [x] Lint clean
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md's Legs list
- [x] Do NOT commit — agentic-workflow batched-review model defers commit to flight end
- [x] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

10 citations verified against current code at leg design time:

- `the_one/connectors/base.py:231` (`def normalize_session_key`) — verified.
- `the_one/connectors/base.py:89` (`class SessionKey:`) — verified at line 89 (the `@dataclass(frozen=True, slots=True)` decorator is line 89; the class line is 90).
- `the_one/connectors/_pool.py:122` (`def _resolve_ttl_seconds`) — verified.
- `the_one/connectors/_pool.py:69` (`_DEFAULT_TTL_SECONDS = 1800`) — verified.
- `the_one/connectors/_stub.py:171` (`def normalize_session_key`) — verified.
- `the_one/db/repositories.py:658` (`class ChatSessionRepository:`) — verified.
- `the_one/db/models.py:181` (`class ChatSession`) — verified (extended by leg 1; check the updated shape includes the 7 new fields).
- `the_one/db/models.py:13` (`def _now_iso`) — verified.
- `the_one/db/models.py:118` (`class ConnectorAccount`) — verified (extended by leg 1 with `session_continuation_seconds`).
- `the_one/connectors/README.md` — verified extant; leg-3 author confirms current section numbering before inserting the new "Optional hooks" section.
