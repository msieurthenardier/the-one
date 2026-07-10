# Flight Debrief: Multimodal `Message.content` — vision (image) inputs (A2)

**Date**: 2026-07-10
**Flight**: [Multimodal Message.content (A2)](flight.md)
**Status**: completed (landed + merged, PR #151 → `main` `2daa539`; release v0.3.2)
**Duration**: 2026-07-08 (planning) → 2026-07-10 (merged, incl. live vision HAT)
**Legs Completed**: 8 of 8 (L08 = the operator-promoted ingestion producer + live HAT)

## Outcome Assessment

### Objectives Achieved

Delivered backlog **A2** — widened the canonical `Message.content` from `str` to
`str | list[ContentBlock]` (provider-neutral `TextContent`/`ImageContent`) so a user
turn carries **image inputs**, mapped to each provider's native multimodal wire
shape (Anthropic content blocks, OpenAI/OpenRouter `image_url` parts, Ollama native
`images:[base64]` / `/v1` base64). The `str` path is byte-identical throughout — no
persisted-session migration (legacy rows decode unchanged). Proven hermetically (an
extended cross-provider conformance matrix with an OpenAI≡OpenRouter≡Ollama-`/v1`
parity assertion) **and live**: the operator attached images in the chat and Claude
answered grounded in them.

### Mission Criteria Advanced

- **Criterion #3** (each prioritized capability implemented-or-deferred):
  **substantively complete** — **A1** (F10), **A2** (this flight), **A4** (F11) all
  landed+merged. Only the low-priority **A3/A5/B1–B4** remain, each needing a
  *recorded deferral*, not implementation.
- Constraint (provider-shape-portability preserved): **held** — `ContentBlock` is a
  provider-neutral dataclass; the ABC signature is unchanged; `agents.md`'s
  convention was updated in place.

## What Went Well

- **The hermetic-first, `str`-byte-identical discipline (DD1/DD6) worked** — the
  capability landed L01–L07 with zero producers, and every byte-identical claim is
  backed by a regression test, not prose.
- **The Leg-01 doc-gate (DD5) prevented wire-format surprises** — like A4, pinning
  the image shapes from SDK stubs + docs up front produced **zero mid-flight mapping
  corrections** across L04–L07. It correctly separated structural facts (pinned)
  from per-model acceptance (flagged HAT-confirm).
- **DD3's USER-turn-only scoping was reconned rigorously** — the ~6-consumer blast
  radius was independently re-confirmed twice (Phase-5b review narrowed it to one
  genuine USER-content reader; L03 re-grepped project-wide and found one more,
  already tracked). No hole surfaced.
- **Batching the three independent provider legs (L04–L06)** — designed + reviewed +
  implemented in parallel (distinct files; FD wrote the shared artifacts) — was clean
  and fast, with L07's parity assertion as the drift net for the deliberate
  OpenAI-compat mapping duplication.
- **The live HAT did its job** (operator: "the HAT worked as expected — we almost
  always find a little something"): it proved vision end-to-end, drove the attach-UX
  to a good place (silent → preview → chicklets-above-input + multi-image), and
  surfaced a real bug (a live `FileList` collapsing when the input `.value` cleared).
- **Cleanest metrics delta the mission has recorded** — +80 passed over Flight 11,
  *exactly* the 80 new hermetic tests, with zero unexplained drift and zero
  regressions (see Test Metrics).

## What Could Be Improved

### Process
- **L08's recon missed the existing Playwright browser-test suite** (`tests/browser/`,
  `make test-browser`) — which is documented in the project's own top-level
  `CLAUDE.md` and named in L07's own leg spec — and proposed a weaker source-scan
  test plan; the design review caught it. Recon depth was uneven: excellent for the
  *provider-SDK-shape* surface (bounded, documentable), shallower for *this project's
  own runtime/test-infra map*. → a standing recon-checklist item (Recommendations).
- **"Capability-then-producer-later" left two latent bugs dormant in `main` for
  ~36h.** Because DD1 deferred the producer, the `json.dumps` crash + the
  title-corruption (both live in `codec.py`/`app.py` the moment content could legally
  be a list) weren't exercised by any test until L08 built a producer. The operator
  assessed this as acceptable ("it worked out; not worried") — so the fix is a
  *cheap, optional* net, not a mandate: a producer-independent hermetic smoke that
  pushes a synthetic list-content `Message` through `messages_to_ui_events` + the
  broadcast path would catch this class at L02/L03 time without needing a producer.

### Technical
- **`ImageContent.__post_init__` still uses a bare `assert`** (`base.py:77`) for the
  data-or-url guard — the exact `-O`-strippable pattern L01 *fixed* three lines away
  on `Message`'s role guard, in the same file, same flight. Live debt (narrow: a
  neither-data-nor-url `ImageContent` is a construction-site defect, not user input).
  Two-line fix. *(Note: flagged by the L08 batch-review verdict, recorded in the PR
  body — not in the committed leg/log artifacts, so a future reader won't find it
  there; hence this entry.)*
- **Two parallel OpenAI-compat duplications now exist** in the same two files:
  F11's `_a4_request_kwargs`/`_v1_a4_kwargs` (request kwargs) and F12's
  `_content_block_to_api` pair (content blocks), each with its own "copy #2, lift at
  rule-of-three" forward-note. Code-lift isn't yet warranted (rule-of-three not
  triggered), and L07's parity test catches drift — but a genuine 3rd `/v1` provider
  would now trigger **two** simultaneous lifts, and the judgment has been
  re-derived twice. → promote to a named convention (Recommendations).
- **`content_to_text` is now load-bearing for *not crashing*** at three sites
  (inference render, live broadcast, replay) — not just display. A future
  frontend-rendering follow-up could remove/bypass it thinking it's a display
  nicety. The `why` comments at `app.py:1461` / `codec.py:356` mitigate; add a
  cross-reference at any removal site.

### Documentation
- The rule-of-three forward-note lives only in code comments (now across two
  duplicated pairs) — F11's debrief already flagged the comment-only status; F12
  repeated the pattern without promoting it. → an `agents.md` convention.

### Test Metrics
`make test-unit` at `2daa539`: **3976 passed / 10 skipped / 660 deselected / 0
failed**, 357.25s. Browser suite (`test_flow_chat_image_attach.py`, `-m browser`):
**5 passed**, 9.65s. **Clean flight-to-flight delta from Flight 11** (3896 → 3976;
no intervening mission): **+80 passed = exactly the 80 new hermetic test functions**
(L01 27 / L02 14 / L03 3 / L04 5 / L05 8 / L06 9 / L07 5 / L08 8), zero unattributed
drift, zero regressions; **+5 deselected** = the 5 new browser tests; wall-clock
+5.4% (proportionate, inside the historical 296–392s band). The known aiosqlite
teardown warning appeared once (stable non-failure disposition, carried since F10).
**Coverage gap**: the vision *round-trip* (model actually grounds on the image) has
**no committed test** — only the one-off HAT prose. Hermetic proves *shape*, never
*grounding*.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L08 promoted from optional → built mid-flight | Operator wanted to see vision live | No — operator-driven; keep "optional producer" as a pattern (with the smoke-test net) |
| Two latent bugs (WS crash, title-corruption) fixed in L08 | Deferred (correctly tracked as an L02 "expiry") until a producer existed | The *tracking* worked; add a producer-independent smoke so discovery isn't gated on a producer |
| L08 test plan changed source-scan → Playwright browser test | Design review found the existing `tests/browser/` suite the recon missed | Yes — recon-checklist item for existing test infra |
| Attach UX iterated across the HAT (chip → chicklets + multi-image) | Live operator feedback | No — this is the HAT working as designed |

## Key Learnings

- **"Zero producers" ≠ "no producer-shaped bugs."** A contract widening makes a new
  value *legal* everywhere the moment it lands; the consumer-side breakage exists
  from that instant, whether or not anything constructs the value yet. Capability-
  only flights should still smoke the full read path with a synthetic value.
- **Recon quality tracks the surface's documentability.** Provider-SDK-shape recon
  (doc-gate) was excellent; own-runtime/test-infra recon (L08) undercounted what was
  already documented in `CLAUDE.md`. Recon should consult the project's own
  methodology docs, not just the code.
- **Boundary-projection (`content_to_text`) is a good tactical fix but has a fork
  point**: fine while the frontend only *displays* what was sent; a dead-end (lossy
  `"[image]"`) the moment the UI needs to *reconstruct/re-edit* image content — at
  which point the codec's `_content_block_to_dict` encoder should feed the event
  instead. Decide this before scoping the thumbnail-rendering follow-up.

## Recommendations

1. **Author a `/behavior-test` spec for the vision round-trip** (highest value). The
   only proof the model *grounds* on the image is a one-off HAT captured as prose.
   The mission has precedent (F07 chat-loop, F03 gemma-tool-use, F10 thinking).
   Convert L08 HAT steps 2–5 (attach → grounded reply → image-only → rejoin-no-crash)
   into a re-runnable spec — durable coverage for the one thing hermetic tests can't
   prove.
2. **Fix the `ImageContent` bare `assert`** (`base.py:77`) → `raise AssertionError`,
   matching `Message`'s role guard. Two lines; closes the `-O` gap the flight's own
   thesis was about.
3. **Promote the OpenAI-compat mapping duplication to a named `agents.md`
   convention** (e.g. `openai-compat-provider-mapping-duplication`) citing both
   pairs (request-kwargs, content-block), so the rule-of-three lift is decided once
   for both at a genuine 3rd `/v1` provider — not re-litigated a third time.
4. **Recon-checklist item**: before a leg's test plan assumes a source-scan, grep
   the project's own methodology docs (`CLAUDE.md`/`agents.md`) for existing test
   infrastructure (`test`/`browser`/`HAT`). Would have caught the L08 Playwright miss
   pre-design-review.
5. *(Optional — operator assessed the pattern acceptable)* a producer-independent
   hermetic smoke for capability-only flights: push a synthetic list-content
   `Message` through `messages_to_ui_events` + the broadcast path, so producer-shaped
   bugs surface without a producer.
6. **A2's own follow-ups** — own-image bubble thumbnail + full `messages_to_ui_events`
   structured rendering are **one** coupled unit (thumbnail without fixing replay
   just relocates the lossy-string problem); attach-while-busy + size limits can ride
   along; **documents/PDF is a separate flight** (distinct wire shape, own doc-gate).
   Keep them in the mission backlog; don't fold into A3 (prompt caching — orthogonal).

## Action Items

- [ ] **Author `/behavior-test vision-round-trip` spec** (Rec 1) — inline in the next
      planning conversation touching this surface.
- [ ] **Fix `ImageContent.__post_init__` bare `assert` → raise** (Rec 2) — trivial;
      can ride the next flight touching `base.py`.
- [ ] **`agents.md`: `openai-compat-provider-mapping-duplication` convention** (Rec 3).
- [ ] **Add the recon-checklist item** to the mission's process notes / next flight's
      recon (Rec 4).
- [ ] *(Mission backlog)* A2 UI follow-ups (thumbnail + full replay rendering =
      one flight; documents/PDF = separate) — recorded, unscheduled (Rec 6).
- [ ] *(Optional)* producer-independent smoke-test pattern (Rec 5) — low priority per
      operator.
