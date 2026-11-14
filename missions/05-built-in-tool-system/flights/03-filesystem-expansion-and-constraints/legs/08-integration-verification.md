# Leg: 08-integration-verification

**Status**: landed
**Flight**: [Filesystem Expansion & Constraints](../flight.md)

## Objective

Final integration verification for Flight 03. Run the full default unit suite, browser suite, and AIAT live smoke. Run the F3 regression sweeps from the flight artifact's Verification section. Refresh CLAUDE.md and agents.md to reflect the 9-tool filesystem surface, the four constraint types, the two new resolver markers, and the wording state shipped from L7. Append mission-level Known Issues for the small-model agency artifacts surfaced during HAT. Mark all F3-assigned mission Open Questions resolved.

## Context

L8 is the **last autonomous leg**. After L8 lands, the Flight Director hands off for the consolidated review, commit, and PR. Per agentic-workflow, code review and commit are deferred until after this leg.

State on entry (post-L7):
- **9 filesystem tools** registered in `_TOOL_CLASSES` and Studio's `TOOL_CATEGORIES`.
- **4 constraint types** enforced via `FilesystemConfig` + helpers: path scope (allowlist + denylist), read-size cap, binary refusal.
- **Resolver markers**: `Narrow`, `NarrowPrefix`, `NarrowSuperset`, `Substitute` (mutual exclusion enforced).
- **646 unit tests passing** (post-L6); same 1 pre-existing CSS-token red.
- **HAT result** (Qwen): 5/7 PASS clean, 2/7 small-model agency failures (Steps 3 + 6) documented as Known Issues.
- **HAT re-verification on Haiku 4.5**: confirmed F3 error strings are model-agnostic correct; small-model artifacts captured as Known Issues.
- **Wording shipped from L7**:
  - `_check_read_size`: `f"file size {size} bytes exceeds cap {cap} bytes (operator can raise the cap; pagination cannot bypass it)"`
  - Binary refusal (read_file + edit_file): `"binary file refused (set by operator only; not an agent-passable parameter)"`
  - Edit-file multi-match: unchanged from L4 (revert per Director decision)

## Inputs

State that must be true:
- L1-L7 have all landed.
- Working tree is dirty with the F3 changes; nothing committed yet.
- Container is running and the wording-tweaks from L7 are synced (host source IS the canonical version; container needs `make rebuild` for clean state, but ad-hoc tests run via `docker exec` will pick up the host-mounted source if mounted, or the L7 `docker cp`'d state).

## Outputs

Files modified:
- `CLAUDE.md` — Tool Configuration Layer section refreshed:
  - Resolver semantics bullet list extended with `NarrowPrefix` and `NarrowSuperset`.
  - Mention of `FilesystemConfig` and the four constraint types.
  - Update the stale wording at line ~103 from `"...no Narrow/Substitute marker..."` to enumerate all four markers.
- `the_one/agents.md` — already updated in L1 with the four-marker references and the Test conventions paragraph; L8 may add a short section enumerating the 9 filesystem tools if missing.
- `missions/05-built-in-tool-system/mission.md` — Known Issues list extended with two small-model artifacts from HAT (Steps 3 + 6 on Qwen 2.5:7b). Open Questions assigned to F3 marked resolved.

Files created: none.

State changes:
- Documentation only. No code changes.

## Acceptance Criteria

- [ ] **Full unit suite green**: `make test-unit` returns 646 passed (modulo the pre-existing CSS-token red `tests/test_token_definitions.py::test_every_var_reference_is_defined`). Any other failures must be triaged and either fixed in L8 or escalated.
- [ ] **Browser suite green**: `make test-browser` passes. Any failures triaged.
- [ ] **AIAT live smoke green**: `docker exec the-one pytest -m live tests/test_aiat.py` passes. Live tests use the user's configured LLM provider and require an API key; if not runnable, document and accept.
- [ ] **F3 regression sweep returns expected counts** (per flight artifact Verification section):
  ```bash
  rg -n 'Path\([^)]+\)\.expanduser\(\)\.resolve\(\)' the_one/tools/   # Expected: empty (no inline platform-coupled calls)
  rg -n 'Config\s*=\s*_EmptyConfig' the_one/tools/filesystem.py        # Expected: empty
  rg -n '^class \w+Tool' the_one/tools/filesystem.py | wc -l            # Expected: 9
  rg -n 'is_within\(' the_one/tools/filesystem.py                       # Expected: only inside resolver/_filesystem_check helpers, NOT inlined per-tool
  rg -n 'NarrowPrefix|NarrowSuperset' the_one/tools/                    # Expected: only resolver.py + filesystem.py imports
  rg -n 'class ConstraintError' the_one/                                # Expected: exactly 1 (in tools/filesystem.py)
  ```
- [ ] **CLAUDE.md** Tool Configuration Layer section reflects:
  - Resolver markers: `Narrow`, `NarrowPrefix`, `NarrowSuperset`, `Substitute` (with one-line semantic each).
  - `FilesystemConfig` introduced; the four constraint fields enumerated.
  - The marker-error wording at line ~103 updated to list all four markers in the message format.
- [ ] **Mission Known Issues** appended with the two HAT small-model artifacts (Qwen size-cap loop, Qwen edit-multi-match fabrication). Format matches existing entries.
- [ ] **Mission Open Questions** marked resolved for any items the flight artifact says are F3-resolved (Decisions 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11). Cross-reference flight.md Open Questions list — most are already `[x]`'d; just confirm.
- [ ] **Flight Status** updated to `landed` in `flight.md` header. (NOT `completed` — that's set by the debrief.)
- [ ] **Flight checklist** in `flight.md` Post-Flight section: check off the items that are now demonstrably true.
- [ ] **Mission flight checklist** in `mission.md` Flights list: check off Flight 3.
- [ ] **Flight log L8 entry** appended summarizing test results, sweep results, doc updates, known issues filed.
- [ ] `ruff check` and `ruff format --check` clean over the entire `the_one/` and `tests/` trees (NOT just changed files — final integration sweep).

## Verification Steps

```bash
cd ~/projects/the-one

# Static regression sweep
rg -n 'Path\([^)]+\)\.expanduser\(\)\.resolve\(\)' the_one/tools/
rg -n 'Config\s*=\s*_EmptyConfig' the_one/tools/filesystem.py
rg -n '^class \w+Tool' the_one/tools/filesystem.py
rg -n 'is_within\(' the_one/tools/filesystem.py
rg -n 'NarrowPrefix|NarrowSuperset' the_one/tools/
rg -n 'class ConstraintError' the_one/

# Test suite (run from inside container)
docker exec the-one bash -lc "cd /app && pytest -q 2>&1 | tail -10"
docker exec the-one bash -lc "cd /app && pytest -m browser 2>&1 | tail -10"   # may be slow; OK to skip if env unavailable
docker exec the-one bash -lc "cd /app && pytest -m live tests/test_aiat.py 2>&1 | tail -10"  # requires API key

# Lint + format
docker exec the-one bash -lc "cd /app && ruff check the_one/ tests/"
docker exec the-one bash -lc "cd /app && ruff format --check the_one/ tests/"

# Smoke: 13 tools registered, 9 filesystem
docker exec the-one python -c "
from the_one.tools.builtins import _TOOL_CLASSES
assert len(_TOOL_CLASSES) == 13
fs_tools = ['read_file', 'write_file', 'edit_file', 'delete_file', 'move_file', 'mkdir', 'glob', 'grep', 'list_dir']
for t in fs_tools:
    assert t in _TOOL_CLASSES, t
print('OK', len(_TOOL_CLASSES), 'fs:', len(fs_tools))
"
```

## Implementation Guidance

### Step 1: Run the full unit suite + lint

```bash
docker exec the-one bash -lc "cd /app && pytest -q"
docker exec the-one bash -lc "cd /app && ruff check the_one/ tests/"
docker exec the-one bash -lc "cd /app && ruff format --check the_one/ tests/"
```

If any failures beyond the CSS-token red, triage and fix. If you can't fix in L8, escalate to the Director.

### Step 2: Run the regression sweeps and capture results

Run each `rg` command from the Verification Steps above. Document the output in the flight log. Any unexpected matches must be investigated:
- `Path(...).expanduser().resolve()` matches → indicates inline platform-coupled calls that bypass `canonicalize`.
- `Config = _EmptyConfig` in `filesystem.py` → indicates a tool that wasn't migrated.
- `NarrowPrefix`/`NarrowSuperset` outside `resolver.py` and `filesystem.py` → indicates leakage of internal markers.

### Step 3: Run browser suite (best-effort)

```bash
docker exec the-one bash -lc "cd /app && pytest -m browser 2>&1 | tail -20"
```

If browser tests time out or fail due to environmental issues (Chromium, Playwright), document and accept — F3 didn't introduce browser-side changes (Studio's `TOOL_CATEGORIES` is the only JS edit, and it's a one-line additive change). Failures unrelated to F3 are out of scope.

### Step 4: Run AIAT live smoke (best-effort)

```bash
docker exec the-one bash -lc "cd /app && pytest -m live tests/test_aiat.py 2>&1 | tail -20"
```

Live tests require an API key. If the container env doesn't have one, document and accept.

### Step 5: Refresh `CLAUDE.md`

Edit the Tool Configuration Layer section. Anchor on the literal heading `### Resolver semantics`. Replace the marker-list bullet with the four-marker form. Add a sub-bullet about `FilesystemConfig` and the four constraint fields. Tighten the line about unannotated fields.

Suggested replacement text:

```
### Resolver semantics
`the_one/tools/resolver.py::resolve(schema, tool_config, agent_override)` composes the two layers per-key:
- `Annotated[type, Narrow]`: agent override must be ≤ tool-level value (bool: True→False or equal; int/float: cap; list: subset). Widening raises `ValueError`.
- `Annotated[type, NarrowPrefix]`: agent override on a `list[str]` of paths is narrowing iff every agent entry is a descendant-of (or equal to) at least one tool entry, checked via `the_one.platform.paths.is_within`. Used by `FilesystemConfig.path_allowlist`.
- `Annotated[type, NarrowSuperset]`: agent override on a `list[T]` is narrowing iff every tool entry is also in the agent value (agent ⊇ tool — agent ADDS restrictions). Used by `FilesystemConfig.path_denylist`.
- `Annotated[type, Substitute]`: agent override replaces tool-level value (no comparison). For identity / shared-credential / KV values.
- Fields with multiple markers OR no marker raise `ValueError` on resolve. Markers are mutually exclusive — declare exactly one of `(Narrow, NarrowPrefix, NarrowSuperset, Substitute)`.

### Filesystem constraint surface (F3)
`the_one/tools/filesystem.py::FilesystemConfig` is the per-category Config shared by all 9 filesystem tools. Four fields:
- `path_allowlist: list[str]` (NarrowPrefix) — default `["~"]`.
- `path_denylist: list[str]` (NarrowSuperset) — default 19-entry curated list (system secrets, browser/app data, agent internals, system paths).
- `read_size_cap_bytes: int` (Narrow) — default 1 MiB; bounds `[1024, 100 MB]`.
- `allow_binary_files: bool` (Narrow) — default False; positively-named permission so resolver's True=permissive reading aligns.

Policy refusals raise `ConstraintError`; tool wrappers format as `[error] [constraint] {msg}`. Environmental errors format as `[error] {e}` so agents can distinguish policy refusals from runtime failures.
```

### Step 6: Append mission Known Issues

Edit `missions/05-built-in-tool-system/mission.md`. Locate the `## Known Issues` section. Append two entries:

```
- [ ] `read_size_cap_exceeded` constraint induces retry-loop on Qwen 2.5:7b and other small (≤7B) local models — discovered in Flight 3 L7 HAT, affects agents using local 7B-class models. The agent retries `read_file` with progressively smaller `limit` values up to ~22 attempts despite the error explicitly stating "pagination cannot bypass it". No fabrication observed in the post-wording-tweak HAT run; the model loops to timeout instead. Confirmed model-agnostic-correctness via Haiku 4.5 re-verification — the wording is well-formed; this is a small-model agency limit, not a constraint-mechanism bug. Operators using small models should expect the agent to fail to terminate cleanly on oversized files; capable models (Haiku 4.5+, Sonnet, Opus) handle this correctly.
- [ ] `edit_file` multi-match constraint can induce fabricated context on Qwen 2.5:7b — discovered in Flight 3 L7 HAT, affects agents using local 7B-class models. The agent treats "add surrounding context" as "invent context" rather than "read the file to discover real context". A `read_file` call between the two `edit_file` attempts would resolve it cleanly; smaller models miss this multi-step recovery. Confirmed model-agnostic-correctness via Haiku 4.5 re-verification — the model called `read_file` defensively before the first `edit_file` attempt and edit succeeded on the first try. Operators using small models should expect occasional misinformation on multi-match scenarios; capable models handle correctly.
```

### Step 7: Update flight + mission status

In `missions/05-built-in-tool-system/flights/03-filesystem-expansion-and-constraints/flight.md`:
- Header: `**Status**: in-flight` → `landed`.
- Post-Flight Completion Checklist: check off items that are demonstrably true (most should be checkable now).

In `missions/05-built-in-tool-system/mission.md`:
- Flights list: check off Flight 3 (the `[ ]` becomes `[x]`).

### Step 8: Append L8 entry to flight log

Append to `flight-log.md`:

```
### Leg 08 — Integration verification
**Status**: landed
**Started**: 2026-04-29
**Completed**: 2026-04-29

#### Test results
- `pytest`: <count> passed; pre-existing CSS-token red still present.
- `pytest -m browser`: <result>
- `pytest -m live tests/test_aiat.py`: <result>

#### Regression sweep results
- `Path(...).expanduser().resolve()` in `the_one/tools/`: 0 matches (PASS)
- `Config = _EmptyConfig` in `filesystem.py`: 0 matches (PASS)
- `^class \w+Tool` in `filesystem.py`: 9 matches (PASS)
- `is_within(` in `filesystem.py`: <count> (in helper bodies only — PASS)
- `NarrowPrefix|NarrowSuperset` outside resolver.py + filesystem.py: 0 matches (PASS)
- `class ConstraintError`: 1 match (PASS)

#### Doc updates
- `CLAUDE.md` Tool Configuration Layer section refreshed with the four markers + FilesystemConfig + ConstraintError.
- Mission Known Issues appended with the two small-model HAT artifacts.
- Flight 3 checked off in mission.md; flight status → `landed`.

#### Lint
- `ruff check the_one/ tests/`: clean
- `ruff format --check the_one/ tests/`: clean
```

### Step 9: Update L8 leg status

Set this leg's `Status` to `landed`. Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]` when the doc updates are complete.

## Edge Cases

- **Browser tests environment-dependent**: Playwright + Chromium may time out on first run if the browser hasn't been pre-installed in the container. The Makefile's `_ensure-playwright` target is wired into `up`/`rebuild`. If browser tests fail with environmental errors, document the failure mode and continue — F3 didn't change the browser surface.
- **AIAT live tests environment-dependent**: requires an API key in the container. If unavailable, document and continue.
- **CLAUDE.md edits — anchor on text, not line numbers**: the file may have shifted lines since the last read. Use the literal `### Resolver semantics` heading as the anchor.
- **Mission Open Questions — most are already resolved**: the flight artifact's Open Questions are mostly `[x]`'d (10/10 resolved per the Pre-Flight Checklist). Just verify; don't re-resolve.
- **Test count drift**: the post-L6 baseline was 646 passed. After the L7 wording edits (which only affect error-string contents, not test count), the count should still be 646 (substring assertions are robust). If it's different, investigate.

## Files Affected

- `CLAUDE.md` — Tool Configuration Layer section refresh (~30 added LoC).
- `missions/05-built-in-tool-system/mission.md` — append 2 Known Issues.
- `missions/05-built-in-tool-system/flights/03-filesystem-expansion-and-constraints/flight.md` — status update + checklist check-offs.
- `missions/05-built-in-tool-system/flights/03-filesystem-expansion-and-constraints/flight-log.md` — append L8 entry.
- `missions/05-built-in-tool-system/flights/03-filesystem-expansion-and-constraints/legs/08-integration-verification.md` — status update.

Total: ~80 LoC of doc changes across 5 files. No code changes.

**Out of scope for L8**:
- Adding new tests, new tools, or new constraints.
- Modifying any code in `the_one/`.
- Committing or opening the PR (deferred to the Flight Director's final commit step).

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Test suite green (modulo pre-existing CSS-token red)
- [ ] Regression sweeps clean
- [ ] CLAUDE.md updated; mission Known Issues appended
- [ ] Flight status `landed`; flight checked off in mission
- [ ] Update flight-log.md with L8 entry
- [ ] Set this leg's status to `landed`
- [ ] DO NOT commit; DO NOT signal `[COMPLETE:leg]`
- [ ] Signal `[HANDOFF:review-needed]`
