# Flight: Cross-Provider Tool-Use Conformance Suite

**Status**: completed
**Mission**: [LLM Provider Layer Hardening & Capability Completeness](../../mission.md)

## Contributing to Criteria
- [x] A **cross-provider tool-use conformance test** exists and passes for Anthropic,
      OpenAI, Ollama, and Mock — asserting that a request→tool_call→tool_result→
      final-answer round-trip works uniformly through the `LLMProvider` contract.
      *(this is the regression net that stops future provider-quirk drift)*
- [x] No agent framework is added and the provider layer still wraps official SDKs;
      the `LLMProvider` contract and the provider-shape-portability convention
      (`Message.content` always `str`; `ToolResult` normalization) are preserved.
      *(trivially preserved — this flight is test/infra-only plus one docstring note;
      no production provider logic changes.)*

This flight also **guards** (does not re-implement) the two landed bug fixes:
- `#122` (Anthropic tool `input_schema` sanitization, Flight 2) — the conformance
  suite + #122 regression guards become its regression net.
- `#105` (open-model text-form tool-call recovery, Flight 3) — a fixtured loose-format
  recovery row joins the conformance matrix.

---

## Pre-Flight

### Objective

Build the **cross-provider tool-use conformance suite**: a provider-parametrized
pytest that drives the full `request → tool_call → tool_result → final-answer`
round-trip through the `LLMProvider` contract for **Anthropic, OpenAI, Ollama, and
Mock**, asserting each provider behaves uniformly at the canonical `Message` boundary.
This closes the last open tool-use mission criterion and becomes the **regression net**
that guards the #122 (Flight 2) and #105 (Flight 3) fixes against future provider-quirk
drift. The flight is **test- and infra-only**: it adds tests + a shared test-fixtures
module + one Makefile fix + one provider-docstring note, and resolves the one
deferred-from-Flight-2 **policy decision** (OpenRouter→Anthropic unsanitizable-schema
behavior) by formalizing the existing **forward-with-WARN** behavior as OpenRouter's
documented contract — pinned by a test, **no production logic change**. No new provider
capabilities, no agent-loop changes, no kernel promotion.

### Background (why this is the right shape)

The round-trip the criterion names lives **at the `LLMProvider` contract**, not in any
single provider: `complete()`/`stream()` returns a canonical `Message` whose
`tool_calls: list[ToolCall]` carry the model's tool intent; the caller dispatches and
appends a `Message.tool(ToolResult(...))`; the next `complete()`/`stream()` consumes
that history and returns the final answer. Each provider reaches that same canonical
shape over a **different wire dialect** — Anthropic via `tool_use`/`tool_result`
content blocks, OpenAI/Ollama via `tool_calls` deltas, Ollama additionally via
text-form recovery when `supports_tools()` is `False`. A conformance suite asserts the
*canonical* shape is uniform across all of them, regardless of dialect.

The repository already has the sibling test for **history encoding**:
`tests/test_llm_provider_cross_provider_history.py` pins each provider's
`_to_api_message()` against a canonical multi-shape session (pure-encoder tier) plus a
`@pytest.mark.live` cross-provider session-swap tier. This flight is its **tool-use
round-trip** counterpart: where that file pins *how a session is encoded onto the wire*,
this suite pins *that a tool-use turn round-trips back into a canonical `Message`* the
same way for every provider.

`Mock` (`the_one/llm/mock.py`) is **config-scriptable** (`config["response"]["tool_calls"]`
+ `config["stream_chunks"]`) and serves as the suite's **reference** round-trip — but
note `MockProvider.complete()` returns the *same* `config["response"]` on every call
(`mock.py:55-78`; it ignores message history), so a two-turn round-trip is driven by
**re-configuring (or re-instantiating) the Mock between turns** — turn-1 config carries
`response.tool_calls`, turn-2 config carries only `content`. With that, Mock runs the
canonical round-trip end-to-end with no transport fake. The three real providers
are driven through **per-provider scripted-transport fakes** built on the existing
mocked-SDK-client patterns (`tests/test_anthropic_provider.py` monkeypatch recorder;
`tests/test_streaming.py` Ollama SSE / OpenAI delta fakes) so the suite stays hermetic
and credential-free by default. A **light `@pytest.mark.live` tier** adds a real-API
confidence signal, reusing the existing live scaffolding rather than duplicating it.

This flight discharges the concrete follow-ups the Flight 2 and Flight 3 debriefs
handed forward (see Reconnaissance Report in the flight log; all four confirmed live):
the three #122 coverage gaps, the DD6 error-format pin, the OpenRouter parity decision,
the `make test-unit` marker-selection bug, and the shared-fixtures extraction (the
conformance suite is the fourth consumer that justifies it).

### Open Questions
- [x] **OpenRouter→Anthropic DD5/DD6 parity** (deferred from Flight 2). A
      *genuinely-unsanitizable* tool schema currently **forwards-with-WARN** on the
      OpenRouter `anthropic/*` route (`openrouter_provider.py:128-142`) and 400s the
      whole turn, whereas Anthropic-direct **drops** it (DD5) and proceeds. → **RESOLVED
      (operator, this flight): formalize forward-with-WARN as OpenRouter's documented
      contract.** No DD5 drop-and-proceed / DD6 name-mapping parity is added; the kernel
      is **not** promoted to a base method (the promotion trigger — a *symmetric*
      `tool_schema()`-seam caller — does not fire). The common `anyOf`/`oneOf` case (the
      real-world trigger) is already fixed on both paths; only the rare unsanitizable
      case diverges, and that divergence is now intentional and pinned by a test +
      module-docstring note (see DD3). Rationale: minimal blast radius (no change to the
      shared OpenAI tools-build path), honest ("no worse than today"), and the
      conformance criterion concerns the *round-trip*, not unsanitizable-schema handling.
- [x] **Conformance depth: contract-level vs full agent-loop.** → **Contract-level**
      (operator-confirmed). The criterion says "through the `LLMProvider` contract"; the
      suite drives `provider.complete()`/`stream()` directly with scripted transports,
      not `Agent._run_iterations`. Rationale: matches the criterion wording, stays a
      pure provider-layer regression net, and avoids coupling the net to agent-loop
      changes. (`Mock` still exercises a true multi-turn end-to-end because it needs no
      transport fake.) See DD1.
- [x] **Live tier vs hermetic-only.** → **Light live tier** (operator-confirmed),
      extending the existing live class rather than duplicating it (DD8).
- [x] **Which adjacent carry-forward items fold in.** → **All three** (operator-
      confirmed): the `make test-unit` marker fix (DD7), the shared test-fixtures module
      (DD6), and the DD6 error-format pin test (DD4). Each shares the test/infra surface
      this flight already edits.

### Design Decisions

**DD1 — Conformance is asserted at the `LLMProvider` contract, with per-provider
scripted-transport fakes; `Mock` is the reference end-to-end.** The suite drives
`provider.complete(...)` and `provider.stream(...)` directly and asserts the canonical
`Message`/`ToolCall`/`ToolResult` round-trip — it does **not** route through
`Agent._run_iterations`. For the three real providers, a **scripted transport** injects
a canned "turn-1 emits tool_call X" response then a "turn-2 emits final answer Y"
response, built per provider on the existing mocked-client patterns (Anthropic:
`monkeypatch` of `client.messages.create`/`.stream` with a per-call response queue,
`test_anthropic_provider.py`; OpenAI/OpenRouter and Ollama: `httpx.MockTransport` with a
stateful handler, `test_openrouter_provider.py` / `test_ollama_provider_recovery.py` /
`test_streaming.py`). `Mock` serves as the canonical reference the others are checked
against, **re-configured between turns** because `MockProvider` returns one response per
config (`mock.py:55-78`) — it is not history-aware.
- Rationale: the criterion is explicitly contract-scoped ("through the `LLMProvider`
  contract"); a provider-layer net must not depend on agent-loop behavior. Keeps the
  suite hermetic, fast, and credential-free by default.
- Trade-off: does not exercise the dispatch/iteration glue (that is the agent loop's
  own tests + the #105 behavior test). Acceptable — those layers are tested elsewhere;
  this net's job is provider-contract uniformity.

**DD2 — One canonical round-trip script, asserted on structural shape, not wire
byte-equality.** Define a single provider-neutral script — a tool definition, a turn-1
expectation (a `ToolCall` with a known `name` + `arguments`), a synthesized
`ToolResult`, and a turn-2 expectation (a final-answer `Message` with no `tool_calls`)
— and run every provider through it. The real providers use their scripted transports
(a per-call response queue); `Mock` is re-configured between the two turns (see
Background — `MockProvider` is single-response-per-config, not history-aware). Assertions
read the **canonical** objects
(`Message.tool_calls[0].name`/`.arguments`, `ToolResult` round-trip, final
`Message.content`/`.role`), mirroring the structural-not-byte-equal discipline already
used in `test_llm_provider_cross_provider_history.py`.
- Rationale: the canonical `Message` is the contract; the wire dialect is the
  provider's private business. Structural assertions catch real shape regressions (a
  dropped `tool_calls`, a mis-parsed `arguments`) without breaking on cosmetic wire
  differences.
- Includes the **`tools=None`/`tools=[]` path** end-to-end through each provider (the
  Flight-2 debrief's noted gap behind the `if tools:` guard): no tools offered → plain
  text round-trip, no `tool_calls`.

**DD3 — OpenRouter forward-with-WARN is formalized as the documented contract; pinned,
not changed.** Add (a) a test asserting the intentional asymmetry — on an
`anthropic/*` route with a genuinely-unsanitizable schema, OpenRouter **forwards** the
tool (no drop) and emits the WARN, whereas Anthropic-direct drops it — and (b) a
one-paragraph note in `openrouter_provider.py`'s module docstring explaining *why* the
two paths diverge (minimal-scope decision; the common combinator case is fixed on both;
the rare unsanitizable case is "no worse than today"). **No production logic changes**
to either provider; the kernel stays a leaf module (no promotion).
- Rationale: the operator chose minimal blast radius; the asymmetry is sound but was
  living only in code comments + Flight-2 artifacts. A pin test makes a future
  accidental change to either path surface as a red test; the docstring makes the
  intent legible at the call site.
- Trade-off: the same unsanitizable schema still behaves differently by route. Accepted
  and documented (the common case is fixed both ways; only the rare edge diverges).

**DD4 — #122 regression guards become part of the conformance surface.** Add the
specific guards the Flight-2 debrief enumerated, co-located with the conformance suite:
- **Cross-provider same-schema assertion** — feed the `press_key` top-level-`anyOf`
  fixture through each provider's tool-schema path and assert: sanitized (no top-level
  combinator, has top-level `type:"object"`) for **Anthropic** and for **OpenRouter
  `anthropic/*`**; left **verbatim** (combinator preserved) for **OpenAI** and **Ollama**
  and for **OpenRouter non-`anthropic/*`** routes.
- **OpenRouter `anthropic/*` `complete()`/`stream()` end-to-end smoke** — a scripted-
  transport round-trip with an `anthropic/*` slug, closing the "only `tool_schema()` is
  called directly today" gap.
- **`stream()` temperature-retry → `tools.N` sub-path** — assert the DD6 name-mapping
  fires on the *retry's* second call inside `stream()` (the defence-in-depth sub-path
  flagged at `anthropic_provider.py:229-231`).
- **DD6 error-format pin** (`test_tools_index_re_matches_known_format`) — assert
  `_TOOLS_INDEX_RE` (`anthropic_provider.py:29`) matches the confirmed first-party
  string `tools.0.custom.input_schema: …` so an Anthropic error-format drift surfaces as
  a red test rather than silent name-mapping loss.
- Rationale: these are exactly the coverage gaps + the format-monitoring test the
  Flight-2 debrief assigned to Flight 4; co-locating them with the conformance suite
  makes one file the tool-use regression net.

**DD5 — #105 loose-format recovery joins the conformance matrix as a fixtured row.**
Add an Ollama (`supports_tools()=False`) conformance case driven by a **recorded
loose-format emission** that must recover into a structured `ToolCall`, dispatch,
round-trip the `ToolResult`, and produce a final answer — the hermetic counterpart to
the live `gemma-tool-use-recovery` behavior test. Use the **kwargs-form** fixture
(`GEMMA_FIXTURE = "```tool\nget_weather(city='Paris')\n```"`, `test_toolcall_recovery.py:22`),
**not** the positional ` ```tool_code ` shell form (`test_toolcall_recovery.py:50-58`):
the positional form parks args under the `POSITIONAL_ARGS_KEY` sentinel that the
*dispatcher* (not the provider) resolves, which a contract-level round-trip deliberately
does not exercise (DD1 trade-off).
- Rationale: brings the #105 fix under the same uniform-round-trip assertion as the
  structured providers; deterministic (fixtured, no live model), satisfying the
  mission's "test-backed with a recorded/fixtured Gemma response" requirement.
- Trade-off: a fixtured emission can drift from real gemma output (the Flight-3 lesson:
  a non-deterministic model's format is a distribution). Mitigated — the live behavior
  test remains the breadth check; this row guards the *recovery path's* round-trip
  shape, not gemma's output distribution.

**DD6 — Extract the shared test-fixtures module.** Lift the duplicated `PRESS_KEY`
schema constant and the `_mk_bad_request()` helper into a single `tests/fixtures/`
module (or a `conftest`-level helper, implementer's call at design) and refactor their
**actual** callers — which differ per fixture (Architect-verified against the tree, not
the same three files):
- **`PRESS_KEY` schema constant** — byte-identical in `test_openrouter_provider.py:16`
  and `test_schema_sanitize.py:23` (NOT in `test_anthropic_provider.py`, which builds a
  *different, simpler* inline `anyOf` via `_tool(...)`). A near-variant `PRESS_KEY_RAW`
  lives in `test_anthropic_live.py:56`. Extract the shared constant; refactor the two
  exact callers; **converge the `PRESS_KEY_RAW` variant too** (the "kill drift" rationale
  argues for one canonical fixture).
- **`_mk_bad_request()` helper** — defined only in `test_anthropic_provider.py:40`; a
  *non-identical* variant `_make_bad_request()` (MagicMock body vs real `httpx.Response`)
  lives in `test_streaming.py:170`. Extract the helper; refactor the one real caller;
  **converge the `test_streaming.py` variant** (cleanest moment to unify the two error
  builders).
- The conformance suite is the **fourth** consumer overall — the threshold the Flight-2
  debrief set for extraction.
- Rationale: kills the multi-file manual-sync drift across both fixtures and their
  near-variants; gives the new suite a clean import.
- Trade-off: touches the existing green test files above (pure refactor, no behavior
  change) — verified by those files staying green.

**DD7 — Fix the `make test-unit` marker-selection bug (additive deselection).** The
`make test-unit` recipe (`Makefile:113`) passes `-m 'not browser and not live and not
pixel'`, which **replaces** (last-`-m`-wins) the pyproject `addopts` deselection
(`pyproject.toml:86`) of `requires_bwrap`/`discord_hat`, silently running the
`requires_bwrap` tests (they pass only because this host has `/bin/bwrap`). Make the
recipe's `-m` expression **additive**: `… and not requires_bwrap and not discord_hat`.
- Rationale: low-effort correctness fix; prevents a bwrap-less-host / CI surprise. This
  flight runs the full suite repeatedly, so it is the natural home (Flight-3 debrief
  Rec 2). Prefer the lowest-drift form at design: either drop the recipe's `-m` entirely
  so it inherits the full `addopts` deselection, or keep a `-m` override with a one-line
  comment tying it to `addopts` (the marker list lives in two places today — `Makefile:113`
  and `pyproject.toml:86` — so they should be maintained together).
- Trade-off: re-baselines the `make test-unit` passing count (the ~12 `requires_bwrap`
  tests move from "run" to "deselected"). Captured in the verify-integration leg.

**DD8 — Light `@pytest.mark.live` tier, extending the existing live class.** Add a
small key-gated, self-skipping live tool round-trip to the conformance suite, reusing
the live scaffolding in `test_llm_provider_cross_provider_history.py` /
`test_input_tokens_cross_provider_live.py` (`_resolve_ollama`, `_aclose_provider_client`,
inline `pytest.skip` on missing keys). Confidence signal only — no exact-content
assertions (LLMs are non-deterministic).
- Rationale: an inexpensive real-API confidence check without duplicating the existing
  cross-provider-history live tests. **Anti-duplication check (mandatory at design):**
  `test_llm_provider_cross_provider_history.py:671` already has
  `test_anthropic_with_tools_to_ollama_swap_live` (a tool-payload swap). The new live
  test must add genuinely distinct coverage (e.g. a full two-turn tool→result→final
  round-trip, or a provider/pair the existing one doesn't cover) or be skipped — confirm
  concretely against that test before adding.
- Trade-off: live tests are deselected by default and only run with credentials; they
  are not the regression net (the hermetic tiers are).

### Prerequisites
- [ ] Optional LLM SDK extras present for hermetic runs (`openai`, `anthropic`) — i.e.
      `.venv` built with `.[all-llms,dev]` (Flight-2 verification confirmed these are
      required for the provider test files to import).
- [ ] `press_key` top-level-`anyOf` fixture available (already captured in the Flight-2
      test files; moves into the shared fixtures module in DD6).
- [ ] Flight-3 loose-format recovery fixture available (captured in
      `tests/test_toolcall_recovery.py` / `test_ollama_provider_recovery.py`; reused for
      DD5, no live model needed).
- [ ] **For the light live tier only** (DD8): `ANTHROPIC_API_KEY` and/or a reachable
      Ollama with a tool-capable model; tests self-skip when absent. Not required for the
      hermetic suite or for the flight to land.

### Pre-Flight Checklist
- [x] All open questions resolved (OpenRouter parity → forward-with-WARN; depth →
      contract-level; live → light tier; scope folding → all three) — operator-ratified
- [x] Design decisions documented (DD1–DD8)
- [x] Prerequisites identified (SDK extras; fixtures already in-repo; live keys optional)
- [x] Validation approach defined (hermetic parametrized suite + #122/#105 guards +
      light live tier; full-suite verify-integration with re-baselined counts)
- [x] Legs defined (5; optional UAT/alignment deliberately omitted — see Legs)

---

## In-Flight

### Technical Approach

Build foundation-first. **Leg 01** extracts the shared test-fixtures module (DD6) and
refactors the three existing callers — a pure, behavior-preserving refactor that gives
the new suite a clean import and is verified by the three files staying green.
**Leg 02** builds the per-provider scripted-transport harness and the central
provider-parametrized round-trip conformance test (DD1/DD2) over {Anthropic, OpenAI,
Ollama, Mock}, including the `tools=None/[]` path. **Leg 03** adds the #122 regression
guards + the DD6 error-format pin + the forward-with-WARN contract pin and docstring
note (DD3/DD4) — no production logic changes. **Leg 04** adds the #105 fixtured
loose-format recovery row (DD5) and the light live tier (DD8). **Leg 05** fixes the
`make test-unit` marker selection (DD7) and runs verify-integration: full suite green,
counts re-baselined and compared to the Flight-3 figure, `requires_bwrap` confirmed
deselected.

### Checkpoints
- [x] Shared fixtures module exists; the three prior callers import it and stay green
- [x] Provider-parametrized round-trip conformance test passes for Anthropic, OpenAI,
      Ollama, and Mock (incl. the `tools=None/[]` path)
- [x] #122 guards green: cross-provider same-schema assertion; OpenRouter `anthropic/*`
      `complete()`/`stream()` smoke; `stream()` temp-retry→`tools.N`; DD6 format pin
- [x] OpenRouter forward-with-WARN pinned by a test + module-docstring note (no logic
      change)
- [x] #105 fixtured loose-format recovery round-trip passes in the matrix
- [x] Light live tier present, key-gated, self-skips cleanly without credentials
- [x] `make test-unit` marker selection additive; `requires_bwrap`/`discord_hat`
      confirmed deselected; full suite green with re-baselined counts recorded

### Adaptation Criteria

**Divert if**:
- A provider genuinely **cannot** be driven through a scripted transport without a
  production seam change (would breach the test-only scope) — surface to the operator
  before adding any non-test code beyond the DD3 docstring + DD7 Makefile fix.
- The conformance suite reveals a **real** cross-provider divergence in the canonical
  round-trip (not a test artifact) — that is a genuine bug; record it, escalate scope
  (it may belong in its own fix leg/flight rather than being papered over in the test).

**Acceptable variations**:
- Exact location/shape of the shared fixtures module (`tests/fixtures/` package vs
  `conftest` helpers) and the scripted-transport harness API.
- `parametrize` structure (single matrix vs per-provider classes), provided one
  canonical script drives all providers (DD2).
- Whether the live tier lives in the conformance file or extends the existing live
  class in place, provided it does not duplicate existing live coverage.

### Legs

> **Note:** Tentative; planned and created one at a time as the flight progresses.

- [x] `shared-test-fixtures` — extract the duplicated `PRESS_KEY` schema constant and the
      `_mk_bad_request()` helper into a shared `tests/fixtures/` module; refactor their
      **actual** callers (`PRESS_KEY`: `test_openrouter_provider.py` + `test_schema_sanitize.py`,
      converging `test_anthropic_live.py`'s `PRESS_KEY_RAW` variant; `_mk_bad_request`:
      `test_anthropic_provider.py`, converging `test_streaming.py`'s `_make_bad_request`
      variant). Pure refactor; acceptance = all touched files stay green and no fixture is
      defined in more than one place. (DD6)
- [x] `roundtrip-conformance` — build the per-provider scripted-transport harness and
      the provider-parametrized `request→tool_call→tool_result→final-answer` round-trip
      test across {Anthropic, OpenAI, Ollama, Mock}, asserting the canonical
      `Message`/`ToolCall`/`ToolResult` shape (DD1/DD2); include the `tools=None/[]`
      plain-text path. `Mock` is the reference end-to-end (re-configured between turns,
      since `MockProvider` is single-response-per-config); the real providers use scripted
      transports modeled on the existing mocked-client patterns. **No hard dep on
      `shared-test-fixtures`** — the round-trip needs only a tool definition + canonical
      script, not the `press_key`/`_mk_bad_request` fixtures. Runs after leg 01 for
      cleanliness but is not blocked on it.
- [x] `schema-122-guards` — add the #122 regression guards (cross-provider same-schema
      sanitized-vs-verbatim assertion; OpenRouter `anthropic/*` `complete()`/`stream()`
      smoke; `stream()` temperature-retry→`tools.N` sub-path) + the DD6 error-format pin
      test; formalize the OpenRouter **forward-with-WARN** contract with a pin test + a
      module-docstring note in `openrouter_provider.py`. **No production logic changes.**
      **Dep:** consumes the shared `PRESS_KEY` + `_mk_bad_request` fixtures from
      `shared-test-fixtures` (this is the real consumer of those fixtures). (DD3/DD4)
- [x] `recovery-105-and-live` — add the #105 fixtured loose-format recovery row to the
      conformance matrix (Ollama `supports_tools()=False`: the **kwargs-form** recorded
      emission `GEMMA_FIXTURE` at `test_toolcall_recovery.py:22` → recovered `ToolCall` →
      dispatch → `ToolResult` → final answer) (DD5); add the light
      `@pytest.mark.live` cross-provider tool round-trip extending the existing live
      scaffolding, key-gated + self-skipping (DD8).
- [x] `test-infra-and-verify` — fix the `make test-unit` `-m` expression to be additive
      (`… and not requires_bwrap and not discord_hat`, DD7); verify-integration: run the
      full suite, confirm green, confirm `requires_bwrap`/`discord_hat` now deselected,
      record re-baselined pass/skip/deselect counts. Report the delta **explicitly and
      auditably** against the Flight-3 figure (`3302 passed / 18 skipped / 541 deselected`):
      DD7 moves ~12 `requires_bwrap` + 5 `discord_hat` ≈ 17 tests from passed→deselected,
      then this flight adds N new conformance/guard tests to passed — so expect roughly
      `passed ≈ 3302 − 17 + N`, `deselected ≈ 541 + 17`. Update any docs the flight's
      changes warrant (e.g. a one-line provider-quirk note if the project keeps one).

> **Optional `uat-and-alignment` deliberately omitted.** This is a hermetic
> test/infra flight with no interactive surface to align; the mission already carries a
> separate optional **Alignment** flight (Flight N) for hands-on real-model tuning. The
> light live tier (DD8) covers the real-API confidence signal.

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing (`make test-unit` hermetic, green, with `requires_bwrap`/`discord_hat`
      deselected; live tier green when run with credentials)
- [x] Documentation updated (OpenRouter module-docstring note shipped; the `agents.md`
      provider-quirk pointer was deferred as a finding — not blocking, recorded for
      follow-up)

### Verification
- **Hermetic (primary):** the provider-parametrized conformance suite passes for
  Anthropic/OpenAI/Ollama/Mock (incl. `tools=None/[]`); the #122 guards + DD6 format pin
  + forward-with-WARN pin are green; the #105 fixtured recovery row is green.
- **Live (gated):** the light `@pytest.mark.live` tool round-trip passes against real
  APIs when credentials are present and self-skips cleanly when absent.
- **Suite health:** `make test-unit` runs the correct deselection set
  (`requires_bwrap`/`discord_hat` no longer silently included); full-suite counts
  recorded and compared to the Flight-3 baseline; net change explained (new conformance
  tests added; `requires_bwrap` tests move to deselected).
- **Scope guard:** `git diff` shows no production provider *logic* changes — only test
  files, the shared fixtures module, the `openrouter_provider.py` docstring note, and the
  `Makefile` recipe.
