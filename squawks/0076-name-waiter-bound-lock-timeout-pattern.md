# Squawk 0076: Name the waiter-bound lock-timeout shape in `agents.md` conventions

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: —

## Report

Flight 5 established a non-obvious concurrency shape and documented it only
locally, inside the `vectors` package: **bound only the wait to acquire a
lock, never the work done while holding it.**

The reason is specific and was measured, not reasoned: `UsearchStore.query`
does its work as `async with entry.lock: await asyncio.to_thread(...)`.
Cancelling that await releases the caller **and the lock** while the pool
thread is still reading the index, and the next holder then mutates it. The
probe: caller free and lock released at 0.302 s, escaped thread still running
at 1.502 s. The failure mode is a corrupt sidecar or a segfault inside a C
extension — unlogged and unrecoverable in-process.

The correct shape has three parts, each of which an "obvious" refactor would
break: the bound wraps `lock.acquire()` only; the acquire sits **outside**
the `try` whose `finally` releases (inside, every timeout raises
`RuntimeError: Lock is not acquired` and masks the real error); and the
resulting error is a **sibling** of the staleness error, not a subclass
(`manager.py` answers staleness with a full rebuild, so inheritance would
turn a transient busy query into a rebuild storm).

This project already names patterns in `agents.md`'s Project Conventions
(`supervised-per-entity-worker`, `leg-staged-hook-seam`,
`structural-Protocol-satisfaction`, …), typically after a second occurrence.
Naming this one now, with a single instance and the history fresh, is
cheaper than reconstructing it when a second one is half-remembered.

**One residual worth stating in the convention**: the protection today is
textual and test-based, not structural. Leg 1's `wait_for`-absence assertion
is scoped to `retrieval.py` only, so a *new* call site elsewhere could wrap
`store.query(...)` in `wait_for` and reintroduce the hazard, with nothing but
code review to catch it. Acceptable with one caller; worth naming as the
boundary of what the documentation guarantees.

## Evidence

`the_one/vectors/usearch_store.py::UsearchStore.query` — docstring carries
the design, the probe numbers and the `RuntimeError` trap.
`the_one/vectors/_store.py` — `VectorStoreBusyError(VectorStoreError)` and
the Protocol contract.
`tests/test_vector_store.py::test_timeout_expiry_raises_busy_without_cancelling_in_lock_work`
— asserts against a real lock that the original holder still holds it after a
timed-out waiter backs off.

## Corrective Action

*(written at completion)*

## Verification

*(written at completion — expected: the convention appears in `agents.md`'s
Project Conventions with a name, the rule, and a pointer to the instance)*

## Sign-Off

*(written at completion)*
