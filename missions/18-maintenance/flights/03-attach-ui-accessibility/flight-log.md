# Flight Log: Attach-UI accessibility

**Flight**: [Attach-UI accessibility](flight.md)

## Summary
Single leg landed 2026-07-10 — the accessibility review's three attach-UI gaps
(missing stage/remove live-region, non-distinguishing accessible names, remove-glyph
contrast) closed in one coherent pass over `chat.js` + `components.css`. Browser suite
green (9/9 in `test_flow_chat_image_attach.py`, incl. 2 new DOM-assertion tests). `ruff
check`/`ruff format --check` clean. Uncommitted, pending flight review.

---

## Leg Progress

### Leg 1 — attach-ui-a11y-pass (landed 2026-07-10)

**A1 — live-region (`the_one/interfaces/web/static/js/areas/chat.js`).** Added a
dedicated visually-hidden `aria-live="polite"` status element
(`data-testid="chat-attachments-status"`, using the project's existing `.visually-hidden`
sr-only utility class from `chat.css`) as a sibling of `.chat-attachments`, NOT on the
visible chicklet row itself (that row fully rebuilds via `innerHTML` on every mutation —
making it the live region would re-announce all N remaining chips on a single removal,
per the design review). New `announceAttachmentChange(text)` helper sets the element's
`textContent` to a short delta: `"Image staged"` (first image), `"N images staged"`
(subsequent stages, N = total after the mutation), `"Image removed"` (any removal) —
called from `appendStagedImage()` / `removeStagedImage()`. Fixed the stale comment at
the old `chat.js:1593-1596` (cap-rejection notices already announce via the message
log's own `role="log" aria-live="polite"`; only the staging-row silence was new — the
comment previously implied the cap notices themselves were awaiting this leg).

**A2 — distinguishing accessible names (`chat.js`, `buildAttachmentChip`).**
Interpolated the 1-based index (`idx + 1`) into both `thumb.alt`
(`"Staged image N"`, was the identical `"Staged image attachment"` for every chip) and
the remove button's `aria-label` (`"Remove staged image N"`, was the identical
`"Remove attached image"`).

**A3 — remove-glyph contrast (`the_one/interfaces/web/static/css/components.css:587`).**
`.chip-remove` resting `color` changed `--status-danger-muted` → `--status-danger`
(≈4.14:1 in light theme → clears 4.5:1; hover already used `--status-danger` and dark
theme already passed). Left the `transition: color 0.2s` rule untouched (A4, the AAA
reduced-motion gap, is explicitly deferred). Blast radius verified narrow: admin/studio's
`.chip-list-editor .chip-remove` (`admin.css:425-439`) carries a more-specific `--accent`
override, unaffected.

**Tests:** extended `tests/browser/test_flow_chat_image_attach.py` with two new
functional/DOM-assertion tests (no pixel snapshots): `test_chat_attachment_live_region_announces_stage_and_remove`
(asserts the hidden status element exists with `aria-live="polite"` + the
`.visually-hidden` class, that the visible `.chat-attachments` row carries no
`aria-live`, and that the delta text updates through stage/stage/remove) and
`test_chat_staged_images_have_distinct_accessible_names` (asserts distinct `alt`/
`aria-label` pairs across two staged images). `THE_ONE_DEV_MODE=true PYTHON=.venv/bin/python
bash scripts/run-tests.sh -m browser tests/browser/test_flow_chat_image_attach.py` — **9
passed** (7 existing + 2 new), 0 failed, ~19s. Also ran `tests/test_design_tokens_a11y.py`
+ `tests/test_ui_guards.py` (153 passed) to confirm the `--status-danger-muted` token
contrast tests and the testid-registry sync guard were unaffected by the CSS/JS changes.

**Docs:** added `chat-attachments-status` to `docs/ui-testid-registry.md`.

**Lint:** `ruff check the_one/ tests/` — all checks passed. `ruff format --check` — 409
files already formatted (no reformat needed).

**No regressions** — all 7 pre-existing tests in the file (including the Flight 2 cap
tests) still pass unmodified.

### Review polish (both reviewers CONFIRMED; 3 non-blocking a11y-review observations closed 2026-07-10)

**Obs 1 — regression gate for the A3 contrast fix.** The A3 fix retuned `.chip-remove`'s
resting color to `--status-danger`, but no test gated that pair against the fill it
actually renders on (`.chip`'s `--accent-translucent` wash). Added
`test_chip_remove_danger_on_chip_fill_passes_body_aa` (`tests/test_design_tokens_a11y.py`,
mirrors the existing `--status-danger`-on-`--status-danger-bg-soft` composited-contrast
pattern at ~line 251): reconstructs the rendered `.chip` fill by compositing
`--accent-translucent`'s base (`--accent`) at the theme's wash alpha (dark 0.10, light
0.08) over each ladder surface (bg / surface / surface-elevated), then asserts
`--status-danger` clears 4.5:1 on that fill — both themes. Measured: dark 4.64–5.98:1,
light 4.72–5.68:1 across the three surfaces; worst case is `surface_elevated` in both
themes, still >0.1 above threshold. This is now the durable net — a future
`--status-danger` / `--accent-translucent` retune fails this test before it can silently
regress the fix.

**Obs 3 — restored the hover affordance.** The A3 fix made `.chip-remove`'s resting and
`:hover` colors identical (both `var(--status-danger)`), so hovering gave no visual
feedback. Rather than reach for a darker danger shade (no such token exists — nothing
between `--status-danger` and the desaturated `--status-danger-muted`, which is the
color the fix moved *away* from), layered the existing `--status-danger-bg-soft` wash as
a `background-color` on `:hover`/`:focus-visible` instead — the same wash already used
for `.app-flash.error`, `.editor-error-banner`, and `.cap-chip-no-tools`. Resting `color`
stays `--status-danger` (the gated pair is untouched). Verified by hand that the glyph
still clears 4.5:1 against the now-two-washes-deep hover fill (danger-bg-soft composited
over the chip's accent-translucent fill): worst case 4.64:1 (dark, surface-elevated),
4.72:1 (light, surface-elevated) — both still ≥4.5:1. `components.css:587-593`:
```css
.chip-remove { cursor: pointer; color: var(--status-danger); font-size: var(--font-size-tiny); border-radius: 3px; transition: color 0.2s, background-color 0.2s; background: transparent; border: none; padding: 0; }
.chip-remove:hover, .chip-remove:focus-visible { background-color: var(--status-danger-bg-soft); }
.chip-remove:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
```

**Obs 2 — stale comment fixed.** `tests/test_design_tokens_a11y.py:172` (now ~176) said
`status_danger_muted` gated "chip-remove on chip surface" — no longer true post-A3
(`.chip-remove` now uses `--status-danger` at rest, gated by the new obs-1 test).
Corrected the comment: `status_danger_muted`'s remaining example consumer is
`.list-item-delete` (session-delete on session-item); `.chip-remove` is called out as no
longer an example, pointing at the new test.

**Tests (re-run after polish):** `tests/test_design_tokens_a11y.py` — **145 passed**
(139 prior + 6 new parametrized cases from the obs-1 test: 2 themes × 3 ladder
surfaces). `THE_ONE_DEV_MODE=true PYTHON=.venv/bin/python bash
scripts/run-tests.sh -m browser tests/browser/test_flow_chat_image_attach.py` — **9
passed**, 0 failed (unchanged — the hover-affordance CSS has no browser-test assertion
today; covered by the manual contrast check above). `tests/test_ui_guards.py` — 14
passed (mirror-sync/testid-registry guards unaffected — no token values changed). `ruff
check the_one/ tests/` — all checks passed. `ruff format --check` — 409 files already
formatted. Still uncommitted, pending flight review.

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
