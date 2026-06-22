# Leg: anthropic-audit

**Status**: landed
**Flight**: [Provider Capability Audit](../flight.md)

## Objective
Audit `anthropic_provider.py` against the installed `anthropic` SDK surface, producing one cited matrix row per capability (the frozen capability list from leg 01) scored on the three axes.

## Context
- Scores against the **frozen rubric + contract inventory** in `flight-log.md` (leg `01-audit-rubric`). Do NOT re-read or re-derive the contract surface — use the inventory as the reference for the "contract-representable" axis.
- SDK is the official `anthropic` SDK installed in the project **`.venv`** (currently 0.97.0 — but **read the exact installed version from `.venv` and record it in the matrix header**; do not trust this number, the pin is a floor `>=0.40`). Read its source for the "SDK-exposed" axis (DD5).
- This leg writes to its **own leg artifact** (the Audit Result section below), NOT the shared flight log — the four provider legs run concurrently and the synthesis leg consolidates them. (DD1's flight-log deliverable is assembled by leg 06.)
- #122 (top-level `oneOf/allOf/anyOf` + missing top-level `type` rejection) is owned by Flight 2 — note it against the tool-calling row, do not re-derive.

## Inputs
- `flight-log.md` → `### Rubric & Contract Inventory` (frozen reference: capability list, three axes, matrix template, citation convention).
- Installed `anthropic` SDK source in the project `.venv` (read the exact version; `~0.97.0`).
- `the_one/llm/anthropic_provider.py` (and `_streaming.py`, `base.py` as needed for wiring).

## Outputs
- This leg artifact gains a filled matrix (one row per capability + any catch-all rows) in the `## Audit Result` section, every SDK-exposed cell carrying a citation.

## Acceptance Criteria
- [ ] Every one of the ten named capabilities in the frozen list, plus any per-SDK catch-all rows discovered, has a row scored on all three axes: SDK-exposed / contract-representable / wired-through (Yes/No/Partial with the missing piece named per Edge Case #1).
- [ ] Every "SDK-exposed: Yes/Partial" cell cites an `anthropic` SDK symbol/path (e.g. a param on `messages.create`, a typed content/usage field) or an official doc URL, per the citation convention.
- [ ] Every "Wired-through" cell cites `anthropic_provider.py:line` (or `_streaming.py:line`) for where it is/isn't built on the request or parsed off the response.
- [ ] Each gap carries a proposed gap class (contract-level / adapter-only / none) consistent with the contract inventory (a gap needing a new `Message`/`TokenUsage` field or a relaxed assert is contract-level + implies a codec change).
- [ ] The tool-calling / parallel-tool-calls row notes #122 as tracked under Flight 2 (cross-ref, not re-derived). Anthropic's `count_tokens` (the SDK exposes `messages.count_tokens`) is captured under the token-counting row.

## Verification Steps
- Confirm one row per frozen-list capability is present, all three axes scored.
- Spot-check 2 SDK citations resolve to a real symbol in the installed `anthropic` package.
- Spot-check 2 wiring citations resolve to the cited `anthropic_provider.py` lines.

## Implementation Guidance
1. Read the frozen rubric/inventory in `flight-log.md` — internalize the axes and citation convention. Do not re-audit the contract.
2. Read `the_one/llm/anthropic_provider.py` fully (plus `_streaming.py` for stream handling). Note for each capability whether the adapter sets the request param / parses the response.
3. Read the installed `anthropic` SDK surface (find the package in site-packages; inspect `messages.create` params, content-block types, usage fields, `messages.count_tokens`, beta namespaces for prompt caching / structured outputs). Cite real symbols.
4. Fill the matrix rows in this leg's `## Audit Result` table. Use Partial honestly; name the missing piece.
5. Set leg status to `landed`. Add a one-line flight-log Session Notes entry naming this leg done (single short append — keep it to Session Notes, not the matrix, to avoid racing the other provider legs). Do NOT commit. Do NOT touch source files.

## Edge Cases
- **Prompt caching / structured outputs may live behind `anthropic` beta namespaces** — if so, cite the beta symbol and note "beta" in the row; still a real SDK-exposed surface.
- **Extended thinking**: SDK-exposed Yes (thinking config + signed thinking blocks, confirmed by Flight 1's spike); contract-representable No (no Message thinking field) → contract-level. Cite Flight 1's finding rather than re-spiking.

## Files Affected
- This leg artifact only (audit results). No source code.

---

## Audit Result

**SDK audited:** `anthropic` **0.97.0** (read from project `.venv`: `.venv/bin/python -c "import anthropic; print(anthropic.__version__)"`). Surface is GA-level — `thinking`, `cache_control`, `output_config` (effort + JSON format), `stop_sequences`, `tool_choice.disable_parallel_tool_use`, image/document content blocks, and `messages.count_tokens` are all top-level (non-beta) on `messages.create` / the response `Usage` model.

**Adapter under audit:** `the_one/llm/anthropic_provider.py` (+ `the_one/llm/_streaming.py`). The adapter builds requests via `_build_kwargs` (`anthropic_provider.py:75-100`), which sets **only** `model`, `messages`, `max_tokens`, `temperature`, `system`, `tools` — no other request param. Responses are parsed in `complete()` (`:123-138`) and `_stream_inner()` (`:186-208`), which read only `text` / `tool_use` blocks and `usage.input_tokens` / `usage.output_tokens`. All other blocks and usage fields are dropped.

| Capability | SDK-exposed | Contract-representable | Wired-through | Gap class (contract-level / adapter-only / none) | Citation | Notes |
|---|---|---|---|---|---|---|
| Extended thinking | Yes | No | No | contract-level (+ codec) | SDK: `messages.create(..., thinking=)` `ThinkingConfigParam` (`anthropic/types/thinking_config_param.py`; enabled/adaptive/disabled); response block `ThinkingBlock{signature, thinking}` (`anthropic/types/thinking_block.py`), in `ContentBlock` union (`content_block.py`). Wiring: not built (`anthropic_provider.py:90-100`); blocks dropped — loop only handles `text`/`tool_use` (`:125-129`, `:188-192`). | SDK Yes per Flight 1 spike (config + signed blocks) — not re-spiked. Contract-representable No: no thinking field on `Message` (`base.py:64-70`); adding one is contract-level AND a codec change (`codec.py` `message_to_dict`/`_from_dict`). |
| Prompt caching | Yes | Partial | No | contract-level (+ codec) | SDK: top-level `cache_control` on `messages.create` (`message_create_params.py`) + per-block `CacheControlEphemeralParam` on `TextBlockParam`/`ImageBlockParam`/`DocumentBlockParam` (`text_block_param.py:18-19`); usage `cache_creation_input_tokens`/`cache_read_input_tokens` (`anthropic/types/usage.py:18-23`). Wiring: breakpoints never set (`_build_kwargs`); cache usage fields never read (`:131-136`, `:194-199`). | Contract-representable **Partial**: request side has no entry point AND `TokenUsage` has only `input_tokens`/`output_tokens` (`base.py:58-61`) so cache-token accounting can't be carried. Both halves are contract-level; the `TokenUsage` field also implies a codec change (`_usage_to_dict`/`codec.py`). cf. any-llm mapping. |
| Structured outputs / JSON mode | Yes | No | No | contract-level | SDK: `output_config={"format": JSONOutputFormatParam{schema, type:"json_schema"}}` (`output_config_param.py`, `json_output_format_param.py`). Wiring: `output_config` never set (`_build_kwargs`). | No `response_format`/`output_config` param on `complete()`/`stream()` (`base.py:303-310`, `314-320`). Request-side only (no durable field) → contract-level, no codec change. |
| Vision / multimodal | Yes | No | No | contract-level | SDK: `ImageBlockParam{source: Base64ImageSourceParam\|URLImageSourceParam}` (`image_block_param.py`), in user-message content list. Wiring: adapter only ever emits `text`/`tool_use`/`tool_result` content; user branch passes a plain string (`anthropic_provider.py:254`; explicit "future vision would route a content-list branch" note `:250-253`). | `Message.content` is `str` and assert-enforced (`base.py:135-137`) — multimodal content is actively rejected. Relaxing the assert + widening the field is contract-level (+ codec for durable storage). |
| Reasoning-effort controls | Yes | No | No | contract-level | SDK: `output_config={"effort": "low"\|"medium"\|"high"\|"xhigh"\|"max"}` (`output_config_param.py:14-16`). Wiring: never set (`_build_kwargs`). | No `reasoning_effort`/`output_config` param on the contract (`base.py:303-310`). Request-side only → contract-level, no codec change. |
| Document inputs | Yes | No | No | contract-level | SDK: `DocumentBlockParam{source: Base64PDFSource\|URLPDFSource\|PlainTextSource\|ContentBlockSource, citations, title}` (`document_block_param.py`). Wiring: adapter never builds a document block (`_to_api_message`). | Same root as vision — `content` is `str`-only (`base.py:135-137`); no document content type. contract-level (+ codec). |
| Parallel tool calls | Yes | Partial | Partial | contract-level (toggle) / adapter-only (emit-back) | SDK: parallel is default; toggle via `tool_choice={"type":"any"/"auto", "disable_parallel_tool_use": true}` (`tool_choice_any_param.py:16-20`). Multiple `tool_use` blocks per turn. Wiring: adapter parses **all** `tool_use` blocks into `tool_calls` (`anthropic_provider.py:128-129`, `:191-192`) so parallel calls ARE read back; but `tool_choice` is never set (`_build_kwargs`) so the toggle can't be controlled. | `Message.tool_calls` (`base.py:64-70`) carries the list (representable). The toggle has no `tool_choice` param on the contract → contract-level. **See #122 / Flight 2** for the `input_schema` rejection (verbatim passthrough at `anthropic_provider.py:210-215`) — not re-derived here. |
| Stop sequences | Yes | No | No | contract-level | SDK: `messages.create(..., stop_sequences=[...])` (`message_create_params.py:149`); response `stop_reason="stop_sequence"` + `stop_sequence` (`message.py:81`, `:99`). Wiring: `stop_sequences` never set (`_build_kwargs`); `stop_reason`/`stop_sequence` never read off the response (`complete()` `:123-138`). | No `stop` param on `complete()`/`stream()` (`base.py:303-310`). Request-side only → contract-level, no codec change. (`stop_reason` is also unparsed, but there's no `Message` field for it either.) |
| Streaming events | Yes | Partial | Partial | adapter-only (fidelity) | SDK: `messages.stream()` ctx mgr + `RawMessageStreamEvent` union (`message_stream_event.py`→`raw_message_stream_event.py`): `message_start`, `content_block_delta`, `message_delta` (carries interim `usage`), `message_stop`. Wiring: adapter uses high-level `stream.text_stream` + `get_final_message()` (`_stream_inner` `anthropic_provider.py:177-184`), NOT raw events. | Streaming IS wired (text deltas + final usage/tool_calls/message via `StreamChunk`, `base.py:239-243`). **Partial**: interim usage is a byte-heuristic estimate, not real `RawMessageDeltaEvent` usage — adapter chose not to iterate raw events (module docstring `:21-32`, `:170-175`); `_StreamAccumulator.maybe_emit_interim` (`_streaming.py:130-164`). Closing = adapter-only (swap to raw-event iteration); no contract change. |
| Token counting | Yes | No | No | contract-level | SDK: `client.messages.count_tokens(...)` → `MessageTokensCount` (`resources/messages/messages.py:1259`/`:2696`; `message_count_tokens_params.py`, `message_tokens_count.py`). Wiring: never called by the adapter (no reference in `anthropic_provider.py`). | No pre-flight count-tokens entry point on the `LLMProvider` contract (`base.py` has only `_resolve_max_context_tokens`/context hooks, no count helper). Adding a contract method is contract-level (no codec; not durable state). |
| _(catch-all)_ Citations | Yes | No | No | contract-level | SDK: `CitationsConfigParam` on `DocumentBlockParam` (`document_block_param.py:28`); `citations` on `TextBlockParam` (`text_block_param.py:21`); typed `citation_*` location blocks (`anthropic/types/citation_*`). Wiring: never set/parsed. | First-class API object. Same `content`-str root blocks representation; no citation field on `Message`. contract-level. |
| _(catch-all)_ Message Batches | Yes | No | No | out-of-scope (request-shape, not a per-message field) | SDK: `client.messages.batches.create/retrieve/results` (`resources/messages/batches.py`). Wiring: not used. | First-class SDK surface but an async bulk-submission workflow, not a `complete()`/`stream()` capability — noted for completeness; not a per-call contract gap. |
| _(catch-all)_ Server-side tools (web_search / code_execution / web_fetch) | Yes | No | No | contract-level | SDK: typed server-tool params (`web_search_tool_*`, `code_execution_tool_20260120_param.py`) + typed result blocks in `ContentBlock` (`content_block.py`: `WebSearchToolResultBlock`, `CodeExecutionToolResultBlock`, …). Wiring: not declared; result blocks dropped (loop handles only `text`/`tool_use`). | First-class API surface. No contract param to declare them and no `Message` field for the result blocks. contract-level (low priority for this mission). |

**Axis-scoring notes:** "Contract-representable" is scored solely against the frozen contract-surface inventory in `flight-log.md` (`base.py` citations) — not re-derived. Every gap that adds a durable `Message`/`TokenUsage` field (extended thinking, prompt-cache usage, vision/document content, citations) is contract-level **and** implies a `the_one/db/codec.py` change per the inventory's persistence round-trip note. Request-side-only gaps (structured outputs, reasoning-effort, stop sequences, count-tokens) are contract-level but need no codec change.
