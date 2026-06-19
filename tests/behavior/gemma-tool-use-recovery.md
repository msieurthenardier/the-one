# Behavior Test: Gemma (Ollama) Text-Form Tool-Call Recovery

**Slug**: `gemma-tool-use-recovery`
**Status**: active
**Created**: 2026-06-18
**Last Run**: 2026-06-19-04-26-15 (pass)

## Intent

Verify, through the **live agent tool surface**, that a non-tool-capable open model
(gemma3:4b via Ollama) which emits a tool call as **loose text** (the ` ```tool ` fenced
Python-call form the model actually produces) nonetheless **executes** the tool end-to-end
— the recovery parser (Flight 3) lifts the text-form call into a structured `ToolCall`, the
existing agent loop dispatches it, and the result feeds back into the turn. This is
real-environment AI-agent behavior that unit/fixture tests can't fully cover: it needs the
*real* model to spontaneously emit the loose format and the *whole path* (model → provider
recovery → agent loop → tool → result → follow-up turn) to hold together, including the
degraded follow-up round-trip (no tools on the wire).

**Authored under the agent-safe-observable rule (project convention):** the checkpoint
asserts a **result-state observable** — the **tool result returned into the turn** carrying a
unique echoed marker — **not** "the agent narrated that it ran the tool." If recovery fails
(the #105 bug), the model prints the tool-call syntax, no tool runs, and the marker never
appears in a tool result; if recovery works, the shell tool runs and the marker comes back in
the tool result. Containment of the failure mode is asserted by the *outcome state*.

> **Amended (M16 F03 L07, #105):** the original step-2 observable was a **host-side canary
> file** the shell tool would write. That observable is **invalid** under the sandbox:
> `ShellTool` runs `host_access=False` by default in an **ephemeral bwrap box** (`home=scratch`,
> `writable_paths=[scratch]`, `rmtree`'d on execute return), so a file the tool writes **never
> reaches the host** and the box is destroyed after the call — the canary could never appear
> even with a perfect fix. The observable is re-scoped to the **tool-result / chat response**
> (an echoed unique marker), which proves the property that matters for #105 — that the tool was
> **dispatched and executed**. This is a *correction of a sandbox-invalid observable*, **not a
> weakening**: the tool-result marker is a *more direct* proof of execution than a host write
> (which only proves a host write, gated on `host_access` the model never emits).

## Preconditions

- A `the-one` instance is running and reachable (`POST /api/chat` confirmed at the
  configured URL, default `http://localhost:8484`).
- Local **Ollama** is reachable with **gemma3:4b** pulled; an agent is configured to use the
  Ollama **gemma3:4b** provider/model and has the built-in **shell** tool enabled. **If no
  such agent exists in the environment, the Executor creates one via the admin API first**
  (step 0) — record the agent id used. The shell tool being enabled is a hard dependency: a
  recovered call to a tool the agent doesn't have would dispatch to a not-found error and look
  like a recovery failure when it is a setup failure (guarded in step 1).
- Confirm the degraded path is actually under test: `OllamaProvider("gemma3:4b").supports_tools()`
  is `False` (so tools are NOT offered on the wire and recovery is what makes the tool run).
  Probe this before judging — if a tool-capable model is selected by mistake, the test
  false-passes via the structured path.
- The Flight 3 recovery fix is deployed in the running instance.

## Observables Required

- http (the `POST /api/chat` response body — measured via curl/Bash)
- session / tool-result read (the turn's tool result(s) and final assistant message — measured
  via the chat response and any session/history read surface)
- (assertions rest on **result state** — the echoed marker present in a tool result returned
  into the turn — and on the **absence** of a raw ` ```tool_code `/` ```tool ` block in the
  final assistant message, not on the agent narrating success)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 0 | (Setup, no judgment) Confirm or create the gemma3:4b agent with the **shell** tool enabled; record the agent id. | (empty) |
| 1 | Confirm readiness: `POST /api/chat` is reachable; the target agent's model is `gemma3:4b`; `supports_tools()` for that model is `False`; **and the agent's loaded tool registry includes `shell`**. | Setup/guard — all four hold. If `supports_tools()` is `True`, STOP (wrong model; the degraded recovery path wouldn't be exercised). If `shell` is absent, STOP (setup failure, not a recovery failure). *(no judgment beyond the guard)* |
| 2 | Pick a unique marker token (e.g. `recovered-ok-<rand>`). Send a chat message asking the agent to use its shell tool to run a command that **echoes** that exact marker (e.g. `echo recovered-ok-<rand>`). If the model returns a normal answer without attempting any tool call, re-send **once** with a more directive prompt (explicitly: "use your shell tool to run the command") before treating it as INCONCLUSIVE. | `[mixed-frame]` tool-result check: within the response/idle window, **a tool was dispatched AND a tool result is present in the turn AND the tool result / chat response contains the marker** — i.e. the text-form tool call was recovered → the shell tool ran → its output returned (this is the core #105 assertion). |
| 3 | Read the `POST /api/chat` response (and session history if exposed) for the turn from step 2. | The final assistant message does **not** contain a raw ` ```tool_code `/` ```tool ` fenced block (the recovered block was stripped, DD4), **and** the turn shows a tool was actually invoked (a tool result is present / the answer reflects the echoed marker). The user does not see raw call syntax. |
| 4 | (Degraded round-trip) Observe that the turn **completed** — the agent produced a normal final answer after the tool ran, not an error or a hang. | The conversation reaches a coherent final assistant answer (the follow-up turn carrying the tool result was accepted by gemma with `tools=None` — DD5 holds, or its adaptation works). No 400 / no stall. |
| 5 | (No-false-positive) Send an ordinary conversational message that should **not** trigger any tool (e.g. "In one sentence, what is a haiku?"). | A normal text answer is returned; **no** tool is dispatched (no tool result in the turn) — recovery does not fire on ordinary prose (DD2 high-precision). |

**Row conventions:** the core assertion (step 2) is `[mixed-frame]` — the tool-result marker is
the legitimate result-state read path, agent-safe (the agent performs an ordinary tool request;
recovery + the loop do the rest; the test reads the *outcome*). Model variability: gemma3:4b
may phrase its tool call differently across runs; the test asserts the recovery *path* works
(tool executed, no raw block), not a specific call string. If the model declines to attempt a
tool call at all on a given run, that is INCONCLUSIVE (re-run / rephrase the eliciting prompt),
not a FAIL of the recovery code.

## Out of Scope

- **Deterministic parser correctness** across the gemma/Hermes/bare-JSON formats — that's the
  hermetic recovery-kernel unit suite (`tests/test_toolcall_recovery.py`, Flight 3 `leg 01`).
- **Provider-level recovery against real model output** — the `@pytest.mark.live` marker test
  (`leg 04`) asserts the returned `Message` carries a recovered `ToolCall`; this spec is the
  full-loop end-to-end breadth test.
- **Tool-capable Ollama models** (qwen2.5, llama3.1) — they use the structured `tool_calls`
  path and never hit recovery.
- **Sandbox containment of the executed tool** — covered by `tool-sandbox-containment`.

## Variants (optional)

- **hermes-format**: if a Hermes-`<tool_call>`-emitting local model is available, re-run with
  it to confirm the Hermes recognizer path executes end-to-end (same canary observable).
