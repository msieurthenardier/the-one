# Leg: live-verify-anthropic

**Status**: completed
**Flight**: [Anthropic Tool `input_schema` Compatibility (#122)](../flight.md)

## Objective

Add a `@pytest.mark.live` test (deselected by default `make test`) that confirms our model
of Anthropic's #122 rule is *correct*, not just internally consistent: the **real**
Anthropic API **accepts** the sanitizer's output for the `press_key` schema and still
**400s** on the un-sanitized original — and pin the provisional array-`type` rule from
leg 01 against real Anthropic behavior.

## Context

- This is **leg 04 of 4** — the only live-gated leg. Depends on leg 01 (kernel) and leg 02
  (the adapter wires the kernel into `AnthropicProvider`, so an end-to-end `complete()`
  through the provider exercises the real fix).
- Closes the flight checkpoint "Live-gated test confirms real Anthropic accepts sanitized
  output" and the verification "Live (gated)".
- The flight's leg-01 array-`type` rule (collapse `["object","null"]` → scalar `"object"`)
  was **provisional**, explicitly to be pinned here.
- **Credentials present**: `ANTHROPIC_API_KEY` is in the gitignored `.env`; the Flight
  Director will run this leg's live test host-native with the key sourced. The test
  self-skips when the key is absent (so it's safe in keyless CI).

### Live-test conventions (verified in-repo)

- `live` marker is registered and deselected by default (`pyproject.toml:86,89`:
  `addopts = "-m 'not live and ...'"`).
- Model: `pytest.mark.live`. Existing live tests self-skip when their credential env var is
  unset, allow a `LIVE_ANTHROPIC_MODEL` override (default `claude-haiku-4-5-20251001`),
  construct the provider directly (async), and best-effort `await provider.client.aclose()`
  in teardown (model on `tests/test_input_tokens_cross_provider_live.py`).
- The request only needs to be **accepted vs rejected** by the API's tool-schema
  validation — the model does not have to actually call the tool — so prompts are trivial
  and `max_tokens` tiny (cost ≈ a few cheap-model tokens per test).

## Inputs

- `the_one/llm/anthropic_provider.py` (leg 02 wired): `complete()` sanitizes tools before send.
- `the_one/llm/_schema_sanitize.py` (leg 01): `sanitize_tool_schema` (to produce the
  sanitized schema for the direct-SDK acceptance assertion / array-type pin).
- The leg-01 `press_key` fixture (top-level `anyOf`).
- `anthropic 0.97.0`; `ANTHROPIC_API_KEY` in `.env` (gitignored).
- Live-test model: `tests/test_input_tokens_cross_provider_live.py`.

## Outputs

- New file `tests/test_anthropic_live.py` — `@pytest.mark.live` tests below.
- No production-code changes expected. **If the array-`type` pin reveals leg-01's rule is
  wrong** (e.g. real Anthropic accepts an array `type` and we needn't collapse, or rejects
  the collapsed form), that is a **divert**: stop, record it in the flight log, and adjust
  the leg-01 kernel + its unit test in a follow-up cycle before this leg lands.

## Acceptance Criteria

All under `@pytest.mark.live`; each self-skips if `ANTHROPIC_API_KEY` is unset.

- [x] **Real Anthropic accepts the sanitized `press_key` (end-to-end through the provider)**:
      `AnthropicProvider(model=LIVE_ANTHROPIC_MODEL).complete(messages=[trivial user msg],
      tools=[press_key_canonical_tool], max_tokens=16)` returns a `Message` **without
      raising** — i.e. leg 02's in-adapter sanitize makes the formerly-400ing tool work
      against the live API.
- [x] **Real Anthropic still 400s on the un-sanitized `press_key`**: a **direct** SDK call
      (`provider.client.messages.create(...)` with `tools=[{... "input_schema":
      PRESS_KEY_RAW ...}]`, bypassing the adapter's sanitize) raises
      `anthropic.BadRequestError` (`status_code == 400`). **Assertion robustness (review,
      medium):** the exact #122 wording was only observed via the OpenRouter→Bedrock relay
      in the probe, never against the first-party API this leg calls — so do **not** hard-gate
      on the literal `"top level"` substring. Bind on: it is a `BadRequestError` AND
      `"anyOf" in str(exc)` AND a tolerant `re.search(r"top[- ]level", str(exc), re.I)`.
      `print` the full message (flush) so the exact first-party wording is recorded in the
      `-v` output and the flight log. This proves the acceptance above is meaningful, not
      vacuous. **A 400 with unexpected wording is a brittle-assertion miss, NOT a leg-01
      divert** — the divert is reserved strictly for the array-type case below.
- [x] **Array-`type` pin (resolves leg 01's provisional rule)**: send, via a **direct** SDK
      call, a tool whose `input_schema` is a minimal object with top-level
      `type: ["object", "null"]`. Record the outcome. Then send the leg-01-sanitized form
      (scalar `type:"object"`) and assert it is **accepted**. The binding assertion is that
      the **sanitized (scalar) form is accepted**; the raw-array outcome is recorded in the
      test (and flight log) to confirm the collapse rule is correct (or trigger the divert
      if the collapsed form is unexpectedly rejected).

## Verification Steps

- `cd /home/cprch/projects/the-one`
- Default suite still excludes these (proves the marker/deselect works):
  `.venv/bin/pytest tests/test_anthropic_live.py -q` → **all deselected/skipped** (0 run
  under default addopts).
- Live run (Flight Director executes, key from `.env`):
  `set -a && . ./.env && set +a && .venv/bin/pytest -m live tests/test_anthropic_live.py -v`
  → all pass (none skipped, since the key is present).
- `ruff check tests/test_anthropic_live.py` clean; `ruff format --check` clean.
- Regression: `.venv/bin/pytest tests/test_schema_sanitize.py tests/test_anthropic_provider.py
  tests/test_openrouter_provider.py -q` still green (32 + 17 + 5-new).

## Implementation Guidance

1. **Skeleton** — module docstring noting cost + live-marker usage; import `os`, `pytest`,
   `anthropic`, the provider, `sanitize_tool_schema`, and inline the `press_key` raw fixture.
   ```python
   pytestmark = pytest.mark.live
   _MODEL = os.environ.get("LIVE_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
   _skip = pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"),
                              reason="ANTHROPIC_API_KEY not set")
   ```
2. **Teardown** — `await provider.aclose()` in a `finally` (the provider exposes `aclose()`
   at `anthropic_provider.py:106`; it calls `self.client.close()`, idempotent). Use this
   public form consistently (not `provider.client.aclose()`).
3. **Accepted-through-provider test** — build the canonical tool dict
   `{"name": "press_key", "description": "...", "parameters": PRESS_KEY_RAW}`, call
   `await provider.complete(messages=[Message.user("Say hi.")], tools=[tool], max_tokens=16)`.
   Assert it returns a `Message` AND a cheap sanity check (`result.role == Role.ASSISTANT`,
   or `result.usage is not None`) so a future SDK change can't return something falsy-but-
   non-raising and pass vacuously. (The adapter sanitizes internally; if the API rejected
   the sanitized schema the call would raise — so a clean return IS the load-bearing
   assertion.)
4. **Rejected-direct test** — construct the Anthropic-native tool by hand
   (`{"name","description","input_schema": PRESS_KEY_RAW}`) and call
   `await provider.client.messages.create(model=_MODEL, max_tokens=16, messages=[...],
   tools=[that_tool])`; wrap in `pytest.raises(anthropic.BadRequestError)` and assert the
   message contains `"anyOf"` and `"top level"`.
5. **Array-type pin** — raw tool with `input_schema = {"type": ["object","null"],
   "properties": {"x": {"type":"string"}}}`. Do a direct `create`; capture accept/raise into
   a variable and `print`/log it (visible in `-v`). Then `sanitize_tool_schema` that same
   schema (→ scalar `type:"object"`) and assert a direct `create` with the sanitized form is
   accepted. `print(..., flush=True)` the raw-array outcome so it survives `-v` capture and
   can be copied into the flight log. If the raw-array call is **accepted** by Anthropic,
   that's fine (our collapse is still valid — scalar object is a subset); if the
   **sanitized** form is **rejected**, STOP — that's the divert (leg-01 rule is wrong).
6. **Keep it cheap** — `max_tokens=16`, one-line prompts. No assertions on model output, only
   on request acceptance/rejection.

## Edge Cases

- **Model not accessible to this key family**: if `complete()`/`create()` raises a 404 /
  model-access error (not a 400 schema error), the test environment's model choice is wrong
  — surface via `LIVE_ANTHROPIC_MODEL`; do not mask a model-access failure as a schema pass.
  (The probe used `claude-3.5-haiku` via OpenRouter; direct Anthropic default here is
  `claude-haiku-4-5-20251001` per the existing live-test convention.)
- **Rate/transient 429/5xx**: acceptable to let the test error (live tests are operator-run,
  not CI-gated); do not add retry complexity.
- **Model-independence of the check**: the #122 rejection is a *request-validation* error
  that fires before model inference, so it is provider/endpoint-level, not model-level — the
  cheap `claude-haiku-4-5-20251001` default is a valid proxy for any Anthropic model the
  operator routes to in production.

## Files Affected
- `tests/test_anthropic_live.py` — **new**; `@pytest.mark.live` correctness tests.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] Default `pytest` excludes the file (deselected); live run with the key passes all
- [x] Array-`type` outcome recorded (confirms leg-01 rule or triggers divert) — raw array
      `type:["object","null"]` **rejected** by first-party Anthropic; sanitized scalar
      `type:"object"` **accepted** → leg-01 collapse rule **CORRECT, no divert**
- [x] Regression suites still green (72 passed)
- [x] Update flight-log.md with leg progress entry (incl. the recorded array-type live result)
- [x] Set this leg's status to `landed` in this file's header; check off acceptance boxes
- [x] (Final autonomous leg — but do NOT flip flight/mission status or commit; the Flight
      Director runs the single flight review + commit + landing after this leg)
