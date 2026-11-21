# Leg: desktop-webviews

**Status**: in-flight
**Flight**: [The GleepGlorp drawer and form filling](../flight.md)

## Objective

Show that the GleepGlorp drawer and a fill work in the three desktop engines
(DD11): WebKitGTK (Linux), WebView2 (Windows) and WKWebView (macOS). In each
engine:
1. **The corner button opens the drawer.** It shows off Chats and opens the
   drawer.
2. **Esc closes it.** Focus returns to the button.
3. **A fill lands as unsaved edits.** A message sent from the drawer makes
   GleepGlorp (a scripted mock, no real model or key) call `fill_form`. The
   fill applies in the agent editor as unsaved edits:
   - the fill row reaches `filled`;
   - an `agent-filled-note` shows;
   - no agent is created.

Operator decisions (2026-11-20):
- **macOS:** extend the existing `lifecycle` mode of
  `.github/workflows/macos-packages.yml` with a drawer step, so no workflow
  input changes and no PR to main.
- **Windows:** runs with the operator present, who is pinged just before
  the run takes the foreground.

## Context (design survey and design review cycle 1)
- **The mock repeats itself.** `MockProvider` (`the_one/llm/mock.py`)
  returns `config["response"]` on every call, so a scripted `fill_form` call
  would repeat on every loop step until the step limit.
- **How the loop builds messages.** `Agent.step` appends the user message,
  the assistant reply, then one tool message per call. A user-sent
  `continue` or an approval starts a new user message. The page line is
  metadata on the user message.
- **Who creates the credential.** `the-one serve` never creates
  `api-credential`. The desktop app does (macOS, Windows), and
  `the-one rotate-api-credential` does (for a serve instance).
- **Setting GleepGlorp's model.** `PUT /api/gleepglorp` with a mock
  provider and model `mock-default` is accepted, as browser tests do.
- **Only a drawer turn can fill.** `fill_form` needs a drawer turn with a
  page, and only the drawer instance that owns the turn applies it
  (`ownsTurn`). The scenario must send from the drawer composer and must not
  navigate during the settle wait.
- **The app opens on Chats.** The router falls back to `chats`, where the
  button and the drawer are hidden, so every engine first moves off Chats.
  The deterministic keyboard path is Jump to (Ctrl K, or Cmd K on macOS),
  type "Appearance", Return, which goes to Settings › Appearance.
- **Push or overlay.** The drawer pushes `<main>` at 1280px and wider and
  overlays below (`js/gleepglorp-drawer/shell.js`). The probe window
  defaults to 1280x900 and a hosted Mac screen may be smaller, so each run
  records its CSS width. No run asserts push mode.
- **What each engine can prove:**
  - **WebKitGTK:** synchronous JS setup scripts plus a GTK-level key (its
    verdict is "partially verified (GTK-level key)"), and selectors.
  - **WebView2 and the macOS hosted app:** no DOM access. The proof is the
    app's HTTP API (`filled`, which the applier posts only after it wrote
    the editor; no new agent) plus screenshots.

## Parts

### Part A — the driver (autonomous, Developer; reviewed and committed before B-D)
1. **`MockProvider` gains an optional `config["responses"]` list.**
   - **Selection:** the entry is chosen statelessly from the request
     messages. Entry `i` is the number of tool-role messages after the last
     user message, clamped to the last entry.
   - **Shape:** each entry has the same shape as `response` (`content`,
     `tool_calls`, `thinking`).
   - **Fallback:** with `responses` absent, behaviour is byte-identical.
   - **One helper** serves `complete`, the non-chunked `stream`, and the
     `stream_chunks` path, which today reads `response` directly and must
     use the selected entry.
   - **Dev-mode-only by documentation.** The provider type is already gated
     by dev mode, so no new gate is added.
   - **Docs:** update the class docstring and the `CLAUDE.md` "Mock provider
     `config` options" list together. Nothing pins them; keep them equal by
     hand.
   - **Tests** in `tests/test_mock_provider.py`:
     - the sequence;
     - the clamp;
     - a new user message restarting at 0;
     - absent `responses` unchanged;
     - streaming with and without chunks.
2. **One server-level proof that a mock-driven fill works through the real
   loop.** Test file: `tests/test_gleepglorp_fill_tool.py`, or a new test
   file.
   - **The turn:** a GleepGlorp agent built through the factory on a mock
     provider with `responses` (a `fill_form` create call, then text).
   - **How it is run:** one `step` with a page and a `TurnContext` carrying
     the page.
   - **Asserts:** one fills row with the changes, the final text, and no
     step-limit stop.
   - **Also confirm:** `fill_form` is in GleepGlorp's starting tool set, or
     the loop runs it anyway.
3. **`scripts/gleepglorp_drawer_seed.py`**, standard library only.
   - **Seeding:**
     - It takes `--base-url` and `--data-dir`, and reads the credential
       from `<data_dir>/api-credential`.
     - It creates the credential with `the-one rotate-api-credential` only
       with `--rotate-if-missing` (the WebKitGTK serve instance only).
     - It creates a mock provider whose `responses` are a `fill_form`
       create-agent call (name "Filled by mock", a description and a system
       prompt, from the declared shape), then the text "The form is filled,
       not saved. Click Save."
     - It sets GleepGlorp to that provider and model `mock-default`, and
       waits for `state: ready`.
     - It prints JSON: the provider id, dev mode, the GleepGlorp state.
   - **Safety:**
     - It refuses port 8484 and 8485.
     - It refuses the default data directory. It tries
       `the_one.config.settings.data_dir`; when `the_one` cannot be
       imported (the macOS runner), it computes the platformdirs path per
       OS (macOS `~/Library/Application Support/the-one`, Linux
       `~/.local/share/the-one`, Windows `%LOCALAPPDATA%\the-one`).
     - It also refuses any extra `--refuse-data-dir PATH`.
     - It refuses a data directory with no credential, unless
       `--rotate-if-missing` is given.
   - **`--check-fill`:** prints the newest fill's status (through
     `GET /api/chat/sessions` then `GET /api/gleepglorp/fills?session_id=`)
     and whether an agent named "Filled by mock" exists. Exit code 0 means
     `filled` and no such agent; 1 means anything else.
   - **Tests:** a unit test on the refusals, the request bodies and the exit
     codes, with a fake transport and no network.
4. **WebKitGTK setup scripts** under `scripts/probe/gg-drawer/`.
   - **How the probe runs them:** wrapped as `(function(){…;return true;})()`
     and run synchronously, so a Promise is not awaited. Async steps use
     `setTimeout`, `setInterval` or a `MutationObserver` that write
     `window.__probeReport`; the probe reads it after keys, asserts and
     polls.
   - **Keys:** `Gdk.keyval_from_name` is case-sensitive, so the key is
     `--press-keys Escape`.
   - **Testids:** use the drawer's real ones (`gg-corner-button`,
     `gg-chat-input`, the drawer's Send button; confirm each in the code).
   - **The three runs** (each starts at `#settings/appearance`):
     - **open:** click the corner button. Report whether `#gleepglorp-drawer`
       is visible, its width and `window.innerWidth`. Use
       `--assert-selector '#gleepglorp-drawer:not([hidden])'`.
     - **Esc:** the setup script opens the drawer and focuses inside it.
       `--press-keys Escape`, then
       `--assert-selector '[data-testid="gg-corner-button"]:focus'`.
     - **fill:**
       - The setup script opens the drawer, types into the drawer composer
         and sends.
       - An observer records into `__probeReport`: the note present, the
         name field's value, the `editor-unsaved` caption text, and the
         route (the fill navigates to `#agents/~new`).
       - Use `--root-selector '[data-testid="agent-filled-note"]'` with a
         `--timeout` above 60 s.
       - The a11y `ok` of the resolver is read separately from the fill
         verdict.
5. **macOS drawer step**, `L9b` in `packaging/macos/lifecycle.sh`.
   - **Placement:** between L9 (the N+1 install) and L10 (the remove step,
     which deletes the app), against the installed N+1. Add it to the `for
     entry in` list, the `case "$STEP"` dispatch and a `CAP_L9B` cap.
     L1-L10's behaviour is untouched.
   - **Fresh app:** the step first stops the running app (`stop_all`),
     because `open -a` on a running app ignores `--env` and the second-launch
     focus logic would attach.
   - **Its own instance:** it then reassigns its child-run globals: `PORT`
     8486 or higher, a scratch `DATA_DIR` under the step directory,
     `CRED_FILE`, `BASE` and `CUSTOM=1`. It launches with `open --env`,
     adding `THE_ONE_DEV_MODE=true` for this step only.
   - **Seed:** the desktop app creates the credential, so the step waits
     for `api-credential`, then runs the seed script with the runner's
     `python3`, passing `--refuse-data-dir` for the lifecycle's own data
     dir.
   - **Drive:**
     - leave Chats with Cmd K, `keystroke "Appearance"`, Return;
     - open the drawer with Cmd K, `keystroke "Ask GleepGlorp"`, Return;
     - type the message and press Return;
     - wait for `--check-fill` to exit 0, with a bound;
     - press Esc (key code 53).
   - **Evidence:** `screencapture -x` shots into the step directory, which
     the existing upload carries (verify), plus the window size from
     `window_state`, recorded as the likely overlay width. A failure fails
     the mode as other steps do. The app is stopped at the end, so L10 runs
     as before.
   - **Time budget:** the existing caps sum to about 1120 s against
     `M32_BUDGET` of 1000 s or less, inside a 1200 s outer bound. Give
     `L9b` an explicit cap of 150-200 s. Check the last lifecycle run's total
     in the Mission 32 logs, and raise the budget or `timeout-minutes`
     formula in the same edit if the headroom is under the cap.
   - **No change to the workflow's `on:` block or inputs.**
6. **Windows runbook,** written into the leg's flight-log entry rather than
   a new tool.
   - **Gates first:** `doctor-host`, which shows the networking mode, then
     `snapshot --out`.
   - **Launch:** `setup`, then `launch --dev-mode` (a source run on port
     8490 or higher with a scratch data dir).
   - **Reachability gate:** WSL must reach `127.0.0.1:<port>/api/live`
     before seeding.
   - **Seed:** run the seed script from WSL. The desktop app created the
     credential; read it through the WSL path of the data dir. The
     default-dir refusal cannot see the Windows dir from WSL, so rely on
     the tool's own data-dir gates and say so.
   - **Drive:**
     - `hands-off`, then `resize --width 1440 --height 900`;
     - `keys` for Ctrl K, "Appearance", `{Enter}`;
     - Ctrl K, "Ask GleepGlorp", `{Enter}`;
     - the message (no `^`, `+` or `%`) and `{Enter}`;
     - `--check-fill`;
     - `keys '{Esc}'`.
   - **Evidence and close:** `capture --window` after each step, `stop`,
     `snapshot --compare`.

### Part B — WebKitGTK run (FD)
- **Instance:** a dev instance on port 8486 or higher, scratch data dir
  under `$HOME`, started from a scratch working directory with `the-one
  serve`. Record its PID.
- **Seed:** the seed script with `--rotate-if-missing`.
- **Runs:** the three probe runs with `/usr/bin/python3
  scripts/webkitgtk_probe.py`.
- **Record:** verdicts and limits. Stop the instance by its PID.

### Part C — macOS run (FD; outward, operator-confirmed command)
- **Push first:** push the branch. The pushed head must equal the intended
  commit (`git rev-parse HEAD origin/<branch>`).
- **Dispatch, as its own command:** `gh workflow run macos-packages.yml
  --ref flight/03-drawer-and-form-filling -f mode=lifecycle`. The operator
  confirms it before it runs.
- **Record:** the run id and the head SHA. Read the summary and the `L9b`
  evidence.

### Part D — Windows run (FD, operator present)
- Ping the operator before the first foreground gesture.
- Follow the runbook. Captures stay outside the repo. Stop the run by its
  recorded process identity only.

## Acceptance Criteria
- **AC1. The mock sequence.** `responses` works as specified, and every
  existing `MockProvider` test and browser user passes unedited. The
  docstring and `CLAUDE.md` agree.
- **AC2. Through the real loop.** The server-level test shows a
  mock-driven GleepGlorp page turn that records exactly one fill and ends
  with the text.
- **AC3. The seed script.** It seeds a dev instance so GleepGlorp is `ready`
  on the mock. It refuses 8484, 8485, the default data directory (with and
  without `the_one` importable) and `--refuse-data-dir` (unit tested).
  `--check-fill` exits 0 only for `filled` with no agent.
- **AC4. WebKitGTK.** The three probe runs pass:
  - the drawer opens (width recorded);
  - Esc returns focus to the button (GTK-level key);
  - the fill shows its note and the unsaved name, with `--check-fill`
    exiting 0.
- **AC5. macOS.** The lifecycle dispatch is green with `L9b`: `--check-fill`
  exits 0, and there are screenshots of the open drawer and the filled
  editor. L1-L10 are green and unchanged in behaviour.
- **AC6. Windows.** Captures show the open drawer, the filled editor and
  the drawer closed after Esc; `--check-fill` exits 0. The snapshot compare
  is clean.
- **AC7. Limits stated.** For each engine, the flight log states what was
  proven directly, what only indirectly (focus after Esc on Windows and
  macOS is screenshot-only), and the CSS width used.

## Verification (Part A)
- `.venv/bin/python -m pytest -x -q --timeout 60 tests/test_mock_provider.py
  tests/test_llm_registry.py tests/test_provider_api.py`, the new loop test
  and the seed script test.
- `THE_ONE_TEST_NETNS=1 make test-unit`.
- The `chats` and `chats-transcript` lanes, one at a time, which hold the
  mock's browser users.
- ruff check and format.
- `bash -n packaging/macos/lifecycle.sh`, and `shellcheck` if available.
- A dry run of the seed script against a local dev serve instance on port
  8486 or higher with a scratch dir, stopped by PID.

## Safety
- **Never** port 8484 or 8485, or the default data directory, in any
  engine.
- **No secrets or real model keys** anywhere: the mock only.
- **Outward steps** (the push and the dispatch) run as their own commands,
  after a head check, with the operator's confirmation.
- **The Windows run** follows the tool's gates; the operator can stop it
  at any time.

## Design review cycle 1 (Developer, Sonnet: approve with changes)
These findings are folded in:
- **macOS step placement:** `L9b` between L9 and L10, since L10 deletes the
  app.
- **macOS instance:** its own port, data dir and dev mode, a stop first,
  and the credential from the app.
- **Starting page:** each engine leaves Chats first, through Jump to (Cmd K
  on macOS).
- **Probe:** `Escape`, synchronous scripts with an observer, and
  `:focus`-based asserts.
- **Seed script:** works without `the_one` (platformdirs fallback,
  `--refuse-data-dir`).
- **Lifecycle time budget:** a `CAP_L9B` cap.
- **A real-loop test:** a mock-driven fill through the agent loop.
- **Windows runbook:** a reachability gate and the key grammar.

The designer's answers: N+1 between L9 and L10; a Settings page hop, with
no seeded agent; `responses` dev-only by documentation.

## Design review cycle 2 (Developer, Sonnet: approve with changes)
These findings are binding on Part A. Where they differ, they override the
text above.
- **Time budget.**
  - The existing caps sum to about 1120 s, and `M32_BUDGET` (`B − 200`, at
    most 1000 s) is checked only at each step's start. With `L9b` added,
    L10 would be skipped as "budget spent".
  - Raise the workflow's `B` ceiling from 1200 to 1450 and `timeout-minutes`
    from 21 to 25, and update the "(<= 20 min)" and "no step cap exceeds
    200 s" comments. The job's 60-minute total must still leave the
    workflow's later steps their time; check the arithmetic.
  - Say in the `lifecycle.sh` header whether the 850 s default changes.
  - Give `CAP_L9B` 180 s.
- **Stopping N+1 before `L9b`.**
  - Use `cli_run "$T_CLI" "$EXE" quit --wait` on the default-port globals,
    before reassigning them, then `wait_exit`. `stop_all` is only the
    fallback.
  - At the end of `L9b`, quit the 8486 instance the same way. Add an
    explicit "no listener on the step's port" check, because `listeners`
    only checks the default `PORT`.
- **The macOS credential wait** is bounded at 30 s. If it is still absent,
  run `the-one rotate-api-credential` through `cli_run` with the step's
  `THE_ONE_DATA_DIR`, then continue.
- **macOS keys** go through `sys_events` with the app's pid:
  - make the app frontmost first (`ensure_visible` or `window_state`);
  - Cmd K is `keystroke "k" using command down`;
  - wait for the palette to close after each Return (about 1 s) before the
    next Cmd K;
  - Esc is key code 53.
- **The Windows runbook** spells Ctrl K as `^k`, and uses `{Enter}` and
  `{Esc}` (confirm the case handling). The message text avoids `^`, `+`,
  `%`, `{` and `}`.
- **WebKitGTK:**
  - the fill run uses `--timeout 120`;
  - the Esc run uses `--assert-timeout 15`;
  - `--data-dir` is the seeded instance's scratch dir;
  - before `Escape`, the Esc run's setup script focuses the drawer's `h2`
    or Close button, not the composer textarea, so the drawer's own
    handler gets the key. Check which element `ui/drawer.js` focuses on
    open.
- **Mock tests also pin:**
  - the second call (one tool message) returns the text entry;
  - with `stream_chunks`, the selected entry's `tool_calls` ride the last
    chunk (`mock.py` reads `response` directly there today).
- **Widths:** only WebKitGTK reports `window.innerWidth`. For Windows and
  macOS, record the window size and say the CSS width is inferred.
- **Part C** records the pushed head SHA together with the `rev-parse`
  check.
- **Answers:**
  - `L9b` reads the shared `app.log` only to attach its tail to its own
    failure evidence; it adds no new log-based gate.
  - A red mode on an `L9b` failure is intended, and L10 still runs as its
    own step.
- **Design review closed** at the two-cycle maximum, with no open high
  issue. The leg is `ready`.
