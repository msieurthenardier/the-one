# Leg: shared-test-fixtures

**Status**: completed
**Flight**: [Cross-Provider Tool-Use Conformance Suite](../flight.md)

## Objective

Extract the duplicated `press_key` tool-schema constant and the Anthropic
`BadRequestError` builder into a single shared test-fixtures location, refactor
their actual callers, and converge the two near-variants — so each fixture is
defined exactly once, with no behavior change and all touched test files staying
green.

## Context

- **DD6** of the flight: the conformance suite is the *fourth* consumer of these
  fixtures (the threshold the Flight-2 debrief set for extraction). Killing the
  multi-file manual-sync drift now gives the new suite a clean import.
- This is a **pure, behavior-preserving refactor** — no production code changes,
  no test-logic changes. The only acceptance signal is that every touched file
  stays green and no fixture is defined in more than one place.
- The fixtures currently carry inline comments explicitly justifying duplication
  ("Kept inline so this test file carries no cross-test dependency"). DD6
  deliberately reverses that trade-off: drift-kill outweighs the no-import
  convention now that there are four consumers. Those comments must be updated or
  removed as part of the refactor so they don't contradict the new structure.
- A `tests/fixtures/` package already exists (`tests/fixtures/__init__.py`, plus
  `mcp/` and `oauth/` subdirs) — the natural home for the extracted module.

### Two fixtures, two different caller sets (Architect-verified against the tree)

1. **`PRESS_KEY_INPUT_SCHEMA`** — the goldfinch `press_key` tool `input_schema`
   (top-level `anyOf` alongside a top-level `type`; the #122 trigger). It is
   **byte-identical** in two hermetic files and has one structurally-identical
   near-variant under a different name:
   - `tests/test_schema_sanitize.py:23` — `PRESS_KEY_INPUT_SCHEMA` (exact)
   - `tests/test_openrouter_provider.py:16` — `PRESS_KEY_INPUT_SCHEMA` (exact, with
     a local `_press_key_tool_def()` helper at `:33` that deep-copies it)
   - `tests/test_anthropic_live.py:56` — `PRESS_KEY_RAW` (same dict, different
     name; **converge onto the shared constant**)
   - Note: `tests/test_anthropic_provider.py` does **not** define this constant —
     it builds a different, simpler inline `anyOf` via its own `_tool(...)` helper.
     Leave that file's schema alone; it is out of scope for this fixture.

2. **`_mk_bad_request()`** — builds an `anthropic.BadRequestError` for the DD6
   error-format / temperature-retry tests. Defined once, with one non-identical
   variant:
   - `tests/test_anthropic_provider.py:40` — `_mk_bad_request(msg)` → real
     `httpx.Request` + `httpx.Response(400)`, `body=None`, positional `msg`
   - `tests/test_streaming.py:170` — `_make_bad_request(message)` → `MagicMock()`
     response, `body={"error": {"message": message}}`, kwarg-named `message`
     (**converge onto the shared helper**)
   - Both work today because the provider's error path only reads `str(err)` (the
     message), never `.body` or `.response.headers`. The shared helper should use
     the **real-`httpx.Response` form** (`test_anthropic_provider.py:40`) — it is
     the more faithful of the two. After convergence, `test_streaming.py`'s three
     call sites (`:214`, `:242`, and the def at `:170`) must use the shared helper.

## Inputs

What exists before this leg runs:
- `tests/fixtures/__init__.py` (package already present)
- `tests/test_schema_sanitize.py` — defines `PRESS_KEY_INPUT_SCHEMA` (`:23`)
- `tests/test_openrouter_provider.py` — defines `PRESS_KEY_INPUT_SCHEMA` (`:16`),
  `_press_key_tool_def()` (`:33`)
- `tests/test_anthropic_live.py` — defines `PRESS_KEY_RAW` (`:56`)
- `tests/test_anthropic_provider.py` — defines `_mk_bad_request()` (`:40`)
- `tests/test_streaming.py` — defines `_make_bad_request()` (`:170`)
- All of the above currently green.

## Outputs

What exists after this leg completes:
- A new shared fixtures module (recommended: `tests/fixtures/tool_schemas.py`)
  exporting `PRESS_KEY_INPUT_SCHEMA` and the `_mk_bad_request()`-equivalent
  builder. (Splitting into two modules — e.g. `tool_schemas.py` +
  `anthropic_errors.py` — is an acceptable variation; a single module keeps the
  import surface small.)
- The five test files above import from the shared module instead of defining
  their own copy/variant.
- `PRESS_KEY_RAW` and `_make_bad_request` no longer exist as separate definitions
  (converged onto the shared names; or re-exported as a local alias only if a
  caller's readability genuinely needs the old name — prefer converging the call
  sites).
- No fixture defined in more than one place.

## Acceptance Criteria
- [x] A shared fixtures module exists under `tests/fixtures/` exporting both
      `PRESS_KEY_INPUT_SCHEMA` (the press_key schema dict) and a single
      `BadRequestError` builder (the real-`httpx.Response` form).
- [x] `tests/test_schema_sanitize.py` and `tests/test_openrouter_provider.py`
      import `PRESS_KEY_INPUT_SCHEMA` from the shared module; neither defines its
      own copy.
- [x] `tests/test_anthropic_live.py`'s `PRESS_KEY_RAW` is converged onto the
      shared `PRESS_KEY_INPUT_SCHEMA` (no separate dict definition remains).
- [x] `tests/test_anthropic_provider.py` and `tests/test_streaming.py` import the
      shared `BadRequestError` builder; neither defines its own copy/variant.
- [x] `grep -rn "PRESS_KEY_INPUT_SCHEMA\|PRESS_KEY_RAW" tests/` shows exactly one
      *definition* (in the shared module); all other hits are imports/usages.
      Likewise for `_mk_bad_request`/`_make_bad_request`.
- [x] Now-obsolete "kept inline to avoid cross-test dependency" comments are
      updated or removed so no comment contradicts the extracted structure.
- [x] All five touched test files pass; no production source file is modified.

## Verification Steps
- `grep -rn "def _mk_bad_request\|def _make_bad_request" tests/` → exactly one
  definition (in the shared module).
- `grep -rn "PRESS_KEY_INPUT_SCHEMA = \|PRESS_KEY_RAW = " tests/` → exactly one
  assignment (in the shared module).
- Run the touched files host-native via the repo venv:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_schema_sanitize.py tests/test_openrouter_provider.py tests/test_anthropic_provider.py tests/test_streaming.py -x --timeout 30`
  → all pass.
- `tests/test_anthropic_live.py` is `@pytest.mark.live` (deselected by default);
  confirm it still **imports/collects** cleanly:
  `.venv/bin/python -m pytest tests/test_anthropic_live.py --collect-only -q`
  → collects without import error.
- `git diff --stat -- 'the_one/**'` → empty (no production source touched).

## Implementation Guidance

1. **Create the shared module** (recommended `tests/fixtures/tool_schemas.py`).
   - Move the `PRESS_KEY_INPUT_SCHEMA` dict verbatim (it is byte-identical across
     the two hermetic callers — copy from `test_schema_sanitize.py:23`).
   - Move the `BadRequestError` builder using the real-`httpx.Response` form from
     `test_anthropic_provider.py:40`, exposing it under the **public name**
     `make_bad_request` (it now crosses a module boundary, so drop the leading
     underscore):
     ```python
     def make_bad_request(msg: str) -> anthropic.BadRequestError:
         """Construct a BadRequestError (response/body are required kwonly).

         Only the message string is load-bearing — the provider error path reads
         str(err) only, never .body or .response.headers.
         """
         req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
         return anthropic.BadRequestError(msg, response=httpx.Response(400, request=req), body=None)
     ```
   - **Import convention**: this repo imports fixtures by absolute package path
     (`tests/conftest.py:291`, `tests/test_mcp_sandbox_integration.py:70` both use
     `from tests.fixtures.mcp.hello_server import ...`), and `pyproject.toml`
     `addopts` sets `--import-mode=importlib`. Use the matching absolute form in
     every refactored caller:
     `from tests.fixtures.tool_schemas import PRESS_KEY_INPUT_SCHEMA, make_bad_request`.

2. **Refactor `test_schema_sanitize.py`** — replace the `:23` definition with an
   import from the shared module. Update the `:20–22` comment block (it explains
   the inline copy; reframe it to point at the shared module).

3. **Refactor `test_openrouter_provider.py`** — replace the `:16` definition with
   an import. `_press_key_tool_def()` (`:33`) already deep-copies the constant, so
   it keeps working unchanged. Update the `:13–15` comment block. The
   `assert params == PRESS_KEY_INPUT_SCHEMA` at `:76` stays correct against the
   imported constant: the deep-copy means the shared constant is never mutated
   (the `test_non_mutation_of_caller_parameters` test at `:79` further guards it).

4. **Refactor `test_anthropic_live.py`** — replace the `PRESS_KEY_RAW` dict
   (`:56`) with an import of `PRESS_KEY_INPUT_SCHEMA`, and either alias it locally
   (`PRESS_KEY_RAW = PRESS_KEY_INPUT_SCHEMA`) or rename the two usages (`:89`,
   `:121`). Prefer renaming the usages so the old name disappears entirely. Update
   the `:52–55` comment (it explicitly mentions staying "in lockstep without a
   cross-file import" — that rationale is now obsolete).

5. **Refactor `test_anthropic_provider.py`** — replace the `_mk_bad_request`
   definition (`:40`) with an import. All ten call sites in this file pass the
   message positionally, so they keep working if the shared helper's first
   positional param is the message.

6. **Refactor `test_streaming.py`** — replace the `_make_bad_request` definition
   (`:170`) with an import of the shared helper, and update its three call sites
   (`:214`, `:242`, and any other) to the shared name. Both current call sites
   pass the message positionally, so they convert cleanly. Leave the `MagicMock`
   import alone (it's used elsewhere in the file).

7. **Run the touched files** (verification command above) and fix any import
   ordering / lint issues. Do **not** introduce `xfail`/`skip` — this is a pure
   refactor; if a test goes red, the refactor changed behavior and must be fixed.

## Edge Cases
- **`body` divergence**: `test_streaming.py`'s variant set
  `body={"error": {"message": message}}`; the shared (real-`httpx`) form uses
  `body=None`. If any streaming assertion reads `.body` (it should not — verify
  with `grep -n "\.body" tests/test_streaming.py`), keep that test green by
  adjusting the assertion, not by special-casing the helper. Expectation: no
  reader of `.body` exists, so `body=None` is safe.
- **Call-signature mismatch**: `test_streaming.py`'s variant named its param
  `message=`; if any call site used the keyword form (`_make_bad_request(message=...)`),
  it must switch to positional (or the shared helper must accept the same kwarg).
  Verified current call sites pass positionally.
- **Live file collection**: `test_anthropic_live.py` is gated by a module-level
  `@pytest.mark.live` skip; the refactor must not break *collection* (import-time
  errors fail collection even for skipped tests). The collect-only check covers this.
- **No new cross-package import cycle**: the shared module imports only `anthropic`
  + `httpx` (already test deps) and stdlib — no import of `the_one.*` beyond what
  the constant needs (it needs none).

## Files Affected
- `tests/fixtures/tool_schemas.py` — **new** shared module (name is a recommended
  default; see DD6 acceptable variations)
- `tests/test_schema_sanitize.py` — import `PRESS_KEY_INPUT_SCHEMA`; drop local def
- `tests/test_openrouter_provider.py` — import `PRESS_KEY_INPUT_SCHEMA`; drop local def
- `tests/test_anthropic_live.py` — import + converge `PRESS_KEY_RAW`
- `tests/test_anthropic_provider.py` — import the bad-request builder; drop local def
- `tests/test_streaming.py` — import the bad-request builder; converge `_make_bad_request`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (touched files green; live file collects cleanly)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] (Not the final leg — no flight/mission status change)
- [ ] Do NOT commit (deferred-commit model — flight commits once after the last leg)

---

## Citation Audit

5 citations verified against current code at leg design time (2026-06-19):
- `tests/test_schema_sanitize.py:23` `PRESS_KEY_INPUT_SCHEMA` — **OK**
- `tests/test_openrouter_provider.py:16` `PRESS_KEY_INPUT_SCHEMA` (+ `_press_key_tool_def()` at `:33`) — **OK**
- `tests/test_anthropic_live.py:56` `PRESS_KEY_RAW` — **OK**
- `tests/test_anthropic_provider.py:40` `_mk_bad_request()` — **OK**
- `tests/test_streaming.py:170` `_make_bad_request()` (call sites `:214`, `:242`) — **OK**

Note: the flight spec's shorthand "PRESS_KEY" resolves to the actual symbol
`PRESS_KEY_INPUT_SCHEMA`; "the same three files" in earlier framing was corrected
during flight design to the two distinct caller sets documented above.
