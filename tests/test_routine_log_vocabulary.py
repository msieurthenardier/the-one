"""Squawk 0309: one guard for the routine log line vocabulary.

The lines are an operator-facing contract (`the_one/agents.md` "Routine log lines"; the
behavior spec `routine-run-observable-from-logs` greps them). The scheduler decision and
proposal emitters are driven directly; the runner and purge-sweep lines are inline format
strings, so their literal text is read from the source with ``ast``. A renamed key, a
reordered key or a renamed decision word fails here, whatever the per-line tests say.
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

from the_one.routines import scheduler, service

ROOT = Path(__file__).resolve().parent.parent / "the_one"


def _keys(line: str) -> list[str]:
    """The ``key`` of every ``key=value`` token, in order, plus bare flags like ``started``."""
    return [tok.split("=", 1)[0] for tok in line.split()]


def _log_formats(path: Path, prefix: str) -> list[str]:
    """Every string literal in ``path`` that starts with ``prefix`` (adjacent literals are
    already joined by the parser)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith(prefix)
    ]


def test_scheduler_decision_lines(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="the_one.routines.scheduler"):
        scheduler._log_decision("unreadable_due", "r1", "a", "junk")
        scheduler._log_decision("skip_changed", "r1", "a", "D", late_s=30.0)
        scheduler._log_decision(
            "missed", "r1", "a", "D", late_s=1.0, run="u1", nxt="N", finished=True, reason="why"
        )
        for word in ("spawn", "still_running_skip"):
            scheduler._log_decision(
                word, "r1", "a", "D", late_s=1.0, trigger="schedule", nxt="N", finished=False
            )
    recs = caplog.records
    assert [r.levelno for r in recs] == [
        logging.WARNING,
        logging.INFO,
        logging.INFO,
        logging.INFO,
        logging.INFO,
    ]
    lines = [r.getMessage() for r in recs]
    assert lines[0] == "routine decision=unreadable_due routine=r1 agent='a' due='junk'"
    assert lines[1] == "routine decision=skip_changed routine=r1 agent='a' due=D late_s=30.0"
    assert lines[2] == (
        "routine decision=missed run=u1 routine=r1 agent='a' due=D late_s=1.0 "
        "next=N finished=True reason='why'"
    )
    assert _keys(lines[3]) == [
        "routine",
        "decision",
        "routine",
        "agent",
        "trigger",
        "due",
        "late_s",
        "next",
        "finished",
    ]
    assert lines[3].startswith("routine decision=spawn ")
    assert lines[4].startswith("routine decision=still_running_skip ")


def test_scheduler_source_uses_only_the_documented_decision_words() -> None:
    src = (ROOT / "routines" / "scheduler.py").read_text(encoding="utf-8")
    words = set(re.findall(r'_log_decision\(\s*"(\w+)"', src))
    assert words == {"unreadable_due", "skip_changed", "missed"}
    assert re.search(r'decision = "still_running_skip"', src)
    assert re.search(r'decision = "spawn"', src)


def test_proposal_line(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="the_one.routines.service"):
        service._log_proposal("p1", "a", "create", "pending", True, "r1")
        service._log_proposal(None, "a", "delete", "applied", False, None)
    first, second = (r.getMessage() for r in caplog.records)
    assert first == (
        "routine proposal=p1 agent='a' action=create decision=pending flagged=True routine=r1"
    )
    assert second == (
        "routine proposal=none agent='a' action=delete decision=applied flagged=False routine=none"
    )
    src = (ROOT / "routines" / "service.py").read_text(encoding="utf-8")
    for word in ("applied", "pending", "approved", "superseded", "dismissed"):
        assert f'"{word}"' in src


def test_runner_run_lines_are_pinned() -> None:
    found = _log_formats(ROOT / "routines" / "runner.py", "routine run=")
    assert sorted(found) == sorted(
        [
            "routine run=%s routine=%s agent=%r session=%s trigger=%s started",
            "routine run=%s routine=%s agent=%r session=%s trigger=%s outcome=%s reason=%r",
            "routine run=%s routine=%s agent=%r session=none trigger=%s outcome=%s reason=%r",
        ]
    )


def test_purge_sweep_line_is_pinned() -> None:
    (fmt,) = _log_formats(ROOT / "interfaces" / "web" / "app.py", "purge sweep")
    assert fmt == (
        "purge sweep deleted=%d runs_deleted=%d routines_deleted=%d proposals_deleted=%d "
        "evicted=%d last_purge_at=%s"
    )
