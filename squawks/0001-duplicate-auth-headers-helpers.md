# Squawk 0001: Three duplicate `auth_headers` implementations in the browser test harness

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-08
**Completed**: 2026-08-29

## Report

Mission 20 Flight 01 left three near-identical implementations of "resolve the
credential registered for a base URL and build an `Authorization: Bearer` header
dict". All three have the same body:

- `tests/browser/_credential_registry.py:auth_headers_for` — public
- `tests/browser/conftest.py:_auth_headers_for` — private
- `tests/browser/seeders.py:_auth_headers` — private

The duplication is known and deliberate: the private copies exist to avoid a
circular import between `conftest.py` and `seeders.py`, and their docstrings
cross-reference each other. So this is not a bug — nothing is broken, and all
three are correct today.

It is logged because the flight's own debrief identified duplication-that-hides-
callers as the root cause of every missed caller category during the enforcement
flip (five separate instances, one of which shipped a broken flagship criterion).
The flight diagnosed that failure mode and then reproduced a milder version of it
in its own harness. Three copies of a six-line function is exactly the shape that
made `grep` unable to find callers, and the next change to credential handling
has to remember all three.

## Evidence

```
tests/browser/_credential_registry.py:auth_headers_for
tests/browser/conftest.py:_auth_headers_for
tests/browser/seeders.py:_auth_headers
```

Flight debrief, "What Could Be Improved → Technical":
> The flight then reproduced this failure mode in its own harness. […] the same
> shape that caused every missed-caller category above.

## Corrective Action

Checked the actual import graph before touching anything: `_credential_registry.py`
imports only `the_one.api_credential` (confirmed leaf — nothing from `conftest`
or `seeders`). `conftest.py` already imported `credential_for` directly from
`_credential_registry`, and `seeders.py` already imported `credential_for as
_credential_for` from it too — so the "circular import" the report flagged as a
live concern for `seeders.py` turned out not to exist for this function either:
both modules could import `auth_headers_for` directly with no alias needed.

Deleted `conftest.py:_auth_headers_for` and `seeders.py:_auth_headers` (both
6-line bodies, byte-identical to `_credential_registry.py:auth_headers_for`,
including the `{}` fallback when no credential is registered) and replaced both
with `from browser._credential_registry import auth_headers_for`, updating each
file's call sites (`_auth_headers_for(base_url)` / `_auth_headers(base_url)` →
`auth_headers_for(base_url)`) in place — no signatures changed. Updated the
docstrings in `_credential_registry.py` that cross-referenced the two now-
deleted private copies by name. No second body was kept anywhere — a single
public implementation now backs all three former call sites.

## Verification

- `grep -rn "def _auth_headers\b\|def _auth_headers_for" tests/browser` — no
  matches (both private definitions gone).
- `grep -rn "auth_headers_for\|_auth_headers(" tests/browser | wc -l` — 108
  matches, all resolving to the one public `auth_headers_for` definition and
  its callers/imports across `conftest.py`, `seeders.py`, and the ~30 test
  modules that already imported it directly; no `_auth_headers(` (private
  call syntax) matches remain.
- `THE_ONE_DEV_MODE=true PYTHON=.venv/bin/python bash scripts/run-tests.sh -m
  browser tests/browser/test_flow_admin_rotate_flash.py
  tests/browser/test_app_spawn_credential_wiring.py -x --timeout 120 -q` — 3
  passed.
- Additionally ran `tests/browser/test_seeders.py` and
  `tests/browser/test_app_fixture.py` (exercise `seeders.py` and `conftest.py`
  auth paths directly) — 4 passed.
- `.venv/bin/ruff check .` and `.venv/bin/ruff format --check .` — both clean
  across the whole repo.
- The full `make test-unit` / `make test-browser` suites (the squawk's own
  broader bar) were not run standalone here — the Flight Director runs the
  whole suite once at the end of the batch to avoid double-running and test
  contention across squawks in this session.

## Sign-Off

*(written at completion)*

## Disposition

*(n/a while open)*
