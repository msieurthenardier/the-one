# Flight: Resilience & Verification

**Status**: landed
**Mission**: [LLM Provider Management](../../mission.md)

## Contributing to Criteria

- [x] API credentials are stored encrypted at rest [...] a rotate function re-encrypts all stored secrets with a new key
- [x] The system degrades gracefully when a configured provider is unreachable or a requested model is unavailable, surfacing clear feedback to the user
- [x] On first start with no provider configurations, the application guides the user to set up at least one provider before chat is functional

---

## Pre-Flight

### Objective

Close the final three partially-met mission success criteria and eliminate all carried-forward technical debt from Flights 01-04. This flight makes key rotation crash-safe, adds session-level health validation so users see actionable feedback when agents or providers are missing, and cleans up accumulated minor debt (hardcoded defaults, dead code, fragile patterns, inconsistent error handling). The result is a resilient, clean foundation with no known deferred issues.

### Open Questions

- [x] Key rotation approach -> temp file + atomic rename (see Design Decisions)
- [x] Old session handling -> session health status with contextual banners (see Design Decisions)
- [x] Masked API key detection -> sentinel value `__MASKED__` (Architect recommendation)
- [x] httpx connection pooling -> keep per-call creation (Architect recommendation)
- [x] estimate_vram -> already removed from source; no action needed
- [x] OllamaProvider default -> remove hardcoded "qwen2.5:7b"

### Design Decisions

**Key rotation: temp-file + atomic rename**
- Rationale: The current implementation writes the new key file *before* re-encrypting DB rows. If DB writes fail, data is encrypted with the old key but the key file holds the new key -- data loss. The fix: re-encrypt DB rows first (using the new key in memory), commit the transaction, *then* atomically write the new key file via temp + rename.
- Trade-off: Slightly more complex than the callback approach, but crash-safe in all failure modes. If DB commit fails, old key file is preserved. If rename fails after DB commit, the new ciphertext is unreadable but the old key file still exists (needs manual recovery -- edge case at filesystem level).
- Implementation: The API route handler bypasses `Encryptor.rotate_key()` entirely and manages the rotation sequence directly: (1) generate new key + Encryptor in memory, (2) re-encrypt all DB rows with new encryptor, (3) commit DB transaction, (4) write new key to temp file, (5) atomic rename temp -> key file, (6) update cached Encryptor. This avoids the sync-to-async callback migration and keeps Encryptor simple. The existing `rotate_key()` method and its sync tests remain unchanged for non-API callers.
- Note: Existing `test_encryption.py` tests (7 tests) use `rotate_key` with sync callbacks -- these are unaffected since we don't change the Encryptor API.

**Session health validation: three states on join**
- When restoring/joining a session, the backend checks agent and provider health before returning `session_joined`. The response includes a `status` field:
  - `"ok"` -- agent and provider are valid, chat is functional
  - `"agent_deleted"` -- the agent referenced by this session no longer exists. Show chat history read-only with a banner: "This agent has been deleted. Chat history is preserved but new messages cannot be sent."
  - `"provider_missing"` -- the agent exists but has no provider configured (or the provider was deleted). Show banner: "This agent's provider is missing. Configure a provider in Studio to continue this conversation." Chat input disabled. Once the provider is fixed, the user can continue the same conversation.
- Rationale: The user explicitly wants old sessions to remain visible with actionable guidance, not silently deleted or auto-redirected.
- Trade-off: Requires frontend state management for degraded sessions. The backend does a few extra lookups on session join, but these are fast (DB queries).
- Implementation: `_restore_session` in app.py checks agent existence and provider validity, returning session health status instead of silently falling back to the default agent (the current fallback at lines 154-161 must be removed). `session_joined` WebSocket message includes `status` field. chat.js renders appropriate banners and disables/enables input accordingly.
- Note: Session health banners are per-session state, distinct from the global setup banner (`checkSetupState`). They use a separate DOM element to avoid conflicts with the existing `chat-no-providers` banner.
- Note: Health checks apply to `join` (restoring existing sessions) only. `new_session` continues to raise exceptions on invalid agents -- you can't create a new session with a deleted agent.

**Masked API key: sentinel value `__MASKED__`** (Architect recommendation)
- Rationale: The current `startswith("***")` check is fragile -- a real API key starting with `***` would be silently discarded. A sentinel value `"__MASKED__"` is unambiguous: no real API key will ever be that exact string. The frontend sends `"__MASKED__"` when the user hasn't touched the key field; the backend checks `if incoming_key == "__MASKED__"`. No payload schema change needed.
- Trade-off: Requires updating both frontend (admin.js mask logic) and backend (api.py check). Minimal.

**httpx connection pooling: keep per-call creation** (Architect recommendation)
- Rationale: Auto-load makes at most 2 HTTP calls per chat message, to localhost (no TLS). Connection pooling overhead (lifecycle management, stale connection handling, use-after-close bugs) outweighs the negligible performance gain. Can be revisited if high-frequency polling is added later.
- No code changes needed.

**Remove OllamaProvider hardcoded default**
- Change `model: str = "qwen2.5:7b"` to `model: str = ""` in `OllamaProvider.__init__`. The agent config already controls model selection; the provider constructor default is a misleading fallback that masks configuration errors.
- Trade-off: If someone creates an OllamaProvider without specifying a model, they'll get an empty string (and an error from Ollama) instead of silently using qwen2.5:7b. This is the correct behavior -- fail explicitly.

**estimate_vram: already removed** (Architect finding)
- The function was specified in Flight 03 but never made it into the source code (only exists in flight documentation artifacts). No action needed.

### Prerequisites

- [x] Flight 04 completed (shared utilities, first-start banner, deletion protection, error boundaries)
- [x] All 325 tests passing on current main *(actual: 317 collected with 2 known collection errors at flight start; both fixed in Leg 04. Final count: 333 passing, 8 deselected)*

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

The flight works in three phases: (1) backend resilience fixes (key rotation, session health), (2) frontend degradation UX (session banners, input state management), (3) cleanup of accumulated minor debt. A comprehensive HAT using state-transition sequences validates all flows end-to-end.

Key rotation is the highest-risk change (touches encryption, DB transactions, file I/O). It goes first so it gets the most review scrutiny and test coverage.

Session health validation is the most complex feature -- it spans backend (app.py session restore), WebSocket protocol (new status field), and frontend (chat.js banner rendering, input state). It's split across two legs (backend + frontend) to keep each reviewable.

The cleanup leg bundles all minor debt items that don't interact with each other.

### Checkpoints

- [x] Key rotation is crash-safe with temp-file pattern and test coverage
- [x] Session join returns health status (ok/agent_deleted/provider_missing)
- [x] Chat UI renders appropriate banners and disables input for degraded sessions
- [x] bannerEl refactored to dedicated boolean state flag
- [x] OllamaProvider default removed
- [x] Masked API key uses `__MASKED__` sentinel
- [x] test_provider error handling clarified (keep 200-with-status for expected errors, HTTPException for unexpected failures)
- [x] workspace/test_agent.py collection error resolved
- [x] All flows verified via HAT with state-transition sequences

### Adaptation Criteria

**Divert if**:
- Key rotation refactor introduces test failures that indicate deeper encryption architecture issues
- Session health validation requires changes to the chat session DB schema (would need a migration leg)

**Acceptable variations**:
- Architect recommends a third option for masked API key or httpx pooling
- Minor scope adjustments to cleanup leg based on what the Architect surfaces
- Additional banners or status states discovered during implementation

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.

- [x] `key-rotation-atomicity` - Make key rotation crash-safe with temp-file + atomic rename pattern; add test coverage
- [x] `session-health-backend` - Add health status to session restore/join; return agent_deleted/provider_missing states via WebSocket
- [x] `session-health-frontend` - Render session health banners in chat.js; disable input for degraded sessions; refactor bannerEl to dedicated boolean
- [x] `backend-cleanup` - Remove OllamaProvider default, fix masked API key sentinel, normalize test_provider errors, fix workspace/test_agent.py collection error
- [ ] `hat-and-alignment` *(optional)* - Guided HAT session using state-transition sequences; iterative fixes until all flows pass

---

## Post-Flight

### Completion Checklist

- [x] All legs completed *(4 autonomous legs + optional HAT leg, all completed)*
- [ ] Code merged *(pending PR merge)*
- [x] Tests passing *(333 passed, 8 deselected, zero collection errors)*
- [ ] All 9 mission success criteria verified as met *(to be confirmed at mission debrief)*

### Verification

1. Key rotation: Rotate key via API, verify all provider credentials remain accessible. Simulate failure (e.g., read-only DB) and verify old key is preserved.
2. Session health: Create agent + provider, start conversation, delete provider, rejoin session -- verify banner and disabled input. Fix provider, verify conversation resumes. Delete agent, rejoin -- verify read-only history with banner.
3. First-start: Fresh DB, verify three-state banner flow through provider creation -> agent creation -> working chat.
4. Cleanup: Verify OllamaProvider without model param raises clear error. Verify masked API key round-trip works correctly with `__MASKED__` sentinel. Verify test collection has no errors.
