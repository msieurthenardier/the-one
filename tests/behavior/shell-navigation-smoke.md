# Behavior Test: Shell Navigation Smoke

**Slug**: `shell-navigation-smoke`
**Status**: active
**Created**: 2026-07-03
**Last Run**: 2026-07-06-06-21-43 (pass, 6/6 — F7 mission-end regression smoke; both/auto theme; hash-survival + theme flip/restore green; see runs/)

## Intent

Verify that the app shell's core navigation contract holds against the running instance: all three areas (Chat, Agent Studio, System) render when selected, the theme switcher visibly changes and restores the theme, hash routing survives a reload, and no area renders an error state. This is deliberately data-independent (passes on any database state) and strictly read-only with respect to server data — designed as a re-runnable gate for the M17 UI-redesign mission, where every flight churns markup and this contract must keep holding. A behavior test (not a Playwright test) because it verifies the *operator's live instance* through a real browser apparatus with rendered-state evidence, exactly the surface the redesign changes.

## Preconditions

- The **instance under test** is running and serving (probe: HTTP 200 on `/` immediately before the run). Default `http://127.0.0.1:8485` — a dedicated dev instance with a scratch data directory; the operator's packaged app owns `:8484` and must never be targeted (see CLAUDE.md's "Behavior-test credential convention" safety rule). The orchestrator states the actual base URL at run time and it applies to every step below.
- A browser apparatus (goldfinch MCP) is attached and can open tabs to that origin.
- **Credential**: this instance is gated (Mission 20 Flight 1). Follow CLAUDE.md's
  "Behavior-test credential convention" — read the long-lived credential from the
  instance's data directory and mint a handoff URL for the Step-1 navigation
  (single-use; re-mint if navigating again, e.g. after the Step-7 cold reload if the
  session cookie was lost).
- Existing data is acceptable — every step accepts both populated and empty states explicitly; no seeding is performed by the test.
- Run-tab environment: prefer an unoccluded/foregrounded window; if pixel capture wedges, the printToPDF fallback per the apparatus doctrine (`the_one/agents.md`) is sanctioned evidence.

## Observables Required

- browser (rendered page state, screenshots, DOM/a11y state — measured via goldfinch MCP)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Open a fresh browser tab to the instance under test (base URL per Preconditions). Wait for the app to finish loading. | The app shell renders: a top bar containing the product branding and three area picker buttons labelled "Chat", "Agent Studio", and "System"; a sidebar region; a main content region. No error banners or blank main region. |
| 2 | Record which theme is currently active — BOTH the control's selected option (Light/Dark/Auto; "Auto" may present as no persisted preference) AND the resolved rendering (attribute + representative colors). State the recorded values explicitly in the report; step 5 restores the recorded OPTION (if "Auto", restore Auto — not the resolved mode). | (setup row, no judgment) |
| 3 | Click the "Agent Studio" picker button. | The Studio area becomes active: the "Agent Studio" picker button is marked as the current area; the sidebar shows Studio navigation including "Agents", "Knowledge", and "MCP Servers"; the main region shows either agent tiles or an empty-state canvas inviting creation of the first agent — exactly one of the two, with no error state. |
| 4 | Click the "System" picker button, then open the "General" section if it is not already shown. Locate the appearance/theme control and switch the theme to whichever explicit mode (Light or Dark) is NOT currently active. | The System area becomes active with General settings visible. After the theme click: the page's rendered appearance visibly flips (background/foreground invert family — verify on a screenshot, not just attributes), and the newly selected mode reads as the active/pressed choice in the theme control. No layout breakage or unstyled regions after the flip. |
| 5 | Restore the theme control to the OPTION recorded in step 2, re-citing the recorded values and the step-1 baseline evidence in the report. Report post-restore persisted-preference state. | The rendered appearance returns to its step-1 state (compare against the re-cited step-1 baseline) and the restored option reads as active in the theme control. |
| 6 | Click the "Chat" picker button. | The Chat area becomes active: the sidebar shows either a session history list or a getting-started/empty state — exactly one of the two; the main region shows a message composer (text input and a Send affordance) or a configuration-needed banner if no agents exist; no error banners. |
| 7 | Reload the page directly at the instance-under-test URL with fragment `#admin/providers` — a cold deep-link. | After the reload, the System area's LLM Providers page renders (provider tiles or the empty-state create affordance — exactly one of the two) — hash routing survives a cold load. No error banners. |

## Out of Scope

- CRUD flows (agent/provider create-edit-delete) — covered by Playwright browser tests and the `studio-smoke` behavior spec (which requires seeded fixtures).
- Chat message round-trips and streaming — a dedicated chat behavior spec (M17 Flight 7) covers those with a mock provider.
- Accessibility depth (keyboard operability, ARIA) — covered by per-leg a11y gates.
- Visual regression against baselines — pixel snapshots (local-only) cover that.
