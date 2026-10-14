"""The wording judge (DD14): Haiku 4.5 through the plan-token provider at temperature 0.

``judge(rubric)`` sends the rubric and one saved note's text and parses
``{"pass": bool, "reason": str}``. A malformed reply, a transport failure or an
unvalidated judge raises ``JudgeError``, which the runner turns into an excluded
``error`` run (never a counted pass or fail). Before any judge-scored cell counts in an
invocation the runner scores ``judge/labelled.toml`` and records the agreement; below
``AGREEMENT_FLOOR`` the judge is *unvalidated* and judge-scored runs are excluded.

The model call is async; checks are synchronous, so ``AnthropicJudge.ask`` runs the call
on a private event loop in a worker thread. Runs are sequential, so blocking is fine.
"""

from __future__ import annotations

import asyncio
import json
import re
import tomllib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

JUDGE_DIR = Path(__file__).resolve().parent / "judge"
JUDGE_MODEL = "claude-haiku-4-5-20251001"
AGREEMENT_FLOOR = 0.90
POSITIVE_LABEL = "as-told"  # the label whose expected verdict is pass


class JudgeError(Exception):
    """The judge could not produce a usable verdict (or is unvalidated)."""


class JudgeClient(Protocol):
    def ask(self, rubric: str, note_text: str) -> str:
        """Return the judge model's raw reply text."""


def load_rubrics(path: Path | None = None) -> dict[str, str]:
    path = path or JUDGE_DIR / "rubrics.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {k: v["text"] for k, v in data.items()}


def load_labelled(path: Path | None = None) -> list[dict[str, str]]:
    path = path or JUDGE_DIR / "labelled.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return list(data["item"])


_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


def parse_verdict(text: str) -> tuple[bool, str]:
    """Parse the judge reply. Raises ``JudgeError`` on anything but a clean verdict."""
    m = _JSON_OBJ.search(text or "")
    if not m:
        raise JudgeError("judge reply has no JSON object")
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise JudgeError(f"judge reply is not valid JSON ({exc.msg})") from None
    if not isinstance(obj, dict) or not isinstance(obj.get("pass"), bool):
        raise JudgeError("judge reply lacks a boolean 'pass'")
    reason = obj.get("reason", "")
    return obj["pass"], reason if isinstance(reason, str) else ""


class AnthropicJudge:
    """The real client: Haiku 4.5 via ``get_provider("anthropic-plan-token", ...)``."""

    def __init__(self, token: str, model: str = JUDGE_MODEL) -> None:
        from the_one.llm import get_provider

        self.provider = get_provider("anthropic-plan-token", model=model, access_token=token)

    def ask(self, rubric: str, note_text: str) -> str:
        from the_one.llm.base import Message

        async def go() -> str:
            msgs = [
                Message.system(rubric),
                Message.user(f"Note to grade:\n\n{note_text}"),
            ]
            reply = await self.provider.complete(msgs, temperature=0.0, max_tokens=300)
            return reply.content if isinstance(reply.content, str) else ""

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, go()).result()
        except Exception as exc:  # noqa: BLE001 - surfaced as a judge failure
            raise JudgeError(f"judge call failed: {type(exc).__name__}") from None


@dataclass
class Agreement:
    total: int = 0
    agreed: int = 0
    misses: list[dict[str, str]] = field(default_factory=list)
    errors: int = 0

    @property
    def rate(self) -> float:
        return self.agreed / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "agreed": self.agreed,
            "rate": round(self.rate, 4),
            "errors": self.errors,
            "misses": self.misses,
        }


def score_labelled(
    client: JudgeClient, rubric_id: str = "as-told", *, labelled: list[dict[str, str]] | None = None
) -> Agreement:
    """Score the frozen labelled set. A malformed reply counts as a disagreement."""
    rubric = load_rubrics()[rubric_id]
    out = Agreement()
    for item in labelled if labelled is not None else load_labelled():
        out.total += 1
        want = item["label"] == POSITIVE_LABEL
        try:
            got, reason = parse_verdict(client.ask(rubric, item["text"]))
        except JudgeError as exc:
            out.errors += 1
            out.misses.append({"id": item["id"], "label": item["label"], "got": f"error: {exc}"})
            continue
        if got == want:
            out.agreed += 1
        else:
            out.misses.append(
                {"id": item["id"], "label": item["label"], "got": str(got), "reason": reason}
            )
    return out


@dataclass
class JudgeState:
    """What the ``judge`` check needs: a client and whether it was validated."""

    client: JudgeClient | None = None
    validated: bool = False
    agreement: Agreement | None = None


_state = JudgeState()


def configure(client: JudgeClient | None, *, validated: bool, agreement: Agreement | None = None):
    global _state
    _state = JudgeState(client, validated, agreement)


def current() -> JudgeState:
    return _state


def validate(
    client: JudgeClient, say: Callable[[str], None] = lambda s: None
) -> tuple[Agreement, bool]:
    ag = score_labelled(client)
    ok = ag.rate >= AGREEMENT_FLOOR
    say(f"judge agreement on the labelled set: {ag.agreed}/{ag.total} ({ag.rate:.0%})")
    return ag, ok
