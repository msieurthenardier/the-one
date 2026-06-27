# Flight: Human Acceptance Testing — Provider Chat Sweep

**Status**: in-flight
**Mission**: [LLM Provider Layer Hardening & Capability Completeness](../../mission.md)

## Contributing to Criteria
This flight does not advance a single *named* provider-layer success criterion up
front. Like F07 (chat-loop robustness), it is a **quality-assurance flight** scoped
into M16's wrap-up: the operator drives real chat sessions across the in-scope
providers on the installed app to shake out defects that unit/integration tests and
behavior tests have not caught. Issues surfaced become legs and are fixed in-flight.
The sweep also serves as **empirical confidence** across the provider surface as the
mission heads toward debrief — and may surface gaps in the still-unmet criteria
(extended thinking + `ThinkingPart`, context-window sourcing). Findings of mission
scope are recorded against the mission's Known-Issues surface.

- [ ] Operator-judged: chat is reliable and pleasant across the in-scope providers
      on the installed app, with all surfaced defects either fixed in this flight or
      explicitly triaged (own follow-up flight / mission Known Issue) by mutual call.

---

## Pre-Flight

### Objective
The operator manually exercises **Chat** across **Anthropic**, **Ollama (native
`/api/chat`)**, and **OpenRouter** on the **installed app** for an extended period —
varied models, varied prompts, tool use, long histories, streaming, cancel/queue,
multi-turn. Each defect or rough edge observed is logged to the flight log and
turned into a leg (repro → fix → verify). Small issues are fixed in-flight as legs;
larger findings are triaged case-by-case as they come up (a leg here, a spun-out
follow-up flight, or a mission Known Issue). The flight lands when the operator
judges chat acceptable across the in-scope providers and the surfaced-issue list is
resolved or explicitly deferred.

### Open Questions
- [x] **Which providers?** → DD3. Anthropic, Ollama (native), OpenRouter. OpenAI
      excluded by operator choice this pass.
- [x] **Which environment?** → DD2. The installed app (real-user conditions).
- [x] **How are issues handled?** → DD1 + DD4. Accretive leg model; triage
      case-by-case.
- [ ] **Specific models per provider** — left to the operator at session time; record
      the actual model id with each finding in the flight log (model-catalog drift has
      stranded prior runs — F05/F08 lineage).

### Design Decisions

**DD1 — Accretive, issue-driven leg model**: This flight starts with **no fix legs**.
Legs are created one at a time as defects surface during HAT, named per issue
(`{NN}-{issue-slug}`), each following the normal leg lifecycle (repro → fix →
verify). The flight's leg list grows during execution; this is expected, not scope
creep.
- Rationale: HAT is exploratory — the work cannot be enumerated before the sessions
  run. F07 itself was born from exactly this kind of live provider-exercising; this
  flight formalizes that pattern.
- Trade-off: the flight has no fixed end-state at planning time; it lands on operator
  judgment rather than a pre-counted checklist.

**DD2 — Target is the installed app, not the dev server**: HAT runs against the
packaged/installed GleepGlorp app (web UI at `http://localhost:8484`, or the desktop
WebView via `the-one app`). Prior live repros (F07's indefinite-hang, the 0.2.8/0.2.9
Ollama `num_ctx` saga) all manifested on the installed instance.
- Rationale: closest to real-user conditions; catches packaging/runtime gaps that a
  source run hides.
- Trade-off / **workflow note**: fixes land in source, so verifying a fix means
  rebuilding/reinstalling (or reproducing on a dev run first, then confirming on the
  installed app). Each fix leg states how it was re-verified on the installed app.

**DD3 — Providers in scope: Anthropic, Ollama (native `/api/chat`), OpenRouter**:
OpenAI is excluded this pass (operator choice). The Ollama path specifically means
the native `/api/chat` route shipped in 0.2.9 (`native_api=True`), which is the one
that honours `options.num_ctx`.
- Rationale: covers the cloud thinking/tool paths (Anthropic), the local
  runtime-window path most recently churned (Ollama native), and the routed path
  (OpenRouter) — the three the operator most wants confidence in.
- Trade-off: OpenAI and `openai-compatible` back-ends (LM Studio, vLLM, llama.cpp)
  are not exercised here; if a finding implicates them, note it and decide coverage.

**DD4 — Triage case-by-case; record the call**: Each finding is sized at discovery.
Small/contained → a leg in this flight. Large/structural or out-of-mission → spun out
as its own follow-up flight or logged to the mission's Known-Issues / debrief
carry-forward. The disposition is decided by the operator + Flight Director together
when the issue surfaces and written into the flight log next to the finding.
- Rationale: the operator explicitly wanted to handle big issues "as they come up"
  rather than commit a rule up front.
- Trade-off: requires a live triage decision per finding (kept lightweight — one log
  line: finding → disposition).

### Prerequisites
- [x] Installed app is current — running 0.2.9 (operator-confirmed 2026-06-26).
- [x] Provider credentials/config present on the installed instance: Anthropic API
      key, OpenRouter API key, and a running Ollama with at least one pulled model
      (native API reachable). *(operator-confirmed 2026-06-26: "got what I need")*
- [x] Flight log open and ready to capture findings with: provider, model id (verified
      live), repro steps, observed vs. expected.

### Pre-Flight Checklist
- [x] All open questions resolved (except per-session model choice, by design)
- [x] Design decisions documented
- [ ] Prerequisites verified
- [x] Prerequisites verified (2026-06-26: on 0.2.9, creds present)
- [x] Validation approach defined (operator judgment + per-fix re-verification)
- [x] Legs defined (accretive by design — seeded empty per DD1)

---

## In-Flight

### Technical Approach
1. Operator runs HAT sessions against the installed app, one in-scope provider at a
   time, varying models, prompt styles, tool use, history length, and the
   stream/cancel/queue controls.
2. Every defect or rough edge is logged to `flight-log.md` as a finding (provider,
   live-verified model id, repro, observed vs. expected, evidence).
3. The Flight Director + operator triage each finding (DD4) and, for in-flight ones,
   open a leg (`{NN}-{issue-slug}`): reproduce → fix in source → re-verify on the
   installed app (rebuild/reinstall or dev-repro-then-confirm per DD2).
4. Fix legs get regression coverage (unit/conformance, or a behavior test) where the
   defect class warrants it — the cross-provider conformance suite (criterion-backed)
   is the natural home for provider-quirk regressions.
5. Repeat until the operator judges chat acceptable across the in-scope providers.

### Checkpoints
- [ ] Anthropic chat exercised and findings logged/triaged
- [ ] Ollama (native) chat exercised and findings logged/triaged
- [ ] OpenRouter chat exercised and findings logged/triaged
- [ ] All in-flight findings resolved; deferred findings recorded with disposition

### Adaptation Criteria

**Divert if**:
- A finding turns out to be large/structural or outside the provider/agent layer —
  spin it out as its own flight (DD4) rather than absorbing it here.

**Acceptable variations**:
- Adding legs ad hoc as findings surface (this is the flight's whole shape — DD1).
- Substituting models per provider as availability/curiosity dictates (record the id).
- Touching adjacent surfaces a finding implicates (e.g. agent loop, tool layer)
  provided the fix stays scoped to the defect and is logged.

### Legs

> **Note:** Accretive by design (DD1). Legs are created one at a time as defects
> surface during HAT, named `{NN}-{issue-slug}`. This list starts empty and grows
> during execution — it is the flight's expected behavior, not scope creep.

- [x] `01-search-tools-truncation` — fix F09-01: `search_tools` silently caps at 8 and
      hides tools (e.g. Sonos `set_volume`); guarantee name matches + honest truncation
      signal so the model re-searches instead of declaring a tool absent. **Completed,
      shipped in 0.2.10, live-verified.** (Operator accepted server-name queries
      returning the full catalog — see flight-log F09-01.)
- [ ] `02-queued-message-render` — redesign the send-while-thinking queue to a client-hold
      model: F09-02 (render queued message as a bubble on dequeue), F09-03 ("Stop" cancels
      the running turn, not the queued task — backend per-session cancel-set), F09-04
      (pin the queued message above the composer instead of scrolling it away, + a cancel ×).
      Batched for the 0.2.11 build.
- [ ] `03-ollama-num-ctx-admin-field` — mitigation for F09-05 (long local-model
      conversations crawl at high context): make `num_ctx` an editable Ollama provider field
      in Administration (precedence per-provider → env → default, clamped to advertised), so
      the window/speed trade-off is tunable without an env var. Compaction (the real fix)
      stays a deferred mission Known Issue. Batched for the 0.2.11 build.

---

## Post-Flight

### Completion Checklist
- [ ] All in-flight findings resolved (legs landed) or explicitly deferred with a
      recorded disposition
- [ ] Code merged
- [ ] Tests passing (incl. any regression coverage added by fix legs)
- [ ] Documentation updated where a fix changed user-facing behavior or config
- [ ] Mission Known-Issues / debrief carry-forward updated with any deferred findings

### Verification
The flight is verified by **operator judgment**: chat is reliable and pleasant across
Anthropic, Ollama (native), and OpenRouter on the installed app, every surfaced defect
is either fixed-and-re-verified or explicitly triaged to a follow-up, and the flight
log holds the full findings ledger with dispositions.
