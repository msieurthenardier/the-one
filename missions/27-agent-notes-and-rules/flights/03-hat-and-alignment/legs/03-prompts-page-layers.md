# Leg: prompts-page-layers

**Status**: completed
**Flight**: [HAT and Alignment](../flight.md)

## Objective

Settings › Prompts shows every hard-coded layer of an agent's system prompt,
read-only and in assembly order: base, then persona (a pointer), then rules,
then notes. It does so through the same render functions that build real
prompts, so it can never drift.

## Context

- **Origin:** an operator request during the HAT, 2026-10-10. The Flight
  Director's fix-vs-feature call: a small, read-only FEATURE on a single
  surface plus one endpoint field, designed here. It rides the HAT-fix
  Reviewer.
- **Today:** `renderPromptsPage` in `static/js/areas/admin/system-page.js`
  (`:56-81`) shows only `/api/info`'s `base_prompt` (`app.py`, the `info()`
  route).
- **Composition** (`agent/config.py::compose_system_prompt`): base, `---`,
  persona, `---`, the rules block (`db/_rules.py::render_rules_block`), `---`,
  the notes block (`db/_notes.py::render_notes_block`).

## Acceptance Criteria

- [ ] AC1. `GET /api/info` adds `rules_prompt_example` and
      `notes_prompt_example` (strings), and keeps `version` and `base_prompt`
      unchanged.
      - `rules_prompt_example` is
        `render_rules_block(["{first enabled rule}", "{second enabled rule}"], notes_present=True)`.
      - `notes_prompt_example` is `render_notes_block([...])` with two
        placeholder notes, `{a saved note}` (trusted) and
        `{a note written after content not from the operator}` (untrusted),
        so the `(unverified)` marker shows.
      - Both come from the real render functions; there are no copied
        strings.
      - A unit test asserts that both appear verbatim in a real
        `compose_system_prompt` output built with the same placeholders.
- [ ] AC2. The Prompts page shows, in order, four headed sections:
      - **Base prompt**, the existing `pre` (testid `base-prompt-content`
        unchanged);
      - **Agent persona**, a line: "Each agent's own system prompt, set on its
        General tab, follows the base prompt.";
      - **Rules**, a line "Added when the agent has enabled rules, numbered in
        your order." and a `pre` (testid `rules-prompt-content`);
      - **Notes**, a line "Added last when the agent keeps notes." and a `pre`
        (testid `notes-prompt-content`).

      The intro text says the layers are assembled in this order, separated by
      `---`, and are read-only. The page is DOM-built with no HTML sinks, and
      uses the project's section-title (eyebrow) style.
- [ ] AC3. New testids are registered. Static guards and `make test-unit`
      pass. The Settings browser test for the Prompts page (find it with
      `grep base-prompt-content tests/browser`) is extended to assert the
      three `pre` blocks and their order, and the `settings` lane passes.
- [ ] AC4. `the_one/agents.md` (Settings › Prompts) and CLAUDE.md's M27
      paragraph (one clause) are updated.
