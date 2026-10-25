# Squawk 0260: the model catalog never refreshes, because the seed lists a model the fetch no longer has

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-25
**Completed**: —

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
*(written at completion)*. Candidates:
- refresh the seed and drop retired pairs (and keep it current with a test that the seed is a subset of a recorded upstream snapshot);
- or have the guard tolerate retired pairs (for example, require coverage of a large share of the seed, or exempt pairs the seed marks as retired), so one retired model never blocks every refresh.

The second choice changes the guard's design. If that is wanted, it escalates past a squawk.

## Verification
- A unit test feeds a projected catalog lacking one retired seed pair, and the cache is written (or the seed no longer lists it), with no warning.
- A launch with network access writes `model_catalog.json` and logs no "missing seed pair".

## Sign-Off
*(written at completion)*

## Disposition
- **Logged** by the Flight Director at Mission 32 Flight 3's `macos-hat`, on the operator's decision ("Squawk it"). Mission 31 took ids 0257-0259, so this one is 0260.
- **Escalate if** the fix means redesigning the coverage guard rather than refreshing the seed.
