# Behavior Test: Agent Retention Setting Round-Trip

**Slug**: `agent-retention-setting-roundtrip`
**Status**: draft
**Created**: 2026-06-05
**Last Run**: never

## Intent

Verifies that the per-agent chat-history retention setting works end-to-end through the
Studio web UI: the input renders in the General-tab Behavior section above Max Iterations, a
non-default value persists across save and a full reload, and an out-of-range value is
rejected with a visible validation error rather than silently accepted or clamped. This is a
real-environment flow (rendered DOM placement, the save→reload round-trip through the API and
SQLite, and the UI's surfacing of a server-side 422) that unit and API tests cannot observe
together — unit tests cover the validator and migration in isolation; only a live UI run
confirms the operator actually sees the setting where the mission specifies and that a bad
value is refused at the surface they interact with.

## Preconditions

- the-one container is running on `http://localhost:8484`, built from the Flight-1 branch
  (`make rebuild` after the Flight-1 edits — the image is baked, so source edits are not live
  until a rebuild). Verified by an active probe: the operator opens the URL and sees Studio
  render.
- At least one agent exists (the dev `mock` provider suffices). The test uses whichever agent
  the operator points it at; the agent's name is supplied at run time.
- Operator has the Chrome MCP browser session attached to that URL.

## Observables Required

- browser (DOM placement, input values, and the rendered validation-error text in the Studio
  editor — measured via chrome-devtools MCP)
- http (PUT `/api/agents/{name}` response status for the authoritative reject check — measured
  via curl through Bash)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Open `http://localhost:8484/`, navigate to Agent Studio, and open an existing agent's editor on the General tab. | The General tab renders. A "Behavior" section is visible containing a chat-history retention input (a number field) **positioned above** the Max Iterations input. The retention input shows an integer value within 1–365 (a freshly-migrated agent shows `30`). |
| 2 | In the retention input, replace the value with `90`. Click Save. | A success indication appears (e.g. a "Saved" flash); no validation error is shown. |
| 3 | Reload the page (full browser reload) and re-open the **same** agent's General tab. | The retention input shows `90` — the value survived the save and a fresh load from the server, confirming it persisted to storage (not just the in-memory form). Max Iterations is unchanged from its prior value. |
| 4 | In the retention input, set the value to `400` (above the 365 maximum). Click Save. | The save is **rejected**: a validation error is surfaced in the editor (the error text references the retention field / an out-of-range condition). The agent is **not** updated to 400 — neither silently accepted nor clamped to 365. |
| 5 | Reload the page and re-open the same agent's General tab. | The retention input still shows `90` (the last valid saved value), confirming the rejected `400` was never persisted. |
| 6 | Via shell, issue a direct `curl -s -o /dev/null -w "%{http_code}" -X PUT http://localhost:8484/api/agents/{name} -H 'Content-Type: application/json' -d '{...config with chat_history_retention_days: 400...}'` (full config body; reuse the GET `/api/agents/{name}` payload with the field overridden). | The response status is `422` — the server authoritatively rejects the out-of-range value at the API layer, independent of the UI. |

**Notes:**
- Step 6 is the authoritative HTTP-layer assertion for the reject; steps 4–5 confirm the UI
  surfaces and honors that rejection. Keep both — the UI path and the API path are distinct
  observables of the same criterion.
- The agent name is a run-time input (no agent name is hard-coded in this spec).

## Out of Scope

- Purge behavior (manual "Purge now" and the daily automated sweep) — those are verified by
  Mission 13 Flights 2 and 3 and their own behavior tests.
- The lower-bound reject at the API layer beyond a spot check (0 / below-1) — covered by
  Python unit tests (`test_config.py`); this spec spot-checks the upper bound through the UI.
- Retention UX polish (label wording, help text, default-value feel) — Mission 13 Flight 4
  (Alignment).
- Accessibility audit of the new input — separate concern.

## Variants (optional)

- **Lower-bound reject**: repeat steps 4–6 with `0` instead of `400`; expect the same UI
  rejection and a `422` from the API. (This is UI-observable only because the General-tab form
  collection preserves the raw value rather than coercing a falsy `0` to the default — see the
  flight's frontend design decision. If that decision is ever reverted to a `|| default` idiom,
  a typed `0` would be silently coerced to 30 client-side and this variant must become
  HTTP-only via step 6.)
