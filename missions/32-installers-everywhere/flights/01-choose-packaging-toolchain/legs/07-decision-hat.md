# Leg: decision-hat

**Status**: ready
**Flight**: [Choose the packaging toolchain](../flight.md)

## Objective
A guided session with the operator, run by the Flight Director. The operator:
- tries the Briefcase MSI over their real Windows install (the `windows-cost` morning guide);
- sees each surviving Linux build's window;
- reads the evidence and the Flight Director's recommendation;
- makes the go/no-go toolchain decision, which is then recorded and applied per DD8.

## Context
- **This is a HAT leg:** no autonomous Developer implementation. The Flight Director presents one step at a time, waits for the operator's result, and fixes anything inline (fix-vs-feature gate).
- **Flight decisions:** DD2 (the operator decides; the evidence table informs and does not compute), DD7 (the operator's Windows install, with backup and rollback), DD8 (the decision record; keep the winner's recipe under `packaging/`, remove the loser; hybrids per platform).
- **Inputs:** the flight log's Evidence Table (Linux, macOS, Windows rows), the `windows-cost` paper half and morning guide, the macOS comparison, the upkeep paragraphs, and the Flight Director's decision brief (drafted in the flight log's Decision section before the session, clearly marked as a recommendation).
- **The overnight decisions to align on first** (the operator delegated them, 2026-10-24; each is listed in the Flight Director Notes):
  - macOS run 2 was candidate A only;
  - the MSI is per-user, built as `0.11.9.dev1`;
  - squawk 0250 is filed;
  - PR #305 was merged with `pip-audit` red.

## Steps (presented one at a time)
1. **Align on the overnight decisions** (the list above). The operator confirms or redirects. Any redirect is logged.
2. **The Windows try** (the `windows-cost` morning guide, steps 1-6):
   - quit the app, then back up;
   - download the MSI and check its hash;
   - install it per-user;
   - go through the checklist;
   - roll back if the operator wishes.

   Record each checklist answer in the flight log under `windows-cost`, which completes that leg's AC6 together with the hosted results.
3. **The Linux windows.** Through forwarded WSLg, in the target containers (`packaging/spike/check.sh`'s window phase, or a short manual `docker run`), open:
   - A's `.deb` on Ubuntu 26.04;
   - B's `.deb` on Ubuntu 26.04;
   - A's AppImage on Ubuntu 26.04.

   The operator looks at each window. Their remarks are logged. Debian is optional.
4. **The evidence walk:** the Evidence Table, the upkeep comparison and the hosted-minutes per release, then the decision brief.
5. **The decision.** The operator chooses: A, B, or a named hybrid per platform. Their words are recorded in the flight log's Decision section, with the reasons.
6. **Apply DD8:**
   - strike through the mission's "Which toolchain?" open question, with a link to the decision;
   - add a pointer to the decision in the BACKLOG seed;
   - remove the loser's files from `packaging/` (per platform for a hybrid); mark the winner's READMEs as the Flight 2 starting point;
   - list the patches the winner needs, and the risks handed to Flights 2-4.

   This is a Developer spawn for the file removals; the Flight Director edits the artifacts.

## Acceptance Criteria
- [ ] The operator has confirmed or redirected each overnight decision, and the result is logged.
- [ ] The Windows try's checklist results (or the operator's choice to skip it) are logged under `windows-cost`.
- [ ] The operator's decision and reasons are in the Decision section, in their words.
- [ ] DD8 is applied: the mission and BACKLOG pointers are in place, only the winner's recipe remains under `packaging/`, and the handed-on patches and risks are listed.

## Verification Steps
- The flight log's Decision section and the windows-cost entry.
- `ls packaging/` and `git diff --stat` for the removals.
- The mission's open question and the BACKLOG pointer.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
