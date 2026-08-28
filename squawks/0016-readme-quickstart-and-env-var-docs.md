# Squawk 0016: README quickstart points at removed `THE_ONE_LLM_*` env vars, names UI areas that no longer match the nav, and six tunables are undocumented

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-27
**Completed**: —

## Report

Three README/`.env.example` accuracy gaps, one doc pass (2026-08-27 maintenance
findings B4, E7, B6):

1. The quickstart says `cp .env.example .env  # edit THE_ONE_LLM_* for your provider
   of choice`, but those variables were removed in Mission 12 when provider config
   moved to the database; `.env.example` itself opens by saying providers are
   configured in the admin UI. A new operator following the README edits variables
   that do nothing.
2. The README refers to the areas as **Administration** and **Studio**; the live nav
   labels are **System** and **Agent Studio**.
3. Six `THE_ONE_*` tunables read by the code are absent from `.env.example`:
   `THE_ONE_ANTHROPIC_EXTENDED_THINKING`, `THE_ONE_TOOL_CALL_TIMEOUT_SECONDS`,
   `THE_ONE_OPENROUTER_TEST_MODELS_JSON`, `THE_ONE_REASONING_EFFORT`,
   `THE_ONE_RESPONSE_FORMAT`, `THE_ONE_STOP`.

Fix: rewrite the quickstart line to point at the admin UI provider setup; reconcile
the area names (either direction — pick one and apply consistently, including the
screenshot captions); add an "advanced LLM tuning" block to `.env.example` mirroring
its existing operational-tunables section.

## Evidence

- `README.md:49` — `cp .env.example .env  # edit THE_ONE_LLM_* for your provider of choice`;
  `.env.example:1-2` — "LLM provider selection and model are configured via the admin UI, not env vars"
- `README.md:13,24,26,30,32,107` — "Studio" / "Administration";
  `the_one/interfaces/web/static/js/areas/admin.js:3` — `label: 'System'`;
  `the_one/interfaces/web/static/js/areas/studio.js:3` — `label: 'Agent Studio'`
- `the_one/llm/anthropic_provider.py:94`, `the_one/agent/core.py:24`,
  `the_one/llm/openrouter_api.py:94`, `the_one/llm/_request_params.py:34-36` — the
  six env reads; none appear in `.env.example`

## Corrective Action
*(written at completion)*

## Verification
*(written at completion — `grep THE_ONE_LLM_ README.md` empty; each of the six vars
present in `.env.example`; area names consistent between README and nav labels)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
