# Flight: Windows install docs & mission closeout

**Status**: landed
**Mission**: [Native Desktop Installers](../../mission.md)

> **Re-scoped from the mission roadmap's "Flight 9: Windows first-run UX, docs & acceptance"
> (operator decision, 2026-06-17).** The roadmap entry bundled three things: (1) new first-run
> *UX* work, (2) install/unsigned-app docs, and (3) a comprehensive operator HAT against the real
> installer. During planning the operator narrowed F9 to a **documentation-only closeout**:
> - The **comprehensive HAT is satisfied** — the operator already installed the real artifact from
>   MinIO (F8) and confirmed it works. No formal HAT leg.
> - **No new first-run UX is built**, and the **two carry-forward edge-case Known Issues are NOT
>   fixed here** (see DD1) — they were never witnessed in normal use, are test-discovered edge
>   cases, and stay as accepted Known Issues carried to the mission debrief / a maintenance pass.
> - What remains, and what this flight does, is **documentation + messaging accuracy**: an
>   end-user Windows install/first-run/SmartScreen guide, replacing the last stale Docker-era
>   runtime messages, and a final reference-doc pass. After F9 lands + debriefs, the mission can be
>   closed via `/mission-debrief`.

## Contributing to Criteria
- [x] Installation and first-run steps — **including how to get past the unsigned-app SmartScreen
      warning** — are documented (Windows). *(primary deliverable)*
- [x] When a required external runtime for MCP servers is absent, the app presents actionable,
      **non-Docker** guidance. *(advanced: this flight removes the last stale Docker-flavored
      operator messages so no Docker-era guidance remains)*
- [x] The installed deliverable includes a working **command-line interface** alongside the
      windowed app. *(documented: the install guide covers `the-one.exe` under the install dir)*
- [x] Data + secrets stored per-user and **preserved across restarts**; existing `~/.the-one`
      migrated. *(behavior already shipped F1; F9 documents the `%LOCALAPPDATA%\the-one` location +
      migration in the install guide — the behavior itself is a mission-debrief disposition, not an
      F9 build item)*

---

## Pre-Flight

### Objective

Close out Mission 15 (Windows-only) with documentation, not code. Author an **end-user Windows
install + first-run + SmartScreen-workaround guide**; replace the remaining **Docker-flavored
runtime messages/comments** (host-native-accurate text); and do a final **README / CLAUDE.md /
SECURITY-MODEL.md** pass so the project docs reflect the shipped state (native Windows desktop app,
host-native runtime, Concourse CI). No behavior changes to the app's launch or execution paths.

### Open Questions
- [x] Where the end-user install guide lives → **`docs/windows-install.md`**, linked from the
      README Quickstart. `docs/` already exists (`docs/kb-architecture.md`, `docs/screenshots/`)
      and the README links into it, so this fits the convention; a top-level `INSTALL.md` would be
      a new convention.
- [x] Are the two carry-forward Known Issues (F6 single-instance no-window-`serve`; F3 `run_shell`
      Windows tree-kill) in scope? → **No** (DD1) — accepted Known Issues, deferred to maintenance.
- [x] Is a formal acceptance HAT needed? → **No** — the operator already validated the real
      installer (F8). The existing F6/F7 GUI behavior-test specs remain the re-runnable regression net.

### Design Decisions

**DD1 — Document-only closeout; carry-forward edge cases are NOT fixed here.**
- Choice: Flight 9 changes no app behavior. The two deferred Windows Known Issues — the
  single-instance silent-exit when a headless `serve` holds the port (F6), and the non-prompt
  `run_shell` child-tree kill on Windows (F3) — are **left as accepted Known Issues** and recorded
  for the mission debrief as maintenance candidates.
- Rationale: neither was ever witnessed in normal use; both are test/HAT-discovered edge cases
  (the single-instance case needs a manually-started headless `serve`; the tree-kill leftover only
  appears after a *timed-out* command on Windows and affects no correctness). A closeout flight
  should not risk regressions in the launch / shell-timeout paths to fix unwitnessed edges.
- Trade-off: the mission closes with two known limitations open. Accepted (operator decision
  2026-06-17); they travel into the mission debrief and a future maintenance pass.

**DD2 — Docker-flavored *operator-facing messaging* accuracy is in scope (messaging, not behavior).**
- Choice: replace the stale **operator-facing** Docker-era runtime text with host-native-accurate
  wording. Confirmed targets:
  - `the_one/mcp/transports/stdio.py` — **two** `SandboxError` messages: lines ~189-194 ("namespace
    creation refused … privilege grants required by §10") and ~197-201 ("cap_add: SYS_ADMIN AND
    security_opt: seccomp:unconfined per F3 design decision §10"). Both reference Docker-compose
    privilege config retired in F1; "§10" is meaningless to an operator.
  - `the_one/mcp/cache_cleanup.py:37,293` — comments referencing `docker compose logs the-one`.
  - `the_one/interfaces/web/api.py:3798` — operator-facing `host.docker.internal` reference.
  - `the_one/config.py:20` — docstring claims Windows data dir is `%APPDATA%\the-one`, but
    `platformdirs.user_data_dir("the-one", appauthor=False)` (roaming=False) resolves to
    **`%LOCALAPPDATA%\the-one`**. Wrong-path doc bug; fix here (the install guide depends on the
    correct path — see DD3).
  - **Leave** the legitimate `~/.docker/config.json` denylist entry in `filesystem.py` (protects
    real Docker creds if present; not Docker-era guidance).
- Rationale: explicit mission criterion ("replacing the remaining Docker-flavored runtime error
  messages"). Shipping "mission complete" while an error tells operators to configure Docker that
  was retired in F1 is a wrong-message bug. Edits are string/comment/docstring content — **no logic
  change**.
- Trade-off: this is where F9 touches `.py` files. Scoped to message/comment/docstring strings.
  **Leg design MUST grep the tests for assertions on the old wording before editing** — known
  candidates: `tests/test_mcp_sandbox_integration.py` (has SYS_ADMIN/seccomp skip-gating),
  `tests/test_mcp_stdio_sandbox.py`, `tests/test_sandbox_bubblewrap.py` — and update any that assert
  the exact removed substrings (mechanical). The behavior these messages describe is unchanged.

**DD2b — The Docker-grep is a *triage* sweep, not a zero-hit gate.** The tree legitimately retains
many Docker references — the README's Docker production-shaped path, the CLAUDE.md "Local dev with
Docker" section, `docker-compose.yml`, SECURITY-MODEL container notes, and `agents.md`/`the_one/agents.md`
dev-reference history (`cap_add: SYS_ADMIN`, `docker compose logs`). The end-state is **not** "grep
returns one hit"; it is: *every remaining hit is reviewed and is either legitimate-creds-protection,
an intentionally-retained dev/historical reference, or a doc updated per DD5 — and no hit prescribes
Docker to an end user/operator as current runtime setup.*

**DD3 — End-user install guide is a NEW user-facing doc, separate from the dev build-contract.**
- Choice: write a download → SmartScreen passthrough → first launch (window + tray) → CLI →
  uninstall guide aimed at a non-technical user. Do **not** fold it into the dev `Quickstart` or
  the `packaging/windows/README.md` (which is the developer build contract).
- Rationale: the two audiences are distinct; the mission criterion targets the end user.

**DD4 — Windows-only.** macOS/Linux install docs are out of scope — they migrate to the follow-up
macOS/Linux mission with their packaging flights (mission re-scope 2026-06-15).

**DD5 — Docker references in docs: demote the retired *end-user/production* path; retain accurate
dev/historical context.**
- Choice: in the README, the Docker production-shaped path (and the `pip`/Docker framing of the
  Quickstart) is **demoted** — the end-user path leads with the Windows installer; the `pip` dev
  path stays; the Docker block is annotated as a **retired path** (Docker was retired entirely in
  M15 F1), not presented as a current option. Dev-reference docs that carry historical Docker
  detail for accuracy (`agents.md`, `the_one/agents.md`, the CLAUDE.md "Local dev with Docker"
  section, `SECURITY-MODEL.md` container notes, `docker-compose.yml`) are **reviewed and retained**
  where they document real history/decisions; only outright-misleading "do this now" guidance is
  corrected.
- Rationale: end users must not be steered to a retired Docker path, but scrubbing every historical
  Docker reference from dev docs is needless churn and erases accurate F-decision history.
- Trade-off: the docs end up with intentional Docker references (flagged as historical/retired) —
  the DD2b triage classifies each rather than chasing a zero-hit grep.

### Prerequisites
- [x] A working Windows installer exists and is **operator-validated** (installed from MinIO, F8).
- [x] Concourse CI is green on `main` (F8) — the docs can be merged through the established gate.
- [x] Confirm the final shipped behaviors the guide will describe (SmartScreen text, Start-menu
      entry, tray/close-to-tray, CLI invocation) match the F5–F7 implementation — verified at leg design.

### Pre-Flight Checklist
- [x] All open questions resolved (install-guide location resolves at leg design)
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Pure documentation + messaging-accuracy work. Two surfaces:

1. **End-user docs** — a new Windows install/first-run/SmartScreen guide (DD3), plus a final pass
   over `README.md` (point the end-user path at the installer; keep the dev `pip` path),
   `CLAUDE.md`, and `SECURITY-MODEL.md` so they describe the shipped Windows-app + host-native +
   Concourse-CI reality.
2. **Messaging accuracy** — replace the stale Docker-era operator text found in `stdio.py` and
   `cache_cleanup.py` (DD2); finish with a `grep -rniE "docker|seccomp|SYS_ADMIN|docker compose"`
   sweep over `the_one/` + top-level docs to confirm nothing user-facing still prescribes Docker
   (the `~/.docker/config.json` denylist entry is the only legitimate remaining hit).

No changes to the launch path, the sandbox/execution behavior, or any pipeline/CI config.

### Checkpoints
- [x] End-user Windows install/first-run/SmartScreen/CLI/uninstall guide written and linked from the README.
- [x] Both `stdio.py` `SandboxError` messages + `cache_cleanup.py` comments + `api.py` `host.docker.internal`
      + `config.py:20` data-dir docstring reworded host-native/accurate; tests asserting old strings
      updated; the full suite stays green.
- [x] Docker-grep **triage** done: every remaining hit reviewed and classified (legitimate /
      historical-dev / retired-path-annotated); **no hit prescribes Docker to an end-user/operator
      as current runtime setup**.
- [x] `README.md` / `CLAUDE.md` / `SECURITY-MODEL.md` reflect the shipped state.
- [x] The two deferred Known Issues recorded in the flight log as accepted/maintenance-bound (DD1).

### Adaptation Criteria

**Divert if**:
- The "final shipped behavior" the guide documents turns out to diverge from the installed app in a
  way that's a *bug* (not just undocumented) — surface it; decide fix-vs-document with the operator
  rather than documenting wrong behavior as intended.

**Acceptable variations**:
- Install-guide location/format (top-level `INSTALL.md` vs `docs/` page vs README section).
- Folding the messaging-accuracy edits and the reference-doc pass into a single leg if small.

### Legs

> **Note:** Tentative; planned and created one at a time as the flight progresses.

- [x] `windows-install-guide` — author `docs/windows-install.md` (end-user): download the
      installer; get past the **unsigned-app SmartScreen** warning ("More info → Run anyway");
      Start-menu launch of the **windowed** app (`the-one-app.exe`); the native window +
      close-to-tray/background behavior; the bundled **CLI** — note it's the *separate*
      `the-one.exe` under the install dir (`C:\Program Files\GleepGlorp AI\`), **no shortcut**, run
      as `the-one.exe chat | serve | doctor | version`; **data location** `%LOCALAPPDATA%\the-one`
      (not `%APPDATA%`) and that an existing `~/.the-one` is migrated, not orphaned; point at
      `the-one.exe doctor` as the self-diagnostic when MCP runtimes (`node`/`uv`) are missing;
      **uninstall** via Add/Remove Programs. Link from the README Quickstart. *(DD3)*
- [x] `messaging-and-doc-accuracy` — replace the stale Docker-era **operator-facing** text per DD2
      (both `stdio.py` `SandboxError` messages; `cache_cleanup.py` comments; `api.py:3798`
      `host.docker.internal`; the `config.py:20` `%APPDATA%`→`%LOCALAPPDATA%` docstring) with
      host-native-accurate wording; **grep the tests first** and update any asserting the old
      substrings (`test_mcp_sandbox_integration.py`, `test_mcp_stdio_sandbox.py`,
      `test_sandbox_bubblewrap.py`); run the DD2b Docker-grep **triage** (classify each hit
      keep-vs-fix); do the README/CLAUDE/SECURITY-MODEL pass per DD5 (demote the retired Docker
      end-user/production path; retain accurate dev/historical context); record the two deferred
      Known Issues as accepted/maintenance-bound; keep the full suite green. *(DD2, DD2b, DD5)*

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [x] End-user Windows install guide published + linked
- [x] No stale Docker-flavored operator messaging remains (grep-verified); suite green
- [x] Reference docs (README/CLAUDE/SECURITY-MODEL) reflect shipped state
- [x] Two deferred Known Issues recorded for the mission debrief
- [ ] Code merged

### Verification

Documentation flight — verification is by review + a clean grep, not a behavior test:
1. The install guide walks a non-technical Windows user from download to a running app (incl. the
   SmartScreen click-through) — reviewed for accuracy against the shipped installer.
2. `grep -rniE "docker|docker compose|seccomp|SYS_ADMIN" the_one/ README.md CLAUDE.md SECURITY-MODEL.md`
   output is **triaged** (DD2b): no surviving hit prescribes Docker to an end-user/operator as
   current runtime setup; remaining hits are creds-protection, retired-path annotations (DD5), or
   accurate historical dev context.
3. The full test suite stays green after the message-string edits (confirms the messaging edits
   broke nothing, incl. any updated assertions).
