# Behavior Test: System provider config — create / edit / test / delete (SC7)

**Slug**: `system-provider-config`
**Status**: active
**Created**: 2026-07-05
**Updated**: 2026-10-11 (sortie 02 leg 2: re-authored for Library, providers left Settings; not re-run); 2026-10-07 (squawk 0127: wording only, no expectation changed: steps 2, 5, 6, 7, 8, 9, 10 and the Last Run line, from the Flight 6 close Validators); 2026-10-05 (M25 F3 leg 7: Providers as tiles, matching Built-in tools, by the operator's decision at the Flight 3 checkpoint; items open below the list, breadcrumb, no Back)
**Last Run**: 2026-10-07-11-51-23 (pass — LIGHT 10/10 + DARK 10/10; M25 F6 mission close; the wording drift recorded in that run log is fixed by squawk 0127; see runs/)

> **Apparatus note (from run 2026-07-30)**: for the row-9 armed state (or any sub-3s transient UI state), single-shot screenshot round-trips lose the race to the revert window. Use the **filmstrip technique**: `performance_start_trace` with screenshots enabled → drive arm(+fire) in ONE `evaluate_script` call (no inter-call gaps) → `performance_stop_trace` → extract the embedded Screenshot frame from the repaint burst as the rendered-state evidence. Proven in both themes.

## Intent

Verify the core Library › Model providers CRUD flow end-to-end in the real
Library surface (providers left Settings in sortie 02): an operator can create a provider from the Library list's Add menu ("Model provider") via the
**full UI create** (not the API seed helper), land in the provider editor, fill its
Name and set Type = **Mock (dev)** — a cred-less type whose create form is name + type
only — save it, see it appear as a row in Library's Model providers group (its name link is the `provider-card`), re-select it, edit a
field and re-save, run **Test Connection**, then delete it through the editor's Danger
Zone via the two-step agent-usage-pre-gated `App.ui.confirm` arm-then-fire. This needs
a **behavior test** rather than a unit test because the observable is the rendered
Library surface across a multi-step navigation flow (list rows → editor field-groups beside the list
→ list rows) plus a stateful two-click confirm affordance whose armed intermediate
("Confirm Delete?") state is a rendered, user-perceivable checkpoint — not a DOM invariant
a single-service test can assert. It is the SC7 (behavior-verified core flows) gate for
Flight 06 (System / Admin Re-skin), exercising the provider list + editor (Library rows since sortie 02; Settings tiles/table before) that Legs 1–4
rebuilt onto the v3 quiet vocabulary (`.field-group` label-association, quieted badges,
`.btn-*`). Runs in **both themes** (light + dark) so a theme-coupled render regression in
the editor surfaces.

## Preconditions

- the-one is running host-native and reachable on `http://localhost:{PORT}` (a dedicated dev instance on a dedicated non-default
  port, 8486 or higher, assigned per run; never 8484 or 8485), with `THE_ONE_DEV_MODE=true`. Dev mode is what makes the `mock` provider type
  *available* in the create dropdown (the backend rejects mock creates with HTTP 400 when
  dev mode is off). Verify with an **active probe** (decay-prone precondition):
  `GET http://localhost:{PORT}/api/providers/types` returns a list that includes
  `{"value":"mock", ...}`. If it does not, dev mode is off and the test cannot proceed.
- **No pre-seeded provider is required** — the mock provider under test is *created through
  the UI* by this flow and deleted by it. To keep the run deterministic, use a distinctive
  name (`Mock (system-provider-config)`); if a prior partial run left a provider by that
  name, delete it before Step 2 (`GET /api/providers` → find by name → `DELETE
  /api/providers/{id}`).
- A **chrome-devtools** browser apparatus is attached to `{PORT}` — used because this is a
  multi-step create-and-drive flow that needs a fresh page with an `ignoreCache` reload
  after each mutation (goldfinch wedges on this flow and cannot force an ignore-cache
  reload). Screenshots + a11y snapshots are the primary rendered-state evidence; CDP
  `evaluate`/focus is supplementary. **Never touch 8484 or 8485.**
- Not mid-edit on any provider. Record the operator's theme preference before Step 2 and
  restore it on teardown (theme is per-origin `localStorage`, shared across tabs).
- **Credential**: this instance is gated (Mission 20 Flight 1). Follow CLAUDE.md's
  "Behavior-test credential convention" — read the long-lived credential from the `{PORT}` instance's
  data directory, mint a handoff URL for the Step-2 browser navigation (single-use;
  re-mint if navigating again), and attach `Authorization: Bearer <credential>` to the
  `curl` calls.

## Observables Required

- browser (rendered Library › Model providers UI (`#library/providers`): the list rows' `provider-card` name links + quiet type badge,
  editor `.field-group` fields, field values, button label text, the armed
  "Confirm Delete?" state, the Test-Connection result flash — measured via chrome-devtools or any CDP-driven Chromium with real input and ignore-cache reloads (e.g. Playwright `connect_over_cdp` + `Page.reload {ignoreCache:true}`);
  a11y-tree + screenshot as primary rendered-state evidence, CDP `evaluate`/focus as
  supplementary). Per the frame discipline, verdicts rest on rendered state (what a user
  sees), not on queryable-but-invisible DOM.
- http (provider-types probe, stale-provider precheck, teardown DELETE status — measured via
  curl/Bash; used only for the precondition/cleanup, not for step verdicts).

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | (Setup, no judgment) Probe `GET /api/providers/types` and confirm it includes `mock`. Open a fresh chrome-devtools page and hard-reload with `ignoreCache` to defeat static-asset cache. If a provider named `Mock (system-provider-config)` already exists (`GET /api/providers`), `DELETE` it. | (empty) |
| 2 | Navigate to `http://localhost:{PORT}/#library` (Library in the rail). | The Library list is showing, with **Model providers** as its first group (one `provider-card` row per provider in A–Z order: the name, a quiet lowercase type badge and its usage value, for example "0 agents"; or the group's empty line when there are none) and an **Add** menu (`library-add-btn`) in the list header. The Library start page shows in the detail pane. No error banner, and no provider editor open. |
| 3 | Open the Add menu (`library-add-btn`) and choose **Model provider** (`library-add-provider`). | The hash is `#library/providers/~new`. The provider editor opens in **create mode** in the detail pane beside the list, with the breadcrumb "Library / Model providers" ("Library" a link) and the one `h1` as the editor title: <ul><li>the **Connection** section shows a stacked **Name** `.field-group` (label above input) and a **Type** `.field-group`;</li><li>the **Create** button (`save-provider-btn`) is present and **disabled** (nothing entered yet).</li></ul> |
| 4 | Type the Name `Mock (system-provider-config)`; select **Type = "Mock (dev)"**. | The Name field shows the typed text; the Type control shows "Mock (dev)" selected; because `mock` is cred-less, the **Base URL and API Key rows are hidden** — the visible form is Name + Type only; the **Create** button (`save-provider-btn`) is now **enabled**. |
| 5 | Click **Create** (`save-provider-btn`). | The create succeeds: a "Provider created" toast appears and no error flash. The editor settles into **edit mode** for the new provider: the primary button now reads **Save** and is disabled (no unsaved changes), and the **Test** (`test-connection-btn`) and **Delete provider** (`delete-provider-btn`) buttons are now present. The new row is in the Model providers group, and the editor's model list is headed "Available models" with its line of help (`provider-models-help`), "Each of your Agents chooses one of these in its Model section.", the word Agents being the link. |
| 6 | Observe the **Model providers** group (no reload needed). | A row for **`Mock (system-provider-config)`** is present, in A–Z position: its name link (`provider-card`), the type `mock` shown as the quiet lowercase type badge (no uppercase eyebrow), and its usage value reading "0 agents". The row is marked current (`aria-current="page"` on it alone). The editor stays open beside the list. |
| 7 | Click the breadcrumb link **Library** to close the item, then click the `Mock (system-provider-config)` row's name link to re-open it. In the **Name** field append distinctive text (for example ` — edited`), then click **Save** (`save-provider-btn`). | **The breadcrumb** closes the editor (hash `#library`, the start page shows), and the name link re-opens it beside the list. **While the Name is dirty,** the Save button enables and the editor shows "Unsaved changes". **After save,** it disables again, the "Unsaved changes" caption clears, a "Provider saved" toast appears, no error flash appears, and keyboard focus returns to the editor title (a DOM read; a programmatic focus shows no ring). The edited name persists in the field, and its row shows the edited name. |
| 8 | Click **Test** (`test-connection-btn`). | A connection-test result is surfaced twice: a toast (for example "Connection successful") and an inline result line in the editor (`.test-result`) (the mock provider resolves its test deterministically); **no unhandled error banner** appears. |
| 9 | Scroll to the editor's **Danger Zone**; click **Delete provider** (`delete-provider-btn`) **once** (arm). | [a11y] The Delete button enters its **armed** state: its visible label changes to **"Confirm Delete?"** and it takes the armed destructive styling. The provider is **not** yet deleted (the agent-usage pre-gate passes — no agent uses this fresh provider — then `App.ui.confirm` arms; a single click must NOT destroy the provider). This intermediate two-step state is the judged checkpoint. Let the armed look settle for about 0.6 s before capturing it. If the ~3s revert window lapses before the capture, the button reverts: arm again (click once more) and capture again. |
| 10 | Click the armed **Confirm Delete?** button a second time (within the ~3s revert window; if it has lapsed back to "Delete provider", arm again first) to fire the delete. | The DELETE succeeds and a "Provider deleted" toast appears. The editor closes and the hash returns to `#library`, and no error flash appears. Focus is on a neighbouring provider row, or at the start of the Model providers group when no providers remain (read focus from the DOM; a programmatic focus shows no ring). |
| 11 | Observe the **Model providers** group (no reload needed). | No row whose name starts with `Mock (system-provider-config)` remains (step 7 renamed it with a ` — edited` suffix). The provider is gone. |
| 12 | (Teardown, no judgment) If any provider whose name starts with `Mock (system-provider-config)` remains (partial run; step 7 renames it), `DELETE /api/providers/{id}`. Restore the operator's original theme preference. | (empty) |

**Row conventions:** one row = one logical checkpoint. `[a11y]`-marked expectations are the
assistive-tech / rendered-state surface for the optional Accessibility Validator.
**Locators (apparatus-agnostic — the Executor maps to its MCP):** Add menu `library-add-btn`, then `library-add-provider`; Create/Save `data-testid="save-provider-btn"`,
Test `data-testid="test-connection-btn"`, Delete `data-testid="delete-provider-btn"` in the
editor Danger Zone (provider-editor.js); row name link `data-testid="provider-card"`
(providers-section.js); the breadcrumb link `data-testid="editor-breadcrumb-link"`; the two-step arm/fire is `App.ui.confirm` with the `Confirm Delete?`
label (provider-editor.js), gated by an agent-usage pre-fetch (`GET /api/providers/{id}/agents`).
Mock is name+type only because `TYPE_DEFAULTS.mock` sets `showBaseUrl:false, showApiKey:false`
(providers-section.js). **List freshness:** since Mission 25 Flight 3 the rows re-render from `App.store`
after each mutation, so steps 6 and 11 read them without a reload. A stale list is a failure to
report, not something to reload away.

## Out of Scope

- The Ollama **models panel** (Refresh / Pull / capability chips) — that surface only renders
  for `ollama`-type providers, not the cred-less mock; not exercised here.
- **Design-token contrast / composite-a11y** — the `.cap-chip-no-tools` and
  `.editor-error-banner` danger-on-soft-fill pairs are gated deterministically by
  `tests/test_design_tokens_a11y.py`, not this wall-clock flow.
- The provider-delete **agent-usage hard-block** ("Used by: …" banner + 3s disable) — this
  flow uses a fresh, unused provider so the pre-gate passes; the hard-block path is a
  separate case.
- The `__MASKED__` **API-key sentinel** preservation on edit — mock is cred-less (no API
  key); the sentinel contract is covered by provider unit/route tests.
- **Provider consumption by agents** on the Agents destination — covered by `studio-agent-crud`.

## Variants

- **theme=light** and **theme=dark** — run the full step table once per theme (set the theme
  preference before Step 2; restore the operator's original preference on teardown, Step 12).
  Overall verdict passes only if the flow passes in **both** themes, so a theme-coupled render
  regression in the provider rows/editor is caught.
