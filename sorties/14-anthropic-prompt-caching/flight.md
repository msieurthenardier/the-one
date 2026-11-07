# Sortie: Anthropic prompt caching

**Status**: planning

## Charter

### Outcome
Agents on Anthropic and on a Claude plan reuse a cached prompt prefix (tool schemas and system prompt), so each tool step in a turn uses less input quota and returns sooner.

### Why Now
Sortie 11's tool exposure sends every enabled tool schema on the first call when the toolset fits the budget, and Anthropic's large window means most agents fit. haiku's first-call input grew from 1044 to 2536 tokens for the bare eval agent and from 1556 to 3161 for all-on. Every tool step in a turn re-sends that same prefix, and `the_one/llm/` sets no `cache_control` anywhere, so plan quota pays for it each time. The sortie 11 debrief named this as recommendation 5.

### Success Criteria
- [ ] On the second and later model calls of a turn, an Anthropic or Claude-plan agent's usage reports cache reads covering the tool schemas and system prompt.
- [ ] Token telemetry counts cached input correctly: the context overlay and the stored `last_usage` neither double-count nor drop cache reads and writes.
- [ ] It covers the `anthropic`, `anthropic-plan` and `anthropic-plan-token` provider types.
- [ ] No change in agent behaviour: the s11 compare shows no gate failure for haiku.

### Constraints
- No platform prompt text changes. Caching changes only request metadata, so the prompt evals' size gates do not move.
- Secrets handling is unaffected: the provider request still carries placeholders only, never a secret value.
- No change to the frozen `the_one/agent/core.py` without the owner's approval.
- Out of scope: caching for other providers (OpenAI, OpenRouter, Ollama), and the conversation-history cache strategy beyond the stable prefix unless the design shows it is the same decision.

---

## Pre-Flight

*(Flight design not started. Run `/mission-control:sortie` design for sortie 14 to continue.)*
