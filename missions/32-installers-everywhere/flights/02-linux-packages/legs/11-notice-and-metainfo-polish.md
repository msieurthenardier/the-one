# Leg: notice-and-metainfo-polish

**Status**: completed
**Flight**: [Linux packages](../flight.md)

## Objective
Fix the two cosmetic findings from leg 6 (operator, 2026-10-24):
1. The no-tray notice fits GNOME's notification banner without being cut off.
2. The software centres show the brand icon (and, where the store reads it, a publisher) for the `.deb`.

## Context
- **Leg 6 found:**
  - the no-tray notice (`shell.py`, the text "GleepGlorp AI is still running. Open it again to bring it back, or right-click its icon and choose Quit GleepGlorp AI.") is truncated with "…" in GNOME's banner;
  - Ubuntu's App Center shows the metainfo summary but a generic icon and "Unknown publisher".
- **The metainfo** (`packaging/linux/metainfo.xml.in`) has a `<developer>`, but no `<icon>`. The packages ship only a 512 px icon (`usr/share/icons/hicolor/512x512/apps/<desktop_id>.png`).
- **Low risk:** one string, one template, and the icon install step in `build-inner.sh`. The flight-end checks (leg 12's VMs) verify the look.

## Acceptance Criteria
- [ ] **AC1** — the no-tray notice is split into a short summary and a short body. Summary: "GleepGlorp AI is still running". Body: "Open it again to show it, or right-click its icon to quit." (the exact wording may be tuned, but stay at or under 60 characters for the body). The tests that pin the text are updated; flight DD4's text is noted as superseded in the flight log, not rewritten.
- [ ] **AC2** — the metainfo gains `<icon type="stock">@DESKTOP_ID@</icon>`. The packages install the icon at 64, 128, 256 and 512 px under `hicolor/<n>x<n>/apps/`, resized at build time from the 512 px source with Pillow, which is in the build image's venv. `appstreamcli validate --no-net` still exits 0, and `desktop-file-validate` still passes.
- [ ] **AC3** — `make test-unit` passes (12 skips); `ruff`; `shellcheck` on `build-inner.sh`; a build of one version shows the four icon sizes in `dpkg-deb -c` and in the extracted AppImage; the audit still PASSes.
- [ ] **AC4** — whether App Center now shows the brand icon and a publisher is checked in leg 12's VM run, not here. Record the outcome there. If App Center still shows a generic icon for a local `.deb`, that is a known App Center limit, recorded and not chased.

## Files Affected
- `the_one/interfaces/desktop/shell.py` (the notice constant), its tests
- `packaging/linux/metainfo.xml.in`, `packaging/linux/build-inner.sh`
- `missions/32-installers-everywhere/flights/02-linux-packages/flight-log.md` (own section)

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
