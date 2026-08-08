# Leg: enforce-gate

**Status**: landed
**Flight**: [Authenticated Local API End-to-End](../flight.md)

## Objective

Register the credential gate on the real application, flipping enforcement live
for the first time — a small, sharp change made against a harness that is
already fully credentialed.

## Context

This is the flight's hinge, and it is deliberately tiny. `harness-credential-
plumbing` moved every test-harness caller onto the `Authorization` header while
the gate was still unregistered, so the whole migration is already proven green.
What remains is one `add_middleware` call, one inverted test, and whatever
residual breakage the plumbing leg did not anticipate.

The flight spec designated `enforce-and-migrate-harness` as "the only leg
permitted to go red mid-flight." That permission now lives here — but the red
window should be near-zero, and a *large* one is a signal that the plumbing leg
missed a caller category rather than that this leg is hard.

Design decision implemented: **DD4** — the gate registers last so it wraps the
Origin allowlist, giving 401-before-origin and 403 for valid-credential-wrong-
origin.

## Inputs

- `the_one/interfaces/web/app.py` — the `add_middleware(OriginAllowlistMiddleware, ...)`
  call, which the gate must be registered **after** (Starlette inserts at index
  0, so last-added is outermost).
- `tests/test_credential_gate.py::test_gate_middleware_is_not_registered_on_the_real_app`
  — Leg 2's deliberate guard against premature registration.
- A green, fully credentialed harness from `harness-credential-plumbing`.

## Pre-Flip Harness Fix — a Leg 3 residual, folded in here

A pre-flip audit found a structural gap that `harness-credential-plumbing`
could not have closed with the strategy it chose, and that would have turned
this leg's "near-zero red window" into most of the browser suite going red.

**A native browser `WebSocket` cannot send an `Authorization` header.**
`the_one/interfaces/web/static/js/areas/chat.js` opens the chat socket with a
bare `new WebSocket(proto + '://' + location.host + '/ws')` — a WHATWG API
restriction, not a bug. The gate's WebSocket path accepts a session **cookie**
or a header and deliberately offers no query-parameter channel (LD1 scopes that
to document requests). Playwright's `set_extra_http_headers` does not apply to
the WS upgrade in Chromium either, so the header channel cannot reach it even in
principle.

Leg 3 authenticated every browser navigation with a header and **never
established a session cookie** — `grep -rn handoff tests/browser/` returns
nothing. Chat is the default area, so essentially every browser test triggers a
WS upgrade that would be refused the moment the gate is live.

**Production is unaffected and was always correct**: the launcher navigates to a
handoff URL, the gate sets the session cookie on the redirect, and the
same-origin WS handshake carries that cookie for free. It is only the *test*
harness that took a shortcut the real path does not take.

**The fix therefore improves fidelity rather than working around anything**: the
browser fixtures must perform the handoff exchange — mint via the endpoint using
the header credential, then `GET /?<handoff>` — so a cookie is established
exactly as it is in production. Keep the header as well; it costs nothing and
covers non-document fetches.

- [ ] Browser fixtures establish a session cookie via the handoff exchange, once
      per app instance, in addition to the existing header.
- [ ] A regression test asserts a **cookie-only** WebSocket connection succeeds
      against the **real** app. Today that combination is exercised only against
      the throwaway app in `tests/test_credential_gate.py`, which is why the gap
      survived Leg 3's own acceptance test — that test asserts the header matches
      on the *document* request and never opens a socket.

## Acceptance Criteria

- [ ] The gate is registered on `app` **after** `OriginAllowlistMiddleware`,
      with a comment recording why the order matters — the existing Origin
      registration carries such a comment and is the model.
- [ ] `test_gate_middleware_is_not_registered_on_the_real_app` is **inverted and
      renamed** to assert the gate is present and outermost. Renamed, not
      deleted and re-added, so `git blame` records the intent shift rather than
      showing a test that vanished and a different one that appeared.
- [ ] An uncredentialed request to the **real** `app` is refused 401 — asserted
      against the real application, not a throwaway one. This is the first point
      in the flight where that assertion is possible and it is the mission's
      central claim.
- [ ] An uncredentialed **WebSocket upgrade** to the real app is refused before
      accept.
- [ ] An uncredentialed request to a **`/static`** path on the real app is
      refused (DD6).
- [ ] `/api/live` remains reachable with no credential on the real app, and it
      is the only path that is.
- [ ] `make test-unit` green.
- [ ] Browser lanes green.
- [ ] No test disables, stubs, monkeypatches away, or otherwise bypasses the
      gate in order to pass. The mission criterion is "with authentication
      enforced, not disabled or bypassed." A test making an uncredentialed
      request must be *asserting the refusal*.

## Verification Steps

- `make test-unit`
- Browser lanes per the Makefile's `test-browser` target. **Never `-m live`** —
  it targets the operator's production instance on the default port.
- `git diff the_one/interfaces/web/app.py` to confirm registration order.

## Implementation Guidance

1. **Register, then run the full suite immediately**, before fixing anything.
   The first failure list is the leg's real scope and is worth recording in the
   flight log verbatim — it is direct evidence of whether the plumbing leg was
   complete.
2. **Resist fixing failures by weakening the gate.** If a caller cannot work
   authenticated, that is a finding about the gate's design and belongs in the
   flight log.
3. **If the failure list is large**, stop and report rather than grinding. A
   large list means a caller category was missed upstream, and the fix probably
   belongs in the plumbing leg's shape rather than in patches here.

## Edge Cases

- **Module-import-time `TestClient(app)` construction** — the credential may not
  exist at collection time.
- **Tests asserting on `/api/info`'s body** — credentialed now.
- **`tests/test_index_asset_cache_busting.py`** — fetches the index and parses
  asset URLs; named because it sits exactly on the DD6 boundary and is easy to
  miss.

## Files Affected

- `the_one/interfaces/web/app.py` — one registration.
- `tests/test_credential_gate.py` — the inverted, renamed test plus the new
  real-app assertions.
- Whatever residual test files the switch reveals.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md

> Commit is deferred to the flight-end review gate. Do **not** commit and do
> **not** signal `[COMPLETE:leg]`.
