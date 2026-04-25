# Leg: hat-and-alignment

**Status**: in-flight
**Flight**: [Resilience & Verification](../flight.md)

## Objective

Human Acceptance Test for Flight 05. Verify the new resilience behaviors end-to-end through the running app: key rotation crash-safety (best-effort smoke), session health states (agent_deleted, provider_missing, ok), stale-join robustness, and the masked API key sentinel round-trip. Mission Control guides the operator one step at a time; failures are fixed inline before moving to the next step.

## Acceptance Criteria

This leg passes when each verification block below passes. Failures are diagnosed and fixed inline (spawning a Developer agent for code changes if needed), then re-verified before proceeding.

## Verification Blocks

### Block A: Key rotation end-to-end

**A1**. With the app running, create a provider with an API key (any cloud provider; OpenAI suggested with a fake key like `sk-hat-test-1234`). Note the masked tail in the response (e.g. `***...1234`).

**A2**. POST to the rotation endpoint:
```bash
curl -X POST http://localhost:8000/api/encryption/rotate
```
Expected: `{"status": "ok"}`. The `~/.the-one/encryption.key` file should change (different bytes from before).

**A3**. GET the same provider — the masked tail should still match (`***...1234`), confirming the rotation re-encrypted the stored key correctly.

### Block B: Session health — agent_deleted

**B1**. Create an agent in Studio with any provider. Start a chat session with that agent. Send at least one message so the session has history.

**B2**. Delete the agent in Studio.

**B3**. Click on the chat session in the chat sidebar (forces a `join` action).

Expected:
- Amber banner appears reading: *"This agent has been deleted. Chat history is preserved but new messages cannot be sent."*
- Chat input is disabled (greyed out, can't type)
- Send button is disabled
- Chat history is still visible
- Agent badge in the header still shows the deleted agent's name (this is intentional — gives the user context about which agent is gone)

### Block C: Session health — provider_missing

**C1**. Create a fresh agent + provider in Studio. Start a chat session, send a message.

**C2**. Delete the provider in Admin (you may need to first reassign the agent to a different provider OR delete the agent first to drop the FK; if the FK blocks deletion, change the agent's provider to something else, then delete the original — choose whichever path matches your current state).

Wait — the cleaner test for `provider_missing` is to set the agent's `provider_config_id` to NULL (or to a non-existent id). The simplest way: in Studio, edit the agent and clear the provider field if the UI supports it. If not, fall back to a SQL update via sqlite3:
```bash
sqlite3 ~/.the-one/the_one.db "UPDATE agent_configs SET provider_config_id = NULL WHERE name = 'YOUR_AGENT_NAME'"
```

**C3**. Click the chat session in the sidebar.

Expected:
- Amber banner: *"This agent's provider is missing. Configure a provider in Studio to continue this conversation."*
- Input + send button disabled
- Chat history visible

**C4**. Restore the provider link (re-edit the agent in Studio, assign a valid provider, save).

**C5**. Click the same chat session again to rejoin.

Expected:
- Banner clears
- Input + send button enabled
- Chat resumes — type a new message, send, get a reply

### Block D: Stale-join guard + "+ new" button

**D1**. With at least 2 sessions in the sidebar, rapid-click session A then session B (one click after the other within ~200ms). Expected: agent badge and history settle on session B (whichever you clicked second), no flash of session A's content. The stale-join guard should discard session A's `session_joined` response when session B's response arrives.

**D2**. With session B currently joined, click the "+ new" button. Expected: a fresh session_joined arrives, the chat clears (empty history), the agent badge updates. **This was a regression caught in flight review** — the fix sets `currentSessionId = null` before sending `new_session`. Verify it works.

**D3**. Repeat D2 several times — each "+ new" click should successfully bind to a fresh session.

### Block E: Masked API key sentinel round-trip

**E1**. In Admin, edit an existing provider. Don't touch the API key field. Save.

**E2**. GET the provider via API; the masked tail should be unchanged from before the edit (proves the original key was preserved via the `__MASKED__` sentinel path).

**E3**. Edit the same provider again. This time clear the API-key field and type a new key (any string). Save.

**E4**. GET the provider — masked tail should now reflect the LAST 4 chars of the new key.

### Block F: test_provider error taxonomy

**F1**. Create a provider with an obviously-invalid API key (e.g. OpenAI with `sk-totally-fake-1234`). Click the "Test Connection" button.

Expected: 200 response with `{status: "error", detail: "..."}`. The UI shows a friendly inline error message (NOT a raw stack trace).

**F2**. (Optional, hard to trigger from UI) verify that an unexpected error path returns 500. This requires temporarily breaking an import or similar — skip unless something already failed.

### Block G: Cleanup verifications

**G1**. `pytest -q` from the repo root — should report 333 passed, 8 deselected, **zero collection errors** and zero `--ignore` flags needed.

**G2**. `ls workspace/test_agent.py` should still exist (we didn't delete it) but `pytest --collect-only -q workspace/` should report no tests collected.

**G3**. `grep -n 'qwen2.5:7b' the_one/llm/ollama_provider.py` should return no matches.

## Pass Criteria

All seven blocks pass. Issues found are fixed inline; the leg only completes once every step is verified working.

## Files Affected

None expected (this is a verification leg). If a fix is required, the Files Affected list grows — record what was touched in the flight log.

---

## Post-Completion Checklist

- [ ] All verification blocks pass
- [ ] Flight log updated with HAT outcomes
- [ ] Set this leg's status to `completed`
- [ ] Check off the "All flows verified via HAT with state-transition sequences" checkpoint in flight.md
- [ ] Commit the leg artifact + flight log update
