# Squawk 0001: Three duplicate `auth_headers` implementations in the browser test harness

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-08
**Completed**: —

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

*(written at completion)*

Suggested shape, not prescribed: collapse to a single implementation. The
circular import is the real constraint — one option is to have `seeders.py`
receive the registry (or the header dict) as a parameter rather than importing
it, breaking the cycle without a second copy. The implementer should pick the
approach after reading the actual import graph.

## Verification

The existing unit and browser suites already exercise all three call paths —
`make test-unit` and `make test-browser` green is sufficient, plus a grep
confirming one definition remains.

## Sign-Off

*(written at completion)*

## Disposition

*(n/a while open)*
