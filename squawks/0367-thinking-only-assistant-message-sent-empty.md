# Squawk 0367: A thinking-only assistant message may be sent empty when thinking is off

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-15
**Completed**: —

## Report
When a Claude request is built with thinking inactive, a stored assistant message that has thinking blocks but no text and no tool calls is projected to `{"role": "assistant", "content": ""}`. The API is expected to reject an empty assistant message that is not the last one (a 400), which would end the turn with an agent error.

The shape predates sortie 17, but sortie 17 makes it easier to reach: a chat that holds such a message, whose agent then runs on a model that cannot think, now takes the thinking-off build on the first attempt, with no retry. Sortie 17's retry strip already drops an assistant message whose content became empty; the first-attempt build does not.

Not reproduced. The API's rejection is the sortie 17 debrief Developer's recollection of the API rule, not a verified fact; the first step is to confirm it.

Reproduce (expected): seed a chat whose history has an assistant message with thinking only (no text, no tool calls), run its agent on a model that cannot think (for example Haiku 4.5) or with the provider's Extended thinking switch off, and send a message. Inspect the built request for an assistant message with empty content.

Expected: such a message is left out of the request, the same way the strip leaves it out.

## Evidence
- `the_one/llm/anthropic_provider.py::AnthropicProvider._to_api_message` — the content-list branch needs `msg.tool_calls or (thinking_active and msg.thinking)`; otherwise the message falls through to `{"role": msg.role.value, "content": projected}`, an empty string for a text-less message.
- `the_one/llm/anthropic_provider.py::_strip_thinking_blocks` — drops an emptied assistant message, for list content only (the retry path).
- `tests/test_anthropic_thinking_model.py::test_thinking_only_assistant_message_is_dropped` — pins the strip's behaviour; there is no test of the first-attempt build.
- `sorties/17-thinking-follows-the-model/flight-debrief.md`, "Technical" and recommendation 3.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
