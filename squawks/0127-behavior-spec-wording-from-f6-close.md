# Squawk 0127: Behavior-spec wording drift from the Mission 25 Flight 6 close

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-10-07

## Report

Mission 25 Flight 6's mission-close re-runs (run `2026-10-07-11-51-23`) all passed. Their Validators listed Expected-Result wording that predates the flight's intended changes. No product change is needed; the specs should say what the build does now, so a later run doesn't stop to re-interpret them. Same shape as squawk 0122.

## Evidence

Each run log's "Validator closing" under `tests/behavior/{slug}/runs/2026-10-07-11-51-23.md`:

- **`system-provider-config`:**
  - Step 2: the empty state has no intro line, and it has its own Add provider button.
  - Step 5: name the "Provider created" toast, the new tile, the intro line and Available models with its help line.
  - Steps 2 and 6: "Used by" is visually hidden; the tile reads "0 agents".
  - Step 7: "the text clears" means the Unsaved changes caption. Name the "Provider saved" toast and the focus on the editor title.
  - Step 8: both a toast and an inline result line appear.
  - Steps 9–10: allow a re-arm before the confirm, and let the armed look settle for about 0.6 s before capturing it.
  - Step 10: the "Provider deleted" toast.
  - The header's Updated line.
- **`shell-navigation-smoke`:**
  - Step 9: record the raw hash at navigation commit (the legacy form is expected there), then assert `#settings/providers` after boot and after the reload.
  - Step 4: the description "begins with" the quoted sentence; "Filter agents" is an accessible name, not a visible label.
  - Step 7: restoring Auto removes the `theme-preference` key.
- **`studio-agent-crud`:**
  - Steps 3–4: with one provider and one model, Provider and Model are pre-selected.
  - Step 8: about 400 ms of settle before judging the armed look.
  - Step 9: name `new-agent-btn`.
  - A neutral "Saved" toast after Save is expected.
- **`list-and-detail`:**
  - Step 18: exempt the Design language page's own `role=alert` demos from "No error banners".
  - Say where focus goes after a dirty-guard Continue (`MAIN#main-content`).

## Corrective Action
Wording only, in four specs under `tests/behavior/`, each with an `Updated` line (and the Last Run line noting the fix); no expectation changed in meaning:
- `system-provider-config`: step 2 (intro line only with tiles, empty state has no intro and its own `providers-empty-add`, usage value with a visually hidden "Used by " prefix); step 5 ("Provider created" toast, new tile, intro, "Available models" and its help line); step 6 ("0 agents", prefix hidden); step 7 ("Unsaved changes" caption clears, "Provider saved" toast, focus on the editor title); step 8 (toast and inline result line); step 9 (about 0.6 s settle, re-arm if the window lapsed); step 10 (re-arm before confirm, "Provider deleted" toast, focus is a DOM read).
- `shell-navigation-smoke`: step 4 ("begins with" the description; "Filter agents" is a visually hidden label); step 7 (Auto restores to an absent `theme-preference` key); step 9 (raw legacy hash at navigation commit, `#settings/providers` after boot and after reload).
- `studio-agent-crud`: step 4 (Provider and Model pre-select with one of each); step 5 and 7 (neutral "Saved" toast); step 8 (about 400 ms settle); step 9 (`new-agent-btn`, focus read from the DOM).
- `list-and-detail`: step 5 and step 16 (focus on `MAIN#main-content` after Continue); step 18 (Design language `role=alert` demos exempt).
**Skipped:** the Validators' other notes not in the Evidence list (section labels as eyebrows, the hidden "Loading library…" `h3`, the "Light Agents link colour" nit, `~new` pre-state hash capture, the dropped default port, step 2 splitting, the "fully in view" inclusivity, the grey-on-grey "mock" badge). No product defect found.

## Verification
Each bullet, the spec and step edited, and the source it was checked against (all under `the_one/interfaces/web/static/js/`):
- provider step 2 (no intro/empty Add) -> `areas/admin/providers-list.js` (`INTRO` and the intro built only with the grid; empty state `providers-empty` with action `providers-empty-add`).
- provider step 5 (toast, tile, intro, Available models) -> `areas/admin/provider-editor.js:847` ("Provider created"), `:109-110` (heading and `provider-models-help`).
- provider steps 2 and 6 ("Used by" hidden, "0 agents") -> `providers-list.js:97-103` (`.visually-hidden` prefix).
- provider step 7 -> `provider-editor.js:725` ("Unsaved changes" caption), `:847` ("Provider saved"), `:870` (`focusAfter.restore(saveTok, focusTitle)`).
- provider step 8 -> `provider-editor.js:895-930` (inline `.test-result` span plus `showFlash` "Connection successful").
- provider steps 9-10 -> `confirm.js` (`revertMs` default 3000, lapse timer); `provider-editor.js:975` ("Provider deleted"). The 0.6 s settle is the squawk's figure; no CSS transition was found for it, so it is a conservative capture allowance.
- provider header Updated line -> edited.
- shell step 9 / 4 / 7 -> Validator closing (no product source involved for the hash samples); `js/theme.js:33` (`removeItem(STORAGE_KEY)`); step 4's hidden label per the run log.
- agent step 3-4 -> `areas/studio/general-tab.js:30` (`provider_config_id` defaults to `providers[0].id`).
- agent step 8 (400 ms) -> squawk's figure (no source constant); step 9 -> `new-agent-btn` per the spec's own locators; "Saved" toast -> `areas/studio.js:3685` (`showFlash('Saved')`).
- list-and-detail step 18 -> `ui/field.js:187` (`role: 'alert'`, the field-error demos on the Design language page); focus after Continue -> `nav.js:56-96` (`focusMain` on `#main-content`, `tabindex=-1` in `index.html:28`).
Discrepancies: none between the source and the Validators; the 0.6 s and 400 ms settle times have no source constant and are taken from the Validators' observation. `make test-unit`: 5458 passed, 10 skipped, 1898 deselected (no failures, so no re-run of `tests/test_self_configuration_surface.py` was needed).

## Sign-Off

**Reviewer**: independent batch Reviewer (Haiku tier: no credential, gate, sandbox or self-configuration-identity surface in the diff); `make test-unit` 5496 passed, 10 skipped; static guards 265 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-07` on branch `squawk/turnaround-2026-10-07`
