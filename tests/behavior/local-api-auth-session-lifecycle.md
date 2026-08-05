# Behavior Test: Local API Auth — Session Lifecycle

**Slug**: `local-api-auth-session-lifecycle`
**Status**: draft
**Created**: 2026-08-04
**Last Run**: never

## Intent

Verifies that the credential gate holds and that the operator never notices it.
Three properties resist unit testing because each spans a process boundary or a
process lifetime: that a real browser reaches the UI through the one-time
credential handoff and ends with nothing sensitive left in the address bar; that
a session already established survives the server process restarting; and that
rotating the credential actually drops that session rather than merely writing a
new file. Unit tests can assert the middleware's decision for a synthetic
request, but they cannot observe a browser's cookie jar persisting across a
server it does not control, and they cannot distinguish "rotation wrote a new
credential" from "rotation invalidated the old one."

## Preconditions

- A dev instance of the app is runnable on a non-default port. **Never target
  port 8484** — that is the operator's production instance; mutating it would
  both corrupt real state and report its state rather than the branch's.
- The instance uses a scratch data directory, not the operator's real one, so
  rotation does not invalidate the operator's own sessions.
- The credential gate is enforced (this test is meaningless with it off).
- A browser apparatus is available and can reach the dev instance's port.

## Observables Required

- **browser** (rendered page state, address bar contents, whether the app shell
  actually loaded) — measured via the registered browser apparatus
- **http** (response status for credentialed vs uncredentialed requests) —
  measured via shell
- **shell** (server start/stop, rotation command, exit codes) — measured via Bash
- **filesystem** (credential file mode and content) — measured via Read/Bash

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Start the dev instance on the non-default port with a scratch data directory. Wait for it to serve. | (empty — setup) |
| 2 | Read the credential file's permission bits and confirm a credential file exists in the scratch data directory. | The file is readable and writable by its owner only — no group or other access of any kind. |
| 3 | From the shell, request the app root with no credential. Then request the liveness endpoint with no credential. | The root request is refused as unauthenticated. The liveness request succeeds and its body carries no version string and no prompt text. |
| 4 | From the shell, request a static asset path with no credential. | Refused as unauthenticated — asset paths are not an unauthenticated hole. |
| 5 | Navigate the browser to the app root with no credential. | The application does not load. The operator sees a refusal, not a partially-rendered or broken shell. |
| 6 | Navigate the browser to the handoff URL carrying a one-time credential, as the launcher would construct it. Wait for the app to finish loading. | The application loads fully — the main UI is rendered and interactive, not an error page. |
| 7 | (No actions — inspect the browser's current address.) | The address no longer contains the one-time credential; it has been stripped. Nothing credential-shaped remains visible in the URL. |
| 8 | Reload the page without re-supplying any credential. | The application loads again. The established session carried it — the handoff was not a one-request-only success. |
| 9 | Open a **fresh browser context with no cookies** — a new incognito/private context, not the one used above. Navigate it to the same handoff URL, reusing the one-time credential already spent in step 6. | The application does not load; the request is refused as unauthenticated. The one-time credential was consumed on first use and cannot establish a second session. *(The cookie-less context is what makes this judgeable — in the original context a successful load would be explained by the existing session cookie, not by the replay.)* |
| 10 | Stop the server process. Wait for it to exit. Start it again on the same port and scratch data directory. Wait for it to serve. | (empty — setup) |
| 11 | Reload the browser page without re-supplying any credential. | The application loads. The session survived the restart — this is the criterion that a non-persisted credential would fail. |
| 12 | Run the rotation command against the scratch data directory. | The command exits successfully and reports that the credential was replaced. The credential file's content differs from what step 2 observed, and its permission bits are still owner-only. |
| 13 | Reload the browser page without re-supplying any credential. | The application no longer loads — the pre-rotation session has been invalidated. Rotation revoked access rather than merely writing a new file alongside a still-valid old one. |
| 14 | Navigate the browser to a fresh handoff URL built from the post-rotation credential. | The application loads fully. Rotation left the system usable, not bricked. |
| 15 | Stop the dev instance and remove the scratch data directory. | (empty — teardown) |

## Out of Scope

- **The packaged desktop path.** The embedded webview is not this apparatus's
  browser engine, so per-backend cookie persistence and handoff timing are not
  observable here. That is the flight's HAT leg.
- **WebSocket upgrade refusal.** Covered by unit tests at the middleware layer,
  where a synthetic upgrade is cheaper and more precise than driving a real one.
- **Cross-origin refusal.** The Origin allowlist is pre-existing behaviour with
  its own coverage; this test exercises the credential gate.
- **Multi-credential behaviour.** Nothing mints a second credential this flight.

## Variants (optional)

None yet. If the exemption set ever grows beyond the single liveness endpoint,
add a variant asserting each exempt path returns nothing sensitive.
