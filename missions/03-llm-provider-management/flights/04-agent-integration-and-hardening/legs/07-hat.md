# Leg: hat

**Status**: completed
**Flight**: [Agent Integration & Hardening](../flight.md)

## Objective

Interactive human acceptance test verifying all Flight 04 changes end-to-end.

## Acceptance Criteria

- [ ] Step 1: First-start banner
- [ ] Step 2: Add a provider
- [ ] Step 3: Banner dismissal
- [ ] Step 4: Create an agent
- [ ] Step 5: Provider deletion protection
- [ ] Step 6: Graceful error handling
- [ ] Step 7: Shared JS utilities
- [ ] Step 8: Library search cache
- [ ] Step 9: Test suite

## Verification Steps

### Step 1: First-start banner
Start the app with no providers configured. Navigate to Chat.
**Expected**: A banner appears saying "No providers configured — set one up in Admin to start chatting."

### Step 2: Add a provider
Navigate to Admin > Providers. Add an Ollama provider pointing to your local instance. Test connection.
**Expected**: Provider saves successfully, connection test passes.

### Step 3: Banner dismissal
Switch to Chat (click the Chat nav icon).
**Expected**: The "No providers" banner is gone.

### Step 4: Create an agent
Navigate to Studio. Create a new agent. Select the provider you just added. Select a model.
**Expected**: New agent form shows "Choose a model" placeholder (not "qwen2.5:7b"). Model dropdown populates after provider selection.

### Step 5: Provider deletion protection
Navigate to Admin > Providers. Click Delete on the provider you added.
**Expected**: Button shows "Used by: <agent-name>" and is disabled (hard-blocked). You cannot delete the provider.

### Step 6: Graceful error handling
(Optional — only if you can create an agent with a non-existent provider_config_id in the DB)
Start a new chat session with an agent whose provider was deleted.
**Expected**: A system message appears: "Cannot start chat: Agent '...' has no provider configured." No crash.

### Step 7: Shared JS utilities
Open browser DevTools console. Navigate between all three areas (Chat, Admin, Studio).
**Expected**: No JS console errors. Flash messages work in Admin and Studio. Byte formatting shows correctly for model sizes in Admin.

### Step 8: Library search cache
In Admin, edit an Ollama provider. In the "Pull a model" search box, type a model name (e.g., "llama"). Wait for results. Clear and type again.
**Expected**: Second search returns results faster (cached). No errors.

### Step 9: Test suite
Run: `cd ~/projects/the-one && python -m pytest tests/ --timeout=30 -x -q`
**Expected**: 325+ tests pass, 0 failures.
