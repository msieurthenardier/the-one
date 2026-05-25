# Flight Debrief: Peer-name Attribution End-to-End (Bug C)

**Date**: 2026-05-24
**Flight**: [Peer-name Attribution End-to-End (Bug C)](flight.md)
**Status**: landed
**Duration**: 2026-05-24 (planning + L1-L4 autonomous implementation + Phase 2d full-flight review + L5 HAT + Phase 3 landing — single-day flight)
**Legs Completed**: 5 of 5 (L1 + L2 + L3 + L4 + L5)

## Outcome Assessment

### Objectives Achieved

F6 closed M10 debrief Bug C end-to-end. `peer_name` threads from the `InboundEnvelope` (already populated at the Discord gateway in `_discord_translate.py:125` and `_discord.py:218`) through every downstream surface:

- **L1** (`message-and-codec`) — `Message.peer_name: str | None = None` field; `Message.user` kwarg-only `peer_name`; codec emit-when-non-None encode + back-compat decode mirroring the visibility precedent.
- **L2** (`ui-event-projection`) — `messages_to_ui_events` `Role.USER` branch spreads `peer_name` onto the user event when set; assistant/tool_call/tool_result branches structurally gated (paranoia tests pin).
- **L3** (`dispatcher-binding`) — `_inbound.py:dispatch_inbound` mutates `agent.messages[pre_step_len].peer_name = working_envelope.peer_name` POST-step, inside the existing per-session lock + try block, mirroring `tag_post_step_visibility`. Hard mission constraint preserved (no `agent/core.py` / `agent/factory.py` edits). Defensive `assert agent.messages[pre_step_len].role == Role.USER` documents invariant; paired with a real test assertion so the invariant is defended even under `python -O`.
- **L4** (`chat-ui-attribution`) — Chat UI renders peer bubbles left-aligned with peer-name attribution via a new `'from-peer'` side; side inferred from `opts.peerName` truthiness inside `addMsg` (no caller-side knob drift). CSS rule `.area-chat .msg.user.msg-from-peer { align-self: flex-start; ... }` declared after `chat.css:129` with same-specificity-source-order-wins discipline. A11y follow-up landed: visually-hidden `From {peerName}:` screen-reader label mirroring `msg-operator-only-label` precedent; `.visually-hidden` utility added to `chat.css` (duplicating `admin.css:508`).
- **L5** (`uat-and-alignment`) — operator-driven HAT against real Discord traffic; single round; Steps 1-6, 8, 10 pass; Steps 7 (multi-peer) and 9 (screen reader) skipped per operator availability; Step 10 rating `looks-good` with no inline fixes needed.

### Mission Criteria Advanced

| M11 criterion | Status after F6 |
|---|---|
| #13 — Peer-name attribution end-to-end (gateway → dispatcher → session → Chat UI) | **`closed-by-F6`** — five new test surfaces (`TestMessagePeerNameCodec`, `TestMessagesToUiEventsPeerName`, `test_dispatch_inbound_persists_inbound_with_peer_name_from_envelope`, `test_dispatch_inbound_broadcasts_carry_peer_name`, `test_flow_chat_peer_attribution.py`) + L5 HAT operator confirmation |

Criterion-coverage map updated; `Last touched` = F6.

## What Went Well

- **L1+L2 atomic-leg-pattern split was the right call.** Architect cycle 1 split the originally bundled "Message + codec + UI-event projection" into two legs because codec JSON shape and WebSocket-event shape are unrelated wire-format contracts. In retrospect: 9 + 7 tests respectively (small), but the contract boundary stayed clear at debrief time. The fold-option (DD Acceptable Variations) was preserved as escape valve but never taken.
- **Architect cycle-1 catches prevented design-time bugs from reaching code.** L4's high-severity CSS-specificity finding (the new `.msg-from-peer` rule must target `.area-chat .msg.user.msg-from-peer` with source-order-after-`chat.css:129`) was load-bearing — shifted CSS specificity from runtime-discovery to spec-time. Architect cycle-1 also caught the original L1 over-bundling.
- **The post-step Message-mutation pattern composed cleanly.** L3's binding mirrors `tag_post_step_visibility` literally — same per-session lock, same try block, same `messages[pre_step_len:]` addressing scheme. `visibility.py:60` `continue`s on `Role.USER` while peer_name only addresses Role.USER, so the two mutators cannot compose-conflict.
- **Provider-adapter audit (Design Decision §2) turned a policy promise into a structural guarantee.** OpenAI/Anthropic/Ollama providers all explicitly project `{role, content}` (verified in code, not just convention) — `peer_name` cannot leak into provider payloads without an explicit code change. Audit-into-design-decision shape worth carrying forward.
- **Defensive runtime `assert` + paired unit test = belt + suspenders.** The `assert agent.messages[pre_step_len].role == Role.USER` is a tripwire for any future agent-loop refactor that violates the invariant; the matching `test_dispatch_inbound_persists_user_message_role_invariant` unit test pins it as a regular test assertion so the invariant is defended even if `-O` strips asserts.
- **Codec back-compat preserved byte-identical encoding** for pre-F6 messages. `peer_name` defaults to None → key omitted from JSON → encoded shape unchanged. No DB migration, no backfill script, no shape churn.
- **L4 browser-test computed-style probe** (`getComputedStyle(peerBubble).alignSelf === 'flex-start'`) directly verifies the CSS source-order override wins at the rendering layer. F5 L4's `evaluate_script` pattern is now reinforced (F5 used it for `display: none`; F6 used it for `align-self: flex-start`).
- **Single-day flight cadence.** All five legs designed, reviewed, implemented, reviewed-at-flight-level, HAT'd, and committed in one working day — F6 is the smallest flight of M11 so far, on a tight wire-shape contract.
- **L5 HAT in one round, `looks-good`** — validates F5 debrief's "single-feature flights budget 1-3 rounds" heuristic at the floor of the band.
- **`cross-flight-ux-debt-reconciliation` recon was correct in retrospect.** The "no open UX-debt items inherited from F3-F5 touch F6 surfaces" finding held throughout — no late-discovered miss surfaced during L1-L5 or HAT. The convention works; empty queue is a valid outcome of the discipline.

## What Could Be Improved

### Process

- **L4 a11y was a real spec gap, not a polish item.** The flight Design Decisions section had no a11y subsection; L4 shipped without an sr-only label and the Accessibility Reviewer's cycle-1 finding was **blocking** (WCAG 1.3.3 / 1.4.1 — left/right alignment + background color are visual-only differentiators). The fix landed cleanly and reviewers confirmed in cycle 2, but the leg AC could have anticipated it. **Operator's verdict at debrief**: cycle-1 catch was the right surface — late-but-cheap. No methodology change needed. Carry-forward observation only: when a UI leg introduces a new visual distinction (color, alignment, iconography), it is worth pausing at design time to ask "what does AT announce?" — but this is leg-author discipline, not a mandated AC.
- **Browser-test invocations in L4's Verification Steps used bare `pytest tests/browser/...`** which silently selects 0 tests because `pyproject.toml` `addopts` deselects browser tests by default. The implementer noticed and corrected via `-m browser`. **Methodology note**: Verification Steps in browser-tier legs should always include the explicit marker selector.

### Technical

- **`.visually-hidden` utility now duplicated** between `chat.css` and `admin.css`. n=2 codification threshold for utility classes met; lift to `base.css` is a routine-maintenance candidate. ~5 LOC to add + 2 deletions.
- **Browser-test fixtures duplicated** between `test_flow_chat_peer_attribution.py` and `test_flow_chat_visibility_distinction.py` (`app_with_data_dir`, `_seed_session_with_messages`, `_free_port`, `_wait_for_ready`). The leg spec called this out explicitly; module-scope fixtures, cross-import would be brittle. n=2 threshold met; F4 already flagged a sibling concern (`discoverable_entities.py`). Lift to `tests/browser/fixtures/seeded_session.py` queued.
- **Post-step Message-mutation idiom at n=2** (`tag_post_step_visibility` + L3 peer_name binding). Design Decision §5 deferred a helper extraction at n=1; threshold now met. Either codify as an `agents.md` Project-wide convention (`post-step-dispatcher-message-metadata-binding`) or lift to a `connectors/post_step_metadata.py` module that exports both mutators with a documented composition contract. Recommendation: **codify the pattern first** (covers the design-time decision shape), defer the module-lift to n=3.
- **Emit-when-non-None / decode-to-None pattern at n=3+** (visibility + tool_result.metadata + peer_name). Worth promoting to an explicit `agents.md` Project-wide convention so future Message-additive flights inherit the back-compat discipline by default.

### Documentation

- **No CLI/API/configuration surface added** by F6, so `CLAUDE.md` / `README.md` / `docs/` were verified untouched — confirmed via `grep -ri peer_name`. F6 added zero user-facing operator commands.
- **`agents.md` convention candidates** (see Recommendations) — currently the post-step mutation pattern and the emit-when-non-None pattern live as code precedents but aren't documented as conventions. With n=2 (post-step) and n=3+ (emit-when-non-None) reached, both are codification-ready.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| L1 split from original bundle into L1 (Message + codec) + L2 (UI-event projection) at architect cycle 1 | Codec JSON shape and WebSocket-event shape are unrelated wire-format contracts; `atomic-leg-pattern` boundary is "shares a contract" not "shares a file" | **Already standardized** — `atomic-leg-pattern` (agents.md L162) covers this. The fold-option was preserved as escape valve. |
| L4 shipped without sr-only label initially; Accessibility Reviewer cycle 1 raised a blocking WCAG 1.3.3 / 1.4.1 finding; fixed in cycle 2 with visually-hidden span + `.visually-hidden` utility | A11y wasn't an explicit design-decision section at flight planning; new visual distinction introduced a semantic-equivalence gap to AT | **No (per operator)** — cycle-1 catch is the right surface; late-but-cheap. Carry-forward as leg-author awareness, not mandated AC. |
| L3's defensive `assert` + paired unit test (`test_dispatch_inbound_persists_user_message_role_invariant`) | Belt-and-suspenders for the agent-loop invariant `step()` appends `Message.user(...)` as its first action | **Pattern worth replicating**: when a runtime `assert` documents a cross-subsystem invariant, pair it with a regular test assertion so the invariant survives `-O`. |
| L4 added `.visually-hidden` utility to `chat.css` (duplicates `admin.css:508`) rather than lifting to `base.css` | At n=2 the duplication-with-comment-trigger is project-acceptable per `n=2-codification`; lift queued for routine-maintenance | **No** at n=2; lift to base.css when n=3 surfaces. |
| L5 HAT skipped Step 7 (multi-peer in same channel) and Step 9 (screen reader) | Single peer account available at HAT time; wire-shape pinned by L4 browser test seeding two distinct peers (`alice` + `bob`) | **No** — skip-with-citation is the right shape when wire-shape is pinned elsewhere. |
| `.visually-hidden` utility-class duplication-with-comment-trigger | n=2 codification threshold for utility classes is met; lift queued | Routine-maintenance candidate. |

## Key Learnings

1. **n=2 codification triggers compound across flights AND categories.** F5 hit it for cross-component event channels; F6 hits it for three different patterns at once (`.visually-hidden` utility, browser-test fixtures, post-step Message-mutation idiom). The next routine-maintenance flight has a queue of three n=2-or-higher lift candidates plus carry-forward items. The convention is doing its job — patterns surface, get used, and at n=2 they earn promotion.
2. **Auditing-into-design-decision shape** (the F6 DD §2 provider-adapter audit) is more durable than policy-promise-into-design-decision. Where F6 said "`peer_name` cannot leak into provider payloads," that's a *structural* guarantee (openai/anthropic/ollama all explicitly project `{role, content}`), not a policy promise. Future flights with similar "should never leak" claims should perform analogous audits at design time and cite the evidence in the Design Decision.
3. **Defensive runtime `assert` + paired unit test** is a strong pattern for documenting cross-subsystem invariants. L3's `assert agent.messages[pre_step_len].role == Role.USER` is paired with `test_dispatch_inbound_persists_user_message_role_invariant`; the invariant is defended at runtime AND in CI, even if `-O` strips asserts.
4. **`opts.<thing>` truthiness inference** beats `opts.side` knob exposure. Architect cycle-1 suggestion to infer the new `'from-peer'` side from `opts.peerName` truthiness (rather than expose a separate `opts.side` knob) eliminated a brittle caller-side contract. Carry-forward: when adding a new "side"/"mode"/"variant" to a render function, prefer inferring from existing semantic-data presence over adding a parallel knob.
5. **Single-feature HAT budget validated at floor of 1-3 range.** F6's `looks-good` after one round confirms F5 debrief's heuristic for single-feature flights. Cumulative-debt flights stay 5-8 (F5 evidence); single-feature with comparable autonomous-review depth lands in 1-2 rounds.
6. **Codec back-compat-by-emission-pattern is now n=3+** (visibility, tool_result.metadata, peer_name). Worth promoting from de-facto codec idiom to a documented project-wide convention so the next Message-additive flight inherits the discipline by default.

## Test Metrics

Run inside the `the-one` container, 2026-05-24 post-flight-landing (HEAD `8b384d4`).

| Tier | Pass | Fail | Skip | Wall |
|------|------|------|------|------|
| Non-browser (`-m "not browser"`) | 2491 | 4 | 7 | 206.7s |
| Browser (`-m browser`) | 419 | 2 | 35 | 465.1s |
| **Combined** | **2910** | **6** | **42** | **~672s** |

### Comparison vs prior flights

| Flight | Combined pass | Failures | Wall |
|---|---|---|---|
| M10 F8 baseline | 2331 | 10 | n/a |
| F1 | 2804 | 10 | 610s |
| F3 | 2879 | 7 | ~658s |
| F4 | 2899 | 6 | ~717s |
| F5 | 2890 | 6 | ~714s |
| **F6** | **2910** | **6** | **~672s** |

### Failure breakdown (all 6 carry-forward; 0 F6-introduced regressions)

**AIAT cluster** (4 fail; now **7 flights deep**): `test_basic_chat`, `test_tool_use_file_read`, `test_self_awareness`, `test_multi_step` — `Agent 'default' has no provider configured`. Fixture issue. F6 did not touch the AIAT surfaces; failures unchanged from F5. **Highest-priority routine-maintenance candidate.**

**Chronic UI tests** (2 fail; now **8 flights deep**): `test_tablist_renders_with_three_tabs`, `test_studio_section_round_trip_preserves_agent_selection`. Studio surfaces unaffected by F6. **Tied for highest-priority routine-maintenance candidate.**

### Test count delta vs F5 (+20 net pass; 0 regression)

- L1 added 9 codec round-trip tests (`TestMessagePeerNameCodec`).
- L2 added 7 UI-event projection tests (`TestMessagesToUiEventsPeerName`).
- L3 added 2 dispatcher tests + 1 broadcast test.
- L4 added 1 browser test with 10 distinct assertions (`test_chat_renders_peer_attribution`).
- Browser tier: 1 new test added; pre-existing count grew by 1 (419 vs ~418 in F5).
- Non-browser tier: 19 new tests; pre-existing count grew by 19 (2491 vs 2472 in F5).

### Key timing observations

- **Wall time dropped ~42s** vs F5 (~672s vs ~714s) — both tiers shorter (non-browser 206.7s vs 237.6s; browser 465.1s vs 476.2s). F6 added 20 tests yet the run got faster; likely host variance / Docker warmup, not a real perf delta. **No regression.** Worth noting: this is the first flight since F2 where the suite got faster rather than slower.
- **No flakes observed.** Both runs single-pass clean; no rerun, no retry.
- **Throughput per F2-era observation** is at ~4.33 t/s overall (2910 / 672s) — improving slightly from F5's ~4.05 t/s, though wall-time variance dominates this number's reliability.

## Recommendations

### Critical — before F7 lands

1. **Promote `cross-subsystem-pattern-premise-revalidation` from M10-specific to project-wide** in `agents.md` if not already done — F6 confirmed the audit-into-design-decision shape (Design Decision §2 provider audit) is durable across flights. Worth a Sources update on the existing convention entry.
2. **Codify the `post-step-dispatcher-message-metadata-binding` pattern** as a new `agents.md` Project-wide convention. n=2 evidence: `tag_post_step_visibility` (M10 F4 L4) + L3 peer_name binding (M11 F6 L3). Wording sketch in the Architect interview's Forward-Looking section. F7 (mentions-aware response policy) is the natural first consumer.
3. **Codify the `message-additive-back-compat-via-emit-when-non-none` pattern** as an `agents.md` Project-wide convention. n=3+ evidence: visibility (M10 F3 L2), tool_result.metadata (F5 L3), peer_name (M11 F6 L1). Future Message-additive flights inherit the back-compat discipline by default.

### Important — F7 (mentions-aware response policy) design considerations

4. **F7 must decide `peer_name`'s LLM-side surface.** F6 punted to F7 (Design Decision §2). F7's design must either (a) thread peer_name into provider payloads via an explicit projection change (e.g. prepend `[from alice]: ` to `Message.content` at provider-serialize time), (b) introduce a system-prompt directive describing multi-peer context, or (c) explicitly keep peer_name UI-only forever. The provider audit pattern (F6 DD §2) is the precedent for this decision.
5. **F7 can reuse the post-step Message-mutation idiom directly.** The mentions-aware inference pre-step or post-step can land on `agent.messages[pre_step_len]` (or a flag on the dispatcher's audit-log) the same way peer_name does — no new infrastructure needed if the convention from Recommendation #2 is codified.
6. **F7's inference pre-step composes with the F6 session lock + try block.** The exception-path reasoning (mutation skipped on agent.step raise) and concurrency reasoning (per-session lock) both apply.

### Methodology — promote to mission-control skills

7. **`/leg` skill — Verification Steps for browser-tier legs must include the `-m browser` selector.** F6 L4 caught this at implementation time (`pyproject.toml` `addopts` deselects browser tests by default). Add to the leg-design checklist: "verify all pytest invocations in Verification Steps actually select tests under the project's default `addopts`."
8. **`/flight-debrief` skill — closed-mission-criterion status transitions** should be reflected in criterion-coverage.md by the flight that triggers the transition. F6 closed criterion #13 cleanly; the debrief skill already references this responsibility but the discipline is project-side. Worth confirming the skill prompt explicitly cites criterion-coverage.md updates.

### Important — refactoring opportunities (routine-maintenance candidates)

9. **Lift `.visually-hidden` utility to `base.css`** (n=2 trigger met). ~5 LOC + 2 deletions. Forces no design conflict; both copies are byte-identical.
10. **Lift shared browser-test fixtures to `tests/browser/fixtures/seeded_session.py`** (n=2 trigger met). `app_with_data_dir`, `_seed_session_with_messages`, `_free_port`, `_wait_for_ready` are duplicated across F5/F6 visibility/peer browser tests. F4 also flagged `discoverable_entities.py` — fold into one fixtures lift.
11. **AIAT cluster fix** (now 7 flights deep — highest-priority routine-maintenance candidate). Fixture-level concern; affects `test_basic_chat`, `test_tool_use_file_read`, `test_self_awareness`, `test_multi_step`.
12. **Chronic UI tests fix** (now 8 flights deep — tied highest-priority). `test_tablist_renders_with_three_tabs`, `test_studio_section_round_trip_preserves_agent_selection` — update to match prod or invert.

### Routine-maintenance candidates (carryforward + new)

- **AIAT 4-test cluster** — fixture fix (now 7 flights deep).
- **Chronic UI tests** — 2 remaining; update to match prod (now 8 flights deep).
- **`_xxxValues` getter pattern unification** (F3 carryover).
- **Axis vocabulary constant lift** (F3 carryover).
- **`_RegistryEntry.account_type=""` backwards-compat default removal** (F3 carryover).
- **Plugin-author guide for connectors** (F3 + F4 carryover).
- **Studio event-bus lift** (F5 carryover; n=2 trigger met).
- **3-column field-row primitive codification** (F5 carryover; D6).
- **Python+JS directive-defaults cross-check test** (F5 carryover).
- **F6 NEW**: `.visually-hidden` utility lift to `base.css` (n=2 trigger met).
- **F6 NEW**: Shared browser-test fixtures lift (n=2 trigger met).
- **F6 NEW**: Post-step Message-mutation idiom codification or module lift (n=2 trigger met).
- **F6 NEW**: Emit-when-non-None / decode-to-None pattern codification (n=3+ trigger met).

## Action Items

### Immediate (before F7 planning)

- [ ] Add `post-step-dispatcher-message-metadata-binding` convention to `the_one/agents.md` Project-wide section (Recommendation #2; n=2 trigger met).
- [ ] Add `message-additive-back-compat-via-emit-when-non-none` convention to `the_one/agents.md` Project-wide section (Recommendation #3; n=3+ trigger met).
- [ ] F7 architect briefing: cite F6's provider-audit precedent (DD §2) and the post-step Message-mutation pattern; resolve peer_name LLM-side decision early.
- [ ] Update F6 PR #74 from draft → ready-for-review (already done in Phase 3 commit).

### Methodology (before F7 planning)

- [ ] Surface to mission-control: `/leg` skill — browser-test Verification Steps must include `-m browser` selector.
- [ ] Surface to mission-control: `/flight-debrief` skill — criterion-coverage.md update is the debrief's mechanical-fallback for closed-criterion status (already implicit in the project's `mechanical-fallback-prompt-truth-pairing` convention).

### Near-term (before F8)

- [ ] `.visually-hidden` utility lift to `base.css` (~5 LOC + 2 deletions; n=2 trigger met).
- [ ] Shared browser-test fixtures lift to `tests/browser/fixtures/seeded_session.py` (n=2 trigger met; F4 + F6 evidence).
- [ ] Post-step Message-mutation module lift to `connectors/post_step_metadata.py` (deferred to n=3; track for the third occurrence).

### Routine-maintenance candidates

- [ ] **C1 (highest priority)**: AIAT 4-test cluster — fixture fix (7 flights deep).
- [ ] **C2 (tied highest priority)**: Chronic UI tests — update to match prod (8 flights deep).
- [ ] Plugin-author guide for connectors (F3+F4 carryover).
- [ ] Unify `_xxxValues` getter pattern (F3 carryover).
- [ ] Lift axis vocabulary to `App.studio.connectorAxes` constant (F3 carryover).
- [ ] Remove `_RegistryEntry.account_type=""` backwards-compat default (F3 carryover).
- [ ] L4 `prior_cache` force-interleaving test (F3 carryover).
- [ ] Shared `tests/browser/fixtures/discoverable_entities.py` (F4 carryover; can fold with F6 fixtures lift).
- [ ] Container playwright install one-off (F4 carryover).
- [ ] Studio event-bus lift (F5 carryover; n=2 trigger met).
- [ ] 3-column field-row primitive codification (F5 carryover; D6).
- [ ] Python+JS directive-defaults cross-check test (F5 carryover).
