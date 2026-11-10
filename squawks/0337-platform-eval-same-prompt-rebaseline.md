# Squawk 0337: re-baseline the platform eval set on the current prompt

**Status**: in-progress
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-08
**Completed**: —

## Report
`evals/baselines/s11-platform.json` was recorded on sortie 11's leg 2 prompt, before leg 3's tool-exposure wording landed. The current prompt's fingerprint differs from it, so every compare against it is a different-prompt compare and `--same-prompt` can never apply. Record a same-prompt baseline of the platform scenario set on the current prompt, for the default models (`haiku`, `qwen3-4b`, `lfm3`), and point `CLAUDE.md`'s and `evals/README.md`'s "current baseline" at it.

## Evidence
- Sortie 14 leg 2 (`sorties/14-anthropic-prompt-caching/flight-log.md`, Leg 2 and Deviations): `measure-prompt` fingerprint `84f8bf2e…` against the baseline's `df5f2249…`.
- That compare's size rows match this history. The tool totals equal the baseline's (1540 and 1283), and prompt text is below its maximum (316 against 354).
- Raised at the sortie 14 debrief, recommendation 1; the operator asked for a squawk. Sortie 12 also plans new same-prompt baselines and may absorb this item; if it does, close this squawk against it.
- Quota-heavy, with a long local run on the Ollama models. Per sortie 11 DD9, `gpt-oss` is not a default model.

## Corrective Action
Mission 35 Flight 2 leg 7 part B1 recorded same-prompt baselines on the shipped prompt (fingerprint `6f1eb7ab`, after the log-scale clause fix), n=20 on `haiku`, `qwen3-4b` and `lfm3`: `evals/baselines/m35f2-platform.json`, `m35f2-routines.json` and `m35f2-visuals.json` (`derive-bars --size-ratio 1.0`). Run directories `evals/runs/m35f2-{platform,routines,visuals}-n20` (gitignored). The operator accepted the one pass-rate hard failure of the different-prompt compare (lfm3 `routines-planted` 19/20, equal to its m35 baseline) at gate 1b on 2026-11-10. `CLAUDE.md` "Prompt evals" and `evals/README.md` now name the `m35f2-*` baselines as current and the `m35-*` ones as history. Left `in-progress`: the review sign-off is leg 7's later review, after which the status becomes `completed`.

## Verification
- A new baseline file (`evals/baselines/m35f2-platform.json`) is committed.
- `measure-prompt` on `main` prints a prompt fingerprint equal to the new baseline's.
- `CLAUDE.md` and `evals/README.md` name it as the current platform baseline.
