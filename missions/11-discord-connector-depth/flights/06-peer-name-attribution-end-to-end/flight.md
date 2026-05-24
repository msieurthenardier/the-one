# Flight: Peer-name Attribution End-to-End (Bug C)

**Status**: in-flight
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

- [ ] M11 #13 — Peer-name attribution flows from the Discord gateway through the dispatcher, the session storage, the message broadcast, and into the Chat UI; the operator opening a connector-attached session sees `discord-username: message` in the platform-visible side of the unified history, not anonymous "peer message" entries; M10 debrief Bug C (peer_name data-model gap, 6 surfaces) is resolved.

Cumulative-debt items folded in: none. The six Bug C surfaces are the contract for this flight; the reconnaissance report (in `flight-log.md`) confirms no carry-forward UX-debt from F3-F5 debriefs touches these surfaces.

---

## Pre-Flight

### Objective

Close M10 Bug C end-to-end: thread `peer_name` from the `InboundEnvelope` (already captured at the Discord gateway in `_discord_translate.py:125` and `_discord.py:218`) through the `Message` dataclass, JSON codec, post-step dispatcher binding, live broadcast, codec replay, and Chat UI rendering — so the operator's unified history shows `alice: @bot ping?` (peer-attributed, left-aligned bubble) instead of an anonymous `You` for peer-originated messages. The constraint is preserved: `agent/core.py` and `agent/factory.py` are NOT modified; the dispatcher binds `peer_name` to the appended user message POST-step, mirroring the existing `tag_post_step_visibility` pattern.

### Open Questions

- [x] **Peer-bubble UI shape** → see Design Decisions §1.
- [x] **LLM-prompt visibility of peer_name** → see Design Decisions §2 (deferred to F7).
- [x] **Back-compat for pre-F6 stored sessions** → see Design Decisions §3.
- [x] **UAT-and-alignment leg** → see Design Decisions §4 (included).
- [x] **Where in the dispatcher does peer_name binding happen** → see Design Decisions §5.

### Design Decisions

**1. Peer-bubble UI shape: left-aligned, peer_name attribution, new `'from-peer'` side.**
- Choice: Operator-typed user bubbles stay right-aligned with `'You'`; peer-from-platform user bubbles render left-aligned with `peer_name` (e.g. `alice`). The Chat UI's `addMsg` already branches on `cls.indexOf('user') === 0 ? 'from-you' : 'from-agent'`; we introduce a third side `'from-peer'` (left-aligned, distinct from `'from-agent'` so the operator can visually distinguish peer messages from agent replies). The renderAttribution side argument grows to accept `'from-you' | 'from-agent' | 'from-peer'`.
- Rationale: Matches mission criterion text (`discord-username: message`); preserves visual hierarchy (right = me/operator; left = anyone else); distinguishes peer (e.g. another human on Discord) from the agent's own replies via CSS styling on the new side. A future generalization for connectors with avatars/colors is additive on the same side.
- Trade-off: Adds one new CSS rule + one new side enum value vs. the simpler "inline prefix" shape (`alice: ping?` inside the bubble). The visual polish is worth the small surface; consistent with F5's design-language discipline. Visually-distinct peer side is on operator's selected preview.

**2. LLM-prompt visibility: peer_name is UI/persistence-only for F6.**
- Choice: F6 lands the Bug C six-surface contract as a UI-and-persistence concern. The agent's LLM sees `Message.content` unchanged (no `alice: ` prefix injected into content; no system-prompt edit). The new `Message.peer_name` field is consumed by the codec's UI-event projection and the Chat UI; the provider-facing serialization paths (e.g. `OpenAI`/`Anthropic` adapters that translate `Message → provider dict`) do not include `peer_name`.
- Rationale: Smallest, cleanest F6 scope. Prompt-side peer attribution intersects with F7 (mentions-aware response policy — the inference pre-step needs to know who's speaking) and possibly with the operator-editable directive surface. F7 is the natural home, and bundling here would expand F6 beyond the "Bug C six surfaces" boundary M10 documented.
- Trade-off: Multi-user channels are visually distinguishable but the agent still treats the conversation as a single voice in its LLM context until F7 lands. F7 design will pick up the prompt-side question.
- **Provider audit (architect-confirmed)**: `the_one/llm/openai_provider.py:270`, `the_one/llm/anthropic_provider.py:232`, `the_one/llm/ollama_provider.py:267` all explicitly project `{"role": msg.role.value, "content": msg.content}` — none use `dataclasses.asdict(msg)` or pass through arbitrary fields. `peer_name` is structurally prevented from leaking into provider payloads, not just policy-prevented. If a future provider adapter is added, it must follow the same explicit-projection idiom.

**3. Back-compat: codec emit-when-non-None on encode; decode defaults to None.**
- Choice: Mirror the visibility back-compat pattern (`codec.py:66-67, 100`). `message_to_dict` emits `"peer_name": msg.peer_name` only when non-None. `message_from_dict` reads `d.get("peer_name")` — legacy stored messages (no key) decode with `peer_name=None` and render with the constant `'You'` attribution as today. No DB migration; no backfill script; no historical-attribution recovery attempt.
- Rationale: Cleanest, smallest, follows project convention (`visibility` precedent). Connector-attached sessions only gain peer attribution on inbound turns landing AFTER F6 ships — pre-F6 history stays as-is, which is correct semantics (we don't have peer-name data for those turns).
- Trade-off: Pre-F6 connector turns in the operator's existing session history show as `'You'` even though they came from a peer. Operator-acceptable — the historical attribution wasn't there before either.

**4. UAT-and-alignment leg included.**
- Choice: Final leg is an operator-driven HAT on a real Discord channel: a peer sends a message, the operator opens the corresponding Chat UI session, walks through the unified history confirming peer-name attribution renders correctly across user bubble + restored history + visibility composition. Budget: 1-3 escalating-tightening rounds (single-feature flight per F5 debrief methodology, not cumulative-debt cleanup).
- Rationale: Bug C is mission-criterion #13; the operator-facing verification (does it actually feel right in the UI?) is HAT-not-test territory. Tests pin the wire shape; HAT pins the UX.
- Trade-off: Adds a leg; small price for the F5-validated methodology that escalating rounds catch IA-tier issues invisible to automated tests.

**5. Dispatcher binding site: inline mutation in `_inbound.py` post-step, co-located with `tag_post_step_visibility`.**
- Choice: Mutate `agent.messages[pre_step_len].peer_name = working_envelope.peer_name` at `_inbound.py` immediately after `agent.step()` returns (after line 629) and alongside `tag_post_step_visibility(...)` at line 644. No helper extraction — this is a 1-3 line block with a single caller, mirroring the inline pattern used by F5 L6 for `index_offset`. The comment block explains why it lives outside `agent.step` (mission constraint: agent loop not modified).
- Rationale: Co-locates with visibility tagging so the post-step "fill in the metadata the agent loop doesn't know about" idiom is visible at one site. Ordering (before/after `tag_post_step_visibility`) is not load-bearing — `visibility.py:60` explicitly `continue`s on `Role.USER`, so the visibility helper never touches the USER message and cannot compose-conflict with the peer_name mutation. Architect-confirmed.
- Trade-off: Could be promoted to a sibling helper in `connectors/visibility.py` for symmetry. Deferred — `n=1` is not the codification threshold; if a future connector adds another post-step Message-mutation surface, lift then.
- **Concurrency note**: The mutation site is inside `async with session_locks[session_row.id]:` (`_inbound.py:590`), which also serializes against the operator-typed concurrent path (`_process_and_broadcast` acquires the same lock at `app.py:258`). The `two-concurrent-callers-reasoning` check passes: no race on `agent.messages[pre_step_len]`.
- **Exception path**: `agent.step` can raise during LLM call; in that case `agent.messages` has already been appended with `Message.user(envelope.text)` at `agent/core.py:144` (first line of step). The mutation site is INSIDE the `try` block at `_inbound.py:620` after `async for _ in agent.step(): pass`, so on exception the mutation does NOT run and the partially-stored user message decodes with `peer_name=None` (no harm — codec back-compat handles it). This is acceptable behavior.

**Naming / codec back-compat**: `peer_name` is the field name on `InboundEnvelope` (`base.py:76`) and across existing test fixtures (`tests/_connector_dispatch_helpers.py:190`, all `test_connectors_*.py`). The `Message` dataclass field uses the same name. The codec JSON key is `"peer_name"`. The UI-event projection key is `peer_name` (snake_case to match the rest of the event shape).

### Prerequisites

- [ ] M10 F4-F5 visibility infrastructure in place (`tag_post_step_visibility`, `OPERATOR_VISIBILITY`, codec visibility emit, Chat UI visibility rendering) — landed (verified).
- [ ] M11 F1 Discord connector type registered (provides the platform the HAT runs against) — landed (verified).
- [ ] M11 F2 directive surface + pool refactor — landed (verified). Note: F5 L6 R8 partially reverted #14's operator-editable directive override, but the underlying directive composition site (`agent/config.py:compose_system_prompt`) is unchanged for F6's purposes — F6 does not touch directive composition.
- [ ] M11 F3 discoverable-dropdowns + F4 hotfixes + F5 UX cleanup — landed (verified). F6 does NOT touch connector-editor surfaces.
- [ ] Operator can drive a real Discord channel for the HAT leg (≥1 peer account in addition to the operator). Existing M11 environment requirement.
- [ ] `peer_name` is already populated on `InboundEnvelope` by the Discord plugin's gateway translator (`_discord_translate.py:125`) and slash-command bridge (`_discord.py:218`) — verified at recon. The cited test pinning (`test_connectors_discord_translate.py:227 test_peer_name_uses_display_name_not_global_name`) confirms the source value is the guild-nickname-aware `display_name`.

### Pre-Flight Checklist
- [ ] All open questions resolved
- [ ] Design decisions documented
- [ ] Prerequisites verified
- [ ] Validation approach defined
- [ ] Legs defined

---

## In-Flight

### Technical Approach

The flight implements the M10 Bug C six-surface contract change as one atomic-leg-pattern leg (Message dataclass + codec + UI-event projection — all the pieces that share the on-disk JSON shape contract), followed by the dispatcher consumer leg, the Chat UI consumer leg, and the operator HAT.

**Surface-by-surface implementation map** (mirrors the recon table; legs L1-L4 below map to surfaces in groups — see Legs section for the leg-bundling):

1. **`Message` dataclass** (`the_one/llm/base.py:42`) — L1: add `peer_name: str | None = None` field. `Message.user` classmethod grows a `peer_name: str | None = None` kwarg-only parameter. `Message.system / .assistant / .tool` classmethods unchanged (peer_name is meaningful only on user-role messages; other roles default to None).

2. **Codec encode/decode** (`the_one/db/codec.py:54-101`) — L1: `message_to_dict` emits `"peer_name": msg.peer_name` only when non-None (mirrors visibility pattern at lines 66-67). `message_from_dict` reads `d.get("peer_name")` (None on legacy rows). No schema migration.

3. **`messages_to_ui_events`** (`the_one/db/codec.py:114-206`) — L2: the `Role.USER` branch (lines 174-177) emits `peer_name` on the user event when `msg.peer_name is not None`, mirroring the visibility spread pattern (`**vis`). Other roles are unaffected (peer_name is None on assistant/tool by construction).

4. **Dispatcher post-step binding** (`the_one/connectors/_inbound.py:618-644`) — L3: immediately after `agent.step()` returns and alongside `tag_post_step_visibility` (ordering not load-bearing per Design Decision §5), mutate `agent.messages[pre_step_len].peer_name = working_envelope.peer_name` with a comment explaining the constraint. The user message at `agent.messages[pre_step_len]` is guaranteed to be `Role.USER` (agent.step always appends `Message.user(...)` as its first action at `agent/core.py:144`). Defensive `assert agent.messages[pre_step_len].role == Role.USER` documents the invariant. Mutation is INSIDE the existing `session_locks[session_row.id]` lock and INSIDE the existing `try` block, so concurrency and exception paths are handled by composition (see Design Decision §5).

5. **Live broadcast** (`_inbound.py:675-681` for connector inbound; `interfaces/web/app.py:880-894` for operator-typed) — L3 verification: connector-inbound uses `messages_to_ui_events(new_msgs, index_offset=pre_step_len)` then broadcasts each event — once L2 lands the projection, the broadcast carries `peer_name` for free. Operator-typed path (`_process_and_broadcast`) builds `user_event` directly from `user_input` — operator has no peer_name (operator is "You"); this path stays unchanged. Verified by negative-case test in L3.

6. **Chat UI consumption** (`the_one/interfaces/web/static/js/areas/chat.js:116-127, 240, 853` and `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:90-103`) — L4:
   - `addMsg(cls, text, attribution, opts)` keeps signature; callers pass `attribution = ev.peer_name || 'You'` AND `opts.peerName = ev.peer_name` for user events. Side is INFERRED inside `addMsg` from `opts.peerName` truthiness: `var side = opts.peerName ? 'from-peer' : (cls.indexOf('user') === 0 ? 'from-you' : 'from-agent')` — no separate `opts.side` knob (avoids caller-contract drift per architect suggestion).
   - `renderAttribution(side, text, ts)` grows to accept `'from-peer'`; CSS adds `.msg-attribution.from-peer` styling (left-aligned, distinct color/border from `.from-agent` so peer messages don't visually merge with agent replies).
   - Bubble side: `renderMessage` already styles `.msg.user` (right-aligned). For peer bubbles, when `opts.peerName` is truthy, the bubble gets an additional `msg-from-peer` class. The CSS rule is `.area-chat .msg.user.msg-from-peer { align-self: flex-start; background: <peer-color>; }` — same specificity as `.area-chat .msg.user` (which is at `chat.css:129`) AND declared AFTER it in source order so the override wins. **L4 acceptance criterion MUST cite both the exact selector AND the source-order requirement.**
   - Replay path (`renderHistory`, line 220-265): branches on `ev.peer_name` to choose attribution + side.
   - Live path (`onmessage data.type === 'user'`, line 846-854): branches on `data.peer_name` likewise.
   - Send-echo path (`chat.js:616`, operator typing into the input box): stays unchanged. Operator has no peer_name by construction.
   - Visibility composition: a peer-attributed message has `visibility=None` (platform-visible, no operator-only marker) — confirmed by `tag_post_step_visibility` which SKIPS `Role.USER` (line 60) so the constructor default (None) sticks. The `msg-operator-only` class is gated on `firstToken === 'user' → isUserBubble → skip operator-only marker on user bubbles` (already true at `message-bubble.js:43-44`); the new peer side composes cleanly with this — peer bubbles render unmarked, operator-typed user bubbles render unmarked, both correct.

**Testing strategy** (per leg):
- L1 unit: codec round-trip with/without peer_name (`tests/test_db_codec.py`); legacy-shape JSON decodes with `peer_name=None`; `Message.user("x")` default; `Message.user("x", peer_name="alice")` kwarg.
- L2 unit: `messages_to_ui_events` user-event projection includes `peer_name` when set, omits the key when None (same test file).
- L3 integration: dispatcher binding (`tests/test_connectors_inbound.py`); existing dispatcher tests already pass `peer_name="Alice"` in envelopes so the new assertion is `assert agent.messages[pre_step_len].role == Role.USER and agent.messages[pre_step_len].peer_name == "Alice"`.
- L3 live-broadcast: `tests/test_connectors_inbound_broadcast.py` (or a new sibling) pins that the broadcast event carries `peer_name` when set; negative test pins operator-typed `_process_and_broadcast` user_event does NOT acquire a peer_name key.
- L4 browser: `tests/browser/test_flow_chat_peer_attribution.py` (new) pins DOM-shape (peer bubble has `msg-from-peer` class + `from-peer` attribution side + correct peer name text) for replay AND live. Composes with existing `test_flow_chat_visibility_distinction.py` (peer bubble + agent reply + operator-typed operator-only marker all coexist).
- L4 CSS verification: a browser test reads `getComputedStyle(peerBubble).alignSelf` and asserts `'flex-start'` — direct verification that the source-order CSS override wins (extends the F5 L4 `evaluate_script` pattern that proved `getComputedStyle === "none"` for the hidden-attribute fix).

### Checkpoints

- [ ] L1: Message dataclass + codec round-trip — `Message.peer_name` field + emit-when-non-None encode + back-compat decode; round-trip tests pass.
- [ ] L2: UI-event projection — `messages_to_ui_events` user-event branch propagates `peer_name`; projection tests pin.
- [ ] L3: dispatcher binding — peer_name lands on `agent.messages[pre_step_len]` post-step; integration tests + live-broadcast tests pin.
- [ ] L4: Chat UI consumption — peer bubble renders left-aligned with peer_name across replay + live; browser tests pin; CSS source-order and specificity verified.
- [ ] L5: HAT — operator drives a real Discord peer message, verifies UX through 1-3 escalating-tightening rounds; criterion-coverage update; flight close.

### Adaptation Criteria

**Divert if**:
- L1 reveals a hidden coupling between `Message.peer_name` and the LLM-facing serialization paths (e.g., a provider adapter that auto-serializes all dataclass fields into the API call) — would expand scope into "LLM-prompt visibility" Design Decision §2's deferred surface. Architect audit confirmed clean today (OpenAI/Anthropic/Ollama all explicitly project role+content only); re-verify at L1 cycle-1.
- L3 reveals that `agent.messages[pre_step_len]` is not guaranteed `Role.USER` (e.g., a future change makes step() prepend a system message) — would require a defensive search loop or a different binding strategy.
- L4's Chat UI changes break the visibility composition (operator-only label appears on peer bubbles incorrectly, or vice versa) — would require visibility-vs-peer interaction redesign.

**Acceptable variations**:
- L1 + L2 can fold into a single leg if the codec test surface stays small AND the UI-event projection change is a single-spread one-liner — the architect noted the split is the default but the fold is legitimate when the dirty surfaces are co-located in `the_one/db/codec.py` and the test surface is single-file. Default is to split; fold-decision made at L1 cycle-1.
- L4 sub-splits between replay and live paths if browser-test setup becomes time-dominant in a single leg.
- L5 round count adjusts up to ~3 (single-feature flight HAT budget per F5 debrief methodology); if it escalates past 3 the flight is mis-scoped and a follow-up needed.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `message-and-codec` — Message dataclass gains `peer_name: str | None = None` field; `Message.user` classmethod adds a kwarg-only `peer_name: str | None = None` parameter; codec `message_to_dict` emits `"peer_name"` only when non-None (mirrors visibility precedent at `codec.py:66-67`); `message_from_dict` reads `d.get("peer_name")` defaulting to None on legacy rows; unit tests pin: (a) round-trip with peer_name set, (b) round-trip with peer_name None (key absent from JSON), (c) legacy-shape JSON (no `peer_name` key) decodes with `peer_name=None`, (d) `Message.user("x").peer_name is None`, (e) `Message.user("x", peer_name="alice").peer_name == "alice"`.
- [x] `ui-event-projection` — `messages_to_ui_events` Role.USER branch propagates `peer_name` onto the user event when `msg.peer_name is not None`, mirroring the `**vis` spread pattern; other roles unaffected; unit test pins user-event includes `peer_name` when set AND omits the key when None (preserves event-shape minimalism per the visibility precedent at `codec.py:173`).
- [x] `dispatcher-binding` — `_inbound.py` post-step mutation `agent.messages[pre_step_len].peer_name = working_envelope.peer_name` after `agent.step()` returns (inside the existing `try` and the existing `session_locks[session_row.id]` lock); a defensive `assert agent.messages[pre_step_len].role == Role.USER` documents the invariant; integration tests pin (a) the binding via existing `peer_name="Alice"` envelope fixtures in `tests/test_connectors_inbound.py` / `tests/test_connectors_session.py`, (b) the projected live-broadcast event carries `peer_name` when set (extend `tests/test_connectors_inbound_broadcast.py` or add a sibling), (c) operator-typed path's `user_event` in `_process_and_broadcast` does NOT acquire a `peer_name` key (operator has no peer; verify negative case).
- [x] `chat-ui-attribution` — `the_one/interfaces/web/static/js/areas/chat.js` `renderHistory` (line 220-265) and live `data.type === 'user'` handler (line 846-854) branch on `ev.peer_name` / `data.peer_name` respectively; when present, pass it as the attribution string AND pass `opts.peerName = ev.peer_name` (or `data.peer_name`) into `addMsg`. `addMsg(cls, text, attribution, opts)` keeps signature; side selection becomes: `opts.peerName ? 'from-peer' : (cls.indexOf('user') === 0 ? 'from-you' : 'from-agent')` — side is INFERRED from `opts.peerName` truthiness, not a separate `opts.side` knob (architect suggestion — avoids a brittle caller contract). The send-echo path (`chat.js:616`) is operator-typed by definition and stays unchanged (no peer_name). `renderMessage` adds class `msg-from-peer` to the bubble when `opts.peerName` is truthy. `renderAttribution(side, text, ts)` accepts the new `'from-peer'` side. CSS rule added to `the_one/interfaces/web/static/css/chat.css`: a selector `.area-chat .msg.user.msg-from-peer { align-self: flex-start; background: <peer-background>; }` declared AFTER the existing `.area-chat .msg.user { align-self: flex-end; background: var(--accent); }` rule at `chat.css:129` — same-specificity override + source-order wins. Acceptance criterion in this leg's spec MUST cite the exact selector AND the source-order requirement. Browser tests in `tests/browser/test_flow_chat_peer_attribution.py` (new): (a) replay path renders peer bubble left-aligned with peer_name attribution, (b) live path same, (c) operator-typed bubble in same session still right-aligned with 'You', (d) visibility-composition: peer bubble (visibility=None) coexists with operator-only assistant marker correctly.
- [ ] `uat-and-alignment` *(optional, but recommended per crew interview)* — operator-driven HAT against a real Discord channel; 1-3 escalating rounds; verify peer-attributed bubble shape, replay preservation, operator-typed bubble unchanged, edge cases (peer DM, peer in thread, multiple peers in same channel, peer with unicode/emoji name, peer who changes display_name mid-session); criterion-coverage map updated (row #13 → `closed-by-F6`); F6 flight-debrief.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (non-browser + browser tiers)
- [ ] Criterion-coverage map updated (row #13 → `closed-by-F6`; row #22 reference noted)
- [ ] Documentation updated (none expected — F6 doesn't add CLI/API surface; agents.md update only if a new convention surfaces during the flight)

### Verification

How to confirm the flight achieved its objective:

1. **Wire-shape pin**: in a fresh test DB, dispatch an inbound envelope with `peer_name="alice"` against a connector-attached session; decode the stored messages; assert the first new message has `Role.USER` AND `peer_name == "alice"`.
2. **Codec round-trip pin**: encode a Message with `peer_name="alice"`; decode; assert `peer_name == "alice"`. Encode a legacy-shape JSON (no `peer_name` key); decode; assert `peer_name is None`.
3. **UI-event projection pin**: `messages_to_ui_events([Message.user("hi", peer_name="alice")])` emits `{type: "user", content: "hi", source: "restored", peer_name: "alice"}`.
4. **Live broadcast pin**: a connector-inbound dispatch fires a WebSocket `user` event carrying `peer_name`; the operator-typed path's `user` event still does NOT carry `peer_name` (no peer; operator is "You").
5. **Chat UI replay pin**: opening a session with stored peer-attributed messages renders left-aligned bubbles with `peer_name` attribution; operator-typed messages still right-aligned with `'You'`; agent messages still left-aligned with agent label.
6. **Chat UI live pin**: an inbound peer message arriving while the operator is on the session renders a peer-attributed left bubble; the subsequent agent reply renders left with the agent label; the operator's typed reply renders right with `'You'`.
7. **HAT verification**: operator-driven walkthrough on a real Discord channel confirms the unified history reads naturally — operator can identify WHO said WHAT at a glance, including in multi-user channels and DMs.

**Criterion-coverage update** (post-flight):

| # | Criterion (excerpt) | Status | Evidence | Last touched |
|---|---------------------|--------|----------|--------------|
| 13 | Peer-name attribution end-to-end (gateway → dispatcher → session → Chat UI) | closed-by-F6 | F6 L1-L3 codec + dispatcher + Chat UI; `tests/test_db_codec.py::test_peer_name_round_trip`; `tests/test_connectors_inbound.py::test_dispatcher_binds_peer_name_post_step`; `tests/browser/test_flow_chat_peer_attribution.py`; F6 debrief HAT | F6 |
