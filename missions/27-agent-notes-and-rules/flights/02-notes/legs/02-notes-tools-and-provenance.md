# Leg: notes-tools-and-provenance

**Status**: completed
**Flight**: [Notes](../flight.md)

## Objective

Give an agent with notes on three tools, `save_note`, `update_note` and
`forget_note`. They are visible from its first turn. Each write records its
origin and whether content not from the operator was in the conversation the
model had seen. Each write respects the switch and the limits, and is visible in
the tool stream. The deterministic contract tests prove that a planted
instruction can never produce an unflagged note.

## Context

- Flight DDs that govern this leg:
  - **DD2:** the execute-time switch re-check is implemented in leg 1's
    repository; the tools surface its refusal.
  - **DD3:** the provider, direct registration, and baseline seeding.
  - **DD5:** tools bound to their Agent, `TurnContext` (peer and writes,
    mutated and never set inside a tool), the set sites, the unset fallback,
    and one shared fallback counter.
  - **DD6:** the backwards anchor, positional attribution,
    `m.tool_result.tool_call_id`, the trusted set (the notes tools,
    `search_tools`, `continue`), `peer_name is not None`, the update OR and
    merge, fail-closed sources.
  - **DD7:** origin.
  - **DD8:** refusal texts, and a duplicate does not count toward the limit.
  - **DD12:** contract cases.

  Read [flight.md](../flight.md).
- **Leg 1** (`notes-store-and-prompt`) provides:
  - `AgentNoteRepository` with `create(...)`, which returns `(note,
    created)`, `update_by_agent(...)` and `forget_by_agent(...)`; each raises
    `NotesDisabledError`, `NoteLimitError` or `NoteDuplicateError`;
  - `the_one/db/_notes.py` constants and `NOTE_WRITES_PER_TURN`;
  - `notes_enabled` on `AgentConfig`;
  - the prompt block.

  Read the flight log's leg 1 entry for what actually landed.
- **Frozen loop:** `the_one/agent/core.py` is **not modified**. If a test shows
  a `TurnContext` set around `step` is not visible and mutable inside
  `tool.execute`, **stop and signal `[BLOCKED:frozen-loop]`** (the flight's
  divert condition).

## Inputs

- Leg 1 landed, uncommitted, on `flight/02-notes`.

## Outputs

- `the_one/notes/__init__.py`, `the_one/notes/tools.py` (the three tool
  classes and the taint scan) and `the_one/notes/tool_provider.py`
  (`NotesToolProvider`).
- `the_one/agent/_context.py`: `TurnContext` and `current_turn`.
- The set sites in `app.py`, `inbound.py` and `cli.py`.
- `AgentFactory`: provider injection, registration, seeding, and binding after
  `Agent(...)`.
- `SECURITY-MODEL.md`: a new "Agent notes (M27 F2)" section.
- `the_one/agents.md`: the tools, provenance and context contract.
- Tests: `tests/test_notes_tools.py` (contract) and
  `tests/test_notes_context.py`; factory additions.

## Acceptance Criteria

**Context (DD5)**
- [ ] AC1. `the_one/agent/_context.py` defines a mutable `TurnContext`
      dataclass:
      - `peer: TurnPeer | None`, where `TurnPeer` holds `platform`,
        `connector_id`, `peer_id` and `peer_name`;
      - `session_id: str | None = None`;
      - `writes: int = 0`.

      The origin session id is `turn.session_id`, falling back to
      `current_chat_session_id`. That covers the REST path without changing
      `current_chat_session_id`'s existing behavior (decided at the leg
      review).

      It also defines `current_turn: ContextVar[TurnContext | None]` with
      default None.
- [ ] AC2. **First test written** (`tests/test_notes_context.py`): a real
      `Agent`, built with a `FakeLLM` scripting one tool call to a stub tool,
      runs `step` with `current_turn` set. Inside `execute`, the stub tool
      reads the context and increments `writes`, and after the step the outer
      object shows the increment. This pins the premise on this Python. If it
      fails, signal `[BLOCKED:frozen-loop]` with the output.
- [ ] AC3. `current_turn` is set and reset with the token pattern at every
      step site:
      - web: **inside `_process_and_broadcast`, around its single
        `session.agent.step(...)`** (`app.py` ~`:2159`), with
        `session_id=session.id` and `peer=None`. That one site covers both
        the WebSocket path (`_locked_message_processing` calls
        `_process_and_broadcast`) and the REST `/api/chat` handler
        (`app.py` ~`:2810`), which calls `_process_and_broadcast` directly
        and was missed in DD5. A test covers the REST path;
      - `_resume_paused_session`, beside `app.py:2463`, with
        `session_id=session.id`;
      - connector `dispatch_inbound`, beside `inbound.py:451`, with
        `session_id=session_row.id` and `TurnPeer(platform=envelope.platform,
        connector_id=..., peer_id=envelope.peer_id,
        peer_name=envelope.peer_name)`;
      - the CLI step (`cli.py:85`);
      - the two self-test steps (`app.py` around `:2736` and `:2750`), which
        are kept for consistency.

      A test covers the connector site: inside a stub tool during
      `dispatch_inbound`, the context's peer equals the envelope's.

**Tools (DD3, DD6, DD7, DD8)**
- [ ] AC4. `NotesToolProvider.get_tools_for_agent(config, *, agent_name)`
      returns the three tools when `config.notes_enabled`, and `[]` (with no
      database call) when it is off. The tools pass `agent_name` to
      `Tool.__init__`. Schemas:
      - `save_note(text: string)`;
      - `update_note(number: integer, text: string)`;
      - `forget_note(number: integer)`.

      Descriptions are short and flat, in line with DD9's wording: "saved
      notes", never "memories".
- [ ] AC5. `AgentFactory` takes `notes_provider` the way it takes
      `kb_provider` (`factory.py:280-299`), registers the notes tools after
      the KB tools **without** the `is_tool_enabled` filter, and **seeds** them
      in the DD-5/DD-6 seed block. `return Agent(...)` becomes `agent =
      Agent(...)`, then `tool.bind_agent(agent)` for each notes tool, then
      `return agent`. Factory tests check:
      - notes on: all three tools are registered and in `loaded_tool_names`,
        including under an `enabled_tools` whitelist that excludes them;
      - notes off: none are present;
      - the `_agent_name` plumbing assertion still holds.
- [ ] AC6. **Taint (DD6).** `compute_taint(agent, tool_call_id, turn)` returns
      `(untrusted: bool, sources: list[str])`. The tool reads its own call id
      from `the_one.agent._context.current_tool_call_id`, which
      `_execute_tool` sets before dispatch. A `None` id gives "unknown
      position". Unit tests that call `execute` directly set the variable
      explicitly, except the test that pins the `None` case:
      - it scans `agent.messages` **backwards** for the nearest assistant
        message whose `tool_calls` ids include `tool_call_id`; with no anchor
        the result is `(True, ["unknown position"])`;
      - for each message before the anchor:
        - a TOOL message is attributed to the nearest preceding assistant
          message's `tool_calls`, by `m.tool_result.tool_call_id`. A name
          outside `TRUSTED_TOOL_NAMES` adds that name; no match, or
          `tool_result is None`, adds `"unknown tool"`;
        - a USER message with `peer_name is not None` adds
          `peer:{peer_name}` (or `peer:` when the name is empty);
      - `turn.peer is not None` adds `peer:{name}`; `turn is None` adds
        `"unknown context"`;
      - an unbound tool returns `(True, ["unknown position"])`.

      Sources are deduplicated, ordered and capped at 10. `TRUSTED_TOOL_NAMES =
      {"save_note", "update_note", "forget_note", "search_tools", "continue"}`
      is defined once, beside the tools. Check the `search_tools` and
      `continue` names against `the_one/tools/_search_tools.py` and
      `core.py`'s continue handling.
- [ ] AC7. **`save_note(text)`:**
      - **Error mechanism (decided).** Every refusal **raises** an exception
        whose message is the exact refusal text, and the tools do **not**
        wrap it. `core.py`'s generic handler returns
        `ToolResult(content="[error] Tool execution failed: <text>",
        is_error=True)`, so the UI tool stream shows an error. Returning a
        string would show a refusal as a success. Tests assert
        `is_error is True` and that the content contains the text.
      - It refuses with "Note limit for this turn reached (5 writes)." when
        the turn's write count has reached 5. The count comes
        from `TurnContext.writes`, or from the shared fallback counter when
        there is no context.
      - Otherwise it computes taint and origin (DD7: session id from
        `turn.session_id`, falling back to `current_chat_session_id`; kind, platform and peer from
        `turn.peer`; the label from the session row's title when it can be
        read, else None) and calls `create`.
      - It increments the write count **only when a note was created or
        changed**.
      - It returns "Saved note [n]." or "Already saved as note [n]."
      - Repository errors become tool errors carrying their `detail` text.
        Raise an exception whose message is the detail, which the loop
        formats as `[error] Tool execution failed: …`, or follow how other
        tools signal errors; check `ConstraintError`'s formatting
        (`tools/base.py`).
- [ ] AC8. **`update_note(number, text)`** applies the same budget, taint and
      repository call. `update_by_agent(name, number, text, *, untrusted,
      sources)` returns `(note, changed)` and ORs the flag and merges sources.
      `changed=False`, for identical text, does not count toward the budget
      and returns "Note [n] is unchanged." Otherwise it returns "Updated note
      [n]." **`forget_note(number)`**
      calls `forget_by_agent` and returns "Forgot note [n]." It does not touch
      the budget. A missing number gives "No note [n]." as a tool error. With
      notes off, all three return the switch refusal "Notes are off for this
      agent."
- [ ] AC9. **Contract tests** (`tests/test_notes_tools.py`, using `FakeLLM`
      scripted turns through a real `Agent` from the factory or built
      directly, stub untrusted tools and a template database). Each case in
      the flight's DD12 list is its own test:
      - an earlier-turn fetch, then a save: flagged with `fetch_url`;
      - a fetch and a save in the same assistant message: not flagged;
      - ids repeating across turns: flagged;
      - Ollama bare-name ids identical every turn: flagged;
      - an orphaned TOOL result: flagged with "unknown tool";
      - a `continue` result: not flagged;
      - a web operator-only conversation: not flagged, origin `web` with the
        session id;
      - a connector peer turn: flagged with `peer:` and origin `connector`
        with the peer;
      - a restored history containing an earlier fetch: flagged;
      - a restored clean history: not flagged;
      - **resume:** a stub tool returns `ToolResult` metadata
        `{"is_auth_required": True}` to pause the turn. The test then sets
        `current_turn` and drives `agent.resume_after_auth()`, as
        `_resume_paused_session` does. A later `save_note` gets the correct
        flag;
      - a save in iteration 2 of the **same turn**, after a fetch in
        iteration 1: flagged;
      - several notes calls in one assistant message: the budget applies in
        order, and the sixth is refused;
      - fail-closed: an unbound tool gives "unknown position", and a `None`
        tool call id gives "unknown position";
      - a flagged note updated in a clean conversation: stays flagged;
      - a newline-injection note: stored on one line, and rendered with no
        forged `[n]` line in a rebuilt prompt;
      - notes off mid-conversation: all three refuse;
      - the limits (per note, total, 5 writes, a duplicate not counted) and
        numbering;
      - **a planted-instruction test:** a stub `fetch_url` whose content
        tells the model to save a note, with the `FakeLLM` scripted to obey.
        The note exists and is flagged. **This is the mission's contract
        test.** Name it
        `test_planted_instruction_never_yields_an_unflagged_note`.
- [ ] AC10. An end-to-end tool-stream check: a mock or `FakeLLM` web turn's
      `save_note` call and its result appear as normal tool messages in the
      persisted session. They are ordinary tool calls; no special handling.

**Docs and gates**
- [ ] AC11. `SECURITY-MODEL.md` gains "Agent notes (M27 F2)", modelled on the
      "Self-configuration surface" section, covering:
      - the threat: ungated writes, with no approval gate by design, that
        persist and reach later conversations, including **other peers' and
        DMs'** conversations, since notes are shared agent-wide;
      - the mitigations: off by default; provenance and the "unverified" flag
        across the whole conversation; the bounded, delimited block; one-line
        normalisation and delimiter neutralisation; limits; rules outrank
        notes; no agent path to rules or the switch;
      - the residual risks: flags do not propagate through notes; every
        connector-conversation note is flagged; outside text that bypasses
        the scan (MCP tool names and descriptions in `tools=` and
        `search_tools` output, KB tool names); a model may still follow a
        planted note's content even though it is flagged, so the operator's
        review is the control.
- [ ] AC12. `the_one/agents.md` documents:
      - the tools;
      - `TurnContext` and its set-site list, which every **new** `agent.step`
        call site must join;
      - the taint algorithm;
      - `TRUSTED_TOOL_NAMES`, and that a new tool is untrusted unless added
        there deliberately.
- [ ] AC13. `make test-unit` passes, and `ruff` is clean.

## Verification Steps

- AC2 first: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_notes_context.py -x --timeout 60`.
- AC1-AC10: `tests/test_notes_context.py`, `tests/test_notes_tools.py`,
  `tests/test_factory.py`, `tests/test_connectors_inbound.py` (the peer
  context).
- AC13: `make test-unit`; `ruff check the_one/ tests/ scripts/`;
  `ruff format --check the_one/ tests/ scripts/`.

## Implementation Guidance

1. Write `TurnContext`, `current_turn` and the AC2 test first. Proceed only if
   it passes.
2. Add the set sites. Follow the existing `current_chat_session_id` token
   pattern exactly (set before the step, reset in `finally`).
3. Write `the_one/notes/tools.py`:
   - test doubles: `tests/conftest.py`'s `StubTool` skips
     `super().__init__` and cannot read context, so the AC2 premise test and
     the "fetch" stubs use small custom `Tool` subclasses;
   - a `_NotesToolBase(Tool)` holding `_agent` (set by `bind_agent`) and the
     shared fallback counter (a small mutable holder the provider gives all
     three tools);
   - `compute_taint` as a module function, so it can be tested directly;
   - the three subclasses.

   The repository is reached through `get_connection()` (lazy import) at
   execute time, like the KB tools.
4. Write `NotesToolProvider`: it builds the three tools with a shared counter
   holder.
5. **Factory:**
   - constructor injection (default `NotesToolProvider()`);
   - registration after the KB block;
   - seeding: extend the seed loop, or add a parallel loop over the notes tool
     names;
   - binding after construction.

   Keep the existing comments' style. Explain why the tools are outside the
   whitelist filter (DD3) and why seeding is factory-only (`core.py` frozen).
6. Contract tests: use `tests/conftest.py`'s `FakeLLM` and `StubTool`. Stub
   tools named `fetch_url` and similar make the untrusted results. Build the
   `Agent` through the factory with notes on, or construct the tools with
   `bind_agent` on an `Agent` built directly. Set `current_turn` and
   `current_chat_session_id` as the production sites do.
7. Docs per AC11 and AC12.

## Edge Cases

- **A tool call with arguments of the wrong type:** coerce an int-string
  `number`, and raise a refusal for anything else. A missing or extra argument
  is a `TypeError` from `**args`, already formatted by the generic handler.
- **Several notes calls in one assistant message:** each counts toward the
  budget in order, and the sixth refuses.
- **A note saved in the same message as `forget_note`** of another: both
  apply.
- **No chat session** (CLI): origin kind `other`, session id None, label None.
- **The session row is unreadable** (deleted mid-turn): label None, and the
  note is still saved.
- **A peer with an empty-string name:** the source is `peer:` and the origin
  peer name is `""`.
- **Disabled between build and call:** the repository raises
  `NotesDisabledError`, and the tool returns the refusal.

## Files Affected

- `the_one/notes/__init__.py`, `tools.py` and `tool_provider.py` (new).
- `the_one/agent/_context.py`, `the_one/agent/factory.py`.
- `the_one/interfaces/web/app.py`, `the_one/connectors/inbound.py`,
  `the_one/interfaces/cli.py`.
- `SECURITY-MODEL.md`, `the_one/agents.md`.
- `tests/test_notes_context.py` (new), `tests/test_notes_tools.py` (new),
  `tests/test_factory.py`, `tests/test_connectors_inbound.py`.

## Citation Audit

Checked against `82a0396`:
- The `current_chat_session_id` set sites are at `app.py:999` (reset `:1019`),
  `app.py:2463` (reset `:2512`) and `inbound.py:451` (reset `:464`).
- The CLI step is at `cli.py:85`.
- The self-test steps are at `app.py:2736` and `:2750`.
- `kb_provider` injection is at `factory.py:280-299`, and the KB registration
  at `:484`.
- The seed block and `return Agent(...)` are at `factory.py:505-530`.
- `tools/connector_send.py` shows a built-in reading `current_chat_session_id`.
- `SECURITY-MODEL.md` "Self-configuration surface" is at `:169`.

All were verified; line numbers drift after leg 1, so re-locate by symbol.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
