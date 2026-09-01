# Squawk 0031: agents.md convention entries for the dual-gate seam and disjoint post-step mutator patterns

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-01
**Completed**: —

## Report

Two patterns from Mission 23 Flight 2 deserve `the_one/agents.md` convention entries so they're
pattern-matched instead of re-derived (the seam risk-tiering was re-argued from scratch for the
second flight running):

1. **Dual-gate test seams with risk tiering** — inert-metadata seams may gate on `dev_mode` alone
   (oauth/pending precedent); seams that mutate real state or inject into a live agent loop gate on
   `dev_mode` AND a seam-specific env var (purge-sweep, `THE_ONE_STUB_TEST_ENDPOINT` precedents).
2. **Composition-disjoint post-step mutators** — `_bind_peer_name` (touches only `Role.USER`) and
   `tag_post_step_visibility` (skips `Role.USER`) are non-conflicting by construction; the pattern
   for composing independent post-step concerns without one function growing multiple jobs.

## Evidence

- Flight 2 debrief, What Could Be Improved / Documentation
- `the_one/connectors/inbound.py::_bind_peer_name`, `the_one/llm/base.py::tag_post_step_visibility`
- Seam gates: `api.py` `/_test/stub/*`, `/_test/purge-sweep`; `tests/test_seam_routes_403_sweep.py`

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
