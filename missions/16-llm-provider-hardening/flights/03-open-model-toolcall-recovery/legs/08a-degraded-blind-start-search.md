# Leg: degraded-blind-start-search

**Status**: aborted *(approach abandoned 2026-06-19 — over-routing was fixed, but the blind→search→call hop is unreliable on gemma3:4b: the model finds tools via search but won't call them and stalls. Operator chose 08C (chat-only). The search tokenize+cap done under this leg is KEPT and re-homed in `08d-search-query-tokenization`. The blind-start `degraded_tools.py`/`core.py` changes are superseded by 08C. See flight-log "Leg 08A — ACCEPT/ABANDON DECISION".)*
**Flight**: [Open-Model Tool-Use Robustness (#105)](../flight.md)

> **POST-LANDING FIX — gated trial, approach A of up to three (08A → 08B → 08C).**
> Flight 3 landed with the degraded direct-tool-protocol (Leg 08) + redundant-call backstop (Leg 09).
> A post-landing live repro (2026-06-19, operator + Claude) found the degraded path **over-routes**:
> gemma3:4b emits a `tool_code` call on essentially *every* message — a greeting → `shell(command="echo
> Hello there!")`, "what is a haiku?" → `read_file(path="haiku_definition.txt")` — **deterministically**
> (the agent path runs at `temperature=0.0`), and **worse the larger the tool catalog**. This is the CP5
> over-routing failure mode that Leg 08's tool-gating clause was believed to have fixed; it was only ever
> verified against the behavior test's **single-`shell` agent**, which masked it (a knowledge question has
> no plausible tool to grab when only `shell` is offered). With a normal full-catalog agent (24 built-ins,
> plus any MCP tools) the gating clause does not hold. This **falsifies the Flight 3 debrief's Key Learning
> 3** ("gating is promptable; only synthesis isn't") for the realistic full-catalog case.
>
> The operator chose to trial three mutually-exclusive fixes, deciding accept/abandon after each. **08A is
> the first.** Only design/run 08B if 08A is abandoned; only design/run 08C if 08B is abandoned.

## Objective

On the degraded path (`supports_tools()=False`), stop dumping the **full** tool catalog every turn and
instead mirror the tool-capable path's **blind-start discovery model** — the model sees only a `search_tools`
discovery entry by default (no concrete tools), so its default stance is **converse**; concrete tools enter
its prompt only after it deliberately calls `search_tools` — so over-routing pressure is removed at the
source while genuine tool use is preserved through the discovery hop.

## Context

- **Root cause.** Leg 08's `_build_degraded_messages` (`agent/core.py:_build_degraded_messages`) sources the
  degraded catalog from `self.tools.all_schemas()` (the **full** registry minus `search_tools`/`continue`)
  and renders every tool's signature into the system prompt on **every** degraded turn. The tool-capable
  path does the opposite: it starts **blind** — `_compute_visible_schemas` (`agent/core.py:_compute_visible_schemas`)
  returns only `[SEARCH_TOOLS_SCHEMA, CONTINUE_SCHEMA] + self._loaded_schemas`, and concrete tools are added
  to `_loaded_schemas` **only** as a side effect of the model calling `search_tools`. Leg 08 **inverted**
  that default stance for degraded models, and a 4B model reads "here are 24 tools + here's the call format"
  as "call a tool." That inversion — not the example text or the gating wording — is the over-routing driver,
  and its severity scales with catalog size.
- **Why this is a *clean* test, not a retread.** Leg 08 (DD-G, `agent/config.py:DEGRADED_BASE_PROMPT`
  comment) *removed* the `search_tools` discovery block from the degraded prompt because gemma "steered into
  emitting `search_tools` calls because of this text." **But that was a confounded setup**: the model saw the
  `search_tools` discovery instruction **and** the full catalog *simultaneously* — a direct contradiction
  ("you have only search_tools" vs. "here are all 24 tools"). The clean configuration — **discovery entry
  only, no catalog** — was never actually tested. 08A is that test. Removing the contradiction is the whole
  point.
- **The discovery machinery already exists and is reused, not rebuilt.** `SearchTools`
  (`the_one/tools/_search_tools.py:SearchTools`, `name = "search_tools"`) is registered into every agent's
  `ToolRegistry` by the factory and is therefore dispatchable by name. Its `_on_match` callback mutates the
  shared `self._loaded_schemas` / `self._loaded_tool_names` containers (the same containers
  `_compute_visible_schemas` reads). So when gemma emits `search_tools(query="…")` as a `tool_code` block,
  the leg-01/07 recovery kernel lifts it, `_run_iterations` dispatches it through the registry, `SearchTools`
  runs and **mutates `_loaded_schemas`**, and the next degraded turn re-renders with the now-populated set —
  all with the existing plumbing. 08A's job is to **render the visibility-filtered set as the degraded
  catalog instead of the full registry**, and to frame the prompt around converse-by-default + discovery.
- **Real risk (the thing we are actually testing).** A 4B model must perform a **multi-step hop**:
  realize an action is needed → emit a `search_tools` call → read the results → emit the concrete tool call.
  Capable models do this routinely; gemma3:4b's instruction-following floor is lower. Leg 08's evidence (even
  confounded) is a yellow flag that discovery steps are hard for it. **The likely *new* failure mode shifts
  from "over-calls `shell`" to "over-calls `search_tools` / can't complete the two-hop."** That is *less
  harmful* (search is read-only) but is exactly what the live verification below must measure. If gemma can't
  reliably complete the hop, 08A is **abandoned** and we proceed to 08B.
- **Backstop interaction (Leg 09).** The degraded redundant-call backstop keys on `(name, raw-args)`
  (`agent/core.py:_executed_key`). A `search_tools(query="…")` call followed — after results change
  `_loaded_schemas` — by a *different* concrete tool call is **not** redundant, so the backstop does not fire.
  But two identical `search_tools(query="…")` re-emissions *would* be keyed identical and trip the backstop's
  closing. That interaction is an explicit edge case below.

## Inputs

What must exist before this leg runs:
- Flight 3 legs 01–09 landed (recovery kernel, `tool_code` fence, positional binding, degraded
  direct-tool-protocol, redundant-call backstop). All present on `main`.
- `the_one/agent/core.py` with the degraded branch (`supports_tools` resolved once at
  `_run_iterations`; the `else:` arm building `tool_schemas=[]` + `request_messages = self._build_degraded_messages()`)
  and `_build_degraded_messages` sourcing the full catalog.
- `the_one/agent/degraded_tools.py` (`build_degraded_tool_prompt`, `_PROTOCOL_HEADER`).
- `SEARCH_TOOLS_SCHEMA` (`agent/core.py:SEARCH_TOOLS_SCHEMA`) and the registered `SearchTools` tool.
- A reachable host-native dev instance (`the-one serve`, **port 8485** — not 8484/8585) and local Ollama with
  `gemma3:4b` pulled.

## Outputs

What exists after this leg completes:
- `the_one/agent/core.py` — `_build_degraded_messages` sources the degraded catalog from the
  **visibility-filtered** set (`search_tools` + `self._loaded_schemas`) rather than `self.tools.all_schemas()`.
  `search_tools` is now **dispatchable on the degraded path** (recovered `search_tools` calls execute and
  mutate `_loaded_schemas`).
- `the_one/agent/degraded_tools.py` — the addendum is reframed: **converse-by-default**, a single
  `search_tools` discovery entry, and the pinned `tool_code` format; the full-catalog dump is gone. When
  `_loaded_schemas` is non-empty, those discovered tools are listed (so the model can call them by name in the
  same format).
- Unit tests: the reframed renderer + the degraded message-list now carries only the discovery entry on a
  fresh turn and the discovered tools after a search; `search_tools` dispatch on the degraded path is
  exercised with a mock provider.
- An **amended** behavior-test spec (`tests/behavior/gemma-tool-use-recovery.md`) whose CP5 runs against a
  **full-catalog** agent (the masking config is the bug), plus a new full-pass run log.
- An explicit **accept/abandon decision** recorded in the flight log and (if it changes mission criteria) the
  mission docs.

## Acceptance Criteria

- [ ] **Renderer reframed (converse-default + discovery-only):** `build_degraded_tool_prompt`, given an
      *empty* discovered set, returns a prompt that (a) instructs **reply in natural language by default**,
      (b) lists exactly **one** callable entry — `search_tools(query)` — and (c) pins the
      ` ```tool_code\nname(arg="value")\n``` ` format. It does **not** list `shell`/`read_file`/the full
      registry. Given a *non-empty* discovered set, it additionally lists those tools' signatures. Deterministic;
      unit-tested for both the empty and non-empty cases (assert `search_tools` present; assert `read_file`
      ABSENT when not yet discovered; assert a discovered tool present after).
- [ ] **Degraded catalog = visibility-filtered set, not the full registry:** on the degraded path the catalog
      is sourced from `search_tools` + `self._loaded_schemas` (mirroring `_compute_visible_schemas`), **not**
      `self.tools.all_schemas()`. Unit-tested on the exact degraded message-list: a fresh turn's system
      message lists only the discovery entry; after `_loaded_schemas` is populated, the next turn's system
      message lists the discovered tool(s). `self.messages` is NOT mutated by the injection (history clean).
- [ ] **`search_tools` dispatches on the degraded path:** a degraded-model turn whose recovered content is
      ` ```tool_code\nsearch_tools(query="read a file")\n``` ` recovers → dispatches through the registry →
      `SearchTools` runs → `_loaded_schemas` is mutated → the next turn's degraded prompt lists the matched
      tool(s). Focused agent test with a mock provider scripting the search-then-call sequence; assert the
      concrete tool ultimately dispatches and executes.
- [ ] **Tool-capable path unchanged (byte-identical):** when `supports_tools()` is `True`, behavior is
      exactly as today (wire `tools=` array from `_compute_visible_schemas`, no addendum). Unit-tested.
- [ ] **LIVE — over-routing fixed against a FULL-catalog agent (the regression that's broken today):** against
      the running dev instance (port 8485) with a gemma3:4b agent that has the **full** tool catalog enabled
      (`enabled_tools: null`), **a greeting** ("Hello there!") and **a knowledge question** ("What is a
      haiku?") each return a **direct natural-language answer with zero concrete-tool dispatches** (a
      read-only `search_tools` probe that resolves to a conversational answer is acceptable; a `shell`/
      `read_file`/etc. dispatch is a FAIL). Recorded with the live transcript as evidence.
- [ ] **LIVE — genuine tool use preserved through the hop:** against the same full-catalog agent, an explicit
      action request ("Use your tools to tell me how many files are in the current directory") results in the
      model **discovering and executing** the right tool end-to-end (a tool result is present in the turn; the
      answer reflects it) — i.e. the blind→search→call hop completes. If the model cannot reliably complete
      this hop across a few attempts, that is the **abandon** signal for 08A (record it; proceed to 08B).
- [ ] **Behavior test strengthened + green:** `tests/behavior/gemma-tool-use-recovery.md` is amended so its
      no-false-positive checkpoint (CP5) is run against a **full-catalog** agent (not the single-`shell`
      agent), and the end-to-end tool-use checkpoints pass via the discovery hop. `/behavior-test
      gemma-tool-use-recovery` → PASS with a new run log committed. (See the behavior-test amendment note in
      Implementation Guidance.)
- [ ] **`make test-unit` stays green** (record the new baseline count).
- [ ] **Accept/abandon decision recorded** (see the decision-gate section) in the flight log; if 08A is
      accepted and it re-opens/closes a mission criterion, the mission docs are updated accordingly.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_degraded_tool_prompt.py
  tests/test_agent_degraded_injection.py tests/test_toolcall_recovery.py -x --timeout 30` — green
  (extend these suites; do not weaken existing assertions — invert/rename the ones that pinned the
  full-catalog-dump behavior, since 08A deliberately changes it). **Tests known to require inversion /
  re-authoring (from design review — confirm against current code, names may have shifted):**
  - `tests/test_degraded_tool_prompt.py::test_catalog_excludes_search_tools_and_continue` — currently asserts
    `search_tools(` is ABSENT; 08A makes it always present. **Invert + rename** (e.g.
    `test_search_tools_discovery_always_present`); assert the discovery entry IS present and that a *discovered*
    tool (e.g. `read_file`) appears only when passed in the discovered set.
  - `tests/test_degraded_tool_prompt.py::test_worked_example_present` — pins the
    `shell(command="echo hello")` worked example, which 08A removes. **Invert/rename** to assert the new
    no-tool-first + `search_tools`-discovery example shape.
  - `tests/test_degraded_tool_prompt.py::test_tool_gating_clause_present` — pins the old gating wording;
    update to the converse-first framing (or assert the converse-default instruction is present).
  - `tests/test_agent_degraded_injection.py::test_addendum_injected_and_search_tools_suppressed` — asserts the
    degraded system message does NOT contain `search_tools(query)` / "call `search_tools`" and DOES contain
    `shell(command)`. 08A flips all of these. **Re-author** (not just extend): on a fresh turn the system
    message contains the `search_tools` discovery entry and does NOT contain `shell(command)` (no tool
    discovered yet); after `_loaded_schemas` is populated it contains the discovered tool's signature.
- `make test-unit` — full hermetic suite green.
- `git diff the_one/agent/core.py` — change confined to `_build_degraded_messages` (catalog source) + any
  minimal wiring to allow `search_tools` dispatch on the degraded path; **no** change to the auth-pause /
  `_deferred_tool_calls` flow or the Leg-09 backstop partition logic beyond what the search-then-call edge
  case requires (call it out explicitly if touched).
- **Restart the dev instance** (host-native, no `--reload`: `make restart`), confirm it's on **8485**, then
  run the LIVE checks against a full-catalog gemma3:4b agent. The repro harness used to find the bug
  (`/tmp/repro_full.py` — WebSocket `new_session` + `message`, port 8485) is a convenient driver; capture the
  event stream as evidence.
- `/behavior-test gemma-tool-use-recovery` — PASS (with the amended full-catalog CP5).

## Implementation Guidance

1. **Reframe the addendum** (`the_one/agent/degraded_tools.py`). Rewrite `_PROTOCOL_HEADER` so the *lead* is
   the default stance, not the call format:
   - First line(s): "Reply to the user in plain natural language. Only when the task genuinely requires an
     external action (running a command, reading/writing a file, fetching data) do you call a tool."
   - Then the discovery instruction: "You do not start with any specific tools. To find a tool for an action,
     call `search_tools` with a query describing what you need; you'll get back the matching tools and may
     then call one of them. To call any tool, output EXACTLY one fenced block and nothing else:" followed by
     the existing pinned ` ```tool_code\nname(arg="value")\n``` ` format and the keyword-arg / one-call-per-turn
     rules.
   - Keep a single worked example, but make the **first** example a no-tool/direct-answer case and the second
     a `search_tools` discovery call (NOT a `shell(command="echo hello")` example — that primed the greeting
     echo).
   - `build_degraded_tool_prompt(discovered_schemas)` now renders the discovery entry **always** plus any
     `discovered_schemas` (the populated `_loaded_schemas`). Empty discovered set → only the `search_tools`
     entry. Keep it pure/deterministic.
2. **Source the degraded catalog from the visibility-filtered set** (`agent/core.py:_build_degraded_messages`).
   Replace `degraded_catalog = [s for s in self.tools.all_schemas() if s["name"] not in {"search_tools",
   "continue"}]` with the discovered set `self._loaded_schemas` (the same list `_compute_visible_schemas`
   reads), and have the renderer always include the `search_tools` discovery entry. Do **not** dump
   `all_schemas()`. The ephemeral message list shape (`[Message.system(degraded_system), *self.messages[1:]]`,
   no mutation of `self.messages`) is unchanged.
   - **Invariant (make explicit, don't leave to inference):** `_loaded_schemas` never contains a `search_tools`
     entry — `SearchTools._filter_candidates` excludes it via `_EXCLUDED_NAMES`, so `_on_match` never adds it.
     The renderer prepending the discovery entry is therefore always purely additive (no dedup/collision with
     the discovered set).
   - **Update the now-stale `_build_degraded_messages` docstring** — it currently cites "DD-B: the FULL
     registry minus the virtual tools"; rewrite it to describe the visibility-filtered source.
3. **Allow `search_tools` to dispatch on the degraded path.** Today the degraded catalog excluded
   `search_tools` by name (so the model never called it) — 08A re-introduces it as the discovery entry.
   `_run_iterations` already dispatches `response.tool_calls` (recovered) through `self.tools.get(name)`, and
   `SearchTools` is registered, so a recovered `search_tools` call executes and mutates `_loaded_schemas` via
   `_on_match` with no core change to the dispatch loop itself. **Verify** `SearchTools.execute` returns a
   human-readable match list (the model needs to read it to pick a tool) — if its text is terse, consider a
   degraded-friendly rendering, but prefer reusing the existing output.
4. **Re-render each turn — this is the crux of why the design works (and resolves the "where do parameter
   signatures come from" question).** `_build_degraded_messages` is already called fresh inside the `while`
   loop. So after a `search_tools` call on iteration N mutates `_loaded_schemas`, iteration N+1's degraded
   system prompt re-renders `build_degraded_tool_prompt(self._loaded_schemas)` and now lists the matched
   tool(s) with their **full `name(param): description` signatures**. The model therefore learns *how* to call
   the discovered tool from the **re-rendered catalog in the next turn's system prompt** — NOT from the
   `search_tools` *result* text. This means `SearchTools._format_result` returning a names-only line
   (`"Found 2 tools matching 'read a file': built-in: read_file, write_file."`) is **sufficient** for the
   design: the result tells the model *which* tool exists; the next system prompt tells it *how* to call it.
   Confirm this two-turn flow with the focused agent test (turn 1 → recovered `search_tools`; turn 2 system
   prompt contains the concrete tool's full signature; turn 2 → the concrete tool call dispatches). *(Optional
   robustness, not required for 08A: enrich `_format_result` with per-tool param signatures so the model could
   also call within the same turn — defer unless the live runs show the two-turn hop is where gemma stumbles.)*
5. **`continue` on the degraded path:** keep it excluded from the degraded catalog (one-tool-per-turn; the
   loop iterates naturally) unless the live runs show the model needs an explicit "keep going" affordance —
   if so, note it; don't add speculatively.
6. **Behavior-test amendment** (the masking config is itself a bug): amend
   `tests/behavior/gemma-tool-use-recovery.md` so its no-false-positive checkpoint provisions / targets a
   **full-catalog** agent (`enabled_tools: null`) — not the single-`shell` agent — and add an explicit
   greeting case ("Hello there!", the exact input that produced `shell(command="echo Hello there!")` in the
   repro) alongside the haiku case. Keep the existing end-to-end tool-use checkpoints, which now pass via the
   discovery hop. Also **update the spec's stale port reference** (Preconditions cite `:8484`) to the actual
   dev instance port **8485** (or note the harness overrides it), so a runner doesn't probe a dead port. (Per
   the project's behavior-test convention, this is a spec amendment, not a new apparatus.) The Orchestrator
   runs it after restart.
7. **DEGRADED_BASE_PROMPT note:** 08A changes the *addendum*, not necessarily `DEGRADED_BASE_PROMPT`. The
   debrief's Rec 3 (derive `DEGRADED_BASE_PROMPT` from `BASE_PROMPT` to kill the verbatim-copy drift) is a
   separate cleanup — do not fold it in here unless it falls out naturally; if touched, keep it a clearly
   separate commit/diff hunk.

## Edge Cases

- **Model over-calls `search_tools` on conversational turns** (e.g. greeting → `search_tools(query="greet")`).
  Far less harmful than running `shell` (read-only, no side effects), and the next turn the model should
  answer. Acceptable per the live criterion (a `search_tools` probe that resolves to a conversational answer
  is a PASS); only a *concrete*-tool dispatch on a no-action message is a FAIL. If it loops on `search_tools`,
  see the next case.
- **Two identical `search_tools(query=…)` re-emissions** → Leg-09 backstop keys them identical and synthesizes
  a closing from the (search-result) content, ending the turn. That's a graceful stop, but it means the model
  failed to advance to the concrete call — count it toward the abandon signal, not a hard error. A *different*
  query or a concrete call afterward is the success path and is not redundant.
- **`SearchTools` returns canned/stub data in some contexts** (the `_search_stubs` path) — ensure the live
  agent uses the real `SearchTools`, not the stub, so discovery reflects the real registry. (The stub is a
  test seam; confirm which is wired for a real agent.)
- **MCP-heavy agent** → discovery scales fine (the model searches by intent; only matched tools render),
  which is a *further* argument for 08A over the full-catalog dump that would balloon the prompt.
- **Capable models** → completely unaffected (the addendum + visibility-as-text only apply on the
  `supports_tools=False` branch).
- **`DEGRADED_BASE_PROMPT` still mentions the `continue` tool** ("call the `continue` tool") while the degraded
  catalog shows only `search_tools` — a pre-existing tension that 08A's discovery-only framing makes more
  visible (the model could try `search_tools(query="continue")`). **Do NOT fold a fix into 08A** (it touches
  `config.py` and is out of this leg's scope). Watch for it in the live runs; if the model actually chases
  `continue`, record it as a follow-up (candidate for the debrief's Rec 3 `DEGRADED_BASE_PROMPT` refactor).

## Accept / Abandon Decision Gate

**Concrete pass/fail bar (temperature=0.0 makes each distinct prompt deterministic, so a single run per prompt
is a valid measurement — no need to average across samples for the *same* prompt):**
- **Over-routing fixed (hard requirement):** with a full-catalog agent, BOTH "Hello there!" (greeting) and
  "What is a haiku?" (knowledge question) → **zero concrete-tool dispatches** each (a read-only `search_tools`
  probe that then resolves to a conversational answer is acceptable; any `shell`/`read_file`/etc. dispatch is
  a FAIL). One deterministic run each.
- **Hop preserved (requirement for ACCEPT):** across **3 distinct action requests** (e.g. "how many files are
  in the current directory", "read the file X", "what's today's date via the shell"), the blind→search→call
  hop completes end-to-end (tool result present, answer reflects it) on **at least 2 of 3**. 0/3 or 1/3 → the
  hop is unreliable → **ABANDON**.

After the live verification, record one of:
- **ACCEPT** — over-routing is fixed against a full-catalog agent (greeting + knowledge question → no concrete
  tool) AND the blind→search→call hop completes reliably enough (≥2/3 per the bar above) that genuine tool use
  is preserved. Then: flip
  this leg to `landed`, update the behavior-test spec status, re-open/close the relevant mission criterion,
  and skip 08B/08C. Record the decision + evidence in the flight log.
- **ABANDON** — over-routing is fixed but the 4B model cannot reliably complete the discovery hop (it loops on
  `search_tools` or never reaches the concrete call), so genuine tool use regresses below the bar. Then:
  revert 08A's code changes (or leave them behind a clearly-marked disabled path), record the finding +
  evidence in the flight log, and proceed to design **08B** (passive recovery, no inducement) in full.

State the decision explicitly — do not leave it implicit in a run log only (a Flight 3 debrief lesson:
leg acceptance boxes drifted from reality).

## Files Affected

- `the_one/agent/degraded_tools.py` — reframed addendum (converse-default + discovery-only; renders
  `_loaded_schemas` when populated).
- `the_one/agent/core.py` — `_build_degraded_messages` sources the visibility-filtered set + updated
  docstring; `search_tools` dispatchable on the degraded path.
- `tests/test_degraded_tool_prompt.py` — invert/rename `test_catalog_excludes_search_tools_and_continue`,
  `test_worked_example_present`, `test_tool_gating_clause_present` (see Verification Steps for the exact
  inversions).
- `tests/test_agent_degraded_injection.py` — re-author `test_addendum_injected_and_search_tools_suppressed`
  (the suppression assertions flip) + add a discovered-tool-appears-after-search case.
- `tests/behavior/gemma-tool-use-recovery.md` — CP5 amended to a full-catalog agent + a greeting case; new
  run log under `runs/`.
- `missions/16-…/flights/03-…/flight-log.md` — leg-08A entry + the accept/abandon decision.
- `missions/16-…/mission.md` — only if 08A's outcome changes a success criterion's state.

## Citation Audit

8 citations verified against current code at leg design time (2026-06-19):
- `agent/core.py:_build_degraded_messages` — OK (sources `self.tools.all_schemas()` minus
  `{"search_tools","continue"}`; builds `[Message.system(degraded_system), *self.messages[1:]]`).
- `agent/core.py:_compute_visible_schemas` — OK (returns `[SEARCH_TOOLS_SCHEMA, CONTINUE_SCHEMA] +
  self._loaded_schemas`).
- `agent/core.py:SEARCH_TOOLS_SCHEMA` — OK (module-level schema dict).
- `agent/core.py:_executed_key` — OK (Leg-09 backstop key on raw `tc.arguments`).
- `agent/degraded_tools.py:build_degraded_tool_prompt` / `_PROTOCOL_HEADER` — OK (full-catalog renderer;
  format-first header with `shell(command="echo hello")` example + gating/contrast clauses).
- `agent/config.py:DEGRADED_BASE_PROMPT` — OK (BASE_PROMPT minus the Tool-discovery section; comment cites
  DD-G).
- `the_one/tools/_search_tools.py:SearchTools` — OK (`name = "search_tools"`, registered by the factory;
  `_on_match` mutates `_loaded_schemas`).
- `the_one/llm/ollama_provider.py:_recover_into_tool_calls` — OK (recovery fires when structured
  `tool_calls` is empty; used by both `complete` and `stream`).
