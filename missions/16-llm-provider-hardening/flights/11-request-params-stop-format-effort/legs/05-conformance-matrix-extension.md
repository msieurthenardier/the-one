# Leg: conformance-matrix-extension

**Status**: completed
**Flight**: [Request-Param Capabilities (A4)](../flight.md)

## Objective

Extend the Flight 4 cross-provider conformance suite with an A4 config→wire matrix:
given one canonical A4 config, assert each provider emits the params in its correct
native wire shape — adding **OpenRouter** to the A4 matrix (config→wire, per DD5) —
by extending the scripted-transport harness to accept a `config` and expose the
sent request uniformly. Test-only, hermetic.

## Context

- **Depends on L02–L04** (all provider wiring landed). This leg adds no production
  code — it is the systematic cross-provider proof that the per-provider unit tests
  (L02/L03/L04) are mutually consistent, and the home of the **DD5 OpenRouter
  config→wire assertion**.
- **The A4 wire shape differs per provider** (unlike the round-trip suite, which
  asserts a single canonical `Message` shape). The canonical config is identical;
  each provider maps it to a different native surface:
  - **Anthropic**: `output_config = {"effort": ..., "format": {"type":"json_schema",
    "schema":...}}` + top-level `stop_sequences` (list).
  - **OpenAI / OpenRouter / Ollama-`/v1`**: the shared OpenAI-compat shape —
    `reasoning_effort` (str), `stop` (list), `response_format = {"type":"json_schema",
    "json_schema":{"name":"response","schema":...}}`.
  - **Mock**: no request path — **N/A** (documented, not asserted).
- **The harness needs two extensions** (`tests/fixtures/scripted_transport.py`):
  1. Each request-capable factory (`make_anthropic`, `make_openai`,
     `make_openrouter`, `make_ollama`) must accept an optional `config=None` and
     pass it to the provider constructor.
  2. The sent request must be exposed uniformly so the A4 test can read it. Today
     `request_bodies` is populated only by `make_openrouter` (and per the docstring
     OpenAI). Extend so **Anthropic** (from `recorder.calls` — the `create`/`stream`
     kwargs, which carry `output_config`/`stop_sequences` as native keys),
     **OpenAI**, and **Ollama** all populate a captured-request list on
     `ScriptedProvider`. For Anthropic the "request body" is the recorded kwargs
     dict; for the transport-backed providers it's the parsed JSON body.

- **Shared canonical config** for the matrix uses **json_schema** for
  `response_format` (honored by all four request-capable providers), so the matrix
  is a uniform positive assertion. The `json_object` variance (OpenAI/Ollama honor;
  Anthropic no-ops+warns) is already covered by the L02/L03/L04 unit tests and is
  **not** re-litigated here — note this in the test so the omission is intentional.

## Inputs

- `tests/test_llm_provider_cross_provider_conformance.py` — the F4 suite;
  `PROVIDER_FACTORIES` (`:97-102`, OpenRouter absent), `TOOL_DEF`/`TURN_*`,
  `_drive_complete_roundtrip`, the `make_*` imports, and the existing
  `_press_key_sent_params(scripted.request_bodies)` reader (`:320`) as the
  request-body-assertion precedent.
- `tests/fixtures/scripted_transport.py` — `ScriptedProvider` (the `request_bodies`
  field, `:88`), the four request-capable factories and their capture mechanisms
  (Anthropic `_CreateRecorder.calls`/`_StreamRecorder.calls`; OpenAI/OpenRouter
  `httpx.MockTransport` handlers; Ollama monkeypatched transport), `make_mock`.
- The landed provider wiring (L02–L04) — the expected native shapes.

## Outputs

- `tests/fixtures/scripted_transport.py` — factories accept `config=None`; uniform
  captured-request exposure across the four request-capable providers.
- `tests/test_llm_provider_cross_provider_conformance.py` — an A4 config→wire test
  block: OpenAI-compat providers (openai, openrouter, ollama-/v1) parametrized
  against the shared shape; a dedicated Anthropic assertion; OpenRouter present.

## Acceptance Criteria

- [x] **Harness: `config` param.** `make_anthropic`, `make_openai`,
      `make_openrouter`, `make_ollama` each accept `config: dict | None = None` and
      pass it to the provider constructor. Existing call sites (no `config`) keep
      working unchanged (the round-trip tests still pass).
- [x] **Harness: uniform request capture.** After driving `complete()` (and
      `stream()`), the sent request is readable for Anthropic, OpenAI, OpenRouter,
      and Ollama via a single `ScriptedProvider` accessor (extend `request_bodies`
      or add an equivalent) — Anthropic exposes the recorded `create`/`stream`
      kwargs; the others expose the parsed JSON body. **Ollama capture MUST filter
      to the `/chat/completions` path** (the `/api/show` context/capability POSTs
      must not pollute `request_bodies` — see Guidance step 2), so the captured A4
      body is unambiguous.
- [x] **A4 config→wire — OpenAI-compat providers.** A parametrized test over
      {openai, openrouter, ollama} constructs each with the shared canonical A4
      config, drives `complete()`, and asserts the captured request carries
      `reasoning_effort == "high"`, `stop == ["</s>"]`, and
      `response_format == {"type":"json_schema","json_schema":{"name":"response",
      "schema":{...}}}`. Repeated for `stream()`.
- [x] **A4 config→wire — Anthropic.** A dedicated test asserts the captured request
      carries `output_config == {"effort":"high","format":{"type":"json_schema",
      "schema":{...}}}` and `stop_sequences == ["</s>"]`, on both `complete()` and
      `stream()`.
- [x] **OpenRouter is in the A4 matrix** and its assertion is **config→wire** (the
      request body carries the params) — **not** attribute-existence alone (DD5).
- [x] **Mock documented N/A.** The test module states Mock has no request path so
      A4 wire-emission is not applicable (a comment or an explicit skip — not a
      silent omission).
- [x] **No production code touched** — only the two test files. `git diff --stat`
      shows no `the_one/**` changes.
- [x] **json_object omission noted** — a comment records that json_object's
      per-provider variance is covered by the L02–L04 unit tests, so the matrix uses
      json_schema (universally honored) deliberately.
- [x] Full suite green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
      tests/test_llm_provider_cross_provider_conformance.py -x --timeout 30`; and a
      whole-unit-suite run (`make test-unit`) shows no regression from the harness
      change.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_llm_provider_cross_provider_conformance.py -x --timeout 30` — green, incl. the new A4 matrix.
- `make test-unit` — no regression (the harness change touches every provider's round-trip test).
- `git diff --stat` — only the two test files changed.
- Read the A4 test — confirm OpenRouter present, Anthropic shape distinct from the OpenAI-compat shape, Mock N/A noted.

## Implementation Guidance

1. **Harness `config` param.** Add `config: dict | None = None` to the four
   request-capable factories; thread it into the provider constructor call
   (Anthropic/OpenAI/Ollama take `config=` via kwargs; OpenRouter takes explicit
   `config=`). Keep the parameter last / keyword-only so existing positional calls
   are unaffected.

2. **Uniform capture.** The cleanest approach: have each factory populate the
   `ScriptedProvider.request_bodies` list.
   - Anthropic: the recorder already stores `.calls` (kwargs dicts). Expose them —
     e.g. set `request_bodies=recorder.calls` on the returned `ScriptedProvider`
     (the kwargs dict IS the sent request; `output_config`/`stop_sequences` are keys
     in it).
   - OpenAI: if `make_openai` doesn't already capture bodies, add a `request_bodies`
     list its handler appends `json.loads(request.content)` to (mirror
     `make_openrouter`, `:349-355`).
   - Ollama: **two distinct capture points, and you MUST filter `/api/show`.**
     `complete()` calls `_resolve_max_context_tokens_if_needed()` → a POST to
     `/api/show` **before** building the `/chat/completions` payload, and (on a
     plain-text turn) `supports_tools()` → **another** `/api/show` POST **after**.
     Since `httpx.AsyncClient.__init__` is monkeypatched at the class level, the same
     `MockTransport` serves all three, so a blanket append yields
     `[api_show, chat_completions(A4), api_show]` — the A4 body is **not** at index 0.
     **Fix: only append when the request path is `/chat/completions`** (mirror the
     existing turn-counter's `/api/show` special-case, `scripted_transport.py:458-463`).
     Note the two mechanisms differ: the `complete()` path captures in the
     `MockTransport` handler via `json.loads(request.content)`; the `stream()` path
     captures inside `fake_chat_stream(base_url, body, headers=None)` (`:447-455`)
     where `body` is **already a parsed dict** (no `json.loads`, and no `/api/show`
     pollution on that path). Add capture to **both**.
   - After filtering, `request_bodies[0]` is the `/chat/completions` body for every
     provider — the A4 params ride every request, so a single-turn drive
     (`PLAIN_TURN`) is sufficient; you don't need the two-turn round-trip. For
     robustness, prefer asserting on the captured `/chat/completions` body
     explicitly rather than a bare index, so the assertion survives any future
     prior-request additions.

3. **A4 test block** in the conformance suite:
   - Define the shared config once:
     `A4_CONFIG = {"reasoning_effort": "high", "response_format": {"type":
     "json_schema", "schema": {"type": "object"}}, "stop": ["</s>"]}` and the
     expected OpenAI-compat `response_format` wrapper + expected Anthropic
     `output_config`.
   - OpenAI-compat providers: parametrize `(make_openai, make_openrouter,
     make_ollama)` (ollama needs `monkeypatch`), construct with `config=A4_CONFIG`,
     drive one `complete()` (a single `PLAIN_TURN` is enough), read
     `request_bodies[0]`, assert the three keys. Repeat for `stream()`.
   - Anthropic: construct with `config=A4_CONFIG`, drive, assert `output_config` +
     `stop_sequences` on `request_bodies[0]`.
   - Add OpenRouter to the OpenAI-compat parametrization (it's the DD5 assertion).
   - Note Mock N/A in a comment near the parametrization.

4. Do NOT modify any `the_one/**` file. If a test reveals a real wiring bug in a
   provider, STOP and surface it to the Flight Director (a wiring fix belongs to the
   relevant L02–L04 file, not this test-only leg) — do not patch production code
   under cover of a conformance leg.

## Edge Cases

- **Round-trip regression from the harness change.** Adding `config` and capture
  must not alter the existing round-trip behavior — run `make test-unit`, not just
  the conformance file, to confirm the harness change is transparent to the other
  suites that import these factories.
- **Ollama native vs `/v1` in the matrix.** The matrix uses Ollama `/v1` (the
  default `make_ollama`, `native_api=False`) — the OpenAI-compat shape. The native
  path's distinct `think`/`format`/`options.stop` shapes are already covered by
  L04's direct `_native_body`/`_native_options` unit tests; note this so the native
  path isn't assumed uncovered.
- **A single drive vs full round-trip.** The A4 params are on every request, so a
  one-turn `complete()`/`stream()` suffices; don't force the two-turn tool round-trip
  just to read a request body.
- **Ollama `/api/show` pollution (load-bearing).** As above — the context-window
  and capability lookups POST to `/api/show` around the real `/chat/completions`
  call; capture must be path-filtered or the A4 body lands at the wrong index.
- **`ollama_api._capabilities_cache` cross-test nondeterminism.** That module-level
  cache (keyed by `(base_url, model)`, TTL'd) means the number of `/api/show` hits
  per run isn't guaranteed stable across tests reusing the same base_url+model —
  another reason to path-filter capture rather than index blindly. Clear the cache
  in the A4 test setup if flakiness appears (the existing `TestSupportsTools` tests
  clear `openrouter_api._models_cache`; the Ollama analog is the same pattern).

## Files Affected

- `tests/fixtures/scripted_transport.py` — `config` param + uniform request capture.
- `tests/test_llm_provider_cross_provider_conformance.py` — the A4 matrix.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (conformance file + `make test-unit` regression check)
- [x] Update flight-log.md with a Leg Progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] (Not final autonomous leg only if L06 follows — L06 is the last autonomous leg;
      no flight/mission status change here)
- [x] Changes stay uncommitted — batch commit after L06 (do NOT commit at leg end)
