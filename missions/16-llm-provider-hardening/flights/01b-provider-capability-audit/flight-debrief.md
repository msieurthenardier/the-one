# Flight Debrief: Provider Capability Audit

**Date**: 2026-06-17
**Flight**: [Provider Capability Audit](flight.md)
**Status**: landed
**Duration**: 2026-06-17 (single session)
**Legs Completed**: 6 of 6

## Outcome Assessment

### Objectives Achieved

Fully achieved. The flight produced a consolidated cross-provider capability matrix
(10 named capabilities + per-SDK catch-alls × Anthropic / OpenAI / Ollama /
OpenRouter), each capability scored on the three-axis rubric (SDK-exposed ×
contract-representable × wired-through) and classified contract-level vs.
adapter-only, plus an operator-ratified, prioritized gap backlog. Deliverable lives
in `flight-log.md` (DD1). **Zero source files changed** — verified at commit level
(landing commit `757f656` touched only `missions/` artifacts), so the read-only
guarantee holds by construction and the flight carries no regression risk.

### Mission Criteria Advanced

- **Closed outright**: *"Per-SDK capability audit exists … yielding a prioritized
  gap backlog."* Checked off in the mission.
- **Set up** (not closed): *"Each prioritized capability gap is either implemented
  or explicitly deferred"* — this flight produced the backlog those downstream
  flights act on.
- **Trivially preserved**: the no-framework / contract-portability boundary (a
  read-only audit touches no code).

The audit also disposed of all four still-open mission open questions
(answerable-now vs. deferred-to-owning-flight) with evidence.

## What Went Well

- **The three-axis rubric (DD4) is the standout.** Splitting each capability into
  SDK-exposed / contract-representable / wired-through made the matrix legible and
  *actionable*: the gap classification (contract-level vs. adapter-only) falls out
  of the scoring rather than being a separate judgment. All four provider audits
  came back genuinely comparable — same rows, same axis semantics, same gap-class
  vocabulary — which is what let the synthesis leg consolidate mechanically instead
  of re-adjudicating.
- **"Freeze the contract inventory once" (leg 01) is the load-bearing decision.**
  Scoring the contract-representable axis against a single frozen `base.py`/`codec.py`
  reference (not re-read per provider) is the mechanism that produced consistency;
  four parallel agents each reading `base.py` independently would have drifted on
  what "representable" means.
- **Parallel-own-artifact leg structure worked cleanly.** Legs 02–05 ran
  concurrently, each writing its matrix to its own leg file and touching the shared
  log only via a one-line Session-Notes append; leg 06 consolidated. The one
  anticipated benign Session-Notes append race resolved by re-read/re-append with no
  matrix contention.
- **The CL vs. CL+codec refinement prevented under-scoping.** Distinguishing
  request-param-only changes (A4 — cheap-per-capability) from durable-field changes
  that need a persistence round-trip (A1/A3 — codec back-compat) is the real
  effort/risk discriminator; collapsing them to one "contract-level" bucket would
  have hidden A2's true blast radius.
- **Hermetic-audit prerequisite held.** "No live API keys" was correct — every
  SDK-exposed verdict is sourced from installed `.venv` source or official docs; the
  only live-dependent cells (Ollama `/api/show` payloads) were tagged
  `[live-unverified]` rather than blocked or faked.
- **Citations are accurate.** Independent spot-checks (Developer + Architect +
  end-of-flight Reviewer) confirmed the contract citations, adapter wiring lines,
  codec pointers, and SDK symbols all resolve against real code / the installed
  `.venv` SDKs (anthropic 0.97.0, openai 2.33.0).

## What Could Be Improved

### Process
- **Version-pinning was the one real miss.** The SDK version pins started stale
  (`anthropic 0.79.0` / `openai 2.32.0` from a stray user-site install) and were
  only caught at the shared design review as a HIGH issue, costing a fix cycle. The
  audit's entire value is citation accuracy, so a wrong SDK source would have
  poisoned every SDK-exposed cell. The durable fix is already installed ("read the
  exact installed version from `.venv`; the pin is a floor") — but the *lesson* is
  that pinning a version into a spec was the wrong instinct from the start.
- **Synthesis leg (06) had no dedicated design-review spawn.** A deliberate,
  logged Flight-Director call (it mechanically consolidates four already-reviewed
  audits; its real gates are operator ratification + the end-of-flight review). It
  held up here, but it's worth surfacing that the consolidated matrix's internal
  consistency rested on the final reviewer pass alone.

### Technical
- **Test suite not run this flight** — no `the-one` container/image present in this
  environment, and zero source changed makes suite metrics non-attributable anyway.
  A baseline exists for downstream comparison (from the mission-12 maintenance
  debrief: full in-container suite ~**2935 passed / 4 skipped / 538 deselected,
  ~290s**). Capability flights that DO touch source should run against it.
- **Standing benign aiosqlite teardown warning** keeps re-litigating across
  debriefs (carry-forward from mission-12, not introduced here) — worth a
  `filterwarnings` entry so future capability-flight debriefs stop spending
  attention on it.

### Documentation
- **DD1's flight-log-as-deliverable is "stale by success."** The matrix + backlog
  are clearly long-lived — A1/A2/A4 and the OQ dispositions will be cited by every
  downstream capability flight. DD1's own trade-off note ("promote to `docs/` if it
  proves long-lived") has effectively already triggered. Recommend promoting the
  matrix/backlog to a durable `docs/` reference so consumers cite a stable doc, not
  a landed flight's log.
- **`the_one/agents.md → provider-shape-portability`** documents the
  `content`-is-`str` invariant as load-bearing — exactly what A2 will relax. The A2
  flight must carry a doc-update gate on that section.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Per-provider audits write to own leg artifacts (not the shared flight log); leg 06 consolidates | Four legs run in parallel; avoids a write-race on `flight-log.md` | **Yes** — default shape for parallel read-only fan-out legs |
| Four provider-leg design reviews batched into one shared pass | Identical structural template; one review caught the stale-version HIGH issue across all legs + DD5 at once | **Yes** — batch design review when legs share a template |
| Synthesis leg got no dedicated design review | Mechanical consolidation of already-reviewed audits; gated by operator ratification + end-of-flight review | Case-by-case — fine for read-only consolidation, log the call |
| SDK version pins replaced with "read installed `.venv` version at audit time" | Pinned versions drift against the actual interpreter; audit value is citation accuracy | **Yes** — default for any source-read audit DD |

## Key Learnings

- **The bottleneck is the contract, not the adapters.** The `LLMProvider` contract
  carries only `messages/tools/temperature/max_tokens` and `Message.content` is a
  `str`-only *assert*, so most capabilities are blocked at the contract before any
  adapter can wire them. The highest-leverage work is shared contract-level enablers
  that unblock multiple providers at once (A1 thinking, A2 content-widening, A4
  request-params) — not per-adapter wiring. This reframing is what made the backlog
  sequenceable.
- **A1 (extended thinking, the ratified first capability flight) is CL+codec.**
  Its capture side is de-risked (Flight 1 confirmed `get_final_message()` carries
  signed `ThinkingBlock`s), so the residual work is a typed `Message` field + a
  `db/codec.py` round-trip following the `peer_name`/`channel_id` emit-when-non-None
  / `d.get()` back-compat pattern. **Codec back-compat (old persisted rows still
  decode) is A1's primary risk, not the adapter parse.** Replay is full only on
  Anthropic; OpenAI Chat surfaces reasoning as a token *count* only, Ollama replay
  needs the native `/api/chat` path — A1 must scope cross-provider replay honestly.
- **A1 sets the codec precedent** that A3 (cache fields) and A2 (content) will
  reuse — treat its codec implementation as establishing the pattern.
- **A2 is the blast-radius watch-item.** Relaxing the `content` assert
  (`base.py:135-137`) touches every adapter's `_to_api_message` content projection +
  the codec; relaxing it without updating each projection would silently
  mis-serialize. A per-adapter content-projection inventory is an A2 prerequisite,
  not a surprise to inherit.
- **Reusable recon patterns** (worth codifying for future audit flights): the
  three-axis rubric; freeze-the-shared-reference-once-in-leg-01; parallel-own-artifact
  legs + a consolidation leg; CL-vs-CL+codec gap distinction; cite-the-installed-
  symbol-and-record-the-version (never pin versions in a spec).

## Recommendations

1. **Promote the capability matrix + gap backlog to a durable `docs/` reference**
   (e.g. `docs/llm-provider-capability-matrix.md`) before A1 starts consuming it, so
   downstream capability flights cite a stable doc rather than a landed flight's log.
   Revisits DD1 in light of the deliverable's proven longevity.
2. **Scope the A1 (extended thinking) flight as contract + codec + adapter**, with a
   first-class codec-back-compat acceptance criterion (old rows decode unchanged) and
   an explicit "Anthropic full, OpenAI/Ollama partial" replay scope. Plan B2 (Ollama
   thinking-delta streaming) as an A1 follow-on, and sequence B4 (OpenRouter
   `supported_parameters` gating) after A4, never before.
3. **Make the A2 flight carry two gates up front**: a per-adapter content-projection
   inventory (before relaxing the assert) and a required update to
   `the_one/agents.md → provider-shape-portability` (which documents the str-only
   invariant A2 changes).
4. **Adopt "cite the installed symbol + record the version read" as the default**
   for any future source-read audit DD — don't pin versions that drift against the
   interpreter.
5. **Plan test strategy now**: unit tests for codec round-trip back-compat (A1/A3)
   and per-adapter content projection (A2); reserve live behavior tests for
   extended-thinking emit+replay, vision/document round-trips, and the #122/#105
   fixes (real-model behaviors mocks won't catch). The Flight 4 conformance suite
   uses `mock.py` for contract-shape assertions per DD6.

## Action Items
- [ ] Promote matrix + backlog to a `docs/` reference before A1 begins (Recommendation 1)
- [ ] Proceed to **Flight 2 (#122 Anthropic `input_schema`)** — the confirmed bug, HIGH priority — then Flight 3 (#105), then A1 as the first capability flight
- [ ] When planning A1: codec-back-compat acceptance criterion + partial-replay scope; B2 as follow-on; B4 after A4
- [ ] When planning A2: per-adapter content-projection inventory + `agents.md` doc-update gate as prerequisites
- [ ] Standardize the recon patterns (three-axis rubric, frozen reference leg, parallel-own-artifact legs, cite-don't-pin-versions) — consider folding into the flight/leg methodology guidance
- [ ] Consider a `filterwarnings` entry for the standing benign aiosqlite teardown warning (carry-forward from mission-12)
