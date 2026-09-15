# Squawk 0049: `hf-xet` ships in the frozen bundle but nothing can ever call it

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-12
**Completed**: 2026-09-15

## Report

`hf-xet` (4.03 MB win_amd64 wheel, a Rust transfer accelerator for Hugging Face
Hub downloads) entered the closure in Mission 24 Flight 1 as a hard dependency
of `huggingface-hub` on x86_64/arm64. The app never downloads from the Hub:
the embedding model is bundled package data and the probe forces
`HF_HUB_OFFLINE=1` in-process. It is the single largest Leg 2 addition and pure
dead weight in a 141.8 MB installer that just doubled.

Mechanism: a `[tool.uv] override-dependencies` (or equivalent) that drops the
`hf-xet` requirement from `huggingface-hub`, regenerate `uv.lock`, remove the
`_hf_xet*` entry from the spec's `upx_exclude`. `huggingface_hub` imports
`hf_xet` lazily inside its download path only, so absence is not an import
error.

**Verification needs a frozen build** — the unit gate does not exercise the
bundle. Natural home is Flight 2, which reshapes this closure anyway (losing
vector-store candidate removal); if Flight 2 picks it up, complete this squawk
against that flight's commit rather than on its own turnaround.

## Evidence

- `uv.lock` `[[package]] name = "huggingface-hub"` → `{ name = "hf-xet", marker = "platform_machine == 'AMD64' or ... 'x86_64'" }`
- `packaging/windows/the-one.spec:400` — `"_hf_xet*",  # hf-xet Rust transfer core`
- `the_one/diagnostics.py:_force_hf_offline` — offline forced before any Hub call
- Flight log, Leg 2 closure table: `hf_xet-1.6.0-cp38-abi3-win_amd64.whl` 4,033,128 bytes, "a Flight 2 candidate"

## Corrective Action

Completed against Mission 24 Flight 2 Leg 6 (`store-decision-and-closure`),
which reshaped this closure anyway (`sqlite-vec` removal, DD-9). Mechanism:
`[tool.uv] exclude-dependencies = ["hf-xet"]` in `pyproject.toml`, next to
the other `[tool.*]` tables — `uv lock` accepted the key directly (0.10.0
on this host), so the `override-dependencies` fallback the leg spec named
was not needed. `uv lock` regenerated `uv.lock`, removing `hf-xet` (and
`sqlite-vec`, the leg's own removal) with no other package version moving.
`packaging/windows/the-one.spec`'s `upx_exclude` list lost its `"_hf_xet*"`
entry (alongside `"vec0*"`, the leg's own removal) — four entries remain:
`"compiled*"`, `"_numkong*"`, `"tokenizers*"`, `"_safetensors_rust*"`.
`huggingface_hub` imports `hf_xet` lazily inside its download path only,
and the app forces `HF_HUB_OFFLINE=1`, so excluding it changes no runtime
behavior.

Files touched: `pyproject.toml` (`[tool.uv]` table + dependency list),
`uv.lock` (regenerated), `packaging/windows/the-one.spec` (`upx_exclude`).

**AC-15 fix (build 606657)**: the frozen `fly execute` gate ran clean
(`RESULT: PASS`, all eight `doctor` gates, no `sqlite-vec:` line, no
`vec0*` in the bundle listing) but AC-15's own bundle inspection found
`_internal\hf_xet\hf_xet.pyd` still present, and the installer landed at
141,812,423 bytes — essentially the 141,827,664-byte pre-squawk baseline,
not the ~4 MB smaller size the closure change above should have produced.
Diagnosis (Flight Director): the closure itself is correct —
`uv export --no-dev --no-emit-project --extra gui --extra all-llms
--format requirements-txt` contains no `hf-xet` line and pins hashes, so
`pip install -r` on the worker runs in hash-checking mode. The actual
leak is a build-env one: the Concourse Windows worker runs tasks
uncontainerised, so `C:\Python311`'s site-packages persist across
builds, and a stale `hf_xet` copy from before this leg's closure change
was still importable at freeze time. `huggingface_hub` carries a guarded
`import hf_xet` in its download path; PyInstaller's module graph follows
that import whenever the module resolves in the build interpreter,
independent of what `uv.lock`/the exported closure say. A persistent
build env can equally mask a MISSING dependency, so the fix addresses
the apparatus, not just this one symptom.

**Correction (AC-15 fix, build 606698 — see the Leg 6 flight-log entry
of the same name)**: the sentence this replaces originally read "...so
`pip install -r` on the worker runs in hash-checking mode and cannot
re-resolve an unpinned package back in," implying the install mostly
succeeded and merely dropped `hf-xet`. That was wrong in mechanism. What
actually happens: `huggingface-hub`'s own wheel metadata still declares
`hf-xet` as a dependency (`[tool.uv] exclude-dependencies` removes it
from the lock/export, not from the wheel's declared `Requires-Dist`), so
pip's `--require-hashes` mode — implied whenever any line in the file
carries a hash, which `uv export` always emits — refuses to proceed at
all, because it cannot find a hash-pinned entry for that transitively
discovered requirement. The install fails and installs **nothing**, not
"everything except hf-xet." Build 606657 hit this exact pip failure too;
it went unnoticed only because it ran before the per-build-venv fix
below, against the persistent `C:\Python311` interpreter, whose
site-packages already held a full set of packages (including a stale
`hf_xet`) from prior successful builds — the failed install left that
stale environment in place and the freeze silently proceeded off it.
Build 606698, run after the per-build-venv fix landed, exposed the same
pip failure directly: the fresh venv had nothing to fall back on, pip
installed nothing at all, and the freeze failed loudly
(`ModuleNotFoundError: No module named 'uvicorn'`) instead of quietly
shipping a stale package. The complete fix is `--no-deps` on the
`pip install -r <uv export>` step in both CI lanes (a `uv export`
closure is already complete, so pip has nothing to resolve) plus
`$LASTEXITCODE` checks after every native step in
`ci/tasks/windows-installer-build.yml` (PowerShell's
`$ErrorActionPreference = "Stop"` does not react to a native
executable's exit code, which is how 606657's failure went unnoticed in
the first place) — on top of, not instead of, the per-build venv and the
spec's `excludes = ["hf_xet"]` below, both of which remain correct and
necessary for the reasons already given.

Two further changes, made against this same Leg 6 tree post-review:
1. `packaging/windows/the-one.spec`: `excludes = []` → `excludes =
   ["hf_xet"]`, with a comment recording the build-606657 evidence — this
   makes the bundle correct regardless of what else is importable in
   whatever environment runs the freeze.
2. `ci/tasks/windows-installer-build.yml`: after `Set-Location repo`,
   creates a fresh per-build `venv` (`& $py -m venv .buildvenv`, then
   `$py` repointed at `.buildvenv\Scripts\python.exe`) and installs the
   exported closure into that throwaway venv instead of the persistent
   `C:\Python311` base interpreter — every later use of `$py` (pip
   installs, `uv export`, `pip install -e . --no-deps`, `pip install
   pyinstaller`, `-m PyInstaller`, the `$ver` computation) runs through
   the venv python. `ci/README.md` and `the_one/agents.md`'s packaging
   notes were updated to record the lesson. The GitHub Actions
   `windows-installer.yml` lane needs no venv (a fresh `windows-2022` VM
   per job has no persistent site-packages to leak from), but it DID
   need the `--no-deps` install change recorded in the Correction below —
   a fresh runner fails exactly like build 606698 without it.

Linux-side verification of this second fix (a frozen Windows rebuild
itself is out of scope on this host — see Verification below):
`python -c "import ast; ast.parse(open('packaging/windows/the-one.spec').read())"`
passes; `python -c "import yaml; yaml.safe_load(open('ci/tasks/windows-installer-build.yml'))"`
loads and the embedded PowerShell block scalar reads correctly by eye
(every later `& $py` call resolves through the repointed venv path);
`ruff check the_one/ tests/ scripts/` and `ruff format --check the_one/
tests/ scripts/` both clean (the `.spec` and `.yml` files are outside
ruff's configured paths). `grep -rn "excludes = \[\]"` across the repo
finds no other code/config reference to the old empty-list form — the
only remaining hits are historical flight-log prose (Mission 23 Flight
1, describing the state as it was then) and one now-stale line in
`packaging/windows/README.md:235` ("PyNaCl / Discord voice" note), which
this fix left untouched as out of its stated scope; flagging it here for
a future maintenance pass.

## Verification

- `uv lock` resolved with no conflict: `Resolved 137 packages`, `Removed
  hf-xet v1.6.0`, `Removed sqlite-vec v0.1.9` — no other package's version
  moved (diffed against the pre-leg lock file).
- `grep -c 'hf-xet' uv.lock` → 1 (the `[manifest] excludes = ["hf-xet"]`
  metadata line `uv` itself records for the exclude directive — not a
  package entry; `grep -c 'name = "hf-xet"' uv.lock` → 0, confirming the
  package itself is gone).
- `uv export --no-dev --no-emit-project --extra gui --extra all-llms
  --format requirements-txt` contains no `hf-xet` line.
- `.venv/bin/pip-audit --disable-pip -r <that export>` → `No known
  vulnerabilities found` (matches `.github/workflows/pr-lint.yml`'s exact
  invocation; the plain `pip-audit -r` form without `--disable-pip` hits an
  unrelated pip-resolver error caused by `huggingface-hub`'s wheel metadata
  still declaring `hf-xet` as a platform-gated dependency even though it is
  excluded from the lock — a resolver artifact, not a vulnerability finding;
  see the Leg 6 flight-log entry).
- `.venv/bin/pip uninstall -y hf-xet` confirmed removed from this host's
  venv (targeted uninstall, matching the regenerated lock).
- `make test-unit`: see the Leg 6 flight-log entry for the figures (run once,
  alone, foreground).
- Frozen `fly execute` run and the installer-size comparison against the
  141,827,664-byte baseline: **Flight Director, AC-15** — not run by this
  leg's Developer per the leg spec's scope. Build 606620 caught the
  doctor-encoding crash; build 606657 caught the `hf_xet.pyd`
  persistent-worker leak fixed above (this build still measured
  141,812,423 bytes, essentially the baseline); build 606698 (the third
  run, first with the per-build venv) failed on the hash-mode `hf-xet`
  refusal and proved the 606657 install had failed silently. **Build
  606735 (the fourth frozen run) succeeded and met AC-15**: frozen
  doctor `RESULT: PASS`, all eight `doctor` gates OK (`usearch: OK`,
  `fts5: OK`, `embedding model: OK`, no `sqlite-vec:` line), the bundle
  listing free of both `_hf_xet*` and `vec0*`, installer
  `the-one-setup-0.8.1.exe` = 134,790,292 bytes against the
  141,827,664-byte baseline — a **7,037,372-byte (−5.0%) reduction**,
  consistent with `hf-xet` (4.03 MB) plus `sqlite-vec` and its bundled
  binaries being gone.

## Sign-Off
*(written at completion)*
**Reviewer**: Sonnet (flight-end review cycles 3–4 of M24 F02 L06)
**Verdict**: confirmed
**Commit**: `9b4e0fc`
