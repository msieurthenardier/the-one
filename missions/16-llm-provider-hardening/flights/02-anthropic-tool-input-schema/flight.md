# Flight: Anthropic Tool `input_schema` Compatibility (#122)

**Status**: completed
**Mission**: [LLM Provider Layer Hardening & Capability Completeness](../../mission.md)

## Contributing to Criteria
- [ ] A tool whose `input_schema` uses top-level `oneOf/allOf/anyOf` (or omits a
      top-level `type`) no longer fails the whole Anthropic turn — the schema is
      sanitized before send, and if a schema genuinely can't be sent the failure
      names the offending tool rather than a bare index. *(#122)*
- [ ] No agent framework is added and the provider layer still wraps official SDKs;
      the `LLMProvider` contract and the provider-shape-portability convention are
      preserved. *(trivially preserved — change is confined to the Anthropic adapter
      + one new pure helper module under `the_one/llm/`)*

---

## Pre-Flight

### Objective

Stop one non-conforming MCP tool schema from killing an entire Anthropic turn.
Anthropic's Messages API rejects any tool whose `input_schema` carries a top-level
`oneOf`/`allOf`/`anyOf`, or omits a top-level `type` (reproduced live in Flight 1:
`400 input_schema does not support oneOf, allOf, or anyOf at the top level`). The
fix is a **pure, deterministic schema sanitizer** applied in the Anthropic adapter's
tool conversion (`_to_anthropic_tool`, `anthropic_provider.py:210-215`; called from
`_build_kwargs`, `:75-100`) immediately before send — normalize the known top-level cases so the turn just
works — plus a defensive `BadRequestError → tool-name` net so that any *future*
top-level constraint Anthropic adds surfaces as the offending tool's **name** rather
than a bare `tools.37` index. The change is confined to `the_one/llm/` (the Anthropic
adapter + one new pure helper); the generic `Message`/`LLMProvider` contract, the
other three adapters, and the MCP layer are untouched.

### Background (why this is the right shape)

Tool `input_schema` blobs originate **upstream**, in third-party MCP servers, and are
ingested verbatim (`the_one/mcp/client.py:670` → stored in `MCPTool.input_schema`,
forwarded as the canonical tool's `parameters`). Built-in tools emit clean flat
object schemas via Pydantic and are never the problem. A top-level combinator is
**legal JSON Schema and legal MCP** — it is only Anthropic that is stricter than the
spec. OpenAI and Ollama accept these schemas. Therefore the fix is **Anthropic-
adapter-local**, not an MCP-layer change: the MCP layer must keep the true schema
(it also validates outgoing tool *arguments* against it at `client.py:715`), and only
Anthropic's *view* of the schema gets normalized. The real-world trigger is a known
case — goldfinch's `press_key` tool (top-level `anyOf` expressing "at least one of
`name`/`key`"; tracked as goldfinch#56) — which becomes this flight's primary fixture.

### Open Questions
- [x] **OpenRouter → Anthropic routing.** `OpenRouterProvider` is a thin
      `OpenAIProvider` subclass (`openrouter_provider.py:46`) that sends tools via the
      inherited **OpenAI** path (`openai_provider.py:130,182` → `self.tool_schema(t)`),
      emitting the OpenAI `{"type":"function","function":{...,"parameters":...}}` shape
      — it **never** calls `_to_anthropic_tool` and never emits an Anthropic-native
      `input_schema`. So translating to Anthropic's stricter rules is *OpenRouter's*
      responsibility on their OpenAI-compat endpoint. Open question: when OpenRouter
      routes to an Anthropic model, does it normalize, or surface the same 400?
      Resolve empirically in `leg 03`. **Likely outcome:** document that OpenRouter
      owns the translation and scope it out (the Anthropic-native sanitizer does not
      drop into the OpenAI tool path without adaptation). Only if OpenRouter→Anthropic
      demonstrably rejects *and* a clean adaptation exists do we wire it.
      → **RESOLVED (`leg 03`, live probe 2026-06-18): the "likely outcome" was
      FALSIFIED.** A live OpenRouter request to `anthropic/claude-3.5-haiku`
      (OpenAI-compat endpoint, tool in OpenAI function shape) **rejected** the raw
      `press_key` schema with the verbatim #122 error
      (`tools.0.custom.input_schema: input_schema does not support oneOf, allOf, or anyOf
      at the top level`, provider: Amazon Bedrock backing Anthropic) and **accepted** the
      sanitized control. OpenRouter does **not** normalize — it forwards the schema and
      the Anthropic backend 400s, same #122 constraint and same kernel as the direct
      path. Both decision-rule conditions held (OpenRouter demonstrably rejects + a clean
      adaptation exists — the leg-01 `sanitize_tool_schema` kernel is schema-in/schema-out
      and provider-neutral), so the sanitizer was wired onto the OpenRouter tool path,
      **gated to `anthropic/*` routes** (minimal scope; no DD5 drop-and-proceed / DD6
      named-error parity on this path). No divert: OpenRouter needs the *same*
      normalization, so the shared-module assumption (DD1) holds — this leg is the
      kernel's promised second caller, on the OpenAI-shaped tool path.
- [x] **Where does the sanitizer live?** → see Design Decisions (shared pure module).
- [x] **anyOf/oneOf strategy** → union-merge (see Design Decisions).
- [x] **Genuinely-unsendable behavior** → drop-and-proceed (see Design Decisions).
- [x] **Copy-button-on-error-bubble UI enhancement** → **split out** of this flight
      (different surface; mission scopes UI changes narrowly). Tracked separately.

### Design Decisions

**DD1 — Sanitizer is a pure, leaf kernel; NOT (yet) a contract-level interface
method**: Add `the_one/llm/_schema_sanitize.py` (underscore-prefixed, mirroring
`_streaming.py`) as a pure, **stdlib-only** library of JSON-Schema normalization
primitives (`schema in → schema out`, no `the_one.llm` imports — even leaner than
`_streaming.py`, which imports from `base`). Anthropic calls it from its **existing**
per-provider transform override (`tool_schema()` / `_to_anthropic_tool`,
`base.py:347-360`). We do **not** add a uniform `LLMProvider.sanitize_tool_schema()`
base method in this flight.
- Rationale (evidence-backed, operator-ratified 2026-06-17): The Flight 1B audit —
  whose job was to enumerate per-SDK gaps — found tool-schema **sanitization** is
  **Anthropic-only** today. OpenAI accepts our schemas (`03-openai-audit.md:76`: "No
  OpenAI #122/#105 tool-schema cross-ref"); Ollama's #105 is the *inverse* (parsing
  tool calls *out of* returned text, not sanitizing input); OpenRouter inherits the
  OpenAI path. *(Update — `leg 03`, 2026-06-18: the "OpenRouter inherits the OpenAI
  path, so it's not a sanitization site" assumption proved only half-right. OpenRouter
  inherits the OpenAI **tool shape**, but when it routes to an Anthropic backend that
  backend enforces the same #122 top-level-combinator constraint and 400s — confirmed
  live. The DD1 kernel was the right call precisely because it is provider-neutral: it
  dropped onto the OpenAI-shaped `parameters` of OpenRouter's inherited tool dict with
  no change to its signature, making OpenRouter the kernel's real second caller. The
  wire is gated to `anthropic/*` routes and intentionally minimal — no DD5/DD6 parity
  on this path. The uniform-interface promotion below is still deferred; this is a
  second **caller**, not yet a second interface.)* The genuinely cross-provider per-provider differences the audit found
  are **capability gaps** (structured outputs, vision, parallel-toggle — the A1–A5
  backlog), not sanitization, and they are *already* served by the existing
  per-provider override seam (`tool_schema()`, `_to_api_message()`). A uniform
  `sanitize_tool_schema()` method designed against the single Anthropic example would
  be guessing at its signature (one tool vs. list? may it drop tools? returns
  warnings?).
- **Dormant second case (acknowledged, not served here):** OpenAI *strict*
  structured-output / strict function-calling has a restricted schema dialect
  (`additionalProperties:false`, all-props-required, limited keywords). The-one uses
  *non-strict* calling today (audit: structured outputs **unwired**), so this is
  inactive; if a future capability flight wires strict mode, **that** flight owns its
  sanitization and becomes the second caller.
- **Promotion path:** when a second real caller appears (the OpenAI-strict capability
  flight, or Flight 4 conformance — whichever first), lift the kernel to a uniform
  `LLMProvider.sanitize_tool_schema()` base method (default no-op, non-breaking) with
  each provider delegating to the kernel. The logic does not move — only where it is
  called from — so the refactor is mechanical.
- Trade-off: one new module vs. a private method on `AnthropicProvider`; and deferring
  the uniform interface vs. declaring it now. Testability/isolation win the former;
  the audit's single-caller evidence + signature-design risk win the latter.

**DD2 — Sanitize on a deep copy; never mutate the shared tool dict**: The sanitizer
must operate on a copy and leave the input object `is`-identical and unmodified.
- Rationale (load-bearing reference chain, confirmed in review): `Tool.to_schema()`
  (`the_one/tools/base.py:106-110`) returns `{"parameters": self.parameters}` — the **same object**
  the tool instance holds. For MCP tools `self.parameters` **is**
  `mcp_tool.input_schema` (`_tool.py:113`), which is the exact object `client.py:717`
  validates outgoing tool *arguments* against; and `to_schema()` is rebuilt per turn
  (`agent/core.py` `_compute_visible_schemas`) but wraps the *persistent*
  `self.parameters`. So in-place mutation would be **sticky across turns** and would
  corrupt (a) the MCP arg-validation source and (b) any other provider reading the
  same schema in the same turn (OpenAI/Ollama *want* the original top-level
  combinator). The `leg 01` non-mutation test asserts the input is `is`-identical and
  byte-unchanged after sanitize.

**DD3 — Top-level only; nested combinators untouched**: Anthropic rejects combinators
*only at the top level*. The sanitizer rewrites the top level and recurses **not at
all** into nested schemas (nested `anyOf` inside a property is valid and is preserved
— indeed union-merge may *introduce* a nested `anyOf` for a colliding key, DD4).
- Rationale: confirmed by the Flight 1 live repro; minimizes blast radius.

**DD4 — Per-case deterministic rules (the sanitizer's contract)**:

| Top-level input case | Rule | Lossy? |
|---|---|---|
| Missing/`None` `parameters` key entirely | treat as empty → `{"type":"object"}` (defend the subscript; don't trust upstream blindly) | no |
| Has `properties`, no `type` | inject `type:"object"` | no |
| Empty / bare (`{}`, no type+no properties) | set `{"type":"object"}` | no |
| `type` is an **array** (e.g. `["object","null"]`) | if `"object"` is a member, collapse to `type:"object"`; else → unsanitizable. *(Whether Anthropic accepts an array `type` is unconfirmed — pin empirically in `leg 04`; this couples the `leg 01` rule to the `leg 04` finding, see leg deps.)* | no |
| Top-level `allOf`, **all branches object/required-fragments** | deep-merge: union `properties`, **union** `required`; set `type:object`; drop `allOf` | no |
| Top-level `allOf` with a **non-object branch** (`$ref`, scalar, `not`, …) | cannot losslessly merge a non-object constraint → unsanitizable | n/a |
| Top-level `anyOf`/`oneOf` of object/required-fragment branches | union branch `properties` into top level; on key collision set `properties.<key> = {anyOf:[...]}` (nested, legal); `required` = **intersection** across branches; set `type:object`; drop combinator | only the cross-field "exactly one / at least one" constraint |
| Top-level bare `$ref` (no top-level `type`) | no object shape to synthesize → unsanitizable (explicit row, not an accidental fallthrough) | n/a |
| Top-level `not`, or any other top-level non-object scalar / non-mergeable shape | unsanitizable | n/a |
| (always) | preserve `description`, `$defs`/`definitions`, `additionalProperties`, and branch/field descriptions; **leave nested `$ref`/combinators untouched** (DD3); append a one-line note to `description` when a combinator was merged so the model keeps the prose guidance that actually steers it | — |

**Unsanitizable signal (the `leg 01`↔`leg 02` contract):** the pure sanitizer raises a
dedicated `UnsanitizableToolSchema(reason: str)` exception for the "unsanitizable"
rows above. `leg 02`'s adapter wraps each tool's sanitize call in `try/except
UnsanitizableToolSchema` to implement drop-and-proceed (DD5), using `reason` in the
named warning. (Chosen over a `None`/sentinel return so the reason travels with the
control-flow signal and the pure function's success type stays a plain schema dict.)

- Rationale: union-merge keeps every real field name + type hint, landing on the
  exact flat-object-with-optional-fields shape that well-behaved tools (incl. Claude
  Code's own) already use and the model is most fluent with. The only dropped
  guarantee (oneOf's "exactly one") is rarely schema-enforced for tool calls, is not
  hard-enforced on model output by Anthropic, and is re-validated by the tool/MCP
  server (e.g. goldfinch's engine `name ?? key`).
- Trade-off: union-merge is technically lossy for `oneOf`; strip-to-permissive-object
  would be simpler but discards field hints. Rejected — losing hints degrades tool
  usability for a constraint that barely bites.

**DD5 — Drop-and-proceed for genuinely-unsanitizable tools**: When the sanitizer
raises `UnsanitizableToolSchema`, exclude **that one tool** from the request, run the
turn with the rest, and surface a structured **named** warning. One broken MCP tool
never kills the conversation. The filtered list `_build_kwargs` actually sends becomes
the **single source of truth** for tool ordering — DD6's index→name map is built from
*this* post-drop list, never the original (the dropped tool shifts every later index).
- Rationale: strongest reading of "no longer fails the whole turn." A blocking error
  would still let one bad tool veto the turn.
- Trade-off: the agent silently loses access to that tool for the turn; mitigated by
  the named warning so the operator can see and fix it. **No new web-UI element** —
  the copy-button is split out and UI changes are out of mission scope; the warning
  rides existing logging. (`AnthropicProvider` currently has no logger import or
  event-emit hook, so `leg 02` adds a module logger and emits there; an agent-event
  surface is used *only if* one already exists at the adapter layer — otherwise
  log-only, which the adaptation criteria permits.)

**DD6 — `BadRequestError → tool name` defensive net**: belt-and-suspenders for any
*new* top-level constraint the sanitizer doesn't yet know — guarantees the criterion
("names the offending tool rather than a bare index") even for unknown future
constraints, without pretending to fix them.
- **Composition with the existing temperature-retry (the real subtlety).** Today both
  `complete()` (≈ lines 112-121) and `stream()` (≈ 158-168) have a single
  `except anthropic.BadRequestError` that branches `if "temperature" in str(exc): retry
  else: raise`. A schema 400 contains no "temperature", so today it hits `else: raise`
  and propagates the bare `tools.N` message. DD6 layers into that **same** `except`
  with **ordered** checks: (1) temperature → retry as today; (2) else if the message
  matches `tools.(\d+)\.` → re-raise naming the tool; (3) else → `raise` unchanged.
- The temperature retry issues a **second** `create()`/`stream()` that can itself 400
  on a schema — the name-mapping must apply to **that** failure too (wrap the retry
  call, not only the first attempt).
- **Index source:** map `N` against the **post-DD5 filtered** tools list that was
  actually sent (DD5), not the original — a dropped tool shifts later indices.
- Trade-off: relies on Anthropic's error-message shape (`tools.N.…`); if the index
  can't be parsed (or is out of range for the sent list), fall back to re-raising the
  original error unchanged (no worse than today).

### Prerequisites
- [ ] Anthropic SDK present in `.venv` (confirmed Flight 1B: `anthropic 0.97.0`).
- [ ] For `leg 04` live test: an `ANTHROPIC_API_KEY` and a tool-capable Claude model.
      The live test is `@pytest.mark.live` so default `make test` stays hermetic.
- [ ] goldfinch `press_key` schema captured verbatim as the primary fixture (source:
      `goldfinch/src/main/automation/mcp-tools.js:257-274`; copied into the-one's test
      fixtures — no live goldfinch dependency).

### Pre-Flight Checklist
- [x] All open questions resolved — except the OpenRouter→Anthropic question, which is
      **deliberately deferred into `leg 03`** to resolve empirically (a divert criterion
      covers the unexpected-outcome case). Ratified by operator.
- [x] Design decisions documented (DD1–DD6)
- [x] Prerequisites verified (anthropic SDK present; live-key + fixture noted for `leg 04`)
- [x] Validation approach defined (hermetic units + one `@pytest.mark.live` check)
- [x] Legs defined (4 + optional UAT)

---

## In-Flight

### Technical Approach

A pure sanitizer module (`_schema_sanitize.py`, DD1–DD4) is built and exhaustively
unit-tested first, in isolation from any provider. It is then wired into the Anthropic
adapter's tool conversion (`_to_anthropic_tool` / `_build_kwargs`, DD2) with the
drop-and-proceed path (DD5) and the `BadRequestError → tool-name` net (DD6) around the
sends in `complete()` and `stream()`. The OpenRouter→Anthropic path is then probed and
either wired to the same shared sanitizer or documented as already-normalized
(`leg 03`). Finally a `@pytest.mark.live` test confirms our model of Anthropic's rules
is *correct*, not just internally consistent: it sends the (formerly-400ing) sanitized
`press_key` schema to the real API and asserts acceptance (and, to keep the test
meaningful, asserts the *un*-sanitized schema still 400s).

### Checkpoints
- [ ] Sanitizer module + unit suite green (all DD4 rows, incl. `press_key` fixture)
- [ ] Anthropic adapter sanitizes before send; one bad tool no longer kills the turn
- [ ] `BadRequestError` surfaces the offending tool **name**
- [ ] OpenRouter→Anthropic question resolved (wired or documented out)
- [ ] Live-gated test confirms real Anthropic accepts sanitized output

### Adaptation Criteria

**Divert if**:
- The live test reveals Anthropic's top-level constraint differs materially from the
  Flight 1 repro (e.g. it also rejects some nested shape) — re-scope DD3/DD4.
- OpenRouter→Anthropic turns out to require a *different* normalization than the
  Anthropic-direct path (then the "shared module" assumption needs revisiting).

**Acceptable variations**:
- Exact module/function names and the regex for the `tools.N` index.
- Whether the drop-and-proceed warning also emits a one-shot agent event vs. log-only,
  provided the offending tool is **named**.

### Legs

- [x] `sanitize-tool-schema` — new pure, stdlib-only `the_one/llm/_schema_sanitize.py`
      implementing DD2–DD4 + the `UnsanitizableToolSchema` signal + exhaustive unit
      tests (every DD4 row; `press_key` real fixture; `is`-identity non-mutation;
      preservation of `description`/`$defs` incl. a nested-`$ref` property round-trip;
      each unsanitizable row raises with a `reason`). **Dep note:** the array-valued
      `type` rule is provisional until `leg 04` pins Anthropic's actual behavior — encode
      the collapse-to-`object` rule, and tighten/relax in `leg 04` if the live result
      differs.
- [x] `wire-into-anthropic-adapter` — call the sanitizer in `_to_anthropic_tool`/
      `_build_kwargs` (DD2); drop-and-proceed with a named, `reason`-carrying warning
      for `UnsanitizableToolSchema` (DD5, incl. the post-drop tools list as ordering
      source of truth); `BadRequestError → tool-name` net folded into the existing
      ordered `except` in **both** `complete()` and `stream()` and covering the
      temperature-retry's second call (DD6). Tests use a **net-new** mocked-Anthropic-
      client harness (no anthropic test file exists today — model it on the mocked-
      client pattern in `tests/test_mcp_tool_provider.py` / `tests/test_openrouter_provider.py`),
      incl. the multi-tool "one bad tool dropped, rest succeed" case and the
      index-shift case (a dropped tool before the offending one).
- [x] `openrouter-anthropic-check` — empirically resolve the OpenRouter→Anthropic open
      question; **likely** documents that OpenRouter owns the translation and scopes it
      out; wires the sanitizer onto that path only if OpenRouter demonstrably rejects
      and a clean adaptation to the OpenAI tool shape exists.
- [x] `live-verify-anthropic` — `@pytest.mark.live` test (deselected by `make test`,
      marker already registered): real Anthropic accepts the sanitized `press_key`
      schema and still 400s on the un-sanitized one (proves the rules are correct, not
      just internally consistent); also pins the array-`type` behavior for `leg 01`.
- [ ] `uat-and-alignment` *(optional)* - Guided UAT exercising a real Anthropic turn
      with a connected MCP server that emits a top-level combinator.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (`make test` hermetic; live test green when run with a key)
- [ ] Documentation updated (if the sanitizer's contract warrants a note in
      `the_one/agents.md`; otherwise N/A)

### Verification
- **Unit (hermetic, primary):** the sanitizer suite covers every DD4 row plus the
  `press_key` real-world fixture, non-mutation, and unsanitizable signalling; the
  adapter suite (mocked SDK) proves sanitize-before-send, one-bad-tool drop-and-proceed
  with a named warning, and `BadRequestError → tool-name` mapping.
- **Live (gated):** `@pytest.mark.live` confirms the real Anthropic API accepts the
  sanitized `press_key` schema and still 400s on the un-sanitized one.
- **Regression net:** Flight 4's cross-provider conformance suite will guard this fix
  going forward (out of scope here; this flight ships its own tests).
