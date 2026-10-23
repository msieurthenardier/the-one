# Flight Debrief: Live Chats list and connector chats

**Date**: 2026-10-23
**Flight**: [Live Chats list and connector chats](flight.md)
**Status**: completed
**Duration**: 2026-10-22 (diagnosis, charter, design, two Architect reviews, three legs) - 2026-10-23 (flight review, gate, commit, PR #302)
**Legs Completed**: 3 of 3
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
A Chats list left open now follows every chat change: connector chats, other tabs, deletes, renames and purges. An open connector chat shows a finished connector turn without a reload. The work landed as `fe7d13e` and `f5d7d0c` on `sortie/05-live-chats`, in PR #302 (ready for review, not merged).

The pieces:
- **Signal.** One in-process "sessions changed" signal is raised by the db layer after commit (`the_one/db/_session_changes.py`).
- **Push.** A 250 ms coalesced `sessions_changed` push of the whole list goes to every WebSocket (`_SessionsPushListener`, the socket registry in `the_one/sessions/_broadcast.py`).
- **Connector turn end.** A `session_updated` frame is sent after a connector turn releases its lock (`dispatch_inbound`), and the client re-joins on it.
- **Data loss.** A content-fingerprint re-sync under the session lock fixes the data loss that planning found. Before it, a web send after a connector turn overwrote that turn.
- **Pre-existing defects fixed by the same re-join:**
  - A thinking indicator stuck after a mid-turn join.
  - A message held during a connector turn that was never sent.

### Charter Criteria Assessment
| Criterion | Result | Note |
|---|---|---|
| 1. A connector-created chat appears in an open Chats list within a few seconds, with no user action | **Met** | Browser tests drive a real `dispatch_inbound` through the stub seam and wait for the row (`test_flow_chat_live_updates.py`). Falsified: with the signal disabled, all five push tests fail. |
| 2. A finished connector turn shows in the open pane without a reload | **Met** | Four browser tests: reply shown with the composer kept, mid-turn join clears thinking, held message sent, scroll kept for an unpinned reader. Falsified by renaming the frame. |
| 3. A browser message after a connector turn keeps the connector turn in history | **Met** | Unit tests (f, g) plus a browser read-back over `GET /api/chat/sessions/{id}`. Falsified by removing the re-sync call. Edges recorded below (resume-after-auth, REST `/api/chat`). |
| 4. A pushed list update never moves the user (no auto-open, route or composer change) | **Met** | The push only primes the lists. Tests: the empty welcome state does not auto-open; the route and composer are untouched; an armed delete survives a push. |

## What Went Well
- **Planning found the worse bug.** The operator reported a stale list. Reading `_locked_message_processing` showed silent data loss beside it, and the charter took it in as criterion 3. That fix landed first (leg 1), so it was proven before the liveness work built on the same files.
- **Design review caught real defects before any code existed.**
  - Architect review 1 (high): the held-message dispatch on re-join; the re-sync in its own `try/except`; a content fingerprint instead of `updated_at`.
  - Architect review 1: a `finally` broadcast; a distinct push frame (inert to a cached old `chat.js`, squawk 0085).
  - Architect review 2: dropped the pause-skip, which would itself have lost a connector turn (`Agent.step` clears the deferral anyway).
  - The three per-leg Developer reviews each added test apparatus details (a second peer, a `delay_ms` fixture, Enter rather than Send while busy). No leg needed a second implementation pass.
- **Falsification in every leg.** Each leg disabled its own change and watched its tests fail.
- **The stub connector seam paid off.** It was never driven by a browser test before. Leg 1 built the apparatus (`StubConnectorApp`, `seed_stub_connector`, `stub_inbound` retrying 409), and every later test reused it. No HAT was needed.
- **Worktree isolation worked.** Another workstream (Mission 31 Flight 3) ran in the main checkout throughout, and nothing collided. The gate ran two lanes wide so the host stayed under its 3-lane cap.
- **Low cost to the gate.** The chats lane gained ten tests and solo stays at 343 s (sortie 04: 343 s with 181 tests). The new file runs in about 39 s and was clean in four runs.

## What Could Be Improved

### Process
- **The prerequisites checked only that the venv imported the worktree, not that its dependency set was reproducible.**
  - A fresh `pip install -e '.[all-llms,dev]'` resolved newer unpinned dependencies, and 7 unrelated unit tests failed: `test_credential_gate` (the oauth callback route), `test_mcp_wire_shapes`, 4× `test_openrouter_wire_level`, `test_vector_store[usearch-i8]`.
  - The Flight Director triaged this mid-flight and pinned the venv to the main venv's `pip freeze`.
  - Two problems: a fresh install of this project is not reproducible today, and some tests (or code) break under current releases of its dependencies. The second will reach `main` on the next fresh install or CI image rebuild.
- **Test apparatus assumptions were found in the leg, not in planning:**
  - The stub resolver keys DM chats on `channel_id`, so two peers on the same empty channel share one chat.
  - A send during the automatic re-join's `joining` state is ignored. This forced a change to the leg-1 test.
  - Both were cheap to absorb. A DD8 line such as "what does the resolver key a chat on?" would have caught the first.
- **The landing gate's lane times are not comparable to priors.** It ran `--parallel 2` beside another workstream's browser lane, and six lanes read over budget. Re-measured solo, chats is 343/450. The over-budget flags were contention, not a regression from this sortie, but the gate gave no way to tell that without a re-run.

### Technical
- **Client flag set in `chat.js`.**
  - `chat.js` grew from 2268 to 2399 lines. It now holds four interacting closure flags (`ownTurn`, `refreshAfterTurn`, `updateRejoin`, `refreshAfterJoin`) cleared through `clearLiveRefresh` from about eight sites.
  - In effect it is a second, hand-rolled state machine beside `session-state.js`. A missed clear site would leave re-joins deferred for that session, and the flight review had to verify every clear site by hand.
  - Fold it into `session-state.js`, or a `live-refresh.js` module with its clear sites pinned, when this area is next touched.
- **The session lock is not yet the single serialisation point for session writes.** The recorded edges share one class: a writer or reader outside the lock or the re-sync.
  - `_resume_paused_session` runs without `session_locks`.
  - REST `/api/chat` has no lock and no re-sync.
  - A second tab's re-join drops a pending deferral.
  - A failed save leaves the fingerprint stale (the next turn adopts the stored row).
- **The full-list push carries no sequence number.** A push and a `list_sessions` reply can arrive out of order; both are whole snapshots, and the window is negligible at single-user scale. If chat counts grow, push changed rows instead: the repository knows which ids changed.
- **The signal, listener and socket registry are in-process.**
  - That is correct for `the-one serve` and the desktop app, where uvicorn runs on a thread in the same process.
  - A second server process, or the CLI writing to the same database, produces no push.
  - The assumption is not stated in `agents.md`.
- **Repository notify contract.**
  - `tests/test_session_changes.py` pins today's notifying methods. A new `ChatSessionRepository` write method would still need a matching notify call and a test row.
  - A reflective guard (every public mutator is either in the notify list or the explicit non-notify list) would make the list exhaustive.
- **`dispatch_inbound`'s `try/finally` re-indented about 90 lines**, which makes blame on that block less useful. This is harmless.
- **Rough edges, user-visible:**
  - An Enter pressed during the brief automatic re-join does nothing (the text stays in the composer, with no feedback).
  - A reader scrolled up gets no "new messages below" cue when a connector reply lands.
  - A chat deleted elsewhere keeps its pane open until the user moves.

### Documentation
- `the_one/agents.md` covers the protocol rows, the frame gate, the re-sync, "Live Chats list push" and "Live open connector chat". The CLAUDE.md store paragraph covers the push and the re-join.
- Still missing:
  - The single-process assumption.
  - The general patterns this sortie used (see Key Learnings) as named Project Conventions.
  - A note for test authors that stub DMs need a per-peer `channel_id`.

## Test Metrics
Measured at the debrief on `f5d7d0c`, worktree venv (pinned to the main venv's freeze):
- **Unit** (`-m 'not browser and not live and not pixel and not requires_bwrap'`, no netns):
  - 6756 passed, 12 skipped (the documented count: 11 platform skips, plus 1 missing-locale skip), 0 failed.
  - 293.8 s in pytest, 5m05s wall.
  - The landing gate under netns gave 6754 passed / 14 skipped, also the documented count for that mode.
  - Priors: sortie 03 6019 / 194.8 s; sortie 04 6653 / 288.6 s; M31 F2 6717 / ~300 s.
  - This sortie added 3 unit files (36 tests across the flight's unit files) with no visible time cost. The 195 s to 294 s creep predates it (squawk 0234, open).
- **Chats lane** (`--lane chats`, netns, `THE_ONE_REQUIRE_WEBKIT=1`, solo):
  - 191 passed, 0 failed, 343 s.
  - Priors: sortie 04 181 / 343 s; M31 F2 348 s.
  - Flat, with ten more tests.
- **Flake check:** `test_flow_chat_live_updates.py` passed 10/10 in three further isolated runs (38.4 s, 38.9 s, 39.0 s), plus the lane run. No flakes seen.
- **Timing margins.** Its tightest waits are a thinking indicator within 2.5 s and a queued chip within 3 s, against a ~4 s mock delay. That leaves about 1 s of margin on a loaded host, the likeliest place for a future flake. Derive those waits from the delay if one appears.
- **Full gate at landing** (`--parallel 2`, shared host):
  - All ten lanes rc=0, total 2106 s.
  - Not comparable to sortie 04's 1052 s or M31 F2's 1590 s, which ran 3-wide on a quiet host.
  - The six OVER-budget readings (chats 466/450, mcp 465/450, providers 442/420, agent-tabs 320/300, settings 301/300, shared 340/300) are dominated by contention: chats re-measured solo at 343 s.
  - Lanes already near budget in earlier debriefs (shared, settings, agent-tabs, library) should be re-measured at `--parallel 3` on a quiet host before any re-budget.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| DD4's pause-skip dropped (design review 2) | `Agent.step` clears `_deferred_tool_calls` at its start, so skipping the re-sync would only have lost a connector turn landing during the pause | yes: before special-casing a state, check what the next step does to that state anyway |
| Data-loss fix moved into leg 1 (design review 1) | The most severe defect should land and be proven first, on its own | yes |
| Tests pass a per-peer `channel_id` to `stub_inbound` | The resolver keys DM chats on channel, so peers on an empty channel share one chat | yes: document for test authors |
| Leg-1 browser test waits for the re-join before sending | A send during the automatic re-join's `joining` is ignored (text kept) | no; the underlying edge is a follow-up |
| Paused-for-auth re-join: no deferral added | `_send_pause_snapshot_if_needed` replays the login group after every join reply (verified by reading code, not a live paused run) | no |
| Worktree venv pinned to the main venv's freeze mid-flight | 7 unrelated tests failed under freshly resolved dependencies | yes: a fresh-worktree prerequisite, until the dependency set is reproducible |
| Gate ran `--parallel 2` | Another workstream was running a browser lane; host cap is 3 | yes: count the other workstream's lanes against the cap |
| Three legs, over the sortie's two-leg soft limit | Operator choice: one decision cluster, data-loss fix first | see Methodology Observations |

## Key Learnings
- **Notify after commit, broadcast after lock release.**
  - The db layer announces committed changes. The `session_updated` broadcast runs in a `finally` after the lock is released.
  - That ordering is what lets a re-join read `is_processing` false and rebuild from the database. Sent under the lock, the same frame would have produced a re-join that skips its rebuild.
- **Use a content fingerprint, not a timestamp, for cache freshness.**
  - `now_iso()` has about 15.6 ms resolution on the shipped Windows build, and a read-back after a save races writers that do not take the lock.
  - Hashing exactly the bytes written, normalised the way the reader normalises, makes a write and its read-back equal by construction.
- **A push gets its own frame type.**
  - Reusing a reply frame (`session_list` with a flag) would have run the idle rules on an old cached client and opened chats under the user.
  - A new frame type is inert to clients that do not know it, which matters with same-version cached assets (squawk 0085).
- **One chokepoint beats call sites.**
  - Every writer passes through `ChatSessionRepository`: the web turn, REST, the connector dispatcher, the purge sweep and retention.
  - Notifying there covers the next writer too. It works only while the method list stays pinned (see Technical).
- **A "liveness" fix exposes every writer that bypasses the cache contract.** Making the list and pane live forced a re-sync, and the re-sync surfaced the writers outside the lock (resume-after-auth, REST `/api/chat`). Plan them together next time the area is touched.

## Methodology Observations
- **Sortie skill, Plan step 5 (re-check the gate), mission-control 1.2.0.**
  - What happened: the designed flight came to three legs, over the two-plus-HAT soft limit. The skill offered two paths: consolidate the legs, or escalate to a mission.
  - The operator chose a third path the skill does not name: keep three legs in one sortie, because the work was one decision cluster with a data-loss fix sequenced first.
  - Expected: the re-check to name "accept over the limit with a recorded reason" as an outcome, and to say what evidence justifies it (one decision cluster, serial legs on the same files).
  - Cost: none in execution. The Architect called it "at the upper bound of the vehicle" (25 files, about 2,250 lines, 1,350 of them tests and docs). A sweep should know this happened.
- **Flight skill, Phase 1 prerequisites / agentic-workflow Phase 1, mission-control 1.2.0.**
  - What happened: work in a git worktree (a separate workspace for a concurrent workstream) had no methodology guidance. The Flight Director improvised the venv set-up and the import check, and only discovered the dependency drift through 7 spurious failures in leg 1's report.
  - Expected: when a flight runs in a fresh worktree, a prerequisite that its environment matches the reference environment (a dependency set check, not just "imports the right source").
  - Cost: one FD triage cycle mid-flight, and a near-miss in which unrelated failures could have been attributed to the leg.
- **agentic-workflow Phase 2d (gate) / flight-debrief Test Metrics, mission-control 1.2.0.**
  - What happened: the lane budget warnings fired on a host shared with another workstream. Nothing in the workflow records host conditions with gate timings, and the debrief had to re-run the lane solo to show the warnings were contention.
  - Expected: a gate entry that records its parallelism and any concurrent load, so a later reader can weight the numbers.
  - Cost: one extra lane run at the debrief (about 6 minutes).
- **agentic-workflow Phase 2a (risk tiers), mission-control 1.2.0.**
  - What happened: all three legs tiered high (cache freshness, the state machine, the dispatcher), and each got a Developer design review run read-only in parallel with the previous leg's implementation.
  - Parallel review worked well and cost no wall time. The skill describes design review as a step between leg design and implementation, and does not mention that it can overlap the previous leg's implementation when the leg designs are settled.
  - Recorded as a working pattern, not a defect.

## Recommendations
1. **Make a fresh install reproducible, and find out why 7 tests fail under current dependency releases.** The failures are a preview of what the next CI image rebuild or new developer machine will hit. One test, `test_credential_gate`, reports a route not registered, which is worth understanding, not just pinning.
2. **Fold `chat.js`'s live-refresh flags into the chat state machine,** or a `live-refresh.js` module with its clear sites pinned by a test, the next time a flight touches chat state. Do it before another flag joins them.
3. **Close the lock gaps as one small flight or sortie:** `_resume_paused_session` under `session_locks` with a re-sync; REST `/api/chat` with the same re-sync. Then the session lock is the single serialisation point for session writes, as DD4 assumed.
4. **Plan a small chat-polish sortie for the user-visible edges:**
   - Feedback (or queueing) for an Enter during the automatic re-join.
   - A "new messages below" cue for an unpinned reader.
   - Closing or marking a chat deleted elsewhere.
5. **Write the patterns into `agents.md` Project Conventions:**
   - notify-after-commit / broadcast-after-lock-release;
   - fingerprint-over-timestamp;
   - a push-only frame type;
   - the single-process assumption of the live push;
   - the stub per-peer `channel_id` note for test authors.

## Action Items
- [ ] Merge PR #302 after review
- [ ] Squawk 0241: investigate the 7 unit failures under freshly resolved dependencies and make a fresh install reproducible (recommendation 1)
- [ ] Squawk 0242: `agents.md` Project Conventions entries, the single-process note, and the stub `channel_id` note (recommendation 5)
- [ ] Plan the lock-gaps flight or sortie (recommendation 3)
- [ ] Plan the chat-polish sortie (recommendation 4)
- [ ] Re-measure lane budgets at `--parallel 3` on a quiet host (shared, settings, agent-tabs, library)
- [ ] Remove the worktree `.claude/worktrees/sortie-live-chats-list` after merge
