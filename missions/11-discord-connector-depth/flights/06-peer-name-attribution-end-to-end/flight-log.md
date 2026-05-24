# Flight Log: Peer-name Attribution End-to-End (Bug C)

**Flight**: [Peer-name Attribution End-to-End (Bug C)](flight.md)

## Summary

Planning state. Recon report below; execution notes will follow per-leg as they land.

---

## Reconnaissance Report

Phase 1b walked the six surfaces M10 mission-debrief Bug C enumerated, against current code at F5-debrief commit. The source items are NOT a numbered list in the mission-debrief; they are enumerated inline as the six coordinated-change sites (`Message` dataclass + codec + `messages_to_ui_events` + `Agent.step` signature + live broadcast + Chat UI `addMsg`/`renderAttribution`). Each row below is one of those six surfaces.

| Item | Classification | Evidence (file:line) | Recommendation |
|------|----------------|----------------------|----------------|
| S1: `Message` dataclass carries no `peer_name` | confirmed-live | `the_one/llm/base.py:42-91` — fields are role, content, tool_calls, tool_result, usage, visibility; no peer_name | F6 L1: add `peer_name: str \| None = None`; grow `Message.user` kwarg surface; other classmethods unchanged. |
| S2: Codec encode/decode emit no `peer_name` | confirmed-live | `the_one/db/codec.py:54-101` — `message_to_dict` knows visibility (lines 66-67) but not peer_name; `message_from_dict` reads visibility (line 100) but not peer_name | F6 L1: emit-when-non-None on encode; `d.get("peer_name")` on decode (None on legacy). |
| S3: `messages_to_ui_events` user-event projection lacks `peer_name` | confirmed-live | `the_one/db/codec.py:174-177` — `Role.USER` branch emits `{type, content, source, **vis}` — no peer_name | F6 L2: spread `peer_name` onto the user event when non-None; pattern mirrors the `**vis` spread. (Split from L1 per architect review — codec ↔ UI-event projection are unrelated wire-shape contracts; default to splitting unless test surface stays small.) |
| S4: `Agent.step` signature cannot carry `peer_name` (mission constraint) | confirmed-live, design-constrained | `the_one/agent/core.py:119-151` — `step(user_input: str, ...)`; constructs `Message.user(user_input)` internally at line 144 with no peer_name. M11 constraint: agent loop NOT modified | F6 L3: dispatcher-side post-step mutation `agent.messages[pre_step_len].peer_name = working_envelope.peer_name` — mirrors `tag_post_step_visibility` pattern (also a post-step Message-mutator). NO core.py edit. Mutation site is inside the existing `session_locks` lock (two-concurrent-callers-reasoning passes per architect review). |
| S5: Live broadcast carries no `peer_name` | partially-satisfied (codec is the conduit) | `_inbound.py:675-681` uses `messages_to_ui_events(new_msgs, index_offset=pre_step_len)` for connector-inbound broadcasts — inherits S3 once L2 lands. `interfaces/web/app.py:880-894` builds `user_event` directly for operator-typed input — no peer; operator is "You"; no change needed. | F6 L3: verify by integration test in `tests/test_connectors_inbound_broadcast.py`; no new dispatcher code beyond the post-step mutation. Operator-typed path stays unchanged (no peer_name there by construction); L3 includes a negative-case test pinning this. |
| S6: Chat UI shows constant `'You'` for user attribution | confirmed-live | `the_one/interfaces/web/static/js/areas/chat.js:116-127` (`addMsg`), `:240` (renderHistory user event), `:616` (operator send echo), `:853` (live user-event handler) — all pass `'You'` literal. `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:90-103` (`renderAttribution`) — no peer concept; sides limited to `'from-you' \| 'from-agent'` | F6 L4: branch on `ev.peer_name` (replay) and `data.peer_name` (live) — attribution = peer_name when present, else 'You'; side INFERRED inside `addMsg` from `opts.peerName` truthiness (no separate `opts.side` knob, per architect suggestion); new CSS rule `.area-chat .msg.user.msg-from-peer { align-self: flex-start; ... }` declared AFTER the `.area-chat .msg.user` rule at `chat.css:129` (same-specificity override + source-order wins — L4 AC cites the exact selector + source-order requirement). Send-echo path (`chat.js:616`) unchanged. |

**Cross-flight UX-debt reconciliation** (per `cross-flight-ux-debt-reconciliation` convention): walked F3, F4, F5 debriefs and the M10 mission-debrief carry-forward queue. Open UX-debt items against F6 surfaces:

| Source | Item | Classification |
|--------|------|----------------|
| F5 debrief Action Items | AIAT 4-test cluster (now 6 flights deep) | out-of-scope — fixture-level concern, doesn't touch Message / codec / dispatcher / Chat UI |
| F5 debrief Action Items | Chronic UI tests (`test_tablist_renders_with_three_tabs`, `test_studio_section_round_trip_preserves_agent_selection`) | out-of-scope — Studio surfaces, not Chat UI |
| F5 debrief Important | 3-column field-row primitive codification (D6) | out-of-scope — connector-editor surface, not Chat UI |
| F5 debrief Important | Studio event-bus lift (n=2 trigger met) | out-of-scope — studio module, not chat module |
| F5 debrief Important | Python+JS directive-defaults cross-check test | out-of-scope — directive surface (R8 simplified), not peer_name |
| F5 debrief Important | Plugin-author guide for connectors (F3+F4 carryover) | out-of-scope — documentation work, can run in parallel without affecting F6 |
| F3 debrief carryforward | `_xxxValues` getter pattern unification; axis vocabulary constant lift; `_RegistryEntry.account_type=""` backwards-compat default removal | out-of-scope — connector-editor surface |
| M10 mission-debrief carry-forward | Audit-log inspector (F9-scoped); rate-limiting HAT (F10/F11); slash-command verification (F9); pairing resolution (F8); mentions-aware policy (F7) | out-of-scope — separate flight scopes |

**F6 surfaces have no open UX-debt items inherited from F3-F5 debriefs.** This is unusual for a single-feature flight; it reflects the fact that the Chat UI surface has been stable since F5 (M10) and the new Bug C work introduces fresh ground rather than re-touching debt.

**Methodology conventions in play**:
- `atomic-leg-pattern` (agents.md §Project-wide) — L1 lands Message + codec + UI-event projection together because they share the JSON-shape contract.
- `cross-flight-ux-debt-reconciliation` (agents.md §Project-wide) — applied above.
- `touched-surface-ux-debt-folding` (agents.md §Project-wide) — applied above; no folding needed (no open debt on F6 surfaces).
- `mechanical-fallback-prompt-truth-pairing` — the criterion-coverage map row #13 update at flight close is the mechanical-fallback for the natural-language criterion text.

---

## Leg Progress

**L1 `message-and-codec` — landed 2026-05-24.**

What landed:
- `Message` dataclass (`the_one/llm/base.py`) gained `peer_name: str | None = None` (declared after `visibility`; full comment cites M11 F06 L01 / Bug C / criterion #13 and documents the empty-string invariant guaranteed by the Discord plugin's `display_name or str(user.id)` fallback at `_discord.py:218`).
- `Message.user` classmethod (`base.py`) grew kwarg-only `peer_name: str | None = None`; threads through to constructor. `system`/`assistant`/`tool` unchanged (peer_name is meaningful only on user-role messages — they leave the field at its default None).
- `message_to_dict` (`the_one/db/codec.py`) gained an emit-when-non-None block for `peer_name`, sibling to the visibility emit. Pre-F6 rows' encoded shape is preserved byte-for-byte when peer_name is None (the default).
- `message_from_dict` (`codec.py`) reads `d.get("peer_name")` — None on legacy rows without the key (back-compat with every pre-F6 session row).
- `tests/test_db_codec.py` gained a new `TestMessagePeerNameCodec` class (9 tests) placed after `TestMessageVisibilityCodec` and before `TestMessagesToUiEventsVisibility`. Covers: dataclass field default, `Message.user` kwarg-only default + set, encode emit-when-non-None, decode back-compat, full round-trip with/without `peer_name`, and the cross-cutting `test_round_trip_with_peer_name_and_visibility` (both new fields compose; neither interferes with the other's encode/decode site).

Verification:
- `docker exec the-one pytest -x --timeout 30 tests/test_db_codec.py` — 63 passed (54 pre-existing + 9 new).
- `docker exec the-one pytest -x --timeout 30 tests/test_db_codec.py tests/test_session_lifecycle.py` — 84 passed (no consumer regressions in the session-lifecycle test surface that loads encoded messages).
- All four smoke-checks from the leg artifact's Verification Steps pass: `Message.user('hi', peer_name='alice').peer_name == 'alice'`; `message_from_dict({'role': 'user', 'content': 'hi'}).peer_name is None`; `message_to_dict(Message.user('hi'))` omits the `peer_name` key; `message_to_dict(Message.user('hi', peer_name='alice'))` includes it.

No deviations from leg spec. No source-file edits outside the leg's `Files Affected` list. `agent/core.py` and `agent/factory.py` were not touched (hard constraint reminder honored — L1 is pure dataclass + codec wire-shape work).

Per agentic-workflow protocol: no commit at leg-end. Commit is deferred to flight-end (after L4 review).

**L2 `ui-event-projection` — landed 2026-05-24.**

What landed:
- `messages_to_ui_events` in `the_one/db/codec.py` gained a per-iteration `peer = {"peer_name": msg.peer_name} if msg.peer_name is not None else {}` dict, declared as a sibling to the existing `vis` dict (both built outside the role branching). The `Role.USER` branch's event-dict spread grew `**peer` at the tail; assistant/tool_call/tool_result branches are unchanged. M11 F06 L02 comment block cites the rationale (peer_name meaningful only on user-role messages by construction; absent key === no peer attribution).
- `tests/test_db_codec.py` gained a new `TestMessagesToUiEventsPeerName` class (7 tests) placed AFTER `TestMessagesToUiEventsVisibility` and BEFORE `TestMessageVisibilityClassmethodKwargs`. Covers: user-event projection (present, absent), assistant/tool_call/tool_result paranoia (peer_name absent even when source `Message.peer_name` is set via direct constructor), compose-with-visibility (both keys present), and a mixed-session test (three user messages, keys independent per message).

Verification:
- `docker exec the-one pytest -x --timeout 30 tests/test_db_codec.py` — 70 passed (63 from L1's end-state + 7 new).
- `docker exec the-one pytest -x --timeout 30 tests/test_db_codec.py tests/test_app_websocket_pause_resume.py` — 76 passed (no consumer regressions in the WebSocket pause/resume test surface, which exercises the live broadcast path that uses `messages_to_ui_events`).
- All three smoke-checks from the leg artifact's Verification Steps pass: user event with peer_name carries the key; assistant event with peer_name on source message does NOT carry the key on the projected event; user event with both peer_name and visibility carries both keys.

No deviations from leg spec. No source-file edits outside the leg's `Files Affected` list. `agent/core.py` and `agent/factory.py` were not touched (hard constraint reminder honored — L2 is pure event-shape projection work).

Per agentic-workflow protocol: no commit at leg-end. Commit is deferred to flight-end (after L4 review).

**L3 `dispatcher-binding` — landed 2026-05-24.**

What landed:
- `the_one/connectors/_inbound.py:dispatch_inbound` gained the M11 F06 L03 post-step peer_name binding block, co-located immediately after `tag_post_step_visibility(agent.messages, pre_step_len)` and inside the existing try block under `session_locks[session_row.id]`. Defensive `assert agent.messages[pre_step_len].role == Role.USER` documents the agent-loop invariant; mutation reads `working_envelope.peer_name` (preserved through the L320 pairing-flow `replace()`). Comment block cites (a) M11 F6 / Bug C / criterion #13 origin, (b) the agent-loop-NOT-modified mission constraint, (c) the `tag_post_step_visibility` parallel idiom, (d) concurrency reasoning (same per-session lock), (e) exception-path reasoning (skipped on `agent.step` raise; partially-appended user message decodes with peer_name=None via codec back-compat).
- `the_one/interfaces/web/app.py:_process_and_broadcast` gained a comment annotation near the existing user_event construction (lines 881-894) noting that the operator-typed path does NOT acquire a `peer_name` key — the operator IS the source; there is no peer to attribute. No behavior change (comment only).
- `tests/test_connectors_inbound.py` gained two new tests in the "Visibility defaults" section between `test_dispatch_inbound_persists_inbound_with_visibility_none` and `test_dispatch_inbound_persists_agent_reply_with_visibility_operator`:
  - `test_dispatch_inbound_persists_inbound_with_peer_name_from_envelope` — asserts the persisted USER message's `peer_name == "Alice"` (matches the `_envelope()` helper's default).
  - `test_dispatch_inbound_persists_user_message_role_invariant` — pins the structural invariant the production assert relies on (first non-system message in persisted history is Role.USER).
- `tests/test_connectors_inbound_broadcast.py` gained `test_dispatch_inbound_broadcasts_carry_peer_name` immediately after `test_dispatch_inbound_broadcasts_carry_visibility`, with its own section header. Drives the same assistant-with-tool_call + final-assistant scripted chain used by the visibility test. Asserts the USER broadcast event carries `peer_name == "Alice"`, and that the `tool_call`, `tool_result`, and final `assistant` broadcast events do NOT carry a `peer_name` key (per L2's branch-gated projection).

Verification:
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_inbound.py` — 52 passed (50 pre-existing + 2 new).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_inbound_broadcast.py` — 7 passed (6 pre-existing + 1 new).
- `docker exec the-one pytest -x --timeout 60 tests/test_connectors_inbound.py tests/test_connectors_inbound_broadcast.py tests/test_connectors_session.py tests/test_db_codec.py` — 145 passed (cross-cutting connector + codec surface, all clean).

No deviations from leg spec. No source-file edits outside the leg's `Files Affected` list. `agent/core.py` and `agent/factory.py` were NOT touched (hard mission constraint honored — the whole leg design hinges on binding peer_name in the dispatcher POST-step, not in the agent loop). The `tag_post_step_visibility` precedent established the post-step Message-mutation idiom; L3 is a literal application of that same pattern for a sibling metadata field.

Per agentic-workflow protocol: no commit at leg-end. Commit is deferred to flight-end (after L4 review).

**L4 `chat-ui-attribution` — landed 2026-05-24.**

What landed:
- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:renderMessage` gained the M11 F06 L04 peer-bubble class composition block. Immediately after the existing operator-only class composition (`if (isOperatorOnly) fullCls += ' msg-operator-only';`) and BEFORE `el.className = fullCls;`, an `if (opts.peerName) { fullCls += ' msg-from-peer'; }` branch fires. Comment block cites (a) M11 F06 L04 origin, (b) the CSS source-order load-bearing requirement (same-specificity rule declared after `.area-chat .msg.user` in chat.css), (c) the visibility-composition reasoning (peer-inbound users have `visibility=None` per `connectors/visibility.py:60`, so `isOperatorOnly` is structurally false for peer bubbles — the two markers cannot co-occur in practice).
- `the_one/interfaces/web/static/js/areas/chat.js:addMsg` gained defensive `opts = opts || {};` at the top (current callers sometimes omit `opts` entirely — e.g. `addMsg('system', detail)`). Side selection became `opts.peerName ? 'from-peer' : (cls.indexOf('user') === 0 ? 'from-you' : 'from-agent')`. The `ts` lookup simplified to `Object.prototype.hasOwnProperty.call(opts, 'ts')` since `opts` is now guaranteed non-null. The `(opts && ...)` guard at the old `ts` lookup is gone.
- `chat.js:renderHistory` user-event branch reads `ev.peer_name` and binds it onto both the `histOpts.peerName` field (forwarded to `renderMessage` for the bubble class) and the `attribution` argument (`ev.peer_name || 'You'`). Other event branches unchanged.
- `chat.js` live `data.type === 'user'` handler mirrors the renderHistory binding: `var liveAttribution = data.peer_name || 'You';` and `{ visibility: data.visibility, peerName: data.peer_name }` on the opts dict.
- `chat.js:616` send-echo path is UNCHANGED — operator-typed by construction, no peer_name source. Stays `addMsg('user', text, 'You')`.
- `the_one/interfaces/web/static/css/chat.css` gained TWO new rules:
  - `.area-chat .msg.user.msg-from-peer { align-self: flex-start; background: var(--surface-elevated); color: var(--fg); box-shadow: none; border: 1px solid var(--border); }` declared immediately after `.area-chat .msg.user.api` at line 130 (same-specificity selector, source-order-after the `.msg.user` base rule). Added `border: 1px solid var(--border)` per the design-review cosmetic note — distinguishes the peer bubble from the assistant bubble (which uses `--surface-translucent`) so the two left-aligned bubble families remain visually distinct.
  - `.area-chat .msg-attribution.from-peer { align-self: flex-start; }` declared immediately after `.area-chat .msg-attribution.from-agent` at line 226. Mirrors the `from-agent` pattern; kept as a distinct class for future themed-peer styling.
- `tests/browser/test_flow_chat_peer_attribution.py` (NEW) — 1 test, browser marker. Mirrors `test_flow_chat_visibility_distinction.py`'s seed-then-render pattern. Fixtures (`app_with_data_dir`, `_seed_session_with_messages`, `_free_port`, `_wait_for_ready`) are DUPLICATED from the visibility-distinction test per design-review note (those fixtures are module-scope, not in conftest — cross-import would be brittle). Seeds a session with 5 messages: SYSTEM, USER #1 operator-typed (visibility=OPERATOR_VISIBILITY), USER #2 peer "alice", ASSISTANT (visibility=OPERATOR_VISIBILITY), USER #3 peer "bob". Asserts: peer-bubble count (2), operator-typed user-bubble count (1), first peer attribution is `.from-peer` "alice", second is `.from-peer` "bob", operator-typed attribution is `.from-you` "You", computed `alignSelf` is `flex-start` on peer bubble (CSS source-order override wins) and `flex-end` on operator-typed user bubble (base `.msg.user` rule still applies), and visibility composition (assistant has `.msg-operator-only`; peer + operator-typed user bubbles do not — F5 L8 HAT decision preserved).

Verification:
- `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_chat_peer_attribution.py` — 1 passed.
- `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_chat_visibility_distinction.py tests/browser/test_flow_chat_operator_input_visibility.py tests/browser/test_flow_chat.py` — 5 passed (no regressions on the adjacent visibility distinction test which exercises the operator-only marker that L4 must compose with cleanly).
- `docker exec the-one pytest -x --timeout 60 -m browser -k "test_flow_chat" tests/browser/` — 7 passed (full chat-flow suite: chat, operator-input-visibility, peer-attribution, session-list-source-badge, visibility-distinction).
- `docker exec the-one pytest -x --timeout 30 tests/test_db_codec.py tests/test_connectors_inbound.py tests/test_connectors_inbound_broadcast.py` — 129 passed (L1-L3 server-side regression net unaffected — L4 is pure frontend + CSS + browser test, zero Python source changes).

Operational note: the `pyproject.toml` `addopts` deselects browser tests by default (`-m 'not browser and ...'`); the targeted invocations above must add `-m browser` to select them. The leg's Verification Steps showed bare invocations; running them verbatim returns "0 selected" — adding `-m browser` is the correct adaptation.

Design-review cosmetic note honored: the `border: 1px solid var(--border)` was added to the peer-bubble rule because `--surface-elevated` reads visually close to the assistant bubble's `--surface-translucent` background — the border visually separates the two left-aligned bubble families.

No deviations from leg AC. No source-file edits outside the leg's `Files Affected` list. `agent/core.py` and `agent/factory.py` were NOT touched (hard mission constraint honored — L4 is pure frontend + CSS + browser test, structurally easy to honor as predicted).

Per agentic-workflow protocol: NO commit at leg-end. NO flight.md status flip to `landed` (L5 HAT runs next; flight status flips at the L5/Phase 3 boundary). Per the orchestrator's spawn instructions, this is the final autonomous leg before Phase 2d full-flight review.

**L4 a11y follow-up — added visually-hidden screen-reader label per Accessibility Reviewer's blocking finding (2026-05-24).** Resolves WCAG 1.3.3 (Sensory Characteristics) / 1.4.1 (Use of Color) blocker raised in the full-flight review: peer-attributed `<div class="msg user">` was semantically indistinguishable from the operator-typed user bubble to assistive technology — the only differentiators (left/right alignment + background color) are visual-only.

What changed (fix scope: pure frontend + CSS + browser test; no Python source touched; `agent/core.py` + `agent/factory.py` constraint preserved):
- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:renderMessage` — when `opts.peerName` is truthy, prepends an `<span class="msg-from-peer-label visually-hidden">From {peerName}: </span>` inside the bubble (mirrors the `msg-operator-only-label` precedent immediately above). The non-markdown text-body branch was extended: `else if (isOperatorOnly || opts.peerName)` now takes the `el.appendChild(document.createTextNode(text))` path so the prepended label survives the body append. Peer bubbles take the non-markdown branch by construction (markdown gating fires only for the `assistant` first-token), so the peer-attributed path always preserves the label.
- `the_one/interfaces/web/static/css/chat.css` — added a bare-class `.visually-hidden` rule (standard sr-only pattern: `position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0;`) inside `@layer areas`. Duplicates the identical rule at `admin.css:508`; rationale comment cites the duplication is fine for now (a future a11y maintenance pass can lift to `base.css` once a second chat-area consumer surfaces). Picked option (a) from the reviewer's two-option offer — matches the project's CSS-utility-class pattern; inline-style on the span would be uglier.
- `tests/browser/test_flow_chat_peer_attribution.py` — added Assertion 9 (each peer bubble contains `.msg-from-peer-label.visually-hidden` with textContent `'From alice: '` / `'From bob: '`, and `getComputedStyle(label).clip === 'rect(0px, 0px, 0px, 0px)' || .clipPath === 'inset(50%)'` to verify the sr-only utility is actually loaded/applied) and Assertion 10 (operator-typed user bubble does NOT contain `.msg-from-peer-label`, pinning the gate as `opts.peerName` truthiness rather than bubble role).

Verification:
- `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_chat_peer_attribution.py tests/browser/test_flow_chat_visibility_distinction.py tests/browser/test_flow_chat.py` — 4 passed.

No deviations from the Accessibility Reviewer's recommended fix. Leg status remains `landed` (this is a follow-up within the same leg; no new leg artifact needed). Per agentic-workflow protocol for this flight: NO commit at leg-end — orchestrator commits at flight-end after L5 HAT.

---

## Decisions

*(Runtime decisions appended during execution.)*

---

## Deviations

*(Departures from planned approach appended during execution.)*

---

## Anomalies

*(Unexpected issues appended during execution.)*

---

## Session Notes

**2026-05-24 (planning)** — Flight Director conducted Phase 1 (mission + F5 debrief + criterion-coverage read), Phase 1b (six-surface recon walked against current code), Phase 2 (code interrogation via grep + Read across `the_one/llm/base.py`, `the_one/db/codec.py`, `the_one/agent/core.py`, `the_one/connectors/_inbound.py`, `the_one/connectors/visibility.py`, `the_one/interfaces/web/static/js/areas/chat.js`, `the_one/interfaces/web/static/js/areas/chat/message-bubble.js`, `the_one/interfaces/web/app.py`), Phase 3-4 (summary + crew interview — operator selected: left-aligned peer-attributed bubble shape; UI-only for F6 with LLM-prompt visibility deferred to F7; back-compat via codec emit-when-non-None; UAT-and-alignment leg included).

**2026-05-24 (architect review cycle 1)** — Spawned Architect via `flight-design.md` crew prompt. Assessment: **approve with changes**. Changes incorporated:
- [high] CSS-specificity for peer-side bubble: L4 AC tightened to explicitly cite the selector `.area-chat .msg.user.msg-from-peer { align-self: flex-start; ... }` + the source-order-after-`chat.css:129` requirement.
- [medium] L1 split into L1 (`message-and-codec`) + L2 (`ui-event-projection`) as the default — codec ↔ UI-event projection are unrelated wire-shape contracts. Subsequent legs renumbered (L3 dispatcher-binding, L4 chat-ui-attribution, L5 uat-and-alignment).
- [medium] Design Decision §5 ordering framing reworded: dropped "BEFORE tag_post_step_visibility" correctness implication; kept co-location rationale. Added concurrency + exception-path notes (architect-confirmed `session_locks` + try-block compose correctly).
- [low] Design Decision §2 cites provider-adapter audit evidence (openai/anthropic/ollama project role+content explicitly; peer_name structurally cannot leak).
- Architect suggestion (addMsg side-inference vs explicit `opts.side`): adopted — side inferred from `opts.peerName` truthiness; no caller-contract drift.
- Architect Q on send-echo path (`chat.js:616`): documented as unchanged (operator-typed by construction).

No structural rework; all changes were spec-tightening. **Skipping Architect cycle 2** per skill protocol ("Skip if only minor/cosmetic fixes were applied").

Ready for Phase 6 (crew walkthrough + final approval).

---

## Flight Director Notes

**2026-05-24** — Flight transitioned `planning → ready → in-flight`. Branch `flight/06-peer-name-attribution-end-to-end` created off `main`. Phase file `leg-execution.md` loaded and validated (Crew + Interaction Protocol + Prompts present; all four prompt subsections have fenced code blocks). Crew: Developer (Sonnet) for design review + implement + fix + commit; Reviewer (Haiku) for code review; Accessibility Reviewer (Sonnet, optional) — L4 (chat-ui-attribution) involves user-facing changes and qualifies for accessibility review.

Total legs: 5. Autonomous: L1-L4. Interactive (HAT): L5. Per skill protocol, leg design is reviewed per leg; code review + commit are deferred until after L4 (the last autonomous leg). L5 (HAT) runs as a guided interactive flow with the human, not autonomously.

Starting L1: `message-and-codec`.
