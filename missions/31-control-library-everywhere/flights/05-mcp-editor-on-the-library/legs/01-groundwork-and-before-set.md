# Leg: groundwork-and-before-set

**Status**: completed
**Flight**: [The MCP server editor on the library](../flight.md)

## Objective
Prepare the flight with no product behaviour change:
- the MCP editor surfaces and their seed in `scripts/ui_capture.py`, and the before captures;
- the `MOVES` rule for the ownership and sink allowances;
- squawk 0259's re-measure of the `chats` lane, with its re-budget and the quiet-host rule.

## Context
- **Flight decisions:** DD2 (groundwork), DD3 (the split this rule serves), DD8 (captures), DD10 (standing rules), DD12 (lanes).
- **No file under `the_one/` changes.** The MCP editor must be byte-identical to `main` when the before set is taken.
- **The capture tool today** (`scripts/ui_capture.py`, 1697 lines):
  - surfaces are `Surface(name, hash, ready, description, prepare, shot, stubs, skipped, tz, restore)` entries in `SURFACES`;
  - seeding is `seed()` (`:1210`), `seed_tabs_agent()` (`:1247`), `seed_library()` (`:1306`) and `seed_settings()` (`:1357`), through the API with the instance's credential;
  - `maybe_reexec_in_netns()` (`:1528`) re-runs the tool in a loopback namespace under `THE_ONE_TEST_NETNS=1`;
  - it refuses ports 8484 and 8485 and anything below 8490, the default or a configured data dir, and an `--out` inside the repo;
  - its only MCP surfaces are `agent-mcps` (stubbed tools) and `mcp-consent-link` (skipped).
- **The planning survey's working seed and driver** (FD scratchpad, outside the repo):
  - `/tmp/claude-1000/-home-<user>-projects-the-one/60f439f3-3d7e-4895-a147-e62bc6860c79/scratchpad/f5-debt/fixtures.py` runs three fixture servers: a rich HTTP server with title, version, website, instructions and 4 tools; `asgi_legacy` in `fast400` mode; and `asgi_401` with bare 401s.
  - `orchestrate.py` and `walk.py` seed the seven MCP servers and drive every state.
  - Read them for what worked. Port them into the tool; do not import from the scratchpad.
- **The guards today:**
  - `tests/test_ui_ownership.py::test_ownership_matches_allowance` compares the measured `(file, class)` counts with `tests/_ui_ownership_allowance.py` `OWNERSHIP_ALLOWANCE` exactly, in both directions (66 rows / 167 uses).
  - `tests/test_ui_guards.py` has `HTML_SINK_ALLOWANCE` (`:134`, exact per file) and `DYNAMIC_SINK_BASELINE` (`:105`, a text freeze per file, where removals never fail).
  - A file split moves rows between files, and the exact-match test cannot tell a move from growth. The Flight 4 debrief (Recommendation 6) asks for "total uses only shrink, plus a committed MOVES table".
- **Lane budgets** (`scripts/run-tests.sh:60-76`, CLAUDE.md "Lane time budgets") are wall seconds **in a `--parallel 3` run**, not a solo lane.
  - Squawk 0259's "run `--lane chats` alone" would measure something else, so this leg corrects it.
  - The re-measure is one full `--parallel 3` browser run with **no other test process on the host** (no Developer lanes, no unit suite, no other session's tests). If chats is 450 s or more, or close to it, a second run follows.
  - That run also gives the flight its quiet-host baseline for every lane.

## Inputs
- The branch `flight/05-mcp-editor-on-the-library` from `main` at `b1e47ae`, with the planning artifacts and squawk 0260 uncommitted.
- WebKit userland installed and `THE_ONE_TEST_NETNS=1` working (re-verify first).

## Outputs
- **`tests/fixtures/mcp/rich_http_server.py`** (new): the survey's rich HTTP fixture (`rich()` in the survey's `fixtures.py`, with title, version, website, instructions and 4 tools), as a reusable test fixture module beside `hello_server.py`. The capture tool must not import from the scratchpad.
- **`scripts/ui_capture.py`:**
  - **An MCP fixture-server helper.** It starts the three fixture servers (rich HTTP, `asgi_legacy` in `fast400` mode, and `asgi_401` with bare 401s) as subprocesses under the venv's `sys.executable` with the repo on `sys.path`. The capture process itself still never imports `the_one` or `mcp`.
    - They start inside the same namespace as the instance under `THE_ONE_TEST_NETNS=1`, after `maybe_reexec_in_netns`.
    - Each is recorded by PID and stopped in a `finally`.
    - Ports: prefer binding port 0 and reading the chosen port back; otherwise pick a free port at 8493 or above and retry on `EADDRINUSE`. Never use the instance's own port, 8484, 8485 or 8491. Inside the namespace, 8491 is invisible, so that refusal is policy.
    - The refusal is a pure function (like `check_capture_safety`), unit-tested in `tests/test_ui_capture_safety.py`;
  - **`Surface.widths`** (`tuple[int, ...] | None`), intersected with `--widths`, so a surface can be taken at 1280 only;
  - **`seed_mcp()` runs only when an MCP surface is selected**, so the existing surfaces (`library-list`, `agent-mcps`, jump-to, …) and their comparability with earlier sets are unchanged. The existing `agent-mcps` surface keeps its name; the new expanded tab surface is `agent-mcps-full`;
  - `seed_mcp()`, which seeds the survey's servers:
    - **Hello tools (local):** stdio, the `hello_server` fixture through the venv python; 4 args, one 90 characters long; 3 plain env vars and 1 sensitive; network off; 2 writable paths, one 87 characters long (an existing scratch directory);
    - **Always fails (local):** a stdio command that exits at once (`<venv python> -c "import sys; sys.exit(1)"`). It replaces the survey's uvx server, whose outcome depends on the host;
    - **Docs search:** the rich HTTP fixture, with a plain header and a sensitive `Authorization` header;
    - **Legacy wiki:** the `asgi_legacy` fixture;
    - **Billing API:** the `asgi_401` fixture, with a sensitive header;
    - **Team calendar:** HTTP to a port nothing listens on, its sign-in states captured with `/test/connect` stubbed to `auth_required`, as the survey did;
    - one agent with every server attached;
  - the MCP surfaces (DD2): create (empty, stdio, HTTP); edit for each server, with each connected, legacy, rejected or failed state produced by a Test run once in `seed_mcp()` (stable, and no per-capture Refresh); the tools and instructions disclosures open; dirty; a Save error; Reset armed; danger armed; sign-in (manual and after create); the agent MCPs tab expanded; the Library list's MCP group;
  - reference surfaces for the provider, connector and knowledge editors' headers and danger zones (A1, B7). Reuse the existing surfaces where they already show these; add only what is missing;
  - every MCP surface at 1280 in both themes; the key/value table surfaces and the create forms also at 1024 (A12), through `Surface.widths`;
  - **the manifest records the sandbox backend for the stdio servers.** It comes from a one-line `python -c` in the instance's environment (same namespace, scratch `THE_ONE_DATA_DIR`) that prints `get_sandbox_backend()`'s class name (`the_one/platform/sandbox/factory.py`). The manifest also records the git SHA and the `git status` of `the_one/`;
  - **run-to-run text masked** as the Library surfaces do: times and "Last updated", plus new rules for `127.0.0.1:<port>` in URLs and for the run id inside scratch paths (the long writable path). Each masked value keeps its shape and length (the existing mask rule).
- **The before set** at `$HOME/.cache/the-one-ui-capture/m31-f5-before`, outside the repo. The flight log records the count and the command.
- **The move rules** (three tables, each a `NamedTuple` list, each empty at the end of this leg; reworked at the leg's design review):
  - **Ownership moves.** `tests/_ui_ownership_allowance.py` gains:
    - `MOVES: list[OwnershipMove(key, from_file, to_file, uses, retire_by)]`. Paths are relative to `static/` (`js/areas/...`, `css/...`), the same key space as `measure()`, `api:` keys included.
    - `TOTAL_USES: dict[str, int]`: each key's total uses across every file, **exact**, measured at this leg.
  - **Ownership tests** in `tests/test_ui_ownership.py`:
    - **(a) Totals are exact.** The live total of every key equals `TOTAL_USES`, and a key missing from `TOTAL_USES` counts as 0. Removing uses therefore lowers `TOTAL_USES` in the same change, exactly like the allowance. Re-growing a key is a visible diff that needs a flight-log reason. A newly owned class used outside `js/ui/` has a total of 0 and fails.
    - **(b) A new row needs a move.** Every allowance row `(file, key)` whose file did not hold that key when its move was recorded is covered by `MOVES` entries with that `to_file`. The covering uses sum to at least the row's count, so a split into several files (8 uses into 5 and 3) is several entries.
    - **(c) No stale entries.** Every `MOVES` entry names a live row.
  - **Sink moves.** `tests/test_ui_guards.py` gains `SINK_MOVES: list[SinkMove(from_file, to_file, count, retire_by)]` for `HTML_SINK_ALLOWANCE`, with paths relative to `js/` (`areas/...`), the table's own key space. Its rules:
    - the whole-app total equals a frozen `SINK_TOTAL` (exact, lowered with each removal);
    - a file key absent from the allowance at flight start needs `SINK_MOVES` entries covering its count;
    - no stale entries.
  - **Snippet moves.** It also gains `SNIPPET_MOVES: list[SnippetMove(snippet, from_file, to_file, retire_by)]` for `DYNAMIC_SINK_BASELINE`, with the same `js/` key space. Its rules:
    - a snippet may appear under a new file key only through an entry;
    - the live count of each snippet across all files is at most its count across the baseline, so copying a statement instead of moving it fails;
    - the "from" file need not still hold the snippet, because the baseline already holds stale entries (removals never fail).
  - **A path in the wrong key space fails with a message naming the expected form** (`js/areas/...` vs `areas/...`).
  - **`retire_by`** is documentation, not checked per leg. The flight's Verification requires every table to be empty at landing, and leg 10's criteria say so too.
  - **The test helpers** take `(allowance, totals, moves)` as arguments, and fixture-dict unit tests cover each rule: a pure move passes; a split into two files passes; growth fails; a move with no entry fails; a copy instead of a move fails (snippets); a stale entry fails; a wrong key space fails.
  - **The existing exact-match tests stay as they are.** Each new test's docstring says what to do on failure.
- **Squawk 0259:**
  - the quiet-host `--parallel 3` run, with its `PARALLEL_RESULT` line and per-lane times in the flight log;
  - `chats` re-budgeted by the measured-plus-25% rule (rounded up to 30 s) if it moved more than 15% or is over budget, or split if the run shows it cannot fit;
  - the quiet-host clause added to CLAUDE.md's "Lane time budgets" paragraph and to the budget comment in `scripts/run-tests.sh`: a budget reading counts only from a `--parallel 3` run with no other test process on the host;
  - the squawk closed with its corrective action and verification (the flight-end Reviewer signs it off, and its commit is the flight's).
- **The flight log:** this leg's entry and a Flight Director Notes line.

## Acceptance Criteria
- [ ] `git diff main -- the_one/` is empty at the end of the leg.
- [ ] `scripts/ui_capture.py --list` shows the new MCP and reference surfaces, each with a description.
- [ ] A capture run under `THE_ONE_TEST_NETNS=1` writes the before set with every new surface in both themes (and at 1024 where listed), with no surface failing.
  - Each fixture server's PID is stopped in a `finally`. After the run, no fixture or instance process from the run is alive, and ports 8493 and above that the run used are free.
  - The FD spot-checks five images: connected HTTP, failed stdio, rejected, sign-in, and the 1024 key/value table.
- [ ] **The "Always fails" server's Test always shows an error state.** Two runs give the same error text, and the capture log names the sandbox backend.
- [ ] **The safety refusals hold:** the tool still refuses ports 8484, 8485 and below 8490, and the default data dir; the fixture helper refuses 8484, 8485 and 8491. A unit test covers the fixture helper's refusal.
- [ ] **The `MOVES` rule tests pass** on the real tree with `MOVES` empty.
  - Each fixture case behaves as specified: a pure move passes; growth, an unlisted move and a stale entry each fail.
  - `test_ownership_matches_allowance` and the sink tests are unchanged.
- [ ] **The quiet-host `--parallel 3` run** completes with rc=0, under the quiet-host procedure below.
  - Its per-lane times and its start load are in the flight log.
  - `chats` is within its budget after any re-budget.
  - CLAUDE.md's budget table matches `scripts/run-tests.sh`. No test checks that, so verify it with a grep step. `tests/test_run_tests_lanes.py` checks only the `--plan` order and likely needs no change.
- [ ] **The quiet-host clause** is in CLAUDE.md and the `run-tests.sh` comment.
- [ ] **Squawk 0259:** its Action text is amended (the re-measure is a quiet-host `--parallel 3` run, not a solo lane), and it records its corrective action and verification, with status `in-progress` until the flight's commit.
- [ ] `make test-unit` passes (with the expected skip count for this host and mode), and `ruff check` and `ruff format --check` pass on `scripts/` and `tests/`.

## Verification Steps
- `git diff --stat main -- the_one/` (empty).
- `.venv/bin/python scripts/ui_capture.py --list | grep -i mcp`.
- `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out $HOME/.cache/the-one-ui-capture/m31-f5-before --surfaces <the new ones>` (or the tool's own selection flag). Then list the files, and check for leftover processes by the PIDs the run printed.
- `.venv/bin/python -m pytest tests/test_ui_ownership.py tests/test_ui_guards.py tests/test_run_tests_lanes.py -q -x --timeout 120`.
- **The quiet-host procedure:**
  - Before starting, `uptime` shows a 1-minute load below about 1.0.
  - `ps -eo pid,user,etime,args` shows no `pytest`, `run-tests.sh`, `playwright`, `chromium` or `uvicorn`/`the-one serve` processes other than long-lived idle app instances. Record any such instance: the instance on 8491 (pid 2322812 at planning) is not this session's, and is left alone.
  - Nothing else is started during the run: no capture run, no unit suite.
  - If the host is not quiet, stop and report `[BLOCKED:host-not-quiet]` with what you found; do not run a noisy measurement.
  - Then run `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short`, and record the start load and the `PARALLEL_RESULT` line.
- `grep -n "chats" CLAUDE.md scripts/run-tests.sh` (the two budget tables agree).
- `make test-unit`, after the browser run, never during it.

## Implementation Guidance
1. Re-verify WebKit and the namespace (`bash scripts/run-tests.sh --lane contracts-overlay --list` is cheap; the run in step 6 proves the rest).
2. **The `MOVES` rule first** (unit tier, fast). Write the fixture tests, then the rule, then measure the baselines. Keep the existing exact tests untouched.
3. **The rich fixture module, the fixture-server helper and `seed_mcp()`**, ported from the survey scripts, plus `Surface.widths`. Stub `/test/connect` only for Team calendar's sign-in states, using the existing stub pattern (`_stub_test`, `:255`). Every other state comes from a real Test against a real fixture.
4. **The surfaces**, one `Surface` per state, with `restore` where a surface changes server state (Reset, Delete armed, a Save error), so the next theme starts clean. "Dirty" and "Save error" are client-only states.
5. **Take the before set.** Spot-check, and record the count and the command in the flight log.
6. **Run the quiet-host `--parallel 3` browser run alone.** Re-budget `chats` if needed, update both tables and the lanes unit test, and add the quiet-host clause. Then run `make test-unit`.
7. Close squawk 0259's corrective action and verification, and write the flight log.

## Edge Cases
- **The fixture servers must start inside the namespace.** A server started outside `unshare -rn` cannot be reached from inside it. Start them after `maybe_reexec_in_netns`.
- **Port collisions:** see the helper's port rule. Never hard-code 8493-8495, since another session may hold them.
- **stdio sandbox backend:** under the namespace, bwrap runs inside a user namespace. Record the backend; do not assume it.
- **The `last_updated` and "just now" texts** vary run to run: mask them.
- **The long writable path** must exist (a scratch directory under the run's scratch home), or the Hello server fails like survey 0.1 (squawk 0260).
- **The `MOVES` baselines** are measured on this leg's tree. A later leg that removes uses lowers the allowance as before. The baseline only caps growth.

## Files Affected
- `scripts/ui_capture.py`, `tests/fixtures/mcp/rich_http_server.py` (new).
- `tests/_ui_ownership_allowance.py`, `tests/test_ui_ownership.py`, `tests/test_ui_guards.py`, `tests/test_ui_capture_safety.py`.
- `scripts/run-tests.sh` (the budget comment, and the `chats` budget if it moves), `tests/test_run_tests_lanes.py` (if the budget moves), `CLAUDE.md`.
- `squawks/0259-chats-lane-at-budget.md`, the flight log.

## Citation Audit
- `scripts/ui_capture.py`: `Surface` (`:232`), `seed` (`:1210`), `seed_library` (`:1306`), `maybe_reexec_in_netns` (`:1528`), `_stub_test` (`:255`), and the `mcp-consent-link` skipped surface. Verified by grep.
- `tests/test_ui_ownership.py::test_ownership_matches_allowance`: exact compare in both directions. Verified (read).
- `tests/test_ui_guards.py`: `HTML_SINK_ALLOWANCE` (`:134`), `DYNAMIC_SINK_BASELINE` (`:105`). Verified.
- `scripts/run-tests.sh:60-63`: the budget comment and `[chats]=450`. Verified.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Developer design review, cycle 1 (2026-10-25): approve with changes.** Applied in place: the three move tables with their key spaces and exact totals (H1, H2, M slack, M absent keys, M `retire_by`); `Surface.widths` (M); `seed_mcp()` only for MCP surfaces, and the `agent-mcps-full` name (M); the quiet-host procedure with a blocking report (M); the fixture module, subprocess spawning and the port rule (M); the sandbox backend probe (M); seed-time Tests instead of per-capture Refresh (L); the mask rules (L); the budget-agreement check (L); the squawk Action text (L). The FD judged these clarifications, not a change of design, so there is no second cycle.
