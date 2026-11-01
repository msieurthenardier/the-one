# Squawk 0302: Package artifact retention exhausts the account's Actions storage

**Status**: completed
**Type**: defect
**Severity**: grounding
**Reported**: 2026-10-31
**Completed**: 2026-10-31

## Report
The v0.13.0 release cannot publish. In all four attempts of the tag run, the Windows, Linux and macOS builds succeed and then fail to upload with `Failed to CreateArtifact: Artifact storage quota has been hit`, so `publish` never runs. Actions storage accrues per hour over the billing cycle, and deleting artifacts does not give back usage already accrued. The package artifacts (~545 MB per release) are kept 14 days, so a busy week of release and dispatch runs (about 20 runs on Oct 24-28) used up the month's allowance. The operator deleted about 3 GB on Oct 30, which did not help. GitHub Free is 500 MB, or 372 GB-hours in a 31-day month. One release at 14 days uses about 183 GB-hours. The publish job only needs the packages for minutes.

This reverses Mission 32 Flight 4 DD7 / leg 04 AC6, which kept packages 14 days "so a failed `publish` can be re-run within that window." The operator's call (2026-10-31): a failed publish re-runs the whole release, which takes about 5 minutes.

## Evidence
- Run 41134183836 (tag `v0.13.0`, attempts 1-4): `##[error]Failed to CreateArtifact: Artifact storage quota has been hit` in `windows / build`, `linux / build` and `macos / build`; `publish` skipped or cancelled.
- `.github/workflows/windows-packages.yml` `windows-installer`, `linux-packages.yml` `linux-packages` and `macos-packages.yml` `macos-dmg`: `retention-days: 14`. Logs and evidence: 7 days, about 0 MB.
- v0.12.3 run 40757656689 still holds 545 MB until 2026-11-11, although the same files are on the published v0.12.3 release.
- `tests/test_release_workflow.py::test_artifact_retention_for_a_rerun_publish` pins the 14 days. `test_platform_jobs`, `test_job_set` and `test_permissions` pin the job set, the platform `with:` blocks and the permissions.
- GitHub Docs, "How use of GitHub Actions is measured": "Deleting artifacts frees up space for current storage, but does not reduce your accrued storage usage."

## Corrective Action
Done as intended:
1. `windows-`, `linux-` and `macos-packages.yml` gained a `workflow_call` input `retention-days` (number, default 3). Only the package artifact upload uses it, as `${{ inputs.retention-days || 3 }}` (the `|| 3` covers a standalone dispatch, where the input is undeclared and null). Logs and evidence stay 7. No `workflow_dispatch` block changed. The Windows `on:` block is pinned whole to `packaging/windows/probe/windows-packages.stub.yml`, so that stub's `workflow_call` block got the same input (its dispatch block, the part GitHub validates, is untouched).
2. `release.yml` passes `retention-days: 1` to each platform job and has a new `cleanup` job (`actions: write` only; `publish` keeps `contents: write`). It runs `if: always() && ((push && needs.publish.result == 'success') || workflow_dispatch)` after `windows, linux, macos, publish`, and deletes this run's three package artifacts through `gh api` (inputs via `env:`; absent artifacts tolerated). It cannot run after a failed publish.
3. Tests: `tests/test_release_workflow.py` (permissions, job set, platform `with`, new retention test, new `test_cleanup_job`) and `tests/test_windows_packages_workflow.py` (retention expression, `workflow_call` inputs). `the_one/agents.md` release prose updated.
4. Review fix (doc only): the `agents.md` "Release workflow (M32 F4)" Jobs bullet now lists `cleanup` after `publish`, and the permissions sentence says only `cleanup` has `actions: write`. CLAUDE.md's Release paragraph lists no job set that is now wrong, so it is unchanged.

## Verification
- `THE_ONE_TEST_NETNS=1 make test-unit`: 8385 passed, 15 skipped (the expected netns count).
- `tests/test_release_workflow.py` + `tests/test_windows_packages_workflow.py`: 35 passed.
- `uvx --from actionlint-py actionlint` (1.7.12) on release.yml and the three *-packages.yml: clean.
- `ruff check tests/` and `ruff format --check tests/`: clean.
- Falsified: the cleanup condition (`== 'success'` to `!= 'failure'`) failed `test_cleanup_job`; linux upload retention set to 14 failed the retention test. Both reverted.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the higher tier because the diff adds an `actions: write` token permission), scoped to the diff, `[HANDOFF:confirmed]`. It traced the `cleanup` condition through push success, publish failure or cancellation, platform failure, a dispatch with skipped platforms and a cancelled dispatch. It checked the `|| 3` fallback under a standalone dispatch, the `gh api` pagination and the absent-artifact path, and the minimal permissions. It re-ran the two workflow test files (35 passed), actionlint and ruff (clean). Its one note, the `agents.md` job list, was fixed (item 4) and re-confirmed.
**Verdict**: confirmed
**Commit**: the `squawk/0302` commit on branch `squawk/0302-package-artifact-retention-exhausts-actions-storage`
