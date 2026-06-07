# Flight: Agent-Selectable Execution Isolation (Boxed Mode)

**Status**: landed
**Mission**: [Unified Tool-Execution Sandbox](../../mission.md)

## Contributing to Criteria
- [x] On **Linux**, a built-in tool process **cannot read or write outside its
      permitted filesystem scope** — Flight 4 satisfies the **read** half (unmet since
      Flight 1) *for the boxed execution path*: a boxed process has no user FS at all
      (minimal RO system rootfs + tmpfs scratch). Host-workspace read-scoping remains a
      separate concern. *(behavior-test-backed + `@requires_bwrap`)*
- [x] Delivers the mission's planned **boxed-mode capability** (Flights list, Flight 4):
      the agent can run untrusted / self-generated code in a disposable box distinct from
      host-workspace execution, selected per call.
- [x] Existing behavior preserved: host-workspace execution still works when the agent
      escalates (`host_access=true`); tests pass; ruff gate passes; MCP sandboxing
      un-regressed.

## Source artifacts
This flight pulls forward small adjacent debt from the **Flight 3 debrief** (the
`_TOOL_CLASSES` cross-config note, the `pty.py` fork-safety convention, the
ordering-is-policy assertion) — bundled into the `box-debt-and-docs` leg because Flight 4
already edits those same surfaces (`tools/builtins.py`, `tools/execution.py`,
`platform/pty.py`). Operator design decisions (box-by-default, true isolation,
per-session persistence, all-three-tools scope) are recorded in Design Decisions.

---

## Pre-Flight

### Objective

Layer an agent-selectable execution-isolation choice on top of the shared sandbox seam
so the agent can run untrusted / self-generated code in a **disposable box** — a minimal
read-only system rootfs with a tmpfs scratch as its only writable space (= `$HOME`),
no user filesystem, no network — distinct from host-workspace execution. The box is the
**default**; the model explicitly escalates out (`host_access=true`) only when it needs
the user's real files or network. Boxed scratch is **ephemeral per one-shot call** and
**persistent per PTY session** (so multi-step self-generated code — install then run —
works inside a session, then is discarded on close). Covers all three built-in spawn
tools (`shell`, `python_exec`, `shell_session_*`), the model-selection guidance, and
behavior-test verification of both containment and the agent's selection decisions.

### Open Questions
- [x] Selection surface: box-by-default + per-call `host_access` escalation, opt-in `box`,
      or separate `*_boxed` tools? → **Box-by-default + `host_access`** (operator; DD1)
- [x] Isolation depth: true isolation (minimal rootfs, no user FS) vs writable-isolated
      (host root readable RO)? → **True isolation — minimal rootfs** (operator; DD2)
- [x] Boxed-workspace lifecycle: per-call / per-session / per-agent? → **Per-session
      persist + per-call ephemeral** (operator; DD3)
- [x] Scope: which tools this flight? → **All three** (`shell`, `python_exec`,
      `shell_session_*`) (operator; DD4)
- [x] Boxed mode on a backend without isolation support (passthrough / non-Linux)? →
      **Degrade loudly, never error**: scratch cwd, no enforcement, WARNING-logged
      (DD5 — consistent with the mission's passthrough-is-observable philosophy)
- [x] Does the new isolation profile field error on backends that can't honor it? →
      **No** — silently ignored per the mission's `SandboxProfile` constraint (DD6)
- [x] **Apparatus re-confirm before the behavior-test run** (prerequisite, below)

### Design Decisions

**DD1 — Box-by-default; the model escalates OUT via a per-call `host_access: bool`
(default `false`).**
- The existing `shell` / `python_exec` / `shell_session_start` tools gain a per-call
  `host_access` parameter (default `false`). Default execution is the box; the model sets
  `host_access=true` only when the task needs the user's actual files or the network. No
  new tools (keeps `_TOOL_CLASSES` count + guidance single-surface).
- Rationale: "do I need the user's real files/network?" is a more concrete decision for
  the model than "is this risky enough to box?"; box-by-default is least-privilege and
  leakage-safe by omission.
- **Trade-off / behavior shift**: this *flips the experienced default*. Pre-flight,
  `shell("cat ~/notes.md")` read the real home; post-flight it runs boxed and sees no
  user files unless the model sets `host_access=true`. Model-selection guidance (the
  `model-selection-guidance` leg) and the selection-decision behavior checkpoints exist
  precisely to manage this shift. `host_access=true` reproduces today's host-workspace
  profile exactly (operator allowlist, real `$HOME`, network per `ExecutionConfig`).
- **Orthogonal to agent config (design-review confirmed)**: `host_access` is a **per-call**
  `execute()` kwarg (the tools already accept `**kwargs`), while operator/agent tool
  config flows through the `Config`-layer resolver at construction (`builtins.py:168-173`).
  They do not collide — `host_access` selects the profile *builder* per call; the resolved
  `ExecutionConfig`/`FilesystemConfig` still apply on the `host_access=true` path.

**DD2 — Boxed = TRUE isolation via a minimal read-only system rootfs, not a
writable-confined view of the host root. (Empirically confirmed buildable at design
review.)**
- A boxed spawn does **not** `--ro-bind / /`. Instead the bubblewrap backend binds only
  the system runtime read-only, mounts `--proc /proc --dev /dev`, provides a **host-side
  scratch dir bound writable as the only writable path and as `$HOME`** (see DD3a — NOT
  an in-box tmpfs), and keeps `--unshare-net`.
- **Mount set (design-review verified in-container, `python:3.11-slim` / Debian bookworm /
  merged-usr / bwrap 0.11.0):** `--ro-bind /usr /usr` (always exists; covers
  `/usr/local` where this base's Python + `libpython` live — a `/usr/lib`-only set would
  silently break Python, so bind `/usr` wholesale) + **`--symlink`** for the merged-usr
  links (`usr/bin /bin`, `usr/sbin /sbin`, `usr/lib /lib`, `usr/lib64 /lib64`) rather than
  double-binding; `--ro-bind-try` only for genuinely-optional `/lib32` `/libx32`; plus a
  **narrowed `/etc`** set (`ssl`, `passwd`, `group`, `nsswitch.conf`, `resolv.conf`,
  `alternatives`, `ld.so.*`) rather than wholesale `/etc` — avoids handing `/etc/shadow`
  and other system config to self-generated code (this does NOT contradict host mode,
  where `/etc` is already RO-readable under `--ro-bind / /`). `--proc /proc --dev /dev`
  still apply. The single branch point is the unconditional `--ro-bind / /` at
  `bubblewrap.py:123`.
- **Confirmed at review (empirical, in the live container):** boxed `python3 -c "import
  sys,json,os,ssl,sqlite3"` and `/bin/sh` both succeed; a planted `/root/.../canary.txt`
  is unreadable from inside the box; `ls /` shows only `bin dev etc lib lib64 proc sbin
  tmp usr` (no `/root` `/home` `/app` `/var`); scratch is writable. So the Divert clause
  (fall back to writable-isolated) is **low-probability**, not the expected path — but the
  leg-1 `@requires_bwrap` gate still runs it as the contract.
- Rationale: matches the mission's "no host FS/network" intent AND advances the unmet
  "cannot read outside scope" criterion for the boxed path. Writable-isolated (host root
  readable RO) was rejected: it leaks reads and does not advance read-scoping.
- **Trade-off**: a new backend code path + a new `SandboxProfile` field. If a stdlib
  import needs a path not in the set, leg 1 widens the RO **system** set (never the
  writable set).

**DD2a — Boxed profile derivation: a sibling `_build_boxed_profile(scratch)`, not a
branch in `_build_tool_profile`.**
- Almost no inputs are shared with host mode (no operator allowlist/denylist, no real
  home, empty `readonly_overlay_paths` — there is no host FS to re-overlay). A sibling
  builder keeps `tools/execution.py:424` clean. Boxed profile: `writable_paths=[scratch]`,
  `home=scratch`, `network_allowed=False`, `readonly_overlay_paths=[]`, isolation field
  set.

**DD3 — Boxed-workspace lifecycle: per-call ephemeral (one-shot) + per-session
persistent (PTY).**
- One-shot `shell` / `python_exec` boxed calls each create a **fresh scratch dir per
  call**, cleaned up when the call returns (no cross-call state — each boxed one-shot is
  fully disposable).
- `shell_session_*` boxed sessions get a scratch dir allocated at `shell_session_start`,
  persisting across `shell_session_send`s (so `pip install` then use works), cleaned up
  on close + reaper + shutdown drain.
- **Cleanup is owned by `PtySession.close()` itself, NOT the registry entry
  (design-review finding).** `entry.session.close()` is invoked from **five** sites
  (`_session_registry.py` `close():140`, `_reap_once():241`, `shutdown_drain():198`,
  `_reap_loop` CancelledError drain `:274`, `_clear_for_test():307`). Binding scratch
  removal to `close()` means all five clean up for free (one locus) — the alternative
  (cleanup held on `_RegistryEntry`) would have to touch all five or leak. Additionally,
  `ShellSessionStartTool.execute` (`sessions.py:141-149`) creates+starts the session
  **before** `register()`; if `register` raises (`_shutting_down`, `:102`), the session is
  orphaned (never registered → reaper/drain never see it). Box mode turns that pre-existing
  process-leak into a scratch-dir leak — leg 4 must **close-on-registration-failure**.
- Rationale: matches how the model already reaches for sessions when it needs continuity;
  one-shot stays maximally disposable; single-locus cleanup structurally satisfies the
  "all exit paths" requirement.
- **Trade-off**: cleanup failure is non-fatal (logged), mirroring the existing
  session-close error tolerance.

**DD3a — Scratch is a HOST-side dir bound writable into the box, NOT an in-box tmpfs
(design-review finding — load-bearing for both the backend and the observe path).**
- The box does `--tmpfs /tmp`; a scratch placed naively under `/tmp` would be **masked**
  by that tmpfs, and an in-box tmpfs scratch would be **invisible to `docker exec`**
  (it lives in bwrap's private mount namespace) — breaking the DD8 observe path. The
  correct pattern (verified at review): a **real host-side dir** created on the container
  fs, then bound writable into the box via the existing `writable_paths` `--bind`
  machinery (bind applied AFTER `--tmpfs /tmp`, so no masking). This reuses the existing
  backend bind path for free.
- **Scratch root**: a dedicated host dir, default `settings.data_dir / "boxes" /
  <unique>` (`unique` = agent + session-id + uuid; one-shot uses a per-call uuid). NOT
  under `/tmp` (sidesteps the `--tmpfs` masking entirely) and on the real fs (observable
  via `docker exec`). Bound into the box at the same path and set as `$HOME`.

**DD4 — All three tools (`shell`, `python_exec`, `shell_session_*`) get boxed mode in
this flight.**
- They share `_build_tool_profile` (`tools/execution.py:424`) and the seam, so doing them
  together is coherent and avoids a second profile-derivation branch later.
- Trade-off: larger flight (~7 legs). Accepted — the lifecycle split (DD3) is the only
  added complexity and it's contained to the session leg.

**DD5 — Boxed mode on a backend that can't enforce isolation (passthrough / non-Linux)
degrades loudly, never errors.**
- On a backend without the minimal-rootfs capability, a boxed call still routes through
  the seam, runs with the **scratch dir as cwd/`$HOME`** (so writes land in the throwaway
  dir), but **cannot** prevent host reads or network. The seam emits a **WARNING**
  ("boxed execution requested but isolation is not enforced on this backend") — the
  absence of enforcement is observable/logged, never silent, never an error.
- **WARNING locus (design-review finding):** NOT the sandbox factory — `factory.py`'s
  selection log (`:89-124`) is once-per-process and cannot see per-call isolation intent.
  The check must live where both the profile's isolation field AND the resolved
  `backend.name` are visible: in `run_shell`/`run_python` (`platform/shell.py` /
  `platform/interpreter.py`, which call `get_sandbox_backend()`) and `UnixPtySession.start`
  (`platform/pty.py:~250`). Pin this in leg 1/2.
- **Passthrough `$HOME` (design-review finding):** `PassthroughSandbox` forwards env
  unchanged (`passthrough.py:58`) — it does NOT honor `profile.home` the way bubblewrap
  does (`bubblewrap.py:108`). So on the boxed passthrough path the tool must put
  `HOME=scratch` **into the env dict** rather than relying on `profile.home`. Forward-compat
  only (current deploy is always bubblewrap).
- Rationale: consistent with the mission's passthrough philosophy (run through the seam,
  surface absent enforcement). The current Linux+bwrap deployment always enforces; this
  is forward-compat for M15 backends.

**DD6 — The new isolation field is silently ignored by backends that can't honor it.**
- Add a `SandboxProfile` field (working name `minimal_rootfs: bool = False`; final name a
  leg-1 detail). The bubblewrap backend honors it (DD2 mount set); passthrough ignores it
  (DD5). Per the mission constraint, an unhonored profile field never errors — so M15's
  macOS/Seatbelt backend slots in behind it without a breaking profile change.

**DD7 — `SandboxError` import-cycle inversion (Flight 3 DD1) stays deferred to
end-of-mission maintenance.**
- Leg-1's minimal-rootfs work touches `bubblewrap.py` but not `mcp/errors.py`; the cycle
  is orthogonal. **Pre-flight gate**: if the backend work unexpectedly forces a new
  error-path through `platform/sandbox` that needs the MCP layer, revisit before leg 1
  lands. Default: deferred.

**DD8 — Apparatus for the boxed behavior test = the same live-agent surface as Flight 3,
re-audited on both axes.**
- **Act**: `POST /api/chat` → agent (the `sandbox-test` agent, reconfigured so the new
  `host_access` param is in its tool schema) → boxed tool call. **Observe**: container-side
  via `docker exec the-one` — the box's scratch dir contents, *absence* of a planted
  host home-file from inside the box, per-session scratch persistence across sends, and
  scratch cleanup after close. Both the act path (chat API) and the read path (docker
  exec on the container FS + the agent's own tool-result output for in-box `pwd`/read
  attempts) exist today — no new test-only seam needed.
- Selection-decision checkpoints read the agent's *tool-call arguments* (did it set
  `host_access`?) from the `/api/chat` response `messages` — that read path exists.

### Prerequisites
- [x] Shared seam + all four spawn paths through it (Flights 1–3, merged to `main`).
- [x] `_build_tool_profile` is the single built-in profile hook (`tools/execution.py:424`);
      `create_pty_session(cwd, profile)` takes a profile (`platform/pty.py:193`).
- [x] `_session_registry` exists with a reaper + shutdown drain to own per-session
      lifecycle (`tools/_session_registry.py:54,165`).
- [x] `bwrap` present and supports `--ro-bind-try` / `--symlink` — host `0.9.0`,
      **in-container `0.11.0`** (the `@requires_bwrap` suite runs against both: host-native
      + in-container; design-review confirmed the minimal-rootfs path on 0.11.0). Docker
      grants userns caps. Note the two-version spread so a future failure isn't mis-triaged.
- [x] **Behavior-test apparatus (DD8) — re-confirm before the run**: running instance +
      the `sandbox-test` agent reconfigured to expose `host_access` on shell/python_exec/
      shell_session_* (rebuilt tool schema), on a bwrap host; drive surface
      `POST /api/chat`; observe via `docker exec the-one`. (The Flight-3 apparatus agent +
      `~/.ssh/id_test` fixture are still on the instance.)
- [x] **Environment**: boxed scratch dirs live under `settings.data_dir / "boxes"` on the
      container's real fs (NOT `/tmp` — DD3a; that would be masked by the box's
      `--tmpfs /tmp` and invisible to `docker exec`), bound writable into the box. Confirm
      `settings.data_dir` is writable and per-call/per-session dirs are uniquely named
      (agent + session id + uuid). Cleaned up per DD3.

### Pre-Flight Checklist
- [x] All open questions resolved (apparatus re-confirm is a runtime prereq, not an open design Q)
- [x] Design decisions documented
- [x] Prerequisites verified (apparatus re-confirm pending until the behavior-test leg)
- [x] Validation approach defined (boxed behavior test + `@requires_bwrap` + selection-decision checkpoints)
- [x] Legs defined

---

## In-Flight

### Technical Approach

Add a minimal-rootfs isolation path to the bubblewrap backend gated by a new
`SandboxProfile` field, with a boxed profile derived from an ephemeral/registry-owned
scratch dir (the only writable path + `$HOME`, network off). Branch the built-in tool
flow on a per-call `host_access` parameter (default false → boxed): boxed cwd is the
scratch dir (validated against the box's own writable set, not the operator allowlist);
`host_access=true` reproduces today's host-workspace profile. One-shot tools allocate +
clean an ephemeral scratch per call; `shell_session_*` allocate a registry-owned scratch
at start, persist it across sends, and clean it on close/reap. Author model-selection
guidance (tool descriptions + system prompt) for the box-by-default/escalate contract.
Verify with a new `tool-sandbox-box-isolation` behavior test (boxed containment +
read-scoping proof + per-session persistence + selection decisions) and a consolidated
`@requires_bwrap` box suite. Fold in the small Flight-3 carry-forward debt on the shared
surfaces.

### Checkpoints
- [x] **Backend isolation path** (`@requires_bwrap`): a boxed profile yields a working
      runtime (boxed `python` imports stdlib + runs) AND cannot read a planted host
      home-file canary; scratch is writable; network is isolated. Green.
- [x] **One-shot boxed** (`@requires_bwrap`): `shell`/`python_exec` default to boxed
      (fresh ephemeral scratch per call, cleaned up); `host_access=true` reproduces
      host-workspace; cross-call state does NOT persist for boxed one-shots.
- [x] **Session boxed** (`@requires_bwrap`): `shell_session_start` (boxed) → scratch
      persists across sends (install-then-use works); cleaned on close AND by the reaper;
      `host_access=true` session reproduces host-workspace.
- [x] **Model guidance**: tool descriptions + system prompt teach the box-by-default /
      `host_access`-to-escalate contract; introspected tool schema shows the param.
- [x] **Boxed behavior test passes** against a live instance: boxed containment +
      read-scoping (box can't read a user file) + per-session persistence + the agent's
      selection decisions (unambiguous tasks → correct `host_access` choice). Agent-safe
      observables only.
- [x] **Debt + docs**: `_TOOL_CLASSES` cross-config note (`agents.md`); `pty.py`
      fork-safety + libc-preload convention promoted to a named module-doc convention;
      ordering-is-policy assertion/comment in `builtins.py`; boxed-mode section in
      `SECURITY-MODEL.md`; mission known-issue updated (read-scoping advanced for the
      boxed path); `CLAUDE.md`. Full suite + ruff green; MCP sandboxing un-regressed.

### Adaptation Criteria

**Divert if**:
- The minimal-rootfs mount set can't produce a working `python`/`sh` for the container
  base without effectively re-binding the host (i.e. true isolation proves infeasible
  with bwrap binds alone) → fall back to writable-isolated for this flight and split true
  read-isolation into its own flight, recording the reason in the flight log. (Re-opens
  the DD2 trade-off; operator decision.)
- Per-session scratch cleanup can't be made reliable across the reaper/crash paths →
  ship per-session boxed as **experimental** with a documented cleanup caveat, or
  descope session-boxed to a follow-up (DD4 → "one-shot first").

**Acceptable variations**:
- Final name/shape of the `SandboxProfile` isolation field and whether boxed profile
  derivation is a branch in `_build_tool_profile` or a sibling `_build_boxed_profile`.
- Exact minimal RO mount set (widen the *system* set as needed; never the writable set).
- Whether the boxed behavior test is a new spec or a variant block on
  `tool-sandbox-containment` (lean: new spec `tool-sandbox-box-isolation` to keep the
  unified containment test focused).

### Legs

> **Note:** Tentative; legs are planned one at a time as the flight progresses.

- [x] `box-backend-isolation` — Add a `SandboxProfile` isolation field (DD6) + the
      minimal-read-only-system-rootfs path in `platform/sandbox/bubblewrap.py`: branch the
      unconditional `--ro-bind / /` (`bubblewrap.py:123`) so the boxed path instead
      `--ro-bind /usr /usr` + `--symlink usr/{bin,sbin,lib,lib64} /{bin,sbin,lib,lib64}`
      (merged-usr) + `--ro-bind-try /lib32 /libx32` + a **narrowed `/etc`** set
      (ssl/passwd/group/nsswitch.conf/resolv.conf/alternatives/ld.so.*), `--proc /proc
      --dev /dev`, `--unshare-net`, and the host-side scratch bound writable (DD3a — reuse
      the existing `writable_paths` `--bind`, applied after `--tmpfs /tmp`). The
      no-enforcement WARNING lives in `run_shell`/`run_python`/`pty.start`, NOT the factory
      (DD5). `@requires_bwrap` tests: boxed `python3` imports stdlib + runs; `/bin/sh`
      works; boxed process cannot read a planted host home-file; `ls /` has no
      `/root`/`/home`; scratch writable + visible via the host fs; loopback-only net.
      Files: `platform/sandbox/base.py`, `platform/sandbox/bubblewrap.py`,
      `platform/shell.py` + `platform/interpreter.py` + `platform/pty.py` (WARNING locus),
      `tests/test_sandbox_bubblewrap.py` / `test_sandbox_contract.py`.
- [x] `boxed-profile-derivation` — Add a sibling `_build_boxed_profile(scratch)`
      (writable=[scratch], home=scratch, network off, `readonly_overlay_paths=[]`,
      isolation field set — DD2a). **Pin the cwd seam**: `_cwd_check` validates against the
      operator `FilesystemConfig` and would self-refuse the scratch (never in the operator
      allowlist) — so boxed cwd is validated against an **ephemeral
      `FilesystemConfig(path_allowlist=[scratch])`** through the same dispatcher (reuses
      `is_dir()` + canonicalization), OR cwd is forced to `scratch` and the operator-scope
      check skipped. Decide whether an agent-supplied `cwd` is honored (validated ⊆ scratch)
      or ignored. Files: `tools/execution.py` (sibling builder + boxed cwd handling),
      unit tests.
- [x] `one-shot-boxed` — Wire `host_access: bool` (default false) into `shell` +
      `python_exec` schemas + `execute()`; box-by-default; per-call ephemeral scratch
      (create + guaranteed cleanup). `host_access=true` → existing host-workspace path.
      Files: `tools/shell.py`, `tools/python_exec.py`, `tools/execution.py`,
      `tests/test_builtin_tool_sandbox.py` (+ `_sandbox_fixtures.py` helper for an
      ephemeral-box context).
- [x] `session-boxed` — `host_access` on `shell_session_start`; scratch persists across
      sends. **Cleanup owned by `PtySession.close()`** (single locus → all five
      `entry.session.close()` sites clean up for free — DD3) rather than held on
      `_RegistryEntry`. Also **close-on-registration-failure** in
      `ShellSessionStartTool.execute` (`sessions.py:141-153`) so a session orphaned when
      `register()` raises doesn't leak its scratch. Test cleanup across close + reaper +
      shutdown-drain + registration-failure. Files: `tools/sessions.py`,
      `the_one/platform/pty.py` (`close()` scratch removal), `tools/_session_registry.py`
      (if the scratch path must be threaded through), `tests/test_pty_sandbox.py`.
- [x] `model-selection-guidance` — Tool descriptions + system-prompt guidance for the
      box-by-default / `host_access`-to-escalate contract (when to escalate; default stays
      boxed). Files: `tools/shell.py` / `python_exec.py` / `sessions.py` descriptions,
      `agent/config.py` (BASE_PROMPT/compose_system_prompt), tests for the composed prompt.
- [x] `box-behavior-test` — Author `tests/behavior/tool-sandbox-box-isolation.md`
      (boxed containment + read-scoping proof + per-session persistence + agent
      selection-decision checkpoints; agent-safe observables; reuse the Flight-3
      apparatus). Consolidate any shared `@requires_bwrap` box setup into
      `tests/_sandbox_fixtures.py`. Files: new behavior spec, `tests/_sandbox_fixtures.py`.
- [x] `box-debt-and-docs` — Flight-3 carry-forwards on shared surfaces + boxed-mode docs:
      `_TOOL_CLASSES` cross-config resolution note + ordering-is-policy assertion/comment
      (`agents.md`, `builtins.py`); `pty.py` fork-safety + libc-preload convention
      promoted to a named module-doc convention; boxed-mode section in `SECURITY-MODEL.md`;
      mission known-issue updated (read-scoping advanced for the boxed path, host path
      still open); `CLAUDE.md`. Files: `the_one/agents.md`, `the_one/tools/builtins.py`,
      `the_one/platform/pty.py`, `SECURITY-MODEL.md`, `missions/14-.../mission.md`, `CLAUDE.md`.
- [x] `verify-integration` — Full suite host-native + in-container; ruff; `-m
      requires_bwrap`; run `/behavior-test tool-sandbox-box-isolation` + re-run
      `tool-sandbox-containment` (no host-mode regression); confirm passthrough still
      no-error (+ the new no-enforcement WARNING fires off-bwrap).
- [~] `uat-and-alignment` *(optional)* — **SKIPPED** (operator: the live behavior test (9/9) + the `@requires_bwrap` suite cover acceptance). Originally: guided HAT to drive the live agent and
      sanity-check box-by-default behavior (does the agent escalate sensibly? does boxed
      multi-step session code work? does a normal "read my file" task escalate?), with
      inline fixes. (Behavior test is primary; this is the human vibe-check on selection
      judgment.)

---

## Post-Flight

### Completion Checklist
- [x] All legs completed (8 core; optional HAT skipped)
- [ ] Code merged
- [x] Tests passing (full suite, `-m requires_bwrap`, `tool-sandbox-box-isolation`,
      `tool-sandbox-containment` un-regressed)
- [x] Documentation updated (boxed-mode security model, model-selection guidance,
      carry-forward debt docs)

### Verification
- **Backend isolation**: a `@requires_bwrap` test proves a boxed spawn has a working
  runtime yet cannot read a planted host home-file (read-scoping for the boxed path).
- **Boxed behavior test** (`tool-sandbox-box-isolation`): live agent surface, agent-safe
  observables — boxed containment, read-scoping, per-session persistence, and the agent's
  `host_access` selection decisions on unambiguous tasks.
- **No host-mode regression**: `tool-sandbox-containment` (Flight 3) still 6/6;
  `host_access=true` reproduces host-workspace behavior.
- **Passthrough**: boxed on a non-enforcing backend runs through the seam, WARNING-logs
  no-enforcement, does not error.
- `ruff check` + `ruff format --check` pass; full default suite green; MCP un-regressed.
- **Honest caveat** (carried): the default `pytest` run does not exercise containment
  (`requires_bwrap` deselected) and there is no pytest CI yet — boxed enforcement is
  proven by the `-m requires_bwrap` run + the live behavior test. Read-scoping is advanced
  for the **boxed** path only; host-workspace read-scoping remains a separate concern.
