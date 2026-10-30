"""Pydantic models for routines and their run history (Mission 33 F1, DD1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TriggerKind = Literal["schedule", "catch_up", "manual"]
Outcome = Literal["running", "ok", "failed", "skipped", "missed", "interrupted", "stopped"]


class Routine(BaseModel):
    id: str
    agent_name: str
    name: str
    prompt: str
    schedule: dict[str, Any]
    enabled: bool = True
    finished_at: str | None = None
    next_run_at: str | None = None
    anchor_at: str | None = None
    created_by: Literal["operator", "agent"] = "operator"
    created_at: str
    updated_at: str
    # M33 F2 DD7: set when an agent write was influenced by untrusted content.
    untrusted: bool = False
    untrusted_sources: list[str] = Field(default_factory=list)


class RoutineRun(BaseModel):
    id: str = ""
    routine_id: str
    trigger_kind: TriggerKind
    outcome: Outcome = "running"
    reason: str | None = None
    due_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    session_id: str | None = None
    repeats: int = 1
    reason_code: str | None = None
