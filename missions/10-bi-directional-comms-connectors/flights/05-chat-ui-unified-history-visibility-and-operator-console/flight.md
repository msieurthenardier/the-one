# Flight: Chat UI — Unified History, Visibility Distinction, Operator Console

**Status**: in-flight
**Mission**: [Bi-directional Communication Connectors](../../mission.md)

## Contributing to Criteria

- [ ] *(advances toward COMPLETE)* "When the operator opens Chat for an agent that has connector-attached sessions, those sessions are listed alongside the Chat-UI-native sessions; opening one shows the full unified conversation history — both the platform-visible exchange (peer messages + agent's platform replies) AND any operator-console exchange (the operator's private messages to the agent + the agent's replies to the operator) — in a single timeline, with clear visual distinction so the operator can see at a glance which messages were visible to peers on the external platform versus which stayed local" — this flight extends the session-list surface and the message-rendering surface; F3+F4 already shipped the visibility data model + tagging, so F5 is the rendering layer.
- [ ] *(advances toward COMPLETE)* "A connector-attached session has two visibility layers feeding the same agent context: (i) the **platform channel** — peer-visible messages exchanged on the external platform; (ii) the **operator console** — the local Chat UI, where the operator can talk privately to the agent about the platform conversation. Messages the operator types in the Chat UI on a connector-attached session, and the agent's replies to those operator messages, DO NOT propagate to the external platform — peers see nothing of the operator console. The agent's responses to operator messages stay in the operator console by default" — this flight lands the operator-input path: WS-typed messages into a connector-attached session get tagged `visibility="operator"` at the storage-edge shim around `_spawn_message_processing`; the agent's responses to those operator messages inherit operator-visibility via the F4 dispatcher post-step pass. Tool-only outbound (F4) makes leakage impossible by construction.
- [ ] *(advances)* "The agent has context awareness across both visibility layers — when answering operator questions in the operator console, it can reference what was said on the platform channel; when responding to platform inbound, it benefits from any direction the operator gave in the operator console; the two are not separate context windows" — this is structurally already true (F3's single-history model + F4's visibility-tag-as-metadata stance), but F5 is the first flight where operator-typed messages actually land in connector-attached sessions, so the criterion is exercised end-to-end for the first time here.
- [ ] *(advances)* "The Admin connector-account surface, the Studio connector-attach surface, the doctor probe, **and the in-Chat connector-session view** all meet the M04/M06 design-language quality bar without alignment-flight rework" — F5 ships the in-Chat connector-session view; the bar applies.
- [ ] *(advances)* "Each layer of the integration has automated coverage proving its contract" — F5 adds session-list-with-source coverage, the WS-into-dispatcher routing test, the operator-visibility-tagging round-trip test, and the unified-history render test.

---

## Pre-Flight

### Objective

Land the **operator-facing surface** of the connector subsystem: the Chat UI side. After F5: when the operator opens Chat, connector-bound sessions appear in the session list alongside web-native sessions with a visible source distinction; opening one renders the unified history (peer messages + agent's platform replies + operator's private messages + agent's responses to the operator) with a clear visual distinction per message-level `visibility` tag; the operator can type into a connector-attached session and have the message reach the agent (and the agent's response back to the operator) WITHOUT propagating to the external platform — only the platform-send tool (F4) can reach peers. F5 also reconciles the F3-flagged per-session-lock unification (mission Known Issue): the WS handler and the F3 dispatcher converge on a single serialization primitive so concurrent inbound + operator-typed messages on the same connector-attached session can no longer race on `agent.messages`. F4 already ships the visibility data model + tagging; F5 makes it observable to a human at the Chat UI render boundary and adds the operator-input write path. The agent loop in `agent/core.py` is NOT modified — operator visibility-tagging happens at the storage edge around the existing `_spawn_message_processing` and the dispatcher's post-step pass.

### Open Questions

- [x] **Per-session-lock unification path: F3 debrief option (a) (route WS through dispatcher) vs. option (b) (extract `Session` out of `app.py` so the lock object is shared)** — resolved in Design Decisions: **hybrid**. F5 introduces a shared `session_locks` registry module (`the_one/connectors/_session_locks.py` or inline in `connectors/_inbound.py`) that BOTH `_spawn_message_processing` AND `dispatch_inbound` consult for the per-session `asyncio.Lock`. This is option (b)-lite: NOT extracting `Session` wholesale, just extracting the LOCK identity. Both code paths converge on `await session_locks.acquire(session_id)` semantics; the WS-side `Session.processing_lock` field is REMOVED in favor of the shared registry. Mission text's "storage-edge shim around `_spawn_message_processing`" wording is honored: the shim tags `visibility="operator"` before persistence; the shim does NOT route to `dispatch_inbound`. Lock unification is orthogonal to routing — both paths exist; both share the lock.
- [x] **Visibility-distinction visual treatment in the Chat UI** — resolved in Design Decisions: subtle inline indicator at the message bubble level, NOT a separate column/section. Operator-only messages get a left-margin marker (M04/M06 token: `border-left` + `padding-left` shift) plus a small `[operator-only]` label rendered in `text-muted` style. Peer-visible messages render unchanged from today's chat. The unified timeline keeps chronological order — no split into "two timelines" or "two panels" because the mission text explicitly says "single timeline."
- [x] **Session-list source surfacing: badge vs. icon vs. text suffix** — resolved in Design Decisions: small text-style badge (mirrors the existing MCP-type badge precedent at `static/js/areas/the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js`). For non-connector sessions: no badge (current rendering preserved). For connector sessions: badge text is the connector type (`stub`/`discord`/`slack` at F8/F9). Sessions in the list are grouped by date bucket (existing `history-buckets.js` logic) regardless of source — date is the primary axis; source is a per-row property.
- [x] **Multiple historical `chat_sessions` rows per external key UX** (F3 debrief #136) — resolved in Design Decisions: F5 ships them as DISTINCT rows in the session list with the bucket-grouping at `history-buckets.js`. No grouping/collapse at F5. Rationale: each superseded session is its own conversation per F3's design (each has its own messages, its own continuation window expired, etc.); collapsing them into a single row would hide the history. F5 ships visual-only "this is a superseded session for external-key X" hint if cheap; full grouping is a follow-on flight if the operator surfaces frustration.
- [x] **`[platform-send-ok]` sentinel structured side-channel** (F4 debrief #134) — resolved in Design Decisions: **DEFER**. F5 does NOT need to consume the prefix at render time. The F4 dispatcher's visibility-tagger already converted "successful platform-send tool_result" into `visibility=None` (peer-visible); F5 reads `visibility` directly. The prefix-string is an INTERNAL coordination contract between the platform-send tool and the dispatcher's post-step pass; F5's render layer doesn't see it. If a future flight (F8/F9/F10) surfaces a second consumer of the sentinel, that's when the structured-side-channel conversation happens.
- [x] **Broadcast surface generalization: zero-subscribers behavior** — resolved in Design Decisions: the existing `_send_to_session` / `_broadcast_to_session` helpers in `interfaces/web/app.py` already handle the zero-subscriber case gracefully (the `subscribers: set[WebSocket]` is empty; the helpers iterate empty). F4's dispatcher does NOT call broadcast today — it just persists. F5's change: when a connector-driven inbound completes and the same `chat_sessions.id` has live WS subscribers in `_sessions[sid].subscribers`, the dispatcher emits the per-message UI events via the broadcast surface. The broadcast helper short-circuits cleanly on empty subscribers. No new helper needed; the dispatcher reaches into `_sessions` via a function-local import (per the load-cycle convention) and calls the same broadcast path the WS-typed flow uses.
- [x] **Storage-edge shim for operator-visibility tagging** — resolved in Design Decisions: the shim is a thin wrapper at `interfaces/web/app.py` around `_spawn_message_processing` that pre-computes the operator-visibility tag BEFORE the agent.step turn, and applies it to BOTH the operator-typed user message (set at `Message.user(...)` construction) AND the post-step pass over `agent.messages` for new assistant/tool messages. The condition: the session's `chat_session_row.platform IS NOT NULL` (i.e. connector-attached). For non-connector sessions, no tagging — behavior is byte-identical to today. The shim borrows the F4-leg-4 post-step walk logic from `_inbound.dispatch_inbound`; ideally the walk is FACTORED into a shared helper that both the WS path and the dispatcher path call.
- [x] **HAT / alignment leg** — resolved in Design Decisions: **INCLUDE as REQUIRED final leg** (not optional). F5 is the first operator-visible end-to-end exercise of the connector subsystem (F1-F4 were pre-UI scaffolding); an interactive HAT session catches design-language drift, two-layer rendering ambiguity, and operator-mental-model gaps that automated tests can't surface. User-directed at planning time: required, not optional.
- [x] **Design-language tokens** — resolved in Design Decisions: M04/M06 tokens reused without inventing new CSS classes. Operator-only message marker uses existing `text-muted` + a new namespaced `msg-operator-only` class with a small `border-left` rule in `chat.css`. Session-list source badge uses the existing `entity-tile-badge` class precedent from `the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js`, applied at row scope.
- [ ] **Exact bucket-grouping behavior for superseded-external-key sessions** — finalized at leg 1 planning. Tentative: superseded sessions land in their own date bucket per the existing `bucketForSession(s, nowDay)` logic at `the_one/interfaces/web/static/js/areas/chat/history-buckets.js:19-33`; no special "history of this external key" rollup. Architect should verify.
- [ ] **Lock-registry module placement: under `connectors/` (load-cycle-safe) vs. under `interfaces/web/` vs. a new `the_one/sessions/` package** — finalized at leg 2 planning. Tentative: a new `the_one/sessions/_locks.py` module owned by neither subsystem, so both `app.py` and `connectors/_inbound.py` import from it without cycle. Tradeoff vs. inlining in `connectors/_inbound.py`: the inline version requires `app.py` to import from `connectors`, which is currently a one-way relationship (`connectors._inbound` already imports from `app.py:_state` via the factory injection). Keeping the import-direction one-way means putting the lock registry in a neutral location.

### Design Decisions

**Per-session-lock unification via a shared registry module — hybrid of F3 debrief options (a)+(b)**

- **Choice**: Introduce a new module `the_one/sessions/_locks.py` (or equivalent neutral location) exporting `session_locks: defaultdict[str, asyncio.Lock]` (mirroring F3's `connectors/_inbound._session_locks`). BOTH `_spawn_message_processing` AND `dispatch_inbound` acquire `session_locks[session.id]` for the duration of their `agent.step` + persist. The `Session.processing_lock` field at `app.py:201` is REMOVED. The dispatcher's `_session_locks` import is REPOINTED to the new module; `_clear_for_test` extends to clear the new registry.
- **Rationale**: F3 debrief recommended option (a) (route WS through dispatcher) "is now confidently correct"; mission text says "storage-edge shim around `_spawn_message_processing`" (keep WS path). The hybrid satisfies BOTH: WS keeps its existing structure (storage-edge shim tags visibility; agent build/step/persist flow unchanged) AND the lock is shared with the dispatcher (no race). The "option (b)" framing in the F3 debrief was "refactor `Session` out of `app.py`"; the hybrid extracts ONLY the lock, not `Session` wholesale — a much smaller refactor than option (b) but yielding the same lock-unification outcome.
- **Trade-off**: A WS-typed message and a connector inbound for the same session_id now BOTH wait on the same `asyncio.Lock`. Correct behavior — both update `agent.messages`. Lock contention is fine: per-session, sub-second `agent.step` turns. Memory growth: the `defaultdict` accumulates an entry per session_id; same growth profile as F3's existing `_session_locks` (flagged for F10 hardening — `WeakValueDictionary` or TTL cleanup). Removing `Session.processing_lock` requires updating THREE call sites (architect-surfaced — original spec missed one): (1) `_spawn_message_processing:250-251` (the lazy-init dance disappears); (2) `_restore_session:387-392` (the "is the lock held?" check changes from `cached.processing_lock.locked()` to `_is_session_processing(session_id)`); (3) `_build_session_joined_ok:499` (the `is_processing` payload field the client uses to size the thinking indicator on rejoin — same `_is_session_processing` helper). Factor a small `_is_session_processing(sid: str) -> bool` helper so the read paths don't trigger the defaultdict's lazy-create side effect.

- **Architect-surfaced trade-off vs. F3 debrief option (a)**: F3 debrief recommended option (a) (route WS through `dispatch_inbound`) as "now confidently correct." F5 chooses the hybrid (shared lock registry + WS path stays put) for a specific reason: routing WS through `dispatch_inbound` would require synthesizing an `InboundEnvelope` for every WS-typed message, but `InboundEnvelope.account_id` is meaningless for a NON-connector session — the operator-typing-into-a-WEB-NATIVE-session case (which F5 must preserve byte-identically) has no account_id to invent. The hybrid avoids inventing a synthetic-WS-envelope shape. Documented here so the F5 debrief records why the recommendation was knowingly overridden.

**Visibility-distinction visual treatment: inline marker on operator-only message bubbles**

- **Choice**: Add a new namespaced CSS class `msg-operator-only` applied to operator-tagged message bubbles in `the_one/interfaces/web/static/css/chat.css`. The class adds: `border-left: 3px solid <var(--accent-muted)>; padding-left: var(--space-2);` plus a small `[operator-only]` label rendered in `font-mono` + `text-muted`. The class is applied at `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:renderMessage` via a new `opts.visibility` parameter: when `event.visibility === "operator"`, the class is appended. For peer-visible (`visibility === undefined` per F3's "absent === platform-visible" codec contract), rendering is unchanged.
- **Rationale**: M04/M06 already establish `border-left` + `padding-left` as the indentation idiom for "nested" or "annotation" content (e.g. tool-result rendering). Operator-only messages are a similar shape semantically — annotations on the platform conversation. The `[operator-only]` label gives screen-reader users a clear distinction; the visual treatment is subtle enough that the message body remains primary.
- **Trade-off**: An operator who is the only-ever user of a connector-attached session sees the marker on every assistant message (the agent's responses to the operator are operator-only by default per F4 dispatcher). Acceptable: in this case the operator IS the only audience, so the visual indicator is purely informational, not a separator. If a future operator-feedback flight surfaces "the markers are noisy when peer activity is rare," consider conditional rendering (e.g. only render the marker when peer-visible messages also exist in the session).

**Session-list source surfacing: text-style badge per row**

- **Choice**: Extend `buildSessionItem` at `the_one/interfaces/web/static/js/areas/chat/history-buckets.js:35-90` to render an additional `<span>` element when the session is connector-bound (`s.platform != null`). Class: `session-item-source` plus the type-specific badge class (mirror of MCP-server-grid's `entity-tile-badge--<type>` pattern at `the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js`). For F5's stub, the badge reads `stub`; F8 lands `discord`; F9 lands the second connector. For non-connector sessions, no badge — current rendering preserved.
- **Rationale**: The MCP-server-grid badge pattern is the established precedent for type surfacing in the design-language. Reusing the class structure means the operator's eye trains on the same visual idiom across Studio MCP servers and Chat connector sessions.
- **Trade-off**: An operator with many connector-bound sessions sees a row of `stub` badges in the list while testing. Cosmetic; resolves naturally once `discord`/`slack` types replace `stub` at F8/F9.

**`list_sessions` WS action returns the connector-keying fields**

- **Choice**: Extend the `list_sessions` action handler at `interfaces/web/app.py:1246-1268` to include `platform`, `connector_account_id`, `channel_id`, `thread_id`, `peer_id`, and `last_inbound_at` in each session dict. The `ChatSession` model already carries them; the projection is a one-line addition per field. The Chat UI consumes `platform` for the source-badge decision and `last_inbound_at` for an optional "last activity" surface (F5 doesn't render it; F6 may).
- **Rationale**: Additive only. Pre-F5 clients that ignore the new fields continue to work. The data is already in `ChatSession` from F3 L1; the projection just exposes it at the WS surface.
- **Trade-off**: Slightly larger payload per session. The number of sessions in a single list call is bounded by the operator's session count (single-user local tool — dozens at most); per-row overhead is ~80 bytes. Negligible.

**Storage-edge shim for operator-visibility tagging — factor the post-step walk into a shared helper**

- **Choice**: Extract the F4-leg-4 post-step walk logic from `connectors/_inbound.dispatch_inbound:228-240` into a free function `tag_visibility(messages: list[Message], pre_step_len: int, *, operator_default: bool) -> None` in a new module (likely `connectors/_visibility.py` or co-located in `connectors/__init__.py`). The function mutates `messages` in-place. Both `dispatch_inbound` AND the new WS-path shim call it. The `operator_default` parameter switches the default-tag behavior: `True` for the WS-typed-into-connector-attached-session path (tag every new non-user message `operator`); `False` for the dispatcher path (current F4 behavior — tag every new non-user message `operator` unless it's a successful platform-send tool_result, which gets `None`). The `successful platform-send tool_result → None` carve-out is also the right behavior for the WS path (if the operator types something and the agent decides to deliver to the platform via `send_to_platform_channel`, that tool_result IS peer-visible).
- **Rationale**: The tagging logic is the SAME for both paths — the only difference is the entry-point message's default visibility (peer-visible inbound vs. operator-typed message). Extracting to a shared helper means future evolution (e.g. tagging tool_call messages differently) lives in one place, and the dispatcher's existing test coverage extends to the WS path for free. The mission-text "storage-edge shim around `_spawn_message_processing`" is honored: the WS path keeps its existing `_spawn_message_processing` call; the shim happens at the persistence-encode boundary (immediately after `agent.step` completes, before `_save_session_to_db`).
- **Trade-off**: The new helper has a slightly awkward signature (`operator_default: bool`) that encodes the entry-point difference. Acceptable; the alternative (separate-but-near-duplicate tagging blocks in `_inbound.py` and `app.py`) is worse for long-term maintainability.

**Broadcast surface generalization — lift `_sessions` registry access AND the broadcast helper to the neutral module (architect-revised)**

- **Choice**: Co-locate with the lock registry under `the_one/sessions/` (neutral module). The new module owns: (a) the `session_locks: defaultdict[str, asyncio.Lock]` registry; (b) the `subscribers` registry (the `WebSocket` set per session_id; today implicit on `Session.subscribers`); (c) a thin `broadcast_to_session(session_id, events: list[dict]) -> None` helper that iterates subscribers and sends the JSON. `interfaces/web/app.py` becomes a CONSUMER of this module (populates subscribers via `the_one.sessions.add_subscriber(sid, ws)` / `remove_subscriber(sid, ws)`); the dispatcher becomes a CONSUMER too (`the_one.sessions.broadcast_to_session(sid, events)` when subscribers exist). The import direction stays one-way: `interfaces.web.app` → `the_one.sessions`; `connectors._inbound` → `the_one.sessions`. No `connectors → interfaces.web.app` import is needed.
- **Rationale**: Architect-flagged. The original spec had the dispatcher function-local-import from `interfaces.web.app` (`_sessions` dict + broadcast helpers). That inverts the established import-direction convention (`connectors → interfaces` is currently never done; all current function-local-imports from `connectors` go to `db`, `config`, `encryption`). Lifting to a neutral module preserves the established direction AND co-locates with the lock registry (same architectural move, same module). The dispatcher emits per-message UI events (per `messages_to_ui_events(new_msgs)` after the visibility-tagging pass) so operators observing the session in real time see each message as it lands, matching the WS-stream cadence; end-of-turn batch is also fine since the dispatcher already persists at end-of-turn — leg-6 author's call.
- **Trade-off**: One more architectural move out of `interfaces/web/app.py`. Acceptable — `app.py` is already 1400+ LoC; thinning it is desirable. The new `the_one/sessions/` package is the neutral home; `app.py` becomes the WS-frontend, not the registry holder. `Session` dataclass stays in `app.py` (it's WS-bound state: agent + history + the WebSocket itself); only the subscribers-registry and the lock-registry move out.

**No new persistence schema — F5 is a read-and-render flight on top of F3+F4's data model**

- **Choice**: F5 ships ZERO schema migrations. The `chat_sessions` connector-keying columns (F3 v16) and the `Message.visibility` field (F3 codec) and the `agents.connector_account_ids` (F4 v17) are all in place. F5 reads them.
- **Rationale**: The data is there. F5's job is to surface it.
- **Trade-off**: None — the absence of a schema change is the right shape for a UI-rendering flight.

**HAT / alignment leg REQUIRED as the closer**

- **Choice**: Last leg of F5 is a guided HAT session (REQUIRED, not optional — user-directed at planning time): operator joins a connector-attached session, types into it, observes the agent respond in operator-only mode, then triggers a platform-send (via the agent's tool call from a previous turn or by reseeding an inbound), observes the platform-visible message rendered without the operator-only marker, navigates back to the session list to see the connector-source badge.
- **Rationale**: F5 is the first end-to-end operator-visible exercise of the connector subsystem. F1-F4 had only synthetic test coverage; F5's HAT catches design-language drift and operator-mental-model gaps that automated tests miss. Making it required (not optional) ensures the flight cannot land without operator sign-off on the visible surfaces.
- **Trade-off**: HAT requires human time. Acceptable for a UI flight; the cost is bounded (one session, ≤30 min walkthrough).

### Prerequisites

- [ ] Flight 4 status is `completed` (confirmed: F4 debrief landed; mission flight 4 checkbox ticked; F4 PR #63 merged)
- [ ] Schema version on `main` is 17 (confirmed: F4 L5 landed v17 with `agents.connector_account_ids` persistence)
- [ ] `Message.visibility` field is on the canonical dataclass (`the_one/llm/base.py:56` per F3 L2) and round-trips through the codec (`db/codec.py:63-67, 99-100, 151-154`)
- [ ] `messages_to_ui_events` projects `visibility` into emitted events when non-None (`db/codec.py:151-154`)
- [ ] F4 dispatcher post-step visibility tagging is in place at `connectors/_inbound.py:228-240` (the source for the shared-helper extraction in leg 3)
- [ ] `connectors/__init__.py:OPERATOR_VISIBILITY` and `PLATFORM_SEND_OK_PREFIX` exported (F3 L2 + F4 L1 outputs)
- [ ] `interfaces/web/app.py:Session` dataclass with `processing_lock` field exists at line ~187; `_spawn_message_processing` at line ~235; `_session_locks` (the dispatcher's separate dict) at `_inbound.py:51` — both serve the same purpose; F5 reconciles them
- [ ] `interfaces/web/app.py:1246-1268 list_sessions WS action` returns minimal session-row projection; F5 extends with connector fields
- [ ] `the_one/interfaces/web/static/js/areas/chat/history-buckets.js:35-90 buildSessionItem` builds session-list rows; F5 extends with source badge
- [ ] `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:22 renderMessage` builds message bubbles; F5 adds visibility-aware class
- [ ] No conflicting in-flight work on `interfaces/web/app.py`, `connectors/_inbound.py`, `the_one/interfaces/web/static/js/areas/chat/*`, or `the_one/interfaces/web/static/css/chat.css` on `main`
- [ ] Container test entry points (`make test`, `make lint`, browser-test recipe) operating cleanly on `main`
- [ ] `connectors → interfaces/web/app` import direction is currently one-way (`app.py` imports from `connectors`; `connectors/_inbound` imports from `app.py:_state` via factory injection only) — F5's lock-registry extraction must preserve this; the new module lands at `the_one/sessions/_locks.py` (or equivalent neutral location) to avoid cycle

### Pre-Flight Checklist

- [x] All open questions resolved (10 closed in Design Decisions; 2 intentionally deferred to leg planning)
- [x] Design decisions documented above with rationale and trade-offs
- [x] Prerequisites verified
- [x] Validation approach defined (see In-Flight § Verification below)
- [x] Legs defined

---

## In-Flight

### Technical Approach

**Bottom-up**: the data projection first (WS surface + frontend session-list), then the lock unification (the F3 carry-forward), then the visibility-tagging shim + render layer, then broadcast generalization, then e2e tests + the HAT closer.

- **Leg 1 — `list-sessions-extend-with-connector-source`**:
  - Extend the `list_sessions` WS action at `interfaces/web/app.py:1246-1268` to include `platform`, `connector_account_id`, `channel_id`, `thread_id`, `peer_id`, `last_inbound_at` in each session-dict. The `ChatSession` model already carries them.
  - Extend `the_one/interfaces/web/static/js/areas/chat/history-buckets.js:buildSessionItem` to render a `session-item-source` badge when `s.platform` is non-null. Badge text = `s.platform` (string literal). Class structure mirrors `the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js`'s `entity-tile-badge` precedent.
  - Add corresponding CSS rules in `the_one/interfaces/web/static/css/chat.css` (or wherever the chat-area CSS lives) for `.session-item-source` using existing M04/M06 tokens.
  - Test: unit test on the WS handler's projection (returns the new fields); browser test on the session-list rendering (a stub-connector session shows the badge; a web-native session doesn't).

- **Leg 2 — `lock-unification-and-broadcast-lift-to-neutral-module`**:
  - New package `the_one/sessions/` with two modules:
    - `the_one/sessions/_locks.py` — exports `session_locks: defaultdict[str, asyncio.Lock]`, `_is_session_processing(sid: str) -> bool` (helper that does NOT trigger lazy-create), and `_clear_for_test() -> None`.
    - `the_one/sessions/_broadcast.py` — exports `add_subscriber(sid, ws)`, `remove_subscriber(sid, ws)`, `subscribers_for(sid) -> set[WebSocket]` (or empty set if none), `broadcast_to_session(sid, events: list[dict]) -> None`, `_clear_for_test()`.
  - Update `connectors/_inbound.py` to import `session_locks` from the new module and use it in place of the local `_session_locks` defaultdict; the local one is deleted.
  - Update `interfaces/web/app.py`:
    - Remove `Session.processing_lock` field.
    - Replace `_spawn_message_processing`'s `session.processing_lock` use (lines 250-252) with `session_locks[session.id]`.
    - Update `_restore_session`'s "is the lock held?" check at L387-392 to use `_is_session_processing(session_id)` from the new module.
    - Update `_build_session_joined_ok` at L499 to use `_is_session_processing(session.id)` for the `is_processing` payload field (architect-surfaced third call site).
    - Move `Session.subscribers` mutation calls to the neutral module: every `session.subscribers.add(ws)` / `.discard(ws)` becomes `the_one.sessions.add_subscriber(session.id, ws)` / `remove_subscriber(session.id, ws)`. The `Session.subscribers: set[WebSocket]` field can stay as a back-reference for the existing helpers if needed; the neutral module is the source-of-truth.
    - Update the existing broadcast helpers (`_send_to_session`, `_broadcast_to_session`) to read subscribers from the neutral module.
  - Update tests' autouse `_clear_pool_locks_registry` fixture (or whatever it's named after the F4 L5 extraction) to clear BOTH new registries.
  - Test: per-session-lock-shared test — spawn a WS-typed message and a connector inbound for the SAME session_id; assert they serialize (only one inside `agent.step` at a time via an event-coordinated fixture, mirror of F3 L4's pattern). Test: `_build_session_joined_ok` reports `is_processing=True` while a `_spawn_message_processing` is in flight (architect-surfaced regression-net for the rejoin path). Test: zero-subscriber broadcast is a clean no-op (no exception, no side effects).

- **Leg 3 — `extract-visibility-tagger-shared-helper`**:
  - Extract the post-step walk from `connectors/_inbound.dispatch_inbound:222-240` into a free function `tag_visibility(messages: list[Message], pre_step_len: int, *, operator_default: bool) -> None` in a new module (`the_one/connectors/_visibility.py` or co-located in an existing connectors module). The function mutates messages in-place per the current logic.
  - The dispatcher calls it with `operator_default=False` (current F4 behavior — default visibility=None for new non-user messages? wait, no — F4 default for non-user is `OPERATOR_VISIBILITY`). Re-read F4 L4: default IS `OPERATOR_VISIBILITY`. The `operator_default: bool` parameter is misleading — both paths use the same default; the difference is the entry-point USER message's visibility (peer's inbound = `None`; operator's typed message = `OPERATOR_VISIBILITY`). The helper extraction focuses on the post-step walk; the entry-point USER message tagging happens at the call site before invoking `agent.step`.
  - **Revised**: `tag_post_step_visibility(messages: list[Message], pre_step_len: int) -> None` — no operator_default kwarg; both paths use the same post-step logic. The entry-point USER message gets tagged at construction time by the caller (`Message.user(text, visibility=None)` for inbound; `Message.user(text, visibility=OPERATOR_VISIBILITY)` for WS-typed-into-connector-attached).
  - Update `connectors/_inbound.dispatch_inbound` to call the helper instead of the inline walk.
  - No behavior change yet — purely a refactor + test that the helper is correctly extracted.

- **Leg 4 — `ws-storage-edge-shim-for-operator-visibility`**:
  - In `interfaces/web/app.py`, add the storage-edge shim around `_spawn_message_processing`. The shim activates when the session's `chat_session_row.platform IS NOT NULL` (i.e. connector-attached). The shim:
    1. Captures `pre_step_len = len(agent.messages)` BEFORE the existing `agent.step` async-iter loop in `_process_and_broadcast`.
    2. AFTER `agent.step` completes (inside `_process_and_broadcast`), BEFORE `_save_session_to_db`:
       - Calls the leg-3 helper `tag_post_step_visibility(agent.messages, pre_step_len)` — this tags new non-USER messages per the F4 dispatcher rules (assistant text + intermediate tool calls/results → `OPERATOR_VISIBILITY`; successful platform-send tool_result → `None`).
       - THEN overrides the USER message at `agent.messages[pre_step_len]` with `agent.messages[pre_step_len].visibility = OPERATOR_VISIBILITY` (architect-recommended two-line call-site override instead of a second helper).
  - **Why post-step tagging of the USER message works**: `agent.step(user_input: str)` at `agent/core.py:138` appends `Message.user(user_input)` (default `visibility=None`) at the top of `step` BEFORE any iterations. The user message is therefore at index `pre_step_len` after `step` returns. Mutating its `visibility` field in-place is a direct dataclass attribute write — no signature change to `agent.step` (mission constraint preserved).
  - Test:
    - WS-typed message into a connector-attached session → after agent.step + persist, the USER message has `visibility=OPERATOR_VISIBILITY`; the assistant reply has `visibility=OPERATOR_VISIBILITY`.
    - WS-typed into a non-connector session → no tagging (byte-identical to pre-F5; regression net).
    - **WS-operator-input that triggers platform-send tool call** (architect-surfaced carve-out test): the operator types something, the agent decides to call `send_to_platform_channel`, the tool returns the success-prefix string → tool_result message has `visibility=None` (peer-visible — the platform-send carve-out fires); the surrounding assistant text + the USER message stay `OPERATOR_VISIBILITY`. Pins the dual-tagging behavior on the WS path.

- **Leg 5 — `chat-ui-render-visibility-distinction`**:
  - Extend `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:renderMessage` to accept a `visibility` param (read from the event dict's `visibility` key set by `messages_to_ui_events`). When `visibility === "operator"`, append the `msg-operator-only` class to the bubble.
  - Add `.msg-operator-only` CSS rule in the chat-area CSS file using M04/M06 tokens (`border-left: 3px solid <var(--accent-muted)>; padding-left: var(--space-2);`).
  - Add an inline `[operator-only]` label in `text-muted` style — either prepended to the message text or rendered as a small adjacent badge. Leg-5 author's call based on visual balance.
  - Update existing consumers of `renderMessage` to pass through `visibility` from the event dict.
  - Test: browser test renders a session with mixed-visibility messages and asserts the operator-only ones have the new class.

- **Leg 6 — `dispatcher-broadcast-when-subscribed`**:
  - After the dispatcher's `chat_repo.update(...)` at `connectors/_inbound.py:219`, check whether the session has live WS subscribers via the neutral module (leg 2 lift): `the_one.sessions.subscribers_for(session_id)`. If the returned set is non-empty, emit per-message UI events via `messages_to_ui_events(new_msgs)` (where `new_msgs = agent.messages[pre_step_len:]`) and call `the_one.sessions.broadcast_to_session(session_id, events)`. The import direction stays one-way (`connectors._inbound → the_one.sessions`); no function-local-import to `interfaces.web.app` needed because leg 2 already moved the subscribers/broadcast helpers out.
  - **Cadence decision** (architect-flagged): per-message events (one event per new Message), NOT a single end-of-turn batch. Matches the WS-stream cadence so an operator observing in real time sees each message as it lands. The dispatcher iterates `new_msgs` and emits one event per message via `broadcast_to_session`.
  - Test: dispatcher e2e test — push an inbound; register a fake-WS subscriber via the neutral module; the test asserts `broadcast_to_session` was called with the expected per-message events.

- **Leg 7 — `e2e-tests-and-design-language`**:
  - Browser-flow tests covering: session list shows connector-source badge; opening a connector-attached session renders both peer-visible and operator-only messages with the right distinction; typing into a connector-attached session shows the operator-visibility on the resulting messages; M04/M06 design-language passes (visual snapshot baselines local-only per the user-global rule).
  - Unit tests: shared helper extraction (leg 3); WS-shim tagging (leg 4); broadcast bridge (leg 6).

- **Leg 8 (REQUIRED) — `uat-and-alignment`**:
  - Guided HAT session walking the operator through: opening a connector-attached session, observing the source badge, scrolling the unified history, typing into the operator console, watching the agent respond in operator-only mode, triggering a platform-send (via prompting the agent to call the tool), observing the platform-visible message render without the marker, navigating back to verify session-list state.
  - Fix any design-language drift inline.

### Checkpoints

- [ ] **Checkpoint A** (after leg 1): `list_sessions` WS action returns the connector-keying fields; session-list browser test shows source badge for a stub-connector session
- [ ] **Checkpoint B** (after leg 2): shared `session_locks` registry exists; WS path + dispatcher path both use it; `Session.processing_lock` removed; concurrent same-session test passes (WS-typed + connector-inbound serialize)
- [ ] **Checkpoint C** (after leg 3): `tag_post_step_visibility` helper extracted; dispatcher uses the helper; no behavior change (existing F4 tests pass byte-identically)
- [ ] **Checkpoint D** (after leg 4): WS-typed message into a connector-attached session lands with `visibility=OPERATOR_VISIBILITY` on the user message AND on the assistant reply; non-connector sessions unchanged (regression net: existing chat tests pass byte-identically)
- [ ] **Checkpoint E** (after leg 5): Chat UI renders operator-only messages with the `msg-operator-only` class + the inline label; browser test asserts the visual distinction
- [ ] **Checkpoint F** (after leg 6): dispatcher emits broadcast events when WS subscribers are present on the session_id; zero-subscriber case persists silently (current F4 behavior)
- [ ] **Checkpoint G** (after leg 7): full browser-flow suite passes; M04/M06 design-language bar met
- [ ] **Checkpoint H** (after leg 8): HAT session signed off by the operator (REQUIRED — flight cannot land without this sign-off)

### Adaptation Criteria

**Divert if**:
- The lock-unification refactor reveals a deeper coupling between `Session.processing_lock` and the WS handler's lifespan teardown / inflight-task tracking that requires a wider restructure than option (b)-lite — surface as a flight-level redirect; the lock unification might need its own dedicated flight
- The mission-text "storage-edge shim around `_spawn_message_processing`" interpretation surfaces a different design (e.g. the operator-visibility tagging should NOT happen at the storage edge but at the WS-receive boundary) — re-read the mission text and reconcile before continuing
- The Chat UI render layer requires a layout overhaul to accommodate the operator-only marker without visual noise — surface and decide whether an alignment-flight is acceptable
- A leg of work exceeds 1 day's planned scope by more than 50% — split the leg, log the deviation

**Acceptable variations**:
- The exact CSS treatment for the operator-only marker is leg-5 author's call as long as it meets M04/M06 design-language tokens and the visual distinction is unambiguous
- The new `the_one/sessions/_locks.py` module placement can shift to a different neutral location if the leg-2 author identifies a cleaner home
- The `[operator-only]` inline label text can be tightened (e.g. `[private]` or no text at all relying on the border indicator) — leg-5 author decides
- Browser-test snapshots are local-only (gitignored per user-global rule)

### Legs

> **Note:** Tentative leg breakdown (8 legs total — HAT closer is REQUIRED per user direction at planning time, not optional). Legs are planned in detail one at a time as the flight progresses; this list will evolve. Each leg gates on `make test` + `make lint` clean (full-suite) before signaling completion.

- [x] `list-sessions-extend-with-connector-source` — WS action projects connector-keying fields; frontend session-list renders source badge
- [x] `lock-unification-and-broadcast-lift-to-neutral-module` — extract `session_locks` + `subscribers`/`broadcast_to_session` to new `the_one/sessions/` package; both WS path + dispatcher consume them; remove `Session.processing_lock` from all THREE call sites (`_spawn_message_processing`, `_restore_session`, `_build_session_joined_ok`); closes mission Known Issue + F3 debrief carry-forward
- [x] `extract-visibility-tagger-shared-helper` — factor F4-leg-4's post-step walk into a free function; dispatcher uses it; no behavior change
- [x] `ws-storage-edge-shim-for-operator-visibility` — WS-typed messages into connector-attached sessions get `visibility=OPERATOR_VISIBILITY`; non-connector sessions unchanged
- [x] `chat-ui-render-visibility-distinction` — `renderMessage` consumes `visibility`; CSS rule + inline label for operator-only marker
- [x] `dispatcher-broadcast-when-subscribed` — dispatcher emits broadcast events when WS subscribers exist; zero-subscriber case unchanged
- [x] `e2e-tests-and-design-language` — browser-flow suite covering session list, unified history, operator-only marker, design-language bar
- [ ] `uat-and-alignment` *(REQUIRED — user-directed at planning time)* — guided HAT session walking the operator through the full surface; fix issues inline; flight cannot land without operator sign-off

---

## Post-Flight

### Completion Checklist

- [ ] All 8 legs completed (HAT closer is REQUIRED, not optional)
- [ ] `list_sessions` WS action projects connector-keying fields; session-list renders source badge
- [ ] Shared `session_locks` registry replaces `Session.processing_lock`; subscribers + broadcast lifted to neutral module; mission Known Issue closed; F3 debrief carry-forward closed
- [ ] `tag_post_step_visibility` shared helper extracted; dispatcher uses it byte-identically
- [ ] WS-typed messages into connector-attached sessions land with `visibility=OPERATOR_VISIBILITY`
- [ ] Chat UI renders operator-only messages with visual distinction (M04/M06 tokens)
- [ ] Dispatcher emits broadcast events when WS subscribers exist on the session_id
- [ ] `make test`, `make lint`, browser-test recipe all clean
- [ ] No regression on F1/F2/F3/F4 surfaces; specifically: existing chat tests (non-connector sessions) pass byte-identically
- [ ] **HAT session signed off by the operator** (REQUIRED — flight cannot land without this sign-off)
- [ ] Flight log captures deviations
- [ ] Code merged
- [ ] Mission flight checkbox ticked for Flight 5

### Verification

End-to-end verification of Flight 5 has four layers:

1. **WS protocol layer** (Python tests against the FastAPI WebSocket TestClient):
   - `list_sessions` action returns the new fields for a connector-attached session; returns null for non-connector sessions; pre-F5 client (no source-badge handling) ignores them cleanly
   - WS-typed message into a connector-attached session produces a persisted session row with the user message tagged `visibility=OPERATOR_VISIBILITY`

2. **Lock-unification layer**:
   - Concurrent WS-typed + connector-inbound on the SAME session_id serialize via the shared `session_locks` registry (event-coordinated test, mirror of F3 L4)
   - Different session_ids parallelize (event-coordinated test)
   - `_restore_session`'s "is the lock held?" check uses the new registry correctly

3. **Frontend layer** (browser-flow tests via the existing Playwright recipe):
   - Session list shows source badge on stub-connector session
   - Opening a connector-attached session renders both peer-visible and operator-only messages with the distinct visual treatment
   - Typing into a connector-attached session adds an operator-only message to the unified timeline
   - M04/M06 design-language snapshot baselines pass (local-only)

4. **Cross-cutting** (regression net):
   - MCP `/test/connect` byte-identical
   - LLM provider `/test` byte-identical
   - F1 connector pool tests green
   - F2 admin surface tests green
   - F3 session-model + dispatcher tests green
   - F4 platform-send tool + dispatcher visibility-tagging tests green
   - F4 e2e platform-send tests green (the shared-helper refactor in leg 3 mustn't move behavior)
   - `make test` clean (the F4 baseline of 1945 grows by ~25-40 for Flight 5; exact number lands during execution)
   - `make lint` clean
   - Browser-test recipe green

The Flight 1 stub-plugin end-to-end test, Flight 2's admin-surface tests, Flight 3's session-model + dispatcher tests, and Flight 4's e2e platform-send tests all remain unchanged; Flight 5 ADDS coverage on top.
