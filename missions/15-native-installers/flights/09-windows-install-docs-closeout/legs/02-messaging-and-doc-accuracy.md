# Leg: messaging-and-doc-accuracy

**Status**: completed
**Flight**: [Windows install docs & mission closeout](../flight.md)

## Objective

Remove the last stale Docker-era **operator-facing** messages and doc inaccuracies, and do the
final reference-doc pass — so nothing the project ships steers a user/operator to the retired
Docker path, and the dev docs reflect the shipped Windows-app + host-native + Concourse-CI reality.
No app-behavior changes (messaging/comment/docstring/markdown only).

## Context

- **DD2** — replace the stale operator-facing Docker-era runtime text with host-native-accurate
  wording. Confirmed targets (verified at planning):
  - `the_one/mcp/transports/stdio.py` — **two** `SandboxError` messages: ~189-194 ("namespace
    creation refused … privilege grants required by §10") and ~197-201 ("Check that the dev/CI
    environment has `cap_add: SYS_ADMIN` AND `security_opt: seccomp:unconfined` per F3 design
    decision §10"). Both prescribe Docker-compose privilege config retired in F1; "§10" is opaque to
    an operator. Reword to host-native terms (unprivileged user namespaces; e.g.
    `sysctl kernel.apparmor_restrict_unprivileged_userns=0` / bubblewrap present), dropping the
    Docker/§-reference framing while preserving the error's diagnostic intent.
  - `the_one/mcp/cache_cleanup.py:37,293` — comments referencing `docker compose logs the-one`;
    reword to the host-native run/log reality.
  - `the_one/interfaces/web/api.py:3798` — operator-facing `host.docker.internal` reference; correct
    to the host-native equivalent (or annotate if it's a legitimate example).
  - `the_one/config.py:20` — `_default_data_dir` docstring says Windows = `%APPDATA%\the-one`, but
    `platformdirs.user_data_dir("the-one", appauthor=False)` (roaming=False) resolves to
    **`%LOCALAPPDATA%\the-one`**. Fix the docstring (the Leg-1 guide already states the correct path).
  - **Leave** `the_one/tools/filesystem.py:40`'s `~/.docker/config.json` denylist entry (protects
    real Docker creds if present — not Docker-era guidance).
- **DD2b** — the Docker-grep is a **triage**, not a zero-hit gate. The tree legitimately retains many
  Docker references (README Docker path, CLAUDE.md "Local dev with Docker", `docker-compose.yml`,
  SECURITY-MODEL container notes, `agents.md`/`the_one/agents.md` dev history). End-state: every
  remaining hit is reviewed and is creds-protection, intentionally-retained dev/historical context,
  or a retired-path annotation (DD5) — and **no hit prescribes Docker to an end-user/operator as
  current runtime setup**.
- **DD5** — README: demote the Docker production-shaped path to a **retired-path** note (Docker
  retired entirely in M15 F1); the end-user path leads with the Windows installer (link the Leg-1
  guide), the dev `pip` path stays. CLAUDE.md / SECURITY-MODEL.md: review their Docker sections —
  retain accurate historical/decision context, annotate anything that reads as "do this now."
- **Leg-1 carry-item** (flight log): `packaging/windows/README.md`'s "Output" section + its "the
  Start-menu shortcut invokes `the-one.exe app`" note are **stale (pre-F5 single-exe model)** — the
  real model is two exes (`the-one-app.exe` shortcut + `the-one.exe` CLI). Fix that dev README's
  description to match `the-one.iss` `[Icons]` + `the-one.spec`.
- **Tests may assert the old message strings** — grep BEFORE editing and update any that break.
  Known candidates: `tests/test_mcp_sandbox_integration.py` (SYS_ADMIN/seccomp skip-gating),
  `tests/test_mcp_stdio_sandbox.py`, `tests/test_sandbox_bubblewrap.py`.
- **Deferred Known Issues** (DD1) — record the two carry-forward edge cases (single-instance
  no-window-`serve`; `run_shell` Windows tree-kill) in the flight log as accepted/maintenance-bound
  so the mission debrief carries them. (They're already in the mission Known Issues.)

## Inputs

- Leg 1 landed (`docs/windows-install.md` exists + README link).
- The stale sites above, present at the cited locations.

## Outputs

- Reworded: `the_one/mcp/transports/stdio.py` (2 messages), `the_one/mcp/cache_cleanup.py` (2
  comments), `the_one/interfaces/web/api.py` (host.docker.internal), `the_one/config.py:20` docstring.
- Any tests asserting the old strings, updated.
- `README.md` (DD5 Docker-path demotion + installer-first), and a reviewed `CLAUDE.md` /
  `SECURITY-MODEL.md` / `packaging/windows/README.md` (stale Output section).
- Flight log: Docker-grep triage result + the two deferred Known Issues recorded.

## Acceptance Criteria

- [x] Both `stdio.py` `SandboxError` messages reworded host-native (no `cap_add: SYS_ADMIN` /
      `seccomp:unconfined` / "§10" Docker-era framing); diagnostic intent preserved.
- [x] `cache_cleanup.py` `docker compose logs` comments + `api.py` `host.docker.internal` corrected;
      `config.py:20` docstring says `%LOCALAPPDATA%\the-one` (Windows).
- [x] `packaging/windows/README.md` "Output"/shortcut description matches the real two-exe model.
- [x] Any tests asserting the old message substrings are updated; **the full default suite is green**
      (`make test` or `python -m pytest tests/ --timeout=300` host-native — NOT docker).
- [x] README demotes the retired Docker production path (DD5) and leads the end-user to the Windows
      installer (Leg-1 guide linked); CLAUDE.md / SECURITY-MODEL.md reviewed (accurate history retained).
- [x] Docker-grep triage (DD2b) recorded in the flight log: every remaining hit classified; none
      prescribes Docker to an end-user/operator as current runtime setup.
- [x] The two deferred Known Issues recorded in the flight log as accepted/maintenance-bound (DD1).

## Verification Steps

- `git diff` shows only message/comment/docstring/markdown edits (+ any test-assertion updates) — no
  logic changes.
- `python -m pytest tests/ --timeout=300 -q` (host-native) is green; if any sandbox/stdio test
  asserted the old strings, it now asserts the new wording and passes.
- `grep -rniE "docker|docker compose|seccomp|SYS_ADMIN|host.docker.internal" the_one/ README.md
  CLAUDE.md SECURITY-MODEL.md packaging/windows/README.md` — walk the output; confirm every hit is
  legitimate/historical/retired-annotated (record the classification in the flight log).

## Implementation Guidance

1. **Grep the tests first** for the old message substrings (`SYS_ADMIN`, `seccomp`, `§10`,
   `docker compose logs`, `host.docker.internal`) so you know what will break before editing. Update
   assertions to the new wording as part of the same change.
2. **Reword the `stdio.py` messages** to host-native diagnostics (bubblewrap present? unprivileged
   userns enabled? — mirror the guidance already in `the_one/platform/sandbox/factory.py`'s
   passthrough WARNINGs, which are the canonical host-native phrasing). Keep them actionable.
   **CRITICAL — preserve the asserted diagnostic prefixes, reword only the Docker-prescriptive
   tail:** tests assert the prefixes verbatim — `tests/test_mcp_sandbox_integration.py:505` →
   `"bubblewrap exited non-zero"`, `:545` → `"namespace creation refused"`. Keep those exact
   substrings; replace ONLY the stale remediation clause (`cap_add: SYS_ADMIN AND
   security_opt: seccomp:unconfined per F3 design decision §10`) with host-native advice. Done this
   way, those assertions keep passing and only the Docker advice changes — re-read the assertions to
   confirm none also assert the remediation text before you reword.
3. **Fix the comments + docstring** (`cache_cleanup.py`, `api.py`, `config.py:20`) — straightforward
   accuracy edits.
4. **Fix the stale `packaging/windows/README.md`** Output/shortcut prose to the two-exe model.
5. **README DD5 pass** — demote the Docker production block to a clearly-labelled "retired (M15 F1)"
   note; ensure the end-user path points at `docs/windows-install.md`; keep the `pip` dev path.
   Review CLAUDE.md / SECURITY-MODEL.md Docker mentions; annotate only outright-stale "do this now"
   text, retain accurate F-decision history.
6. **Run the host-native suite** to green; **run the Docker-grep triage** and record both the result
   and the two deferred Known Issues in the flight log.

## Edge Cases

- **Don't scrub legitimate/historical Docker references** (DD2b) — the goal is no *current-setup*
  Docker prescription to users/operators, not zero mentions. Over-scrubbing erases accurate history.
- **`api.py:3798` host.docker.internal** — if it's a legitimate example of reaching a host service
  (not a prescription), annotate rather than delete; judge from context.
- **Message rewording must not change control flow** — only the human-readable string; the
  `SandboxError` type, when it's raised, and what catches it stay identical.
- **If a test asserts the *behavior* the message describes (not the literal string)**, leave the
  behavior/skip-gating alone — only update literal-string assertions.
- **Test-harness & live-fixture Docker refs are out of scope** (classify as historical in the
  triage, don't scrub): `tests/HAT.md`'s `docker compose logs` steps, `tests/behavior/
  pty-session-containment.md`'s "under Docker: cap_add SYS_ADMIN" precondition note, and the
  `host.docker.internal` Ollama base-URLs in `test_llm_provider_*` / `test_provider_api.py` /
  `test_input_tokens_*` (live-test fixtures). These are dev/test docs + live-test scaffolding, not
  end-user/operator runtime setup — they pass the DD2b bar. Flag HAT.md/behavior-spec Docker-era
  staleness as a maintenance candidate in the flight log; do not rewrite them in this closeout.

## Files Affected

- `the_one/mcp/transports/stdio.py`, `the_one/mcp/cache_cleanup.py`, `the_one/interfaces/web/api.py`,
  `the_one/config.py` — message/comment/docstring rewording.
- Possibly `tests/test_mcp_stdio_sandbox.py` / `tests/test_sandbox_bubblewrap.py` /
  `tests/test_mcp_sandbox_integration.py` — assertion updates (only if they assert old strings).
- `README.md`, `CLAUDE.md`, `SECURITY-MODEL.md`, `packaging/windows/README.md` — doc accuracy.
- `missions/.../flight-log.md` — triage result + deferred Known Issues.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified; host-native suite green
- [x] Docker-grep triage recorded; no current-setup Docker prescription to users/operators remains
- [x] Two deferred Known Issues recorded for the mission debrief
- [x] `git diff` is messaging/comment/docstring/markdown only (+ test-assertion updates) — no logic change
- [x] Flight log updated with the leg progress entry
- [x] Set this leg's status to `landed` (commit deferred to end-of-flight batch)
