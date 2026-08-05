# Mission: Local API Authentication

**Status**: active

## Outcome

The local HTTP/WebSocket API stops being drivable by anything that can reach the
port. Today any process on the machine — including low-privilege or sandboxed
ones, and on a shared machine any *other local user* — can drive the full API,
which reaches `shell` and `python_exec` and reads a database now holding an
Anthropic Pro/Max OAuth token. After this mission, driving the API requires a
credential that only the operator's own OS account can read, and the operator
never handles it by hand: launching the app just works, exactly as it does today.

The honest boundary: a process already running *as the operator* can read the
credential file and is therefore still trusted. What this mission removes is
access by callers that cannot read that file — other local accounts,
lower-privilege processes, and browser-vectored callers such as a DNS-rebinding
page, which can issue requests but cannot read the filesystem.

## Context

`SECURITY-MODEL.md` states "No auth on HTTP/WebSocket routes by design" and
names F3 Decision 10 ("operator-trusted setup") as the canonical citation for
any future auth question. That posture was chosen for a dev-tool form factor
started ad hoc and stopped when done. Two things changed it:

- **M15 packaged desktop** — the server is increasingly an always-on background
  process on an end-user machine, widening the exposure window from "while I'm
  working" toward 24/7.
- **M19 plan provider** — the database now stores OAuth tokens for a Claude
  Pro/Max subscription, materially raising the value of what sits behind the
  unauthenticated surface.

Two residual risks follow. Any local process can reach `shell`/`python_exec`
over plain HTTP on the loopback. And the existing Origin allowlist gates only
mutating methods and WebSocket upgrades, so a DNS-rebinding page can still issue
GETs and read chat history and agent/provider metadata.

This mission deliberately revisits F3 Decision 10 — which `SECURITY-MODEL.md`
itself flags as required before changing the auth posture — and is a stated
prerequisite for the run-as-a-service form factor (issue #166), which is not
acceptable while the exec API is unauthenticated.

Tracked as issue #165.

## Success Criteria

- [ ] Every request path is refused without a valid credential — all HTTP
      methods including GET, WebSocket upgrades, and static assets — except a
      deliberately enumerated, documented exemption set that is justified
      case by case rather than by convenience.
- [ ] The operator reaches the UI through the normal launch path without ever
      seeing, copying, or typing a credential, and no credential remains
      visible in the address bar afterward.
- [ ] A UI session already open survives a server restart without relaunching.
- [ ] Every non-browser caller authenticates from the operator's own
      environment, with no credential committed to the repository and none
      hardcoded in a test. The inventory is: the desktop shell, the browser
      test lane, the live/AIAT lane, the behavior-test runner, the repository's
      own serving-verification target, and the packaged-app smoke check in CI.
- [ ] The credential is readable only by the operator's OS account, with no
      window at any point — including creation — where it is world-readable.
- [ ] The operator can invalidate the current credential and issue a
      replacement without hand-editing files; sessions authenticated with the
      old credential stop working.
- [ ] A request is authorized against an identified caller rather than a
      boolean, demonstrated by honouring a second credential type in a test
      with no change to the request-gating logic itself.
- [ ] The documented security model no longer describes the API as
      unauthenticated, and states plainly what the new posture does and does
      not protect against.
- [ ] The unit and browser suites pass with authentication enforced — not
      disabled, stubbed out, or bypassed for tests.

## Stakeholders

- **Operator (device owner)** — the only user. Needs the hardening to cost
  nothing in daily use: launch, use, restart, no credential handling.
- **Future automation surface** — a planned MCP surface through which internal
  agents and external clients will manage agents, requiring per-agent and admin
  tokens. Not built here, but its existence constrains the shape chosen now.
- **Issue #166 (run as a service)** — blocked on this outcome.

## Constraints

- **Single-user local posture is retained.** Multi-user accounts, TLS, and
  reverse-proxy auth remain out of scope; this hardens against non-operator
  *local* and *browser-vectored* callers, nothing more.
- **The Origin allowlist stays** as defense in depth — it covers a
  leaked-credential CSRF class that a credential alone does not.
- **No in-app credential minting.** Nothing consumes a minted token today: the
  browser is handed a session automatically, the desktop shell and test lanes
  read the operator's environment, and connectors run in-process and never
  touch the HTTP API. Minting implies a lifecycle (create, label, revoke,
  expire) and a store that is encrypted at rest, masked in responses, and
  enrolled in key rotation — making it a fifth secrets-bearing table, which the
  M19 debrief already records as the trigger for extracting a shared
  secrets-column helper. That is a separate mission.
- **Do not paint into a corner.** Per-agent and admin tokens are coming with
  the MCP automation surface. Three cheap accommodations are in scope: the gate
  resolves a caller identity rather than a boolean; the credential carries an
  identifier distinct from its secret so a future store can revoke by
  identifier and logs can name a credential without leaking it; and credential
  lookup sits behind a seam a second source can be registered against.
- **Per-route scope enforcement is out of scope.** It has no consumer until the
  automation surface exists and would require a policy decision on each of
  ~85 routes.
- **Rotation is command-line only** this mission — no endpoint, no UI control.
  Rotation semantics under multiple principals (rotate-everything vs.
  revoke-one) are unsettled, and a single-token rotate endpoint risks encoding
  "there is exactly one token" before the automation surface clarifies it.
- **Planning-only skills do not implement.** Implementation runs through
  `/agentic-workflow`.

## Environment Requirements

- Local toolchain, existing test lanes: `make test-unit` is the canonical gate;
  browser lanes via `scripts/run-tests.sh --lane …`.
- The `-m live` AIAT lane must never be pointed at the operator's production
  instance on port 8484 for verification; use a dedicated dev instance.
- The packaged desktop path needs a real windowed run to verify — the one place
  autonomous verification cannot reach. The webview dependency is pinned to an
  exact version, and the handoff design depends on that pin; a version bump
  invalidates the mechanism analysis.
- The repository's serving-verification target and the packaged-app smoke check
  in CI both probe the app unauthenticated today and are in scope for
  migration, not fast-follow — leaving them broken would mean the flight cannot
  demonstrate a green verification path.
- No external accounts, network services, or third-party credentials required.

## Open Questions

- **Does the browser session handoff survive a real desktop run?** The
  *mechanism* is no longer open: the pinned webview version exposes no way to
  seed a cookie or inject a header into the initial navigation, so the only
  shape the installed API supports is the one the shell can already reach —
  it owns the initial URL, so a one-time credential carried on that first
  document request, consumed synchronously, exchanged for a session, and
  stripped by redirect. What remains genuinely unknown is whether that survives
  in practice across platform backends, which is a question about timing and
  persistent-storage behaviour that only a real run answers. Resolve early —
  it gates the desktop path and is the mission's single largest risk.
- **Does the liveness/version probe join the exemption set?** This is the
  highest-leverage open question, because three separate bootstrap callers hit
  it *before* the app has finished starting: the desktop shell's readiness poll
  and its single-instance port classification, the browser-test fixture's
  readiness wait, and the packaged-smoke step in CI. Exempting it makes all
  three trivial but leaks version information to any local process. Requiring
  a credential is the stronger posture and gives the port classifier a
  *better* signal than today — a foreign instance with a different data
  directory now fails authentication rather than being told the version — but
  each of the three callers then needs its own answer to a chicken-and-egg.
  Decide this before the flight designs the clients; it changes all three.
- **Do static assets require the credential?** Gating them is architecturally
  free — the existing Origin middleware already wraps the static mount, so a
  sibling gate inherits the same coverage — but it constrains the handoff:
  the session must be established on the document response itself, since
  anything deferred to a post-load exchange races the asset requests the
  document triggers. Not gating them means local callers can read JavaScript
  that already ships inside the installer. Low stakes, but it should be a
  decision, not an accident.
- **How do the two gates layer?** The Origin allowlist and the credential gate
  enforce independently on the same request path. Which runs first, and what
  each returns on refusal, is unspecified — and getting it wrong produces a
  confusing debugging experience where a 403 and a 401 are easily mistaken for
  each other. Cheap to decide deliberately, annoying to untangle later.
- **Should an agent ever hold an admin credential?** Not this mission's
  problem, but if internal agents get tokens on the automation surface, an
  agent could manage agents — including itself. Far cheaper to decide before
  that surface exists than after.

## Known Issues

*(none yet — populated as flights surface blockers)*

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are
> planned and created one at a time as work progresses. This list will evolve
> based on discoveries during implementation.

- [ ] Flight 1: Authenticated local API end-to-end — credential generation and
      storage, the caller-identity gate covering every method plus WebSocket
      upgrades, browser session handoff, migration of the desktop shell and all
      test lanes, command-line rotation, and the security-model revision.

**Pre-declared split point:** if the browser session handoff turns out to need
its own design conversation — most likely because the desktop path resists the
one mechanism the pinned webview supports — split it into a second flight at
that boundary. Otherwise this stays one flight: enabling the gate reddens every
browser test until the fixtures migrate, so the intermediate state is not
independently landable, and the design decisions form one entangled cluster.

**What keeps it one flight.** The client migration touches roughly 80–100 call
sites across ~60 files, none of which funnel through a shared authenticated
client today. That stays a single flight only if credential handling is
centralized into the existing per-test fixtures and a small shared helper. If
that centralization does not hold, the fallback is dozens of independent call
site edits — which is a signal to invoke the split point, not to push through.
