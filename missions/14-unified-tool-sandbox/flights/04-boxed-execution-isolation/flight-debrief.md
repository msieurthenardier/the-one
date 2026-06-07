# Flight Debrief: Agent-Selectable Execution Isolation (Boxed Mode)

**Date**: 2026-06-07
**Flight**: [Agent-Selectable Execution Isolation (Boxed Mode)](flight.md)
**Status**: landed
**Duration**: 2026-06-07 (single execution session — design, 8 legs, verification, commit, land)
**Legs Completed**: 8 of 8 core (`box-backend-isolation`, `boxed-profile-derivation`, `one-shot-boxed`, `session-boxed`, `model-selection-guidance`, `box-behavior-test`, `box-debt-and-docs`, `verify-integration`); optional `uat-and-alignment` HAT skipped by operator.

## Outcome Assessment

### Objectives Achieved

Delivered the mission's capstone capability: agent-selectable execution isolation on the shared sandbox seam. Box-by-default with a per-call `host_access` escalation; **true isolation** via a minimal read-only system rootfs + a host-bound scratch (= `$HOME`, the only writable space), no user filesystem, no network; per-call-ephemeral (one-shot) and per-session-persistent (PTY) scratch; across `shell` / `python_exec` / `shell_session_*`. Host-workspace execution (`host_access=true`) reproduces prior behavior exactly.

### Mission Criteria Advanced

- **Read-scoping** ("cannot read or write outside its permitted filesystem scope") — the long-deferred **read** half is now satisfied **for the boxed path**: a boxed process has no user FS at all. Host-workspace read-scoping remains a separate open concern (recorded in the mission known-issue).
- **Boxed-mode capability** (the mission's Flight-4 scope) delivered in full.
- Existing behavior preserved: host mode byte-identical; MCP un-regressed.

All flight checkpoints met. PR #107 (ready for review).

## What Went Well

- **Design-time empirical verification of DD2 paid off concretely.** The Architect ran the minimal-rootfs mount set in the live container at *design* time and discovered the base puts Python under `/usr/local` (so `/usr` must be bound wholesale, not `/usr/lib`). Had this not been caught pre-flight, leg 1 would have shipped a silently-broken Python runtime and forced a mid-flight architecture discussion. The Divert clause (fall back to writable-isolated) never fired.
- **Per-leg design review earned its keep every leg.** Catches that would otherwise have been mid-implementation bugs: the `read_file` cross-config keying (F3 carry, re-confirmed), the function-local `settings` import (eager `Settings()` breaks monkeypatch tests), `path_denylist=[]` explicitness (else the default 19-entry denylist fires), the `PtySession.close()`-owned single-locus cleanup + close-on-registration-failure, the PTY-HOME passthrough no-op, the `test_factory` exact-equality breakage from the BASE_PROMPT line. None reached `main` as defects.
- **Single-locus cleanup (DD3) held perfectly.** Binding scratch removal to `PtySession.close()` meant all five `entry.session.close()` sites (explicit, reaper, drain, cancel-drain, clear) clean up for free; the live test confirmed cleanup at the filesystem level.
- **The live behavior test found two real things a unit test couldn't** — a spec-design confound (step 3) and the model's `host_access` over-escalation tendency — exactly the kind of agent-behavior observation behavior tests exist for.
- **8-leg breakdown was right-sized and correctly sequenced** — `box-backend-isolation` first as the gating leg (its `@requires_bwrap` gate re-proved DD2 before any tool-layer work depended on it); the dependency graph (backend → derivation → one-shot/session → guidance → spec → docs → integration) needed no re-ordering.

## What Could Be Improved

### Process

- **Selection-judgment vs containment test design must be separated at first authoring.** Step 3 of the boxed behavior spec conflated a read-scoping *containment* check with a *selection-judgment* observable — its "read `~/.box_test_canary`" phrasing was structurally identical to the step-8 host task, so the agent correctly escalated and the literal expected result failed. Resolved cleanly via "update spec → re-run" (added "stay in default isolated mode — do not use host access"), but the lesson is: a containment checkpoint must remove the selection confound in its phrasing from the start.
- **Two recurring import-time footguns are still being caught at design review, not front-loaded in leg specs.** The function-local `settings` import (leg 3) is the second flight running where an import-time footgun was a design-review catch. It's now in `agents.md`, but a "common import footguns" entry + front-loading in future leg specs would prevent the re-catch.

### Technical

- **`host_access` over-escalation (accepted as-is) has two distinct causes needing two distinct responses.** (1) *Spec confound* — authoring, not the model (step 3). (2) *Genuine escalation eagerness* — the model escalated to read `/proc/net/dev`, which is **inside** the boxed mount set and needed no host access (step 4). Box-by-default is only as strong as the model's adherence; both interviewers flag that the **operator "disallow unboxing" control** (enforcement layer) and **sharper guidance** (intent layer) address *different* threat models and both are warranted. A concrete guidance gap: the `shell_session_send` description says the boxed scratch persists across sends but does NOT say "you do not need `host_access` to use a session scratch you already created" — a model that escalates at send time would undo the session's boxed isolation.
- **`_build_boxed_profile` hardcodes `network_allowed=False`** (does not read `ExecutionConfig`). Correct policy now, but it couples a future macOS/Seatbelt backend (M15) to a code change for any "boxed + network" profile. A `network_allowed: bool = False` parameter on `_build_boxed_profile` costs nothing now and removes the coupling.
- **`prune_box_scratch` single-process assumption** is documented in the function docstring but not in `SECURITY-MODEL.md`, and is silently unsafe under a future multi-worker deployment (`uvicorn --workers N` sharing `data_dir`).
- **Reaper-path scratch cleanup is asserted by structural argument, not a test** — the most complex session exit path has no dedicated `@requires_bwrap` test (explicit-close + registration-failure are tested).

#### Test metrics (Flight 4 vs Flight 3 baseline)

Full default suite (`-m "not requires_bwrap"`, container): **3051 passed**, 52 skipped, **5 failed / 486 errored — all pre-existing** (Playwright/Chromium-not-installed + live-LLM AIAT), wall-clock **417s**. `@requires_bwrap` arm: **31 passed**, **15.1s**.

Deltas vs the F3 debrief: full-suite **3015 → 3051 (+36)** — accounted for by the flight's new tests (box-isolation 7 + contract 8 + execution-tools helpers 6 + builtin-boxed 5 + pty-boxed 5 + session-tools 4 + description/guidance contract 16 + prune 5, net of bwrap deselections); `@requires_bwrap` **14 → 31 (+17)** = leg-1 (7) + leg-3 (5) + leg-4 (5), wall-clock 12.5s → 15.1s (+2.6s, the 17 new live-bwrap spawns). Full-suite wall clock 430s → 417s (within the noise the F3 debrief already flagged). **0 new failures.**

### Documentation

- `SECURITY-MODEL.md`: add the multi-worker `prune_box_scratch` caveat and the non-merged-usr `--symlink` portability note (the minimal-rootfs mount set is tied to the merged-usr Debian base).
- `_build_boxed_profile` docstring: note boxed network is unconditionally off (the SECURITY-MODEL says it; function-level readers won't look there).
- `agents.md`: add the `path_denylist=[]`-explicitness footgun and the "create-resource → register → close-on-registration-failure" session-tool idiom; name the function-local `settings` import convention.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Step 3 behavior-spec de-confounded mid-run ("update spec → re-run") | Its phrasing invited the agent's *correct* escalation, failing a containment check | Yes — separate containment vs selection-judgment phrasing at authoring time |
| `test_…_no_user_dirs` checks `home`/`app`/`var` absence, not `/root` | Container `HOME=/root`; `--bind scratch` auto-creates `/root` as the bind parent | Acceptable — the canary-unreadable test proves the real property; note the leg-spec ↔ test-assertion gap |
| PTY-HOME passthrough step dropped | No-op — bubblewrap sets `$HOME` from `profile.home`; the stated env-mutation point didn't exist | Acceptable — design-review caught it; clarifying comment added instead |
| `uat-and-alignment` HAT skipped | Operator: live behavior test (9/9) + `@requires_bwrap` cover acceptance | Yes — skip the HAT when the behavior test + bwrap suite cover the surface |
| `host_access` over-escalation accepted as-is | Containment held; escalating to read user-referenced files is defensible; compute stayed boxed | Partial — accept now; address via guidance + the operator control in Flight 5 |

## Key Learnings

- **Empirically verify a load-bearing feasibility premise at design time, not implementation time.** DD2's pre-flight in-container check turned a "probably works" into a deployment-specific mount set and pre-empted a silent Python breakage. This is the second consecutive flight where design-time empirical verification of the load-bearing DD changed the spec for the better (F3: DD4 orphan-window; F4: DD2 `/usr/local`).
- **Box-by-default's security is the model's adherence, not a guarantee.** Genuine isolation (containment) is solid and kernel-enforced; the *experienced* default depends on the model not over-escalating. This is precisely why the deferred operator policy control (`allow_host_access`) is an enforcement-layer necessity, distinct from guidance.
- **A behavior test that asserts agent *judgment* must phrase the task so exactly one choice is correct** — and must not let a containment property and a selection property share one checkpoint.
- **Single-locus resource cleanup beats N-locus.** Binding scratch cleanup to `PtySession.close()` (one place) rather than the registry entry (five places) made "cleanup on all exit paths" a structural guarantee instead of a coverage problem.

## Recommendations

1. **Flight 5 (Alignment) should ship the operator "disallow unboxing" control as a first-class leg** — `ExecutionConfig.allow_host_access: bool = True`; when false, the tool `execute()` forces `host_access=False` (or refuses with `[constraint]`) regardless of the model's argument; surfaced in the Studio/Administration tool-config UI alongside `FilesystemConfig`/`ExecutionConfig`. This is the operator enforcement backstop the over-escalation finding requires. *(Important — the security posture currently rests on model judgment alone.)*
2. **Tune the model guidance (separately from #1)** — add a sharper "if the task is self-contained computation, package installs, or reading from within the box's scope, stay boxed" framing, and fix the `shell_session_send` description gap (no `host_access` needed to use an existing session scratch). Re-run the selection-judgment behavior checkpoints against the new guidance to confirm. *(Important.)*
3. **Add a `network_allowed` parameter to `_build_boxed_profile`** (default `False`) to decouple a future boxed-network profile from a code change. *(Minor — cheap forward-proofing for M15.)*
4. **Add a `@requires_bwrap` reaper-path cleanup test** for boxed sessions (short TTL or direct `_reap_once`). *(Important — the most complex exit path is only structurally argued.)*
5. **Resolve the `SandboxError` import-cycle inversion (F3 DD1, still owed) in end-of-mission maintenance** before Mission 14 closes; and surface the multi-worker `prune` caveat + the non-merged-usr portability note in `SECURITY-MODEL.md`. *(Minor — hygiene before mission close.)*

## Action Items

- [ ] **Flight 5 / follow-up**: operator "disallow unboxing" control (`ExecutionConfig.allow_host_access` + tool `execute()` enforcement + tool-config UI). *(Highest-priority deferred capability.)*
- [ ] **Flight 5 / guidance**: sharpen box-by-default framing; fix the `shell_session_send` description (no `host_access` for an existing session scratch); re-run the selection checkpoints to confirm reduced over-escalation.
- [ ] Add `network_allowed` param to `_build_boxed_profile` (default `False`).
- [ ] Add a `@requires_bwrap` reaper-path boxed-session cleanup test.
- [ ] End-of-mission maintenance: resolve `SandboxError` import-cycle (F3 DD1); `SECURITY-MODEL.md` multi-worker prune caveat + non-merged-usr `--symlink` portability note; `_build_boxed_profile` docstring network note.
- [ ] `agents.md`: `path_denylist=[]` footgun; "create→register→close-on-failure" session idiom; name the function-local `settings` import convention.
- [ ] Cleanup (optional): the `sandbox-test` agent + `/root/.box_test_canary` fixture left on the running instance for behavior-test re-runs.
