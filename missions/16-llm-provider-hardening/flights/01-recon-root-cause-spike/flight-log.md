# Flight Log: Recon & Root-Cause Spike

**Flight**: [Recon & Root-Cause Spike](flight.md)

## Summary

Read-only spike to confirm/correct the mission's root-cause hypotheses, evaluate
`any-llm`, and emit go/no-go for Flights 2–5. **LANDED** — all 4 legs complete.
Headline: hole #1 (extended-thinking) **falsified**; the real Anthropic bug is
**#122** (tool `input_schema` top-level combinators), reproduced live. Hole #2
(**#105**) confirmed, fix is text-form recovery, fixture captured. **any-llm →
hand-roll.** Mission reframed (operator: add #122 flight, keep thinking as a
separate lower-priority feature). No production source touched. Detail in Leg
Progress, ★ Headline Finding, Hole #2, any-llm (Leg 3), and ★ Synthesis & Go/No-Go.

---

## Flight Director Notes

**Context-load + environment scan (start of flight):**
- Mission 16 transitioned `planning` → `active`; flight `planning` → `in-flight`.
  Branch `flight/01-recon-root-cause-spike` created off `main`.
- Ollama up on `:11434` with `gemma3:4b` installed. Gemma 3 does not advertise
  tool capability — so this model is the right target for the hole-#2
  capability-gate probe (`supports_tools()` → `False`).
- **No Anthropic API key in the execution environment**, and **no `the-one`
  container running.** The hole-#1 repro needs a live, secret, extended-thinking-
  capable Anthropic credential that the Flight Director's spawned agents do not
  have.

**Orchestration decision: this flight runs operator-in-the-loop, not fully
autonomous.** Three of four legs need the operator's live environment or secret
credentials, and the synthesis leg is a Flight-Director + human strategic call.
The default `/agentic-workflow` autonomous Developer-agent cycle is therefore used
only for the genuinely delegatable work; the live-model reproductions are driven
interactively (HAT-style), with the operator supplying credentials / running the
live calls. Rationale logged before any agent was spawned, to avoid spawning
agents into an environment where they cannot reach the live services.

**Credential/environment resolution (operator-prompted):** Operator asked why the
repro can't just run inside the-one where the provider is already configured.
Correct — it can, and should. The configured Anthropic key lives **encrypted in
the app's SQLite DB**, unlocked by a file-backed Fernet key (`encryption.py:86`
`get_encryptor`), not in any env var — which is why raw `AnthropicProvider()`
(falling back to `os.environ`, `anthropic_provider.py:44`) couldn't see it.
Resolution: the hole-#1 repro builds the provider through the-one's own path —
`get_connection()` (`db/connection.py:12`) + `get_encryptor(data_dir)` +
`LLMProviderRepository(conn, encryptor).get(...)` → `get_provider("anthropic",
api_key=cfg.api_key, ...)` (mirrors `agent/factory.py:256-277`) — then calls
`provider.stream()` directly. This bypasses only the **agent loop**, NOT the
credential store. No `.env` re-supply needed. Runs on **host Python** (the_one +
anthropic SDK import OK; editable install; no container required). This refines
the flight's "direct provider.stream()" design decision: the provider is *built
from configured storage*, then *called directly*.

---

## Leg Progress

### anthropic-thinking-repro
**Status**: landed — hole #1 **CORRECTED (not reproduced)**

#### Result (live run, claude-sonnet-4-6, anthropic SDK 0.97.0, thinking forced on, temperature dropped)
- **Turn 1** `get_final_message()` block inventory: `['thinking', 'text', 'tool_use']`;
  the `thinking` block **carries a signature** (`has_signature: true`);
  `stop_reason: tool_use`. → Signed thinking blocks ARE exposed by
  `get_final_message()` — the *replay-capture* question is answered: capturing for
  replay would be a low-effort additive change IF it were needed.
- **Turn 2** replayed the assistant turn rebuilt via `_to_api_message()` (i.e.
  `[text, tool_use]`, **thinking blocks dropped**) + the tool_result, through
  `provider.stream()`. **Result: SUCCESS — no API error.** The model returned a
  normal final answer.
- **Conclusion:** the hole-#1 mechanism ("API rejects the tool turn because
  dropped thinking blocks/signatures aren't replayed") **does not reproduce** on
  Sonnet 4.6 for a single-tool, non-interleaved turn.
- **Compounding evidence:** the_one's current code never sets the Anthropic
  `thinking` param (grep: zero thinking handling), so in real usage thinking blocks
  are never produced — nothing to drop. The bug-as-stated cannot fire on the
  current code path regardless of the replay rule.
- **Per flight divert criterion:** paused to re-plan Flight 2's premise with the
  operator before any fix work. Open follow-up probes if warranted: interleaved-
  thinking beta (`interleaved-thinking-2025-05-14`), multi-round tool exchanges,
  or identifying the operator's *actual* original Anthropic symptom.
- Evidence: live run output captured in the orchestration transcript (throwaway
  script, not committed). Repro at `/tmp/the-one-spike/anthropic_thinking_repro.py`.

#### Notes
- Designed as an interactive repro leg. Developer design review (Sonnet) found a
  blocking precondition (no provider config in host DBs → configured provider is
  in the container volume), which drove the operator's path decision: host repro +
  `.env` key. Other review findings folded in: run under `.venv/bin/python`
  (anthropic 0.97.0, not host 0.79.0); import the provider directly (avoid the
  `db.repositories` cold-import cycle); `_build_kwargs` must be bypassed to set
  `thinking` + drop `temperature`.
- Throwaway repro at `/tmp/the-one-spike/anthropic_thinking_repro.py` (not
  committed). Two-turn design: turn 1 raw `client.messages.stream()` to inspect
  real blocks; turn 2 through `provider.stream()` to exercise the lossy replay.
- Awaiting: operator places `ANTHROPIC_API_KEY` in `.env` and confirms the
  thinking-capable model, then live run.

---

## Decisions

_(runtime decisions not in the original plan)_

---

## Deviations

_(departures from planned approach)_

---

## Anomalies

_(unexpected issues encountered)_

---

## Findings

> The spike's primary output. Each hole gets a captured artifact (error text / raw
> response) proving the failure reproduces, plus the root-cause determination.

### ★ Headline finding — the operator's recorded issues supersede holes #1/#2 framing

The operator recorded the actual bugs as GitHub issues. They redirect the mission:

- **Anthropic bug = #122**, NOT extended thinking. Title: *"Tool use fails with
  400: input_schema does not support oneOf/allOf/anyOf at top level."* The
  Anthropic Messages API rejects any tool whose `input_schema` uses
  `oneOf`/`allOf`/`anyOf` at the **top level** (observed: `tools.37.custom.
  input_schema` → 400 `invalid_request_error`). Likely an MCP-published tool
  (index 37, past the built-in set). **Hole #1 (extended-thinking replay) is a
  red herring** — derived from the origin research conversation, not the
  operator's real failure. the_one passes tool schemas through verbatim
  (`anthropic_provider.py:210-215` → `input_schema: tool_def["parameters"]`), so
  a top-level `anyOf` reaches Anthropic unmodified and the whole turn is rejected.
  Fix surface: normalize/wrap top-level `oneOf/allOf/anyOf` before send; name the
  offending tool instead of failing the whole turn. (#122 also bundles a UI
  enhancement: copy-button on chat error bubbles.)
  **Reproduced live** (claude-sonnet-4-6, the-one's `AnthropicProvider`,
  `/tmp/the-one-spike/anthropic_schema_repro.py`): a tool with `{type: object,
  anyOf: [...]}` → verbatim 400 `tools.0.custom.input_schema: input_schema does
  not support oneOf, allOf, or anyOf at the top level`. A sibling constraint also
  surfaced (`input_schema.type: Field required` when `type` is absent) — same
  class: verbatim schema passthrough vs. Anthropic's stricter top-level rules. So
  a robust fix sanitizes for BOTH (wrap/flatten top-level combinators AND ensure a
  top-level `type`), not just `anyOf`.
- **Gemma bug = #105**, confirms hole #2 verbatim ("prints tool calls as raw text
  instead of executing them") and already documents the dual mechanism the F1
  design review re-derived: (1) `supports_tools()` → `False` for Gemma drops all
  tools from the wire (`ollama_provider.py:71-79`, `core.py:167-188`); (2) the
  model emits tool-call text anyway; (3) the parser only reads structured
  `tool_calls` (`ollama_provider.py:117-129`, `:197-228`), so text-form calls
  render as content. Hole #2 stands.

**Mission implication — operator decision (2026-06-17): "add #122 flight, keep
thinking too."** Reframe to apply during the synthesis leg:
- **New high-priority flight: Anthropic tool `input_schema` compatibility (#122)** —
  sanitize top-level `oneOf/allOf/anyOf` AND ensure top-level `type` before send;
  name the offending tool instead of failing the whole turn. (Optionally folds in
  #122's bundled UI enhancement: copy-button on chat error bubbles — or split that
  out.) This becomes the real "Flight 2".
- **Keep extended-thinking support as a SEPARATE, lower-priority flight** (feature,
  not the bug). De-risked by the spike: `get_final_message()` carries signed
  thinking blocks, so capture/replay is low-effort if pursued; live UI streaming of
  thinking deltas remains the harder, optional part.
- Holes #2 (Flight 3) and #3 (Flight 5) unaffected.
Per the mid-execution-pivot rule, the mission body is not rewritten here; the
synthesis leg applies it with operator sign-off.

### Hole #2 (#105) — live reproduction against gemma3:4b

Three probes (`/tmp/the-one-spike/ollama_gemma_repro.py`, local Ollama):
- **A. Capability gate confirmed:** `OllamaProvider("gemma3:4b").supports_tools()`
  → `False`.
- **B. The gate is CORRECT — tools cannot be offered:** native `POST /api/chat`
  with a `tools` array → **HTTP 400 `"gemma3:4b does not support tools"`** from
  Ollama itself. So the fix is **NOT** "stop dropping tools for Gemma" (that path
  is blocked at the Ollama layer); the capability gate is right to drop them.
- **C. Captured text-form tool call (the user symptom + Flight 3 fixture seed):**
  with no tools offered but primed to call one, gemma3:4b returned
  `tool_calls: null` and this in `content`:
  ```
  ```tool
  get_weather(city='Paris')
  ```
  ```
  A fenced ` ```tool ` block containing **Python-call syntax** (`name(kwarg='v')`)
  — not Hermes `<tool_call>`, not JSON.

**Flight 3 refinement:** the only viable fix is a **text-form tool-call recovery
parser** that runs when `supports_tools()` is `False` — detect the ` ```tool `
fenced block (and other common formats) and parse `name(kwargs)` into a structured
`ToolCall`. Parsing Python-call syntax (quoted kwargs) is the specific shape to
handle for gemma3; the parser should be conservative + format-pluggable since
other open models differ (Hermes tags, bare JSON). Fixture for Flight 3 = the
captured block above. Hole #2 **confirmed and characterized.**

### any-llm evaluation (Leg 3) — decision: HAND-ROLL

Source-read of `mozilla-ai/any-llm` (`any-llm-sdk` v1.17.0). Verdict: adopting it
fixes **neither** real bug.
- **#122 (Anthropic schema):** `anthropic/utils.py::_convert_tool_spec` copies only
  `properties`/`required` and hardcodes `type: object`. No combinator handling — a
  top-level `oneOf/allOf/anyOf` is **silently dropped** (worse than today's 400, not
  better). Nested combinators pass through and still 400. No per-tool isolation.
- **#105 (text-form recovery):** `ollama/utils.py` reads only structured
  `tool_calls`; no fenced-block/Hermes/JSON-in-content parsing; no unsupported-tools
  fallback. #105 reproduces identically under any-llm.
- **Fit:** mechanically clean (wraps official SDKs, good streaming/usage incl. cache
  tokens, Ollama supported) but stacks a second abstraction over the layer the-one
  already hand-rolls, adds a 3.11+ floor + fat provider-dep surface, and retires no
  fix we still must write.
- **Decision:** keep the hand-rolled `LLMProvider`; build the #122 sanitizer and
  #105 parser directly. Optional steal: any-llm's Anthropic usage mapping
  (`cache_read_input_tokens`/`cache_creation_input_tokens` → prompt tokens) as a
  reference if the-one's usage accounting omits cache tokens.

---

## ★ Synthesis & Go/No-Go (Leg 4)

**Root causes — final:**
| Hole (mission) | Verdict | Real root cause |
|---|---|---|
| #1 extended-thinking replay | **Falsified** | Not a bug. Real Anthropic bug = **#122** tool `input_schema` top-level combinator / missing-`type` rejection (verbatim MCP schema passthrough). |
| #2 Gemma loose tool calls | **Confirmed (#105)** | Model can't be offered tools (Ollama 400s); capability gate correctly drops them; model emits a ` ```tool ` fenced Python-call block; parser reads only structured `tool_calls`. Fix = text-form recovery. |
| #3 model-table drift | **Standing** (code observation, not re-probed) | OpenAI hand-table + Anthropic hardcoded 200k vs. Ollama/OpenRouter live. OpenAI can't live-fetch (no `context_length` in `/models`) → generated/cached. |

**Reframed flight plan (per operator "add #122 flight, keep thinking too"):**
- **Flight 2 (NEW, HIGH): Anthropic tool `input_schema` compatibility (#122)** —
  sanitize before send: wrap/flatten top-level `oneOf/allOf/anyOf`, ensure top-level
  `type`; isolate + name the offending tool instead of failing the whole turn.
  (Optionally fold in #122's copy-button-on-error-bubbles UI enhancement, or split
  it out.) **GO.**
- **Flight 3: Open-model tool-use robustness (#105)** — text-form recovery parser
  gated on `supports_tools()==False`; handle the gemma ` ```tool ` fenced Python-call
  format + Hermes/JSON; do NOT offer tools (Ollama rejects). Fixture = captured
  block. **GO (approach refined).**
- **Flight 4: cross-provider tool-use conformance suite** — unchanged; now guards
  both #122 and #105 fixes. **GO.**
- **Flight 5: model-catalog drift removal** — unchanged; OpenAI via generated/cached
  (no live `context_length`). **GO.**
- **Flight (NEW, LOWER priority): Extended-thinking support** — feature, not a bug.
  De-risked: `get_final_message()` carries signed thinking blocks → capture/replay is
  low-effort; live UI streaming of thinking deltas is the harder optional part. **GO
  when prioritized.**
- **Build-vs-adopt:** hand-roll (any-llm rejected). **Settled.**

**Post-spike scope broadening (operator, 2026-06-17):** beyond the two bug fixes,
the mission now targets **preemptive capability completeness** — full coverage of
the capabilities each official SDK exposes (extended thinking promoted to
first-class, plus prompt caching, structured outputs, vision, reasoning effort,
etc.). Added **Flight 1B: provider capability audit** to enumerate per-SDK gaps
and bound the scope; capability flights are planned from that backlog. Mission
banner, success criteria, and flight list updated accordingly.

### Recon finding — configured-provider location (Leg 1 design review)

The operator's configured Anthropic provider is **not on the host**. Verified:
- `~/.local/share/the-one/the-one.db` — 0 tables (empty since 2026-06-07; today's
  `-wal`/`-shm` are a read-probe artifact, no data lost).
- `~/.the-one/the-one.db` — legacy, `schema_version=2`, predates the
  `llm_providers` table (created at migration v3, `db/schema.py:147`).
- Neither has an `llm_providers` row.
- Docker volume **`the-one_the_one_data`** exists — the running app's data store.
  No the-one image built currently; no container running.

**Conclusion:** the-one runs containerized; the configured credential lives in the
`the-one_the_one_data` volume, reachable only from inside the running container
(not a host script). This is why host-side direct construction found nothing — and
confirms the operator's "it's configured in the-one" intuition: it is, in the
container. Path decision pending (run spike in-container vs. `.env` key supply).

---

## Session Notes

_(chronological notes from work sessions)_
