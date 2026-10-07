# Squawk 0135: Move the project's Python target from 3.11 to 3.12

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

## Report

Local development runs on Python 3.12, but CI, the Windows installer and the project metadata all target 3.11. That split has bitten twice:
- **Sortie 01's design** found that a `typing.TypedDict` route annotation would pass on the 3.12 dev venv and crash `api.py` at import everywhere else.
- **Sortie 01 leg 1:** a 3.11 import check rebuilt the repo `.venv` as 3.11.

The operator decided on 2026-10-07 to move the project to 3.12 permanently, so dev, CI and the shipped Windows build run one interpreter line. Pin the **minor** version (`3.12`), not a patch release. The local venv is CPython 3.12.3, the system Python on the dev host.

Raised mid-flight during sortie 01 and deferred until that sortie lands (out of its scope).

## Evidence

- **Project metadata:** `pyproject.toml:5` `requires-python = ">=3.11"`, `pyproject.toml:183` `target-version = "py311"` (ruff), and `uv.lock` header `requires-python = ">=3.11"`.
- **Concourse:** `ci/tasks/test.yml:17`, `bwrap.yml:38` and `lint.yml:13` have `tag: "3.11"`, and `browser.yml:21` has `tag: "3.11-bookworm"`.
- **Windows:** `ci/tasks/windows-tests.yml`, `windows-installer-build.yml` and `windows-vector-bench.yml` install choco Python 3.11. `packaging/windows/README.md:33` says "Python 3.11".
- **GitHub Actions** (break-glass and release): `.github/workflows/test.yml` (lines 26, 66, 92), `pr-lint.yml` (34, 48), `lint.yml` (20) and `windows-installer.yml` (38) set `python-version: "3.11"`.

## Corrective Action
*(written at completion)*

## Verification
- `grep -rn '3\.11\|py311' pyproject.toml uv.lock ci/ .github/workflows/ packaging/windows/` shows no remaining target pins. Historical prose in mission or flight artifacts is left alone.
- `make test-unit` is green on 3.12, and `ruff check` and `ruff format --check` are clean under `target-version = "py312"`, including any new ruff findings.
- The Concourse test, lint, bwrap and browser lanes are green on the 3.12 images.
- A Windows installer build on 3.12 succeeds, and `the-one doctor` passes in the packaged smoke run. PyInstaller and the `pywinpty` wheel are the likely snags.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
