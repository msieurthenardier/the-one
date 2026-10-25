# Leg: disabled-buttons-and-guard

**Status**: completed
**Flight**: [Settings on the library](../flight.md)

## Objective
1. Make disabled buttons readable in both themes (B14, ledger row 37) by moving every disabled **button** from `opacity: 0.4` to opaque disabled tokens.
2. Add the emitted-class guard: every class a library factory emits is owned by a catalogue row or explicitly exempt, with a ratchet that is exact in both directions.

Split from the original leg 04a at its design review (2026-10-23). The disabled-button change is visible in every editor, and deserves its own review and lane run.

## Context
- **The disabled `opacity: 0.4` sites** (`components.css`, from the design review; re-locate them):
  - **Buttons, which move to tokens:** `.btn-outlined-primary:disabled` (`:480`), `.btn-filled-primary:disabled` (`:489`), `.btn-ghost:disabled` (`:501`), `.btn-muted-destructive:disabled` (`:510`), `.save-btn[disabled]` and `.save-btn:not([disabled])` (`:1464-1465`), `.refresh-btn:disabled` (`:1476`), and the progress cancel button (about `:2342`).
  - **Not buttons, which stay on opacity:** the checkbox (`:386`) and the toggle track (about `:1997`). Their disabled look is a control state, not a label, and is out of B14's scope. Record that.
- **The target:** a disabled button's label reaches **at least 3:1** against the surface directly behind it, in both themes. For a filled button that is its own disabled fill; for outlined, ghost and destructive buttons, the surface the button sits on (`--surface-elevated` or `--bg`). WCAG exempts disabled controls; this is the operator's approved readability target.
  - A disabled button must still read as disabled without relying on colour alone: keep `cursor: not-allowed`, and keep a visible difference from the enabled look.
  - Windows forced colours: disabled buttons use `GrayText`. Check it with a CSS-text assertion.
- **Tokens:**
  - new opaque-hex tokens, for example `--btn-disabled-fg`, `--btn-disabled-bg` and `--btn-disabled-border`, light and dark, in `css/tokens.css`;
  - the same values mirrored in `tests/browser/design_tokens.py` (`test_ui_guards.py` pins the mirror against `tokens.css`);
  - the a11y pairs in `tests/test_design_tokens_a11y.py` computed with `contrast_ratio` (opaque hex);
  - a consumption pin, like `_FILL_SITES`: each disabled block uses the tokens and not `opacity`.

  Keep or drop the 0.2s opacity transition, and say which.
- **The emitted-class guard** (`tests/test_ui_emitted_classes.py`, unit tier).
  - **The scan:** reuse the tokenizer `scan_js` already provides in `tests/test_ui_ownership.py` (import it). Collect every string literal in class-setting expressions in `js/ui/*.js`: `className` keys and assignments, `classList.add`, the `VARIANT_CLASS`/`SIZE_CLASS`-style tables, `rootClass`, `cls +=`, and ternaries.
  - **Each class token found** is owned by some catalogue row, or is in `EMITTED_EXEMPT` (a dict of name or prefix to reason).
  - **The ratchet is exact in both directions,** like the ownership test: a new unowned class fails, and a stale exempt entry fails.
  - **The design review measured about 193 class literals, about 18 unowned and 11 dynamic families,** so expect a starting exempt list of about 20-25 entries, plus the legacy names 04a and 04b emit before their handovers (`page-header`, `page-title`, `banner*`, `code-block`). Paste it into the flight log.
  - **The docstring names its blind spots:** it is heuristic; a class built from a variable outside the recognised forms is invisible. The guard is a ratchet, not a proof.
  - **Falsifications,** both recorded: a fake unowned literal fails, and a stale exempt entry fails.
- **Order:** this leg runs after 04a and 04b, so the guard's starting list reflects their controls. Legs 04d and 04e update it for their new classes.

## Acceptance Criteria
1. Every button disabled site above uses the tokens, and none uses `opacity` for its disabled state. The consumption pin passes. The non-button sites are unchanged, with the reason recorded.
2. The a11y test computes each disabled button variant's label against its background in both themes: at least 3:1, pinned. `cursor: not-allowed` is kept. The forced-colours rule is asserted.
3. The `design_tokens.py` mirror matches `tokens.css` (`test_ui_guards.py`).
4. **The visible change is captured.** Re-capture a disabled Save in both themes (one Settings surface and one Library editor) and compare it with leg 01's before set. The difference is ledger row 37, with the before and after contrast numbers.
5. The emitted-class guard passes with its exempt list committed, and both falsifications are recorded in the flight log.
6. The unit tier, the static guards, both contracts lanes and every editor lane (`providers`, `agents`, `agent-tabs`, `library`, `knowledge`, `mcp`, `settings`) pass, at most 3 at a time.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_ownership.py tests/test_ui_control_inventory.py tests/test_ui_emitted_classes.py -q -x --timeout 120`.
- The lanes above under `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`.
- The capture compare.
- `make test-unit` once.

## Files Affected
- `static/css/tokens.css`, `static/css/components.css`.
- `tests/browser/design_tokens.py`, `tests/test_design_tokens_a11y.py`, `tests/test_ui_emitted_classes.py` (new).
- `docs/ui-control-inventory.md` (the button row's disabled state, and a note on the guard), `the_one/agents.md`, CLAUDE.md (the control library paragraph: one sentence on the guard), the flight log.

## Citation Audit
- The disabled sites `components.css:480/489/501/510/1464` were verified by an FD grep. `:386`, `:1476`, `:1997` and `:2342` come from the 04a design review.
- `scan_js` in `tests/test_ui_ownership.py`, and the 193/18/11 counts, come from the 04a design review.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
