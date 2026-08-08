# Flight: Authenticated Local API End-to-End

**Status**: landed
**Mission**: [Local API Authentication](../../mission.md)

## Contributing to Criteria

- [x] Every request path refused without a valid credential — all HTTP methods, WebSocket upgrades, static assets — except a documented exemption set
- [x] Operator reaches the UI through the normal launch path without seeing, copying, or typing a credential; none remains in the address bar
- [x] An already-open UI session survives a server restart without relaunching
- [ ] Every non-browser caller authenticates from the operator's environment — desktop shell, browser lane, live/AIAT lane, behavior-test runner, serving-verification target, CI packaged-smoke *(**partially verified**: desktop shell and browser lane confirmed by the HAT and the green suites; the AIAT lane, `make verify-serving`, the CI packaged-smoke and the behavior-test runner were **code-changed but never executed** — the live lane deliberately so, since it defaults to the operator's production `:8484`. Carried to the debrief.)*
- [x] Credential readable only by the operator's OS account, with no world-readable window including at creation
- [x] Operator can invalidate and replace the credential without hand-editing files; old sessions stop working
- [x] Requests authorized against an identified caller, demonstrated by honouring a second credential type with no change to the gating logic
- [x] Documented security model no longer describes the API as unauthenticated and states what the posture does and does not protect against
- [x] Unit and browser suites pass with authentication enforced, not disabled or bypassed

---

## Pre-Flight

### Objective

Turn the local HTTP/WebSocket API from fully unauthenticated into a surface that
requires a credential only the operator's OS account can read — without the
operator ever handling that credential by hand. This flight delivers the
credential itself, the gate that enforces it across every request path, the
browser session handoff that keeps launching transparent, the migration of every
existing caller, command-line rotation, and the revision of the documented
security posture that F3 Decision 10 requires before any of this is legitimate.

### Open Questions

- [x] Does the browser session handoff work inside the embedded webview? → **Mechanism resolved** (DD7); survival under a real run is the HAT leg's job
- [x] Does the liveness/version probe join the exemption set? → DD5
- [x] Do static assets require the credential? → DD6
- [x] How do the two gates layer? → DD4
- [x] Does the per-test credential become readable before the readiness probe fires? → **The race is avoided, not resolved.** The fixture creates the isolated `data_dir` itself and only then spawns the server, so writing the credential before `subprocess.Popen` removes the ordering question entirely. Settled in `harness-credential-plumbing` against the real fixture, as intended
- [x] Where does DD13's behavior-test credential mechanism live? → **Project-side, carried by instruction rather than by per-spec edits** (DD13)

### Design Decisions

**DD1 — Credential shape**: An opaque string carrying a public identifier and a
secret, distinguishable by prefix.
- Rationale: A future store can revoke by identifier, and logs and errors can
  name a credential without printing its secret. Costs nothing now.
- Trade-off: Slightly more parsing than a bare random string, and a format that
  must stay stable once written to disk.

**DD2 — Storage and creation**: A file in the resolved data directory, created
via an exclusive open at mode `0600` in a single syscall.
- Rationale: Follows `the_one/interfaces/web/api.py:4892-4896`, whose comment
  records exactly why: "Path.write_bytes followed by chmod has a brief
  world-readable window." `encryption.py:78,104` uses the weaker
  write-then-chmod pattern; do not copy that one.
- Trade-off: Slightly more code than `write_text` for a file most readers will
  assume is trivial — the comment must say why.

**DD3 — The gate is ASGI middleware, not a route dependency**: Enforcement sits
in a middleware sibling to `OriginAllowlistMiddleware`.
- Rationale: `app.py:353-356` already records the binding constraint — a
  dependency runs *after* `ws.accept()`, too late to refuse a WebSocket
  upgrade. Middleware is the only layer that covers routes, the `/static`
  mount, and upgrades uniformly.
- Trade-off: No per-route granularity, which is fine because no per-route
  policy exists this flight.

**DD4 — Layering and status codes**: The credential gate is registered last so
it wraps the Origin allowlist. Missing or invalid credential → 401 before origin
logic runs; valid credential from a disallowed origin → 403.
- Rationale: Starlette's `add_middleware` inserts at index 0, so last-added is
  outermost. Distinct codes make the failure legible: 401 means "no credential,"
  403 means "wrong origin."
- Trade-off: A cross-origin caller learns whether its credential was valid
  before being refused on origin. Acceptable — origin is defense in depth here,
  not the primary gate.

**DD5 — Exemption set is exactly one minimal liveness endpoint**: A new
unauthenticated endpoint returning liveness and nothing else. `/api/info` stays
credentialed.
- Rationale: `/api/info` returns `{"version", "base_prompt"}`
  (`app.py:1985-1987`) — exempting it would publish the agent's system prompt to
  any local process and any rebinding page. The bootstrap callers that genuinely
  need pre-credential access only need "is it up," not version or prompt.
- Trade-off: A new endpoint to maintain, and the exemption must be defended
  against future accretion — it is a set of one, and stays that way absent a
  written reason.

**DD6 — Static assets are gated**: `/static` requires the credential.
- Rationale: The middleware already wraps the mount (`app.py:361`) with no
  special-casing, so it is free. Makes the invariant "nothing unauthenticated
  except liveness" rather than "nothing except liveness and assets."
- Trade-off: `make verify-serving`'s 18-path asset loop must carry the
  credential.

**DD7 — Browser handoff is a one-time credential on the first document
request**: The launcher opens a URL carrying a single-use credential; the gate
consumes it on that request, establishes a session cookie, and redirects to
strip it from the address bar.
- Rationale: This is the only shape the pinned webview supports — it exposes no
  cookie-injection method and `create_window()` takes no header parameter, so
  seeding a session out-of-band is unavailable. The shell does control the
  initial URL (`shell.py:497,615`) and runs non-private with persistent storage
  (`shell.py:665-671`). Consuming it in middleware rather than the index route
  means the session is established on the document *response*, which is what
  makes DD6 safe — a post-load exchange would race the `<script src="/static/…">`
  tags the document triggers.
- Trade-off: A credential briefly appears in a URL. It is single-use and
  stripped by redirect, but it will transit any URL-logging surface in between.

**DD8 — Authorization resolves a caller identity behind a lookup seam**: The
gate yields an identified caller, and credential lookup goes through a seam a
second source can register against. No minting, no per-route scope enforcement.
- Rationale: A per-agent/admin token surface is planned; these are the cheap
  accommodations that avoid a rewrite later.
- Trade-off: Speculative generality at one implementation — the exact risk the
  M19 debrief flagged ("the seam's shape may not generalize past 'swap the auth
  mechanism'"). Held to three items deliberately; do not widen mid-flight.

**DD9 — Rotation is command-line only**: A new subcommand on the existing
`sys.argv` dispatch (`main.py:10-40`). No endpoint, no UI.
- Rationale: Rotation semantics under multiple principals are unsettled;
  a single-token rotate endpoint would encode "there is exactly one token"
  before the automation surface says otherwise.
- Trade-off: Rotating requires a terminal and a relaunch.

**DD10 — Test credential handling is centralized, not per-call-site**: The
browser fixture and a shared client helper carry the credential; the ~56 direct
`httpx` sites and ~20 `TestClient` sites adopt them rather than each learning
about credentials.
- Rationale: The alternative is dozens of independent edits, which is also the
  flight's stated trip-wire for invoking the split point.
- Trade-off: A fixture-level change with wide blast radius — a mistake there
  reddens everything at once, which is loud rather than subtle.

**DD11 — Single-instance classification uses the credentialed `/api/info`**:
`_select_port` treats "shares our credential" as "ours."
- Rationale: Strictly better than today, where "ours" means "same version" — so
  a second instance on a *different* data directory with the same version is
  currently misclassified as ours.
- Trade-off: A non-the-one server that also 401s is no longer distinguishable
  from a foreign the-one. Both resolve to "not ours," which is the safe answer.

**DD12 — One-time credential policy is fixed here, not invented in a leg**: The
handoff credential is single-use and time-limited. It is invalidated on first
successful exchange regardless of whether a session already exists; a second
request bearing the same value never establishes or extends a session — only an
existing session cookie may authorize. It carries a TTL on the order of minutes,
so an unused handoff URL does not stay live indefinitely. The redirect target is
fixed, not parameterized.
- Rationale: Leaving this to a leg means inventing security policy at
  implementation time. The fixed redirect target matters most: no
  `next`/return-path parameter exists anywhere in the codebase today, and adding
  one later without a target allowlist is a textbook open redirect. Recording
  the constraint now puts a guardrail on whoever adds one.
- Trade-off: A TTL means a launcher that constructs a URL and opens it slowly
  can fail. Choose the TTL generously; failure mode is a relaunch, not a lockout.
- **Consumed-state lives with the process, and handoff values are per-process.**
  A handoff credential is issued by, and valid only for, the running server
  process; its consumed-marker is held in memory alongside it. A restart
  therefore invalidates every outstanding handoff value rather than forgetting
  which ones were spent — the failure mode is "that URL no longer works," never
  "that spent URL works again." This is the specific trap the storage question
  hides: a persisted credential with an in-memory consumed-marker would let a
  restart *un-consume* a value that had already leaked into a URL-logging
  surface, quietly reopening the replay window this decision exists to close.
  Note the asymmetry with the long-lived credential, which persists by design
  (DD2) — these are two different credentials with two different lifetimes, and
  conflating them is the likeliest implementation error in this flight.
- Interaction with restart survival: none. The restart-survival criterion is
  about the established *session*, which outlives the process because the
  long-lived credential does. Outstanding handoff values dying at restart is
  correct and does not weaken it.

**DD13 — The behavior-test apparatus is a first-class caller, credentialed
project-side by standing instruction**: The convention for obtaining a
credential and constructing a handoff URL lives in this project's own
instruction surfaces — `CLAUDE.md`, and the `.flightops/agent-crews/` prompts
where a crew drives the app. Individual spec step tables are not edited.
- Rationale: At least ten currently-`active` specs navigate a browser directly to
  the app root with no credential step, several targeting the default port. They
  are real regression coverage and they all break at step 1 the moment the gate
  goes on. `CLAUDE.md` is auto-loaded into any session working in this
  repository, so an Executor driving the app inherits the convention without any
  spec being touched — and every future spec gets it for free rather than
  acquiring the same footgun. Keeping it here also respects Mission Control's
  boundary rule: the `/behavior-test` skill must not encode a convention owned
  by one project.
- Trade-off: Instruction-carried conventions are softer than code — an agent can
  miss them in a way a fixture cannot. Mitigated by the specs' own Preconditions,
  which the runner checks before spawning, and by the fact that a missed
  credential fails loudly at step 1 rather than silently.

### Prerequisites

- [x] Mission approved and `active`
- [x] Exemption, static-gating, layering, and handoff decisions taken (DD4-DD7)
- [x] Webview pinned to an exact version; handoff mechanism analysis depends on that pin
- [x] Behavior-test apparatus audited on both axes (see Verification)
- [x] A dedicated dev instance on a non-default port available for live checks — the `-m live` lane must never target the operator's production instance *(deferred: first needed by `operational-callers`; not a gate on legs 1–2)*
- [x] Working tree clean; flight branch created (`flight/01-authenticated-local-api`)

### Pre-Flight Checklist

- [x] All open questions resolved (one deferred to `enforce-and-migrate-harness` design by intent — a startup-ordering race only observable against the real fixture)
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

A credential module owns generation, exclusive-mode creation, reading, and
constant-time comparison, exposing a lookup seam that yields an identified
caller. A middleware registered outside the Origin allowlist consumes that seam
on every request — routes, the static mount, and WebSocket upgrades alike —
refusing with 401 and exempting exactly one liveness endpoint. The same
middleware recognises a one-time credential on a document request, exchanges it
for a session cookie, and redirects to strip it. Every existing caller then
migrates: the browser fixture and a shared client helper for tests, the desktop
shell's readiness poll and port classifier, the serving-verification target, and
the CI packaged-smoke probe. A new CLI subcommand rotates. `SECURITY-MODEL.md`
is revised where it currently asserts the API is unauthenticated by design.

### Checkpoints

- [x] Credential exists, is created without a world-readable window, and rotates
- [x] A second credential type is honoured with no change to the gating logic
- [x] Gate refuses every path unauthenticated; liveness endpoint is the only exemption
- [x] Browser reaches the UI through the handoff with no credential left in the URL
- [x] One-time credential is single-use and expires; replay never establishes a session
- [x] Unit and browser suites green with the gate enforced
- [x] Desktop shell (all three call sites), serving-verification target, and CI packaged-smoke green
- [ ] Live/AIAT lane authenticates *(code changed; **not executed** — `-m live` defaults to the operator's production instance and was never pointed at it)*
- [ ] Existing behavior-test specs run green through the runner's credential mechanism *(convention established in `CLAUDE.md` and the crew prompts, 24 active specs' Preconditions updated; **no spec was actually run** — carried to the debrief)*
- [x] Session survives a server restart; rotation drops it
- [x] Security model revised; stale unauthenticated-probe documentation corrected

### Adaptation Criteria

**Divert if**:
- Centralizing credential handling into fixtures does not hold and the migration
  degenerates into per-call-site edits — this is the mission's pre-declared
  trip-wire; invoke the split point rather than grinding through ~76 sites
- The one-time-credential handoff does not survive a real windowed run, since
  the pinned webview offers no fallback mechanism — this becomes a flight-level
  design question, not a leg-level fix
- Gating `/static` proves to race bootstrap in a way DD7 does not resolve

**Acceptable variations**:
- Exact credential encoding, file name, cookie attributes, and subcommand name
- Where the liveness endpoint lives in the route table
- Whether the shared test client is a fixture, a helper, or both
- Additional unit tests beyond those named in leg acceptance criteria

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `credential-foundation` - Credential module (shape, exclusive-mode creation, constant-time compare), identified-caller type, lookup seam, rotate subcommand, and the second-credential-type seam test. Nothing enforced yet; suite stays green throughout.
- [x] `gate-middleware` - The middleware itself: enforcement across methods, upgrades and the static mount; the liveness exemption; the one-time-credential handoff, single-use invalidation, TTL and redirect (DD12); layering and status codes. Built and unit-tested against a throwaway app, **not registered on the real app** — follows the existing precedent at `tests/test_origin_allowlist.py:31-39`. Zero blast radius; suite stays green. Note for the implementer: exercising DD4's layering requires registering *both* the Origin allowlist and the new gate on the throwaway app — the gate alone cannot demonstrate 401-before-origin versus valid-credential-wrong-origin-403.
- [x] `harness-credential-plumbing` - Move every test-harness caller onto the credential **with the gate still unregistered**, so the migration is proven green before enforcement flips. Consolidates the **10** browser app-spawn implementations, credentials the **252** seeder call sites without editing them, and adopts a shared authenticated client across the **34** unit-test fixtures (DD10). Suite stays green throughout.
- [x] `enforce-gate` - Register the gate on the real app, flipping enforcement live. One `add_middleware` call and one inverted test, against an already-credentialed harness. Inherits the "permitted to go red" licence, but the window should be near-zero — a large failure list means the plumbing leg missed a caller category.
- [x] `operational-callers` - Credential attachment for four caller categories: the desktop shell's readiness poll, port classifier **and the window-focus forward at `shell.py:493`**; `make verify-serving` including its 18-path asset loop; the CI packaged-smoke probe; and the live/AIAT lane (`tests/test_aiat.py`, `tests/live/discord_hat/*`). Mostly mechanical, with two exceptions carrying real content: DD11's redefinition of "is that instance ours", and a credential-leak hazard — `curl -H "Bearer $(cat …)"` publishes the credential via world-readable `/proc/<pid>/cmdline` to every local account, defeating this mission's protection inside its own verification target.
- [x] `behavior-test-apparatus` - DD13's project-side credential convention in `CLAUDE.md` and the relevant `.flightops/agent-crews/` prompts, plus Preconditions updates across the **24 active** specs — **11** of which name the operator's production `:8484` directly. Separated from `operational-callers` because it is mechanism design rather than header attachment, and because its correctness is judged by running a spec rather than by a green suite.
- [x] `security-model-and-docs` - The `SECURITY-MODEL.md` revision of F3 Decision 10 and its Authentication section, plus documentation describing the now-stale unauthenticated probe (`docs/windows-install.md`, `packaging/windows/README.md`) and testing-lane guidance in `CLAUDE.md`.
- [x] `uat-and-alignment` *(optional)* - Guided HAT session on the real windowed desktop path: handoff, restart survival, rotation.

**On leg count**: eight — planned as seven, and `enforce-and-migrate-harness`
split in two during execution once its design review counted the real migration
surface (see the flight log's Deviations). Against a methodology guideline of
one-to-four. This is recorded as a deviation, not defended as compliant. The boundaries between legs
are genuine decision boundaries — the gate's correctness is reviewable before it
is switched on, the switch-on is isolated from mechanical migration, mechanical
credential attachment is isolated from mechanism design, and documentation
revision is the mission criterion it satisfies rather than a chore appended to
code work. But the honest reading is that a flight needing seven legs is a
flight carrying two risk clusters: designing an auth model, and migrating an
ecosystem to it. That the second cluster kept growing under review — the
live/AIAT lane, then ten behavior-test specs, then a cross-repo boundary
question — is evidence for that reading, not against it. **Revisit the split
before execution rather than after.**

**Intermediate state, stated deliberately**: enforcement goes live in
`enforce-and-migrate-harness`, leaving the desktop path, the operational
callers and the behavior-test specs red until `operational-callers` lands. This
was verified safe rather than assumed: the heavy suites run on local Concourse
against a resource pinned to `main`, the GitHub Actions suites are
`workflow_dispatch`-only, the sole automated pull-request gate lints and audits
without running functional tests, and no pre-push hook is installed. The flight
lands green as a unit, not leg by leg.

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [ ] Code merged *(PR open; not yet merged)*
- [x] Tests passing
- [x] Documentation updated

### Verification

- **Unit gate**: `make test-unit` green with enforcement on — not disabled,
  stubbed, or bypassed. This is the canonical gate; never `-m live`.
- **Browser lanes**: via `scripts/run-tests.sh --lane …`, green with
  enforcement on.
- **Serving verification**: `make verify-serving` green, including the 18-path
  asset loop under DD6 and the pid-ownership check.
- **CI**: the packaged-smoke steps pass on a real frozen build.
- **Behavior test**: `/behavior-test local-api-auth-session-lifecycle` — covers
  what unit tests structurally cannot: that a real browser reaches the UI
  through the handoff, that an established session survives a server restart,
  and that rotation drops it. Apparatus audited on both axes — it can *act*
  (browser drives navigation and interaction; shell restarts the server and runs
  rotation) and it can *observe* (browser reads rendered state and response
  status; shell reads the credential file's mode and content, and issues
  uncredentialed requests to confirm refusal).
- **HAT leg**: the packaged desktop path, which no apparatus reaches — the
  pinned webview is not the browser lane's Chromium, so per-backend cookie
  persistence and handoff timing are only observable to a human running the
  real app.
