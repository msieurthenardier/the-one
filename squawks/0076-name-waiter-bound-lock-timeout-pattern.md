# Squawk 0076: Name the waiter-bound lock-timeout shape in `agents.md` conventions

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: 2026-09-18

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

Added `### \`waiter-bound-lock-timeout\`` to `the_one/agents.md`'s Project
Conventions (`### Project-wide` block), immediately after
`remote-cap-needs-a-negative-test` and before `### Mission-specific (M16)` —
matching that entry's density (rule paragraph, then a residual/scope
paragraph, then a citation paragraph naming files and tests). The convention
states the rule (bound only the wait to acquire a lock, never the work held
under it) and the three parts an "obvious" refactor would break: the bound
wraps `lock.acquire()` only; the acquire sits outside the `try` whose
`finally` releases; the resulting error is a sibling of the staleness error,
not a subclass. The residual paragraph states the protection is textual and
test-based, scoped to `retrieval.py` only, per the Report.

Also updated two existing agents.md passages that already described this
instance so they point at the new convention name rather than leaving the
rule unnamed nearby: the "Knowledge storage" section's `SEMANTIC_QUERY_TIMEOUT`
sentence now names `waiter-bound-lock-timeout` inline, and the "Knowledge
retrieval" crash-window sentence cross-references the new
`multi-await-reads-are-not-snapshots` convention (squawk 0078, same spawn) —
kept together since both squawks touch the same paragraphs.

Did not touch `the_one/vectors/usearch_store.py`, `_store.py`, or the test
file — the squawk's ask is a naming/documentation change in Project
Conventions, not a code change; the existing docstring and test already
carry the design and the probe numbers, and are now cited by name from the
new convention entry rather than duplicated.

## Verification

`the_one/agents.md` Project Conventions now contains `### \`waiter-bound-lock-timeout\``
with the rule, the three-part shape, the residual, and citations to
`UsearchStore.query`, `VectorStoreBusyError`/`VectorStoreStaleError`'s
sibling (not subclass) relationship, and
`tests/test_vector_store.py::test_timeout_expiry_raises_busy_without_cancelling_in_lock_work`
plus `tests/test_kb_retrieval.py::test_no_wait_for_anywhere_in_the_module` (the
residual's textual guard, confirmed scoped to `the_one/knowledge/retrieval.py`
only). `make lint` (`ruff check` + `ruff format --check` via
`.venv/bin/python -m ruff`) is clean. No code changed, so no behavioral test
run was required; `tests/test_kb_retrieval.py` (31 tests) still passes as a
sanity check for the same-spawn 0077/0078 doc edits touching adjacent
paragraphs.

## Sign-Off

**Reviewer**: batch Reviewer agent (**Sonnet** tier — the diff touches the encryption-rotation endpoint and a dependency floor for a package inside the shipped frozen closure, both security-sensitive surfaces per `.flightops/agent-crews/leg-execution.md`, even though every change is comment-, doc- or version-only)
**Verdict**: confirmed
**Commit**: `PENDING`
