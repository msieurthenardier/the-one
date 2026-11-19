# Leg: gleepglorp-prompt

**Status**: completed
**Flight**: [GleepGlorp exists and can answer](../flight.md)

## Objective
Replace GleepGlorp's placeholder with its shipped prompt (version 1, the text
Leg 9's evals start from), and show it read-only first in Settings › Prompts.

## Context
- Flight DD6 (the prompt part), board screen 6, the mission constraints (app
  support only, never a change, never a secret, never promise an ability).
  Split from the planned Leg 6 (flight log); it follows Leg 7 because the
  prompt's links must pass Leg 7's route check.
- Design-review facts: `/api/info` (`app.py` `info()` ~:3211) takes no
  connection and is called by `tests/test_prompt_layers.py` ~:479 as
  `asyncio.run(info())` with no database, so it renders the prompt through the
  pure `compose(...)` (Leg 6 keeps it beside `build_prompts`) with the
  placeholder date line the other examples use
  (`render_date_line("{today's date}", "{time zone}", tool_available=True)`,
  `app.py` ~:3228). The Prompts page (`areas/admin/system-page.js`
  `renderPromptsPage` ~:171-251; `promptBlock` ~:87, `promptLayer` ~:104, the
  intro ~:192) is pinned by `tests/browser/test_flow_admin_settings_nav.py`
  ~:240-335 (one `.admin-system-section` on Prompts),
  `tests/browser/test_flow_admin_encryption_page.py` ~:271-312 (h2/h3, trimmed
  code blocks) and `tests/test_aiat.py` ~:111. The tokenizer: `.venv` has
  `tiktoken` and `evals/.cache/tiktoken` is populated.

## Inputs
- Leg 7 landed (the route check exists).

## Outputs
- The shipped prompt in `the_one/gleepglorp/prompt.py` as section constants.
- `/api/info` `gleepglorp_prompt`; the Prompts block.
- Tests and docs.

## Acceptance Criteria
- [ ] The prompt replaces the placeholder, in short sections (constants, so
      Leg 9 can tune one at a time): who GleepGlorp is; app support only
      (decline anything else in one sentence and suggest one of the operator's
      own agents); it cannot change anything (the operator makes every change;
      never say a change was made); never ask for, repeat or write a secret,
      and if the operator pastes something that looks like a key, do not
      repeat it and say where it belongs; never promise an ability it does not
      have; how to answer (`get_app_guide` for how things work,
      `read_app_config` for what is configured, the web only for outside
      facts, say when unsure); links as `[text](#route)` to routes that land on
      a page, listing the main ones (`#settings/gleepglorp`, `#library`,
      `#library/providers/~new`, `#library/mcp/~new`,
      `#library/knowledge/~new`, `#library/connectors/~new`,
      `#library/secrets/~new`, `#agents/~new`, `#settings/tools`); brief
      Markdown replies. A tool-free variant drops the tool instructions and
      tool names.
- [ ] Every link in the prompt passes Leg 7's route check (a test).
- [ ] The tool-capable variant measures at most 450 tokens with the evals'
      tokenizer (`o200k_base`), recorded in the flight log with the tool-free
      size.
- [ ] `/api/info` gains `gleepglorp_prompt`: `compose(...)` of the tool-capable
      prompt with no notes and the placeholder date line;
      `tests/test_prompt_layers.py` asserts it equals that composition.
- [ ] Settings › Prompts shows it first, inside the page's existing section
      (the `.admin-system-section` count stays 1): an `h2` "GleepGlorp" layer,
      the line "Applies when: a chat with GleepGlorp. It replaces the platform
      prompt; GleepGlorp gets no rules, persona or secrets. Its notes (when
      memory is on) and the date line follow it.", and a trimmed code block
      (testid `gleepglorp-prompt-content`). The intro sentence no longer says
      every agent's prompt is assembled from the layers below. The pinned
      Prompts tests are updated for the new first block.
- [ ] Other agents' prompts are unchanged: `tests/_platform_prompt_pins.py` and
      every platform-prompt test pass untouched.
- [ ] `THE_ONE_TEST_NETNS=1 make test-unit` passes under 350 s; lanes
      `settings` and `shared` pass; static guards pass; ruff clean.
- [ ] Docs: CLAUDE.md (the GleepGlorp prompt and the Prompts block; it is
      platform prompt text under the eval rule, with its own baseline from
      Leg 9), `the_one/agents.md`, `docs/ui-testid-registry.md`.

## Verification Steps
- `tests/test_gleepglorp_prompt.py` (new), `tests/test_prompt_layers.py`,
  `tests/test_platform_prompt.py`.
- The token measurement with `.venv/bin/python` and `tiktoken`.
- `THE_ONE_TEST_NETNS=1 make test-unit`; lanes `settings`, `shared`.

## Implementation Guidance
1. Write the section constants and `compose`/`build_prompts` around them; keep
   the notes layer and date line placement from Leg 6.
2. The route-check test over the prompt's links.
3. Measure; trim to the target without losing a must-keep item (the limits,
   the secret rule, the link format, the decline).
4. `/api/info` and the Prompts block; update the pinned tests.
5. Docs.

## Edge Cases
- **The tool-free variant**: no tool names, and the link guidance stays.
- **The Prompts page in light and dark**: library controls only.

## Files Affected
- Changed: `the_one/gleepglorp/prompt.py`, `the_one/interfaces/web/app.py`,
  `static/js/areas/admin/system-page.js`, `tests/test_prompt_layers.py`, the
  pinned browser tests, docs. New: `tests/test_gleepglorp_prompt.py`.

## Citation Audit
From the superseded `06-gleepglorp-guide-memory-web.md` design review
(flight log): `app.py` `info()` ~:3211 and its placeholder date line ~:3228;
`test_prompt_layers.py` ~:479; `system-page.js` ~:87, ~:104, ~:171-251, ~:192;
the pinned browser tests - verified (review). Re-locate by symbol.
