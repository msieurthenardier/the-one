"""Per-agent rules: limits, prompt heading text and the numbered-list renderer
(Mission 27 Flight 1, DD4/DD5).

(Lives under ``the_one.db`` so the repository can import it without the
``the_one.agent`` package cycle.)

Rules are operator-authored directives appended to an agent's system prompt
after the persona. This module holds the constants in one place so the
repository, the REST layer and the composer cannot drift.
"""

from __future__ import annotations

from collections.abc import Sequence

# DD4 — counted in characters, after trimming whitespace.
RULE_MAX_CHARS = 500
RULES_TOTAL_MAX_CHARS = 4000

# DD5 — the rules layer's heading. Flight 2 adds the sentence ranking rules
# above notes when notes exist.
RULES_HEADING = (
    "Rules set by the operator for this agent. Follow every rule. If two rules\n"
    "conflict, the one listed first wins."
)


# Appended to the rules layer when a notes layer follows it (M27 F2, DD9).
RULES_OVER_NOTES = "Rules take precedence over saved notes."


class RuleLimitError(ValueError):
    """A rule or the agent's rule total exceeds a limit (HTTP 422)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class RuleOrderError(ValueError):
    """A reorder request is not an exact permutation of the rule ids (422)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def validate_rule_text(text: str) -> str:
    """Return *text* trimmed; raise :class:`RuleLimitError` if empty or too long."""
    trimmed = (text or "").strip()
    if not trimmed:
        raise RuleLimitError("A rule cannot be empty.")
    if len(trimmed) > RULE_MAX_CHARS:
        raise RuleLimitError(
            f"Each rule is limited to {RULE_MAX_CHARS} characters; "
            f"this one is {len(trimmed)} characters."
        )
    return trimmed


def total_limit_error(attempted_total: int) -> RuleLimitError:
    return RuleLimitError(
        f"Rules are limited to {RULES_TOTAL_MAX_CHARS:,} characters in total; "
        f"this would make {attempted_total:,}."
    )


def render_rules_block(rules: Sequence[str], notes_present: bool = False) -> str:
    """The DD5 rules layer: heading, blank line, then ``1. …`` numbered rules.

    A rule containing a newline is rendered as-is after its number.
    With ``notes_present`` the heading gains "Rules take precedence over saved
    notes." (the default output is unchanged).
    """
    numbered = "\n".join(f"{i}. {text}" for i, text in enumerate(rules, start=1))
    heading = f"{RULES_HEADING}\n{RULES_OVER_NOTES}" if notes_present else RULES_HEADING
    return f"{heading}\n\n{numbered}"
