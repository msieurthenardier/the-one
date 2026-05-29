"""Engagement-policy inference call infrastructure.

M11 F7 L7 — implements the standalone async helper that the L8 dispatcher
gate consults to decide whether the bot should engage with an inbound that
wasn't explicitly addressed (not a DM, not a mention, not an always-listen
override). Per Flight DD §9: a small LLM call with a hand-tuned, bias-toward-
no prompt that projects a filtered slice of session history + the inbound
text + light contextual scaffolding (channel name, peer name) and parses a
single-word ``"yes"`` / ``"no"`` answer.

Provider resolution (Flight DD §9 + L7 model-source extension): the inference
provider is configured via two paired Settings fields —
``inference_provider_config_id`` (auth + base_url scope, the
``LLMProviderConfig`` row id) AND ``inference_model`` (per-call model name).
Both must be set, or both unset. When both are set, the helper uses them.
When both are unset, the helper falls back to the routed agent's LLM (the
L8 dispatcher passes the agent's ``provider_config_id`` AND ``llm_model``
to :func:`run_engagement_inference` so this module never reaches into the
agent factory). Partial pairs on either path → log + None (operator
misconfiguration surfaced as silence per the safe-default discipline).

Safe-default discipline (Flight DD §9): every exceptional outcome —
provider resolution failure, provider-construction failure, exception during
the inference call itself, ``content=None`` / empty / multi-word /
non-"yes" response — collapses to ``False``. Silence is always the safe
default; an overly chatty bot is the failure mode the gate prevents.

The function is fully testable in isolation via the
:class:`the_one.llm.mock.MockProvider` (stub the configured response /
construct the helper with monkeypatched provider resolution). L8 wires
this into the dispatcher's policy gate at the pre-step decision point.
"""

from __future__ import annotations

import logging

from the_one.agent.factory import _PROVIDER_TYPE_MAP
from the_one.config import Settings
from the_one.connectors import OPERATOR_VISIBILITY
from the_one.connectors._pool import _get_account_cache_snapshot
from the_one.connectors.base import InboundEnvelope
from the_one.connectors.post_step_metadata import resolve_channel_name
from the_one.db.models import Connector
from the_one.db.repositories import LLMProviderRepository
from the_one.llm import get_provider
from the_one.llm.base import LLMProvider, Message, Role

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Prompt template — Flight DD §9 verbatim
# ─────────────────────────────────────────────────────────────────────────────
#
# Multi-line raw-string literal preserving exact DD §9 wording (strong-bias-
# toward-no, four yes-criteria bullets, "When in doubt, no" closing). The
# four placeholders are ``{filtered_session_history_as_turns}``,
# ``{peer_name}``, ``{channel_name}``, and ``{inbound_text}``; the helper
# fills each at call time via :meth:`str.format`.

_INFERENCE_PROMPT_TEMPLATE = """\
You are deciding whether an AI agent should respond to a message in a chat conversation.

Recent conversation context (most recent last):
{filtered_session_history_as_turns}

New message from {peer_name} in {channel_name}:
{inbound_text}

Should the agent respond? Respond with exactly one word: "yes" or "no".

STRONG BIAS TOWARD "no". An overly chatty bot is annoying — silence is the default. Only respond "yes" when there is high confidence (beyond a reasonable doubt) that the agent should engage. Pass on borderline cases.

"yes" criteria — at least one must clearly hold:
- The message is unambiguously directed at the agent (by name, implicit reference, or direct question that no human in the conversation has answered)
- The message is a question that the agent's persona is clearly well-suited to answer AND no other participant has answered
- The recent context shows the agent is mid-conversation about this topic
- The operator has explicitly indicated (in operator-only messages tagged visibility="operator") that the agent should engage with this kind of message

When in doubt, "no".
"""


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────


def _filter_session_history(
    messages: list[Message], limit: int = 20
) -> list[Message]:
    """Project ``Role.USER`` + ``Role.ASSISTANT`` (plaintext only) from history.

    Drops:

    - ``Role.SYSTEM`` and ``Role.TOOL`` messages (system prompts + tool results
      add noise without adding signal at the cap).
    - ``Role.ASSISTANT`` messages that carry tool_calls (the inference LLM
      cares about conversational content, not tool dispatch).
    - Messages with empty ``content`` regardless of role.

    Returns the last ``limit`` entries from the filtered list — the inference
    LLM is small and chatty histories quickly exceed its useful context. Per
    DD §9 the default cap is 20.
    """
    filtered = [
        m
        for m in messages
        if m.role in (Role.USER, Role.ASSISTANT)
        and m.content
        and not m.tool_calls
    ]
    return filtered[-limit:]


def _render_history_for_prompt(filtered: list[Message]) -> str:
    """Render the filtered session history as the prompt-template substring.

    Each turn becomes one line: ``user: ...`` or ``assistant: ...``.
    Operator-typed USER turns (``visibility == OPERATOR_VISIBILITY``) get the
    ``[operator] `` prefix on the content so the inference LLM can
    distinguish operator-steering messages from peer messages per Flight
    DD §9's fourth "yes" criterion.

    Most-recent-last ordering — preserves the input order (callers pass the
    filter output unmodified). Empty input → empty string (caller substitutes
    into the template as a blank history section; the strong-bias-no in the
    prompt handles the no-history edge gracefully).
    """
    lines: list[str] = []
    for m in filtered:
        role_label = "user" if m.role == Role.USER else "assistant"
        content = m.content
        if m.role == Role.USER and m.visibility == OPERATOR_VISIBILITY:
            content = f"[operator] {content}"
        lines.append(f"{role_label}: {content}")
    return "\n".join(lines)


async def _resolve_inference_provider(
    settings: Settings,
    provider_repo: LLMProviderRepository,
    fallback_provider_config_id: str | None,
    fallback_llm_model: str | None,
) -> LLMProvider | None:
    """Resolve which LLM provider+model runs the inference call per DD §9.

    Two paired-fields paths:

    - **Settings path** — both ``settings.inference_provider_config_id`` AND
      ``settings.inference_model`` must be set. On resolution OR construction
      failure → return None (does NOT fall back to the fallback path;
      operator misconfiguration is surfaced via silence + log).
    - **Settings partial** — one set, one not → log + None.
    - **Fallback path** — only used when BOTH settings fields are unset.
      Requires BOTH ``fallback_provider_config_id`` AND
      ``fallback_llm_model``. Partial pair OR either None → None.

    Mirrors the agent/factory.py provider-construction pattern (the
    ``_PROVIDER_TYPE_MAP`` lookup + ``get_provider`` factory call); the
    cross-subsystem import is intentional (single-source-of-truth for the
    provider-type → registry-name dispatch). A future refactor could lift
    ``_PROVIDER_TYPE_MAP`` to ``the_one/llm/registry.py`` if a third caller
    emerges (YAGNI bias from agents.md).
    """
    settings_id = settings.inference_provider_config_id
    settings_model = settings.inference_model
    # Pairing invariant for the settings path.
    if (settings_id is None) != (settings_model is None):
        logger.warning(
            "inference: settings partial pair — "
            "inference_provider_config_id=%r inference_model=%r "
            "(both must be set or both unset)",
            settings_id,
            settings_model,
        )
        return None

    if settings_id is not None:
        # Settings path wins (and shadows the fallback). Failures here do
        # NOT escalate to the fallback per DD §9 — operator misconfiguration
        # surfaces as silence, not as a silent fallback.
        target_id, target_model = settings_id, settings_model
    elif (
        fallback_provider_config_id is not None
        and fallback_llm_model is not None
    ):
        target_id, target_model = fallback_provider_config_id, fallback_llm_model
    else:
        # Either both settings unset AND fallback partial / unset, or
        # both settings unset with no fallback. No inference provider.
        return None

    try:
        config = await provider_repo.get(target_id)
    except Exception:
        logger.warning(
            "inference: provider resolution failed for id=%r",
            target_id,
            exc_info=True,
        )
        return None

    try:
        # Mirror the agent/factory.py:258-278 construction pattern.
        # Note: ``_PROVIDER_TYPE_MAP`` is currently private to
        # ``agent/factory.py``; importing it across the connector→agent
        # boundary is a layering smell that L7 accepts (single-caller,
        # single source-of-truth). A future refactor could lift the map
        # to ``the_one/llm/registry.py`` if a third caller emerges
        # (YAGNI bias per agents.md).
        registry_name = _PROVIDER_TYPE_MAP[config.type]
        return get_provider(
            registry_name,
            model=target_model,
            base_url=config.base_url,
            api_key=config.api_key,
            config=config.config,
        )
    except Exception:
        logger.warning(
            "inference: provider construction failed for id=%r model=%r",
            target_id,
            target_model,
            exc_info=True,
        )
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Public function
# ─────────────────────────────────────────────────────────────────────────────


async def run_engagement_inference(
    account: Connector,
    envelope: InboundEnvelope,
    session_messages: list[Message],
    settings: Settings,
    provider_repo: LLMProviderRepository,
    fallback_provider_config_id: str | None,
    fallback_llm_model: str | None,
) -> bool:
    """Decide whether the bot should engage with an inbound that wasn't addressed.

    Called by the L8 dispatcher's policy gate (Flight DD §1 decision tree
    step 4) when the inbound is neither a DM, a mention, nor explicitly
    permitted by always-listen overrides. Returns True iff the inference
    LLM responds with a single-word ``"yes"`` (case-insensitive, whitespace-
    stripped). Every other outcome — multi-word, ``"no"``, garbage, missing
    content, provider exception, provider resolution failure — returns False.
    Silence is the safe default per DD §9.

    Parameters mirror the dispatcher's available data at the gate point:

    - ``account`` — the full Connector row (the dispatcher has it
      already; passing the row leaves room for future inference signals to
      read ``account.config`` without changing the signature).
    - ``envelope`` — the inbound envelope.
    - ``session_messages`` — the session's full message history (filtered
      internally to USER + ASSISTANT-plaintext, last 20).
    - ``settings`` — :class:`the_one.config.Settings` (provides the
      inference provider+model pairing).
    - ``provider_repo`` — :class:`the_one.db.repositories.LLMProviderRepository`
      (already constructed by the dispatcher).
    - ``fallback_provider_config_id`` — the routed agent's
      ``provider_config_id`` (dispatcher passes this when the settings
      pair is unset).
    - ``fallback_llm_model`` — the routed agent's ``llm_model``
      (dispatcher passes this alongside the fallback id; both must be
      non-None for the fallback to fire).

    Output parsing is strict: ``(result.content or "").strip().lower()``
    → first whitespace-separated token compared against ``"yes"``. Only
    single-word ``"yes"`` engages; ``"yes, ..."``, ``"yes."``, etc. do
    NOT — the prompt requests exactly one word and ambiguous responses
    collapse to silence.
    """
    # 1. Resolve cache snapshot + channel name for the prompt scaffolding.
    snapshot = await _get_account_cache_snapshot(account.id)
    resolved_channel_name = (
        resolve_channel_name(snapshot.cache if snapshot else None, envelope.channel_id)
        or envelope.channel_id
    )

    # 2. Filter the session history + render as a turn-by-turn string.
    filtered = _filter_session_history(session_messages)
    rendered_history = _render_history_for_prompt(filtered)

    # 3. Format the prompt template.
    prompt = _INFERENCE_PROMPT_TEMPLATE.format(
        filtered_session_history_as_turns=rendered_history,
        peer_name=envelope.peer_name,
        channel_name=resolved_channel_name,
        inbound_text=envelope.text,
    )

    # 4. Resolve the inference provider per DD §9's paired-fields semantic.
    provider = await _resolve_inference_provider(
        settings,
        provider_repo,
        fallback_provider_config_id,
        fallback_llm_model,
    )
    if provider is None:
        logger.warning(
            "inference: no provider available (settings + fallback both "
            "unresolved or unconfigured); returning False (silent default)"
        )
        return False

    # 5. Issue the inference call. Any exception → log + False (silent).
    try:
        result = await provider.complete(
            messages=[Message.user(prompt)],
            tools=None,
            temperature=0.0,
            max_tokens=10,
        )
    except Exception:
        logger.warning(
            "inference: provider.complete raised; returning False",
            exc_info=True,
        )
        return False

    # 6. Parse defensively — guard against content=None from codec corner cases.
    text = (result.content or "").strip().lower()
    first = text.split()[0] if text else ""
    return first == "yes"
