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
