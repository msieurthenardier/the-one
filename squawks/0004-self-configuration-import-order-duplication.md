# Squawk 0004: Factor the surface-row marker check into `constants.py` to remove import-order duplication

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-25
**Completed**: 2026-08-29

## Report

The `the_one/self_configuration/` package routes around a circular import by
duplicating the surface-row ownership-marker check. `credentials.py:load_from_rows`
re-implements the same marker predicate that `manage.is_surface_row` already
provides, inline, rather than calling it — because `manage` imports `surface` and
`surface` imports `manage` (function-local imports break the cycle at runtime). The
duplicated marker logic is exactly the "duplicate shape for import-order reasons"
pattern the Mission 20 debrief flagged as a recurring maintenance smell (its three
near-identical `auth_headers` implementations).

Servicing action: move the marker constant + the `is_surface_row`-style predicate
into the leaf `constants.py` module (which already holds `MOUNT_PATH` /
`CONFINED_SOURCE_PATHS` and imports nothing heavy), then have both `manage.py` and
`credentials.py` import it from there — removing the duplication and, ideally, the
function-local import dance.

Non-urgent watch-item raised by the Mission 21 Flight 1 debrief; do it if/when the
self-configuration package grows further.

## Evidence

- `the_one/self_configuration/credentials.py:load_from_rows` — inline marker check.
- `the_one/self_configuration/manage.py:is_surface_row` — the canonical predicate.
- `the_one/self_configuration/manage.py:enable` / `surface.py:_calling_agent` —
  function-local imports of each other to break the cycle.
- Precedent: Mission 20 debrief, "three near-identical `auth_headers`" finding
  (see squawk 0001).

## Corrective Action

Read both implementations first, as instructed, before unifying: `manage.py:54`'s
`is_surface_row` (`isinstance(marker, dict) and bool(marker.get("agent"))`) and
`credentials.py:load_from_rows`'s inline check (`not isinstance(marker, dict) or
not marker.get("agent")`, i.e. the negation of the same predicate) are
semantically identical for the marker check itself — `load_from_rows` also
filters on `source.type != "streamable-http"` first, but that's a separate,
unrelated filter kept in place, not part of the duplicated marker logic. No
divergence found, so proceeded with the unification as scoped.

Added to `the_one/self_configuration/constants.py` (still a leaf — no import
from `manage`, `surface`, `credentials`, or `the_one.db` at runtime):
- `OWNER_MARKER_KEY = "self_configuration"` — the marker key, previously an
  unnamed literal repeated in both call sites.
- `is_surface_row(source) -> bool` — the predicate moved verbatim from
  `manage.py:54`. Takes `source: "MCPSource"` under `TYPE_CHECKING` only (the
  runtime import is duck-typed on `source.config`), per the task's guidance,
  so the leaf-module invariant holds.

`manage.py`: deleted the local `is_surface_row` definition; imports it from
`.constants` instead (`from the_one.self_configuration.constants import
CREDENTIAL_SECRET_KEY, MOUNT_PATH, is_surface_row`). The name `manage.is_surface_row`
still resolves (module-level import binds it in `manage`'s namespace), so
every existing caller (`find_surface_row`, `reconcile_on_startup`,
`reject_foreign_surface_attachments`, `reject_surface_credential_overrides`,
and any test referencing `manage.is_surface_row`) is unaffected. Left
`owner_of`'s separate `"self_configuration"` literal and the marker-
construction sites (`enable`, `cascade_rename`) untouched — out of scope per
the task (predicate + constant move only).

`credentials.py:load_from_rows`: replaced the inline marker check with a call
to the shared predicate (`if not is_surface_row(source): continue`, kept
after the pre-existing `source.type != "streamable-http"` filter), and
updated the docstring's "duplicated inline ... to avoid a circular import"
note to reflect that both modules now import the predicate from `constants`.

Did not touch the function-local imports between `manage.py` and `surface.py`
(`manage.enable` / `surface._calling_agent`) — explicitly out of scope per
the task; the report's "ideally" language about unwinding those was not
requested as a squawk deliverable.

## Verification

- `grep -rn "is_surface_row\|OWNER_MARKER\|marker" the_one/self_configuration/*.py`
  — one definition of `is_surface_row` (in `constants.py:98`), one
  `OWNER_MARKER_KEY` (`constants.py:95`); all other hits are the import in
  `manage.py`/`credentials.py`, call sites, and docstring/comment prose
  referencing "marker" — no second implementation anywhere.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_self_configuration_surface.py tests/test_self_configuration_api.py
  tests/test_self_configuration_external.py tests/test_self_configuration_write.py
  tests/test_self_configuration_projection.py tests/test_imports.py -x
  --timeout 120` — 150 passed, 3 warnings (pre-existing deprecation warnings
  from `discord`/`websockets`, unrelated to this change).
- `.venv/bin/python -c "import the_one.self_configuration.constants"` as a
  first-touch import — succeeds (confirms `constants.py` still imports
  nothing from `the_one.db`, `manage`, `surface`, or `credentials` at
  runtime; the `MCPSource` reference is `TYPE_CHECKING`-only).
- `.venv/bin/ruff check .` — all checks passed. `.venv/bin/ruff format --check .`
  — 455 files already formatted, no diff.
- Scope check: `git status --short` shows exactly the three
  `self_configuration/` files (`constants.py`, `manage.py`, `credentials.py`)
  changed by this squawk, plus this artifact — no fourth file touched, no
  signature changes with outside callers, no test rewrites.
- The full `make test-unit` / `make test-browser` suites were not run
  standalone here — the Flight Director runs the whole suite once at the end
  of the batch, per this squawk's task instructions.

## Sign-Off

*(written at completion — Flight Director finalizes status/sign-off after
the batch-end `make test-unit` run)*
