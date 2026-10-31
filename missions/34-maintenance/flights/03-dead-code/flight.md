# Flight: Dead code

**Status**: ready
**Mission**: [Post-Mission-33 Maintenance](../../mission.md)

## Contributing to Criteria
- [ ] Dead code removed. *(#24, #25)*

---

## Pre-Flight

### Objective
Delete the code the 2026-10-30 inspection verified dead, then retire two production methods that only tests call. Keep every live trap intact. The repo is already clean, with no dead module and no unloaded asset, so this flight is small by design. Expect about 35 lines from the definite sweep and about 60 from the second leg, plus matching test lines.

### Open Questions
N/A. This is a maintenance flight. Whether to retire the rest of the test-only production code (finding #25's remainder) is an open operator decision. This flight takes only the two items the review settled.

### Design Decisions

**Verify each deletion again at leg time with a repo-wide grep that excludes `.claude/`**: the inspection's evidence is a snapshot, and the `.claude/worktrees/` repo copies inflate every grep.
- Rationale: a stale finding deletes live code.
- Trade-off: none.

**Leave `tools/resolver.py` alone**: sortie 07 rewrites it.
- Rationale: it avoids a collision.
- Trade-off: the stale `list_all` mention at `resolver.py:6` waits for sortie 07, or for squawk 0296 after it.

### Citation Audit

Verified at `e33e8657` by the 2026-10-30 Dead-code Inspector; spot-checked by the Flight Director:

| Citation | Status |
|---|---|
| `scripts/entrypoint.sh` — 4-line Docker-era `exec "$@"`, zero references in Makefile, ci, .github, docs or tests | verified |
| `scripts/ui_capture.py:750` `_tool_read_file` — not wired into any Surface `prepare=` | verified |
| `the_one/db/models.py:189` `VALID_ROUTING_SCOPES` — only its definition | verified |
| `the_one/mcp/cache_cleanup.py:68` `UV_ENVIRONMENTS_ROOT` — comment says "retained for backward compatibility", no importer | verified |
| `the_one/tools/_search_backends.py:539` `SEARCH_BACKENDS` — no importer | verified |
| `static/css/studio.css:236` `.self-configuration-toggle-switch` — no emitter | verified |
| `tests/conftest.py:215` `make_registry` — no consumers; documented at CLAUDE.md L457 | verified |
| `static/js/areas/studio/agent-editor.js:361` `App.studio.AGENT_PANEL_IDS` — no reader (low confidence) | verified (re-grep at leg time) |
| `the_one/encryption.py:198` `Encryptor.rotate_key` — called only by `tests/test_encryption.py:96-215`; the route `api.py::rotate_encryption_key` (~L6371) has its own implementation and tests | verified |
| `the_one/db/repositories.py:2462` `ToolConfigRepository.list_all` — tests only; docstring at L2433 says the resolver uses it, but `agent/factory.py:402` reads `list()` | verified |

### Prerequisites
- [ ] None beyond a green `make test-unit` at leg start.

### Pre-Flight Checklist
- [x] All open questions resolved (N/A, maintenance flight)
- [x] Design decisions documented
- [x] Citation Audit complete
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

**1. `definite-dead-sweep` (#24).** Delete:
- `scripts/entrypoint.sh`
- `_tool_read_file`
- `VALID_ROUTING_SCOPES`
- `UV_ENVIRONMENTS_ROOT` and its comment
- `SEARCH_BACKENDS`
- the `.self-configuration-toggle-switch` rule
- the `make_registry` fixture, together with its CLAUDE.md "Test patterns" bullet
- `App.studio.AGENT_PANEL_IDS`, if a fresh grep still finds no reader
- the single-reference test helpers `NO_SLEEP_HOOKS` (`tests/_evals_helpers.py`), `_MISSING` (`tests/_mcp_signin_helpers.py:26`) and `_origin` (`tests/browser/_nav.py:282`)

Also check the medium-confidence CSS variants `badge--local`, `badge--remote` and `ui-list-pane-compact` against the factories that build class names from options (`App.ui.badge.KINDS`, `listPane`). Delete a variant only if no option value can produce it.

Do not touch the traps the report lists:
- FastAPI handlers
- pydantic hooks
- the mcp `TokenStorage` methods
- Cocoa delegate callbacks and ctypes fields
- the `_reset_for_tests` helpers
- `StubPlugin.mark_dead`

Run the CSS ownership and emitted-class guards (`tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`) and `make test-unit`.

**2. `retire-test-only-methods` (#25, settled items).**
- **`Encryptor.rotate_key`.**
  - Delete the method and the `rotate_key` tests in `tests/test_encryption.py`.
  - Move the properties those tests alone cover to tests of the shared primitives (`stage_pending_key`, `promote_pending_key`, `install_key`): the 0o600 mode of the promoted key file, and in-place install.
  - Update the comment in `the_one/api_credential.py` that mentions it.
- **`ToolConfigRepository.list_all`.**
  - Delete it, re-point `tests/test_db_repositories.py` and `tests/test_factory.py` at `list()`, and fix the docstring at `repositories.py:2433`.
  - Leave `resolver.py:6` to sortie 07.
- **Verify.** The rotation route tests in `tests/test_provider_api.py` (`test_rotate_*`) and `tests/test_key_reconcile.py` stay green and unchanged.

### Checkpoints
- [ ] Sweep deleted, guards green
- [ ] Rotation primitives carry the 0o600 assertion

### Adaptation Criteria

**Divert if**:
- A fresh grep finds a live caller of any item. Drop that item and record why.

**Acceptable variations**:
- Leaving a medium-confidence CSS variant in place when an option could produce it.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `definite-dead-sweep` - Delete the verified-dead items and the `make_registry` fixture with its CLAUDE.md line.
- [ ] `retire-test-only-methods` - Delete `Encryptor.rotate_key` and `ToolConfigRepository.list_all`; move their coverage to the live code.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated (CLAUDE.md "Test patterns")

### Verification
- `make test-unit` is green with the same skips.
- `ruff check` is clean.
- `uvx vulture the_one/ evals/ scripts/ --min-confidence 60` no longer lists the deleted items.
- A repo-wide grep excluding `.claude/` finds no reference to any deleted name.
