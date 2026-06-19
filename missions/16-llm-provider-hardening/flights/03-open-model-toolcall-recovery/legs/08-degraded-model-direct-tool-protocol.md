# Leg: degraded-model-direct-tool-protocol

**Status**: completed
**Flight**: [Open-Model Tool-Use Robustness (#105)](../flight.md)

> **DURABLE FIX — operator-directed MISSION-scope expansion into `the_one/agent/` (2026-06-19).**
> Two behavior-test runs proved recognizer-based recovery is best-effort, not reliable, for gemma3:4b
> (it improvises a new tool-call format nearly every turn). The durable fix is upstream: **tell the
> non-tool model exactly which tools exist and the one format to call them in**, then recover that
> deterministic format with the existing kernel. This necessarily touches the agent/prompt layer the
> mission scoped out — an explicit, operator-authorized boundary expansion. See flight-log Decisions.

## Objective

For a model where `supports_tools()` is `False` (e.g. gemma3:4b via Ollama), make tool use **reliable**
by injecting a **direct tool protocol** into the request the agent loop already sends on the degraded
path: a concise catalog of the available tools **plus** one pinned, deterministically-parseable
call format — ` ```tool_code\nname(arg="value")\n``` ` — so the model emits a call the leg-01/07
recovery kernel lifts every time, instead of improvising unparseable shapes.

## Context

- **Root cause** (two behavior-test runs, `runs/2026-06-19-00-27-41.md` + `…-01-03-58.md`): the
  non-tool model is given **no concrete tool-call format** and the `search_tools` discovery protocol
  (BASE_PROMPT, `config.py:9-54`) is unreliable for it. It guesses a different serialization each turn.
- **Why this can't stay in `the_one/llm/`** (Explore map): the agent loop forces `tool_schemas=[]` for
  degraded models (`core.py:185-188`), so the provider never receives the tool catalog — it has nothing
  to tell the model about. The catalog + system prompt live in the agent layer.
- **The exact seam already exists**: `core.py:167-188` resolves `supports_tools` once and branches; the
  `else: tool_schemas = []` arm (`:187-188`) is the degraded path. A comment at `:171-176` even calls
  out "Ollama Gemma … run as a single-shot chat" — that wording is the stale one the flight already
  flagged (recovery makes it multi-iterate); this leg makes the degraded path *actively tool-using*, so
  the comment is corrected here.
- **Reuses, unchanged**: the recovery kernel (`_toolcall_recovery.py`, `tool_code` fence from leg 07),
  the Ollama recovery wiring (`ollama_provider.py`), and `Tool.bind_positional_args` (leg 07). This leg
  supplies the *input-side* reliability; those supply the *output-side* parsing.

## Design Decisions

**DD-A — Inject a direct tool protocol on the degraded path; the wire `tools=` stays `None`.** In the
`not supports_tools` branch, the agent loop builds a **direct-tool-protocol system addendum** and sends
it with the request. The Ollama wire `tools=` array stays `None` (Ollama still 400s if tools are
offered to gemma — the Flight-1 finding is unchanged). The tool information travels in the **prompt**,
not the wire. The model's resulting ` ```tool_code ` call is recovered by the existing kernel and
dispatched (DD6 unchanged — the loop already dispatches `response.tool_calls`).

**DD-B — Catalog = the full registry minus the virtual tools.** Source the catalog from
`self.tools.all_schemas()` (`ToolRegistry.all_schemas()`, `tools/base.py:187-188` — every *registered*
tool's `to_schema()`), **NOT** `_compute_visible_schemas()` (which returns only the search_tools
baseline + discovered set — the opposite of what's wanted). **Exclude `search_tools` and `continue` by
name**: `search_tools` is the discovery dance being replaced (re-listing it re-introduces the DD-G
contradiction) and `continue` is a turn-control signal with no direct-call meaning. Filter by name so it
holds whether or not `continue` is a registered `Tool`. The addendum lists each remaining tool's name +
one-line description + parameter names/required. (Cap/cost: if the catalog is large — many MCP tools —
list names + short descs only; keep it compact for a small model.) **Unit-test the ABSENCE of
`search_tools`/`continue`, not just the presence of `shell`.**

**DD-C — Pin ONE format, matched to the kernel: ` ```tool_code\nname(arg="value")\n``` ` (keyword
args).** The addendum instructs: *to call a tool, output exactly one fenced block tagged `tool_code`
containing a single call with keyword arguments, and nothing else.* Keyword form (`shell(command="…")`)
is pinned because the kernel parses kwargs first-class → `{"command": "…"}` dispatches directly (no
positional binding needed; leg-07 binding remains the safety net if the model uses positional). One
call per turn; the loop's natural iteration handles multi-step.

**DD-D — Injection is ephemeral per degraded turn, by REPLACING `messages[0]` — not a second system
message.** `messages[0]` is **always** the system prompt (`core.py:92`, `:367`). Do NOT prepend a second
`role:"system"` message (two adjacent system messages are weaker prompt design for a 4b model and leave
the contradictory base discovery text in play — see DD-G). Instead, for the degraded `stream()` call,
build an ephemeral list `[Message.system(degraded_system), *self.messages[1:]]` where `degraded_system`
is the composed degraded prompt (DD-G), **without mutating `self.messages`** (history stays clean; the
catalog re-renders each turn). Only the degraded branch builds this; the tool-capable branch keeps
`messages=self.messages` unchanged. **Pin the exact resulting message shape** (one leading system
message, count/order) in a unit test.

**DD-G — Suppress the `search_tools` discovery block on the degraded path (the single biggest
compliance lever).** The BASE_PROMPT opens with a hard "you have only `search_tools`+`continue`; call
`search_tools` to discover tools" protocol (`config.py:13-30`) — directly **contradictory** with the
addendum's "here is the full catalog, call tools directly." Both run logs show gemma steered into
emitting `search_tools` calls *because of this text*. On the degraded path, compose `degraded_system` =
the direct-tool-protocol addendum (DD-C) **+ a degraded base that OMITS the search_tools discovery
section** (keep the non-discovery parts: identity, the "take the action / prefer the right tool /
isolated box" guidance, turn semantics, and the persona). Implement by composing from the prompt's parts
in the degraded branch (the ephemeral message list is built there, so `messages[0]` is swapped without
touching `compose_system_prompt`'s persisted output or the capable path). Make this a named, tested
behavior: assert the degraded system message does NOT contain the "call `search_tools`" discovery
instruction.

**DD-E — Correct the stale "single-shot" degraded-path docs** (the flight's existing doc-drift
Anomaly): update the `core.py:171-176` comment and the matching `agents.md` degradation note — the
degraded path now multi-iterates AND actively uses tools via the recovered protocol.

**DD-H — Deliberately taking the prompt-injection lever, NOT constrained decode; escalation destination
pre-recorded.** Both run logs' top durable recommendation was **constrained decoding** (force a
parseable shape at the decoder). This leg instead instructs via the prompt, because constrained decode
is *not* a drop-in here: `OllamaProvider` talks to the **OpenAI-compat `/v1/chat/completions`** endpoint
(`ollama_provider.py:126`), which does **not** expose Ollama's native `format`/grammar JSON-schema
constrained decode (that's on the native `/api/chat`); using it would mean a provider-layer change back
in `the_one/llm/` and a conditional-application problem (can't force a tool-call JSON on every
conversational turn). Prompt-injection is the lower-scope, lower-risk lever. **Honest efficacy note:**
this should materially raise gemma3:4b's compliance from the observed ~0% (it removes the two confounds —
no concrete format + the search_tools steer), but instruction-following is **not guaranteed** for a 4b
model. **If gemma still won't reliably comply after this leg, the agreed escalation is constrained
decode via the native `/api/chat` `format`/grammar (a follow-up that re-expands into `the_one/llm/`) —
NOT another recognizer** (the run logs explicitly warn against whack-a-mole). This is pre-recorded so a
failed re-run points at the right next step.

**DD-F — Mission-boundary record.** This leg edits `the_one/agent/core.py` (degraded-branch injection)
and adds an agent-layer helper (`the_one/agent/` — a new module or `config.py`). The mission scoped
`the_one/llm/` + Message protocol + codec only. This is a **deliberate, operator-authorized expansion**,
narrowly scoped to **tool exposure / prompt for non-tool-capable models** — it does NOT touch the
iteration/auth-pause logic, add a framework, or change the `LLMProvider` contract. Annotated at the
mission header (not a body rewrite — the mission's original framing is preserved as the record).

## Inputs

- `the_one/agent/core.py:167-188` (the `supports_tools` resolve + degraded branch + `stream()` call),
  `the_one/agent/config.py:9-54` (BASE_PROMPT), the tool registry (`self.tools`, `ToolRegistry` at
  `tools/base.py:114-131` — `to_schema()` / iteration to build the catalog).
- The recovery kernel + `Tool.bind_positional_args` (legs 01/07) — used unchanged.

## Outputs

- `the_one/agent/` — a helper that renders the direct-tool-protocol addendum from a list of tool
  schemas (new module `the_one/agent/degraded_tools.py` **or** a function in `config.py`).
- `the_one/agent/core.py` — the degraded branch builds the addendum + sends an augmented message list;
  the stale comment corrected.
- Unit tests for the addendum renderer + the degraded-injection behavior.
- A passing behavior-test re-run.

## Acceptance Criteria

- [x] **Addendum renderer** (`build_degraded_tool_prompt(tool_schemas) -> str`): given tool schemas,
      returns a string that (a) lists each tool's name + description + parameters, and (b) pins the exact
      ` ```tool_code\nname(arg="value")\n``` ` format with a "emit only the fenced block" instruction.
      Deterministic; unit-tested (includes the `shell` tool → output names `command`).
- [x] **Degraded branch injects, tool-capable branch unchanged**: when `supports_tools()` is `False`,
      `stream()` is called with an augmented message list whose leading `system` message contains the
      addendum, and `tools=None`. When `True`, behavior is byte-identical to today (no addendum,
      `tools=` array as before). `self.messages` is NOT mutated by the injection (verify the persisted
      history is unchanged). Unit-tested with a mock provider capturing the `messages` it receives.
- [x] **Catalog = full registry minus virtual tools** on the degraded path: sourced from
      `self.tools.all_schemas()`, **excluding `search_tools` and `continue` by name**. Test asserts the
      addendum lists `shell` AND does **not** list `search_tools`/`continue`.
- [x] **search_tools discovery suppressed (DD-G)**: the degraded system message does **not** contain the
      "call `search_tools`" discovery instruction, and there is exactly **one** leading `system` message
      (no double-system); `self.messages[1:]` is passed through unchanged. Unit-tested on the exact
      degraded message-list shape.
- [x] **End-to-end recovery still dispatches**: a degraded-model turn whose content is
      ` ```tool_code\nshell(command="echo hi")\n``` ` recovers → dispatches → executes (covered by the
      behavior test; optionally a focused agent test with a mock provider returning that content).
      *(Focused agent test added — `test_degraded_loop_dispatches_recovered_tool_code`.)*
- [x] **Docs corrected** (DD-E): the `core.py:171-176` "single-shot" comment and the `agents.md`
      degradation note reflect the now-tool-using, multi-iterating degraded path.
- [x] **`agent/core.py` change is bounded** to the degraded branch (build + augment + send) — no
      iteration/auth-pause logic touched. Reviewer confirms the diff scope.
- [x] `make test-unit` stays green (3273 baseline + new tests → 3285 passed / 18 skipped).
- [ ] **END-TO-END: re-run `/behavior-test gemma-tool-use-recovery` → PASS** against the host-native
      dev instance: a real gemma turn, now given the direct protocol, **dispatches and executes** the
      shell tool (tool-result present, echoed marker returned) with no raw fenced block in the final
      message. New run log committed. Spec status flips `draft` → `active` on pass. The flight does not
      land until this passes. *(If gemma still fails to follow the format after the protocol injection —
      a genuine small-model limitation — that is a material finding to escalate, not to paper over.)*

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh <new-tests> tests/test_toolcall_recovery.py -x --timeout 30` — green.
- `make test-unit` — full hermetic suite green.
- `git diff the_one/agent/core.py` — change confined to the degraded branch + the comment fix.
- Restart the :8585 dev instance (it has no `--reload`), then `/behavior-test gemma-tool-use-recovery` → pass.

## Implementation Guidance

1. **Addendum renderer** (`the_one/agent/degraded_tools.py`, new — keeps `core.py` lean and the logic
   unit-testable in isolation): `build_degraded_tool_prompt(tool_schemas: list[dict]) -> str`. **Order
   for a small model: format spec FIRST (single unmissable block) + ONE concrete worked example, THEN
   the catalog.** Shape:
   ```
   You do not have native tool-calling. To call a tool, output EXACTLY one fenced block and nothing
   else in the message — no prose before or after:
   ```tool_code
   tool_name(arg1="value1", arg2="value2")
   ```
   Rules: use KEYWORD arguments matching the parameter names; use DOUBLE-QUOTED string values (do not
   put unescaped double-quotes inside a value); call ONE tool per message — you will get its result and
   may call another.
   Example — to run a shell command:
   ```tool_code
   shell(command="echo hello")
   ```
   Available tools:
   - shell(command): Execute a shell command...
   - ...
   ```
   Pure function; no I/O. Keep the catalog compact (DD-B). (The "emit ONLY the fenced block" instruction
   reduces the chance gemma wraps the call in malformed prose/second fence; the kernel preserves prose
   but prose-free output is cleaner.)
2. **Degraded base prompt** — to suppress the search_tools discovery block (DD-G) cleanly, add a
   `DEGRADED_BASE_PROMPT` (or a small composer) in `the_one/agent/config.py` = the BASE_PROMPT with the
   "Tool discovery / call search_tools" section (`:13-30`) removed, keeping identity + the non-discovery
   "Tool use" guidance + turn semantics. (Persona still appends as today.) This keeps the swap testable
   and avoids ad-hoc string surgery in `core.py`.
3. **Degraded branch** (`core.py:185-188`): when `not supports_tools`, build
   `addendum = build_degraded_tool_prompt(degraded_catalog)` where `degraded_catalog =
   [s for s in self.tools.all_schemas() if s["name"] not in {"search_tools", "continue"}]`; compose
   `degraded_system = addendum + "\n\n" + <degraded base + persona>`; construct the ephemeral
   `messages = [Message.system(degraded_system), *self.messages[1:]]` for the `stream()` call (do NOT
   mutate `self.messages`). Keep `tools=None` on this path. The capable branch keeps
   `messages=self.messages`. Factor the `stream()` call so both branches share it with the right
   `messages`/`tools`.
3. **Comment fix** (DD-E): rewrite the `:171-176` comment — the degraded path is no longer "single-shot
   chat"; it injects a direct tool protocol and multi-iterates as recovered calls are dispatched. Update
   the matching `agents.md` degradation note (re-locate it; the flight log notes the old `:798` citation
   drifted).
4. **Tests**: renderer unit tests (format pinned, shell listed with `command`, empty catalog edge);
   a degraded-injection test using a mock provider (e.g. extend `the_one/llm/mock.py` or a stub) that
   captures the `messages` it receives — assert the addendum system message is present on the degraded
   path, absent on the capable path, and `self.messages` is unmutated; an end-to-end-ish agent test
   where the mock provider returns ` ```tool_code\nshell(command="echo hi")\n``` ` and the shell call is
   dispatched (recovery + binding already covered, but this pins the full degraded loop).
5. **Behavior-test re-run** (Orchestrator does this, not the Developer): restart :8585, run
   `/behavior-test gemma-tool-use-recovery`.

## Edge Cases

- **Large catalog (many MCP tools)** → compact rendering (names + short descs); optional cap with a
  note. Don't blow the small model's context.
- **Model still emits a non-`tool_code` fence or positional args** → the kernel's other recognized
  tags + leg-07 positional binding remain the safety net. The protocol improves reliability; the
  recovery breadth catches near-misses.
- **Capable models** → completely unaffected (addendum only on the `supports_tools=False` branch).
- **Model emits prose + a fenced call** → recovery strips the fence (DD4); prose preserved.
- **Genuine small-model non-compliance** → if gemma3:4b still won't follow even an explicit format, that
  is a real capability finding (escalate per the acceptance criterion) — not something to hide by
  loosening the test.

## Files Affected

- `the_one/agent/degraded_tools.py` — new addendum renderer (agent layer — mission-boundary expansion).
- `the_one/agent/config.py` — `DEGRADED_BASE_PROMPT` (BASE_PROMPT minus the search_tools discovery block, DD-G).
- `the_one/agent/core.py` — degraded-branch injection (compose degraded system, ephemeral message list) + the `:171-176` comment fix.
- `the_one/agents.md` — degradation-note correction.
- `tests/` — renderer unit tests + degraded-injection/mock-provider tests.
- `tests/behavior/gemma-tool-use-recovery.md` — status `draft` → `active` after the re-run passes.
- `tests/behavior/gemma-tool-use-recovery/runs/{new-ts}.md` — the passing re-run log.
- `missions/16-…/mission.md` — header annotation recording the agent-layer scope expansion (not a body rewrite).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [~] All acceptance criteria verified EXCEPT the **behavior-test re-run** (deferred to Orchestrator)
- [x] `make test-unit` green (3285 passed / 18 skipped); `agent/core.py` diff confined to the degraded branch + comment
- [x] Stale "single-shot" docs corrected (`core.py` + `agents.md`)
- [x] Mission header annotated with the scope expansion
- [x] Update flight-log.md with the leg-08 progress entry (re-run result deferred to Orchestrator)
- [ ] Flip the behavior-test spec `draft` → `active` (passing) — *Orchestrator, after the re-run*
- [x] Set this leg's status to `landed`; mark leg 05 landed — *leg-05 marking deferred to Orchestrator (behavior test verifies)*
- [ ] Check off this leg in flight.md — *Orchestrator, Phase 2d*
- [ ] (After this: resume agentic-workflow Phase 2d — flight review + commit)
