# Leg: schema-122-guards

**Status**: completed
**Flight**: [Cross-Provider Tool-Use Conformance Suite](../flight.md)

## Objective

Add the #122 regression guards (cross-provider same-schema sanitized-vs-verbatim
assertion; OpenRouter `anthropic/*` `complete()`/`stream()` smoke; `stream()`
temperature-retry→`tools.N` sub-path) plus the DD6 error-format pin test, and
formalize the OpenRouter **forward-with-WARN** contract with a pin test + a
one-paragraph module-docstring note — with **no production logic changes** (the
docstring is the only production-file edit).

## Context

- **DD4**: the #122 coverage gaps + the DD6 format-monitoring test the Flight-2
  debrief assigned to Flight 4, co-located with the conformance suite so one file
  is the tool-use regression net.
- **DD3**: the OpenRouter `anthropic/*` route forwards a *genuinely-unsanitizable*
  schema with a WARN (no drop), whereas Anthropic-direct drops it (DD5). The
  operator chose to **formalize** this asymmetry: pin it with a test + a docstring
  note. **No logic change to either provider**; the kernel is not promoted.
- **Dependencies (both landed):**
  - Leg 01 → `tests/fixtures/tool_schemas.py` exports `PRESS_KEY_INPUT_SCHEMA`
    (the top-level-`anyOf` #122 trigger, **sanitizable**) and `make_bad_request(msg)`.
  - Leg 02 → `tests/fixtures/scripted_transport.py` exports the scripted-transport
    harness (`make_openai`/`make_anthropic`/… + `CannedTurn`). The OpenRouter
    `anthropic/*` smoke needs a **new `make_openrouter` constructor added to this
    harness** (`make_openai` hardcodes `OpenAIProvider(model="gpt-test")` and cannot
    drive an `anthropic/*` OpenRouter slug) — so this leg edits the harness file,
    extending the cross-leg harness contract that leg 04 also inherits.
- **Co-location**: all guards/pins land in the leg-02 conformance module
  `tests/test_llm_provider_cross_provider_conformance.py` (DD4 "one file is the
  regression net"). The forward-with-WARN pin lives there too.

### The seams these guards exercise (source-verified 2026-06-19)

- **Anthropic sanitize seam is NOT `tool_schema()`** — it is `_to_anthropic_tool()`
  (`anthropic_provider.py:284-293`, calls `sanitize_tool_schema(tool_def.get("parameters"))`),
  invoked inside `_build_kwargs` (`:137-156`), which also implements **DD5
  drop-and-proceed**: an `UnsanitizableToolSchema` is caught, the tool is dropped
  with a named `logger.warning`, and if all tools drop the `tools` key is omitted.
- **OpenRouter sanitize seam IS `tool_schema()`** — `openrouter_provider.py:124-149`,
  gated on `self.model.startswith("anthropic/")`; on `UnsanitizableToolSchema` it
  **forwards unmodified** + `logger.warning` (the forward-with-WARN behavior; no drop).
- **OpenAI / Ollama**: inherit the base `tool_schema()` (`base.py:347-360`) which
  returns `parameters` **verbatim** (no sanitize). Confirm Ollama does not override
  `tool_schema` (`grep -n "def tool_schema" the_one/llm/ollama_provider.py` → expect
  none; it inherits base).
- **`stream()` temperature-retry → `tools.N`** — `anthropic_provider.py:227-242`:
  on a pre-delta `BadRequestError` whose message contains "temperature" (and
  `not yielded_any`), `stream()` pops `temperature` and re-enters `_stream_inner`;
  if *that* raises a `BadRequestError`, `_name_offending_tool(exc2, kwargs.get("tools"))`
  (`:32-57`, uses `_TOOLS_INDEX_RE` at `:29`) maps a `tools.N` 400 to the tool's
  name. This retry→tools.N sub-path is currently uncovered (the `complete()`-side
  equivalent is tested; the `stream()`-side is not).
- **`_TOOLS_INDEX_RE`** (`anthropic_provider.py:29`) = `re.compile(r"tools\.(\d+)\.")`.
  The confirmed first-party 400 string is `tools.0.custom.input_schema: …`.
- **A genuinely-unsanitizable schema** — `sanitize_tool_schema` raises
  `UnsanitizableToolSchema` (`_schema_sanitize.py:38`) when a top-level combinator
  branch is non-object (`:172-176`), e.g. `{"anyOf": [{"type": "string"}]}`, or a
  bare non-object top-level `type`/`$ref`/`not`. Use the `anyOf`-with-non-object-
  branch form — it is the representative #122 "can't flatten" case.

## Inputs
What exists before this leg runs:
- `tests/test_llm_provider_cross_provider_conformance.py` (leg 02) — the regression-
  net module to extend.
- `tests/fixtures/tool_schemas.py` (leg 01) — `PRESS_KEY_INPUT_SCHEMA`, `make_bad_request`.
- `tests/fixtures/scripted_transport.py` (leg 02) — scripted-transport harness.
- Providers (read-only except the OpenRouter docstring): `anthropic_provider.py`,
  `openrouter_provider.py`, `openai_provider.py`, `ollama_provider.py`,
  `_schema_sanitize.py`.

## Outputs
What exists after this leg completes:
- New guard/pin tests in `tests/test_llm_provider_cross_provider_conformance.py`:
  1. cross-provider same-schema sanitized-vs-verbatim assertion;
  2. OpenRouter `anthropic/*` `complete()` + `stream()` round-trip smoke;
  3. Anthropic `stream()` temperature-retry → `tools.N` → tool-name mapping;
  4. `test_tools_index_re_matches_known_format` (DD6 error-format pin);
  5. forward-with-WARN contract pin (OpenRouter forwards + WARNs; Anthropic-direct
     drops) — the documented asymmetry.
- A new `make_openrouter` constructor in `tests/fixtures/scripted_transport.py`
  (with the network context-resolver defused), extending the harness for the
  `anthropic/*` smoke and for leg 04's reuse.
- A new unsanitizable-schema fixture (recommended: add `UNSANITIZABLE_ANYOF_SCHEMA`
  to `tests/fixtures/tool_schemas.py`; inline is acceptable).
- A one-paragraph note added to `openrouter_provider.py`'s **module docstring**
  explaining the forward-with-WARN asymmetry. **This is the only production-file
  change in this leg — docstring text only, zero logic change.**

## Acceptance Criteria
- [x] **Cross-provider same-schema**: feeding `PRESS_KEY_INPUT_SCHEMA` (as a tool
      def) through each provider's tool-schema path asserts — sanitized (no
      top-level `anyOf`/`oneOf`/`allOf`, has top-level `type:"object"`) for
      **Anthropic** (`_to_anthropic_tool(...)["input_schema"]`) and **OpenRouter
      `anthropic/*`** (`tool_schema(...)["function"]["parameters"]`); left
      **verbatim** (combinator preserved) for **OpenAI**, **Ollama**, and
      **OpenRouter non-`anthropic/*`**.
- [x] **OpenRouter `anthropic/*` smoke**: a new `make_openrouter` harness
      constructor exists (defusing the network context-resolver — see guidance);
      `complete()` and `stream()` round-trip on a scripted transport with an
      `anthropic/claude-*` slug, returning the canonical `Message`/`ToolCall` shape,
      **and** the test asserts the sent tool schema was **sanitized** on this route
      (capture the request body in the stateful handler and assert no top-level
      combinator) — this is what proves the `anthropic/*` sanitize ran end-to-end
      through `complete()`, not just via the standalone `tool_schema()` test. Closes
      the "only `tool_schema()` called directly" gap.
- [x] **`stream()` temp-retry → `tools.N`**: a stream whose first submission 400s on
      "temperature" and whose retry 400s on `tools.1.custom.input_schema: …` raises a
      `BadRequestError` whose message **names the tool at index 1** (not a bare index).
- [x] **DD6 format pin**: `test_tools_index_re_matches_known_format` asserts
      `_TOOLS_INDEX_RE` matches `tools.0.custom.input_schema: …` capturing `"0"`, and
      does not match a non-`tools.N` string (e.g. `messages.0: …`).
- [x] **Forward-with-WARN pin**: on an `anthropic/*` route, an unsanitizable schema
      passed to `OpenRouterProvider.tool_schema(...)` returns the tool with its
      combinator **preserved** (forwarded) and emits a WARN on
      `the_one.llm.openrouter_provider`; the same schema through Anthropic-direct
      `_build_kwargs(..., tools=[t])` **omits** the tool (dropped) and emits a WARN on
      `the_one.llm.anthropic_provider`. The asymmetry is asserted in one test.
- [x] **Docstring note** added to `openrouter_provider.py` module docstring; `git diff
      the_one/llm/openrouter_provider.py` shows **only** docstring lines changed (no
      code/logic).
- [x] No other production source modified (`git diff --stat -- 'the_one/**'` shows
      only `openrouter_provider.py`, docstring-only).

## Verification Steps
- Run the conformance module:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_llm_provider_cross_provider_conformance.py -x --timeout 30`
  → all guards + the leg-02 round-trips pass.
- `grep -n "def tool_schema" the_one/llm/ollama_provider.py` → no match (confirms
  Ollama inherits base verbatim `tool_schema`).
- `git diff the_one/llm/openrouter_provider.py` → only the module docstring changed;
  no change inside any `def`. Confirm with
  `git diff -G '^\s*(def|return|if|for|try|except|logger|result)' the_one/llm/openrouter_provider.py` → empty.
- Re-run the existing #122 tests to confirm no collateral breakage:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_anthropic_provider.py tests/test_openrouter_provider.py tests/test_schema_sanitize.py tests/test_streaming.py -x --timeout 30`
  → green.

## Implementation Guidance

1. **Add the unsanitizable fixture** — to `tests/fixtures/tool_schemas.py` (recommended):
   `UNSANITIZABLE_ANYOF_SCHEMA = {"anyOf": [{"type": "string"}]}` (a top-level
   combinator whose branch is non-object → `sanitize_tool_schema` raises
   `UnsanitizableToolSchema`). Add a `def _tool(name, params)` helper if convenient
   for wrapping a schema into the canonical `{"name","description","parameters"}`.

2. **Cross-provider same-schema test** — build the press_key tool def once
   (`{"name":"press_key","description":"…","parameters": PRESS_KEY_INPUT_SCHEMA}`):
   - Anthropic: `AnthropicProvider(model="claude-test", api_key="x")._to_anthropic_tool(td)`
     → assert `"anyOf" not in result["input_schema"]` and
     `result["input_schema"]["type"] == "object"`.
   - OpenRouter anthropic/*: `OpenRouterProvider(model="anthropic/claude-3.5-haiku",
     api_key="x").tool_schema(td)` → assert no `anyOf` in
     `["function"]["parameters"]`, type object. (Mirrors the existing
     `test_anthropic_route_sanitizes`; co-locate the cross-provider view.)
   - OpenAI: `OpenAIProvider(model="gpt-4o", api_key="x").tool_schema(td)` → assert
     `["function"]["parameters"]` still has the top-level `anyOf` (verbatim).
   - Ollama: `OllamaProvider(model="qwen2.5:7b", base_url="http://t:11434").tool_schema(td)`
     → verbatim (`anyOf` preserved).
   - OpenRouter non-anthropic: `OpenRouterProvider(model="openai/gpt-4o", api_key="x")
     .tool_schema(td)` → verbatim.
   Deep-copy `PRESS_KEY_INPUT_SCHEMA` into each tool def (or rely on the kernel's
   internal deep-copy) so the shared constant is never mutated across cases.

3. **OpenRouter `anthropic/*` complete()/stream() smoke** — **add a dedicated
   `make_openrouter(turns, *, model="anthropic/claude-3.5-haiku", streaming=False)`
   to `tests/fixtures/scripted_transport.py`** (pinned approach — leg 04 inherits
   this surface). OpenRouterProvider is an `OpenAIProvider` subclass, so the same
   stateful-transport + instance-client-replacement injection `make_openai` uses
   works; `make_openrouter` differs only in constructing
   `OpenRouterProvider(model=…, api_key="x")` and in **defusing the network
   context-resolver** (required for hermeticity — see Edge Cases): monkeypatch
   `the_one.llm.openrouter_api.get_model_context_length` to return `None` (or
   pre-flip the provider's `_max_context_tokens_resolved` sentinel to `True`),
   because OpenRouter's `_resolve_max_context_tokens` (`openrouter_provider.py:151-163`)
   builds its **own** `httpx.AsyncClient` inside `openrouter_api` that the
   `MockTransport` does **not** intercept. Drive a two-turn round-trip (turn-1 emits
   a tool_call, turn-2 final answer) and assert the canonical `Message`/`ToolCall`
   shape. **Required**: capture the turn-1 request body in the stateful handler and
   assert the sent tool's parameters were **sanitized** (no top-level
   `anyOf`/`oneOf`/`allOf`) — this is the only assertion that proves the
   `anthropic/*` sanitize ran through `complete()`/`stream()`, vs. the standalone
   `tool_schema()` test. (Pass the `PRESS_KEY_INPUT_SCHEMA` tool so there is a
   combinator to sanitize.)

4. **`stream()` temp-retry → `tools.N` test** — model on `test_streaming.py`'s
   `TestAnthropicStreamRetry` + `test_anthropic_provider.py`'s complete()-side
   temp-retry→tools.N test. Build an Anthropic provider whose `client.messages.stream`
   is a recorder returning two context managers: the **first** raises
   `make_bad_request("temperature: unsupported")` in `__aenter__` (pre-delta); the
   **second** raises `make_bad_request("tools.1.custom.input_schema: invalid")` in
   `__aenter__`. Call `stream(messages, tools=[tool0, tool1])` (two tools so index 1
   exists) and consume the generator; assert it raises `anthropic.BadRequestError`
   whose message names `tool1`'s name (the `_name_offending_tool` mapping). Use the
   harness's stream stubs or a local `_StreamCM`/`_StreamRecorder` whose factory
   raises in `__aenter__` (see `test_streaming.py:212-218` for the raising-CM shape).
   Note: `tools` here are canonical tool defs passed to `stream()`; after
   `_build_kwargs` the post-sanitize `kwargs["tools"]` is what `_name_offending_tool`
   indexes — ensure both tools sanitize cleanly so neither is dropped (use simple
   object schemas, not the unsanitizable fixture) and index 1 is preserved.

5. **DD6 format pin** — `from the_one.llm.anthropic_provider import _TOOLS_INDEX_RE`;
   assert `_TOOLS_INDEX_RE.search("tools.0.custom.input_schema: invalid").group(1) ==
   "0"`, and `_TOOLS_INDEX_RE.search("messages.0: unrelated") is None`. A short
   docstring on the test should state it pins the Anthropic first-party error format
   so a drift surfaces as a red test.

6. **Forward-with-WARN pin** — one test asserting the asymmetry, using `caplog`:
   - OpenRouter: `prov = OpenRouterProvider(model="anthropic/claude-3.5-haiku",
     api_key="x")`; `td = {"name":"t","description":"d","parameters":
     UNSANITIZABLE_ANYOF_SCHEMA}`; with `caplog.at_level(logging.WARNING,
     "the_one.llm.openrouter_provider")`: `result = prov.tool_schema(td)`. Assert
     `result["function"]["parameters"] == UNSANITIZABLE_ANYOF_SCHEMA` (forwarded
     unmodified, combinator preserved) and a WARN record was emitted.
   - Anthropic-direct: `aprov = AnthropicProvider(model="claude-test", api_key="x")`;
     with `caplog.at_level(logging.WARNING, "the_one.llm.anthropic_provider")`:
     `kwargs = aprov._build_kwargs([Message.user("hi")], [td], 0.0, 16)`. Assert
     `"tools" not in kwargs` (the sole tool was dropped) and a WARN was emitted.
   - The single test documents: same unsanitizable schema, divergent handling by route.

7. **OpenRouter module-docstring note** — append a paragraph to the module docstring
   at the top of `openrouter_provider.py` (the `"""…"""` block, lines 1-10). Suggested
   text (adjust to house voice):
   > **#122 route asymmetry (Flight 4, DD3).** On an ``anthropic/*`` route a tool
   > whose ``input_schema`` is *genuinely unsanitizable* is **forwarded unmodified
   > with a WARN** (see ``tool_schema`` below) — it is *not* dropped, unlike the
   > Anthropic-direct path (``anthropic_provider.py`` DD5 drop-and-proceed). This is
   > an intentional minimal-scope decision: the common ``anyOf``/``oneOf`` case is
   > fixed on *both* paths; only the rare unsanitizable case diverges, where
   > forwarding is "no worse than today" (the request 400s exactly as pre-fix).
   > Pinned by ``test_…`` in the cross-provider conformance suite.
   Do **not** touch any code inside a function. Verify the diff is docstring-only.

## Edge Cases
- **Index-1 preservation in the stream test** — if either tool in `tools=[t0, t1]`
  is unsanitizable, `_build_kwargs` drops it and the post-drop list re-indexes, so a
  `tools.1` 400 would map to the wrong tool (or out of range). Use two cleanly-
  sanitizable tools so the index is stable; the 400 is *synthesized* by the recorder,
  not produced by a real schema, so the tools themselves need only be valid.
- **`caplog` logger names** — the WARN assertions must target the exact module
  loggers (`the_one.llm.openrouter_provider`, `the_one.llm.anthropic_provider`);
  `caplog.at_level` with the logger name (not the root) avoids cross-test log bleed.
- **`tool_schema` returns the OpenAI function envelope** — OpenRouter/OpenAI assert
  on `result["function"]["parameters"]`, not `result` directly. Anthropic's
  `_to_anthropic_tool` returns `{"name","description","input_schema"}` — assert on
  `["input_schema"]`.
- **Don't assert a dropped-tool WARN message string verbatim** — assert the record
  exists + the structural outcome (`"tools" not in kwargs`); message wording is not
  a contract.
- **Ollama `tool_schema` inheritance** — verify with the grep in Verification Steps;
  if a future Ollama override existed it would change the verbatim expectation.
- **OpenRouter context-resolver is a live network call** — `complete()`/`stream()`
  call `_resolve_max_context_tokens_if_needed()`, and OpenRouter's override hits
  `openrouter_api.get_model_context_length` over the network via its **own**
  `httpx.AsyncClient` (NOT the injected `MockTransport`). `base.py:281-293` swallows
  the failure so the test won't *fail*, but it attempts a real network call —
  breaking the suite's hermetic guarantee. `make_openrouter` MUST defuse it
  (monkeypatch `get_model_context_length` → `None`, or pre-flip the sentinel). This
  is unique to OpenRouter; OpenAI's resolver is a pure dict lookup and Anthropic's is
  a no-op (neither needs defusing).

## Files Affected
- `tests/test_llm_provider_cross_provider_conformance.py` — **append** the five
  guard/pin tests.
- `tests/fixtures/scripted_transport.py` — **add** `make_openrouter` (with the
  context-resolver defused).
- `tests/fixtures/tool_schemas.py` — **add** `UNSANITIZABLE_ANYOF_SCHEMA` (recommended).
- `the_one/llm/openrouter_provider.py` — **module-docstring note only** (no logic).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (conformance module green; #122 test files still green)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] (Not the final leg — no flight/mission status change)
- [ ] Do NOT commit (deferred-commit model — flight commits once after the last leg)

---

## Citation Audit

Citations verified against current code at leg design time (2026-06-19):
- `the_one/llm/anthropic_provider.py:29` `_TOOLS_INDEX_RE = re.compile(r"tools\.(\d+)\.")` — **OK**
- `:32-57` `_name_offending_tool` (uses the regex, maps index→name) — **OK**
- `:137-156` `_build_kwargs` DD5 drop-and-proceed (drop + named WARN; omit empty tools) — **OK**
- `:227-242` `stream()` BadRequestError temperature-retry → `tools.N` sub-path — **OK**
- `:284-293` `_to_anthropic_tool` (the Anthropic sanitize seam via `sanitize_tool_schema`) — **OK**
- `the_one/llm/openrouter_provider.py:124-149` `tool_schema` forward-with-WARN (anthropic/*-gated) — **OK**
- `:1-10` module docstring (the edit target) — **OK**
- `the_one/llm/base.py:347-360` default verbatim `tool_schema` (OpenAI/Ollama inherit) — **OK**
- `the_one/llm/_schema_sanitize.py:38` `UnsanitizableToolSchema`; `:172-176` raises on a
  non-object top-level combinator branch (the `{"anyOf":[{"type":"string"}]}` case) — **OK**
- Fixtures from prior legs: `tests/fixtures/tool_schemas.py` (`PRESS_KEY_INPUT_SCHEMA`,
  `make_bad_request`) and `tests/fixtures/scripted_transport.py` (harness) — both landed.

> Note: `the_one/llm/*` line numbers are stable (no production code changes in legs
> 01/02). The `tests/test_*` stub citations (e.g. `test_streaming.py:212-218`) refer
> to the current working-tree state; prefer symbol/shape over line number if they drift.
