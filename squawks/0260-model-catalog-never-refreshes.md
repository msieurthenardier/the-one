# Squawk 0260: the model catalog never refreshes, because the seed lists a model the fetch no longer has

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-25
**Completed**: 2026-10-26

## Report
Every launch logs:

```
WARNING the_one.llm.model_catalog: model_catalog: fetch missing seed pair (anthropic, claude-3-5-haiku-20241022) — skipping cache write to protect existing catalog
```

The fetched upstream catalog no longer lists `claude-3-5-haiku-20241022`, but the bundled seed still does. The seed-coverage write guard refuses any fetched catalog that lacks a seed pair, so the fetch is thrown away on every launch, and the cached context-window catalog is never refreshed: new models and changed limits never arrive. It is not platform-specific. It was seen on macOS at Mission 32 Flight 3's HAT (P2) and applies everywhere.

## Evidence
- `the_one/llm/model_catalog.py`: the seed-coverage write guard (the `for provider, seed_models in seed_providers.items()` loop) returns False on the first seed pair missing from the projection.
- `the_one/llm/data/model_catalog.json:5`: `"claude-3-5-haiku-20241022": 200000` in the bundled seed.
- The hosted run `40214604211` (`macos-packages.yml`, lifecycle), `lifecycle/app.log` line 15, at every launch.

## Corrective Action
*(Candidates considered, kept for the record:)*
- refresh the seed and drop retired pairs (and keep it current with a test that the seed is a subset of a recorded upstream snapshot);
- or have the guard tolerate retired pairs (for example, require coverage of a large share of the seed, or exempt pairs the seed marks as retired), so one retired model never blocks every refresh.

The second choice changes the guard's design. If that is wanted, it escalates past a squawk.

## Verification
- A unit test feeds a projected catalog lacking one retired seed pair, and the cache is written (or the seed no longer lists it), with no warning.
- A launch with network access writes `model_catalog.json` and logs no "missing seed pair".

### Applied (Mission 32 Flight 4, leg 4 phase 4b)
**The original plan (refresh the seed and prune retired pairs) was replaced by the operator's decision, 2026-10-26: "seed as floor for now, get the updated list, then log an issue".** The design review ran the live fetch: 25 of the 77 seed pairs are gone upstream (14 anthropic, all 200k; 11 openai, seven of them 400k). Pruning them would lose those windows and the problem would recur at the next retirement. So:
- `the_one/llm/model_catalog.py::refresh_catalog_cache`: the all-or-nothing seed-coverage guard is now a merge. The seed is a floor: every seed pair the fetch lacks is added from the seed, and the fetched value wins where both have a pair. The guard that remains refuses the write (WARNING, returns False) only when the fetch projected zero models for a provider the seed covers (an empty or garbage payload; checked before the OpenAI floor, which would otherwise mask it). One INFO line reports the count of floored pairs; a normal launch logs no warning. Docstring updated. (This goes beyond the squawk's original scope; the operator approved it.)
- `scripts/refresh_model_catalog.py`: found NOT to keep seed pairs as a floor despite its docstring (a live run removed all 25 retired pairs). Added `merge_existing_seed`, so a regeneration keeps pairs upstream no longer lists at their recorded window.
- Seed regenerated live from models.dev on 2026-10-25 (`generated_at`): anthropic 25 -> 31 (6 added, 0 changed, 0 removed); openai 52 -> 63 (11 added, 0 changed, 0 removed); 25 retired pairs kept by the floor.
- `the-one doctor`: `model catalog: OK - seed resolves claude-sonnet-4-6 -> 1000000`.

### Verification results
- `tests/test_model_catalog_refresh.py`: `test_missing_seed_pair_is_kept_from_the_seed` (renamed and inverted from `test_guard_blocks_write_when_payload_missing_seed_pair`; also asserts no WARNING and one INFO line), `test_fetched_value_overrides_the_seed`, `test_provider_with_zero_fetched_models_is_refused`, `test_refresh_script_keeps_existing_seed_pairs`. Fixtures are built in the test; no upstream dump is committed. `pytest tests/test_model_catalog*.py tests/test_doctor.py`: 152 passed.
- A launch with network access: not run on this host (the unit tests cover the path); to be seen in the v0.12.0 field checks.

## Sign-Off
- **Reviewer:** Haiku, the Mission 32 Flight 4 leg 4 phase 4b checkpoint: `[HANDOFF:confirmed]`, no blocking issues.
- **Commit:** the flight/4 leg 4b commit on `flight/04-windows-and-release`. The live launch check ("no `missing seed pair` warning") is read from the dry run's macOS `app.log` in leg 5.

## Disposition
- **Logged** by the Flight Director at Mission 32 Flight 3's `macos-hat`, on the operator's decision ("Squawk it"). Mission 31 took ids 0257-0259, so this one is 0260.
- **Escalated and decided** by the operator (2026-10-26): redesign the guard as a seed floor. The longer-term fix, dynamic Claude windows from the Models API's `max_input_tokens`, is GitHub issue #316.
