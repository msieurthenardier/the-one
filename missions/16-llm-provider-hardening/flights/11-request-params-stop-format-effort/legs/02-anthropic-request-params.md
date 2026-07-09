# Leg: anthropic-request-params

**Status**: completed
**Flight**: [Request-Param Capabilities (A4)](../flight.md)

## Objective

Wire the three A4 params (`reasoning_effort`, `response_format`, `stop`) from the
config surface into the Anthropic provider's request, in their native SDK shapes,
at the single `_build_kwargs` site — with `json_object` a documented no-op on
Anthropic — and fixture it with direct-`_build_kwargs` assertions.

## Context

- **Depends on L01** (landed): canonical resolvers `resolve_reasoning_effort` /
  `resolve_response_format` / `resolve_stop` + `_coerce_*` in
  `the_one/llm/_request_params.py`; the Wire-Format Premise in the flight log.
- **Doc-gate findings that bind this leg** (flight-log `## Wire-Format Premise`):
  - `reasoning_effort` → **`output_config.effort`**
    (`Literal["low","medium","high","xhigh","max"]`), a sibling field on the same
    `output_config` dict that carries `format`. Confirmed top-level
    `messages.create` param (`message_create_params.py:138 — output_config`).
  - `response_format` → **`output_config.format`**, which is **`json_schema`-only**
    (`JSONOutputFormatParam`: both `schema` and `type` `Required`, `type ==
    "json_schema"`). **No bare JSON mode.** Canonical `{"type": "json_object"}` has
    no Anthropic target → **documented no-op + warning** (flight "Acceptable
    variations" bucket, NOT a divert).
  - `stop` → **`stop_sequences: list[str]`**, top-level `messages.create` param
    (`message_create_params.py:150`).
  - **effort × adaptive-thinking composes** (resolved from cited docs): add
    `output_config.effort` *alongside* the existing
    `kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}` block —
    not instead of it. `output_config` and `thinking` are independent top-level
    params.
- **DD1**: params ride the config surface; the ABC signature is untouched. Read
  the three config keys in `__init__` (coerce there via the `_coerce_*` helpers),
  apply the resolved values in `_build_kwargs`. This mirrors the existing
  `self._thinking_enabled_config` read (`anthropic_provider.py:__init__`).

## Inputs

- `the_one/llm/_request_params.py` (L01) — resolvers + `_coerce_*` helpers.
- `the_one/llm/anthropic_provider.py`:
  - `__init__` — reads `config["thinking_enabled"]` today; add the three A4 reads
    next to it.
  - `_build_kwargs` — the single request-kwargs assembly (used by both `complete`
    and `stream` via `_stream_inner`); the `kwargs["thinking"] = {...}` site and
    the `return kwargs` at the end are the anchors.
- `tests/test_anthropic_provider.py` — `test_init_reads_thinking_enabled_from_config`
  (`:585`) is the exact precedent for the `__init__`-attr tests. **For asserting
  the built kwargs**, note two idioms: the `_build_kwargs` enablement tests
  (`:606+`) exercise the result *through `prov.complete()` + `_CreateRecorder`*
  (inspecting `rec.calls[0]`), NOT via a direct `_build_kwargs()` call; the
  precedent for a **direct** `_build_kwargs()` call is
  `tests/test_llm_provider_cross_provider_conformance.py:499`
  (`aprov._build_kwargs([Message.user("hi")], [...], 0.0, 16)`). This leg's new
  `_build_kwargs` tests use the **direct-call** idiom (simpler, no mock plumbing) —
  a deliberate divergence from this file's recorder style. The temperature-retry
  test (below) DOES use the recorder idiom (`_CreateRecorder(side_effects=[...])`,
  `:253-345`).

## Outputs

- `the_one/llm/anthropic_provider.py` — `__init__` reads three A4 config keys into
  instance attrs; `_build_kwargs` emits `stop_sequences` and `output_config`
  (`effort` / `format`) in native shapes.
- `tests/test_anthropic_provider.py` — A4 tests (init attr reads + `_build_kwargs`
  wiring + `json_object` no-op warning + effort/thinking coexistence).

## Acceptance Criteria

- [x] **`__init__` reads the three A4 config keys** into instance attrs (e.g.
      `self._reasoning_effort_config`, `self._response_format_config`,
      `self._stop_config`) via the L01 `_coerce_*` helpers — canonical-or-`None`,
      never raising on junk/absent/non-dict config (mirrors the existing
      `_thinking_enabled_config` read).
- [x] **`stop` wired**: when `resolve_stop(self._stop_config)` is non-empty,
      `_build_kwargs` sets `kwargs["stop_sequences"]` to that `list[str]`; when
      `None`, the key is absent.
- [x] **`reasoning_effort` wired**: when `resolve_reasoning_effort(...)` is
      non-empty, `_build_kwargs` sets `output_config["effort"]` to that string;
      when `None`, no `effort` key.
- [x] **`response_format` json_schema wired**: canonical
      `{"type": "json_schema", "schema": {...}}` → `output_config["format"] =
      {"type": "json_schema", "schema": {...}}`.
- [x] **`response_format` json_object no-ops on Anthropic**: canonical
      `{"type": "json_object"}` sets **no** `output_config["format"]` and logs a
      `warning` naming the reason (Anthropic structured output is json_schema-only).
      Verified via `caplog` (the file already uses `caplog` — see
      `test_drop_warning_names_tool_and_reason`).
- [x] **`output_config` assembled correctly**: `effort` and `format` share one
      `output_config` dict; the key is present only when at least one sub-field is
      set, absent otherwise (never send an empty `output_config`).
- [x] **Coexists with the thinking block**: with thinking active AND effort set,
      the built kwargs carry **both** `kwargs["thinking"] = {"type":"adaptive",
      "display":"summarized"}` and `kwargs["output_config"]["effort"]` — neither
      clobbers the other (asserted in a test).
- [x] **No ABC signature change**; `complete`/`stream` signatures unchanged.
- [x] **Temperature-retry preserves A4 kwargs (tested)**: a test mirroring the
      existing retry construction (`_CreateRecorder(side_effects=[<temperature
      BadRequestError>, <ok>])`, `test_anthropic_provider.py:253-345`) with
      `config={"stop": [...], "reasoning_effort": "high"}` set asserts the
      **retried** call's kwargs still carry `stop_sequences` and `output_config`
      (only `temperature` is popped).
- [x] Targeted tests green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
      tests/test_anthropic_provider.py -x --timeout 30`.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_anthropic_provider.py -x --timeout 30` — all pass, including new A4 tests.
- Read the `_build_kwargs` diff — confirm `output_config` is built once, guarded on non-empty, and the `json_object` branch warns + skips.
- `git diff --stat` — only `anthropic_provider.py` + `tests/test_anthropic_provider.py` changed (plus flight artifacts).

## Implementation Guidance

1. **`__init__` — read the three A4 keys** (right after the existing
   `self._thinking_enabled_config` block):
   ```python
   from the_one.llm._request_params import (
       resolve_reasoning_effort, resolve_response_format, resolve_stop,
       _coerce_effort, _coerce_response_format, _coerce_stop,
   )  # import at module top, next to existing imports
   ...
   _cfg = config if isinstance(config, dict) else {}
   self._reasoning_effort_config = _coerce_effort(_cfg.get("reasoning_effort"))
   self._response_format_config = _coerce_response_format(_cfg.get("response_format"))
   self._stop_config = _coerce_stop(_cfg.get("stop"))
   ```
   (`config = kwargs.get("config")` already exists above the thinking read — reuse
   it; do not re-fetch.)

2. **`_build_kwargs` — apply, just before `return kwargs`** (after the `thinking`
   block so ordering reads naturally; both are independent top-level params):
   ```python
   # A4 (M16 F11 L02): stop / reasoning_effort / structured output from config surface.
   stop = resolve_stop(self._stop_config)
   if stop:
       kwargs["stop_sequences"] = stop
   output_config: dict[str, Any] = {}
   effort = resolve_reasoning_effort(self._reasoning_effort_config)
   if effort:
       output_config["effort"] = effort
   rf = resolve_response_format(self._response_format_config)
   if rf:
       if rf.get("type") == "json_schema" and rf.get("schema") is not None:
           output_config["format"] = {"type": "json_schema", "schema": rf["schema"]}
       else:
           logger.warning(
               "anthropic: response_format %r has no Anthropic surface "
               "(structured output is json_schema-only); ignoring.",
               rf.get("type"),
           )
   if output_config:
       kwargs["output_config"] = output_config
   ```
   Match the module's existing style (the `logger` is already module-level;
   `Any` is already imported).

3. **Tests** — add an A4 block to `tests/test_anthropic_provider.py`:
   - `__init__` attr reads: mirror `test_init_reads_thinking_enabled_from_config`
     — construct `AnthropicProvider(model="claude-test", config={...})`, assert the
     three attrs; and absent/non-dict/junk → `None` for each.
   - `_build_kwargs` wiring: construct with each config, call
     `prov._build_kwargs([Message.user("hi")], None, 0.0, 16384)` directly (the
     `test_llm_provider_cross_provider_conformance.py:499` idiom — `Message.user`
     is the house helper; do NOT import `Role` / construct `Message(role=...)`,
     which the file doesn't do) and assert `stop_sequences` /
     `output_config["effort"]` / `output_config["format"]` as specified.
   - json_object no-op: assert no `output_config` `format` key AND a warning via
     `caplog.at_level(logging.WARNING, logger=_LOGGER_NAME)`.
   - Coexistence: with `config={"thinking_enabled": True, "reasoning_effort":
     "high"}`, assert both `kwargs["thinking"]` and `kwargs["output_config"]
     ["effort"] == "high"` present.
   - `None`-path: with no A4 config and env unset (`monkeypatch.delenv` the three
     env vars `raising=False`), assert neither `stop_sequences` nor `output_config`
     appears.
   - Temperature-retry survival: use the `_CreateRecorder(side_effects=[...])`
     recorder idiom (`:253-345`), `config={"stop": ["</s>"], "reasoning_effort":
     "high"}`, drive `await prov.complete(...)`, and assert the **second**
     (retried) recorded call still carries `stop_sequences` and `output_config`.

4. Do **not** change `complete`/`stream` signatures, the ABC, or any other
   provider. Do not export anything new from `the_one/llm/__init__.py`.

## Edge Cases

- **Unsupported effort value for the target model** (e.g. `xhigh` on a model that
  only accepts up to `high`): the API 400s at request time. **Not caught this
  flight** — per-route/param capability gating is backlog B4. The canonical layer
  deliberately does not validate the effort set (sets differ per model). Document
  in the leg progress; the HAT (L07) will surface any real mismatch on the chosen
  model.
- **`output_config` 400**: if `output_config` itself is rejected, the existing
  temperature-retry won't fix it (only pops `temperature`) → the error re-raises.
  Acceptable — the flight does not add graceful degradation for unsupported params.
- **json_schema missing `schema`**: the L01 canonical coercer guarantees a
  `json_schema` canonical value carries a `schema`; the `rf.get("schema") is not
  None` guard is belt-and-suspenders — a malformed value skips the format key
  rather than sending `{"type":"json_schema"}` bare (which would 400).
- **Empty-dict schema (`{"type":"json_schema","schema":{}}`)**: passes the `is not
  None` guard and is forwarded as `output_config.format` with an empty schema. This
  is intentional and harmless — an empty JSON Schema is valid (matches anything);
  no special-casing. Noted so it isn't mistaken for a gap.

## Files Affected

- `the_one/llm/anthropic_provider.py` — `__init__` A4 reads; `_build_kwargs` A4
  wiring.
- `tests/test_anthropic_provider.py` — A4 test block.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`tests/test_anthropic_provider.py`)
- [ ] Update flight-log.md with a Leg Progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] (Not final leg — no flight/mission status change)
- [ ] Changes stay uncommitted — batch commit after L06 (do NOT commit at leg end)
