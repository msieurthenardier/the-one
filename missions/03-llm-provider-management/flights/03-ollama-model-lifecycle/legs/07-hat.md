# Leg: hat

**Status**: completed
**Flight**: [Ollama Model Lifecycle](../flight.md)

## Objective

Verify all flight 03 features work end-to-end through guided human acceptance testing.

## Acceptance Criteria

- [x] Key rotation works without data loss
- [x] Provider error handling returns consistent 502s
- [x] Admin ollama provider shows model lifecycle panel (running/available, VRAM summary, pull/load/unload/delete)
- [x] Model pull shows progress bar via SSE
- [x] Model load/unload updates status in real-time
- [x] Model delete with confirmation works
- [x] Studio VRAM warning appears for large models on ollama providers
- [x] Studio VRAM warning does NOT appear for non-ollama providers
- [x] Auto-load triggers "Loading model..." when starting chat with unloaded model
- [x] Non-ollama providers work unchanged (no lifecycle UI, no warnings, no auto-load)

## Verification Steps

1. Start the application
2. Admin: verify ollama provider lifecycle panel
3. Admin: pull a small model
4. Admin: load/unload model
5. Admin: delete model
6. Studio: verify VRAM warnings
7. Chat: verify auto-load
8. Admin: test key rotation
9. Verify non-ollama providers unaffected
