# Squawk 0206: Text and UI contrast below WCAG AA

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-13
**Completed**: 2026-10-13

## Report
GitHub issue #236 reports that light-mode text and UI elements are hard to read. The operator confirmed it applies to **both** themes. Fix target: every text-bearing token clears 4.5:1 and every non-text UI token clears 3.0:1 on all ladder surfaces (`bg`, `surface`, `surface-elevated`) in both themes. No exceptions. The fg ladder must keep its order (fg > secondary > tertiary > muted > faint).

## Evidence
Ratios are computed with `contrast_ratio` in `tests/test_design_tokens_a11y.py` over `tests/browser/design_tokens.py` (which mirrors `tokens.css`). The gaps are all deliberate exceptions or under-gated pairs in that test:
- `--fg-faint` is a text token that the test pins *below* body AA (`test_fg_faint_band_exception`, band 3.0 ≤ r < 4.5). Its ratios on bg / surface / surface-elevated:
  - dark `#6b6d78`: 3.67 / 3.45 / 3.27
  - light `#898993`: 3.46 / 3.32 / 3.15
  - Consumers: `chat.css` (6) and `studio.css` (2).
- Dark `--accent-fill` `#7c3aed` on `surface-elevated` is 2.95, under the 3.0 UI threshold (`test_accent_fill_vs_surface_elevated_dark_band_exception`).
- `--status-danger-muted` is used as delete-affordance **text** but is gated only at 3.0 (`test_large_or_ui_passes_aa`). Light `#b45252` on surface-elevated is 4.47, under 4.5.
- `--fg-muted` sits closest to the floor of the gated text tokens (light 4.59, dark 4.69 on surface-elevated). It has to move up for `--fg-faint` to rise without inverting the ladder.
- Out of scope: hairline separators (`--border`, `--border-hover`) are decorative, and WCAG 1.4.11 does not cover them.

## Corrective Action
Retuned the shared tokens in `tokens.css` (dark and light blocks; no other duplicates exist), mirrored them in `tests/browser/design_tokens.py`, and tightened the gates in `tests/test_design_tokens_a11y.py`: `fg_faint` and `status_danger_muted` joined the body-AA sweep (`_BODY_FG_TOKENS`), the faint band exception and the dark accent-fill band exception were retired (accent-fill on surface-elevated is now one parametrized >=3.0 gate), and `test_fg_ladder_is_strictly_ordered` pins fg > secondary > tertiary > muted > faint with >=0.3 steps on every ladder surface in both themes. Neutral tints were kept (dark cool grey, light zinc). Desktop chrome palette (`chrome.py` `text_inactive`/`fg_secondary`), `tests/test_window_chrome.py`, the Windows behavior spec and `agents.md` were updated to match. Chosen over lowering the ladder or keeping exceptions because the operator ruled no exceptions; the ladder was raised from the top (muted/tertiary/secondary in dark) so faint could rise without inversion.

Ratios on bg / surface / surface-elevated:

| token | theme | old | new | new ratios |
|---|---|---|---|---|
| fg-secondary | dark | #a1a3ad | #adafb7 | 8.62 / 8.10 / 7.69 |
| fg-tertiary, fg-tool-msg | dark | #8f919c | #9a9ca4 | 6.89 / 6.48 / 6.14 |
| fg-muted | dark | #85878f | #8f9199 | 6.00 / 5.64 / 5.35 |
| fg-faint | dark | #6b6d78 | #868890 | 5.34 / 5.02 / 4.76 |
| accent-fill | dark | #7c3aed | #7f3eef | 3.45 / 3.24 / 3.07 (white ink 5.47) |
| fg-muted | light | #6e6e77 | #65656e | 5.77 / 5.53 / 5.25 |
| fg-faint | light | #898993 | #6d6d76 | 5.12 / 4.91 / 4.66 |
| status-danger-muted | light | #b45252 | #af4d4d | 5.26 / 5.04 / 4.79 |

Unchanged: light fg-secondary/tertiary, dark/light fg, dark status-danger-muted (6.47 min), light accent-fill. Dark `--badge-openrouter` stays #7c3aed (separate token).

## Verification
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_ui_guards.py tests/test_window_chrome.py -x --timeout 60` -> 336 passed.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget.

## Disposition
