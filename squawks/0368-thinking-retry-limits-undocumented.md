# Squawk 0368: agents.md does not state the two limits of the thinking retry

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-15
**Completed**: —

## Report
`the_one/agents.md` documents sortie 17's model rule, the remembered set of model ids found unable to think, and the one retry. It does not state two limits a maintainer needs:

1. **The match is on the error's wording.** The retry fires on a 400 whose text contains "thinking" together with "not supported". If the API rewords the error, the retry stops matching and the 400 reaches the user as before. A different 400 that contains both phrases would mark the model as unable to think until restart.
2. **The remembered set is keyed by model id only and spans providers.** One provider's or account's refusal turns thinking off for that model id on every Claude provider in the process, until restart. Nothing clears the set in production.

Both were accepted at sortie 17's review as residual risks. Why now: the real error text is still pinned from a single recorded line (squawk 0361), because sortie 17's HAT never produced the 400.

## Evidence
- `the_one/llm/anthropic_provider.py::AnthropicProvider._strip_for_bad_request` — the thinking branch's condition.
- `the_one/llm/anthropic_provider.py` — the module-level set of model ids and `supports_adaptive_thinking`, which consults it; the clearing helper is used by tests only.
- `the_one/agents.md`, "Extended thinking follows the model (sortie 17)" — names the rule, the set and "a restart forgets", not the two limits.
- `sorties/17-thinking-follows-the-model/flight-debrief.md`, recommendation 6.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
