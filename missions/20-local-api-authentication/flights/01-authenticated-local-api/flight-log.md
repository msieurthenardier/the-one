# Flight Log: Authenticated Local API End-to-End

**Flight**: [Authenticated Local API End-to-End](flight.md)
**Mission**: [Local API Authentication](../../mission.md)
**Started**: 2026-08-05

## Summary

Execution began 2026-08-05 on branch `flight/01-authenticated-local-api`.
Flight transitioned `planning` → `in-flight` on operator approval via
`/agentic-workflow`.

## Leg Progress

{Appended per leg during execution.}

### Leg 01 `credential-foundation` — review fixes (post-implementation)

The Flight Director's review of the initial implementation returned two
blocking findings, both fixed before the leg landed:

1. **Cache not keyed by path.** `_cache` in `the_one/api_credential.py` was a
   single module-level slot holding `(identifier, secret, mtime_ns, size)`
   with no record of which file it came from. A process that swaps
   `settings.data_dir` and then reads could be served the previous
   directory's credential whenever the new file's `st_mtime_ns` happened to
   coincide with the cached value (`st_size` is a no-op guard for this
   fixed-length format, so the whole guard rested on an `st_mtime_ns`
   collision between two distinct files) — unlikely on ext4, more likely on
   coarse-granularity filesystems reachable via the operator-overridable
   `THE_ONE_DATA_DIR`. The test fixture's `_cache` reset between tests was
   evidence this was masking a real gap rather than a theoretical one, and
   the next-but-one leg (`enforce-and-migrate-harness`) would otherwise have
   pushed that reset burden onto ~76 call sites across ~60 files.

   Fix: `_cache` is now `dict[str, _CachedCredential]`, keyed by
   `str(credential_path())`. A data_dir swap invalidates on its own — the
   previous directory's entry simply sits under a different key and is never
   consulted again. Added
   `TestCacheContract::test_data_dir_swap_with_no_cache_reset_returns_correct_credential`,
   which swaps `settings.data_dir` twice mid-test with **no** explicit
   `_cache` reset and asserts each directory's own credential comes back.
   The Cache Contract docstring on `_read_credential_cached` and the
   `_cache` module comment were updated to describe path-keying explicitly.

2. **`resolve()` could create a credential and ran `ensure_dirs()` on every
   lookup.** `FileCredentialSource.resolve` called `get_credential()`, which
   calls `settings.ensure_dirs()` (a legacy-migration guard plus a `mkdir`
   syscall) and creates the credential file when absent. `gate-middleware`
   (two legs out) calls the resolution entry point inline on every request,
   including every static asset per DD6 — a single page load would have
   become dozens of `mkdir` syscalls and migration checks, and a lookup
   should not have the side effect of creating the thing it looks up.

   Fix: added `lookup_credential() -> LocalApiCredential | None`, a
   read-only entry point that does not call `ensure_dirs()` and does not
   create the file — it returns `None` when the file is absent, logging a
   warning (since a resolve-path miss on an absent file most likely
   indicates misconfiguration, not routine "wrong credential" traffic), and
   still lets `CredentialFileError` propagate uncaught for a malformed/empty
   *existing* file. `FileCredentialSource.resolve` now calls
   `lookup_credential()` instead of `get_credential()`. `get_credential()`
   is unchanged and remains the create-on-first-use entry point for the CLI
   rotate subcommand and the launcher/harness callers arriving in later
   legs. Added `TestReadOnlyResolvePath` (7 tests): resolve does not create
   a file when absent, resolve does not call `ensure_dirs()`, the same two
   properties asserted directly against `lookup_credential()`, `lookup_credential()`
   returns the stored credential when present, a credential created via
   `get_credential()` still resolves via the read-only path, and the
   absent-file warning is logged.

Neither fix touched a request path, `app.py`, `middleware.py`, or the
one-time handoff credential — both are internal to `the_one/api_credential.py`
and its test module, consistent with this leg's "enforces nothing" scope.

Verification: `tests/test_api_credential.py` — 36 passed (28 original + 8
new: 1 cache-contract, 7 read-only-resolve). Full `make test-unit` — 4169
passed, 10 skipped (up from 4161/10 by exactly the 8 new tests; no
regressions). `ruff check` and `ruff format --check` clean on both changed
files.

### Leg 04 `enforce-gate` — enforcement is live

**Status**: landed. The credential gate is registered on the real application,
outermost of `OriginAllowlistMiddleware`, with a comment recording why the order
matters. Leg 2's deliberate guard test
(`test_gate_middleware_is_not_registered_on_the_real_app`) was **inverted and
renamed** to `test_gate_middleware_is_registered_on_the_real_app_and_outermost`
rather than deleted and re-added, so `git blame` carries the intent shift.

Work done, in order:

1. **Pre-flip harness fix** (LD6) — browser fixtures now perform the handoff
   exchange (mint via the endpoint with the header credential, then follow the
   returned URL) to establish a real session cookie, once per app origin, in
   addition to the header. Plus a regression test asserting a **cookie-only**
   WebSocket connection succeeds against the real app.
2. **Registration** — one `add_middleware` call.
3. **Residuals** — see the failure chain below.

#### The first post-registration run: 125 browser failures

Recorded verbatim as the leg artifact required, because it is the leg's most
valuable diagnostic: `1 failed` (unit-side, none) / **`125 failed, 462 passed,
6 skipped`** on the browser lane, against a green unit suite.

Single root cause, and a mechanical one: **browser test files make raw `httpx`
calls inline in their own test bodies** — 52 call sites across 24 files — none
of which any prior survey had touched. Representative:

```python
r = httpx.get(f"{app_with_provider.base_url}/api/providers", timeout=5.0)
assert r.status_code == 200      # now 401
```

Fixed by adding `auth_headers_for(base_url)` to the existing
`tests/browser/_credential_registry.py` and applying it explicitly at each site.

**A global `httpx` monkeypatch was considered and deliberately rejected.** It
would have been one fixture instead of 52 edits, but on *this* mission it would
silently credential any test attempting to assert a 401 refusal — exactly the
tests this flight most needs to keep honest — and an invisible injector is not
greppable. Explicit edits were the right trade even at 52×.

#### Then 1 failure, then another

- `test_copy_button_writes_url_to_clipboard` — an **eleventh** browser-context
  implementation. `clipboard_page` built its own
  `browser.new_context(permissions=[...])` locally, bypassing the credentialed
  `page` fixture entirely. Fixed by factoring a shared credentialed-context
  helper in `conftest.py` taking `**context_kwargs`, which both local duplicates
  (this one and `test_markdown.py`'s) now call.
- `test_oauth_modal_flow.py::test_second_auth_required_event_navigates_popup_to_consent_url`
  — failed in one full run, **passes 6/6 in isolation**, and the file has not
  been touched by this flight (last commit predates it). Assessed as an
  order/timing flake rather than a credential break. Recorded rather than
  silently re-run until green.

#### The recurring lesson — four instances, one mistake

| Survey key used | Category it missed |
|---|---|
| `grep subprocess.Popen` | callers that *imported* the shared spawn helper |
| enumerate fixtures + seeders | inline `httpx` in test bodies (125 tests) |
| DD10's wording, "TestClient and direct-`httpx` sites" | 28 `ASGITransport` fixtures |
| the credentialed `page` fixture | 2 locally-defined `browser.new_context` duplicates |

Every one asked **"where is this pattern written?"** when the question was
**"who calls this API?"** Pattern-shaped surveys find pattern-shaped things.

The sharper tell: *each missed category was a duplicate of something already
surveyed.* Duplication is precisely what makes a call-graph question
un-answerable by grep — the duplicate does not share the searched-for token.

And the fix was the same every time, never "patch the missed caller" but
"collapse the duplicate onto the shared path." That is what converts a recurring
class of bug into a closed one, and it is why the last fix added a shared
context helper rather than crediting two contexts independently.

Carry to debrief: this generalizes past authentication to any cross-cutting
migration. The survey method should be call-graph-first, and existing
duplication should be treated as a *prerequisite to consolidate*, not an
inconvenience to work around.

### Leg 05 `operational-callers` — review fixes (post-implementation)

**Status**: landed, then reopened by the flight-end independent code review,
which found ONE BLOCKING defect and it was verified directly against the
running code before any fix was made.

**Finding**: the desktop launcher never performed the browser handoff (DD7).
`shell.py` built the window URL as a bare `http://{host}:{port}/` — no call to
`mint_handoff_credential()` existed anywhere in `the_one/interfaces/desktop/`
or `the_one/interfaces/app.py`/`main.py` (`grep -rn "handoff\|HANDOFF"`
returned zero hits before this fix). Once `enforce-gate` made
`CredentialGateMiddleware` live on the real app, the launcher's first
navigation carried no credential on any of the gate's three channels and was
refused with a 401 — `the-one app` showed an error instead of the UI. This is
the mission's flagship success criterion breaking silently.

**Why leg 05 itself didn't catch it**: this leg's scope is the launcher's
*outbound* HTTP calls — `_select_port`'s `/api/info` probe and the
`is_ours=True` focus POST — both credentialed correctly here and covered by
unit tests. The window's own document-request URL is a different kind of call
(the launcher navigating a browser control at itself, not calling an API) and
was never in this leg's Files Affected or Acceptance Criteria. DD7's handoff
mechanism and `mint_handoff_credential()`'s pinned wiring were built two legs
earlier (`gate-middleware`), with a docstring naming the launcher as the
intended caller — but no leg's acceptance criteria ever assigned "wire the
mint call into `shell.py`'s window URL" as a concrete task, so it fell through
the gap between "the function that mints" and "the caller that consumes it."
LD6 (below, in Decisions) audited the *browser-test harness* side of this same
mechanism and fixed a real gap there — but asserted, without checking, that
production already did the equivalent correctly. It did not; see the
correction appended to LD6.

**Fix** (`the_one/interfaces/desktop/shell.py`):
- Both navigation call sites — `webview.create_window()` inside `_boot()`
  (pywebview path) and `webbrowser.open()` (no-pywebview fallback) — now mint
  a fresh token via `mint_handoff_credential()` and build the URL as
  `f"{base_url}?{HANDOFF_QUERY_PARAM}={token}"`, importing both names lazily
  from `the_one.interfaces.web.handoff_store` at the point of use (matching
  this file's existing lazy-import convention for `webview`, `window_state`,
  and `tray`).
- Minting happens immediately before each navigation call, not earlier in the
  boot sequence: the token is single-use with a multi-minute TTL (DD12), and
  minting right after `_select_port` — before the splash screen and
  `_wait_until_serving`'s poll — would burn wall-clock time against that TTL
  for no benefit.
- The `is_ours=True` early-return branch (an existing instance already owns
  the port) still returns before either navigation call site is reached and
  does not mint — verified by a new test asserting `mint_handoff_credential`
  is not called on that path, matching its existing behavior of never opening
  a window.
- No changes to `middleware.py` or the gate's own logic — the defect and the
  fix are entirely in the launcher, not the gate.

**Tests** (`tests/test_desktop_shell.py`): the two existing happy-path tests
covering `create_window`'s and `webbrowser.open`'s URL construction now assert
the URL carries `?handoff=<64-hex-char token>`; the two `is_ours=True` tests
now assert `mint_handoff_credential` is **not** called. Before this fix, no
test in the file asserted anything about the URL's *content* — precisely why
the gap survived this leg's own implementation and unit suite undetected.

**Verification**: `tests/test_desktop_shell.py` — 24 passed. No new test
functions were added; the fix extended five existing tests (two happy-path
URL-content assertions, one fallback-URL assertion, and two `is_ours`
does-not-mint assertions) rather than duplicating their setup boilerplate.
Full `make test-unit` run after the fix — **4238 passed, 10 skipped, 676
deselected**, exit code 0; suite green, no failures. **Not verified end-to-end**: exercising the real
handoff (window opens, gate consumes the token, session cookie lands, UI
renders) needs a live GUI/webview backend, which this environment does not
have. That check is deferred to the operator's HAT session (Leg 8) per the
flight plan — this fix is verified at the unit level only, and that
limitation should not be read as "confirmed working in the real launcher."

### Leg 06 `behavior-test-apparatus` — documentation/convention only, no code touched

**Scope**: this leg is explicitly documentation-and-convention-only (DD13) — no
Python file, and nothing under `the_one/`, `tests/browser/`, `tests/*.py`,
`Makefile`, or `.github/` was touched, since another agent was concurrently
implementing Legs 1-5's code on this same branch. Files changed: `CLAUDE.md`,
`.flightops/agent-crews/behavior-tests-execution.md`, and Preconditions-only
edits across `tests/behavior/*.md`.

**`CLAUDE.md`**: added a "Behavior-test credential convention" section covering
(1) reading the long-lived credential from `<data_dir>/api-credential` verbatim,
(2) the two apparatus shapes — a browser-driving Executor mints a handoff URL via
`POST /api/session/handoff` (out-of-process; NOT the launcher's in-process
`mint_handoff_credential()`), a shell-only Executor attaches `Authorization:
Bearer <credential>` directly, (3) that a handoff credential is single-use and
short-lived so a second navigation needs a second mint, (4) that `/api/live`
needs no credential, and (5) the safety rule stated prominently: never target
port 8484 / the operator's default data directory — always a dedicated dev
instance, non-default port AND scratch data directory together (port alone is
not enough, since a non-default port still sharing the default data directory
shares the same credential file and sessions as production).

**Crew file**: `.flightops/agent-crews/behavior-tests-execution.md` got a new
"Credential convention" section plus a "CREDENTIAL & SAFETY" block inserted into
both the Executor's and Validator's Initial prompts, each restating the safety
rule and instructing `[BLOCKED:no-dev-instance]` rather than guessing a target —
belt-and-suspenders on top of `CLAUDE.md` auto-load, per the leg's own
instruction-vs-code trade-off note.

**Specs touched**: all **24** `active` specs' Preconditions, plus the one `draft`
spec named explicitly in the acceptance criteria
(`local-api-auth-session-lifecycle`) — **25 spec files** total, zero step-table
edits except the two described below. Breakdown of the 24 active specs:

- **8** literally defaulted to or allowed `:8484` and were corrected to a
  non-default port + scratch data directory: `agent-history-auto-purge`,
  `agent-purge-now-clears-history`, `agent-retention-setting-roundtrip`,
  `audit-log-inspector-renders-routing-entries`,
  `connector-inference-provider-config-roundtrip`, `discord-approval-flow`,
  `extended-thinking-tool-turn` (dropped its "or installed app on `:8484`"
  allowance), `shell-navigation-smoke` (its Preconditions literally defaulted to
  `:8484` before this fix).
- **8** named no port/instance at all (ambiguous enough to default to
  production by omission) and were given explicit non-default-instance
  guidance: `agent-governance-and-search` (already 8485, just needed the
  convention reference), `anthropic-plan-chat-parity`, `anthropic-plan-signin`,
  `connector-editor-ux`, `discord-slash-end-to-end`, `pty-session-containment`,
  `tool-sandbox-box-isolation`, `tool-sandbox-containment`.
- **6** already correctly targeted a non-default port with an explicit "never
  touch 8484" — only the CLAUDE.md convention reference was added:
  `chat-roundtrip`, `connector-editor-keyboard-a11y`, `save-preserves-config`,
  `studio-agent-crud`, `system-provider-config`, `vision-round-trip`.
- **2** Windows specs (`windows-desktop-presence`, `windows-native-frame-splash`)
  were deliberately left targeting `:8484` — that is the installed app's own
  default port, and these specs test the packaged installer's real default
  behavior on a **dedicated Windows test host**, not the operator's daily-driver
  machine. Their Preconditions now say this explicitly and point at where the
  credential file lives on that host.

For specs whose Steps literally hardcode `http://localhost:8484` inline (not
just their Preconditions) —`agent-purge-now-clears-history`,
`agent-retention-setting-roundtrip`, `audit-log-inspector-renders-routing-entries`,
`connector-inference-provider-config-roundtrip`, `discord-approval-flow` — the
Steps table itself was **not** edited (DD13); instead each spec's Preconditions
now say explicitly that every literal `8484` appearing anywhere in that spec is
a placeholder for the actual dev-instance base URL, never a literal instruction.

**Two specs resisted a pure-Preconditions fix; recorded rather than forced**:

1. `windows-native-frame-splash.md` Step 9 opens `http://localhost:8484/` in a
   **separate plain browser** with no prior handoff of its own (distinct from
   the app's own authenticated webview exercised by the surrounding steps).
   Under the live gate this browser holds no session cookie and the page will
   be refused, not "render normally" as the Expected Result currently states.
   Flagged in the spec's Preconditions as a known gap; not fixed here per the
   leg's Preconditions-only scope.
2. `discord-approval-flow.md` and `discord-slash-end-to-end.md` depend on
   whichever the-one instance holds the live, warm Discord bot connection —
   infrastructure the operator controls, not something a behavior-test run
   spins up fresh. If that instance happens to be the operator's persistent
   `:8484` deployment, forcing a dedicated non-default-port instance would
   break the spec's actual mechanism (no live bot on it). Preconditions now
   frame this as an explicit operator decision made with full awareness, never
   a default the spec assumes — this is a scope/authorization finding about
   the convention, not a Preconditions-fixable gap.

**Non-active specs (9 of 33)**: deliberately left out of scope, except
`local-api-auth-session-lifecycle` (named explicitly in the acceptance
criteria). The other 8 — `chat-loop-hang-and-cancel` (draft),
`discord-engagement` (draft, still names `:8484`), `discord-multi-agent-routing`
(draft), `discord-multi-channel-routing` (draft), `discord-multi-user-routing`
(draft), `gemma-tool-use-recovery` (retired), `studio-smoke` (archived, still
names `:8484`), `windows-pty-parity` (draft) — were left untouched. Rationale:
drafts get a full precondition review at promotion time regardless (they are
unfinished by definition), and archived/retired specs are not going to run
again, so pre-fixing them now is scope creep this leg doesn't need. Residual
risk, accepted: an operator who manually runs one of these against a
live-gated instance today must apply the CLAUDE.md convention by hand, since
the spec file itself doesn't yet reference it.

**`local-api-auth-session-lifecycle.md`** (the spec that tests the credential
machinery itself) had genuinely drifted from what Legs 1-5 built: Steps 6 and
14 described navigating to a handoff URL "as the launcher would construct it"
— i.e., via the launcher's in-process `mint_handoff_credential()`, which an
out-of-process behavior-test Executor cannot reach. Corrected both steps to
describe the actual mechanism an Executor uses: `POST /api/session/handoff`
with the long-lived credential, then navigate to the returned URL. This is the
one spec where a step-table edit was appropriate — DD13's "no credential step
in the step table" restriction is about *consumer* specs inheriting the
convention silently; this spec's whole purpose is to exercise the credential
mechanism directly, so its steps must describe that mechanism correctly.

**Not done in this leg execution**: the leg's last acceptance criterion — a
representative existing spec **actually run** via `/behavior-test` against a
live-gated dev instance — was explicitly excluded from this leg's scope by the
orchestrating instructions (needs a dev instance and an operator, and the
shared test apparatus was in use by concurrent Leg 1-5 work). Verification for
this leg was by inspection only. The actual run remains a follow-up once Legs
1-5 land and a dev instance is available.

### Leg 07 `security-model-and-docs` — documentation only, last autonomous leg

**Scope**: documentation-only, as instructed. No Python file touched; nothing
under `the_one/`, `tests/`, `Makefile`, `.github/`, or `.flightops/` changed.
Files changed: `SECURITY-MODEL.md`, `packaging/windows/README.md`,
`CLAUDE.md`, `.env.example`. `docs/windows-install.md` was checked
(`grep -n "unauthenticated\|api/info\|api/live\|credential"`) and found to
carry none of the staleness the leg artifact flagged for
`packaging/windows/README.md` — left unmodified.

**`SECURITY-MODEL.md`** — the substantive revision the mission's own success
criterion names:

- **F3 Decision 10 revised, not deleted**, under "Threat Model": records that
  Mission 20 (issue #165) reconsidered it, states what it originally
  justified (a fully unauthenticated local API), why that collapsed in
  practice ("operator-trusted" became "any local process, trusted or not"),
  and what replaced it (the credential gate). The filesystem-actor premise
  itself — inherited by F4/F5/F6 for the tool-execution boundary — is
  recorded as unchanged; only the auth conclusion drawn from it changed.
- **`## Authentication` rewritten** — no clause of the old "no auth by
  design" text survives. New content: what the posture protects against
  (other OS accounts, lower-privilege local processes, browser-vectored
  access including plain `GET`) and what it does not (a process running as
  the operator can read `<data_dir>/api-credential` and has full access —
  stated as the mission's deliberate boundary, not a gap); the single
  exemption (`GET /api/live`) and why `/api/info` was rejected for it (it
  returns `base_prompt`); the two-credential distinction (long-lived
  file-backed vs. single-use short-lived handoff) with the query-parameter
  channel restricted to `GET /`; the stateless HMAC session cookie and why
  rotation drops every session; `SameSite=Strict` and why `Lax` would reopen
  the GET-side rebinding gap; and the DD4 layering (401 before Origin logic,
  403 for a valid credential from a disallowed origin).
- **Origin-allowlist paragraph reframed** as a layer beneath the credential
  gate rather than the alternative to it, with its "GET / missing-Origin
  passes through" note reframed as the gap the gate now covers — see the
  correction below for the one place this needed a second pass.
- **Future Work "multi-user form factor" entry rewritten** to name what
  remains (per-user identity, tool isolation, encryption keys) now that
  per-request auth for the single-user case has landed, rather than
  describing a change that already partially happened.
- **Secrets section correction**: `POST /api/encryption/rotate` was
  documented as "gated by the Origin-allowlist middleware" only; corrected
  to name the credential gate first, since it is now the outer and primary
  check on that route.

**Verification catches worth recording** (found during the "read the
revision against the actual implementation" pass, not anticipated by the leg
artifact):

1. **A first-draft claim that bootstrap callers use `/api/live` to avoid
   needing a credential was wrong for two of the three callers named.**
   Grepping `the_one/interfaces/desktop/shell.py`,
   `tests/browser/conftest.py`, the `Makefile`, and
   `.github/workflows/windows-installer.yml` for `api/live`/`api/info`
   showed only the desktop launcher's own just-started-server poll
   (`_wait_until_serving`) and the browser-test harness's readiness wait
   actually use the unauthenticated `/api/live`. `make verify-serving` and
   the desktop launcher's `_select_port` ownership classifier both
   deliberately use the **credentialed** `/api/info` — they're answering
   "is that instance mine," not "is anything up yet," and DD11 requires the
   credential for that question. The first draft had named `make
   verify-serving` and `_select_port` as `/api/live` bootstrap examples;
   corrected to attribute the liveness-probe pattern only to the two actual
   readiness-wait call sites, and to state explicitly that the
   ownership-question callers use the credentialed endpoint on purpose.
2. **A second overclaim in the same paragraph**: "nothing reaches the
   Origin-allowlist layer without a valid credential first" is false for one
   path — `/api/live` itself bypasses the credential check by construction
   (`EXEMPT_PATHS` short-circuits straight to `self.app`, i.e. through the
   Origin-allowlist middleware to the route) and only isn't blocked there
   because `GET` was never gated by that layer to begin with. Corrected to
   name the exemption as the one path that reaches that layer without the
   gate having checked it first, rather than claiming an absolute.

Neither catch was in the leg artifact's list of "what currently says X, must
change to Y" — both surfaced only from re-reading the draft against
`the_one/interfaces/desktop/shell.py`, `tests/browser/conftest.py`, the
`Makefile`, and `middleware.py`'s actual control flow, which is what the leg's
own verification step exists to catch.

**`packaging/windows/README.md`**: the `/api/info` probe description at the
CI packaged-smoke section corrected — it now states the probe is
credentialed (matching `.github/workflows/windows-installer.yml`'s current
`get_credential()` + `Authorization: Bearer` code, read directly rather than
assumed) and explains why `/api/info` rather than `/api/live` is the right
probe for that step (it asserts on response content — the version — not just
liveness).

**`CLAUDE.md`**: one new paragraph added to the "Testing" section (before the
existing browser-tests paragraph), naming the credential gate as the likely
cause of an unexpected 401 in a new ad-hoc test or manual `curl`, and pointing
at the two existing shared-credential helpers
(`tests/_credential_helpers.py::auth_headers()`,
`tests/browser/_credential_registry.py::auth_headers_for()`). Leg 6's
"Behavior-test credential convention" section (further down the same file)
was left untouched — confirmed via `git diff` that the new paragraph sits
above it with no overlap.

**`.env.example`**: the `THE_ONE_DATA_DIR` comment now notes that the
credential file lives in that directory alongside the database, since moving
`data_dir` moves the credential with it and that wasn't previously stated
anywhere an operator configuring the env file would see it.

**`grep -rn "unauthenticated"`** across the repo (docs + code) after all
edits: the only remaining hits describe the current design accurately — the
one-time handoff credential being "refused as unauthenticated" once consumed
(`CLAUDE.md`), `/api/live` being "the one unauthenticated route" (`CLAUDE.md`,
matches `EXEMPT_PATHS`), the `/api/info` rejection rationale in the new
`packaging/windows/README.md` text, and the F3 Decision 10 history in
`SECURITY-MODEL.md`. No stragglers found beyond the two files the leg artifact
already named.

Verification was by inspection only, as instructed (no code changed; `make
test-unit`/`make test-browser` deliberately not run, per the leg's
instruction not to interfere with another agent's verification run). Every
code reference added (`the_one/api_credential.py`, `middleware.py`'s
`LIVENESS_PATH`/`EXEMPT_PATHS`/`SESSION_COOKIE_NAME`/layering comment,
`handoff_store.py`'s TTL and query-param name, `app.py`'s route registrations,
`shell.py`'s two readiness/ownership call sites, `main.py`'s CLI subcommand
list) was re-read from the current tree during this pass, not carried over
from the leg artifact's own citations.

## Decisions

### LD1 — Three presentation channels; the query parameter carries only the one-time credential

**Context**: The flight's DD7 fixed *how* a browser gets a session (a one-time
credential on the first document request) but never enumerated the channels the
gate accepts a credential from. Leg 2 cannot be built without that enumeration,
and the choice has direct security consequences.

**Decision**: exactly three. `Authorization: Bearer` carries the long-lived
credential for every non-browser caller; an `HttpOnly` session cookie carries an
opaque session value for the browser after a handoff; a query parameter on a
document request carries the one-time handoff credential and **nothing else**.
The long-lived credential is never accepted from a query parameter.

**Impact**: This is what makes the two-credential design pay for itself. A URL is
the one channel that reliably leaks — into shell history, server logs, browser
history, referrers — so only a value that is worthless after one use may travel
there. It also settles how `enforce-and-migrate-harness` migrates the Playwright
lane: browser contexts set `extra_http_headers` with the long-lived credential
and need no handoff at all.

### LD3 — The session cookie is stateless and bound to the current long-lived credential

**Context**: Leg 2's design review found that the leg specified the session
cookie only as "opaque," never saying what it is checked against — while the
only store the leg described building was the per-process, in-memory *handoff*
store. An implementer extending that same pattern to sessions would have shipped
per-process sessions, which fail behavior-test step 11 (session survives a
server restart), and no acceptance criterion in the leg would have caught it.

**Decision**: there is no session store. The cookie is
`<nonce>.<HMAC-SHA256(key=long-lived secret, msg=nonce)>`, verified on every
request by recomputing the HMAC against whatever `lookup_credential()` returns at
that moment, with a constant-time comparison.

**Impact**: satisfies both behavior-test constraints simultaneously and for
free. A fresh process reading the same on-disk credential recomputes an
identical HMAC and authorizes (step 11 passes); `rotate_credential()` changes the
secret so the HMAC stops matching on the very next request, inside the
one-request staleness bound Leg 1's Cache Contract already guarantees (step 13
passes, with no restart). Rotation necessarily drops *every* session at once,
which is exactly what the mission's revocation criterion asks for. No capability
is granted to an attacker: forging a cookie requires reading the credential
file, and anyone who can do that could simply present the credential.

The flight spec pointed at this without stating it — DD12's closing note that
the restart-survival criterion "is about the established *session*, which
outlives the process because the long-lived credential does" only makes sense
if session validity derives from the credential. That the note existed and was
still not enough to prevent the gap is worth remembering at debrief.

### LD6 — The browser test harness must establish a session cookie, not just send a header

**Context**: a pre-flip audit before `enforce-gate` found that
`harness-credential-plumbing`'s chosen strategy — authenticate every browser
navigation with an `Authorization` header — structurally cannot cover the
WebSocket channel. Three facts, each verified directly:

- `the_one/interfaces/web/static/js/areas/chat.js` opens the chat socket with a
  bare `new WebSocket(...)`. A native browser `WebSocket` cannot set request
  headers; this is a WHATWG API restriction, not something the app can work
  around.
- The gate's WebSocket path accepts a session cookie or an `Authorization`
  header, and deliberately has no query-parameter channel (LD1 scopes that to
  document requests).
- `grep -rn handoff tests/browser/` returns **nothing**. No browser test drives
  the handoff exchange, so no browser test ever holds a session cookie.

Playwright's `set_extra_http_headers` is also documented not to apply to the WS
upgrade in Chromium, so the header channel could not reach it even if `chat.js`
were changed.

Chat is the default area, so nearly every browser test triggers a WS upgrade.
Left alone, the enforcement flip would have reddened most of the browser suite —
turning the split's entire purpose, a near-zero red window, into exactly the long
ambiguous one it was created to avoid.

**Decision**: browser fixtures perform the handoff exchange (mint via the
endpoint with the header credential, then `GET /?<handoff>`) to establish a
session cookie, once per app instance, keeping the header as well for
non-document fetches. Folded into `enforce-gate` as a pre-flip step rather than
reopening a landed leg.

**Impact**: this raises harness fidelity rather than working around a problem.
Production was always correct — the launcher navigates to a handoff URL and the
same-origin WS handshake carries the resulting cookie for free. It was only the
test harness that took a shortcut the real path does not take, and the fix makes
the harness exercise the production flow.

> **Correction (Leg 05 flight-end review, recorded here rather than silently
> rewritten)**: the sentence above — "Production was always correct — the
> launcher navigates to a handoff URL" — was an unverified assumption, not a
> checked fact, and it was **wrong**. The launcher did not construct a handoff
> URL at all until the Leg 05 review fix: `shell.py` built the window URL as a
> bare `http://{host}:{port}/`, with no call to `mint_handoff_credential()`
> anywhere in `the_one/interfaces/desktop/`. Once `enforce-gate` made the gate
> live, the launcher's own first navigation would have hit a 401 — the exact
> failure mode this LD6 entry describes fixing for the *browser-test harness*
> was, unnoticed, still live in *production*. The flight-end independent code
> review caught it by reading `shell.py` directly rather than trusting this
> paragraph; see the Leg 05 review-fixes entry above (in Leg Progress) for the
> fix and its verification. The lesson for debrief: this LD6 entry fixed the
> harness side of a gap and asserted, without checking, that the production
> side needed no equivalent fix — the same "trust the design intent instead of
> reading the caller" mistake DD7 itself exists to guard against.

**Why Leg 3's own acceptance test missed it**:
`tests/browser/test_app_spawn_credential_wiring.py` asserts the credential
matches on the **document** request and never opens a socket. The leg's criteria
were about *which* credential reached *which* app instance, and were silent on
*which channel* each protocol requires. A criterion can be fully satisfied and
still not cover the thing that breaks.

### LD5 — The session cookie is `SameSite=Strict`, not `Lax`

**Context**: Leg 2's second design review found that `SameSite=Lax` — which the
leg specified before review, as an unexamined default — reopens the exact gap
this mission exists to close. `Lax` attaches a cookie to cross-site *top-level
navigations* using a safe method; that is the one case `Lax` does not restrict.
`OriginAllowlistMiddleware` never gates `GET` (`middleware.py`, `GATED_METHODS`
excludes safe methods, with a comment explaining that SOP already protects read
responses). So once a session existed, a hostile page could top-level-navigate
the operator's browser to a loopback `GET` path, arrive carrying a valid
session, and no origin check would run. LD3's sessions have no expiry, so the
exposure would persist until manual rotation.

**Decision**: `SameSite=Strict`, asserted by an acceptance criterion rather than
left as an implementation detail.

**Impact**: verified to break nothing — the redirect that sets the cookie has
nothing to send yet, the launcher's initial handoff navigation is browser/OS-
initiated with no cross-site initiator, and every later request originates from
the app's own loaded page. Worth noting at debrief that this was a *default*
rather than a decision, and that the flight's own reconnaissance had already
recorded "the GET-side rebinding gap is genuine" — the finding was available
from material already in the artifact and still took a second review cycle to
surface.

### LD4 — Cookie-authenticated requests are attributed to a distinct session source

**Context**: LD3's HMAC check recovers no source or identity on its own, and the
leg had pinned `IdentifiedCaller`-on-`scope` only for the header path — leaving
the majority of real browser traffic with unspecified identity.

**Decision**: synthesize `IdentifiedCaller(identifier=<verifying credential's
identifier>, source="session")`. Naming the channel honestly beats reporting
`source="file"`, which would claim the request presented the file credential
when it did not.

**Impact**: records a limitation rather than hiding it. A session minted by a
non-file source is still keyed to the file credential, because LD3 binds the
HMAC to `lookup_credential()`. No non-file source exists outside tests this
flight, so nothing is affected now — but "which credential does a session
outlive" becomes a real question when the MCP automation surface lands, and this
is where it will need answering. The mint endpoint deliberately does not
restrict which source may authenticate it; forcing file-only would encode an
assumption this flight has no grounds to make in either direction.

### LD2 — An authenticated mint endpoint, alongside the in-process mint function

**Context**: Reconnaissance during Leg 2 design established that the desktop
shell runs uvicorn on a daemon thread *in its own process*, so DD12's
per-process in-memory handoff store is directly callable by the launcher. But it
also established that two callers need a handoff URL from **outside** the server
process, which an in-process-only mint cannot serve:

- `tests/browser/conftest.py:app_clean` spawns the server via
  `subprocess.Popen([... "-m", "uvicorn" ...])` with an isolated
  `THE_ONE_DATA_DIR` — it holds the long-lived credential but shares no memory
  with the server.
- The behavior test `local-api-auth-session-lifecycle` needs a handoff URL
  twice: at step 6 against a `serve`-started instance, and again at step 14 for
  a *fresh* URL after rotation, with no server restart between steps 12 and 14.
  A mint-once-at-startup scheme cannot supply the second.

**Decision**: handoff credentials are minted two ways into the same per-process
store — a function the launcher calls directly, and a new endpoint that mints
one for a caller already authenticated with the long-lived credential. The
endpoint authenticates in-route via `resolve_caller`, not via the middleware, so
an unauthenticated mint endpoint never exists even transiently on this branch. A
handoff credential may not be used to authenticate a mint request, or one leaked
URL would become an unbounded session generator.

**Impact**: Adds a route the flight spec did not anticipate. It does not weaken
the posture — it converts a credential the caller already holds into a strictly
weaker, single-use, short-lived one — and it does not contradict DD9's "no
endpoint", which governs *rotation* and whose rationale (not prematurely
encoding "there is exactly one token") does not apply to minting a session
handoff.

**Alternatives rejected**, recorded so they are not re-proposed:

- *Derive the handoff value deterministically from the long-lived credential* so
  any holder can construct one. Rejected: a restart would then **un-consume** a
  spent value, which is the exact trap DD12 was written to close.
- *Have the browser set the session cookie via JavaScript.* Impossible — the
  cookie must be `HttpOnly`.
- *Mint once at server startup and print the URL.* Attractive and simpler, but
  defeated by behavior-test step 14's post-rotation re-mint with no restart.

## Deviations

### `enforce-and-migrate-harness` split into two legs

**Planned**: one leg registering the gate on the real app *and* migrating the
pytest harness, designated "the only leg permitted to go red mid-flight."

**Actual**: split into `harness-credential-plumbing` (credential every harness
caller with the gate still unregistered; suite stays green) and `enforce-gate`
(one `add_middleware` call and one inverted test). Flight leg count goes 7 → 8.

**Reason**: the leg's design review verified, against the working tree, that the
migration surface is materially larger and differently shaped than the flight
spec's reconnaissance recorded. Counted directly:

- **10** browser app-spawn implementations, not one. Beyond
  `tests/browser/conftest.py:app_clean`, there is a module-scoped
  `app_clean_module` in `test_markdown.py` and an `app_with_data_dir` fixture
  **duplicated across 8 `test_flow_*.py` files**, each with its own
  `subprocess.Popen` and its own local readiness poll against `/api/info`. Both
  the flight spec and the leg's first draft assumed fixing `app_clean` covered
  the browser suite; it covers one of ten.
- **252** seeder call sites, via 4 functions in `tests/browser/seeders.py` plus
  2 inline helpers in `conftest.py`. These issue raw `httpx` **from the pytest
  process**, so the leg's own proposed mechanism — Playwright
  `extra_http_headers` — cannot reach them at all; that header covers
  browser-originated requests only.
- **34** unit-test client fixtures, of which **28** use
  `httpx.AsyncClient(transport=ASGITransport(app=app))`. DD10's wording is
  "`TestClient` and direct-`httpx` call sites," and these match neither term
  while going through the full ASGI stack and therefore being fully gated. An
  implementer working from DD10's language alone would have missed all 28.

**Why split rather than expand.** The flight's trip-wire — divert if
centralization fails and the work degenerates into per-call-site edits — is
**not** met: the mechanism still holds (consolidate the ten spawn paths;
resolve the seeders' credential from the `base_url` they already receive, so the
252 call sites are untouched; one shared helper adopted one line at a time
across the 34 fixtures). But doing that plumbing *and* the enforcement switch
together would mean a long red window across ~50 files with no way to tell a
migration bug from an enforcement bug. Plumbing first, with credentials sent to
a server that does not yet check them, keeps the suite green throughout and
reduces the switch to a change whose failures are unambiguous.

**Impact on the flight's leg-count deviation**: it widens. The spec already
recorded seven legs against a one-to-four guideline and noted the honest reading
— that this flight carries two risk clusters, designing an auth model and
migrating an ecosystem to it — adding that "the second cluster kept growing
under review" was evidence for that reading. This is a third instance of exactly
that growth, and it strengthens rather than weakens the case. The split is the
right local call; the flight-level reading stands.

## Anomalies

### Browser lane became non-deterministic after the gate went live

**Observed**: three consecutive full `make test-browser` runs against the same
tree produced *different* failure sets, with the count growing:

| Run | Result | Failures |
|---|---|---|
| A | 1 failed / 586 passed | `test_copy_button_writes_url_to_clipboard` |
| B | 1 failed / 586 passed | `test_oauth_modal_flow::test_second_auth_required_event_navigates_popup_to_consent_url` |
| C | 5 failed / 582 passed | 2× `test_flow_admin_navigation`, `test_flow_admin_tools_grid`, `test_flow_studio_mcp_editor`, and run B's oauth test again |

Run A's failure was **real** — the `clipboard_page` local-context gap — and is
fixed. Runs B and C are the anomaly.

**Severity**: degraded. Not blocking correctness; the gate itself behaves
deterministically and the unit suite is stable at 4236 across every run.

**Evidence gathered**: all five of run C's failures pass in isolation — a
combined run of the four affected files gives **70 passed** in 1m57s. None of
those test files' own logic was touched by this flight; only shared fixtures in
`tests/browser/conftest.py` were. So this is not a deterministic credential
defect.

**Most plausible mechanism, stated as hypothesis rather than conclusion**: the
Leg 4 pre-flip fix adds **two extra HTTP round trips per browser context** (the
handoff mint plus the redirect-following exchange). Across ~587 browser tests
that is upwards of a thousand additional requests in a ~14-minute run. Tests
whose Playwright `expect(...)` assertions sit near the default 8s timeout would
become more likely to exceed it as machine load rises. That mechanism predicts
exactly what was seen: no single reproducible failure, a failure *set* that
varies run to run, and everything passing when run in a small fast subset.

If that is right, the flight has not broken these tests but has **narrowed their
timing margin**, which is a genuine cost of the design and should be recorded as
such rather than dismissed.

**Explicitly not established**: whether this lane was already flaky before the
flight. That baseline was not measured, and without it the attribution above
stays a hypothesis. Determining it requires running the browser lane on the
pre-flight tree.

**Corroborating evidence, gathered after the above was written**: a fourth full
run, on an **idle machine with no subagents or concurrent suites**, against the
byte-identical tree that produced run C's five failures, returned
**587 passed, 6 skipped, 0 failed** in 13m44s. No code changed between run C and
run D — only machine load. That is direct support for the load-sensitivity
mechanism and against a logic defect, though it still does not establish the
pre-flight baseline.

| Run | Machine state | Result |
|---|---|---|
| C | loaded (concurrent subagents + suites) | 5 failed / 582 passed |
| D | idle, same tree | **0 failed / 587 passed** |

> ## ⛔ SUPERSEDED — the load hypothesis above is WRONG, and this flight is
> ## responsible for the instability. Read this block before anything above it.
>
> Two later measurements demolished the load-sensitivity story:
>
> **1. An idle run failed.** Run 11, on a quiesced machine at the final tree,
> returned **7 failed / 580 passed** — different tests again, all passing in
> isolation. "Idle ⇒ green" rested on two data points and did not survive a
> third.
>
> **2. The pre-flight baseline is CLEAN.** The decisive measurement, finally
> taken: `git checkout 54d2d56` (this flight's planning commit — code identical
> to pre-flight `main`, `the_one/api_credential.py` absent) and a full
> `make test-browser` returned **586 passed, 6 skipped, 0 failed** in 13m31s, on
> the same machine, same venv, same Playwright.
>
> **Conclusion: the browser lane was stable before this flight and is not stable
> after it. The instability is attributable to this flight's changes.** Not to
> machine load, and not to pre-existing flakiness. Every "load-sensitivity"
> claim above is retained only as a record of a wrong turn — it should not be
> cited as a finding.
>
> **Consequence for landing**: the flight's own Post-Flight verification
> requires the browser lanes green, and mission criterion 9 requires the unit
> *and browser* suites to pass with authentication enforced. That criterion is
> **not met**. The flight does not land on this evidence.
>
> **Leading hypothesis, untested**: the gate performs a `path.stat()` plus a
> credential resolution on *every* request, and under DD6 that includes every
> static asset — a page load that pulls 20+ assets now does 20+ extra
> filesystem checks and HMAC verifications. Added to that, Leg 4's fix performs
> a handoff mint plus exchange per browser context. None of this is
> individually large, but the browser suite's `expect()` assertions default to
> an 8s timeout, and the failures are consistently timing-shaped: never
> reproducible in a small isolated run, never the same test twice.
>
> **Candidate directions** (for the operator to choose between, not for the
> Flight Director to pick unilaterally): memoize the session-cookie
> verification so a valid cookie skips the stat-and-HMAC path; reconsider DD6's
> gating of `/static` on cost grounds; perform the handoff once per app
> instance rather than once per browser context; or raise the browser lane's
> default expect timeout, which treats the symptom rather than the cause.
>
> **Methodological note worth carrying to the debrief**: this baseline
> measurement costs 14 minutes and was available from the first moment the word
> "flake" was used. It was deferred through *four* separate assessments, two of
> which were stated to the operator with more confidence than the evidence
> supported. When attribution is the question, measure the baseline first —
> a cheap decisive experiment beats an accumulating narrative every time.

**Full tally across the flight** — every full `make test-browser` run, in order.
The correlation between machine load and failure count is the finding; note that
the *identity* of the failing tests changes almost every time, and that no test
has ever failed in a small isolated re-run:

| # | Context | Loaded? | Result | Real defect? |
|---|---|---|---|---|
| 1 | Leg 3 | yes | 1 failed | **yes** — 11th `_spawn_app` caller |
| 2 | Leg 3 refix | mostly idle | 0 / 587 | — |
| 3 | Leg 4 flip | yes | 125 failed | **yes** — inline `httpx` category |
| 4 | Leg 4 fix | yes | 1 failed | **yes** — `clipboard_page` context |
| 5 | Leg 4 fix 2 | yes | 1 failed | no |
| 6 | Leg 4 confirm | yes | 5 failed | no |
| 7 | Leg 4 confirm, quiesced | **no** | **0 / 587** | — |
| 8 | Leg 5 | yes | 4 failed | no |
| 9 | flight-end + reviewer | yes | 1 failed | no |
| 10 | flight-end + re-reviewer | yes | 5 failed | no |

Every genuine defect (runs 1, 3, 4) was reproducible and stayed failing until
fixed. Every non-defect failure appeared only under load, differed run to run,
and passed in isolation. Both idle runs were clean.

Worth stating plainly: this means **a loaded run's failure list cannot be read
as a regression signal without isolating each failure first.** During this
flight that distinction was the difference between finding three real bugs and
chasing a dozen phantoms.

**Resolution**: mechanism supported but attribution still open; the pre-flight
baseline remains unmeasured. Deliberately **not** handled by
re-running until a green result appeared — that would have converted a real
signal into a false record of stability. Carried to the debrief as an open
question, with two candidate follow-ups: measure the pre-flight baseline to
settle attribution, and consider whether the handoff exchange can be performed
once per *app instance* rather than once per *browser context*, which would cut
the added round trips substantially.

## Session Notes

### Merged `origin/main` into the flight branch — 2026-08-07

Four commits, merged cleanly with **zero file overlap** against the flight's
changes:

- `3326abd` — fix: stop MCP streamable-HTTP sessions dying 30s after they open
- `57e2776` — version bump to 0.5.0
- `a55babd` — CVE floors raised: `aiohttp>=3.14.3`, `cryptography>=50.0.0`
- `d39e1ec` — merge of PR #167

**The merge risk that mattered** was new tests written against the pre-auth
world, which would 401 under the live gate. Checked explicitly: none of
`tests/test_mcp_transport_timeouts.py`, `tests/test_mcp_client.py` or
`tests/test_mcp_pool.py` construct a `TestClient` or `ASGITransport` against
this app — they are all outbound-MCP tests. No migration needed.

**A self-inflicted error worth recording**, because it would have silently
invalidated any test result taken in that window: the first sync used a bare
`uv sync`, which drops the `dev` optional-dependency group and removed `pytest`,
`playwright`, `pytest-asyncio`, `pytest-timeout` and `ruff` from the venv. The
correct invocation for this project is `uv sync --extra dev --extra all-llms`.
Note that `--all-extras` does **not** work here: the `gui` extra pulls
`pywebview[gtk]` → `pygobject` → `pycairo`, which needs system cairo headers and
fails to build. `pywebview` is therefore genuinely absent from this venv, which
matches the pre-merge state — the desktop tests mock it.

Post-merge dependency state verified: `cryptography` 49.0.0 → **50.0.0**,
`aiohttp` 3.14.1 → **3.14.3**. The `cryptography` major bump was treated as a
real risk rather than a formality, since `the_one/encryption.py` builds Fernet
on it.

**Post-merge verification**: `make test-unit` **4252 passed / 10 skipped** (up
14 from 4238 — exactly main's new MCP tests). `make test-browser` **587 passed /
6 skipped / 0 failed**.

**That single green browser run does not clear the regression recorded in
Anomalies.** Runs 2 and 7 of this flight were also green and were followed by
failures; one observation cannot establish stability for a lane whose whole
problem is intermittency. Repeat runs are in progress; the verdict belongs with
their outcome, not with this note.

One hypothesis the merge raises, stated as such: `3326abd` fixes MCP
streamable-HTTP sessions dying and reworks the connection pool, and
`test_flow_studio_mcp_editor` was the single most frequent repeat offender
across the failing runs, with `test_oauth_modal_flow` (MCP OAuth) close behind.
It is plausible that main independently fixed a real contributor. But roughly
half the observed failures were in areas untouched by MCP — admin navigation,
agent tabs, dirty-confirm modals, the provider editor — so this can be at most a
partial explanation, and attributing the whole regression to it would repeat
exactly the over-confident pattern this flight has already fallen into twice.

{Freeform notes.}

---

## Flight Director Notes

### Flight start — 2026-08-05

- Phase file loaded: `.flightops/agent-crews/leg-execution.md` — structure valid
  (`## Crew`, `## Interaction Protocol`, `## Prompts` all present with fenced
  blocks). Crew: Developer (Sonnet), Reviewer (Haiku), optional Accessibility
  Reviewer (Sonnet, not applicable to this flight — no user-facing UI changes).
- Git strategy `branch` per ARTIFACTS.md. Branch `flight/01-authenticated-local-api`
  created off `main` at `5df53b2`-equivalent tip; planning artifacts committed as
  the flight baseline so the flight-end Reviewer's "changes since last commit"
  scopes to implementation, not planning.
- Flight status advanced `planning` → `in-flight` directly. The intermediate
  `ready` state was not separately recorded because operator approval and
  execution start were the same act.
- Prerequisite "dedicated dev instance on a non-default port" deliberately left
  open at flight start. It gates `operational-callers` and the behavior test,
  not `credential-foundation` or `gate-middleware`, both of which are pure unit
  work. Recorded here so it is not mistaken for an unnoticed gap.
- Review cadence per the current methodology: design review is risk-tiered
  per leg; code review and commit are deferred until after the last autonomous
  leg. Legs 1–6 are therefore implemented uncommitted on top of the baseline.

### Leg 01 `credential-foundation` — risk tier: HIGH

Rationale: it is a security-sensitive surface (the credential primitive the
whole flight rests on), and it introduces a cache with a correctness-relevant
freshness requirement. Either alone would tier it high. Design review runs
before implementation.

Two findings from the leg-design risk checks, recorded because both would
otherwise have been discovered during implementation:

1. **Cache freshness — a real gap in the flight spec.** The behavior test
   rotates the credential (step 12) and expects the *already-running* server to
   drop the pre-rotation session (step 13), with no restart between them. No
   design decision covered how a reader notices an out-of-process rotation. A
   read-once-at-startup credential store passes every unit test in leg 1 and
   fails that step. The leg artifact now carries an explicit Cache Contract:
   source of truth is the file, the single rebuild trigger is a `stat` identity
   change (`st_mtime_ns` + size, not `st_mtime` — a rotate can complete inside
   one second's resolution), and maximum staleness is one request. Noted there
   that `encryption.py`'s `_encryptor_cache` is the wrong pattern to copy: it
   caches by `data_dir` with no invalidation, correct for a key rotated through
   an in-process API and wrong for one rotated by a separate process.

2. **A false alarm worth recording so it is not re-raised.**
   `tests/test_auth_posture_probe.py` reads, by name, like a test pinning the
   current unauthenticated posture — the kind the risk checks require inverting
   or renaming when a leg breaks the behavior they pin. It is not. It covers
   `the_one.mcp.transports.streamable_http._probe_auth_posture`, which
   classifies the auth posture of *outbound* MCP servers the-one connects to.
   Unaffected by this flight; must not be modified. The leg artifact says so
   explicitly.

**Design review outcome** — one cycle, *approve with changes*. All five issues
applied; a second cycle was deliberately skipped because every change was the
reviewer's own prescription applied verbatim, adding no new design for a second
pass to evaluate. The two high-severity findings are worth recording, since both
are Windows-specific and neither was visible from the code the leg design read:

1. The `0600` mode assertion needed a POSIX guard. The codebase's own adjacent
   precedent — `tests/test_encryption.py:TestGetEncryptor.test_key_file_permissions`
   — wraps the identical assertion in `skipif(os.name != "posix")`, because
   Windows synthesizes `st_mode` from a single read-only bit and does not model
   owner/group/other. The leg design had cited `encryption.py` twice as the
   file-creation anti-pattern without looking at its sibling test file.
2. The new test module must be registered in the curated Windows lane —
   `ci/tasks/windows-tests.yml` and its documented mirror, the `windows` job in
   `.github/workflows/test.yml`. Both carry a MAINTENANCE comment requiring it
   for platform-divergent tests, and `tests/test_encryption.py` is already
   listed. Without it, the leg's single highest-risk property (`st_mtime_ns`
   across an `os.replace`) would go unverified on real Windows, and the first
   signal would be a red `main` pipeline *after* the flight lands — that lane
   runs on push to `main` only, so nothing on this branch exercises it.

Three medium findings, all corrections to the Cache Contract's reasoning rather
than to its conclusion: size is a no-op signal for a fixed-length token and must
not be treated as a second independent leg of the guard; the mtime comparison
must be `!=` and not `>`, because `st_mtime_ns` is wall-clock and a backward NTP
step would otherwise defeat the guard for exactly the one request the staleness
bound exists to cover; and the create-race edge case described the wrong
mechanism — `O_EXCL` guards the uniquely-named temp file and produces no
"loser," while `os.replace` onto the canonical path is last-write-wins and
raises nothing, so no `FileExistsError` arises anywhere in this design.

**Forward commitment carried to `gate-middleware`**: the review observed that
this leg's in-memory-source seam test proves only half of mission criterion 7 —
that a second source *can* resolve, not that the gating logic is indifferent to
which one did. Leg 2's design must assert that the middleware reaches the
credential module through the single resolution entry point with no per-source
branching. Recorded here so it survives the gap between leg designs.

### Leg 02 `gate-middleware` — risk tier: HIGH

Rationale: the flight's central security surface; it introduces a state machine
(one-time credential: issued → consumed → expired) whose reachability matters;
and it settles two design questions the flight spec left open (recorded as LD1
and LD2 under Decisions). Design review runs before implementation.

Risk checks: no schema or migration changes. State-machine reachability — the
one-time credential's states are the leg's own new machine, and the leg design
requires a test proving a fresh store cannot resurrect a spent value, which is
the reachability property that matters. Cache freshness — no new cache; the leg
consumes Leg 1's, and the leg artifact explicitly forbids `get_credential` on
the request path so Leg 1's read-only/create split is not silently undone.
Interface changes — the gate is new and unregistered, so it has no consumers
yet; the two new routes are additive. No existing test pins the unauthenticated
posture of this API (checked again; `tests/test_auth_posture_probe.py` remains
about outbound MCP servers).

**Design review outcome — two cycles, escalated.** Cycle 1 returned *approve
with changes*; its high finding was that the session cookie's binding was
unspecified while the only store the leg described was per-process, so an
implementer would plausibly have shipped sessions that die at restart, failing
behavior-test step 11 with no acceptance criterion to catch it. Fixed by LD3.

Cycle 2 returned **needs rework**, which is the methodology's escalation
trigger. Its findings were *new* — raised against the LD3 material that did not
exist during cycle 1 — rather than unresolved items persisting across rounds, so
the escalation is a checkpoint for operator visibility rather than a signal that
review has stalled. All findings applied: LD5 (`SameSite=Strict`), LD4 (caller
identity for cookie-authenticated requests), the query-parameter channel
restricted to document requests with a non-consuming refusal elsewhere, plus
acceptance assertions for the `SameSite` value, HEAD/OPTIONS on the liveness
path, and notes recording that the nonce is not a security control and that the
absent `Max-Age` is deliberate.

Worth carrying to debrief: `SameSite=Lax` entered the artifact as an unexamined
default rather than a decision, and the flight's own reconnaissance table
already recorded "the GET-side rebinding gap is genuine." The evidence needed to
catch it was sitting in the flight artifact and it still took a second review
cycle. Defaults inside a security surface deserve the same defence as choices.

### Legs 03/04 after the split — risk tiers and review disposition

Both tier **HIGH**: `harness-credential-plumbing` is a shared-interface change
across roughly 50 files, and `enforce-gate` flips enforcement live and inherits
the licence to go red.

**No fresh design review was run against the split artifacts, deliberately.**
The review that produced the split *is* the design review for this material — it
enumerated the full migration surface with counts I then verified independently
against the working tree (10 app-spawn implementations, 252 seeder call sites,
34 unit-test client fixtures, all confirmed). A fresh reviewer would be
re-deriving findings already incorporated. `enforce-gate` will be reviewed on its
own terms before it runs, since its scope is defined by what the plumbing leg
actually leaves behind rather than by what this design predicts.

The note below is retained as written for the pre-split leg, since its risk
checks (test inversion, the deferred open question, the readiness probe, the
overstated `httpx` count) apply unchanged and are now distributed across the two
legs.

### Leg 03 `enforce-and-migrate-harness` — risk tier: HIGH *(pre-split; superseded)*

Rationale: it flips enforcement live on the real app; it is a shared-interface
change with roughly 76 candidate consumers; and it is the only leg authorized to
go red mid-flight. Every tier-high trigger fires at once.

Risk checks run at design time:

- **Test inversion.** Leg 2 deliberately left a test asserting the gate is
  *absent* from the real app's middleware stack — a guard against accidental
  early registration. This leg makes that assertion false by design, so the leg
  artifact requires it be **inverted and renamed** rather than deleted and
  re-added, keeping the intent shift in `git blame`. This is the risk check's
  "tests that pin behavior the new design breaks" case, caught before
  implementation rather than during.
- **The deferred open question is now answerable, and the answer is to avoid
  the race rather than resolve it.** The flight deferred "does the per-test
  credential become readable before the readiness probe fires?" to this leg.
  Reading `tests/browser/conftest.py:app_clean` settles it: the fixture creates
  the isolated `data_dir` itself and only then spawns the server, so writing the
  credential *before* `subprocess.Popen` removes the ordering question entirely.
  The leg artifact explicitly forbids the alternative — polling for server-side
  creation — which would reintroduce exactly the race the deferral flagged.
- **`_wait_for_ready` polls `/api/info`**, which is credentialed from this leg
  onward. It must move to the liveness endpoint. This is DD5 earning its
  keep: the exemption exists so bootstrap probes work before a credential is
  presented, and this is the first caller to need it.
- **The migration surface is smaller than the raw counts suggest.** Roughly 69
  test files reference `httpx`, but many use `httpx.MockTransport` to stub
  *outbound* calls to LLM providers and MCP servers and never touch this API.
  The leg artifact says to migrate what actually calls this app and leave
  outbound-mock sites alone, so the ~76 figure is not mistaken for a work
  estimate.
- No schema or migration changes. No new cache.

**The flight's trip-wire lives in this leg.** The spec pre-declares a divert if
centralizing credential handling into fixtures fails and the migration
degenerates into per-call-site edits. The leg artifact instructs the implementer
to stop and escalate rather than grind through the sites, because that outcome
is evidence for the flight-splitting reading its own leg-count note already
records as likelier.

Also checked and clear: no schema or migration changes in this leg; no
state-machine or lifecycle values introduced beyond the identified-caller type;
the only interface change is a new `elif` branch on `cli_entry`, whose sole
test-side consumer (`tests/test_frozen_entry.py`) mocks `cli_entry` wholesale
and asserts nothing about dispatch branches. The subcommand list in
`packaging/windows/README.md` is a documentation consumer and is in the leg's
scope.

---

## Reconnaissance Report

Source artifact: GitHub issue #165, which cites specific code locations. Each
cited item verified against current `main` before leg design.

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| API fully unauthenticated; F3 Decision 10 is the canonical citation | `confirmed-live` | `SECURITY-MODEL.md:14-16,20-23` | Real work; DD3/DD4 |
| Origin allowlist gates only mutating methods + WS upgrades, so GETs pass | `confirmed-live` | `middleware.py:57` `GATED_METHODS = {"POST","PUT","PATCH","DELETE"}`; `:81` gates only those | Real work; the GET-side rebinding gap is genuine |
| API reaches `shell` / `python_exec` over plain loopback HTTP | `confirmed-live` | `app.py:357-362` — single middleware, then full router | Real work |
| M19 stores plan-provider OAuth tokens in the DB | `confirmed-live` | Mission 19 debrief; encrypted at rest but reachable via the unauthenticated API | Real work; motivates the mission |
| Persist token at `{data_dir}/api-token`, mode `0600`, "same handling as `encryption.key`" | `partially-satisfied` — premise drifted | `encryption.py:78,104` uses write-then-`chmod`; `api.py:4892-4896` uses `os.open(..., O_EXCL, 0o600)` *because* the former "has a brief world-readable window" | **Do not** follow `encryption.key`'s handling as the issue says; follow `api.py`'s. Captured as DD2 |
| Exempt a `/health`-style probe for the launcher port classification | `confirmed-live` but **rejected as specified** | `/api/info` returns `base_prompt` (`app.py:1985-1987`), not just version | Exemption is right; the endpoint named is wrong. Captured as DD5 |
| Browser handoff via `?token=` → cookie → redirect | `confirmed-live` | Pinned webview exposes no cookie-injection method and no header parameter on window creation; shell owns the URL (`shell.py:497,615`) | Real work — and the *only* available mechanism, not merely the chosen one. DD7 |
| `tests/browser/conftest.py` fixtures need the per-instance token | `confirmed-live`, larger than stated | `conftest.py:112-190` spawns uvicorn per test with isolated data dir; 59 files consume `base_url`; ~56 direct `httpx` sites bypass any shared client; no authenticated-client fixture exists in `tests/conftest.py` | Real work; drove DD10 |
| `_select_port`'s connect-probe must work against the authenticated server | `confirmed-live` | `shell.py:223-261` classifies by reading version from `/api/info` | Real work; DD11 — and the change *improves* classification |
| AIAT lane needs a token env var or file lookup | `confirmed-live` | `tests/test_aiat.py:33`; `tests/live/discord_hat/config.py:99` | Real work |
| `the-one doctor` listed as a client needing the token | `already-satisfied` — **not a client at all** | `the_one/diagnostics.py` contains no HTTP client; its only `subprocess` use (`:69`) is a child-spawn check | Retire from the client inventory |
| *(not in issue)* `make verify-serving` | `confirmed-live` — **missed by the issue** | `Makefile:112-140` curls `/api/info` and loops 18 `/static/js/areas/*.js` asserting 200 | Add to scope — breaks under DD5 *and* DD6 |
| *(not in issue)* CI packaged-smoke | `confirmed-live` — **missed by the issue** | `.github/workflows/windows-installer.yml` step (b) makes a bare `httpx.get` to `/api/info` with no credential handling | Add to scope. Step (c) calls `_select_port` through the `the_one/interfaces/app.py:7-9` shim and inherits the shell's behaviour |
| Connectors as API clients | `already-satisfied` — not clients | No HTTP client anywhere under `the_one/connectors/*.py`; they run in-process | Retire from the client inventory |
| *(not in issue, missed by mission review)* Existing behavior-test specs | `confirmed-live` — **whole caller category missed** | ≥10 `active` specs under `tests/behavior/` navigate a browser straight to the app root with no credential step — `shell-navigation-smoke.md`, `chat-roundtrip.md`, `agent-history-auto-purge.md`, `agent-purge-now-clears-history.md`, `agent-retention-setting-roundtrip.md`, `connector-inference-provider-config-roundtrip.md`, `discord-approval-flow.md`, `audit-log-inspector-renders-routing-entries.md`, `windows-desktop-presence.md`, `windows-native-frame-splash.md`; several target the default port | Add to scope via a runner-level credential mechanism, not per-spec edits. DD13 |
| *(not in issue)* Desktop window-focus forward | `confirmed-live` | `shell.py:493` `httpx.post(.../api/window/focus)`, fired when `_select_port` finds an existing instance — a third shell call site beyond the readiness poll and classifier | Itemize explicitly in the operational-callers leg |
| *(not in issue)* Stale CI comment | `drifted` | `.github/workflows/windows-installer.yml:8` claims unit-test CI "still runs on every PR / main push"; `test.yml:9` is `workflow_dispatch` only — routine CI moved to local Concourse | Pre-existing drift, not caused by this flight; correct opportunistically in the docs leg |
| *(not in issue)* Docs describing the unauthenticated probe | `confirmed-live` | `docs/windows-install.md:89`, `packaging/windows/README.md:202-204` describe the same unauthenticated `/api/info` check | Correct in the docs leg so documentation does not describe retired behaviour |
