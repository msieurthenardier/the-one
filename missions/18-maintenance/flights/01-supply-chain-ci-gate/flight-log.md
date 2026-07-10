# Flight Log: Supply-chain & CI gate

**Flight**: [Supply-chain & CI gate](flight.md)

## Summary
Both legs landed 2026-07-10. Runtime CVE closure via seven `uv lock --upgrade-package`
moves + refreshed `pyproject.toml` CVE-floor comment; new `pr-lint.yml` restores a
pre-merge GH Actions gate (ruff + runtime-only pip-audit) without re-enabling the
Concourse-shifted heavy lanes. Full unit suite green. Uncommitted, pending flight review.

---

## Leg Progress

### Leg 1 — dependency-cve-bump (landed 2026-07-10)

**Changed:** `pyproject.toml` — bumped explicit CVE floors `aiohttp>=3.14.0`→`>=3.14.1`
and `starlette>=1.0.1`→`>=1.3.1`, and rewrote the CVE-floor comment block to cite the
fresh IDs from this run (the old block cited stale CVE-2026-34993/47265/PYSEC-2026-161).
`uv.lock` regenerated; `uv lock --check` clean, no drift.

**Version moves (all 7 runtime packages + 1 dependency-of-a-pin):**
- aiohttp 3.14.0 → 3.14.1
- starlette 1.2.1 → 1.3.1
- cryptography 47.0.0 → 49.0.0 (leg named a ≥48.0.1 floor; resolver picked 49.0.0)
- python-multipart 0.0.29 → 0.0.32
- pydantic-settings 2.13.1 → 2.14.2 (own `--upgrade-package`)
- soupsieve 2.8.3 → 2.8.4 (own `--upgrade-package`)
- lxml-html-clean 0.4.4 → 0.4.5 (own `--upgrade-package`)
- lxml 6.1.0 → 6.1.1 (forced: lxml-html-clean 0.4.5 requires lxml>=6.1.1 — a dependency
  of the pin, not scope creep)

**pip-audit delta (`pip-audit --skip-editable`, full venv):** before = 24 vulns / 9
packages; after = 2 vulns / 2 packages. Cleared: aiohttp (PYSEC-2026-237, CVE-2026-54273,
-54274, -54276, -54277, -54278, -54279, -54280), cryptography (GHSA-537c-gmf6-5ccf),
lxml-html-clean (CVE-2026-49825), pydantic-settings (GHSA-4xgf-cpjx-pc3j), python-multipart
(CVE-2026-53538, -53539, -53540), soupsieve (CVE-2026-49476, -49477), starlette
(PYSEC-2026-248, -249). All seven runtime clusters cleared. Remaining 2 are dev/toolchain-only
and out of scope: `pip` 26.1.1 (PYSEC-2026-196) and `msgpack` 1.1.2 (GHSA-6v7p-g79w-8964,
via pip-audit's own cachecontrol dep). Runtime-closure audit (`uv export --no-dev
--no-emit-project | pip-audit -r`) = **No known vulnerabilities found**.

**No breaking-API surprises** from the cryptography 47→49 or starlette 1.2→1.3 moves — no
code edits required. `make doctor` = ok.

**Tests:** `make test-unit` — 3976 passed, 10 skipped, 660 deselected, 21 warnings in
350.29s (5m54s wall); exit 0. Warnings are pre-existing (aiosqlite teardown event-loop,
websockets/starlette deprecation notices), not regressions from the bumps.

**Review follow-up (2026-07-10) — floor-fix for the release-artifact resolve path.**
Flight review flagged that the CVE fixes only landed in `uv.lock`; the Windows
installer build (`.github/workflows/windows-installer.yml:44`,
`pip install -e ".[gui,all-llms]"`) re-resolves from `pyproject.toml` ranges, not
`uv.lock` — the same "image build doesn't consume uv.lock" gap that
`missions/12-maintenance/.../legs/01-bump-runtime-cves.md` closed for aiohttp/idna/
starlette. Only aiohttp/starlette/idna had explicit floors; the other five packages
this leg closed (cryptography, pydantic-settings, python-multipart, soupsieve,
lxml-html-clean, plus the lxml dependency-of-the-pin) either had a stale floor or
none at all. Fixed:
- `cryptography>=43.0` → `>=48.0.1` (GHSA-537c-gmf6-5ccf, vulnerable statically-linked
  OpenSSL, fixed in 48.0.1 — verified via OSV).
- `pydantic-settings>=2.0` → `>=2.14.2` (GHSA-4xgf-cpjx-pc3j / CVE-2026-58203, symlink
  escape in `NestedSecretsSettingsSource`, fixed in 2.14.2 — verified via OSV).
- Added explicit floors for three previously-transitive-only packages: `python-multipart
  >=0.0.31` (GHSA-5rvq-cxj2-64vf / CVE-2026-53539 + GHSA-v9pg-7xvm-68hf / CVE-2026-53540,
  fixed in 0.0.31), `soupsieve>=2.8.4` (GHSA-2wc2-fm75-p42x / CVE-2026-49476 +
  GHSA-836r-79rf-4m37 / CVE-2026-49477, fixed in 2.8.4), `lxml-html-clean>=0.4.5`
  (GHSA-4jhm-jv67-739f / CVE-2026-49825, `xlink:href` javascript: URL bypass, fixed in
  0.4.5) — all verified via OSV, not trusted from the review prompt.
- Added `lxml>=6.1.1` — not itself CVE-affected here; forced by `lxml-html-clean>=0.4.5`
  requiring `lxml>=6.1.1` (dependency-of-the-pin floor).
- Extended the `pyproject.toml` CVE-floor comment block to document all seven packages
  (was aiohttp/idna/starlette only) and reworded it to name the actual re-resolve
  trigger (`pip install -e` in the Windows installer workflow), not a generic "image
  build".

`uv lock` regenerated; `uv lock --check` clean, no drift; all locked versions
unchanged/still at the fixed versions (cryptography 49.0.0, pydantic-settings 2.14.2,
python-multipart 0.0.32, soupsieve 2.8.4, lxml-html-clean 0.4.5, lxml 6.1.1). **Verified
the release-artifact resolve actually binds** (not just incidentally resolves safe): both
`pip install --dry-run -e ".[all-llms]"` (pip's own resolver) and `uv pip install --dry-run
-e ".[gui,all-llms]" --python-platform windows` (matching the installer job's OS) show
`Collecting <pkg>>=<floor>` for all seven packages and resolve to the CVE-fixed versions
list above — the floors bind, they aren't incidental. (Plain `pip install --dry-run` with
the `[gui]` extra fails on this Linux dev box on an unrelated pycairo/GTK system-library
build error — `pywebview[gtk]` only activates on `sys_platform == 'linux'` and needs
`cairo`/`pkg-config` not present here; the Windows-platform uv resolve sidesteps that by
matching the actual CI OS.) Runtime-closure audit re-run (`uv export --no-dev
--no-emit-project --format requirements-txt | pip-audit -r`) = **No known vulnerabilities
found**. `make doctor` = ok. No source changed, so no additional test run beyond the
existing green suite above.

### Leg 2 — pre-merge-lint-gate (landed 2026-07-10)

**Added** `.github/workflows/pr-lint.yml` — `on: pull_request` → `branches: [main]`, two
fail-on-nonzero jobs:
- `lint`: `ruff check the_one/ tests/` + `ruff format --check the_one/ tests/`, pinned
  `ruff==0.15.15` (parity with `ci/tasks/lint.yml`).
- `pip-audit`: runtime-only audit via `uv export --no-dev --no-emit-project --format
  requirements-txt > runtime-requirements.txt && pip-audit -r runtime-requirements.txt`.
  `--no-emit-project` drops the editable `-e .` self-entry (pip-audit's `--require-hashes`
  install can't hash it). This is a **deliberate policy change** from the warn-only
  `make audit` (`pip-audit --skip-editable || true`) — the PR job blocks on runtime-closure
  findings. Documented inline in the workflow + in `ci/README.md`.

Actions pinned `actions/checkout@v5` + `actions/setup-python@v6` (matches existing workflow
style — C3 floating-major advisory deferred, not regressed). Heavy lanes untouched:
`test.yml`/`windows-installer.yml`/`lint.yml` unchanged — no test/browser/windows added to
`pull_request`. `ci/README.md` updated with the new pre-merge lane in the "what runs where"
table + a "Pre-merge lint + audit gate" section documenting the pip-audit policy change.

**Validation:** YAML parsed via PyYAML (actionlint unavailable in env). Current tree passes
the exact workflow commands: `ruff check` = "All checks passed!", `ruff format --check` =
"408 files already formatted", runtime-closure pip-audit = "No known vulnerabilities found".

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
