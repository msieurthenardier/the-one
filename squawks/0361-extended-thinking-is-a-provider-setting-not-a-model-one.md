# Squawk 0361: Extended thinking is set per provider, so it breaks every model on that provider that cannot think

**Status**: escalated
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-14
**Completed**: —

## Report
"Extended thinking" is a switch on a Claude **provider** (Library › Model providers). One provider serves many models, and an agent picks the model. With the switch on, every agent on that provider sends the thinking option, whichever model it chose. A model that does not support adaptive thinking then fails every turn with an agent error:

`Error code: 400 … 'adaptive thinking is not supported on this model'`

So the operator must choose between thinking for the models that support it and working chats for the models that do not, or keep two providers that differ only in this switch.

Found by the operator on 2026-11-14, during sortie 16's HAT (step 8c): they turned the switch on to see a thinking-only turn, and the only model they had available on that provider did not support adaptive thinking.

Reproduce: on a Claude provider, turn on Extended thinking and save. Create an agent on that provider with a model older than Claude Sonnet 4.6. Send it any message. The turn ends with the 400 above.

Expected: thinking follows the model, not the provider. A model that cannot think is never sent the option, or the setting lives where the model is chosen (the agent), or the provider's switch is applied only to models that support it. Which of these is right is a design decision.

## Evidence
- `the_one/llm/anthropic_provider.py:188-194` — the provider reads `config["thinking_enabled"]` once, from its own config; `:272` passes it to `resolve_extended_thinking` when it builds every request, with no check of the request's model.
- `the_one/interfaces/web/static/js/areas/studio/provider-editor.js:44, 181-190` — the "Extended thinking" switch (`config.thinking_enabled`) is on the provider form; its help text says "Requires Claude Sonnet 4.6 or newer" but nothing enforces it.
- `~/the-one-hat-sortie16/cwd/serve.log:445` (the sortie 16 HAT instance) — `anthropic.BadRequestError: Error code: 400 - … 'adaptive thinking is not supported on this model'`.

## Corrective Action
*(not a squawk-sized fix; see Disposition)*

## Verification
*(written when the follow-up lands)*

## Sign-Off
*(written at completion)*

## Disposition
**Escalated**: it fails two of the squawk criteria. **No design decisions** fails: where the setting should live (the provider, the agent, or a per-model capability check) and what to do for a model that cannot think (drop the option silently, refuse on save, or fall back after the 400) are open choices. **Bounded blast radius** fails: any of them changes a provider or agent configuration shape that the API, the editors and stored rows share. It is one self-contained outcome with one cluster of decisions, so the right vehicle is a sortie (`/mission-control:sortie`), not yet chartered. Logged here at the operator's request so it has an id and is not lost; link the sortie from this file when it exists.

**Sortie**: [17, Extended thinking follows the model](../sorties/17-thinking-follows-the-model/flight.md), chartered 2026-11-14.

**Outcome (2026-11-15)**: fixed by sortie 17 (commit `fbb6198a`). The thinking option is now sent only to models from version 4.6 on, and a new Claude provider starts with the switch on. Confirmed at the sortie's HAT with a real model: Haiku 4.5 answered with the switch on and the log held no 400. The squawk stays `escalated` (its terminal state); the sortie's [debrief](../sorties/17-thinking-follows-the-model/flight-debrief.md) carries the follow-ups (squawks 0367 to 0370).
