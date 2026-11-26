# Leg: python-size-ratchet

**Status**: completed
**Flight**: [Backend boundaries before connectors](../flight.md)

## Objective
Add a test that stops any Python module under `the_one/` from growing past 800 lines without a visible, reasoned allowance (T3). Also add one `logger.info` line to each create, update and delete path of the write services (P5, optional).

## Context
- Flight design decision: "The size ratchet follows `tests/test_area_module_size.py`".
- **The JS precedent** (`tests/test_area_module_size.py`, Mission 31):
  - `LIMIT = 800`.
  - `ALLOWANCE` maps each module that is over the limit to a ceiling.
  - An unlisted module over 800 lines fails.
  - A listed module over its ceiling fails.
  - A listed module at or under 800 lines fails too, naming the entry to remove, so the allowance only shrinks.
- **Python modules over 800 lines** at this branch's head:

  | Module | Lines |
  |---|---|
  | `interfaces/web/api.py` | 5108 |
  | `interfaces/web/app.py` | 4139 |
  | `db/repositories.py` | 4121 |
  | `db/schema.py` | 3627 |
  | `diagnostics.py` | 1364 |
  | `mcp/client.py` | 1171 |
  | `interfaces/desktop/shell.py` | 1162 |
  | `visuals/chart_image.py` | 1095 |
  | `tools/filesystem.py` | 844 |
  | `agent/factory.py` | 836 |
  | `tools/resolver.py` | 826 |
  | `routines/service.py` | 805 |

- **The parallel-work rule.** Sortie 20 (PR #392, open) grows `app.py` (+76), `repositories.py` (+51), `schema.py` (+37) and `api.py`. A ceiling pinned at today's count would fail that PR after its rebase.
  - The ratchet's point is that growth must be visible, not impossible.
  - A PR may raise a ceiling in the same diff, with a one-line reason on the entry.
  - The failure message says exactly that.
  - The Flight Director tells the Sortie 20 session about the ratchet once it lands.
- **P5** (2026-11-24 report). The new write services have no logging: `agent/service.py`, `agent/rules_service.py`, `llm/provider_service.py`, `secret_store/service.py`, `knowledge/service.py` and `gleepglorp/proposals/apply.py`. A create, update, delete or proposal apply leaves no server-side trace.

## Inputs
- Legs 1 and 2 are in the tree (uncommitted). `api.py` is now about 5108 lines.

## Outputs
- New `tests/test_python_module_size.py`, which mirrors `test_area_module_size.py`'s structure, messages and self-tests.
- Info log lines in the write services.

## Acceptance Criteria
- [ ] **AC1, the ratchet.**
  - `tests/test_python_module_size.py` scans every `*.py` under `the_one/`.
  - `LIMIT = 800`.
  - Its `ALLOWANCE` lists every module over the limit at its current line count, each with a short comment.
  - It enforces the three rules: an unlisted module over the limit fails, a listed one over its ceiling fails, and a listed one at or under 800 must be removed from the list.
  - Each failure message names the file and the remedy: split the module, or raise the ceiling in the same PR with a reason.
- [ ] **AC2, its own tests.** Like the JS guard, it tests `violations()` on synthetic inputs for each rule, and the real tree passes.
- [ ] **AC3, P5 logging.**
  - Each create, update and delete function in the six named modules, and each proposal apply, logs one `logger.info` line on success.
  - Each line carries the kind, the name or id, and the action. Values never appear: no secret value, header, prompt text or field values.
  - Use the module's existing `logger`, or add `logger = logging.getLogger(__name__)`.
  - A test with caplog proves one line per action, for one service, and that it holds no value. Use the secret store service, with a known secret value asserted absent.
- [ ] **AC4, the tier and lint.**
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes when no other test process is running.
  - `ruff check` and `ruff format --check` are clean.
- [ ] **AC5, docs.** CLAUDE.md or `the_one/agents.md` says the Python 800-line rule is now enforced, next to the existing JS guard mention. Grep `test_area_module_size` to find it. Keep it to one sentence.

## Verification Steps
Read the test file and the log-line diff. Check the outputs of the new tests, the caplog test, the tier, ruff and the doc diff.

## Implementation Guidance
1. Copy the structure of `tests/test_area_module_size.py`, pointing it at `the_one/` with `*.py`.
2. Fill `ALLOWANCE` from a fresh `wc -l` at implementation time, because Legs 1 and 2 changed `api.py`.
3. Add the info lines. Logging an action is not a behaviour change. Keep each line short, for example `logger.info("agent %s: updated", name)`.
4. Write the caplog test, then run the touched services' existing tests.
5. Run the unit tier once, then ruff.
6. Update the docs. Write the "Leg 3" entry in the flight log, then `[LAND:leg]`.

## Edge Cases
- **Generated or vendored Python under `the_one/`:** check whether any exists. Exclude it only with a reason.
- **A log line inside a `precheck` or `on_commit` hook:** log after a successful commit, not inside the transaction. In `change_agent`, log after `save` returns.
- **Never log `mcp_overrides`, secret values, headers, env or prompt text.**

## Files Affected
- new `tests/test_python_module_size.py`
- the six service modules named in AC3
- a new caplog test, for example in `tests/test_secret_store_service.py` or a new file
- one sentence in CLAUDE.md or `agents.md`

## Citation Audit
- `tests/test_area_module_size.py:1-40`: the rule text, `LIMIT`, `ALLOWANCE` and `violations()`. Verified.
- The Python module sizes above come from `find the_one -name '*.py' | xargs wc -l` on 2026-11-25, after Leg 2. Verified.
- P5's module list is from the 2026-11-24 report. Re-check at implementation.
