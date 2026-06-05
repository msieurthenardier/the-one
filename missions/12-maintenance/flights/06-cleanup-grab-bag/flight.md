# Flight: Cleanup Grab-Bag

**Status**: landed
**Mission**: [Maintenance (Post-M11)](../../mission.md)

## Contributing to Criteria
- [ ] A shared `_StreamAccumulator` removes the OpenAI/Ollama streaming-parser duplication (P5)
- [ ] A shared `App.api.fetchJson` helper replaces the duplicated fetch-error-parsing blocks (Q4)
- [ ] Documentation scrubbed: DOC1 phantom event, DOC2 stale Slack/F9 refs, DOC3 `.env.example` vars, DOC4 `os.environ` tunables, DOC5 agents.md anchors
- [ ] 3 stale merged remote branches deleted (G1); oversized brand PNGs re-exported (G2)

---

## Pre-Flight

### Objective
Land the low-risk, no-prerequisite tidy items in one flight: the streaming-parser extraction (P5), a shared JS fetch helper (Q4), the documentation/env scrubs (DOC1–DOC5), and git/asset hygiene (G1, G2).

### Open Questions
N/A — all items are concrete.

### Design Decisions

**P5 must be behavior-preserving**: The `_StreamAccumulator` extraction is a pure refactor — existing OpenAI/Ollama/Anthropic provider tests must stay green *unchanged*. No new behavior, no new constants; the byte-emitter heuristic is centralized exactly as-is.

**Q4 helper centralizes the existing logic, doesn't change it**: `App.api.fetchJson` captures the current ok-check + 422-`detail` flatten + snippet-fallback behavior verbatim; call sites switch to it without changing what the user sees on error.

**Docs are corrected to match reality**: DOC1's phantom event is corrected to describe the actual optimistic-update + poll mechanism (not implemented). DOC2/DOC3/DOC4/DOC5 are factual scrubs.

**Git/asset hygiene is a separate leg**: branch deletion (G1) is a remote operation; PNG re-export (G2) is an asset change. Both are independent of the code/doc legs.

### Prerequisites
- [ ] Network access for remote branch deletion (G1).
- [ ] Coordinate `.env.example` edits with Flight 05 (DOC4 + the new session-TTL var touch the same file).

### Pre-Flight Checklist
- [ ] All open questions resolved — N/A
- [ ] Design decisions documented
- [ ] Prerequisites verified
- [ ] Validation approach defined
- [ ] Legs defined

---

## In-Flight

### Technical Approach
Four independent legs: P5 (extract `_StreamAccumulator`), Q4 (extract `App.api.fetchJson`), DOC1–DOC5 (doc + env scrub), G1+G2 (git + asset hygiene). Each is self-contained and individually verifiable; they can land in any order.

### Checkpoints
- [x] Streaming-parser duplication removed, provider tests green unchanged
- [x] Shared fetch helper in use, error rendering unchanged
- [x] Docs/env accurate
- [x] Stale branches gone (already), PNGs re-exported (`_small` 512×512)

### Adaptation Criteria

**Divert if**:
- The `_StreamAccumulator` extraction can't be made provably behavior-equivalent without test changes — stop and treat the streaming refactor as its own flight (it would then be a behavior change, not a tidy).

**Acceptable variations**:
- Splitting or merging the doc/git legs if scope shifts.

### Legs
- [x] `01-streaming-accumulator-extraction` - Extract shared `_StreamAccumulator` (P5)
- [x] `02-fetch-json-helper` - Extract shared `App.api.fetchJson` (Q4)
- [x] `03-docs-and-env-scrub` - DOC1–DOC5 corrections
- [x] `04-git-and-asset-hygiene` - G1 (stale branches) + G2 (brand PNGs)

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing (provider/streaming unchanged + browser 422 path; full suite)
- [x] Documentation updated (DOC1–DOC5; agents.md anchors)

### Verification
Provider tests green unchanged (P5 behavior-preserving); studio JS error rendering unchanged (Q4); `grep` confirms the phantom event / stale Slack refs / dead env vars are gone (DOC1–DOC4); `git branch -a --merged main` shows the 3 branches deleted (G1); brand PNGs are meaningfully smaller (G2).
