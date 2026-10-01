# Flight Log: Control Library Foundation

**Flight**: [Control Library Foundation](flight.md)

## Summary

Flight landed 2026-10-01 under autonomous execution: all 6 legs completed
(`ui-test-apparatus`, `control-mechanism-spike`, `deep-violet-tokens`, `core-controls`,
`menu-control`, `living-reference-and-inventory`). Mechanism decision: factories (DD1
confirmed; custom elements not adopted). Deep violet is applied app-wide. WebKit route 1
(local, Playwright WebKit 26.0 via userland libraries plus the WebKitGTK probe) works, so
no post-merge gating was needed. The flight-scoped Reviewer and Accessibility Reviewer both
confirmed; a fix round for non-blocking items was re-reviewed and confirmed. Squawks 0105
and 0106 close in the flight commit. The human touchpoints remain the post-Flight-3
checkpoint and the alignment flight.

---

## Reconnaissance Report

Source items folded into this flight (DD12), checked against `b9630bc`:

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Squawk 0105 — stale `DYNAMIC_SINK_BASELINE` header count | confirmed-live | `tests/test_ui_guards.py:90` still reads "92 sites across 27 files" | Fold into Leg 1 |
| Squawk 0106 — JS changes can skip the static UI guards | confirmed-live | `.flightops/agent-crews/leg-execution.md` names no static-guard tests for `static/` changes | Flight Director edits the crew prompts at flight start; close in the flight commit |
| Squawk 0101 — KB create lands on grid | confirmed-live (out of this flight) | Mission assigns it to Flight 3 | Not folded |
| Squawk 0082 (deferred) — `App.router.replaceSub` leaves `currentSub` stale | confirmed-live (out of this flight) | `static/js/app.js` | Carry to Flight 2 (router contract) |

---

## Leg Progress

### Leg 1: ui-test-apparatus

**Status**: landed (pending Flight Director review and commit)
**Started**: 2026-09-30  **Completed**: 2026-09-30

**Changes Made**
- `tests/_ui_guard_helpers.py`: `relpath(path, root=JS_DIR)`; `extract_testids`/`classify_sinks` thread `js_dir`; DD2 literal/parametric `testid:` patterns; `find_testid_value_violations`; `find_ui_dir_sink_tokens`.
- `tests/test_ui_guards.py`: library testid probes, testid-value guard and probes, ui-dir zero-token guard and probe, any-directory test; squawk 0105 comment reworded.
- `tests/browser/_a11y_resolve.js` (single resolver), `_a11y_resolvers.py`, `_ui_engines.py` (fixtures, pure `webkit_policy`, disk harness), `test_ui_apparatus_contract.py`; `conftest.py` registers the fixtures; chiplist test migrated onto the shared resolver (its `.chip-list-input` assertion stays local; `_RESOLVE_JS` removed).
- `tests/test_ui_engines_policy.py` (unmarked policy tests); `tests/test_webkitgtk_probe_safety.py` (unmarked, probe refusal tests; an addition beyond the leg).
- `scripts/setup-webkit-userland.sh`, `scripts/webkitgtk_probe.py`.
- `Makefile`, `ci/tasks/browser.yml` (image `3.11-bookworm`, `--with-deps chromium webkit`, `THE_ONE_REQUIRE_WEBKIT=1`), `.github/workflows/test.yml`.
- Docs: `the_one/agents.md` "UI test apparatus (M25 F1 L1)", `CLAUDE.md` pointer. Squawk 0105 Corrective Action and Verification written, status `in-progress`.

**WebKit route outcome: route 1 variant (Playwright WebKit with userland libraries) works locally.**
- `playwright install webkit` downloads webkit-2248 with no sudo. The host-validation step then fails, and a bare launch fails on missing libraries (`libwoff2dec`, `libavif`, `libevent`, `libflite`, `libgtk-4`, gstreamer-bad, `libgav1`, `libyuv`, `libabsl20220623`).
- `scripts/setup-webkit-userland.sh` fetches those with `apt-get download` + `dpkg -x` into `~/.cache/the-one-webkit-deps`. Playwright launches WebKit 26.0 and `test_ui_apparatus_contract.py[webkit]` passes (13/13), with the version printed (`[ui-engine] webkit 26.0`) and recorded via `record_property`.
- Deviation from the leg text: `LD_LIBRARY_PATH` cannot be passed through `launch(env=...)`, because the bundle's `MiniBrowser` wrapper overwrites it. The script therefore also writes `webkit-wrapper.sh`, which re-states the bundle paths and appends the userland dir. The fixture uses it as `executable_path` and passes `GST_PLUGIN_PATH` through `env`. A custom `executable_path` also skips host validation, so `PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS` is not needed. Chromium never sees the userland dir; `os.environ` is not mutated.

**Probe (AC13/AC14)**: WebView creation on WSLg works. Run against a dev instance (port 8485, scratch data dir under /tmp, dev mode, stopped with `make down` and the scratch removed; the credential was minted with `rotate-api-credential` against the scratch dir because `make up`'s verify step needs one):
- `--root-selector '[data-section="fields"]'`, dark and light: `engine_version` "WebKitGTK 2.52.6", env `GDK_BACKEND=x11`, `WEBKIT_DISABLE_DMABUF_RENDERER=1`, `hardware_acceleration_policy=never` (DISPLAY `:0`, WAYLAND_DISPLAY `wayland-0`), `actual_theme` equal to the requested theme, `results` `{count: 9, failures: []}`, `ok: true`, exit 0.
- `--root-selector '.design-language-section'` (all sections): 47 controls, ok. `body`: 63 controls, 1 failure (legacy markup, not identified, not fixed per the leg). `.design-language-page, #app-topbar`: 3 controls, ok.
- Refusals demonstrated with no contact to 8484: `http://127.0.0.1:8484/` and `http://localhost:8484/x` exit 2 with a refusal; `--data-dir` set to the derived platformdirs default exits 2 with a refusal.
- Note: the first run with `.design-language-page` (a class that does not exist) hit the 60s hard timeout cleanly (no hang), with JSON and exit 1.

**Verification (per AC)**
- AC1-AC5: `tests/test_ui_guards.py` (19 passed) plus `tests/test_ui_engines_policy.py`; probes in `tmp_path` assert each listed form. `grep -n "92 sites" tests/test_ui_guards.py` is empty.
- AC6: the resolver exists only in `_a11y_resolve.js`; the chiplist test imports the helper (2 passed).
- AC7-AC9: `-m browser tests/browser/test_ui_apparatus_contract.py -rA`: 26 passed (13 chromium + 13 webkit). Skip path with `THE_ONE_WEBKIT_FORCE_UNAVAILABLE=1`: 13 passed, 13 skipped with reason "WebKit unavailable: forced unavailable (...)". With `THE_ONE_REQUIRE_WEBKIT=1` added, the webkit params error (fail).
- AC10: chiplist test passes (shared lane). AC11: `git diff Makefile ci/tasks/browser.yml .github/workflows/test.yml`. AC15: docs read back.
- AC16 gates: `make lint` clean; `make test-unit` 4824 passed, 10 skipped; new/changed browser files 28 passed; `--lane shared` 206 passed, 3 skipped on the second run.

**Anomalies / notes**
- First `--lane shared` run had one failure, `test_flow_keyboard.py::test_agent_item_keyboard_select` (aria-selected "false"). It passed alone and on a full re-run of the lane, so it reads as a load-sensitive flake that predates this leg (the leg touches neither the test nor the agent list). Flagged, not investigated further.
- The body-scoped probe run reported one resolver failure on legacy markup; recorded, not fixed (leg scope).
- Operator-state check: only port 8485 and a /tmp scratch dir were used; the dev instance was stopped and the scratch dir and `.the-one.8485.*` files removed. Port 8484 and the default data dir were never contacted.


### Leg 2: control-mechanism-spike

**Status**: landed (pending Flight Director review and commit)
**Started**: 2026-09-30  **Completed**: 2026-09-30

**Changes Made**
- Library: `static/js/ui/core.js` (`util.el/uid/icon/rovingFocus`), `button.js`, `field.js` (`textInput`, `field`), `list-pane.js` (`listPane`, factory variant). Four `<script>` tags in `index.html` after `icons.js`; `.ui-list-pane*` CSS in `components.css` (`@layer components`, existing tokens only); `test_index_asset_cache_busting.py` count 55 to 59.
- Tests: `tests/browser/test_ui_library_contract.py` (56 params, both engines), `test_ui_listener_cleanup.py` (the spike's factory-side cleanup criterion plus negative control, kept because it tests committed code; renamed from `test_ui_mechanism_spike.py` so the leg's "no leftover spike file" grep is clean), `_dialog_rule.js`, `_dialog_rule_checks.py`, `test_ui_dialog_rule.py`, `test_ui_dialog_scroll.py`, `_probe_mount_ui.js`, `_probe_dialog_backdrop.js`; unit: `tests/test_ui_library_source.py` (ES5, strict IIFE, no app globals, export idiom), `tests/test_ui_mechanism_testids.py` (criterion 1 snippets), four new `--setup-script` tests in `tests/test_webkitgtk_probe_safety.py`.
- Probe: `scripts/webkitgtk_probe.py` gained `--setup-script PATH` (repeatable, validated before the WebView exists, wrapped to end in `true`) and an echo of `window.__probeReport` as `report` (an addition beyond the leg, needed to read the (f) backdrop colour out of WebKitGTK).
- Docs: `the_one/agents.md` Modals bullet rewritten to DD8; new "Control library (`App.ui`)" section.
- The throwaway `<ui-list-pane>` file (`_spike_ui_list_pane_ce.js`) was deleted after the decision; `git status --porcelain tests/browser | grep -i spike` is empty.

**Mechanism decision**: factories (DD1 confirmed). Evidence table in Decisions. AC7 stop condition did not trigger.

**Dialog rule (DD8)**, harness `_dialog_rule.js` (layer counts observed are in the test output with `-rA`):

| Check | Chromium 145.0.7632.6 | WebKit 26.0 | WebKitGTK 2.52.6 (probe) |
|---|---|---|---|
| (a) stacked, real clicks, Escape peels one each | pass, layers [1,2,1,0] | pass, [1,2,1,0] | n/a |
| (b) programmatic confirm over click-opened modal | pass, [1,2,1,0] | pass, [1,2,1,0] | n/a |
| (c) focus restore, mouse and keyboard (and inner opener after a peel) | pass | pass | n/a |
| (d) backdrop click: closes transient, not confirm | pass, [1,0,2,2,0] | pass, [1,0,2,2,0] | n/a |
| (e) inertness (real coordinate click, Tab, positive control) | pass; Tab reaches both dialog buttons, then hands focus to `(body)` | pass; same, plus Tab lands on the `<dialog>` element itself (still inside the modal) | n/a |
| (f) `::backdrop` colour equals resolved `--x-scrim` token | pass (rgb(12, 34, 56)) | pass (same) | pass, dark and light: `reportedBackdrop` equals `expectedToken`, literal control read back (so verifiable), `showModal` opened (`:modal`) |
| (g) body scroll, Chromium only, empty DB | 1024x768: scrollHeight 768 = clientHeight 768; 1440x900: 900 = 900. The shell does not scroll `body`; DD8's scroll-lock note stands (no lock needed). |

No `xfail`/"unverifiable" outcome occurred. **Finding for Flight 2:** the keyboard-open focus-restore check exposed a real race in the first harness draft (about 1 in 7 runs, Chromium): `dialog.close()` queues its `close` event as a task, so a dialog reopened in the same turn receives the OLD `close` event, and a wrapper that trusts it drops the reopened dialog from its stack (the next Escape then peels nothing). Fix in the harness: the `close` listener ignores the event while `dlg.open` is true. A deterministic regression (`test_reopen_right_after_close_survives_the_stale_close_event`) fails in both engines with the guard removed (falsified and restored) and passes with it. The real wrapper must carry the same guard; documented in `agents.md` Modals.

**WebKitGTK probe results** (dev instance on 8485, scratch data dir under /tmp, dev mode; stopped with `make down`, scratch removed; 8484 and the default data dir never touched):
- Factory mount (`--setup-script tests/browser/_probe_mount_ui.js --root-selector '#ui-probe-root'`), dark and light: engine `WebKitGTK 2.52.6`, env `GDK_BACKEND=x11`, `WEBKIT_DISABLE_DMABUF_RENDERER=1`, `hardware_acceleration_policy=never`, `actual_theme` equals requested, `results` `{ok: true, failures: [], count: 6}` (3 rows, filter, button, field input), exit 0.
- Custom element (two ordered setup scripts: definition file, then a mount wrapper, before deletion), dark: same engine and env, `{ok: true, failures: [], count: 6}`, exit 0.
- Dialog backdrop (`--setup-script tests/browser/_probe_dialog_backdrop.js`), dark and light: see (f) above, `ok: true`.

**Verification (per AC)**
- AC1-AC4: `-m browser tests/browser/test_ui_library_contract.py -rA`: 56 passed (28 chromium + 28 webkit, no skips); `tests/test_ui_library_source.py`; `tests/test_ui_guards.py` (testid-value and ui-dir guards now live over four files).
- AC5-AC7: Decisions entry; CE deleted.
- AC8-AC9: `test_ui_dialog_rule.py` 18 passed (9 per engine: (a)-(f) plus the stale-close regression and the probe-script test); `test_ui_dialog_scroll.py` 2 passed.
- AC10: docs read back. The registry (`docs/ui-testid-registry.md`) is unchanged: no `static/js` file calls a factory with a `testid`.
- AC11 gates: see "Gate results" below.

**Gate results (AC11)**
- `make lint`: clean (`ruff check`; `ruff format --check` also clean, 465 files).
- `make test-unit`: 4843 passed, 10 skipped (672.95s), includes the cache-busting count (59), the Leg 1 guards now live over `ui/`, `test_js_string_css_var_refs_are_defined`, the token-definition and a11y-token tests.
- Explicit browser files (`-m browser`, `-rA`): contract 56, dialog rule 18, dialog scroll 2, listener cleanup 6, apparatus contract 26 = 108 passed, no skips and no xfails; every `[webkit]` param ran (WebKit 26.0).
- `--lane shared`: 288 passed, 3 skipped (the same 3 skips as before this leg), 141.6s.
- `--lane system`: first run 123 passed, 1 failed (`test_flow_admin_tools_editor.py::test_editor_renders_prompt_block`: `.editor-title` not found within 8s on `#admin/tools/web_search`, an area this leg does not touch). It passed 3 of 3 times alone and the whole lane then re-ran clean: 124 passed in 227.3s. Read as a load-sensitive flake (same class as the Leg 1 `shared` flake); flagged, not investigated.
- Operator-state check: only port 8485 and a /tmp scratch dir were used; the instance was stopped with `make down`, the scratch dir and `.the-one.8485.*` files removed. Port 8484 and the default data dir were never contacted.

**Anomalies / notes**
- The dialog-harness race above (stale `close` event) is the one substantive finding; it changes what Flight 2's wrapper must do.
- In WebKit, Tab inside a modal can land on the `<dialog>` element itself; Chromium hands focus to browser chrome (`(body)`) after the last button. Both stay inside the modal or leave the page, never reaching an outside element; check (e) treats `(body)` as the engine handing off to chrome and still requires the outside button to be unreachable.
- The probe's `report` echo of `window.__probeReport` and the rename of the spike test file are additions beyond the leg text.

---

### Leg 3: deep-violet-tokens

**Status**: landed (pending Flight Director review and commit)
**Started**: 2026-09-30  **Completed**: 2026-09-30

**Changes Made**
- `tokens.css` + mirror `design_tokens.py` (both themes): `--accent-fill`, `--accent-fill-hover`, `--fg-on-accent-fill`, `--control-border`, `--control-thumb`, each commented; `--accent` comments rewritten (no longer "interactive states ONLY").
- CSS: fills migrated (list below); buttons restyled to the board's `.deep` rules (shared base block, per-variant colours, hover details, transitions on bg/border/color/opacity); `.btn-icon` (+ `.btn-sm`) added; `.save-btn` padding/size pins removed; `.delete-btn` pins removed (armed state kept, commented); `.mcp-refresh-tools-btn` size pin removed; boundaries on the checkbox, admin/studio `.tool-enable-switch-track` and `.tool-switch`; thumbs on `--control-thumb` in both states.
- `tests/test_design_tokens_a11y.py`: new gates (below), dark band exception, `"--control"` in `_FG_ROLE_PREFIXES`, `control_border` in the UI list, 17 usage pins (`test_migrated_site_consumes_the_gated_tokens`), housekeeping comments (fg_on_accent gate, danger soft-fill gate comment, status-text docstring, tokens.css accent comments, button block comment, admin track comment).
- `tests/browser/test_deep_violet_computed_styles.py` (new, `shared` lane): 5 tests x 2 themes x 2 engines (20 cases), reduced motion emulated, hover via `page.hover()`, area wrappers for admin/studio rules.
- Docs: `the_one/agents.md` (deep violet, fill tokens, `--control-*`, band exception, buttons, `.btn-icon`, completeness-net prefixes); `tokens-section.js` lists the four new colour tokens (`--control-thumb` omitted: a plain white, not a palette colour); `buttons-section.js` gains an icon-only row (SVG via DOMParser, no innerHTML sink).

**Token ratios (computed, verified by gates)**
| Pair | Dark | Light |
|---|---|---|
| `fg_on_accent_fill` on `accent_fill` / `accent_fill_hover` | 5.70 / 7.10 | 7.10 / 8.98 |
| `accent_fill` vs bg / surface / elevated | 3.31 / 3.11 / 2.95 (band) | 7.10 / 6.81 / 6.46 |
| `control_border` vs bg / surface / elevated | 3.87 / 3.64 / 3.45 | 3.60 / 3.45 / 3.28 |
| `control_thumb` on `control_border` (off) / `accent_fill` (on) | 4.88 / 5.70 | 3.60 / 7.10 |
| `status_danger` on elevated | 6.08 | 5.89 |

The approved hexes and the review-chosen `--control-border` hexes were used unchanged; every DD6/DD7 pair passes with no operator decision needed. Gate rows: `test_text_on_color` (+2 tuples), `test_accent_fill_vs_bg_and_surface_passes_ui_aa`, `..._elevated_light_...`, `test_accent_fill_vs_surface_elevated_dark_band_exception`, `test_status_danger_on_surface_elevated_passes_body_aa`, `test_toggle_thumb_pairs_hold_ui_contrast`; `accent_fill_hover` vs surfaces deliberately not gated (comment in the test).

**`var(--accent)` / `var(--fg-on-accent)` classification (static/css; JS has no inline `--accent` fills: the only JS hit is the `'--accent'` swatch name in `tokens-section.js`)**
- MOVED to fill tokens: `components.css` `.skip-link`; `.checkbox-primary:checked` (fill, border) and its `::after` tick; `.btn-filled-primary` (fill, ink); `admin.css` `.admin-theme-option.active` (fill, ink, border); admin+studio `.tool-enable-switch` on-track (`:checked`); `studio.css` `.tool-toggle:checked + .tool-switch` (fill; thumb to `--control-thumb`); `.chip-attached` (fill, ink, border; `white` fallback dropped); `chat.css` `.msg-pending-approval-approve` (fill, ink, border).
- STAY on `--accent` / `--fg-on-accent` (reason): `.context-bar` (chat.css:119) and `.admin-pf-pull-fill` (admin.css:161), data meters not controls; studio indeterminate `.tool-switch` thumb (pinned by its own gate, an accent wash track); `.msg.user.api` on `--accent-api` (the remaining real `fg_on_accent` x `accent_api` consumer); `.msg-pending-approval-badge--approved` on `--status-success` (chat.css:557); base `.admin-provider-badge` / `.admin-tool-badge` colours (overridden by modifiers); `.checkbox-primary:hover` border; every other `var(--accent)` hit (about 85) is an outline/focus ring, border, text link/chevron/hover colour, `border-left` bar, `--nav-fg-active`, or `.stub-sidebar .title` text colour, i.e. non-fill uses. Leg 2's `.ui-list-pane-row` selection is a ring/inset border, stays.

**Documented exceptions / accepted design notes**
- Compact CSS-only rows keep compact size, commented with DD6: `.tool-actions .btn-outlined-primary`, `.mcp-source-tile-row1 .mcp-refresh-tools-btn`.
- Indeterminate `.tool-switch` track: accent wash, no boundary; gated thumb carries the state.
- Secondary button on a `--surface-elevated` tile is a 1.1:1 hairline; accepted (label visible, WCAG 1.4.11 needs no boundary).
- Dark `accent_fill` on elevated is 2.95:1: band-pinned; also covers `.chip-attached` (white text on fill is 5.70).
- Dark checkbox tick changes from dark ink to white (expected).

**Verification**
- `tests/test_design_tokens_a11y.py tests/test_ui_guards.py tests/test_token_definitions.py`: 196 passed.
- `test_deep_violet_computed_styles.py`: 20 passed (chromium + webkit x dark + light), ~5.5s.
- Hit during the first full unit run: `test_no_new_dynamic_innerhtml_sinks` caught an `innerHTML` in my buttons-section icon row; replaced with DOMParser and re-run.
- `make lint` equivalents: `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/` clean (466 files).
- Full unit suite (`-m 'not browser and not live and not pixel'`): 4921 passed, 13 skipped, 711s.
- Browser lanes, run one at a time: shared 308 passed / 3 skipped (149s); system 124 passed (229s); chat 41 passed (98s); studio 186 passed / 3 skipped / 2 failed (503s). The two studio failures (`test_flow_agent_crud.py::test_studio_agent_crud_flow`, `test_flow_studio_mcp_editor.py::test_sandbox_chip_add_remove_marks_form_dirty`, both "locator expected visible") passed when rerun alone (2 passed, 5s), so per the standing flake rule they are treated as flakes, not regressions.
- Pixel snapshots not run, not regenerated, not committed.

### Leg 4: core-controls

**Status**: landed (pending Flight Director review and commit)
**Started**: 2026-09-30  **Completed**: 2026-10-01

**Changes Made**
- `ui/field.js`: `textarea`, `select`; `field` throws `field: checkbox/toggle carry their own label` for a control (or wrapper) marked `data-ui-own-label`.
- `ui/choice.js` (new): `checkbox`, `toggle`. `ui/feedback.js` (new): `badge` (+ `badge.KINDS`), `emptyState`. Script tags added after `list-pane.js`; cache-busting count 59 to 61.
- `ui/list-pane.js`: empty element via `emptyState`, kinded badges via `badge`, row `count`.
- `components.css`: checkbox `:indeterminate`/`:disabled`, `.ui-checkbox*`, `.ui-toggle*`, `.ui-empty-*`, `.badge*`, selected-row `--fg-secondary` rule, `.ui-list-pane-count`.
- Tests: `tests/browser/test_ui_choice_contract.py` (26 tests x 2 engines), `tests/test_ui_badge_kinds.py`, additions to `test_design_tokens_a11y.py` (selected-row composite gate x4, 12 badge-kind pair pins, 2 semantic-badge pins, 7 usage pins), probe mount script extended (+ assertion in `test_ui_library_contract.py`). Docs: `agents.md` "Control library".

**Deviation / finding**: the leg assumed `.badge` and `.badge--<kind>` existed. They did not (only per-area `.admin-provider-badge--*` etc.). I created them in `components.css`: the 12 token kinds use the gated `--badge-<kind>`/`--badge-ink-<kind>` pairs; `approved`/`dismissed` use `--fg`/`--fg-secondary` on `--surface-elevated` with an inset ring (both on the gated body ladder) rather than the chat area's ungated pair. The empty-state body/title pairs (`--fg`, `--fg-muted` on bg/surface) are covered by the existing body ladder; no new gate needed.

**Verification**
- Browser `-m browser tests/browser/test_ui_*.py test_deep_violet_computed_styles.py`: 180 passed, no skips (chromium + webkit).
- Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_library_source`, cache-busting, badge kinds): all pass.
- `ruff check` and `ruff format --check` clean. `make test-unit`: 4914 passed, 10 skipped (672s). `--lane shared`: 360 passed, 3 skipped (same pre-existing skips as Leg 3).
- WebKitGTK probe (dev instance 8485, scratch data dir, dev mode; `make down`, scratch and log removed): dark and light both `ok: true`, `failures: []`, `count: 16` controls, `actual_theme` equals requested, exit 0. Engine WebKitGTK 2.52.6 (system install as in Leg 2; version not re-printed this run).
- Fix during iteration: Playwright `fill` emits a clearing input event first, and the toggle track colour transitions, so those tests wait/assert on the final value.

### Leg 5: menu-control

**Status**: landed (pending Flight Director review and commit)
**Started**: 2026-10-01  **Completed**: 2026-10-01

**Changes Made**
- `static/js/ui/menu.js` (new): `App.ui.menu`, the APG menu button, per the leg ACs. `<script>` tag after `feedback.js`; `/static` ref count 61 to 62 in `tests/test_index_asset_cache_busting.py`.
- `css/components.css`: `.ui-menu*` block in `@layer components` (existing tokens only; popup `--surface-elevated` + `--border` + `--shadow-popover`; item hover/focus `--surface`; danger `--status-danger`, both pairs already gated).
- Tests: `tests/browser/test_ui_menu_contract.py` (new, 66 params, both engines, includes the menu-in-dialog checks on the Leg 2 `_dialog_rule.js` harness for keyboard-open, mouse-open and outside click); two menu cases added to `test_ui_listener_cleanup.py`; open and closed menus added to `_probe_mount_ui.js`.
- `the_one/agents.md`: "Control library" menu bullet (API, keyboard contract, outside-click/cleanup, dialog safety, no-flip limitation).

**Design notes / deviations from the leg text (none against ACs)**
- `focusout` closes only when `relatedTarget` is a real element outside `el`; a null `relatedTarget` is left to the document `pointerdown` handler, because WebKit does not focus a pressed button and would otherwise blur-close the menu before the click lands. A `mousedown` `preventDefault` on the popup keeps focus put as well.
- `rovingFocus` sets `tabindex=0` on the focused item; the menu resets all items to `-1` in a later popup keydown listener to satisfy "items stay tabindex -1".
- Playwright treats `aria-disabled` buttons as not enabled, so disabled-item clicks use `click(force=True)` (still a real mouse click). WebKit masks a throwing `onSelect` message as "Script error."; the test asserts the error fired and accepts either text.

**Verification**
- Probe: WebKitGTK 2.52.6 against a dev instance (8485, scratch data dir, dev mode; removed after), `--root-selector '#ui-probe-root'`: dark `ok: true`, light `ok: true`, count 22 (up from the prior probe's controls by the closed and open menu).
- `ruff check` and `ruff format --check`: clean. All `tests/browser/test_ui_*.py` + `test_deep_violet_computed_styles.py` with `-m browser`: 250 passed, no skips. Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_library_source`, cache-busting): pass. `make test-unit`: 4917 passed, 10 skipped. `--lane shared`: 430 passed, 3 skipped (the pre-existing `test_flow_picker.py` skips).

### Leg 6: living-reference-and-inventory

**Status**: landed (pending Flight Director review and commit)
**Started**: 2026-10-01  **Completed**: 2026-10-01

**Changes Made**
- `design-language-page.js` rebuilt with `App.ui.util.el` (no inner-HTML sink; its two `DYNAMIC_SINK_BASELINE` entries removed). Section order: tokens, typography, six library sections, surfaces, status, tabs, modal, markdown.
- New `design-language/ui-demo.js` (shared `demo(host, factory, buildFn)`: one `[data-ui-demo]` root, dark and light panes, built twice) and `ui-buttons|fields|choices|feedback|lists|menus-section.js`. Badge demo iterates the existing `App.ui.badge.KINDS` (no `feedback.js` change needed). Menus render closed.
- Removed `buttons-section.js`, `fields-section.js`, the `surfaces` toggle demo and helper, and the `.design-language-button-grid` / `-toggle-sample` / `-toggle-label` CSS; added `.design-language-ui-*` pane CSS in `admin.css`. `index.html`: -2 +7 script tags; cache-busting count 62 to 67; `Makefile` verify-serving file list updated.
- `docs/ui-control-inventory.md` (new, 5-column tables by family; known debt recorded: `.tool-toggle` display:none, both legacy toggles, per-editor copies, `App.confirmDialog`, `buildItemMenu`, squawk 0094).
- Tests: `tests/test_ui_control_inventory.py` (both-direction guard, row classification, tmp_path probe for missing row and stale citation, library-section source rules, demo-call coverage), `tests/browser/test_ui_reference_page.py` (4 tests, Chromium).
- Docs: `agents.md` (living reference/inventory bullet, mandatory "Adding a factory" checklist, component-vocabulary pointer), `CLAUDE.md` Control library pointer. Testid registry unchanged (no testid added).

**Deviation / finding**: the leg's "no test references a design-language data-section" was re-checked by grep: true for design-language (the only `data-section` hits are Studio/Admin `.section-nav-item` ones). No ID registry change. The 4 reference-page browser tests passed first run.

### Flight-close verification (AC8)
| Check | Result | Duration |
|---|---|---|
| `make lint` + `ruff format --check` | clean (471 files formatted) | instant |
| `make test-unit` | 4929 passed, 10 skipped | 11m14s |
| `tests/browser/test_ui_*.py` + `test_deep_violet_computed_styles.py` (`-m browser -rA`, chromium + webkit, no skips) | 254 passed | 1m10s |
| `--lane chat` | 41 passed | 1m39s |
| `--lane studio` | 188 passed, 3 skipped | 8m20s |
| `--lane system` | 124 passed | 3m52s |
| `--lane shared` | 434 passed, 3 skipped (pre-existing `test_flow_picker.py` skips) | 3m06s |
| WebKitGTK 2.52.6 probe, dev instance 8485 + scratch dir, `#admin/design-language`, `--root-selector '[data-ui-demo]'` | dark `ok: true`, light `ok: true`, 150 controls each, `failures: []`, actual_theme matched; instance stopped, scratch/log/pid removed | n/a |

The four historically flaky tests (`test_agent_item_keyboard_select`, `test_editor_renders_prompt_block`, `test_studio_agent_crud_flow`, `test_sandbox_chip_add_remove_marks_form_dirty`) passed in the lane runs; no failure, so no investigation was needed. Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`) are inside `make test-unit` and passed.

### Flight review fixes

- `ui/list-pane.js`: the hidden empty state no longer carries `role="status"`; a persistent, never-hidden `.ui-list-pane-status` polite live region (own sr-only rule in `components.css`, since `.visually-hidden` is only defined in area CSS) is written only on filter-query change ("N results" / "1 result" / emptyText or "No matches" / cleared).
- `components.css`: `@media (forced-colors: active)` block for `.ui-toggle-track`, `.checkbox-primary`, selected list-pane row, menu-item focus.
- Stale `fieldGroup()` comments fixed in `tests/_ui_guard_helpers.py` and `tests/test_ui_guards.py`.
- Item 4 (`menu.js close()` early return) accepted as-is: harmless, no reorder.
- Existing contract tests that located the empty state via `role=status` / bare text updated (heading role). New tests: live-region contract (both engines) and forced-colors contract (chromium only; WebKit skips because Playwright has no forced-colors emulation there).
- Verified: static guards + `tests/test_ui_*.py` (264 pass), browser ui lane + deep-violet (every webkit param ran; 1 intentional skip), `make lint`, `--lane shared`.

### Flight completion

**Date**: 2026-10-01

- **Review outcome**: Reviewer (Sonnet, flight-scoped) and Accessibility Reviewer both
  `[HANDOFF:confirmed]`. A fix round for the non-blocking items (list-pane live region,
  forced-colors block, stale `fieldGroup()` comments; see "Flight review fixes") was
  re-reviewed and confirmed.
- **Final gates** (Leg 6 AC8, plus the fix round): `make lint` and `ruff format --check`
  clean; `make test-unit` 4929 passed, 10 skipped; UI browser tests in chromium + webkit
  254 passed, no skips; lanes chat 41, studio 188 (3 skipped), system 124, shared 434
  (3 skipped); WebKitGTK 2.52.6 probe of the reference page dark and light `ok: true`, 150
  controls each. Fix round: static guards + `tests/test_ui_*.py` 264 passed, browser ui
  lane and deep-violet green (1 intentional webkit skip), `--lane shared` green.
- **Carry-forward to Flight 2**:
  - native `<dialog>` migration of `App.confirmDialog`, with the stale-close-event guard
    (the `close`-event reopen race found in Leg 2);
  - squawk 0082 (`App.router.replaceSub` leaves `currentSub` stale);
  - CI WebKit install (`3.11-bookworm`, `--with-deps webkit`) is unverified until CI runs;
  - published design system update (tokens, Button, Checkbox, Toggle) pending by the
    Flight Director.

## Flight Director Notes

- 2026-09-30: Phase file `.flightops/agent-crews/leg-execution.md` loaded and its
  structure validated (Crew, Interaction Protocol and Prompts present). Flight set to
  `in-flight`. The flight has 5 legs.
- Leg 1 `ui-test-apparatus` designed. **Risk tier: high.** It changes shared test
  infrastructure that existing consumers use: the guard-helper signatures behind every
  registry and sink guard, and the browser conftest that every browser test uses. It also
  changes CI install lines. So a Developer design review runs before implementation.
- Leg 1 landed and reported `[LAND:leg]`. WebKit route 1 works locally (WebKit 26.0 via
  userland deps). So DD9's post-merge gating of Flight 2's first native modal is
  **not needed**: WebKit DD8 checks run locally from Leg 2 on. CI's `3.11-bookworm`
  `--with-deps webkit` install remains unverified until the first CI run, since
  Concourse and Docker are unavailable. The Flight Director will check it after the
  merge if CI is reachable.
- One `--lane shared` flake was seen in Leg 1:
  `test_flow_keyboard.py::test_agent_item_keyboard_select`. It passed alone and on a
  re-run, and is untouched by this flight. Watch for recurrence.
- Leg 2 `control-mechanism-spike` designed. **Risk tier: high.** It is the mechanism
  decision point and creates the shared `App.ui` interface every later flight consumes.
  A Developer design review runs.
- Leg 3 `deep-violet-tokens` was drafted ahead, during Leg 1, and is held at `planning`
  until Leg 2 lands.
- Leg 2 landed and reported `[LAND:leg]`. **Flight Director confirms the mechanism
  decision: factories (DD1 confirmed).** Factories passed all six criteria in Chromium
  145, Playwright WebKit 26.0 and WebKitGTK 2.52.6. The custom element also passed,
  and cleanup was non-differentiating. With no criterion separating them, DD1's
  rationale decides: native elements, ES5, no convention change. The `<dialog>` rule
  (DD8) is verified in both engines and in WebKitGTK for the backdrop.
  - The `close`-event reopen race the spike found is carried to Flight 2 as a required
    property of the real dialog wrapper. It is documented in the `agents.md` Modals
    bullet.
- A second load-sensitive lane flake appeared in Leg 2 (`--lane system`,
  `test_flow_admin_tools_editor.py::test_editor_renders_prompt_block`). It passed alone
  3/3 and on a lane re-run. It is not in this flight's diff. It is the same flake class
  as Leg 1's; the debrief will evaluate whether to log it as a squawk.
- Leg 3 `deep-violet-tokens`: a design review ran in parallel with Leg 2 (read-only).
  **Risk tier: high**, because app-wide tokens and CSS have consumers in every area. The
  review was applied and the leg set to `ready`. Implementation is spawned now.
- Leg 4 `core-controls` design review: "approve with changes". It found three high
  issues, all in the menu (Escape placement, Tab handling, contrast premise). Split
  out: **the menu becomes its own leg, `menu-control` (Leg 5)**. The reference leg
  becomes Leg 6 (`06-living-reference-and-inventory.md`). The flight now has 6 legs;
  `flight.md`'s leg list is updated (adaptive change, while in flight).
  - **Rationale:** the menu's keyboard and outside-click logic, dialog safety and
    cleanup form one risk cluster. Separating it cuts one Developer pass's blast radius.
  - **Corrected contrast premise:** selected-row meta, badges and counts use
    `--fg-secondary`, because `--fg-muted` fails 3 of 4 composites.
  - **Risk tiers:**
    - Leg 4 is **high** (shared CSS and gates edited after Leg 3; reviewed).
    - Leg 5 is **high** (keyboard and dialog interplay; its design is the reviewed
      material from Leg 4's review, with all three high issues resolved, so no second
      review).
    - Leg 6 is **low**: additive to a dev-only page, docs and guards, within the
      established library pattern. It skips leg design review; the flight-end
      Reviewer covers it.
- Leg 3 landed and reported `[LAND:leg]`. All DD6 and DD7 pairs pass with the
  operator's hexes. In the studio lane, 2 failures passed alone:
  `test_flow_agent_crud.py::test_studio_agent_crud_flow` and
  `test_flow_studio_mcp_editor.py::test_sandbox_chip_add_remove_marks_form_dirty`.
  That makes 4 rerun-clean lane failures across Legs 1–3, all in tests outside this
  flight's diff, but Leg 3's CSS touched every area. The **flight-close lane runs in
  Leg 6 are the arbiter**: a recurrence of any of these four there gets investigated,
  not waved through. Leg 4 implementation is spawned now.
- Leg 4 landed and reported `[LAND:leg]`.
  - **Deviation accepted:** a global `.badge`/`.badge--<kind>` vocabulary did not exist;
    only area-scoped badge classes did. The Developer created it on the gated
    `--badge-*` pairs. This was the right call under DD5: the library owns the global
    class.
  - Leg 5 `menu-control` implementation is spawned now.
- Leg 5 landed and reported `[LAND:leg]`. The deviations are recorded in its entry
  (`focusout` relatedTarget handling, the tabindex reset, `force` clicks on
  aria-disabled items, WebKit "Script error."); none goes against an AC. Leg 6
  `living-reference-and-inventory` is set `ready`. It is risk tier low, so the leg design
  review is skipped. It includes the flight-close verification (AC8).
- Leg 6 landed and reported `[LAND:leg]`. The flight-close verification (AC8) is all
  green: unit tier, UI browser tests in both engines, all four lanes, and the WebKitGTK
  probe of the reference page in dark and light. None of the four watched flaky tests
  recurred. **All 6 autonomous legs have landed.**
- **Flight review (Phase 2d):** a Reviewer and an Accessibility Reviewer run in parallel
  over the whole uncommitted diff.
  - **Reviewer tier: Sonnet.** The diff includes `scripts/webkitgtk_probe.py`, which
    reads the local-API credential file and mints a handoff. That is a credential-adjacent
    surface under the crew file's security-sensitive rule.
  - The Accessibility Reviewer is enabled because every leg changed UI.

## Decisions

### Control-library mechanism (Leg 2, 2026-09-30)

**Decision: factories (DD1 confirmed).** Custom elements are not adopted; the throwaway `<ui-list-pane>` and its test code are deleted. Factories passed all six criteria in Chromium and WebKit, so the AC7 divert condition ("factories fail a criterion the custom element passes") did not trigger.

Engines: Chromium 145.0.7632.6, Playwright WebKit 26.0 (userland libraries), WebKitGTK 2.52.6 (system, probe). Evidence is reproducible from `tests/test_ui_mechanism_testids.py` (criterion 1), `tests/browser/test_ui_library_contract.py` and `tests/browser/test_ui_listener_cleanup.py` (2, 3, 6; the CE column ran from a test-only file now deleted), `tests/test_ui_guards.py` (4) and `scripts/webkitgtk_probe.py` (5).

| Criterion | Factory | Custom element (throwaway) |
|---|---|---|
| 1. Test ids registry-visible, no manual exception | pass: literals `agents-pane`, `agents-filter`, `agents-new-btn`; per-item `agents-row-` seen as one parametric family and no literal; `find_testid_value_violations` empty | pass: `data-testid` in an HTML string and `setAttribute` literal both seen; per-item property form identical to the factory; a host attribute computed elsewhere would be invisible, same as the factory's `setAttribute` with a variable |
| 2. Locators: strict `get_by_role` link/button, `fill` on filter, click and Enter, `fill`/`is_disabled` on `button` and `textInput` (`check` n/a until Leg 4) | pass, chromium 145 and webkit 26.0 | pass, chromium and webkit (list-pane locators; `button`/`textInput` are factories either way) |
| 3. Resolver `assert_controls_labelled_and_described` over each mounted variant | pass, both engines (list pane, filter, button, field in hint+error states) | pass, both engines |
| 4. No sinks | pass: `find_ui_dir_sink_tokens` scans 4 files, 0 hits | pass: `find_markdown_html_sink_tokens` on the CE file, 0 hits |
| 5. WebKitGTK 2.52.6 through the probe | pass: dark and light, `ok: true`, count 6 | pass: dark, `ok: true`, count 6 (definition script then mount wrapper) |
| 6. Cleanup: `textContent = ''` wipe, no `destroy()`, zero outstanding document-level listeners, no handler touches a detached node on dispatched keydown/click | pass, both engines: none registered while mounted (live set empty before and after) | pass, both engines: the `/` shortcut IS registered on connect (instrumentation sees `document keydown`), and `disconnectedCallback` removes it on the wipe (live set empty after; 0 detached touches) |

**Criterion 6 is non-differentiating.** Both pass: the custom element via `disconnectedCallback`, the factory by installing no document-level listener at all. This is not a factory win. The negative control (a deliberately leaky mock that registers a `document` keydown and never removes it) is reported by the instrumentation in both engines: one outstanding listener after the wipe and at least one detached-node touch on dispatch. The instrumentation also has its own test for `once`, `signal` and explicit removal.

What actually separates the mechanisms is not in the six: native controls (`fill`/`check`/`select_option`, `HTMLLabelElement.control`) work without a wrapper for factories, custom elements need a `class` in an ES5 codebase and carry upgrade/`connectedCallback` ordering hazards (the CE here needed `configure()` to be called before connect to avoid them), and the factory keeps the existing idiom. Trade-off kept: no declarative markup authoring.


---

## Deviations

---

## Anomalies

---

## Session Notes

- 2026-09-30: Planning probes. `DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`. System
  `python3` has `gi` with WebKit2 4.1 (WebKitGTK 2.52.6); the repo venv has neither `gi`
  nor `pywebview`. Playwright 1.58.0 is installed; `~/.cache/ms-playwright` holds chromium
  and firefox builds but no webkit.
- 2026-09-30: Design review. Architect cycle 1 returned "approve with changes" with 17
  issues: the DD2 regex collision, composite test ids, the WebKit route, the
  skip/require policy, control boundaries, DD6 site lists, listener cleanup, DD8 engine
  gaps, probe environment pinning and smaller items. The spec was revised, Leg 1 was
  split into `ui-test-apparatus` and `control-mechanism-spike`, and DD14 was added
  (list-pane ARIA). Architect cycle 2 also returned "approve with changes" with 10
  refinements, all applied without a third cycle (the methodology caps review at two):
  - Escape `preventDefault` and popup containment
  - `--fg-on-accent-fill` moving with each fill, plus CSS usage pins
  - all three toggle kinds named, with a dedicated `--control-border`
  - route-2 post-merge gating of Flight 2's first native modal
  - the §15 disposition (DD15)
  - testid value enforcement
  - DD4 comment convention
  - userland WebKit gotchas
  - the menu-in-dialog check moved to `core-controls`

  Flight set to `ready`.
