# Squawk 0003: `the_one.db.repositories` fails as a first-touch import in a fresh process

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-08-25
**Completed**: —

## Report

Importing `the_one.db.repositories` (or `the_one.interfaces.web.api`, which pulls
it in) as the very first `the_one`-touching import in a fresh Python process
raises a circular-import error: `repositories.py`'s
`from the_one.agent.config import AgentConfig` transitively re-enters
`the_one.mcp._pool`'s `from the_one.db.repositories import MCPSourceRepository`
before that class has finished defining.

Does **not** manifest in `make test-unit` or any real entrypoint (`the-one serve`,
CLI, tests) because other modules are imported first and warm the cycle. Surfaced
only by a bare `.venv/bin/python -c "import the_one.interfaces.web.api"`.

Discovered during Mission 21 Flight 1 (Leg 1 design review) as flight-log
Anomaly A10; deferred to a squawk at flight end per the out-of-scope-defect rule.

## Evidence

- `.venv/bin/python -c "import the_one.interfaces.web.api"` on a clean checkout →
  `ImportError` (partially-initialized module) from the
  `agent.config` → `mcp._pool` → `db.repositories` re-entry.
- `the_one/db/repositories.py`: top-level `from the_one.agent.config import AgentConfig`.
- `the_one/mcp/_pool.py`: `from the_one.db.repositories import MCPSourceRepository`.

## Corrective Action

*(written at completion)*

## Verification

*(written at completion)*

## Sign-Off

*(written at completion)*

## Disposition

**Deferred**: cosmetic/latent — no production path or test hits it, and Mission 21
Flight 1's own additions (`the_one.config`, `the_one.encryption`, both leaf
modules) neither touch nor worsen it. Revisit when a genuinely first-touch import
of `db.repositories` becomes necessary (e.g. a new standalone script or a
packaging entrypoint that imports it before the web/CLI modules), or during a
maintenance cycle addressing import-graph hygiene. Candidate fix: make the
`AgentConfig` import in `repositories.py` function-local, or break the
`mcp._pool` → `db.repositories` edge.
