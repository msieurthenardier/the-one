# Squawk 0224: pip-audit fails on new certifi and Pillow advisories in the release closure

**Status**: completed
**Type**: servicing
**Severity**: grounding
**Reported**: 2026-10-21
**Completed**: 2026-10-21

## Report
The `pr-lint` workflow's `pip-audit` job (`pip-audit --disable-pip -r release-requirements.txt`) now fails on every PR, with 9 known vulnerabilities in 2 packages of the release closure:
- `certifi` 2026.2.25: PYSEC-2026-4320, fixed in 2026.10.19;
- `pillow` 12.3.0: CVE-2026-112895, -112400, -112397, -112896, -112897, -112395, -112404, -112899, fixed in 13.0.0.

These are newly published advisories. Nothing in the code changed: it surfaced on squawk 0223's PR #299 (run 39660899079), whose diff touches no dependency. The scheduled run on `main` passed on 2026-10-19.

Bump both pins in the release closure and wherever else they are pinned. Check the Pillow 13 major bump against its users (icon generation in `packaging/windows/regenerate_icon.py`, brand assets in `scripts/derive_brand_assets.py`, and anything else importing PIL) and the packaged-build smoke.

## Evidence
- GitHub Actions run 39660899079, job `pip-audit (release closure — fails on findings)`.
- `release-requirements.txt` (the release closure) and `pyproject.toml` pins.

## Corrective Action
- `pyproject.toml`: raised the Pillow floor `>=12.3` -> `>=13.0` in both places (the `gui` extra, which binds the Windows installer, and `dev`), and updated the comment above the `gui` floor. There was no explicit certifi floor (transitive only).
- `uv.lock` (the source of `release-requirements.txt` via `uv export`): `uv lock --upgrade-package pillow --upgrade-package certifi` -> certifi 2026.2.25 -> 2026.10.19, pillow 12.3.0 -> 13.0.0. No other package moved.
- Pillow 13 compatibility: every PIL user (`packaging/windows/regenerate_icon.py`, `scripts/derive_brand_assets.py`, `the_one/interfaces/desktop/tray.py`, `the_one/diagnostics.py`) uses only `Image.open/new/resize(Image.Resampling.LANCZOS)/save(..., "ICO", sizes=)`; no code change needed.

## Verification
Results (2026-10-21, worktree venv synced to the lock with `uv sync --frozen`):
- `uv export --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt` then `pip-audit --disable-pip -r <closure>`: "No known vulnerabilities found".
- `python -m pytest tests/ -m 'not browser and not live and not pixel'`: 6751 passed, 15 skipped. (An earlier run on a pip-resolved venv, which had drifted from the lock, showed 6 failures that reproduced identically with the old certifi/pillow; they vanish on the locked env.)
- `ruff check` and `ruff format --check` on the_one/ tests/ scripts/ evals/: clean.
- `regenerate_icon.py` run to a scratch path: sizes 16/32/48/64/128/256 and the .ico is byte-identical (md5 3009ce1f...) to the committed `the-one.ico`; `derive_brand_assets.py --out-dir <scratch>` ran fine; `the-one doctor`: RESULT PASS.
- `pr-lint` green on the PR: pending (CI).

Criteria:
- `pip-audit --disable-pip -r release-requirements.txt` passes.
- `make test-unit` passes.
- The PIL users are exercised: icon regeneration produces the same `.ico` sizes, and `the-one doctor` passes.
- The PR's `pr-lint` is green.

## Sign-Off
*(written at completion)*
**Reviewer**: independent Reviewer crew agent (Haiku), scoped to the diff
**Verdict**: confirmed. `uv.lock` changes only certifi, pillow and the-one's two requires-dist floors. The rebuilt closure audits clean ("No known vulnerabilities found"). The PIL call sites use nothing Pillow 13 removed, and an in-memory ICO write matched the committed `.ico`. Noted, not folded in: the pyproject comment's CVE range shorthand reads wider than the 8 ids, and certifi has no floor in `pyproject.toml`, so only the lock carries its fix.
**Commit**: this commit, on branch `squawk/0224-pip-audit-certifi-pillow-advisories`
