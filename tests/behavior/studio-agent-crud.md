# Behavior Test: Studio agent create / edit / delete (SC7)

**Slug**: `studio-agent-crud`
**Status**: active
**Created**: 2026-07-05
**Last Run**: 2026-07-06-06-06-19 (pass — DARK 9/9 full flow; cap-chip quiet non-regression confirmed on studio agent-tiles; F7 re-run; see runs/)

## Intent

Verify the core Agents-destination CRUD flow end-to-end in the real re-skinned UI: an
operator can create an agent from the Agents grid, land in the General tab, fill its
name / description / provider / model, save it, see it appear in the grid, re-select it,
edit a field and re-save, then delete it through the General-tab Danger Zone's two-step
`App.confirmDelete` arm-then-fire. This needs a **behavior test** rather than a unit test
because the observable is the rendered Studio surface across a multi-step navigation flow
(grid → editor tabs → grid) plus a stateful two-click confirm affordance whose armed
intermediate ("Confirm Delete?") state is a rendered, user-perceivable checkpoint — not a
DOM invariant a single-service test can assert. It is the SC7 (behavior-verified core
flows) gate for Flight 05 (Studio Re-skin), and it exercises the re-skinned agent editor
that Legs 1–5 rebuilt onto the v3 vocabulary. Runs in **both themes** (light + dark) so a
theme-coupled render regression in the editor surfaces.

## Preconditions

- the-one is running host-native and reachable on `http://localhost:8485` (the mission dev
  instance), with `THE_ONE_DEV_MODE=true` (dev mode makes the `mock` provider type
  *acceptable*; it does not create one). Verify with an active probe:
  `GET http://localhost:8485/api/providers/types` returns a list that includes
  `{"value":"mock",...}`. If it does not, dev mode is off and the test cannot proceed.
- **A `mock`-type LLM provider exists on 8485** (agent creation dead-ends on the disabled
  "No provider — configure in Admin" option (literal UI text) — general-tab.js:56 — when none exists). This
  is a **decay-prone fixture** — seed it immediately before the run and remove it after:
  - Seed: `POST http://localhost:8485/api/providers` with body
    `{"name":"Mock (studio-agent-crud)","type":"mock","base_url":"http://localhost","config":{"models":["mock-default"]}}`
    (expect `201`). Record the returned `id`.
  - Clean up (teardown, always): `DELETE http://localhost:8485/api/providers/{id}`.
- A browser apparatus is attached to 8485 (goldfinch MCP preferred — printToPDF for pixel
  evidence, a11y-tree for rendered-state judgment; CDP for focus). Never touch 8484.
- Not mid-edit on any agent; the operator can observe the Studio UI in the browser session.
- **Credential**: this instance is gated (Mission 20 Flight 1). Follow CLAUDE.md's
  "Behavior-test credential convention" — read the long-lived credential from 8485's
  data directory, mint a handoff URL for the Step-2 browser navigation (single-use;
  re-mint if navigating again), and attach `Authorization: Bearer <credential>` to the
  `curl` calls in steps 1 and 11.

## Observables Required

- browser (rendered Studio UI: grid tiles, editor tab panels, field values, button label
  text, the armed "Confirm Delete?" state — measured via goldfinch MCP; a11y-tree +
  screenshot/printToPDF as primary rendered-state evidence, CDP `evaluate`/focus as
  supplementary). Per the frame discipline, verdicts rest on rendered state (what a user
  sees), not on queryable-but-invisible DOM.
- http (provider seed/teardown status codes — measured via curl/Bash; used only for the
  precondition fixture and cleanup, not for step verdicts).

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | (Setup, no judgment) Probe `GET /api/providers/types` includes `mock`; seed the mock provider via `POST /api/providers` (body above) and record its `id`. | (empty) |
| 2 | Defeat client caching (fresh tab / hard reload, ignore cache), navigate to `http://localhost:8485/`, click the rail's **Agents** link (`#agents`). | The Agents grid renders — a page header plus either existing agent tiles or the empty-state canvas; no error banner. |
| 3 | Click the **New Agent** button (`new-agent-btn`). | The agent editor opens in create mode: the **General** tab (`tab-general`) is the selected tab panel, its fields (Name, Description, Provider, Model) are visible and empty/default, and the Create button (`save-agent-btn`) is present and **disabled** (nothing entered yet). |
| 4 | In the General tab, type a distinctive Name (e.g. `Behave CRUD Agent`) and a Description; select the seeded **Mock (studio-agent-crud)** provider from the Provider dropdown; then select a Model (e.g. `mock-default`) from the now-populated Model dropdown. | The Name and Description fields show the typed text; the Provider dropdown shows the mock provider selected (the disabled "No provider" placeholder is gone); the Model dropdown is enabled and shows the chosen model; the Create/Save button (`save-agent-btn`) is now **enabled**. |
| 5 | Click **Create/Save** (`save-agent-btn`). | The save succeeds (no error flash). The editor settles into edit mode for the new agent (the button reads "Save" and is disabled again — no unsaved changes). |
| 6 | Return to / observe the **Agents grid** (hard-reload if navigating through a client-cached view). | A tile for `Behave CRUD Agent` is present in the grid — visible, labelled with the agent's name. |
| 7 | Re-select the `Behave CRUD Agent` tile to open its editor; on the **General** tab change a field (e.g. edit the Description text); click **Save** (`save-agent-btn`). | While the field is dirty the Save button enables; after save it disables again (no unsaved changes) and no error flash appears. The edited value persists in the field. |
| 8 | Scroll to the General-tab **Danger Zone**; click **Delete Agent** (`delete-agent-btn`) **once** (arm). | [a11y] The Delete button enters its armed state: its visible label changes to **"Confirm Delete?"** and it takes the armed destructive styling. The agent is **not** yet deleted (this is the intermediate two-step checkpoint the Validator judges — a single click must NOT destroy the agent). |
| 9 | Click the armed **Confirm Delete?** button a second time (within the ~3s revert window) to fire the delete. | The DELETE succeeds; the editor leaves the deleted agent (falls through to the first remaining agent, or the empty editor if none) with no error flash. |
| 10 | Observe the **Agents grid** (hard-reload if the view is client-cached). | No tile labelled `Behave CRUD Agent` remains in the grid — the agent is gone. |
| 11 | (Teardown, no judgment) `DELETE /api/providers/{id}` for the seeded mock provider; if any test agent remains (partial run), delete it. | (empty) |

**Row conventions:** one row = one logical checkpoint. `[a11y]`-marked expectations are the
assistive-tech / rendered-state surface for the optional Accessibility Validator.
**Locators (apparatus-agnostic — the Executor maps to its MCP):** New Agent
`data-testid="new-agent-btn"` (studio.js); General tab `data-testid="tab-general"`
(agent-editor.js); Save/Create `data-testid="save-agent-btn"` (agent-editor.js); Delete
`data-testid="delete-agent-btn"` in the General-tab Danger Zone (general-tab.js); the
two-step arm/fire is `App.confirmDelete` with the `Confirm Delete?` label (studio.js
`handleDeleteEditor`). **Cache discipline:** the grid is a client-rendered SPA view — after
each create/delete mutation, re-observe the grid via a deliberate cache defeat (fresh tab or
hard reload) so a stale in-memory list can't mask the mutation.

## Out of Scope

- Provider configuration / the Settings › LLM Providers surface — the mock provider is a seeded
  precondition, not under test here (covered by the system/provider browser lane).
- The other agent-editor tabs' content (Knowledge stub, MCPs, Built-in Tools) — this flow
  only drives the General tab.
- The save→delete race fallback (concurrent delete during a PUT) — covered deterministically
  by the unit/route-stub test `tests/browser/test_flow_studio_agent_save_race.py`, not this
  wall-clock flow.
- Visual token contrast / composite-a11y — covered by `tests/test_design_tokens_a11y.py`.

## Variants (optional)

- **theme=dark** and **theme=light** — run the full step table once per theme (set the theme
  preference before Step 2, restore the operator's original preference on teardown). Overall
  verdict passes only if the flow passes in **both** themes, so a theme-coupled render
  regression in the re-skinned editor is caught.
