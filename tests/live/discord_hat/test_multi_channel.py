"""M11 F15 L5 — multi-channel routing + channel-scoped override HAT.

Drives one burner bot into THREE separate channels and proves, against the
real guild, mission criterion #6 (multi-channel routing):

  * **Per-channel default routing (#6):** with connector ``config.routing`` set
    to channel-scope rules ch1→Agent 1, ch2→Agent 2 and a per-account
    ``default`` of Agent 1, an ``@mention`` in **ch1** routes (in ch1's own
    session) to Agent 1 via ``scope=="channel"``; an ``@mention`` in **ch2**
    routes (in ch2's SEPARATE session) to Agent 2 via ``scope=="channel"``.
  * **Default fall-through (#6):** an ``@mention`` in **ch3** (no matching
    rule) routes to the per-account ``default`` (Agent 1) via
    ``scope=="default"`` — distinguishing rule-match from default.
  * **Separate sessions (#6):** the three channels resolve to three DISTINCT
    session ids (sessions key on ``(platform, connector_id, channel_id,
    thread_id)`` — distinct ``channel_id`` → distinct session).
  * **Channel-scoped override (#6):** adding a ch3→Agent 2 channel rule and
    re-posting in **ch3** re-routes it away from the default — the new entry
    shows ``agent=="Connector Agent 2"``, ``scope=="channel"``,
    ``reason=="rule-match"``.

The mutation targets the operator's LIVE connector ``config.routing``, so the
prior value is captured before any change and RESTORED in a ``finally`` (to the
captured prior — ``None`` when no routing was configured, NOT a hardcoded
value). The bot token is never touched (every connector PUT omits ``secrets``).

Skips cleanly when the HAT env is not provisioned (the default state).
"""

from __future__ import annotations

import uuid

import pytest

from .config import skip_if_unconfigured
from .driver import (
    BotDriver,
    latest_routing_entry,
    post_and_wait_new_routing,
    restore_connector_routing,
    set_connector_routing,
    wait_for_session,
)
from .report import HatReport

# The two agents attached to the test connector.
_AGENT_1 = "Connector Agent 1"
_AGENT_2 = "Connector Agent 2"


@pytest.mark.discord_hat
async def test_multi_channel_routing_live() -> None:
    cfg = skip_if_unconfigured()
    report = HatReport()
    # Unique per-run nonce so re-runs don't read a prior run's routing entry.
    nonce = uuid.uuid4().hex[:8]
    base = cfg.base_url
    cid = cfg.connector_id
    ch1, ch2, ch3 = cfg.channel_ids[0], cfg.channel_ids[1], cfg.channel_ids[2]

    # Set the per-channel routing rules + a per-account default. ``match`` is a
    # LIST ([channel_id]); the routing dict needs BOTH "rules" and "default".
    # Capture the prior routing for an exact restore in the finally.
    prior = await set_connector_routing(
        base,
        cid,
        {
            "rules": [
                {"scope": "channel", "match": [ch1], "agent": _AGENT_1},
                {"scope": "channel", "match": [ch2], "agent": _AGENT_2},
            ],
            "default": _AGENT_1,
        },
    )

    try:
        async with BotDriver(cfg) as bots:
            # ── Per-channel default routing (#6) ──────────────────────────
            # PRIME each cold channel with a direct post + wait. We do NOT use
            # post_and_wait_new_routing as the FIRST contact: it requires a
            # pre-existing session (it snapshots the routing length first) and
            # would time out on a cold channel. ch1/ch2 hit a channel rule
            # (scope=="channel"); ch3 has no rule → the per-account default
            # catches it (scope=="default"), still disposition=="stepped".
            session_ids: list[str] = []
            for channel_id, expected_agent, expected_scope in (
                (ch1, _AGENT_1, "channel"),
                (ch2, _AGENT_2, "channel"),
                (ch3, _AGENT_1, "default"),
            ):
                await bots.post(0, channel_id, bots.mention(f"mc {nonce} {channel_id}"))
                detail = await wait_for_session(
                    base,
                    cid,
                    channel_id,
                    until=lambda d: (latest_routing_entry(d) or {}).get("disposition") == "stepped",
                    timeout=120.0,
                )
                entry = latest_routing_entry(detail)
                assert entry is not None  # guaranteed by the until predicate
                assert entry["agent"] == expected_agent, (
                    f"channel {channel_id} routed to {entry.get('agent')!r}; "
                    f"expected {expected_agent!r} "
                    f"(scope={entry.get('scope')!r}, reason={entry.get('reason')!r})"
                )
                assert entry["scope"] == expected_scope, (
                    f"channel {channel_id} routed via scope={entry.get('scope')!r}; "
                    f"expected {expected_scope!r} (agent={entry.get('agent')!r})"
                )
                session_ids.append(detail["id"])

            report.record(
                "#6 per-channel routing — ch1→Agent 1, ch2→Agent 2 (channel rules)",
                "PASS",
                f"ch1→{_AGENT_1!r} scope=channel; ch2→{_AGENT_2!r} scope=channel",
            )
            report.record(
                "#6 default fall-through — ch3 (no rule) → per-account default",
                "PASS",
                f"ch3→{_AGENT_1!r} scope=default (no matching channel rule)",
            )

            # Three distinct channels → three distinct channel-keyed sessions.
            assert len(set(session_ids)) == 3, (
                f"expected 3 distinct channel-keyed sessions; got {session_ids!r}"
            )
            report.record(
                "#6 separate sessions — ch1/ch2/ch3 → 3 distinct session ids",
                "PASS",
                f"distinct session ids: {session_ids!r}",
            )

            # ── Channel-scoped override (#6) ──────────────────────────────
            # ch3's session now EXISTS (from the prime above), so
            # post_and_wait_new_routing is correct here. Add a ch3→Agent 2
            # channel rule (override the default) and re-post in ch3: the NEW
            # routing entry must show the override won (scope=channel, Agent 2).
            await set_connector_routing(
                base,
                cid,
                {
                    "rules": [
                        {"scope": "channel", "match": [ch1], "agent": _AGENT_1},
                        {"scope": "channel", "match": [ch2], "agent": _AGENT_2},
                        {"scope": "channel", "match": [ch3], "agent": _AGENT_2},
                    ],
                    "default": _AGENT_1,
                },
            )
            entry = await post_and_wait_new_routing(
                base,
                cid,
                ch3,
                bots,
                0,
                bots.mention(f"mc-override {nonce}"),
                timeout=120.0,
            )
            assert entry["agent"] == _AGENT_2, (
                f"ch3 override → expected agent={_AGENT_2!r}; got {entry.get('agent')!r}"
            )
            assert entry["scope"] == "channel", (
                f"ch3 override → expected scope='channel'; got {entry.get('scope')!r}"
            )
            assert entry["reason"] == "rule-match", (
                f"ch3 override → expected reason='rule-match'; got {entry.get('reason')!r}"
            )
            report.record(
                "#6 channel-scoped override — ch3 rule re-routes away from default",
                "PASS",
                f"ch3→{_AGENT_2!r} scope=channel reason=rule-match (was default→Agent 1)",
            )
    finally:
        # Restore the connector's routing to the captured prior value (None is
        # a legitimate prior — "no routing configured"). The token/allowlist
        # are never touched (every PUT omits `secrets`). Re-runnable.
        await restore_connector_routing(base, cid, prior)

    # Surface the evidence table in pytest output for the FD's run record.
    print("\n" + report.render())
