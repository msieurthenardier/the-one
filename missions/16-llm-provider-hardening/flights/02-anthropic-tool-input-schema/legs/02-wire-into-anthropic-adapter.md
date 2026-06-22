# Leg: wire-into-anthropic-adapter

**Status**: completed
**Flight**: [Anthropic Tool `input_schema` Compatibility (#122)](../flight.md)

## Objective

Wire the leg-01 sanitizer into `AnthropicProvider` so every tool's `input_schema` is
normalized immediately before send, one genuinely-unsanitizable tool is dropped (not
fatal) with a named warning, and any Anthropic `tools.N` schema-400 surfaces the
offending tool's **name** instead of a bare index — all without mutating the shared
tool dicts or regressing the existing temperature-retry.

## Context

- This is **leg 02 of 4**. Depends on **leg 01** (`landed`): imports
  `sanitize_tool_schema` and `UnsanitizableToolSchema` from
  `the_one/llm/_schema_sanitize.py`.
- Implements flight **DD2** (sanitize on a deep copy; never mutate the shared tool
  dict — already guaranteed by leg 01's kernel, but this leg must not reintroduce
  mutation), **DD5** (drop-and-proceed with a named, `reason`-carrying warning for
  `UnsanitizableToolSchema`), and **DD6** (`BadRequestError → tool-name` defensive net,
  composed with the existing temperature-retry).
- Scope is the Anthropic adapter only. The generic `Message`/`LLMProvider` contract,
  the other three adapters, the MCP layer, and the web UI are untouched.

### Current adapter shape (verified against source this session)

- `_to_anthropic_tool(self, tool_def)` — `the_one/llm/anthropic_provider.py:210-215`.
  Currently returns `{"name", "description", "input_schema": tool_def["parameters"]}`
  with **no** sanitization. This is where the sanitizer is called (DD1).
- `_build_kwargs(...)` — `:75-100`. Builds `kwargs["tools"] = [self._to_anthropic_tool(t)
  for t in tools]` at `:99`. This list comprehension becomes the DD5 drop-and-proceed
  loop. The resulting `kwargs["tools"]` (post-drop) is the **single source of truth for
  tool ordering** (DD5/DD6) — a dropped tool is simply never appended, so later indices
  shift naturally and `kwargs["tools"][N]["name"]` is the correct DD6 lookup.
- `complete()` — `:102-138`; its `except anthropic.BadRequestError` is `:114-121`
  (temperature branch + `else: raise`).
- `stream()` — `:140-168`; its `except` is `:162-168`. `stream()` builds `kwargs` once
  (`:156`) and the temperature-retry re-calls `_stream_inner(kwargs)` after `kwargs.pop`.
  The same `kwargs["tools"]` list is in scope in the `except`, so DD6 can read names
  there.
- There is **no module logger and no anthropic test file today** — both are net-new in
  this leg (DD5 adds the logger; tests model the mocked-client pattern in
  `tests/test_mcp_tool_provider.py` / `tests/test_openrouter_provider.py`, which use
  `unittest.mock.AsyncMock`/`MagicMock` + `monkeypatch`).

### Test-harness gotchas (verified against `anthropic 0.97.0` — read before writing tests)

- **`anthropic.BadRequestError` cannot be constructed from a bare message.** Its
  signature is `__init__(self, message, *, response: httpx.Response, body)` — `response`
  and `body` are **required keyword-only**. `side_effect=anthropic.BadRequestError("tools.1...")`
  raises `TypeError` at construction, not the handler under test. Use a tiny factory:
  ```python
  import httpx, anthropic
  def _mk_bad_request(msg: str) -> anthropic.BadRequestError:
      req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
      return anthropic.BadRequestError(msg, response=httpx.Response(400, request=req), body=None)
  ```
  Use it for both the `"temperature"` and the `"tools.N.…"` `side_effect`s.
- **Streaming happy-path mock** needs an **async context manager** whose `text_stream`
  is an async iterator AND whose `get_final_message()` is awaitable. Build a small
  fixture factory for this (more setup than the `complete()` mocks).
- **`caplog` for the DD5 warning**: the logger is `the_one.llm.anthropic_provider`
  (module `__name__`). Use `caplog.at_level(logging.WARNING, logger="the_one.llm.anthropic_provider")`
  (or `caplog.set_level`) so the warning record is captured.

## Inputs

- `the_one/llm/_schema_sanitize.py` (leg 01, `landed`): `sanitize_tool_schema`,
  `UnsanitizableToolSchema`.
- `the_one/llm/anthropic_provider.py` at the shape described above.
- `anthropic` SDK present (`0.97.0`); `anthropic.BadRequestError` is the caught type.
- Test models: `tests/test_mcp_tool_provider.py`, `tests/test_openrouter_provider.py`,
  `tests/CONVENTIONS.md`.

## Outputs

- `the_one/llm/anthropic_provider.py` modified:
  - `_to_anthropic_tool` calls `sanitize_tool_schema(tool_def["parameters"])` and uses
    the result as `input_schema`.
  - `_build_kwargs` wraps per-tool conversion in `try/except UnsanitizableToolSchema`:
    drop the offending tool, emit a named warning via a new module logger.
  - A `BadRequestError → tool-name` helper folded into the **existing** `except` in
    **both** `complete()` and `stream()`, covering the temperature-retry's second call.
  - A module logger (`logging.getLogger(__name__)`).
- New file `tests/test_anthropic_provider.py` — mocked-client unit suite (all acceptance
  criteria below), green.
- No changes to `base.py`, the other adapters, the MCP layer, or the web UI.

## Acceptance Criteria

Each maps to a unit test in `tests/test_anthropic_provider.py` (mocked SDK client; no
network).

**Sanitize-before-send (DD1/DD2):**
- [x] A tool whose `parameters` has a top-level `anyOf` (the `press_key` fixture from
      leg 01) produces an Anthropic tool whose `input_schema` has **no top-level
      `anyOf`** and `type == "object"`. Assert by inspecting the `tools` kwarg captured
      by the mocked `messages.create`.
- [x] **Non-mutation**: after a `complete()`/`_build_kwargs` call, the original tool
      `parameters` dict passed in is `is`-identical and byte-unchanged (the kernel
      deep-copies, but this guards against the adapter re-assigning into the source).
- [x] A clean flat-object schema passes through unchanged in substance (sanitizer is a
      near no-op: `type:"object"` present, properties intact).

**Drop-and-proceed (DD5):**
- [x] **One bad tool dropped, rest succeed**: given three tools where the middle one is
      unsanitizable (e.g. top-level bare `$ref`), `kwargs["tools"]` sent to the client
      contains the **two** good tools (by name), the bad one is absent, and the call
      proceeds (no exception bubbles out of `_build_kwargs`).
- [x] The drop emits a **warning** that names the offending tool **and** includes the
      `UnsanitizableToolSchema.reason` (assert via `caplog`).
- [x] **All tools unsanitizable** → `kwargs` has **no `tools` key** and the turn still
      runs (degenerate but non-fatal). *(We omit the key to be safe — strictly more
      conservative than sending `[]`; whether the SDK actually rejects `[]` is unverified
      and we don't depend on the answer. This is a design choice, not an SDK-forced one.)*

**BadRequestError → tool-name (DD6):**
- [x] **Ordered-check composition**: the existing temperature branch still fires first
      — a `BadRequestError` containing `"temperature"` triggers the existing retry
      (no name-mapping interference).
- [x] A `BadRequestError` whose message matches `tools.(\d+)\.` (e.g.
      `"tools.1.custom.input_schema: ..."`) is re-raised with an error that **names**
      `kwargs["tools"][1]["name"]` instead of the bare index. Both `complete()` and
      `stream()`.
- [x] **Index-shift case**: with a tool dropped *before* the offending one (so the
      original and post-drop indices differ), the name reported maps against the
      **post-drop** `kwargs["tools"]` list actually sent — i.e. it names the right tool.
- [x] **Temperature-retry's second call also maps**: a request that first 400s on
      `"temperature"`, retries, and the retry 400s on `tools.N` → the retry's failure is
      also name-mapped (not the bare index). **Required test in `complete()` only.** For
      `stream()`, mirror the same composition in code but **no dedicated test is required**
      for the temperature-retry→`tools.N` sub-path — streaming 400s arrive pre-delta
      (`not yielded_any` true), so that combination is defence-in-depth (resolves the
      design-review question). `stream()` still gets the first-call `tools.N` test below.
- [x] **Unparseable / out-of-range index** → fall back to re-raising the **original**
      `BadRequestError` unchanged (no worse than today; no `IndexError`).
- [x] A non-temperature, non-`tools.N` `BadRequestError` is re-raised **unchanged**
      (the `else: raise` path is preserved).

**No regression:**
- [x] Streaming still yields content + a final tool-call chunk for a normal (no-400)
      stream (smoke test with a mocked `stream()` context manager) — confirms the DD6
      wrapping did not break the happy path.

## Verification Steps

- `cd /home/cprch/projects/the-one`
- Preferred (containerized): `docker exec the-one pytest tests/test_anthropic_provider.py
  -x --timeout 30 -q`. **If Docker is unavailable in this environment** (it was during
  leg 01 — daemon not running), fall back to host-native: `.venv/bin/pytest
  tests/test_anthropic_provider.py -x --timeout 30 -q` (anthropic `0.97.0` + pytest are
  present in `.venv`; the suite mocks the client so no network/container is needed).
- `.venv/bin/pytest tests/test_anthropic_provider.py -q -k "dropped or tool_name or
  index_shift"` — the three highest-risk DD5/DD6 paths in isolation.
- Run the leg-01 suite too, to prove no cross-contamination:
  `.venv/bin/pytest tests/test_schema_sanitize.py -q` (still 32 passed).
- `ruff check the_one/llm/anthropic_provider.py tests/test_anthropic_provider.py` clean;
  `ruff format --check` clean.

## Implementation Guidance

1. **Imports** — add to `anthropic_provider.py`:
   ```python
   import logging
   from the_one.llm._schema_sanitize import sanitize_tool_schema, UnsanitizableToolSchema
   logger = logging.getLogger(__name__)
   ```

2. **Sanitize in `_to_anthropic_tool` (DD1/DD2)** — call the kernel on the schema:
   ```python
   def _to_anthropic_tool(self, tool_def):
       return {
           "name": tool_def["name"],
           "description": tool_def["description"],
           "input_schema": sanitize_tool_schema(tool_def.get("parameters")),
       }
   ```
   The kernel deep-copies internally (leg 01 DD2), so the source `parameters` is
   untouched. Do **not** assign the sanitized result back onto `tool_def`.
   **Intentional change (do not "restore"):** the current source uses
   `tool_def["parameters"]` (subscript, `KeyError` on absence); switch to
   `tool_def.get("parameters")` so a tool with no `parameters` key flows to the kernel as
   `None` → `{"type":"object"}` (the missing-`parameters` edge case). `name`/`description`
   stay as subscripts — they are contract-guaranteed.

3. **Drop-and-proceed in `_build_kwargs` (DD5)** — replace the `:99` list comprehension
   with a loop that catches `UnsanitizableToolSchema` per tool:
   ```python
   if tools:
       sent_tools = []
       for t in tools:
           try:
               sent_tools.append(self._to_anthropic_tool(t))
           except UnsanitizableToolSchema as exc:
               logger.warning(
                   "Dropping tool %r from Anthropic request: unsanitizable "
                   "input_schema (%s)", t.get("name", "<unnamed>"), exc.reason,
               )
       if sent_tools:
           kwargs["tools"] = sent_tools
       # else: omit "tools" entirely — never send an empty list (SDK may reject it)
   ```
   `kwargs["tools"]` (post-drop) is now the ordering source of truth for DD6.

4. **DD6 helper — `BadRequestError → tool-name`.** Add a small module-level helper that,
   given the exception and the sent tools list, returns either a new exception naming the
   tool or `None` (no mapping applies). **Pinned wrapping type (resolves the design-review
   question):** re-raise as `anthropic.BadRequestError`, **reusing the caught exception's
   own `response` and `body`** (they are required keyword-only args on `0.97.0` — see the
   test gotcha below; reusing the caught ones is the clean way to construct a valid
   instance). This keeps the public exception type stable (callers catching
   `BadRequestError` still work) while the message names the tool:
   ```python
   import re
   _TOOLS_INDEX_RE = re.compile(r"tools\.(\d+)\.")
   def _name_offending_tool(exc, sent_tools):
       m = _TOOLS_INDEX_RE.search(str(exc))
       if not m:
           return None
       idx = int(m.group(1))
       if sent_tools and 0 <= idx < len(sent_tools):
           name = sent_tools[idx].get("name", "<unnamed>")
           return anthropic.BadRequestError(
               f"Anthropic rejected tool {name!r}'s input_schema "
               f"(original error: {exc})",
               response=exc.response,
               body=exc.body,
           )
       return None
   ```
   Tests assert `pytest.raises(anthropic.BadRequestError)` AND that the tool **name**
   appears in the message AND that the original `tools.N` text is still quoted (nothing
   lost). Re-raise with `from exc` at the call site to preserve `__cause__`.

5. **Compose into the EXISTING `except` (ordered checks) — `complete()` `:114-121`:**
   ```python
   except anthropic.BadRequestError as exc:
       if "temperature" in str(exc).lower():          # (1) existing behavior, first
           kwargs.pop("temperature", None)
           try:
               response = await self.client.messages.create(**kwargs)
           except anthropic.BadRequestError as exc2:   # retry can ALSO 400 on schema
               named = _name_offending_tool(exc2, kwargs.get("tools"))
               raise (named or exc2) from exc2
       else:
           named = _name_offending_tool(exc, kwargs.get("tools"))  # (2) tools.N → name
           raise (named or exc) from exc               # (3) else unchanged
   ```
   Order is load-bearing: temperature first (unchanged), then `tools.N` mapping, then
   plain re-raise. The retry's second `create()` is wrapped so its schema-400 is mapped
   too (DD6 sub-requirement).

6. **`stream()` `:162-168`** — mirror the same composition. The `except` already gates
   the temperature retry on `not yielded_any`; layer the `tools.N` mapping into the
   `else` and around the retry's `_stream_inner` re-entry the same way. `kwargs["tools"]`
   is in scope at `:156`.

7. **Keep DD2 honest** — the adapter must never write the sanitized schema back into the
   caller's `tool_def`/`parameters`. The non-mutation test asserts this at the adapter
   boundary (in addition to leg 01's kernel-level test).

8. **Logging only (DD5)** — no new web-UI element, no agent-event surface unless one
   already exists at the adapter layer (it does not). The named warning rides the module
   logger. This satisfies the flight's "named warning" requirement (log-only is
   explicitly permitted by the adaptation criteria).

## Edge Cases

- **Empty filtered tools list** (all dropped): omit the `tools` kwarg entirely rather
  than sending `[]` — some SDKs reject an empty tools array. Test asserts no `tools` key.
- **`tool_def` missing `parameters` key**: `tool_def.get("parameters")` → `None` →
  kernel returns `{"type":"object"}` (leg 01 contract). No crash.
- **`BadRequestError` message format drift**: if Anthropic changes the `tools.N.` shape,
  the regex misses → `_name_offending_tool` returns `None` → original error re-raised
  unchanged. Documented fallback; no worse than today.
- **Multiple `tools.N` in one message**: `.search` takes the first match — acceptable;
  the first offending index is the one Anthropic reports.
- **Streaming retry reachability**: Anthropic raises `BadRequestError` on submission
  (before deltas), so `not yielded_any` is normally true; the `tools.N` mapping on the
  stream retry is defence-in-depth (mirror complete(), don't over-engineer).

## Files Affected
- `the_one/llm/anthropic_provider.py` — sanitize call in `_to_anthropic_tool`;
  drop-and-proceed loop + logger in `_build_kwargs`; DD6 name-mapping folded into the
  `except` in `complete()` and `stream()`.
- `tests/test_anthropic_provider.py` — **new**; mocked-client unit suite.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified (suite green)
- [x] Original tool dicts confirmed unmutated (DD2 adapter-boundary test)
- [x] leg-01 suite still green (no cross-contamination)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (NOT `completed`) in this file's header
- [ ] (Not the final leg — do NOT check off the leg in flight.md or flip flight/mission status)
- [ ] Do NOT commit — this flight commits once after all autonomous legs
