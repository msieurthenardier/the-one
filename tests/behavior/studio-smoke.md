# Behavior Test: Studio Smoke

**Slug**: `studio-smoke`
**Status**: archived
**Created**: 2026-05-26
**Last Run**: never
**Updated**: 2026-10-02 (M25 F3 surface rename; not re-run)

> **Archived (2026-07-05, Flight 05 Studio Re-skin, Leg 06).** Superseded by
> [`studio-agent-crud`](./studio-agent-crud.md) as the SC7 studio behavior gate. This
> draft was never run and is stale in every apparatus dimension: it targets the retired
> port `8484` (the mission dev instance is now `8485`), the retired goldfinch-only
> apparatus assumptions, and the gone "Discord Constellation" connector fixture. Retiring
> it loses no regression coverage — `studio-agent-crud` covers a real create/edit/delete
> flow. The connector account editor Steps 2–3 exercise no longer exists (Mission 23
> Connector Reset removed the old connector-editor UI). Kept for history; not deleted.

## Intent

Smoke test for the Studio web UI. Verifies that the application loads, that core navigation works, and that an operator can reach the connector account editor for the Discord connector. Intentionally minimal — used to validate the behavior-test methodology and apparatus discovery before running larger HATs.

## Preconditions

- the-one is running host-native on `http://127.0.0.1:8484` (verified by an active probe: the operator opens the URL in the browser and sees the Studio render).
- Operator has the goldfinch MCP browser session attached to that URL.

## Observables Required

- browser (DOM and rendered text in the Studio UI, measured via goldfinch MCP)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Open the application at `http://localhost:8484/`. | The page renders fully — not blank, no error banner. A top-level navigation is visible containing entries for the major app areas (exact labels and number may vary). |
| 2 | From the top-level navigation, open the Agent Studio area, then navigate to Connector Accounts. | The list view renders and shows at least one connector account tile labelled "Discord Constellation" with a visible "DISCORD" type indicator. |
| 3 | Open the Discord Constellation connector account editor. | The editor opens with the account's name visible in a header. Multiple editor tabs are visible (the test does not assert exact tab labels — only that an editor with tabs has loaded). |

> **M25 F3:** Step 2's "connector account tile" is not renamed. Connectors are now rows in
> the Library list's Connectors group (`connector-card`, `#library/connectors`), but the
> Connector Accounts surface and its account editor this archived spec walks were already
> removed (Mission 23 Connector Reset; see the archive note), so there is no current
> equivalent to map the step onto. Left for the Flight Director.

## Out of Scope

- Toggle interactions, save behaviour, and routing rules for the connector account editor
  in Steps 2–3 — that editor no longer exists (Mission 23 Connector Reset); this note is
  kept for historical context only.
- Login / authentication — Studio currently has none.
- Performance, accessibility audits — separate concerns.

## Variants (optional)

None.
