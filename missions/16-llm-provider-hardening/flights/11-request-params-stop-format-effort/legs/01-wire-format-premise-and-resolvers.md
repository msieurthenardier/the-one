# Leg: wire-format-premise-and-resolvers

**Status**: completed
**Flight**: [Request-Param Capabilities (A4)](../flight.md)

## Objective

Pin the accepted request wire-format and per-model default for each A4 param
(`reasoning_effort`, `response_format`, `stop`) against first-party authority
and record it as a flight-log premise; then land the three canonical
config→env→default resolvers in a new shared module, unit-tested — touching **no**
provider request path.

## Context

- **DD4 (wire-format gate, F10 Rec 1)**: no param is wired on an assumed format.
  Both of Flight 10's mid-flight corrections came from skipping this gate, so it
  is its own leg and runs *before* any provider wiring (L02–L04 depend on it).
- **DD1 (config surface, not the ABC)**: A4 params ride
  `LLMProviderConfig.config` (config → env → default) and are read in each
  provider's `__init__` into an instance attr — exactly like
  `resolve_extended_thinking` (`anthropic_provider.py:resolve_extended_thinking`)
  and `effective_num_ctx` (`ollama_provider.py:effective_num_ctx`). The abstract
  `complete()`/`stream()` signatures stay untouched, so nothing cascades to the
  ~13 hand-rolled test doubles.
- **DD3 (canonical → per-provider mapping)**: the resolvers produce a *canonical*
  value; each provider's request builder (L02–L04) maps that canonical value to
  its native SDK shape. This leg builds only the canonical resolvers, not the
  mappings.
- **Design call — new shared module.** The two existing resolvers are
  provider-local because they are provider-specific concepts (Anthropic thinking;
  Ollama num_ctx). The A4 params are **cross-provider**, so their canonical
  resolvers live in a new `the_one/llm/_request_params.py`, matching the repo's
  underscore-prefixed shared-helper idiom (`_streaming.py`, `_schema_sanitize.py`,
  `_toolcall_recovery.py`). Provider modules import from it in later legs.
- **Canonical env vars are provider-agnostic** (`THE_ONE_REASONING_EFFORT`,
  `THE_ONE_RESPONSE_FORMAT`, `THE_ONE_STOP`) because the param is canonical — this
  differs from the provider-scoped `THE_ONE_ANTHROPIC_EXTENDED_THINKING` /
  `THE_ONE_OLLAMA_NUM_CTX`, and is deliberate.

## Inputs

- `the_one/llm/anthropic_provider.py` — `resolve_extended_thinking` + `_coerce_bool`
  (resolver/coercer pattern to mirror).
- `the_one/llm/ollama_provider.py` — `effective_num_ctx` + `_coerce_num_ctx`
  (precedence + lenient-coercion pattern to mirror).
- `tests/test_anthropic_provider.py:509-569` — the `_coerce_bool` /
  `resolve_extended_thinking` unit-test block (test shape to mirror).
- Installed, pinned SDKs as first-party authority for accepted params/shapes:
  **anthropic 0.97.0**, **openai 2.33.0** (per flight-log SDK pre-check).

## Outputs

- **NEW** `the_one/llm/_request_params.py` — canonical resolvers + coercers.
- **NEW** `tests/test_request_params.py` — unit tests for all three resolvers.
- **flight-log.md** — a recorded **Wire-Format Premise** section (the doc-gate
  deliverable) + a Leg Progress entry.
- **No** provider request path modified; **no** ABC signature change.

## Acceptance Criteria

- [x] **Doc-gate recorded**: flight-log.md gains a clearly-titled Wire-Format
      Premise section stating, for each of `reasoning_effort` / `response_format` /
      `stop`, the accepted request shape and per-model default on the current
      target lineup for **Anthropic**, **OpenAI**, and **Ollama** (both `/v1` and
      native paths), each sourced from a cited authority (installed SDK
      type/param surface, and/or first-party docs). Every claim cites its source;
      anything not verifiable from the repo/SDK is explicitly flagged as
      **HAT-confirm (L07)** rather than asserted.
- [x] **Effort × adaptive-thinking composition resolved** (flight open question):
      the premise states, for the target Anthropic lineup, whether
      `output_config.effort` and the existing `thinking={type:adaptive,...}` block
      (`anthropic_provider.py` `_build_kwargs`, the `kwargs["thinking"]` site)
      coexist, whether one supersedes the other, or whether the combination is
      rejected. **Resolve it now from first-party docs if they settle it** —
      current Anthropic docs indicate effort *composes* with adaptive thinking
      ("Combine with adaptive thinking…"); WebFetch and **cite** the effort/thinking
      doc rather than defaulting to HAT-confirm. Flag HAT-confirm only if the docs
      genuinely don't settle it.
- [x] **Divert-trigger check**: the premise explicitly states, per provider,
      whether each param maps cleanly to a single canonical shape or hits a
      flight "Divert if" condition (e.g. Anthropic structured output being
      tool-based rather than a `response_format` analog). If a divert condition
      fires, STOP and surface to the Flight Director — do not force a leaky
      canonical.
- [x] **`resolve_reasoning_effort(configured)`** exists in
      `the_one/llm/_request_params.py`, precedence config → env
      `THE_ONE_REASONING_EFFORT` → default `None`, returning a canonical
      lowercased effort string or `None`; junk/`bool`/empty coerces to `None`
      (falls through), never raises.
- [x] **`resolve_response_format(configured)`** exists, precedence config → env
      `THE_ONE_RESPONSE_FORMAT` → default `None`, returning a canonical
      structured-output value (per the doc-gate; see Guidance) or `None`; a JSON
      string from env is parsed leniently; junk coerces to `None`, never raises.
      The canonical value space keeps **both** `{"type": "json_object"}` and
      `{"type": "json_schema", "schema": {...}}` (decision, see Guidance step 2) —
      the canonical layer does not reject `json_object`; providers that lack a
      bare-JSON-mode surface no-op it in their wiring leg.
- [x] **Anthropic structured-output constraint recorded**: the doc-gate premise
      states explicitly that anthropic 0.97.0 `output_config.format` accepts
      **only** `{"type": "json_schema", "schema": {...}}` (no bare JSON-mode) —
      confirmed in the installed stub
      `.venv/.../anthropic/types/output_config_param.py` (`JSONOutputFormatParam`).
      Consequence to carry into L02: canonical `{"type": "json_object"}` on
      Anthropic is a **documented no-op/warning**, not an error and not forced —
      this is the flight's "Acceptable variations: per-provider no-ops"
      bucket, NOT a "Divert if" trigger.
- [x] **`resolve_stop(configured)`** exists, precedence config → env
      `THE_ONE_STOP` → default `None`, returning `list[str]` (a bare string
      becomes a one-element list; a JSON-array env string is parsed) or `None`;
      empty/junk coerces to `None`, never raises.
- [x] **Unit tests** in `tests/test_request_params.py` cover, for each resolver:
      config-wins-over-env, env-fallback, default-when-unset, and
      junk/empty/`bool`-coerces-to-`None` — mirroring the existing
      `resolve_extended_thinking` test block. Env cases use `monkeypatch`.
      Additionally, for `response_format` and `stop`, one explicit
      **valid-JSON-but-wrong-shape** case each (e.g. `THE_ONE_STOP='{"a":1}'` — a
      dict, not a list/string → `None`; `THE_ONE_RESPONSE_FORMAT='[1,2]'` → `None`)
      to lock the recursive-recoerce behavior, and one **valid-JSON-right-shape**
      env case each (e.g. `THE_ONE_STOP='["</s>","STOP"]'` → `["</s>","STOP"]`) to
      lock the new JSON-decode-from-env path that has no in-repo precedent.
- [x] **No provider request path touched**: `git diff --stat` shows changes only
      under the new module, the new test, and the flight artifacts — no
      `*_provider.py` request-building code modified.
- [x] Targeted test run green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
      tests/test_request_params.py -x --timeout 30`.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_request_params.py -x --timeout 30` — all new resolver tests pass.
- `git diff --stat` — confirms only the new module, new test, and flight artifacts changed (no `*_provider.py`).
- Read the flight-log Wire-Format Premise section — confirm every param×provider cell has a cited source or an explicit HAT-confirm flag, and that the effort×thinking composition question is answered.
- `grep -n "def resolve_" the_one/llm/_request_params.py` — three resolvers present.

## Implementation Guidance

1. **Doc-gate first (record before writing resolvers).**
   - Treat the installed pinned SDKs as the authoritative surface for *accepted
     params and shapes*: inspect `anthropic` 0.97.0 and `openai` 2.33.0 type stubs
     (e.g. `.venv/bin/python -c "import anthropic, inspect; ..."`, or read the
     installed package sources under `.venv/`) to confirm the parameter names and
     value types the flight-log SDK pre-check already sketched:
     Anthropic `output_config.effort` (`Literal[...]`), `output_config.format`
     (native `json_schema`), `stop_sequences`; OpenAI `reasoning_effort`,
     `response_format` (`json_schema` vs `json_object`).
   - For **per-model defaults** and the **effort × adaptive-thinking** interaction
     (which the SDK types don't encode), consult first-party docs (WebFetch/
     WebSearch the Anthropic + OpenAI + Ollama API docs). Where a claim cannot be
     settled from repo/SDK/docs with confidence, flag it **HAT-confirm (L07)** —
     do not guess.
   - For **Ollama**, record the `/v1` (OpenAI-compat) surface vs the native
     `think`/`format`/`options.stop` surface for each param, noting which path
     honors which (the native path is the one to trust where they diverge).
   - Write it all into flight-log.md under a new `## Wire-Format Premise` section
     (append; do not disturb existing sections). One sub-block per param, a small
     table of provider × {accepted shape, per-model default, source|HAT-confirm}.

2. **Create `the_one/llm/_request_params.py`.**
   - Module docstring: canonical cross-provider A4 resolvers; config→env→default;
     canonical value mapped to native shapes per-provider in later legs (cite
     DD1/DD3). Mirror the tone of the `resolve_extended_thinking` docstring.
   - `_coerce_effort(value) -> str | None`: accept a non-empty `str`
     (strip+lower); reject `bool` explicitly and everything else → `None`. (Do
     **not** hard-validate the allowed set here — the accepted set differs per
     provider, so per-provider validation belongs in L02–L04. Canonical layer
     only normalizes shape.)
   - `_coerce_response_format(value) -> <canonical> | None`: **decision (binds
     L02–L04): keep BOTH canonical variants** — accept the string
     `"json"`/`"json_object"` → canonical `{"type": "json_object"}`; accept a dict
     already shaped `{"type": "json_object"}` or
     `{"type": "json_schema", "schema": {...}}` and pass it through; accept a JSON
     **string** (env case) by `json.loads` then re-coercing the result; anything
     else → `None`. Never raise on bad JSON — catch and return `None`. Do **not**
     drop `json_object`: OpenAI and Ollama `/v1` support bare JSON mode natively;
     **Anthropic does not** (its `output_config.format` is `json_schema`-only, per
     the doc-gate), so L02 resolves canonical `json_object` to a documented
     no-op/warning on Anthropic — the canonical layer stays capable, the provider
     leg handles the gap. **New pattern flag**: the JSON-string-from-env decoding
     here (and in `_coerce_stop`) has **no in-repo precedent** —
     `resolve_extended_thinking`/`effective_num_ctx` are scalar bool/int coercions
     with no JSON step — so do not assume existing tests cover it; the new tests
     must exercise the decode paths directly.
   - `_coerce_stop(value) -> list[str] | None`: accept a non-empty `str` → `[str]`;
     a `list`/`tuple` of non-empty `str` → `list[str]` (drop non-str/empty
     entries; if nothing survives → `None`); a JSON-array **string** (env case)
     via `json.loads` then re-coerce; anything else → `None`.
   - `resolve_reasoning_effort(configured: str | None) -> str | None`,
     `resolve_response_format(configured=None)`, `resolve_stop(configured=None)`:
     **decision (binds all three, resolving the "be consistent" ambiguity):**
     follow the `resolve_extended_thinking` / `effective_num_ctx` contract — the
     caller's `__init__` coerces the raw `config` value via the `_coerce_*` helper
     and passes an **already-canonical `configured`** (so `configured` wins as-is
     when not `None`); the resolver itself coerces **only** the env read (env is
     always a raw string) via the same `_coerce_*` helper, at call time (not
     import time); else default `None`. This matches both in-repo precedents (both
     coerce in `__init__`, pass coerced value to the resolver) and keeps `_coerce_*`
     independently unit-testable. Apply the identical shape to all three.

3. **Write `tests/test_request_params.py`.**
   - Mirror `tests/test_anthropic_provider.py:509-569`: a `_coerce_*` block
     (pass-through, string encodings, junk→None, bool handling) and a
     `resolve_*` block (config-wins, config-wins-over-env, env-fallback,
     default-when-unset, env-junk→default). Use `monkeypatch.setenv` /
     `monkeypatch.delenv(..., raising=False)` for env cases.
   - No live calls; no provider construction — pure helper tests.

4. **Do not** import the new module into any provider yet, and do not export the
   resolvers from `the_one/llm/__init__.py` this leg (wiring is L02–L04).

## Edge Cases

- **Env holds malformed JSON** for `response_format`/`stop`: `json.loads` raises —
  catch and return `None` (fall through), never propagate.
- **Env holds valid JSON of the wrong shape** (`THE_ONE_STOP='{"a":1}'`,
  `THE_ONE_RESPONSE_FORMAT='[1,2]'`): decode succeeds but re-coercion rejects the
  shape → `None`. Explicitly tested (see criteria).
- **Anthropic has no bare-JSON mode**: canonical `{"type": "json_object"}` is
  valid at the canonical layer but has no Anthropic target (schema-required only).
  This is NOT handled here — the canonical resolver returns it unchanged; L02
  no-ops/warns for Anthropic. Recorded so it is a designed no-op, not a surprise.
- **`bool` for effort/stop**: `bool` is an `int` subclass; reject explicitly
  (the `_coerce_num_ctx` precedent does this) so `True` doesn't become `"true"`
  or `[True]`.
- **Empty string / empty list**: coerces to `None` so the resolver falls through
  to env/default rather than sending an empty param downstream.
- **Doc-gate divert**: if a param can't map to one canonical shape across
  providers (a flight "Divert if" trigger, e.g. Anthropic structured output is
  tool-based), STOP and escalate — do not invent a leaky canonical to satisfy the
  resolver criterion.

## Files Affected

- `the_one/llm/_request_params.py` — **NEW**: `resolve_reasoning_effort`,
  `resolve_response_format`, `resolve_stop` + `_coerce_*` helpers.
- `tests/test_request_params.py` — **NEW**: unit tests for the three resolvers.
- `missions/16-llm-provider-hardening/flights/11-request-params-stop-format-effort/flight-log.md`
  — append `## Wire-Format Premise` (doc-gate) + Leg Progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`tests/test_request_params.py`)
- [ ] Update flight-log.md with leg progress entry + Wire-Format Premise section
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] (Not final leg — no flight/mission status change)
- [ ] Changes committed together with the rest of the autonomous batch (this
      flight defers per-leg commit to the post-L06 batch review — do NOT commit
      at leg end)
