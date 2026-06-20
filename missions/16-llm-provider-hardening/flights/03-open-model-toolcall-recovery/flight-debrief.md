# Flight Debrief: Open-Model Tool-Use Robustness — Text-Form Tool-Call Recovery (#105)

**Date**: 2026-06-19
**Flight**: [Open-Model Tool-Use Robustness (#105)](flight.md)
**Status**: landed
**Duration**: 2026-06-18 (planning) → 2026-06-19 (landed); execution ~1 day
**Legs Completed**: 9 of 9 planned-or-added (5 original + 4 added mid-flight); optional `uat-and-alignment` HAT not run
**Crew**: Developer (debrief interview + test metrics) + Architect (design review); human interview skipped (flight log comprehensive; all operator decisions captured via in-run AskUserQuestion + flight-log Decisions)

## Outcome Assessment

### Objectives Achieved

The flight's objective — make a non-tool-capable open model (gemma3:4b via Ollama,
`supports_tools()=False`) reliably **execute** tool calls instead of printing them as loose text — was
**achieved end-to-end**, but via a materially larger solution than planned. The behavior test
`gemma-tool-use-recovery` passes **5/5 checkpoints** (run `2026-06-19-04-26-15`): a real gemma turn
emits a tool call, it is recovered + dispatched + executed (marker round-trips), no raw fence leaks,
ordinary questions dispatch no tool, and the turn ends with a coherent non-empty answer.

The delivered solution is a three-layer pipeline: **(1)** a pure recovery kernel (`_toolcall_recovery.py`)
parsing loose tool-call text; **(2)** a direct-tool-protocol the agent injects for degraded models
(tool catalog + one pinned `tool_code` format, with the contradictory `search_tools` discovery
suppressed); **(3)** a dispatch-side redundant-call backstop that caps the model's loop with a
deterministic closing. Plus an orthogonal **Docker-removal diversion** (the stale deployment scaffold
the flight surfaced).

### Mission Criteria Advanced

- ✅ **"A tool-using conversation with Gemma via Ollama reliably executes tool calls, including loose
  text/JSON format"** — met at the *execution* level (the headline #105 criterion). Caveat carried
  forward: answer *composition* is backstopped (system-synthesized closing), not native model prose —
  a gemma3:4b capability floor (see Key Learnings).
- ✅ **"No agent framework added; LLMProvider contract + provider-shape-portability preserved"** — held.
- ⚠️ **"The agent loop, tool registry, MCP integration, and sandbox are untouched"** (mission Outcome,
  `mission.md`) — **now false.** The durable fix required agent-layer changes (legs 08–09). Operator-
  authorized and annotated at the mission header, but the mission **Outcome section still asserts the
  old boundary** and self-contradicts the header — flagged for the mission debrief to reconcile.

## What Went Well

- **Behavior-test-as-acceptance-gate was the flight's biggest win.** It is the *only* mechanism that
  caught the falsified core premise. Hermetic units (19+ kernel tests, all green) and the directed
  live test (leg 04, passed) both gave **false confidence** — the live test actively *masked* the bug
  by forcing the `tool` fence label via a directive prompt. The Witnessed behavior test, non-directive
  against the real model, surfaced every gap across five runs; the Validator escalated *strategy*
  ("stop patching recognizers; go to the dispatch layer"), not just verdicts.
- **The pure-leaf-kernel discipline paid off under scope change.** `_toolcall_recovery.py` stayed
  stdlib-only with no `the_one` imports; adding `tool_code` (leg 07) was a one-line set change, and the
  schema-aware binding went to the tools layer rather than polluting the kernel.
- **Disciplined, recorded boundary crossings.** Each agent-layer expansion (legs 07→08→09) was
  deliberate, operator-authorized, narrowly scoped, and recorded with its narrowing ("tool exposure
  only," "not iteration/auth-pause logic," "degraded branch only"). The capable path stayed
  byte-identical and the auth-pause flow genuinely untouched (verified: the executed-map records only
  after the `_deferred_tool_calls` guard).
- **DD5's live-probe-resolves-open-question pattern** (borrowed from Flight 2) worked cleanly: name the
  open question, pre-authorize the adaptation, resolve empirically, pin the result with a hermetic test.
- **Leg specs were uniformly high quality** — explicit acceptance criteria, line-cited insertion
  points, named tests, pre-litigated design forks; the reactive legs were *denser* than the planned
  ones and each cited the behavior-test run that triggered it.

## What Could Be Improved

### Process

- **The core reliability premise was validated against a fixture, not reality.** Legs 01–04 built and
  green-tested against a *single captured* gemma emission (` ```tool ` + keyword args); real gemma3:4b
  differs on every axis (`tool_code` fence, positional args, a fresh serialization nearly every turn).
  A **format-variability spike** at planning — run the tool-eliciting prompt N times un-directed and
  tabulate the emitted shapes — would almost certainly have shown the improvisation and steered the
  flight to the direct-tool-protocol from the start. Estimated cost of the miss: ~4 legs of rework.
- **A directed live test gives false capability confidence.** Leg 04's `@pytest.mark.live` test tells
  the model the exact format, so it validates the *mechanism* against cooperative output, not the
  *capability*. It passed while the real path was broken.
- **Environment-hygiene gap derailed leg 05.** The stale Docker scaffold caused the Flight Director to
  twice mis-infer a containerized runtime (it runs host-native), costing a whole diversion leg before
  the behavior test could run. A preflight environment check would have caught it.
- **Leg status vs acceptance-box discrepancy.** Legs 05/07/08/09 are marked `Status: completed` but
  their end-to-end `/behavior-test → PASS` acceptance boxes are left unchecked (leg 05 in particular is
  `completed` with zero boxes checked — because the test it owned *failed*, which spawned 07–09). The
  terminal gate **was** satisfied (run 5, 5/5) but the leg artifacts were never back-annotated;
  "completed" was used to mean "ran and learned." Final-gate verification lives only in the run logs.

### Technical

- **`DEGRADED_BASE_PROMPT` is a ~90% verbatim copy of `BASE_PROMPT`** (`config.py`) — a real drift
  hazard: an edit to the shared guidance won't propagate to the degraded prompt, and nothing tests for
  equivalence-minus-discovery-block. **Highest-value cleanup:** derive it by removing the discovery
  section from `BASE_PROMPT`, or factor the shared body into one constant.
- **Latent test-selection bug, CONFIRMED:** `make test-unit` passes `-m 'not browser and not live and
  not pixel'`, which *replaces* (last-`-m`-wins) the pyproject `addopts` deselection of
  `requires_bwrap`/`discord_hat`. So `make test-unit` silently runs the 11 `requires_bwrap` pty tests;
  they pass **only because this host has `/bin/bwrap`** — on a bwrap-less host or CI, `make test-unit`
  would start failing. Not a runtime defect; a test-selection correctness defect.
- **Intentional `POSITIONAL_ARGS_KEY` duplication** across `_toolcall_recovery.py` and `tools/base.py`
  (keeps the kernel a leaf; guarded by an agreement test) — acceptable debt, but the implicit contract
  should be documented so it isn't "fixed" into a cross-boundary import later.
- **The non-tool-model support is a complete pipeline spread across 5 sites** (`llm/_toolcall_recovery`,
  `tools/base`, `agent/degraded_tools`, `agent/config`, three branches in `agent/core._run_iterations`)
  with no single module/doc owning the concept. Coherent now; risks becoming a bolt-on. Deserves a
  name + a one-page design note (and ideally a light consolidation pass).
- **The deterministic-closing backstop quietly redefines "the agent answered."** It substitutes
  templated system prose for model composition. The right robustness floor for a 4B model, but the
  "system-synthesized, not model prose" semantics should be a tracked design invariant, not just a
  run-log line — so a future change can't silently assert "the model produced the final answer."

### Documentation

- The Post-Flight doc items landed: the stale "single-shot/single LLM iteration" wording in `core.py`
  + `agents.md` was corrected to the multi-iterating degraded path; `agents.md` "Capability gate"
  section gained the degraded-protocol + backstop notes. (Spot-check recommended that the `agents.md`
  edits actually landed as the flight log states.)
- Missing: a named design note for the "non-tool-capable model support" subsystem; a documented note
  on the intentional `POSITIONAL_ARGS_KEY` duplication.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Scope expanded 5 legs → 9 (added 07/08/09) | Behavior test falsified the recognizer-only premise; durable fix needed the agent layer | No — but standardize the *spike* that would prevent it |
| Mission `the_one/llm/`-only boundary breached into `the_one/agent/` | Reliable non-tool support is impossible in the provider alone (no tool catalog on the degraded path) | Yes — revise the mission scope; record the agent layer as in-scope |
| Full Docker removal folded in mid-flight | Stale scaffold misled execution; operator directed the rip-out | No (one-time cleanup) — but add a preflight env check |
| `make test-unit` host-native (crew prompt said `docker exec`) | the-one runs host-native; docker unavailable | Yes — already fixed in the project crew file (leg 06) |
| Behavior-test observable amended (host-canary → tool-result marker) | The shell tool sandboxes (ephemeral bwrap box); a host canary is unobservable | Yes — observe the result via the response, not a host file, when the tool sandboxes |
| CP4 closing is system-synthesized, not model prose | gemma3:4b can't compose a closing answer from a tool result (capability floor) | Accepted as a known limitation; constrained-decode is the candidate follow-up |

## Key Learnings

1. **A non-deterministic model's output format is a distribution, not a contract.** Reliability comes
   from *constraining/instructing the input* (the direct tool protocol), not from *recognizing the
   output* (recognizer whack-a-mole). DD6 was correct about the dispatch mechanism but rode on a
   wrong unstated premise — that recovery input is reliable.
2. **Behavior tests are load-bearing — not supplementary — for AI-agent behavior against a real model.**
   They caught what 19+ green unit tests and a passing (directed) live test could not. A live test that
   hands the model the answer validates the mechanism, not the capability.
3. **Small/local models have sub-step capability floors.** gemma3:4b can *decide* to call a tool and
   *invoke* it, but cannot reliably *compose a closing answer from the result*. Gating (a pre-action
   decision) is promptable; synthesis (a post-action composition) is not — the asymmetric prompt
   efficacy seen across runs 3→4. Expect this pattern in future capability flights.
4. **The reusable asset: a "non-tool-capable model support" pattern** — recover loose calls → instruct
   with an explicit catalog + pinned format (suppress contradictory discovery) → dispatch-side backstop
   for loops. Reusable across any OpenAI-compatible local backend (LM Studio, vLLM, llama.cpp).
5. **Test metrics:** `make test-unit` → **3302 passed / 18 skipped / 541 deselected / 0 failed**,
   ~385s (this flight added +64 hermetic tests; trajectory 3238→3302 across legs). vs Flight 2's
   3232/10/592 ~313s — +70 passing, longer partly because the `-m` override now runs 11 bwrap tests.

## Recommendations

1. **(Flight 4+ candidate) Evaluate constrained decode for non-tool models — as a deliberate decision,
   not an automatic yes.** Ollama's native `/api/chat` `format`/grammar could force the tool-call shape
   (retiring recognizer fragility) but **cannot be applied unconditionally** (it would break ordinary
   prose turns / CP5). Worth a *spike* on per-turn conditional grammar; do not assume it dominates the
   current prompt-based approach, which satisfies both CP2 and CP5.
2. **Fix the `requires_bwrap`/`make test-unit` selection bug.** Make the Makefile `-m` expression
   *additive* to the deselections (`… and not requires_bwrap and not discord_hat`) so host-only tests
   aren't silently run. Low-effort; prevents a bwrap-less-host/CI surprise. Good pre-flight or
   end-of-mission maintenance item.
3. **Refactor `DEGRADED_BASE_PROMPT` to derive from `BASE_PROMPT`** (strip the discovery section) to
   kill the verbatim-copy drift hazard. Highest-value, low-risk cleanup.
4. **Name + document the "non-tool-capable model support" subsystem** (a one-page design note covering
   the recover→instruct→backstop pipeline, the intentional `POSITIONAL_ARGS_KEY` duplication, and the
   system-synthesized-closing invariant), and consider a light consolidation pass.
5. **Adopt the distribution-sampling spike discipline** for any flight whose core mechanism depends on
   a non-deterministic model's output: sample N un-directed emissions at planning, not one capture.
   Pair any directive live test with a non-directive behavior test before claiming an acceptance
   criterion.

## Action Items

- [ ] Reconcile the mission **Outcome** section ("agent loop… untouched") with the recorded agent-layer
      expansion — carry into `/mission-debrief` for mission 16.
- [ ] Fix `make test-unit` marker selection so `requires_bwrap`/`discord_hat` stay deselected (Rec 2).
- [ ] Refactor `DEGRADED_BASE_PROMPT` to derive from `BASE_PROMPT` (Rec 3).
- [ ] Add a named design note for the non-tool-capable-model subsystem + document the
      `POSITIONAL_ARGS_KEY` duplication and the system-synthesized-closing invariant (Rec 4).
- [ ] Decide on a constrained-decode spike/flight for degraded-model answer composition (Rec 1).
- [ ] Add a live regression net for the degraded protocol-injection + backstop path (currently only
      the behavior test exercises legs 08/09 against a real model) — or schedule the behavior test on a
      recurring cadence.
- [ ] Back-annotate the leg-05/07/08/09 behavior-test acceptance boxes (or note in the flight log that
      final-gate verification lives in run `2026-06-19-04-26-15`).
- [ ] Split behavior-spec CP4 into a transport assertion (round-trip completes) + a synthesis-quality
      assertion (coherent closing) so the run log records exactly what's guaranteed.
- [ ] Mark PR #129 ready for review when the operator has reviewed the branch.
- [ ] Mission-control methodology note: capability flights depending on a stochastic model's output
      should require a distribution-sampling spike (Rec 5) — feed to `/mission-debrief`.

---

# Addendum — Post-Landing Reopening: Degraded Over-Routing Fix (2026-06-19)

> The original debrief above stands as the record of the first landing. This addendum covers the
> **post-landing reopening** of Flight 3, which fixed a degraded-path over-routing bug discovered live after
> the original landing. Commit `1e96d7a` on branch `flight/03-degraded-over-routing`; draft PR #132. Legs:
> 08A (aborted), 08B (skipped), 08C (completed), 08d (completed).

## What reopened the flight

A live repro found the Leg-08 degraded direct-tool-protocol made **gemma3:4b over-route**: it emitted a
`tool_code` call on essentially *every* message (a greeting → `shell(command="echo Hello there!")`, "what is
a haiku?" → `read_file(...)`), **deterministically** (`temperature=0.0`) and **worse the larger the catalog**.
Root cause: Leg 08 dumped the **full** tool catalog into the degraded system prompt every turn, **inverting
the capable path's blind-start discovery model** (capable agents start with only `search_tools` visible and
must discover tools; degraded agents were handed all 24 + the call format, which a 4B reads as "call a tool").

## Outcome of the reopening

Resolved by a **gated trial** of three mutually-exclusive approaches, with explicit accept/abandon gates and
operator decisions (including hands-on testing):

- **08A — blind-start discovery (ABORTED).** Mirrored the capable path (discovery-only, no catalog dump).
  Fixed over-routing decisively, but the blind→search→call **hop is unreliable on gemma3:4b (1/3)**: the model
  re-searches instead of selecting from results, copies the format placeholder (`name(arg="value")`) verbatim,
  and emits bare commands. Confirmed a 4B multi-step-composition floor. A search improvement made under this
  trial was salvaged (08d).
- **08B — passive recovery (SKIPPED).** The operator went straight to 08C; passive recovery against a model
  with `tool_code` training priors is the original failure mode, and offers nothing for the hop.
- **08C — chat-only (COMPLETED, shipped).** Non-tool models (`supports_tools=False`) are conversational only:
  recovery gated OFF in the Ollama provider, tool-free `CHAT_ONLY_PROMPT`, `degraded_tools.py` retired.
  LIVE-verified: over-routing gone **and** no more stalls/no-response.
- **08d — search tokenization + cap (COMPLETED).** Tokenized + capped `search_tools` matching so multi-word
  natural-language queries resolve. Kept as an **independent** robustness win for the capable path even though
  08A was abandoned.

## Test Metrics (this run)

`make test-unit` → **3365 passed / 10 skipped / 594 deselected / 0 failed**, ~306s.

| Metric | Original landing | Reopening | Delta |
|---|---|---|---|
| Passing | 3302 | 3365 | +63 |
| Skipped | 18 | 10 | −8 |
| Wall-clock | ~385s | ~306s | ~−80s |

The skip drop (18→10) and deselected rise (~541→594) are consistent with the original debrief's **Rec 2**
(the `make test-unit` `-m`-override bug that silently ran 11 `requires_bwrap` pty tests) now being fixed — the
bwrap tests are consistently deselected. Net +63 passing = +52 `test_search_tools.py` (08d) + 4 provider-layer
gate tests (08C) − 12 deleted `test_degraded_tool_prompt.py` (module retired) − 2 moot 08A discovery tests,
plus the 08A-trial additions. No flakes observed.

## What Went Well

- **The gated trial with pre-committed, quantified accept/abandon bars** was the right instrument for an
  uncertain fix on a stochastic model. The bars (over-routing: 0 concrete-tool dispatches on greeting + haiku,
  deterministic; hop: ≥2/3 action requests end-to-end) made the 1/3 abandonment clean rather than a judgment
  call, and stopped 08A from being rationalized as "close enough."
- **The recovery-gating seam was correctly placed in the provider, not the agent layer** — because parse and
  content-strip are the same step, an agent-layer gate would leave a stripped-but-empty message. Gating at the
  `_recover_into_tool_calls` call site (on `supports_tools()`, fail-open=True) lets a non-tool model's raw
  text pass through verbatim. Per-leg design review caught this *and* corrected two implementation traps
  pre-implementation (don't double-cache `supports_tools()`; the conformance §6 rows must stub
  `supports_tools()=True` or they pass only by fail-open accident; invert recovery-dispatch tests at the
  *provider* layer, not the agent-mock layer that bypasses recovery).
- **08C simplified the architecture**: the prior 5-site degraded pipeline collapsed to two coherent sites
  (provider gate + tool-free prompt); `degraded_tools.py` retired. The "non-tool model" concept now has a
  minimal, honest expression.
- **An aborted approach still produced a kept asset** (08d) — the trial surfaced a real, latent brittleness in
  the shared `search_tools` (whole-phrase substring matching) that affected the capable path too.

## What Could Be Improved — Lessons

- **★ Test-validity gap (the headline lesson): a behavior test's agent/tool configuration is part of its
  validity, not an environmental detail.** The original behavior test's CP5 ("what is a haiku?" → no tool)
  **false-passed** because the spec provisioned a **single-`shell`** agent — a knowledge question has no
  plausible tool to grab when only `shell` is offered, so the gating text *appeared* to hold. Against a
  realistic full catalog (24 tools), the same check fails. **Principle:** when a behavior-test step asserts
  model *routing/gating* behavior (whether to invoke a tool at all), the agent's `enabled_tools` must reflect
  a realistic production catalog; a restricted catalog only validates a catalog-agnostic property and must be
  justified in the spec. → Carry into `AUTHORING.md`.
- **★ Restate the original debrief's Key Learning 3.** "Gating is promptable; only synthesis isn't" holds only
  in the narrow single-tool configuration that masked the bug. Restated: **small models have sub-step
  capability floors, and prompt-based gating is catalog-sensitive, not a general capability.** A 4B can decide
  to call a tool and invoke one when prompt + catalog point the same way, but cannot gate on a semantic
  judgment ("does this need an action?") when the catalog holds many plausibly-applicable tools — catalog
  presence is itself an attractor toward tool use. Post-action composition is a second, independent floor.
  Both are non-promptable; verify empirically against a realistic config.
- **Capable-vs-degraded asymmetry is a design smell worth a standing principle.** Leg 08's instinct — "give
  the weak model everything it needs" (full catalog) — was exactly backwards; the capable path proves a model
  selects better when it must search-and-choose from a small visible set. **Default visibility posture should
  be the same for all models; if a model can't handle native discovery, reduce/gate what's visible — don't
  pre-expand it.**
- **The gated trial needs a pre-committed tuning-pass budget.** 08A required two nested tuning passes
  (tokenize, then cap) before its hop rate could be judged; each could have been mistaken for "almost there."
  The operator's "one agreed tuning pass, then decide" rule was the actual terminator. Standardize: enumerate
  the tuning knobs and a max pass count *before* implementing a stochastic-model trial leg.

## Technical Debt

- **Leg-09 redundant-call backstop is now unreachable dead code on the chat-only path** (recovery never fires
  for a non-tool model → `response.tool_calls` always empty → the degraded partition + `_synthesize_closing`
  never run). Annotated, harmless, but a maintainer must trace it to learn it's dead. Its 14 tests
  (`test_agent_redundant_backstop.py`) only exercise a mock-provider scenario with no production counterpart
  after 08C. → A small cleanup leg should remove the backstop + tests (concrete task, not just "candidate").
- **`CHAT_ONLY_PROMPT` drift.** It's a clean minimal rewrite (better than `DEGRADED_BASE_PROMPT`'s ~90% copy),
  but the persona-append paragraph is now duplicated verbatim with `BASE_PROMPT`; an edit there won't
  propagate. → Extract a shared `_PERSONA_APPEND_NOTE` constant (5-line refactor) **or** add a test asserting
  the forbidden tool sections are absent from `CHAT_ONLY_PROMPT` so the invariant self-enforces.

## Action Items (addendum)

- [ ] Mark **PR #132** ready for review after the operator reviews the branch (mirrors the original #129 item;
      #129 is merged).
- [ ] **Cleanup leg: remove the now-dead Leg-09 redundant-call backstop** (partition + `_synthesize_closing` +
      `test_agent_redundant_backstop.py`); confirm `test_agent_degraded_injection.py` still covers the degraded
      branch.
- [ ] **Guard `CHAT_ONLY_PROMPT` drift** — extract the shared persona-append note, or add an absent-tool-sections
      test.
- [ ] **Carry to `/mission-debrief`:** (a) the **mission-criterion reframe** — replace the binary "Gemma
      reliably executes tool calls" with capability-split wording: *models advertising `tools` execute reliably
      (incl. loose-text recovery); models that don't are conversational-only and never dispatch tools*;
      (b) the **behavior-test config-realism** lesson as a methodology standard; (c) the small-model
      multi-step-floor finding.
- [ ] **Update the non-tool-model design note** (original Rec 4) — the "recover→instruct→backstop" pipeline it
      called for is superseded by "recover-gated-OFF → chat-only"; `agents.md` "Capability gate" was updated in
      08C, but a one-page subsystem note should reflect the 08C architecture.
- [ ] **Close original Rec 2** (the `requires_bwrap`/`make test-unit` marker bug) — the skip/deselect deltas
      indicate it's fixed; confirm and check it off.
