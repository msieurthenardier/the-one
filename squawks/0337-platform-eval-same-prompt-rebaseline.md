# Squawk 0337: re-baseline the platform eval set on the current prompt

**Status**: open
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
*(written at completion)*

## Verification
- A new baseline file (for example `evals/baselines/s14-platform.json`) is committed.
- `measure-prompt` on `main` prints a prompt fingerprint equal to the new baseline's.
- `CLAUDE.md` and `evals/README.md` name it as the current platform baseline.
