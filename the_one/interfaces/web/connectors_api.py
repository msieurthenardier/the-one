"""Connector account routes, split out of ``api.py`` (Mission 37 F2 L1).

The router has no prefix; ``api.py`` attaches it to ``api.router`` (prefix ``/api``) at the
bottom of that module. Handlers reach ``api.py`` helpers through ``_api`` at call time, so
tests that patch ``the_one.interfaces.web.api.get_connection`` / ``.get_encryptor`` /
``.settings`` and friends still apply. ``/connectors/types`` is declared before
``/connectors/{connector_id}``: routes match in declaration order. The connector test seams
(``/_test/stub/*``, ``/_test/discord/sever``) stay in ``api.py``.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from the_one.agent.write_checks import validation_detail as _validation_detail
from the_one.connectors import registry as connector_registry
from the_one.connectors.base import ConnectorClientError, DoctorReport
from the_one.connectors.manager import PAIRING_TTL_SECONDS
from the_one.connectors.manager import get_manager as get_connector_manager
from the_one.db.models import Connector
from the_one.secret_mask import looks_masked as _looks_masked


class _ApiModule:
    """Call-time lookup of ``api.py`` names (no import at load: ``api`` imports this module)."""

    def __getattr__(self, name: str) -> Any:
        from the_one.interfaces.web import api

        return getattr(api, name)


_api = _ApiModule()

router = APIRouter()

# ── Connector Accounts (Mission 23 Flight 2 Leg 2, DD-7) ───────────────────
#
# Seven CRUD/doctor/pairing routes over the kept ``connectors`` table, plus
# an eighth ``/connectors/types`` route (design review Q2) gating "stub"
# creatability behind the same dual gate as the two test seams below.
# Masking mirrors the MCP source pattern (``Connector.secrets`` is a
# free-form dict like ``MCPSource.secrets``) — reuses ``_mask_secrets`` /
# ``_looks_masked`` verbatim, NOT the single-column ``_mask_api_key``
# pattern. PUT always stops the old listener and starts a fresh one from
# the just-persisted row (Edge Cases: "MUST NOT leave a listener running on
# stale credentials" — unconditional restart is the implementer's-choice
# variation that satisfies this without a connection-relevant-change diff).


def _connector_response(account: Connector) -> dict[str, Any]:
    """Render a Connector into the masked HTTP response shape.

    Mirrors ``_mcp_source_response`` minus the OAuth-managed-keys strip
    (connectors have no OAuth-managed keys) and the ``_cache`` flag (no
    lazy-install cache to reflect). ``model_dump()`` populates
    ``data["secrets"]`` with the decrypted plaintext dict; the overwrite
    below is the load-bearing anti-leak step — see
    ``tests/test_api_secret_mask_roundtrip.py``.
    """
    data = account.model_dump()
    data["secrets"] = _api._mask_secrets(account.secrets)
    return data


def _creatable_connector_types() -> set[str]:
    """Types selectable in the UI / accepted by ``create_connector`` on
    THIS running instance. "discord" is always creatable (Flight 3 ships
    the plugin; the type exists on the model today per DD-1); "telegram"
    joins it unconditionally (Mission 23 Flight 4 DD-1b — the plugin ships
    in leg 2, but the type is admitted here in leg 1's lockstep set same
    as "discord" was in Flight 3). "stub" is creatable only when BOTH
    gates are open — ``settings.dev_mode`` AND
    ``THE_ONE_STUB_TEST_ENDPOINT=1`` — the same dual gate as the two
    ``/_test/stub/...`` seams below and the lifespan startup hook that
    registers the stub plugin (``interfaces/web/app.py``). Mirrors the
    provider/MCP ``/types`` precedent (``list_provider_types`` /
    ``list_mcp_source_types``)."""
    types = {"discord", "telegram"}
    if _api.settings.dev_mode and os.environ.get("THE_ONE_STUB_TEST_ENDPOINT") == "1":
        types.add("stub")
    return types


async def _connector_doctor_warnings(account: Connector) -> list[str]:
    """Binding-health warnings (DD-4 trade-offs): a connector's
    ``default_agent`` may not exist, or may exist but lack the send tool
    — both are operator foot-guns the doctor probe surfaces alongside the
    plugin's own report, never as a crash."""
    from the_one.tools.connector_send import SEND_TO_PLATFORM_CHANNEL_TOOL_NAME

    warnings: list[str] = []
    default_agent = account.config.get("default_agent")
    if not default_agent:
        warnings.append("no default_agent configured — this connector cannot serve traffic")
        return warnings
    store = await _api._agent_store()
    if not await store.exists(default_agent):
        warnings.append(f"default_agent {default_agent!r} does not exist")
        return warnings
    agent_cfg = await store.load(default_agent)
    if not agent_cfg.is_tool_enabled(SEND_TO_PLATFORM_CHANNEL_TOOL_NAME):
        warnings.append(f"agent {default_agent!r} does not have the send tool enabled")
    return warnings


@router.get("/connectors")
async def list_connectors() -> list[dict[str, Any]]:
    repo = await _api._connector_repo()
    return [_connector_response(a) for a in await repo.list()]


@router.get("/connectors/types")
async def list_connector_types() -> list[dict[str, str]]:
    """MUST be registered BEFORE ``/connectors/{connector_id}`` — FastAPI
    matches routes in registration order; reordering would resolve GET
    ``/connectors/types`` to ``get_connector`` with ``connector_id="types"``
    and 404. Mirrors ``list_mcp_source_types`` / ``list_provider_types``."""
    return [{"value": t, "label": t.capitalize()} for t in sorted(_creatable_connector_types())]


@router.get("/connectors/{connector_id}")
async def get_connector(connector_id: str) -> dict[str, Any]:
    repo = await _api._connector_repo()
    try:
        account = await repo.get(connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")
    return _connector_response(account)


@router.post("/connectors", status_code=201)
async def create_connector(request: Request) -> dict[str, Any]:
    data = await _api._read_json(request)
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    # Edge Case: a masked sentinel on CREATE is rejected — there is no
    # stored secret yet to preserve.
    incoming_secrets = data.get("secrets")
    if isinstance(incoming_secrets, dict):
        for key, value in incoming_secrets.items():
            if _looks_masked(value):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"secrets[{key!r}] is a masked placeholder; there is no stored "
                        "secret to preserve on create."
                    ),
                )
    try:
        account = Connector.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=_validation_detail(e))
    if account.type not in _creatable_connector_types():
        raise HTTPException(
            status_code=422,
            detail=f"Connector type {account.type!r} is not creatable on this instance.",
        )
    _api._reject_reserved_binding(account.config)
    repo = await _api._connector_repo()
    await repo.create(account)
    # Edge Case: a connector must start listening on create, not only on
    # the next app restart. DD-6: honor ``enabled`` (absent key = enabled)
    # — a connector created with ``enabled: false`` does not start.
    manager = get_connector_manager()
    if manager is not None and account.config.get("enabled", True) is not False:
        manager.start(account, _api.get_encryptor(_api.settings.data_dir), repo=repo)
    return _connector_response(account)


def _merge_paired_peers(stored_config: Any, incoming: Any, base: list[str]) -> Any:
    """Three-way merge of ``allowlist.peers`` (squawk 0288).

    Result: the operator's incoming peers, then peers present in the stored
    config but not in ``base`` (paired since the editor loaded). Returns a
    copy of ``incoming`` with the merged peers, or ``incoming`` itself when
    its shape is malformed so the model validator raises its usual 422.
    Never mutates its arguments.
    """
    if not isinstance(incoming, dict):
        return incoming
    allowlist = incoming.get("allowlist")
    if allowlist is not None and not isinstance(allowlist, dict):
        return incoming
    in_peers = (allowlist or {}).get("peers")
    if in_peers is None:
        in_peers = []
    if not isinstance(in_peers, list) or not all(isinstance(p, str) for p in in_peers):
        return incoming
    stored_al = stored_config.get("allowlist") if isinstance(stored_config, dict) else None
    stored_peers = stored_al.get("peers") if isinstance(stored_al, dict) else None
    if not isinstance(stored_peers, list):
        stored_peers = []
    base_set = set(base)
    merged_peers = list(dict.fromkeys(in_peers))
    for p in stored_peers:
        if isinstance(p, str) and p not in base_set and p not in merged_peers:
            merged_peers.append(p)
    if not merged_peers:
        return incoming
    out = dict(incoming)
    out_al = dict(allowlist or {})
    out_al["peers"] = merged_peers
    out["allowlist"] = out_al
    return out


@router.put("/connectors/{connector_id}")
async def update_connector(connector_id: str, request: Request) -> dict[str, Any]:
    data = await _api._read_json(request)
    data["id"] = connector_id
    repo = await _api._connector_repo()
    try:
        existing = await repo.get(connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")

    # Per-key __MASKED__ resolution — verbatim mirror of the MCP source PUT
    # handler's block (minus the OAuth-managed-keys step, which has no
    # connector analog).
    incoming_secrets = data.get("secrets")
    if incoming_secrets is not None:
        if not isinstance(incoming_secrets, dict):
            raise HTTPException(status_code=422, detail="secrets must be a dict.")
        resolved_secrets: dict[str, Any] = {}
        for key, value in incoming_secrets.items():
            if _looks_masked(value):
                if key in existing.secrets:
                    resolved_secrets[key] = existing.secrets[key]
                # else: client sent __MASKED__ for a key we don't have; drop
                # it silently — same as an omitted key.
            else:
                resolved_secrets[key] = value
        data["secrets"] = resolved_secrets

    # Squawk 0288: the editor sends the peers it last loaded/saved so a peer
    # paired meanwhile (``_pair_peer``) survives a stale Save. Never stored.
    peers_base = data.pop("allowlist_peers_base", None)
    if peers_base is not None:
        if not isinstance(peers_base, list) or not all(isinstance(p, str) for p in peers_base):
            raise HTTPException(
                status_code=422, detail="allowlist_peers_base must be a list of strings."
            )
        data["config"] = _merge_paired_peers(existing.config, data.get("config"), peers_base)

    # ``model_copy(update=...)`` does NOT re-run field validators in
    # Pydantic v2 — round-trip through model_dump()|data→model_validate so
    # the DD-2 config validator fires on the merged payload. Mirrors
    # ``update_mcp_source``.
    try:
        merged = existing.model_dump()
        merged.update(data)
        updated = Connector.model_validate(merged)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=_validation_detail(e))
    if updated.type not in _creatable_connector_types():
        raise HTTPException(
            status_code=422,
            detail=f"Connector type {updated.type!r} is not creatable on this instance.",
        )
    _api._reject_reserved_binding(updated.config)
    await repo.update(updated)

    # PUT restarting semantics (DD-6, amended leg-2 design review
    # 2026-09-01): branch on the NEW row's effective ``enabled`` value
    # ONLY — never on whether it changed. Effective true (covers
    # enabled→enabled config edits AND disabled→enabled) → today's
    # unconditional stop+start, satisfying "no stale-credential listener
    # survives a save". Effective false (covers enabled→disabled AND
    # disabled→disabled) → stop only, NEVER start — the original
    # "restart-as-today" framing let a disabled→disabled PUT on an
    # unrelated field wake a listener that should stay down. ``repo`` is
    # threaded through so the DD-Q3 rotation fix's fresh-row re-fetch
    # applies to this listener's future reconnects too.
    # Squawk 0033: this stop() before start() is load-bearing — see the
    # stale-entry invariant documented on ConnectorManager._run's
    # PermanentConnectorFailure branch (connectors/manager.py).
    manager = get_connector_manager()
    if manager is not None:
        await manager.stop(connector_id)
        if updated.config.get("enabled", True) is not False:
            manager.start(updated, _api.get_encryptor(_api.settings.data_dir), repo=repo)

    return _connector_response(updated)


@router.delete("/connectors/{connector_id}")
async def delete_connector(connector_id: str) -> dict[str, str]:
    """DELETE stops the listener BEFORE the row dies (DD-7); DD-1g's
    directory cleanup runs after the connector row itself is confirmed
    gone (a deterministic DELETE — no FK/cascade, per DD-4)."""
    repo = await _api._connector_repo()
    try:
        await repo.get(connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")
    manager = get_connector_manager()
    if manager is not None:
        await manager.stop(connector_id)
    try:
        await repo.delete(connector_id)
    except KeyError:
        # Race: another caller deleted between our get and delete.
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")
    directory_repo = await _api._connector_directory_repo()
    await directory_repo.delete_for_connector(connector_id)
    return {"status": "ok"}


@router.post("/connectors/{connector_id}/test")
async def test_connector(connector_id: str) -> dict[str, Any]:
    """Doctor probe: plugin report + binding-health warnings (DD-4).

    With no plugin registered for the type — the NORM this flight, since
    Discord lands Flight 3 — this returns a clean degraded/failed report,
    never a crash (design review catch #1). Doctor runs on a disabled
    connector too — diagnosis, not traffic — and the response's
    ``disabled`` field distinctly marks that state (DD-6, Mission 23
    Flight 3 Leg 2; supersedes the prior "no enabled gate to check" note).
    A connector can be both disabled AND carry a stale plugin-side
    permanent-failure marker (disabled after a permanent failure); the two
    facts are independent and both surface — disabled never masks a prior
    failure, and vice versa.
    """
    repo = await _api._connector_repo()
    try:
        account = await repo.get(connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")

    plugin = connector_registry.get_plugin(account.type)
    if plugin is None:
        report = DoctorReport(
            status="failed",
            message=f"no plugin registered for type {account.type!r}",
        )
    else:
        try:
            report = await plugin.doctor(account, _api.get_encryptor(_api.settings.data_dir))
        except ConnectorClientError as exc:
            report = DoctorReport(status="failed", message=str(exc))
        except Exception as exc:
            _api.logger.exception("connector %s: doctor probe raised", connector_id)
            report = DoctorReport(status="failed", message=f"doctor probe raised: {exc}")

    warnings = await _connector_doctor_warnings(account)
    return {
        "status": report.status,
        "message": report.message,
        "details": report.details,
        "warnings": warnings,
        "disabled": account.config.get("enabled", True) is False,
    }


@router.post("/connectors/{connector_id}/pairing-code")
async def generate_connector_pairing_code(connector_id: str) -> dict[str, str]:
    """Generate (or regenerate) the one-time pairing code (DD-3).

    404s on an unknown connector id — repo-checked FIRST, before touching
    the manager's in-memory pairing store. A second request replaces
    (invalidates) the first: ``ConnectorManager.generate_pairing_code``
    simply overwrites the prior ``_PairingEntry`` for this connector id.
    Allowed even when the connector's listener isn't running — the code
    just expires unused by TTL (Edge Case, stated rather than left
    implicit).
    """
    repo = await _api._connector_repo()
    try:
        await repo.get(connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")
    manager = get_connector_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="connector manager is not running")
    code = manager.generate_pairing_code(connector_id)
    from datetime import datetime, timedelta, timezone

    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=PAIRING_TTL_SECONDS)).isoformat()
    return {"code": code, "expires_at": expires_at}
