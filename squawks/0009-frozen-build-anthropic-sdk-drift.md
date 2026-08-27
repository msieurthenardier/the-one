# Squawk 0009: Frozen build re-resolves `anthropic>=0.40` and ships an untested SDK that crashes chat

**Status**: completed
**Type**: defect
**Severity**: grounding
**Reported**: 2026-08-27
**Completed**: 2026-08-27

## Report

A packaged v0.7.0 install crashes on the first chat turn against an Anthropic-backed
agent with `TypeError: AsyncMessages.stream() got an unexpected keyword argument
'temperature'`. Root cause is a build-reproducibility gap, not an application bug:

- `uv.lock` pins **anthropic 0.96.0**, whose `AsyncMessages.stream()` accepts
  `temperature` (verified). That is the tested closure.
- The GUI/Windows installer build runs `pip install -e ".[gui,all-llms]"`
  (`.github/workflows/windows-installer.yml:44`), which **ignores the lock and
  re-resolves `anthropic>=0.40` fresh at build time** — so the frozen app bundled a
  newer SDK than 0.96.0, and that newer `messages.stream()` no longer accepts
  `temperature`. `the_one/llm/anthropic_provider.py` always sends `temperature`
  (`:234` build, `:417` send).
- The provider's temperature-retry only catches `anthropic.BadRequestError` (an API
  400), not this `TypeError` (an SDK signature mismatch), so it crashes rather than
  degrading.

## Evidence

- `uv.lock:181-183` — `anthropic == 0.96.0`; its `stream()` signature includes
  `temperature` and `output_config` (confirmed via `inspect.signature`).
- `.github/workflows/windows-installer.yml:44` — `pip install -e ".[gui,all-llms]"`
  (re-resolves; does not install the locked closure). Contrast
  `.github/workflows/pr-lint.yml:61` which DOES compute the locked closure via
  `uv export --no-dev --no-emit-project --extra gui --extra all-llms`.
- `pyproject.toml` — `anthropic = ["anthropic>=0.40"]` and the `all-llms` extra, both
  unbounded.
- `the_one/llm/anthropic_provider.py:311-333` (`complete`) and `:388-408` (`stream`) —
  retry catches only `anthropic.BadRequestError`, not `TypeError`.

## Corrective Action

Three coordinated changes (delivered together in the v0.7.1 hotfix):
1. Pin an upper bound — `anthropic>=0.40,<0.97` in both the `anthropic` and `all-llms`
   extras — and relock (`uv lock`), so every install resolves to the known-good 0.96.0.
2. Build the frozen app from the locked closure — the installer workflow installs the
   `uv export`ed pinned requirements + `pip install -e . --no-deps`, instead of
   re-resolving with `pip install -e ".[gui,all-llms]"`.
3. Harden `AnthropicProvider.complete()`/`stream()` to catch `TypeError: ... unexpected
   keyword argument '<param>'`, strip the offending sampling param, and retry once —
   mirroring the existing `BadRequestError` temperature-retry — so future SDK drift
   degrades gracefully. With a regression test.

### Delivered (precise changes)

1. **Pin + relock.** `pyproject.toml` — `anthropic>=0.40` → `anthropic>=0.40,<0.97`
   in both the `anthropic` extra and the `all-llms` extra. `uv lock` re-run:
   anthropic stays **0.96.0**; the lock's `requires-dist` records the new
   `>=0.40,<0.97` specifier on both `extra == 'anthropic'` and
   `extra == 'all-llms'`. (The lock also corrected its own stale project-version
   metadata 0.6.0 → 0.7.0, matching pyproject; no dependency resolution changed.)
2. **Build from the locked closure.** `.github/workflows/windows-installer.yml`
   "Install GUI freeze deps + PyInstaller" step now: `pip install uv` →
   `uv export --no-dev --no-emit-project --extra gui --extra all-llms
   --format requirements-txt > release-requirements.txt` →
   `pip install -r release-requirements.txt` → `pip install -e . --no-deps` →
   `pip install pyinstaller` (was `pip install -e ".[gui,all-llms]"`). A comment
   explains the frozen app must ship the tested/locked closure, not a fresh
   resolve. No other workflow touched.
3. **Provider signature-drift net.** `the_one/llm/anthropic_provider.py` — added
   `_UNEXPECTED_KWARG_RE` + `_unexpected_kwarg_name(exc)` (regex-extracts the
   param from `unexpected keyword argument '<name>'`, else None). `complete()`
   and `stream()` each gained an `except TypeError` branch (alongside the intact
   `BadRequestError` branches): if the extracted name is a key in `kwargs`, log a
   warning, pop it, and retry once; otherwise re-raise unchanged. `stream()`'s
   branch is gated on `not yielded_any` like the existing temperature-retry. A
   retry that still TypeErrors propagates. Not hard-coded to `temperature` — the
   name is extracted, so a future drifted sampling param is covered too.

## Verification

Run 2026-08-27 on branch `squawk/0009-frozen-build-anthropic-sdk-drift`:

- **Relock invariant** — `uv lock` resolved 134 packages; `uv.lock` still pins
  `anthropic == 0.96.0` (`>=0.40,<0.97` recorded on both extras). Confirmed the
  pin did not drift the installed SDK.
- **New regression tests** (`tests/test_anthropic_provider.py`) — 4 added:
  `test_complete_typeerror_strips_kwarg_and_retries`,
  `test_complete_typeerror_unrelated_reraised`,
  `test_stream_typeerror_strips_kwarg_and_retries`,
  `test_stream_typeerror_unrelated_reraised`. They assert (a) `complete()` returns
  without raising, (b) `stream()` yields chunks without raising, (c) the retried
  call omits `temperature`, (d) an unrelated `TypeError` (kwarg `bogus`, not in
  kwargs) re-raises unchanged with no retry.
- **Provider suite** — `run-tests.sh tests/test_anthropic_provider.py -x
  --timeout 30`: **84 passed** (was 80).
- **Lint** — `ruff check the_one/ tests/`: All checks passed. `ruff format
  --check the_one/ tests/`: 441 files already formatted (0 to reformat).
- **Full unit suite** — `make test-unit`: **4511 passed, 10 skipped, 695
  deselected, 0 failed** (562s).

## Sign-Off
**Reviewer**: independent Reviewer agent (leg-execution crew)
**Verdict**: confirmed — all three corrective actions correct, complete, tested, and confined; the `--no-deps` closure verified complete; the stream() TypeError retry gated on `not yielded_any` (no double-yield)
**Commit**: squawk/0009 hotfix, shipped in the v0.7.1 release
