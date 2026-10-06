# Leg: windows-apparatus-core

**Status**: completed
**Flight**: [Window Chrome](../flight.md)

## Objective

Build the non-injecting half of the Windows test-copy helper,
`scripts/windows_test_copy.py`, and prove it on the operator's desktop. This half
records, snapshots, sets up, freezes, launches, observes and stops a test copy, with
every refusal of the flight's DD10, and sends no keyboard or mouse input. The leg also
answers spike premises 5, 6, 8, 10 and 12.

## Context

- **Flight DD10** is the contract: the act and observe paths, the safety rules, the
  session record and the snapshot. Read it in full first.
- **Flight DD11** splits verification. The spike premises are listed in the flight
  spec's Legs section.
- **Leg 1 was split at design review** (2026-10-06):
  - **1a (this leg)** sends no input.
  - **1b** (`windows-apparatus-input`) adds input, captures and the other eight premises.
  - 1b builds on this leg's helper unchanged, so everything here must be finished and
    documented when 1a lands.
- **The operator consented** (2026-10-06) to a test copy on their Windows desktop. Their
  installed `the-one-app.exe` runs on **port 8484 in session 1**, with data in their
  default Windows data dir (`C:\Users\cprch\AppData\Local\the-one` at planning; resolve
  it, never assume it). **Nothing in this leg may touch that process, that directory or
  the user or machine environment.**
- **The host, at planning:**
  - Windows 11 build 26200 (25H2), one 2560×1440 screen, 96 DPI;
  - `C:\Python311` (3.11.9, pip, `uv` at `C:\Python311\Scripts\uv.exe`) and Git for
    Windows;
  - `powershell.exe` from WSL runs in session 1;
  - WSL networking is mirrored. `ss` in WSL does not list Windows listeners, so the
    Windows-side port check is authoritative;
  - Concourse is unreachable, so the freeze is local.
- **Precedent:** `scripts/webkitgtk_probe.py`:
  - `FORBIDDEN_PORTS`, `check_safety()`, `default_data_dir()`, `ProbeError` (exit 2);
  - its unit tests in `tests/test_webkitgtk_probe_safety.py`, which import the script
    through `importlib`.
- **Session notices.** The Flight Director tells the operator in chat when this leg's
  Windows work starts and ends (before spawning and after `[LAND:leg]`). The Developer
  does not need to send one.
- **No product code changes.** Nothing under `the_one/` changes except
  `the_one/agents.md`. Spike prototypes are throwaway scripts in the Flight Director's
  scratchpad, never committed.

## Inputs

- Branch `flight/05-window-chrome`. The plan commit `debc7fa`, plus uncommitted flight
  artifacts (`flight.md`, `flight-log.md`, `legs/`), which the Flight Director owns.
- The flight spec, flight log and draft spec `tests/behavior/windows-window-chrome.md`.
- `ci/tasks/windows-installer-build.yml` (closure and freeze steps) and
  `packaging/windows/the-one.spec`.
- `scripts/webkitgtk_probe.py` and `tests/test_webkitgtk_probe_safety.py`.
- pywebview 5.4's source, read-only, at
  `/tmp/claude-1000/-home-cprch-projects-the-one/0eb14466-3200-4ca3-9529-5ff071966eae/scratchpad/pw/x54/webview/`.
  It is not in the repo `.venv`; the Windows test-copy venv gets it from the locked
  closure.

## Outputs

- **`scripts/windows_test_copy.py` (new).**
  - It is run from WSL: `.venv/bin/python scripts/windows_test_copy.py <command> …`.
  - It is importable on Linux: every `ctypes.windll` and `winreg` use is lazy.
  - The commands are in "The commands" below. 1b adds the input and capture commands.
- **`tests/test_windows_test_copy.py` (new).** Unit tests for the pure core, run on
  Linux in `make test-unit` with no Windows access.
- **`the_one/agents.md`.** A "Windows test copy (M25 F5)" block inside "UI test
  apparatus" covering this leg's commands, refusals, recipe and findings. 1b extends it.
- **`CLAUDE.md`.** One sentence in the "UI test apparatus" paragraph pointing to the
  helper and its refusals.
- **The flight log.** A Leg 1a entry with:
  - the premise findings for 5, 6, 8, 10 and 12;
  - every Windows session's snapshot result;
  - the setup and freeze times.
- **The scratch root** `C:\Users\cprch\AppData\Local\Temp\the-one-f5\`, left in place
  for legs 1b–4. It holds:
  - `src\` (the copied tree), `venv\` and `src\dist\` (the frozen build);
  - `pids\` (identity records and watchdog scripts), `audit.log`, `last-injection`
    (used by 1b), `data-*\` (scratch data dirs), `spike\` (spike scripts),
    `src-manifest.json` (the last synced file list), `logs\` (setup and freeze logs), and
    `cache\pip` and `cache\uv` (package caches);
  - `.the-one-f5-root` (a sentinel file).

## The commands (this leg)

**Shape.** One file, two halves:
- **The WSL-side CLI** validates and refuses (pure functions).
- **The Windows-side actions** run under a Windows interpreter: `ctypes` (stdlib), plus
  the scratch venv once it exists.
- **Before `setup`,** only `C:\Python311` exists, and nothing is ever installed into it.
- **How the Windows half runs.** It is this file's own source, piped on stdin to
  `C:\Python311\python.exe -` (stdlib only: `ctypes`, `winreg`, `json`, `subprocess`).
  - Arguments go in as JSON on stdin, and results come back as UTF-8 JSON on stdout.
  - This works before `R` or the venv exist, and avoids command-line length limits.
  - Start `python.exe` and any `powershell.exe` with a `/mnt/c/...` working directory,
    which avoids the UNC working-directory warning.
- **Calling PowerShell,** where needed: never build a quoted `-Command` string from
  arguments. Use `-EncodedCommand` (short commands only) or a script file under `R`, with
  UTF-8 output.
- **One source for process data.** Creation time, executable path, command line and
  parent PID come from one source, used for both the record and the check: one `ctypes`
  path (`OpenProcess` plus `GetProcessTimes` and `QueryFullProcessImageNameW`, with a
  Toolhelp snapshot for parents), or `Get-CimInstance Win32_Process` throughout. Never
  mix them, because creation times from two sources spuriously mismatch.
- **No other Windows calls.** No raw `powershell.exe` or `cmd.exe` call touches Windows
  outside the helper, except read-only probes.

| Command | Behaviour |
|---|---|
| `doctor-host` | Prints the session record as JSON: the build (registry `CurrentBuild` and `sys.getwindowsversion().platform_version`), the WebView2 runtime version, the DPI, `AppsUseLightTheme`, `SystemUsesLightTheme`, `DWM\ColorPrevalence`, `EnableTransparency`, user- and machine-level `WEBVIEW2_*` and `THE_ONE_*` variables, the networking mode (`wslinfo --networking-mode`), whether the session is locked (`OpenInputDesktop` returns null, or `LogonUI.exe` is running), Hyper-V excluded port ranges (`netsh int ipv4 show excludedportrange`), `LongPathsEnabled`, the WebView2 runtime directory (from the registry `pv` value and `EdgeWebView\Application\<version>`) and the operator's data dir (see "The operator's data dir"). |
| `snapshot --out F` / `snapshot --compare F` | Records and compares:<br>• **The installed app:** found as the owner of the port 8484 listener whose executable path is not under the scratch root and not in any recorded tree. Its PID, creation time and path are recorded; "not running" is classified, not an error.<br>• **The operator's data dir:** each of `api-credential`, `.env`, `window-chrome.json` and `window-state.json` (existence, mtime and sha256), plus the names of all its top-level entries.<br>• **The environment:** the user- and machine-level `WEBVIEW2_*` and `THE_ONE_*` variables.<br>`--compare` classifies changes: the two allowed ones in DD10 (geometry saved by the operator's own close or tray; a new installed-app PID after a restart) are reported. Any other change, a new top-level entry name or an environment change fails with exit 4. |
| `setup [--root R]` | See "Setup" below. |
| `freeze [--root R]` | Installs `pyinstaller` into the scratch venv (CI step 2, exit code checked). Then runs PyInstaller one-dir from `packaging/windows/the-one.spec` with working directory `R\src`, into `R\src\dist\the-one\`, with the scratch venv (never the base interpreter). Checks that `the-one.exe` and `the-one-app.exe` exist. It is timed, and logs to `R\logs\freeze.log`. **Never Inno or ISCC, never an installer.** |
| `doctor [--frozen] --data-dir D` | Runs `the-one doctor` (frozen `the-one.exe`, or the venv's `python -m the_one doctor`) with `THE_ONE_DATA_DIR=D` and the scrubbed environment, under the same data-dir and `.env` refusals as `launch`. Reports the exit code, the `RESULT:` line, the gate count and CI's four needles (`usearch: OK`, `fts5: OK`, `embedding model: OK`, `file watcher: OK`). |
| `launch --port P --data-dir D [--cdp-port C] [--frozen \| --script S] [--max-minutes M] [--tree-id T]` | See "Launch" below. `--script S` runs a spike script under `R\spike\` with the venv's `pythonw.exe`, through the same code path. |
| `tree` | The recorded trees: identity-checked live members, plus newly found descendants (persisted, see "Process identity"). |
| `windows` | Top-level windows owned by a recorded tree (HWND, title, rect, visible, whether in front). |
| `rect` | `GetWindowRect` and the client rect of the tree's **main window**: the largest visible window owned by the tree whose title is exactly "GleepGlorp AI" (the splash's title differs). `windows` lists both windows. |
| `stop [--tree-id T]` | See "Stop" below. With no `--tree-id` it stops every recorded tree. |

**Setup.**
- **The root.** `R` must be under `%LOCALAPPDATA%\Temp` with a leaf matching
  `the-one-f5*`, and must not equal, contain or sit inside the operator's data dir (a
  pure check). The default is `%LOCALAPPDATA%\Temp\the-one-f5`.
- **The sentinel.** The first run writes `R\.the-one-f5-root`. Every later write or
  delete requires the sentinel and stays within `R`, checked on the **resolved** target of
  each write and delete (the writes go through `/mnt/c`), not only on the lexical path.
- **The sync.**
  - Its delete pass deletes only files listed in the previous `R\src-manifest.json` that
    are no longer in the `git ls-files` list. It never touches `dist\`, `build\`,
    `*.egg-info` or `__pycache__`, so a re-run cannot wipe the frozen build or the
    editable install.
  - "Up to date" means equal size and mtime (or sha256). A second run copies only changed
    files.
  - Symlinks in the tree are skipped.
- **The copy.** The working tree goes into `R\src`: `git ls-files -co --exclude-standard
  --deduplicate`, filtered to files that exist (tracked-but-deleted files are skipped).
  The copy is timed. It must include the tracked embedding data under
  `the_one/embeddings/data/`.
- **The venv.** `R\venv` is created from `C:\Python311`, and `uv` is installed into the
  venv (`pip install uv`, as CI does; never into the base interpreter). The copied tree
  must include `uv.lock`. `PIP_CACHE_DIR` and `UV_CACHE_DIR` point under `R\cache\`, so no
  user-profile cache is written. The venv gets the CI closure verbatim, each step's exit
  code checked as CI does:
  - `uv export --no-dev --no-emit-project --extra gui --extra all-llms --format
    requirements-txt`, run on the Windows side, so markers resolve for Windows;
  - `pip install -r … --no-deps`;
  - `pip install -e . --no-deps`.
- **Re-running.** It re-syncs the tree and skips an up-to-date venv.
- **Long steps.** `setup` and `freeze` can exceed a 10-minute foreground command. Run
  them in the background, with progress streamed to `R\logs\`. The helper exits non-zero
  on any failed step. The root refusal ("a root outside `Temp`") is exercised through
  `setup --root`.
- **Network.** The closure install downloads the same wheels a CI build does, which is
  acceptable.

**Launch.**
- **Refusals** (pure, before anything starts):
  - ports, the data dir and `.env` (below);
  - the hands-off rule (below), because a launch can take the foreground.
- **A tree already exists.** `launch` refuses while a live recorded tree exists for the
  same tree id, or any live recorded tree when no id is given. Run `stop` first.
- **The environment.** The child gets `THE_ONE_PORT`, `THE_ONE_DATA_DIR` and, only with
  `--cdp-port`, `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=C`. Without
  `--cdp-port` that variable is not set at all, and an inherited value is not passed on.
  - Every other inherited `THE_ONE_*` and `WEBVIEW2_*` variable is removed from the
    child's environment.
  - The variables go through `subprocess` `env=`, or through
    `ProcessStartInfo.EnvironmentVariables`, or through `$env:` inside a child PowerShell
    process. Never through `[Environment]::SetEnvironmentVariable`.
- **Spike scripts** (`--script`) get the same refusals, scrub, records and watchdog. They
  must set pywebview's `storage_path` under their scratch data dir, so their WebView2
  profile is identifiable and the CDP variable applies. Any HTTP port a spike opens must
  pass the same port refusals.
- **The process.** The working directory is the scratch root, and there is no hidden
  window style. From source it runs the venv's `pythonw.exe -m the_one app`, with
  stdout and stderr redirected to `D\launch.log`; frozen, `the-one-app.exe`.
- **Recording.** The identity records are written (below). Then it waits for `/api/live`
  and checks `/api/info` with `D\api-credential` on port `P`, which proves it did not
  fall back to another port.
- **The watchdog.**
  - It is a script under `R\pids\`, run detached by the venv's `pythonw.exe` with the same
    scrubbed environment, and recorded in its own tree's file.
  - It sleeps for `--max-minutes` (30 by default), then runs the same identity-checked
    stop logic for its own tree id only.
  - `stop` kills it last, after the app tree.

**Stop.**
- **Each kill uses one handle.** `OpenProcess(PROCESS_TERMINATE |
  PROCESS_QUERY_LIMITED_INFORMATION)`, then re-read the creation time and path on that
  same handle and compare them with the record, then `TerminateProcess` on it. Check and
  kill can never race against a reused PID.
- A mismatch is refused and logged.
- **Never** `taskkill`, `taskkill /T`, `Stop-Process -Name` or `Get-Process |
  Stop-Process`. A `/T` kill takes unrecorded children.
- It kills the interpreter first (never the venv launcher alone), then other members.
- It waits until every recorded member has exited, including WebView2 processes recorded
  before their parent died, and until the app and CDP ports are free on the Windows side.
- The wait is bounded (30s by default) and reports a timeout.
- It appends every kill to `R\audit.log` and clears the records and the watchdog.
- **It never kills by name.**

**Process identity.**
- Every recorded process is stored as `(pid, creation_time, executable path)` in
  `R\pids\<tree-id>.json`.
- **When records are written:** at launch, on every `tree` call and just before a kill.
- **What `tree` adds:**
  - live descendants by parent link. A process counts as a child only if its creation
    time is at or after its parent's, so a reused parent PID cannot adopt unrelated
    processes;
  - processes whose command line contains `--user-data-dir=` pointing inside this
    tree's scratch data dir. This is how WebView2 processes are found once their parent
    has died; it is not "by name".
- **Before any kill,** the live process's creation time and path must match the record,
  and the path must be under the scratch root, under `C:\Python311` (the venv's base
  interpreter), or the WebView2 runtime directory. Otherwise it is refused.
- These rules are pure functions over a process table, with unit tests.

**The operator's data dir.**
- Before the venv exists: `%LOCALAPPDATA%\the-one`, which is what
  `platformdirs.user_data_dir("the-one", appauthor=False)` yields. The cross-check is
  marked `pending`.
- After `setup`: resolved through `platformdirs` in the venv, and cross-checked against
  that value. Any mismatch stops the helper.

**Refusals** (exit 2 with a message naming the rule; the hands-off timeout exits 3; a
failed snapshot compare exits 4):
- **Ports.**
  - Refused: any port in {8484, 8485}; any port below 8490 for `--port`, or below 9390
    for `--cdp-port`; any port in a Hyper-V excluded range.
  - Refused: any port with a listener on the Windows side (`Get-NetTCPConnection`, the
    authoritative check) or the WSL side (`ss`, a supplement).
- **Paths.** Normalise lexically first, then resolve the longest existing ancestor on
  the Windows side (`realpath` or `GetFinalPathNameByHandle`), so junctions, symlinks and
  8.3 names cannot hide a match. Then:
  - refuse a data dir or root equal to, inside or containing the operator's data dir,
    compared by path components, case-insensitively;
  - refuse a data dir outside the scratch root.

  The lexical forms covered: `C:\…` and `/mnt/c/…`, `\\?\` prefixes, `\\wsl.localhost\…`,
  `..` segments, trailing dots and spaces, relative paths, mixed separators and case.
- **`.env`.** Refuse a frozen `launch` or `doctor` while the operator's data dir holds a
  `.env`.
- **Hands-off.** Refuse any command that can take the foreground or show a window (in
  this leg: `launch` and a frozen `doctor`) while operator input is recent.
  - "Recent" means `GetLastInputInfo` is newer than the helper's own last injection
    (persisted in `R\last-injection`; 1b writes it) and within the last 5 seconds.
  - The rule is a pure function over `(last_input_tick, last_injection_tick, now)` and
    handles 32-bit tick wraparound.
    - A missing or unreadable `R\last-injection` means no injection (None). In 1a,
      nothing writes it, so the 5-second rule is the only gate.
    - `now` (`GetTickCount`) and `last_input_tick` (`GetLastInputInfo`) are read in the
      same Windows process, in one call.
  - It waits up to 60s, then exits 3.
- **Stopping.** Refuse any process whose identity does not match its record.
- **The environment.** A unit test greps the helper source. The patterns live only in
  the test file, so the guard never matches the helper's own constants. It must find
  none of:
  - `setx`;
  - `[Environment]::SetEnvironmentVariable`;
  - `reg add`, `reg delete`, `reg import`;
  - `Set-ItemProperty`, `New-ItemProperty`, `Remove-ItemProperty`;
  - `winreg.SetValue`, `winreg.CreateKey`, `winreg.DeleteValue`, `winreg.DeleteKey`;
  - any write to `HKCU:` or `HKLM:`.

## Acceptance Criteria

- [ ] **Unit tests.** `tests/test_windows_test_copy.py` covers, with pure-function tests
  that make no Windows calls:
  - **Ports:** 8484, 8485, 8489 and 9389 refused, 8490 and 9390 accepted when free, an
    excluded range refused, a busy port refused.
  - **Paths:** containment for every lexical form listed under Refusals, plus a
    sibling-prefix case (`…\Temp\the-one-f5` against `…\Local\the-one`), allowed inside
    the root.
  - **Root validation:** a valid root, a root outside `Temp`, the wrong leaf, the
    operator's data dir and an ancestor of it.
  - **Process identity:**
    - a launcher → interpreter → `msedgewebview2` fixture (process tables are plain dicts,
      so the pure core never imports `ctypes`);
    - a reused parent PID, where a child created before its recorded parent is not
      adopted;
    - the parent gone, so WebView2 is found by user data folder;
    - a reused PID refused;
    - a same-named `the-one-app.exe` outside the root never selected.
  - **The installed app:** identified from a process table with two same-named processes,
    and "not running" classified.
  - **The snapshot diff:** unchanged, both allowed exceptions, a changed credential, a new
    top-level entry, an environment change.
  - **The hands-off rule:** the helper's own injection ignored, recent operator input,
    tick wraparound, and a missing `last-injection` file.
  - **The setup sync:** the delete pass spares `dist\`, `build\`, `*.egg-info` and
    `__pycache__`, and deletes only files from the previous manifest.
  - **The environment guard:** the source grep.
- [ ] **On this host, bracketed by a snapshot:**
  - `doctor-host` prints the session record;
  - `setup` builds a from-source copy, and a second `setup` run is quick; both times
    recorded;
  - refusals exit 2 with nothing started: `launch` on port 8484, `launch` with the
    operator's data dir, and `setup --root` outside `Temp`;
  - `launch --port 8490 --cdp-port 9390` with a fresh `R\data-l1a` starts the copy, and
    `/api/info` with the scratch credential answers 200 on 8490;
  - `tree`, `windows` and `rect` list its processes, windows and rects;
  - `stop` clears the whole tree, including WebView2, and frees both ports within its
    wait;
  - `audit.log` lists each kill;
  - the comparison is clean, or shows only an allowed change.
- [ ] **Frozen**, bracketed by a snapshot:
  - `freeze` produces `the-one.exe` and `the-one-app.exe`, with the time recorded;
  - `doctor --frozen --data-dir R\data-l1a-doctor` exits 0, prints a `RESULT: PASS`
    line and all four CI needles, and its gate count is recorded (CLAUDE.md says nine);
  - a frozen `launch` and `stop` run cleanly.

  If the freeze fails or takes over about 20 minutes, the cause and time are recorded,
  and the flight's "No local freeze" variation applies. Record it; don't block on it.
- [ ] **The watchdog** stops a tree launched with `--max-minutes 1` on its own. Its kill
  is in `audit.log`.
- [ ] **Premises answered** in the flight log, each with method, observed values,
  verdict and its consequence for legs 2–3:
  - **5:** `window.chrome.webview` at document start; `window.pywebview` and
    `pywebviewready` on the main window of a two-window (splash plus main) spike, read
    over CDP or recorded by the page.
  - **6:** outer versus client rect, and `innerWidth`/`innerHeight`, at 100%.
  - **8:** reading `Handle` off the UI thread, and whether the HWND changes across
    `hidden=True` then `show()`. This reads handles only; colours wait for 1b.
  - **10:** CDP through `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` on the real copy.
  - **12:** the freeze time.

  Spike scripts live in the scratchpad's `f5-spike/` folder and run under the helper's
  records, refusals and snapshot bracket.
- [ ] **The operator's installation is untouched.** Every Windows session's snapshot
  comparison is recorded in the flight log, and every kill is in `audit.log`.
- [ ] **Docs.** The `agents.md` block, covering commands, refusals, process identity, the
  recipe and findings, and the `CLAUDE.md` sentence.
- [ ] **Gates.**
  - `ruff check` and `ruff format --check` pass on `scripts/` and `tests/`. Win32
    structure fields may carry `# noqa: N815`.
  - `make test-unit` passes.
  - Apart from the flight artifacts the Flight Director owns (`flight.md`, the flight log
    and `legs/`), `git status` shows changes only in:
    - `scripts/windows_test_copy.py`, `tests/test_windows_test_copy.py`;
    - `the_one/agents.md`, `CLAUDE.md`.

## Verification Steps

- **Unit tests:** `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_windows_test_copy.py -x --timeout 30`, then `make test-unit`.
- **Lint:** `.venv/bin/ruff check scripts/ tests/` and `.venv/bin/ruff format --check
  scripts/ tests/`.
- **The session:**
  1. `snapshot --out`;
  2. `doctor-host`;
  3. `setup`, run twice;
  4. the three refused launches;
  5. `launch`;
  6. `curl` `/api/live`, and `/api/info` with the credential;
  7. `tree`, `windows`, `rect`;
  8. `stop`;
  9. the ports free on Windows;
  10. `snapshot --compare`.
- **Frozen:** `snapshot --out`, `freeze`, `doctor --frozen`, a frozen `launch` and
  `stop`, `snapshot --compare`.
- **Watchdog:** `launch --max-minutes 1`, wait about 90s, `tree` (empty), `audit.log`.
- **Premises:** each row names its spike script or commands and the observed values.

## Implementation Guidance

1. **Read first.** Read the flight's DD10, DD11 and spike premises, the draft spec's
   Preconditions, the probe precedent and the CI task's steps 1–4. Then confirm the
   starting state:
   - nothing listening on 8490–8499 or 9390–9399 on the Windows side;
   - the operator's session unlocked.
2. **The pure core and its tests, before any Windows call.** That is ports, paths and
   root, process identity, installed-app identification, the snapshot diff, the
   hands-off rule and the environment guard.
3. **The Windows-side layer.** `-EncodedCommand` or script files under `R`, UTF-8 output,
   lazy `ctypes`.
4. **Commands, in this order:** `snapshot`, `doctor-host`, `setup`, `launch`, `tree`,
   `windows`, `rect`, `stop`, the watchdog. Exercise each on the host as it lands, with
   the session bracketed by a snapshot.
5. **The frozen build.** `freeze`, then `doctor --frozen`, then a frozen launch and stop.
   Record anything PyInstaller needed beyond the CI steps. Do not modify `packaging/`.
6. **The spike for premises 5, 6, 8 and 10.**
   - Write throwaway scripts in
     `/tmp/claude-1000/-home-cprch-projects-the-one/0eb14466-3200-4ca3-9529-5ff071966eae/scratchpad/f5-spike/`.
   - Copy them into `R\spike\` and run them with the venv's Python. Premise 5 uses a
     two-window pywebview spike with a tiny local HTTP page on a port of 8490 or higher.
   - Launch spike windows through the helper's records and refusals, or record their PIDs
     in the same identity format, so `stop` can clear them.
   - Read over CDP from WSL with the repo `.venv`'s Playwright (`connect_over_cdp` to
     `http://127.0.0.1:<cdp-port>`), on loopback only, for premises 5, 6 and 10.
   - Send no input in this leg, and paint no DWM colours (that is 1b).
7. **Record:** the flight-log Leg 1a entry, the `agents.md` block and the `CLAUDE.md`
   sentence.
8. **Finish:** run the gates, mark the leg `landed`, and signal `[LAND:leg]`.

## Edge Cases

- **A locked session.** `doctor-host` reports it. A launch is still allowed, but nothing
  is judged from it. Report `[BLOCKED:session-locked]` if the premises need the
  desktop. Never lock or unlock the session.
- **The operator is typing.** The launch waits, then exits 3. Report it.
- **A port is taken, or in an excluded range.** Take the next free port in 8490–8499 or
  9390–9399 and record it.
- **Storage Sense purged the root.** `launch` reports a missing venv or dist and says to
  re-run `setup`. The sentinel check also fails cleanly.
- **A leftover tree** from a crashed session. `stop` reads `R\pids\` and identity-checks
  each member before killing it.
- **WebView2 lingers.** `stop` waits for it, finding it by its recorded identity or its
  user data folder. On timeout it reports, and never kills by name.
- **The installed app restarts or is closed** mid-session. The snapshot classifies it.
- **The freeze fails** for an environment reason. Record it and continue under "No local
  freeze".
- **The WebView2 runtime auto-updates.** `doctor-host` records the version each session.
- **The installed app creates a new top-level entry** mid-session (for example a new
  log). `snapshot --compare` exits 4, as intended. Report it, and do not widen the
  allow-list; the Flight Director judges it.
- **Long paths.** If a deep path under `Temp` fails and `LongPathsEnabled` is off, record
  it and shorten the root (e.g. `…\Temp\the-one-f5`), rather than changing the setting.
- **Known limit, for the `agents.md` block:** the snapshot does not cover registry writes
  by WebView2 or the app (for example `HKCU\Software\Microsoft\Edge\BLBeacon`).

## Files Affected

- `scripts/windows_test_copy.py`: new.
- `tests/test_windows_test_copy.py`: new.
- `the_one/agents.md`: the "Windows test copy" block under "UI test apparatus".
- `CLAUDE.md`: one sentence in "UI test apparatus".
- `missions/25-workbench-navigation/flights/05-window-chrome/flight-log.md`: the Leg 1a
  entry.
- This leg file: status transitions.

## Citation Audit

Checked on 2026-10-06 against `debc7fa`:
- **`scripts/webkitgtk_probe.py`:** `FORBIDDEN_PORTS` (lines 53–56), `default_data_dir`
  (line 64), `check_safety` (line 91).
- **`tests/test_webkitgtk_probe_safety.py`:** present.
- **`ci/tasks/windows-installer-build.yml`:**
  - the toolchain and `.buildvenv` (lines 20–44);
  - the closure (lines 65–90);
  - the freeze (lines 92–96);
  - the doctor needles (line 113).
- **`the_one/interfaces/desktop/shell.py`:** `storage_dir = settings.data_dir /
  "webview"` (line 741), passed as `storage_path` (line 746), so the WebView2 profile
  sits under the scratch data dir.
- **`the_one/agents.md`:** "UI test apparatus (M25 F1 L1)" (line 1818).
- **`pyproject.toml`:** the `gui` extra (lines 111–114).

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
