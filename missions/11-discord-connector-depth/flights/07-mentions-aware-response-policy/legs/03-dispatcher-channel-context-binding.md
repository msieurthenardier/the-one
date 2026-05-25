# Leg: dispatcher-channel-context-binding

**Status**: completed
**Flight**: [Mentions-Aware Response Policy](../flight.md)

## Objective

Add `bind_channel_context(messages, pre_step_len, channel_id, channel_name)` to `the_one/connectors/post_step_metadata.py`; wire it into the dispatcher's post-step block (after `bind_peer_name`) so the appended USER message picks up `channel_id` always (from the envelope) and `channel_name` when the F3 L4 discoverable-entities cache resolves a label; project both new fields onto the codec's USER-event output (which serves BOTH replay and live broadcast through the connector-inbound path — `_inbound.py` calls `messages_to_ui_events` then `broadcast_to_session`, single projection site); finalize the `post-step-dispatcher-message-metadata-binding` convention's `pending L3` citation.

## Context

- **Flight DD §6 (lift the mutators)** — `bind_channel_context` is the third mutator in the lifted module, completing the n=3 set the convention names. L1 already added the L3 forward-reference (`pending L3 within this flight`) in `agents.md`; L3 finalizes it by adding the citation with concrete line numbers.
- **Flight DD §1 step 3 + DD §5 (channel context for the engaged agent)** — `Message.channel_id` and `Message.channel_name` reach the LLM payload via L4's provider-side inline prefix; L3 is the binding slice that ensures the fields are populated on the dispatched USER message. The fields also surface in the Chat UI (replay + live broadcast) so the operator sees `discord-username: ...` AND can see which channel the message came from, even cross-channel in the unified history. **Note: chat.js client-side rendering of channel attribution is NOT in L3 scope** — L3 ships the WS payload field; a future leg (or L11 Studio UI work) wires the UI rendering. L3 only ensures the data reaches the WS client.
- **Single projection site discipline** — the connector-inbound path goes `_inbound.py:701-707` → `messages_to_ui_events` (codec) → `broadcast_to_session` (in `the_one/sessions/_broadcast.py`). Both replay AND live broadcast for connector inbound use this same codec function. `the_one/interfaces/web/app.py:_process_and_broadcast` (lines ~880-899) handles the **operator-typed** USER input path, which has no `peer_name` projection today (the comment at app.py:892-896 documents this); L3 does NOT modify `app.py` (operator-typed turns carry no inbound channel context — they originate from the operator console, not a Discord channel).
- **`InboundEnvelope.channel_id` is always populated** (per `the_one/connectors/base.py:InboundEnvelope`) — the Discord translator at `_discord_translate.py:122` sets `channel_id=channel_id_str` unconditionally. So `bind_channel_context` always has `channel_id` to bind. `channel_name` is conditional: resolved from the F3 L4 discoverable-entities cache by matching `envelope.channel_id` against `cache.channels[i].id`; if the cache is cold (no entry yet), the entry is missing, or the plugin doesn't implement `enumerate_discoverable_entities` (stub plugin), `channel_name` stays `None`. L4's provider projection handles partial-absence gracefully.
- **F3 discoverable-entities cache read API** — `the_one/connectors/_pool.py:_get_account_cache_snapshot(account_id) -> _DiscoverableCacheSnapshot | None` is the async read. The dispatcher post-step is inside a per-session lock (`session_locks[session_row.id]`) but the pool lock is separate; awaiting the cache read from inside the session-lock block is safe — the pool lock acquisition is brief and holds no callable that could in turn try to acquire any session lock (no ordering violation possible). The snapshot exposes a `cache: DiscoverableEntities | None` field; the cache exposes `channels: list[DiscoverableEntity]` with each entry carrying `id: str` and `label: str`.
- **Resolution helper** — a small synchronous helper `resolve_channel_name(cache, channel_id) -> str | None` (NO leading underscore — it is part of the module's public surface, imported by `_inbound.py`) factors the cache walk: iterate `cache.channels`, return `entity.label` where `entity.id == channel_id`, else None. This helper lives in `post_step_metadata.py` so `bind_channel_context` can be tested in isolation by passing the cache directly; the dispatcher fetches the snapshot async and passes the resolved `channel_name` (already-resolved) to the binder. This keeps `bind_channel_context` itself synchronous and pure (same shape as `bind_peer_name`).
- **Projection site** — `the_one/db/codec.py:messages_to_ui_events` is THE canonical Chat UI event projection. The connector dispatcher's live broadcast at `_inbound.py:701-707` calls this same function then routes through `broadcast_to_session`, so a single edit to the codec's USER-event spread covers BOTH replay AND live broadcast for connector inbound. L3 extends the USER-event spread to include `channel_id` and `channel_name` (only when non-None — same pattern as `peer_name`).

## Inputs

- L1 + L2 landed (uncommitted). `the_one/connectors/post_step_metadata.py` exists with `tag_post_step_visibility` and `bind_peer_name`; its docstring forward-references `bind_channel_context` as "pending F7 L3" (line 41). `Message` dataclass has `channel_id` and `channel_name` fields; codec round-trips them.
- `the_one/connectors/_inbound.py` post-step block (around line 630–670 after L1) calls `tag_post_step_visibility` and `bind_peer_name`. L3 appends a third call after `bind_peer_name`.
- `the_one/connectors/_pool.py:_get_account_cache_snapshot` (async) is the read API; `the_one/connectors/base.py:DiscoverableEntities` has `channels: list[DiscoverableEntity]` with `(id, label)` fields each.
- `the_one/connectors/base.py:InboundEnvelope` carries `channel_id: str` (always set) and does NOT carry `channel_name`. The Discord translator at `_discord_translate.py:119–134` populates `channel_id`; non-Discord plugins (stub) do the same shape.
- `the_one/db/codec.py:messages_to_ui_events` (around lines 137–235) projects `peer_name` onto USER events via a `**peer` spread. L3 extends the same shape for channel_id + channel_name.
- The live broadcast for connector-inbound USER events flows through `the_one/connectors/_inbound.py:701-707` → `messages_to_ui_events` (codec) → `broadcast_to_session` (`the_one/sessions/_broadcast.py:42`). The codec change at `db/codec.py:messages_to_ui_events` covers both replay and live broadcast. **No separate `app.py` edit needed** — `app.py:_process_and_broadcast` is for operator-typed input, not connector inbound (the existing peer_name projection in F6 L3 only touched the codec; F6 L3's `test_dispatch_inbound_broadcasts_carry_peer_name` test exercises this single-projection-site discipline).
- `tests/test_connectors_inbound.py:593–619` (`test_dispatch_inbound_persists_inbound_with_peer_name_from_envelope`) is the binding test precedent.
- `tests/test_connectors_inbound_broadcast.py:301–356` (`test_dispatch_inbound_broadcasts_carry_peer_name`) is the broadcast test precedent.
- `tests/test_connectors_post_step_metadata.py` (renamed by L1; contains `bind_peer_name` unit tests) is the unit-test home for `bind_channel_context`.
- `the_one/agents.md`'s `post-step-dispatcher-message-metadata-binding` block (post-L1) has a `pending L3 within this flight` placeholder line for `bind_channel_context`; L3 replaces the placeholder with a concrete citation.

## Outputs

- `the_one/connectors/post_step_metadata.py`:
  - New synchronous helper `resolve_channel_name(cache: DiscoverableEntities | None, channel_id: str) -> str | None` — walks `cache.channels`, returns `label` where `id` matches, else None. Defensive against `cache is None` (returns None directly).
  - New mutator `bind_channel_context(messages: list[Message], pre_step_len: int, channel_id: str, channel_name: str | None) -> None` — asserts the message at `pre_step_len` is `Role.USER`, sets `messages[pre_step_len].channel_id = channel_id` always, sets `messages[pre_step_len].channel_name = channel_name` (passing through None as-is). Same shape as `bind_peer_name`: synchronous, pure, scope-limited to one USER message slot.
  - Module docstring updated: the `bind_channel_context — pending F7 L3` forward-reference becomes a confirmed citation. The "(L3)" annotation is replaced with the actual implementation summary.
- `the_one/connectors/_inbound.py`:
  - Import extended: `from the_one.connectors.post_step_metadata import bind_channel_context, bind_peer_name, tag_post_step_visibility` (alphabetical order after extension).
  - Import added (or re-used) for the cache snapshot reader. Either `from the_one.connectors._pool import _get_account_cache_snapshot` (if not already imported here for another purpose) or a top-level helper exposed by `_pool`. The Developer agent picks the import shape based on existing imports in `_inbound.py`.
  - Post-step block (after the `bind_peer_name` call): a new block that (a) awaits `snapshot = await _get_account_cache_snapshot(working_envelope.account_id)`, (b) resolves `channel_name = resolve_channel_name(snapshot.cache if snapshot is not None else None, working_envelope.channel_id)`, (c) calls `bind_channel_context(agent.messages, pre_step_len, working_envelope.channel_id, channel_name)`. The block lives inside the existing per-session lock and try block (same scaffolding `bind_peer_name` uses).
  - A short explanatory comment block above the new call (mirroring the `bind_peer_name` comment shape) cites M11 F7 L3, names the F3 cache as the resolution source, and explains the always-bind-id / conditional-bind-name semantic.
- `the_one/db/codec.py:messages_to_ui_events`:
  - The USER-event branch's spread is extended with two new sentinel-emit dicts mirroring the `peer` pattern:
    ```python
    channel_id_spread = {"channel_id": msg.channel_id} if msg.channel_id is not None else {}
    channel_name_spread = {"channel_name": msg.channel_name} if msg.channel_name is not None else {}
    # ... in the USER branch:
    events.append({
        "type": "user",
        "content": msg.content,
        "source": "restored",
        **vis,
        **peer,
        **channel_id_spread,
        **channel_name_spread,
    })
    ```
  - Comment block above the spreads (M11 F7 L3 attribution).
- `the_one/agents.md`:
  - The `post-step-dispatcher-message-metadata-binding` convention's third Citation (currently the `(M11 F7 L3; pending L3 within this flight)` parenthetical entry) is replaced so the parenthetical reads `(M11 F7 L3)` only — the `; pending L3 within this flight` text is removed. The full citation reads:
    `- `the_one/connectors/post_step_metadata.py:bind_channel_context` (M11 F7 L3) — channel_name + channel_id binding on the appended USER message; addresses `messages[pre_step_len]` directly. Channel_id always bound from envelope; channel_name resolved from the F3 L4 discoverable-entities cache and bound when found (None otherwise).`
- New tests in `tests/test_connectors_post_step_metadata.py`:
  - `test_bind_channel_context_binds_channel_id_and_channel_name` — both args non-None → both written to `messages[pre_step_len]`.
  - `test_bind_channel_context_binds_channel_id_with_none_channel_name` — channel_name is None → channel_id written, channel_name stays None.
  - `test_bind_channel_context_raises_on_non_user_message` — message at `pre_step_len` is Role.ASSISTANT → AssertionError (mirrors `bind_peer_name`'s assertion test).
  - `test_bind_channel_context_does_not_touch_non_user_messages` — messages above `pre_step_len` (other roles) are unchanged.
  - `test_resolve_channel_name_returns_label_on_match` — cache with one channel `(id="C123", label="general")`, lookup `channel_id="C123"` → returns "general".
  - `test_resolve_channel_name_returns_none_on_miss` — cache has channels but none with matching id → returns None.
  - `test_resolve_channel_name_returns_none_on_none_cache` — cache is None → returns None.
- New tests in `tests/test_connectors_inbound.py`:
  - `test_dispatch_inbound_persists_inbound_with_channel_id_from_envelope` — mirror of the peer_name precedent; verifies the persisted USER message's `channel_id` equals `envelope.channel_id`. Uses stub plugin (cache None) so channel_name remains None.
  - `test_dispatch_inbound_persists_inbound_with_channel_name_from_cache` — monkeypatches `_get_account_cache_snapshot` (the call site in `_inbound.py`) to return a synthetic `_DiscoverableCacheSnapshot` whose `cache.channels` contains a matching `(id, label)` entry. Verifies the persisted USER message's `channel_name` equals the cache label. Monkeypatch chosen over extending `StubPlugin` because the binding is the L3 contract surface — the test boundary is "given a cache returns X, the message picks up Y," not "given a plugin implements hook H, the refresh sweep populates cache C."
  - `test_dispatch_inbound_persists_inbound_with_none_channel_name_when_cache_miss` — monkeypatches snapshot to return a cache with NO matching channel id; verifies channel_name stays None while channel_id is still set.
- New tests in `tests/test_connectors_inbound_broadcast.py`:
  - `test_dispatch_inbound_broadcasts_carry_channel_id` — mirror of the peer_name broadcast precedent; verifies the live `user` event payload carries `channel_id` and non-USER events do NOT carry the key.
  - `test_dispatch_inbound_broadcasts_carry_channel_name` — same shape for `channel_name` (with a populated cache fixture or monkeypatch).
- New tests in `tests/test_db_codec.py` (extending the `messages_to_ui_events` tests if a class for them exists; otherwise add a class):
  - `test_messages_to_ui_events_projects_channel_id_on_user_event` — Message with `channel_id="C123"` → resulting event has `channel_id: "C123"`.
  - `test_messages_to_ui_events_projects_channel_name_on_user_event` — Message with `channel_name="general"` → event has `channel_name: "general"`.
  - `test_messages_to_ui_events_omits_channel_keys_when_none` — Message with both fields None → event has no `channel_id` / `channel_name` keys.
  - `test_messages_to_ui_events_does_not_project_channel_on_assistant_or_tool_events` — assistant/tool messages with channel fields populated (artificial but defensive) → events have NO `channel_id`/`channel_name` keys, gating the projection to USER events only.

## Acceptance Criteria

- [ ] `the_one/connectors/post_step_metadata.py` exports `bind_channel_context` and the internal helper `resolve_channel_name`. The module docstring's `pending F7 L3` forward-reference is replaced with the confirmed implementation summary.
- [ ] `bind_channel_context(messages, pre_step_len, channel_id, channel_name)` asserts `messages[pre_step_len].role == Role.USER`, writes `channel_id` unconditionally, writes `channel_name` passing through `None` as-is. Docstring documents the Role-touch / Role-skip semantic as the composition complement of `tag_post_step_visibility` (same shape as `bind_peer_name`).
- [ ] `the_one/connectors/_inbound.py` post-step block, after `bind_peer_name`, includes a new block that fetches the discoverable-entities cache snapshot async (`_get_account_cache_snapshot(working_envelope.account_id)`), resolves `channel_name` via `resolve_channel_name`, and calls `bind_channel_context(agent.messages, pre_step_len, working_envelope.channel_id, channel_name)`. The block lives inside the existing session lock + try block.
- [ ] `the_one/db/codec.py:messages_to_ui_events` projects `channel_id` and `channel_name` onto the USER event branch using the conditional-include pattern (same as `peer_name`). Non-USER branches do NOT receive the keys.
- [ ] `the_one/agents.md`'s `post-step-dispatcher-message-metadata-binding` convention's third citation parenthetical is updated from `(M11 F7 L3; pending L3 within this flight)` to `(M11 F7 L3)` and the citation body references `post_step_metadata.py:bind_channel_context` (NOT `_inbound.py`). `grep -n "pending L3" the_one/agents.md` returns nothing.
- [ ] `tests/test_connectors_post_step_metadata.py` has the seven new tests listed in Outputs (four `bind_channel_context` tests + three `resolve_channel_name` tests).
- [ ] `tests/test_connectors_inbound.py` has the three new dispatch-binding tests listed in Outputs.
- [ ] `tests/test_connectors_inbound_broadcast.py` has the two new broadcast tests listed in Outputs.
- [ ] `tests/test_db_codec.py` has the four new `messages_to_ui_events` projection tests listed in Outputs.
- [ ] `docker exec the-one pytest tests/test_connectors_post_step_metadata.py tests/test_connectors_inbound.py tests/test_connectors_inbound_broadcast.py tests/test_db_codec.py -x --timeout 30` passes.
- [ ] Full suite at leg-end: `docker exec the-one pytest -x --timeout 60` — no L3-introduced regressions.
- [ ] Flight log L3 entry under `## Leg Progress` documents the leg; leg checked off in `flight.md` under `### Legs`. Leg artifact status set to `landed`.

## Verification Steps

- `python -c "from the_one.connectors.post_step_metadata import bind_channel_context, resolve_channel_name; print('OK')"` prints `OK`.
- `grep -n "bind_channel_context(agent.messages, pre_step_len" the_one/connectors/_inbound.py` returns one match.
- `grep -n "channel_id\|channel_name" the_one/db/codec.py | grep -i "messages_to_ui_events\|conditional\|spread\|peer" | head` shows the new projection lines.
- `grep -n "pending L3" the_one/agents.md` returns NOTHING (placeholder replaced).
- `grep -n "bind_channel_context" the_one/agents.md` returns at least one citation match.
- Targeted: `docker exec the-one pytest tests/test_connectors_post_step_metadata.py tests/test_connectors_inbound.py tests/test_connectors_inbound_broadcast.py tests/test_db_codec.py -x --timeout 30` — all green.
- Full suite: `docker exec the-one pytest -x --timeout 60` — all green.

## Implementation Guidance

1. **Add `resolve_channel_name` and `bind_channel_context` to `the_one/connectors/post_step_metadata.py`:**
   ```python
   def resolve_channel_name(
       cache: DiscoverableEntities | None,
       channel_id: str,
   ) -> str | None:
       """Resolve a friendly channel label from the F3 L4 discoverable-entities cache.

       Returns the matching channel entity's ``label`` if one exists with
       ``id == channel_id``; returns ``None`` when the cache is ``None``
       (cold pool, plugin doesn't implement ``enumerate_discoverable_entities``,
       or the first refresh hasn't landed) or when no matching entry is found
       (stale cache, channel deleted, bot kicked).

       Pure synchronous walk over ``cache.channels``. The caller (the
       dispatcher's post-step block) fetches the cache snapshot async
       upstream so this helper stays sync-and-testable.
       """
       if cache is None:
           return None
       for entity in cache.channels:
           if entity.id == channel_id:
               return entity.label
       return None

   def bind_channel_context(
       messages: list[Message],
       pre_step_len: int,
       channel_id: str,
       channel_name: str | None,
   ) -> None:
       """Bind channel context onto the USER message ``agent.step`` appended.

       **Touches**: ``Role.USER`` only — the single message at
       ``messages[pre_step_len]``. Composition complement of
       ``tag_post_step_visibility`` (which skips USER and touches all
       other roles); same Role-scope as ``bind_peer_name``.

       ``channel_id`` is bound unconditionally (the envelope always
       carries one — see ``InboundEnvelope.channel_id`` invariant).
       ``channel_name`` may be ``None`` when the F3 L4 cache hasn't
       resolved a label; the field stays ``None`` and L4's provider
       projection handles partial-absence gracefully.

       M11 F7 L3 (added to the lifted module's n=3 set; see agents.md
       § post-step-dispatcher-message-metadata-binding).
       """
       assert messages[pre_step_len].role == Role.USER, (
           "agent.step must append a Role.USER message at pre_step_len"
       )
       messages[pre_step_len].channel_id = channel_id
       messages[pre_step_len].channel_name = channel_name
   ```

2. **Update the module docstring** to replace the `bind_channel_context — pending F7 L3` line with the confirmed citation:
   `bind_channel_context` — channel context (id + optional name) on the appended USER message; channel_id from envelope, channel_name resolved from F3 L4 cache.

3. **Update `the_one/connectors/_inbound.py`:**
   - Import: extend the `from the_one.connectors.post_step_metadata import …` line to include `bind_channel_context` and `resolve_channel_name` (and any companion helpers).
   - Import the cache reader: `from the_one.connectors._pool import _get_account_cache_snapshot` (if not already present — confirm at implementation time).
   - In the post-step block, after the `bind_peer_name(...)` call, add:
     ```python
     # M11 F07 L03: post-step channel-context binding.
     # The envelope always carries channel_id; channel_name is resolved
     # from the F3 L4 discoverable-entities cache (label lookup matching
     # envelope.channel_id against cache.channels[i].id). Cold pool /
     # non-Discord plugin / stale cache → channel_name stays None; the
     # L4 provider projection handles partial-absence gracefully.
     # Composition: this is the third mutator in the post_step_metadata
     # set (visibility, peer_name, channel_context — n=3 per agents.md).
     _channel_cache_snapshot = await _get_account_cache_snapshot(
         working_envelope.account_id
     )
     _resolved_channel_name = resolve_channel_name(
         _channel_cache_snapshot.cache if _channel_cache_snapshot is not None else None,
         working_envelope.channel_id,
     )
     bind_channel_context(
         agent.messages,
         pre_step_len,
         working_envelope.channel_id,
         _resolved_channel_name,
     )
     ```

4. **Update `the_one/db/codec.py:messages_to_ui_events`:**
   - In the USER-event branch (where `**peer` spread happens), add two new conditional-include spreads for `channel_id` and `channel_name`. Comment block above the spreads citing M11 F7 L3.
   - Verify non-USER branches do NOT include the new keys — the test `test_messages_to_ui_events_does_not_project_channel_on_assistant_or_tool_events` pins this.

5. **Update `the_one/agents.md`:**
   - In the `post-step-dispatcher-message-metadata-binding` Citations list, replace the third entry's `(M11 F7 L3; pending L3 within this flight)` parenthetical with `(M11 F7 L3)` (drop the pending suffix); replace the body of the citation with the concrete `bind_channel_context` description pointing at `the_one/connectors/post_step_metadata.py`. After this edit, `grep -n "pending L3" the_one/agents.md` returns nothing.

6. **Add tests** per the Outputs section. Mirror the precedent test bodies (peer_name binding tests at `tests/test_connectors_inbound.py:593–619`; peer_name broadcast test at `tests/test_connectors_inbound_broadcast.py:301–356`; peer_name codec projection tests in `tests/test_db_codec.py` if they exist as a class). The Developer agent finds the exact mirror sites.
   - For `test_dispatch_inbound_persists_inbound_with_channel_name_from_cache` and `test_dispatch_inbound_persists_inbound_with_none_channel_name_when_cache_miss`: monkeypatch `_get_account_cache_snapshot` at the `_inbound.py` call site (`monkeypatch.setattr("the_one.connectors._inbound._get_account_cache_snapshot", lambda account_id: <coro returning synthetic snapshot>)` or equivalent async-aware shape). This keeps the test scoped to L3's binding behavior without wiring a full refresh sweep. **Important coupling**: the monkeypatch path string MUST match the import shape chosen in step 3. If the Developer agent imports as `from the_one.connectors._pool import _get_account_cache_snapshot` (the leg's preferred shape, surfacing the symbol into `_inbound`'s namespace), monkeypatch `the_one.connectors._inbound._get_account_cache_snapshot`. If instead the Developer agent calls it via module qualification (`_pool._get_account_cache_snapshot(...)`), monkeypatch `the_one.connectors._pool._get_account_cache_snapshot`. Pick the import shape FIRST, then write the monkeypatch path. The existing F3 L4 tests at `tests/test_connectors_pool.py:591-616` use a local `_DiscoverablePlugin` subclass for the refresh-path tests; L3 doesn't need that depth.

7. **Run targeted tests** then full suite per Verification Steps. Update flight log under `## Leg Progress` with `### L3 — dispatcher-channel-context-binding`. Check off in flight.md. Set L3 status to `landed`. Do NOT commit (F7 flight-level commit ordering).

## Edge Cases

- **Cache snapshot is None (cold pool)** — `_get_account_cache_snapshot` returns None when the pool hasn't been warmed yet. `resolve_channel_name(None, channel_id)` returns None; `bind_channel_context` writes `channel_id` only. The Chat UI sees `channel_id` without `channel_name`; L4 provider projection handles partial absence.
- **Cache present but cold (snapshot exists, cache is None)** — the snapshot's `cache` field is None when the first refresh hasn't landed. Same shape as cold pool: `resolve_channel_name` defends with `if cache is None`.
- **Cache miss (cache present, channel_id not in cache.channels)** — happens when a channel was created on the platform between cache refreshes. `resolve_channel_name` falls through the loop and returns None. Same downstream handling.
- **Stub plugin (no `enumerate_discoverable_entities`)** — pool entry's `discoverable_entities_cache` stays None forever. The dispatcher binds `channel_id` only. The stub-based tests verify this path.
- **`channel_id == ""`** — defensive: the assertion is on Role.USER, not on channel_id non-emptiness. Empty `channel_id` would be a translator-layer bug; L3 doesn't defend against it (the precedent from `bind_peer_name` similarly trusts the envelope's contract).
- **Cache-snapshot async call awaiting inside the session lock** — safe: the pool lock is separate from `session_locks[session_row.id]`; awaiting `_get_account_cache_snapshot` is a brief lock acquisition + pointer dereference. The dispatcher already does much heavier async work inside the session lock (`agent.step()`).
- **Race: cache refreshed between snapshot read and dispatch persistence** — the snapshot is by-value, so the dispatcher sees a stale snapshot if the refresh races. Acceptable — the channel_name binding is best-effort metadata; the next inbound on the same channel picks up the fresh label.
- **WS broadcast for non-USER events erroneously carrying channel keys** — the projection MUST be gated to `msg.role == Role.USER`. The test `test_messages_to_ui_events_does_not_project_channel_on_assistant_or_tool_events` pins this.
- **L4 provider projection when channel_name is None** — out of L3 scope. L4's spec must specify the partial-absence behavior (peer + channel_id but no channel_name → `[from alice in #C123456]: ...` or `[from alice]: ...`? — L4's design decision). L3 just ensures channel_name is None when unresolvable; L4 reads the field.
- **Operator-typed turns do NOT carry channel context** — `app.py:_process_and_broadcast` (lines ~880-899) emits USER events for operator-typed input with no inbound channel; L3 does NOT modify this site, mirroring the F6 L3 peer_name precedent (operator-typed turns originate at the operator console, not a Discord channel). The USER event from operator-typed input continues to omit channel_id and channel_name keys.
- **Chat UI client-side rendering (chat.js)** — out of L3 scope. L3 only ships the data over the WS payload; the existing chat.js reads `data.peer_name` but does not (yet) read `data.channel_id` or `data.channel_name`. A future leg (or L11 Studio UI work) renders channel attribution. Until then, the data flows but isn't rendered — operators can verify via WS inspector or by reading the persisted Message row.
- **Linear scan over `cache.channels` in `resolve_channel_name`** — acceptable for v1 (typical Discord guild has <500 channels; the lookup runs once per inbound; no profile data flags this). If a future operator hits a very large guild and profiling shows the linear scan matters, swap to an `{id: label}` dict cached alongside `DiscoverableEntities`. Tracked as scaling-debt; not addressed in L3.
- **Deadlock safety of async cache read inside session lock** — the pool lock and session lock are independent; `_get_account_cache_snapshot` acquires the pool lock briefly, dereferences the entry's cache pointer, releases. It holds no callable that could in turn try to acquire any session lock. No ordering violation possible. The session lock around `agent.step()` already awaits much heavier work; this brief pool-lock acquisition is comparatively trivial.

## Files Affected

- `the_one/connectors/post_step_metadata.py` — ADD `resolve_channel_name` + `bind_channel_context`; update module docstring.
- `the_one/connectors/_inbound.py` — UPDATE imports + ADD post-step binding block after `bind_peer_name`.
- `the_one/db/codec.py` — UPDATE `messages_to_ui_events` USER branch with channel_id + channel_name projection. **This is the single projection site** — `app.py` is NOT touched (the connector-inbound live broadcast routes through this codec function, not through `app.py:_process_and_broadcast`).
- `the_one/agents.md` — UPDATE convention's third citation parenthetical from `(M11 F7 L3; pending L3 within this flight)` to `(M11 F7 L3)`.
- `tests/test_connectors_post_step_metadata.py` — ADD 7 new tests (4 binding + 3 resolver).
- `tests/test_connectors_inbound.py` — ADD 3 new dispatch-binding tests.
- `tests/test_connectors_inbound_broadcast.py` — ADD 2 new broadcast tests.
- `tests/test_db_codec.py` — ADD 4 new `messages_to_ui_events` projection tests.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight-log.md` — APPEND `## Leg Progress` entry.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight.md` — CHECK OFF leg.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (targeted + full suite)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: NOT applicable
- [ ] Commit all changes together (code + artifacts) — DEFERRED in F7 per `/agentic-workflow` flight-level commit ordering; do NOT commit per leg.

## Citation Audit

Citations verified against current code at design time via the F7 L3 reconnaissance pass:

- `the_one/connectors/_inbound.py:~630–670` — post-step block with `tag_post_step_visibility` + `bind_peer_name` calls (post-L1 state).
- `the_one/connectors/post_step_metadata.py:1–42+` — module docstring + two existing functions (post-L1 state).
- `the_one/connectors/_pool.py:_get_account_cache_snapshot` — async cache read API (verified).
- `the_one/connectors/base.py:InboundEnvelope:49–93` — envelope with `channel_id: str` (always set), no `channel_name` field (verified).
- `the_one/connectors/base.py:DiscoverableEntities` — `channels: list[DiscoverableEntity]` with `(id, label)` per entity (verified).
- `the_one/connectors/_discord_translate.py:119–134` — Discord envelope construction (verified).
- `the_one/db/codec.py:messages_to_ui_events:137–235` — USER-event branch with `peer_name` projection (verified).
- `tests/test_connectors_inbound.py:593–619` — peer_name binding test precedent (verified).
- `tests/test_connectors_inbound_broadcast.py:301–356` — peer_name broadcast test precedent (verified).

No forward-locates remain. The connector-inbound live broadcast path was traced in the cycle-2 review: `_inbound.py:701-707` → `messages_to_ui_events` (codec) → `broadcast_to_session` (`the_one/sessions/_broadcast.py:42`). The codec is the single projection site for both replay and live broadcast on this path; `app.py` is not touched.
