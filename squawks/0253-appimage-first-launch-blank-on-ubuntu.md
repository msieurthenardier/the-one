# Squawk 0253: the AppImage's first launch on Ubuntu shows an empty window for about 20 s

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-24
**Completed**: —

## Report
On a fresh Ubuntu 26.04.1 GNOME desktop, the first launch of the AppImage (`GleepGlorp_AI-0.11.9.dev20-x86_64.AppImage`, double-clicked in Files) opens the window within about 5 s. The window body stays empty, and the dock shows a generic gear icon, for about 20 s; then the Chats page ("Hello.") renders. On Debian 13 the same AppImage renders by +5 s. The `.deb` on Ubuntu rendered in under 30 s, with no long blank reported.

It was seen in Mission 32 Flight 2's `linux-package-install` behavior test (variant ubuntu-appimage, step 2) and is worth a look before release. A user may think the app is broken. It may share a cause with Flight 1's blank first paint on macOS (Flight 3).

Reproduce:
1. Use the Flight 2 VM apparatus: `packaging/linux/vm/vm.sh up ubuntu --visible`.
2. Copy an AppImage in, and make it executable in Files.
3. Double-click it, and take screendumps at +5, +12, +20 and +30 s.

## Evidence
- The run log `tests/behavior/linux-package-install/runs/2026-10-24-20-34-28.md`: the Executor closing summary, "ubuntu-appimage step 2: at +5 s the window was up but its body was empty and the dock icon was a generic gear. At about +20 s it showed 'Hello.'".
- Candidates to check, unverified:
  - the first-run AppImage mount plus the bundle's cold import (the embedding model, the vector store) delaying the server's first response;
  - the window being shown before the server answers (`_wait_until_serving` covers the webview path);
  - WebKit's first process start with software rendering.

  Compare with the `.deb` on the same guest, and with a second launch.

## Corrective Action
*(written at completion)*

## Verification
- On a fresh Ubuntu guest, the first AppImage launch shows the splash, or a rendered page, with no long empty window. Or the cause is shown to be environmental (the VM's software rendering) and documented.

## Sign-Off
*(written at completion)*

## Disposition
- **Logged** by the Flight Director at Mission 32 Flight 2's `linux-hat`, on the operator's decision ("Squawk the 20 s blank").
- **Id note:** Mission 31 was told to take its next squawk id from 0252, so this one takes 0253 to avoid a collision.
- **Escalate if** the fix needs a change to the desktop launch sequence's design.
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** deferred. It needs the fresh-VM apparatus. **Revisit trigger:** the next Linux VM run (`packaging/linux/vm/vm.sh up ubuntu --visible`), or the next release's pre-release check.
