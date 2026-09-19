# Squawk 0089: CLAUDE.md's mock-provider options omit `tool_calls`

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-19
**Completed**: —

## Report

CLAUDE.md's **"Mock provider `config` options (all optional...)"** list enumerates
three keys — `response`, `stream_chunks`, `input_tokens`. It presents itself as
complete ("all optional, set in `LLMProviderConfig.config`") and it is not.

`MockProvider` also reads **`response["tool_calls"]`** (`the_one/llm/mock.py:100`),
a list of `{id, name, arguments}` dicts synthesized into real `ToolCall`s on the
returned `Message`. That is the only way to drive a deterministic tool-calling
agent turn with no live provider, and it is already load-bearing: two behavior
specs depend on it (`kb-agent-query-round-trip`, and `kb-studio-round-trip`'s
step-12 apparatus). `response["thinking"]` (`mock.py:18`) is likewise absent from
the list, and the class docstring at `mock.py:28-52` documents both.

**The cost is a capability nobody can audit.** Mission 24 Flight 6's DD-18 required
a HAT state observable only through an agent's live tool set. No product surface
exposes that, so the walk needed an apparatus that could make the agent *attempt* a
tool call — which `tool_calls` provides, and which was discovered mid-HAT by
reading `mock.py` rather than at planning by reading the docs. The
`/mission-control:flight` skill's premise-audit step asks whether the apparatus can
*act*; an operator or agent auditing that question against CLAUDE.md's list would
conclude it cannot.

## Evidence

- `CLAUDE.md`, "Dev mode and the mock provider" → "Mock provider `config` options
  (all optional, set in `LLMProviderConfig.config`)" — three bullets, no
  `tool_calls`, no `thinking`
- `the_one/llm/mock.py:100` — `for tc in response.get("tool_calls", [])`
- `the_one/llm/mock.py:18` — `_thinking_from_response` reads `response["thinking"]`
- `the_one/llm/mock.py:28-52` — the class docstring documents both, including the
  `{"id", "name", "arguments"}` shape

## Corrective Action

*(pending)* Add `tool_calls` and `thinking` to CLAUDE.md's list, with the nested
shape (both live **inside** `response`, not beside it — a non-obvious detail that
costs a debugging cycle to discover), and note that `response` may be a dict as
well as a bare string.

## Verification

*(pending)* Every key `MockProvider` reads from `config` appears in CLAUDE.md's
list; cross-check against `mock.py`'s class docstring.

## Sign-Off

*(pending)*
