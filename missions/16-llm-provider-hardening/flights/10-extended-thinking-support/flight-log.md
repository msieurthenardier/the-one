# Flight Log: Extended-Thinking / Reasoning Support (A1)

**Flight**: [Extended-Thinking / Reasoning Support (A1)](flight.md)

## Summary

Planning. This flight implements backlog item **A1** (thinking field on `Message` + codec
round-trip + Anthropic capture/replay + web-UI surfacing) — the first ratified capability
after the F2/F3 bug fixes. Scope, design decisions (DD1–DD7), and the leg breakdown are in
`flight.md`. The reconnaissance below verified A1's cited locations against current code
before legs were drafted.

---

## Reconnaissance Report

Phase-1b upstream recon of A1 (source: F1B `flight-log.md` `## Gap Backlog → A1`). A1 cites
`base.py:64-70`, `db/codec.py`, and the Anthropic adapter; those citations are weeks old.
Three read-only agents verified each against current code. **All of A1's premises are
`confirmed-live`; only the audit's line numbers had drifted** (recorded below as real
current locations). No item retired.

| Item | Classification | Evidence (real current location) | Note |
|------|----------------|----------------------------------|------|
| A1.a — `Message` has no thinking field | `confirmed-live` | `the_one/llm/base.py:65–119` (fields end at `channel_name`); `StreamChunk` `:228–243` also has none | audit's `:64-70` → real `:65–119` |
| A1.b — codec round-trip needed, emit-when-non-None | `confirmed-live` | `db/codec.py` `message_to_dict:71–102`, `message_from_dict:105–141`; template = `_tool_result_to_dict:54–64` (`metadata` conditional emit `:62–63`); tripwire `tests/test_db_codec.py:655–677` | pattern intact; a scalar/list both fit |
| A1.c — capture de-risked (thinking arrives whole) | `confirmed-live` | `anthropic_provider.py` `_stream_inner:245`, `text_stream:253`, `get_final_message():259`; content-block iteration `191–195` (complete) / `263–276` (stream) handles only `text`/`tool_use` — **thinking silently discarded** | premise for DD2; **still to reconfirm live w/ thinking ENABLED (Leg 02 probe)** |
| A1.d — replay site exists | `confirmed-live` | `_to_api_message:296`; assistant blocks built `315–323` as `[text, tool_use]`; **no thinking slot** | thinking must precede `tool_use` (DD1/DD3) |
| A1.e — enablement site exists | `confirmed-live` | `_build_kwargs:115`, kwargs assembled `130–157` (`temperature` at `:134`); `thinking` key never set | DD6: enabling forces `temperature=1` |
| (context) tool-schema passthrough (#122, F2) | `confirmed-live` | `_to_anthropic_tool:285–294`, `sanitize_tool_schema` at `:293` | audit's `:210-215` had drifted; #122 owned by F2, untouched here |
| (context) no existing thinking/reasoning handling anywhere | `confirmed-live` | grep across `the_one/`: only UI-placeholder comments (`app.py:147,651`; `_discord.py:182,198`) + mock model name (`mock.py:20`); **no protocol field** | greenfield on the protocol |

### Two recon findings that refined A1's one-line sketch

1. **Representation must be structured (→ DD1).** A1 sketched "a typed thinking/reasoning
   field … mirroring `peer_name`" (a scalar `str | None`). But criterion #1's follow-up turn
   requires replaying thinking blocks **with signatures**, and `redacted_thinking` blocks are
   opaque `data` with no text. A scalar `str` cannot carry either → a `list` of structured
   blocks (round-tripped like `tool_calls`) is the minimum shape that meets the criterion.

2. **Live streaming is a separable, heavier effort (→ DD2, deferred).** `stream()` uses
   `text_stream` + `get_final_message()` (`_stream_inner:245–276`), so thinking arrives whole
   at turn end — enough to store/replay/reveal-after with **no** stream-loop rewrite. Live
   token-by-token thinking needs a `text_stream`→raw `RawMessageStreamEvent` refactor (the L04
   code comment flags it "too invasive"). Explicitly deferred.

### Web-UI hook points (for Leg 04)

WS events emit from `app.py` (`assistant_chunk:1501`, `assistant:1392`+`:1558`,
`usage:1382–1389`, `done:1709`); history projected by `messages_to_ui_events`
(`app.py:53`, call `~979`). Client render in `chat.js`: streaming assembly `1184–1210`,
`finalizeStreamingBubble` **defined at `:586`** (called from `:1216/1226/1243/1284/1318/1347`),
`renderHistory:358–424`. Reuse target: the trace-shell `<details>` disclosure
(`chat.css:149–208`). ⚠️ `.msg.thinking` (`chat.css:444`) + `createThinking`/`removeThinking`
(`chat.js:602/608`) are the **ACTIVE ephemeral "thinking…" loading indicator** — Leg 04 must
use distinct identifiers, not reuse these. The F09-06 routing-audit-panel overlay pattern was
considered and **not** chosen (DD3).

### Config precedent (for Leg 05)

The F09-05 `num_ctx` field is the end-to-end template: backend effective-value resolver
(config → env → default) + a Studio provider-editor field (label + ⓘ tooltip + `0`/blank
sentinel). Leg 02 builds the resolver; Leg 05 adds the UI field.

**Operator ratification of recon (2026-07-02):** _pending — presented in planning; no item
proposed for retirement, so this is confirmation-only._

---

## Decisions

### Thinking is OFF by default (default budget = 0)
**Context**: Flight DD4 carries an ambiguity — "default (`0` = disabled)" vs. "default 4096".
The resolver needs one terminal default.
**Decision**: The budget resolver's terminal default is **`0` = disabled**. `4096`
(`DEFAULT_THINKING_BUDGET`) is only the *suggested enabled magnitude* that Leg 05's admin field
pre-fills / writes when the operator turns thinking on. Thinking is opt-in per provider config.
**Rationale**: The only reading consistent with (a) the `0`/blank = disabled sentinel, (b) the
behavior-test "Budget = 0 (disabled)" gating variant, and (c) not silently forcing
`temperature=1` + raised `max_tokens` + thinking-token billing onto every existing Anthropic
user. The flight lists "choosing the exact default budget value" as an acceptable variation,
granting the latitude. Design review (Leg 02) independently confirmed on-by-default was not
intended.
**Impact**: Leg 05's admin field must default the display/pre-fill to `4096` but persist `0`/blank
as disabled; the behavior test's disabled variant is a real regression guard.

### `enable_thinking` added to the `LLMProvider` contract (DD4 suppression)
**Context**: The connector inference classifier (`_inference.py:325–330`) calls `complete()` on a
*generic* provider and must not have thinking forced onto its `max_tokens=10` yes/no call.
**Decision**: Add a back-compatible keyword-only `enable_thinking: bool | None = None` to
`LLMProvider.complete`/`.stream` (and the concrete overrides); only Anthropic acts on it
(`False` → suppress). Classifier passes `enable_thinking=False`.
**Impact**: A contract *extension* (not a break — the mission's "preserve the contract" constraint
holds). `base.stream`'s default body forwards the param; the four inference test doubles must
accept it (design-review [high] finding). **Survives the adaptive pivot unchanged** — suppression
is mode-independent.

### PIVOT — adaptive-only enablement; `budget_tokens` dropped; effort deferred (supersedes DD4/DD6 enablement)
**Context**: Leg 03 design review surfaced, and Anthropic's authoritative docs
(platform.claude.com → Extended thinking) **confirmed**, that `thinking: {"type": "enabled",
"budget_tokens": N}` (Leg 02's wire format) **400s** on Sonnet 4.6 + all current models; it works
only on Opus 4.5 / Haiku 4.5 / older Claude 4. Current models require `thinking: {"type":
"adaptive"}` (+ optional `effort`). the-one's default model is `claude-sonnet-4-6`, so Leg 02's
enablement would 400 on the default model — the flight's core value at risk. (See Anomalies.)
**Decision (operator, 2026-07-02)**: Support extended thinking on **Sonnet 4.6 and newer only**.
Enablement becomes **adaptive-only** (`thinking: {"type": "adaptive"}`); the `budget_tokens` path
and its resolver are **removed** (they served only the unsupported pre-4.6 models). Operator
control is **on/off** (a boolean enable, default off). The adaptive **`effort` knob stays deferred
to backlog A4** per DD5 — adaptive uses the API-default effort this flight.
**Impact (supersedes DD4/DD6 enablement; DD1/DD2/DD3/DD5/DD7/DD8 unchanged)**:
- DD6's `temperature=1`-forcing + `max_tokens`-raise **evaporate** — adaptive has no budget; newer
  models reject `temperature` regardless and the existing temperature-retry already handles that.
- The per-provider config surface flips from `config["thinking_budget"]` (int, `0`=off) to
  `config["thinking_enabled"]` (bool, default off); env `THE_ONE_ANTHROPIC_THINKING_BUDGET` →
  `THE_ONE_ANTHROPIC_EXTENDED_THINKING`.
- **Replan (6→7 legs):** a new **Leg 03 `anthropic-adaptive-enablement`** revises Leg 02's
  enablement + config resolver (Leg 02's *capture* + the `enable_thinking` contract are correct
  and stay); the replay leg (design-approved) becomes **Leg 04**; UI→05; the admin field
  (**Leg 06**) becomes an on/off "Extended thinking" toggle, not a budget number; verify+HAT→07.
- Leg 02's enablement/budget code + tests land as *superseded* (uncommitted, so no history churn —
  Leg 03 revises before the Phase-2d commit). Original DD4/DD6 framing preserved in `flight.md` as
  commentary with a pivot banner.
**Rationale**: Verified against first-party docs; keeps the flight lean (no A4 effort UX); delivers
thinking on the operator's actual/default model. Operator-ratified.

### HAT fix — request `display: "summarized"` so the disclosure shows readable reasoning
**Context**: The Leg 07 live HAT found the thinking disclosure rendered empty on Sonnet 5: the
adapter sent `thinking: {"type": "adaptive"}` with no `display`, and — confirmed against Anthropic's
adaptive-thinking docs — **`thinking.display` DEFAULTS to `"omitted"` on Sonnet 5 / Opus 4.8/4.7 /
Fable 5 / Mythos 5** (thinking blocks return an EMPTY `thinking` text field; only the `signature`
is populated, for replay). So `thinking_display_text` correctly returned `""` → no event → no
disclosure. The backend replay path was fine (signed blocks captured/persisted/replayed, no 400);
only the readable-text surface was missing.
**Decision (HAT inline fix, 2026-07-03)**: enable at the single `_build_kwargs` site with
`kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}` so the model returns readable
summarized reasoning text for the DD3 web-UI disclosure.
**Impact**: One prod line + 3 test-assertion updates (the `{"type": "adaptive"}` shape → adds
`"display": "summarized"`). The `signature` is **identical** across display modes (per docs), so
capture/replay are unaffected; no per-model branching (`"summarized"` is valid on all adaptive
models; already the default on Opus 4.6 / Sonnet 4.6). Live-verified: the disclosure now renders
non-empty reasoning that matches persistence exactly (behavior test 7/7 PASS).

---

## Deviations

### Leg 02 — `enable_thinking` blast radius wider than the leg's step 9b named
**Planned**: The leg (step 9b, from design review) named **four** `LLMProvider` test doubles in
`test_connectors_inference.py` as needing the `enable_thinking` kwarg.
**Actual**: Because `base.stream`'s concrete default now **forwards** `enable_thinking` into
`self.complete(...)` (the [medium] review fix), EVERY test double that relies on the default
`stream` AND whose `complete` lacked the kwarg `TypeError`'d — a suite-wide 46-failure cascade.
The Developer extended the fix to **five additional default-stream doubles**: `conftest.FakeLLM`,
`_connector_dispatch_helpers._ScriptedProvider`, `test_streaming._CompleteOnlyProvider`,
`test_llm_registry`'s dummy, `test_web_session_reaper._NopLLM`.
**Reason**: The design review located the doubles in the one file it inspected
(`test_connectors_inference.py`), but the forwarding change reaches any default-stream double
repo-wide. A grep for `class .*\(LLMProvider\)` / `def complete` across `tests/` at design time
would have caught the full set. **Standardize?** Yes — leg-design lesson: when a change touches a
base-class default that call-sites depend on, enumerate ALL subclasses/doubles (prod AND test)
before scoping. Carry to the flight debrief.

---

## Anomalies

### `budget_tokens` enablement (Leg 02 / DD4 / DD6) 400s on the current model lineup
**Observed**: Surfaced as a Leg 03 design-review question; **verified against Anthropic's
authoritative docs** (platform.claude.com → Extended thinking). The wire format Leg 02
implemented — `thinking: {"type": "enabled", "budget_tokens": N}` — is **rejected with a 400** on
Sonnet 4.6, Opus 4.6/4.7/4.8, Sonnet 5, Fable 5, Mythos 5. It is accepted **only** on Opus 4.5,
Haiku 4.5, and earlier Claude 4 models. Current models require `thinking: {"type": "adaptive"}`
(+ optional `effort: low|medium|high`).
**Severity**: **blocking (for flight value)**. the-one's default Anthropic model is
`claude-sonnet-4-6` (`anthropic_provider.py:137`; overridable via `config.llm_model`), which the
docs list as deprecated and `budget_tokens`-rejecting. So on the default (and every current)
model, Leg 02's enablement 400s before the criterion is ever exercised — the live probe / behavior
test would have caught it, but at Leg 06, after Legs 04–05 built atop the premise.
**Not affected**: Leg 03 replay. The docs confirm thinking blocks + signatures replay identically
regardless of enablement mode (`[thinking_block, tool_use_block]`, signatures verbatim, 400 on any
modification). Legs 01 (protocol/codec) and 03 (replay) are correct as-is.
**Resolution**: escalated to the operator (flight-level go/no-go — a full adaptive+`effort` build
overlaps backlog **A4**, explicitly deferred by this flight's DD5). **RESOLVED (operator,
2026-07-02):** support thinking on **Sonnet 4.6 and newer only** → **adaptive-only enablement**
(`thinking: {"type": "adaptive"}`); **drop `budget_tokens` entirely** (it served only the
pre-4.6 models we're not supporting). **On/off** operator control; **effort knob stays deferred
to A4**. See the Decision + Flight Director Note below. Legs 01 (protocol) + 03-as-designed
(replay) are correct as-is; Leg 02's enablement + config surface are revised by a new leg.

---

## Session Notes

**2026-07-02 — Flight planned.** Selected A1 (extended thinking) as Flight 10 — the F1B
backlog's ratified first capability flight, closing two named mission criteria. Ran Phase-1b
recon (3 read-only agents: Anthropic adapter, codec+loop, web UI) — all A1 premises
confirmed-live, line numbers refreshed. Resolved DD1–DD7 with the operator (structured
thinking blocks; capture-whole/reveal-after; collapsible `<details>`; Studio budget field;
Anthropic-first; enforced request constraints; behavior-test apparatus both-axes audited).
Drafted the 6-leg breakdown + the `extended-thinking-tool-turn` behavior-test spec.

**2026-07-02 — Architect design review (Phase 5b): approve with changes; all applied.**
Recon spot-checked (~20 cites) accurate; installed `anthropic` SDK 0.79.0 confirms
`ThinkingBlock={signature,thinking,type}` / `RedactedThinkingBlock={data,type}` → DD1's
structured shape validated exactly; config→adapter reach confirmed (`factory.py:273,276`),
so prerequisites are satisfiable today. Changes incorporated:
- **Codec guard corrected (DD1 / Leg 01):** `thinking` is a list modeled on `tool_calls`
  (truthy emit guard), explicitly **outside** the `emit-when-non-none` convention; the
  byte-identity tripwire stays green **unchanged** (prior "update the tripwire" wording was
  wrong).
- **Dropped `StreamChunk.thinking` (DD2 / Leg 01):** redundant under capture-from-final-message
  — thinking rides `final_chunk.message.thinking`.
- **New DD8 — replay gated on outgoing thinking state:** strip stored thinking when thinking is
  off on the request (mixed on/off session); verify Anthropic's tolerance live in Leg 03;
  behavior-test mixed-session variant added.
- **Connector inference fast path (DD4 / Leg 02):** suppress thinking on the
  `_inference.py:322–330` `complete(max_tokens=10)` classifier (per-provider budget would
  otherwise force thinking onto it).
- **DD6 refined:** `max_tokens` **raised** (not clamped) to clear the budget; single
  enforcement site in `_build_kwargs` (loop passes no temperature); existing temperature-retry
  noted benign under thinking.
- **Default budget named:** `4096` when enabled.
- **Leg 02 adds** a non-fatal-error check (non-thinking model under a thinking budget survives).
- **Low cites fixed:** `finalizeStreamingBubble` def `:586`; `.msg.thinking` flagged ACTIVE.
Second Architect pass judged unnecessary — every change is the reviewer's own prescription
(no novel design); the one new element (DD8) is encoded as intended-contract-with-live-
verification, the form the reviewer requested.

**2026-07-02 — Flight marked `ready`.** Operator walkthrough (Phase 6) complete; operator
declined a second Architect pass and approved. Status `planning → ready`; pre-flight checklist
closed; registered as Flight 10 in `mission.md`. Legs authored one at a time at execution
(`/agentic-workflow` or `/leg`). No source touched; nothing committed.

---

## Leg Progress

**2026-07-02 — Leg 01 (`thinking-message-protocol`) implemented → `landed`.** Added the pure
protocol + codec foundation for extended thinking; no producer yet (Leg 02 is the first).

- `the_one/llm/base.py`: new `ThinkingBlock` dataclass near `ToolCall` (discriminated by a
  free-`str` `type`; `thinking`/`signature`/`data` default `None` — covers Anthropic's
  `thinking` and `redacted_thinking` variants). Added `Message.thinking:
  list[ThinkingBlock] = field(default_factory=list)` directly after `tool_calls` (structural
  sibling, truthy emit guard, deliberately OUTSIDE the emit-when-non-none convention).
  `Message.assistant` threads an optional keyword-only `thinking` kwarg (`thinking or []`).
  `StreamChunk` untouched (DD2); `Message.content` `__post_init__` str-assert untouched.
- `the_one/db/codec.py`: `_thinking_block_to_dict` / `_thinking_block_from_dict` serializers
  (two-level guard — field-level truthy in `message_to_dict`, sub-key `is not None` so
  empty-string signatures and the exact Anthropic block shape round-trip). `message_to_dict`
  emits `"thinking"` under `if msg.thinking:` adjacent to the `tool_calls` emit;
  `message_from_dict` reads `d.get("thinking", [])`. Extended the `base` import.
- `tests/test_db_codec.py`: new additive `TestMessageThinkingCodec` (12 tests) — emit/omit,
  signature preservation, redacted round-trip, back-compat (legacy rows → `[]`), full
  list-codec round-trip, empty-string-signature survival, mixed content
  (content + thinking + tool_calls, the criterion-#1 shape), unknown-future-type forward-compat,
  and a belt-and-suspenders composed-shape guard. The real byte-identity tripwire
  `test_encode_emits_no_keys_when_all_optional_fields_default` was NOT edited.

**Test results:** `tests/test_db_codec.py` — **95 passed** (12 new), tripwire green unchanged.
Full `make test-unit` — **3625 passed, 10 skipped, 1 failed**. The single failure
(`test_lifespan.py::test_lifespan_drains_session_registry`) is the known carried cross-suite
aiosqlite teardown flake the flight spec warns of: it passes clean in isolation AND when its
whole file runs (7/7); this leg touches only protocol/codec (no session-registry / db-connection
code), so it is not an A1 regression. `git diff the_one/agents.md` empty (no citation-count bump,
per DD1). `[HANDOFF:review-needed]`.

**2026-07-02 — Leg 02 (`anthropic-thinking-capture`) implemented → `landed`.** First PRODUCER of
thinking blocks: Anthropic enablement + DD6 enforcement + capture on both request paths, plus the
DD4 `enable_thinking` suppression contract.

- `the_one/llm/anthropic_provider.py`: module-level budget resolver `_coerce_thinking_budget` /
  `effective_thinking_budget` (+ constants `_THINKING_BUDGET_ENV`, `_MIN_THINKING_BUDGET=1024`,
  `DEFAULT_THINKING_BUDGET=4096`, `_ANSWER_HEADROOM_MIN=4096`) mirroring the F09-05 `num_ctx`
  resolver — the one deliberate divergence (commented) is that `0` is a MEANINGFUL explicit-disable
  and does NOT fall through to env (precedence config → env `THE_ONE_ANTHROPIC_THINKING_BUDGET` →
  default `0` = OFF). `__init__` reads `config["thinking_budget"]` into
  `self._configured_thinking_budget`. Single DD6 enforcement site in `_build_kwargs`: when
  `budget > 0 and enable_thinking is not False`, sets
  `kwargs["thinking"]={"type":"enabled","budget_tokens":budget}`, forces `temperature=1`, and
  RAISES `max_tokens` via `max(caller, budget + headroom)` (never shrinks). Capture of
  `thinking`/`redacted_thinking` blocks (content order preserved) in both `complete()` and
  `_stream_inner`, threaded via `Message.assistant(..., thinking=blocks)`; `text_stream` loop
  untouched (DD2 — thinking read whole from `get_final_message()`). `ThinkingBlock` imported.
  Existing temperature-retry left as-is (benign under thinking).
- `the_one/llm/base.py`: keyword-only `enable_thinking: bool | None = None` on abstract
  `LLMProvider.complete` and the concrete default `LLMProvider.stream`; the default `stream` body
  now FORWARDS `enable_thinking` into its `self.complete(...)` call (DD5 latent-correctness).
- `the_one/llm/{openai_provider,ollama_provider,mock}.py`: `enable_thinking` added (accepted,
  ignored) to each `complete`/`stream` override. OpenRouter INHERITS from `OpenAIProvider` — no
  edit (grep-confirmed).
- `the_one/connectors/_inference.py`: classifier `complete(max_tokens=10)` call now passes
  `enable_thinking=False` (DD4 — never pay the thinking premium on the cheap yes/no probe).
- `tests/test_connectors_inference.py`: added `enable_thinking` to the four `LLMProvider` doubles
  (`_RaisingProvider` + three `_CapturingProvider`s) so the new kwarg doesn't `TypeError` them
  (step 9b).
- **Broader test-double fix (beyond the leg's step-9b scope).** `base.stream`'s new
  `enable_thinking` forwarding into `self.complete(...)` `TypeError`'d EVERY `LLMProvider` test
  double that relies on the default `stream` and whose `complete` didn't accept the kwarg — a
  suite-wide blast radius (first full `make test-unit` = 46 failures across
  `test_agent_visibility_filter`, `test_connectors_e2e_*`, `test_connectors_inbound*`,
  `test_streaming::TestBaseStreamDefault`, `test_tool_call_timeout`,
  `test_agent_search_integration`). Fixed by adding `enable_thinking` (ignored) to the five
  default-stream doubles: `conftest.FakeLLM`, `_connector_dispatch_helpers._ScriptedProvider`,
  `test_streaming._CompleteOnlyProvider`, `test_llm_registry`'s dummy, and
  `test_web_session_reaper._NopLLM`. Doubles that override `stream` were unaffected (the agent
  loop never passes `enable_thinking` to `stream`, confirmed by their tests not failing). The
  leg's step 9b under-scoped this to the four inference doubles only.
- `tests/test_anthropic_provider.py`: +30 tests — resolver matrix, `__init__` config read,
  enablement/DD6-enforcement (temperature=1, max_tokens raised-not-shrunk), disabled/`0`
  passthrough (byte-identical request), `enable_thinking=False` suppression, capture on
  `complete()` (thinking + redacted + mixed content), capture on the streaming final message (no
  thinking-text leak into deltas), non-thinking-model `BadRequestError` non-fatal re-raise, and
  inference-style suppression.
- `tests/test_anthropic_live.py`: authored a `@pytest.mark.live` premise probe
  (`test_real_anthropic_streaming_thinking_premise`, thinking-capable model, budget-bearing
  provider → asserts `text_stream` yields answer text AND `get_final_message()` carries a signed
  thinking block). **Deselected by default; NOT run in this leg** (no Anthropic key in sandbox) —
  deferred to a pre-Leg-03 operator run (fail-fast gate before replay builds on the premise).

**Test results:** `tests/test_anthropic_provider.py` — **43 passed** (30 new); ruff clean on all
changed files. `tests/test_connectors_inference.py` — **25 passed** (step-9b regression green).
Full `make test-unit` — **3651 passed, 10 skipped, 1 failed**. The single failure is the known
carried aiosqlite teardown flake `test_lifespan.py::test_lifespan_drains_session_registry`
(passes clean in isolation — 7/7; this leg touches no session-registry / db-connection code) —
not an A1 regression, matches the flight-spec pre-flight warning. Live premise probe authored but
NOT run (no Anthropic key; deferred to pre-Leg-03 operator run). `[HANDOFF:review-needed]`.

**2026-07-02 — Leg 03 (`anthropic-adaptive-enablement`) implemented → `landed`.** Executed the
adaptive-only pivot: replaced Leg 02's `budget_tokens` enablement wire format (400s on Sonnet 4.6
+ all current models) with `thinking={"type":"adaptive"}`, flipped the config surface from an
integer `thinking_budget` to a boolean `thinking_enabled` (on/off, default off), and dropped DD6's
now-moot `temperature=1`-force + `max_tokens`-raise. Leg 02's capture (both paths) and the
`enable_thinking` suppression contract were NOT touched (mode-independent, correct as-is).

- `the_one/llm/anthropic_provider.py`: RIPPED OUT the budget scaffolding
  (`_THINKING_BUDGET_ENV`, `_MIN_THINKING_BUDGET`, `DEFAULT_THINKING_BUDGET`, `_ANSWER_HEADROOM_MIN`,
  `_coerce_thinking_budget`, `effective_thinking_budget`); replaced with a boolean resolver
  `_EXTENDED_THINKING_ENV` (`THE_ONE_ANTHROPIC_EXTENDED_THINKING`) + `_coerce_bool` (real
  bools/ints pass through; `1/true/yes/on`→True; `0/false/no/off/""`→False; else None) +
  `resolve_extended_thinking` (precedence config → env → default False; config False
  short-circuits, does NOT fall through to a truthy env). `__init__` reads
  `config["thinking_enabled"]` via `_coerce_bool` into `self._thinking_enabled_config: bool | None`.
  `_build_kwargs` hoists `thinking_active = resolve_extended_thinking(self._thinking_enabled_config)
  and enable_thinking is not False` BEFORE the message loop (Leg 04 will thread it into
  `_to_api_message`; NOT threaded here); when active sets ONLY `kwargs["thinking"]={"type":
  "adaptive"}` — temperature/max_tokens left at the caller's values (the existing temperature-retry
  still handles model rejection).
- `tests/test_anthropic_provider.py`: swapped the module import
  (`_coerce_thinking_budget`/`effective_thinking_budget` → `_coerce_bool`/`resolve_extended_thinking`)
  in the same edit as the removal (collection-safe). Replaced the budget-resolver matrix with a
  `_coerce_bool`/`resolve_extended_thinking` matrix (incl. the explicit-False-short-circuit case);
  replaced the enablement test to assert `thinking=={"type":"adaptive"}`, no `budget_tokens`, and
  `temperature==0.0`/`max_tokens==caller-value` (load-bearing proof DD6 forcing is gone); kept
  disabled-passthrough + `enable_thinking=False` suppression + inference-suppression migrated to
  the bool config; migrated the two error-path tests off the budget config; REMOVED the obsolete
  budget tests (0/blank/500→1024, max_tokens-raised, budget_tokens shape). Capture tests unchanged
  (set no enablement config).
- `tests/test_anthropic_live.py`: migrated the premise probe
  (`test_real_anthropic_streaming_thinking_premise`) from `config={"thinking_budget":1024}` →
  `config={"thinking_enabled":True}` and retargeted the default model to `claude-sonnet-4-6`
  (Sonnet 4.6+ for adaptive). Stays `@pytest.mark.live` (deselected). **Migrated but NOT run** (no
  Anthropic key in sandbox) — Leg 07's behavior test is the acceptance gate.

**Test results:** `tests/test_anthropic_provider.py` — **43 passed**. Budget-symbol grep over
`the_one/` returns CLEAN (no `budget_tokens`/`thinking_budget`/`effective_thinking_budget`/
`_coerce_thinking_budget`/`DEFAULT_THINKING_BUDGET`/`_ANSWER_HEADROOM_MIN`); the only remaining
`budget_tokens` hits in `tests/` are a deliberate negative assertion + its docstring. Full
`make test-unit` — **3651 passed, 10 skipped, 1 failed**. The single failure is the known carried
aiosqlite teardown flake `test_lifespan.py::test_lifespan_drains_session_registry` (passes clean
in isolation — 1/1); not an A1 regression, matches the flight-spec pre-flight warning.
`[HANDOFF:review-needed]`.

**2026-07-02 — Leg 04 (`anthropic-thinking-replay`) implemented → `landed`.** The REPLAY leg that
makes mission criterion #1's follow-up turn (carrying `tool_result` back) pass: stored thinking
blocks (signatures intact) are now projected **before** `text`/`tool_use` in the assistant turn,
gated on the outgoing request's thinking state (DD8 replay-when-on / strip-when-off). Builds on the
Leg 03 adaptive pivot — no enablement/budget/temperature logic touched.

- `the_one/llm/anthropic_provider.py`: added `_thinking_block_to_api(self, tb)` adjacent to
  `_to_anthropic_tool` — emits `{"type": tb.type}` plus only the set sub-fields (`thinking`/
  `signature` for thinking blocks, `data` for redacted), signatures verbatim (the API 400s if a
  replayed block is modified). Changed `_to_api_message` signature to
  `_to_api_message(self, msg, thinking_active: bool = False)` and widened the assistant guard to
  `msg.role == Role.ASSISTANT and (msg.tool_calls or (thinking_active and msg.thinking))`; when
  `thinking_active`, the projected `content` is `[*thinking, text?, *tool_use]` (thinking strictly
  first). When off, the thinking loop is skipped → stored thinking stripped, byte-identical to the
  pre-L03 projection; a thinking-only turn with thinking off falls through to the plain-string
  branch. `_build_kwargs`' ONLY change: threaded the already-hoisted (Leg 03) `thinking_active`
  into the loop call — `self._to_api_message(m, thinking_active)`; the Leg 03 hoist and adaptive
  enablement block were NOT touched. Refreshed two stale breadcrumbs (the L02 content-order comment
  and the L03 hoist comment) to reflect that Leg 04 now performs the replay/threading.
- `tests/test_anthropic_provider.py`: +10 tests — replay-on ordering (thinking@content[0],
  signature intact, before text before tool_use); two-block stored-order lock; redacted replay
  (`{"type":"redacted_thinking","data":...}`, no thinking/signature keys); strip-off default
  (thinking_active=False ≡ single-arg legacy call ≡ a message with no thinking, byte-identical
  `[text, tool_use]`); thinking-only turn on → `[thinking, text]` / off → plain-string branch;
  empty-thinking tool turn no-op; end-to-end replay-on through a config-bearing
  (`{"thinking_enabled": True}`) provider + `_CreateRecorder` (assistant entry has
  thinking-before-tool_use AND `kwargs["thinking"] == {"type":"adaptive"}`); hermetic end-to-end
  strip-off (no config → no thinking block, no `"thinking"` kwarg); end-to-end mid-session disable
  (`enable_thinking=False` over signed history → stripped).
- `tests/test_anthropic_live.py`: authored a deselected `@pytest.mark.live` mixed-session probe
  `test_real_anthropic_mixed_session_disable_after_thinking_tool_turn` — thinking-on tool
  round-trip, then continue with `enable_thinking=False` over the signed history and assert the
  follow-up does NOT 400 (the DD8 strip-when-off contract live). Deselected; NOT run this leg (no
  Anthropic key) — run at Leg 07 / HAT.

**Test results:** `tests/test_anthropic_provider.py` — **53 passed** (43 → 53, +10 new); ruff clean
on all three changed files; live probe collection green (5 deselected, +1). Full `make test-unit` —
**3661 passed, 10 skipped, 1 failed** (3651 baseline + 10 new replay tests). The single failure is
the known carried aiosqlite teardown flake
`test_lifespan.py::test_lifespan_drains_session_registry` (passes clean in isolation — 1/1;
`RuntimeError: Event loop is closed` at teardown); not an A1 regression, matches the flight-spec
pre-flight warning. `[HANDOFF:review-needed]`.

---

## Flight Director Notes

_Orchestration decisions from `/agentic-workflow` execution (append-only)._

**2026-07-02 — Flight execution started (`/agentic-workflow 10`).** Loaded mission (active),
flight (`ready`→`in-flight`), ARTIFACTS.md, and the `leg-execution` crew file (Developer=Sonnet,
Reviewer=Haiku; commit deferred to Phase 2d). Git: created feature branch
`flight/10-extended-thinking-support` off `main` (carried the uncommitted planning artifacts —
flight.md/flight-log.md/behavior spec + the mission.md registration — onto the branch; they ride
into the flight commit). `main` was +1 unpushed (F09 checkoff `b6fb5b9`), a legitimate ancestor.
6 legs total; starting at Leg 01. Per-leg design review is on; code review + commit deferred to
one pass after the last autonomous leg (Leg 05 — Leg 06 is the optional guided HAT).

**2026-07-02 — Leg 01 (`thinking-message-protocol`) designed.** Authored the protocol-foundation
leg (structured `ThinkingBlock` + `Message.thinking` list field modeled on `tool_calls`, truthy
emit guard, outside the emit-when-non-none convention; codec round-trip; tripwire stays green
unchanged). Citations self-verified against current code during authoring (base.py Message
fields end at `:119`; codec `tool_calls` emit `:74`; tripwire `:655–676`; peer_name test template
`:479–533`; agents.md convention `:414–443`). Spawned a Developer for independent design review.

**2026-07-02 — Leg 01 design review: approve (no blocking issues).** Developer validated all
five key design claims against real code: `tool_calls` truthy guard confirmed (`codec.py:74`);
tripwire stays green unchanged (the convention mandate is scoped to `is not None` fields, and
`tool_calls` is likewise absent from both the tripwire's expected list and the `agents.md`
citations — precedent is internally consistent); `content`-is-`str` assert untouched;
`StreamChunk` correctly excluded (DD2); every `file:line` citation accurate. Three **low**
non-blocking suggestions applied: (a) mixed-content round-trip test (content+thinking+tool_calls
coexist — the criterion-#1 shape, +acceptance criterion); (b) unknown-future-`type`
forward-compat test; (c) a code comment at `_thinking_block_to_dict` explaining the two-level
guard (field-level truthy vs sub-key `is not None`) so a future reader doesn't "harmonize" them.
Two questions were self-answered as intentional (keyword-only `thinking` on `.assistant`; safe
mid-dataclass field insertion — all `Message` sites use keyword/factory construction). Additive
refinements only → no second review pass. Leg 01 → `ready`; spawning Developer to implement.
`[HANDOFF:review-needed]` (design finalized).

**2026-07-02 — Leg 01 implemented → `landed`.** Developer implemented the protocol+codec
foundation per guidance. Codec suite: 95 passed (12 new `TestMessageThinkingCodec`); byte-identity
tripwire green **unchanged**; `agents.md` diff empty (no `n=5` bump); `StreamChunk` + `content`
str-assert untouched. Full unit suite: `3625 passed / 10 skipped / 1 failed` — the one failure is
`test_lifespan.py::test_lifespan_drains_session_registry`, the **known carried aiosqlite teardown
flake** (passes clean in isolation + when its file runs 7/7; this leg touches no
session-registry/db-connection code) → **not an A1 regression**, matches the flight-spec
pre-flight warning. Code review + commit deferred to Phase 2d (post-Leg-05) per the flight's
batch-commit workflow. `legs_completed = 1/5` autonomous. Advancing to Leg 02 design
(`anthropic-thinking-capture`).

**2026-07-02 — Leg 02 designed + reviewed: approve with changes; all applied.** Authored the
Anthropic enablement+capture leg (budget resolver mirroring F09-05 `num_ctx`; `_build_kwargs`
enable/enforce DD6; capture on `complete()` + `_stream_inner`; `enable_thinking` contract addition
for DD4 suppression). Two Decisions recorded above (off-by-default budget; `enable_thinking`
contract). Design review validated every citation + both consequential design points; two
findings applied: **[high]** the four `LLMProvider` doubles in `test_connectors_inference.py`
need `enable_thinking`/`**kwargs` or the new classifier kwarg `TypeError`s them (my grep scope
missed `tests/`) → added as step 9b + acceptance criterion + Files Affected; **[medium]**
`base.stream`'s concrete default must forward `enable_thinking` to its `self.complete()` call →
added. Two suggestions applied: noted `_provider_with_create` doesn't forward `config` (budget
tests construct directly); moved the recommended live-probe run point to **pre-Leg-03** (operator
action, needs a key) to preserve the fail-fast gate — autonomous acceptance stays fixtured.
Fixes are mechanical + reviewer-prescribed → no second review pass. Leg 02 → `ready`; spawning
Developer to implement. `[HANDOFF:review-needed]` (design finalized).

**2026-07-02 — Leg 02 implemented → `landed` (Flight-Director-verified).** Developer implemented
enablement + capture + the `enable_thinking` contract + the DD6 enforcement. **Verification note:**
my mid-run full-suite checks initially showed a 46-failure cascade — this was an artifact of
running `make test-unit` against a **still-mutating working tree** while the Developer was
concurrently fixing the `base.stream` blast radius (see Deviation). All 46 passed in isolation
and in file-groups; diagnosed as cross-test pollution, not logic breakage. After the Developer
settled the tree (5 extra default-stream doubles fixed), I ran one **authoritative** full suite:
`3651 passed / 10 skipped / 1 failed` — the lone failure is the known aiosqlite teardown flake
(`test_lifespan_drains_session_registry`, **confirmed 7/7 in isolation**), matching the
flight-spec pre-flight warning → not an A1 regression. Targeted suites: `test_anthropic_provider`
+ `test_connectors_inference` + `test_db_codec` = 163 passed. Live premise probe authored,
deselected, **unrun** — operator should run it pre-Leg-03 (needs an Anthropic key). Code review +
commit deferred to Phase 2d. `legs_completed = 2/5` autonomous. Advancing to Leg 03 design
(`anthropic-thinking-replay` — the leg that makes criterion #1's follow-up turn pass).

**2026-07-02 — Replay leg designed + reviewed (approve) → PIVOT surfaced → flight replanned
(6→7 legs).** Designed the replay leg (thinking-before-tool_use, signatures intact, DD8
strip-when-off). Design review returned **approve** — replay logic validated mode-agnostic +
correct; applied 2 low fixes (hermetic strip-off e2e test; degenerate empty-content thinking-only
note) + a 2-block ordering test. **The review also raised — and I then verified against
Anthropic's authoritative docs — that Leg 02's `budget_tokens` enablement 400s on Sonnet 4.6 + all
current models** (see Anomalies + the pivot Decision). Escalated; operator chose **adaptive-only,
on/off, effort deferred to A4**. **Replan:** the replay leg's approved design is **renumbered
Leg 04** (`legs/04-anthropic-thinking-replay.md`; replay logic unchanged — only its `_build_kwargs`
hoist now derives `thinking_active` from the new `thinking_enabled` resolver instead of
`budget > 0`). A **new Leg 03 `anthropic-adaptive-enablement`** is inserted to revise enablement +
config before replay. Remaining order: **03** adaptive-enablement → **04** replay → **05** web-UI
disclosure → **06** admin on/off enable field → **07** verify+HAT. `legs_completed` stays `2`
(Leg 02's *capture* + `enable_thinking` contract are correct and retained; its *enablement/budget*
code is superseded by Leg 03 — both uncommitted, so no history churn). The pre-Leg-03 live probe
recommendation is now moot for `budget_tokens` (removed); the adaptive-enablement live check moves
to the Leg 07 behavior test. Authoring Leg 03 (adaptive enablement) next.

**2026-07-02 — Leg 03 (`anthropic-adaptive-enablement`) designed + reviewed: approve with changes;
all applied.** Design review **independently re-verified the wire-format premise** against
Anthropic docs (adaptive is the on-mode for Sonnet 4.6+; budget_tokens hard-400s on Opus 4.8/4.7/
Fable 5, deprecated-but-functional on Sonnet 4.6; dropping DD6's `temperature=1`+`max_tokens`
forcing is sound — adaptive has no such constraint and the existing temp-retry covers newer models
rejecting temperature). All 8 review points checked; line refs exact; capture + `enable_thinking`
contract confirmed untouched. Findings applied: **[med]** blast-radius missed
`test_anthropic_live.py:217` (Leg 02 budget probe) → migrate it to `thinking_enabled=True` on a
4.6+ model (premise is mode-agnostic; keep, don't retire); **[med]** test-migration must swap the
module import at `test_anthropic_provider.py:29–33` or the module fails at collection → explicit
step added; **[low]** softened the Sonnet-4.6-400 wording (deprecated-not-rejected there); **[low]**
config-key-rename silent-change edge note added. Suggestions applied: explicit-`False`-short-circuit
resolver test; assert `temperature==0.0`/`max_tokens` unchanged as proof the DD6 forcing is gone.
Mechanical + reviewer-prescribed → no second pass. Leg 03 → `ready`; spawning Developer.
`[HANDOFF:review-needed]` (design finalized).

**2026-07-02 — Leg 03 implemented → `landed` (Flight-Director-verified).** Developer ripped out the
budget path and installed the adaptive-only boolean resolver; migrated the tests (incl. the module
import swap + the live probe). Developer ran the full suite to completion this time (no racing):
`3651 passed / 10 skipped / 1 failed` (known aiosqlite flake, isolation-clean) — matches the Leg 02
baseline, no regression. **My independent spot-check:** budget-symbol grep over `the_one/` = CLEAN;
adaptive enablement present (`{"type": "adaptive"}` at `:223`, `thinking_active` hoisted `:175`,
`resolve_extended_thinking`/`_EXTENDED_THINKING_ENV`/`config["thinking_enabled"]` in place);
`test_anthropic_provider.py` = 43 passed. Code review + commit deferred to Phase 2d.
`legs_completed = 3` (01 protocol, 02 capture+contract, 03 adaptive-enablement). Advancing to
**Leg 04 (replay)** — refreshed its stale pre-pivot refs against the settled code (`_to_api_message`
`:399`, assistant branch `:418`, loop call `:185`; the `thinking_active` hoist is done by Leg 03 so
Leg 04's `_build_kwargs` change reduces to threading `thinking_active` into the loop call; e2e tests
assert `{"type": "adaptive"}` + `thinking_enabled`). Spawning a fresh design review for Leg 04
against post-Leg-03 code (the prior "approve" predates two landed legs + the pivot).

**2026-07-02 — Leg 04 (replay) re-reviewed: approve with changes; all applied.** Fresh design
review against settled post-Leg-03 code confirmed the replay logic + all refreshed refs correct
(`:175` hoist, `:185` loop call, `:222` adaptive enablement, `:388`/`:399`/`:418`); guard-widening
correct across all four combinations; `_thinking_block_to_api` matches Anthropic's per-variant
shape + the stored `ThinkingBlock`; DD8 strip-when-off safe via the `False` default (~30 single-arg
callers stay byte-identical); ordering `[*thinking, text, *tool_use]` correct + mode-agnostic. Four
stale renumber cross-refs fixed (no code impact): 4× "Leg 06"→"Leg 07" (live-probe/HAT), the
Post-Completion progress entry "Leg 03"→"Leg 04", a Context line-ref `:410–447`→`:399–436`, and
pre-pivot "thinking budget" wording → "whether thinking is enabled". Reviewer's optional suggestion
(refresh the landed Leg-02 breadcrumb comment at `anthropic_provider.py:262` "Leg 03 replay"→"Leg
04") folded into the implement instructions. Mechanical → no second pass. Leg 04 → `ready`; spawning
Developer. `[HANDOFF:review-needed]` (design finalized).

**2026-07-02 — Leg 04 implemented → `landed` (Flight-Director-verified).** Developer added
`_thinking_block_to_api`, widened `_to_api_message` (guard `msg.tool_calls or (thinking_active and
msg.thinking)`; projects `[*thinking, text?, *tool_use]`), threaded `thinking_active` into the
`:184` loop call, refreshed the breadcrumb comments. +10 replay tests. The agent paused waiting on
its full-suite run; I resumed it (SendMessage) to collect the settled result rather than race the
tree — it reported `3661 passed / 10 skipped / 1 failed` (= 3651 baseline + 10 new; the 1 failure
is the known aiosqlite flake, isolation-clean). **My spot-check:** `test_anthropic_provider.py` =
53 passed; replay wiring confirmed (`_to_api_message(m, thinking_active)` `:184`,
`_thinking_block_to_api` `:398`, widened guard `:433`). **The full Anthropic backend chain is now
complete** (protocol → capture → adaptive enablement → replay); criterion #1's follow-up-turn
machinery is in place (autonomous/fixtured; live confirmation deferred to Leg 07). Code review +
commit deferred to Phase 2d. `legs_completed = 4`. Advancing to **Leg 05 (web-UI thinking
disclosure)** — pivot-independent full-stack UI; mapping current hook points (recon refs are weeks
old) before design.

**2026-07-02 — Leg 05 (web-UI disclosure) designed + reviewed: approve with changes; all applied.**
Explore agent mapped current hook points (planning refs mostly held; `usage`/`assistant` drifted).
Designed: a `thinking_display_text` helper + a `thinking` event in the codec `messages_to_ui_events`
ASSISTANT branch (replay) + a broadcast in `_process_and_broadcast` (live, reveal-after) +
`chat.js` handler/`renderHistory` branch/`renderThinking` + a `.thinking-disclosure` CSS class
(distinct from the `.msg.thinking` spinner). Design review verified every hook point against live
code; findings applied: **[high]** frontend was untested-until-Leg-07 → added a **MockProvider
thinking seam** (`config["response"]["thinking"]` → `ThinkingBlock`s) + a **required Playwright
browser test** driving the real disclosure (collapsed/expand/coexist-with-tool-trace/survive-reopen)
with no live key; **[med]** live emit → **broadcast-only** (interim-usage precedent, not
`add_event` — no functional diff, cleaner); **[med]** `renderThinking` made **position-independent**
(criterion #1's turn has empty `content` → no preceding bubble) + a codec test for the `content=""`
thinking+tool turn; **[low]** DD3 "above the answer" reconciled as HAT-tunable (v1 attaches with the
turn); **[low]** `renderThinking` tolerates both live/replay event shapes. Mechanical +
reviewer-prescribed → no second pass. Leg 05 → `ready`; spawning Developer.
`[HANDOFF:review-needed]` (design finalized).

**2026-07-02 — Leg 05 implemented → `landed` (Flight-Director-verified).** Developer built the
codec `thinking_display_text` helper + projection, the broadcast-only live `thinking` event, the
`chat.js`/`trace-shell.js` `renderThinking` (position-independent, distinct `.thinking-disclosure`),
the CSS, and the MockProvider thinking seam. **The [high] frontend gate is real:** a Playwright
browser test (`tests/browser/test_flow_chat_thinking_disclosure.py`) drives the disclosure via the
mock seam — collapsed default, expands, coexists with the tool trace, survives reopen. **My
spot-check:** codec suite 107 passed (12 new); browser disclosure test 1 passed; distinct
identifiers confirmed (`.thinking-disclosure`, `renderThinking` at `trace-shell.js:99`/`chat.js:701`,
`appendChild` position-independent, no spinner collision). Full suite `3673 / 10 / 1` (baseline 3661
+ 12 new; the 1 is the known aiosqlite flake). Code review + commit deferred to Phase 2d.
`legs_completed = 5`. Advancing to **Leg 06 (on/off admin toggle)** — the pivot turned the F09-05
"budget field" into an on/off "Extended thinking" toggle writing `config["thinking_enabled"]`;
reconning the current provider-editor hook points (num_ctx template) before design.

**2026-07-02 — Leg 06 (on/off admin toggle) designed + reviewed: approve with changes; all
applied.** Explore mapped the num_ctx field end-to-end (render/type-gate/collect/round-trip; all
refs accurate). Designed the "Extended thinking" checkbox gated to the `anthropic` type via
`showThinkingEnabled` on `TYPE_DEFAULTS`, writing `config["thinking_enabled"]` (bool). Backend
confirmed zero-change (opaque config passthrough + Leg 03's `_coerce_bool` read). Design review's
**[high] catch:** the provider-editor's dirty/snapshot/revert machinery is `.value`-based and
**blind to checkbox `.checked`** — a mirrored checkbox would render + save but never mark the form
dirty (Save stays disabled) + Cancel wouldn't restore it; the tools-editor checkbox idiom doesn't
transfer because it has its own checkbox-aware snapshot. Applied: explicit guidance-4b to patch
`getFormSnapshot`/listener-class/`Cancel-revert` + the `field-input` class + a guarding browser
assertion (toggle flips Save disabled→enabled). **[med]** `model_copy(update=data)` replaces
`config` wholesale → the "other keys survive" API test must seed a second key (`num_ctx`) in the
PUT body (preservation is client-re-send, not backend merge); **[low]** reworded the clobbering AC.
Checkbox idiom confirmed to exist (`checkbox-primary` + `readFieldValue`). Mechanical +
reviewer-prescribed → no second pass. Leg 06 → `ready`; spawning Developer.
`[HANDOFF:review-needed]` (design finalized).

**2026-07-03 — Leg 06 implemented → `landed` (Flight-Director-verified). ALL AUTONOMOUS LEGS
COMPLETE.** Developer added the anthropic-gated "Extended thinking" checkbox + the checkbox-aware
dirty machinery (`getFormSnapshot`/revert). **My spot-check:** browser provider-editor suite 26
passed (6 new incl. the Save-disabled→enabled dirty guard), provider-API suite 126 passed (2 new
round-trip), `showThinkingEnabled: true` on the anthropic `TYPE_DEFAULTS` entry, checkbox-aware
snapshot `:210` + revert `:319` confirmed. Full suite `3675 / 10 / 1` (baseline 3673 + 2 new API;
the 1 is the known aiosqlite flake). `legs_completed = 6/6` autonomous.

**2026-07-03 — Phase 2d: consolidated flight review begins.** All six autonomous legs (01–06) are
implemented and uncommitted (commit deferred to this phase per the batch-commit workflow). Diff
scope: ~1675 insertions across 25 source/test files + 1 new browser test + the flight artifacts.
Spawning a single **Reviewer** over the ENTIRE uncommitted diff (objective — no Developer
reasoning). **FD model decision:** using **Sonnet** (not the crew-default Haiku) for this review —
the diff is large and touches the `LLMProvider` contract, signature replay, and WS events; Haiku
would under-serve a single-gate review of this scale. Not Opus (per the never-Opus-Reviewer rule).
Leg 07 (verify + guided HAT) is interactive/human-driven and runs AFTER the commit.

**2026-07-03 — Phase 2d review: `[HANDOFF:confirmed]` — zero blocking issues.** The Sonnet
Reviewer verified all seven high-risk areas PASS (signature replay + strip-when-off; the
`enable_thinking` contract across all providers + `base.stream` forwarding + all test doubles;
codec byte-identity with the tripwire green unchanged; adaptive-only enablement with **zero
`budget_tokens` residue in `the_one/`**; broadcast-only WS thinking event not in `result_messages`;
the checkbox-aware dirty machinery backward-compatible), mission constraints intact
(`Message.content`-always-`str`, `StreamChunk` untouched, mock + credential-store preserved), no
secret/identity leakage, tests meaningful with no xfails. Two non-blocking findings: (1) the
behavior spec used pre-pivot "budget" terminology → **fixed** (Preconditions/Step-2/both Variants
now reference the on/off toggle, adaptive-only, Sonnet 4.6+); (2) the live thinking broadcast omits
`visibility` — cosmetic, consistent with other derived live events (usage/done), left as-is.

**2026-07-03 — Flight committed (Phase 2d).** Legs 01–06 → `completed`; checked off in `flight.md`;
committed all code + tests + artifacts on `flight/10-extended-thinking-support`. Flight remains
`in-flight` pending **Leg 07 (verify + guided HAT)** — the live behavior test on a real Anthropic
(adaptive) model + the guided HAT session, which run interactively with the operator. Draft PR to
follow.

**2026-07-03 — Leg 05 (`web-ui-thinking-disclosure`) implemented → `landed`.** The DISPLAY side:
captured thinking now surfaces in the web chat as a collapsed-by-default `<details>` disclosure per
assistant turn — emitted live at turn-settle (DD2 reveal-after) and re-projected on chat reopen from
persistence — reusing the tool-trace disclosure idiom with DISTINCT identifiers (never the active
`.msg.thinking` loading spinner). No provider/protocol change; keys on `Message.thinking` (DD5
provider-agnostic).

- `the_one/db/codec.py`: added `thinking_display_text(blocks)` — the single source of truth for the
  UI's reasoning string (joins `type=="thinking"` text; `[reasoning redacted]` for redacted-only;
  `""` otherwise; signatures/data never projected). `messages_to_ui_events` ASSISTANT branch now
  emits `{"type":"thinking","content":<text>,"parent_message_id":f"replay-msg-{i}",**vis}` AFTER the
  assistant-content event, BEFORE tool_calls — only when the text is non-empty (no-thinking turns
  project byte-identically).
- `the_one/interfaces/web/app.py`: imported `thinking_display_text`; `_process_and_broadcast`
  BROADCASTS a live `thinking` event when a settled assistant `msg` has displayable thinking —
  broadcast-only (NO `session.add_event`; interim-usage precedent, reopen re-derives from the codec)
  and NOT in the REST `result_messages` payload.
- `the_one/interfaces/web/static/js/areas/chat/trace-shell.js`: added `renderThinking(evt)` — builds
  a collapsed `<details class="thinking-disclosure" data-testid="thinking-disclosure">` with a
  `summary.thinking-toggle` "Thinking" + a `.thinking-body`; tolerates missing
  `parent_message_id`/`vis` (live shape).
- `the_one/interfaces/web/static/js/areas/chat.js`: a `thinking` ws-handler branch (calls only the
  local `renderThinking` + `scrollToBottomIfPinned` — NOT `hideThinking`/`finalizeStreamingBubble`),
  a `thinking` branch in `renderHistory`, and a position-independent local `renderThinking` that
  appends to `messagesEl` in stream order (mirrors `getOrCreateTrace`; criterion #1's empty-content
  turn has no preceding bubble). Distinct from `createThinking`/`removeThinking`/`showThinking`/
  `hideThinking` (untouched).
- `the_one/interfaces/web/static/css/chat.css`: added a `.thinking-disclosure` rule block reusing
  the trace-shell disclosure visual pattern (border-left, muted mono summary, custom triangle);
  `.msg.assistant.thinking` (spinner) untouched. Existing edited assets are auto-cache-busted (no
  `index.html` edit; no new static file).
- `the_one/llm/mock.py`: dev-mode thinking seam — `_thinking_from_response` parses an optional
  `config["response"]["thinking"]` (list of block dicts) into `[ThinkingBlock(**b)]` on the
  synthesized assistant `Message` in both `complete()` and `stream()` (mirrors the existing
  `tool_calls` read); `enable_thinking` stays accepted-and-ignored.
- `tests/browser/seeders.py`: `seed_mock_agent` gains an optional `max_iterations` param (bounds the
  static-mock tool loop for the browser test).

**Test results:** `tests/test_db_codec.py` — **107 passed** (12 new: `TestThinkingDisplayText` ×6 +
`TestMessagesToUiEventsThinking` ×6, incl. the `content=""` thinking+tool_calls turn and the
no-thinking byte-identity tripwire). Required browser test
`tests/browser/test_flow_chat_thinking_disclosure.py` (`-m browser`) — **1 passed**: via the
MockProvider seam, the `.thinking-disclosure` `<details>` renders collapsed, expands on toggle,
coexists with the `.trace-shell` (not nested), and survives a page reload / chat reopen (history
replay). Full `make test-unit` — **3673 passed, 10 skipped, 1 failed** (= 3661 baseline + 12 new;
the 1 failure is the known carried aiosqlite teardown flake
`test_lifespan.py::test_lifespan_drains_session_registry`, isolation-clean 1/1 — not a regression).
Code review + commit deferred to Phase 2d. `legs_completed = 5`. `[HANDOFF:review-needed]`.

**2026-07-03 — Leg 06 (`thinking-enable-admin-field`) implemented → `landed`.** The OPERATOR-SURFACE
side (last code leg): an "Extended thinking" on/off checkbox in the Studio provider editor, gated to
the `anthropic` type, default off, writing the bool `config["thinking_enabled"]` that Leg 03's
resolver already reads. Mirrors the F09-05 `num_ctx` field end-to-end (render / type-gate / collect /
round-trip) as a checkbox. **No backend change** — grep confirmed `config` is opaque passthrough
(`models.py:29`, `api.py` create/update `model_copy` merge) and `anthropic_provider.py:135-136,175`
already reads the key via `_coerce_bool` → `resolve_extended_thinking`. Masked-api-key handling
untouched.

- `the_one/interfaces/web/static/js/areas/admin/provider-editor.js`: render an `#pf-thinking-enabled`
  checkbox (`class="field-input checkbox-primary"`, `data-field="config.thinking_enabled"`) after the
  num_ctx block, wrapped in `.field-row.admin-pf-thinking-enabled` (`is-hidden` gated on
  `defaults.showThinkingEnabled`), `checked` iff `provider.config.thinking_enabled`, with the
  label + focusable `.field-info-icon` tooltip + `aria-describedby` + visually-hidden desc a11y idiom
  (mirrors num_ctx). Type-change handler toggles the row's `is-hidden` on `!defaults.showThinkingEnabled`.
  Collect-on-save: when `defaults.showThinkingEnabled`, always-persist
  `payload.config.thinking_enabled = !!(teInput && teInput.checked)`.
- **Guidance-4b (the [high] load-bearing fix): made the `.value`-based dirty machinery checkbox-aware.**
  `getFormSnapshot` now reads `el.type === 'checkbox' ? el.checked : el.value` (backward-compatible);
  the `field-input` class makes the existing `.field-input, .field-select` change/input listener fire
  on the checkbox (no extra listener needed); Cancel-revert now sets `.checked` for checkbox fields.
  Without these the toggle would render + save but never mark the form dirty (Save stays disabled) and
  Cancel wouldn't restore it.
- `the_one/interfaces/web/static/js/areas/admin.js`: added `showThinkingEnabled: true` to the
  `'anthropic'` `TYPE_DEFAULTS` entry (only) — the gate.

**Test results:** `tests/test_provider_api.py` — **126 passed** (2 new: anthropic create round-trips
`config.thinking_enabled == true`; PUT with a `__MASKED__` key + full config re-send
[`thinking_enabled` + `num_ctx`] preserves the stored key and round-trips BOTH config keys, pinning
the client-re-send contract since `model_copy(update=data)` replaces `config` wholesale). Browser
`tests/browser/test_flow_provider_editor.py` (`-m browser`) — **26 passed** (6 new: toggle visible +
unchecked default for anthropic; hidden for non-anthropic; info-icon tooltip + `aria-describedby`
a11y; **toggling the checkbox flips Save disabled→enabled** [guards the 4b snapshot patch]; save +
reload → checked; Cancel after toggling reverts). Full `make test-unit` — **3675 passed, 10 skipped,
1 failed** (= 3673 baseline + 2 new API tests; the 1 failure is the known carried aiosqlite teardown
flake `test_lifespan.py::test_lifespan_drains_session_registry`, isolation-clean 1/1 — not a
regression). Code review + commit deferred to Phase 2d. `legs_completed = 6` (all autonomous code legs
landed). `[HANDOFF:review-needed]`.

**2026-07-03 — Leg 07 (verify + guided HAT) → `completed`; FLIGHT LANDED. `[COMPLETE:flight]`.**
Ran the `extended-thinking-tool-turn` behavior test live on Sonnet 5 (Witnessed pattern; Executor +
Validator, both Sonnet) → **PASS 6/6**. Both Mission 16 extended-thinking criteria confirmed live
(thinking+tool replay incl. multi-turn stability; disclosure renders + survives reload with text
matching persistence). The HAT surfaced + fixed **two live-only defects** the fixtured suites could
not: (1) the operator's `:8485` dev process predated the flight-10 backend (served new static JS
while running old Python) → restart; (2) `thinking.display` defaults to `"omitted"` on Sonnet 5 →
signed-but-empty thinking text → empty disclosure → fixed inline to `{"type":"adaptive","display":
"summarized"}` (see Decisions; signature identical → replay unaffected). Three toggle-UX findings
(iPhone switch / `label (i)` icon / "a model" tooltip) fixed inline (commit `7735b88`). Optional
disabled + mixed-session(DD8) variants skipped per operator (hermetic-unit-test-covered). Artifacts
finalized: Leg 07 → `completed`; flight status `in-flight → landed`; both criteria checked in
`flight.md` + `mission.md`; Flight 10 marked LANDED in the mission Flights list; behavior spec →
`active` (+ Validator spec-quality tweaks); `agents.md` `message-thinking-field` convention added;
run log at `tests/behavior/extended-thinking-tool-turn/runs/2026-07-03-12-14-26.md`. Committing the
`display:"summarized"` fix + run log + artifacts, then opening the draft PR. Flight debrief
(`/flight-debrief`) will transition `landed → completed`.
