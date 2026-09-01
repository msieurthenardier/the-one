# Squawk 0030: Secret mask reveals last-4 plaintext — nearly the whole value for short secrets

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-01
**Completed**: 2026-09-01

## Report

The established `_emit_mask` convention (M11 F8 L3) renders masked secrets as `***...{tail4}` in API
responses. For a short secret this reconstructs nearly the whole value — the behavior-test's 5-char
token `dummy` masked to `***...ummy`, eliding only one character. Fix: show the tail only when the
secret length clears a threshold (e.g. ≥12 chars), else fully opaque (`***`). Strictly safer; the
tail's identification purpose only makes sense for long tokens anyway. Applies to the shared helpers
(`_mask_secrets`/`_emit_mask` in `api.py`), so MCP-source and connector responses both change —
update the existing mask-format regression test accordingly.

## Evidence

- `the_one/interfaces/web/api.py` `_emit_mask`/`_mask_secrets` (~`:1489-1609`)
- Behavior-test runs `2026-08-31-21-37-14` (checkpoint 1 validator notes) and `2026-08-31-22-43-08`
  (validator closing) — flagged non-blocking both runs
- Flight 2 flight-end review: convention pre-exists this flight (not a Flight 2 defect), but "weak masking"

## Corrective Action

Added a threshold constant `_MASK_TAIL_MIN_SECRET_LEN = 12` in
`the_one/interfaces/web/api.py` (next to the existing `_MASK_PREFIX` /
`_MASK_TAIL_SEPARATOR` / `_MASK_TAIL_LEN` mask-shape constants). `_emit_mask`
— the single shared helper all consumers route through (`_mask_secret_value`
for MCP-source/connector per-key secrets, `_mask_api_key` for LLM-provider
`api_key`) — now returns bare `***` (no tail) for any secret shorter than 12
chars, and `***...{tail4}` only at or above that length. `dummy` (5 chars)
now masks as `***` instead of `***...ummy`.

`_looks_masked` / `_MASK_SHAPE_RE` needed no code change: the regex's
`***...tail`-suffix group was already optional, so it recognized bare `***`
as a mask before this fix too — verified explicitly (see Verification) since
this was the squawk's stated correctness risk (a client echoing the new
short form back on PUT must still resolve to "preserve existing", not
overwrite the stored secret with the literal string `***`).

Docstrings on `_emit_mask` and `_mask_secret_value` updated to describe the
threshold instead of the old fixed 4-char cutoff; a stale "≤4 char" comment
in the `test_short_value_mask_roundtrip` test was also corrected.

Scope check: grepped the front-end JS (`the_one/interfaces/web/static/js/`)
for any code parsing the mask tail — none found; the Studio UI treats the
GET-masked value as an opaque pre-fill and either resubmits it verbatim
(sentinel round-trip) or replaces it with a new plaintext value. Mask format
is display + sentinel-round-trip only, confirming this stayed within the
squawk's scope gate (no [BLOCKED] needed).

## Verification

- Located the shared helper via `grep _emit_mask _mask_secrets api.py`;
  confirmed both `_mask_secret_value` (MCP-source/connector) and
  `_mask_api_key` (LLM-provider) route through `_emit_mask`, so the fix
  applies uniformly to all three consumers from one change site.
- Manual spot-check (`python -c ...`): `dummy` → `***`; 11-char secret →
  `***`; 12-char secret → `***...{tail4}`; `_looks_masked("***")` → `True`;
  `_looks_masked("***hello")` → `False` (non-mask value still overwrites,
  unaffected by the threshold change).
- Extended `tests/test_api_secret_mask_roundtrip.py` with
  `test_squawk_0030_below_threshold_secret_masks_fully_opaque_roundtrip`
  (pins the `dummy`-shaped case end-to-end via the HTTP API: GET masks to
  `***`, PUT-ing that back preserves the original stored plaintext — direct
  DB decrypt assertion, not just re-GET) and
  `test_squawk_0030_threshold_boundary` (unit-pins `_emit_mask`: 11 chars →
  `***`, 12 chars → tail shown).
- Full command, foreground:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_api_secret_mask_roundtrip.py tests/test_provider_api.py -x
  --timeout 60` → **199 passed** (197 pre-existing + 2 new), no changes
  needed to any pre-existing assertion — every secret value already used in
  these suites was either ≤4 chars (already opaque under the old rule) or
  ≥12 chars (unaffected by raising the tail threshold).
- Also ran `tests/test_oauth_secrets_api.py`, `tests/test_db_api.py`,
  `tests/test_api_tool_configs.py` (the other files referencing `***...`
  mask literals) — 85 passed, no changes needed.
- `ruff check` clean on `the_one/interfaces/web/api.py` and
  `tests/test_api_secret_mask_roundtrip.py`.
- Did not commit — left for FD review per batch protocol.

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet), squawk/turnaround-2026-09-01
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-01 batch commit (PR follows)
