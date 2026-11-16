# Squawk 0369: The set of Claude provider types is repeated, so a new type would miss the thinking default

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-15
**Completed**: —

## Report
Sortie 17 stamps `config.thinking_enabled = true` on a newly created provider of one of the three Claude types, using a new tuple `_CLAUDE_PROVIDER_TYPES` in `api.py`. The same three types are listed independently in several other places, and nothing ties the lists together. A fourth Claude provider type added later would show the Extended thinking switch (from the JavaScript table) but silently miss the create-time default (from the Python tuple), or the reverse.

No behaviour is wrong today. The defect is the missing link between the lists.

Expected: the Python set has one source, and a unit test pins that the JavaScript table's `showThinkingEnabled` types equal it.

## Evidence
- `the_one/interfaces/web/api.py` — `_CLAUDE_PROVIDER_TYPES = ("anthropic", "anthropic-plan", _PLAN_TOKEN_TYPE)`, used by `create_provider`'s stamp.
- `the_one/interfaces/web/static/js/areas/studio/providers-section.js` — `showThinkingEnabled: true` on the same three types.
- Also listing the types: `the_one/interfaces/web/static/js/areas/studio/library-pane.js`, `the_one/db/_provider_types.py`, `the_one/models.py`, `the_one/llm/registry.py` (cited by the sortie 17 debrief Developer; re-check each before changing anything).
- `sorties/17-thinking-follows-the-model/flight-debrief.md`, recommendation 7.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
