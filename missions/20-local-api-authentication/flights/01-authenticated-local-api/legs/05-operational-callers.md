# Leg: operational-callers

**Status**: landed
**Flight**: [Authenticated Local API End-to-End](../flight.md)

## Objective

Credential the four non-test caller categories that break the moment the gate is
live: the desktop shell's three call sites, `make verify-serving`, the CI
packaged-app smoke check, and the live/AIAT lane.

## Context

Mechanically the simplest leg in the flight — each item is an existing HTTP call
that gains a credential. Two exceptions carry real design content and are called
out below: DD11's redefinition of "is that instance ours," and a credential-leak
hazard in the Makefile target that the naive fix introduces.

Design decisions implemented: **DD11** (single-instance classification uses the
credentialed `/api/info`), **DD5** (liveness for pure readiness probes), and
**DD6** (the 18-path asset loop needs the credential too).

### Prior-leg learnings

- `the_one/api_credential.py` — `get_credential()` is the create-on-first-use
  entry point and is correct for these callers, which run outside the request
  path. Do **not** use the request-path-only `lookup_credential` here.
- Leg 3 established the pattern for reading a credential out of a specific data
  directory; reuse rather than re-invent.
- `/api/live` is the unauthenticated liveness endpoint.

## The four categories

### 1. Desktop shell — three call sites, and they are not the same

`the_one/interfaces/desktop/shell.py`:

- **`_wait_until_serving`** polls `/api/info` waiting for its *own* just-started
  server. This is a pure readiness probe → move it to **`/api/live`**. It does
  not need a credential at all, and using the exemption here is exactly what
  DD5 created it for.
- **`_select_port`** probes `/api/info` and treats `200 + matching version` as
  "ours." Under DD11 this becomes **credentialed**: send the credential and
  treat success as "shares our credential," which is what "ours" should always
  have meant. This is strictly better than today — the current version-only
  check misclassifies a *different* instance running the same version on a
  different data directory as ours. Keep the retry/startup-window behaviour.
  Note the three-way outcome is unchanged: free, ours, or foreign; a foreign
  server that also 401s simply resolves to "not ours," which is the safe answer.
- **The window-focus POST** (`/api/window/focus`, in the `is_ours=True` branch)
  needs the credential. Easy to miss because it sits in the branch that returns
  early without opening a window. The flight's reconnaissance flagged this one
  specifically.

### 2. `make verify-serving` — and a credential leak the obvious fix creates

The target curls `/api/info`, then loops **18 static asset paths** (gated under
DD6), then does a pid-ownership check. All the curls need the credential.

**Do not put the credential in a curl argument.** On Linux `/proc/<pid>/cmdline`
is world-readable, so `curl -H "Authorization: Bearer $$(cat …)"` publishes the
credential to every local account for the lifetime of each of the 19 curl
processes — defeating, in the verification target itself, the exact protection
this mission exists to add. `/proc/<pid>/environ` by contrast is owner-only, so
passing through an exported shell variable and referencing it inside the header
string is materially safer. Safer still is `curl --config <file>` with a
`0600` file holding the header. Pick one deliberately and say why in a comment —
a future contributor will otherwise "simplify" it back to `-H`.

The pid-ownership check needs no credential; leave it alone.

### 3. CI packaged-app smoke

`.github/workflows/windows-installer.yml` probes the frozen build. Same
treatment; prefer the liveness endpoint if the probe is only asking "did it come
up," and credential it if it asserts anything about content.

### 4. Live / AIAT lane

`tests/test_aiat.py` reads `THE_ONE_TEST_URL`, **defaulting to
`http://localhost:8484`** — the operator's production instance. Its `test_health`
hits `/api/info`, and other tests POST `/api/chat`. All need the credential,
read from the data directory of whichever instance `THE_ONE_TEST_URL` points at.
`tests/live/discord_hat/*` gets the same treatment.

**Safety note that outranks this leg's convenience**: the `-m live` lane must
never be pointed at the operator's production instance during verification. Do
not run it as a verification step for this leg; make the code change and verify
by inspection plus whatever unit-level coverage is reachable.

## Acceptance Criteria

- [ ] `_wait_until_serving` polls `/api/live` and needs no credential.
- [ ] `_select_port` sends the credential to `/api/info` and classifies
      "ours" as "shares our credential" (DD11), preserving the existing
      three-way free/ours/foreign outcome and the startup-retry window.
- [ ] The window-focus POST sends the credential.
- [ ] `make verify-serving` passes with the gate live — the `/api/info` probe,
      all 18 asset paths, and the pid-ownership check.
- [ ] **The credential never appears in any process's command line.** Assert by
      inspecting the target: no credential value in a `curl` argument.
- [ ] The CI packaged-smoke probe authenticates (or uses the liveness endpoint
      where it is only checking that the process came up).
- [ ] `tests/test_aiat.py` and `tests/live/discord_hat/*` send the credential.
- [ ] `make test-unit` and the browser lanes stay green.
- [ ] Unit coverage exists for the `_select_port` classification change — it is
      the one item here with real logic, and it decides whether a second app
      instance is launched.

## Verification Steps

- `make test-unit`; browser lanes via the Makefile's `test-browser` target.
- `make verify-serving` against a **dedicated dev instance on a non-default
  port**, never the operator's `:8484`.
- Read the Makefile diff to confirm no credential in argv.
- **Do not run `-m live`.**

## Edge Cases

- **`_select_port` when the credential file does not exist yet** — first launch
  on a fresh machine. It must not crash; a missing credential means "cannot be
  ours."
- **A foreign server that returns 200 on `/api/info`** — without the right
  credential it is not ours. Already the safe answer, but assert it.
- **The `is_ours=True` branch is the one that never opens a window** — it POSTs
  focus and returns. A credential failure there should log, not crash; the
  existing code already tolerates a failed focus POST.
- **`verify-serving` running when no credential exists** — should fail with a
  clear message, not an opaque 401 loop for 30 seconds.

## Files Affected

- `the_one/interfaces/desktop/shell.py` — three call sites.
- `Makefile` — `verify-serving`.
- `.github/workflows/windows-installer.yml` — packaged smoke.
- `tests/test_aiat.py`, `tests/live/discord_hat/*`.
- Unit tests for the `_select_port` change (`tests/test_desktop_shell.py`
  already exists and covers `_wait_until_serving`).

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md

> Commit is deferred to the flight-end review gate. Do **not** commit and do
> **not** signal `[COMPLETE:leg]`.
