# Squawk 0049: `hf-xet` ships in the frozen bundle but nothing can ever call it

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-12
**Completed**: —

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
*(written at completion)*

## Verification
`uv lock` resolves with no conflict; `make test-unit` green; `pip-audit` clean on the release closure; `fly execute -c ci/tasks/windows-installer-build.yml` → `RESULT: PASS` with `embedding model: OK` and installer size recorded against 141,827,664 bytes.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
