"""M11 F15 L4 — multi-user routing + per-user ACL differentiation HAT.

Drives all three burner bots into ONE channel and proves, against the real
guild, the mission #5 / #13 shapes:

  * **Topology (#5):** the three bots resolve to ONE channel-scoped session
    (sessions key on ``(platform, connector_id, channel_id, thread_id)`` —
    ``peer_id`` excluded — so a shared channel is one conversation).
  * **Attribution (#13):** each bot's inbound message carries its own F6
    ``peer_name`` (its Discord display name) — no collapse, no blanks.
  * **Per-user ACL differentiation (#5):** a per-agent overlay on Connector
    Agent 1 narrowing ``peers`` to bot0/bot1 (with ``channels: None`` so guild
    messages stay admitted) routes bot0 → Agent 1 but falls bot2 through to
    Agent 2 (first-eligible-alphabetical). Because routing entries carry no
    ``peer_id``, the bots are posted ONE AT A TIME and the single new entry's
    ``agent`` is read — that is the only reliable peer→agent correlation.
  * **Hard-deny → no-eligible (#5):** narrowing BOTH agents to exclude bot2
    makes a bot2 mention route to ``no-eligible`` (every agent denies).

The overlay mutates the operator's LIVE agents, so both agents'
``connector_acls`` are captured before and RESTORED in a ``finally`` (to the
captured prior value, not a hardcoded null) — a mid-test failure must not leave
the operator's agents narrowed, and a second run must pass without manual
cleanup.

Skips cleanly when the HAT env is not provisioned (the default state).
"""

from __future__ import annotations

import uuid

import pytest

from .config import skip_if_unconfigured
from .driver import (
    BotDriver,
    inbound_peer_names,
    post_and_wait_new_routing,
    restore_agent_connector_acls,
    set_agent_connector_acl,
    wait_for_session,
)
from .report import HatReport

# The two agents attached to the test connector, in alphabetical order (which
# is the first-eligible iteration order the routing layer uses).
_AGENT_1 = "Connector Agent 1"
_AGENT_2 = "Connector Agent 2"

# Sentinel distinguishing "overlay not yet captured" from a legitimately-None
# prior, so the restore-finally skips an agent we never mutated.
_UNSET = object()


@pytest.mark.discord_hat
async def test_multi_user_routing_live() -> None:
    cfg = skip_if_unconfigured()
    if not cfg.bot_user_ids:
        pytest.skip(
            "THE_ONE_HAT_BOT_USER_IDS not set — required for the ACL peers axis "
            "(add comma-separated burner-bot user ids to .env.hat)"
        )
    report = HatReport()
    # Unique per-run nonce so re-runs don't read a prior run's attribution.
    nonce = uuid.uuid4().hex[:8]
    channel_id = cfg.channel_ids[0]
    account_id = cfg.connector_id
    base = cfg.base_url

    # Captured pre-test overlays — restored in the finally (None is a
    # legitimate prior; the _UNSET sentinel marks an un-mutated agent).
    prior_agent1: object = _UNSET
    prior_agent2: object = _UNSET

    async with BotDriver(cfg) as bots:
        # The three bots' display names — the F6 peer_name attribution target.
        bot_names = [bots._clients[i].user.display_name for i in range(3)]  # noqa: SLF001 — own clients

        try:
            # ── Phase A — topology + attribution (no overlay) ─────────────
            # Post an @mention from each of the three bots into the shared
            # channel. Each engaged post drives an agent.step (LLM, seconds)
            # under a per-session lock, so the three serialize — wait for all
            # three distinct peer_names to land.
            for i in range(3):
                await bots.post(i, channel_id, bots.mention(f"u{nonce} from b{i}"))

            detail = await wait_for_session(
                base,
                cfg.connector_id,
                channel_id,
                until=lambda d: len(set(inbound_peer_names(d))) >= 3,
                timeout=180.0,
            )

            # ONE stable session id for the channel (the lookup seam returns
            # the same id across all three posts — topology #5).
            session_id = detail.get("id")
            seen_names = set(inbound_peer_names(detail))
            missing = [n for n in bot_names if n not in seen_names]
            assert not missing, (
                f"expected all 3 bot display names attributed in the shared "
                f"session; missing {missing!r} (saw {sorted(seen_names)!r})"
            )
            report.record(
                "#5 topology — 3 bots → ONE channel-scoped session",
                "PASS",
                f"single session id={session_id!r}; "
                f"{len(seen_names)} distinct inbound peer_names",
            )
            report.record(
                "#13 attribution — F6 peer_name per bot",
                "PASS",
                f"inbound peer_names ⊇ {sorted(bot_names)!r}",
            )

            # ── Phase B — per-user ACL routing differentiation ────────────
            # Capture BOTH agents' prior overlays first (for restore), then
            # narrow Agent 1 to bot0/bot1. channels: None (inherit) — NOT []
            # (the DMs-only trap that would deny all guild messages).
            prior_agent1 = await set_agent_connector_acl(
                base,
                _AGENT_1,
                account_id,
                {
                    "peers": [{"id": cfg.bot_user_ids[0]}, {"id": cfg.bot_user_ids[1]}],
                    "channels": None,
                },
            )
            # Agent 2 stays untouched in Phase B (bot2 must fall through to it
            # un-narrowed). Its prior is captured when Phase C narrows it (the
            # set helper returns the prior) — and if the test fails before
            # Phase C, Agent 2 was never mutated, so prior_agent2 stays _UNSET
            # and the finally skips its restore.
            #
            # bot0 (admitted by Agent 1) → new stepped entry, agent == Agent 1.
            entry_b0 = await post_and_wait_new_routing(
                base,
                cfg.connector_id,
                channel_id,
                bots,
                0,
                bots.mention(f"u{nonce} aclB b0"),
                timeout=90.0,
            )
            assert entry_b0["disposition"] == "stepped", (
                f"bot0 is Agent-1-admitted → expected stepped; got "
                f"{entry_b0.get('disposition')!r} (overlay may not have taken — "
                f"agent store caching would be a product finding)"
            )
            assert entry_b0["agent"] == _AGENT_1, (
                f"bot0 admitted by Agent 1's overlay → expected agent="
                f"{_AGENT_1!r}; got {entry_b0.get('agent')!r}"
            )

            # bot2 (denied by Agent 1, falls through) → stepped, agent == Agent 2.
            entry_b2 = await post_and_wait_new_routing(
                base,
                cfg.connector_id,
                channel_id,
                bots,
                2,
                bots.mention(f"u{nonce} aclB b2"),
                timeout=90.0,
            )
            assert entry_b2["disposition"] == "stepped", (
                f"bot2 falls through to Agent 2 (no overlay there yet) → "
                f"expected stepped; got {entry_b2.get('disposition')!r}"
            )
            assert entry_b2["agent"] == _AGENT_2, (
                f"bot2 denied by Agent 1 → first-eligible falls through to "
                f"{_AGENT_2!r}; got {entry_b2.get('agent')!r}"
            )
            report.record(
                "#5 per-user ACL differentiation (same channel, 2 agents)",
                "PASS",
                f"bot0 → {_AGENT_1!r} (admitted); "
                f"bot2 → {_AGENT_2!r} (Agent-1-denied, fell through)",
            )

            # ── Phase C — hard-deny → no-eligible (attempt) ───────────────
            # Narrow BOTH agents to bot0/bot1 (exclude bot2). Agent 1 already
            # carries that overlay; set Agent 2 the same way (capturing its
            # prior). A bot2 @mention now finds every agent denying → the
            # routing layer collapses to no-eligible (no LLM step — fast).
            prior_agent2 = await set_agent_connector_acl(
                base,
                _AGENT_2,
                account_id,
                {
                    "peers": [{"id": cfg.bot_user_ids[0]}, {"id": cfg.bot_user_ids[1]}],
                    "channels": None,
                },
            )
            entry_c = await post_and_wait_new_routing(
                base,
                cfg.connector_id,
                channel_id,
                bots,
                2,
                bots.mention(f"u{nonce} aclC b2"),
                timeout=90.0,
            )
            assert entry_c["disposition"] == "no-eligible", (
                f"bot2 excluded by BOTH agents' overlays → expected "
                f"no-eligible; got {entry_c.get('disposition')!r}"
            )
            report.record(
                "#5 hard-deny — bot2 excluded by both agents → no-eligible",
                "PASS",
                f"disposition={entry_c['disposition']!r} (every agent denied)",
            )

        finally:
            # Restore BOTH agents' connector_acls to their captured prior
            # values (None is a legitimate prior). Skip a restore only if we
            # never mutated that agent (sentinel still set).
            if prior_agent1 is not _UNSET:
                await restore_agent_connector_acls(
                    base, _AGENT_1, prior_agent1  # type: ignore[arg-type]
                )
            if prior_agent2 is not _UNSET:
                await restore_agent_connector_acls(
                    base, _AGENT_2, prior_agent2  # type: ignore[arg-type]
                )

    # Surface the evidence table in pytest output for the FD's run record.
    print("\n" + report.render())
