# Behavior Test: Gemma (Ollama) Text-Form Tool-Call Recovery

**Slug**: `gemma-tool-use-recovery`
**Status**: draft
**Created**: 2026-06-18
**Last Run**: never

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
asserts a **result-state observable** — a host-side canary file the tool would create —
**not** "the agent narrated that it ran the tool." If recovery fails (the #105 bug), the
model prints the tool-call syntax and the canary never appears; if recovery works, the
canary exists. Containment of the failure mode is asserted by the *outcome state*.

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
- Host filesystem read access for the canary checkpoint (Bash/Read on the instance host).

## Observables Required

- filesystem (host canary file presence/contents — measured via Bash/Read on the instance host)
- http (the `POST /api/chat` response body + any session/history read surface — measured via
  curl/Bash)
- (the chat response carries the assistant text; assertions rest on **result state** — the
  canary — and on the **absence** of a raw ` ```tool ` block in the final assistant message,
  not on the agent narrating success)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 0 | (Setup, no judgment) Confirm or create the gemma3:4b agent with the **shell** tool enabled; record the agent id. | (empty) |
| 1 | Confirm readiness: `POST /api/chat` is reachable; the target agent's model is `gemma3:4b`; `supports_tools()` for that model is `False`; **and the agent's loaded tool registry includes `shell`**. | Setup/guard — all four hold. If `supports_tools()` is `True`, STOP (wrong model; the degraded recovery path wouldn't be exercised). If `shell` is absent, STOP (setup failure, not a recovery failure). *(no judgment beyond the guard)* |
| 2 | Pick a unique host canary path under `$HOME` (e.g. `~/gtur_canary_<rand>.txt`) that does **not** yet exist. Send a chat message asking the agent to use its shell tool to write the exact text `recovered-ok` to that file. If the model returns a normal answer without attempting any tool call, re-send **once** with a more directive prompt (explicitly: "use your shell tool to run the command") before treating it as INCONCLUSIVE. | `[mixed-frame]` host check: within the response/idle window, the canary file **exists on the host** with content `recovered-ok` — i.e. the text-form tool call was recovered and **executed** (this is the core #105 assertion). |
| 3 | Read the `POST /api/chat` response (and session history if exposed) for the turn from step 2. | The final assistant message does **not** contain a raw ` ```tool ` fenced block (the recovered block was stripped, DD4), **and** the turn shows a tool was actually invoked (a tool result is present / the answer reflects the write). The user does not see raw call syntax. |
| 4 | (Degraded round-trip) Observe that the turn **completed** — the agent produced a normal final answer after the tool ran, not an error or a hang. | The conversation reaches a coherent final assistant answer (the follow-up turn carrying the tool result was accepted by gemma with `tools=None` — DD5 holds, or its adaptation works). No 400 / no stall. |
| 5 | (No-false-positive) Send an ordinary conversational message that should **not** trigger any tool (e.g. "In one sentence, what is a haiku?"). Pick a fresh canary path and confirm it stays absent. | A normal text answer is returned; **no** tool is dispatched and no canary side effect appears — recovery does not fire on ordinary prose (DD2 high-precision). |

**Row conventions:** the core assertion (step 2) is `[mixed-frame]` — the host canary is the
legitimate result-state read path, agent-safe (the agent performs an ordinary tool request;
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
