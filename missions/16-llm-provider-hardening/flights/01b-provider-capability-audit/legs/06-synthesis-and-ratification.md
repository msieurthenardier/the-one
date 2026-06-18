# Leg: synthesis-and-ratification

**Status**: landed
**Flight**: [Provider Capability Audit](../flight.md)

## Objective
Consolidate the four per-provider audit matrices into the flight log's `## Capability Matrix` (the DD1 deliverable), classify each gap, attach a proposed priority + effort/risk, route owned-elsewhere gaps to their flights, mark the mission open questions, and produce the prioritized gap backlog for operator ratification.

## Context
- Inputs are the four **landed, reviewed** audit legs (02–05); this leg does not re-audit, it consolidates.
- DD1: the consolidated matrix + ratified backlog live in `flight-log.md`.
- DD3: the audit *proposes* priority/effort/risk; the operator *ratifies*. This leg produces the proposal; the Flight Director runs the ratification with the operator.
- DD4: gaps are classified contract-level vs. adapter-only. The provider audits found the dominant pattern is **contract-level** (the contract carries only messages/tools/temperature/max_tokens), so the backlog must surface the **shared contract-level enablers** (e.g. a thinking field; widening `content` off the str-assert; `TokenUsage` cache fields; new request params for stop/response_format/reasoning_effort) that unblock multiple providers at once — these are higher-leverage than any single adapter wiring.

## Inputs
- `legs/02-anthropic-audit.md`, `legs/03-openai-audit.md`, `legs/04-ollama-audit.md`, `legs/05-openrouter-audit.md` — filled `## Audit Result` matrices.
- `flight-log.md` → `### Rubric & Contract Inventory` (the frozen reference + empty `## Capability Matrix` body + `## Gap Backlog (proposed → ratified)` section).
- The mission's still-open questions (Ollama SDK vs httpx; model-catalog sourcing; reasoning beyond Anthropic; thinking representation).

## Outputs
- `flight-log.md` `## Capability Matrix`: a consolidated cross-provider matrix (capability × provider, each cell carrying the three-axis verdict + gap class, citations preserved or referenced back to the per-provider legs).
- `flight-log.md` `## Gap Backlog (proposed → ratified)`: one entry per gap (or per shared contract-level enabler), each with: gap class, affected providers, **proposed priority (High/Med/Low)**, **rough effort (S/M/L)**, **risk note**, one-line rationale, and a route tag for owned-elsewhere items (#122→F2, #105→F3, model-catalog→F5).
- A mission-open-questions disposition: each of the four still-open OQs marked **answerable-now** (with the evidence) or **deferred-to-owning-flight**.
- (After operator ratification — added by the Flight Director) a **timestamped ratification block** recording confirmed/overridden priorities per gap.

## Acceptance Criteria
- [ ] The consolidated cross-provider matrix is in `flight-log.md` `## Capability Matrix`, covering all ten named capabilities + every catch-all row any provider leg added, for all four providers; each cell shows the three-axis verdict + gap class, with citations preserved or referenced to the source leg.
- [ ] The gap backlog has one entry per gap or shared contract-level enabler, each with gap class, affected providers, proposed priority, rough effort, risk note, and one-line rationale.
- [ ] **Shared contract-level enablers are surfaced as first-class backlog entries** (not buried per-provider) — e.g. "add a thinking field to `Message` + codec" is one entry noting it unblocks Anthropic (full) and OpenAI/Ollama (partial), rather than three disconnected rows.
- [ ] Owned-elsewhere gaps are routed, not re-scoped: #122→Flight 2, #105→Flight 3, model-catalog/context-window→Flight 5, each tagged in the backlog as tracked-there.
- [ ] Each of the four still-open mission OQs is marked answerable-now (with evidence from the audit) or deferred-to-owning-flight.
- [ ] The backlog is presented to the operator (by the Flight Director) and a timestamped ratification block records confirmed/overridden priorities. *(This AC is closed at the ratification step, after the agent produces the proposal.)*

## Verification Steps
- The `## Capability Matrix` is filled (no empty template cells) and every provider/ capability intersection is present.
- Spot-check that each backlog entry's affected-providers + gap class match the per-provider legs.
- Confirm #122/#105/catalog routing tags are present and no fix is proposed for them here.
- Confirm the four OQ dispositions are present with evidence.
- Confirm the ratification block exists and is timestamped (added after the operator confirms).

## Implementation Guidance
1. Read all four `## Audit Result` matrices and the frozen rubric.
2. Build the consolidated matrix in `flight-log.md` `## Capability Matrix` (below the existing `### Rubric & Contract Inventory`). Recommended shape: one section/row-group per capability, a sub-row per provider — or a wide table (capability × provider) with the verdict+gap-class in each cell and citations referenced back to the per-provider leg (don't duplicate every citation inline; "see legs/02 row X" is fine where it keeps the matrix readable).
3. Derive the gap backlog in `## Gap Backlog (proposed → ratified)`. Group by **shared contract-level enabler** first (thinking field; content-widening for vision+documents; `TokenUsage` cache fields; new request params for stop / response_format / reasoning_effort; parallel-tool-call toggle), each entry naming the providers it unblocks and to what degree. Then adapter-only gaps. Then a clearly-separated "routed elsewhere (#122/#105/F5)" list.
4. For each backlog entry assign proposed Priority (H/M/L), Effort (S/M/L), a risk note, and a one-line rationale. Use the audit evidence — e.g. a contract-level enabler that unblocks several providers and is low-effort (capture side de-risked by Flight 1 for thinking) ranks higher than a single-provider adapter tweak.
5. Write the mission-OQ disposition (four OQs: Ollama SDK vs httpx — use leg 04's track-b note; model-catalog sourcing — defer to F5; reasoning beyond Anthropic — use the OpenAI reasoning_effort + Ollama reasoning findings; thinking representation — answerable-now design input from the contract-level enabler analysis).
6. Set leg Status to `landed`. Add a Session Notes line. Do NOT commit. Do NOT touch source. **Do NOT write the ratification block** — leave a clearly-marked placeholder; the Flight Director fills it after the operator ratifies.

## Edge Cases
- **Catch-all rows differ across providers** (anthropic added citations/server-tools/batch; openai added predicted-outputs/audio; ollama added model-lifecycle; openrouter added context-resolution/capability-discovery): keep them as provider-specific rows in the matrix, and in the backlog only promote ones the operator might plausibly want — mark the rest "noted, low/defer."
- **Conflicting gap-class between providers for the same capability** (e.g. parallel tool calls is contract-level for the toggle but adapter-only for parse): represent both facets in the entry rather than collapsing to one class.

## Files Affected
- `flight-log.md` (`## Capability Matrix` + `## Gap Backlog`) and this leg artifact. No source code.

---
