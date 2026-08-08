# Squawk 0002: Gate's per-request cost is asserted in a docstring, never measured

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-08
**Completed**: —

## Report

`the_one/api_credential.py:resolve_caller` documents the credential gate's
per-request cost as "a `stat` plus an occasional read is sub-millisecond on local
disk". That claim justified a real design decision — making the resolution entry
point synchronous so `gate-middleware` could call it inline on every request,
including every static asset under DD6 — but nothing anywhere measures it. There
is no benchmark in `tests/test_api_credential.py` or `tests/test_credential_gate.py`.

The number is very probably right. On a cache hit the cost is one `stat()`
syscall, a dict lookup, and an HMAC over ~16 bytes, against tens-to-hundreds of
microseconds of existing ASGI overhead. The flight also measured +13 seconds on a
13.5-minute browser suite for the entire gate, which is consistent.

It is worth measuring anyway because this exact mechanism is what the flight spent
three rounds of investigation wrongly blaming for browser-lane instability — the
strongest argument in the whole flight record for measuring rather than reasoning.
An assertion that survives in a docstring becomes a fact future engineers build on.

**Scope note**: this is deliberately "measure once and record the real number",
**not** "add a permanent performance test". A perf assertion in the suite would be
timing-sensitive and flaky, and choosing how to make one stable would be a design
decision — which would take this outside squawk scope.

## Evidence

`the_one/api_credential.py:resolve_caller` — docstring:
> Synchronous is deliberate […] a `stat` plus an occasional read is
> sub-millisecond on local disk — not worth an executor hop.

No benchmark exists: `grep -rn "benchmark\|perf_counter" tests/test_api_credential.py
tests/test_credential_gate.py` returns nothing.

Flight debrief, "What Could Be Improved → Technical":
> "Sub-millisecond" is asserted, never measured. […] the flight's own three-round
> attribution failure was about this exact mechanism.

## Corrective Action

*(written at completion)*

Measure the per-request cost once — e.g. time N gated requests against a
throwaway app with and without the middleware, run locally and discarded — then
replace the qualitative claim with the measured figure and the conditions it was
taken under. If the measurement contradicts the claim, that is the finding, and
it should be escalated rather than quietly reworded.

## Verification

The docstring cites a real number and how it was obtained. `make test-unit` green
(no behavioural change expected — this touches a docstring only).

## Sign-Off

*(written at completion)*

## Disposition

*(n/a while open)*
