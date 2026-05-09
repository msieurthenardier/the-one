# Leg: 00-maintenance-bundle

**Status**: completed
**Flight**: [Studio MCPs tab + inspector polish](../flight.md)

## Objective

Bundle six independent F6.5 + F6.6 carry-forward maintenance items into a single leg: docs-first additions to `MCPClient.connect()` docstring, `mission.md`, and `CLAUDE.md`; pytest deselect-count investigation+comment; one new cross-check test for `OAUTH_MANAGED_SECRET_KEYS`; and a pytest-marker migration that re-includes `tests/test_mcp_pool.py`'s 10 pure-unit tests in the default run while cleanly deselecting its 2 bwrap-dependent tests.

## Context

- All six items come from the F6.5 + F6.6 debriefs' Action Items, classified `confirmed-live` in the F8 Reconnaissance Report. None has been silently fixed; each is real outstanding work.
- Per Design Decision §7, the bundle is ordered docs-first → code-second so reviewers can scan the docs additions, then the test/config additions. Each item is independent and ≤30 LOC; combined LOC ~150-200 across 5-7 files.
- F6.6 landed `connect()`'s `except* (OAuthFlowError, OAuthTokenError)` translation block at `client.py:250-269` and the broader 401-translation pattern documented in `CLAUDE.md` lines 340-351. These items propagate that contract into the function's own docstring (item 1) and into `mission.md` as a cross-flight constraint (item 2).
- F6.6's Anomaly A2 retro re-exported `App.areas`; that's already shipped. F8 inherits the F6.6 deviation but will add a lock-test for the array shape — but that lock-test belongs to L3 (per Design Decision §4), NOT L0.
- The `tests/test_mcp_pool.py` `--ignore=` directive **lives only in flight artifacts** (verified at design time — no `pyproject.toml`/`Makefile`/`.github/workflows/` reference). So today, the file already runs by default and the 2 bwrap tests skip via `pytest.mark.skipif`. The migration is architectural cleanup: replace silent `skipif` with explicit deselection by marker, making the deselect math explicit.

## Inputs

- `the_one/mcp/client.py` exists with `connect()` defined at `client.py:connect` — the function has NO docstring today (line 205 `async def connect(self) -> None:` goes straight to code).
- `the_one/mcp/oauth/storage.py` exists with `OAUTH_MANAGED_SECRET_KEYS` frozenset at `storage.py:OAUTH_MANAGED_SECRET_KEYS` (lines 51-60) and `MCPSourceTokenStorage.set_tokens` at `storage.py:set_tokens` (lines 107-132).
- `tests/test_mcp_pool.py` exists with `requires_bwrap = pytest.mark.skipif(...)` at `tests/test_mcp_pool.py:36-39` and two `@requires_bwrap`-decorated tests at lines 322 and 354.
- `pyproject.toml` exists with `[tool.pytest.ini_options]` declaring `markers = [...]` at lines 56-60 and `addopts = "-m 'not live and not browser and not pixel' --import-mode=importlib"` at line 54.
- `CLAUDE.md` exists; the "MCP Error Translation Contracts" section is at lines 340-358; the "Testing" section starts at line 409.
- `missions/07-mcp-integration/mission.md` exists; "Constraints" section starts at line 57.

## Outputs

- `the_one/mcp/client.py::MCPClient.connect` has a docstring with a `Raises:` block.
- `missions/07-mcp-integration/mission.md` has a 5-7-line entry codifying the `connect()` exception-translation contract under Constraints.
- `CLAUDE.md` has a 3-5-line addition under the Testing section explaining `tests/test_mcp_pool.py`'s historic exclusion + current marker-based filtering.
- `pyproject.toml::addopts` has a same-line trailing comment showing the per-marker count math (e.g. `# 306 deselected: live=N, browser=M, pixel=K`).
- `tests/test_mcp_oauth_storage.py` (new test file OR appended to an existing oauth-storage-related test file — see Implementation Guidance) has one new test fixture-cross-checking `set_tokens` writes against `OAUTH_MANAGED_SECRET_KEYS`.
- `tests/test_mcp_pool.py:36-39` no longer assigns `requires_bwrap = pytest.mark.skipif(...)`; the two `@requires_bwrap` decorations now resolve to `pytest.mark.requires_bwrap` (a registered marker).
- `pyproject.toml::[tool.pytest.ini_options]::markers` includes a `requires_bwrap: ...` entry.
- `pyproject.toml::addopts` includes `and not requires_bwrap`.
- `flight-log.md` updated with the L0 entry; the leg's status is `completed`; L0 is checked off in `flight.md`.

## Acceptance Criteria

- [ ] **L0.1** — `MCPClient.connect()` has a docstring with a `Raises:` block enumerating, at minimum: `MCPConnectionError`, `MCPVersionMismatch`, `MCPAuthRequired`, `MCPCapabilityMissing`, `MCPSandboxError`. Each entry is one short line ≤120 chars naming the trigger condition. `pytest tests/test_mcp_client.py -q --timeout 60` passes (no behavior change).
- [ ] **L0.2** — `mission.md` has a new bullet under Constraints (or a clearly-titled subsection if the project's mission constraints are bullet-only) codifying the F6.6 `connect()` exception-translation contract. The bullet names: the four-class translation set (`MCPConnectionError`, `MCPVersionMismatch`, `MCPAuthRequired`, `MCPSandboxError`), explicit invariant that `MCPToolProvider.get_tools_for_agent` graceful-skips all four, and a forward-ref to `CLAUDE.md`'s detailed contract section. ≤7 lines.
- [ ] **L0.3** — `CLAUDE.md` "Testing" section has a 3-5-line addition documenting `tests/test_mcp_pool.py`'s exclusion history and the post-L0 state (10 unit tests run by default; 2 `@pytest.mark.requires_bwrap` tests deselected by `addopts`). The text references the marker name verbatim.
- [ ] **L0.4** — `pyproject.toml::addopts` has a comment showing the per-marker deselection count math. The implementer FIRST runs `pytest --collect-only -q -m "live or browser or pixel"` (and same for the new `requires_bwrap` once registered) to get the live counts, THEN writes the comment. Format: `# N deselected: live=A, browser=B, pixel=C, requires_bwrap=D` either as a `# ` leading comment-line above `addopts =` or as a same-line trailing comment — whichever ruff/the existing pyproject style accepts. The total in the comment matches the actual default-run deselection count at L0 commit time.
- [ ] **L0.5** — A new test in `tests/test_mcp_oauth_storage.py` (or `tests/test_mcp_oauth.py` if that's the existing oauth-related test home — implementer chooses based on existing repo conventions, see Implementation Guidance) does the following: constructs an `OAuthToken` with every optional field populated (`access_token`, `token_type`, `expires_in`, `refresh_token`, `scope`); awaits `MCPSourceTokenStorage.set_tokens(token)` against a recording stub repo; asserts that the set of secret keys WRITTEN by `set_tokens` is a subset of `OAUTH_MANAGED_SECRET_KEYS`. The test passes today and would fail loudly if a future PR adds a key write without updating the frozenset. Test name pattern: `test_set_tokens_writes_only_managed_secret_keys` (or close).
- [ ] **L0.6** — `tests/test_mcp_pool.py:36-39` removes the local `requires_bwrap = pytest.mark.skipif(...)` assignment; the two existing `@requires_bwrap` decorators (lines 322, 354) become `@pytest.mark.requires_bwrap`. `pyproject.toml::[tool.pytest.ini_options]::markers` adds an entry `"requires_bwrap: marks tests that need a real bwrap binary in $PATH (deselect with '-m \"not requires_bwrap\"')"`. `pyproject.toml::addopts` is extended from `-m 'not live and not browser and not pixel'` to `-m 'not live and not browser and not pixel and not requires_bwrap'`.
- [ ] **L0.7** — Default `pytest -q --timeout 60` (run inside `docker compose exec the-one`) passes with no new failures vs main; `tests/test_mcp_pool.py`'s 10 unit tests run successfully; the 2 bwrap-dependent tests **in `tests/test_mcp_pool.py` specifically** are deselected (NOT skipped — the marker filter excludes them at collection time). Concretely: `pytest --collect-only -q -m "requires_bwrap" tests/test_mcp_pool.py` shows exactly 2 tests; default `pytest -q tests/test_mcp_pool.py` runs 10 tests and reports 2 deselected. **Note**: `tests/test_mcp_sandbox_integration.py`'s ~13 `@requires_bwrap`-decorated tests retain their existing skipif-driven SKIP behavior (intentionally out of scope per Edge Cases) — the global marker registration in `pyproject.toml` does NOT collide with the local `MarkDecorator` object in that file.
- [ ] **L0.8** — `flight-log.md` gets a new "Leg Progress" entry naming each item, status `completed`. Leg artifact's status field flipped from `in-flight` to `landed` (the final commit step then flips it to `completed`).

## Verification Steps

1. **L0.1** — Open `the_one/mcp/client.py` at `connect`; confirm the docstring presence with a `Raises:` block. Run `pytest tests/test_mcp_client.py -q --timeout 60` — passes.
2. **L0.2** — Open `mission.md`; confirm the new bullet under Constraints; ≤7 lines; references `CLAUDE.md`'s contract section.
3. **L0.3** — Open `CLAUDE.md` Testing section; confirm 3-5-line addition naming `requires_bwrap`. `grep -n "requires_bwrap" CLAUDE.md` returns the new content.
4. **L0.4** — Run `pytest --collect-only -q` and confirm the deselected count matches the math written in the `addopts` comment. Run `pytest --collect-only -q -m "live or browser or pixel or requires_bwrap"` to break down per marker; the comment numbers MUST match.
5. **L0.5** — Run `pytest tests/test_mcp_oauth_storage.py -q --timeout 60` (or wherever the new test lives) — passes. Optionally: temporarily monkey-patch `set_tokens` to write a bogus key (e.g. `secrets["foo"] = "bar"`); rerun — the new test fails. Revert the monkey-patch before commit.
6. **L0.6** — Run `pytest --collect-only -q -m "requires_bwrap" tests/test_mcp_pool.py` — should list exactly 2 tests (lines 322 and 354 originals). Run `pytest -q tests/test_mcp_pool.py --timeout 60` — should report 10 passed + 2 deselected.
7. **L0.7** — Run `docker compose exec the-one pytest -q --timeout 120` — passes; no new failures vs main.
8. **L0.8** — Open `flight-log.md`; new entry present; leg status updated. The post-completion checklist's leg-status flip happens in the final commit step at flight close, not per-leg in this batched flight.

## Implementation Guidance

### Preferred ordering (docs-first → code-second, per Design Decision §7)

1. **L0.1** — Add the `Raises:` docstring to `MCPClient.connect()`.
2. **L0.2** — Add the cross-flight constraint bullet to `mission.md`.
3. **L0.3** — Add the `tests/test_mcp_pool.py` rationale paragraph to `CLAUDE.md` Testing section.
4. **L0.6** — Migrate `requires_bwrap` to a true pytest marker (do this BEFORE L0.4 so the new `requires_bwrap` deselect bucket exists when L0.4 measures).
5. **L0.5** — Add the `OAUTH_MANAGED_SECRET_KEYS` cross-check test.
6. **L0.4** — Investigate and document the pytest deselect count. **Do not finalize the comment until L0.5 + L0.6 have landed** — the comment captures the post-leg deselection math, not a transient mid-leg count. Run the `--collect-only -q -m "..."` commands AFTER L0.5 + L0.6 are in the working tree.
7. **CLAUDE.md test-count update** — If L0.5 added a test (it does — one new test in `tests/test_mcp_oauth_storage.py`), the existing CLAUDE.md Testing line "~212 tests in <6s" needs to bump by +1 (or by however many tests actually land — the implementer counts via `pytest --collect-only -q | tail -3` and updates the count if it changed). One-line edit, paired with L0.3.

### Item-by-item

#### L0.1 — `MCPClient.connect()` docstring with `Raises:` block

Insert a docstring as the first statement of `connect()` at `the_one/mcp/client.py:connect` (function header at line 205; the first executable statement today is the `if self._is_alive: raise ...` at line 206). The docstring ends just before that check.

The Raises block enumerates these five exceptions (cross-checked against the function body at design time):
- `MCPConnectionError` — already-connected guard, `asyncio.TimeoutError` on initialize, transport-layer non-401 failures (incl. cleanup-after-cancel diagnostics), and the catchall `(Exception, BaseExceptionGroup)` collapse.
- `MCPVersionMismatch` — server announces a `protocolVersion` not in `mcp.shared.version.SUPPORTED_PROTOCOL_VERSIONS` (raised by the SDK as `RuntimeError` and translated, plus the explicit post-init membership check at `client.py:386`).
- `MCPAuthRequired` — three sources per `CLAUDE.md` "MCP Error Translation Contracts": SDK auth-flow exceptions (`OAuthFlowError`/`OAuthTokenError`) caught in the inner `except*`; transport-level 401 walked out of `BaseExceptionGroup.subgroup(httpx.HTTPStatusError)`; never from the `except asyncio.CancelledError` branch (post-F6.6).
- `MCPCapabilityMissing` — server initialize handshake returns `result.capabilities.tools is None` (post-init check at `client.py:390-392`).
- `MCPSandboxError` — stdio transport only; bwrap rejected the spawn before the target was successfully exec'd; propagates from `_cleanup_after_failed_connect`'s narrow `except MCPClientError` re-raise (per `_cleanup_after_failed_connect`'s docstring at `client.py:402-414`).

Suggested form (illustrative — implementer may rephrase for clarity):

```python
async def connect(self) -> None:
    """Run the MCP lifecycle handshake: open transport, initialize, version-gate, capability-gate.

    On success: ``_is_alive=True``, ``_capabilities`` and ``_protocol_version``
    populated. On failure: state restored to disconnected (transport stack
    closed or abandoned) and one of the typed exceptions below raised.

    Raises:
        MCPConnectionError: Already-connected guard; initialize timeout; transport-layer
            non-401 failures; cleanup-deadlock recovery diagnostics. Catchall.
        MCPVersionMismatch: Server announces a protocolVersion outside the SDK's
            SUPPORTED_PROTOCOL_VERSIONS set.
        MCPAuthRequired: SDK auth-flow exceptions (OAuthFlowError / OAuthTokenError) or
            transport-level 401 walked out of a BaseExceptionGroup. resource_metadata_url
            populated only on the WWW-Authenticate path.
        MCPCapabilityMissing: Server initialize result lacks the tools capability.
        MCPSandboxError: Stdio transport only — bwrap rejected the spawn (writable_paths
            invalid, EPERM on unshare, bwrap missing) before the target exec'd.
    """
```

Keep total docstring ≤20 lines. Do NOT mention F6.6 / F6.5 leg numbers in the docstring (those are in code comments).

#### L0.2 — Cross-flight constraint in `mission.md`

Add a new bullet under the existing Constraints section. Position: insert after the "Spec compliance against a moving target" bullet (or wherever the project's mission convention groups cross-flight invariants — implementer's discretion). Suggested wording (≤7 lines):

```markdown
- **`MCPClient` exception-translation contract is a cross-flight invariant**: `MCPClient.{connect, list_tools, call_tool}` raise EXACTLY one of `MCPVersionMismatch`, `MCPAuthRequired`, `MCPSandboxError` (stdio only), or `MCPConnectionError` (catchall). `MCPToolProvider.get_tools_for_agent` graceful-skips all four. Adding a fifth typed exception to this surface requires updating BOTH the translator and every consumer's match list — see `CLAUDE.md` "MCP Error Translation Contracts" for the canonical contract.
```

This is the F6.6 cross-flight contract being lifted from leg-level documentation to mission-level constraint, where future flights designing against it will see it as authoritative.

#### L0.3 — `CLAUDE.md` Testing section addition

Insert a 3-5-line paragraph under Testing — natural anchor is right after the existing "Unit tests run by default..." line. Suggested wording:

```markdown
**`tests/test_mcp_pool.py`** ships 10 pure-unit pool tests + 2 bwrap-dependent integration tests. The integration tests use `@pytest.mark.requires_bwrap` (registered in `pyproject.toml::markers`) and are deselected by default via the `not requires_bwrap` clause in `addopts`. To run the integration tests on a host with bwrap available: `pytest -m requires_bwrap tests/test_mcp_pool.py`.
```

#### L0.4 — pytest deselect count investigation + comment

Run inside the dev container:

```bash
docker compose exec the-one pytest --collect-only -q | tail -3
docker compose exec the-one pytest --collect-only -q -m "live" | tail -3
docker compose exec the-one pytest --collect-only -q -m "browser" | tail -3
docker compose exec the-one pytest --collect-only -q -m "pixel" | tail -3
docker compose exec the-one pytest --collect-only -q -m "requires_bwrap" | tail -3
```

Capture the per-marker counts from each run (the lines like `N deselected`). Sum to the total deselected. Add a comment ABOVE the `addopts =` line in `pyproject.toml`:

```toml
# Per-marker deselect math (last verified L0): live=A, browser=B, pixel=C, requires_bwrap=D, total=N
addopts = "-m 'not live and not browser and not pixel and not requires_bwrap' --import-mode=importlib"
```

If the existing pyproject style or ruff prefers same-line trailing comments, use that instead — implementer's discretion within the project's lint/style constraints.

**Important**: do this AFTER L0.6 lands so the `requires_bwrap` count is non-zero. Then re-run after L0.5 lands the new oauth-storage test to confirm the live count didn't shift the deselected math.

#### L0.5 — `OAUTH_MANAGED_SECRET_KEYS` cross-check test

Search for the existing oauth-storage test home: `find tests -name "test*oauth*" -o -name "test*storage*" -type f` to find a natural location. If `tests/test_mcp_oauth_storage.py` exists, append; otherwise create the file with module-level imports.

Test shape (one test):

```python
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.shared.auth import OAuthToken

from the_one.db.models import MCPSource
from the_one.mcp.oauth.storage import (
    MCPSourceTokenStorage,
    OAUTH_MANAGED_SECRET_KEYS,
)


async def test_set_tokens_writes_only_managed_secret_keys() -> None:
    """`set_tokens` must NOT write a secrets key absent from OAUTH_MANAGED_SECRET_KEYS.

    Fails loud if a future PR adds a `secrets["foo"] = ...` write without also
    updating the frozenset; api.py / streamable_http.py rely on the frozenset
    to strip-and-preserve OAuth state on PUT and to filter non-string values
    out of the merged HTTP-headers dict.
    """
    # Build a stub MCPSource with empty starting secrets.
    src = MCPSource(
        id="src-test",
        name="test",
        type="streamable-http",
        config={"url": "https://example.test/mcp"},
        secrets={},
    )

    # Recording-stub repo: get returns the seeded src; update captures the
    # post-write secrets dict for assertion.
    repo = MagicMock()
    repo.get = AsyncMock(return_value=src)
    written: dict = {}
    async def _capture_update(updated):
        written.update(updated.secrets)
    repo.update = AsyncMock(side_effect=_capture_update)

    storage = MCPSourceTokenStorage(repo, source_id=src.id)
    token = OAuthToken(
        access_token="at",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="rt",
        scope="scope1 scope2",
    )
    await storage.set_tokens(token)

    extra_keys = set(written.keys()) - OAUTH_MANAGED_SECRET_KEYS
    assert not extra_keys, (
        f"set_tokens wrote keys outside OAUTH_MANAGED_SECRET_KEYS: {extra_keys}. "
        f"Either update the frozenset or remove the unmanaged write."
    )
```

The recording stub is preferred over a real `MCPSourceRepository` because (a) it removes DB setup overhead, (b) it keeps the test's failure mode narrowly focused on the `set_tokens` contract — not on repo internals.

**Mutability precondition (verified at design time)**: `MCPSource` (`the_one/db/models.py:50`) inherits `BaseModel` with NO `model_config` override, so it's NOT frozen — `source.secrets = secrets` reassignment in `set_tokens` works under Pydantic v2 defaults. The test relies on the same mutation path the production `set_tokens` uses; if a future PR freezes `MCPSource`, both the production code and this test break together (the desired coupling).

**`expires_in=None` delete-path note**: with `expires_in=None`, `set_tokens` runs `del secrets["token_expires_at"]` (or no-ops if absent). The deletion path can never add a key outside the frozenset, so the test's subset-check is sound regardless of `expires_in`'s value. The all-fields-populated case in this test exercises the maximum write surface (5 conditional writes); the additional negative case (`expires_in=None` after a prior populated write) is the existing get_tokens/set_tokens round-trip tests' job, not L0.5's.

#### L0.6 — Pytest marker migration

In `tests/test_mcp_pool.py`:
- Delete lines 36-39 (the `requires_bwrap = pytest.mark.skipif(...)` block) and the now-unneeded `import shutil` (line 26) IF nothing else in the file imports `shutil`. Check first: `grep -n "shutil" tests/test_mcp_pool.py` — if only line 26 + lines 36-39 reference it, drop the import.
- Replace the two `@requires_bwrap` decorators (lines 322 and 354 today) with `@pytest.mark.requires_bwrap`.

In `pyproject.toml`:
- Extend `markers` list with `"requires_bwrap: marks tests that need a real bwrap binary in $PATH (deselect with '-m \"not requires_bwrap\"')"`.
- Extend `addopts` from `-m 'not live and not browser and not pixel'` to `-m 'not live and not browser and not pixel and not requires_bwrap'`.

**Scope note**: `tests/test_mcp_sandbox_integration.py:86` ALSO defines a local `requires_bwrap = pytest.mark.skipif(...)`. The flight design Decision §7 #6 names ONLY `tests/test_mcp_pool.py`. Do NOT migrate the sandbox-integration file in this leg — that is a separate cleanup with its own collection-count + deselect-math implications, and the implementer should respect the flight's scope. If the implementer feels strongly about the inconsistency, leave a TODO comment near the sandbox-integration `skipif` referring to L0 and surface it in the flight log under Decisions; do NOT extend the file edit.

### Test runner notes

All test runs go inside the dev container (`docker compose exec the-one ...`) per project convention. Use `--timeout 60` for the per-test bound (the project's pytest-timeout is configured project-wide; the per-CLI flag matches the leg-execution prompt's "fail fast" guidance).

If `docker compose exec the-one ...` fails, the implementer should NOT silently fall back to host-side pytest — diagnose first (likely the dev container isn't running). Run `docker compose up -d the-one` and retry.

## Edge Cases

- **L0.1 docstring placement**: there is currently NO docstring on `connect()`. The first executable statement is `if self._is_alive: raise ...` at line 206. The docstring goes between the `async def connect(self) -> None:` signature line and that `if` — Python's standard module-level docstring placement.
- **L0.2 mission constraint placement**: implementer chooses the natural insertion point under Constraints. The bullet's content is what matters; its position within the section is secondary.
- **L0.4 deselect-count drift**: if L0.5 lands a new test that gets ANY marker (it shouldn't — the new oauth-storage test is unmarked), the deselect count won't shift. But the comment specifies "last verified L0" so future drift after L0 is the next maintenance leg's problem, not L0's.
- **L0.5 test home**: `find tests -iname "*oauth*"` should locate the existing storage tests (likely `tests/test_mcp_oauth_storage.py` per project naming convention `test_<module>.py`). If no such file exists, create it. Do NOT append to `tests/test_mcp_pool.py` — that file's purpose is pool primitives, not storage.
- **L0.6 import cleanup**: after deleting the skipif block, `import shutil` may be unused. Verify with `grep -n "shutil" tests/test_mcp_pool.py` BEFORE removing — the file is 770 lines; another usage is plausible.
- **L0.6 sandbox-integration scope**: do NOT migrate `tests/test_mcp_sandbox_integration.py:86`. Reasons documented in Implementation Guidance. **The global pytest-marker registration in `pyproject.toml::markers` does NOT collide with the local `requires_bwrap = pytest.mark.skipif(...)` `MarkDecorator` object in that file** — pytest marker registration is metadata only; a Python module is free to bind the same name to a different `MarkDecorator`. Runtime behavior of sandbox-integration's tests is unchanged: they continue to SKIP (not deselect) when bwrap is missing, exactly as today.
- **CLAUDE.md anchor stability**: project-owned artifact (per the mission-control skill–project boundary rule). Use the existing "Testing" heading as the semantic anchor, not a literal line number — the implementer locates it by section name and inserts in the natural spot.
- **Flight artifact updates**: per project convention, this leg's commit happens at flight-end (single batched commit per `/agentic-workflow`). The leg artifact's status flip and the flight.md checkbox tick happen in that final commit, not as a per-leg commit.

## Files Affected

- `the_one/mcp/client.py` — add docstring on `MCPClient.connect`. ~15-20 lines added; 0 lines deleted.
- `missions/07-mcp-integration/mission.md` — add 1 bullet (≤7 lines) under Constraints. ~7 lines added.
- `CLAUDE.md` — add 3-5-line paragraph under Testing. ~5 lines added.
- `pyproject.toml` — extend `addopts` (1 string change); extend `markers` (1 list entry); add per-marker count comment (1-2 lines). ~3 lines net change.
- `tests/test_mcp_pool.py` — delete `requires_bwrap = pytest.mark.skipif(...)` block (lines 36-39); maybe delete `import shutil` (line 26 if unused); update 2 decorators. Net ~-4 lines.
- `tests/test_mcp_oauth_storage.py` (new OR appended) — add `test_set_tokens_writes_only_managed_secret_keys`. ~40-50 lines added if new file (with imports + test); ~30 lines if appending.
- `missions/07-mcp-integration/flights/08-studio-mcps-tab/flight-log.md` — append L0 progress entry.
- `missions/07-mcp-integration/flights/08-studio-mcps-tab/flight.md` — check off L0 in legs list (final commit step).
- `missions/07-mcp-integration/flights/08-studio-mcps-tab/legs/00-maintenance-bundle.md` — update status to `landed` (final commit step).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `pytest -q --timeout 60` (default suite) passes inside the dev container with no new failures
- [ ] `pytest --collect-only -q -m "requires_bwrap" tests/test_mcp_pool.py` reports exactly 2 tests
- [ ] Update `flight-log.md` with the L0 progress entry (under "Leg Progress")
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT commit yet — orchestrator batches code review + commit at flight end
- [ ] Do NOT signal `[COMPLETE:leg]` — orchestrator handles final flight close
- [ ] Signal `[HANDOFF:review-needed]` per the leg-execution-phase implement prompt's batched-commit contract

## Citation Audit

8 citations verified against current code at leg design time:

- `client.py:connect` (function header at line 205, no docstring) — **OK**.
- `client.py:189-194` (`server_capabilities` property) — **OK**, snippet matches the Read output.
- `client.py:250-269` (inner `except* (OAuthFlowError, OAuthTokenError)` block) — **OK**, structure verified.
- `client.py:386` (post-init `SUPPORTED_PROTOCOL_VERSIONS` membership check) — **OK**, line content matches.
- `client.py:390-392` (capabilities-tools-None check raising `MCPCapabilityMissing`) — **OK**.
- `client.py:402-414` (`_cleanup_after_failed_connect` docstring naming `MCPSandboxError`) — **OK**.
- `storage.py:OAUTH_MANAGED_SECRET_KEYS` (lines 51-60) — **OK**.
- `storage.py:set_tokens` (lines 107-132) — **OK**, the 5 keys it can write match the leg's claim (access_token, token_type, refresh_token if not None, scope if not None, token_expires_at conditional).
- `tests/test_mcp_pool.py:36-39` (`requires_bwrap = pytest.mark.skipif(...)`) — **OK**.
- `tests/test_mcp_pool.py:322,354` (two `@requires_bwrap` decorators) — **OK**.
- `pyproject.toml:54` (addopts) and `pyproject.toml:56-60` (markers) — **OK**, contents verified.
- `CLAUDE.md:340-358` ("MCP Error Translation Contracts") and `CLAUDE.md:409` (Testing section start) — **OK**.

No drift detected; no repairs needed.
