"""Regenerate the bundled model-catalog seed from models.dev.

This script is invoked by ``make refresh-model-catalog``, which runs it
host-native against the repo venv.  It fetches ``https://models.dev/api.json``,
filters to the ``openai`` and ``anthropic`` providers, projects each model's
context window to the flat catalog shape (bare model ids → int), stamps
``generated_at`` and ``source``, and writes
``the_one/llm/data/model_catalog.json`` with stable key ordering for clean
diffs.

Bare-id contract
    models.dev may namespace model ids as ``openai/gpt-4o``.  The ``provider/``
    prefix is stripped before writing so runtime lookups receive bare ids (the
    ids that the SDKs return).

Floor / no-regression rule
    If models.dev returns a ``null`` or absent context field for a model that
    already appears in the seed, or if models.dev would regress a known window
    (returns a smaller value), the existing seed value is preferred.  The seed
    is the floor; the script never shrinks a window.

Seed pairs upstream no longer lists
    Every pair already in the seed that the fetch lacks is kept at its recorded
    window (squawk 0260), so a retired model never loses its window.

When to re-run
    Any time the seed needs refreshing against the upstream dataset.  The output
    is idempotent when models.dev returns the same data — only ``generated_at``
    and data changes produce a diff.

Usage::

    python scripts/refresh_model_catalog.py
    python scripts/refresh_model_catalog.py --out the_one/llm/data/model_catalog.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import httpx

# Shared projection helpers live in the runtime module so the background loop
# and this script share the same transform without duplication.
from the_one.llm.model_catalog import (
    _FETCH_TIMEOUT,
    _MODELS_DEV_URL,
    _OPENAI_FLOOR,
    apply_floor,
    project_raw,
)

# Paths resolved repo-relative from this file's location.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUT = _REPO_ROOT / "the_one" / "llm" / "data" / "model_catalog.json"


def fetch_and_project(url: str = _MODELS_DEV_URL) -> dict[str, dict[str, int]]:
    """Fetch models.dev synchronously and project to the flat catalog shape.

    Returns a dict keyed by provider name, each containing a dict of
    ``{bare_model_id: context_window}`` for models where a context window is
    available.

    Raises ``httpx.HTTPError`` or ``ValueError`` on fetch/parse failure — the
    caller handles these.
    """
    with httpx.Client(timeout=_FETCH_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()

    return project_raw(resp.json())


def write_catalog(
    providers: dict[str, dict[str, int]],
    out_path: Path,
    source: str = "models.dev",
) -> None:
    """Write the catalog JSON with stable key ordering."""
    catalog = {
        "generated_at": date.today().isoformat(),
        "source": source,
        "providers": {p: dict(sorted(models.items())) for p, models in sorted(providers.items())},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def merge_existing_seed(providers: dict[str, dict[str, int]], seed_path: Path) -> int:
    """Add every pair of the seed at ``seed_path`` that ``providers`` lacks.

    Returns the number of pairs added.  A missing or unreadable seed adds none.
    """
    try:
        existing = json.loads(seed_path.read_text(encoding="utf-8")).get("providers", {})
    except (OSError, ValueError):
        return 0
    added = 0
    for provider, models in existing.items():
        if not isinstance(models, dict):
            continue
        section = providers.setdefault(provider, {})
        for model, window in models.items():
            if model not in section and isinstance(window, int):
                section[model] = window
                added += 1
    return added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--out",
        type=Path,
        default=_DEFAULT_OUT,
        help=f"Output path for the catalog JSON (default: {_DEFAULT_OUT})",
    )
    parser.add_argument(
        "--url",
        default=_MODELS_DEV_URL,
        help=f"models.dev API URL (default: {_MODELS_DEV_URL})",
    )
    args = parser.parse_args(argv)

    print(f"Fetching {args.url} …")
    try:
        providers = fetch_and_project(args.url)
        source = "models.dev"
    except Exception as exc:
        print(f"ERROR: fetch failed — {exc}", file=sys.stderr)
        print(
            "Hint: run with network access, or hand-author the seed per the leg-01 Edge Cases "
            "guidance and record the deviation in the flight log.",
            file=sys.stderr,
        )
        return 1

    # Apply no-regression floor for OpenAI.
    providers = apply_floor(providers, _OPENAI_FLOOR, "openai")

    # The existing seed is a floor too (squawk 0260): a pair upstream no longer
    # lists keeps its recorded window, and a fetched value wins where both have one.
    kept = merge_existing_seed(providers, args.out)
    if kept:
        print(f"Kept {kept} existing seed pair(s) upstream no longer lists")

    write_catalog(providers, args.out, source=source)

    total = sum(len(m) for m in providers.values())
    print(f"Wrote {args.out} — {len(providers)} providers, {total} models")
    for prov, models in sorted(providers.items()):
        print(f"  {prov}: {len(models)} models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
