# Behavior Test: Studio agent create / edit / delete (SC7)

**Slug**: `studio-agent-crud`
**Status**: active
**Created**: 2026-07-05
**Updated**: 2026-10-07 (squawk 0127: wording only, no expectation changed: steps 4, 5, 7, 8 and 9); 2026-10-06 (M25 F6 leg 4c: the Agents and Library start pages replace the old empty-state copy in the steps that quote it); 2026-10-02 (M25 F3: list and detail; New → `#agents/~new`, list rows, breadcrumb, no Back)
**Last Run**: 2026-10-28-02-59-04 — pass (18/18; Light + Dark; M31 F6 close sweep, port 8503; row 5 re-author: create toast "Agent created", see runs/)

## Intent

Verify the core Agents-destination CRUD flow end-to-end in the real re-skinned UI: an
operator can create an agent from the Agents list's "New" (`#agents/~new`), land in the General tab, fill its
name / description / provider / model, save it, see it appear in the list beside the editor, re-select it,
edit a field and re-save, then delete it through the General-tab Danger zone's Delete agent
confirmation dialog (tick the acknowledgement, then Delete; sortie 20). This needs a **behavior test** rather than a unit test
because the observable is the rendered Studio surface across a multi-step navigation flow
(list → editor beside the list → list) plus a modal confirmation whose gated Delete is a rendered,
user-perceivable checkpoint — not a
DOM invariant a single-service test can assert. It is the SC7 (behavior-verified core
flows) gate for Flight 05 (Studio Re-skin), and it exercises the re-skinned agent editor
that Legs 1–5 rebuilt onto the v3 vocabulary. Runs in **both themes** (light + dark) so a
theme-coupled render regression in the editor surfaces.

## Preconditions

- the-one is running host-native and reachable on a dedicated dev instance at `http://localhost:{port}` (a dedicated port of 8490 or higher (not 8485, the Flight Director's preview port; never 8484), with a fresh scratch data directory and working directory under `$HOME`; below, `{port}` is that port), with `THE_ONE_DEV_MODE=true` (dev mode makes the `mock` provider type
  *acceptable*; it does not create one). Verify with an active probe:
  `GET http://localhost:{port}/api/providers/types` returns a list that includes
  `{"value":"mock",...}`. If it does not, dev mode is off and the test cannot proceed.
- **A `mock`-type LLM provider exists on the dev instance** (agent creation dead-ends on the disabled
  "No provider — add one in Library" option (literal UI text) — general-tab.js:56 — when none exists). This
  is a **decay-prone fixture** — seed it immediately before the run and remove it after:
  - Seed: `POST http://localhost:{port}/api/providers` with body
    `{"name":"Mock (studio-agent-crud)","type":"mock","base_url":"http://localhost","config":{"models":["mock-default"]}}`
    (expect `201`). Record the returned `id`.
  - Clean up (teardown, always): `DELETE http://localhost:{port}/api/providers/{id}`.
- A browser apparatus is attached to the dev instance (goldfinch MCP preferred — printToPDF for pixel
  evidence, a11y-tree for rendered-state judgment; CDP for focus). Never touch 8484.
- Not mid-edit on any agent; the operator can observe the Studio UI in the browser session.
- **Credential**: this instance is gated (Mission 20 Flight 1). Follow CLAUDE.md's
  "Behavior-test credential convention" — read the long-lived credential from the dev instance's
  data directory, mint a handoff URL for the Step-2 browser navigation (single-use;
  re-mint if navigating again), and attach `Authorization: Bearer <credential>` to the
  `curl` calls in steps 1 and 11.

## Observables Required

- browser (rendered Agents UI: the list column and its rows, editor tab panels, field values, button label
  text, the Delete agent confirmation dialog — measured via goldfinch MCP; a11y-tree +
  screenshot/printToPDF as primary rendered-state evidence, CDP `evaluate`/focus as
  supplementary). Per the frame discipline, verdicts rest on rendered state (what a user
  sees), not on queryable-but-invisible DOM.
- http (provider seed/teardown status codes — measured via curl/Bash; used only for the
  precondition fixture and cleanup, not for step verdicts).

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | (Setup, no judgment) Probe `GET /api/providers/types` includes `mock`; seed the mock provider via `POST /api/providers` (body above) and record its `id`. | (empty) |
| 2 | Defeat client caching (fresh tab / hard reload, ignore cache), navigate to `http://localhost:{port}/`, click the rail's **Agents** link (`#agents`). | The Agents destination renders as a list beside a detail pane. The list column shows a list titled "Agents" with a "New" button (`new-agent-btn`, accessible name "New agent"), plus either agent rows or the line "No agents yet.". The detail pane shows the Agents start page (the description "An agent is an assistant you set up for a kind of work." and a "New agent" button), with the line "Pick an agent from the list to edit it." or "No agents yet." matching the list column. No error banner. |
| 3 | Click the **New** button (`new-agent-btn`). | The hash is `#agents/~new`. The agent editor opens in create mode in the detail pane, beside the list: <ul><li>the **General** tab (`tab-general`) is the selected tab panel;</li><li>its fields (Name, Description, Provider, Model) are visible and empty or default;</li><li>the Create button (`save-agent-btn`) is present and **disabled** (nothing entered yet).</li></ul> |
| 4 | In the General tab, type a distinctive Name (e.g. `Behave CRUD Agent`) and a Description; select the seeded **Mock (studio-agent-crud)** provider from the Provider dropdown; then select a Model (e.g. `mock-default`) from the now-populated Model dropdown. With only the one seeded provider and one model, the form pre-selects both, so the selections confirm the defaults and do not prove the Model list refills on a provider change (seed a second provider to prove that). | The Name and Description fields show the typed text; the Provider dropdown shows the mock provider selected (the disabled "No provider" placeholder is gone); the Model dropdown is enabled and shows the chosen model; the Create/Save button (`save-agent-btn`) is now **enabled**. |
| 5 | Click **Create/Save** (`save-agent-btn`). | The save succeeds (no error flash; a neutral "Agent saved" toast is expected and is not an error). The editor settles into edit mode for the new agent: the button reads "Save" and is disabled again, and there is no "Unsaved changes" text. The hash is `#agents/Behave%20CRUD%20Agent/general` (or the same name with the browser's own encoding of the space). |
| 6 | Observe the **Agents list** (no reload needed). | A row for `Behave CRUD Agent` is present in the list, in A–Z position. It is the only row with `aria-current="page"`, and it is labelled with the agent's name and its model. |
| 7 | Click the breadcrumb link **Agents** in the editor header to close the agent, then click the `Behave CRUD Agent` row to re-open it. On the **General** tab, change a field (for example, edit the Description text), then click **Save** (`save-agent-btn`). | **The breadcrumb** closes the agent to the empty state (hash `#agents`), and the row re-opens it. **While the field is dirty,** the Save button enables and the editor shows "Unsaved changes". **After save,** it disables again, the "Unsaved changes" text clears, no error flash appears (the neutral "Agent saved" toast does), and the edited value persists. The edited value persists in the field. |
| 8 | Scroll to the General-tab **Danger zone**; click **Delete agent** (`delete-agent-btn`) **once**. | [a11y] A modal dialog (`delete-agent-dialog`) titled **Delete "Behave CRUD Agent"?** opens; the button itself is not armed (its label stays "Delete agent"). The message says the agent has no chats ("This deletes the agent. It has no chats. This can't be undone."). The checkbox (`delete-agent-ack-checkbox`) reads "I understand this will delete all of this agent's chat history" and is unticked; **Delete** (`delete-agent-confirm-btn`) is disabled; **Cancel** (`delete-agent-cancel-btn`) has focus. The agent is **not** yet deleted (the dialog is the checkpoint the Validator judges: a single click must NOT destroy the agent). |
| 9 | Tick the checkbox, then click **Delete** in the dialog. | Delete enables once the box is ticked. The DELETE succeeds and the dialog closes. A flash reads "Deleted Behave CRUD Agent." The editor leaves the deleted agent and returns to the Agents root (`#agents`), showing the detail pane's empty state, with no error flash. Focus is on a neighbouring agent row, or on the list's "New" button (`new-agent-btn`; not the start page's own "New agent" button) when no agents remain. Read focus from the DOM; a programmatic focus shows no ring. |
| 10 | Observe the **Agents list** (no reload needed). | No row labelled `Behave CRUD Agent` remains in the list; the agent is gone. |
| 11 | (Teardown, no judgment) `DELETE /api/providers/{id}` for the seeded mock provider; if any test agent remains (partial run), delete it. | (empty) |

**Row conventions:** one row = one logical checkpoint. `[a11y]`-marked expectations are the
assistive-tech / rendered-state surface for the optional Accessibility Validator.
**Locators (apparatus-agnostic — the Executor maps to its MCP):** New
`data-testid="new-agent-btn"` (studio.js); agent rows `data-testid="agent-item"`; the breadcrumb link
`data-testid="editor-breadcrumb-link"`; General tab `data-testid="tab-general"`
(agent-editor.js); Save/Create `data-testid="save-agent-btn"` (agent-editor.js); Delete
`data-testid="delete-agent-btn"` in the General-tab Danger zone (general-tab.js); the
click opens the confirmation dialog `delete-agent-dialog` (`agent-delete-dialog.js`) with `delete-agent-ack-checkbox`, `delete-agent-cancel-btn` and `delete-agent-confirm-btn`. **List freshness:** since Mission 25 Flight 3 the Agents list re-renders from
`App.store` after each mutation, so steps 6 and 10 read it without a reload. If a row looks stale,
the Executor reports it as observed (a stale list is a failure, not something to reload away).

## Out of Scope

- Provider configuration / the Library › Model providers surface — the mock provider is a seeded
  precondition, not under test here (covered by the system/provider browser lane).
- The other agent-editor tabs' content (Knowledge stub, MCPs, Built-in tools) — this flow
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
