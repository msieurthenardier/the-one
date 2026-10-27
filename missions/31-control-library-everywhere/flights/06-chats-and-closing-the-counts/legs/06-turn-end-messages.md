# Leg: turn-end-messages

**Status**: ready
**Flight**: [Chats, and closing every count to zero](../flight.md)

## Objective
Make a turn end honestly in two places:
- **F2:** when an agent stops because it ran out of steps (`max_iterations`), every interface says so: the web chat (a notice line with a settings link), connector chats (a neutral plain line), the REST `/api/chat` result (a key) and the CLI (a line). Nothing is stored in history.
- **0.2 (DD11 2):** an `openai-compatible` provider's connection errors name that provider type, not "Ollama".

The leg also drafts the behavior spec `agent-step-limit-notice`.

## Context
- **Flight decisions:** DD8 (F2's flag lifecycle, the frame contract, the web, connector, REST and CLI wording, the tests), DD11 2 (the wording fix and its divert line), DD15 (the new spec) and ledger rows 28 and 31.
- **The agent loop** (`the_one/agent/core.py`):
  - `step()` (`:215`) appends the user message, clears `_deferred_tool_calls`, re-primes `_remaining_iterations = self.max_iterations` (`:245`) and runs `_run_iterations` (`:249`).
  - `_run_iterations` loops `while self._remaining_iterations > 0:` (`:286`), consuming one iteration up front. Its `return`s are all non-exhaustion exits:
    - a text-only answer (`:326`);
    - the degraded backstops (`:356`, `:362`);
    - an auth pause (`:375`).
  - **Leaving the `while` without a `return` is exhaustion.**
  - `resume_after_auth()` (`:518`) is a no-op without deferred calls (`:535`). It re-dispatches the deferred calls, returns on a re-pause (`:562`), then runs `_run_iterations()` with the remaining budget, which may be 0, so the `while` is skipped at once: exhaustion.
  - `reset()` (`:662`) sets the budget to 0 (`:669`).
- **The web paths** (`the_one/interfaces/web/app.py`):
  - **`_process_and_broadcast`** (the WebSocket turn and the REST `/api/chat` handler, `:3020-3046`) runs `async for msg in session.agent.step(...)` (`:2299`). Then come the visibility tagging, `_save_session_to_db` (`:2534`), and, `if not paused:`, the usage persist, pending revisions and `{"type": "done"}` (`:2568`). An exception sends `{"type": "system", "content": f"Agent error: {exc}"}` (`:2515`).
  - **`_resume_paused_session`** runs `async for msg in session.agent.resume_after_auth()` (`:2621`). Inside `if not re_paused:` it applies pending revisions and sends `done` (`:2643`), **before** the tail's save (`:2666`).
  - `_send_to_session` (`:1909`) broadcasts only. `Session.add_event` (`:766`) appends to the in-memory `Session.history` (`:743`) that `session_joined` replays (`:1865`).
- **Connectors** (`the_one/connectors/inbound.py`):
  - `dispatch_inbound` runs `async for _ in agent.step(envelope.text): pass` (`:472`), then `_bind_peer_name`, `tag_post_step_visibility` and `_auto_deliver_reply(...)` (`:247-345`), then persists `encode_messages(agent.messages)`.
  - **`_auto_deliver_reply`** returns early when the agent already sent through `send_to_platform_channel` (`:293-302`). Otherwise it delivers the final assistant text when it is non-empty, through `manager.client_for(connector_id)` (`:317`). It logs and drops when there is no client or the send fails.
  - Its target is built from the envelope (`PeerTarget` for a DM, `ChannelTarget` otherwise).
- **The CLI** (`the_one/interfaces/cli.py:88`): `async for msg in agent.step(user_input):` prints assistant text and tool results with `rich`.
- **The web client** (after legs 04 and 05c): turn frames are handled in `js/areas/chat/turn-frames.js` behind the session-state gate (`session-state.js` `onFrame`/`accepts`, joined only). The transcript renders lines through `App.ui.notice`, which takes a body Node. The agent record comes from the client store (`App.store.peek('agents')`).
- **0.2.** `PROVIDER_TYPE_MAP` maps `"openai-compatible": "ollama"` (`the_one/llm/registry.py:22`). The `ollama_api.py` errors hard-code "Ollama", for example `ConnectionError(f"Cannot connect to Ollama at {url}: {exc}")` (`:101`, `:103`, and others).
  - Two known probes call the Ollama-only `/api/show` on an `openai-compatible` provider and fail softly: `supports_tools` → `get_model_capabilities` (`ollama_provider.py:294-302`; the failure is swallowed at `ollama_api.py:215-218`) and `_resolve_max_context_tokens` (`ollama_provider.py:264-279`). They stay as they are.
  - **Divert:** any other Ollama-only call on this type is raised as its own question.
- **The docs to update:**
  - `the_one/agents.md`: the WebSocket event table and the session-scoped frame list; `step_limit` is added;
  - `SECURITY-MODEL.md` only if it lists frames (grep first).
- **The eval rule** (CLAUDE.md "Prompt evals") applies only to platform prompt text. This leg changes no prompt text: the notice is never stored or sent to the model.

## Inputs
- Batch B3 (legs 04, 05a, 05b, 05c) landed and committed: the chat controls, including `App.ui.notice`, and the migrated transcript.

## Outputs
- **`Agent.stopped_at_step_limit`** (a public boolean attribute, default `False`, documented in the class docstring):
  - **cleared** at the entry of `step()`, `resume_after_auth()` (before its no-op return) and `reset()`;
  - **set** to `True` only when `_run_iterations`' `while` ends with no `return`. That covers a last iteration with text and tool calls, and `resume_after_auth` with a zero remaining budget;
  - set before the generator returns (squawk 0219's set-before-the-yield rule), so a consumer reading it after its `async for` sees it.
- **The web frame** `{"type": "step_limit", "steps": n}`, with `n` the agent's `max_iterations`:
  - **On the step path** (`_process_and_broadcast`): sent in the non-paused branch, after `_save_session_to_db` and immediately before `done`.
  - **On the resume path** (`_resume_paused_session`): sent inside `if not re_paused:`, immediately before that branch's `done`. The resume path's later save is not moved.
  - **Broadcast-only,** through `_send_to_session` and never `add_event`, so neither `Session.history` nor the DB holds it.
  - Not sent when the step raised; the "Agent error" path is unchanged.
- **The REST `/api/chat` result** gains `"step_limit": true` when the flag is set. The key is absent otherwise, so the change is additive.
  - **The mechanism** (design review): `_process_and_broadcast` gains an optional out-parameter `turn_info: dict | None = None`. It captures `session.agent.stopped_at_step_limit` into a local **right after its `async for` ends**, before anything else awaits.
  - The same local gates the WebSocket frame, and is written to `turn_info["step_limit"]` when a dict is passed.
  - The `/api/chat` handler passes a dict and adds the key from it. The handler does not hold `session_locks`, so it must never re-read agent state itself.
  - The return type is unchanged, so the ~10 existing callers (`tests/test_ws_storage_edge_shim_visibility.py`, `tests/test_streaming.py:493`) are untouched.
- **Connectors** (`dispatch_inbound`):
  - **A fully suppressed helper** (design review). `_auto_deliver_reply` and the persist share one `try/except`, so a raise there would skip the persist. The step-limit send is a sibling helper, `_send_step_limit_line(…)`, that catches `ConnectorClientError` and every other `Exception` and never raises. It is called **after the persist**, so a send failure can never cost the stored turn. The flag is captured into a local right after the `async for`;
  - when that local is set, send the neutral line "(Stopped: reached its step limit for this message.)" to the same target, through the same client;
  - it is sent **always**, including after a `send_to_platform_channel` turn (operator, 2026-10-26);
  - with no client, or on a send failure, it is logged and dropped, like auto-delivery;
  - it is not stored: `encode_messages(agent.messages)` is unchanged.
  - Build the target the way `_auto_deliver_reply` does, through a small shared helper, not a copy.
- **The CLI:** after the turn, when the flag is set, it prints the web wording without the link, dimmed: "Stopped: this agent used its {n} steps for this message. Send another message to continue, or raise Max iterations in its settings." The same count rule as the web applies: with `n` below 1, the count is left out.
- **The web client** (`turn-frames.js`):
  - `step_limit` is added to the gated turn frames;
  - on it, the handler first calls `hideThinking()` and `finalizeStreamingBubble()` (as the assistant and tool-call branches do), because `step_limit` arrives before `done`. Then the transcript appends an `App.ui.notice({tone: 'muted', body})` line after the reply. A queued message held at `done` (`sendHeld`) leaves the notice in place: "Stopped: this agent used its {n} steps for this message. Send another message to continue, or raise Max iterations in its settings.";
  - "Max iterations" is a link to `#agents/{name}` (through `App.router.href`) **only when** the chat's agent has a stored record in `App.store.peek('agents')`; for the default agent (null name) or a deleted agent it is plain text;
  - when `steps` is below 1, the count is left out: "Stopped: this agent reached its step limit for this message. …";
  - the notice is not part of replay: a re-join renders none.
- **0.2:**
  - **The label's home** (design review: no Python label map exists today; `the_one/db/_provider_types.py` holds slugs only). A `PROVIDER_TYPE_LABELS` dict is added beside `PROVIDER_TYPES`, with `"openai-compatible": "OpenAI-compatible"` and `"ollama": "Ollama"` at least. `llm/registry.py` already imports from `db/`, so there is no layering issue. `api.py`'s provider-types endpoint (`:5465`) reads the same dict where that is a small change; otherwise the duplication is recorded.
  - The factory passes the label to `OllamaProvider`.
  - **Only the paths an `openai-compatible` provider reaches** take it:
    - `ollama_api.chat_stream`, the generation path: "Cannot connect to …", "Timeout streaming from …", "… returned {status}";
    - `show_model` through `_resolve_max_context_tokens` (logged, not user-facing, but labelled for consistency);
    - `ollama_provider.py:336`'s own "Ollama returned {status}".
  - **The new wording:** "Cannot connect to the OpenAI-compatible server at {url}: …" for `openai-compatible`; the existing "Ollama" wording for `ollama`.
  - `chat_native` / `chat_stream_native`, the model-management handlers (`api.py:5439`, `:5958`) and `_ensure_ollama_model_loaded` are Ollama-only (guarded by type), and are left as they are.
  - The exact phrasing of each changed message is recorded in the flight log.
- **The behavior spec** `tests/behavior/agent-step-limit-notice.md` (status `draft`), in the format of `.flightops/ARTIFACTS.md` "Behavior Test — Spec":
  - **Preconditions** reference CLAUDE.md "Behavior-test credential convention": a dedicated dev instance on a non-default port and scratch data dir, `THE_ONE_DEV_MODE=true`, `THE_ONE_STUB_TEST_ENDPOINT=1`.
  - **The seed:** a mock provider whose `response` has `tool_calls` calling `current_time` on every reply (the same call id each time, which is fine for two iterations), and an agent with `max_iterations` 2 attached to it and to a stub connector. The connector, pairing and admission setup cross-references `stub-connector-round-trip.md`'s preconditions rather than restating them.
  - **The steps:**
    - the web notice and its link;
    - the stub connector's outbound line through `GET /api/_test/stub/outbound` after a `POST /api/_test/stub/inbound`;
    - a reload, and a second browser context, show no notice;
    - `GET /api/chat/sessions/{id}` shows no notice in `messages`.
  - It is run in leg 09b.
- **Docs:** `the_one/agents.md`: the WebSocket event table and session-scoped frame list gain `step_limit`; the agent loop section notes the flag; `connectors/README.md` notes the line. CLAUDE.md needs no change unless it lists frames.
- **Ledger rows 28 and 31** confirmed in the flight log, with the final wording.

## Acceptance Criteria
- [ ] **Unit (agent loop, `FakeLLM`):**
  - a tool call on every iteration with `max_iterations=2` sets the flag;
  - a text answer, an auth pause, a degraded-backstop exit and a resume that finishes with text do not;
  - a resume with a zero remaining budget sets it;
  - the next `step()` clears it;
  - `reset()` clears it.
- [ ] **Unit (web, the step path):** with a scripted always-tool-calling mock, the WebSocket receives `step_limit` (with `steps` equal to `max_iterations`) immediately before `done`, after the save. A normal turn sends no `step_limit`. A second socket joining after `done` gets no `step_limit` in `session_joined.history`, and the stored session's `messages` contain no notice.
- [ ] **Unit (web, the resume path):** a paused turn resumed with a zero budget sends `step_limit` immediately before `done`, and a re-paused resume sends none.
- [ ] **Unit (REST):** `/api/chat` returns `"step_limit": true` on exhaustion and no such key otherwise.
- [ ] **Unit (connectors):**
  - the stub connector's outbound holds the neutral line exactly once after an exhausted turn, including when the agent used `send_to_platform_channel`;
  - when `client.send` raises for the line, the turn's messages are still persisted;
  - nothing is sent for a normal turn;
  - with no live client, the line is logged and dropped;
  - the persisted messages hold no line.
- [ ] **Unit (CLI):** an exhausted turn prints the line (captured console output).
- [ ] **Browser** (`chats-transcript` lane), with the mock provider's `tool_calls` on `current_time` and `max_iterations` 2:
  - the notice appears after the turn with the settings link, which navigates to `#agents/{name}`;
  - for a deleted agent's chat it is plain text;
  - after a reload it is gone.
- [ ] **0.2:** a unit test drives an `openai-compatible` provider at a dead loopback port and asserts the error names the OpenAI-compatible server, not Ollama. An `ollama` provider's error is unchanged. No other Ollama-only call path is found beyond the two known probes, or one is raised as a question and the leg stops.
- [ ] **The spec** `agent-step-limit-notice.md` exists as `draft`, shaped per ARTIFACTS.md, with Observables Required naming the read paths (the WebSocket and DOM, `GET /api/_test/stub/outbound`, `GET /api/chat/sessions/{id}`).
- [ ] `the_one/agents.md` lists `step_limit` in the frame table and the session-scoped list.
- [ ] `make test-unit` passes, the `chats-transcript` and `chats` lanes pass, and `ruff` is clean.

## Verification Steps
1. `.venv/bin/python -m pytest tests/test_agent_core*.py tests/test_ws_*.py tests/test_connectors_inbound*.py tests/test_cli*.py tests/test_ollama*.py -q -x --timeout 60`, or the files the new tests land in.
2. `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats-transcript -x --tb=short`, then `--lane chats`.
3. `git grep -n "step_limit" -- the_one/ tests/`.
4. `make test-unit`; `ruff check`; `ruff format --check`.

## Implementation Guidance
1. **The flag and its unit tests first** (core), test first. Clear it as the **first statement** of `step()` (before the message append) and of `resume_after_auth()` (before the deferred check); set it right after the `while` ends. A consumer that `break`s early (the resume path on a re-pause) treats it as unset.
2. **The web step path and resume path,** with the WebSocket tests (find the existing WebSocket test helpers; for example tests that drive `_process_and_broadcast` with `FakeLLM`).
3. **REST, then connectors** (the shared target helper), **then the CLI.**
4. **The client:** the gated frame and the notice, plus the browser test.
5. **0.2:** trace the label from the factory, then fix the wording; its test.
6. **The spec draft, docs and ledger.** Then `make test-unit` and the lanes.

## Edge Cases
- **Exhaustion with a pending `next_turn` self-revision:** the revision still applies at the settle, before `step_limit`/`done`, unchanged.
- **The degraded path** (a model with no tool support) never exhausts by tool calls, but if the budget runs out on that path the same rule applies.
- **`max_iterations` of 0 or less** (no lower bound, `config.py:132`): the loop never runs, so the flag is set at once and the notice leaves the count out.
- **Concurrency:** read the flag right after the turn's own loop, inside the same task, before another turn on the session could start.
- **A connector chat open in the web UI:** the web view gets only `session_updated` and a re-join, so it shows no notice. That is expected (DD8).
- **The deleted-agent chat** has no agent record, so the link is plain text and must not throw.

## Files Affected
- `the_one/agent/core.py`, `the_one/interfaces/web/app.py`, `the_one/connectors/inbound.py`, `the_one/interfaces/cli.py`.
- `the_one/llm/registry.py` and/or `the_one/llm/ollama_provider.py`, `the_one/llm/ollama_api.py`.
- `the_one/interfaces/web/static/js/areas/chat/turn-frames.js` (and the transcript helper it calls).
- New and updated unit tests, a browser test (`chats-transcript`), `tests/behavior/agent-step-limit-notice.md` (new).
- `the_one/agents.md`, `the_one/connectors/README.md`, the flight log.

## Citation Audit
- `core.py`: `:215` `step`, `:245` re-prime, `:286` `while`, `:326`/`:356`/`:362`/`:375` returns, `:518` `resume_after_auth`, `:535`, `:562`, `:662` `reset`, `:669`. FD grep (2026-10-27).
- `app.py`: `:743`, `:766`, `:1865`, `:1909`, `:2299`, `:2515`, `:2534`, `:2568`, `:2621`, `:2643`, `:2666`, `:3020-3046`. FD read; Architect cycle 2 for the resume order.
- `inbound.py`: `:247-345` `_auto_deliver_reply` (skip rule `:293-302`, `client_for` `:317`) and `:472`. FD read.
- `cli.py:88`. FD read.
- `registry.py:22`, `ollama_api.py:101`, `:103`, `:215-218`, `ollama_provider.py:264-302`. FD grep and Architect cycle 1.
- **Line numbers will drift** with leg 05's client work, which does not touch these server files. Re-derive anyway.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

- **Contract with leg 05c (added 2026-10-27):** the web `system` frame for an agent error keeps its `"Agent error: "` content prefix. Leg 05c detects it to render the danger notice (A4). 0.2 changes only the provider wording after the prefix.

## Design Review
- **Developer design review, cycle 1 (Sonnet, 2026-10-27, read-only): approve with changes.** Applied in place:
  - **[high] persistence:** the connector line goes through a fully suppressed helper after the persist (FD answer: after), plus a test;
  - **[high] REST:** the `turn_info` out-parameter, with the flag captured once after the loop (FD answer: the out-parameter, which leaves the existing callers untouched);
  - **[medium] the label:** a `PROVIDER_TYPE_LABELS` dict beside `PROVIDER_TYPES` (FD answer), with the 0.2 scope narrowed to the paths `openai-compatible` reaches, including `ollama_provider.py:336`;
  - **[medium] the client:** `hideThinking` and `finalizeStreamingBubble` before the notice;
  - **[low] the rest:** the CLI count rule (FD answer: same as the web); the spec seed notes; the clear and set placement.
- **The reviewer verified** the exhaustion rule against every `return`, the re-pause `break`, the absence of any frame allowlist on server or client, every `agent.step` caller (selftest and evals ignore the flag harmlessly) and the stub outbound seam.
- No second cycle (clarifications within the design).
