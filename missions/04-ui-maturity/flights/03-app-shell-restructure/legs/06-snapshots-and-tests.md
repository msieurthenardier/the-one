# Leg 06 — Snapshot Policy + A11y Polish

**Status**: completed
**Type**: autonomous (small)
**Depends on**: legs 01-05 (and the mid-flight snapshot policy decision)

---

## Why scope changed

Original plan: regenerate all 12 F2 visual snapshot baselines to capture the new top-bar layout, add 8 keyboard-state baselines, total 20 committed to git.

Mid-flight (during leg 04 / batch A) the user changed the policy: **visual snapshot baselines are gitignored, never committed.** Each developer regenerates locally. CI never runs pixel comparison. That decision invalidates the original leg-06 goal.

Replacement scope (this leg):

1. Split the snapshot suite onto its own pytest marker (`pixel`) so the standard `-m browser` collection used by CI never touches them.
2. Document the local-only snapshot workflow in `the_one/agents.md`.
3. Land the three non-blocking a11y polish items flagged in batch-A's accessibility review.

---

## Pytest marker split

Added a `pixel` marker; default `addopts` deselects it alongside `live` and `browser`.

| Marker | Tests | Default `pytest` | CI |
|---|---|---|---|
| (no marker) | unit | runs | runs |
| `live` | hits real LLM APIs (paid) | skipped | skipped |
| `browser` | Playwright **functional** flow tests | skipped (run with `-m browser`) | runs `-m browser` |
| `pixel` | Playwright **visual** snapshot regression | skipped (run with `-m pixel`) | **never runs** |

Snapshot tests in `tests/browser/test_visual_snapshots.py` had `@pytest.mark.browser` swapped for `@pytest.mark.pixel`. They no longer collect under `-m browser`.

PIL + pixelmatch imports were promoted to `pytest.importorskip(...)` at the top of `test_visual_snapshots.py` so a venv without those dev deps (the typical CI environment) collects the module cleanly and skips the whole file. With the libs installed locally, the suite runs normally.

The existing missing-baseline auto-generation logic (`_assert_screenshot` line 113: `if _update_mode() or not baseline_path.exists()`) stays — it's friendly for fresh checkouts. The docstring at the top of the snapshot file was updated to note baselines are gitignored and CI never runs the pixel suite.

---

## Documented workflow (`agents.md` "Pytest markers" + "Visual snapshot workflow" subsections)

Local dev:
1. **First run on a fresh checkout**: `pytest -m pixel --snapshot-update` (or `UPDATE_SNAPSHOTS=1 pytest -m pixel`) — generates baselines into `tests/browser/__snapshots__/` (gitignored).
2. **Subsequent runs**: `pytest -m pixel` — compares each scenario's screenshot against the local baseline; >2% pixel diff fails and writes `<name>-actual.png` + `<name>-diff.png` next to the baseline.
3. **After an intentional layout change**: `pytest -m pixel --snapshot-update` to regenerate.
4. **CI**: never runs `-m pixel`. Functional Playwright coverage is provided by `-m browser`.

If pixel regression detection ever becomes a CI requirement, the design note in `agents.md` recommends: capture a fresh baseline on each run, store it as a build artifact, and compare against the previous successful build's artifact. Do not commit baselines to git.

---

## A11y polish items (batch-A review carry-overs)

Three non-blocking items flagged by the Accessibility Reviewer (Sonnet) at batch-A signoff. All landed in this leg.

1. **chip-remove `aria-label` includes item name** (`studio.js` lines 317, 327, 549). Was `aria-label="Remove"` for all three sites — screen readers reading multiple chips heard "Remove" repeatedly without context. Now `aria-label="Remove <item-name>"` in all three sites (MCP source chips, knowledge-base chips, dynamic add-dropdown chips). `escapeAttr(name)` keeps the attribute safe.
2. **Active picker option gets `aria-current="page"`** (`app.js` line ~158). The picker popover is wrapped in a `<nav>` landmark; sighted users see the `.active` cyan-stripe but screen-reader users got no announcement of which area is current. WCAG 2.2 best practice. Now: when an option matches the current area, `aria-current="page"` is set; otherwise removed. Closes the `<nav>` semantic loop.
3. **Picker `<nav>` landmark concern collapses into item 2.** The reviewer noted `<nav>` with `<button>` children is "semantically unusual but operable; AA-compliant via aria-label='App areas'". Adding `aria-current` to the active option resolves the semantic ambiguity (the `<nav>` IS area navigation; buttons that perform navigation + an `aria-current` is a recognized pattern). No structural change needed.

---

## Test counts after leg

- Unit: **393 passing** (unchanged).
- Browser (`-m browser`): **32 passing, 1 skipped** (snapshot module skipped via `importorskip` when PIL absent).
- Pixel (`-m pixel`): collects 12 tests, runs locally with pillow + pixelmatch installed. Skipped when libs absent.

---

## Files changed

- `pyproject.toml` — `pixel` marker registered; default `addopts` excludes it.
- `tests/browser/test_visual_snapshots.py` — markers retagged `browser → pixel`; PIL/pixelmatch imports promoted to `importorskip`; docstring updated to reflect gitignored / CI-skipped policy.
- `the_one/interfaces/web/static/js/areas/studio.js` — chip-remove `aria-label` includes item name (3 sites).
- `the_one/interfaces/web/static/js/app.js` — active picker option gets `aria-current="page"`.
- `the_one/agents.md` — new "Pytest markers and what runs where" subsection + "Visual snapshot workflow (local-only)" subsection under Browser test fixtures.

---

## Out of scope

- Regenerating any baselines (gitignored, leave to local dev).
- New snapshot scenarios for keyboard-state focus rings (the user's policy makes this lower-value; if needed, devs add them locally).
- The two F2-debrief deferred items (`section-marker` lift, `// PREFIX` literal-vs-`::before` consolidation) — still scheduled for F3.5 form-primitive-extraction follow-up.

---

## Acceptance

User direction (verbatim): *"with regard to the snapshots we should describe the workflow rather than doing a snapshot comparison necessarily... For CI we should exercise the playwright tests but only from a functional and not a pixel comparison perspective."* Delivered as scoped above.
