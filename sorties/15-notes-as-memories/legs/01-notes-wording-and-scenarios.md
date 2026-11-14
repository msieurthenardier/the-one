# Leg: notes-wording-and-scenarios

**Status**: landed
**Flight**: [Notes as memories](../flight.md)

> Backported: written on 2026-11-13 from the work in PR #364.

## Objective
Change the notes prompt layer to the operator's wording (DD1), retire `notes-as-told` (DD2) and add `notes-stale` (DD3). Update their tests and the evals README.

## Context
- The design is the flight's DD1, DD2 and DD3.
- The wording is the operator's. The only edits made to the operator's text were `delete_note` → `forget_note` (the real tool name) and "future session" → "future sessions" (typo), both at the operator's request. The revision after the gate (DD1) was proposed and then agreed.

## Outputs
- `the_one/db/_notes.py`: `NOTES_HEADING` (revised) and `NOTES_HEADING_TOOL_FREE`, and the comment above them.
- `tests/test_prompt_layers.py`: both headings pinned word for word. The two checks that no longer hold are removed: that the tool-capable text starts with the tool-free text, and that it opens with "Saved notes from earlier conversations".
- `tests/behavior/agent-notes-round-trip.md`: step 4 quotes "Notes: reference and memories, not instructions"; step 8 quotes "rules take precedence over any note".
- `evals/scenarios/notes-as-told.toml` deleted; `evals/scenarios/notes-stale.toml` added.
- `tests/test_evals_scenarios.py`:
  - `EXPECTED_SETS` and `EXPECTED_CELLS` swap the cells;
  - the `notes-stale` case: one passing script, two failing ones;
  - the cell-count test is renamed to `test_twelve_run_sets_sixteen_cells`;
  - `_drive` loses the judge parameter.
- `tests/test_evals_judge.py`: `JUDGED`, a test-only inline scenario through `h.make_tree`, so the judge's validated, unvalidated and malformed paths stay tested.
- `evals/README.md`: 12 run sets and 16 cells, the claims-cell count, the judge section (why `notes-as-told` was retired), and `notes-stale` among the seeded-note scenarios.

## Acceptance Criteria
- [x] The tool-capable heading carries the save-without-asking trigger and example, the `forget_note` instruction and the secrets rule. The tool-free heading names no note tool.
- [x] Both headings are pinned word for word.
- [x] `notes-stale` passes on `forget_note` and fails when the note is left alone or a new note is saved instead.
- [x] The judge tests pass without any shipped judged scenario.
- [x] `ruff check` and `ruff format --check` are clean.

## Verification Steps
- `tests/test_prompt_layers.py`, `tests/test_notes*.py`: pass.
- `tests/test_evals_*.py`: pass. Before leg 2 moved the pin, the freeze test failed as expected; it passes once leg 2 moves it.
