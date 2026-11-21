"""GleepGlorp fill routes (Mission 36 F3 L5, DD6).

Operator-only: behind the credential gate, POST-only for writes. They change only a fill's own
status, never configuration: the browser writes the values as unsaved edits and only the
operator's Save stores them. The outcome takes codes only (no browser text is stored), and
nothing from a request body is echoed in a response or log line. The router has no prefix;
``api.py`` attaches it to ``api.router`` (prefix ``/api``).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from the_one import time_zones
from the_one.gleepglorp.fill import events
from the_one.gleepglorp.fill.store import (
    FillClaimRefused,
    FillNotFound,
    FillOutcomeRefused,
    GleepGlorpFillRepository,
    fill_view,
)


class _ApiModule:
    def __getattr__(self, name: str) -> Any:
        from the_one.interfaces.web import api

        return getattr(api, name)


_api = _ApiModule()

router = APIRouter()


class FillOutcomeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    status: Literal["filled", "partly_filled", "not_filled"]
    kept: list[str] = []
    reason: Literal["in_chats", "stay", "editor_unavailable", "target_gone"] | None = None


def _not_found(fill_id: int) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Fill not found: {fill_id}")


def _unprocessable(msg: str, field: str) -> HTTPException:
    return HTTPException(status_code=422, detail=[{"loc": ["body", field], "msg": msg}])


@router.get("/gleepglorp/fills")
async def list_gleepglorp_fills(session_id: str = "") -> dict[str, Any]:
    conn = await _api.get_connection()
    if not session_id:
        return {"fills": []}
    rows = await GleepGlorpFillRepository(conn).list_for_session(session_id)
    return {"fills": [await fill_view(conn, r) for r in rows]}


@router.post("/gleepglorp/fills/{fill_id}/claim")
async def claim_gleepglorp_fill(fill_id: int) -> dict[str, Any]:
    conn = await _api.get_connection()
    try:
        fill, token = await GleepGlorpFillRepository(conn).claim(fill_id, time_zones.utcnow())
    except FillNotFound:
        raise _not_found(fill_id) from None
    except FillClaimRefused as e:
        raise HTTPException(
            status_code=409, detail={"error": "claimed", "status": e.status}
        ) from None
    view = await fill_view(conn, fill)
    await events.push_fill_changed(fill.session_id, view)
    return {"fill": view, "claim": token}


@router.post("/gleepglorp/fills/{fill_id}/outcome")
async def report_gleepglorp_fill_outcome(fill_id: int, request: Request) -> dict[str, Any]:
    # The body is read by hand so no 422 ever echoes an input.
    try:
        body = FillOutcomeBody.model_validate(await request.json())
    except (ValidationError, ValueError):
        raise _unprocessable("The outcome is not valid.", "body") from None
    conn = await _api.get_connection()
    repo = GleepGlorpFillRepository(conn)
    current = await repo.get(fill_id)
    if current is None:
        raise _not_found(fill_id)
    if body.status == "filled" and (body.kept or body.reason):
        raise _unprocessable("A filled fill has no kept fields and no reason.", "status")
    if body.status == "partly_filled":
        if not body.kept or body.reason:
            raise _unprocessable("A partly filled fill names kept fields and no reason.", "kept")
        # Bounded by the fill's own keys: no more entries than it has changes, none repeated.
        if len(body.kept) > len(current.changes) or len(set(body.kept)) != len(body.kept):
            raise _unprocessable("kept names more fields than the fill has.", "kept")
        if not set(body.kept) <= set(current.changes):
            raise _unprocessable("kept names a field the fill does not have.", "kept")
    if body.status == "not_filled" and (body.kept or not body.reason):
        raise _unprocessable("A fill not filled has a reason and no kept fields.", "reason")
    try:
        fill = await repo.record_outcome(fill_id, body.claim, body.status, body.kept, body.reason)
    except FillNotFound:
        raise _not_found(fill_id) from None
    except FillOutcomeRefused:
        raise HTTPException(status_code=409, detail={"error": "not_applying"}) from None
    view = await fill_view(conn, fill)
    await events.push_fill_changed(fill.session_id, view)
    return {"fill": view}
