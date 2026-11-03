# Squawk 0265: the artifact actions still target Node.js 20

**Status**: deferred
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: —

## Report
Every job that uploads an artifact warns: "Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/upload-artifact@v4". The jobs still pass. `actions/download-artifact@v4` is the same generation. The current majors are `upload-artifact` v7.0.2 and `download-artifact` v8.0.2 (both 2026-10-07).

## Evidence
- The `v0.12.0` release run `40269216641`: three job annotations with the warning above.
- `.github/workflows/*.yml`: 7 uses of `actions/upload-artifact@v4` and 5 of `actions/download-artifact@v4`. `checkout@v5` and `setup-python@v6` already target Node 24.

## Corrective Action
*(written at completion)*. Bump both actions together, upload and download, across every workflow. Read each major's breaking changes first. For example, newer `upload-artifact` versions exclude hidden files by default, and some evidence paths may hold dotfiles. Then check that the artifact names `release.yml`'s `publish` downloads (`windows-installer`, `linux-packages`, `macos-dmg`) and the `evidence-*` pattern still resolve. Prove it with one `release.yml` dry run (`platforms` as needed) or a platform dispatch.

## Verification
- A dispatch shows no Node.js 20 annotation, and every artifact is uploaded and downloaded by name as before.

## Sign-Off
*(written at completion)*

## Disposition
- **Logged** by the Flight Director during the `v0.12.0` release run (Mission 32 Flight 4, leg 6), at the operator's mention. Deferred out of the release so the workflows are not changed mid-release.
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** deferred. Still valid: 7 upload and 5 download uses of the `@v4` actions. Verification needs a hosted dispatch. **Revisit trigger:** the next hosted `release.yml` dry run or platform-package dispatch.
