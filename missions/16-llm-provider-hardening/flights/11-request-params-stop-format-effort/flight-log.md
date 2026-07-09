# Flight Log: Request-Param Capabilities — reasoning_effort, structured outputs, stop (A4)

**Flight**: [Request-Param Capabilities (A4)](flight.md)

## Summary

Planning. Flight scoped to backlog **A4** (reasoning_effort / structured outputs /
stop) via the provider **config surface** (config → env → default), provider-native
structured-output pass-through, with a guided live HAT. Split from A2 (following
flight) per operator decision 2026-07-06. Not yet in-flight.

---

## Leg Progress

**L01 — wire-format-premise-and-resolvers (2026-07-06).** Doc-gate premise recorded
(see `## Wire-Format Premise` below): pinned accepted request shapes + per-model
defaults for `reasoning_effort` / `response_format` / `stop` across Anthropic,
OpenAI, and Ollama (`/v1` + native), sourced from the pinned SDK stubs
(anthropic 0.97.0, openai 2.33.0) and first-party docs. Effort×adaptive-thinking
composition resolved from cited Anthropic docs (they compose; not HAT-confirm).
Divert-check: no param requires a genuinely divergent canonical shape — Anthropic's
lack of bare JSON mode is a documented no-op (Acceptable-variations bucket per
flight DD2/L01 criteria), not a Divert-if trigger. Landed
`the_one/llm/_request_params.py` (`resolve_reasoning_effort`,
`resolve_response_format`, `resolve_stop` + `_coerce_effort`/
`_coerce_response_format`/`_coerce_stop`, mirroring
`resolve_extended_thinking`/`_coerce_bool` and `effective_num_ctx`/
`_coerce_num_ctx`) and `tests/test_request_params.py` (config-wins, env-fallback,
default-unset, junk/bool→None, valid-JSON-wrong-shape, valid-JSON-right-shape for
all three resolvers). No provider request path touched; resolvers not exported
from `the_one/llm/__init__.py` (wiring is L02–L04). `PYTHON=.venv/bin/python bash
scripts/run-tests.sh tests/test_request_params.py -x --timeout 30` green.

**L02 — anthropic-request-params (2026-07-06).** Wired the three A4 params into
`AnthropicProvider`: `__init__` coerces `reasoning_effort`/`response_format`/`stop`
from `config` via the L01 `_coerce_*` helpers into
`_reasoning_effort_config`/`_response_format_config`/`_stop_config` (canonical-or-
`None`, mirroring the existing `_thinking_enabled_config` read); `_build_kwargs`
resolves each via `resolve_*` and emits, just before `return kwargs`:
`kwargs["stop_sequences"]` (list[str], omitted when empty) and a single
`output_config` dict carrying `effort` and/or `format` (json_schema-only —
canonical `json_object` is a no-op + `logger.warning`, per the Wire-Format
Premise), never sent empty. `output_config.effort` composes alongside the existing
`kwargs["thinking"]` adaptive block (independent top-level params, verified in a
coexistence test) — neither clobbers the other. No ABC/signature change; nothing
new exported from `the_one/llm/__init__.py`.

Added an A4 test block to `tests/test_anthropic_provider.py` (13 new tests): init-
attr reads (present + absent/None/non-dict/junk → `None` for all three) mirroring
`test_init_reads_thinking_enabled_from_config`; direct-`_build_kwargs` wiring for
`stop_sequences`, `output_config.effort`, `output_config.format` (json_schema),
using `Message.user("hi")` (the
`test_llm_provider_cross_provider_conformance.py:499` direct-call idiom, not the
file's usual `complete()`+`_CreateRecorder` style); `json_object` no-op verified
via `caplog.at_level(..., logger=_LOGGER_NAME)`; `output_config` omitted-when-empty;
thinking+effort coexistence; a `None`-path test with the three A4 env vars
delenv'd; and the temperature-retry-preserves-A4-kwargs test using the
`_CreateRecorder(side_effects=[...])` recorder idiom (`:253-345`) with
`config={"stop": ["</s>"], "reasoning_effort": "high"}`, asserting the **retried**
call still carries `stop_sequences` and `output_config` (only `temperature`
popped).

`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_anthropic_provider.py
-x --timeout 30` — 63 passed. `tests/test_request_params.py` (41) and
`tests/test_llm_provider_cross_provider_conformance.py` (32) re-run clean — no
regression from the new import. `ruff check`/`ruff format --check` clean on both
touched files. `git diff --stat` scoped to `the_one/llm/anthropic_provider.py` +
`tests/test_anthropic_provider.py` (plus flight/leg artifacts and L01's
already-landed, still-uncommitted `_request_params.py` +
`tests/test_request_params.py`).

Edge cases (per leg, not resolved this leg — recorded, not gaps): unsupported
effort value for a given model 400s at request time (per-model capability gating
is backlog B4, out of scope); an `output_config` 400 isn't caught by the existing
temperature-only retry and re-raises (acceptable — no graceful-degradation scope
this flight); an empty-schema `{"type":"json_schema","schema":{}}` passes the
`is not None` guard and forwards as-is (valid, matches-anything JSON Schema, not a
gap).

**L04 — ollama-request-params (2026-07-06).** Wired the three A4 params into
`OllamaProvider` across **both** wire dialects. `__init__` reads
`reasoning_effort`/`response_format`/`stop` from `config` via the L01 `_coerce_*`
helpers into `_reasoning_effort_config`/`_response_format_config`/`_stop_config`
(canonical-or-`None`), placed next to the existing `_configured_num_ctx` read.

`/v1` (OpenAI-compat) path: a new private `_v1_a4_kwargs(self) -> dict[str, Any]`
produces the same mapping as `OpenAIProvider._a4_request_kwargs` (`stop`->`stop`,
effort->`reasoning_effort`, json_object passthrough, json_schema re-wrapped with a
synthesized/caller `name`). Merged via `payload.update(self._v1_a4_kwargs())`
(`complete`) and `body.update(self._v1_a4_kwargs())` (`stream`), both right after
their `if tools:` block. Per the leg's DRY decision, this stays a local
duplicate of L03's mapping (copy #2, not rule-of-three) — a forward-note code
comment on `_v1_a4_kwargs` names the rule-of-three trigger (`_request_params.py
::to_openai_compat_a4`) for a future third `/v1`-style provider.

Native `/api/chat` path: `_native_options` adds `options["stop"]` (from
`resolve_stop`) alongside the existing `num_ctx` logic; `_native_body` adds
body-level `think` (from `resolve_reasoning_effort`) and body-level `format`
(`"json"` for canonical `json_object`, or the **bare** `rf["schema"]` object for
canonical `json_schema` — no wrapper, unlike `/v1`). Confirmed via the
`ollama_api.chat_native`/`chat_stream_native` review that both native call sites
spread the whole body (`{**body, ...}`) with no allow-listing, so `think`/
`format`/`options.stop` reach the wire untouched. `think` was genuinely unused
before this leg (F10 left `enable_thinking` accept-and-ignore on this provider),
so there is no collision with any existing thinking wiring.

New `tests/test_ollama_provider_a4_request_params.py` (25 tests): `__init__` reads
(present + absent/None/non-dict/junk -> `None`, mirroring
`test_anthropic_provider.py:test_init_reads_a4_config`); `_v1_a4_kwargs()` unit
tests for all shapes (stop/effort passthrough, json_object direct, json_schema
synthesized-name + caller-name, all-three-together, empty -> `{}`); native mapping
via direct `_native_body`/`_native_options` calls (`think`, both `format`
variants, `options["stop"]`, each present/absent per config, plus an explicit
no-`/v1`-key-leakage assertion on the native body); `/v1` config->wire tests on
BOTH `complete()` and `stream()` using the `httpx.AsyncClient.__init__`
monkeypatch-to-inject-`MockTransport` idiom from `test_ollama_provider_auth.py`
(Ollama has no injectable `http_client`, unlike L03's OpenAI approach) — asserting
the wire body carries `stop`/`reasoning_effort`/`response_format` and none of
`think`/`format`; a None-path test (env delenv'd, no config) confirming
`_v1_a4_kwargs() == {}` and the wire body carries none of the three keys.

`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ollama_native_provider.py
tests/test_ollama_provider_auth.py tests/test_ollama_provider_recovery.py
tests/test_llm_provider_cross_provider_conformance.py tests/test_request_params.py
tests/test_ollama_provider_a4_request_params.py -x --timeout 30` — 131 passed (no
regression from the new import/wiring). `ruff check`/`ruff format --check` clean on
`ollama_provider.py` + the new test file. `git diff --stat` scoped to
`the_one/llm/ollama_provider.py` (plus the new untracked test file, flight/leg
artifacts, and the prior legs' already-landed, still-uncommitted files —
batch-commit model). No ABC/signature change; nothing new exported from
`the_one/llm/__init__.py`; the conformance-suite harness (L05 scope) untouched.

Two **HAT-confirm carry items for L07** (per the leg's doc-gate — not resolved
this leg, hermetic tests assert emitted wire shape only, not model acceptance):
(1) the exact `/v1` `reasoning_effort`->native-`think` translation (accepted-value
set and the effort-string->`think`-level mapping Ollama performs internally) is
not pinned by docs at the granularity needed — live-verify against the target
Ollama model/build; (2) `/v1` **json_schema-wrapper support** — the doc-gate
pinned json_object/OpenAI-compat `response_format` on `/v1` but not whether the
target Ollama build accepts the `{"type":"json_schema","json_schema":{...}}`
wrapper on that endpoint (if rejected, it 400s; native `format` with a bare schema
remains the reliable structured-output route for Ollama regardless of this
outcome).

Edge cases recorded, not resolved this leg (per leg's Edge Cases section): a
non-reasoning native model silently ignores `think` (not an error — the runner
just drops an unrecognized field); an effort value outside the native `think`
set (e.g. canonical `minimal`/`xhigh` from an OpenAI-oriented config) is emitted
to `think` as-is and Ollama rejects unknown values with a 400 (the canonical
layer does not validate per-provider, matching L02/L03's disposition); an
empty-dict schema (`{"type":"json_schema","schema":{}}`) forwards as-is on both
paths (`format: {}` native / wrapped `/v1`) — same benign disposition as L02/L03.

**L05 — conformance-matrix-extension (2026-07-06).** Test-only leg (no production
code touched — verified `git diff` for this leg is `tests/fixtures/scripted_transport.py`
+ `tests/test_llm_provider_cross_provider_conformance.py`). Extended the harness:
all four request-capable factories (`make_anthropic`/`make_openai`/`make_openrouter`/
`make_ollama`) now accept `config=`; the sent request is exposed uniformly on
`ScriptedProvider.request_bodies` (Anthropic = the recorder's `create`/`stream`
kwargs; OpenAI/OpenRouter/Ollama = parsed JSON body). The **[high]** design-review
finding landed correctly: Ollama capture is **path-filtered to `/chat/completions`**
so the `/api/show` context/capability POSTs never pollute `request_bodies`
(index 0 is unambiguously the A4-bearing request — asserted via a
`_chat_completions_body` helper, not blind indexing). Added the A4 config→wire
matrix: one shared `A4_CONFIG` (`reasoning_effort:"high"`, json_schema
`response_format`, `stop:["</s>"]`); the OpenAI-compat providers (openai,
**openrouter**, ollama-/v1) parametrized against the shared wrapper shape on both
`complete()` and `stream()`; a dedicated Anthropic assertion (`output_config` +
`stop_sequences`) on both paths. **DD5 satisfied**: OpenRouter is in the matrix
with a config→wire assertion (the request body carries the params), not
attribute-existence alone. Mock documented N/A (no request path); the json_object
per-provider variance is deliberately left to the L02–L04 unit tests (noted in the
suite). Conformance suite **40 passed** (was 32 → 8 new A4 tests). Full regression
`make test-unit` (run by the Flight Director) **3891 passed, 10 skipped, exit 0** —
no regression from the harness change touching every provider's round-trip factory.
Uncommitted (batch model). *(Finalized by the Flight Director: the implementing
agent completed the code + conformance run + lint but paused mid-finalization on a
long `make test-unit` wait; FD independently ran the full regression green and wrote
this entry / set the leg `landed`.)*

**2026-07-06 — L06 designed + design-reviewed (Developer/Sonnet: approve with
changes) → `ready`.** Last autonomous leg (DD6): a minimal `reasoning_effort`
`<select>` in the Studio provider-config editor (`config.reasoning_effort`),
mirroring the `num_ctx`/`thinking_enabled` config-dict field pattern; options
`Provider default`(`""`)/`low`/`medium`/`high`; always-persist (`""` → `None`
server-side). Review confirmed the **highest-risk assumption**: no production
Python / schema change is needed — `LLMProviderConfig.config` is free-form and the
provider create/update endpoints (`api.py:3978-4035`) pass the whole config dict
through with no key allow-listing, so `config.reasoning_effort` round-trips on the
existing path (and the provider `__init__`s already read it, L02–L04). Folded
changes: **[medium]** use the light `Path.read_text()` source-scan idiom
(`tests/_ui_guard_helpers.py` / `test_ui_guards.py`) for the hermetic test, not the
FastAPI-app/`AsyncClient` machinery of `test_tools_admin_editor_assets.py`;
**[low]** **include `openai-compatible`** in `showReasoningEffort` — `factory.py`
maps it to the same `OllamaProvider` reasoning_effort path as `ollama`, so
excluding it would be an avoidable UI gap. Single cycle → no second cycle.
Proceeding to implementation. Behavioral round-trip through a live browser is the
L07 HAT, not this leg.

**L06 — admin-reasoning-effort-field, IMPLEMENTED + landed (2026-07-06).** UI-only,
**no production Python / schema change** (diff = `admin.js` + `provider-editor.js` +
the new test only). Added a `Reasoning Effort` `<select>`
(`data-field="config.reasoning_effort"`, id `pf-reasoning-effort`, marker
`admin-pf-reasoning-effort`) to the Studio provider-config editor, mirroring the
`num_ctx`/`thinking_enabled` config-dict field pattern (`.field-group` + label +
info-icon + `aria-describedby`); options `Provider default`(`""`)/`low`/`medium`/
`high`, pre-selected from `provider.config.reasoning_effort`; a `reasoningEffortRow`
type-change toggle; an always-persist save block (`""` → `None` server-side via
`_coerce_effort`). `TYPE_DEFAULTS` (`admin.js`) gained `showReasoningEffort: true`
on all five reasoning-capable types — anthropic, openai, openrouter, ollama, **and
openai-compatible** (shares OllamaProvider's reasoning_effort path per `factory.py`);
`mock` untouched. New `tests/test_admin_reasoning_effort_field.py` (4 tests, the
`Path.read_text()` source-scan idiom per `test_ui_guards.py`) asserts the field
markup + options + the `showReasoningEffort` flags across the five types. Targeted
run **18 passed** (new file 4 + `test_ui_guards.py` 14); full `make test-unit`
regression run by the FD as the Phase-2d pre-commit gate. Uncommitted (batch model).
*(Finalized by the Flight Director — implementing agent stood down mid-`make
test-unit`; FD confirmed targeted green and owns the flight-log/status/commit-gate.)*

**2026-07-06 — Phase-2d batch code review fix: provider-editor config-wipe
(BLOCKING).** The Phase-2d batch review of L02–L06 flagged one blocking issue in
the Studio provider editor (`provider-editor.js`, `collectFormData`): the
save-payload builder constructed `payload = {name, type, base_url, api_key}`
with no `config` key, then only ever *set* `payload.config` inside
type-specific blocks (openrouter referer/title — building a **fresh** `cfg`
object; `showNumCtx`/`showThinkingEnabled`/L06's new `showReasoningEffort` —
each doing `payload.config = payload.config || {}` then setting one key). The
backend `update_provider` (`api.py:~4022`) does
`existing.model_copy(update=data)` — a field-level **replace**, not a deep
merge — so whatever `config` object the UI sends becomes the entire stored
config. Any config key the UI does not render — critically `response_format`
and `stop`, settable only via config/env per DD6 (no UI field this flight) —
would be silently wiped on the next Save. L06 newly made `openai`/`openai-
compatible` always send `config` (they gained `showReasoningEffort`),
**introducing** the regression for those two types; anthropic/ollama/
openrouter already always sent config (had the same latent wipe) and are
fixed by the same change.

**Fix**: seed `payload.config` at the top of `collectFormData`, before any
field-specific block, from a shallow clone of the existing provider config —
`(isEdit && provider && provider.config) ? Object.assign({}, provider.config) : {}`
(ES5-consistent `Object.assign` shallow-clone idiom, precedented in
`areas/studio/connector-editor.js:3783`). `collectFormData` gained a `provider`
parameter (passed from its one call site, which already has `provider` in
closure scope) since it previously had no access to the provider object. The
openrouter branch now **overlays** onto the seeded config (`payload.config.referer
= ...` / `delete payload.config.referer` else-branch) instead of replacing it
with a fresh `cfg`; the num_ctx/thinking_enabled/reasoning_effort blocks were
already additive (`payload.config = payload.config || {}` then one key) and
needed no change — with the seed in place they now correctly overlay onto
preserved keys instead of an empty object. The openrouter no-leak invariant
(`HTTP-Referer`/`X-Title` hardcoded server-side to `_APP_URL`/`_APP_NAME`,
`openrouter_provider.py:115-116`) is untouched — the branch only manages the
optional `config.referer`/`config.title` ranking-header keys, never the
hardcoded headers themselves.

Added `test_provider_editor_seeds_config_from_existing_provider_before_field_blocks`
to `tests/test_admin_reasoning_effort_field.py` (source-scan idiom, matching
the file's existing `Path.read_text()` guards): asserts the seed line is
present, uses `Object.assign` (not aliasing), appears before all four
field-specific blocks in source order, and that the openrouter block overlays
(`payload.config.referer`/`.title` set/delete) rather than replacing
(`payload.config = cfg` absent). This is a **weak, source-level guard only**
(no JS unit runner exists in this repo) — it proves the shape of the fix, not
the runtime behavior. **The actual save-preserves-out-of-band-config property
(a Save round-trip that leaves an operator-set `response_format`/`stop`
untouched) is unverified by any automated test and is recorded here as a
checkpoint for the L07 HAT.**

`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_admin_reasoning_effort_field.py
tests/test_ui_guards.py -x --timeout 30` — 19 passed. `ruff check`/`ruff format
--check` clean on the touched test file (JS has no ruff/linter in this repo).
`git diff --stat` for this fix scoped to `provider-editor.js` +
`tests/test_admin_reasoning_effort_field.py` (the rest of the working tree's
diff is the prior legs' already-landed, still-uncommitted files — batch-commit
model, untouched by this fix). Uncommitted.

---

## Decisions

### Split A4 from A2; A4 first
**Context**: Operator asked to design "the next flight with A2/A4." The blast-radius
recon showed the pair is ~9–13 legs (oversized), the two are independent surfaces
(request params vs `Message.content` shape), and A2 has no in-scope ingestion path to
drive vision live.
**Decision**: Split. Design A4 first (request-side, live-verifiable, continues the A1
thinking work); A2 becomes the following flight, paired with an ingestion decision.
**Impact**: This flight is A4-only. Mission criterion #3 is advanced, not closed, here.

### A4 via config surface, not the ABC
**Context**: F10 added `enable_thinking` to the ABC and paid a 46-failure cascade
across ~13 hand-rolled test doubles (none use `**kwargs`). F10 Rec 6 recommends
config-surface for tuning knobs.
**Decision**: Resolve all three A4 params from `LLMProviderConfig.config` via
`resolve_*` helpers (config → env → default), mirroring `resolve_extended_thinking` /
`effective_num_ctx`. ABC signature unchanged.
**Impact**: No test-double cascade. Params are provider/session-scoped defaults, not
per-call (per-call plumbing is a future extension — see flight DD1).

### Structured outputs = provider-native pass-through
**Context**: Operator chose pass-through over full schema-validated (2026-07-06).
**Decision**: Map a canonical `response_format` to each provider's native surface; no
client-side JSON validation/repair this flight.
**Impact**: Deferral recorded below; malformed/off-schema JSON is unguarded except by
the provider's own strict mode.

---

## Deviations

_(none yet)_

---

## Anomalies

_(none yet)_

---

## Reconnaissance Report

Blast-radius recon (2026-07-06) against `the_one/llm/` at mission-16 HEAD. Source
items are the A4 sub-capabilities from the Flight 1B audit backlog; all classified
**confirmed-live** (A4 is unimplemented). Cited sites for the wiring legs:

| Item | Classification | Evidence | Note |
|------|---------------|----------|------|
| A4 `reasoning_effort` | confirmed-live | `anthropic_provider.py:66,219` carry explicit "deferred to A4" effort hooks; no effort in any request path | Anthropic hook pre-carved |
| A4 `response_format` | confirmed-live | no `response_format` in any provider request build | needs per-provider mapping (Leg 01 doc-gate) |
| A4 `stop` | confirmed-live | no `stop`/`stop_sequences` in any request build | trivial per-provider map |
| Config surface home | available | `LLMProviderConfig.config` free-form dict (`db/models.py:29`); resolvers `resolve_extended_thinking` (`anthropic_provider.py:92`), `effective_num_ctx` (`ollama_provider.py:85`) | A4 resolvers copy this |
| ABC signature (avoid) | n/a — dodged by DD1 | `complete`/`stream` `base.py:344/365`; base default `stream` forwards to `complete` `:383-385`; ~13 test doubles hand-roll signatures, none `**kwargs` | config-surface avoids touching these |
| Request-kwargs sites | confirmed-live | Anthropic `_build_kwargs` `anthropic_provider.py:163`; OpenAI inline `openai_provider.py:99-106` + `:151-160`; Ollama `/v1` `ollama_provider.py:248-256` + `:338-346`, native `_native_body`/`_native_options` `:440`/`:432`; Mock synthesizes (no request path) | wiring targets for L02–04 |
| OpenRouter inheritance | confirmed | `OpenRouterProvider` overrides neither `complete` nor `stream` (`openrouter_provider.py:60`) | inherits OpenAI A4 wiring free (DD5) |
| Conformance suite | confirmed | `tests/test_llm_provider_cross_provider_conformance.py`; `PROVIDER_FACTORIES` `:97-102` = anthropic/openai/ollama/mock (**OpenRouter absent**) | L05 adds A4 rows + OpenRouter to A4 matrix |
| Admin config field precedent | confirmed | `num_ctx` (F9) + thinking toggle (F10) fields in provider editor | L05 adds minimal `reasoning_effort` field (DD6) |

Full map: launched during flight planning (see planning session). No source item
was retired; A4 is greenfield capability work.

---

## Session Notes

**2026-07-06 — Flight planned.** Scoped from mission criterion #3 + the Flight 1B
backlog (A4). Split from A2 (operator). Config-surface + provider-native pass-through
+ guided HAT (operator, 4 decisions). Wire-format doc-gate (F10 Rec 1) set as Leg 01
/ DD4.

**2026-07-06 — Phase-5b design review incorporated (Architect: approve with changes).**
Verified against the codebase + pinned SDKs. Key confirmations: DD1 holds — no A4
param needs to be per-call (agent loop `agent/core.py:399` passes only
messages+tools; the one per-call kwarg consumer, the inference classifier
`connectors/_inference.py:325`, is a plain-text yes/no probe needing no
`response_format`). **SDK pre-check (de-risks the doc-gate):** repo runs
**anthropic 0.97.0** + **openai 2.33.0**; anthropic already exposes
`output_config.effort` (`Literal[low..max]`), `output_config.format`
(`{type:json_schema, schema}` — **native, not tool-based**), and `stop_sequences`;
OpenAI exposes `reasoning_effort` + `response_format`. So all three A4 params map to
native surfaces on both — Leg 01's job narrows to per-model *acceptance* + defaults,
and the "structured output is tool-based → divert" trigger is unlikely to fire.
Changes folded in: (1) **[medium]** DD5 reworked — OpenRouter inherits OpenAI's
*request methods* free but NOT config reading; both `OpenAIProvider.__init__` (reads
no config today) and `OpenRouterProvider.__init__` (skips `super().__init__()`,
ignores `config`) must be wired to read the A4 keys → explicit in Leg 03; conformance
asserts config→wire, not attribute-existence. (2) **[low]** Added the Anthropic
`output_config.effort` × adaptive-thinking composition question to the Leg 01
doc-gate. (3) Split the Studio admin field out of the old L05 into its own leg (L06);
conformance-matrix extension is now hermetic/test-only L05; HAT is L07. Open item for
the walk-through: DD6 admin field this flight vs config/env-only (mission "no web UI
beyond thinking" fence — droppable, now isolated in L06). Awaiting crew walk-through.

**2026-07-06 — Operator sign-off; flight → `ready`.** Spec approved as presented
(DD6 admin field kept as L06). Flight checked off in mission.md. Next step:
per-leg design + implementation via `/agentic-workflow` (Leg 01 doc-gate first).
Not started.

---

### Flight Director Notes

**2026-07-06 — Flight started via `/agentic-workflow`; → `in-flight`.** Loaded
mission, flight spec, flight log, ARTIFACTS.md, and `leg-execution.md` crew
(Developer=Sonnet, Reviewer=Haiku; branch strategy). Feature branch
`flight/11-request-params-stop-format-effort` cut from `main` (carries the
uncommitted planning artifacts). 7 legs planned; per-leg design review, then
batch code-review + single commit after the last autonomous leg (L02–L06);
L07 HAT is operator-guided. Beginning Leg 01 design (`/leg`).

**2026-07-06 — L01 designed + design-reviewed (Developer/Sonnet: approve with
changes) → `ready`.** Leg scope: doc-gate premise + canonical
`resolve_reasoning_effort`/`resolve_response_format`/`resolve_stop` in a new shared
`the_one/llm/_request_params.py` + unit tests; no provider wiring. Review
confirmed module placement, mirrored resolver/test references, and clean
`stop`/`reasoning_effort` canonical mappings (spot-checked the pinned SDK stubs:
OpenAI `reasoning_effort` `Literal[none,minimal,low,medium,high,xhigh]`, Anthropic
`effort` `Literal[low,medium,high,xhigh,max]` — correctly left unvalidated at the
canonical layer). Changes folded in: **(medium)** anthropic 0.97.0
`output_config.format` is `json_schema`-**only** (no bare JSON mode, confirmed in
the installed `JSONOutputFormatParam` stub) → recorded as a doc-gate requirement
and an "Acceptable variation" no-op for Anthropic in L02 (NOT a divert trigger);
**(decision)** keep both canonical `json_object` and `json_schema` variants —
OpenAI/Ollama-`/v1` honor bare JSON, Anthropic no-ops it; **(decision)** coercion
lives in caller `__init__`, resolver coerces only the env read (binds all three,
matches both in-repo precedents); **(suggestion)** doc-gate resolves effort×adaptive
composition from cited first-party docs now (docs indicate they compose), HAT only
if unsettled; **(suggestion)** added explicit valid-JSON-wrong-shape + valid-JSON-
right-shape env test cases for the new JSON-decode path (no in-repo precedent).
Single review cycle; folded changes were clarifications + bound decisions, no
structural rewrite → no second cycle. `[HANDOFF:review-needed]` cleared;
proceeding to implementation.

**2026-07-06 — L01 implemented + landed (Developer/Sonnet).** 41 tests green
(`tests/test_request_params.py`); doc-gate `## Wire-Format Premise` recorded (all
three params × Anthropic/OpenAI/Ollama-`/v1`+native, cited to pinned-SDK stubs +
first-party docs). Effort×adaptive-thinking resolved (they compose — cited, not
HAT). No divert. Two HAT-confirm items flagged for L07: Ollama `/v1`
`reasoning_effort`→`think` translation + Ollama per-model effort/thinking defaults.
No provider path touched; resolvers unexported. Uncommitted (batch model).

**2026-07-06 — L02 designed + design-reviewed (Developer/Sonnet: approve with
changes) → `ready`.** Scope: wire effort/response_format/stop into Anthropic
`_build_kwargs` (native `output_config.effort` / `output_config.format` /
top-level `stop_sequences`); `json_object` no-ops+warns on Anthropic (json_schema-
only); effort added alongside the existing adaptive-thinking block (they compose).
Review verified every citation against live code + the pinned SDK. Folded changes:
**(medium)** added the temperature-retry-preserves-A4-kwargs test the criterion
demanded (recorder idiom, `:253-345`); **(low)** corrected the direct-`_build_kwargs`
precedent citation to `test_llm_provider_cross_provider_conformance.py:499` (the
file's own `:606+` tests go through `complete()`+`_CreateRecorder`, not a direct
call); **(low)** switched test message construction to the house `Message.user("hi")`
helper (no `Role` import); **(suggestion)** documented the empty-`{}`-schema pass-
through as intentional/harmless. Single cycle; changes were test-additions +
citation fixes, no design change → no second cycle. Proceeding to implementation.

**2026-07-06 — L02 implemented + landed (Developer/Sonnet).** 63 tests green in
`tests/test_anthropic_provider.py` (13 new A4 tests); `test_request_params.py` (41)
and the conformance suite (32) re-run clean. `_build_kwargs` emits `stop_sequences`
+ `output_config{effort,format}`; `json_object` no-ops+warns; effort composes with
the adaptive-thinking block; temperature-retry preserves A4 kwargs. Uncommitted.

**2026-07-06 — L03 designed + design-reviewed (Developer/Sonnet: approve with
changes) → `ready`.** Scope: OpenAI two request sites + config reads into BOTH
`OpenAIProvider.__init__` (read none before) and `OpenRouterProvider.__init__`
(skips super().__init__) via a shared `_read_a4_config` helper (satisfies the
`vars(parent)-vars(sub)` parity test); OpenRouter inherits `complete`/`stream` so
gets the wiring free. Native mapping: `stop`→`stop`, effort→`reasoning_effort`,
json_object→`{type:json_object}` (OpenAI DOES support bare JSON), json_schema→the
OpenAI wrapper `{type:json_schema,json_schema:{name,schema}}` with a synthesized
`name` (`rf.get("name") or "response"` — L01 passes a caller `name` through).
Review verified every citation against live code + pinned openai 2.33.0
(reasoning_effort/stop top-level; json_schema name Required; stop unsupported on
o3/o4-mini; no OpenAI temperature-retry). Confirmed `test_config_kwarg_is_ignored`
concerns referer/title (different namespace) → NOT inverted. Folded changes:
**(low)** config→wire tests must use direct-construction + injected
`httpx.MockTransport` (neither `make_openai`/`make_openrouter` accepts `config`);
**(low)** update the stale `openrouter_provider.py:90` "unused" comment;
**(suggestion→criterion)** wire-test BOTH `complete` and `stream` paths, not one.
Single cycle; changes were test-scoping + comment fixes → no second cycle.
Proceeding to implementation.

**2026-07-06 — L03 implemented + landed (Developer/Sonnet).** 121 tests green
(openai + openrouter + conformance + request_params); new `tests/test_openai_provider.py`
(25 tests). Both `__init__`s read A4 via shared `_read_a4_config`; parity + config-
ignored tests unchanged; `_a4_request_kwargs` maps to native OpenAI shapes
(json_schema re-wrapped with synthesized name); config→wire proven on both
complete+stream for both OpenAI and OpenRouter via injected MockTransport.
Uncommitted.

**2026-07-06 — L04 designed + design-reviewed (Developer/Sonnet: approve with
changes) → `ready`.** Scope: Ollama both paths. `/v1` (OpenAI-compat: `stop`,
`reasoning_effort`, `response_format` wrapper) merged at both `payload`/`body`
sites via a local `_v1_a4_kwargs` helper; native (`options.stop`, body-level
`think`=effort, body-level `format`="json"|bare-schema) in `_native_options` /
`_native_body`. Review confirmed the load-bearing fact: `ollama_api.chat_native`/
`chat_stream_native` spread the whole body (`{**body, ...}`) with no allow-listing,
so native `think`/`format`/`options.stop` reach the wire; `think` is genuinely
unused today (F10 accept-and-ignore) → no collision. Folded changes: **(low)**
corrected the DRY line-count (~17 not ~6) and **decided: keep local duplication**
(copy #2, not rule-of-three; L05 conformance catches drift; forward-note to lift to
`_request_params.to_openai_compat_a4` at rule-of-three); named the imports + the
`/v1` transport-mock idiom (`test_ollama_provider_auth.py`) + the init-read pattern
(`test_anthropic_provider.py:~1047`) explicitly. Two HAT-confirm carry items for
L07: `/v1` effort→`think` translation exactness, `/v1` json_schema-wrapper support.
Single cycle → no second cycle. Proceeding to implementation.

**2026-07-06 — L04 implemented + landed (Developer/Sonnet).** 131 tests green; new
`tests/test_ollama_provider_a4_request_params.py` (25 tests). Both paths wired:
`/v1` via `_v1_a4_kwargs` (local dup of L03 mapping + forward-note), native via
`_native_options` (`options.stop`) + `_native_body` (`think`, `format`="json"|bare-
schema). Confirmed whole-body spread reaches the wire; no `think` collision.
Uncommitted.

**2026-07-06 — L05 designed + design-reviewed (Developer/Sonnet: approve with
changes) → `ready`.** Test-only leg: extend the scripted-transport harness (add
`config=` to the four request-capable factories + uniform request capture) and add
an A4 config→wire matrix — OpenAI-compat providers (openai/openrouter/ollama-/v1)
parametrized against the shared wrapper shape, a dedicated Anthropic `output_config`
assertion, OpenRouter present (the DD5 config→wire assertion), Mock N/A. Review
confirmed all expected wire shapes are byte-for-byte correct against the landed
L02–L04 wiring, the harness scope is accurate (make_openai does NOT currently
capture bodies despite the docstring; Anthropic recorder.calls IS the sent kwargs).
Folded **[high]**: Ollama `complete()` POSTs `/api/show` before and (plain-text
turn) after `/chat/completions`, so blanket capture puts the A4 body at the wrong
index — capture MUST path-filter to `/chat/completions` (mirror the existing turn-
counter's `/api/show` special-case); noted the two distinct Ollama capture points
(complete=MockTransport handler w/ json.loads; stream=`fake_chat_stream(base_url,
body)` already-parsed). Folded **[low]**+suggestions: the two-mechanism split, the
`_capabilities_cache` nondeterminism note (clear-cache pattern), assert-on-body-not-
bare-index robustness. Single cycle; changes were guidance-precision fixes → no
second cycle. Proceeding to implementation.

**2026-07-06 — L03 implemented + landed (Developer/Sonnet).** Added
`_read_a4_config(self, config)` + `_a4_request_kwargs(self)` to `OpenAIProvider`;
`__init__` now calls `self._read_a4_config(kwargs.get("config"))` (previously read
no config). `_a4_request_kwargs` maps `stop`→`stop`, effort→`reasoning_effort`,
`response_format` json_object→`{"type":"json_object"}` direct, json_schema→the
OpenAI wrapper `{"type":"json_schema","json_schema":{"name": rf.get("name") or
"response", "schema": rf["schema"]}}`; returns `{}` when nothing configured. Both
`complete` and `stream` merge it via `kwargs.update(self._a4_request_kwargs())`
right after the `if tools:` block, before `create(**kwargs)`.
`OpenRouterProvider.__init__` (which skips `super().__init__()`) now calls
`self._read_a4_config(config)` directly using its own explicit `config=` param —
inherits the request wiring via `complete`/`stream` for free, satisfying the
`vars(parent)-vars(sub)` parity test
(`test_subclass_has_all_parent_instance_attrs`, `tests/test_openrouter_provider.py:272`)
without duplicating the merge logic. Reworded the stale `openrouter_provider.py:90`
inline comment (`config` is now used for the A4 keys, just not `referer`/`title`).

New `tests/test_openai_provider.py` (25 tests): `_read_a4_config` reads for BOTH
`OpenAIProvider` and `OpenRouterProvider` (present + absent/None/non-dict/junk →
`None`, parametrized); `_a4_request_kwargs` mapping (stop/effort passthrough,
json_object direct, json_schema synthesized-name + caller-supplied-name honored,
all-three-together, empty→`{}`); config→wire integration for BOTH providers on
BOTH `complete()`/`stream()` via direct provider construction + an injected
`httpx.MockTransport` (the `make_openai` internal pattern,
`scripted_transport.py` ~`:300-307` — the shared harness was NOT expanded, per
DD5/leg scope); a None-path test (env delenv'd, no config) confirming
`_a4_request_kwargs() == {}` and the request body carries none of the three keys.
OpenRouter's config→wire tests pre-flip `_max_context_tokens_resolved = True`
(mirrors `make_openrouter`'s hermeticity note — its context resolver hits the
network on its own client, not the injected transport).

`test_subclass_has_all_parent_instance_attrs` and `test_config_kwarg_is_ignored`
(`tests/test_openrouter_provider.py:272`, `:257`) re-run unchanged and pass — the
A4 config-key reads are a distinct namespace from the hardcoded `referer`/`title`
headers, so the no-leak invariant they pin is untouched.

`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_openai_provider.py
tests/test_openrouter_provider.py tests/test_llm_provider_cross_provider_conformance.py
tests/test_request_params.py -x --timeout 30` — 121 passed. `ruff check`/`ruff
format --check` clean on `openai_provider.py`, `openrouter_provider.py`,
`tests/test_openai_provider.py`. `git diff --stat` scoped to those two provider
files + the new test file (plus flight/leg artifacts and the prior legs'
already-landed, still-uncommitted files — batch-commit model). No ABC/signature
change; nothing new exported from `the_one/llm/__init__.py`; Ollama and the
conformance-suite harness untouched (L04/L05 scope).

Edge cases recorded, not resolved this leg: `stop` unsupported on OpenAI o3/o4-mini
(per-route/param gating is backlog B4); no OpenAI temperature-retry exists so
there's no A4-preservation-under-retry test needed here (unlike Anthropic's L02).

---

## Wire-Format Premise

**Leg 01 doc-gate (F10 Rec 1 / DD4).** Method: the installed **pinned SDKs**
(`anthropic` 0.97.0, `openai` 2.33.0 — repo's actual pins) are treated as
authoritative for *accepted param names/shapes* (read directly from the type
stubs under `.venv/lib/python3.12/site-packages/`). First-party docs
(WebFetch/WebSearch, fetched 2026-07-06) fill in *per-model defaults* and the
*effort×adaptive-thinking composition* question, which the SDK types don't encode.
Every claim below cites its source; anything not settleable from repo/SDK/docs is
flagged **HAT-confirm (L07)** rather than asserted.

### `reasoning_effort`

| Provider | Accepted request shape | Per-model default (current target lineup) | Source |
|---|---|---|---|
| **Anthropic** | `output_config.effort: Optional[Literal["low","medium","high","xhigh","max"]]` — sibling field to `output_config.format` on the same `output_config` dict (message-create top-level param) | No single universal default value is sent by the API when omitted; under adaptive thinking, `high` is the documented reference point ("At the default effort level (`high`), Claude almost always thinks"). `xhigh` is only accepted on Claude Fable 5, Claude Mythos 5, Claude Opus 4.8, Claude Opus 4.7, and Claude Sonnet 5; `max` is accepted on all adaptive-thinking-capable models. | SDK stub `.venv/lib/python3.12/site-packages/anthropic/types/output_config_param.py:14`; docs [Adaptive thinking](https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking) ("Adaptive thinking with the effort parameter" table) |
| **OpenAI** | `reasoning_effort: Optional[Literal["none","minimal","low","medium","high","xhigh"]]` — top-level `chat.completions.create` param | Per-model, not universal: `gpt-5.1` defaults to `none` (supported values `none`/`low`/`medium`/`high` only); **all models before `gpt-5.1` default to `medium`** and do not support `none`; `gpt-5-pro` defaults to (and only supports) `high`; `xhigh` supported on all models after `gpt-5.1-codex-max`. Docs additionally note the newest `gpt-5.5` defaults to `medium` ("the best starting point for gpt-5.5's full balance of quality, reliability and performance") — defaults are explicitly stated to be model-dependent, not universal. | SDK docstring `.venv/lib/python3.12/site-packages/openai/types/chat/completion_create_params.py:196-215` (`reasoning_effort` field docstring, verbatim per-model default text); docs [Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning) |
| **Ollama `/v1`** | `reasoning_effort` (OpenAI-compat alias) **and** a `reasoning: {"effort": ...}` object, both accepted on `/v1/chat/completions`; internally translated to Ollama's native `think` field | Model-dependent (thinking-capable models only); no universal default is documented — **HAT-confirm (L07)**: exact accepted-value set and the effort-string→`think`-level translation table for the target Ollama model are not pinned by docs at the granularity this flight needs live verification for. | docs.ollama.com [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility) |
| **Ollama native** | `think: bool \| Literal["low","medium","high","max"]` on `/api/chat` and `/api/generate` | Model/Modelfile-dependent; most non-reasoning models ignore it, reasoning models vary — **HAT-confirm (L07)** for the specific target model's default. | github.com/ollama/ollama `docs/api.md` (`think` field description) |

**Effort × adaptive-thinking composition — RESOLVED, not HAT-confirm.** Current
Anthropic docs settle this explicitly: "You can combine adaptive thinking with the
effort parameter to guide how much thinking Claude does. The effort level acts as
soft guidance for Claude's thinking allocation," followed by a worked example
sending `"thinking": {"type": "adaptive"}` **and** `"output_config": {"effort":
"medium"}` in the same request body. They compose — `output_config.effort` does
not supersede or conflict with the `thinking: {type: adaptive}` block already set
by `_build_kwargs` (`anthropic_provider.py`, the `kwargs["thinking"]` site); L02
adds `effort` alongside the existing thinking block, not instead of it. Source:
[Adaptive thinking — "Adaptive thinking with the effort parameter"](https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking).

### `response_format`

| Provider | Accepted request shape | Per-model default | Source |
|---|---|---|---|
| **Anthropic** | `output_config.format: Optional[JSONOutputFormatParam]` where `JSONOutputFormatParam = TypedDict(schema: Required[Dict[str,object]], type: Required[Literal["json_schema"]])` — **`schema` is `Required`, `type` accepts only the literal `"json_schema"`. No bare/dict-free JSON mode exists on this surface.** | Omitted → free-text response (no structured-output default). Structured outputs GA on Claude Fable 5, Claude Mythos 5, Claude Opus 4.8/4.7/4.6, Claude Sonnet 5/4.6/4.5, Claude Haiku 4.5. | SDK stub `.venv/lib/python3.12/site-packages/anthropic/types/json_output_format_param.py` (confirms `Required` on both fields); docs [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) ("Currently, only `json_schema` is supported — there is no bare JSON mode") |
| **OpenAI** | `response_format: ResponseFormat` = `ResponseFormatText \| ResponseFormatJSONSchema \| ResponseFormatJSONObject`. `{"type":"json_object"}` accepted (docstring: "older method... using `json_schema` is recommended for models that support it"); `{"type":"json_schema","json_schema":{"name","schema","strict"}}` accepted. | Omitted → free-text; no forced default. `json_object` is explicitly the legacy path, `json_schema` the recommended one — both remain valid request shapes on the pinned SDK. | SDK stubs `.venv/lib/python3.12/site-packages/openai/types/shared_params/response_format_json_object.py`, `response_format_json_schema.py`; docstring in `completion_create_params.py:224-230` |
| **Ollama `/v1`** | `response_format` accepted (OpenAI-compat JSON mode) | Omitted → free-text; no universal per-model default. | docs.ollama.com [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility) |
| **Ollama native** | `format: "json" \| <json-schema-object>` on `/api/chat`/`/api/generate` — accepts the bare string `"json"` **or** a full JSON-schema object | Omitted → free-text. | github.com/ollama/ollama `docs/api.md` ("the format to return a response in. Format can be `json` or a JSON schema") |

**Anthropic structured-output constraint (binds L02 — Acceptable-variation, NOT a
Divert trigger).** `output_config.format` accepts **only**
`{"type": "json_schema", "schema": {...}}` — confirmed in the installed
`JSONOutputFormatParam` stub (both `schema` and `type` are `Required`, `type` is a
one-member `Literal["json_schema"]`) and independently confirmed by the fetched
docs page. There is no Anthropic request shape corresponding to canonical
`{"type": "json_object"}`. Consequence for L02: canonical `json_object` on
Anthropic is a **documented no-op/warning**, not an error — this is the flight's
"Acceptable variations: per-provider no-ops" bucket (flight.md DD2), explicitly
**not** the "structured output is tool-based" Divert-if condition (Anthropic's
structured-output surface is native `output_config`, not tool-based — confirmed by
both the SDK stub and the docs page's example, matching the Phase-5b design-review
SDK pre-check already recorded in this log).

### `stop`

| Provider | Accepted request shape | Per-model default | Source |
|---|---|---|---|
| **Anthropic** | `stop_sequences: SequenceNotStr[str]` — top-level `messages.create` param, list of strings | Omitted → no custom stop sequences (model's own end-of-turn behavior only). | SDK stub `.venv/lib/python3.12/site-packages/anthropic/types/message_create_params.py:150-158` |
| **OpenAI** | `stop: Union[Optional[str], SequenceNotStr[str], None]` — bare string **or** list of up to 4 sequences | Omitted → no custom stop. Docstring: **"Not supported with latest reasoning models `o3` and `o4-mini`"** — noted as a known per-model exception on the reasoning-model family; not expected to block the current target lineup's HAT model choice, recorded for L03/L07 awareness. | SDK docstring `.venv/lib/python3.12/site-packages/openai/types/chat/completion_create_params.py:264-268` |
| **Ollama `/v1`** | `stop` accepted (OpenAI-compat), forwarded through to the native runner | Omitted → no custom stop. | docs.ollama.com [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility) (`stop` listed among supported `/v1/chat/completions` fields) |
| **Ollama native** | `options.stop: list[str]` on `/api/chat`/`/api/generate` (example: `"stop": ["\n", "user:"]`) | Omitted → no custom stop. | github.com/ollama/ollama `docs/api.md` |

Canonical mapping (confirms flight.md DD3): `stop` → canonical `list[str]` maps
cleanly to all four request paths — Anthropic `stop_sequences` (list), OpenAI /
Ollama-`/v1` `stop` (list form of the string-or-list union), Ollama-native
`options.stop` (list). No divergence.

### Divert-trigger check (per flight "Divert if" list)

None of the three A4 params hits a Divert-if trigger:

- **`stop`** maps to one canonical shape (`list[str]`) across all four paths with
  no gaps.
- **`reasoning_effort`** maps to one canonical shape (a lowercased effort string)
  across all four paths; the *accepted value sets* differ per provider/model
  (deliberately left unvalidated at the canonical layer per this leg's Implementation
  Guidance — per-provider validation is L02–L04's job, not a divert condition).
- **`response_format`** maps to one canonical value space (kept as **both**
  `{"type":"json_object"}` and `{"type":"json_schema","schema":{...}}`, per the
  bound decision below). Anthropic's inability to accept the `json_object` variant
  is a **per-provider no-op**, explicitly called out in the flight spec's
  "Acceptable variations" bucket — **not** the "structured output is tool-based"
  Divert-if condition, since Anthropic's structured-output surface is confirmed
  native (`output_config.format`), not tool-based.

**Conclusion: no divert.** Proceeding to land the canonical resolvers (Leg 01
Part B).

### Bound decisions carried into this leg's implementation

- Canonical `response_format` keeps **both** `json_object` and `json_schema`
  variants (OpenAI/Ollama-`/v1` honor bare JSON; Anthropic no-ops `json_object` in
  its L02 wiring — recorded above).
- Coercion lives in the caller's `__init__` (raw `config` value → canonical, via
  `_coerce_*`); each resolver coerces **only** the env read, at call time —
  matching both `resolve_extended_thinking` and `effective_num_ctx` precedent.
- Canonical env vars are provider-agnostic: `THE_ONE_REASONING_EFFORT`,
  `THE_ONE_RESPONSE_FORMAT`, `THE_ONE_STOP`.

---

## Flight Director Notes — Phase 2d (batch review + commit)

**2026-07-06 — All autonomous legs (L01–L06) landed; batch code review + fix.**
Per the agentic-workflow batch model, code review + commit were deferred to after
the last autonomous leg. Regression gate: `make test-unit` **3895 passed, 10
skipped, exit 0** (run by the Flight Director). Batch Reviewer (fresh agent,
Sonnet — FD escalated from the crew-default Haiku for a 6-leg cross-cutting batch;
Opus barred for Reviewer per methodology) reviewed all uncommitted changes against
DD1–DD6 + criteria. Verdict: **one BLOCKING issue**, everything else clean
(ABC untouched, resolver/coercion correctness, per-provider native mappings,
conformance config→wire, parity, temperature-retry preservation all verified;
268 targeted tests + ruff clean).

**BLOCKING (found + fixed) — Studio save wiped config/env-only keys.**
`provider-editor.js::collectFormData` built `payload` with no `config` seed and set
`payload.config` only inside per-field blocks, so a UI Save sent a `config` object
containing only the UI-known keys; the backend `update_provider` does
`model_copy(update=data)` (field-level replace, not deep merge), silently wiping
`response_format`/`stop` (DD6: config/env-only, no UI field) and any other
out-of-band `config` key. L06 newly triggered this for `openai`/`openai-compatible`
(they gained `showReasoningEffort` → always send `config`); anthropic/ollama/
openrouter had the same latent wipe. **Fix**: seed `payload.config` from a shallow
clone (`Object.assign({}, provider.config)`) of the existing config at the top of
`collectFormData` (before all field blocks; `{}` on create), and make the
OpenRouter referer/title branch overlay rather than replace. Threaded `provider`
into the one call site. Source-scan guard test added
(`test_provider_editor_seeds_config_from_existing_provider_before_field_blocks`);
the **behavioral** save-preserves-config property has no JS-unit coverage and is a
checkpoint for the L07 HAT. Re-review by the original Reviewer (full flight context):
**`[HANDOFF:confirmed]`** — all 5 verification points pass (seed precedes all field
blocks; `provider` genuinely reaches the call site so the seed can't degrade to
`{}` on edit; OpenRouter no-leak invariant intact; unknown keys survive Save for
all five types; no new issue). Bonus: the fix also closes the latent OpenRouter
`reasoning_effort` wipe.

**Post-flight doc**: `the_one/agents.md` updated with the A4 config-surface
convention (resolver precedence + per-provider native mapping + OpenRouter subclass
caveat) per the flight Completion Checklist. Legs L01–L06 set `completed` and
checked off in flight.md. Committing the batch; flight stays `in-flight` pending
L07 (optional operator-guided HAT).

---

## L07 — HAT run (2026-07-08, operator-guided, Anthropic-only)

**Scope**: live-verified on **Anthropic** (`claude-sonnet-4-6`, adaptive thinking
on) via the running dev backend on :8485, rebuilt from this branch (`d5a359d`) and
confirmed serving our code at the asset level (curled `provider-editor.js` /
`admin.js` contained the L06 field + the config-wipe fix). OpenAI + Ollama live
verification **deferred** (operator had no live OpenAI reasoning key / local Ollama
this session) — their wire paths remain proven hermetically by the L05 conformance
matrix + unit tests; the two L04 Ollama HAT-confirm items (`/v1` effort→`think`
translation; `/v1` json_schema-wrapper acceptance) carry forward.

**Result: PASS (6/6).**
- **S1 backend currency** — PASS (served assets contain our code; pid 3652178).
- **S2 reasoning_effort field renders** — PASS (dropdown present, Provider default
  selected; live-confirms L06).
- **S3 save-preserves-config (config-wipe fix)** — **PASS**, the highest-value step
  (no automated coverage): set `response_format`+`stop` out-of-band via API, then a
  UI Save that added `reasoning_effort:high` preserved all four keys
  (`thinking_enabled`, `response_format`, `stop`, `reasoning_effort`). Pre-fix this
  Save would have wiped `response_format`/`stop`.
- **S4 reasoning_effort behavioral delta** — PASS: same river-crossing puzzle at
  `high` vs `low` (fresh sessions). High showed verbose working-through +
  mid-answer self-correction + a full state table; low gave a lean, direct, still-
  correct list. Visible effort difference.
- **S5 structured outputs (json_schema)** — PASS on retry (see Finding 1): returned
  well-formed `{"answer": "..."}` matching the schema.
- **S6 stop sequence** — PASS on a fresh session (see Finding 2): `stop:["5"]`
  truncated "count to 10" to `1 2 3 4` (plain text, confirming `response_format`
  cleared).

### Findings (recorded; neither is an A4 defect, neither blocks landing)

**Finding 1 — Anthropic strict structured output requires
`additionalProperties: false` on object schemas.** S5 attempt 1 400'd:
`output_config.format.schema: For 'object' type, 'additionalProperties' must be
explicitly set to false`. This actually **confirmed the wire path end-to-end** (the
request reached Anthropic with `output_config.format` correctly assembled by L02) —
Anthropic rejected the schema *content*, not the request shape. Per **DD2**
(provider-native pass-through, no client-side schema repair), the-one forwards the
caller's schema as-is; a non-compliant schema is caught by the provider's strict
mode, exactly the recorded DD2 trade-off. The fix was to the *test* schema (add
`additionalProperties:false`), after which S5 passed. **Candidate follow-up
(optional, out of scope):** an opt-in schema normalizer that injects
`additionalProperties:false` for strict-mode providers — a convenience, not a
correctness gap. Worth a usage note in the response_format docs.

**Finding 2 — provider config changes don't affect an already-open chat session
(session-cached agent).** S6 attempt 1 returned the *previous* config's behavior
(still JSON, counted to 10) because `app.py` holds a per-session cached `agent`
(`session.agent`, evicted/`aclose`d at `app.py:566`/`:637`) whose provider read the
A4 config **once at construction**; a mid-conversation config edit doesn't reach it.
A **fresh session** picked up the new config immediately (S6 then passed). This is
**pre-existing infrastructure behavior shared by `thinking_enabled`/`num_ctx`**, not
an A4 bug — but it is an operator-facing caveat for the L06 admin field: setting
`reasoning_effort` in the UI won't change an already-open chat until a new session
(or restart). Recorded as a UX caveat; a provider-config-change → session-agent
eviction hook is a candidate follow-up (broader than A4). *(This is distinct from
the config-wipe fix, which S3 verified — persistence is correct; live-propagation
to running sessions is the caching caveat.)*

### Design direction surfaced (recorded as a mission Known Issue)

Operator: the provider-scoped tuning knobs (`num_ctx`, `thinking_enabled`,
`reasoning_effort`) should move to an **agent-level** config surface in a future
mission — agents sharing a provider connection can't tune independently today
(there is no per-model/per-agent config store). Logged to
`missions/16-llm-provider-hardening/mission.md` Known Issues as a future-mission
candidate. Not an A4 defect (A4 followed the ratified DD1/DD6 provider-config
precedent).

**Provider config restored** to its original `{"thinking_enabled": true}` after the
run. Dev backend left running on :8485.
