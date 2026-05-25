# M11 Criterion Coverage

Living artifact mapping each M11 mission criterion to evidence (specific tests, leg references, debrief sections, HAT outcomes).

**Status vocabulary**:
- `closed-by-Fn` — criterion fully satisfied by flight Fn; evidence cited.
- `partially-closed-by-Fn` — criterion structurally complete via flight Fn but with a documented residual gap (deferred sub-item, follow-on HAT, etc.).
- `structurally-complete-pending-HAT` — code/UX shipped; verification waits on a real-traffic or operator-driven HAT.
- `open` — not yet addressed by any landed flight.

**Maintenance contract**: each flight's debrief MUST update the rows it affected — new evidence pointers, status transitions, and the `Last touched` column. The `Last touched` column makes drift-detection mechanical at debrief time; an unchanged `Last touched` after a flight that should have moved a row is a methodology violation that the flight-debrief skill surfaces in its own debrief. This applies the `mechanical-fallback-prompt-truth-pairing` convention recursively (the artifact IS the mechanical truth source for the per-flight criterion-coverage prompt). Seed state captured as-of 2026-05-23 (F3 closed, F4 starting).

| # | Criterion (excerpt) | Status | Evidence | Last touched |
|---|---------------------|--------|----------|--------------|
| 1 | Discord-shaped creation form (bot token, intents, guild scoping, invite-URL helper) | closed-by-F1 | F1 L1-L7; `tests/browser/test_flow_studio_discord_account_creation.py`; F1 debrief | F1 |
| 2 | Discord vocabulary (username/server/channel/role) replaces generic peer/group in UI | open | — | — |
| 3 | Allowlist editor uses searchable dropdowns from live bot view (stale-entry indicator) | partially-closed-by-F3 | F3 L4-L6a; stale-entry indicator deferred to F9 per F3 debrief + F4 recon R8 | F3 |
| 4 | Routing-rules editor uses same dropdown data source as allowlist | partially-closed-by-F3 | F3 L4 + L6b; stale-entry indicator deferred to F9 | F3 |
| 5 | Multi-user routing HAT — ≥3 distinct users through same channel | open | — | — |
| 6 | Multi-channel routing HAT — ≥3 channels each defaulting to different agents | open | — | — |
| 7 | Multi-peer / multi-agent routing HAT against real Discord traffic | open | — | — |
| 8 | Pairing question resolved (stay / Discord-native approval / both) | open | — | — |
| 9 | Operator can detach attached agent from Connectors screen without Studio nav | open | — | — |
| 10 | All six slash commands (`/agents`, `/talk_to`, `/whoami`, `/new`, `/reset`, `/help`) HAT-validated | open | — | — |
| 11 | End-to-end Chrome-driven repeatable HAT script in-repo | open | — | — |
| 12 | Mentions-aware response policy in inbound dispatcher (per-agent / per-channel modes) | open | — | — |
| 13 | Peer-name attribution end-to-end (gateway → dispatcher → session → Chat UI) | closed-by-F6 | F6 L1 `Message.peer_name` + codec emit-when-non-None (`tests/test_db_codec.py::TestMessagePeerNameCodec` 9 tests); F6 L2 `messages_to_ui_events` user-event projection (`TestMessagesToUiEventsPeerName` 7 tests); F6 L3 dispatcher post-step binding co-located with `tag_post_step_visibility` (`test_dispatch_inbound_persists_inbound_with_peer_name_from_envelope` + `test_dispatch_inbound_broadcasts_carry_peer_name`); F6 L4 Chat UI peer-bubble rendering + WCAG 1.3.3 sr-only label (`tests/browser/test_flow_chat_peer_attribution.py`); F6 L5 HAT outcome `looks-good` (1 round; Steps 1-6, 8, 10 pass; Steps 7+9 skipped with wire-shape pinning by browser test) | F6 |
| 14 | Operator-editable per-account system-prompt directive surface | closed-by-F2 | F2 L1-L4; `tests/browser/test_flow_studio_connector_account_directive_section.py`; F2 debrief | F2 |
| 15 | Audit-log inspector surface renders `session_metadata["routing"]` | open | — | — |
| 16 | Lifecycle pool refactored from sentinel-wrapper to account-keyed primitive | closed-by-F2 | F2 L5-L6; `the_one/connectors/_pool.py:account_acquire`; F2 debrief | F2 |
| 17 | Outbound rate-limiting + backpressure live-load HAT | open | — | — |
| 18 | Fresh operator under fifteen minutes (operational "easy to use" definition) | open | — | — |
| 19 | Full working-day daily-driver run without operator intervention | open | — | — |
