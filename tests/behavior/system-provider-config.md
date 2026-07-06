# Behavior Test: System provider config — create / edit / test / delete (SC7)

**Slug**: `system-provider-config`
**Status**: active
**Created**: 2026-07-05
**Last Run**: 2026-07-06-05-41-42 — pass (20/20; light 10/10, dark 10/10; F7 H1/subtitle re-render confirmed both themes; cap-chip quiet on grid) — [run log](system-provider-config/runs/2026-07-06-05-41-42.md)

## Intent

Verify the core System (Admin) LLM-provider CRUD flow end-to-end in the real re-skinned
admin surface: an operator can create a provider from the LLM Providers grid via the
**full UI create** (not the API seed helper), land in the provider editor, fill its
Name and set Type = **Mock (dev)** — a cred-less type whose create form is name + type
only — save it, see it appear in the grid as a `provider-card`, re-select it, edit a
field and re-save, run **Test Connection**, then delete it through the editor's Danger
Zone via the two-step agent-usage-pre-gated `App.confirmDelete` arm-then-fire. This needs
a **behavior test** rather than a unit test because the observable is the rendered
re-skinned admin surface across a multi-step navigation flow (grid → editor field-groups
→ grid) plus a stateful two-click confirm affordance whose armed intermediate
("Confirm Delete?") state is a rendered, user-perceivable checkpoint — not a DOM invariant
a single-service test can assert. It is the SC7 (behavior-verified core flows) gate for
Flight 06 (System / Admin Re-skin), exercising the provider grid + editor that Legs 1–4
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

## Observables Required

- browser (rendered admin/providers UI: grid `provider-card` tiles + quiet type badge,
  editor `.field-group` fields, field values, button label text, the armed
  "Confirm Delete?" state, the Test-Connection result flash — measured via chrome-devtools;
  a11y-tree + screenshot as primary rendered-state evidence, CDP `evaluate`/focus as
  supplementary). Per the frame discipline, verdicts rest on rendered state (what a user
  sees), not on queryable-but-invisible DOM.
- http (provider-types probe, stale-provider precheck, teardown DELETE status — measured via
  curl/Bash; used only for the precondition/cleanup, not for step verdicts).

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | (Setup, no judgment) Probe `GET /api/providers/types` and confirm it includes `mock`. Open a fresh chrome-devtools page and hard-reload with `ignoreCache` to defeat static-asset cache. If a provider named `Mock (system-provider-config)` already exists (`GET /api/providers`), `DELETE` it. | (empty) |
| 2 | Navigate to `http://localhost:8485/#admin/providers`. | The **LLM Providers** grid renders — the page header "LLM Providers", a **New Provider** button, and either existing `provider-card` tiles or the empty-state canvas; no error banner. |
| 3 | Click **New Provider** (`new-provider-btn`). | The provider editor opens in **create mode**: the **Connection** section shows a stacked **Name** `.field-group` (label above input) and a **Type** `.field-group`; the **Create** button (`save-provider-btn`) is present and **disabled** (nothing entered yet). |
| 4 | Type the Name `Mock (system-provider-config)`; select **Type = "Mock (dev)"**. | The Name field shows the typed text; the Type control shows "Mock (dev)" selected; because `mock` is cred-less, the **Base URL and API Key rows are hidden** — the visible form is Name + Type only; the **Create** button (`save-provider-btn`) is now **enabled**. |
| 5 | Click **Create** (`save-provider-btn`). | The create succeeds (no error flash). The editor settles into **edit mode** for the new provider: the primary button now reads **Save** and is disabled (no unsaved changes), and the **Test** (`test-connection-btn`) and **Delete Provider** (`delete-provider-btn`) buttons are now present. |
| 6 | Observe the **LLM Providers** grid (open it fresh / `ignoreCache` reload if navigating through a client-cached view). | A `provider-card` labelled **`Mock (system-provider-config)`** is present in the grid — visible, with the quiet **mock** type badge (lowercase, no uppercase eyebrow). |
| 7 | Re-select the `Mock (system-provider-config)` card to open its editor; in the **Name** field append distinctive text (e.g. ` — edited`); click **Save** (`save-provider-btn`). | While the Name is dirty the Save button enables; after save it disables again (no unsaved changes) and no error flash appears. The edited name persists in the field. |
| 8 | Click **Test** (`test-connection-btn`). | A connection-test result is surfaced as a flash/status (the mock provider resolves its test deterministically); **no unhandled error banner** appears. |
| 9 | Scroll to the editor's **Danger Zone**; click **Delete Provider** (`delete-provider-btn`) **once** (arm). | [a11y] The Delete button enters its **armed** state: its visible label changes to **"Confirm Delete?"** and it takes the armed destructive styling. The provider is **not** yet deleted (the agent-usage pre-gate passes — no agent uses this fresh provider — then `App.confirmDelete` arms; a single click must NOT destroy the provider). This intermediate two-step state is the judged checkpoint. |
| 10 | Click the armed **Confirm Delete?** button a second time (within the ~3s revert window) to fire the delete. | The DELETE succeeds; the editor leaves the deleted provider (returns to the grid / falls through to the remaining providers) with no error flash. |
| 11 | Observe the **LLM Providers** grid (`ignoreCache` reload if the view is client-cached). | No `provider-card` labelled `Mock (system-provider-config)` remains — the provider is gone. |
| 12 | (Teardown, no judgment) If any `Mock (system-provider-config)` provider remains (partial run), `DELETE /api/providers/{id}`. Restore the operator's original theme preference. | (empty) |

**Row conventions:** one row = one logical checkpoint. `[a11y]`-marked expectations are the
assistive-tech / rendered-state surface for the optional Accessibility Validator.
**Locators (apparatus-agnostic — the Executor maps to its MCP):** New Provider
`data-testid="new-provider-btn"` (providers-grid.js); Create/Save `data-testid="save-provider-btn"`,
Test `data-testid="test-connection-btn"`, Delete `data-testid="delete-provider-btn"` in the
editor Danger Zone (provider-editor.js); grid tile `data-testid="provider-card"`
(providers-grid.js); the two-step arm/fire is `App.confirmDelete` with the `Confirm Delete?`
label (provider-editor.js), gated by an agent-usage pre-fetch (`GET /api/providers/{id}/agents`).
Mock is name+type only because `TYPE_DEFAULTS.mock` sets `showBaseUrl:false, showApiKey:false`
(admin.js). **Cache discipline:** the grid is a client-rendered SPA view — after each
create/delete mutation, re-observe the grid via a deliberate cache defeat (fresh tab or
`ignoreCache` reload) so a stale in-memory list can't mask the mutation.

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
- **Provider consumption by agents** in Agent Studio — covered by `studio-agent-crud`.

## Variants

- **theme=light** and **theme=dark** — run the full step table once per theme (set the theme
  preference before Step 2; restore the operator's original preference on teardown, Step 12).
  Overall verdict passes only if the flow passes in **both** themes, so a theme-coupled render
  regression in the re-skinned provider grid/editor is caught.
