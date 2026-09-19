# Squawk 0089: CLAUDE.md's mock-provider options omit `tool_calls`

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-19
**Completed**: 2026-09-19

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

Rewrote CLAUDE.md's "Dev mode and the mock provider" option list so it is
actually complete, and made the nesting explicit.

1. **Nesting stated up front.** The list's lead-in now says only the five
   top-level keys are in `config` itself, and that `content`, `tool_calls` and
   `thinking` live *inside* `response`, not beside it. It also points at
   `MockProvider`'s class docstring in `the_one/llm/mock.py` as the other copy
   of the same list, so the next divergence is cheap to spot.

2. **`response` corrected from "scripted reply text" to a dict**, with its three
   keys nested as sub-bullets:
   - `content` — the reply text (default `""`)
   - `tool_calls` — a list of `{"id": str, "name": str, "arguments": dict}`
     (`arguments` optional, defaults `{}`), synthesized into real `ToolCall`s on
     the assistant `Message`, also attached to the final chunk of a
     `stream_chunks` run
   - `thinking` — a list of `ThinkingBlock` dicts, both variants spelled out
     (`type: "thinking"` with `thinking`/`signature`, and
     `type: "redacted_thinking"` with `data`)

3. **Two further keys the list still omitted were added**, both real:
   - `delay_ms` — read by `MockProvider` in both `complete()` and `stream()`
     (awaited once before `complete()` returns; *between* successive
     `stream_chunks`, not before the first)
   - `models` — read by `interfaces/web/api.py`'s
     `GET /providers/{provider_id}/models` (`provider.config.get("models",
     ["mock-default"])`). Not read by `MockProvider` itself, which the bullet
     says, but it is a mock-provider `config` key and a list claiming
     completeness has to carry it.

4. **The section intro was corrected too** — it described
   `config["response"]` as if it were the reply text and gave the default as a
   bare string. It now names `response` as a dict whose `content` holds the
   text, with the default written as
   `{"content": "Mock response from the mock provider."}` (matching
   `_DEFAULT_RESPONSE` in `mock.py`).

**One claim in the report's proposed corrective action was wrong and was not
carried into the docs.** It asked to "note that `response` may be a dict as well
as a bare string ... so both forms are live". A bare string is **not** live:
`complete()` does `response.get("content", "")`, so `config = {"response": "hi"}`
raises `AttributeError: 'str' object has no attribute 'get'` (reproduced
directly against `MockProvider`). The only bare-string occurrence in the
repository is a raw DB row fixture in `tests/test_db_migration.py`, which never
reaches `MockProvider`; and Mission 04 Flight 01's debrief already carries an
open follow-up to make exactly this case fail gracefully rather than with an
`AttributeError`. Documenting the bare string as supported would have written a
crash into CLAUDE.md as a feature. The docs instead state that `response` must
be a dict and name the `AttributeError` outright, so the next person who tries
the short form recognises the traceback.

## Verification

Cross-checked the list against every `config` and `response` read in
`the_one/llm/mock.py` (`grep -n 'config\.get\|config\[\|response\.get\|response\['`):
`config.get("delay_ms")`, `config.get("response")`, `config.get("input_tokens")`,
`config.get("stream_chunks")` in `MockProvider`; `response.get("content")`,
`response.get("tool_calls")` in `complete()`/`stream()`; `response.get("thinking")`
in `_thinking_from_response`. Plus `provider.config.get("models", ...)` in
`interfaces/web/api.py`'s mock branch of `GET /providers/{id}/models`, found by
searching for mock-provider `config` reads outside `mock.py`. Every one of those
keys now appears in CLAUDE.md's list, at the correct nesting level, and the list
introduces no key the code does not read.

Also cross-checked against `MockProvider`'s class docstring (`mock.py`), which
documents the same six keys, and against `ThinkingBlock` in `the_one/llm/base.py`
for the two block variants. Behaviour spot-checked by construction: a dict
`response` returns its `content`, no `response` returns the default, and a bare
string raises `AttributeError`.

## Sign-Off

*Verified every listed `config` key against `the_one/llm/mock.py` and the `GET /providers/{id}/models` mock branch in `api.py` — the list is now complete and correctly nested, with no key the code reads left undocumented and none invented. `ThinkingBlock`'s two variants match `the_one/llm/base.py` exactly. Approved.*

**Reviewer**: independent Reviewer agent, turnaround batch 2026-09-19.

> Prior pending note, kept for the record:
>
> *(pending)*
