# Leg: chat-reading-layout

**Status**: completed
**Flight**: [Chat Re-skin + Markdown Hardening](../flight.md)

## Objective

Re-skin the chat message layout to the v3 quiet reading vocabulary — refined user/agent turn distinction (tinted user bubble, not full-accent), agent prose on the reading surface, content column max-width — with composited-a11y gates for every washed surface carrying text.

## Scope (flight DD "Chat reading layout" authoritative)

- Keep the single-column `.messages` log (`role="log" aria-live="polite"`). User turns → compact right-aligned tinted block (`--accent-subtle`/translucent wash, NOT the current saturated `--accent` fill). **Preserve right-alignment** (`alignSelf` — peer-attribution/visibility tests assert it). Agent turns → near-full-width plain prose on the reading surface + muted attribution meta line. Content column max-width for readability. Tool/system messages stay distinct-but-quiet.
- **Composited-a11y gates** (F3 pattern, `_alpha_composite(fg,alpha,base)` in `test_design_tokens_a11y.py`, both themes): assistant-on-translucent, tool-on-surface-tool, peer-on-elevated, table zebra, telemetry-ghost — each authored as rgba-over-a-single-known-surface (no wash-over-wash / `color-mix()`); add each fg+alpha+base to the `design_tokens.py` mirror.
- **NEW composite gate**: the tinted user-bubble text (fg on `--accent-subtle`/translucent, both themes). Refresh the stale comment at `test_design_tokens_a11y.py:~188-191` tying `fg_on_accent`×`accent` to "the parent `.msg.user` rule" (the pair test stays valid — `.btn-filled-primary` still uses accent fill — only the comment goes stale).
- **Streaming-setup invariant** (do not break): if you wrap the bubble in a visual container, keep `currentStreamingMsg = bubble` (inner text-bearing element, not the wrapper) — `commitSafeBoundary`/`finalizeStreamingBubble` depend on `lastChild.nodeType===3`. Render seam untouched.
- Snapshot note: `test_snapshot_chat_with_messages` changes with the tint — local-only `--snapshot-update` regen (gitignored), NOT a committed-baseline break; regenerate, don't chase.

## Acceptance Criteria

- [x] User bubble tinted (not full-accent), right-aligned; agent prose reads on the surface; both themes visually verified on 8485
- [x] Every washed-surface-with-text has a composite-a11y gate green (both themes) incl. the new tinted-user-bubble gate; mirror updated; stale comment refreshed
- [x] `test_markdown.py` + `test_flow_markdown_chat.py` + the chat flow modules (`test_flow_chat.py`, `test_flow_new_chat.py`, `test_flow_chat_*`) green via run-tests.sh (alignment/live-region/class assertions preserved)
- [x] `make test-unit` green; guard/token/a11y slice green; ruff clean; sink baseline unchanged or shrunk (justify any JS diff); pixel snapshots regenerated locally (not committed)
- [x] Focus states unaffected (no interactive elements added here; if any, pinned focus + CDP evidence) [a11y gate]

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry (turn-distinction decisions, composite gates added, snapshot regen); leg `landed`; checked off in flight.md
