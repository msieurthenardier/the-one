# Flight Debrief: Chat-loop Robustness & Control

**Date**: 2026-06-22
**Flight**: [Chat-loop Robustness & Control](flight.md)
**Status**: landed
**Duration**: 2026-06-21 (planned → 6 legs → landed, same day) + 0.2.6 follow-up (2026-06-21/22)
**Legs Completed**: 6 of 6 (5 autonomous + HAT)

## Outcome Assessment

### Objectives Achieved
The indefinite chat-loop **hang is gone**. `http_request`/`fetch_url` stream the body
with an in-loop byte cap (mirror `download_file`), a total `asyncio.wait_for` deadline,
and a narrow `audio/*|video/*|application/octet-stream` short-circuit — HAT-verified
against the exact repro URL (`stream.radioparadise.com/aac-320`: infinite hang → 0.3s
bounded). A per-tool-call timeout at `_execute_tool` bounds any stalled tool. Operators
can interrupt an in-flight turn (WS `cancel` → task cancellation, partial output kept
as `_[interrupted]_`, `cancelled` event, lock released — HAT-verified: cancel mid-turn
→ session recovered) and queue one message while a turn runs.

### Mission Criteria Advanced
- [x] "Chat turns cannot hang indefinitely on a tool call, and the operator can always
      interrupt an in-flight turn." **Met** for the hang/interrupt axes; see the size-cap
      caveat under What Could Be Improved.

### Test Metrics (debrief run)
`3492 passed / 10 skipped / 595 deselected / 0 failed`, ~340s (main @ 0.2.6).

| | F4 base | F05 debrief | F06 land | F07 land | F07 debrief (0.2.6) |
|---|---|---|---|---|---|
| Passed | 3347 | 3448 | ~3448 | 3489 | **3492** |
| Skipped | 10 | 10 | 10 | 10 | **10** |
| Deselected | 594 | 595 | 595 | 595 | **595** |
| Wall-clock | ~346s | ~324s | ~316s | — | **~340s** |

F07 added **+44 tests** (web stream/cap/media, 13 timeout, 14 cancel, +3 in the 0.2.6
follow-up). Skip count rock-stable at **10** since F3; deselected stable at 595; timing
inside the historical 296–346s band, no regression despite +44 tests. **No new flakes.**
The benign `RuntimeError: Event loop is closed` aiosqlite teardown warnings have now
ridden through F05/F06/F07 debriefs — candidate for a mission-level fix-or-accept note.

## What Went Well
- **Parallel leg execution validated by outcome.** Legs 1–3 (disjoint files —
  web.py / core.py / app.py) ran in parallel, leg 4 (frontend) serialized after leg 3's
  contract. No integration/merge surprise — the later defect was a *design* gap, not a
  parallelism gap.
- **The combined leg-design review earned its keep** — it caught leg 3's two HIGHs
  *before* implementation: no `Message.metadata` field (→ content-suffix interrupt
  marker) and the `except CancelledError` also firing on shutdown (→ best-effort
  `suppress` + re-raise). Both shipped exactly as prescribed; legs landed clean.
- **Reusable patterns worth codifying:** the `_stream_read_with_cap` (raises) vs
  `_stream_read_head_capped` (head-preserving) pair — *the right truncation direction
  depends on the consumer, not the byte budget*; the narrow `_is_media_stream_type`
  predicate with a guard-comment against re-widening to `_is_binary_content_type`; the
  per-session `_session_inflight` task map with an identity-guarded done-callback
  (handles the running+queued coexistence) alongside `_inflight_tasks` for shutdown.
- **Cancel (DD3) is the best-engineered part** — `BaseException`-hierarchy-aware
  sibling handler with a reviewer-facing comment guarding a future `except BaseException`
  refactor that would silently strand the lock.

## What Could Be Improved

### Process
- **Verification was too narrow on the input space.** Tests + HAT exercised the
  *pathological* input (infinite stream → bounded) thoroughly, but never a **large-but-
  valid page** — exactly the input the new code path now returns whole. One test —
  "fetch a 500 KB–1 MB valid HTML page, assert the returned text is context-bounded" —
  would have caught the 0.2.6 defect pre-ship, with no new apparatus. **Lesson: when a
  flight changes the size/shape of what a tool returns to the model, verify a large
  *valid* input, not only the pathological one that motivated the flight.**
- **The 0.2.6 fix-forward ran a partial test set** (web-*tool* tests only), tripping the
  `WebConfig` field-count guard in `tests/test_web_config.py` → CI red → corrected. Same
  false-green / partial-validation theme the F05 debrief raised. **Lesson: fix-forwards,
  and any schema-shape change, run the full unit suite (~340s — affordable).**
- **Artifact hygiene:** the 0.2.6 follow-up (a same-area HIGH defect within hours of
  landing) lived only in code + git (PR #138); the flight-log Deviations/Anomalies read
  "(none)". Now recorded as an Anomaly for accuracy.

### Technical
- **DD1's size-cap design had a blind spot (the headline defect).** It treated "cap the
  body" as one concept and reused `response_size_cap_bytes` (1 MB) for it. There are
  **two distinct caps**: a transport/anti-hang cap (1 MB is fine) and an **LLM-context
  cap** (1 MB ≈ 250K tokens from one tool call — obviously too large). A 631 KB valid
  page, under the streaming cap, poisoned a ~167K-token context → 1-token degenerate
  reply. Tellingly, the config's own UI labels read "1MB — default (Opus 200K
  headroom)" — the cap was *sized against model context windows* yet *used as a per-tool-
  result cap*. The 0.2.6 `tool_text_cap_bytes` (48 KB, head-preserving) is the correct
  separation; it should have been a DD1 sub-decision, not a post-landing hotfix.
- **The truncation story is now intricate** — a fetch passes three gates (streaming abort
  @1 MB → `_truncate_response` tail-cut @1 MB → `_cap_tool_text` head-cut @48 KB); the
  middle gate is now effectively dead for text. Worth a consolidation pass / gate-order
  doc comment.
- **`tool_text_cap_bytes` isn't operator-surfaced** (no `ui_hint`/`ui_choices` dropdown)
  unlike its sibling caps — an invisible knob until admin wiring catches up.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Legs 1–3 implemented in parallel (disjoint files) | Independent leaf changes; deferred-commit | Yes — for disjoint-file legs under deferred-commit |
| ONE combined leg-design review over legs 1–4 | Architect already validated designs at flight level; efficiency | Yes — when a flight-level design review already ran |
| Flight-wide review on Sonnet (not crew's Haiku) | Large multi-file deferred-commit diff | Yes — already standardized (F04/F05) |
| HAT via automated WS + direct-tool-call (not full two-agent `/behavior-test`); UI eyeballs deferred | Cost call; core behaviors are event-observable | Partial — fine for the *mechanism*, but the *input space* was too narrow (see above) |
| **0.2.6 post-landing follow-up** (separate `tool_text_cap_bytes`) | DD1 size-cap blind spot surfaced in production | **No** — this should have been designed in; it's the central lesson |

## Key Learnings
- **Missing cross-cutting principle: bounded, budgeted inputs to the LLM context.**
  Context safety today is ad-hoc and per-tool — web (`tool_text_cap_bytes`), filesystem
  (`read_size_cap_bytes`), execution (`output_cap_bytes`) — each sized independently, at
  least one against the wrong axis. There is no single governor asserting "no tool
  result / fetched page / future RAG chunk hands the model more than a sane fraction of
  its context budget," and **no conversation-level accounting** (the 631 KB page was
  per-result legal; the failure was cumulative). This wants to be a first-class concern,
  not a cap each new tool author re-derives.
- **Three defects, one theme, and they compound.** Web-tool hang (fixed), oversized-page
  context-poison (fixed), and `web_search` returning nothing (open, pulled forward) form
  one causal chain: search returns nothing → the model guesses URLs → it scrapes
  large/streaming pages → hang or poison. Fixing search reduces the pressure; cap
  discipline bounds the blast radius. They want to be designed together.
- **Verify the adjacent failure mode, not just the named one.** A flight that fixes
  failure X by changing a code path often introduces failure X′ on that same path; the
  verification must probe X′ (here: large valid input), not re-confirm X.

## Recommendations
1. **Make the next flight "agent-loop resource governance / context-budget management"**
   (the operator is already pulling `web_search` forward — fold it in here). Scope: a
   single context-budget governor every `ToolResult.content` flows through at the
   `_execute_tool` dispatch boundary (retire per-tool ad-hoc caps; derive caps from the
   *active model's* context window, which the config UI already thinks in); conversation-
   level accounting, not just per-result; extend to future RAG injection; and a reliable
   `web_search` backend (configured, not unauthenticated DDG scraping) as the upstream
   fix. Turns recurring whack-a-mole into a designed subsystem.
2. **Add a "what does the model actually receive?" verification class** to the tools/
   agent-loop checklist — assert the *size of returned text* for a large valid input, not
   just that the call terminates. (The 0.2.6 `TestToolTextCap` is the seed; generalize.)
3. **Test discipline:** fix-forwards and schema-shape changes run the full unit suite;
   consider folding the per-config field-count guards into one parametrized shape test so
   adding a field forces one obvious deliberate update.
4. **Surface `tool_text_cap_bytes` in the admin picker** (match sibling caps) and add a
   gate-order doc comment to the three-stage web truncation.
5. **Mission-level:** decide fix-or-accept on the benign aiosqlite `Event loop is closed`
   teardown warnings (carried through three debriefs now).

## Action Items
- [ ] **(Next flight)** Frame the operator's `web_search` pull-forward as a context-
      budget / resource-governance flight (Rec 1): shared LLM-input cap at `_execute_tool`
      + conversation-level accounting + reliable `web_search` backend.
- [ ] **(Mission-debrief carry)** Record the "bounded/budgeted inputs to the LLM context"
      principle as a mission-level lesson (joins the F05 packaging-survival lesson).
- [ ] Generalize the large-valid-input "returned-text size" test beyond web tools
      (`read_file`, `shell`, `python_exec`).
- [ ] Surface `tool_text_cap_bytes` in the admin UI; add the truncation gate-order doc note.
- [ ] Decide fix-or-accept on the aiosqlite teardown warnings at `/mission-debrief`.
