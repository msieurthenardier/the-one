# Leg: hat-and-alignment

**Status**: completed
**Flight**: [Ollama Pull shows the download size first](../flight.md)

## Objective
The operator observes every charter criterion against their real Ollama and the live registry, on a fresh scratch dev instance. The Flight Director guides one step at a time and fixes what surfaces.

## Context
- **Leg 1** (`pull-size-flow`) is committed as `d59786e` (draft PR #235).
- **Interactive leg:** there is no autonomous Developer or Reviewer cycle. Fixes that surface follow agentic-workflow's fix-versus-feature gate and its multi-surface trigger.
- **Live data at design (2026-10-07):** 445 entries.
  - **Cloud only:** for example `kimi-k3`, `mistral-large-3`.
  - **Not downloadable:** `wizardlm` and `qwen3.8-flash-next`.
  - **Largest:** `cogito-2.1:671b` at 1342.3 GB.
  - **Cold fill:** about 10 s, longer than the 8 s wait, so the loading message should show.

## Inputs
- **Operator's Ollama:** `http://localhost:11434`, v0.34.0, with `gpt-oss:20b` and `ministral-3:8b` installed. `qwen3:0.6b` is **not** installed, so the pull-then-delete leaves Ollama as it was.
- **HAT instance:** `THE_ONE_PORT=8486`, with a fresh scratch data directory under the session scratchpad.
  - It is never 8484, never the default data directory, and not 8485 (the existing preview instance).
  - `THE_ONE_OLLAMA_LIBRARY_TEST_JSON` is unset, confirmed in the process environment. Dev mode is on through the repo `.env`, so the unset variable is what keeps the seam out.
  - It is started by the Flight Director with `make up`. The operator opens it through a one-time handoff URL.

## Acceptance Criteria (HAT steps, as state transitions)
- [x] **1. [cold]** Add an Ollama provider at `http://localhost:11434`, then open its Models panel.
  - The Pull select is disabled, reading "Loading models and sizes. The first load takes a little while…".
  - The list appears by itself within about 15 s.
  - There are no error messages.
  - Installed models show decimal sizes (`gpt-oss:20b` about 13.8 GB).
- [x] **2. [list]** Scan the list.
  - Every entry has a size or a reason, for example `llama3.2:1b (1.3 GB)`, and `1b` comes before `3b`.
  - Cloud entries read "(cloud only, not downloadable)" and are greyed out and unselectable (`kimi-k3`).
  - `wizardlm` reads "(not downloadable)" and is greyed out.
  - `cogito-2.1:671b` shows its size.
- [x] **3. [big model] → [confirm] → [cancel]** Select `deepseek-r1:671b`.
  - Pull reads "Pull · 404.4 GB", and the status line reads "Download: 404.4 GB, from the Ollama registry."
  - Pull shows "Checking size…" briefly.
  - The modal reads "Pull deepseek-r1:671b?" and "This downloads 404.4 GB to {provider} (localhost:11434)." Cancel is focused.
  - Cancel closes the modal: nothing downloads, focus is back on Pull, and there are no errors.
- [x] **4. [small model] → [confirm] → [pull]** Select `qwen3:0.6b`, choose Pull, then "Pull 523 MB".
  - Progress shows, and focus is on the progress Cancel.
  - The pull completes, and `qwen3:0.6b` appears in the installed list at about 523 MB.
  - There is no error, and Refresh was disabled while the pull ran.
- [x] **5. [delete]** Delete `qwen3:0.6b` from the panel. It is gone from the list, and from `ollama list`.
- [x] **6. [restart] → [warm]** The Flight Director restarts the instance (`make restart`), and the operator reopens the panel.
  - The list appears **without** the loading message, which proves the disk cache.
  - `ollama-sizes.json` exists in the scratch data directory.
- [x] **7. [operator verdict]** The operator is satisfied with the wording and behaviour, or names what to change. Copy changes within DD6/DD7's meaning are an acceptable variation.

## Verification Steps
The operator performs each step in the browser and reports what they saw. The Flight Director checks server-side state where useful: the instance log, `ollama-sizes.json`, and `curl localhost:11434/api/tags`.

## Edge Cases
- **Ollama or the registry unreachable mid-HAT:** record it. If the registry fails, step 3 can instead cover the "Pull anyway" path.
- **A step fails:** diagnose it, fix it (through a spawned Developer), re-verify that step, then continue.

## Files Affected
None planned. Any fix is recorded in the flight log.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
