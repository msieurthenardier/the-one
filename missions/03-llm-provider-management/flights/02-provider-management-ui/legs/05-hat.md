# Leg: hat

**Status**: completed
**Flight**: [Provider Management UI](../flight.md)

## Objective

Human acceptance testing across all UI changes from Flight 02. Verify the provider management UI, system key rotation, settings cleanup, and studio dropdowns work correctly in a live browser session.

## Acceptance Criteria

- [x] Admin sidebar shows: General, LLM Providers, System (no Agents, no Integrations)
- [x] General settings shows only Paths, Server, Concourse CI sections (no LLM Configuration)
- [x] LLM Providers: can add a provider (e.g., ollama at localhost:11434/v1)
- [x] LLM Providers: type-specific fields appear/hide correctly
- [x] LLM Providers: connection test shows success/failure
- [x] LLM Providers: models auto-load after successful connection test
- [x] LLM Providers: can edit and delete providers
- [x] LLM Providers: delete shows agent-usage warning when applicable
- [x] System: key rotation button works with double-click confirmation
- [x] Studio: provider dropdown shows configured providers
- [x] Studio: model dropdown populates when provider is selected
- [x] Studio: new agent defaults to "No provider" placeholder
- [x] CLI starts without crash (`python -m the_one.interfaces.cli` or equivalent)
- [x] All tests pass: `pytest tests/ -v --timeout=30`

## Verification Steps

Each step is performed by the human in a live browser session. The Flight Director guides one step at a time, waits for results, and fixes issues inline.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight:
  - [x] Update flight.md status to `landed`
  - [x] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
