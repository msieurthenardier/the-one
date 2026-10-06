# Behavior Test: Studio agent create / edit / delete (SC7)

**Slug**: `studio-agent-crud`
**Status**: active
**Created**: 2026-07-05
**Updated**: 2026-10-02 (M25 F3: list and detail; New → `#agents/~new`, list rows, breadcrumb, no Back)
**Last Run**: 2026-10-02-12-46-53 (pass — LIGHT 9/9 + DARK 9/9; M25 F3 close gate, list-and-detail shell; see runs/)

## Intent

Verify the core Agents-destination CRUD flow end-to-end in the real re-skinned UI: an
operator can create an agent from the Agents list's "New" (`#agents/~new`), land in the General tab, fill its
name / description / provider / model, save it, see it appear in the list beside the editor, re-select it,
edit a field and re-save, then delete it through the General-tab Danger Zone's two-step
`App.confirmDelete` arm-then-fire. This needs a **behavior test** rather than a unit test
because the observable is the rendered Studio surface across a multi-step navigation flow
(list → editor beside the list → list) plus a stateful two-click confirm affordance whose armed
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

- browser (rendered Agents UI: the list column and its rows, editor tab panels, field values, button label
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
| 2 | Defeat client caching (fresh tab / hard reload, ignore cache), navigate to `http://localhost:8485/`, click the rail's **Agents** link (`#agents`). | The Agents destination renders as a list beside a detail pane. The list column shows a list titled "Agents" with a "New" button (`new-agent-btn`, accessible name "New agent"), plus either agent rows or the line "No agents yet.". The detail pane shows the matching empty state ("Select an agent to edit it, or create a new one.", or "No agents yet. Create one to get started."). No error banner. |
| 3 | Click the **New** button (`new-agent-btn`). | The hash is `#agents/~new`. The agent editor opens in create mode in the detail pane, beside the list: <ul><li>the **General** tab (`tab-general`) is the selected tab panel;</li><li>its fields (Name, Description, Provider, Model) are visible and empty or default;</li><li>the Create button (`save-agent-btn`) is present and **disabled** (nothing entered yet).</li></ul> |
| 4 | In the General tab, type a distinctive Name (e.g. `Behave CRUD Agent`) and a Description; select the seeded **Mock (studio-agent-crud)** provider from the Provider dropdown; then select a Model (e.g. `mock-default`) from the now-populated Model dropdown. | The Name and Description fields show the typed text; the Provider dropdown shows the mock provider selected (the disabled "No provider" placeholder is gone); the Model dropdown is enabled and shows the chosen model; the Create/Save button (`save-agent-btn`) is now **enabled**. |
| 5 | Click **Create/Save** (`save-agent-btn`). | The save succeeds (no error flash). The editor settles into edit mode for the new agent: the button reads "Save" and is disabled again, and there is no "Unsaved changes" text. The hash is `#agents/Behave%20CRUD%20Agent/general` (or the same name with the browser's own encoding of the space). |
| 6 | Observe the **Agents list** (no reload needed). | A row for `Behave CRUD Agent` is present in the list, in A–Z position. It is the only row with `aria-current="page"`, and it is labelled with the agent's name and its model. |
| 7 | Click the breadcrumb link **Agents** in the editor header to close the agent, then click the `Behave CRUD Agent` row to re-open it. On the **General** tab, change a field (for example, edit the Description text), then click **Save** (`save-agent-btn`). | **The breadcrumb** closes the agent to the empty state (hash `#agents`), and the row re-opens it. **While the field is dirty,** the Save button enables and the editor shows "Unsaved changes". **After save,** it disables again, the "Unsaved changes" text clears, and no error flash appears. The edited value persists in the field. |
| 8 | Scroll to the General-tab **Danger Zone**; click **Delete Agent** (`delete-agent-btn`) **once** (arm). | [a11y] The Delete button enters its armed state: its visible label changes to **"Confirm Delete?"** and it takes the armed destructive styling. The agent is **not** yet deleted (this is the intermediate two-step checkpoint the Validator judges — a single click must NOT destroy the agent). |
| 9 | Click the armed **Confirm Delete?** button a second time (within the ~3s revert window) to fire the delete. | The DELETE succeeds. The editor leaves the deleted agent and returns to the Agents root (`#agents`), showing the detail pane's empty state, with no error flash. Focus is on a neighbouring agent row, or on "New" when no agents remain. |
| 10 | Observe the **Agents list** (no reload needed). | No row labelled `Behave CRUD Agent` remains in the list; the agent is gone. |
| 11 | (Teardown, no judgment) `DELETE /api/providers/{id}` for the seeded mock provider; if any test agent remains (partial run), delete it. | (empty) |

**Row conventions:** one row = one logical checkpoint. `[a11y]`-marked expectations are the
assistive-tech / rendered-state surface for the optional Accessibility Validator.
**Locators (apparatus-agnostic — the Executor maps to its MCP):** New
`data-testid="new-agent-btn"` (studio.js); agent rows `data-testid="agent-item"`; the breadcrumb link
`data-testid="editor-breadcrumb-link"`; General tab `data-testid="tab-general"`
(agent-editor.js); Save/Create `data-testid="save-agent-btn"` (agent-editor.js); Delete
`data-testid="delete-agent-btn"` in the General-tab Danger Zone (general-tab.js); the
two-step arm/fire is `App.confirmDelete` with the `Confirm Delete?` label (studio.js
`handleDeleteEditor`). **List freshness:** since Mission 25 Flight 3 the Agents list re-renders from
`App.store` after each mutation, so steps 6 and 10 read it without a reload. If a row looks stale,
the Executor reports it as observed (a stale list is a failure, not something to reload away).

## Out of Scope

- Provider configuration / the Settings › Providers surface — the mock provider is a seeded
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
