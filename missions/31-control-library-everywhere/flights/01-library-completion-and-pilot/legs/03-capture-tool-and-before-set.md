# Leg: capture-tool-and-before-set

**Status**: completed
**Flight**: [Library completion and a stateful pilot](../flight.md)

## Objective
Build `scripts/ui_capture.py`, a dev tool that starts its own scratch app instance, seeds it, and captures named UI surfaces in both themes as PNGs outside the repo. Pin its safety refusals with unit tests, then take the flight's "before" capture set.

## Context
- **Flight DD10** (the capture tool and its pinned environment) and the mission's capture criterion: before and after captures are local flight-log evidence, never committed; the operator approves each flight's set at the HAT.
- This was split from leg 02 at design review. The review's details are folded in below.
- **Reference implementations to read, without importing from `tests/`:**
  - `tests/browser/conftest.py::_spawn_app` (`:206`): uvicorn subprocess, credential written before `Popen`, `THE_ONE_DEV_MODE=true`, and `THE_ONE_OLLAMA_LIBRARY_TEST_JSON` as the Ollama library seam.
  - `tests/browser/conftest.py::_establish_session_cookie`: `POST /api/session/handoff` with the bearer credential, then `context.request.get(url)` sets the session cookie for the context.
  - `tests/browser/seeders.py`: the exact `POST /api/providers` shapes per type (`mock` needs dev mode).
  - `tests/browser/test_flow_provider_ollama_pull.py:43-56`: the route stubs for `**/api/providers/*/models`, `**/models/status` and `models/pull`, and their payload shapes (or `tests/browser/_providers.py`).
  - `tests/browser/test_flow_provider_plan_signin.py`: `/oauth/start` is local-only and safe to call for real. Block navigation to claude.ai with a context route, as `_providers.block_claude_ai` does. The awaiting-code state needs a saved `anthropic-plan` provider, then a click on Sign in.
  - `static/js/theme.js:14`: the localStorage key `theme-preference` (`light`/`dark`/`auto`).
  - `scripts/run-tests.sh:483-497`: the netns wrapper (`unshare -rn sh -c 'ip link set lo up && exec "$@"'`).
  - `scripts/webkitgtk_probe.py`: `default_data_dir()` (`:64`) and `mint_handoff_url()` (`:111`). **Do not move them.** `tests/test_webkitgtk_probe_safety.py` loads the probe through `importlib` and calls its names; a shared module would not be on `sys.path`. Load them into `ui_capture.py` with `importlib`, or copy the two small functions. `ui_capture.py` writes its own `check_capture_safety(...)`.
- Playwright's sync API is importable from the venv. Chromium already runs inside the netns in the browser lanes with a default headless launch.

## Inputs
- Legs 01-02 landed (uncommitted).

## Outputs
- `scripts/ui_capture.py` (new).
- `tests/test_ui_capture_safety.py` (new, unit tier).
- The "before" set at `$HOME/.cache/the-one-ui-capture/m31-f1-before/`, with a `manifest.json`. Recorded in the flight log; never in git.
- Docs: `the_one/agents.md` "UI test apparatus" and one line in `CLAUDE.md`.

## Acceptance Criteria
- [ ] **`check_capture_safety(port, data_dir, out_dir, default_dir, env_data_dirs, repo_root)`** raises on:
  - port 8484 or 8485, or any port below 8490;
  - `data_dir` equal to or inside `default_dir`, or equal to or inside any of `env_data_dirs`;
  - `out_dir` inside `repo_root`.

  `env_data_dirs` comes from `THE_ONE_DATA_DIR` in the environment and from `THE_ONE_DATA_DIR=` in the repo's `.env`, parsed as text lines, never by importing the app's settings in the parent. `default_dir` comes from the probe's `default_data_dir()` derivation.
- [ ] **`tests/test_ui_capture_safety.py`** (unit tier, no app start, no browser, default dir injected) pins every refusal above plus one accepted configuration. It loads the script with `importlib`, as the probe's safety test does.
- [ ] **Instance and seeding.** `scripts/ui_capture.py`:
  - **Port:** picks a free port of 8490 or higher (loop until the port is at least 8490 and bindable). Never 8484 or 8485.
  - **Directories:**
    - a fresh data dir (default `$HOME/.cache/the-one-ui-capture/<run-id>/data`), seeded from nothing;
    - the credential written before start;
    - a scratch cwd.
  - **Start:** `THE_ONE_DEV_MODE=true` plus the Ollama library seam, then a readiness poll on `GET /api/live`.
  - **Seeding,** through the API with the bearer credential:
    - one provider of each type the editor renders differently: `ollama`, `openai-compatible`, `openai`, `anthropic`, `anthropic-plan`, `anthropic-plan-token`, `openrouter`, `mock`, with dummy keys and URLs;
    - one agent.
  - **Stop:** by its own PID. The scratch tree is removed unless `--keep`.
- [ ] **Capture.** For each surface in its table, the script:
  - opens a fresh context with viewport 1440×900, time zone `UTC`, locale `en-US` and `color_scheme` set;
  - sets `theme-preference` through `add_init_script` before the first load;
  - authenticates by a handoff minted per context, fetched through `context.request`;
  - routes claude.ai to an abort;
  - navigates to the surface's hash, applies its stubs and actions, waits for its settled-state ready selector (a testid), and asserts the page is not the unauthenticated or empty state;
  - writes `<out>/<surface>--light.png` and `--dark.png`.
- [ ] **The surface table** covers at least:
  - the provider editor in edit mode for each seeded type;
  - the provider editor in create mode (`library/providers/~new`);
  - the Ollama models panel, stubbed with 2-3 models in mixed loaded and unloaded states;
  - the provider Test result, ok and failed, stubbed;
  - the plan sign-in block in its awaiting-code state;
  - a flash, shown after a Save.

  The chat and MCP consent-link surfaces are wanted but may be `SKIPPED` with a reason (their leg-05 change is click feedback, which a static capture does not show). Every `SKIPPED` surface is listed in the script with its reason and printed at the end.
- [ ] **Clock.** The plan-token "expires around" line is stubbed to a fixed date, or recorded in the script as an accepted difference.
- [ ] **CLI:**
  - `--out DIR` (required; refused inside the repo, and refused if non-empty unless `--force`);
  - `--surfaces a,b` filters;
  - `--list` prints the table;
  - `--keep` keeps the scratch tree.
- [ ] **Netns.** `THE_ONE_TEST_NETNS=1` re-runs the whole script under `unshare -rn` (with `lo` up) before anything starts. A sentinel environment variable prevents a loop. It fails loudly when the namespace is unavailable.
- [ ] **Manifest.** The script writes `<out>/manifest.json`: git SHA, `git status --short`, surfaces captured and skipped, viewport, themes, timestamp.
- [ ] **The "before" set is taken** with `THE_ONE_TEST_NETNS=1` to `$HOME/.cache/the-one-ui-capture/m31-f1-before/`.
  - First, the unchanged-tree check: `git diff 59992fd --` on `the_one/interfaces/web/static/js/areas/studio/provider-editor.js`, `provider-models.js`, `providers-section.js`, `the_one/interfaces/web/static/js/consent-link.js`, `js/app.js` and `js/confirm.js` is empty.
  - `git diff 59992fd -- the_one/interfaces/web/static/css/` shows only leg 01's page-only deletions and leg 02's `ui-icon` banner.
  - At least four PNGs, from both themes, are opened with the Read tool to confirm they show the intended surface.
  - The flight log records the path, the surface list, the `SKIPPED` list and the check results.
- [ ] **Gates:**
  - `make test-unit`;
  - ruff check and format (`scripts/` is in scope).
- [ ] **Docs:**
  - `the_one/agents.md` "UI test apparatus" describes the tool, its refusals, the netns re-run and the no-commit rule;
  - `CLAUDE.md` gets one line where the other dev tools are listed.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_capture_safety.py -x -q`; `make test-unit`.
- `.venv/bin/python scripts/ui_capture.py --list`.
- `.venv/bin/python scripts/ui_capture.py --out "$PWD/tmp-capture"` exits non-zero with a clear refusal (inside the repo).
- `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out $HOME/.cache/the-one-ui-capture/m31-f1-before`; list the directory; Read four PNGs.
- The two `git diff 59992fd` checks.
- `git status --short` shows no PNG under the repo.

## Implementation Guidance
1. Write `check_capture_safety` and its unit test first.
2. Start-up and seeding: mirror `_spawn_app`, copying from `seeders.py`.
3. The capture loop with one surface (a provider editor). Get light and dark right, and check the images by eye.
4. Add the remaining surfaces and stubs, copying payload shapes from the provider tests.
5. The netns re-run, the manifest, the "before" set, docs.

## Edge Cases
- **A slow render.** The ready selector is the settled state (for example the models list rows, or the Test result text), not the editor shell.
- **The handoff is single-use.** Mint one per context.
- **A leftover scratch dir** from a crashed run: the run id makes each run's directory unique. `--keep` is never the default.
- **An out dir that exists and is non-empty** is refused without `--force`, so a "before" set is never overwritten by accident.

## Files Affected
- `scripts/ui_capture.py` (new), `tests/test_ui_capture_safety.py` (new), `the_one/agents.md`, `CLAUDE.md`.

## Citation Audit
Checked 2026-10-15 by the leg 02 design review:
- `conftest.py:206` (`_spawn_app`);
- `webkitgtk_probe.py:64,111`;
- `theme.js:14` (`theme-preference`);
- `test_flow_provider_ollama_pull.py:47-49` (stub routes);
- `test_flow_provider_plan_signin.py:13` (`/oauth/start` local-only);
- `run-tests.sh:483-497`.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
