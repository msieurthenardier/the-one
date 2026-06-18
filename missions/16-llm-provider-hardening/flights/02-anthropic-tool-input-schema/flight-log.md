# Flight Log: Anthropic Tool `input_schema` Compatibility (#122)

**Flight**: [Anthropic Tool `input_schema` Compatibility (#122)](flight.md)

## Summary

Planning. Spec authored from the Flight 1 recon (live-reproduced #122) and the Flight
1B capability audit. Direction ratified with the operator: sanitize tool schemas in
the Anthropic adapter regardless of source MCP server (crashing is not an option),
union-merge for `anyOf`/`oneOf`, drop-and-proceed for genuinely-unsanitizable tools,
plus a `BadRequestError → tool-name` defensive net. Real-world trigger (goldfinch
`press_key` top-level `anyOf`) filed as a complementary source-side cleanup
(goldfinch#56) and adopted as this flight's primary test fixture.

---

## Flight Director Notes

- 2026-06-18 — `/agentic-workflow` started (Flight Director orchestrating). Loaded
  mission 16, flight 2, flight log, and `leg-execution.md` crew (validated: Crew +
  Interaction Protocol + Prompts present). Crew: Developer (Sonnet), Reviewer (Haiku).
- **Branch base decision (operator-ratified):** Flight 1B (PR #126, open, based on
  `main`) made zero code changes (read-only audit), so Flight 2 branches from `main`
  as `flight/02-anthropic-tool-input-schema` for a clean, independent PR rather than
  stacking on the unmerged #126. 1B's debrief (uncommitted in the working tree) was
  committed onto its own branch (#126) first, not folded into Flight 2.
- Flight status `ready` → `in-flight`. `leg 01` already designed and `ready` from
  planning; proceeding to its design review per Phase 2a before implementation.
- **Batched-review mode:** autonomous legs (01, 02, 03, 04) implement without
  per-leg commit; single Reviewer pass + commit after the last autonomous leg.
  `uat-and-alignment` is optional/interactive — handled with the operator if reached.
- 2026-06-18 — `leg 01` design review (Developer/Sonnet): **approve with changes**,
  all issues low-severity. Incorporated without a second cycle (additive only):
  added acceptance criteria for empty-combinator-list, both-`anyOf`+`oneOf`, and the
  top-level-`$ref`-alongside-object-shape DD3 boundary; pinned array-`type` collapse
  to the scalar string `"object"`; merge note appended exactly once. Also fixed a
  flight-spec DD2 citation: `Tool.to_schema()` is `the_one/tools/base.py:106-110`
  (the prior `base.py:108-110` pointed at the `Message` dataclass) — matters for
  `leg 02`'s non-mutation contract. Proceeding to implement `leg 01`.
- 2026-06-18 — `leg 01` (`sanitize-tool-schema`) **implemented** (Developer).
  - **Built**: `the_one/llm/_schema_sanitize.py` — pure, stdlib-only (`import copy`
    only) kernel exporting `sanitize_tool_schema(schema: dict | None) -> dict` and
    `class UnsanitizableToolSchema(Exception)` (carries `.reason`). Order of ops per
    guidance: merge combinators (allOf = union required; anyOf/oneOf = intersection
    of branch requireds, then unioned with base required) BEFORE reconciling `type`;
    array `type` containing `"object"` collapses to the scalar string `"object"`;
    colliding property keys across branches become a nested `{"anyOf": [...]}`
    (identical variants dedup); empty combinator lists drop without raising; both
    `anyOf`+`oneOf` processed with the merge note appended exactly once; bare
    top-level `$ref`/`not` (no object shape) raise, but a `$ref` *alongside* an
    object shape is preserved untouched (DD3). Operates on a `copy.deepcopy` — input
    stays `is`-identical and byte-unchanged (DD2).
  - **Tests**: `tests/test_schema_sanitize.py` — 32 class-grouped plain-`def` unit
    tests (modeled on `test_llm_base.py`), one per acceptance criterion incl. the
    newly-added rows. `pytest tests/test_schema_sanitize.py -q` → **32 passed**.
    High-risk subset (`-k "non_mutation or press_key or nested"`) → 4 passed.
  - **Verification env note**: Docker was unavailable in the execution shell (Docker
    Desktop daemon not running / no WSL integration), so the leg's `docker exec
    the-one pytest ...` command could not run as written. Verified instead host-native
    via the repo `.venv` (`python 3.12.3`, `pytest 8.4.2`) — equivalent for this leg
    since the module is pure stdlib with no container-only deps; CLAUDE.md documents
    `make test-unit` as a host-native path. Re-running under `docker exec` before the
    flight commit is advisable but expected to be a no-op.
  - **Lint**: `ruff check` clean. `UnsanitizableToolSchema` triggers N818
    (no `Error` suffix), but the name is the F02 cross-leg contract (leg 02 imports it
    verbatim) — suppressed with a targeted `# noqa: N818` + rationale, following the
    existing `the_one/mcp/errors.py:13` precedent for contract-mandated exception
    names. `ruff format --check` clean.
  - Observations: spec ↔ lint conflict on the exception name resolved in favor of the
    contract (noqa, precedent-backed) rather than renaming — flagged here so leg 02
    and review are aware.
- 2026-06-18 — **Environment anomaly: Docker unavailable** in this orchestration shell
  (daemon not running / no WSL integration). Crew prompt mandates `docker exec the-one
  pytest`. Mitigation: verified `.venv` has `anthropic 0.97.0` + `pytest`; autonomous
  legs fall back to host-native `.venv/bin/pytest` (CLAUDE.md documents `make test-unit`
  as a host-native path). Acceptable for legs 01–02 (pure-stdlib kernel + mocked-client
  adapter tests — no container-only deps); leg 04's live test is `@pytest.mark.live`,
  deselected by `make test` regardless. Recorded as an anomaly for the debrief.
- 2026-06-18 — `leg 02` (`wire-into-anthropic-adapter`) designed → `ready`
  (`legs/02-wire-into-anthropic-adapter.md`). Line refs verified against current source
  (`_to_anthropic_tool` 210-215, `_build_kwargs` 75-100, `complete()` except 114-121,
  `stream()` except 162-168). Design review (Developer/Sonnet): **approve with changes**.
  Incorporated all (reviewer's own prescriptions, no new design risk — skipped 2nd cycle):
  - [high] documented the `anthropic.BadRequestError` construction gotcha (required
    keyword-only `response`/`body` on 0.97.0) + a `_mk_bad_request` test factory.
  - [med] flagged the intentional `tool_def.get("parameters")` change (vs the current
    `KeyError`-on-absence subscript) so it isn't "restored".
  - [low] softened the empty-`tools` criterion to "omit the key to be safe" (no SDK
    dependency claimed).
  - Pinned the DD6 wrapping type (resolves Q1): re-raise `anthropic.BadRequestError`
    reusing the caught `exc.response`/`exc.body`, message names the tool — keeps the
    public type stable and dodges the construction gotcha.
  - Resolved Q2: `stream()` temperature-retry→`tools.N` is defence-in-depth — mirror in
    code, no dedicated test required; `stream()` still gets the first-call `tools.N` test.
  Proceeding to implement `leg 02`.
- 2026-06-18 — `leg 02` (`wire-into-anthropic-adapter`) **implemented + landed**
  (Developer). 17 mocked-client tests pass; leg-01 suite still 32; ruff clean. DD5
  drop-and-proceed (omit `tools` when all dropped, named+reason warning) + DD6 name-map
  re-raising `anthropic.BadRequestError` reusing `exc.response`/`exc.body` in both
  `complete()` and `stream()` incl. the temperature-retry's second call. Host-native run.
- 2026-06-18 — `leg 03` reframed by an **empirical finding** (see Anomalies): the live
  OpenRouter probe proved OpenRouter→Anthropic 400s on #122 (it does NOT normalize).
  Operator decision (asked): **minimal wire now** — sanitize in
  `OpenRouterProvider.tool_schema` gated to `anthropic/*` routes; unsanitizable schemas
  fall back to the original (still 400) with a WARN; **no DD5 drop-and-proceed / DD6
  named-error parity** on this path (those stay Anthropic-direct-only). Designed →
  `ready`. Design review (Developer/Sonnet): **approve** (no blocking issues). Folded in:
  WARN on the unsanitizable fallback (observability, not drop-and-proceed — reviewer Q1);
  test-docstring note that the single `tool_schema` override covers both `complete()` and
  `stream()`; Q2 resolved (fallback is unit-level only, no leg-04 live coverage). Skipped
  2nd cycle (additive). Proceeding to implement `leg 03`.
- 2026-06-18 — `leg 03` (`openrouter-anthropic-check`) **implemented + landed**
  (Developer).
  - **Built**: modified `the_one/llm/openrouter_provider.py` only. Added a `tool_schema`
    override that calls `super().tool_schema(tool_def)` (OpenAI function shape), then —
    **only when `self.model.startswith("anthropic/")`** — runs the leg-01
    `sanitize_tool_schema` on `result["function"]["parameters"]`. On
    `UnsanitizableToolSchema` it falls back to the original parameters (exception does
    NOT escape) and emits a WARN naming the tool via a new module logger
    (`logging.getLogger(__name__)`). Non-anthropic slugs pass through verbatim (gate
    skipped). DD2 preserved: `super().tool_schema()` returns a fresh dict and the override
    reassigns its `parameters` key to the kernel's deep-copied output, so the caller's
    `tool_def["parameters"]` stays `is`-identical and byte-unchanged. The single override
    is the shared chokepoint for both `complete()` (`openai_provider.py:130`) and
    `stream()` (`:182`). **No DD5 drop-and-proceed / DD6 named-error parity** on this path
    (minimal scope, operator 2026-06-18) — those stay Anthropic-direct-only.
  - **Tests**: `tests/test_openrouter_provider.py` extended with `TestToolSchemaAnthropicSanitize`
    — 5 tests (provider constructed directly, no network; `tool_schema` is pure/sync),
    one per acceptance criterion: anthropic-route-sanitizes (press_key anyOf → no
    top-level anyOf, type:object), non-anthropic-route-untouched (`openai/gpt-4o` keeps
    the anyOf), non-mutation (`is`-identity + byte-unchanged + distinct returned object),
    unsanitizable-falls-back-no-raise + WARN (`caplog`, logger
    `the_one.llm.openrouter_provider`, bare top-level `$ref`, returns original params),
    clean-schema near-no-op (asserts properties unchanged, not whole-dict equality).
    Reuses the leg-01 `press_key` fixture (inlined). `.venv/bin/pytest
    tests/test_openrouter_provider.py -x --timeout 30 -q` → **23 passed** (18 prior + 5 new).
  - **No regression**: `.venv/bin/pytest tests/test_schema_sanitize.py
    tests/test_anthropic_provider.py -q` → **49 passed** (32 + 17, legs 01–02 unaffected).
  - **Verification env note**: Docker unavailable in the execution shell (confirmed, as in
    legs 01–02) — verified host-native via `.venv` (`python 3.12.3`, `pytest 8.4.2`). The
    override is pure/synchronous and the tests construct the provider directly with no
    network, so no container is needed; equivalent path.
  - **Lint**: `ruff check the_one/llm/openrouter_provider.py tests/test_openrouter_provider.py`
    clean; `ruff format --check` clean on both files.
  - Scope held: no changes to `OpenAIProvider` (OpenAI-direct keeps schemas verbatim),
    the Anthropic adapter, `base.py`, the MCP layer, or the web UI. Flight Open Question
    (OpenRouter→Anthropic) checked off in `flight.md`; DD1's OpenRouter-reuse note
    annotated (speculative case became real, wired gated+minimal).
- 2026-06-18 — `leg 04` (`live-verify-anthropic`) designed → `ready`
  (`legs/04-live-verify-anthropic.md`). `@pytest.mark.live` test (deselected by default;
  marker registered `pyproject.toml:86,89`) modeled on
  `tests/test_input_tokens_cross_provider_live.py` (self-skip on missing key,
  `LIVE_ANTHROPIC_MODEL` default `claude-haiku-4-5-20251001`, direct async provider,
  `aclose()` teardown). Three checks: real Anthropic accepts the sanitized `press_key`
  end-to-end through `complete()`; still 400s on the raw schema (direct SDK bypass); pins
  leg-01's provisional array-`type` collapse. Design review (Developer/Sonnet): **approve
  with changes** — folded in (additive, skipped 2nd cycle): [med] loosened the rejection
  assertion (the #122 wording was only seen via OpenRouter→Bedrock; bind on
  `BadRequestError` + `"anyOf"` + tolerant `top[- ]level` regex, record exact wording — a
  surprise-wording 400 is a brittle miss, NOT a leg-01 divert); [low] fixed `aclose()`
  line ref (`:106`, not `:67`) + consistent `provider.aclose()` teardown; added a result
  sanity check; noted the 400 is request-validation (endpoint-level, model-independent →
  cheap model is a valid proxy). Divert reserved strictly for "sanitized scalar form
  rejected." `ANTHROPIC_API_KEY` present in gitignored `.env` → FD will run the live test
  for real (not skipped). Proceeding to implement `leg 04`.
- 2026-06-18 — `leg 04` (`live-verify-anthropic`) **landed**: live run **3 passed** against
  first-party Anthropic. Key findings: first-party #122 wording is verbatim
  `tools.0.custom.input_schema: input_schema does not support oneOf, allOf, or anyOf at the
  top level`; the array-`type` pin **rejected** raw `["object","null"]` (`Input should be
  'object'`) and **accepted** the leg-01-sanitized scalar `"object"` → leg-01's collapse
  rule is **correct and load-bearing**, no divert. Regression suites 72 passed.
- 2026-06-18 — **All four autonomous legs landed.** Single flight Reviewer (Haiku,
  independent — Phase 2d) reviewed the full uncommitted diff (the_one/llm/_schema_sanitize.py
  + anthropic_provider.py + openrouter_provider.py + 3 test files + test_openrouter edits):
  **[HANDOFF:confirmed]** — all leg acceptance criteria + DD1–DD6 met, 72 hermetic tests
  pass, live tests properly gated/deselected, ruff clean, scope confined to `the_one/llm/`,
  no secrets or operator paths leaked. No fix cycles needed. Legs 01–04 → `completed` and
  checked off in flight.md. Committing the flight; flight status held `in-flight` pending
  the operator's call on the optional `uat-and-alignment` leg before landing.
- 2026-06-18 — Flight committed (`216b098`), draft PR **#127** opened (base `main`).
  Operator chose to **land now, skip the optional `uat-and-alignment`** (leg 04's live
  first-party verification already satisfies the core #122 acceptance criterion). Doc check
  (Phase 3): **N/A** — internal provider-layer robustness fix, no new commands / endpoints /
  config / agent-facing contract; no CLAUDE.md/README change warranted. Flight status →
  **landed**; mission Flight 2 + the #122 success criterion checked off. PR #127 marked
  ready for review. `[COMPLETE:flight]`. The flight debrief is the separate `/flight-debrief`
  step (transitions the flight to `completed`).

## Decisions

### Cross-project: goldfinch source-side cleanup filed (complementary, not a substitute)
**Context**: The schema that triggers #122 in the wild is goldfinch's `press_key` tool
(`goldfinch/src/main/automation/mcp-tools.js:257-274`), which uses a legal top-level
`anyOf` to express "at least one of `name`/`key`".
**Decision**: File goldfinch#56 recommending goldfinch drop the top-level `anyOf` to be
more LLM-friendly. This does **not** descope Flight 2 — the-one must sanitize
defensively because it cannot assume every connected MCP server avoids the idiom.
**Impact**: goldfinch#56 tracked on the goldfinch repo; `press_key` schema captured as
the-one's primary sanitizer fixture (no live goldfinch dependency).

---

## Deviations

_None yet._

---

## Anomalies

### Leg 03 empirical finding contradicts the spec's "likely outcome": OpenRouter→Anthropic DOES reject #122
**Observed**: A live OpenRouter probe (`anthropic/claude-3.5-haiku`, via the OpenAI-compat
endpoint, tool sent in OpenAI function shape) returned **400** for the raw `press_key`
schema (top-level `anyOf`) with the verbatim #122 error —
`tools.0.custom.input_schema: input_schema does not support oneOf, allOf, or anyOf at the
top level` (provider: **Amazon Bedrock** backing Anthropic). The sanitized control schema
(no top-level `anyOf`) was **accepted** and produced a tool call. Probe script:
`/tmp/or_anthropic_probe.py` (outside the repo, not committed; reads keys from the
gitignored `.env`).
**Severity**: degraded — real users routing to `anthropic/*` via OpenRouter hit #122 today,
exactly as on the direct Anthropic path. The flight's pre-flight "likely outcome" (OpenRouter
owns the translation → scope out) is **falsified**; OpenRouter passes the schema through.
**Resolution**: The flight's Adaptation rule is met — *demonstrably rejects* AND a clean
adaptation exists (the leg-02 `sanitize_tool_schema` kernel is schema-in/schema-out and
provider-neutral; it can post-process the `parameters` of OpenRouter's inherited OpenAI tool
shape, gated to `anthropic/*` model slugs). Escalated to operator for the scope decision
(minimal-wire-now vs. defer to a follow-up flight) — see Flight Director Notes.

---

## Session Notes

- 2026-06-17 — Spec authored. Open question deliberately left live: OpenRouter→Anthropic
  routing (resolved in `leg 03`). Copy-button-on-error-bubble UI enhancement (bundled
  with #122) split out of this flight per operator (different surface; UI changes are
  out of mission scope).
- 2026-06-17 — Architect design review (Phase 5b): **approve with changes**.
  Incorporated all high/medium issues without a second cycle (changes were the
  architect's own prescriptions — no new design risk):
  - DD6 now composes with the **existing** single `except BadRequestError`
    (temperature-retry) via ordered checks, maps the index against the **post-drop**
    tools list (DD5), and covers the temperature-retry's second call.
  - DD4 table gained the missing top-level cases (array-valued `type` → collapse to
    object [pinned live in `leg 04`]; bare `$ref`; `not`; non-object `allOf` branch;
    missing `parameters` key) and the unsanitizable signal contract
    (`UnsanitizableToolSchema(reason)`).
  - DD2 rationale strengthened with the concrete shared-reference chain
    (`to_schema` → `self.parameters` → `mcp_tool.input_schema` → `client.py:717`
    arg-validation); non-mutation test asserts `is`-identity.
  - DD1 reframed around testability/isolation; OpenRouter-reuse downgraded to
    speculative (OpenRouter rides the OpenAI tool path, never emits `input_schema`).
  - Module is stdlib-only (leaf). Adapter tests are net-new (no anthropic test file
    exists). Drifted line numbers corrected.
- 2026-06-17 — Architecture question raised by operator: should sanitization be a
  uniform per-connector interface method (C#-style) rather than an Anthropic-only
  helper? Resolved against the **Flight 1B audit evidence**: tool-schema sanitization
  is **Anthropic-only** today (OpenAI accepts our schemas; Ollama #105 is the inverse
  problem; OpenRouter inherits OpenAI). The cross-provider per-provider differences the
  audit found are *capability gaps* (already served by the existing `tool_schema()` /
  `_to_api_message()` override seam), not sanitization. **Decision (operator-ratified):
  build the pure kernel now, Anthropic calls it from its existing override; defer the
  uniform `LLMProvider.sanitize_tool_schema()` base method until a second real caller
  exists** (dormant OpenAI-strict structured-output case, or Flight 4 conformance).
  Promotion is then a mechanical refactor. Recorded in DD1.
- 2026-06-18 — Flight status → **ready** (operator-confirmed). Pre-flight checklist
  satisfied; OpenRouter→Anthropic open question deliberately deferred into `leg 03`.
  Proceeding to design `leg 01` (`sanitize-tool-schema`).
- 2026-06-18 — `leg 01` (`sanitize-tool-schema`) designed and set to **ready**
  (`legs/01-sanitize-tool-schema.md`). Pure stdlib-only kernel + `UnsanitizableToolSchema`
  + exhaustive unit suite (all DD4 rows, `press_key` real fixture, `is`-identity
  non-mutation, `$defs`/nested-`$ref` preservation). Citations verified clean. No
  source touched by this leg's design (planning artifact only).
- 2026-06-18 — `leg 02` (`wire-into-anthropic-adapter`) **implemented** (Developer).
  - **Built**: modified `the_one/llm/anthropic_provider.py` only.
    - `_to_anthropic_tool` now calls `sanitize_tool_schema(tool_def.get("parameters"))`
      for `input_schema` (DD1/DD2). Intentional `.get("parameters")` (not subscript) so a
      tool with no `parameters` key flows to the kernel as `None` → `{"type": "object"}`;
      `name`/`description` stay subscripts (contract-guaranteed). The kernel deep-copies, so
      the caller's `tool_def`/`parameters` is never mutated.
    - `_build_kwargs` replaced the `tools` list-comprehension with a per-tool
      `try/except UnsanitizableToolSchema` drop-and-proceed loop (DD5): a genuinely
      unsanitizable tool is dropped (not fatal) with a `logger.warning` naming the tool
      and its `.reason`; if every tool drops, the `tools` key is omitted entirely (never
      send `[]`). The post-drop `sent_tools` list is the single source of truth for tool
      ordering. Added a module logger (`logging.getLogger(__name__)`).
    - DD6 `BadRequestError → tool-name` net: module-level `_name_offending_tool(exc,
      sent_tools)` matches `tools\.(\d+)\.`, maps the index against the post-drop list,
      and re-raises as `anthropic.BadRequestError` **reusing the caught `exc.response`/
      `exc.body`** (PINNED — no new exception type) with a message naming the tool and
      quoting the original error; returns `None` (→ original re-raised unchanged) when no
      index, no sent tools, or out-of-range. Folded into the EXISTING `except
      anthropic.BadRequestError` in both `complete()` and `stream()` with ordered checks
      (temperature branch first/unchanged → `tools.N`→name → plain re-raise), wrapping the
      temperature-retry's second call too. `raise (named or exc) from exc` preserves
      `__cause__`.
  - **Tests**: `tests/test_anthropic_provider.py` — **new**, 17 mocked-client tests, one
    per acceptance criterion: press_key anyOf→no top-level anyOf, adapter-boundary
    non-mutation (`is`-identity + byte-equal), clean-schema passthrough, missing-parameters
    →`{"type":"object"}`, one-bad-tool-dropped-rest-succeed, named+reason warning (via
    `caplog` targeting `the_one.llm.anthropic_provider`), all-tools-unsanitizable (no `tools`
    key), temperature-branch-fires-first (complete + stream), `tools.N`→name (complete +
    stream), index-shift maps post-drop, temperature-retry second call name-maps (complete
    only), out-of-range index → original error unchanged, non-`tools.N` re-raised unchanged
    (complete + stream), and the streaming happy-path smoke test. Used the `_mk_bad_request`
    factory (keyword-only `response`/`body`) and an async-CM stream stub with async
    `text_stream` + awaitable `get_final_message()` per the test-harness gotchas.
    `.venv/bin/pytest tests/test_anthropic_provider.py -x --timeout 30 -q` → **17 passed**.
  - **No cross-contamination**: `.venv/bin/pytest tests/test_schema_sanitize.py -q` →
    **32 passed** (leg 01 unaffected).
  - **Verification env note**: Docker unavailable in the execution shell (confirmed, as in
    leg 01) — verified host-native via `.venv` (`python 3.12.3`, `pytest 8.4.2`,
    `anthropic 0.97.0`). The suite mocks the SDK client, so no network/container is needed;
    equivalent path. Re-running under `docker exec` before the flight commit is advisable
    but expected to be a no-op.
  - **Lint**: `ruff check the_one/llm/anthropic_provider.py tests/test_anthropic_provider.py`
    clean; `ruff format` reformatted `anthropic_provider.py` once (the new helper +
    drop-loop), now `ruff format --check` clean on both files.
  - Scope held: no changes to `base.py`, the other adapters, the MCP layer, or the web UI.
- 2026-06-18 — `leg 04` (`live-verify-anthropic`) **implemented + live-run passing** (Developer).
  - **Built**: `tests/test_anthropic_live.py` — **new**, 3 `@pytest.mark.live` tests, each
    self-skipping when `ANTHROPIC_API_KEY` is unset; `LIVE_ANTHROPIC_MODEL` override (default
    `claude-haiku-4-5-20251001`); `PRESS_KEY_RAW` fixture inlined verbatim (top-level `anyOf`,
    in lockstep with `tests/test_schema_sanitize.py`); `await provider.aclose()` teardown in a
    `finally`. No production-code changes — verification leg only.
  - **Tests (one per acceptance criterion)**:
    1. *Accepted-through-provider* — `provider.complete(tools=[{name,description,parameters:
       PRESS_KEY_RAW}], max_tokens=16)` returns a `Message` (leg-02 in-adapter sanitize makes
       the formerly-400ing tool work live); sanity assert `role == ASSISTANT or usage is not
       None`.
    2. *Rejected-direct* — direct `provider.client.messages.create(... input_schema:
       PRESS_KEY_RAW ...)` raises `anthropic.BadRequestError` (status 400). Tolerant assertion:
       `BadRequestError` AND `"anyOf" in msg` AND `re.search(r"top[- ]level", msg, re.I)` (NOT a
       hard literal-substring gate); full message printed (flush).
    3. *Array-type pin* — direct `create` with `input_schema {"type":["object","null"], ...}`
       (outcome recorded), then assert the leg-01-sanitized scalar form is **accepted**.
  - **Live-run result** (`set -a && . ./.env && set +a && .venv/bin/pytest -m live
    tests/test_anthropic_live.py -v`): **3 passed, 0 skipped** (real first-party Anthropic API
    calls, cheap — `max_tokens=16`, one-line prompts).
    - **#122 first-party rejection wording (recorded)**: `tools.0.custom.input_schema:
      input_schema does not support oneOf, allOf, or anyOf at the top level` (status 400,
      `invalid_request_error`). The literal phrase is **"at the top level"** — the tolerant
      `top[- ]level` regex matched; the model of #122 is confirmed against the first-party API
      (previously only seen via the OpenRouter→Bedrock relay).
    - **Array-type pin outcome (recorded)**: raw top-level `type:["object","null"]` is
      **REJECTED** by first-party Anthropic — `tools.0.custom.input_schema.type: Input should
      be 'object'` (status 400). The leg-01-sanitized scalar `type:"object"` form is
      **ACCEPTED**. → **Leg-01's collapse rule (`["object","null"]` → scalar `"object"`) is
      CORRECT. No divert.** First-party Anthropic does not accept an array `type` at the tool
      `input_schema` top level, so the collapse is load-bearing (not merely a subset
      narrowing).
  - **Default-deselect confirmed**: `.venv/bin/pytest tests/test_anthropic_live.py -q` →
    `3 deselected` (0 run under default `addopts`).
  - **Regression**: `.venv/bin/pytest tests/test_schema_sanitize.py tests/test_anthropic_provider.py
    tests/test_openrouter_provider.py -q` → **72 passed** (green).
  - **Lint**: `ruff check tests/test_anthropic_live.py` clean; `ruff format --check` clean.
  - Scope held: only `tests/test_anthropic_live.py` added (no source touched). Flight/mission
    status NOT flipped and nothing committed — the Flight Director runs the single flight
    review + commit + landing after this leg.
