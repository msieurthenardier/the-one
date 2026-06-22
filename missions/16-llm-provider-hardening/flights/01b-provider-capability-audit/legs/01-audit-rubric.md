# Leg: audit-rubric

**Status**: landed
**Flight**: [Provider Capability Audit](../flight.md)

## Objective
Establish the frozen audit framework — the capability list, the three-axis scoring rubric (DD4), the contract-surface inventory the "contract-representable" axis is scored against, the matrix template, and the citation convention — so the four provider-audit legs produce consistent, comparable, evidence-backed rows.

## Context
- **DD4** (flight): each capability is scored on three axes per provider — *SDK-exposed* / *contract-representable* / *wired-through* — and each gap is classified by where the fix lands (contract-level vs. adapter-only). That classification is only reproducible if the contract surface is captured once, as a frozen reference, rather than re-read per provider.
- **DD2**: the capability list is the full mission list plus a per-SDK catch-all.
- **DD5**: every "SDK-exposed" claim carries a source citation (SDK symbol/path or doc URL). This leg defines that convention so the provider legs follow it.
- This is the first leg; all other legs depend on its output. It writes to the **flight log** (the deliverable per DD1), not to a source file.

## Inputs
- `the_one/llm/base.py` — the `LLMProvider` contract + `Message`/`ToolCall`/`ToolResult`/`StreamChunk`/`TokenUsage`.
- Flight spec (DD1–DD6, capability list).
- Flight 1's `flight-log.md` (root causes for #122/#105) — to seed cross-references.
- `flight-log.md` with empty `## Capability Matrix` and `## Gap Backlog` sections already scaffolded.

## Outputs
- `flight-log.md` gains, under a clearly-titled rubric subsection:
  - The **capability list** (rows of the matrix).
  - The **three-axis rubric** definition + the gap-classification rule (contract-level vs. adapter-only).
  - The **contract-surface inventory** — the exact representable fields of the contract today, with `base.py` line citations — as the frozen reference for the middle axis.
  - The **matrix template** (a table shape the provider legs fill) + the **citation convention**.
  - Seeded **#122 / #105 cross-reference notes** so the relevant capability rows point at the owning bug-fix flights.
- No source files touched.

## Acceptance Criteria
- [ ] The capability list is recorded and covers every capability the mission names: extended thinking, prompt caching, structured outputs / JSON mode, vision/multimodal, reasoning-effort controls, document inputs, parallel tool calls, stop sequences, streaming events, token counting — plus an explicit "per-SDK catch-all" row instructing auditors to add anything else the SDK surfaces.
- [ ] The three-axis rubric is defined with each axis given an unambiguous decision rule, and the contract-level-vs-adapter-only gap-classification rule is stated.
- [ ] The contract-surface inventory lists, with `base.py` line citations, exactly what the contract can represent today — at minimum: `complete()`/`stream()` accepted params (`base.py:303-333`), `Message` fields (`base.py:64-70`), `ToolCall` (`:21-25`), `ToolResult` normalization-to-`str` (`:28-56`), `TokenUsage` fields (`:58-61`), `StreamChunk` fields (`:228-243`), and the `supports_tools()` / `tool_schema()` / `_resolve_max_context_tokens()` hooks (`:335-360`, `:276-301`). It explicitly notes the representational gaps that are already visible from the contract alone (e.g. no thinking/reasoning field on `Message`; `content` is `str` only — and **assert-enforced** at construction (`base.py:135-137`), so multimodal would be actively *rejected*, not merely unmodeled; `TokenUsage` has no cache-read/creation fields; no `stop`/`response_format`/`reasoning_effort` params on the call signatures).
- [ ] The inventory records that "contract-representable" includes **round-trip through persistence**, not just a field on `Message` — so a contract-level gap that adds a `Message` field also implies a codec change. Locate and cite the `Message` persistence codec (the encode/decode path that serializes `Message`/its fields for storage) as a one-line pointer, so the provider legs don't under-scope contract-level gaps.
- [ ] The matrix template is laid down (a table with one row per capability and columns for the three axes + gap class + citation + notes), and the citation convention is stated (every SDK-exposed cell names an SDK symbol/path or doc URL).
- [ ] #122 (Anthropic tool `input_schema`) and #105 (Ollama text-form tool calls) are noted as cross-references against the relevant rows (tool-calling / parallel-tool-calls), pointing at Flights 2 and 3 respectively, so the audit relates them rather than re-deriving them.

## Verification Steps
- Read the rubric subsection of `flight-log.md`: confirm the capability list is complete against the mission list, the three axes each have a decision rule, and the classification rule is present.
- Spot-check 3 inventory citations against `base.py` (e.g. `Message` at 64-70 really has no thinking field; `TokenUsage` at 58-61 has only input/output).
- Confirm the matrix template has the required columns and that the citation convention is written down.
- Confirm #122/#105 cross-reference notes are present and point at F2/F3.

## Implementation Guidance
1. **Read the contract.** Read `the_one/llm/base.py` end-to-end. Capture the representable surface verbatim with line numbers — do not paraphrase from memory.
2. **Read Flight 1's flight log** for the confirmed root causes of #122 and #105 so the cross-reference notes are accurate (and so later legs don't re-investigate them).
3. **Write the rubric subsection** into `flight-log.md` (a new subsection under `## Capability Matrix`, above the empty matrix body — or a clearly-titled "Rubric & Contract Inventory" subsection). Include: capability list, three-axis rubric + classification rule, contract-surface inventory with citations, matrix template, citation convention, #122/#105 notes.
4. **Do not fill any provider rows** — that is the provider legs' job. This leg only lays the frame.
5. **Update the flight log** session notes with a one-line entry; set this leg's status to `landed` when done. Do NOT commit.

## Edge Cases
- **A capability is ambiguous at the contract level** (e.g. "streaming events" partially exists via `StreamChunk`): record it in the inventory as *partially representable* with the specific missing piece, rather than a binary yes/no — the provider legs will refine per-provider.
- **The catch-all risks unbounded scope**: cap it — instruct auditors to add only capabilities the official SDK surfaces as first-class API parameters/objects, not every transport detail.

## Files Affected
- `missions/16-llm-provider-hardening/flights/01b-provider-capability-audit/flight-log.md` — rubric subsection + matrix template added. (Artifact only; no source code.)

---
