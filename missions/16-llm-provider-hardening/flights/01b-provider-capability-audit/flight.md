# Flight: Provider Capability Audit

**Status**: landed
**Mission**: [LLM Provider Layer Hardening](../../mission.md)

## Contributing to Criteria

> This is a **read-only recon flight** — the same shape as Flight 1. It produces a
> documentation deliverable (a capability matrix + a ratified gap backlog), not
> code. It **closes one success criterion outright** and **sets up two others** by
> producing the backlog they later act on.

- [x] (closes) **Per-SDK capability audit exists** enumerating, for Anthropic /
      OpenAI / Ollama / OpenRouter, the capabilities the official SDK exposes vs.
      what the `LLMProvider` layer currently wires through — yielding a prioritized
      gap backlog. *(Consolidated matrix + ratified backlog in `flight-log.md`.)*
- [ ] (sets up) Each prioritized capability gap is either implemented or explicitly
      deferred — *this flight produces the backlog that downstream capability
      flights act on; it does not implement any gap.*
- [ ] (trivially preserved) No agent framework added; contract + provider-shape
      portability preserved — *read-only audit touches no code, so the boundary
      holds by construction; the audit records each gap's expected blast radius
      against this boundary.*

---

## Pre-Flight

### Objective

Enumerate, per official SDK (Anthropic, OpenAI, Ollama, OpenRouter), the
capabilities the SDK exposes versus what `the_one/llm/` actually wires through the
`LLMProvider` contract — across the full mission capability list (extended
thinking, prompt caching, structured outputs / JSON mode, vision/multimodal,
reasoning-effort controls, document inputs, parallel tool calls, stop sequences,
streaming events, token counting) plus anything else each SDK surfaces. Classify
every gap by **where the work lands** (contract change vs. adapter-only) and by
expected effort/risk, propose a priority for each, and have the operator ratify.
Output: a cross-provider capability matrix and a prioritized capability-gap
backlog, recorded in this flight's log, that drives the capability flights to
come. No production code changes — the deliverable is findings and a ratified
backlog.

### Open Questions

- [x] ~~Where does the deliverable live?~~ → **Flight log section** (DD1).
- [x] ~~How wide is the enumeration?~~ → **Full mission capability list + per-SDK
      catch-all** (DD2).
- [x] ~~Does the audit propose priority, or only enumerate?~~ → **Propose priority +
      rough effort/risk; operator ratifies** (DD3).
- [ ] **Does this flight resolve the mission's standing open questions, or only
      inform them?** The audit *feeds* all four still-open mission OQs — (a) Ollama
      official-SDK-vs-`httpx`, (b) model-catalog sourcing, (c) reasoning-beyond-
      Anthropic scope, and (d) thinking representation — by surfacing the SDK
      evidence each needs; but each is *decided* by the flight that owns it, not
      here. *(Resolve during the synthesis leg: mark each of these four OQs as
      "answerable-now" or "deferred-to-owning-flight" with evidence.)*

### Design Decisions

**DD1 — Deliverable lives in the flight log, not a standalone doc.**
- Choice: Record the capability matrix and the ratified gap backlog as a section
  in this flight's `flight-log.md` (matching how Flight 1 kept its findings).
- Rationale: Recon output, not a durable product doc; keeping it with the flight
  preserves the chain of evidence and the mission flight-list already points here.
- Trade-off: Less discoverable than a top-level `docs/` reference. Mitigated by the
  mission's flight list linking to this flight; if the backlog proves long-lived,
  a later flight can promote it to `docs/`.

**DD2 — Audit the full mission capability list, plus a per-SDK catch-all.**
- Choice: Enumerate every capability the mission names — extended thinking, prompt
  caching, structured outputs / JSON mode, vision/multimodal, reasoning-effort
  controls, document inputs, parallel tool calls, stop sequences, streaming events,
  token counting — and add a "what else does this SDK surface that we don't wire?"
  pass per provider.
- Rationale: The mission's goal is *preemptive completeness*; narrowing to
  already-wanted capabilities risks missing gaps the operator would want surfaced.
- Trade-off: More recon effort per provider. Bounded by the fixed capability list
  and the read-only scope.

**DD3 — Audit proposes priority + rough effort/risk; operator ratifies.**
- Choice: For each gap, the audit assigns a suggested priority (High / Med / Low),
  a rough effort (S/M/L), a risk note, and a one-line rationale. A closing
  ratification step presents the backlog to the operator to confirm or override.
- Rationale: Produces a ready-to-act, prioritized backlog rather than a raw list.
- Trade-off: Proposed priorities may need operator correction — the ratification
  step exists precisely to catch that.

**DD4 — Three-axis audit rubric: SDK-exposed × contract-representable × wired-through.**
- Choice: Each capability is scored on three axes per provider — does the **SDK
  expose** it, can the **`LLMProvider` contract represent** it today
  (`Message`/`ToolCall`/`ToolResult`/`StreamChunk`/`TokenUsage` in `base.py`), and
  does the **adapter wire** it. A gap is classified by where the fix lands:
  *contract-level* (needs a `base.py`/protocol/persistence change — e.g. extended
  thinking needs a thinking field before any adapter can carry it) vs.
  *adapter-only* (the contract already supports it, one provider just doesn't wire
  it).
- Rationale: Sequences the downstream flights correctly — contract-level gaps are
  shared prerequisites; adapter-only gaps are independent and parallelizable. It
  also ties each gap to the mission's "contract + portability preserved" boundary.
- Trade-off: A bit more analysis per cell than a flat exposed/wired matrix.

**DD5 — Determine SDK surface from installed SDK source + official docs, not memory.**
- Choice: Read the SDK surface from the packages installed in the project **`.venv`**
  (`anthropic ~0.97.0`, `openai ~2.33.0` — read the exact version at audit time; the
  pins are floors `>=0.40` / `>=2.16`) and the official SDK docs/changelogs; cite a
  source location (SDK symbol/path or doc URL) for every
  "SDK-exposed" claim so the backlog is auditable. The **`ollama` SDK is not
  installed** — audit Ollama on two tracks: (a) the current raw-`httpx`
  OpenAI-compatible path (`ollama_provider.py` + `ollama_api.py`), and (b) what the
  official `ollama` SDK *would* add (from its docs), feeding the mission's
  Ollama-SDK open question.
- Rationale: Capability claims must be grounded, not recalled; SDK surfaces drift
  and the audit's whole value is accuracy.
- Trade-off: Reading SDK source/docs is slower than asserting from memory — which
  is the point.

**DD6 — Mock is excluded from the SDK capability audit.**
- Choice: `mock.py` is dev-only and wraps no SDK, so it is out of scope for the
  capability matrix. It is noted only where the later cross-provider conformance
  suite (Flight 4) needs it to stand in for a provider.
- Rationale: There is no SDK surface to audit against.
- Trade-off: None — Mock's role is a Flight 4 concern, recorded as a pointer.

### Prerequisites

- [x] Anthropic + OpenAI SDKs importable from the project `.venv` for source reading
      (`anthropic 0.97.0`, `openai 2.33.0` confirmed in `.venv`, 2026-06-17 — this is
      the authoritative env where the-one is installed; a stray user-site install
      carries older versions and must not be the audit source).
- [ ] Official-docs access for SDK surfaces that aren't fully discoverable from
      installed source — including the **`ollama` SDK**, which is *not installed*
      (DD5 track b reads its docs, not local source).
- [x] **No live API keys required.** The audit reads SDK source/docs and our
      adapters; it makes no live API calls. (This keeps the flight hermetic and
      removes the credential-location problem Flight 1 hit.) Caveat: the OpenRouter
      `/models` (`supported_parameters`) and Ollama `/api/show` surfaces, *if probed
      live* rather than read from docs, need only network reachability — still no
      credentials.
- Flight 1's findings are a **rubric-leg input, not a pre-flight blocker** — read
  the landed recon flight-log during `audit-rubric` so the matrix cross-references
  #122/#105 (already promoted into the mission's Known Issues) rather than
  re-deriving them.

### Pre-Flight Checklist
- [x] All open questions resolved (the one remaining is a synthesis-leg deliverable,
      not a blocker)
- [x] Design decisions documented
- [x] Prerequisites verified (live-key-free; SDKs readable)
- [x] Validation approach defined (see Verification)
- [x] Legs defined (six legs designed + landed)

---

## In-Flight

### Technical Approach

Read-only, evidence-first. Establish the audit rubric once (the capability list ×
the three axes of DD4), then walk each provider's adapter against its SDK surface,
filling one row per capability with a source citation. Anthropic and OpenAI read
from installed SDK source; Ollama reads the raw-`httpx` path plus the official-SDK
docs (DD5); OpenRouter is a thin `OpenAIProvider` subclass, so its audit is "what
does the subclass add/override or lose vs. OpenAI, and what does the OpenRouter
`/models` surface expose." Synthesis collapses the four provider audits into one
cross-provider matrix, classifies each gap (contract-level vs. adapter-only),
attaches proposed priority + effort/risk, and is presented to the operator for
ratification. Cross-reference the two confirmed bugs (#122 Anthropic schema, #105
Ollama text-form tool calls) so the backlog shows how the planned bug-fix flights
(F2, F3) and the capability gaps relate.

### Checkpoints
- [ ] Audit rubric fixed (capability list × three axes; matrix template in the log)
- [ ] Anthropic provider audited with citations
- [ ] OpenAI provider audited with citations
- [ ] Ollama audited on both tracks (raw `httpx` + official-SDK delta)
- [ ] OpenRouter audited (delta vs. OpenAI subclass)
- [ ] Cross-provider matrix assembled; gaps classified (contract vs. adapter)
- [ ] Each gap carries proposed priority + effort/risk + rationale
- [ ] Operator ratifies the backlog (priorities confirmed/overridden)

### Adaptation Criteria

**Divert if**:
- A capability turns out to require touching the agent loop / registry / sandbox to
  even represent — that violates the mission's scope boundary and is a finding to
  escalate, not silently fold in.
- The audit uncovers a *correctness* bug (not a capability gap) in an adapter — log
  it as a new known issue and route to a bug-fix flight rather than the capability
  backlog.

**Acceptable variations**:
- Merging or splitting provider legs (e.g. folding OpenRouter into the OpenAI leg as
  a delta section) as long as all four providers are covered.
- Adding capability rows beyond the mission list when an SDK surfaces something
  notable (that is what the DD2 catch-all is for).

### Legs

> **Note:** Tentative suggestions, not commitments. Legs are planned and created one
> at a time via `/leg` as the flight progresses.

- [x] `audit-rubric` - Fix the capability list and the three-axis rubric (DD4);
      record the **contract surface inventory once** (the exact fields of
      `Message`/`ToolCall`/`ToolResult`/`StreamChunk`/`TokenUsage` in `base.py`) as
      the frozen reference the "contract-representable" axis is scored against; lay
      down the matrix template + citation convention in the flight log; read Flight
      1's findings to seed the #122/#105 cross-references.
- [x] `anthropic-audit` - Audit `anthropic_provider.py` against the installed
      `anthropic` SDK surface; one cited row per capability.
- [x] `openai-audit` - Audit `openai_provider.py` against the installed `openai`
      SDK surface; one cited row per capability.
- [x] `ollama-audit` - Audit the raw-`httpx` path (`ollama_provider.py` +
      `ollama_api.py`) and the official-`ollama`-SDK delta (docs; SDK not installed).
- [x] `openrouter-audit` - Audit `openrouter_provider.py` as a delta vs. OpenAI
      (what the subclass adds/overrides) plus the OpenRouter `/models` surface.
- [x] `synthesis-and-ratification` - Collapse into the cross-provider matrix,
      classify each gap (contract-level vs. adapter-only) and, **for each
      contract-level gap, name the specific contract change needed** (e.g. "thinking
      → `Message` thinking field + persistence-codec round-trip"); attach proposed
      priority + effort/risk; route gaps that are owned elsewhere to their flight
      (model-catalog/context-window sourcing → Flight 5; #122 → F2; #105 → F3)
      rather than re-deriving them; mark each mission open question this audit
      touches answerable-now vs. deferred-to-owning-flight with evidence; present to
      the operator and record ratification as a **timestamped block** (confirmed /
      overrode, per gap) so the Post-Flight checkbox is verifiable from the log
      alone.

---

## Post-Flight

### Completion Checklist
- [x] All four providers audited across the full capability list with citations
- [x] Cross-provider matrix + classified, prioritized gap backlog recorded in the
      flight log
- [x] Operator has ratified the backlog *(timestamped block, 2026-06-17)*
- [x] Mission's "Per-SDK capability audit exists" criterion checked off
- [x] Mission flight list updated (1B marked landed; capability flights to be spawned
      from the ratified backlog — A1 extended thinking sequenced first, after F2/F3)
- [x] Each mission open question this audit touches marked answerable-now or
      deferred-to-owning-flight with evidence
- [ ] Flight debrief (separate `/flight-debrief` step; transitions flight → completed)

### Verification

Confirm the flight log contains: (1) a cross-provider capability matrix covering
Anthropic / OpenAI / Ollama / OpenRouter across the full mission capability list,
every "SDK-exposed" cell carrying a source citation; (2) each gap classified as
contract-level or adapter-only per DD4; (3) each gap carrying a proposed priority,
rough effort, and risk note; and (4) an operator ratification record (priorities
confirmed or overridden). No behavior test applies — the deliverable is a
documentation artifact with no real-environment behavior to observe; correctness is
verified by the citations being checkable against SDK source/docs and the matrix
being complete across the provider × capability grid.
