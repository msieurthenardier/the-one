# Flight Log: Linux packages

**Flight**: [Linux packages](flight.md)

## Summary
Planning (2026-10-24). Not yet in flight.

---

## Planning Notes

### Flight Director Notes
- **Branch:** `flight/02-linux-packages`, off `origin/main` at `6f92fd5` (after #305-#308), in the Mission 32 worktree `/home/cprch/projects/the-one-worktrees/m32-installers`. Mission 31's checkout (`/home/cprch/projects/the-one`) is untouched.
- **Inputs carried in:**
  - **Flight 1 debrief recommendations:**
    - rec 1, rehearse hosted scripts by running them → DD10;
    - rec 2, the 3.11 failures → done, squawk 0251;
    - rec 3, measure the release runner's bundle → DD2 and leg 4;
    - rec 4, consider a split → the operator chose one flight, risk first.
  - **Flight 1 action items:**
    - the AppImage bundling → DD1;
    - the pystray fall-through → DD3;
    - hide-without-tray → DD4;
    - the metadata source → DD6;
    - fresh-VM checks → DD9;
    - a hosted build check → DD10;
    - the spike's fate and the packaging unit tier → DD8.
  - **The operator's decision:** "bundle the two libs".
- **Operator answers (2026-10-24):**
  - one flight, risk first;
  - quit with no tray through a launcher Quit action plus a one-time notice;
  - an AppImage self-integrates on first run;
  - QEMU-in-container VMs, the `.github/`-only PR, and a closing guided walk all approved.
- **Probes at planning:**
  - KVM works inside a container (`--device /dev/kvm`, API 12, VM created; nested `Y`);
  - the Ubuntu 26.04 and Debian 13 cloud images answer 200;
  - `ubuntu:24.04` digest `sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac`;
  - Flight 1's `m32/{ubuntu-26.04,debian-13}:{bare,baseline}` images are still present.
- **Design review cycle 1 (Architect, Opus): approve with changes.** Three high findings, each re-checked by the Flight Director against the code:
  1. Every Linux close deadlocks: the locked `closing` event, plus the blocking GTK geometry getters → DD12.
  2. On GTK, pywebview's `show()` re-hides a window created hidden; only `restore()` maps it. This is the cause of Flight 1's finding 5 → DD12.
  3. A wrong citation: `_select_port` decides "ours" by credential, not version, so an upgraded launch reaches the old running process → DD13.

  The medium and low findings were folded in:
  - the Ubuntu guest from the desktop ISO, and Debian `generic`;
  - polkit and the GUI-only install act, and `usb-tablet`;
  - TryExec semantics;
  - the action name;
  - the WebKitGTK-missing criterion → DD14;
  - the behavior test's session environment;
  - the hosted matrix reduced to bare images;
  - legs 2, 3 and 5 split (6 legs became 9), and the apparatus moved earlier;
  - the dynamic version deferred to Flight 4 (the mission flight list was updated);
  - the quit route's details;
  - DD1's location and best-effort handling;
  - DD3's host check and XEmbed note;
  - Wayland passes `None` for position;
  - `AppRun` as the integration locus;
  - `git safe.directory`;
  - the tool paths;
  - a separate notice marker;
  - the activation token.
- **Operator answers after cycle 1 (2026-10-24):**
  - a newer launch replaces an older running instance;
  - the Ubuntu guest comes from the desktop ISO's autoinstall;
  - a missing WebKitGTK gets a notification plus a `doctor` line;
  - the launcher action is named "Quit GleepGlorp AI".
- **Design review cycle 2 (Architect, Opus): approve with changes.** No stale cycle-1 text was found in the spec. Two new high findings, both re-checked by the Flight Director:
  1. Caching geometry from pywebview's `resized`/`moved` events records the wrong measure, because they include the client-side decorations on Wayland. `_on_closing` always runs on the GTK main thread (`destroy` → `idle_add(close_window)`), so DD12 reads `Gtk.Window` geometry directly.
  2. DD13 must wait for the old process's `pid` to exit, not for the port to free. uvicorn closes the listener before the lifespan drain, so a port-free wait reopens the M24 DD-3a race. The version comes from `/api/info`, and an old server with no quit route is focused at once.

  The medium and low findings were folded in:
  - the tray decision before any pystray import (`_xorg` connects at import);
  - DD11's host-GTK-first rule, and the no-display case;
  - the boot-race lock;
  - the asynchronous notice;
  - the no-`gi` notice path;
  - the state route's `mode`/`pid`;
  - the focus route as a plain `def`;
  - the three close states;
  - lazy imports moved to boot;
  - a VM relaunch probe before any hosted spend (the new leg 6);
  - GUI upgrade/remove and AppStream metainfo as premises;
  - upgrade coverage of providers and chats in the behavior test;
  - `WM_DELETE_WINDOW` in the smoke test;
  - the size round-trip;
  - legs 3 and 5 split (9 legs became 12).
- **The Flight Director's answers to the cycle-2 questions** (no third cycle: the max-2 rule, and the remaining items are concrete fixes, not disagreements):
  - DD13 applies on every platform (`shell.py` is shared), and Flight 4 confirms it on Windows beside Inno's close-applications step.
  - The test versions are N=`0.11.8` and N+1=`0.11.9.dev1` (dpkg `0.11.9~dev1`), with a unit test pinning PEP 440 against dpkg order.
  - The frozen `doctor` passes with no display at all (DD11).
- **Calls the Flight Director made without asking (standing autonomy mode, logged for alignment):**
  - the build container pin (DD2);
  - host-first soname preloading rather than `LD_LIBRARY_PATH` (DD1);
  - the tray-detection rules (DD3);
  - `GET /api/window/state` as the read path (DD4);
  - separate desktop ids for the AppImage and the `.deb`, and `AppRun` as the integration locus (DD5);
  - `packaging/product.toml`; the `pyproject` version pinned by a test, with the dynamic version deferred to Flight 4 (DD6);
  - Wayland size-only geometry (DD7);
  - the spike fold (DD8);
  - a 6-dispatch cap (DD10).

---

## Leg Progress

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
