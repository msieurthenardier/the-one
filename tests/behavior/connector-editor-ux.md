# Behavior Test: Connector editor UX (live status · save-warm · typed/subtractive form)

**Slug**: `connector-editor-ux`
**Status**: active
**Created**: 2026-06-03
**Last Run**: 2026-06-03-11-42-48 (pass — 7/7 after the step-6 fold-in fix)

## Intent

Validate the post-batch Discord connector editor UX — the visual/interaction changes from F17 Legs **A** (live connection status, Save-opens-WS, Test→Validate, invite context, discoverable-entities relocation), **B** (intent checkboxes removed), and **C** (Additional Config demoted to a bottom Advanced section). These are UI changes whose correctness is *visual and interactive* — they don't fit unit/DOM-shape tests; an agent must drive the real Studio editor and judge what's rendered. Run after Legs A/B/C land.

## Preconditions

- the-one running and reachable (Studio UI).
- A Discord connector ("Discord Constellation", `58f1fe5a833f`) exists with **≥1 attached agent** (so it warms) and is currently **Connected** (warm gateway).
- Chrome MCP available; not mid-edit on the connector.

## Observables Required

- browser (DOM state / rendered text of the Studio connector editor — measured via chrome-devtools).

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Navigate to Studio → open the "Discord Constellation" connector editor, General tab. | Editor loads. A **single live connection-status indicator** is present on General and reads **Connected** (the connector is warm). The old hardcoded "Not tested" string is **absent**. [a11y] status is text, not color-only. |
| 2 | Edit a connection-relevant field (e.g. toggle a guild-scope/presence option) and click **Save**. | After save, the status shows **Connected** again **without** clicking Test Connection — i.e. save reopened/reconnected the gateway. No manual Test step was needed. |
| 3 | Locate the former "Test Connection" control. | It is presented as an optional **"Validate"** (pre-flight check) — labeled/positioned as validation, **not** as the primary way to connect. |
| 4 | Open the Access-and-Routing / Advanced tab; look for the intents "Receive messages from" checkbox row. | The **3 intent checkboxes are gone** (no operator-facing intent toggles). [Leg B] |
| 5 | Find the "Additional Config" key-value table. | It lives in its **own "Advanced" section at the bottom** of the form, below the typed fields — visually separated, de-emphasized. [Leg C] |
| 6 | Locate the invite link (without having run Test Connection this session). | The invite link **renders** (not blank/needs-test), and its **info-icon/tooltip explains its purpose** — adding the bot to a Discord server at setup. [Leg A] |
| 7 | Locate the discoverable-entities "entries last refreshed" / refresh control. | It appears in its **new location** (near the dropdowns it powers / a data-status area), **relabeled** as entries/data freshness — clearly distinct from the connection status. [Leg A] |
| 8 | *(Optional — requires a stub.)* With a Playwright `page.route()` stub making `GET /api/connectors/{id}/status` return `{state:"error", last_error:"…PrivilegedIntentsRequired…", last_error_link:"https://discord.com/developers/applications"}`, reload the editor. | The live status (`connector-live-status`) shows **Error**; `connector-live-status-error` carries the actionable message; `connector-live-status-error-link` links to the Developer-Portal "Privileged Gateway Intents" page. |

**Row conventions:** one row = one checkpoint. **Locators:** the live status uses `data-testid="connector-live-status"` (+ `-error`/`-error-link` for step 8), added by Leg A; the Validate button keeps `connector-test-connection-btn`; intents `discord-intent-*`; Additional Config `discord-additional-config-row`; invite `connector-invite-*`. Step 8 is optional — a `PrivilegedIntentsRequired` failure is **not live-drivable** via Chrome MCP (needs a real IDENTIFY rejection); it requires the route-stub above, else skip (the backend unit tests cover the mapping).

## Out of Scope

- The unknown-DM → approve → respond flow — see `discord-approval-flow`.
- Backend correctness of save-warm / status / error-mapping (covered by Leg A/B unit + browser tests); this test is the *visual* acceptance layer.
