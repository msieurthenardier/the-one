"""GleepGlorp proposal routes (Mission 36 F2 L4, DD7).

Operator-only: behind the credential gate, POST-only for writes, and no GleepGlorp tool reaches
them. The router has no prefix; ``api.py`` attaches it to ``api.router`` (prefix ``/api``).
Handlers reach ``api.py`` helpers through ``_api`` at call time so tests that patch
``get_connection`` and friends still apply.
"""

from __future__ import annotations

from datetime import tzinfo
from typing import Any

from fastapi import APIRouter, HTTPException

from the_one import time_zones
from the_one.gleepglorp.proposals import apply as proposal_apply
from the_one.gleepglorp.proposals.store import GleepGlorpProposalRepository, proposal_view


class _ApiModule:
    def __getattr__(self, name: str) -> Any:
        from the_one.interfaces.web import api

        return getattr(api, name)


_api = _ApiModule()

router = APIRouter()


def _answer(result: proposal_apply.ProposalApplyResult) -> dict[str, Any]:
    """The 200 body, or the 409 for a refusal (none of which wrote anything)."""
    o = result.outcome
    if o in ("applied", "already_applied", "failed", "dismissed"):
        return {"proposal": result.view}
    if o == "stale":
        raise HTTPException(status_code=409, detail={"error": "stale", "fields": result.stale})
    if o == "closed":
        raise HTTPException(status_code=409, detail={"error": "closed", "status": result.status})
    raise HTTPException(status_code=409, detail={"error": o})


def _not_found(proposal_id: int) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")


@router.get("/gleepglorp/proposals")
async def list_gleepglorp_proposals(session_id: str = "") -> dict[str, Any]:
    conn = await _api.get_connection()
    if not session_id:
        return {"proposals": []}
    rows = await GleepGlorpProposalRepository(conn).list_for_session(session_id)
    return {"proposals": [await proposal_view(conn, r) for r in rows]}


@router.post("/gleepglorp/proposals/{proposal_id}/approve")
async def approve_gleepglorp_proposal(proposal_id: int, override: bool = False) -> dict[str, Any]:
    conn = await _api.get_connection()
    deps = await _api._agent_write_deps()

    async def zone() -> tzinfo:
        return (await time_zones.load_effective_zone(conn)).tzinfo

    try:
        result = await proposal_apply.apply_proposal(
            conn, deps, proposal_id, override=override, now=time_zones.utcnow(), zone=zone
        )
    except proposal_apply.ProposalNotFound:
        raise _not_found(proposal_id) from None
    return _answer(result)


@router.post("/gleepglorp/proposals/{proposal_id}/dismiss")
async def dismiss_gleepglorp_proposal(proposal_id: int) -> dict[str, Any]:
    conn = await _api.get_connection()
    try:
        result = await proposal_apply.dismiss_proposal(conn, proposal_id)
    except proposal_apply.ProposalNotFound:
        raise _not_found(proposal_id) from None
    return _answer(result)
