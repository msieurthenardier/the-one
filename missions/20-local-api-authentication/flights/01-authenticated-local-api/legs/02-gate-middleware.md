# Leg: gate-middleware

**Status**: landed
**Flight**: [Authenticated Local API End-to-End](../flight.md)

## Objective

Build the credential gate — an ASGI middleware enforcing an identified caller
across every HTTP method, the WebSocket upgrade, and the static mount, with a
single liveness exemption and the one-time browser-handoff exchange — and prove
it against a throwaway app, **without registering it on the real application**.

## Context

Design decisions from the flight this leg implements: **DD3** (ASGI middleware,
not a route dependency), **DD4** (layering and status codes), **DD5** (the
exemption set is exactly one minimal liveness endpoint), **DD6** (static assets
are gated), **DD7** (browser handoff is a one-time credential on the first
document request), **DD8** (resolve a caller identity through the lookup seam),
and **DD12** (one-time credential policy — single-use, TTL, fixed redirect
target, per-process consumed-state).

**Why this leg does not register the middleware.** Registering it flips
enforcement live and reddens every browser test until the harness migrates.
That is `enforce-and-migrate-harness`'s job, and it is the only leg permitted to
go red. This leg follows the precedent at `tests/test_origin_allowlist.py`,
whose `_make_app` helper builds a minimal `FastAPI` app, registers the
middleware under test on *it*, and asserts against that — zero blast radius,
suite stays green.

**One note carried forward from that precedent**: exercising DD4's layering
requires registering **both** `OriginAllowlistMiddleware` and the new gate on
the throwaway app. The gate alone cannot demonstrate 401-before-origin versus
valid-credential-wrong-origin-403.

### Prior-leg learnings (from `credential-foundation`)

- `the_one/api_credential.py` exists and is the only thing this leg calls for
  long-lived credential resolution. Its entry point is **`resolve_caller`** —
  synchronous by deliberate decision, so call it inline from the ASGI handler
  with no executor hop.
- Use **`lookup_credential`**, never `get_credential`, on any request path.
  `get_credential` calls `settings.ensure_dirs()` and creates the credential
  file when absent; a Flight Director review finding in Leg 1 split the two
  precisely so that this leg's hot path — which under DD6 runs on every static
  asset — does not perform a `mkdir` and a legacy-migration check per request.
  Reintroducing `get_credential` here re-opens that finding.
- **Forward commitment inherited from Leg 1's design review**: Leg 1's
  second-source seam test proves a second credential source *can* resolve, but
  not that the gating logic is indifferent to which one did — only half of
  mission criterion 7. **This leg owes the other half**: an assertion that the
  middleware reaches the credential module through the single `resolve_caller`
  entry point with **no per-source branching anywhere in the gate**. Satisfy it
  by registering an in-memory second source and driving a real request through
  the throwaway app with a credential that source owns, asserting the request is
  authorized and the caller identity names that source — with the gate's own
  code untouched between the two cases.

## Reconnaissance Findings — Read Before Designing Anything Here

Three facts established by reading `the_one/interfaces/desktop/shell.py` and
`tests/browser/conftest.py` during this leg's design. The third contradicts an
assumption the flight spec left implicit, and it changes what this leg must
build.

1. **The launcher and the server share a process.** When the desktop shell
   starts a server it constructs `uvicorn.Server(...)` and runs it on a
   `threading.Thread(daemon=True)` in the *same* process
   (`shell.py`, in `run_desktop`'s server-start block). DD12's "handoff values
   are per-process, consumed-state lives with the process" therefore works for
   the launcher by direct function call — no IPC, no file, no shared secret.

2. **The launcher's other branch never opens a window.** When `_select_port`
   returns `is_ours=True`, the shell POSTs `/api/window/focus` to the
   *already-running* instance and returns without creating a window. That branch
   needs the long-lived credential on an outbound POST (which is
   `operational-callers`' problem, not this leg's) and needs **no** handoff
   credential at all. Do not build one for it.

3. **Two callers need a handoff URL from outside the server process, and an
   in-process-only mint cannot serve either.** This is the gap.
   - `tests/browser/conftest.py:app_clean` spawns the server as a
     `subprocess.Popen([...,"-m","uvicorn",...])` with an isolated
     `THE_ONE_DATA_DIR`. It holds the long-lived credential (it can read the
     file in that data dir) but shares no memory with the server.
   - The behavior test `local-api-auth-session-lifecycle` needs a handoff URL
     **twice**: at step 6 against a `serve`-started dev instance, and again at
     step 14 for a *fresh* URL after rotation — with no server restart between
     steps 12 and 14, so a mint-once-at-startup scheme cannot supply the second.

   Two non-solutions were considered and rejected, recorded so they are not
   re-proposed: deriving the handoff value deterministically from the
   long-lived credential would let a restart *un-consume* a spent value, which
   is the exact trap DD12 exists to close; and having the browser set the
   session cookie via JavaScript is impossible because the cookie must be
   `HttpOnly`.

## Design Decisions Taken At Leg Level

These settle questions the flight spec left open. Both are recorded in the
flight log as runtime decisions.

**LD1 — Three presentation channels, with the query parameter restricted to the
one-time credential.** The gate accepts a credential from exactly three places:

| Channel | Carries | Used by |
|---------|---------|---------|
| `Authorization: Bearer <credential>` header | the **long-lived** credential | every non-browser caller — desktop shell, pytest harness, Playwright contexts via `extra_http_headers`, `make verify-serving`, CI smoke, AIAT |
| Session cookie (`HttpOnly`, **`SameSite=Strict`**, not `Secure` — loopback is plain HTTP) | a session value bound to the long-lived credential (LD3) | the browser, after a handoff |
| Query parameter on a document request | the **one-time handoff** credential only | the launcher's first navigation, and the behavior test |

**`SameSite=Strict` is load-bearing, not a default.** `Lax` — the obvious choice,
and what this table said before design review — attaches the cookie to
cross-site *top-level navigations* using a safe method. That is the one case
`Lax` does not restrict, and it is precisely the hole this flight exists to
close: `OriginAllowlistMiddleware` never gates `GET`, so a hostile page that
top-level-navigates the operator's browser to a loopback `GET` path would arrive
carrying a valid session, and no origin check would run. LD3's sessions have no
expiry, so that exposure would last until the operator manually rotated.

`Strict` costs nothing here, verified flow by flow: the redirect that *sets* the
cookie has nothing to send yet; the launcher's initial handoff navigation is
browser/OS-initiated with no cross-site initiator; and every subsequent request
— reload, in-page navigation, static assets, the WebSocket handshake —
originates from the app's own loaded page and is unambiguously same-site.

The long-lived credential must **never** be accepted from a query parameter.
That is the whole reason the handoff credential is a separate, single-use,
short-lived value: a URL is the one channel that reliably leaks into logs,
history and referrers, so only a value that is worthless after one use may
travel there.

**LD3 — The session cookie is stateless and cryptographically bound to the
*current* long-lived credential. There is no session store.**

The cookie value is a nonce plus an HMAC of that nonce keyed by the long-lived
credential's secret — `<nonce>.<HMAC-SHA256(key=secret, msg=nonce)>` — verified
on every request by recomputing the HMAC against whatever `lookup_credential()`
returns *at that moment*.

This is forced, not chosen. Two behavior-test requirements pin it from opposite
sides: step 11 requires an established session to survive a server restart, and
step 13 requires rotation to invalidate that same session with no restart. A
per-process session store fails step 11. A persisted session store would need
its own invalidation-on-rotation machinery. Deriving from the credential
satisfies both for free — a fresh process reading the same on-disk credential
recomputes an identical HMAC and authorizes, while `rotate_credential()` changes
the secret so the HMAC stops matching on the very next request, inside the
one-request staleness bound Leg 1's Cache Contract already guarantees.

The flight spec pointed at this without stating it: DD12's closing note says the
restart-survival criterion "is about the established *session*, which outlives
the process because the long-lived credential does." That sentence only makes
sense if the session's validity derives from the credential.

Note what this does *not* weaken: anyone who can read the credential file can
forge a session cookie — but they could equally just present the credential
itself, so no capability is added. And rotation necessarily drops *every*
session at once, which is precisely what the mission's revocation criterion
asks for.

Use a constant-time comparison when verifying the HMAC, for the same reason
Leg 1 pins one on the secret.

**On the nonce**: it carries no verifiable security property — nothing checks it
against anything, and security rests entirely on the secrecy of the credential's
secret. A fixed message would be equally secure. It exists so that every session
is not one constant blob for the lifetime of an install, which keeps a captured
cookie from being trivially recognizable across contexts and leaves room for
binding something meaningful into the message later. Say this in a comment, so a
future reader does not mistake it for a security control and reason from it.

**On expiry**: the cookie carries no `Max-Age`, making it a browser-session
cookie, and its server-side validity ends only at rotation. This is deliberate —
the mission's restart-survival criterion wants sessions to be durable, and its
revocation criterion routes revocation through rotation. It is also why
`SameSite=Strict` matters: an unbounded session amplifies anything that could
attach it to a cross-site request.

**LD4 — Cookie-authenticated requests are attributed to a distinct session
source.** An HMAC check recovers no source or identity on its own, so the gate
synthesizes `IdentifiedCaller(identifier=<the verifying credential's
identifier>, source="session")`. Naming the channel honestly is better than
reporting `source="file"`, which would claim the request presented the file
credential when it did not.

Known limitation, stated rather than discovered later: a session minted by a
*non-file* source is still keyed to the file credential, because LD3 binds the
cookie's HMAC to `lookup_credential()`. This flight registers no non-file source
outside tests, so nothing is affected in practice — but when the MCP automation
surface introduces per-agent and admin credentials, "which credential does a
session outlive" becomes a real question, and this is where it will need
answering. The mint endpoint therefore does not restrict which source may
authenticate it; forcing file-only would encode an assumption this flight has no
grounds to make either way.

**LD2 — An authenticated mint endpoint, alongside the in-process mint
function.** Handoff credentials are minted in two ways, both landing in the same
per-process in-memory store:
- a plain function the launcher calls directly (finding 1 above), and
- a new endpoint that mints a handoff credential for a caller **already
  authenticated with the long-lived credential** (finding 3 above).

The endpoint does not weaken the posture: it converts a credential the caller
already holds into a strictly weaker, single-use, short-lived one. It is the
only way to satisfy the behavior test's step 14 without either persisting
handoff state (which DD12 forbids) or putting the long-lived credential in a
URL (which LD1 forbids).

This does **not** contradict DD9's "no endpoint." DD9 governs *rotation*, and
its rationale — that a single-token rotate endpoint would prematurely encode
"there is exactly one token" — does not apply to minting a session handoff.

**Authenticate this endpoint in the route itself**, via a dependency calling
`resolve_caller`, not by relying on the middleware. The middleware is not
registered until the next leg, and an unauthenticated mint endpoint must not
exist even transiently on this branch.

## Inputs

- `the_one/api_credential.py` — `resolve_caller`, `lookup_credential`,
  `IdentifiedCaller`, `register_source`, `CredentialSource`.
- `the_one/interfaces/web/middleware.py` — `OriginAllowlistMiddleware`: the
  structural template for an ASGI middleware handling both `http` and
  `websocket` scopes, its `_extract_origin` header-walking idiom, and its
  `_send_403` raw-ASGI response helper. Note its docstring already records the
  binding constraint this leg inherits: *"WebSocket upgrades MUST be intercepted
  at the ASGI layer — `Depends()` runs after `ws.accept()`."*
- `tests/test_origin_allowlist.py` — `_make_app`, the throwaway-app test
  pattern, including its `TestClient`-based WebSocket assertions.
- `tests/test_api_credential.py::_isolated_credential_module` — **required
  precedent, not optional.** `api_credential._sources` is a module-level list
  mutated in place by `register_source()` with no unregister API, and the whole
  `make test-unit` suite runs in one process. This leg's second-source seam test
  calls `register_source()`; without an equivalent autouse isolation fixture in
  the new test module, that registration leaks into every subsequent test in the
  run and produces exactly the order-dependent flakiness Implementation Guidance
  #5 warns about — just from pre-existing shared state rather than new.
- `the_one/interfaces/web/app.py` — the `app.add_middleware(...)` /
  `app.mount("/static", ...)` / `app.include_router(api_router)` block; the
  index route returning `_cache_busted_index_html()`; `/api/info` returning
  `{"version", "base_prompt"}`; the `/ws` route.

## Outputs

- A credential-gate ASGI middleware, in `the_one/interfaces/web/middleware.py`
  alongside `OriginAllowlistMiddleware` — **not registered on `app`**.
- A per-process, in-memory handoff store with mint / consume / expiry.
- A new minimal liveness endpoint on the real app (additive, unauthenticated,
  enforces nothing — safe to add here).
- A new mint endpoint on the real app, authenticated in-route.
- New unit tests.

## Acceptance Criteria

**Enforcement**

- [ ] With no credential, an HTTP request to a gated path is refused **401** —
      asserted for `GET`, `HEAD`, `OPTIONS`, `POST`, `PUT`, `PATCH`, `DELETE`.
      `GET` is called out explicitly: the Origin allowlist deliberately does not
      gate safe methods, and closing the GET-side rebinding hole is a stated
      mission driver.
- [ ] A request bearing a valid long-lived credential in the `Authorization`
      header is allowed through, and the resolved `IdentifiedCaller` is made
      available to downstream handlers (e.g. on `scope`), not discarded.
- [ ] A WebSocket upgrade with no credential is refused **before**
      `ws.accept()` runs — asserted the way `tests/test_origin_allowlist.py`
      asserts its 1008 close, so a route handler that would have accepted is
      proven never to have.
- [ ] A request to a path under the static mount is refused without a
      credential (DD6), and allowed with one.
- [ ] The liveness endpoint is reachable with **no** credential, and its
      response body contains **no version string and no prompt text** — asserted
      on the body, not merely on the status. This is the whole reason `/api/info`
      was rejected as the exemption (it returns `base_prompt`).
- [ ] The liveness path is the **only** exemption. A test enumerates the
      middleware's exempt set and asserts it has exactly one member, so adding a
      second requires deliberately editing that assertion.

**Layering (DD4)**

- [ ] The throwaway app registers `OriginAllowlistMiddleware` **first** and the
      gate **second**, mirroring the order they will take in `app.py`. Starlette
      inserts at index 0, so last-added is outermost.
- [ ] **No credential + a disallowed `Origin` header → 401**, and the origin
      logic never runs. The foreign `Origin` header is mandatory in this test,
      not optional: with *no* `Origin` header the request returns 401 under
      **either** registration order, because `OriginAllowlistMiddleware` is a
      no-op when `Origin` is absent. A test using the natural no-headers case
      passes while proving nothing about layering, and would not catch a
      reversed registration.
- [ ] **Valid credential + disallowed origin on a gated method → 403**, proving
      the request reached the origin logic.
- [ ] Both asserted on a throwaway app carrying **both** middlewares.

**Handoff (DD7, DD12)**

- [ ] A document request carrying a valid one-time credential in the query
      parameter is answered with a redirect that sets a session cookie, and the
      redirect **Location contains no credential**.
- [ ] The session cookie is `HttpOnly`; a subsequent request presenting only the
      cookie is authorized.
- [ ] The cookie is set on the **redirect response** produced by the handoff
      exchange — one hop before the document. That ordering is what makes DD6
      safe: the browser stores the cookie, follows the redirect as a fresh
      top-level navigation that already carries it, receives the HTML, and only
      then parses `<script src="/static/...">` and fires subresource requests,
      all of them credentialed. This is also why the exchange lives in
      middleware rather than the index route. (Do not go looking for a way to
      attach `Set-Cookie` to the document response itself — it is the redirect
      that carries it.)

**Session binding (LD3)**

- [ ] A session cookie established against one middleware instance is still
      honoured by a **second, freshly constructed instance** backed by the same
      on-disk credential. This is the restart stand-in, and it is the property a
      per-process session store would silently fail.
- [ ] That same cookie is refused — by either instance, with **no restart
      involved** — immediately after `rotate_credential()` runs against that
      data directory.
- [ ] A cookie whose HMAC does not verify is refused, and verification uses a
      constant-time comparison.
- [ ] **Single-use**: replaying a consumed one-time credential neither
      establishes nor extends a session — asserted both with no cookie present
      and *with an existing valid session cookie present*, since DD12 requires
      invalidation "regardless of whether a session already exists."
- [ ] **TTL**: an unused handoff credential older than its TTL is refused.
      Drive this with an injectable clock, not `time.sleep`.
- [ ] **Fixed redirect target**: the target is not read from any request-
      controlled input. A test asserts that adding a `next`-style parameter to
      the handoff URL does not change the redirect Location — the open-redirect
      guardrail DD12 asks for.
- [ ] **Per-process store**: a test proves consumed-state and outstanding
      handoff values live with the store instance, such that a fresh store
      (standing in for a restarted process) both rejects a previously-issued
      value and cannot resurrect a spent one.
- [ ] The long-lived credential presented in the **query parameter** is
      **refused** (LD1) — this is a security assertion, not an omission.
- [ ] **The query-parameter channel is checked only for document requests.** A
      non-document request — a static asset, an `/api/*` call — carrying a valid
      one-time credential in its query string is refused **and does not consume
      it**. Both halves matter: consuming it would let
      `<script src="/static/x.js?token=...">` or a pasted full URL silently burn
      the credential before the real document request arrives, breaking a
      legitimate handoff; authorizing it would extend the query channel to
      request types LD1 never intended it to reach.
- [ ] The session cookie's `SameSite` attribute is asserted to be `Strict`, and
      a foreign-referrer top-level `GET` is shown not to carry the cookie.

**Caller identity (LD4)**

- [ ] A cookie-authenticated request stashes an `IdentifiedCaller` on `scope`
      with `source` naming the session channel and the identifier of the
      long-lived credential the cookie verified against — not `None`, and not
      silently the file source.
- [ ] A header-authenticated request stashes the caller the lookup seam
      resolved, unchanged.

**Seam (mission criterion 7 — the half this leg owes)**

- [ ] A second, in-memory credential source registered via `register_source` is
      honoured by the gate on a real request through the throwaway app, yielding
      an identified caller naming that source, **with no change to the gate's
      code** between that case and the file-source case, and with no
      source-specific branching anywhere in the middleware.

**Mint endpoint (LD2)**

- [ ] The mint endpoint requires the long-lived credential and refuses without
      it — enforced in-route, verified while the middleware is still
      unregistered.
- [ ] It returns a usable handoff URL, and the returned value satisfies every
      one-time-credential property above.
- [ ] It does **not** accept a handoff credential as its own authentication —
      a handoff credential cannot be used to mint another. Otherwise a single
      leaked URL becomes an unbounded session generator.

**Blast radius**

- [ ] The gate middleware is **not** added to `app` in
      `the_one/interfaces/web/app.py`. A test asserts the real app's middleware
      stack does not contain it, so accidental registration fails loudly here
      rather than silently reddening the next leg.
- [ ] `make test-unit` is green. Nothing existing reddens.
- [ ] The new test module(s) are added to the curated Windows lane file lists in
      `ci/tasks/windows-tests.yml` **and** `.github/workflows/test.yml`, per the
      MAINTENANCE comments both carry.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_<gate>.py -x --timeout 30`
- WebSocket refusal: follow `tests/test_origin_allowlist.py`'s pattern — a
  throwaway route whose handler would `accept()`, asserting the client sees the
  refusal and the handler never ran.
- TTL: inject a clock into the store; never `time.sleep`.
- Non-registration: assert against `app.user_middleware` (or equivalent) that
  the gate class is absent.
- Full gate: `make test-unit`.

## Implementation Guidance

1. **Mirror `OriginAllowlistMiddleware`'s structure** — a plain ASGI class
   taking `app` plus config, an `__call__` switching on `scope["type"]`, an
   early pass-through for non-http/websocket scopes, and raw-ASGI send helpers
   for refusals. Do not reach for `BaseHTTPMiddleware`; it does not give
   WebSocket coverage and the existing sibling deliberately avoids it.

2. **Refusal shapes differ by scope type.** HTTP refusal is a JSON 401 body, in
   the shape `_send_403` already establishes. A WebSocket refusal must be a
   `websocket.close` before the route can accept — `OriginAllowlistMiddleware`
   uses code 1008 for policy violation; pick deliberately and say why in a
   comment, since a WebSocket handshake has no 401.

3. **Resolve once per request, then stash the caller on `scope`.** Downstream
   handlers, and the future per-route policy the automation surface will want,
   should read the identity rather than re-resolving.

4. **Order the channel checks: cookie, then header, then query.** Put the
   handoff exchange last and gate it on the request being a document request, so
   the common authenticated case costs one dictionary lookup.

5. **Keep the handoff store a small explicit object with an injected clock**, not
   module-level globals with `time.time()` inline. The TTL and single-use tests
   both need to control time, and Leg 1's cache finding is a live reminder that
   module-level mutable state without a key becomes a test-isolation problem the
   moment a second consumer appears.

6. **Register the exempt path as data, not as an `if` chain**, so the
   "exactly one exemption" test has something to enumerate.

7. **Pin the in-process mint function's name and module in this leg**, and note
   it in the flight log when the leg lands. `operational-callers` wires the
   launcher to it and should not have to reverse-engineer where it lives.

8. **The mint endpoint's in-route auth dependency is new ground here.** No
   FastAPI `Depends`-based header-auth pattern exists elsewhere in this codebase
   — `Authorization` is read manually in the couple of places that touch it.
   Write it as a small explicit dependency rather than hunting for an idiom to
   match; there isn't one.

7. **The liveness endpoint returns liveness and nothing else.** No version, no
   prompt, no build info, no data directory. It is reachable by any local
   process by design, so anything in its body is public to every local process.

## Edge Cases

- **A request that is both a document request with a handoff credential and
  carries an already-valid session cookie** — DD12 is explicit: consume the
  one-time credential anyway; it must not survive to be replayed. Decide and
  document whether the existing session is kept or replaced; either is
  defensible, silence is not.
- **Malformed credential** — a garbage `Authorization` header must produce the
  same 401 as an absent one, with no parse error escaping. Leg 1's
  `LocalApiCredential.parse` returns `None` rather than raising, so this should
  fall out — assert it rather than assuming it.
- **Missing credential file entirely** — `lookup_credential` returns `None` and
  logs a warning. The gate must refuse cleanly, not 500.
- **`CredentialFileError`** — a malformed *existing* credential file propagates
  as an exception by Leg 1's deliberate design. Decide what the gate does with
  it; a 500 is arguably correct (it is a server misconfiguration, not a client
  error) but it must not be an unhandled traceback leaking file paths.
- **HEAD and OPTIONS on the liveness path** — exempt or not? The Origin
  middleware's comment warns that gating `OPTIONS` without CORS headers breaks
  future preflight. Be deliberate, and **pin the choice with an acceptance
  assertion** rather than deciding it silently in code: the "exactly one
  exemption" property has to hold per-method too, or the exempt set is one path
  and an unexamined set of methods.
- **The static mount's path prefix** — match on the mount prefix, not on file
  extension.
- **Concurrent consumption of one handoff credential** — two racing requests
  must not both succeed. The store's consume step needs to be atomic in a way
  that holds under a threaded server (the launcher runs uvicorn in a thread).

## Files Affected

- `the_one/interfaces/web/middleware.py` — the gate middleware, alongside the
  existing Origin allowlist.
- A new module for the handoff store (or the same file if it stays small —
  implementer's call, but it must be independently testable with an injected
  clock).
- `the_one/interfaces/web/app.py` — **routes only**: the liveness endpoint and
  the mint endpoint. **No `add_middleware` call for the gate.**
- `tests/test_<gate>.py`, and any handoff-store test module — new.
- `ci/tasks/windows-tests.yml`, `.github/workflows/test.yml` — new test modules
  registered in the curated Windows lane.

## Citation Audit

Verified against the working tree on `flight/01-authenticated-local-api` at
Leg 2 design time (Leg 1 landed, uncommitted):

| Citation | Status |
|----------|--------|
| `shell.py` — `uvicorn.Server(...)` + `threading.Thread(target=server.run, daemon=True)` in the same process | Present, read |
| `shell.py` — `is_ours` branch POSTs `/api/window/focus` and returns without creating a window | Present, read |
| `shell.py` — browser-fallback branch calls `webbrowser.open(url)`, also in-process | Present, read |
| `tests/browser/conftest.py:app_clean` — `subprocess.Popen` of `python -m uvicorn` with isolated `THE_ONE_DATA_DIR` | Present, read |
| `app.py` — `add_middleware(OriginAllowlistMiddleware, ...)` then `mount("/static", ...)` then `include_router` | Present, read |
| `app.py` — `/api/info` returns `{"version": __version__, "base_prompt": BASE_PROMPT}` | Present, read |
| `middleware.py` — `GATED_METHODS` excludes safe methods; `_send_403`; WebSocket 1008 close before accept; docstring on the `Depends()`-after-`accept()` constraint | Present, read |
| `tests/test_origin_allowlist.py:_make_app` — throwaway-app pattern | Present, read |
| `the_one/api_credential.py` — `resolve_caller`, `lookup_credential`, `register_source` | Present (Leg 1 output) |

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md

> Commit is deferred to the flight-end review gate. Do **not** commit and do
> **not** signal `[COMPLETE:leg]`.
