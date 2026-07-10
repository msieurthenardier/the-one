# Flight: Multimodal `Message.content` — vision (image) inputs (A2)

**Status**: completed
**Mission**: [LLM Provider Layer Hardening & Capability Completeness](../../mission.md)

## Contributing to Criteria

- [ ] **Each prioritized capability gap is either implemented behind the
      `LLMProvider` contract or explicitly deferred** with a recorded reason.
      *(This flight implements backlog **A2** — widening `Message.content` to carry
      image inputs mapped to each provider's native multimodal wire shape. With A4
      (Flight 11) done, A2 is the last substantive capability item; after it, only
      the A3/A5/B1–B4 deferral sweep remains to close #3.)*
- [ ] The `LLMProvider` contract and provider-shape-portability convention are
      preserved. *(A2 **widens the canonical `Message` contract** — the one
      capability that legitimately requires a contract change. It stays
      provider-neutral: a canonical `ContentBlock` type each provider maps to its
      native shape — see DD2. The `str`-only assert becomes conditional, not
      removed; the `agents.md` convention is updated to match — DD2/L01.)*

---

## Pre-Flight

### Objective

Widen the canonical `Message.content` from bare `str` to `str | list[ContentBlock]`
so a user turn can carry **image inputs** alongside text, and map that structured
content to each provider's native multimodal wire shape (Anthropic image content
blocks, OpenAI `image_url` content parts, Ollama native `images` / `/v1` base64
parts; OpenRouter inherits OpenAI). This is a protocol migration to the canonical
`Message` dataclass — the blast radius (every `str`-assuming consumer of
`.content`) is the real work, and the recon has mapped it. Verification is hermetic
(unit + an extended cross-provider conformance matrix that injects image-content
messages); a live vision HAT is an **optional** leg because there is **no ingestion
producer today** (DD1/DD6).

### Open Questions

- [x] **Scope — capability-only, or capability + a live ingestion surface?** →
      **Capability + native-wire mapping, images-first** (operator best-judgment,
      2026-07-08; adjustable at review). Mirrors A4's "capability delivered, wire
      proven" bar and A2's original split rationale (no in-scope ingestion path). A
      minimal chat image-upload producer + Anthropic-vision HAT is an **optional
      promotable leg** (L08). See DD1.
- [x] **Content-block representation — raw `dict` or a canonical dataclass?** →
      **Canonical `ContentBlock` dataclass** mirroring `ThinkingBlock`
      (provider-neutral; each provider maps to native). See DD2. *(Recon fork: dicts
      round-trip the codec free; the dataclass needs a codec encoder/decoder but
      matches the provider-shape-portability convention. Recommended dataclass;
      overridable at review — the whole L02 codec leg collapses if we pick dicts.)*
- [ ] **[wire-format gate — resolve in L01, before any provider wiring]** For each
      provider, the exact accepted image wire shape + base64-vs-URL support on the
      current target lineup, per first-party docs (the F10-Rec-1 / A4-DD5 gate). The
      recon pinned the SDK-stub shapes (Anthropic `ImageBlockParam`
      base64/url; OpenAI `image_url` part; Ollama native `images` base64 / `/v1`
      base64-only) — L01 confirms per-model acceptance + records the premise.
- [ ] **Documents/PDF** — deferred to a follow-up (distinct wire shape, patchier
      provider support). Images-first. → Out of Scope.

### Design Decisions

**DD1 — Scope: capability + native-wire mapping, images-first; ingestion optional.**
- Choice: widen the contract + map image content to each provider's native wire
  shape + prove hermetically. Documents/PDF and a live ingestion producer are
  out-of-scope-but-recorded; a minimal chat image-upload + Anthropic-vision HAT is
  an optional promotable leg (L08).
- Rationale: the mission's capability-completeness bar is "the layer wires through
  what the SDK exposes," met by native mapping + hermetic proof (mirrors A4). Recon
  §6 confirmed **zero ingestion producers** (`Agent.step` is `str`-typed;
  `app.py:2163` reads `payload.get("message","")`), so live vision can't be HAT'd
  without building a producer — a product feature separable from the capability.
- Trade-off: without L08, image support is real and wire-proven but has no user-
  facing entry point yet. Recorded as intended shape.

**DD2 — Canonical `ContentBlock` dataclass union (provider-neutral), not raw dicts.**
- Choice: introduce a provider-neutral content-block **union** — **`TextContent`**
  (a `text: str`) **and `ImageContent`** (`media_type`, plus a base64 `data` or a
  `url`) — mirroring the `ThinkingBlock` precedent (`base.py`);
  `Message.content: str | list[ContentBlock]`. **`TextContent` is load-bearing, not
  optional**: because content is `str` XOR `list` (there is no separate text field),
  a user's own typed text must live in the list as a `TextContent` block whenever an
  image is present. Each provider's projection maps blocks to its native shape (DD5).
  The `__post_init__` `str`-assert becomes **conditional** — a
  `list[ContentBlock]` on a USER message is legitimate (the assert validates
  `all(isinstance(b, ContentBlock) for b in content)`); a bare non-str non-list, or
  a list of non-blocks, still asserts.
- Rationale: the `provider-shape-portability` convention (`agents.md:192-218`) makes
  canonical types provider-neutral dataclasses; raw dicts would be ad-hoc/provider-
  shaped and reintroduce the exact "assert content is str, non-str is a parser
  defect" invariant this migration modifies. Type-safe, matches `ThinkingBlock`.
- Trade-off: dataclass content does **not** round-trip the codec unchanged — needs
  a `_content_block_to_dict`/`_from_dict` pair (L02), mirroring
  `_thinking_block_to_dict` (`codec.py:60-75`). (A raw-dict design would skip L02
  entirely — recorded as the alternative; overridable at review.)

**DD3 — Content blocks only on USER-role messages.**
- Choice: `list[ContentBlock]` content is legitimate only on `Role.USER`. SYSTEM
  (Anthropic `system` is a str-only API param), ASSISTANT, and TOOL messages stay
  `str`-content. The conditional assert enforces this.
- Rationale: images/documents are *inputs*; the whole point is user-turn ingestion.
  Recon §2 confirmed the assistant/tool-side `str`-assuming consumers
  (`_inference.py:283/343` classifier parse, `post_step_metadata.py:119`
  `.startswith`, `app.py:1920` `str.join`) stay valid under this scoping — the
  blast radius shrinks to the USER-turn projection + a handful of genuinely
  user-content-reading sites (L03).
- Trade-off: assistant-generated structured content (rare; e.g. a model emitting an
  image) is out of scope — a separate future concern, like the streaming-delta
  interleave DD2 deferred in F10.

**DD4 — Widen `build_user_message_content` to be shape-aware (shared prefix path).**
- Choice: widen the shared helper (`build_user_message_content`) to
  `str | list[ContentBlock]` → **same-shape-out**: for `str` content, unchanged
  (returns a native-ready `str` with the peer/channel bracket prefix); for `list`
  content, return canonical `list[ContentBlock]` with a **separate prepended
  `TextContent` block** carrying the peer/channel prefix (a distinct block, NOT
  merged into the user's own leading text block — chosen so L04–L06 don't each
  re-decide; two adjacent text blocks render fine on all providers). Each provider's
  USER branch becomes a simple `isinstance` fork: `str` → today's path;
  `list[ContentBlock]` → the new native-mapping path (DD5). All three providers call
  the one widened helper.
- Rationale: keeps the peer/channel-attribution projection (M11) in ONE place
  rather than re-implemented per provider. **Supersedes** the Anthropic forward-
  comment (`anthropic_provider.py`, the `build_user_message_content` forward-note)
  that assumed the helper stays str-only and a multimodal branch must avoid it —
  widening the helper is cleaner than forking it away.
- Trade-off: the helper's contract changes from `-> str` to
  `-> str | list[ContentBlock]`; its call sites are all in the provider projections
  being reworked anyway (L04–L06), each guarded by the `isinstance` fork.

**DD5 — Canonical → per-provider native mapping (finalized against L01 doc-gate).**
- Each canonical block maps to native: **`TextContent`** → the provider's text
  block/part (Anthropic `{type:"text",text}`, OpenAI `{type:"text",text}`, Ollama
  text) — this includes the DD4 prefix block, which is a canonical `TextContent` and
  gets native-mapped like any other; **`ImageContent`** → Anthropic
  `{type:"image", source:{type:"base64"|"url", ...}}`, OpenAI/OpenRouter
  `{type:"image_url", image_url:{url}}` (base64 data-URL or URL), Ollama native
  message-level `images:[base64]`, Ollama `/v1` base64 `image_url` part.
- **base64 vs URL (resolves the recon/review question):** the canonical
  `ImageContent` carries **either** a base64 `data` or a `url`. **base64 is the
  universal path** — Anthropic + OpenAI + both Ollama paths accept it. A `url` maps
  natively on Anthropic + OpenAI only; **Ollama has no remote-URL support**, so a
  `url`-bearing block on an Ollama route is a **documented per-provider gap**
  ("Acceptable variation" — no client-side fetch/re-encode this flight). The
  optional L08 producer base64-encodes, so in practice the universal path is
  exercised; `url` support is best-effort pass-through where the provider allows it.
- Exact shapes + per-model acceptance pinned in L01, not assumed.

**DD6 — Hermetic verification; live vision HAT optional.** Unit tests + an extended
cross-provider conformance matrix inject an image-content `Message` and assert each
provider projects the correct native wire shape (the A4-L05 pattern; no producer
needed). L08 (optional) adds a minimal chat image-upload producer + a live Anthropic
vision HAT (Claude is vision-capable; runnable with the operator's Anthropic key).

### Prerequisites

- [ ] **L01 doc-gate complete** — per-provider accepted image wire shapes +
      base64/URL support recorded as a flight premise before provider wiring.
- [ ] Hermetic tests inject structured `Message`s directly (no producer needed);
      no live calls in `make test`.
- [ ] **For the optional HAT (L08) only**: live Anthropic key + a vision-capable
      Claude model; backend built from this branch (F10/F11 lesson).

### Pre-Flight Checklist
- [ ] All open questions resolved *(the wire-format gate is the L01 deliverable by
      design; documents deferred; scope + representation decided as best-judgment
      defaults pending operator confirmation at review)*
- [x] Design decisions documented
- [ ] Prerequisites verified
- [x] Validation approach defined (conformance extension + optional live HAT)
- [x] Legs defined
- [x] Design-reviewed (Phase 5b: Architect/Opus approve-with-changes; incorporated)
- [x] Operator sign-off (2026-07-08) — spec approved as presented: **L08 optional**
      (not promoted), **dataclass content blocks** (DD2 confirmed). Flight → `ready`.

---

## In-Flight

### Technical Approach

Follow the A4 playbook (doc-gate first, then contract, then per-provider mapping,
then conformance), adapted for a contract migration rather than a config surface.
L01 lands the canonical `ContentBlock` type, widens `Message.content` + the assert +
`build_user_message_content`, and records the wire-format premise — touching no
provider request path yet. L02 makes the persistence codec round-trip structured
content (the dataclass encoder/decoder, per DD2). L03 hardens the ~6 genuinely
`str`-assuming consumers the recon found (`agent/core.py:328` `.strip()`;
`connectors/_inference.py:135` history f-string; `connectors/post_step_metadata.py:119`
`.startswith`; `interfaces/cli.py:79` `Markdown()`; `interfaces/web/app.py:1920`
`str.join` — the last two/three are assistant-side and low-risk under DD3 but made
shape-safe defensively). L04–L06 fork each provider's USER-turn projection into a
content-list path (mirroring the list-of-blocks shape the Anthropic ASSISTANT branch
`anthropic_provider.py:479-497` already builds); OpenRouter inherits OpenAI's fix
(no override). L07 extends the cross-provider conformance suite to assert an
image-content message reaches each provider's request in the correct native shape.
L08 (optional) adds a minimal ingestion surface + a live Anthropic vision HAT.

The `str`-content path stays byte-identical throughout (every widening is additive
under a shape check), so existing sessions/persistence/tests are unaffected — the
same additive-back-compat discipline `ThinkingBlock` used in F10.

### Checkpoints
- [ ] Canonical `ContentBlock` landed; `Message.content` + assert +
      `build_user_message_content` widened; wire-format premise recorded; `str` path
      byte-identical (L01)
- [x] Structured content round-trips the persistence codec (L02)
- [x] All `str`-assuming `.content` consumers shape-hardened (L03)
- [ ] Each provider projects an image-content USER turn in its native shape
      (L04–L06); OpenRouter inherits OpenAI
- [ ] Conformance matrix asserts image-content → native wire shape across providers
      (L07)
- [ ] *(optional)* Live Anthropic vision HAT: a real image in, a grounded answer out
      (L08)

### Adaptation Criteria

**Divert if**:
- L01 doc-gate reveals a provider's image surface can't map to the canonical block
  cleanly (e.g. a provider needs a fetch/upload handshake rather than inline
  base64/URL) — narrow to the providers where it maps, document the gap.
- The codec round-trip forces a schema/migration change beyond an additive
  encoder/decoder — stop and re-confirm scope (persistence migrations are their own
  risk class).

**Acceptable variations**:
- Per-provider base64-vs-URL differences (Ollama `/v1` base64-only) — documented, not
  forced.
- Reordering L04–L06 (providers independent).

### Legs

> **Note:** Tentative; planned and created one at a time as the flight progresses.

- [x] `content-block-contract-and-doc-gate` — L01: canonical `ContentBlock` union
      — **both `TextContent` and `ImageContent`** (DD2) — + widen `Message.content`
      (`str | list[ContentBlock]`) **and the `Message.user()` factory signature**
      (`base.py`, currently `content: str`) + conditional assert
      (`all(isinstance(b, ContentBlock))`) + shape-aware `build_user_message_content`
      returning a **separate prepended `TextContent` prefix block** for list input
      (DD4) + wire-format premise (DD5) + `agents.md` `provider-shape-portability`
      convention update (assert now conditional); unit tests; `str` path
      byte-identical. No provider request wiring.
- [x] `codec-content-round-trip` — L02: `_content_block_to_dict`/`_from_dict` in
      `codec.py` (mirror `ThinkingBlock`); structured-content persist+replay tests.
      *(Collapses to a verification-only leg if the operator picks raw-dict blocks.)*
- [x] `str-consumer-hardening` — L03: make the recon's ~6 `str`-assuming `.content`
      consumers shape-aware (extract text parts / graceful non-crash); tests pinning
      each.
- [x] `anthropic-image-projection` — L04: fork `_to_api_message` USER turn into an
      image-content-block path (`ImageBlockParam`); fixtured tests.
- [x] `openai-openrouter-image-projection` — L05: fork OpenAI `_to_api_message` USER
      turn (`image_url` part); confirm OpenRouter inherits; fixtured tests.
- [x] `ollama-image-projection` — L06: native `images:[base64]` + `/v1` base64
      `image_url` across both Ollama paths; document `/v1` no-remote-URL; tests.
- [x] `conformance-matrix-multimodal` — L07: extend the cross-provider conformance
      suite — an image-content USER message projects to each provider's native wire
      shape (hermetic; the A4-L05 pattern).
- [x] `ingestion-and-vision-hat` *(optional)* — L08: minimal **send-path** producer
      — a chat-input image attach/paste control → a new WS payload shape (images
      alongside `message`) → `app.py` + `Agent.step` construct a list-content USER
      `Message` — + a live Anthropic vision HAT (real image in → model returns a
      grounded answer). **Scoped to the send path + the model receiving the image**;
      the *display* round-trip (rendering the user's own image bubble, the
      `messages_to_ui_events` USER-branch projection, and session replay of
      list-content — the frontend today renders user content via `textContent`, so a
      list would coerce to `[object Object]` garbage, per the design review) is an
      **explicit follow-up**, NOT this leg. This keeps the HAT runnable (the model
      sees the image) without the full frontend rendering + replay migration.
      Promote at review if the operator wants the working feature now.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (full suite + multimodal conformance matrix)
- [ ] `the_one/agents.md` `provider-shape-portability` convention updated (assert now
      conditional; canonical `ContentBlock`)
- [ ] Mission criterion #3 advanced (A2 implemented; documents + ingestion deferrals
      recorded)

### Verification
- **Hermetic**: unit tests for the `ContentBlock` contract + codec round-trip + the
  hardened consumers; the extended conformance matrix asserts an image-content
  message reaches each provider's request in the correct native shape via the
  scripted transport.
- **Live (optional HAT, L08)**: with a real image attached, a vision-capable Claude
  model returns an answer grounded in the image; backend confirmed built from the
  current tree first.

### Out of Scope (this flight)
- **Document/PDF inputs** — distinct native wire shape; images-first (follow-up).
- **A live ingestion surface**, unless L08 is promoted (DD1) — capability is
  wire-proven hermetically without it.
- **Frontend image-bubble display + list-content replay** — even if L08 is promoted,
  it covers the *send* path + the model receiving the image, NOT rendering the
  user's own image bubble or the `messages_to_ui_events` USER-branch projection /
  session replay of list content (the frontend renders user content via
  `textContent` today — a list coerces to `[object Object]`). Explicit follow-up.
  **Prerequisite coupling (flagged by L02 review):** `messages_to_ui_events`
  (`codec.py:298-309`) passes `content` opaquely — it is safe *only* while there is
  no producer. **Hardening `messages_to_ui_events` is a prerequisite of any producer
  (L08 / this frontend follow-up)** and must land before list content can be
  constructed at runtime.
- **Assistant-generated structured content** and **interleaved streaming blocks**
  (DD3) — user-input-scoped this flight.
- **Client-side image validation / re-encoding / URL→base64 fetch** — pass-through;
  the provider's own limits are the guard (mirrors A4 DD2's pass-through posture);
  a `url` on an Ollama route is a documented gap (DD5), not fetched here.
- **The opt-in structured-output schema normalizer** (F11 debrief Rec 5) — that was
  mis-scoped to A2; A2 touches multimodal *content*, not structured outputs. It
  stays with the structured-output surface (a separate follow-up / the deferral
  sweep), NOT bundled here. *(Correction confirmed at F12 design review.)*
