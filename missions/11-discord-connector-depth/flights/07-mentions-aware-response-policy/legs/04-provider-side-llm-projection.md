# Leg: provider-side-llm-projection

**Status**: completed
**Flight**: [Mentions-Aware Response Policy](../flight.md)

## Objective

Project `Message.peer_name` and `Message.channel_name` into the LLM payload by prepending `[from {peer_name} in #{channel_name}]: ` (or the appropriate partial-absence variant) to the user-role content at each provider adapter's `_to_api_message` site. OpenRouter inherits via OpenAIProvider; tests pin parity across all four. Closes F6 Rec #4 / M11 criterion #13 LLM-side projection.

## Context

- **Flight DD §5 (peer-name + channel-name LLM-side projection)** — the projection is inline-prefix at provider-serialize time. Both fields optional; absent-on-message → no prefix. L4 ships this projection at the three provider serialization sites; OpenRouter inherits via OpenAIProvider so the inherited `_to_api_message` picks up the change automatically; tests include a parity assertion.
- **F6 DD §2 audit precedent ("no leak" → "intentional projection")** — F6 audited the three adapters and pinned that all explicitly project `{"role": msg.role.value, "content": msg.content}` (`openai_provider.py:270`, `anthropic_provider.py:232`, `ollama_provider.py:267`). The audit's structural guarantee was: peer_name cannot leak without an explicit code change. **L4 IS that explicit code change**, transferring "no leak" to "intentional projection." Per the `cross-subsystem-pattern-premise-revalidation` convention (`agents.md:122-130`), L4 carries a premise revalidation paragraph stating: the audit's premise was "no field beyond `{role, content}` reaches the LLM"; the new premise (post-L4) is "the prefix is the projection — `peer_name` and `channel_name` reach the LLM ONLY via explicit `msg.content`-shaped mutation at the `_to_api_message` return path, never carried as separate fields on the API payload."
- **Shared helper discipline** — the prefix format must be identical across all three serialization sites. Rather than duplicate the prefix-building logic at each site, L4 adds a free helper `build_user_message_content(msg: Message) -> str` in `the_one/llm/base.py` (alongside the `Message` dataclass that owns the source fields). Each provider's `_to_api_message` calls the helper at the user-role branch return; the helper centralizes the four partial-absence variants and the bracket-and-`#`-prefix glyphs. The provider adapters still satisfy the explicit-projection idiom (each calls the helper at its serialization site; the call is the explicit projection).
- **Partial absence variants** — four cases:
  - `peer_name` non-None AND `channel_name` non-None → `[from {peer_name} in #{channel_name}]: {content}`
  - `peer_name` non-None AND `channel_name` is None → `[from {peer_name}]: {content}`
  - `peer_name` is None AND `channel_name` non-None → `[in #{channel_name}]: {content}`
  - Both None → `{content}` (no prefix — byte-identical to pre-F6 + pre-F7 payload)
  - Empty-string `peer_name=""` or `channel_name=""` is treated AS-IF non-None (the `is not None` guard from `message-additive-back-compat-via-emit-when-non-none` convention applies: empty strings must round-trip; rendering them as `[from  in #...]` is the contracted shape, not the helper's concern).
- **User-role only** — the projection applies only when `msg.role == Role.USER`. Assistant/tool messages bypass the helper (the existing branches in each `_to_api_message` already short-circuit before the user-role fall-through). The helper itself defends with an assertion / early return for non-USER roles so it can be called accidentally without leaking data.

## Inputs

- L1+L2+L3 landed uncommitted on `flight/07-mentions-aware-response-policy`. `Message.peer_name`, `Message.channel_id`, `Message.channel_name` all exist (L2); the dispatcher binds them (L3); the codec round-trips them.
- `the_one/llm/openai_provider.py:_to_api_message` at line 247 — user-role fall-through at line 270 (`return {"role": msg.role.value, "content": msg.content}`).
- `the_one/llm/anthropic_provider.py:_to_api_message` at line 210 — user-role fall-through at line 232.
- `the_one/llm/ollama_provider.py:_to_api_message` at line 244 — user-role fall-through at line 267.
- `the_one/llm/openrouter_provider.py` — `OpenRouterProvider(OpenAIProvider)` at line 46; no override of `_to_api_message`. L4's OpenAI edit propagates automatically.
- `the_one/llm/base.py` — `Message` dataclass home; the natural location for `build_user_message_content` helper.
- `the_one/agents.md:122-130` — `cross-subsystem-pattern-premise-revalidation` convention block; needs a new citation for L4 (the F6 audit's premise refined).
- F6 flight.md / F6 flight-debrief.md — the audit precedent that L4 deliberately changes.

## Outputs

- `the_one/llm/base.py`:
  - New free function `build_user_message_content(msg: Message) -> str` after the `Message` class:
    ```python
    def build_user_message_content(msg: Message) -> str:
        """Build the LLM-payload content string for a user message,
        projecting peer_name and channel_name as an inline bracket prefix.

        Format depends on which fields are set (all use ``is not None``,
        NOT truthiness — empty strings round-trip as-is per the
        ``message-additive-back-compat-via-emit-when-non-none`` convention):

        - peer_name + channel_name both set → ``[from {peer} in #{ch}]: {content}``
        - peer_name only                    → ``[from {peer}]: {content}``
        - channel_name only                 → ``[in #{ch}]: {content}``
        - neither set                       → ``{content}`` (byte-identical
          to pre-F6 + pre-F7 payload — legacy back-compat)

        Defensive: returns ``msg.content`` unchanged for any non-USER
        role (the projection is meaningful only on inbound user turns;
        assistant/tool messages should never reach this helper, but the
        safety branch prevents accidental leakage if a future caller
        violates the contract).

        M11 F7 L4: closes F6 Rec #4 / M11 criterion #13 (LLM-side
        projection of peer_name + channel_name). The prefix IS the
        projection — the F6 audit's "no leak" guarantee becomes
        "intentional projection at this single site"; the fields
        never appear as separate keys on the API payload.
        """
        if msg.role != Role.USER:
            return msg.content
        peer = msg.peer_name
        ch = msg.channel_name
        if peer is not None and ch is not None:
            return f"[from {peer} in #{ch}]: {msg.content}"
        if peer is not None:
            return f"[from {peer}]: {msg.content}"
        if ch is not None:
            return f"[in #{ch}]: {msg.content}"
        return msg.content
    ```
- `the_one/llm/openai_provider.py`:
  - Import `build_user_message_content` from `the_one.llm.base`.
  - In `_to_api_message`, replace the user-role fall-through `return {"role": msg.role.value, "content": msg.content}` with `return {"role": msg.role.value, "content": build_user_message_content(msg)}`.
  - Brief comment above the return citing M11 F7 L4 + the helper.
- `the_one/llm/anthropic_provider.py`:
  - Same shape: import the helper; replace the user-role return with the helper-projected content.
- `the_one/llm/ollama_provider.py`:
  - Same shape: import the helper; replace the user-role return with the helper-projected content.
- `the_one/llm/openrouter_provider.py`:
  - **No code change.** The class inherits `_to_api_message` from `OpenAIProvider`; the L4 edit propagates automatically. A test pins this parity to prevent a future override that would silently strip the projection.
- `the_one/agents.md`:
  - In the `cross-subsystem-pattern-premise-revalidation` convention block (lines 122-130), append a new citation paragraph in the same shape as the existing `the_one/connectors/_pool.py` citation:
    ```
    M11 F7 L4: the F6 DD §2 provider audit pinned "no leak" — peer_name (and forthcoming channel_name) cannot reach LLM payloads because all three adapters explicitly project ``{role, content}``. F7 L4 deliberately refines that premise: peer_name and channel_name DO reach the LLM, but ONLY via an inline-prefix mutation at ``_to_api_message``'s user-role return path; never as separate API-payload keys. The audit-into-design-decision shape from F6 produced the structural guarantee that the new projection now relies on (a single, explicit, code-cited mutation site per adapter); the convention's "premise P holds" check is satisfied by L4's premise-revalidation paragraph in the L4 leg artifact.
    ```
- New tests for the projection helper in `tests/test_llm_base.py` (or a new file if no such test module exists — confirm at implementation time):
  - `test_build_user_message_content_with_both_fields` — `Message.user("hi", peer_name="alice", channel_name="general")` → `[from alice in #general]: hi`.
  - `test_build_user_message_content_with_peer_name_only` — peer_name set, channel_name None → `[from alice]: hi`.
  - `test_build_user_message_content_with_channel_name_only` — channel_name set, peer_name None → `[in #general]: hi`.
  - `test_build_user_message_content_with_neither` — both None → `hi` (byte-identical to legacy).
  - `test_build_user_message_content_with_empty_string_peer_name` — peer_name="" non-None → `[from  in #general]: hi` (empty string renders as-is per convention).
  - `test_build_user_message_content_with_assistant_role_returns_unchanged` — `Message(role=Role.ASSISTANT, content="hi", peer_name="alice")` → `hi` (defensive non-USER branch).
- New tests for each provider's `_to_api_message`:
  - In each provider's test file (or a new file `tests/test_llm_provider_user_content_projection.py` if the existing test files don't have a unit-test class for `_to_api_message`):
    - `test_<provider>_to_api_message_user_with_peer_name_and_channel_name` — projects prefix into the API payload's content key.
    - `test_<provider>_to_api_message_user_with_peer_name_only` — peer_name only variant.
    - `test_<provider>_to_api_message_user_with_no_attribution` — both None → byte-identical legacy payload (content key matches `msg.content` directly).
    - `test_<provider>_to_api_message_assistant_unchanged_by_projection` — assistant message → no projection (the existing branch handles it).
  - One cross-provider parity test: `test_user_content_projection_parity_across_providers` — same Message → all four providers emit the same `content` string in the resulting API payload. The test MUST instantiate concrete provider objects (`OpenAIProvider()`, `AnthropicProvider()`, `OllamaProvider()`, `OpenRouterProvider()`) and call `_to_api_message(msg)` on each instance, asserting the resulting `content` strings are equal — NOT a method-identity check. Identity (`OpenRouterProvider._to_api_message is OpenAIProvider._to_api_message`) is covered by the Verification Steps grep + Python one-liner; the behavior parity test pins that a future override on any subclass that returns the same shape but elides the helper call would be caught.
  - Optional 24th test (defense-in-depth on the `is not None` convention): `test_build_user_message_content_with_empty_string_channel_name` — empty `channel_name=""` renders verbatim mirroring the empty-string peer_name test. Apply if it tightens; the convention is well-established without it.
  - Optional 25th test (special characters): `test_build_user_message_content_with_special_characters` — e.g. `peer_name="alice (bot)"` and `channel_name="general/sub"` — pins the no-escaping contract listed in Edge Cases. Apply if it tightens.

## Acceptance Criteria

- [ ] `the_one/llm/base.py` exports `build_user_message_content(msg)` with the four-variant logic + non-USER defensive branch + docstring citing F6 Rec #4 / M11 criterion #13.
- [ ] `the_one/llm/openai_provider.py:_to_api_message` user-role return uses `build_user_message_content(msg)` instead of `msg.content`.
- [ ] `the_one/llm/anthropic_provider.py:_to_api_message` user-role return uses `build_user_message_content(msg)` instead of `msg.content`.
- [ ] `the_one/llm/ollama_provider.py:_to_api_message` user-role return uses `build_user_message_content(msg)` instead of `msg.content`.
- [ ] `the_one/llm/openrouter_provider.py` is NOT modified; OpenRouter inherits via `OpenAIProvider`.
- [ ] `the_one/agents.md` `cross-subsystem-pattern-premise-revalidation` convention has an L4 citation paragraph documenting the premise refinement.
- [ ] Helper tests (6) and per-provider tests (4 × 4 = 16) + 1 parity test = 23 new tests, all passing.
- [ ] Legacy payload byte-identity preserved when peer_name + channel_name are both None — `test_<provider>_to_api_message_user_with_no_attribution` pins this.
- [ ] `docker exec the-one pytest tests/test_llm_base.py tests/test_openrouter_provider.py tests/test_ollama_provider_auth.py -x --timeout 30` passes (plus any new provider test file).
- [ ] Full suite at leg-end: `docker exec the-one pytest -x --timeout 60` — no L4-introduced regressions.
- [ ] Flight log L4 entry under `## Leg Progress` documents the leg; leg checked off in `flight.md` under `### Legs`. Leg artifact status set to `landed`. F6 Rec #4 explicitly closed; M11 criterion #13 LLM-side gap explicitly closed.

## Verification Steps

- `python -c "from the_one.llm.base import build_user_message_content, Message; m = Message.user('hi', peer_name='alice', channel_name='general'); print(build_user_message_content(m))"` prints `[from alice in #general]: hi`.
- `python -c "from the_one.llm.base import build_user_message_content, Message; print(build_user_message_content(Message.user('hi')))"` prints `hi` (legacy byte-identity).
- `python -c "from the_one.llm.openrouter_provider import OpenRouterProvider; from the_one.llm.openai_provider import OpenAIProvider; print(OpenRouterProvider._to_api_message is OpenAIProvider._to_api_message)"` prints `True` (inheritance preserved).
- `grep -n "build_user_message_content" the_one/llm/openai_provider.py the_one/llm/anthropic_provider.py the_one/llm/ollama_provider.py` returns one match per file.
- `grep -n "build_user_message_content" the_one/llm/openrouter_provider.py` returns NOTHING (no override; inheritance carries the change).
- `grep -n "M11 F7 L4\|F6 Rec #4\|F6 audit" the_one/agents.md` returns the new citation paragraph.
- Targeted: `docker exec the-one pytest tests/test_llm_base.py tests/test_openrouter_provider.py tests/test_ollama_provider_auth.py <any_new_provider_test_file> -x --timeout 30` — all green.
- Full suite: `docker exec the-one pytest -x --timeout 60` — all green.

## Implementation Guidance

1. **Add the helper** in `the_one/llm/base.py`. Define it as a module-level free function after the `Message` class (no class method — the helper takes the Message, doesn't own it). Use exact-match string formatting per the Outputs code sketch. Add `__all__` entry if the module has one.

2. **Update each provider adapter** (`openai_provider.py`, `anthropic_provider.py`, `ollama_provider.py`):
   - At the top of the file (with other LLM imports), add `from the_one.llm.base import build_user_message_content` (or extend an existing import line).
   - Locate the user-role fall-through return in `_to_api_message`. Replace `msg.content` with `build_user_message_content(msg)` in the returned dict:
     ```python
     # M11 F7 L4: project peer_name + channel_name as an inline prefix.
     # The helper handles all four absence variants; legacy back-compat
     # is preserved when both fields are None (byte-identical payload).
     # F6 DD §2 audit premise refined: the prefix IS the projection.
     return {"role": msg.role.value, "content": build_user_message_content(msg)}
     ```
   - **Anthropic-specific defensive comment**: at the Anthropic user-role return, add a one-line note:
     ```python
     # L4 contract: this branch passes through a string content; future
     # vision/multimodal would route via a separate content-list branch
     # and would NOT call build_user_message_content (it would build the
     # projection per content-block, or fall back to a different shape
     # per DD §5's divert criterion).
     ```
     OpenAI / Ollama don't need this note (their content-list paths don't go through the user-role fall-through today). Anthropic's `content` flexibility is what makes the divert-criterion language in DD §5 apply specifically to it.

3. **OpenRouter — DO NOT EDIT.** The class inherits `_to_api_message` from `OpenAIProvider`. The L4 OpenAI edit automatically propagates. A parity test pins this.

4. **Add the cross-subsystem-pattern-premise-revalidation citation** in `the_one/agents.md`:
   - Open the convention block at lines 122-130. The block ends with a `Source:` line at line 130; the new citation paragraph MUST land between the existing `Citation: the_one/connectors/_pool.py` paragraph (line 128) and the trailing `Source:` line (line 130) — at line 129 — so `Source:` remains the block terminator. Do NOT append past `Source:`.

5. **Add tests:**
   - **Helper tests** in `tests/test_llm_base.py` (create the file if it doesn't exist — verify at implementation time). Six tests per the Outputs section.
   - **Per-provider `_to_api_message` tests**: the existing test files (`tests/test_openrouter_provider.py`, `tests/test_ollama_provider_auth.py`) cover auth + OpenRouter-specific concerns, not unit tests for `_to_api_message`. Create a new file `tests/test_llm_provider_user_content_projection.py` housing the four-tests-per-provider × four-providers grid (16 tests) plus the parity test (1). Each test directly invokes `provider._to_api_message(message)` and asserts on the returned dict.
   - **Parity test**: same Message → same `content` string across OpenAI / Anthropic / Ollama / OpenRouter. Anthropic's user-role payload shape matches OpenAI/Ollama at this branch (`{"role": ..., "content": ...}`), so parity is well-defined. The test instantiates one of each provider and asserts the four returned `content` strings are equal.

6. **Run tests** per Verification Steps. Update flight log under `## Leg Progress` with `### L4 — provider-side-llm-projection`. Check off in flight.md. Set L4 status to `landed`. Mark `F6 Rec #4 closed by F7 L4` explicitly in the flight log entry (this is the F6 debrief follow-up action item). Do NOT commit (F7 flight-level commit ordering).

## Edge Cases

- **Non-USER message accidentally passed to the helper** — defensive non-USER branch returns `msg.content` unchanged. The provider adapters only call the helper at the user-role return path, so this is structurally prevented; the defensive branch protects against a future caller that violates the contract.
- **Empty-string `peer_name=""` or `channel_name=""`** — renders verbatim (`[from  in #general]: hi`). Treating empty as "absent" would silently strip information; the convention's `is not None` discipline applies (mirrors F6 L1's peer_name decision).
- **Special characters in `peer_name` or `channel_name`** — e.g. `peer_name="alice (bot)"` or `channel_name="general/sub"`. The helper does straight string interpolation; if the platform allows the character, the prefix carries it as-is. No escaping. The LLM sees what the operator sees. Tests should cover at least one special-character case (parens or hash).
- **Anthropic content as a list vs. string** — Anthropic's user-role branch at line 232 returns `{"role": msg.role.value, "content": msg.content}` — content is a string at that path (Anthropic's tool_result branch uses a list, but that's the TOOL role, not USER). The helper returns a string, drop-in compatible.
- **Cross-provider parity edge case** — if a provider ever swaps its content shape from string to list (e.g. Anthropic vision multi-block), the helper's string output would need re-encoding at the call site. L4 ships the string-shape contract; future vision/multimodal expansion is out of scope. The parity test catches a silent divergence.
- **L4 + L8 interaction** — when L8's policy gate silences a turn, the user message is NOT appended to `agent.messages` (per DD §13's terminal-return semantics). The helper is never called for silent turns. Engaged turns: the helper runs as part of `_to_api_message`'s normal flow; the projection lands in the LLM payload. No conflict.

## Files Affected

- `the_one/llm/base.py` — ADD `build_user_message_content` helper after `Message` class.
- `the_one/llm/openai_provider.py` — UPDATE user-role return in `_to_api_message` to call the helper.
- `the_one/llm/anthropic_provider.py` — UPDATE user-role return in `_to_api_message` to call the helper.
- `the_one/llm/ollama_provider.py` — UPDATE user-role return in `_to_api_message` to call the helper.
- `the_one/llm/openrouter_provider.py` — NO CHANGE; inheritance carries the L4 edit.
- `the_one/agents.md` — UPDATE `cross-subsystem-pattern-premise-revalidation` convention with L4 citation paragraph.
- `tests/test_llm_base.py` — ADD/CREATE 6 helper tests.
- `tests/test_llm_provider_user_content_projection.py` — CREATE with 16 per-provider tests + 1 parity test.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight-log.md` — APPEND `## Leg Progress` entry with explicit "F6 Rec #4 closed" note.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight.md` — CHECK OFF leg.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (targeted + full suite)
- [ ] Update flight-log.md with leg progress entry; explicitly mark F6 Rec #4 closed
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: NOT applicable
- [ ] Commit all changes together — DEFERRED in F7 per `/agentic-workflow` flight-level commit ordering; do NOT commit per leg.

## Citation Audit

Citations verified against current code at design time via the F7 L4 reconnaissance pass:

- `the_one/llm/openai_provider.py:_to_api_message:247–270` (verified; user-role return at 270).
- `the_one/llm/anthropic_provider.py:_to_api_message:210–232` (verified; user-role return at 232).
- `the_one/llm/ollama_provider.py:_to_api_message:244–267` (verified; user-role return at 267).
- `the_one/llm/openrouter_provider.py:46` — `class OpenRouterProvider(OpenAIProvider):` (verified; no `_to_api_message` override).
- `the_one/agents.md:122–130` — `cross-subsystem-pattern-premise-revalidation` convention block (verified).
- F6 flight.md DD §2 provider audit (verified at design time via the reconnaissance pass; sites at openai_provider.py:270, anthropic_provider.py:232, ollama_provider.py:267 all confirmed to use the explicit `{"role": msg.role.value, "content": msg.content}` projection).

No drift detected. The Anthropic file uses fewer lines than OpenAI/Ollama (the assistant-tool-call branch is structured differently due to Anthropic's content-block shape), but the user-role fall-through is identical in shape at line 232.
