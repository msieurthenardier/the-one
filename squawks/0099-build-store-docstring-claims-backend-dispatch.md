# Squawk 0099: `_build_store`'s docstring claims it constructs the backend named by settings; it hardcodes `UsearchStore`

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-22
**Completed**: 2026-11-03
**Related**: 0096, 0098: docstring and doc claims that overstate the knowledge/vector code; complete together ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report

`_build_store`'s docstring says it constructs "the backend named by
`vector_store_settings`". It reads `dtype` and `dim` from those settings but
ignores `.backend` entirely and always returns `UsearchStore`.

Harmless today — `VectorStoreSettings.backend` is `Literal["usearch"]`, so there
is nothing else to name. It matters because this is the seam a second backend
would arrive through, and the docstring describes dispatch that does not exist,
which is how the next reader mis-plans that work. Same family as squawks 0096
and 0098: documentation asserting behaviour the code does not implement.

## Evidence

- `the_one/vectors/__init__.py:70` — "Construct (but do not open) the backend
  named by ``vector_store_settings``."
- `the_one/vectors/__init__.py:76-78` — `from the_one.vectors.usearch_store import UsearchStore` / `return UsearchStore(conn, dtype=..., dim=...)`; `.backend` is never read.

## Corrective Action

`_build_store`'s docstring (`the_one/vectors/__init__.py`) now says it constructs the one
production backend, `UsearchStore`, with `dtype`/`dim` from settings, and that `.backend`
is not read.

## Verification

Read-back: the docstring matches the body.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
