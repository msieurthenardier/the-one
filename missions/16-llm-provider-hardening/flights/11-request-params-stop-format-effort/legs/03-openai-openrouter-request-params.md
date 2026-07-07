# Leg: openai-openrouter-request-params

**Status**: completed
**Flight**: [Request-Param Capabilities (A4)](../flight.md)

## Objective

Wire the three A4 params into the OpenAI provider's two request sites in their
native OpenAI shapes, and wire the A4 config-key reads into **both**
`OpenAIProvider.__init__` (reads no config today) and `OpenRouterProvider.__init__`
(skips `super().__init__()`, ignores config today) — so OpenRouter inherits the
request wiring for free while still reading its own config — with a config→wire
assertion for each.

## Context

- **Depends on L01** (landed resolvers) and follows **L02** (Anthropic, landed).
- **DD5** (the sizing correction from the flight design review): OpenRouter
  overrides neither `complete` nor `stream`, so once OpenAI's request assembly
  forwards the A4 params they are inherited for free — **but config→attr reading is
  NOT inherited**: `OpenAIProvider.__init__` reads no `config` today, and
  `OpenRouterProvider.__init__` (`openrouter_provider.py:85`) deliberately skips
  `super().__init__()` and currently ignores its `config=` param
  (`:90 "accepted for factory uniformity; unused"`). So A4 must wire the three
  config-key reads into **both** `__init__`s separately.
- **Instance-attribute parity is enforced.** `OpenAIProvider.__init__`
  (`openai_provider.py:54-56`) carries a "any new `self.X` here MUST also be set in
  `OpenRouterProvider.__init__`" contract, pinned by
  `test_subclass_has_all_parent_instance_attrs`
  (`tests/test_openrouter_provider.py:272` — `vars(parent) - vars(sub) == set()`).
  The A4 attrs must therefore be set in **both** constructors. The clean way to
  guarantee that: a single `_read_a4_config(config)` helper on `OpenAIProvider`
  that both `__init__`s call.
- **Doc-gate findings that bind this leg** (flight-log `## Wire-Format Premise`):
  - `reasoning_effort` → OpenAI top-level **`reasoning_effort`** (string). Applies
    to reasoning models; per-model default varies (not our concern — we only send
    when configured).
  - `stop` → OpenAI top-level **`stop`** (`str | list[str]`); canonical `list[str]`
    maps directly. Doc-gate flag: **not supported on o3 / o4-mini** — if configured
    against those models it 400s (per-route gating is B4, out of scope; record).
  - `response_format` → OpenAI **`response_format`**. Two native shapes:
    - canonical `{"type": "json_object"}` → OpenAI `{"type": "json_object"}`
      (direct — the legacy bare-JSON mode; **OpenAI supports it**, unlike Anthropic).
    - canonical `{"type": "json_schema", "schema": {...}}` → OpenAI requires a
      **wrapper with a required `name`**:
      `{"type": "json_schema", "json_schema": {"name": <str>, "schema": {...}}}`.
      The canonical shape carries no guaranteed `name`, so **synthesize one**:
      `name = rf.get("name") or "response"` (L01's `_coerce_response_format` passes
      a json_schema dict through unchanged, so a caller-supplied `"name"` survives
      and is honored; absent it, default `"response"`).

## Inputs

- `the_one/llm/_request_params.py` (L01) — `resolve_*` + `_coerce_*`. Confirmed
  canonical `response_format` returns `{"type":"json_object"}` or a passed-through
  `{"type":"json_schema","schema":{...}}` (possibly with extra keys like `name`).
- `the_one/llm/openai_provider.py`:
  - `__init__` (`:46-65`) — reads no config today; `**kwargs` receives `config`.
  - `complete` inline kwargs (`:99-104`) and `stream` inline kwargs (`:151-158`) —
    the two request-assembly sites; both build a `kwargs` dict then call
    `self.client.chat.completions.create(**kwargs)`. Add the A4 merge after the
    `if tools:` block at each.
- `the_one/llm/openrouter_provider.py`:
  - `__init__` (`:85-138`) — explicit `config: dict | None = None` param, currently
    unused; call `self._read_a4_config(config)` here.
  - overrides neither `complete` nor `stream` (inherits both).
- Tests: no `tests/test_openai_provider.py` exists — OpenAI's request path is
  covered by the scripted-transport conformance suite. `tests/fixtures/
  scripted_transport.py` provides `make_openai` / `make_openrouter` (httpx
  `MockTransport`, exposes captured `request_bodies`) — the config→wire tool.
  `tests/test_openrouter_provider.py` holds the parity test (`:272`) and
  `test_config_kwarg_is_ignored` (`:257`).

## Outputs

- `the_one/llm/openai_provider.py` — `_read_a4_config` + `_a4_request_kwargs`
  helpers; `__init__` calls the former; `complete`/`stream` merge the latter.
- `the_one/llm/openrouter_provider.py` — `__init__` calls `_read_a4_config(config)`.
- `tests/test_openai_provider.py` — **NEW**: A4 `__init__` reads (OpenAI +
  OpenRouter), `_a4_request_kwargs` mapping incl. json_schema re-wrap, config→wire
  integration, None-path.
- (Possibly a small OpenRouter-reads-A4-config test added to
  `tests/test_openrouter_provider.py` next to the parity test — implementer's
  choice of file, but OpenRouter's config→attr read MUST be tested per DD5.)

## Acceptance Criteria

- [x] **`_read_a4_config(self, config)` helper** on `OpenAIProvider` sets
      `self._reasoning_effort_config` / `self._response_format_config` /
      `self._stop_config` from `config` via the L01 `_coerce_*` helpers
      (canonical-or-`None`, never raising on absent/non-dict/junk).
- [x] **`OpenAIProvider.__init__` calls `_read_a4_config(kwargs.get("config"))`** —
      OpenAI now reads the A4 config keys (it read none before).
- [x] **`OpenRouterProvider.__init__` calls `_read_a4_config(config)`** using its
      own explicit `config=` param — the three attrs are set on OpenRouter too.
- [x] **Instance-attribute parity preserved**:
      `test_subclass_has_all_parent_instance_attrs` (`:272`) still passes (both
      constructors set the identical three attrs).
- [x] **`_a4_request_kwargs(self) -> dict` helper** returns the A4 additions:
      `stop` (from `resolve_stop`), `reasoning_effort` (from
      `resolve_reasoning_effort`), and `response_format` — with json_object →
      `{"type":"json_object"}` and json_schema → the OpenAI wrapper
      `{"type":"json_schema","json_schema":{"name":<rf.name or "response">,
      "schema":{...}}}`. Returns `{}` when nothing is configured.
- [x] **Both request sites merge it**: `complete` and `stream` both do
      `kwargs.update(self._a4_request_kwargs())` (after the `if tools:` block,
      before `create(**kwargs)`), so the params reach the wire on both paths.
- [x] **OpenRouter inherits the request wiring** (no `complete`/`stream` override):
      a config→wire test constructs `OpenRouterProvider(config={...})`, drives a
      request through an injected `httpx.MockTransport`, and asserts the request
      body carries `reasoning_effort` / `response_format` / `stop` — **config→wire,
      not attribute-existence alone** (DD5). Exercised on **both** `complete` and
      `stream` (both are inherited from OpenAI).
- [x] **config→wire for OpenAI**: an analogous test asserts an OpenAI request body
      carries the three params when configured, on **both** `complete` and `stream`
      paths (parametrize or duplicate — the merge is at two sites, so both must be
      wire-proven, not just diff-read).
- [x] **json_schema re-wrap verified**: a test asserts canonical
      `{"type":"json_schema","schema":{...}}` becomes the OpenAI-wrapped shape with
      a `name`, and that a caller-supplied `name` is honored.
- [x] **None-path**: with no A4 config and the three env vars unset
      (`monkeypatch.delenv(..., raising=False)`), `_a4_request_kwargs()` is `{}` and
      neither request site adds `reasoning_effort`/`response_format`/`stop`.
- [x] **No ABC/signature change**; nothing new exported from
      `the_one/llm/__init__.py`.
- [x] Targeted tests green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
      tests/test_openai_provider.py tests/test_openrouter_provider.py
      tests/test_llm_provider_cross_provider_conformance.py -x --timeout 30`.

## Verification Steps

- Run the three test files above — all green, including new A4 tests and the
  unchanged parity + config_kwarg_is_ignored tests.
- Read the `complete`/`stream` diffs — confirm the A4 merge sits after `if tools:`
  and before `create(**kwargs)` at both sites, identically.
- `git diff --stat` — only `openai_provider.py`, `openrouter_provider.py`, the new
  `tests/test_openai_provider.py` (+ maybe `tests/test_openrouter_provider.py`) and
  flight artifacts changed.

## Implementation Guidance

1. **Import the resolvers/coercers** at the top of `openai_provider.py`
   (`from the_one.llm._request_params import resolve_reasoning_effort,
   resolve_response_format, resolve_stop, _coerce_effort, _coerce_response_format,
   _coerce_stop`).

2. **`_read_a4_config` on `OpenAIProvider`**:
   ```python
   def _read_a4_config(self, config: Any) -> None:
       """Read the A4 request params (reasoning_effort / response_format / stop)
       from the free-form provider ``config`` into canonical-or-None instance
       attrs. Called from BOTH OpenAIProvider.__init__ and (because it skips
       super().__init__) OpenRouterProvider.__init__ — keeps the instance-attr
       parity contract (test_subclass_has_all_parent_instance_attrs) satisfied."""
       _cfg = config if isinstance(config, dict) else {}
       self._reasoning_effort_config = _coerce_effort(_cfg.get("reasoning_effort"))
       self._response_format_config = _coerce_response_format(_cfg.get("response_format"))
       self._stop_config = _coerce_stop(_cfg.get("stop"))
   ```
   Call `self._read_a4_config(kwargs.get("config"))` at the end of
   `OpenAIProvider.__init__`.

3. **`_a4_request_kwargs` on `OpenAIProvider`**:
   ```python
   def _a4_request_kwargs(self) -> dict[str, Any]:
       out: dict[str, Any] = {}
       stop = resolve_stop(self._stop_config)
       if stop:
           out["stop"] = stop
       effort = resolve_reasoning_effort(self._reasoning_effort_config)
       if effort:
           out["reasoning_effort"] = effort
       rf = resolve_response_format(self._response_format_config)
       if rf:
           if rf.get("type") == "json_object":
               out["response_format"] = {"type": "json_object"}
           elif rf.get("type") == "json_schema" and rf.get("schema") is not None:
               out["response_format"] = {
                   "type": "json_schema",
                   "json_schema": {"name": rf.get("name") or "response", "schema": rf["schema"]},
               }
       return out
   ```
   In `complete` and `stream`, after the `if tools:` block:
   `kwargs.update(self._a4_request_kwargs())`.

4. **`OpenRouterProvider.__init__`**: add `self._read_a4_config(config)` (its
   explicit `config` param) — place it alongside the other attr-setting, e.g. just
   before or after `self._init_provider_state()`. Do NOT call `super().__init__()`
   (the no-leak invariant forbids it) — call the helper directly. **Also update the
   now-stale inline comment on the `config` param** (`openrouter_provider.py:90`,
   currently `# accepted for factory uniformity; unused`) — `config` IS now used
   (for the A4 keys), just not for `referer`/`title`; reword to reflect that.

5. **Tests** — new `tests/test_openai_provider.py`:
   - `__init__` reads: `OpenAIProvider(model="gpt-4o", api_key="x",
     config={...})` sets the three attrs; absent/None/non-dict/junk → all `None`.
     Same for `OpenRouterProvider(model="m", api_key="x", config={...})`.
   - `_a4_request_kwargs` mapping: construct with each config, assert the returned
     dict — including json_object → `{"type":"json_object"}`, json_schema →
     wrapped-with-name, caller `name` honored, empty → `{}`.
   - config→wire (OpenAI): **`make_openai`/`make_openrouter` accept NO `config`
     kwarg** (confirmed) — so construct the provider directly with A4 `config` and
     inject an `httpx.MockTransport` into `prov.client` (the exact pattern
     `make_openai` uses internally, ~`scripted_transport.py:300-307`:
     replace `prov.client` with `AsyncOpenAI(..., http_client=httpx.AsyncClient(
     transport=httpx.MockTransport(handler)))`, handler recording the request body).
     Drive both `complete()` and `stream()`; assert the captured body carries
     `reasoning_effort` / `response_format` / `stop`. Do NOT expand the shared
     harness here (that's L05).
   - config→wire (OpenRouter): same direct-transport approach — the DD5 config→wire
     assertion (not attribute-existence), both `complete` and `stream`.
   - None-path: env delenv'd, no config → `_a4_request_kwargs() == {}` and request
     body has none of the three keys.

## Edge Cases

- **`test_config_kwarg_is_ignored` (`:257`) stays valid — do NOT invert it.** It
  pins that the OpenRouter `referer`/`title` config keys remain ignored (a no-leak
  invariant on the hardcoded app-identity headers) — a *different* config namespace
  than the A4 keys. Reading `reasoning_effort`/`response_format`/`stop` does not
  touch `referer`/`title`. Confirm the test still passes unchanged; if its
  class/docstring framing ("config kwarg is ignored") now reads as over-broad, a
  one-line clarifying comment is fine, but no behavior change.
- **OpenAI reasoning models reject `stop`/`temperature`/`max_tokens`** (doc-gate:
  `stop` unsupported on o3/o4-mini): sending a configured `stop` to such a model
  400s at request time. **Not caught this flight** (per-route/param gating is
  backlog B4). OpenAI's `complete`/`stream` have **no** temperature-retry (only
  Anthropic does), so there's no retry path to preserve — nothing to test there.
- **json_schema missing `schema`**: guarded by `rf.get("schema") is not None`
  (belt-and-suspenders; L01 guarantees a `schema` for the json_schema canonical
  value) — a malformed value skips `response_format` rather than sending an invalid
  wrapper.
- **Empty-dict schema**: forwarded as-is inside the wrapper (valid, matches-any) —
  same disposition as L02.

## Files Affected

- `the_one/llm/openai_provider.py` — `_read_a4_config` + `_a4_request_kwargs`
  helpers; `__init__` + both request sites wired.
- `the_one/llm/openrouter_provider.py` — `__init__` calls `_read_a4_config(config)`.
- `tests/test_openai_provider.py` — **NEW** A4 test module.
- (optional) `tests/test_openrouter_provider.py` — OpenRouter A4 config-read test.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (openai + openrouter + conformance)
- [ ] Update flight-log.md with a Leg Progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] (Not final leg — no flight/mission status change)
- [ ] Changes stay uncommitted — batch commit after L06 (do NOT commit at leg end)
