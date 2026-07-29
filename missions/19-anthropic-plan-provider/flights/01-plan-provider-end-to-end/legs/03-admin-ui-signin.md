# Leg: admin-ui-signin

**Status**: completed
**Flight**: [Anthropic Plan Provider End-to-End](../flight.md)

## Objective

Make the `anthropic-plan` provider fully operable from Administration: the type appears in the picker, the editor offers the save-gated sign-in flow (popup + copyable URL + code paste), connected / re-authenticate / reset states render from `oauth_active` and the `/test` status, badges and tokens pass all design guards, and the browser suite covers the new UI including a seeded revoked-token re-auth affordance.

## Context

- **DD-1/DD-7 (flight)**: frontend `window.open` popup mirroring the MCP server editor precedent, **plus** the authorize URL rendered as copyable text (popup-blocked fallback AND the path the browser-MCP apparatus uses at HAT). Sign-in affordance disabled until the provider row is saved (endpoints are `/api/providers/{id}/...`). The MCP editor abandoned `postMessage` for polling due to COOP — we need neither: the code returns by paste, not redirect.
- **Leg 2 handoff — exact API surface** (all verified landed, uncommitted):
  - `POST /api/providers/{id}/oauth/start` → 200 `{"authorize_url": "..."}`; 404 unknown, 409 non-plan; repeated start replaces the pending window.
  - `POST /api/providers/{id}/oauth/code` `{"code": "..."}` (bare or `code#state`) → 200 masked provider `oauth_active: true`; 422 empty, 409 no pending flow, 400 state-mismatch/failed exchange (actionable detail), 404 deleted row.
  - `DELETE /api/providers/{id}/oauth` → 200 masked provider `oauth_active: false`; local disconnect only.
  - `POST /api/providers/{id}/test` → always HTTP 200, `status`: `"ok" | "error" | "reauth_required"` (+ actionable detail).
  - `GET /api/providers/{id}/models` → live or static fallback, always non-empty for this type, never signals re-auth.
  - `oauth_active` on every provider response = both tokens stored.
- **Deferred here from Leg 1**: `/providers/types` hardcoded literal list (`api.py`, locate `list_provider_types`) + its pinned tests (`tests/test_provider_api.py` ~2024-2043, incl. a `len == 6` dev-mode assertion → 7).
- **Conventions that have bitten before**: seed-before-overlay for partial-field saves (`agents.md` — payload must seed `Object.assign({}, provider.config)` before overlaying edited fields); config-touching admin legs must ship with `tests/browser/test_flow_provider_editor.py` green (M16 F09, broke 3×); design-token changes must satisfy the mirror-sync and contrast guards.
- `TYPE_DEFAULTS` **must** carry non-empty `base_url: "https://api.anthropic.com"` — the editor force-submits `defaults.base_url` when the field is hidden, the model requires it, and `anthropic-plan` is NOT URL-validation-skipped. `showApiKey: false` for this type (mission criterion: no API key is ever entered).

## Inputs

- Legs 1–2 landed (uncommitted): full backend surface above.
- Frontend sites (anchors from pre-flight exploration; verify by symbol, lines have drifted):
  - `the_one/interfaces/web/static/js/areas/admin.js` — `TYPE_DEFAULTS` map (~:182).
  - `.../js/areas/admin/providers-grid.js` — `KNOWN_BADGE_TYPES` (~:21).
  - `.../js/areas/admin/provider-editor.js` — type-conditional fields (~:620), save-payload seed (~:595), base_url force-submit (~:581), reasoning-capable type list (~:227).
  - `.../js/areas/studio/mcp-server-editor.js` — OAuth UX precedent: consent `window.open` (~:1708), polling-not-postMessage rationale (~:1717-1730), `oauth_active` gating, reset-connection control.
  - `.../js/areas/admin/design-language/status-section.js` — badge swatch gallery (~:25-31).
  - `.../css/tokens.css` — badge fill/ink tokens in BOTH theme blocks; `.../css/admin.css` — `.admin-provider-badge--{type}` modifiers (~:165-171).
  - `tests/browser/design_tokens.py` (Python mirror; lockstep-guarded by `tests/test_ui_guards.py::test_design_token_mirror_in_sync`); `tests/test_design_tokens_a11y.py` `_BADGE_INK_PAIRS` (~:639-650).
  - `.../js/areas/studio/general-tab.js` + `.../js/areas/studio.js` capability chips (~:1827) — provider/model pickers and thinking-capable type lists.
  - `docs/ui-testid-registry.md` — testid registry.
- Frontend is vanilla ES5-style JS, no framework, no build step; ordered `<script>` tags in `static/index.html` (new files must be registered there if any are added).

## Outputs

- `/providers/types` gains the `anthropic-plan` entry (label: "Anthropic (Plan)") + pinned tests updated to 7.
- `TYPE_DEFAULTS['anthropic-plan']`: `base_url: "https://api.anthropic.com"`, `showBaseUrl: false`, `showApiKey: false`, thinking/reasoning surface matching the `anthropic` type (`showThinkingEnabled` etc.) so extended-thinking parity is reachable from Studio.
- Provider editor plan-type section: sign-in affordance (disabled + hint until row saved), on click → `POST /oauth/start` → open popup via `window.open` AND render the returned `authorize_url` as copyable text → show code-paste field + confirm; on confirm → `POST /oauth/code`, success → connected state (connected indicator + "Re-authenticate" + "Reset connection" controls; sign-in affordance replaced); errors render the endpoint's actionable detail. Reset → `DELETE /oauth` → back to sign-in state. Re-authenticate → same start/paste flow over the connected state. `/test` result rendering handles `"reauth_required"` distinctly (actionable message). No unsaved-changes trap after connect (server persisted the tokens; editor state must reconcile).
- `anthropic-plan` joins the reasoning-capable type lists (provider-editor + studio capability chips) wherever `anthropic` appears.
- Badges: `KNOWN_BADGE_TYPES`, `admin.css` modifier, `tokens.css` fill+ink in both theme blocks, `design_tokens.py` mirror, `_BADGE_INK_PAIRS` a11y parametrization, status-section swatch — palette choice passing the contrast guard.
- Testid registry entries for every new interactive element; CLAUDE.md LLM-layer one-line note (flight docs checklist).
- Browser tests: plan-provider editor flow (create → save-gated affordance → start → paste field + copyable URL visible; connected-state rendering from a **seeded token fixture**; **route-stubbed** `/test` → distinct reauth message; reset returns to sign-in state). **Network boundary + fixture mechanics (design-review resolved)**:
  - Browser tests never call the real token endpoint; the code-exchange path stays unit-tested.
  - **Connected state** uses REAL seeded encrypted secrets so `oauth_active` derivation is exercised end-to-end: create the provider via API, then UPDATE the `secrets` column via direct sqlite3 against `data_dir/the-one.db`, encrypting the blob with the app subprocess's `data_dir/encryption.key` (fixture precedent: `app_with_data_dir` in `tests/browser/test_flow_chat_session_list_source_badge.py:69`; blob helpers in `db/repositories.py`; key auto-generated at startup, so seed after startup — fixture ordering already guarantees this). There is NO repository-handle pattern in `tests/browser/seeders.py` (API-only) — do not look for one.
  - **Reauth message** cannot come from a seeded fixture (deciding "revoked" requires a refresh attempt against the hardcoded `TOKEN_URL` — offline it's a network error → `"error"`, online it hits Anthropic). Use Playwright `page.route()` to intercept `POST /api/providers/{id}/test` and fulfill `{"status": "reauth_required", "detail": ...}` — the exact in-repo pattern marked "referenceable for L3" at `tests/browser/test_mcp_test_connection_button.py:216-221` (canonical: `test_connector_test_connection_button.py`).
  - **Affordance semantics (resolved)**: the connected state's "Re-authenticate" control IS the standing re-auth affordance (present whenever `oauth_active: true`); the *distinct revoked message* appears only as the rendered `/test` result. No separate persistent "revoked overlay" state exists or is required.

## Acceptance Criteria

- [x] `/providers/types` includes `anthropic-plan` labeled "Anthropic (Plan)" (parenthetical precedent: "Mock (dev)"); BOTH pinned count tests updated: `test_returns_5_types_when_dev_mode_off` set-equality 5 → 6 (`anthropic-plan` is not dev-gated) and `test_returns_6_types_when_dev_mode_on` 6 → 7 (test class at `tests/test_provider_api.py:2022-2060`). *(Tests renamed to `..._6_types_when_dev_mode_off` / `..._7_types_when_dev_mode_on`; +1 label-pin test.)*
- [x] Creating a provider of type "Anthropic (Plan)" in the editor shows: no API-key input, no base-url input (default submitted invisibly, saves validate), and a sign-in affordance that is disabled with a hint until the row is saved and enabled after.
- [x] Clicking sign-in calls `/oauth/start`, opens the popup, AND renders the same URL as copyable text; the paste field + confirm control appear. Popup-blocked case degrades to the copyable URL without error. *(Also: explicit "Open sign-in page" button restores gesture context per the Implementation Guidance option.)*
- [x] Submitting a pasted code calls `/oauth/code`; on success the editor shows the connected state (indicator + Re-authenticate + Reset) with no unsaved-changes warning; on 400/409/422 the endpoint's detail renders as an actionable inline error and the paste field remains usable.
- [x] Reset calls `DELETE /oauth` and returns the editor to the sign-in state (`oauth_active: false` respected after reload too). Re-authenticate runs the start/paste flow without first resetting (existing tokens survive until the new exchange succeeds).
- [x] Connected state (real seeded encrypted secrets, `oauth_active: true` derived end-to-end) renders the Re-authenticate control (the standing re-auth affordance); a route-stubbed `/test` returning `"reauth_required"` renders its message via an EXPLICIT branch, distinct from the generic-error branch (current rendering at `provider-editor.js:446-495` has ok/warning/else-fail only — reauth must not fall into else-fail).
- [x] Thinking/reasoning surface — closed checklist (there is NO studio type list to edit; `anthropic` appears nowhere in studio JS; the `provider-editor.js:227` "reasoning-capable" text is a prose comment, and the actual mechanism is `TYPE_DEFAULTS` flags): (a) `TYPE_DEFAULTS['anthropic-plan']` carries the same `showThinkingEnabled`/`showReasoningEffort` flags as `anthropic` (`admin.js:186`) — this alone delivers the editor's thinking rows; (b) the prose comment at `provider-editor.js:227` is updated; (c) functional Studio assertion only: an agent can select the provider and its model list populates (fallback path acceptable) — no studio.js/general-tab.js code edits.
- [x] Badge lands across ALL token sites — the closed "everywhere anthropic appears" set: `admin.js:186` (TYPE_DEFAULTS), `providers-grid.js:21`, `status-section.js:28`, `tokens.css` lines ~129/149/260/280 (fill+ink × both theme blocks), `admin.css:168`, `tests/browser/design_tokens.py` **both theme dicts** (light ~:97-120, dark ~:183+ — the mirror-sync guard at `test_ui_guards.py:346` fails on a missing half), `_BADGE_INK_PAIRS` (`test_design_tokens_a11y.py:638-650`). Naming per the multi-hyphen precedent (`openai-compatible`): `admin-provider-badge--anthropic-plan`, `--badge-anthropic-plan`/`--badge-ink-anthropic-plan`, Python key `badge_anthropic_plan`. Both guard tests green. *(Palette: fill `#cc785c`, ink `#101114` — 5.76:1 both themes.)*
- [x] Seed-before-overlay honored in any new save-payload code path (no sibling `config.*` key loss — pinned by an editor save test if a new partial-save path is introduced). *(No new save-payload path introduced — the sign-in section is entirely outside `collectFormData`.)*
- [x] Every new interactive element has a `data-testid` registered in `docs/ui-testid-registry.md`; CLAUDE.md LLM-layer note added.
- [x] `make test-browser` green including `test_flow_provider_editor.py` and the new plan-provider flow tests; `make test-unit` ≥ 4148 passed / 0 failed; `make lint` + `make format-check` clean. *(Browser: 585/0/6. Unit: 4133/0/10 — the "≥ 4148" threshold inherited a Leg-2 misreport; full reconciliation in the flight log Anomalies shows no test lost and every itemized leg addition present.)*

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_provider_api.py tests/test_design_tokens_a11y.py tests/test_ui_guards.py -x --timeout 30` for the API/guard loop.
- `THE_ONE_DEV_MODE=true make test-browser` for the browser suite (Playwright).
- `make test-unit` at leg end; `make lint`; `make format-check`.

## Implementation Guidance

1. **Backend sliver first**: `/providers/types` entry + pinned-test updates (isolated, unblocks the picker).
2. **TYPE_DEFAULTS + editor conditional fields**: mirror the `anthropic` entry's thinking/reasoning surface; hide base-url/api-key; wire the force-submitted default base_url.
3. **Sign-in section**: follow the MCP server editor's structure (state machine: signed-out → awaiting-code → connected; the `/test` result is the only revoked signal — no persistent revoked state). Poll nothing — state advances on explicit user actions and endpoint responses. Reuse existing editor CSS/components; no new script files unless necessary (register in index.html if so). **No-trap rule**: sign-in section inputs (especially the code-paste field) must carry NO `data-field` attribute — the dirty snapshot selects `[data-field]` (`provider-editor.js:253-265`), so that single rule keeps them out of the dirty machinery; after `/oauth/code` success, refresh the local provider reference from the returned masked provider (mirror the isEdit save path ~:415-431) without touching the snapshot. **Popup gesture note**: `window.open` fires after the `/oauth/start` fetch resolves, which loses user-gesture context and will often be popup-blocked (documented in `mcp-server-editor.js:1650-1660`, `:1925-1930`) — this degradation is EXPECTED and acceptable because the copyable URL is first-class; optionally adopt the MCP editor's explicit post-fetch "Open sign-in page" button to restore gesture context.
4. **Badges + tokens**: pick a palette passing `_BADGE_INK_PAIRS` contrast math in both themes; update css tokens (both blocks), Python mirror, a11y parametrization, admin.css, grid, swatch in one pass, then run the two guard tests.
5. **Browser tests**: extend `tests/browser/` following existing provider-editor flows; seed token/revoked fixtures via the harness's repository handle. Respect the network boundary (no real token-endpoint calls).
6. **Docs**: testid registry + CLAUDE.md note.
7. **Leg-end**: flight log entry, status `landed`, no commit, signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Popup blocked**: no JS error; copyable URL is the visible path.
- **Paste of full `code#state`, bare code, or padded whitespace**: all accepted (backend normalizes; UI passes through untrimmed is fine but trimming is harmless).
- **Exchange fails after popup closed**: paste field remains; error is inline, not a toast that vanishes.
- **Provider deleted in another tab mid-flow**: `/oauth/code` 404 renders actionably.
- **Editor reload mid-flow (start called, code not yet pasted)**: pending window survives server-side; re-clicking sign-in restarts cleanly (backend replaces pending).
- **Legacy `anthropic` providers**: editor unchanged for them; `oauth_active: false` present in their responses must not render any plan UI.
- **Sign-in with a dirty form**: allowed — safe server-side (PUT pins managed keys from the stored row, so a later Save can't clobber tokens); do not require a clean form before sign-in.
- **Type switched away from `anthropic-plan` mid-create**: the plan section hides via the existing is-hidden toggle pattern (`provider-editor.js:314-332`); assert in a test.

## Files Affected

- `the_one/interfaces/web/api.py` — `/providers/types` entry
- `the_one/interfaces/web/static/js/areas/admin.js`, `admin/provider-editor.js`, `admin/providers-grid.js`, `admin/design-language/status-section.js`
- `the_one/interfaces/web/static/js/areas/studio.js`, `studio/general-tab.js` (thinking-capable lists only, if enumerated there)
- `the_one/interfaces/web/static/css/tokens.css`, `css/admin.css`
- `tests/browser/design_tokens.py`, `tests/test_design_tokens_a11y.py`, `tests/test_provider_api.py`, `tests/browser/` flow tests
- `docs/ui-testid-registry.md`, `CLAUDE.md`

## Citation Audit

2026-07-28 (Flight Director, post-design-review): backend endpoint surface verified in the uncommitted tree by the design reviewer (`/oauth/start` api.py:4167, `/oauth/code` :4188, `DELETE /oauth` :4264, `/test` statuses :4336-4357, `list_provider_types` :3990-4011). Frontend anchors verified exact: `TYPE_DEFAULTS` admin.js:182 (anthropic entry :186), `KNOWN_BADGE_TYPES` providers-grid.js:21, base_url force-submit provider-editor.js:581, save-payload seed :604-613 (NOT ~595), field rendering ~:115-250 with show/hide toggle :314-332, save-time config overlay region ~:620s (openrouter ~:621, num_ctx ~:648, thinking ~:665) — both regions matter; dirty snapshot :253-265; `/test` rendering :446-495; `window.open` mcp-server-editor.js:1708, COOP rationale :1714-1730, gesture-loss notes :1650-1660/:1925-1930; status-section :25-31 (anthropic :28); admin.css:168; `_BADGE_INK_PAIRS` test_design_tokens_a11y.py:638-650; pinned type-count tests test_provider_api.py:2022-2060; mirror-sync guard test_ui_guards.py:346.

---

## Post-Completion Checklist

**Batched-commit mode: do NOT commit at leg end.**

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit` 4133/0/10, `make test-browser` 585/0/6), lint + format clean
- [x] Flight log Leg Progress entry written
- [x] Leg status set to `landed` (this file's header)
- [x] Signal `[HANDOFF:review-needed]` — review and commit happen at flight end
