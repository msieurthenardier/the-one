# Flight Log: Chat Restructure — Components, Streaming & Markdown

**Flight**: [Chat Restructure — Components, Streaming & Markdown](flight.md)

## Summary

Flight in planning. Designed 2026-04-27, immediately following the F3 debrief. Scope is the F3-debrief's recommended re-scope of the original "Chat Alignment" framing: chat.js component split (closes the 782-LOC critical-mass concern flagged at F3 close), shared component CSS lift (consolidates 313 per-area selectors and the F2-debrief `// PREFIX` / `.section-marker` items that F3.5 was originally going to absorb), hand-rolled markdown library (`App.markdown`), streaming infrastructure across all four providers (Anthropic, OpenAI, Ollama, mock), markdown + streaming integration in chat, and a final HAT pass.

---

## Leg Progress

_(Populated during execution)_

---

## Decisions

_(Runtime decisions not in original plan — populated during execution)_

---

## Deviations

_(Departures from planned approach — populated during execution)_

---

## Anomalies

_(Unexpected issues encountered — populated during execution)_

---

## Session Notes

### 2026-04-27 — Flight design

- F4 designed in interactive interview with the user, immediately after the F3 merge to `main` (`8c08601`).
- User explicitly chose hand-rolled markdown over vendored (Snarkdown / Marked) — supply chain risk + extension flexibility.
- User explicitly added streaming to scope (was "future flight" candidate at F3 debrief; the user's wording in this session: *"lets put it in scope, its good to have, might as well tackle it."*).
- 6-leg breakdown: chat.js component split → shared component CSS lift → hand-rolled markdown library → streaming infrastructure → markdown+streaming integration → comprehensive review + HAT.
- Per F3-lessons-learned: HAT leg is verification-style (not discovery-via-HAT), since F4 doesn't have unknown user intents to elicit; the 6-leg HAT scope-cap is "walk the surface, surface awkward bits, apply fixes inline" with explicit divert-to-F5 for any "while we're here…" additions.

### 2026-04-27 — Architect design review

Spawned an Architect (Opus) for codebase-validated design review per the `/flight` skill's Phase 5b. Result: **approve with changes** — 3 HIGH issues, 5 MEDIUM, 2 LOW, plus suggestions and questions. All HIGH and MEDIUM issues incorporated below; LOW issues + key suggestions also applied.

**HIGH issues fixed in spec**:
1. **Streaming providers' WS contract vs server-side persistence contract** — original spec said "no final assistant event from streaming providers". Architect flagged that `_process_and_broadcast` (`app.py:430-447`) and `result_messages` (returned by `POST /api/chat/send` at `app.py:597-598`) BOTH depend on the assistant event being added to session history. Fix: WS contract = chunks-only-no-final-assistant; persistence contract = final-assistant-synthesized-server-side. `_process_and_broadcast` accumulates `chunk.content`; on `is_final`, calls `session.add_event({"type": "assistant", "content": <accumulated>})` and appends the synthesized `Message` to `result_messages`. The synthesized event is NOT broadcast (client already has the text from chunks). Distinction documented in Open Questions + leg 04 description.
2. **"Ollama uses the existing `ollama_api` stream helper" was wrong** — `ollama_api.py` only has `pull_model` (model-pull progress, not chat). New work: `ollama_api.chat_stream(provider_url, body) → AsyncIterator[dict]` parsing SSE `data:` lines via `httpx.AsyncClient().stream(...)` (~30-50 LOC, mirrors `pull_model`). Spec updated; `ollama_api.py` added to Files Affected.
3. **F3 `BadRequestError` temperature-retry must be ported into the Anthropic streaming path** — `anthropic_provider.py:48-57` handles it for `complete()` but the streaming variant hits the same deprecation on Opus 4.x / Sonnet 4.x. Spec now requires the retry on `client.messages.stream(...)` calls + an explicit unit test.

**MEDIUM issues fixed in spec**:
4. **chat.js extraction targets include closure-bound functions** — `renderWelcomeList` and `buildSessionItem` close over WS lifecycle state (`startSessionWith`, `joinSession`, `currentSessionId`, `ws`). Original spec called them "pure helpers"; they aren't. Fix: leg 01 helper signatures now distinguish PURE helpers (take inputs, return DOM) from CALLBACK-INJECTED helpers (receive callbacks for what would otherwise be closure references). Each helper signature documented explicitly in leg 01.
5. **21 inline `style.display =` setters** corrected to **19** — verified count via `grep -c '\.style\.display' admin.js`. Updated in Open Questions, leg 02, and File Layout.
6. **313 selector count clarification** — kept the count (correct against actual selector usage); the regex the spec implied wouldn't reproduce because rules are nested under `@layer areas { ... }`.
7. **`.chip` is studio-only**, **`.btn-outlined-cyan` / `.btn-filled-cyan` / `.btn-muted-destructive` are NEW vocabulary** — not deduplications. Spec now distinguishes "Genuine deduplication" (3+ existing impls) from "Vocabulary invention" (NEW canonical names that replace ad-hoc selectors) from "Single-use lift" (`.chip`). Leg 02 enumerates the rename map for the vocabulary-invention category.
8. **`.empty-state` actually has 5 sites** (chat-welcome-empty, agent-empty, editor-empty, admin-provider-empty, admin-pf-models-empty) — confirmed as a genuine consolidation target.

**LOW issues fixed in spec**:
9. **`markdown.js` placeholder for leg 01** — added a 3-line stub (`(function(){window.App=window.App||{};window.App.markdown={};})();`) so any leg-01/02 test referencing `App.markdown` doesn't trip; leg 03 replaces with the real implementation.
10. **HAT verification of thinking indicator for non-streaming providers** — leg 06 HAT script now distinguishes streaming-provider behavior (indicator clears on first chunk) from non-streaming-provider behavior (indicator must still appear briefly until the lone chunk arrives). Critical for default-impl `stream()` paths.

**Suggestions absorbed**:
- **Nested-emphasis algorithm: non-recursive in v1** committed in leg 03. `***word***` renders as `<em><strong>word</strong></em>` (outer-em-first); test corpus locks it. Full CommonMark "left/right flanking delimiter run" algorithm is v2+ scope.
- **Per-provider streaming chunk granularity documented** — Anthropic `text_stream` deltas; OpenAI `choices[0].delta.content`; Ollama same shape via SSE; mock yields configured chunks. Documented in Open Questions.
- **`StreamChunk.usage` field added** explicitly so the telemetry overlay update path lands at end-of-stream cleanly. OpenAI streaming requires `stream_options={"include_usage": True}` — documented in leg 04.
- **Code-block copy-button accessibility** — `aria-label="Copy code"` on the `<button>`, `aria-hidden="true"` on the icon, "Copied!" flash via existing `App.showFlash` helper. Documented in leg 03.

**Questions answered in spec**:
- Same render function for streaming + non-streaming paths: yes — `App.chat.renderMessage(cls, text, attribution, opts)` with `opts.renderMarkdown: bool`. Documented in Open Questions + leg 05.
- OpenAI usage opt-in: yes — `stream_options={"include_usage": True}` required. Documented in leg 04.
- `_save_session_to_db` change: NOT needed — the synthesized `assistant` event reaches `add_event` (which `_save_session_to_db` reads from), preserving the existing persistence path.

**Skipped second review pass** — per `/flight` skill protocol, only clarifications and explicit-decision additions were applied (no new technical approach). Proceeding with codebase-validated spec.

### 2026-04-27 — Flight ready

Status flipped `planning` → `ready`. F4 prerequisites satisfied (F3 merged at `8c08601`; baseline test counts confirmed at 393 + 32). Mission flight list retitled from "Chat Alignment" → "Chat Restructure: Components, Streaming & Markdown" with link to this spec. Awaiting `/agentic-workflow` kickoff to enter `in-flight`.

### Flight Director Notes

**Phase file loaded**: Project-side `the-one/.flightops/agent-crews/flight-design.md` (same as F1/F2/F3).

**Auto-mode flight-design**: Open questions resolved at design time using the F3 debrief as the substantive input — every design decision is traceable to either the F3 debrief, the user's verbatim direction in this session's interview, or a code-level constraint surfaced at code interrogation.

**Visual snapshot strategy**: F4 cosmetic changes (chat.css migration to shared components, markdown-rendered code blocks) will drift local visual baselines. Per the F3-introduced policy, baselines are gitignored — no flight-level coordination needed; devs regenerate locally via `pytest -m pixel --snapshot-update`. CI continues to skip the pixel marker.

**Browser-test additions planned**:
- Markdown library corpus: ~50-80 parametrized cases via `tests/browser/test_markdown.py` (loads any page, calls `page.evaluate("App.markdown.render(input).outerHTML")`, asserts shape)
- Streaming flow: `tests/browser/test_flow_streaming.py` — uses mock provider's new `stream_chunks` + `delay_ms` knobs to deterministically exercise the chunk-accumulation + done-render-as-markdown path
- Component migration: existing browser tests must continue passing without modification (regression guard)

Total post-F4 browser test count target: ~40+ (was 32 pre-F4). Unit-test count: 393 + new StreamChunk + provider streaming tests (~5-10 new).
