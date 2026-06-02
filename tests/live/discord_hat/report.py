"""Per-criterion pass/fail report structure for the live-traffic HAT.

A :class:`HatReport` accumulates one row per acceptance observable
(``criterion``, ``status``, ``evidence``) and renders a Markdown table. The
smoke (L3) populates the load-bearing-premise rows; later legs (L4–L6)
import this and append their own criterion rows so the HAT emits a single
consolidated evidence table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Status = Literal["PASS", "FAIL", "PENDING"]


@dataclass
class HatReportRow:
    criterion: str
    status: Status
    evidence: str


@dataclass
class HatReport:
    """Accumulates criterion rows and renders a Markdown evidence table."""

    rows: list[HatReportRow] = field(default_factory=list)

    def record(self, criterion: str, status: Status, evidence: str) -> None:
        self.rows.append(HatReportRow(criterion=criterion, status=status, evidence=evidence))

    def render(self) -> str:
        """Render the accumulated rows as a Markdown table."""
        lines = [
            "| Criterion | Status | Evidence |",
            "| --- | --- | --- |",
        ]
        for row in self.rows:
            # Escape pipes so evidence text can't break the table layout.
            evidence = row.evidence.replace("|", "\\|")
            criterion = row.criterion.replace("|", "\\|")
            lines.append(f"| {criterion} | {row.status} | {evidence} |")
        return "\n".join(lines)
