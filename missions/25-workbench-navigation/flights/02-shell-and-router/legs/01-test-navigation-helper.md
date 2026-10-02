# Leg: test-navigation-helper

**Status**: completed
**Flight**: [Shell and Router](../flight.md)

## Objective

Make the browser test suite independent of the shell's markup and URL scheme before the
shell changes:
- **Fix the four flakes.** Root-cause and fix the four recurring lane flakes.
- **Add the helper.** Land the central navigation helper `tests/browser/_nav.py`, which
  takes new-scheme routes and maps them to whatever the app serves.
- **Migrate the tests.** Move every navigating browser test onto the helper, and keep a
  deliberate legacy-URL set.
- **Re-map the lanes.** Lanes follow the four destinations.

No app code changes in this leg.

## Context

- **Flight decisions:** DD9 (tests first, flakes first, helper, legacy set, lanes) and DD1/DD2
  (the route scheme and legacy mapping the helper encodes). Read DD1, DD2, DD9 and DD12
  in `flight.md`.
- **Legs that come after this one:** leg 3 (`router-and-redirects`) flips the helper's
  one mapping switch to new routes and migrates the Agents-side section-nav clicks and
  readiness probes. Leg 5 (`rail-and-shell`) switches `open_destination` from top-bar
  buttons to the rail. This leg must make both flips one-line changes inside `_nav.py`.
- **The four flakes:**

  | Test | Location |
  |---|---|
  | `test_agent_item_keyboard_select` | `tests/browser/test_flow_keyboard.py:122` |
  | `test_editor_renders_prompt_block` | `tests/browser/test_flow_admin_tools_editor.py:84` |
  | `test_studio_agent_crud_flow` | `tests/browser/test_flow_agent_crud.py:32` |
  | `test_sandbox_chip_add_remove_marks_form_dirty` | `tests/browser/test_flow_studio_mcp_editor.py:512` |

  Each failed once during Flight 1 lane runs and passed on rerun. The F1 debrief's
  sequential run did not reproduce any of them, so treat them as load-sensitive.
- **Migration surface** (from the router research, `fe595cc`):
  - 63 browser files call `goto(`, and 289 of those `goto`s carry a hash. The biggest
    groups are `#studio` (71), `#studio/mcp-sources/{sid}` (40), `#studio/mcp-sources/new`
    (22), `#admin/providers/new` (21), `#admin/providers/{id}` (about 29) and
    `#admin/tools/{name}` (24).
  - **There is no `to_have_url`, `wait_for_url` or `page.url` anywhere** (design review).
    The real shapes are:
    - `assert page.evaluate("location.hash") == "#admin/…"` (about 50 hits);
    - `initial_hash = page.evaluate("location.hash")` followed later by `== initial_hash`
      (unchanged-URL assertions with no literal);
    - **writes**, `page.evaluate("location.hash = '#admin'")`
      (test_flow_admin_navigation:43, test_flow_dirty_confirm:215), where a
      same-document `hashchange` is the point of the test;
    - **waits**, `wait_for_function` on the hash (test_flow_new_chat:175,
      test_flow_agent_tabs:53);
    - **app-emitted link targets**, `[href="#admin/providers"]`, `[href="#studio"]`,
      `[href="#admin"]` (test_flow_new_chat:44-59);
    - **hashes built into a variable** and reused (test_theme_cross_tab_sync:51,
      test_flow_agent_tabs:206-224).
  - Not routes, so left alone: `#beta` in test_ui_library_contract:451, the
    `#main-content` readback in test_ui_dialog_scroll, test_flow_oauth_callback_cross_site's
    `location.assign` of API URLs, and markdown `href="#"` fixtures.
  - No fixture, seeder or `_credential_registry.py` code builds route hashes; the last
    mentions one only in a docstring.
  - Top-bar clicks (`.app-picker-button`, `nav-chat-btn`) in 5 files:
    `test_flow_studio_loadall_error.py`, `test_flow_cross_area_dirty_gate.py`,
    `test_flow_picker.py`, `test_flow_hash_routing.py`,
    `test_flow_studio_knowledge_inventory.py`.
- **Transport:** the `page` fixture's `goto` wrapper (`tests/browser/conftest.py:407-480`,
  `_goto_with_credential`) stays as the transport. `_nav` calls `page.goto`.
- **Lanes:** `scripts/run-tests.sh:57-79`. `shared` is the complement.
- **Out of scope:** section-nav clicks (20 files) are left as they are; leg 3 migrates
  the Agents ones. App code is not touched.

## Inputs

- `tests/browser/conftest.py` (`page` fixture, `_goto_with_credential`, app fixtures).
- All `tests/browser/test_*.py`.
- `scripts/run-tests.sh` (lane globs), `CLAUDE.md` "Per-area browser test lanes",
  `the_one/agents.md` lane mentions.
- `missions/25-workbench-navigation/flights/02-shell-and-router/flight.md` DD1/DD2: the
  route list and the legacy map.

## Outputs

- **Fixes for the four flakes**, in their test files, plus app-side fixes only if a
  flake is an app race. If one is, it is recorded as an anomaly and the fix is kept
  minimal.
- **`tests/browser/_nav.py`** (new) provides:
  - `goto(page, base, route, **kw)` (passes `**kw` through);
  - `set_route(page, route)` (a same-document hash write, for `hashchange` tests);
  - `expect_route(page, route, timeout=...)`;
  - `current_route(page)`;
  - `wait_for_route_prefix(page, prefix, …)`;
  - `href(route)`, which returns `"#" + <scheme hash>`, for app-emitted link selectors;
  - `open_destination(page, name)`;
  - `seg(value)`;
  - `legacy_hash(route)`, `new_hash(route)`, `canonical(route)`, and the inverse used by
    `current_route`;
  - one module-level switch, `SCHEME = "legacy"`;
  - the route → legacy-hash table, which mirrors DD2;
  - `LEGACY_URL_TESTS`: the deliberate legacy set as **`file::function`**
    identifiers, listed in the docstring as well.
- **Unit tests:** `tests/test_nav_helper.py` (new, unmarked), covering the mapping
  table, encoding and the `~new` scoping.
- **Migrated browser tests:** every test that navigates by hash, asserts the URL or hash,
  or clicks the top bar now goes through `_nav`.
- **Migration guard:** `tests/test_nav_helper.py::test_no_raw_route_hashes_in_browser_tests`
  (unmarked).
  - **Scanning.** It is an **`ast`** walk over `tests/browser/test_*.py`, not a text
    grep. It checks string constants, including the literal parts of f-strings, and
    skips docstrings. Comments are skipped for free.
  - **Pattern.** It applies
    `(?<![\w&/])#(?:studio|admin|chats?|agents|library|settings)(?![\w-])` to each
    literal. The lookahead lets the CSS ids `#studio-model` (26 hits) and
    `#studio-provider` (14) through, while still catching `#studio/agents`.
  - **Top-bar selectors.** It also flags `.app-picker-button` and `nav-chat-btn`.
  - **Allow-list.** The allow-list is `_nav.py` plus the **functions** named in
    `LEGACY_URL_TESTS`, applied by enclosing `FunctionDef` span, never whole files. The
    guard asserts every `LEGACY_URL_TESTS` entry still exists, so a rename can't orphan
    one.
  - **Self-test.** The guard is tested against synthetic sources:
    - a `#studio-model` selector passes;
    - a raw `#studio/agents` goto fails;
    - a docstring mention passes;
    - a listed legacy function passes;
    - an unlisted sibling function in the same file fails.
- **Lanes:** `scripts/run-tests.sh` gains the `chats | agents | library | settings |
  shared` lanes, with `chat`, `studio` and `system` as aliases. CLAUDE.md and `agents.md`
  lane docs are updated.
- **Flight log:** the leg entry, including each flake's root cause and the lane results.

## Acceptance Criteria

**Flakes**

- [x] **AC1 — Each of the four flakes is root-caused and fixed.**
  - The flight log names, for each one, the race (what the test read or clicked before
    what state settled) and the fix.
  - Fixes are deterministic waits on an observable state: `expect(...)` on the element
    or state the next action needs, or waiting for a network response. A bare timeout
    increase or a `sleep` is not acceptable as the fix.
  - If the race is in app code, the minimal app fix is made and recorded as an anomaly.
- [x] **AC2 — Stability proof.** (variation: see flight log; the consecutive-green bar was not met on this host because of Chromium ERR_NETWORK_CHANGED, mitigated by the opt-in `THE_ONE_TEST_NETNS=1` lane option)
  - **Before the fix,** each test is run 10× under load and the result is recorded:
    whether it reproduced or not. A non-reproducing flake is flagged as "root-caused by
    inspection". Prove that fix with an **artificial hook** that forces the race
    instead: a Playwright route delay on the relevant `/api/` call, or CDP
    `Emulation.setCPUThrottlingRate` in Chromium.
  - **After the fix,** each test passes **10 consecutive runs** under CPU load.
  - The load comes from a busy-loop load generator on `nproc − 1` cores, started and
    stopped by the verification script. It is not committed. A small inline Python or
    shell loop is fine.
  - Runs use `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser <file>::<test> -x`,
    or equivalent. One run takes about 1.2s, so ten reps are cheap.
  - The flight log records the counts.

**Helper**

- [x] **AC3 — `tests/browser/_nav.py`.**
  - **Routes.** Routes are written in the **new** scheme (DD1), without the leading
    `#`: `"settings/providers/~new"`, `"agents/My%20Agent/tools"`, `"library/mcp/abc"`,
    `"chats"`.
  - **`legacy_hash(route)`** maps every DD1 route form to today's legacy hash, per the
    DD2 table:
    - `~new` → `/new`, only for providers and MCP sources;
    - `settings/knowledge-indexing` → `admin/knowledge`;
    - `library/mcp` → `studio/mcp-sources`.

    It also covers the bare destinations: `chats` → `chat`, `agents` → bare `studio`
    (what most tests use), `library` → `studio/knowledge`, `settings` → bare `admin`.
  - **Canonicalisation.** `canonical(route)` folds the app's own default redirects, so
    `expect_route` and `current_route` accept either form:
    - `studio` ≡ `studio/agents`;
    - `admin` ≡ `admin/general`;
    - after the flip, `settings` ≡ `settings/general` and `library` ≡ `library/knowledge`.
  - **Inverse.** An inverse map turns an observed hash back into a new-scheme route for
    `current_route`.
  - **Comparison.** Hashes are compared **per segment**: split on `/`, `unquote` each
    segment, then compare. A `%2F` inside an id therefore stays distinct from a path
    separator, and `%20` and space compare equal.
  - **`new_hash(route)`** returns `#` + route.
  - **The switch.** With `SCHEME = "legacy"`:
    - `goto` navigates to `legacy_hash(route)`;
    - `expect_route` asserts `location.hash == legacy_hash(route)`.

    Flipping the switch to `"new"` uses `new_hash`. That flip is the **only** change leg
    3 makes to `goto` and `expect_route`.
  - **`expect_route`** retries until the timeout, using Playwright's `expect(page)` URL
    matching or polling `location.hash`.
  - **`open_destination(page, name)`**, with name one of `chats`, `agents`, `library`,
    `settings`:
    - today it clicks the top-bar button for `chats`/`agents`/`settings`
      (`.app-picker-button[data-area=chat|studio|admin]`);
    - for `library` it navigates with `goto(page, base, "library")`, because there is no
      top-bar button yet;
    - one internal branch is marked for leg 5's rail flip.
  - **Encoding.** `_nav` never re-encodes a route the caller already encoded. Callers
    pass ids through `_nav.seg(value)`, which matches JS `encodeURIComponent` exactly:
    `quote(value, safe="!'()*")`. A **leading** `~` is then encoded as `%7E` (DD1).
    Existing callers using `quote(name)` with the default `safe="/"` move to `seg`.
  - **Base URL.** `goto` normalises the base as `base.rstrip("/") + "/#" + hash` and
    passes an **absolute** URL to `page.goto(url, **kw)`. The conftest wrapper is an
    instance attribute keyed on the origin, so the handoff is never re-implemented. A
    second tab (`context.new_page()`) works, because auth is context-level.
- [x] **AC4 — Unit tests** (`tests/test_nav_helper.py`, unmarked, so it runs in
  `make test-unit`) cover:
  - every DD2 legacy row, plus the bare destinations;
  - the round trip `current_route`-inverse(`legacy_hash(r)`) == `canonical(r)` for
    every row;
  - per-segment comparison, including `%2F` vs `/` and `%20` vs space;
  - the `~new` scoping: a provider and an MCP source map to `/new`, while
    `agents/new/general` stays an agent named "new";
  - `seg()` encoding, including spaces, slashes, unicode, a leading `~`, and the five
    characters `!'()*`, which stay unencoded as in JS;
  - the `SCHEME` switch.

**Migration**

- [x] **AC5 — Every navigating browser test uses `_nav`.**
  - Every `page.goto(<base> + "#…")` with a route hash becomes `_nav.goto(...)`.
  - Every URL or hash assertion that names a route becomes `_nav.expect_route(...)`, or
    uses `_nav.current_route(page)`.
  - Every top-bar click becomes `_nav.open_destination(...)`.
  - Same-document hash writes become `_nav.set_route(...)`.
  - Hash `wait_for_function`s become `_nav.wait_for_route_prefix(...)`.
  - `[href="#…"]` selectors become `f'[href="{_nav.href(route)}"]'`.
  - `initial_hash` / `== initial_hash` patterns become `current_route` before and after.
  - Hashes built into variables are routed through `_nav` by hand. The codemod won't
    see them; the guard will.
  - Assertions on non-route fragments, such as the skip link's `#main-content`, stay
    as they are.
  - The migration guard (Outputs) passes. Its allow-list is exactly `_nav.py` and the
    `LEGACY_URL_TESTS` set.
- [x] **AC6 — The legacy-URL set.** At least 8 tests keep a **raw legacy `goto`**: 1
  Chats, 2 Agents (one with a tab), 2 Library (KB, MCP), and 3 Settings (a provider item,
  a tools item, bare `#admin`).
  - They assert through `_nav.expect_route` with the **new-scheme** route. Under
    `SCHEME = "legacy"` that is today's hash, and after leg 3 it proves the redirect.
  - They are named in `LEGACY_URL_TESTS` and in the `_nav.py` docstring, and each has
    a one-line comment at its legacy `goto`.
- [x] **AC7 — Unrelated tests untouched.** Section-nav clicks and assertions in the 20
  files that use them are unchanged. Tests that don't navigate are untouched apart from
  imports.

**Lanes**

- [x] **AC8 — Lanes.** `scripts/run-tests.sh --lane` accepts `chats`, `agents`,
  `library`, `settings` and `shared`, plus the aliases `chat` (= chats), `studio`
  (= agents + library) and `system` (= settings).
  - **`library`** explicitly lists `test_flow_studio_knowledge_inventory`,
    `test_flow_studio_mcp_editor`, `test_flow_studio_mcp_navigation`,
    `test_mcp_test_connection_button` and `test_studio_connector_editor`, plus any other
    Library-owned file you find.
  - **`agents`** is the rest of today's studio globs.
  - **`shared`** stays the complement, keeping today's hard-coded exclusion of
    `test_visual_snapshots.py`, which has no `browser` marker.
  - **`agents`** is the studio globs minus the library list, subtracted with `comm` as
    `shared` already is. `test_flow_studio_knowledge_attach.py` and
    `test_studio_mcps_tab.py` are agent-editor tabs and belong in `agents`.
  - **Aliases** expand to the union of their lanes. The error message lists the new lane
    names.
  - **Union check.** It compares file lists (no duplicates, via `sort | uniq -d`) as well
    as counts. A check proves the union of `chats`, `agents`, `library`,
    `settings` and `shared` collects exactly the same test count as `-m browser
    tests/browser/`, with no file in two lanes. Use `--collect-only -q`, as M17 F5 did,
    and record the counts in the flight log.
  - **Docs.** `CLAUDE.md` "Per-area browser test lanes" and `agents.md` are updated with
    the new names, the alias note and the explicit Library list.

**Gates**

- [x] **AC9 — Gates pass.**
  - `make lint`.
  - `make test-unit`, including `tests/test_nav_helper.py` and its guard.
  - **All five lanes, one at a time:**
    `PYTHON=.venv/bin/python TEST_TIMEOUT=1800 bash scripts/run-tests.sh --lane <name>`.
    A failure is rerun alone. A failure of one of the four fixed tests is a **leg
    failure**, not a flake.
  - `tests/browser/test_ui_*.py` (both engines) is unaffected but runs in `shared`.
  - The flight log records counts and durations per lane.

## Verification Steps

- AC1–AC2: read the flight-log entry (causes, fixes, the 10/10 counts under load), then
  read the diffs of the four tests.
- AC3–AC4: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_nav_helper.py -x`.
- AC5–AC7: the migration guard. Then
  `git diff --stat tests/browser/ | tail -1`, plus a spot read of 5 migrated files and
  the 8 legacy-set tests.
- AC8: the union check output in the flight log, and `bash scripts/run-tests.sh --lane studio --collect-only -q | tail -1`
  equals the sum of the agents and library lanes.
- AC9: the commands listed.

## Implementation Guidance

1. **Flakes first.**
   - Run each test 10× under load *before* fixing it, to try to reproduce the failure,
     and record the failure output.
   - Read the test and the code it drives, and find the read-before-settle. Typical
     shapes: clicking before a re-render finishes, reading a count before a fetch
     resolves, or asserting a dirty state before an input event propagates.
   - Fix it with an `expect` on the precondition, then re-run 10× under load.
2. **`_nav.py`.** Write the table from DD2 (`flight.md`), plus its unit tests.
3. **Codemod.** Prefer an `ast`-aware rewriter or careful per-file hand edits; about 60
   f-string sites embed ids, which makes a regex rewriter error-prone. The real shapes to
   rewrite are:
   - `page.goto(f"{base}#studio…")` and `page.goto(f"{app}/#admin/…")`;
   - `assert page.evaluate("location.hash") == "#…"`;
   - `initial_hash` patterns;
   - `location.hash = '…'` writes;
   - `wait_for_function` on the hash;
   - `[href="#…"]` selectors;
   - hashes stored in variables.

   Keep each test's intent: a test that asserts the URL is *unchanged* stays an
   unchanged-URL assertion via `current_route`. A post-pass `git diff` should show only
   these line classes.
4. **Legacy set.** Choose 8 or more tests that already navigate to a legacy URL as their
   setup, and leave their `goto` raw.
5. **Lanes**, then the union check, then the docs.
6. **Gates.** Lanes run one at a time. Budget about 20–25 minutes for all five.

## Edge Cases

- **Tests that build a hash from an id at runtime** (`f"#admin/providers/{pid}"`). Route
  them through `_nav.goto(page, base, f"settings/providers/{_nav.seg(pid)}")`.
- **Tests asserting the router's default redirects** (`#admin` → `#admin/general`).
  Under `SCHEME = "legacy"` they become `expect_route(page, "settings/general")`, which
  maps to `#admin/general`. After the flip they expect `#settings/general`. This is
  correct either way.
- **`test_flow_hash_routing.py`** is the router's own contract file, and leg 3 rewrites
  it. In this leg, migrate only its navigation calls, and mark its history-policy
  assertions with a comment that leg 3 inverts them (DD4).
- **`test_flow_picker.py`'s 3 permanently skipped dead tests.** Leave them. Leg 5
  retires them along with the top bar.
- **The `#main-content` skip-link test.** Not a route. Leave it as it is.

## Files Affected

- `tests/browser/_nav.py` (new)
- `tests/test_nav_helper.py` (new)
- `tests/browser/test_*.py` (about 45–50 files migrated)
- The four flaky tests' files, plus any minimal app fix (recorded)
- `scripts/run-tests.sh`
- `CLAUDE.md`, `the_one/agents.md`
- `missions/25-workbench-navigation/flights/02-shell-and-router/flight-log.md`

## Citation Audit

Checked at leg design against `ddc2c22`:
- the four test names and line numbers ✔ (grep);
- top-bar selector files (5) ✔;
- 63 files contain `goto(` ✔.

The following come from the router research at `fe595cc`, unchanged by Flight 1's
commits after it: `conftest.py:407-480 _goto_with_credential`, `run-tests.sh:57-79` lane
globs, and the 289 hash `goto`s with their group counts.

Design review (Developer, 2026-10-01) — "approve with changes". Applied:
- the real assertion and navigation shapes (there is no `to_have_url`);
- the `set_route`, `wait_for_route_prefix` and `href` helpers;
- the AST-based guard with a precise pattern and a per-function allow-list that
  self-checks for orphans;
- bare-destination rows plus canonicalisation and the inverse;
- per-segment hash comparison;
- `seg()` matching JS `encodeURIComponent` exactly;
- a pre-fix reproduction record, plus an artificial-hook option;
- the `-p no:randomly` no-op dropped;
- base normalisation;
- lane subtraction, the snapshot exclusion and the union-by-files check.

---

## Post-Completion

Completion steps — status transitions, flight-log update, checking off in the parent
flight, and commit — are Flight Control protocol, driven by the execution workflow. Not
repeated here.
