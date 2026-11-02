# Squawk 0300: Bump the dev-only virtualenv and msgpack locks past their CVEs

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: 2026-11-01

## Report
`pip-audit` reports 9 vulnerabilities in two locked packages. Both are dev or tool dependencies and neither ships in the packaged app (virtualenv comes in through pre-commit; msgpack through pip-audit's cachecontrol), so the risk is low, but the audit stays red until they move. From maintenance report 2026-10-30, finding #20.

## Evidence
- `uv.lock`: `virtualenv` 21.14.5 (CVE-2026-113714, -113715, -113717, -113718, -113720, -113722, -113723, -113725; fixed in 21.14.7-21.14.9).
- `uv.lock`: `msgpack` 1.2.1 (CVE-2026-114613; fixed in 1.2.3).
- `.venv/bin/pip-audit` run on 2026-10-30.

## Corrective Action
Ran `uv lock --upgrade-package virtualenv --upgrade-package msgpack`. Lock deltas: `virtualenv` 21.14.5 -> 21.15.2, `msgpack` 1.2.1 -> 1.2.4, and one transitive move, `packaging` 26.1 -> 26.3 (a dependency of virtualenv, moved by uv alongside it). `pyproject.toml` untouched; no other package moved.

## Verification
- `git diff --stat -- uv.lock pyproject.toml` before: empty. After: only `uv.lock` (90 insertions, 65 deletions).
- `uv lock --check`: passes.
- `uv sync --frozen --extra all-llms --extra dev`: installed msgpack 1.2.4, packaging 26.3, virtualenv 21.15.2.
- `.venv/bin/pip-audit --skip-editable` (the full-venv audit, as in `make audit`; CI's pr-lint job audits only the `--no-dev` release closure, which excludes these two): "No known vulnerabilities found".
- `.venv/bin/pre-commit --version`: 4.6.0; `import msgpack, virtualenv`: (1, 2, 4) 21.15.2.
- `make test-unit` is run once for the batch by the Flight Director.

Planned: `uv lock --upgrade-package virtualenv --upgrade-package msgpack` moves only those two (and any forced transitive) entries; `uv lock --check` passes; `pip-audit` reports neither package; `make test-unit` is green.

`uv lock --upgrade-package virtualenv --upgrade-package msgpack` moves only those two (and any forced transitive) entries; `uv lock --check` passes; `pip-audit` reports neither package; `make test-unit` is green.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch states security-model residual risks, 0298 and 0299), batch review of the 2026-11-01 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]`. `packaging` 26.1 -> 26.3 moved with virtualenv; `pyproject.toml` unchanged; `pip-audit --skip-editable` clean.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-01` commit on `squawk/turnaround-2026-11-01`. Unit tier under `THE_ONE_TEST_NETNS=1`: 8560 passed, 23 skipped, 3 failed (the known `tests/test_desktop_host.py` baseline, unchanged from main).
