# Leg: ui-test-apparatus

**Status**: completed
**Flight**: [Control Library Foundation](../flight.md)

## Objective

Make the test infrastructure ready for a control library before any library code
exists:
- **Guards.** The testid extractor, the testid-value guard and the zero-sink guard
  understand library calls.
- **Accessibility.** A shared runtime label/description resolver exists.
- **Engines.** Library contract tests can run in Chromium and WebKit through an
  engine-parametrized harness with an explicit skip/require policy.
- **Desktop engine.** A WebKitGTK probe can evaluate checks in the real desktop engine.
- **Squawk.** Squawk 0105's stale comment is fixed.

## Context

- Flight design decisions this leg implements: **DD2** (testid patterns, composite rule
  enforcement, `relpath` fix), **DD3** (shared resolver JS and Playwright helper), **DD4**
  (zero-token guard over `static/js/ui/`), **DD9** (engine policy, installs, local WebKit
  route, WebKitGTK probe), **DD12** (squawk 0105). Read those DDs in `flight.md` before
  starting; they are the spec, and this leg restates only what is needed to verify.
- `static/js/ui/` does **not** exist yet; the next leg (`control-mechanism-spike`) creates
  it. Every guard added here must pass *vacuously* on the current tree, and must be shown
  to fire through `tmp_path` probes or synthetic DOM.
- Planning probes (2026-09-30, flight log Session Notes):
  - `DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`.
  - System `/usr/bin/python3` has `gi` with WebKit2 4.1 (WebKitGTK 2.52.6). The repo
    `.venv` has neither `gi` nor `pywebview`.
  - Playwright 1.58.0 is installed, with `pytest-playwright` 0.7.2. No webkit build is
    in `~/.cache/ms-playwright`.
  - `sudo` needs a password. Docker is not available in this WSL distro. The local
    Concourse (`127.0.0.1:8080`) is unreachable.
  - The Architect's dry run (`install-deps --dry-run webkit`) listed missing host
    packages: `libwoff1`, `libavif16`, `libevent-2.1-7t64`, `libflite1`, `libgtk-4-1`,
    the gstreamer bad and libav plugins, `libgstreamer-plugins-bad1.0-0` and `xvfb`.
  - `apt-get download` works without root. `webkit2gtk-driver` 2.52.6 is an
    uninstalled candidate.
- Conventions: `single-source-of-truth-for-paired-helpers` (one resolver JS shared by
  the Playwright helper and the probe); `report-what-you-got` (assert and record the
  engine actually launched and its version); `verbatim-message-equality` (guard failure
  messages are tested verbatim where tests assert on them).
- The production-safety rule applies (CLAUDE.md): never port 8484 or the default data
  dir. The dev instance for the probe is `THE_ONE_PORT=8485 THE_ONE_DATA_DIR=<scratch>
  THE_ONE_DEV_MODE=true`. Re-verify that 8485 is free before starting it, and stop it
  (`make down` with the same env) when done.

## Inputs

- `tests/_ui_guard_helpers.py`:
  - `relpath` (line 73), hardwired to `JS_DIR`;
  - `extract_testids` (line 78);
  - `classify_sinks` (line 269);
  - `find_markdown_html_sink_tokens` (line 353).
- `tests/test_ui_guards.py`:
  - the registry tests at lines 215, 248, 276 and 295;
  - the sink tests at lines 398 and 418;
  - the probe-test precedent at lines 497 and 524;
  - the `DYNAMIC_SINK_BASELINE` header comment at line 90 (squawk 0105).
- `tests/browser/test_flow_chiplist_label_resolver.py::_RESOLVE_JS` (line 34) and
  `_assert_labels_resolve_to_chip_input`.
- `tests/browser/conftest.py`:
  - `playwright_instance` (module-scoped `sync_playwright()`, line 316);
  - `browser` (`chromium.launch`, line 331).
- `Makefile:89-90` `_ensure-playwright`.
- `ci/tasks/browser.yml`: image `python:3.11` (lines 14-18), install (line 30), pytest
  (line 31).
- `.github/workflows/test.yml:73-78`, the break-glass browser job.
- `the_one/interfaces/web/static/index.html`, whose script and link order is the source
  of truth for load order.

## Outputs

**Guard helpers** (`tests/_ui_guard_helpers.py`):
- `relpath(path, root=JS_DIR)`;
- `extract_testids` and `classify_sinks` compute paths relative to the `js_dir` passed
  in;
- the two DD2 patterns;
- a testid-value scanner;
- a `static/js/ui/` zero-token helper.

**Unit guards and probes** in `tests/test_ui_guards.py`:
- library testid patterns;
- testid-value enforcement;
- the ui-dir zero-token guard;
- squawk 0105's comment reworded.

**Browser test files:**

| File | What it is |
|---|---|
| `tests/browser/_a11y_resolve.js` | The single resolver JS (DD3 rules) |
| `tests/browser/_a11y_resolvers.py` | `assert_controls_labelled_and_described(page, root_selector)` |
| `tests/browser/_ui_engines.py` | Engine-parametrized fixtures, the WebKit skip/require policy, and the disk harness that loads tokens, CSS and library JS in `index.html` order into a blank page |
| `tests/browser/test_ui_apparatus_contract.py` | Proves the resolver and harness in both engines on synthetic DOM. Its name falls to the `shared` lane |
| `tests/browser/test_flow_chiplist_label_resolver.py` | Migrated onto the shared resolver, keeping its stricter `.chip-list-input` assertion locally |

**Scripts:**
- `scripts/setup-webkit-userland.sh`: no sudo, idempotent.
- `scripts/webkitgtk_probe.py`: system-python WebKitGTK probe per DD9.

**Install changes:**
- `Makefile`: `_ensure-playwright` installs chromium and webkit.
- `ci/tasks/browser.yml`: pinned image, `--with-deps chromium webkit`,
  `THE_ONE_REQUIRE_WEBKIT=1`.
- `.github/workflows/test.yml`: the same install and env.

**Docs:**
- `the_one/agents.md`: a "UI test apparatus" subsection covering the library testid
  rule, resolver, engine fixture and policy, WebKit setup, and the probe.
- `CLAUDE.md` Testing section: a short pointer for the WebKit contract tests, the
  setup script, the probe and `THE_ONE_REQUIRE_WEBKIT`.

**Records:**
- `squawks/0105-*.md`: Corrective Action and Verification written; Status
  `in-progress`. The Flight Director closes it in the flight commit.
- Flight log entry, including the **WebKit route outcome** (route 1 established, or
  route 2 with evidence) and the probe's engine version and environment.

## Acceptance Criteria

**Guards (unit tier)**

- [x] **AC1** — `relpath`, `extract_testids` and `classify_sinks` work against any
  directory:
  - `extract_testids(tmp_path)` and `classify_sinks(tmp_path)` return paths relative to
    `tmp_path` without raising;
  - default-argument behaviour is unchanged;
  - every existing test in `tests/test_ui_guards.py` passes.
- [x] **AC2** — `extract_testids` recognises the DD2 library forms. Literal pattern:
  `\btestid:\s*'([^"'\n]+)'(?!\s*\+)`. Parametric pattern: `\btestid:\s*'([^"'\n]+)'\s*\+`.
  Probe tests in `tmp_path` assert:
  - (a) `App.ui.button({testid: 'x-save-btn'})` yields literal `x-save-btn` and no
    parametric;
  - (b) `{testid: 'x-row-' + a.id}` yields parametric `x-row-` and **no** literal;
  - (c) the same with the `+` on the next line yields parametric only;
  - (d) a per-item object inside an array literal yields its id;
  - (e) `rowtestid: 'nope'` yields nothing.
- [x] **AC3** — A testid-value guard (new unit test) scans `static/js/**/*.js`,
  comments included (consistent with the extractor).
  - It finds keys with `(?<![\w-])['"]?testid['"]?\s*:`. This excludes `data-testid`,
    `rowtestid` and bare `testid` parameters.
  - Outside `static/js/ui/`, a value must be a single-quoted literal followed by `,` `}`
    `)` or end of line, or a single-quoted `'prefix' +` concatenation.
  - Inside `ui/`, the only allowed value form is `<identifier-chain>.testid`
    (forwarding).
  - Quoted keys (`'testid':`, `"testid":`) and double-quoted values are rejected
    everywhere.
  - Classify the value by its **leading token**, not by splitting on `:`/`,`, so the
    quotes and colon inside a ternary (`c ? 'a' : 'b'`) are not mis-split.

  It passes on the current tree, which has zero `testid` keys. Probe tests in `tmp_path`
  show it flags `testid: someVar`, `testid: c ? 'a' : 'b'`, `'testid': 'x'`, `testid: "x"`,
  and a literal inside `ui/`. They show it accepts `testid: 'a-b'`, `testid: 'a-' + x`,
  and (inside `ui/`) `testid: opts.testid`.
- [x] **AC4** — A ui-dir sink guard (new unit test):
  - when `static/js/ui/` exists, it asserts the directory holds ≥1 `.js` file, and that
    `find_markdown_html_sink_tokens` returns zero tokens for each one;
  - when the directory is absent, it passes;
  - a `tmp_path` probe shows a file containing the token in a comment is flagged.
- [x] **AC5** — Squawk 0105: the `DYNAMIC_SINK_BASELINE` header comment
  (`tests/test_ui_guards.py:~90`) no longer restates a live site or file count; it says
  the dict is the authoritative current truth. The squawk file's Corrective Action and
  Verification are written.

**Runtime resolver and harness (browser tier)**

- [x] **AC6** — `tests/browser/_a11y_resolve.js` implements DD3's rules exactly:
  - the control set;
  - the accessible-name sources;
  - `aria-describedby`/`aria-labelledby` resolution with non-empty labelledby text;
  - the `aria-controls` exemption when `aria-expanded="false"`.

  The resolver **fails on zero matches**: a `root_selector` matching no element is a
  failure, never a vacuous pass. `_a11y_resolvers` exposes:
  - `collect_label_failures(page, root_selector) -> list[str]`, which never raises;
  - `assert_controls_labelled_and_described(page, root_selector)`, which raises
    `AssertionError` whose message lists the failures verbatim.

  Both load that file. No other copy of the logic exists: the chiplist test's
  `_RESOLVE_JS` is removed, and it uses the shared helper plus its own
  `.chip-list-input` tag/class assertion.
- [x] **AC7** — `tests/browser/_ui_engines.py` provides an engine-parametrized fixture
  family, `engine_browser` and `engine_page`, with parameter ids `chromium` and `webkit`.
  - **Name collisions.** pytest-playwright 0.7.2 is installed and active. No fixture in
    the family may reuse its names: `browser_name`, `browser_type`, `browser`, `page`,
    `context`, `playwright`, `browser_context_args`, `browser_type_launch_args`. The
    family must not request the plugin's `browser_type`.
  - **Launch.** The webkit browser is module-scoped and launched lazily, so chromium
    params never pay for it. Userland env (AC12) is passed through `launch(env={**os.environ, …})`,
    never by mutating `os.environ`.
  - **Smoke.** After launch, the fixture runs `page.goto("about:blank")` and
    `evaluate("1")`. A crash there counts as a launch failure under AC8.
  - **Marking.** Every test using the family carries `@pytest.mark.browser`.

  The disk harness loads static assets without spawning the app. It opens a blank page,
  and from `static/index.html`, in document order, it:
  - adds the `@layer` order statement;
  - adds each `/static/css/*.css` linked there, and `icons.js`;
  - adds every `/static/js/ui/*.js` script there, which is none today.

  It then mounts a root `<div data-theme="dark|light">` whose `color` and `background`
  are set from tokens.
- [x] **AC8** — WebKit skip/require policy:
  - with `THE_ONE_REQUIRE_WEBKIT` unset, a WebKit launch failure **skips** the webkit
    param with a reason naming the failure;
  - with `THE_ONE_REQUIRE_WEBKIT=1`, the same failure **fails**;
  - when WebKit launches, the test asserts `browser.browser_type.name == "webkit"` and
    records `browser.version`. Use pytest's `record_property`, and also print it so it
    appears in `-rA` output.

  The policy is a **pure function** in `_ui_engines.py`: given the env mapping and the
  launch outcome, it returns `ok`, `skip(reason)` or `fail(reason)`. It is demonstrated:
  - the skip path, by setting `THE_ONE_WEBKIT_FORCE_UNAVAILABLE=1`, a test-only seam
    documented in the module;
  - all branches, by **unmarked** unit tests in a separate file,
    `tests/test_ui_engines_policy.py`. They import `browser._ui_engines`, following the
    precedent of `tests/test_ui_guards.py` importing `browser.design_tokens`. They run
    in `make test-unit` and are not hidden by a lane's `-m browser`.
- [x] **AC9** — `tests/browser/test_ui_apparatus_contract.py` passes in **both** engines,
  or in chromium only with webkit skipped and the reason recorded. Under the disk
  harness, on synthetic DOM, the helper **flags**:
  - (a) an unnamed `<input>`;
  - (b) an icon-only `<button>` with no name;
  - (c) a dangling `aria-describedby`;
  - (d) a dangling `aria-labelledby`;
  - (e) an `aria-labelledby` pointing at an empty element;
  - (f) a dangling `aria-controls` on an `aria-expanded="true"` trigger.

  It **passes**:
  - (g) a labelled input with a resolving describedby;
  - (h) a content-named `[role=menuitem]`;
  - (i) a dangling `aria-controls` with `aria-expanded="false"`;
  - (j) an `aria-label`-named icon button.

  The "flags" cases assert on `collect_label_failures` output, matching each rule's
  failure text verbatim. The harness check: on the dark root, the computed
  `background-color` equals the dark `--bg` value from `tests/browser/design_tokens.py`.
  The same check on the light root gives the light value. The harness uses
  `page.set_content` first, then the index-derived `@layer` statement as the first style
  tag.
- [x] **AC10** — `tests/browser/test_flow_chiplist_label_resolver.py` still passes. It
  belongs to the `shared` lane, as does the new contract test.

**WebKit route and probe**

- [x] **AC11** — Installs:
  - `Makefile` `_ensure-playwright` runs `$(PY) -m playwright install chromium webkit`,
    and the comment above it (lines 83-87) is updated.
  - `ci/tasks/browser.yml`:
    - image tag pinned to `3.11-bookworm`;
    - the header comment updated;
    - install `python -m playwright install --with-deps chromium webkit`;
    - pytest runs with `THE_ONE_REQUIRE_WEBKIT=1`.
  - `.github/workflows/test.yml`: the browser job installs `chromium webkit` with
    `--with-deps` and sets `THE_ONE_REQUIRE_WEBKIT: "1"`.
- [x] **AC12** — Local WebKit route, attempted in order and recorded in the flight log:
  1. `.venv/bin/python -m playwright install webkit`, which needs no sudo.
  2. If headless WebKit fails to launch, `scripts/setup-webkit-userland.sh`:
     - uses `apt-get download` plus `dpkg -x` into `${THE_ONE_WEBKIT_DEPS:-$HOME/.cache/the-one-webkit-deps}`;
     - needs no sudo, is idempotent, and prints the env it expects;
     - the fixture applies `LD_LIBRARY_PATH` and `GST_PLUGIN_PATH` from that directory to
       the **WebKit launch only**, so chromium never sees userland libraries.

     Use `PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1` if host validation runs in the
     driver.

  Outcome: either `test_ui_apparatus_contract.py[webkit]` **runs and passes** locally
  (route 1, with engine version recorded), or the flight log records route 2 with the
  failing launch error, the libraries tried and why it stops. Either outcome satisfies
  this AC; silence does not.
- [x] **AC13** — `scripts/webkitgtk_probe.py`. Runs with `/usr/bin/python3`; `gi`
  imports sit inside `main()`.

  Arguments and safety:
  - takes `--url`, `--data-dir`, `--root-selector` (default `body`) and `--theme`
    (`dark|light`, default `dark`);
  - refuses port 8484, parsed with `urlsplit` (`127.0.0.1:8484` and `localhost:8484`
    both refuse);
  - refuses the platformdirs default data dir, derived by running
    `.venv/bin/python -c "from the_one.config import settings; print(settings.data_dir)"`
    with `THE_ONE_DATA_DIR` removed from that subprocess's environment. Both paths are
    compared after `Path.resolve()`.

  Loading the page:
  - reads `<data-dir>/api-credential` and mints a handoff via
    `POST {origin}/api/session/handoff`;
  - pins and records `GDK_BACKEND`, `WEBKIT_DISABLE_DMABUF_RENDERER=1` and the
    hardware-acceleration policy;
  - uses an ephemeral `WebKit2.WebsiteDataManager`;
  - sets `localStorage['theme-preference']` before the app's scripts run, then loads the
    handoff URL and verifies `document.documentElement.dataset.theme`.

  Waiting for the page: the handoff redirect strips the query, and the hash route
  renders client-side. So after load `FINISHED` the probe navigates to the URL's hash
  (`location.hash`). It then polls, under the timeout, until `--root-selector` matches at
  least one element, and only then runs checks.

  Checks and output:
  - evaluates `tests/browser/_a11y_resolve.js` over `--root-selector`;
  - prints one JSON object (`engine_version`, `env`, `theme`, `url`, `results`,
    `ok`) and exits 0 iff `ok`;
  - has a hard timeout (default 60s) so a wedged WebView cannot hang;
  - is ruff-clean.
- [x] **AC14** — The probe is **run once** against a dev instance (port 8485, scratch
  data dir, dev mode) on the dev-mode Design language page (`#admin/design-language`),
  with `--root-selector` scoped to a section that has labelled form controls.
  - The flight log records the JSON output: engine version, pinned env, theme, ok or
    not, and failures, since legacy sections may legitimately fail.
  - If a WebView cannot be created on WSLg, the flight log records the error as an
    **anomaly**. That is a flight divert criterion; do not paper over it.
  - Pre-existing resolver failures on legacy markup are **recorded, not fixed**. They are
    not part of this leg's scope.

**Docs and gates**

- [x] **AC15** — `the_one/agents.md` gains a "UI test apparatus" subsection, placed near
  the existing UI guard and testid content. It covers:
  - the library `testid` rule and enforcement;
  - the shared resolver and how to apply it;
  - the engine fixture and its skip/require policy and env vars;
  - the userland WebKit setup;
  - probe usage, with the production-safety rule.

  `CLAUDE.md`'s Testing section gains a ≤6-line pointer to it.
- [x] **AC16** — Gates pass:
  - `make lint`;
  - `make test-unit`;
  - the new and changed browser tests, via `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_ui_apparatus_contract.py tests/browser/test_flow_chiplist_label_resolver.py -x -rA`
    (the explicit `-m browser` is required);
  - `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane shared`.

## Verification Steps

- AC1–AC5:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_ui_engines_policy.py -x --timeout 60`,
  then read the new probe tests. `grep -n "92 sites" tests/test_ui_guards.py` returns
  nothing.
- AC6: `grep -rn "_RESOLVE_JS\|label.control" tests/browser/` shows the logic only in
  `_a11y_resolve.js`; the chiplist test imports the helper.
- AC7–AC9: `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_ui_apparatus_contract.py -x -rA`.
  - **Mind the marker.** `-m browser` is required. `pyproject` addopts deselect browser
    tests, and `run-tests.sh` adds `-m browser` only with `--lane`, so without it zero
    tests are collected.
  - **Expected output.** Every test appears twice, as `[chromium]` and `[webkit]`, and
    the WebKit version is printed (or the skip reason is shown).
  - **Skip path.** Run once more with `THE_ONE_WEBKIT_FORCE_UNAVAILABLE=1`. Every
    `[webkit]` param shows SKIPPED with the reason string.
- AC10: `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_flow_chiplist_label_resolver.py -x`.
- AC11: `git diff Makefile ci/tasks/browser.yml .github/workflows/test.yml`.
- AC12–AC14: the flight-log entry with the route outcome and the probe JSON.
  `/usr/bin/python3 scripts/webkitgtk_probe.py --url http://127.0.0.1:8484/ ...` exits
  non-zero with a refusal message, so production safety is demonstrated without
  contacting 8484.
- AC15: read the two doc sections.
- AC16: run the commands listed.

## Implementation Guidance

1. **Guard helpers first** (AC1–AC5). Make `relpath` take a `root` argument and thread
   `js_dir` through `extract_testids` and `classify_sinks`.
   - Add the two DD2 patterns to `extract_testids`.
   - Add the testid-value scanner. A simple approach: regex out every `testid` key with
     its value up to the next `,` `}` or newline, then classify.
   - Keep regex comments explaining each pattern, matching the existing style
     (lines 50-66).
   - Write probes in the style of `test_label_for_guard_flags_dangling_target`
     (line 497).
2. **Resolver JS** (AC6): write a plain function `(rootSelector) => ({ok, failures: [...]})`
   in `_a11y_resolve.js`. ES5 is not required for test code, but keep it plain so
   WebKitGTK 2.52 evaluates it.
   - Each failure names the element (tag, id, testid, outerHTML prefix) and the rule it
     broke.
   - The Python helper reads the file and calls `page.evaluate`. It asserts `ok` and
     prints the failures verbatim.
   - The probe embeds the same file by reading it from disk.
3. **Engine fixtures** (AC7–AC8).
   - Launch webkit lazily, only when a webkit param runs, from the existing
     module-scoped `playwright_instance`, or from a dedicated one if env must be set
     before the driver starts. Do not change how chromium launches for the rest of the
     suite.
   - The disk harness reads `index.html` with a regex over `href="/static/…css"` and
     `src="/static/…js"`, maps each to a disk path under `the_one/interfaces/web/static/`,
     and loads them with `page.add_style_tag(path=…)` / `page.add_script_tag(path=…)`.
   - Font `@font-face` URLs will 404 from a blank page; that is acceptable.
4. **Installs** (AC11). Mechanical.
5. **Local WebKit** (AC12). Try route 1 first; only write the userland script if the
   launch fails.
   - Keep the userland libraries out of the repo.
   - Time-box this. If after a reasonable attempt (about 45 minutes of work) WebKit still
     won't launch, record route 2 and move on. The flight design anticipated this.
6. **Probe** (AC13–AC14). Use `WebKit2.WebView` inside a `Gtk.Window` (GTK 3, WebKit2
   4.1).
   - Load with `load_uri` and wait for `load-changed` `FINISHED`.
   - Set the hash and poll for the root selector (AC13).
   - Then call `evaluate_javascript`, which is **async**: pass length `-1` and `None` for
     world, source_uri and cancellable; finish with `evaluate_javascript_finish` and read
     the `JavaScriptCore.Value` via `.to_json(0)`. Quit the main loop after.
   - `gi.require_version` is needed for `Gtk` 3.0, `WebKit2` 4.1 and `JavaScriptCore`
     4.1, all inside `main()`.
   - Guard everything with `GLib.timeout_add_seconds`.
   - Start the dev instance with
     `THE_ONE_PORT=8485 THE_ONE_DATA_DIR=<scratch> THE_ONE_DEV_MODE=true make up` and stop
     it with `make down` using the same env.
7. **Docs** (AC15), then the full gates (AC16).

## Edge Cases

- **A comment carries `testid: '…'`.** The extractor scans comments, so do not add
  example ids in comments anywhere in `static/js`. Test fixtures live in `tmp_path`, not
  in `static/js`.
- **`index.html` changes later.** The harness derives load order from it, so the next
  leg's new `<script>` tags are picked up automatically. The disk harness must not
  hardcode a file list.
- **WebKit "launches" but crashes on first navigation.** Treat that as a launch failure
  under the skip/require policy, with the stderr excerpt in the reason.
- **WSLg display unavailable mid-run.** The probe exits non-zero with a clear message,
  never hangs.
- **A first-run gate on a fresh scratch data dir.** If one prevents
  `#admin/design-language` from rendering, seed only what is needed, via the API with
  the credential, and note it in the flight log. Do not change app behaviour.
- **The dev instance on 8485 is already running** from another session. Don't kill it
  blindly. Check its data dir via `/proc/<pid>/environ`, and pick 8486 if it isn't
  yours.

## Files Affected

- `tests/_ui_guard_helpers.py` — `relpath` root parameter; DD2 patterns; testid-value
  scanner; ui-dir zero-token helper.
- `tests/test_ui_guards.py` — new guards and probes; squawk 0105 comment.
- `tests/browser/_a11y_resolve.js` — new; the single resolver.
- `tests/browser/_a11y_resolvers.py` — new; the Playwright helper.
- `tests/browser/_ui_engines.py` — new; engine fixtures, policy, disk harness. Register
  its fixtures through `tests/browser/conftest.py` if needed.
- `tests/browser/test_ui_apparatus_contract.py` — new (`shared` lane).
- `tests/test_ui_engines_policy.py` — new; unmarked unit tests of the policy function.
- `tests/browser/test_flow_chiplist_label_resolver.py` — migrated onto the shared
  resolver.
- `scripts/setup-webkit-userland.sh` — new, only if route 1 fails.
- `scripts/webkitgtk_probe.py` — new.
- `Makefile`, `ci/tasks/browser.yml`, `.github/workflows/test.yml` — WebKit installs and
  the require flag.
- `the_one/agents.md`, `CLAUDE.md` — docs.
- `squawks/0105-*.md` — Corrective Action and Verification.
- `missions/25-workbench-navigation/flights/01-control-library-foundation/flight-log.md`
  — leg entry.

## Citation Audit

Checked against `797b4d2` (the flight branch head at leg design):
- `tests/_ui_guard_helpers.py:73` `relpath` → `path.relative_to(JS_DIR)` ✔
- `:78` `extract_testids`, using the `_ATTR_*`/`_SETATTR_*` patterns at `:52-62` ✔
- `:269` `classify_sinks` ✔
- `:353` `find_markdown_html_sink_tokens(path)` ✔
- `tests/test_ui_guards.py` test names at `:215/:248/:276/:295/:398/:418/:497/:524` ✔
- `:90` "92 sites across 27 files" ✔
- `tests/browser/test_flow_chiplist_label_resolver.py:34` `_RESOLVE_JS` ✔
- `tests/browser/conftest.py:316/:331` ✔
- `Makefile:89-90` ✔
- `ci/tasks/browser.yml:16-18,30-31` ✔
- `.github/workflows/test.yml:73-78` ✔

Design review (Developer, 2026-09-30) — "approve with changes". Applied:
- `-m browser` added to every browser command; AC10's lane corrected to `shared`;
- the pure policy function, with unit tests in an unmarked top-level file;
- the probe's hash-render wait and zero-match failure;
- the full pytest-playwright fixture-name ban (`engine_*` names);
- AC3's key regex and leading-token value classification;
- the async `evaluate_javascript` notes;
- port and path checks in the probe;
- `collect_label_failures` and the assert split;
- the Makefile comment;
- a first-run-gate edge case.

---

## Post-Completion

Completion steps — status transitions, flight-log update, checking off in the parent
flight, and commit — are Flight Control protocol, driven by the execution workflow. Not
repeated here.
