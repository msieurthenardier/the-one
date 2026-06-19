# Flight Log: Open-Model Tool-Use Robustness — Text-Form Tool-Call Recovery (#105)

**Flight**: [Open-Model Tool-Use Robustness (#105)](flight.md)

## Summary

Planning. Spec authored from issue #105 + the Flight 1 spike (`leg 02`, which confirmed the
capability gate is correct and captured the real loose format — a ` ```tool ` fenced
Python-call block — from live gemma3:4b). Direction ratified with the operator: a pure
text-form tool-call recovery kernel wired into the Ollama adapter (all three formats —
gemma fenced Python-call first-class, Hermes tags, bare-JSON), recovering into structured
`ToolCall`s that the existing agent loop dispatches unchanged. Verification: fixtured units +
a live gemma marker test + a behavior test. Optional HAT included.

---

## Reconnaissance Report

Upstream source: GitHub issue **#105**, which cites specific code locations. Verified against
current code at planning (2026-06-18):

| Item (from #105) | Classification | Evidence | Note |
|---|---|---|---|
| Capability gate drops tools for Gemma — `ollama_provider.py:71-79` | `confirmed-live` | `supports_tools()` at `:71-79`, Gemma-style models → `False` | Gate is CORRECT (spike: Ollama 400s if tools offered). Keep. |
| Loop drops all schemas + single-shot when no tools — `agent/core.py:167-188` | `confirmed-live` (refined) | Logic at `:177-238`; `supports_tools` gates only the wire `tools=` array (`:185-188`) | **Key refinement:** dispatch `if not response.tool_calls: return` / `_dispatch_tool_calls(...)` at `:225-235` is **unconditional** of `supports_tools` → recovering into `tool_calls` is dispatched even in degraded mode. No loop change needed (DD6). |
| `complete()` parses only structured `tool_calls` — `ollama_provider.py:117-129` | `confirmed-live` | `:117-129` reads `msg.get("tool_calls")` only | The recovery wire point (DD2). |
| `stream()` parses only structured `tool_calls` — `ollama_provider.py:197-228` | `confirmed-live` | `:197-228` accumulates `delta.tool_calls` only | The streamed recovery wire point. |
| "no tools" degradation documented — `the_one/agents.md:798` | `drifted` | `agents.md:798` is now the subprocess-env-invariant section | The degradation note moved; re-locate when updating docs in the Post-Flight doc step. |

Decision: all items proceed as live work (the gate item proceeds as "keep as-is, do not
offer tools"). No retirements. The `agents.md` citation drift is a doc-update detail, not a
scope change.

---

## Flight Director Notes

- 2026-06-18 — `/flight` planning started for Flight 3 (#105). Pulled in #105 as the primary
  issue; excluded the UI copy-button / #117 / #122-enhancement items (UI surface, out of
  mission scope). Reused the Flight 1 spike's captured gemma fixture.
- **Central design question resolved at planning (DD6):** provider-side recovery is
  sufficient — the agent loop dispatches `response.tool_calls` unconditionally (`core.py:225-235`).
  Flight stays within the mission's "agent loop untouched" boundary (`the_one/llm/` only).
- **Operator design decisions (interview):** (1) cover all three text-form formats, gemma
  first-class; (2) verification = fixtured units + live gemma marker test + behavior test;
  (3) include the optional HAT/alignment leg.
- **One question deliberately left live:** DD5 degraded round-trip serialization (does gemma
  400 on tool-call/tool-role history with `tools=None`?) — deferred into `leg 03` with a
  pre-authorized `_to_api_message` plain-text adaptation, mirroring Flight 2's live-probe-
  resolves-open-question pattern.

---

## Decisions

### Test invocation is host-native, NOT `docker exec` (Flight Director, 2026-06-18)
**Context**: The `leg-execution.md` crew "Implement" prompt hard-codes
`docker exec the-one pytest …`. The leg-01 design-review Developer cross-referenced the actual
repo and found this is wrong for this environment: the Makefile runs all tests **host-native**
via `scripts/run-tests.sh` (`PY := .venv/bin/python`), and `run-tests.sh` exists *specifically
because* `docker exec … pytest` orphans subprocesses. Verified directly: `docker` is not even
available in this WSL distro, so the crew-prescribed command would fail outright.
**Decision**: The Flight Director overrides the crew prompt's test-invocation line for every
Developer spawn — use `PYTHON=.venv/bin/python bash scripts/run-tests.sh <files> -x --timeout 30`
for scoped runs and `make test-unit` for the hermetic suite. (Per the project CLAUDE.md
skill-boundary rule, crew prompts are scaffolding; the SKILL/Director carries the protocol.)
**Impact**: All legs this flight. Flagged for the debrief: the crew file's Implement prompt
should be corrected to the host-native form (or the discrepancy reconciled with whatever
environment it was written for).

### DD5 resolved LIVE — structured degraded round-trip is ACCEPTED by gemma3:4b (leg 03, 2026-06-18)
**Question** (deliberately left live at planning): does a follow-up request whose history carries
an assistant `tool_calls` block **and** a `role:"tool"` result get accepted by live gemma3:4b
when `tools` is **omitted** (the non-tool-capable degraded path)?
**Probe** (throwaway `/tmp/the-one-degraded-probe/probe.py`, run via `.venv/bin/python`):
`OllamaProvider(model="gemma3:4b", base_url="http://localhost:11434/v1")` with
`supports_tools()` → **False**, `complete(history)` called with **no `tools=` arg** (so the
`if tools:` guard is falsy and the `tools` key is omitted entirely from the payload).
The exact wire `messages` sent (verbatim from the probe, `tools` key absent):
```json
[
  {"role": "user", "content": "What's the weather in Paris?"},
  {"role": "assistant", "content": null,
   "tool_calls": [{"id": "get_weather_0", "type": "function",
     "function": {"name": "get_weather", "arguments": "{\"city\": \"Paris\"}"}}]},
  {"role": "tool", "tool_call_id": "get_weather_0", "content": "Sunny, 24°C"}
]
```
**Observed result — ACCEPTED (2xx, model replied):** no `HTTPStatusError`; the model returned a
coherent assistant message (`reply.content` a multi-line Paris weather report beginning
`"Okay, here's the current weather information for Paris, France:\n\n..."`; `reply.tool_calls == []`).
Live Ollama does **not** 400 on tool-call / tool-role history when `tools` is omitted — it only
400s when tools are *offered* (the Flight 1 spike's finding). 
**DD5 resolution**: this is the flight prior's **likely outcome** (clean round-trip) → **NO
production code change**. The pre-authorized `_to_api_message` plain-text adaptation + capability
gate are **NOT applied** (they were conditional on rejection). `_to_api_message` keeps its
structured degraded serialization unchanged. The validated contract is pinned by a new hermetic
test `tests/test_ollama_degraded_roundtrip.py`
(`test_degraded_followup_history_serializes_structured`) so a future refactor cannot silently
break the round-trip. No re-probe needed (re-probe is the rejection-branch-only criterion).

### the-one runs HOST-NATIVE, not in Docker (operator correction, 2026-06-18)
**Context**: At leg 05 the Flight Director initially inferred (from `docker-compose.yml`'s
bind-mount + `--reload` config, the absence of a visible host process, and no docker CLI in this
WSL distro) that the running `:8484` instance was a Docker Desktop container, and reasoned about a
container-boundary canary-observability problem for the behavior test.
**Operator correction**: the-one does **not** run in Docker — it runs host-native. The
`docker-compose.yml` in the tree does not describe the live deployment and is itself flagged as
incorrect/to-be-updated.
**Impact**: (1) Reinforces the host-native test-invocation decision above (the crew file's
`docker exec the-one pytest` is doubly wrong — there is no container). (2) The behavior-test
(leg 05) host-canary observable has **no boundary to cross** — the spec apparatus holds as written.
**Flagged for the debrief**: the project's docker-oriented scaffolding (`docker-compose.yml`, the
crew Implement prompt) misrepresents the actual host-native runtime and should be reconciled (a
doc/infra cleanup, out of this flight's scope).

### FIX-BOTH on the leg-05 behavior-test failure — minimal agent-loop-boundary exception (operator-directed, 2026-06-19)
**Context**: The leg-05 behavior test failed end-to-end on two real-world mismatches (see Anomalies):
(1) gemma's ` ```tool_code ` fence is unrecognized; (2) gemma's positional call syntax (`shell("…")`)
can't bind to the tool's named `command=` param. The operator was presented the disposition options
(fix-both / fix-tool_code-only / land-as-known-issue / rethink) and chose **fix both, re-run**.
**Decision**: New **leg 07 `gemma-toolcode-positional-fix`**:
- (1) Add `"tool_code"` to `_toolcall_recovery.py` `_FENCE_TAGS_TO_PARSE` (pure kernel — in
  `the_one/llm/`, fully in mission scope).
- (2) Add a **schema-aware** `bind_positional_args()` on the `Tool` base (`the_one/tools/base.py`) that
  maps recovered `__positional_args__` onto the tool's `parameters.properties` names in declaration
  order; apply it at the dispatch site `the_one/agent/core.py:_execute_tool` with a **one-line** change
  (`tool.execute(**tool.bind_positional_args(tool_call.arguments))`).
**Mission-constraint note**: this is the flight's first touch of `the_one/agent/core.py`. The mission
forbids "changing the agent loop's **iteration/auth-pause logic**" — this change is neither; it is a
single arg-normalization call at the tool-dispatch site, with the binding logic living in the tools
layer. No framework added; `LLMProvider` contract + provider-shape-portability preserved. Recorded as a
**deliberate, minimal, operator-authorized exception** to the flight's working "agent loop untouched"
convention (DD6), narrowly scoped to arg marshaling. **Re-run the behavior test after the fix; the leg-05
test must pass before the flight lands.**

### DURABLE FIX → leg 08, with a deliberate MISSION-boundary expansion into `the_one/agent/` (operator-directed, 2026-06-19)
**Context**: Two behavior-test runs (leg-05 baseline + the leg-07 re-run) independently concluded that
recognizer-based recovery is best-effort, not reliable, for gemma3:4b — the non-tool model improvises a
new tool-call serialization nearly every turn (Python-call, JSON-array-of-`{tool_name,query}`, bare
`search_tools`, pseudo-Python). The Validator's guidance: the durable fix is **upstream** of the
recognizer (constrain/instruct the model's output), not another recognizer.
**Investigation (Explore map)**: the `search_tools` discovery protocol + system prompt are
**unconditional** (no `supports_tools` branch); BASE_PROMPT (`config.py:9-54`) gives **no concrete
tool-call format**; and for a degraded model the agent loop forces `tool_schemas=[]`
(`core.py:185-188`), so the provider never gets the tool catalog. Therefore a reliable "instruct the
model with the exact format + the available tools" fix **cannot** live in `the_one/llm/` alone — it
needs an agent-layer seam. Ollama `format`/grammar can't be applied conditionally (can't force a
tool-call JSON on every conversational turn), so it's not the primary lever.
**Operator decision**: pursue the durable fix **as a new leg (08) in flight 3, full design first**,
**accepting a deliberate expansion of the MISSION scope** (the mission scoped `the_one/llm/` + Message
protocol + codec; this leg touches `the_one/agent/`). 
**Design (leg 08)**: in the agent loop's existing degraded branch (`core.py:185-188`, the
`else: tool_schemas=[]` path — and note the stale "single-shot chat" comment at `:171-176` the flight
already flagged), when `supports_tools()` is False, inject a **direct tool protocol** into the request:
list the available tools (the registry catalog, since `search_tools` discovery is unreliable for these
models) + pin ONE exact format — ` ```tool_code\nname(arg="value")\n``` ` (keyword args; matches the
kernel's `tool_code` fence + leg-07 binding). The wire `tools=` stays `None` (Ollama still 400s on
offered tools). The model now KNOWS the tools and the format → emits a deterministically-parseable call
→ the existing recovery kernel lifts it. **Recorded as a deliberate, operator-authorized mission-scope
expansion**, narrowly: tool-exposure/prompt for non-tool-capable models, not the iteration/auth-pause
logic. Re-run the behavior test; the leg-05 test must pass before the flight lands.

_(Other decisions: none yet.)_

---

## Deviations

### DIVERSION — full Docker removal folded into Flight 3 (operator-directed, 2026-06-18)
**Planned**: Flight 3 scope is confined to `the_one/llm/` recovery work (#105); the flight plan
has 5 legs + an optional HAT, none touching deployment/infra.
**Actual**: At leg 05 (behavior test), the Flight Director discovered the repo still carries a
full Docker deployment scaffold (`Dockerfile`, `docker-compose.yml`, `.dockerignore`, a
Docker-based Makefile "Container lifecycle" section, a `docker exec` line in the
`leg-execution.md` crew prompt, and Docker-as-deployment prose in `CLAUDE.md`, `SECURITY-MODEL.md`,
`tests/HAT.md`, and two `scripts/`), **even though Docker was retired in favour of the Windows
installer / host-native runtime a prior mission.** This stale scaffold actively misled the Flight
Director into believing the running `:8484` instance (actually the operator's host-native Windows
app) was a container, and is "causing problems" (operator's words).
**Reason / decision**: The operator directed a **full rip-out of all deployment-Docker scaffolding
with host-native replacements**, **folded into the flight/03 branch** (not a separate PR), to be
done **before** finishing the leg-05 behavior test (the test needs a clean host-native launch).
Acknowledged by the operator as a **necessary flight diversion**. Tracked as new **leg 06
`docker-removal-host-native`** added to the flight. Boundaries: remove only *deployment* Docker;
**preserve** (a) tool-execution **sandbox**-Docker references (a different subsystem) and (b)
**historical** artifacts under `missions/**` and `tests/behavior/**/runs/**` (snapshots, not living
config). Recovery work (legs 01–04) is unaffected — it never touched deployment.

---

## Anomalies

### Doc drift: "single-shot / single iteration" wording is stale for the recovery path
**Observed** (architect design review, 2026-06-18): `the_one/agent/core.py:172-173` comments
"run as a single-shot chat" and `agents.md` says the degraded path "runs a single LLM
iteration as plain chat." This is **false once tool calls are recovered**: the only degraded-
mode early-exit is `if not response.tool_calls: return` (`:225-226`), so a recovered call is
dispatched and the loop **re-iterates** (the follow-up turn carries the tool result). The code
is correct; the *documentation* is stale and would mislead a reviewer of the recovery wiring.
**Severity**: cosmetic (no code impact). **Resolution**: fix both the `core.py` comment and the
`agents.md` sentence in the Post-Flight documentation step (Completion Checklist), alongside
the degradation-note update.

### Behavior test FAILS end-to-end — real gemma uses ` ```tool_code ` fence + positional args (leg 05, 2026-06-19)
**Observed** (Witnessed behavior-test run `gemma-tool-use-recovery/runs/2026-06-19-00-27-41.md`,
against a host-native dev instance on :8585 serving this branch): a real gemma3:4b agent turn through
`/api/chat`, asked to use its shell tool, emitted `` ```tool_code\nshell("echo recovered-ok > …")\n``` ``
— **no tool dispatched, raw block not stripped, canary never written** (the literal #105 failure shape).
Validator concurred (CP1 pass / CP2 fail / CP3 fail / CP4 pass).
**Root cause — TWO independent real-world mismatches the fixture-based design missed:**
1. **Fence tag `tool_code` unrecognized.** `_toolcall_recovery.py:60` `_FENCE_TAGS_TO_PARSE =
   {"", "tool", "python", "py"}` excludes `tool_code` (Gemma's documented tool-call fence).
   `recover_tool_calls()` returns `[]` for it; a `` ```tool `` control with the same body recovers.
2. **Positional call syntax unbound.** gemma emits `shell("…")` (positional); the kernel parks it under
   `__positional_args__` (leg-01 known limitation), and `core.py:334-335` `tool.execute(**arguments)`
   can't bind it to `ShellTool`'s required `command=`. So even with `tool_code` recognized, the call
   errors on arg binding. Nothing maps `__positional_args__` → named params (sentinel referenced only
   in `ollama_provider.py`).
**Why earlier tests passed**: the Flight-1 fixture + leg-04 live test used the ` ```tool ` fence with a
*keyword*-arg call (`get_weather(city='Paris')`), and leg-04 *forced* the `tool` label via a directive
prompt. Real gemma differs on **both** axes. Hermetic units + a directed live test cannot catch this;
the end-to-end behavior test did (working as intended).
**Severity**: blocking for the #105 acceptance criterion ("a tool-using conversation with Gemma via
Ollama reliably executes tool calls") — NOT met end-to-end. **Scope tension**: fix (1) is in-scope
(`the_one/llm/`); fix (2) needs schema-aware positional→named mapping, which the schema-less kernel
(DD1) can't do — it implicates the provider (no degraded-wire schema) or `the_one/agent/core.py`
(mission scopes the agent loop as untouched). **Disposition: operator decision (in progress).** The
leg does not land while the behavior test fails (agentic-workflow rule).

---

## Session Notes

- 2026-06-18 — Spec authored (planning). Behavior-test spec drafted
  (`tests/behavior/gemma-tool-use-recovery.md`, status `draft`).
- 2026-06-18 — Architect design review (Phase 5b): **approve with changes**. DD6 boundary
  claim verified correct (loop dispatches recovered `tool_calls` unconditionally, re-iterates;
  no agent-loop change). Incorporated (additive — skipped 2nd cycle):
  - [high→cosmetic] recorded the "single-shot" doc-drift anomaly + scheduled the `core.py:172`
    + `agents.md` fix in the Post-Flight doc step.
  - [med] DD5 now names **both** `_to_api_message` branches the plain-text adaptation must
    change (assistant `tool_calls` → inline text; `role:"tool"` → `role:"user"` prose) + the
    gating signal; `leg 03` updated.
  - [med] `leg 02` now states the **explicit** recovery insertion points (esp. stream(): after
    `acc.finalize_tool_calls()` `:225-228`, before the final `Message` `:230` — not inside the
    loop) + pins the `ToolCall.id → ToolResult.tool_call_id` invariant.
  - [low] DD3 pins positional-arg handling (`arguments["__positional_args__"]` + WARN, never
    dropped); added DD5a (no per-turn recovery cap; multi-call ordered list).
  - [low] behavior test gained a step 0 (confirm/create the gemma+shell agent), a shell-tool
    guard in step 1, and a one-shot directive re-prompt before INCONCLUSIVE.
  - `leg 04` now also asserts the raw block is stripped from `Message.content`.
- 2026-06-18 — Flight status → **ready** (operator-confirmed). Pre-flight checklist satisfied;
  DD5 degraded-round-trip question deliberately deferred into `leg 03`. Planning artifacts are
  currently untracked on the `flight/02` branch (will not enter PR #127); at execution start
  they branch from `main` as `flight/03-open-model-toolcall-recovery` and are committed there.
  Next: run `/agentic-workflow flight 3, mission 16, the-one` to execute.
- 2026-06-18 — `/agentic-workflow` execution started. Flight Director (Mission Control)
  orchestrating. Branched `flight/03-open-model-toolcall-recovery` from `main` (flight/02 is
  unmerged but independent — Anthropic schema vs Ollama recovery — per the planning note).
  **Flight-start prerequisites verified:** local Ollama reachable with `gemma3:4b` pulled
  (capabilities `['completion','vision']` — no `tools`, confirming the `supports_tools()=False`
  degraded path this flight targets); the-one app responding at `:8484` (HTTP 200). Flight
  status → **in-flight**. Loaded crew from `.flightops/agent-crews/leg-execution.md` (Developer
  Sonnet / Reviewer Haiku). Per the deferred-review model, leg design is reviewed per leg, but
  code review + commit are batched after the last autonomous leg. Execution plan: legs 01–02
  (kernel + adapter wiring) are standard autonomous; leg 03 (degraded-roundtrip-probe) and leg
  04 (live-verify-gemma) need the live model already verified present; leg 05 runs via the
  `/behavior-test` skill directly (not a spawned Developer); leg 06 (HAT) is operator-driven and
  optional. Committed planning artifacts as the branch foundation.

---

## Leg Progress

### `toolcall-recovery-kernel` (leg 01) — landed (2026-06-18)

**Built**: the pure, stdlib-only recovery kernel `the_one/llm/_toolcall_recovery.py`
(`recover_tool_calls(content: str) -> list[dict]` + private per-format helpers) and its
exhaustive hermetic unit suite `tests/test_toolcall_recovery.py`. The Ollama provider was
deliberately not touched — wiring is leg 02.

**Result**: scoped run green —
`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_toolcall_recovery.py -x --timeout 30`
→ **19 passed**. Import-discipline and no-`eval` grep gates both pass: the module imports only
`ast`, `json`, `logging`, `re` (+ `__future__`), and `grep -n 'eval('` shows only
`ast.literal_eval` (never builtin `eval`). `make test-unit` run at the end to confirm no
hermetic regressions across the full suite.

**Notable decisions**:
- **Dispatch order** implemented as Hermes → fenced Python-call → whole-content bare-JSON, with
  *first non-empty recognizer wins* (its full list returned, no merge across recognizers). Each
  recognizer is a private helper wrapped in try/except at the dispatch level so a malformed match
  contributes nothing rather than raising — `recover_tool_calls` is total over `str`. Within-format
  multi-call works (a recognizer returns all its own matches); cross-format mixed multi-call is
  deliberately out of scope and pinned by `test_cross_format_first_recognizer_wins`.
- **Positional-arg sentinel**: positional args are carried under the reserved key
  `arguments["__positional_args__"]` (exported as `POSITIONAL_ARGS_KEY` for leg 02's dispatcher to
  reference rather than re-typing the literal) and a WARN is logged. Positional and keyword args
  coexist in the same dict. A `**kwargs` splat (`kw.arg is None`) is treated as non-recoverable
  (returns `None`).
- **Hermes nested-object matching**: the tag regex `<tool_call>\s*(.*?)\s*</tool_call>` with
  `re.DOTALL` matches up to the *closing tag*, not the first inner `}`, so a nested object inside
  `arguments` survives intact (pinned by `test_hermes_nested_object_arguments`). Tags with invalid
  JSON or missing `name` are skipped, not raised.
- **Bare-JSON tightest gate**: only fires when `content.strip()` starts with `{` and the whole
  content parses to a tool-call-shaped dict — never mid-prose (`test_bare_json_only_whole_content`).
  Accepts `{name,arguments}`, the `{type:function,function:{...}}` wrapper, and
  `{tool|function, arguments|parameters}` shapes via a shared `_normalize_json_call` (also used by
  the Hermes path).
- **Dotted callee**: `_callee_name` reconstructs the full dotted `Attribute` path
  (`tools.get_weather`) and preserves it as the name; downstream resolves it.

### `wire-into-ollama-adapter` (leg 02) — landed (2026-06-18)

**Wired**: the leg-01 recovery kernel into `OllamaProvider`. When a response carries **no**
structured `tool_calls` but its content holds a recognizable text-form call, the provider now
recovers it into `ToolCall`s and strips the recognized block from the returned content — in
**both** `complete()` (after the structured-parse loop, before `Message.assistant(...)`) and
`stream()` (after `acc.finalize_tool_calls()`, **outside** the `async for` loop, before the
final `Message`). The agent loop and `_to_api_message` were deliberately left untouched (leg 03
owns the degraded round-trip).

**Strip approach (Option B, pinned)**: extended the kernel with
`recover_and_strip(content) -> tuple[str, list[dict]]` doing recovery **and** span-stripping in
one pass; `recover_tool_calls` became a thin wrapper that drops the stripped-content half (its
signature and all 19 existing kernel tests preserved). Each recognizer (`_recover_hermes`,
`_recover_fences`, `_recover_bare_json`) now uses `finditer`/explicit spans and returns
`(calls, spans)`; the dispatch-winner's spans are removed by a stdlib `_strip_spans` helper
(whitespace-only remainder → `""`). The kernel stayed stdlib-only. The adapter helper
`_recover_into_tool_calls` holds **no** marker knowledge — its only added responsibility beyond
calling `recover_and_strip` is mapping each dict → `ToolCall` with a synthesized stable id
`f"{name}_{index}"` (deliberately more collision-safe than the structured path's bare-name
fallback: two same-name recovered calls get distinct ids `get_weather_0` / `get_weather_1`).
`arguments` (including the `__positional_args__` sentinel) passes through verbatim — the
dispatcher special-cases it, not the provider.

**Result**: scoped run green —
`tests/test_ollama_provider_recovery.py tests/test_toolcall_recovery.py tests/test_ollama_provider_auth.py tests/test_ollama_api.py -x --timeout 30`
→ **85 passed** (15 new adapter tests in `test_ollama_provider_recovery.py` + 8 new
`recover_and_strip` kernel tests in `test_toolcall_recovery.py`). Full hermetic suite
`make test-unit` → **3261 passed / 18 skipped** (was 3238/18 after leg 01; the +23 are this
leg's new tests — no regressions).

**Notes / intentional limitation (DD4 scope)**: the per-delta `StreamChunk`s already yielded
during streaming carry the **raw, un-stripped** content — the recognized block briefly shows in
the live-streamed text. Recovery and stripping run **once** on the fully-accumulated content
*after* the loop, so only the **final** message (the one the session persists and the agent loop
dispatches) carries the stripped content + recovered calls. Interim deltas are not retroactively
edited. This is intentional and pinned by `test_stream_interim_deltas_carry_unstripped_content`.
The "marker split across deltas" edge is covered (recovery runs post-accumulation, so a marker
straddling two deltas recovers correctly).

### `degraded-roundtrip-probe` (leg 03) — landed (2026-06-18)

**Branch taken: ACCEPTED (clean round-trip) — NO production code change.** Ran the throwaway
probe (`/tmp/the-one-degraded-probe/probe.py`, NOT committed) against **live gemma3:4b**:
`OllamaProvider("gemma3:4b", base_url="http://localhost:11434/v1").complete(history)` on a
degraded follow-up history (USER → assistant-with-recovered-`ToolCall` `get_weather_0` → TOOL
`ToolResult`) with **no tools offered** (`supports_tools()` → False, `tools` key omitted from
the payload). **Live Ollama ACCEPTED it (2xx)** — the model returned a coherent Paris-weather
reply, no `HTTPStatusError`. The full request shape and the raw observation are recorded verbatim
in **Decisions → "DD5 resolved LIVE"** above. This is the flight prior's likely outcome, so the
pre-authorized `_to_api_message` plain-text adaptation + capability gate were **NOT applied**;
`_to_api_message` is unchanged this leg (its only diff is leg 02's).

**Pinned the validated contract**: added the hermetic test
`tests/test_ollama_degraded_roundtrip.py`
(`test_degraded_followup_history_serializes_structured`) — pure, no transport/mocks, asserts
`_to_api_message` serializes the three degraded-follow-up messages into the exact structured wire
shape (`role:"assistant"`+`tool_calls`, `role:"tool"`+`tool_call_id`) that live gemma3:4b accepted
on 2026-06-18, with a comment recording the live validation. Scoped to the recovered-call
follow-up history specifically (not the structured shape globally), so a future tool-capable
refactor isn't tripped.

**Result**: scoped run green — `tests/test_ollama_degraded_roundtrip.py -x --timeout 30` →
**1 passed**. Full hermetic suite `make test-unit` → **3262 passed / 18 skipped** (was 3261/18
after leg 02; the +1 is this leg's pin test — no regressions). `grep -rn "tmp"` over `the_one/`
+ `tests/` shows no committed reference to the throwaway probe; `git status` confirms the probe
lives only in `/tmp`. No live `@pytest.mark.live` test added (leg 04 owns that).

### `live-verify-gemma` (leg 04) — landed (2026-06-18)

**Added**: one committed `@pytest.mark.live` test `tests/test_ollama_recovery_live.py`
(`test_gemma_textform_toolcall_recovery_live`) that drives `OllamaProvider("gemma3:4b")` against
real local Ollama with a directive prompt eliciting a single ` ```tool ` fenced
`get_weather(city='Paris')` block, then asserts recovery fired and the raw block was stripped from
`Message.content`. A **local** `_resolve_gemma()` (mirroring `_resolve_ollama` at
`test_llm_provider_cross_provider_history.py:545-585`) probes `{base}/api/tags`, `pytest.skip`s if
Ollama is unreachable, and skips unless a `gemma3` model is present (substring match) — deliberately
NOT reusing the canonical resolver's "first-available / qwen-preferred" order (which would skip
whenever a non-gemma sorts first). Honors `LIVE_OLLAMA_BASE_URL` (container vs host) and
`LIVE_OLLAMA_MODEL` (exact override). Bounded 3-attempt retry; `temperature` defaults to 0.0 in
`complete()`; non-cooperation after 3 attempts → `pytest.skip` (inconclusive, never a hard red,
per the confidence-test stance). No production code changed this leg.

**Live run — PASSED (recovery fired).**
`LIVE_OLLAMA_BASE_URL=http://localhost:11434/v1 .venv/bin/python -m pytest tests/test_ollama_recovery_live.py -m live -v`
→ **1 passed in 4.55s** on attempt 1. Recovered call (captured verbatim):
`ToolCall(id='get_weather_0', name='get_weather', arguments={'city': 'Paris'})`. The raw fenced
block was **fully stripped** — `Message.content` came back as `''` (the entire content was the
fenced span; the kernel's whitespace-only-remainder rule collapsed it to empty). Both strip
assertions hold (`"get_weather(" not in content` AND `"```tool" not in content`). gemma emitted the
call as **loose text** (no structured `tool_calls`), confirming the recovery path — not the
structured path — is what fired.

**Hermeticity confirmed**: `make test-unit` → **3262 passed / 18 skipped, 541 deselected** (was
540 deselected after leg 03 — the +1 deselected is this leg's live test, NOT collected under the
`-m 'not live'` unit profile; pass/skip counts unchanged at 3262/18, proving the live test adds to
the default-deselected live set and does not touch the hermetic count). `pytest
tests/test_ollama_recovery_live.py --collect-only` under the default profile → **1 deselected, no
tests collected** (deselected, not skipped — the right mechanism per the acceptance criterion).
`grep -n "pytest.mark.live" tests/test_ollama_recovery_live.py` → marker present (line 118).

### `docker-removal-host-native` (leg 06) — landed (2026-06-18) — operator-directed DIVERSION

**Why (DIVERSION):** Docker was retired a prior mission for the Windows installer / host-native
runtime, but the deployment-Docker scaffold lingered and actively misled this flight (the Flight
Director mistook the operator's host-native Windows app on `:8484` for a container). The operator
directed a full rip-out, folded into the flight/03 branch, done before resuming the leg-05
behavior test. Not part of the original #105 scope.

**Removed (deployment-Docker):**
- Files `git rm`'d: `Dockerfile`, `docker-compose.yml`, `.dockerignore`.
- `Makefile`: rewrote the entire "Container lifecycle" section host-native. `up`/`down`/`restart`
  now manage a backgrounded `$(PY) -m the_one.main serve` via a PID file (`.the-one.pid`) + log
  file (`.the-one.log`); `logs` tails the log file; `reset-db` resolves the data dir dynamically
  via `$(PY) -c "from the_one.config import settings; print(settings.data_dir)"` (keeps the
  `CONFIRM=1` gate); `verify-serving` keeps its curl checks but the failure hint now points at
  `make logs`/`make restart` (no "image stale / make rebuild"); `brand-assets` + `smoke-runtimes`
  run host-native. **Removed** `shell`/`rebuild`/`rebuild-browsers`/`rebuild-clean`. Header comment
  + `help` rewritten host-native. `grep -nE "docker( |$)|docker compose|docker exec" Makefile` → empty.
- `.flightops/agent-crews/leg-execution.md`: rewrote the whole "Run tests with…" paragraph (incl.
  the `docker compose exec` TTY parenthetical) to the host-native form
  (`PYTHON=.venv/bin/python bash scripts/run-tests.sh … -x --timeout 30` / `make test-unit`).
- `README.md`: the "Docker (retired)" block → "Docker fully removed; runs host-native via
  `the-one serve` / `make up`".
- `CLAUDE.md`: rewrote the "Local dev with Docker" section (→ "Local dev (host-native)"),
  rewrote the `make`-command block target-by-target, dropped the two-container-paths / image-baked
  / `make rebuild`-required content and reframed the Pydantic `--reload` gotcha as "restart to pick
  up class-definition edits". Kept the existing "test suite runs host-native — no Docker" note.
- `SECURITY-MODEL.md`: reframed the Network-Bind `0.0.0.0`/bridge-network notes (host-native binds
  the `127.0.0.1` default; operator owns host firewalling); rewrote the stale "no secrets in
  `Dockerfile`/`docker-compose.yml`" assertion to reference committed files generally. Tool-sandbox
  security content untouched.
- `tests/HAT.md`: converted all ~13 `docker compose exec/ps/logs` commands host-native
  (`.venv/bin/python`, `.venv/bin/pip`, direct `which bwrap`/`pgrep`; `docker compose ps` →
  `make verify-serving`/`make up`). **Windowed-log gates** (the F5 L1 "transport close failed"
  count gate + the deleted-source WARNING scan + Tier-2 caplog gate) had no clean `tail -f`
  equivalent — converted to a **line-count-marker** scheme against the persistent host log file:
  capture `HAT_START_LINE`/`T2_START_LINE` = current `wc -l` of `$THE_ONE_LOGFILE` at the marker
  point, then `tail -n +$MARKER "$HAT_LOG" | grep …`. Step structure + intent preserved.
- `scripts/derive_brand_assets.py`: `DEFAULT_SOURCE`/`DEFAULT_OUT_DIR` now resolve repo-relative
  from `Path(__file__).resolve().parents[1]` (was `/app/...`); docstring usage examples → host-native.
- `scripts/run-tests.sh:7`: retold the WHY comment (orphan-zombie self-bounding rationale) without
  the `docker exec`/container framing — the process-group-kill mechanism is unchanged.

**Converted (live, deployment-flavored — not historical):**
- `tests/test_input_tokens_cross_provider_live.py`: docstring `docker exec the-one pytest`
  run-examples → host-native `.venv/bin/python -m pytest`. **Kept** the `host.docker.internal`
  env-overridable resolver default at the resolver site (that reaches Ollama, is
  `LIVE_OLLAMA_BASE_URL`-overridable — not how the-one is deployed).
- `tests/behavior/connector-inference-provider-config-roundtrip.md`: the one
  `docker exec the-one git grep` build-verify probe → host-native `git grep` (scans the working
  tree directly); "container is running" → "running host-native". Trivial — done, not deferred.

**smoke-runtimes intent change:** the original premise was that the generic-runtime caches PERSIST
across `docker compose restart` (named volumes). Host-native there is no container restart — the
caches live in the operator's host home (`${XDG_CACHE_HOME:-$HOME/.cache}/uv`,
`$HOME/.local/share/pipx`, `${npm_config_cache:-$HOME/.npm}`) and persist by default. The check is
narrowed to **cache-population + reuse on the host** (step 3 populates the uv cache, step 4
confirms it; re-running exercises the cache-hit path). Noted in the script header.

**`.env` migration (Step 0, done BEFORE `git rm docker-compose.yml`):** the compose
`environment:` block held the dev defaults; the repo `.env` previously had only API keys, so these
would have silently vanished. Appended the still-relevant dev vars to `.env` (gitignored, local
only), translating container-isms. Migrated var **NAMES** (no values):
`THE_ONE_DEV_MODE`, `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT`, `THE_ONE_LLM_PROVIDER`,
`THE_ONE_LLM_MODEL`, `THE_ONE_LLM_BASE_URL` (with `host.docker.internal` → `localhost`).
**Dropped** `THE_ONE_HOST=0.0.0.0` (host-native binds the `127.0.0.1` default; `0.0.0.0` only
exposed the container). `.gitignore` gained `.the-one.pid` + `.the-one.log`.

**Ambiguous / out-of-leg-scope deployment-Docker refs — PRESERVED and FLAGGED for the operator**
(the leg enumerated a specific file list; these carry deployment-flavored docker references but
were NOT in that list, so per the leg's "default to PRESERVE and flag" edge-case rule they were
left untouched rather than risk scope creep):
- `the_one/agents.md` — substantial container/dev-server prose (`docker exec the-one pytest`,
  `make rebuild`, `uvicorn … --reload --reload-dir /app/the_one`, `cap_add: [SYS_ADMIN]` dev
  container, `docker logs the-one`). This is the largest remaining deployment-Docker surface and
  likely wants a follow-up pass — but it's the architecture-orientation doc, out of this leg's
  named scope.
- `tests/test_llm_provider_cross_provider_history.py:593` — a `docker exec the-one pytest`
  docstring run-example (exact parallel to the input_tokens file that WAS in scope). Its
  `host.docker.internal` Ollama resolver (`:554`) is correct-to-keep regardless; only the docstring
  run-example is deployment-flavored.
- `tests/behavior/audit-log-inspector-renders-routing-entries.md` — a `docker exec the-one git grep`
  build-verify probe (same pattern as the connector-roundtrip one that WAS converted).
- The four Discord behavior specs (`discord-engagement`, `discord-multi-agent-routing`,
  `discord-multi-channel-routing`, `discord-multi-user-routing`) — use `docker exec`/`docker logs`
  as the observation apparatus for a containerized the-one.
- `tests/live/discord_hat/README.md` + `driver.py` — `docker exec the-one pytest` / `docker logs`
  runbook + diagnostic hints.
  (All of the above are candidates for a future host-native sweep if the operator wants the repo
  100% deployment-Docker-free; flagged here rather than silently expanded into.)

**PRESERVED (verified untouched — git status clean for these):** `ci/**` (Concourse CI infra —
intentionally still shows docker hits), the tool-sandbox refs (`tests/test_platform_interpreter.py`,
`tests/test_box_isolation.py`, `tests/test_mcp_cache_cleanup.py`, `tests/test_mcp_stdio_error_translation.py`'s
`_DOCKER_TOKENS` negative assertion, `tests/behavior/tool-sandbox-box-isolation.md`,
`tests/behavior/pty-session-containment.md`, `the_one/mcp/transports/stdio.py`'s `docker run` MCP
image, `the_one/mcp/README.md`/`SECURITY-MODEL.md` sandbox sections), the `host.docker.internal`
Ollama-resolver defaults in `test_provider_api.py`/`test_llm_provider_cross_provider_history.py`,
and ALL historical artifacts under `missions/**`, `maintenance/**`, `tests/behavior/**/runs/**`.

**Verification:**
- `make test-unit` → **3262 passed / 18 skipped** (matches baseline exactly — the Makefile/doc/script
  edits don't touch test behavior).
- `make help` renders without error; the help "common workflow" hint now says `make restart` (not
  `make rebuild`).
- `grep -nE "docker( |$)|docker compose|docker exec" Makefile` → empty. `ls Dockerfile
  docker-compose.yml .dockerignore` → all "No such file".
- `reset-db` without `CONFIRM=1` → refuses (non-zero exit), data dir left intact.
- **`make up` → verify → `make down` round-trip smoked** host-native on an **alternate port (8585)**
  because the operator's Windows app already holds `:8484`. Launched `THE_ONE_PORT=8585 … serve`
  backgrounded (PID file written); `/api/info` came up in 1s; `/static/js/areas/admin.js` → 200;
  the host log captured startup lines; `make down` stopped it by PID and removed the pidfile;
  post-down `:8585` no longer served. Clean round-trip. (Note: `make up`'s chained `verify-serving`
  curls a hardcoded `:8484`, so a default-port `make up` verifies correctly; the 8585 smoke was
  driven manually to avoid the running Windows app — the leg explicitly anticipated this port
  conflict.)

**SECOND PASS (operator-directed, 2026-06-18) — swept the remaining deployment-Docker prose the
first pass flagged-and-preserved above (lines 410-431).** The operator wanted ALL deployment-Docker
references gone; this pass converted the flagged set (and a few adjacent same-category hits the
re-grep surfaced) to the host-native reality, while preserving the sandbox/security and
Ollama-reach references per an explicit per-file disposition. Leg status stays **landed**.

**Converted in this pass:**
- `the_one/agents.md` — the dev/test-workflow prose: the `host-side-bench-drift-detection`
  convention (canonical "container run" → repo `.venv`); the test-entrypoints convention
  (renamed `container-test-entrypoints-reach-via-make` → `host-test-entrypoints-reach-via-make`;
  `docker exec the-one pytest` → `.venv/bin/python -m pytest`; the `make rebuild` / missing-Playwright
  foot-gun reframed — `make rebuild` no longer exists, edits take effect on `make restart`); the
  `connector.(inbound|outbound)` grep target (`docker logs the-one` → `grep … .the-one.log` / `make
  logs`); the "Dev iteration" section (dev-container uvicorn `--reload` + `docker exec` test running
  → host-native `the-one serve` + `make restart` + `.venv` pytest); and the standalone
  missing-Playwright foot-gun section (heading + body). Cross-reference to the renamed convention
  updated in `the_one/connectors/README.md`.
- `tests/test_llm_provider_cross_provider_history.py:593` — docstring run-example → `.venv/bin/python
  -m pytest … -m live`.
- `tests/behavior/audit-log-inspector-renders-routing-entries.md` — `docker exec the-one git grep`
  build-verify probes → direct `git grep` in the repo; "container is running" → "running
  host-native" (same conversion leg 06's first pass applied to the connector-roundtrip sibling).
- `tests/live/discord_hat/README.md` — runbook converted: `docker exec the-one pytest` →
  `.venv/bin/python -m pytest -m discord_hat` / `make test-discord-hat`; `docker logs the-one` →
  host log (`make logs` / `grep … .the-one.log`); `docker restart the-one` → `make restart`; dropped
  the `docker compose exec` TTY caveat. Steps/intent preserved.
- `tests/live/discord_hat/driver.py:223,232` — error-message hints "check `docker logs`" → "check
  the host log / `make logs`".
- The four Discord behavior specs (`discord-engagement`, `discord-multi-agent-routing`,
  `discord-multi-channel-routing`, `discord-multi-user-routing`) — precondition "the the-one
  container is running … diagnosable from `docker logs`" → "the-one is running host-native …
  diagnosable from the host log (`make logs`)". Also converted the two adjacent same-category hits
  the re-grep surfaced: `discord-engagement.md` observables (`the-one SQLite database, measured via
  docker exec` → "read directly on the host") and `discord-multi-user-routing.md` step 4 driver
  observation (`docker logs` → the host log (`make logs`)).

**PRESERVED in this pass (verified by re-grep — these are the only remaining `docker` hits across
the swept files, all intentional):**
- `the_one/agents.md` §Privilege-model line (`cap_add: [SYS_ADMIN]` / `seccomp:unconfined`) and the
  `THE_ONE_TEST_MODE` "MUST NOT appear in any Dockerfile/compose/k8s/CI" operational guardrail —
  both sandbox/security semantics, not deployment-Docker. Added a one-line note that the privilege
  description referred to the now-retired dev container and host-native runs bwrap directly; did NOT
  delete the seccomp/SYS_ADMIN semantics.
- `tests/test_llm_provider_cross_provider_history.py:554,565` — the `host.docker.internal` default
  base_url and the "native-Linux Docker" skip hint: these REACH OLLAMA
  (`LIVE_OLLAMA_BASE_URL`-overridable), not the-one deployment.

No ambiguous references were encountered in this pass — every flagged ref had a clean
deployment-vs-sandbox/Ollama-reach classification per the disposition.

**Verification (second pass):**
- `make test-unit` → **3262 passed / 18 skipped** (matches baseline; driver.py and the cross-provider
  test file import cleanly — the latter's `-m live` tests stay deselected).
- Re-grep across the swept files → only the four PRESERVED refs above remain (agents.md privilege +
  guardrail lines; cross-provider :554/:565 Ollama-reach).

### `gemma-toolcode-positional-fix` (leg 07) — landed (2026-06-18)

**Why:** the leg-05 behavior test FAILED end-to-end (see Anomalies, 2026-06-19). Real gemma3:4b
emits a ` ```tool_code ` fence (the kernel didn't recognize it) carrying a **positional** call
(`shell("echo …")`, which the named-param dispatcher couldn't bind). Two compounding causes, two
targeted fixes (FIX-BOTH, operator-directed), plus a spec amendment for a sandbox-invalid
observable.

**Changed:**
- **DD-A — kernel** (`the_one/llm/_toolcall_recovery.py:60`): added `"tool_code"` to
  `_FENCE_TAGS_TO_PARSE` → `{"", "tool", "tool_code", "python", "py"}` (Gemma/Gemini's documented
  fenced-tool-call tag). Scoped to the observed tag only; positional args still park under
  `__positional_args__` (binding is DD-B's job, downstream where the schema lives).
- **DD-B — `Tool.bind_positional_args`** (`the_one/tools/base.py`): new method on the `Tool` base
  that maps recovered positional values onto `self.parameters["properties"]` names in
  **declaration order**, skipping names already supplied as keywords (keyword args win). Returns a
  **new** dict (never mutates input) with the sentinel removed and bound names added. Edge handling
  (DD-C): overflow → bind what fits, leave remainder under the sentinel + a `logger.warning`;
  no-`properties` tool → sentinel untouched; no sentinel → no-op. **Layering (pinned):**
  `POSITIONAL_ARGS_KEY = "__positional_args__"` is defined LOCALLY in `base.py` (with a comment
  cross-referencing the kernel's identical constant) — NOT imported from `the_one.llm`, keeping the
  kernel a leaf; the literal is duplicated, not imported, in either direction. A regression test
  asserts the two literals agree.
- **DD-B — dispatch** (`the_one/agent/core.py:_execute_tool`): the flight's ONLY `agent/core.py`
  change — a single arg-normalization call before the unpack. Diff:
  ```diff
                   tool = self.tools.get(tool_call.name)
  -                output = await tool.execute(**tool_call.arguments)
  +                args = tool.bind_positional_args(tool_call.arguments)
  +                output = await tool.execute(**args)
                   return ToolResult(tool_call_id=tool_call.id, content=output)
  ```
  No iteration/auth-pause logic touched.
- **DD-D — behavior-spec amendment** (`tests/behavior/gemma-tool-use-recovery.md`): the original
  step-2 observable (a host canary file) is **invalid** — `ShellTool` runs `host_access=False` in
  an ephemeral bwrap box (`home=scratch`, `rmtree`'d on return), so a tool write never reaches the
  host and the box is destroyed after the call. Re-scoped step 2 to **echo a unique marker** and
  assert a tool was dispatched AND a tool result is present AND the tool-result/response contains
  the marker (a *more direct* proof of execution — a correction, not a weakening). Dropped the
  filesystem precondition + `filesystem` observable (observables become http + session/tool-result
  read); step 3 now checks for no raw ` ```tool_code `/` ```tool ` block. Rationale recorded inline
  in the spec. **Spec status left `draft`** — the Orchestrator flips it to `active` after the
  amended behavior test re-run passes.

**Tests added:** kernel `tool_code` fence test (positional `shell('echo hi')` → recovered under
`__positional_args__`); `bind_positional_args` unit tests (single positional → `{command:...}`;
no-sentinel no-op; input-not-mutated; mixed positional+keyword with keyword winning;
multiple positionals in declaration order; overflow → WARN + leftover sentinel; no-properties tool
leaves sentinel; real `ShellTool` binds `command`); a `required`-is-prefix-of-declared-properties
agreement test across ALL built-in tools (future-proofs declaration-order binding); the
cross-layer sentinel-constant agreement test.

**Verification:**
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_toolcall_recovery.py
  tests/test_tool_base.py -x --timeout 30` → **49 passed**.
- `make test-unit` → **3273 passed / 18 skipped** (baseline 3262 + 11 new tests; 541 deselected).
- `git diff the_one/agent/core.py` → exactly the one-line normalization shown above.

**NOT done here (Orchestrator's job):** the END-TO-END behavior-test re-run
(`/behavior-test gemma-tool-use-recovery` against a restarted dev instance) — code + tests + spec
amendment only; the spec status flip to `active` and the new run log are deferred to the
Orchestrator.

### `degraded-model-direct-tool-protocol` (leg 08) — landed (2026-06-19) — DURABLE FIX, operator-authorized agent-layer expansion

**Why:** Two behavior-test runs (leg-05 baseline + leg-07 re-run) proved recognizer-based recovery
is best-effort, not reliable, for gemma3:4b — it improvises a new tool-call serialization nearly
every turn. The durable fix is upstream: tell the non-tool model exactly which tools exist and the
ONE format to call them in, then recover that deterministic format with the existing kernel. An
explicit, operator-authorized expansion of the mission boundary into `the_one/agent/` (the mission
scoped `the_one/llm/` only — DD-F).

**What was built:**
- **`the_one/agent/degraded_tools.py`** (NEW, pure): `build_degraded_tool_prompt(tool_schemas) -> str`.
  Renders the direct-tool-protocol addendum — format spec FIRST (one ```` ```tool_code ```` block) +
  rules (keyword args, double-quoted values, one tool per message, emit ONLY the fenced block) + ONE
  worked example (`shell(command="echo hello")`) + THEN the catalog (each tool: `name(params):
  description`, required params first). No I/O; empty-catalog edge handled.
- **`the_one/agent/config.py`**: added `DEGRADED_BASE_PROMPT` = `BASE_PROMPT` with the "Tool
  discovery / call `search_tools`" section removed (DD-G — that block directly contradicts the direct
  catalog and steered gemma into emitting `search_tools` calls in both run logs). Identity, the
  non-discovery "Tool use" guidance, turn semantics, and the persona-append note are kept verbatim.
- **`the_one/agent/core.py`** degraded branch: when `not supports_tools`, `_build_degraded_messages()`
  builds the ephemeral request list `[Message.system(degraded_system), *self.messages[1:]]` where
  `degraded_system = addendum + "\n\n" + (DEGRADED_BASE_PROMPT + persona)` (the persona is recovered
  by swapping the `BASE_PROMPT` prefix of `self.system_prompt` for `DEGRADED_BASE_PROMPT`, so the
  persona + any connector directive carry through). Catalog = `self.tools.all_schemas()` minus
  `search_tools`/`continue` by name. `self.messages` is NOT mutated; the catalog re-renders each
  turn. The `stream()` call was factored into `_stream_response()` so the capable branch
  (`messages=self.messages`, visible-schema array) and the degraded branch (ephemeral list,
  `tools=None`) share the exact chunk/usage handling.

**core.py diff scope:** confined to (1) the stale "single-shot chat" comment → corrected to describe
the now-tool-using, multi-iterating degraded path; (2) the degraded branch selecting
`request_messages`/`tool_schemas`; (3) two new helper methods (`_stream_response`,
`_build_degraded_messages`). NO change to `_remaining_iterations`, `_dispatch_tool_calls`, or the
auth-pause/`_deferred_tool_calls` logic. (The `bind_positional_args` line in `_execute_tool` is the
pre-existing leg-07 change, not this leg's.)

**Docs (DD-E):** the `core.py` degraded-path comment + the `agents.md` "Capability gate" degradation
note both rewritten — the degraded path now injects a direct tool protocol and multi-iterates with
recovered tool calls (the stale "single-shot / single iteration" wording is retired).

**Tests added (12, all green):**
- `tests/test_degraded_tool_prompt.py` (8): format block + rules + worked example present; catalog
  lists `shell(command)` with description; required-before-optional ordering; empty-catalog edge
  ("none available"); no-param tool renders bare signature; deterministic. Excludes
  `search_tools`/`continue` from a supplied catalog.
- `tests/test_agent_degraded_injection.py` (4): with a capturing fake provider — degraded path's
  leading system message contains the addendum AND does NOT contain the "call `search_tools`"
  discovery instruction (and `Tool discovery:` block is gone), exactly ONE leading system message,
  persona survived the base swap, `tools=None` on the wire, `search_tools` excluded from the catalog;
  `self.messages` UNMUTATED + `self.messages[1:]` passed through; full degraded loop dispatches a
  recovered `tool_code` shell call; capable path unchanged (no addendum, `messages=self.messages`,
  `tools=` carries `search_tools`+`continue`).

**Verification:**
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_degraded_tool_prompt.py
  tests/test_agent_degraded_injection.py tests/test_toolcall_recovery.py -x --timeout 30` →
  **40 passed**.
- `make test-unit` → **3285 passed / 18 skipped** (baseline 3273 + 12 new tests).
- `ruff check` on the new + changed files → clean.

**NOT done here (Orchestrator's job):** the END-TO-END behavior-test re-run
(`/behavior-test gemma-tool-use-recovery` against a restarted dev instance), the spec status flip
`draft` → `active`, and the new run log. The behavior-test re-run acceptance criterion is left
UNCHECKED in the leg artifact for the Orchestrator to verify.

**Refinement (2026-06-18): added post-tool-stop + tool-gating clauses (CP4/CP5 fixes).** The leg-08
behavior-test re-run showed the CORE property now WORKS (gemma reliably emits a parseable
```` ```tool_code ```` `shell(command=...)` call that executes), but two behavioral side-effects
failed: CP4 — the model looped, re-emitting the same tool call to `max_iterations` and never writing
a closing answer; CP5 — it over-routed a plain knowledge question ("what is a haiku?") through
`shell`. Both fixed by addendum-text-only changes in `degraded_tools.py` (no `core.py`/`config.py`/
injection change). Added to the Rules block (format-first ordering preserved): a **TOOL-GATING**
clause — "Only use a tool when the task genuinely requires an external action … For questions you can
answer from your own knowledge (definitions, explanations, general facts), answer directly in natural
language and do NOT call any tool." — and a **POST-TOOL STOP** clause — "After you receive a tool
result, do NOT call the same tool again for the same purpose. Read the result and write a final,
natural-language answer to the user that incorporates it. Only call another tool if the task
genuinely needs a further, different action." Also added a compact one-shot **CONTRAST** pair after
the worked example: an ordinary question ("What is a haiku?") → a direct natural-language answer (no
tool); an action request ("How many files are in this directory?") → a ```` ```tool_code ````
`shell(command="ls -1 | wc -l")` call. Existing format spec + `shell(command="echo hello")` worked
example + catalog kept. Tests: `tests/test_degraded_tool_prompt.py` extended with 3 assertions
(gating clause, post-tool-stop clause, contrast example present); all prior assertions still pass.
Verification: targeted (`test_degraded_tool_prompt.py` + `test_agent_degraded_injection.py -x
--timeout 30`) → **15 passed**; `make test-unit` → **3288 passed / 18 skipped** (baseline 3285 + 3
new tests).

---

## Leg 09 — redundant-toolcall-loop-backstop (CP4 fix, 2026-06-19)

**Operator-authorized agent-loop change.** This leg enters `_run_iterations`' iteration/dispatch
logic — the logic legs 01–08 deliberately left alone — to fix CP4: on the degraded path gemma3:4b
re-emits a tool call whose result it already holds and terminates with an **empty message**, so
`_run_iterations` exits leaving an empty final assistant message (no answer for the user). Two
behavior-test runs (`…-03-35-08.md`, `…-03-51-38.md`) showed this is a gemma synthesis-floor, not
prompt-tunable; the fix is a model-agnostic dispatch-side backstop.

**core.py diff scope** (confined to `_run_iterations` + two new module-level pure helpers):
- New imports: `import json`; `Role` added to the `llm.base` import; `truncate_for_event` from
  `db.codec` (no import cycle — `codec` imports only `db.models` + `llm.base`).
- `_executed_key(tc)` — `(tc.name, json.dumps(tc.arguments, sort_keys=True))` on the **RAW**
  `tc.arguments` (recovered gemma call is `{"__positional_args__": [...]}` here; `bind_positional_args`
  runs later in `_execute_tool` and does NOT mutate the ToolCall, so the key is stable across
  re-emissions; order-insensitive via `sort_keys`). (DD-A)
- `_synthesize_closing(redundant)` — pure helper rendering a non-empty closing from
  `(name, content, is_error)` triples; single inline / multiple compact-list; errors marked as
  failures; oversized content truncated via `truncate_for_event` (the codec projection cap). (DD-C)
- In `_run_iterations`: a turn-local `executed: dict[tuple[str,str], tuple[str,bool]]` reset per
  entry. The dispatch decision after `if not response.tool_calls: return` now branches on
  `supports_tools`:
  - **Capable path BYTE-IDENTICAL** to before — `to_dispatch = response.tool_calls`; the backstop
    never runs (DD-D: a capable model may legitimately re-poll changing state).
  - **Degraded path** — partition into `new` (key not in `executed`) vs redundant; dispatch only
    `new` (DD-B). All-redundant + blank content → **replace** `self.messages[-1]` in-place with
    `Message.assistant(content=closing)`, yield, return (DD-C — `response is self.messages[-1]` here,
    so no stray empty message with orphaned `tool_calls` persists). All-redundant + non-blank content
    → clear `self.messages[-1].tool_calls = []` and return (DD-C2). After a successful, non-paused
    dispatch, record each real call's key → `(result.content, is_error)` by matching `tool_call_id`
    against the just-appended `Role.TOOL` messages (skips `continue`).

**Auth-pause untouched.** The `_deferred_tool_calls` / `is_auth_required` flow inside
`_dispatch_tool_calls` is unchanged. The executed-map records ONLY after the existing
`if self._deferred_tool_calls is not None: return` guard, so a paused call is never recorded as
redundant and stays re-dispatchable on resume. The backstop's partition runs on the *response's*
calls before dispatch; the pause logic is entirely inside the helper.

**Docs:** mission header annotated (Flight 3 Leg 09 iteration-logic expansion, operator-authorized);
`agents.md` "Capability gate" section gained a "Degraded redundant-call backstop" paragraph.

**Tests added (14, all green) — `tests/test_agent_redundant_backstop.py`** (scripted fake provider,
no network):
- Pure helpers: `_executed_key` stable across re-emissions despite id change, order-insensitive,
  distinct calls distinct keys; `_synthesize_closing` single/error/multiple/truncation.
- All-redundant backstop: same recovered call twice → 2nd triggers the closing; **asserts directly on
  `agent.messages`** — no orphaned `tool_call` (every emitted tool_call id has a following
  tool_result), no empty-content assistant message carrying undispatched tool_calls, final assistant
  message is the non-empty synthesized closing with no tool_calls, exactly one TOOL message.
- Error result surfaced in the closing (marked as failure).
- Partition: redundant + new in one response → only the new dispatches.
- DD-C2: redundant calls + non-empty text → text kept, tool_calls cleared, no synthesized closing,
  no duplicate message.
- Degraded-path scoped (DD-D): with `supports_tools=True`, a re-emitted identical `shell("date")` is
  dispatched BOTH times (not short-circuited).
- No false positives: clean multi-step (distinct calls) dispatches all; normal single call → text is
  unaffected.

**Verification:**
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_agent_redundant_backstop.py -x
  --timeout 30` → **14 passed**.
- `make test-unit` → **3302 passed / 18 skipped** (baseline 3288 + 14 new tests). No regressions in
  the existing `test_agent_*.py` agent-loop suite.

**NOT done here (Orchestrator's job):** the END-TO-END behavior-test re-run
(`/behavior-test gemma-tool-use-recovery`), the spec status flip `draft` → `active`, and the new run
log. That acceptance criterion is left UNCHECKED in the leg artifact for the Orchestrator.

---

## Leg 06 review fix — make-rebuild sweep

docker-removal review fix: swept the make-rebuild/container references the first pass missed
(6 behavior specs + 3 code comments). The 4 BLOCKING specs (`agent-retention-setting-roundtrip`,
`agent-purge-now-clears-history`, `agent-history-auto-purge`, `connector-editor-keyboard-a11y`)
still instructed operators to run the removed `make rebuild` target → rewritten to the host-native
`make restart` (dropped the "image-baked"/"JS-CSS-not-served-otherwise" framing, since host-native
serves the working tree and a restart picks up edits). 2 NON-BLOCKING specs with stale
"the-one container is running" framing (`discord-slash-end-to-end`, `studio-smoke`) reworded to
"running host-native" to match the discord-* siblings. 3 stale code comments updated
(`the_one/interfaces/web/app.py:205`, `:406`; `the_one/llm/ollama_api.py:22`) to drop the
docker-compose.yml / `make rebuild` historical references. Verified:
`grep -rniE "make rebuild|image[- ]baked|container is (running|rebuilt)" tests/behavior/*.md | grep -v runs/`
returns nothing; `make test-unit` green (3302 passed / 18 skipped). NOT committed.
