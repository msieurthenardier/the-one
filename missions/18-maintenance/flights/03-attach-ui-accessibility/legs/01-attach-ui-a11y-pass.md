# Leg: attach-ui-a11y-pass

**Status**: completed
**Flight**: [Attach-UI accessibility](../flight.md)

## Objective
Close the three WCAG 2.1 AA gaps the accessibility review found on the chat image-attach UI — a missing live-region, non-distinguishing accessible names across multi-staged images, and the remove-glyph contrast — in one coherent pass over `chat.js` + `components.css`.

## Context
Maintenance report 2026-07-10 accessibility findings (all new; the attach UI is otherwise solid — real buttons, aria-labels, focus-visible, alt text):
- **A1 (4.1.3 AA, Action Required)** — `attachmentsEl` (the staging region, `chat.js` `data-testid="chat-attachments"`) is rebuilt via `innerHTML` on every mutation with no `role="status"`/`aria-live`; SR users get no feedback on stage / silent non-image drop / remove / **cap rejection** (Flight 2 added `addMsg('system')` cap notices, which land in the chat log; the staging-region change itself is still silent). The project's own `pending-queued-chip` (`chat.js`, `aria-live="polite"`) is the precedent.
- **A2 (4.1.2 Level A, Action Required)** — identical `alt="Staged image attachment"` and identical `aria-label="Remove attached image"` for every staged image; with multi-image staging a user can't tell which remove button removes which. Interpolate an index (or filename).
- **A3 (1.4.3 AA, Advisory)** — `.chip-remove` resting color `--status-danger-muted` over `--accent-translucent` ≈ 4.14:1 in light theme (< 4.5:1; hover + dark pass). Use `--status-danger` resting.

## Inputs
- `the_one/interfaces/web/static/js/areas/chat.js` — the staging region (`attachmentsEl`), the thumbnail `alt`, the remove-button `aria-label`, `renderAttachments()`.
- `the_one/interfaces/web/static/css/components.css` — `.chip-remove` (~line 587).
- `docs/ui-testid-registry.md` — if a testid is added.
- `tests/browser/test_flow_chat_image_attach.py` — the existing Playwright attach suite (extended by Flight 2) to add DOM assertions.

## Acceptance Criteria
- [x] **A1** — stage/remove of images is announced to SR users **via a separate visually-hidden `aria-live="polite"` status element** that emits a short *delta* sentence per mutation (e.g. "Image staged" / "Image removed" / "3 images staged"). **Do NOT** make the visible `.chat-attachments` chicklet row itself the live region (design-review [1]): it fully rebuilds via `innerHTML` on every mutation, so removing 1-of-N would re-announce all N remaining chips — noisy. A DOM assertion confirms the hidden live-region element exists and updates on stage/remove. (Note: cap-rejection notices already announce via the message log's existing `role="log" aria-live="polite"` — this leg only closes the staging-row silence.)
- [x] **A2** — each staged image's thumbnail `alt` and its remove-button `aria-label` include a distinguishing token (index `N` — or filename if readily available), so no two staged images share an identical accessible name. DOM assertion confirms distinct names across ≥2 staged images.
- [x] **A3** — `.chip-remove` resting color uses `--status-danger` (not `--status-danger-muted`) in light theme; re-verify the computed contrast ≥ 4.5:1 (assert the resolved token/color, not a screenshot).
- [x] **Browser tests** (functional/DOM assertions, NOT pixel snapshots — snapshot baselines are gitignored): extend `tests/browser/test_flow_chat_image_attach.py` to assert the live-region attribute on the staging region and the distinct accessible names across two staged images.
- [x] No regression to the Flight 2 cap behavior or the existing attach flow; `ruff`/format clean (JS isn't linted by ruff, but keep the Python test edits clean).
- [x] `git diff` limited to `chat.js`, `components.css`, `tests/browser/...`, `docs/ui-testid-registry.md` (if touched), + flight artifacts.

## Verification Steps
- Run the browser suite: `make test-browser` (or scoped to `tests/browser/test_flow_chat_image_attach.py`, `-m browser`, `THE_ONE_DEV_MODE=true`) — green incl. the new a11y assertions.
- Confirm the remove glyph resolves to `--status-danger` in light theme and computes ≥ 4.5:1.

## Implementation Guidance
1. **A1**: add a dedicated **visually-hidden** `aria-live="polite"` status element (an `.sr-only`/off-screen `<div>` near the composer — check for an existing visually-hidden utility class first, else add minimal off-screen CSS). On each stage/remove, set its `textContent` to a short delta ("Image staged" / "Image removed" / "N images staged"). Filename isn't captured at stage time (design-review), so a count/generic delta is correct. **Do NOT** put `aria-live` on the visible `.chat-attachments` row — it fully rebuilds via `innerHTML` on every mutation, so a container live-region would re-announce all N chips on any change (design-review [1]). Mirror the `aria-live="polite"` attribute style of `pendingQueuedEl` (`chat.js:61`). Fix the now-stale comment at `chat.js:1593-1596` ("will announce these once Flight 3 lands") — the message log (`role="log" aria-live="polite"`, `chat.js:257`) has always announced cap notices; only the staging-row silence is new.
2. **A2**: in `buildAttachmentChip(img, idx)` / `renderAttachments()`, interpolate the **1-based** index (`idx + 1`) into both `thumb.alt` (`chat.js:175`) and the remove-button `aria-label` (`chat.js:188`) — e.g. `alt="Staged image 1"`, `aria-label="Remove staged image 1"`. `idx` is already in scope (used for `data-attachment-index`).
3. **A3**: change `.chip-remove` resting `color` from `--status-danger-muted` to `--status-danger` in `components.css:587`. Blast radius verified narrow (admin/studio `.chip-list-editor .chip-remove` have a more-specific `--accent` override at `admin.css:425-439`; the design-language showcase correctly reflects the new color). Do NOT touch the AAA reduced-motion transition (A4 deferred).
4. Extend `tests/browser/test_flow_chat_image_attach.py` with DOM assertions: the hidden live-region element exists + updates on stage/remove (A1); distinct `alt`/`aria-label` across two staged images (A2).

## Edge Cases
- The hidden live-region announces one delta per mutation — avoids the container-rebuild re-announce-all problem.
- Single staged image — the index token is still fine (`Staged image 1`).

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat.js`, `the_one/interfaces/web/static/css/components.css`, `tests/browser/test_flow_chat_image_attach.py`, possibly `docs/ui-testid-registry.md`.

---

## Post-Completion Checklist
- [x] All acceptance criteria verified
- [x] Browser tests passing (DOM assertions, no snapshots)
- [x] Update flight-log.md with a Leg Progress entry
- [x] Set this leg's status to `landed` (methodology: `completed` follows batch-review + commit)
- [x] Check off this leg in flight.md
- [x] **Only leg** — batch-reviewed (code + accessibility, both confirmed; 3 non-blocking polish items folded in: contrast regression gate, restored hover affordance, comment fix), committed/PR
