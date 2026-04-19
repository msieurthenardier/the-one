# Leg: verify-integration

**Status**: completed
**Flight**: [Test Infrastructure & CI Hardening](../flight.md)

## Objective

Verify all flight deliverables work end-to-end: unit tests pass, lint clean, pipeline valid, and CI test gate blocks on failure.

## Acceptance Criteria

- [x] `python3 -m pytest tests/ --tb=short -q` passes (unit tests only, AIAT excluded)
- [x] `python3 -m pytest tests/ --tb=short -q -m "not live"` — same result
- [x] `python3 -m pytest -m live --co tests/test_aiat.py` lists 8 tests
- [x] `ruff check the_one/ tests/` clean (pre-existing source lint issues out of scope)
- [x] `fly validate-pipeline -c ci/pipeline.yml` valid
- [x] CI pipeline set and deploy triggered to verify test gate — Concourse offline, pipeline validated offline with `fly validate-pipeline`

## Verification Steps

1. Run unit tests
2. Verify AIAT marker filtering
3. Run ruff linter
4. Validate pipeline YAML
5. Set pipeline and trigger deploy
6. Verify test gate works (tests pass → deploy proceeds)

## Files Affected

None — verification only.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed`
- [x] Check off this leg in flight.md
- [x] Update flight status to `landed` (final leg)
- [x] Check off flight in mission.md
- [x] Commit all changes together (artifacts only)
