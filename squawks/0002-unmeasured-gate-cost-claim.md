# Squawk 0002: Gate's per-request cost is asserted in a docstring, never measured

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-08
**Completed**: 2026-08-29

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

Measured with a throwaway micro-benchmark (session scratchpad, not committed —
not in the repo per the scope note): an isolated temp data dir, a credential
written the same way `tests/test_api_credential.py` writes one
(`get_credential()`, which creates-on-first-use), the default file source
registered, then `resolve_caller(presented)` timed over 20,000 iterations for
(a) the warm cache-hit path (same credential repeatedly — the per-request
production case) and (b) a wrong-credential miss, via `time.perf_counter_ns`.
Run 3 times; middle run reported. A bare `stat()` on the credential file was
timed for reference.

Result: the claim holds and is a significant underestimate of the actual
margin — the measured cost is roughly two orders of magnitude below "sub-
millisecond," not merely under the 1ms bar. Docstring updated at
`the_one/api_credential.py:resolve_caller` (~line 455) with the measured
figure, the date, the one-sentence method, and the machine class, keeping the
original "sub-millisecond" claim structure intact rather than replacing it
(the measurement supports it, so no softening or escalation is warranted).

## Verification

Benchmark output (middle of 3 runs, N=20,000 iterations each, `the_one`
`resolve_caller`, Linux/WSL2 local disk):

```
cache-hit   median=6.251us  p99=14.673us
wrong-cred  median=5.773us  p99=13.001us
bare stat() median=0.981us  p99=1.301us
```

The docstring now cites this figure, the date, and how it was obtained.

`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_api_credential.py -x --timeout 60` — passing.
`.venv/bin/ruff check .` and `.venv/bin/ruff format --check .` — passing.

## Sign-Off

*(written at completion)*

## Disposition

*(n/a while open)*
