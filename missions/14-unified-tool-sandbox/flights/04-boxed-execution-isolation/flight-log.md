# Flight Log: Agent-Selectable Execution Isolation (Boxed Mode)

**Flight**: [Agent-Selectable Execution Isolation (Boxed Mode)](flight.md)

## Summary

Flight `ready` (design-reviewed, operator-confirmed). Capstone capability for Mission 14:
agent-selectable execution isolation layered on the shared seam. Operator design decisions (box-by-default + escalate,
true isolation via minimal rootfs, per-session persist + per-call ephemeral, all three
tools) are folded into the flight's Design Decisions. Pulls forward small adjacent debt
from the Flight 3 debrief on the surfaces this flight already edits.

---

## Reconnaissance Report

Architecture interrogation against current `main` (`ed63ce6`, post-Flight-3 merge) — the
branch points and current-state facts the design rests on:

| Area | Current state | Citation | Bearing on Flight 4 |
|---|---|---|---|
| Profile derivation hook | `_build_tool_profile(fs_cfg, exec_cfg)` → `SandboxProfile` (writable=allowlist, ro-overlay=denylist, network=exec_cfg, home=real `$HOME`) | `tools/execution.py:424-458` | Single branch point; boxed profile derives here (or a sibling) |
| Profile flow into seam | `ShellTool.execute`/`PythonExecTool.execute`/`ShellSessionStartTool.execute` build profile → `run_shell`/`create_pty_session` → `backend.prepare_spawn` | `shell.py:93`, `python_exec.py:91`, `sessions.py:137,141`, `shell.py:127`, `pty.py:251` | All three tools share the hook → DD4 (all-three) is coherent |
| SandboxProfile fields | writable_paths, readonly_overlay_paths, network_allowed, home, pid/ipc/uts_unshare | `platform/sandbox/base.py:91-117` | Add isolation field (DD6); boxed = scratch-only writable + scratch home |
| bwrap arg structure | `--ro-bind / /` + `--tmpfs /tmp` are foundational; writable via `--bind`, denylist via `--ro-bind-try`, net via `--unshare-net` | `platform/sandbox/bubblewrap.py:75-153` | DD2: boxed drops `--ro-bind / /` for a minimal RO system mount set — NEW backend path |
| Tool params → execute | per-tool `parameters` JSON schema + `execute(**kwargs)`; agent narrowing via `agent_overrides` | `tools/shell.py`, `tools/python_exec.py`, `tools/builtins.py:122-201` | DD1: add per-call `host_access` to schema + execute |
| `_TOOL_CLASSES` cross-config | shared `FilesystemConfig` resolved from the FIRST tool whose `Config IS FilesystemConfig` (= `read_file`, not `shell`) | `tools/builtins.py:122-201` | Ordering is policy → carry-forward assertion/comment (debt leg) |
| PTY session registry | module dict keyed `(agent_name, session_id)`; `_RegistryEntry` holds session+ttl; reaper @30s; shutdown drain | `tools/_session_registry.py:54,57,165` | DD3: extend `_RegistryEntry` with scratch path; reaper/drain own cleanup |
| cwd check | `_cwd_check` enforces cwd ⊆ allowlist + is_dir; defaults `cwd or $HOME` | `tools/execution.py:342-355`, `filesystem.py:139-228` | Boxed cwd = scratch, validated against the box's writable set (not operator allowlist) |
| Scratch location | no `workspace/` dir; `settings.data_dir = ~/.the-one` (agent data, not scratch); bwrap already `--tmpfs /tmp` | `config.py:22` | Boxed scratch under `/tmp` in-container, uniquely named (agent+session+uuid) |
| Behavior-test apparatus | `tool-sandbox-containment` drives live agent via `POST /api/chat`, observes via `docker exec` | `tests/behavior/tool-sandbox-containment.md` | DD8: same apparatus; reconfigure `sandbox-test` agent to expose `host_access` |

**Flight-3 carry-forward debt pulled into this flight** (shared-surface bundling): the
`_TOOL_CLASSES` cross-config note (`agents.md`), the `pty.py` fork-safety + libc-preload
convention, and the ordering-is-policy assertion (`builtins.py`) — all on surfaces Flight 4
edits. The `SandboxError` import-cycle inversion (Flight-3 DD1) stays deferred to
end-of-mission maintenance (Flight-4 DD7), gated at pre-flight.

---

## Design Review (Phase 5b)

**Architect verdict (Opus): approve with changes (1 cycle)**, with **empirical
verification of the load-bearing DD2** inside the live `the-one` container — not just on
paper. Confirmed: the minimal-rootfs mount set is **buildable** on the actual base
(`python:3.11-slim` / Debian bookworm / merged-usr / bwrap 0.11.0): boxed `python3` (with
`import sys,json,os,ssl,sqlite3`) and `/bin/sh` both run; a planted `/root/.../canary.txt`
is unreadable from the box; `ls /` shows only `bin dev etc lib lib64 proc sbin tmp usr`
(no `/root`/`/home`/`/app`/`/var`); scratch writable. The Divert (fall back to
writable-isolated) is therefore low-probability. Changes incorporated (all spec-clarity
pins on load-bearing mechanisms; no architectural reversal):

- **[verified] DD2 mount set**: bind `/usr` wholesale (this base's Python + `libpython`
  live under `/usr/local`, so a `/usr/lib`-only set would silently break Python);
  `--symlink` for merged-usr links (not double-bind); narrowed `/etc` (not wholesale —
  keeps `/etc/shadow` out of the box). Single branch point = `bubblewrap.py:123`.
- **[medium] DD3a (new)**: scratch must be a HOST-side dir bound writable into the box
  (reusing `writable_paths` `--bind`, applied after `--tmpfs /tmp`), NOT an in-box tmpfs —
  else it's masked by `--tmpfs /tmp` and invisible to `docker exec` (breaking the DD8
  observe path). Scratch root = `settings.data_dir / "boxes" / <unique>` (not under `/tmp`).
- **[medium] DD5 WARNING locus**: in `run_shell`/`run_python`/`pty.start` (where the
  isolation field + `backend.name` are both visible), NOT the once-per-process factory log.
  Plus: passthrough doesn't honor `profile.home`, so the boxed tool must put `HOME=scratch`
  in the env dict (forward-compat).
- **[medium] cwd seam**: `_cwd_check` validates against the operator `FilesystemConfig` and
  would self-refuse the scratch — boxed cwd validated via an ephemeral
  `FilesystemConfig(path_allowlist=[scratch])` or cwd forced to scratch (leg 2 decides;
  pinned in the leg).
- **[medium] session cleanup**: own it in `PtySession.close()` (single locus → all five
  `entry.session.close()` sites covered) rather than on `_RegistryEntry` (5 loci); plus
  close-on-registration-failure to fix a pre-existing orphan path box mode would turn into
  a scratch leak (DD3).
- **Suggestions folded**: sibling `_build_boxed_profile` not a branch (DD2a);
  `readonly_overlay_paths=[]` in the boxed profile; `host_access` confirmed orthogonal to
  the `agent_overrides`/Config layer (per-call kwarg vs construction-time resolver);
  in-container bwrap is 0.11.0 (host 0.9.0) — note the two-version spread.

**Architect open questions resolved by operator/designer:**
1. *Scratch root* → dedicated host dir `settings.data_dir / "boxes" / <unique>` (not
   `/tmp`; sidesteps `--tmpfs` masking; observable via `docker exec`).
2. *`host_access` × `agent_overrides`* → confirmed orthogonal; noted in DD1.
3. *Session cleanup design* → `PtySession.close()`-owns-scratch (1 locus) + close-on-
   registration-failure (DD3).

Second review cycle **skipped**: every change is a faithful application of the architect's
own findings (mechanism pins + the empirically-verified mount set), not new architecture.
Leg-1's `@requires_bwrap` gate remains the contract that re-proves DD2 in-flight.

## Leg Progress

_None yet._

---

## Decisions

_Runtime decisions not in the original plan will be recorded here._

---

## Deviations

_Departures from the planned approach will be recorded here._

---

## Anomalies

_Unexpected issues will be recorded here._

---

## Session Notes

- **Planning (2026-06-07)**: Flight 4 designed via `/flight`. Architecture interrogated
  against `main@ed63ce6`. Operator selected all recommended directions (box-by-default +
  `host_access` escalate; true isolation via minimal rootfs; per-session persist + per-call
  ephemeral; all three tools). 8 core legs + optional HAT. Flight-3 carry-forward debt
  bundled into `box-debt-and-docs` by shared surface.
