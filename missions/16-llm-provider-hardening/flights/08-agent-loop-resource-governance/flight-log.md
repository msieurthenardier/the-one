# Flight Log: Agent-loop Resource Governance & Context-budget Management

**Flight**: [Agent-loop Resource Governance & Context-budget Management](flight.md)

## Summary

Flight created (planning). Implements Flight 07 debrief Recommendation 1: a single
context-budget governor at the tool-dispatch boundary, conversation-level accounting
surfaced (color-coded) in the telemetry overlay, and a reliable/configurable
`web_search` backend. Context compaction (eviction/summarization) is deferred to its
own future mission. No execution yet.

---

## Reconnaissance Report

Source: `flights/07-chat-loop-robustness/flight-debrief.md` (Recommendation 1 +
Key Learnings) and the operator's scoping this session. Cited locations walked against
current `main`.

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| No central context-budget governor over tool results | `confirmed-live` | `the_one/agent/core.py:535` `_execute_tool`; `:555` `return ToolResult(content=output)` — output passed through unbounded | Add governor here (DD1, leg 1) |
| Per-tool LLM caps inconsistent / wrong axis | `confirmed-live` | web `tool_text_cap_bytes`=48 KB (`_web_config.py:196`); filesystem `read_size_cap_bytes`=1 MB **file size** (`filesystem.py:91,266`); execution `output_cap_bytes` (~100 MB ceiling) | Unify under governor; retire LLM-facing caps, keep safety caps (DD1) |
| Model context window reachable from the agent | `already-satisfied` | `self.llm.max_context_tokens` (`base.py:250`, catalog-resolved via `_resolve_max_context_tokens_if_needed`) | Governor derives budget from it (DD1/DD4) |
| No tokenizer; only byte-per-token heuristic | `confirmed-live` | `BYTES_PER_TOKEN_*` in providers / `_streaming.py`; no tiktoken dep | Budget in bytes-with-heuristic (DD4) |
| `web_search` = unauthenticated DDG scrape, silent empty | `confirmed-live` | `the_one/tools/_search_backends.py` `DDGSearchBackend` (HTML scrape of `html.duckduckgo.com`); `SearchBackend` Protocol already exists | Pluggable backend + honest-empty + optional keyed (DD3, leg 2) |
| Telemetry overlay already renders a context fraction | `already-satisfied` | `chat.js` `updateTelemetry`/`setTelemetryMax`; renders `context_tokens / max_context_tokens` bar (F6/F7); `.telemetry-overlay` in `chat.css` | Add threshold coloring on top (DD2, leg 3) — accounting is mostly already present |
| Web 1 MB streaming cap + file-size read cap are SAFETY guards | `confirmed-live` | `response_size_cap_bytes` streaming hard-abort (`web.py`); `read_size_cap_bytes` file-size guard (`filesystem.py:266`) | KEEP (transport/OOM axis); do NOT retire as part of unifying LLM caps (DD1) |

No `drifted`/`partially-satisfied`. The two `already-satisfied` rows (model window
reachable; overlay fraction present) shrink the flight: the governor's input and the
accounting's display both already exist — the work is the governor logic + the coloring.

**Lineage**: F07 fixed the single-oversized-result case (0.2.6 `tool_text_cap_bytes`);
this flight generalizes it to a model-derived governor over ALL tools and adds the
cumulative-pressure signal. The F07 debrief's verification miss (tested the pathological
infinite-stream input but never a large *valid* page) is the test-discipline this
flight's DD5 corrects: assert "what the model receives" for a large valid input, across
tool types.

---

## Flight Director Notes

- **2026-06-23** — Flight planned via `/flight`. Operator design decisions: central
  governor that retires per-tool LLM-facing caps (safety caps stay); full conversation
  accounting + warn via overlay color (orange/red), NO eviction; configurable search
  backend with honest-empty default; bytes-with-heuristic budgeting. Context compaction
  (evict/summarize) deferred to its own future mission per operator ("almost feels like
  its own mission").

---

## Deviations

_(none yet)_

---

## Anomalies

_(none yet)_

---

## Session Notes

- **2026-06-23** — Flight created from the F07 debrief Recommendation 1.

- **2026-06-23 — Architect design review → approve-with-changes.** Architecture sound
  (`_execute_tool` chokepoint correct; pure-helper governor; max_context_tokens timing
  safe; read_size_cap_bytes correctly kept as safety). Folded in three HIGHs (all F07-
  lesson repeats): field-count guard will break again; `output_cap_bytes` is a second
  mis-axed LLM cap with a head/tail direction clash (governor must be direction-aware);
  "honest-empty" needs a backend contract change. Plus: DD2 coloring already shipped →
  leg 3 rescoped to config-thresholds + a11y (not rebuild); promote `bytes_per_token` to
  the provider base; governor floors max_context_tokens / excludes auth sentinel. See
  flight.md "Design-Review Corrections (binding)". No DD rework; ready to execute.
