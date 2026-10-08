# Squawk 0138: Browser tests run a Chromium 11 major versions behind the shipped engine

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

## Report

The browser suite runs Chromium **145.0.7632.6**: Playwright is pinned at exactly `1.58.0` (released 2026-01-30), and that release bundles Chromium 145. The engine the app actually ships on moves on by itself. On Windows, pywebview uses WebView2, which updates with Edge and is on roughly Chrome stable, today **156.0.8078.12**.

So the tests check an engine **11 major versions**, about 10 months, older than the one users run. Playwright itself is 5 minor releases behind (latest **1.63.0**).

The UI is plain ES5 and DOM, so breakage from the gap is unlikely, but nothing surfaces it. `uv.lock` holds the pin and `pip-audit` doesn't flag browser age, so the gap only grows.

The pin was made exact on purpose, in Leg 03 of the pre-Mission-06 flight (`ebf694d`, 2026-05-04: "pin Playwright==1.58.0"), to make CI reproducible. Keep it exact; bump it to a current release. Raised by the operator on 2026-10-07 during the sortie 01 debrief.

A candidate to batch with squawk 0135 (the move to Python 3.12) in one turnaround. Both touch CI images and the dev toolchain.

## Evidence

- **The pin:** `pyproject.toml:130` `dev = [… "playwright==1.58.0" …]`; `uv.lock` `playwright` `version = "1.58.0"`.
- **Installed browsers:** `~/.cache/ms-playwright/chromium-1208` reports "Google Chrome for Testing 145.0.7632.6"; `webkit-2248` is WebKit 26.0. Both come from Playwright 1.58.0's `browsers.json`.
- **Current releases** (2026-10-07): PyPI `playwright` 1.63.0; Chrome stable (Windows), from the versionhistory API, 156.0.8078.12.
- **Browser installs to update:** `ci/tasks/browser.yml:33` and `.github/workflows/test.yml:73` run `python -m playwright install --with-deps chromium webkit`. Both follow the pinned version automatically. `scripts/setup-webkit-userland.sh` fetches WebKit's host libraries, and a new WebKit build may need different ones.
- `~/.cache/ms-playwright/chromium-1217` (Chrome 147) is present on the dev host but unused by this repo.

## Corrective Action
*(written at completion)*

## Verification
- `playwright==` in `pyproject.toml` and `uv.lock` is the current release, still an exact pin, and `uv lock --check` passes.
- `.venv/bin/python -m playwright install chromium webkit` is done, and the bundled Chromium is at or near current stable.
- **Browser lanes:** all six pass under `THE_ONE_TEST_NETNS=1`. The contracts lane runs with `THE_ONE_REQUIRE_WEBKIT=1`, so a WebKit launch failure fails rather than skips. Re-run `scripts/setup-webkit-userland.sh` if WebKit's host libraries changed.
- The Concourse browser task is green with the new browsers.
- The commit body records any test changes the new engines forced.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
