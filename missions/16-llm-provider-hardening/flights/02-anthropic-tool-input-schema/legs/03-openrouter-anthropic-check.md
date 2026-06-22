# Leg: openrouter-anthropic-check

**Status**: completed
**Flight**: [Anthropic Tool `input_schema` Compatibility (#122)](../flight.md)

## Objective

Resolve the flight's OpenRouter→Anthropic open question empirically (done — see Finding),
and, because the probe proved OpenRouter passes tool schemas through to the Anthropic
backend unmodified (it 400s on #122 identically to the direct path), **wire the leg-01
sanitizer into OpenRouter's tool conversion, gated to `anthropic/*` routes** — the minimal
clean adaptation the flight pre-authorized. No DD5 drop-and-proceed / DD6 named-error
parity on this path (operator-scoped minimal).

## Context

- This is **leg 03 of 4**. Depends on leg 01 (`landed`, the kernel) and is independent of
  leg 02's adapter wiring (different provider, different code path).
- **Empirical Finding (live probe, 2026-06-18) — resolves the flight Open Question:**
  A live OpenRouter request to `anthropic/claude-3.5-haiku` (OpenAI-compat endpoint, tool
  in OpenAI function shape) **rejected** the raw `press_key` schema (top-level `anyOf`)
  with the verbatim #122 error — `tools.0.custom.input_schema: input_schema does not
  support oneOf, allOf, or anyOf at the top level` (provider: Amazon Bedrock backing
  Anthropic) — and **accepted** the sanitized control. So OpenRouter does **not** normalize;
  it forwards the schema and the Anthropic backend 400s. The flight's pre-flight "likely
  outcome" (OpenRouter owns translation → scope out) is **falsified**. Recorded in the
  flight log Anomalies.
- **Decision rule met** (flight Open Question + Adaptation Criteria): wire "only if
  OpenRouter demonstrably rejects **and** a clean adaptation exists." Both hold — the
  leg-01 `sanitize_tool_schema` kernel is schema-in/schema-out and provider-neutral, so it
  drops cleanly onto the `parameters` of OpenRouter's inherited OpenAI tool shape.
- **No divert**: the flight's divert criterion fires only if OpenRouter needed a
  *different* normalization than the Anthropic-direct path. It needs the **same** one
  (same #122 constraint, same kernel) — so the shared-module assumption (DD1) holds; this
  leg is the kernel's promised second caller, but on the OpenAI-shaped tool path rather
  than the Anthropic-native one.

### Code path (verified against current source)

- `OpenRouterProvider(OpenAIProvider)` — `the_one/llm/openrouter_provider.py:46`. It does
  **not** override tool building; it inherits `OpenAIProvider.complete()`/`stream()`, which
  build tools via `self.tool_schema(t)` (`openai_provider.py:130` and `:182`).
- `tool_schema(self, tool_def)` — defined in `base.py:347-360`; returns
  `{"type":"function","function":{"name","description","parameters": tool_def["parameters"]}}`.
  Note: base builds a **fresh** dict each call but sets `"parameters"` to the *same*
  `tool_def["parameters"]` object — so an override that **reassigns**
  `result["function"]["parameters"]` to the sanitizer's (deep-copied) output does **not**
  mutate the caller's `tool_def` (DD2 preserved).
- OpenRouter Anthropic slugs are all `anthropic/...` (confirmed live against
  `/api/v1/models`: `anthropic/claude-3.5-haiku`, `anthropic/claude-sonnet-4.6`,
  `anthropic/claude-opus-4.x`, …). `self.model.startswith("anthropic/")` is the correct gate.

## Inputs

- `the_one/llm/_schema_sanitize.py` (leg 01): `sanitize_tool_schema`, `UnsanitizableToolSchema`.
- `the_one/llm/openrouter_provider.py`, `the_one/llm/openai_provider.py`, `base.py:347`.
- `tests/test_openrouter_provider.py` (the mocked-provider test model), `tests/CONVENTIONS.md`.

## Outputs

- `the_one/llm/openrouter_provider.py` modified: a `tool_schema` override that sanitizes
  `parameters` for `anthropic/*` routes only.
- `tests/test_openrouter_provider.py` extended (or a new `test_openrouter_anthropic_tool_schema.py`)
  with unit tests for the override.
- Flight Open Question + the relevant Design Decision annotated as resolved (the probe
  finding + the wire decision). Flight log leg-progress entry.
- No changes to `OpenAIProvider` (OpenAI-direct untouched), the Anthropic adapter, base.py,
  the MCP layer, or the web UI.

## Acceptance Criteria

Each maps to a unit test (no network — call `provider.tool_schema(tool_def)` directly).

- [x] **Anthropic route sanitizes**: an `OpenRouterProvider(model="anthropic/claude-3.5-haiku")`
      converting a tool whose `parameters` has a top-level `anyOf` (the leg-01 `press_key`
      fixture) returns a function dict whose `function.parameters` has **no top-level
      `anyOf`** and `type == "object"`.
- [x] **Non-Anthropic route untouched (gating)**: the same tool through
      `OpenRouterProvider(model="openai/gpt-4o")` (or any non-`anthropic/` slug) returns
      `function.parameters` **identical** to the input (top-level `anyOf` preserved) — the
      sanitizer does not run.
- [x] **Non-mutation (DD2)**: after `tool_schema(...)`, the caller's original
      `tool_def["parameters"]` is `is`-identical and byte-unchanged.
- [x] **Unsanitizable falls back, no raise escapes (minimal scope)**: an `anthropic/*`
      route converting a tool with a genuinely-unsanitizable schema (e.g. top-level bare
      `$ref`) does **not** propagate `UnsanitizableToolSchema` out of `tool_schema`;
      instead it returns the **original** (un-sanitized) parameters, so the request reaches
      the API and 400s there exactly as today (no worse than pre-fix). Assert the call
      returns normally and `function.parameters` equals the original schema, **and** a
      WARN naming the tool is emitted (`caplog`, logger `the_one.llm.openrouter_provider`)
      so the otherwise-silent #122 rejection is diagnosable. *(This is unit-level only —
      no live coverage of the fallback in leg 04; the unit assertion that no exception
      escapes is sufficient for the minimal scope.)*
- [x] **Clean schema near-no-op**: a flat-object schema on an `anthropic/*` route passes
      through with substance intact (`type:"object"`, properties unchanged).

## Verification Steps

- `cd /home/cprch/projects/the-one`
- Host-native (Docker unavailable this environment): `.venv/bin/pytest
  tests/test_openrouter_provider.py -x --timeout 30 -q` (or the new test file) — all pass.
- `.venv/bin/pytest tests/test_schema_sanitize.py tests/test_anthropic_provider.py -q` —
  legs 01–02 suites still green (32 + 17).
- `ruff check the_one/llm/openrouter_provider.py <test-file>` clean; `ruff format --check` clean.
- **Empirical (already done; not a gate, recorded as evidence):** the live probe
  `/tmp/or_anthropic_probe.py` showed raw→400(#122), sanitized→accepted against
  `anthropic/claude-3.5-haiku`. Re-runnable with a key from the gitignored `.env`.

## Implementation Guidance

1. **Imports** — add to `openrouter_provider.py`:
   ```python
   import logging
   from the_one.llm._schema_sanitize import sanitize_tool_schema, UnsanitizableToolSchema
   logger = logging.getLogger(__name__)
   ```

2. **Override `tool_schema`** on `OpenRouterProvider`:
   ```python
   def tool_schema(self, tool_def: dict[str, Any]) -> dict[str, Any]:
       result = super().tool_schema(tool_def)  # OpenAI function shape
       # #122: OpenRouter forwards tool schemas verbatim to the provider
       # backend; the Anthropic backend (incl. via Bedrock) rejects a
       # top-level oneOf/allOf/anyOf. Sanitize only for anthropic/* routes —
       # other backends accept the combinators and we must not degrade them.
       if self.model.startswith("anthropic/"):
           try:
               result["function"]["parameters"] = sanitize_tool_schema(
                   result["function"].get("parameters")
               )
           except UnsanitizableToolSchema as exc:
               # Minimal scope (operator 2026-06-18): no DD5 drop-and-proceed
               # on this path. Leave the original schema so the request 400s
               # at the API exactly as today — no worse than pre-fix. Warn so
               # the otherwise-silent #122 rejection is diagnosable (this is
               # observability, NOT drop-and-proceed — the tool is still sent).
               logger.warning(
                   "Tool %r has an input_schema that cannot be sanitized for the "
                   "Anthropic route %r (%s); sending it unmodified — the Anthropic "
                   "backend will likely reject it (#122).",
                   tool_def.get("name", "<unnamed>"), self.model, exc.reason,
               )
       return result
   ```
   Because `super().tool_schema()` returns a fresh dict, reassigning
   `result["function"]["parameters"]` to the sanitizer's deep-copied output leaves the
   caller's `tool_def["parameters"]` untouched (DD2). This single override is the shared
   chokepoint for **both** `complete()` (`openai_provider.py:130`) and `stream()` (`:182`)
   — wiring it once covers both entry points.

3. **Do not touch `OpenAIProvider`** — OpenAI-direct accepts the combinators (mission audit:
   "No OpenAI #122 cross-ref") and must keep its schemas verbatim. The override lives only
   on the OpenRouter subclass and is gated by the model slug.

4. **Tests** — model on `tests/test_openrouter_provider.py` (construct the provider directly;
   no network — `tool_schema` is pure). Reuse the leg-01 `press_key` anyOf fixture. Cover all
   five acceptance criteria, especially the gating (anthropic vs non-anthropic slug) and the
   unsanitizable-fallback (no exception escapes).

5. **Resolve the flight artifacts**: check the OpenRouter Open Question box in `flight.md`
   and annotate the relevant Design Decision (DD1's OpenRouter-reuse note) that the
   speculative case became real and was wired (gated, minimal). Append the leg-progress
   entry to the flight log.

## Edge Cases

- **Model slug with a suffix** (`anthropic/claude-opus-4.6-fast`): still `startswith
  "anthropic/"` → sanitized. Correct (same Anthropic backend).
- **`parameters` missing**: `result["function"].get("parameters")` → `None` → kernel returns
  `{"type":"object"}`. No crash.
- **OpenRouter "auto" / non-prefixed routing**: a model slug that does not start with
  `anthropic/` is left untouched by design; if such a route lands on an Anthropic backend
  and 400s, that is the documented minimal-scope boundary (recorded; a future full-parity
  flight could broaden the gate).

## Files Affected
- `the_one/llm/openrouter_provider.py` — `tool_schema` override (gated sanitize).
- `tests/test_openrouter_provider.py` (or a new sibling test file) — override unit tests.
- `missions/.../flights/02-.../flight.md` — Open Question resolved; DD1 OpenRouter note annotated.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified (suite green) — 23 passed (5 new) in test_openrouter_provider.py
- [x] Gating confirmed (non-anthropic routes untouched) + non-mutation
- [x] legs 01–02 suites still green — 49 passed (32 schema_sanitize + 17 anthropic_provider)
- [x] Flight Open Question (OpenRouter→Anthropic) checked off in flight.md; DD1 note annotated
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (NOT `completed`) in this file's header
- [x] (Not the final autonomous leg in the build sense, but leg 04 is a live-only test —
      do NOT check off the flight or flip flight/mission status here)
- [x] Do NOT commit — this flight commits once after all autonomous legs
