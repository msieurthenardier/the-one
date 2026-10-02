# Behavior Test: System provider config — create / edit / test / delete (SC7)

**Slug**: `system-provider-config`
**Status**: active
**Created**: 2026-07-05
**Updated**: 2026-10-02 (M25 F3: Providers table, items open below it, breadcrumb, no Back)
**Last Run**: 2026-10-02-12-46-53 (pass — LIGHT 10/10 + DARK 10/10, D10 judged on a recorded rerun; M25 F3 close gate; see runs/)

> **Apparatus note (from run 2026-07-30)**: for the row-9 armed state (or any sub-3s transient UI state), single-shot screenshot round-trips lose the race to the revert window. Use the **filmstrip technique**: `performance_start_trace` with screenshots enabled → drive arm(+fire) in ONE `evaluate_script` call (no inter-call gaps) → `performance_stop_trace` → extract the embedded Screenshot frame from the repaint burst as the rendered-state evidence. Proven in both themes.

## Intent

Verify the core Settings › Providers CRUD flow end-to-end in the real re-skinned
Settings surface: an operator can create a provider from the Providers page's "Add provider" via the
**full UI create** (not the API seed helper), land in the provider editor, fill its
Name and set Type = **Mock (dev)** — a cred-less type whose create form is name + type
only — save it, see it appear as a row in the Providers table (its name link is the `provider-card`), re-select it, edit a
field and re-save, run **Test Connection**, then delete it through the editor's Danger
Zone via the two-step agent-usage-pre-gated `App.confirmDelete` arm-then-fire. This needs
a **behavior test** rather than a unit test because the observable is the rendered
re-skinned admin surface across a multi-step navigation flow (table → editor field-groups below the table
→ table) plus a stateful two-click confirm affordance whose armed intermediate
("Confirm Delete?") state is a rendered, user-perceivable checkpoint — not a DOM invariant
a single-service test can assert. It is the SC7 (behavior-verified core flows) gate for
Flight 06 (System / Admin Re-skin), exercising the provider table + editor (the grid until Mission 25 Flight 3) that Legs 1–4
rebuilt onto the v3 quiet vocabulary (`.field-group` label-association, quieted badges,
`.btn-*`). Runs in **both themes** (light + dark) so a theme-coupled render regression in
the editor surfaces.

## Preconditions

- the-one is running host-native and reachable on `http://localhost:8485` (the mission dev
  instance), with `THE_ONE_DEV_MODE=true`. Dev mode is what makes the `mock` provider type
  *available* in the create dropdown (the backend rejects mock creates with HTTP 400 when
  dev mode is off). Verify with an **active probe** (decay-prone precondition):
  `GET http://localhost:8485/api/providers/types` returns a list that includes
  `{"value":"mock", ...}`. If it does not, dev mode is off and the test cannot proceed.
- **No pre-seeded provider is required** — the mock provider under test is *created through
  the UI* by this flow and deleted by it. To keep the run deterministic, use a distinctive
  name (`Mock (system-provider-config)`); if a prior partial run left a provider by that
  name, delete it before Step 2 (`GET /api/providers` → find by name → `DELETE
  /api/providers/{id}`).
- A **chrome-devtools** browser apparatus is attached to 8485 — used because this is a
  multi-step create-and-drive flow that needs a fresh page with an `ignoreCache` reload
  after each mutation (goldfinch wedges on this flow and cannot force an ignore-cache
  reload). Screenshots + a11y snapshots are the primary rendered-state evidence; CDP
  `evaluate`/focus is supplementary. **Never touch 8484.**
- Not mid-edit on any provider. Record the operator's theme preference before Step 2 and
  restore it on teardown (theme is per-origin `localStorage`, shared across tabs).
- **Credential**: this instance is gated (Mission 20 Flight 1). Follow CLAUDE.md's
  "Behavior-test credential convention" — read the long-lived credential from 8485's
  data directory, mint a handoff URL for the Step-2 browser navigation (single-use;
  re-mint if navigating again), and attach `Authorization: Bearer <credential>` to the
  `curl` calls.

## Observables Required

- browser (rendered Settings › Providers UI (`#settings/providers`): the table's `provider-card` name links + quiet type badge,
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
| 2 | Navigate to `http://localhost:8485/#settings/providers` (Settings in the rail, then "Providers" in the Settings nav). | The **Providers** page renders with the page header `h1` "Providers" and an **Add provider** button (`new-provider-btn`). Below it there is either a table of providers (columns Name, Type, Used by; each name a link with testid `provider-card`), or the empty state "No providers yet." (`providers-empty`). No error banner, and no provider editor open. |
| 3 | Click **Add provider** (`new-provider-btn`). | The hash is `#settings/providers/~new`. The provider editor opens in **create mode** **below the table or empty state** (the page still shows it above), with the breadcrumb "Settings / Providers": <ul><li>the **Connection** section shows a stacked **Name** `.field-group` (label above input) and a **Type** `.field-group`;</li><li>the **Create** button (`save-provider-btn`) is present and **disabled** (nothing entered yet).</li></ul> |
| 4 | Type the Name `Mock (system-provider-config)`; select **Type = "Mock (dev)"**. | The Name field shows the typed text; the Type control shows "Mock (dev)" selected; because `mock` is cred-less, the **Base URL and API Key rows are hidden** — the visible form is Name + Type only; the **Create** button (`save-provider-btn`) is now **enabled**. |
| 5 | Click **Create** (`save-provider-btn`). | The create succeeds (no error flash). The editor settles into **edit mode** for the new provider: the primary button now reads **Save** and is disabled (no unsaved changes), and the **Test** (`test-connection-btn`) and **Delete Provider** (`delete-provider-btn`) buttons are now present. |
| 6 | Observe the **Providers** table (no reload needed). | A row for **`Mock (system-provider-config)`** is present in the table, in A–Z position: its name link (`provider-card`), the type `mock` shown as the quiet lowercase type badge (no uppercase eyebrow), and "Used by" reading "0 agents". The row is marked current (`aria-current="page"` on its link), and the editor stays open below the table. |
| 7 | Click the breadcrumb link **Providers** to close the item, then click the `Mock (system-provider-config)` name link in the table to re-open it. In the **Name** field append distinctive text (for example ` — edited`), then click **Save** (`save-provider-btn`). | **The breadcrumb** closes the editor (hash `#settings/providers`, nothing below the table), and the name link re-opens it below the table. **While the Name is dirty,** the Save button enables and the editor shows "Unsaved changes". **After save,** it disables again, the text clears, and no error flash appears. The edited name persists in the field, and the table row shows the edited name. |
| 8 | Click **Test** (`test-connection-btn`). | A connection-test result is surfaced as a flash/status (the mock provider resolves its test deterministically); **no unhandled error banner** appears. |
| 9 | Scroll to the editor's **Danger Zone**; click **Delete Provider** (`delete-provider-btn`) **once** (arm). | [a11y] The Delete button enters its **armed** state: its visible label changes to **"Confirm Delete?"** and it takes the armed destructive styling. The provider is **not** yet deleted (the agent-usage pre-gate passes — no agent uses this fresh provider — then `App.confirmDelete` arms; a single click must NOT destroy the provider). This intermediate two-step state is the judged checkpoint. |
| 10 | Click the armed **Confirm Delete?** button a second time (within the ~3s revert window) to fire the delete. | The DELETE succeeds. The editor closes and the hash returns to `#settings/providers`, with nothing below the table or empty state, and no error flash. Focus is on a neighbouring provider name link, or on **Add provider** when no providers remain. |
| 11 | Observe the **Providers** table (no reload needed). | No row whose name starts with `Mock (system-provider-config)` remains (step 7 renamed it with a ` — edited` suffix). The provider is gone. |
| 12 | (Teardown, no judgment) If any provider whose name starts with `Mock (system-provider-config)` remains (partial run; step 7 renames it), `DELETE /api/providers/{id}`. Restore the operator's original theme preference. | (empty) |

**Row conventions:** one row = one logical checkpoint. `[a11y]`-marked expectations are the
assistive-tech / rendered-state surface for the optional Accessibility Validator.
**Locators (apparatus-agnostic — the Executor maps to its MCP):** Add provider
`data-testid="new-provider-btn"` (providers-table.js); Create/Save `data-testid="save-provider-btn"`,
Test `data-testid="test-connection-btn"`, Delete `data-testid="delete-provider-btn"` in the
editor Danger Zone (provider-editor.js); table name link `data-testid="provider-card"`
(providers-table.js); the breadcrumb link `data-testid="editor-breadcrumb-link"`; the two-step arm/fire is `App.confirmDelete` with the `Confirm Delete?`
label (provider-editor.js), gated by an agent-usage pre-fetch (`GET /api/providers/{id}/agents`).
Mock is name+type only because `TYPE_DEFAULTS.mock` sets `showBaseUrl:false, showApiKey:false`
(admin.js). **List freshness:** since Mission 25 Flight 3 the table re-renders from `App.store`
after each mutation, so steps 6 and 11 read it without a reload. A stale table is a failure to
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
  regression in the provider table/editor is caught.
