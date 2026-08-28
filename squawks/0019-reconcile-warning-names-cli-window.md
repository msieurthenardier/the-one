# Squawk 0019: Reconcile WARNING doesn't name the CLI-window loss; "undecidable → promote" invariant uncommented

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-28
**Completed**: 2026-08-28

## Report

`resolve_pending_key` already WARNs when sampled ciphertext decrypts only under the canonical
key while a pending key is promoted — which is exactly the documented "CLI process wrote rows
under the old key during a crashed rotation" loss — but the message doesn't say so, so an
operator can't connect the log line to the `agents.md` trade-off note. Separately, the
"nothing decidable → promote" branch is correct only because the sidecar is written before the
DB commit (a `.next` with no decidable rows means nothing was re-encrypted that matters); that
invariant is not named at the branch. Rename the warning text to mention the CLI window and add
the invariant comment (and, if cheap, a test named for the failure mode the branch is not
vulnerable to).

## Evidence

- `the_one/encryption.py:resolve_pending_key` — `logger.warning(...)` at ~`:262` with `under_canonical_only`
- `the_one/agents.md` "Encryption-rotation invariant (seven corpora)" — CLI-window trade-off paragraph
- Debrief 2026-08-28, "What Could Be Improved → Technical"

## Corrective Action

- `the_one/encryption.py:resolve_pending_key` — reworded the promote-branch WARNING
  (`under_canonical_only > 0`) to name the loss explicitly: "…sampled ciphertext(s)
  decrypt only under the retiring canonical key and will become unreadable after
  promotion — the documented CLI-window loss (a process that kept encrypting under
  the old key during an interrupted rotation); see agents.md 'Encryption-rotation
  invariant'". Counts stay in the message; no key bytes are logged.
- `the_one/encryption.py:resolve_pending_key` — added a comment at the
  "nothing decidable → promote" branch naming the invariant that makes it safe: the
  sidecar is written before the DB commit (`rotate_encryption_key` step 3b, in
  `the_one/interfaces/web/api.py`), so a `.next` with no decidable ciphertext means a
  fresh DB, residue-only rows, or a rotation that crashed before commit — in every
  case nothing was re-encrypted under a key that promotion would lose.
- `the_one/agents.md` "Encryption-rotation invariant (seven corpora)" — appended a
  sentence to the CLI-window trade-off paragraph pointing at the new WARNING log
  line, so the doc and the log now reference each other by name.
- `tests/test_encryption.py` — updated
  `test_resolve_pending_key_mixed_promotes_with_warning`'s caplog assertion to check
  for the new wording ("CLI-window", "unreadable after promotion") in addition to the
  existing count check. Added
  `test_undecidable_promote_is_safe_because_sidecar_precedes_commit`: residue-only
  samples plus a pending key promote via the undecidable branch, and ciphertext
  written under the canonical key *after* promotion still round-trips — demonstrating
  the branch isn't vulnerable to losing readable data.

No behavior change to the reconcile logic itself — message text, a comment, a doc
sentence, and tests only.

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_encryption.py tests/test_key_reconcile.py -x --timeout 60`
  → 40 passed.
- `.venv/bin/ruff check . && .venv/bin/ruff format --check .` → all checks passed,
  453 files already formatted.

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-28; Sonnet — batch touches the credential gate and key-material code)
**Verdict**: confirmed
**Commit**: `{sha}` on `squawk/turnaround-2026-08-28` — PR #{pr}

Full unit suite at close-out: 4580 passed / 10 skipped / 0 failed (513s); browser lane for 0022: 2 passed.
