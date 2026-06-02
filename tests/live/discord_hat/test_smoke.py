"""M11 F15 L3 — the live-traffic HAT smoke scenario.

Makes the three load-bearing premises (bot-peer equivalence,
author-agnostic ``@mention``, channel-shared-vs-DM-isolated topology)
empirical with real bot traffic before L4–L6 assert against them.

Preconditions (operator-provisioned, see the leg's Context):
  - the test connector has ``ingest_bots=true`` (bots ingested as peers)
    and ``always_listen=FALSE`` (so non-mention → ``policy-silent`` with
    ``policy.outcome == "always-listen-off"``, the negative control).
  - the HAT env is set (else the test SKIPs — the default state).

Asserts ONLY against fields that exist on the real shapes (per the leg's
observability-gap analysis): a ``stepped`` routing ``disposition`` for the
mention (NOT ``policy.outcome``/``peer_id`` — those are absent on the
engaged path), F6 ``peer_name`` for bot-peer ingestion, and a distinct DM
session id for topology.
"""

from __future__ import annotations

import uuid

import pytest

from .config import skip_if_unconfigured
from .driver import (
    BotDriver,
    inbound_peer_names,
    latest_routing_entry,
    wait_for_session,
)
from .report import HatReport


@pytest.mark.discord_hat
async def test_smoke_live_premises() -> None:
    cfg = skip_if_unconfigured()
    report = HatReport()
    # Unique nonce so re-runs don't read a stale prior message's attribution.
    nonce = uuid.uuid4().hex[:8]
    channel_id = cfg.channel_ids[0]

    async with BotDriver(cfg) as bots:
        # ── (engage) @mention → stepped ──────────────────────────────────
        await bots.post(0, channel_id, bots.mention(f"smoke ping {nonce}"))
        # The session row appears early in dispatch, but the inbound message +
        # peer_name + the engaged routing entry persist only after agent.step()
        # finishes the LLM call (seconds later). Poll the detail until the
        # inbound message lands, so we don't race the dispatch.
        detail = await wait_for_session(
            cfg.base_url,
            cfg.connector_id,
            channel_id,
            until=lambda d: bool(inbound_peer_names(d)),
        )
        entry = latest_routing_entry(detail)
        assert entry is not None, "no routing entry on the connector-attached session"
        assert entry["disposition"] == "stepped", (
            f"expected the @mention to engage (disposition=stepped); "
            f"got {entry.get('disposition')!r}"
        )
        report.record(
            "author-agnostic @mention engages (stepped)",
            "PASS",
            f"routing disposition={entry['disposition']!r} after bot[0] @mention",
        )

        # ── (attribution / bot-peer ingestion) F6 peer_name ──────────────
        peer_names = inbound_peer_names(detail)
        assert peer_names, "no inbound (role=user) messages carried a peer_name"
        bot0_name = bots._clients[0].user.display_name  # noqa: SLF001 — own client
        assert bot0_name in peer_names, (
            f"bot[0] display name {bot0_name!r} not in inbound peer_names "
            f"{peer_names!r} (bot-peer ingestion / F6 attribution)"
        )
        report.record(
            "bot-peer equivalence (F6 peer_name on inbound)",
            "PASS",
            f"inbound peer_name {bot0_name!r} present",
        )

        # ── (negative control) non-mention → policy-silent ───────────────
        await bots.post(0, channel_id, f"smoke non-mention {nonce}")
        # The non-mention adds a fresh routing entry; poll until the LATEST
        # entry flips to policy-silent (it's quick — no LLM step on the silent
        # path — but still not instantaneous vs the gateway round-trip).
        neg_detail = await wait_for_session(
            cfg.base_url,
            cfg.connector_id,
            channel_id,
            until=lambda d: (latest_routing_entry(d) or {}).get("disposition")
            == "policy-silent",
        )
        neg_entry = latest_routing_entry(neg_detail)
        assert neg_entry is not None
        assert neg_entry["disposition"] == "policy-silent", (
            f"expected non-mention to be policy-silent (always_listen=FALSE); "
            f"got {neg_entry.get('disposition')!r}"
        )
        assert neg_entry.get("policy", {}).get("outcome") == "always-listen-off", (
            f"expected policy.outcome=always-listen-off; got "
            f"{neg_entry.get('policy')!r}"
        )
        report.record(
            "negative control (non-mention → policy-silent/always-listen-off)",
            "PASS",
            f"disposition={neg_entry['disposition']!r} "
            f"policy.outcome={neg_entry['policy']['outcome']!r}",
        )

        # ── (topology) DM → separate session ─────────────────────────────
        # DEFERRED to L7's human pass. A Discord *bot cannot DM another bot*
        # (REST 50007 "Cannot send messages to this user"), so a driver bot
        # cannot DM the-one's GleepGlorp bot to exercise the DM path. The
        # DM-isolated-session premise (a DM keys on its own channel_id →
        # separate session, the "channel of 1") is verified live in L7 with a
        # real human DM (which Discord permits). The substrate guarantee is
        # `_discord_translate.py:99` (DM channel_id = message.channel.id).
        report.record(
            "channel-shared-vs-DM-isolated topology",
            "DEFERRED",
            "bot-to-bot DM blocked by Discord (50007); DM isolation verified "
            "via a real human DM in L7's pairing/mentions pass",
        )

    # Surface the evidence table in pytest output for the FD's run record.
    print("\n" + report.render())
