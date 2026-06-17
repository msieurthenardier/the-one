# Flight Log: Windows install docs & mission closeout

**Flight**: [Windows install docs & mission closeout](flight.md)

## Summary

Planning. Mission-15 closeout flight, **re-scoped from the roadmap's "Flight 9: Windows first-run
UX, docs & acceptance"** to a **documentation-only** flight (operator decision, 2026-06-17). The
comprehensive installer HAT is already satisfied (operator installed the F8 MinIO artifact and
confirmed it works); no new first-run UX is built; the two carry-forward edge-case Known Issues are
left as accepted Known Issues (DD1). What remains: an end-user Windows install/SmartScreen guide,
removal of the last stale Docker-era operator messages, and a final reference-doc pass. After this
flight lands + debriefs, the mission can be closed via `/mission-debrief`.

---

## Planning Notes

**2026-06-17 — scope settled with the operator.** Original roadmap F9 bundled first-run UX + docs +
a comprehensive acceptance HAT. Narrowed to docs-only after two operator signals: (1) "we're ok on
the HAT" (installer already validated, F8); (2) on review, the operator had **never witnessed**
either carry-forward Known Issue — confirming they are test/HAT-discovered edge cases, not
normal-use defects. Chose **Option A (document-only closeout)** over Option B (also fix the two
issues): lower regression risk in a wrap-up flight, and the edge cases ride into the mission debrief
as maintenance candidates.

**Deferred Known Issues (NOT fixed in F9 — carried to the mission debrief / maintenance):**
- **Single-instance silent-exit when a headless `serve` holds the port** (F6 L6 HAT). The desktop
  app POSTs `/api/window/focus` (`shell.py:488-496`), ignores the `{"focused": false}` response when
  there's no window to raise, and exits with no UI/message. Only triggers if a headless `the-one
  serve` was started first — never seen in normal double-click use.
- **`run_shell` non-prompt child-tree kill on Windows** (F3 L4 CI). The shell timeout fires and
  reports correctly, but a spawned `cmd.exe`'s children aren't tree-killed on Windows (no
  `taskkill /F /T` / Job Object); the prompt-kill test is POSIX-gated
  (`tests/test_execution_tools.py:103`). A leftover background process after a *timed-out* command;
  no correctness impact, Windows already ships best-effort/unsandboxed.

**Docker-era messaging found (in scope per DD2 — messaging accuracy, no behavior change):**
- `the_one/mcp/transports/stdio.py:199-200` — sandbox-setup error advises `cap_add: SYS_ADMIN` +
  `security_opt: seccomp:unconfined` (Docker-compose-era; wrong post-F1 host-native).
- `the_one/mcp/cache_cleanup.py:37,293` — comments referencing `docker compose logs the-one`.
- `the_one/tools/filesystem.py:40` — `~/.docker/config.json` denylist entry is **legitimate**
  (protects Docker creds if present); leave it.

---

**2026-06-17 — Architect design review (Opus, 1 cycle): approve with changes.** All cited code
locations verified accurate; the two deferred Known Issues correctly characterized; deferring them
judged sound for a closeout. Changes incorporated (accuracy/completeness — no scope re-expansion):
- **[high]** DD2 was incomplete + the "grep returns one hit" end-state is unachievable (the tree
  legitimately retains many Docker refs). Reframed: added the *second* `stdio.py` SandboxError
  message (~189-194), `api.py:3798` `host.docker.internal`, and the `config.py:20`
  `%APPDATA%`→`%LOCALAPPDATA%` docstring bug; added **DD2b** (grep is a triage, not a zero-hit gate).
- **[high]** Named the test files the messaging leg must grep before editing
  (`test_mcp_sandbox_integration.py`, `test_mcp_stdio_sandbox.py`, `test_sandbox_bubblewrap.py`).
- **[med]** Install guide must capture the **two-exe reality** (`the-one-app.exe` windowed shortcut
  vs `the-one.exe` CLI at `{app}`, no shortcut) and the correct data path `%LOCALAPPDATA%\the-one`.
- **[low]** Added the data-preservation/`~/.the-one`-migration criterion as a documented line +
  mission-debrief disposition; added **DD5** (README demotes the retired Docker end-user/production
  path; dev/historical Docker context retained).
- Folded suggestions: `docs/windows-install.md` location confirmed (open question resolved); point
  users at `the-one.exe doctor`; annotated the mission roadmap Flight 9 entry with the re-scope.
Fixes were reviewer-validated additions; flight remains 2 docs legs → **2nd review cycle skipped**
(within the 2-cycle cap).

**2026-06-17 — operator approved (Phase 6).** Confirmed both judgment calls: (1) DD2's messaging
edits to `.py` strings are in scope (messaging accuracy, not behavior); (2) DD5 — demote the README
Docker production path to a retired-path note. Flight → `ready`; executing via `/agentic-workflow`.

## Decisions
_See flight.md Design Decisions (DD1–DD5). Runtime decisions recorded here during execution._

---

## Flight Director Notes

**2026-06-17 — Flight Director engaged (`/agentic-workflow` flight 9).** Crew file
`leg-execution.md` already validated this session (F8). Flight `ready` → `in-flight`; branch
`flight/9-windows-install-docs-closeout` created off `main` (carries the F9 planning artifacts +
the mission.md roadmap annotation). 2 autonomous docs legs; batched review+commit at flight end.
Both legs are documentation/messaging (no app-behavior changes per DD1) — the crew "Implement"
prompt's `docker exec` test guidance is moot here (Leg 2 runs the host-native suite only to confirm
message-string/test-assertion edits stay green).

### windows-install-guide (Leg 1 — design, 2026-06-17)

Authored `legs/01-windows-install-guide.md`. Developer design review (Sonnet, 1 cycle):
approve-with-changes — all factual. Fixes incorporated (accuracy):
- **[high]** CLI command list: `the-one.exe` CLI is `chat|serve|version|doctor`; `app` exists via
  CLI but opens a console — the **shortcut** (`the-one-app.exe`, which hard-forces `app` per
  `frozen_entry_gui.py:31`) is the normal window launch. Reworded AC + Context.
- **[high]** `packaging/windows/README.md` "Output" section + its "shortcut invokes `the-one.exe app`"
  note are **stale (pre-F5 single-exe model)**. Added a WARNING in the leg's guidance not to copy it;
  **CARRY-ITEM for Leg 2 design**: fix that stale dev-README Output/shortcut description as part of
  the doc-accuracy sweep (DD5 — it's a now-misleading dev doc).
- **[med]** Tray menu has **Show** (default) + **Quit**; guide must mention Show restores the window.
- **[low]** Install triggers a **UAC admin prompt** (`PrivilegesRequired=admin` + `{autopf}`); optional
  desktop-shortcut checkbox (`[Tasks] desktopicon`). Added to the install step.
- Folded: quote the shipped first-run notice string; Focus-Assist toast-suppression troubleshooting line.
Corrections only (no reshaping) → 2nd design-review cycle skipped. Leg 1 → `ready`.

### messaging-and-doc-accuracy (Leg 2 — design, 2026-06-17)

Authored `legs/02-messaging-and-doc-accuracy.md`. FD grounded the key risk directly (no separate
design-review spawn — the flight-level Architect already validated DD2/DD2b/DD5 + sites): grepped
the tests for the stale message substrings. **Finding:** `test_mcp_sandbox_integration.py:505`
asserts `"bubblewrap exited non-zero"` and `:545` asserts `"namespace creation refused"` — the
stdio.py message **prefixes**. So the rewording must **preserve those prefixes and replace only the
Docker-prescriptive remediation tail** (`cap_add: SYS_ADMIN`/`seccomp`/§10) — protects the tests AND
is the right approach (keep the diagnosis, drop the stale advice). Added that as a CRITICAL guidance
note. Also classified `HAT.md` / `pty-session-containment.md` / `host.docker.internal` live-test
fixtures as **test-historical, out of scope** (pass the DD2b bar; flag HAT/behavior-spec staleness as
a maintenance candidate, don't rewrite in this closeout). Leg 2 → `ready`.

## Deviations
_None yet._

---

## Anomalies
_None yet._

---

## Leg Progress

### windows-install-guide (Leg 1 — implementation, 2026-06-17)

**Files written:**
- `docs/windows-install.md` — new end-user install guide (sections: Download → SmartScreen passthrough → Install → First launch → Close-to-tray → CLI → Troubleshooting/advanced)
- `README.md` — added one-line Windows install link in the Desktop window subsection of Quickstart

**Source files verified for key claims:**
- `packaging/windows/the-one.iss` — AppName "GleepGlorp AI", install dir `{autopf}\GleepGlorp AI` → `C:\Program Files\GleepGlorp AI\`, `[Icons]` block (Start-menu shortcut → `the-one-app.exe`; no shortcut for `the-one.exe` CLI), `[Tasks] desktopicon` (optional desktop shortcut checkbox), `PrivilegesRequired=admin` (UAC prompt), uninstall via Inno default.
- `the_one/main.py` — CLI commands: `chat | serve | app | version | doctor`; `app` exists as a CLI subcommand but the shortcut is `the-one-app.exe` (two-exe model).
- `the_one/config.py` — `platformdirs.user_data_dir("the-one", appauthor=False)` → `%LOCALAPPDATA%\the-one` on Windows (docstring at line 20 incorrectly says `%APPDATA%` — NOT copied; fixed in Leg 2). `_maybe_migrate_legacy` migrates `~/.the-one` automatically.
- `the_one/interfaces/desktop/shell.py` — first-run tray notice quoted verbatim from `_close_to_tray` (lines 383–386): "GleepGlorp AI is still running in the system tray — Quit from the tray menu to exit".
- `the_one/interfaces/desktop/tray.py` — tray menu: `Show` (default) + `Quit`.
- `packaging/windows/README.md` — SmartScreen wording reused; stale "Output" section / "shortcut invokes `the-one.exe app`" prose NOT copied (pre-F5 single-exe model, flagged in leg design review).

### messaging-and-doc-accuracy (Leg 2 — implementation, 2026-06-17)

**Files changed (messaging/comment/docstring/markdown only — no logic changes):**
- `the_one/mcp/transports/stdio.py` — rewrote both stale `SandboxError` messages (catalog #2 and #3) to host-native diagnostics. Preserved asserted prefixes (`"bubblewrap exited non-zero"`, `"namespace creation refused"`) verbatim; replaced Docker-prescriptive remediation tail (`cap_add: SYS_ADMIN`, `seccomp:unconfined`, `§10` references) with host-native advice (bubblewrap install + unprivileged user namespaces, mirroring factory.py passthrough WARNINGs).
- `the_one/mcp/cache_cleanup.py` — rewrote two comments: (a) module docstring `"docker compose logs the-one"` → `"the host-native uvicorn log output"`; (b) `cleanup_runtime_cache` docstring same. Also updated `/root/.cache/uv/` → `~/.cache/uv/` and "in this container" → dropped.
- `the_one/interfaces/web/api.py:3798` — updated `host.docker.internal:11434` example → `localhost:11434` with a "LAN hostname / IP address" note (comment-only; no logic change to the skip-validation frozenset).
- `the_one/config.py:20` — fixed `_default_data_dir` docstring: `%APPDATA%\the-one` → `%LOCALAPPDATA%\the-one` (matches `platformdirs.user_data_dir(appauthor=False)` actual output).
- `packaging/windows/README.md` — rewrote stale "Output" section: replaced single-exe description with the accurate two-exe model (`the-one.exe` CLI, no shortcut; `the-one-app.exe` windowed launcher, Start-menu shortcut), citing `the-one.iss [Icons]` + `the-one.spec` (two EXE entries).
- `README.md` — DD5 Docker-path demotion: added "Windows installer" (end-user path, links `docs/windows-install.md`) as the lead option; demoted Docker block to `> **Docker (retired — M15 F1):**` blockquote annotation; updated intro line.
- `CLAUDE.md` / `SECURITY-MODEL.md` — reviewed; no changes needed. All Docker references are accurate historical/dev context (no current-setup operator prescription).
- No test-assertion updates needed: `test_mcp_stdio_sandbox.py` and `test_sandbox_bubblewrap.py` had no stale string assertions; `test_mcp_sandbox_integration.py:505,545` asserts the preserved prefixes only — both pass.

**Suite result:** 3178 passed, 10 skipped, 589 deselected — all green (host-native, 316s).

**Docker-grep triage** (`grep -rniE "docker|docker compose|seccomp|SYS_ADMIN|host.docker.internal" the_one/ README.md CLAUDE.md SECURITY-MODEL.md packaging/windows/README.md`):

| Hit | File / Location | Disposition |
|-----|-----------------|-------------|
| `~/.docker/config.json` | `the_one/tools/filesystem.py:40` | **legitimate-creds** — denylist protects real Docker creds if present; leave it |
| `docker exec`, `docker logs`, `docker run ...` | `the_one/agents.md:116,138,140,594,953,1323` | **historical-dev** — dev-workflow / dev-container invocation patterns; not operator instructions |
| `SYS_ADMIN`, `seccomp:unconfined` | `the_one/agents.md:704` | **historical-dev** — dev-container privilege model; accurate F3 design history |
| `THE_ONE_TEST_MODE … Dockerfile, compose` | `the_one/agents.md:706`, `the_one/mcp/README.md:345-346` | **historical-dev** — security guardrail against test-mode leaking to prod; retain |
| "non-Docker", "Mission 15 retired Docker" | `the_one/platform/interpreter.py:52,65,95` | **historical/accurate** — describes what was retired; not prescriptive |
| legacy env var from `docker-compose.yml` | `the_one/interfaces/web/app.py:205` | **historical-dev** — accurate context note |
| Playwright Docker image in stdio.py comment | `the_one/mcp/transports/stdio.py:94` | **historical-dev** — CI note, not operator instruction |
| `Local dev with Docker` section | `CLAUDE.md:42-69` | **historical-dev** — developer contributor docs; describes Docker dev path accurately; not end-user/operator setup |
| "host-native — no Docker" | `CLAUDE.md:174` | **accurate** — states Docker was retired |
| `docker-compose.yml` overrides to `0.0.0.0` | `SECURITY-MODEL.md:41-43` | **historical/accurate** — explains why the dev form factor uses `0.0.0.0`; accurate design context |
| "No secrets in Dockerfile, docker-compose.yml" | `SECURITY-MODEL.md:261-262` | **accurate security policy** — retain |
| `Docker (retired — M15 F1)` | `README.md:55,57` | **retired-annotated** — just added; the demotion note |

**Verdict:** No hit prescribes Docker to an end-user/operator as current runtime setup. DD2b satisfied.

**Deferred Known Issues (accepted/maintenance-bound — DD1):**
- **(a) Single-instance no-window-serve silent exit** (`shell.py:488-496`, F6 HAT): when a headless `the-one serve` holds the port, the desktop app POSTs `/api/window/focus`, receives `{"focused": false}`, and exits with no UI message. Only triggers with a pre-existing headless serve; not observed in normal double-click use. Accepted as maintenance-bound; will surface in mission debrief.
- **(b) `run_shell` Windows tree-kill** (`test_execution_tools.py:103`, F3 POSIX-gated): shell timeout fires and reports correctly, but child tree on Windows is not killed (no `taskkill /F /T` / Job Object on the non-PTY path). POSIX-gated test; no correctness impact. Accepted as maintenance-bound; will surface in mission debrief.

**Maintenance candidate (noted, not fixed):** `tests/HAT.md` `docker compose logs` steps and `tests/behavior/pty-session-containment.md` "under Docker: cap_add SYS_ADMIN" precondition note are test-historical / dev-context; they pass the DD2b bar but are stale. Flagged as a maintenance candidate for a future test-doc cleanup pass.

---

## Flight Review & Landing (2026-06-17)

**Phase 2d — single flight review (Sonnet, fresh context): `[HANDOFF:confirmed]`.** No issues.
The reviewer independently verified the install guide claim-by-claim against `the-one.iss` /
`main.py` / `config.py` / `desktop/` (SmartScreen, UAC, install dir, two-exe model, close-to-tray
incl. the verbatim first-run notice, `%LOCALAPPDATA%` data path + migration, doctor, uninstall — no
factual errors); confirmed Leg 2 is messaging/comment/docstring/markdown only with **no logic
change** and the test-asserted prefixes (`bubblewrap exited non-zero`, `namespace creation refused`)
preserved; re-ran the DD2b grep and concurred no surviving hit prescribes Docker to an
end-user/operator as current runtime setup (incl. the `agents.md:704` privilege-model entry =
acceptable dev/historical context); confirmed the two deferred Known Issues are recorded; and ran
the host-native suite green (**3178 passed, 10 skipped**).

**Landing.** Both legs → `completed`; flight → `landed`; Flight 9 checked off in `mission.md`.
flight.md checklist fully checked except "Code merged" (the PR merge). After this lands + the
debrief, the mission closes via `/mission-debrief` — carrying the two deferred Known Issues + the
HAT.md/behavior-spec test-doc-staleness maintenance candidate. **`[COMPLETE:flight]`**

---

## Session Notes
_Chronological notes added during execution._
