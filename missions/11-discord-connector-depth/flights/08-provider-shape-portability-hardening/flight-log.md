# Flight Log: Provider-Shape-Portability Hardening

**Flight**: [Provider-Shape-Portability Hardening](flight.md)

## Summary

(Populated during and after execution.)

---

## Reconnaissance Report

**Date**: 2026-05-26 (Phase 1b, F8 planning)
**Source artifact**: [F7 flight debrief](../07-mentions-aware-response-policy/flight-debrief.md) — "What Could Be Improved → Technical" section and "Recommendations → #1" (line 83).

Items in F7-debrief Recommendation #1 walked against current code:

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| **(a) `ToolResult.content` typing — runtime enforcement** | `already-satisfied` (surgical), `confirmed-live` (permanent fix) | Surgical: 12.l at `the_one/llm/anthropic_provider.py:219-249` (Anthropic-only `json.dumps` coercion guarded by `isinstance(content, str)`); 12.m at `the_one/db/codec.py:18-39` (`truncate_for_event` non-str coercion). **Additional consumer (Architect-flagged at Phase 5b, recon-omitted):** `the_one/interfaces/cli.py:83-85` does `len(output)` and slices to 500 chars on `tool_result.content` — would crash on non-str. Construction site: `the_one/agent/core.py:336` wraps tool output as `ToolResult(content=output)`. Tests: `tests/test_llm_provider_tool_result_serialization.py` (8 tests), `tests/test_truncate_for_event_non_str_coercion.py` (6 tests). Trigger sites unchanged: `the_one/tools/connector_history.py:134, 233, 321, 416` still return `list[dict[str, Any]]`. | Permanent fix is real F8 work. **Resolved at Phase 5b: Architect pick (c) hybrid** — widen annotation + `__post_init__` JSON-stringifies non-str. Operator-confirmed. |
| **(b) `Message.content` ASSISTANT/SYSTEM audit** | `confirmed-live` (partially-satisfied) | `build_user_message_content` at `the_one/llm/base.py:148-184` defends USER-role only via `if msg.role != Role.USER: return msg.content` (line 174-175). ASSISTANT+tool_calls branches pass `msg.content` through unguarded: `anthropic_provider.py:250-258` (line 253 inline text block); `openai_provider.py:262-277` (line 265); `ollama_provider.py:256-279` (line 262). No `__post_init__` validator on `Message` dataclass at `base.py:42-44`. | Real F8 work. Audit + enforce at chosen layer (matches L2's approach). |
| **(c) GET/PUT mask sentinel sweep — `api.py:1588` and beyond** | `already-satisfied` | Line 1588 (POST `/test/connect` MCP body-override) already uses `_looks_masked()` check at `the_one/interfaces/web/api.py:688-707` which recognizes both `_MASKED_API_KEY_SENTINEL` and the regex shape. Connector `/test/connect` at `api.py:2598-2679` has no body override (no asymmetry possible). Tests: `tests/test_api_secret_mask_roundtrip.py` (437 lines, covers MCP + connector + provider GET/PUT). | Retire from F8 scope. Documented here as closed. |
| **Mask-shape regex / `_mask_secret_value` shared-constant** | `confirmed-live` (low-risk) | `_mask_secret_value` at `api.py:642-664` emits `"***"` or `f"***...{value[-4:]}"`. `_MASK_SHAPE_RE` at `api.py:685` is `^\*\*\*(\.\.\..{1,4})?$`. Literals identical, adjacent (same function block), but no shared constant. Drift unlikely structurally but not prevented mechanically. | Fold into F8 as L4. Small refactor (~10 LOC). Operator confirmed in-scope. |
| **(d) Cross-provider chat-history (task #25)** | `needs-human-recheck` → resolved by operator (real concern, in scope) | No code reference to "task #25" found in repo (grepped commits, comments, TODOs). Provider landscape: Anthropic (271 LOC), OpenAI (286 LOC), OpenRouter (157 LOC, inherits OpenAI), Ollama (282 LOC). Canonical `Message` dataclass at `the_one/llm/base.py:42-44` is the portable shape. Cross-provider parity test exists at `tests/test_llm_provider_user_content_projection.py` (17 tests) but covers USER-role projection only, not full assistant + tool-call round-trip across provider swaps. | F8 L1: pin via cross-provider tool-call round-trip test for Anthropic↔Ollama (qwen) and Anthropic↔OpenRouter (`google/gemma-4-26b-a4b-id:free`). Test+fix atomic. |

### Retirements from F7-debrief Rec #1 scope
- **Item (c) — GET/PUT mask sentinel sweep at `api.py:1588`**: already-satisfied per recon evidence above. Confirmed retired by operator (implicit via "F8 stays focused on the typing axis" framing during planning).

### Carry-forwards from F7 debrief NOT in F8 scope
- F7 Rec #3 candidates (`.tool-enable-switch` CSS default flip, `_inbound.py` helper extraction, studio-event-bus pattern lift, field-row-3-column primitive): routine-maintenance candidates, not F8.
- F7 Rec #5 (re-run discord-engagement behavior test in fresh session): one-off action item, may happen alongside F8 but not part of the flight scope.
- F7 Rec #4 (codify inline-hotfix-during-HAT discipline in mission-control): cross-project methodology work, lives on `skill/wbt` branch — separate from this flight.

### Operator decisions during F8 planning (logged here for traceability)
- **F8 scope**: provider-shape-portability hardening only (not bundled with pairing+detach per the original mission flight list); pairing+detach becomes F9; subsequent flights renumber accordingly.
- **`ToolResult.content` enforcement shape**: deferred to Architect at Phase 5b. **Resolved**: pick (c) Hybrid — widen annotation + `__post_init__` JSON-stringifies non-str. Operator-confirmed.
- **Task #25 framing**: real concern (per operator: "I think it's real but we should test"). L1 pins the gap via a test; if test passes from the start, the concern was overstated and L1 ships clean.
- **Mask-shape constant refactor**: in F8 scope as L3 (was L4 before L2+L3 collapse).
- **HAT**: conditional on L1 outcome — only added as L4 (was L5) if L1 surfaces a real fix.
- **Provider test pairs**: Anthropic↔Ollama (qwen-family) + Anthropic↔OpenRouter (`google/gemma-4-26b-a4b-it:free`). OpenRouter inherits OpenAI, so OpenAI is implicitly covered.

### Phase 5b Architect review summary (2026-05-26)
- **Verdict**: approve with changes.
- **`ToolResult.content` pick**: (c) Hybrid. Rationale: trigger sites (channel-context tools) legitimately return `list[dict]`; pushing JSON-encoding to tool authors (option a) puts serialization in the wrong layer; option (b) leaves multiple consumer sites needing audit-and-coercion forever (anthropic_provider.py:236, db/codec.py:38, cli.py:83-85, plus openai/ollama branches that currently pass through unchecked); option (c) collapses to a single normalization site at construction so every consumer reads `str` uniformly. **Operator-confirmed.**
- **High-severity issue**: OpenRouter model slug `google/gemma-4-26b-a4b-id:free` was likely a typo; operator confirmed the correct slug at Phase 5b is `google/gemma-4-26b-a4b-it:free`.
- **Medium-severity issue**: recon missed `cli.py:83-85` as a `ToolResult.content` consumer. Now added to item (a) evidence column.
- **Medium-severity issue**: L2 and L3 collapse cleanly under pick (c) — L3 becomes ~5 LOC. **Operator-confirmed**: collapse into one `dataclass-shape-invariants` leg.
- **Low-severity issue**: L1 needs a concrete divert threshold. **Resolved**: ~80 LOC across more than one module triggers divert; flight artifact's Adaptation Criteria updated.
- **Codebase-state observations**: the-one is on branch `flight/07-mentions-aware-response-policy` (not main); F7 landed at `b42c609`, debriefed at `9949dbe`. Stray `docker-compose.yml` modification in working tree — Architect-flagged for stash/commit before F8 starts. Added to Prerequisites.
- **Convention naming**: `provider-shape-portability` and `single-source-of-truth-for-paired-helpers` are collision-free against existing `agents.md` conventions.

---

## Leg Progress

(Populated as legs execute.)

---

## Decisions

(Runtime decisions not in original plan.)

---

## Deviations

(Departures from planned approach.)

---

## Anomalies

(Unexpected issues encountered.)

---

## Session Notes

(Chronological notes from work sessions.)
