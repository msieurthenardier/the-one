# Leg: uat-and-alignment

**Status**: landed
**Flight**: [Authenticated Local API End-to-End](../flight.md)
**Type**: Human acceptance test — interactive, operator-driven. No autonomous agents.

## Objective

Confirm on the **real packaged desktop path** that the operator reaches the UI
through the normal launch with no credential handling, that an open session
survives a server restart, and that rotation drops it.

## Why this leg exists

Every other verification in this flight runs against Chromium via Playwright or
against ASGI in-process. Neither is the thing that ships. The pinned webview is
**not** the browser lane's Chromium, so per-backend cookie persistence and
handoff timing are only observable to a human running the real app.

It matters more than originally planned. The flight-end review found that the
launcher never performed the handoff at all — `shell.py` built a bare
`http://host:port/` URL and `mint_handoff_credential()` was never called, so
`the-one app` would have shown a 401 instead of the UI. That defect is fixed,
but **the fix is unit-verified only**: the tests assert a handoff token appears
in the URL passed to `create_window`. Nobody has watched a window open, consume
the token, and render. This leg is that observation.

## Preconditions

- [x] `pywebview` importable and `_webview_available()` returns `True`.
      Verified absent at leg start — the `gui` extra needs system cairo/GTK dev
      headers on this machine. Without it the launcher silently takes the
      `webbrowser.open()` fallback, which is a **different code path** and does
      not satisfy this leg's objective.
- [x] A dedicated dev instance on a **non-default port** with a **scratch data
      directory**. This is the flight's last outstanding prerequisite.
- [x] The operator's production instance on `:8484` is **not** the target.
      Confirmed running at leg start (answers `/api/live` with 404, i.e. old
      pre-auth code). Nothing in this leg may point at it.

## Acceptance Criteria

Each is an observation the operator makes, not a command that self-asserts.

- [x] **Launch** — `the-one app` against the dev instance opens a window showing
      the actual UI, not a 401 or an error page.
- [x] **No credential handling** — the operator never sees, copies, or types a
      credential to get in.
- [x] **Address bar clean** — no credential remains visible in the URL after
      load. (In the webview there may be no address bar; then confirm via the
      server's request log that the post-redirect URL carries no token.)
- [x] **The app works** — chat area loads and the WebSocket connects. This is
      the real test of LD3/LD6: a native `WebSocket` cannot send a header, so a
      working socket proves the session cookie was genuinely established.
- [x] **Restart survival** — restart the server process with the window still
      open; the UI recovers without the operator relaunching or re-authenticating.
- [x] **Rotation drops it** — run the rotate subcommand against the dev data
      directory; the open session stops working.
- [x] **Relaunch after rotation** — `the-one app` again works, with the new
      credential, without manual intervention.

## Protocol

Flight Director presents **one step at a time**, waits for the operator's
observation, then proceeds. Failures are diagnosed and fixed inline before
moving on; a look-and-feel fix rides the inline protocol, anything that adds
behaviour is promoted to a scoped design review first, and any change spanning
more than one surface gets a lightweight review pass before implementation.

## Out of Scope

- Windows packaging and the frozen build — covered by CI's packaged-smoke.
- The browser-fallback (`webbrowser.open()`) path, unless the operator elects
  to test it instead; if so, record the webview path as unverified.

---

## Post-Completion Checklist

- [x] All acceptance criteria observed
- [x] Update flight-log.md with the HAT outcome
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
