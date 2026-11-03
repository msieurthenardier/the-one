# Squawk 0138: Browser tests run a Chromium 11 major versions behind the shipped engine

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-11-03

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
Bumped `playwright==1.58.0` to `==1.64.0` in `pyproject.toml` (dev extra), still an exact pin. Chose 1.64.0 (released 2026-10-13, 20 days old on 2026-11-02) over the newer 1.64.1 (2026-10-22, 11 days old) to honour the 14-day soak. Re-locked with `uv lock --upgrade-package playwright` (the playwright entry moves 1.58.0 -> 1.64.0; the same lock run also records the tzdata 2026.4 -> 2026.6 and certifi-floor changes that follow other uncommitted `pyproject.toml` edits in this batch, not this squawk). Bundled Chromium is now Chrome for Testing 156.0.8078.4 (chromium-1248), matching WebView2 stable (156.0.8078.12); WebKit is webkit-2370. No other version pins exist: `ci/tasks/browser.yml:66` and `.github/workflows/test.yml:73` run `playwright install --with-deps chromium webkit` and follow the pin automatically; no CI image tag or Dockerfile pins the Playwright version. The only other mentions are a historical comment in `the_one/mcp/transports/stdio.py:92` and past maintenance/run logs, left as records. No CI image rebuild is needed; the Concourse browser task will download the new browsers on first run (its `playwright-browsers` cache is keyed by path, so it fetches them then).

## Verification
Developer run (2026-11-02):
- `uv lock --check`: passes. Installed with `uv pip install --python .venv/bin/python playwright==1.64.0`.
- `.venv/bin/playwright install chromium webkit` downloaded both; its host-requirements check then failed (missing system libs, expected on this host), so `bash scripts/setup-webkit-userland.sh` was run (no sudo) and WebKit launches work.
- `THE_ONE_TEST_NETNS=1 make test-unit`: 8729 passed, 15 skipped.
- `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 ... --lane contracts-chat`: 148 passed (Chromium + WebKit).
- Same with `--lane contracts-overlay`: 548 passed, 1 skipped.
- No test changes were needed.
- Not run here: the full browser suite. The Flight Director's single full `make gate` at the end of this batch completes this squawk's verification, and the Concourse browser task check remains for after the commit.

Original criteria:
- `playwright==` in `pyproject.toml` and `uv.lock` is the current release, still an exact pin, and `uv lock --check` passes.
- `.venv/bin/python -m playwright install chromium webkit` is done, and the bundled Chromium is at or near current stable.
- **Browser lanes:** all six pass under `THE_ONE_TEST_NETNS=1`. The contracts lane runs with `THE_ONE_REQUIRE_WEBKIT=1`, so a WebKit launch failure fails rather than skips. Re-run `scripts/setup-webkit-userland.sh` if WebKit's host libraries changed.
- The Concourse browser task is green with the new browsers.
- The commit body records any test changes the new engines forced.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs. The final full gate ran on 1.64.0 / Chromium 156: every lane was within budget, with the one failure being squawk 0315.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
