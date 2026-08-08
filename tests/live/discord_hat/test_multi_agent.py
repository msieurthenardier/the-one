"""M11 F15 L6 — multi-agent ``/talk-to`` override routing HAT.

Drives one burner bot into test-channel-2 and proves, against the real guild,
the one remaining facet of mission criterion #7 (multi-peer / multi-agent
routing): the **peer-issued ``/talk-to <agent>`` override**. A bot issues the
text-prefix ``/talk-to`` command (parsed at dispatch step 11, BEFORE the policy
gate — so it needs NO ``@mention`` and is intercepted with ``disposition ==
"command-intercepted"``, never reaching the engagement gate); the override is
written to ``session_metadata["routing_override"]``. The bot's NEXT ``@mention``
in that session then routes via routing **step 1 — override**
(``scope == "override"``, ``reason == "override"``), taking precedence over
channel rules (step 2) and first-eligible (step 4).

  * **Phase A — override takes effect (#7):** ``/talk-to Connector Agent 2`` is
    command-intercepted (``intercept_source == "builtin"`` — the built-in
    handler fired); the next ``@mention`` routes to Agent 2 via
    ``scope == "override"``.
  * **Phase B — override beats a channel rule (#7):** with a ch2 → Agent 1
    channel rule set, a re-issued ``/talk-to Connector Agent 2`` + ``@mention``
    STILL routes to Agent 2 (``scope == "override"``) — step-1 override
    precedence over the step-2 rule.
  * **Phase C — dynamic re-override (#7):** ``/talk-to Connector Agent 1`` +
    ``@mention`` re-routes to Agent 1 (``scope == "override"``) — the override
    is re-settable at runtime.

The other #7 facets — multiple agents on one connector, multiple peers, and the
per-(agent, peer) ACL precedent — were already verified live in **L4** (PASS
4/4); this leg cites that and closes the override facet.

Phase B mutates the operator's LIVE connector ``config.routing``, so the prior
value is captured before any change and RESTORED in a ``finally`` (to the
captured prior — ``None`` when no routing was configured, NOT a hardcoded
value). The token is never touched (every connector PUT omits ``secrets``).
Cleanup also posts ``/new`` to rotate the session (the ``ended_at`` sentinel),
which clears the ``routing_override`` so a second run starts override-free.

Skips cleanly when the HAT env is not provisioned (the default state).
"""

from __future__ import annotations

import uuid

import pytest

from .config import auth_headers, skip_if_unconfigured
from .driver import (
    BotDriver,
    post_and_wait_new_routing,
    restore_connector_routing,
    set_connector_routing,
)
from .report import HatReport

# The two agents attached to the test connector.
_AGENT_1 = "Connector Agent 1"
_AGENT_2 = "Connector Agent 2"


@pytest.mark.discord_hat
async def test_multi_agent_routing_live() -> None:
    cfg = skip_if_unconfigured()
    report = HatReport()
    # Unique per-run nonce so re-runs don't read a prior run's routing entry.
    nonce = uuid.uuid4().hex[:8]
    base = cfg.base_url
    cid = cfg.connector_id
    # test-channel-2 — a clean lane (L4 used ch1, L5 exercised ch1-3 rules);
    # assertions read the LATEST routing entry so prior state doesn't interfere.
    ch2 = cfg.channel_ids[1]

    # Capture the connector's prior routing for an exact restore in the finally.
    # `set_connector_routing` (Phase B) returns this too, but Phase A runs
    # first WITHOUT a routing change, so capture it explicitly up front.
    prior_routing = await _get_connector_routing(base, cid)

    # All three phases must complete within the connector's
    # `session_continuation_seconds` window: each phase's `@mention` must land
    # in the SAME session the preceding `/talk-to` set the override on. At
    # interactive HAT speed (a handful of commands + LLM steps, well under a
    # minute total) this is comfortable — but a stalled run that idles past the
    # continuation window would rotate the session mid-phase and drop the
    # override, so don't pad the phases with long sleeps.
    try:
        async with BotDriver(cfg) as bots:
            # ── Phase A — override takes effect (#7) ──────────────────────
            # `/talk-to` is intercepted at step 11 (no @mention needed, no LLM
            # step). The built-in handler sets the override → command-intercepted
            # with intercept_source == "builtin".
            e = await post_and_wait_new_routing(
                base,
                cid,
                ch2,
                bots,
                0,
                f"/talk-to {_AGENT_2}",
                until_entry=lambda x: x.get("disposition") == "command-intercepted",
                timeout=120.0,
            )
            assert e["disposition"] == "command-intercepted", (
                f"/talk-to should be intercepted at step 11; got "
                f"disposition={e.get('disposition')!r}"
            )
            # Cheap extra signal: the BUILT-IN handler (not a plugin) fired.
            assert e.get("intercept_source") == "builtin", (
                f"expected the built-in /talk-to handler to fire "
                f"(intercept_source='builtin'); got {e.get('intercept_source')!r}"
            )

            # The NEXT @mention routes via step-1 override to Agent 2.
            e2 = await post_and_wait_new_routing(
                base,
                cid,
                ch2,
                bots,
                0,
                bots.mention(f"ma {nonce}"),
                timeout=120.0,
            )
            assert e2["scope"] == "override", (
                f"after /talk-to {_AGENT_2!r}, the next @mention should route via "
                f"scope='override'; got {e2.get('scope')!r} "
                f"(agent={e2.get('agent')!r}, reason={e2.get('reason')!r})"
            )
            assert e2["agent"] == _AGENT_2, (
                f"override should route to {_AGENT_2!r}; got {e2.get('agent')!r}"
            )
            assert e2["reason"] == "override", (
                f"override entry should carry reason='override'; got {e2.get('reason')!r}"
            )
            report.record(
                "#7 /talk-to override — intercept + next @mention routes to target",
                "PASS",
                f"/talk-to {_AGENT_2!r} → command-intercepted (builtin); "
                f"next @mention → {_AGENT_2!r} scope=override reason=override",
            )

            # ── Phase B — override beats a channel rule (#7) ──────────────
            # Set a ch2 → Agent 1 channel rule. A re-issued /talk-to Agent 2 +
            # @mention must STILL route to Agent 2 (step-1 override > step-2
            # rule). The override from Phase A persists, but re-issue it for
            # clarity. set_connector_routing returns the SAME prior we captured
            # up front; discard it (prior_routing already holds the restore
            # value).
            await set_connector_routing(
                base,
                cid,
                {
                    "rules": [
                        {"scope": "channel", "match": [ch2], "agent": _AGENT_1},
                    ],
                    "default": _AGENT_1,
                },
            )
            e3 = await post_and_wait_new_routing(
                base,
                cid,
                ch2,
                bots,
                0,
                f"/talk-to {_AGENT_2}",
                until_entry=lambda x: x.get("disposition") == "command-intercepted",
                timeout=120.0,
            )
            assert e3["disposition"] == "command-intercepted", (
                f"re-issued /talk-to should be intercepted; got "
                f"disposition={e3.get('disposition')!r}"
            )
            e4 = await post_and_wait_new_routing(
                base,
                cid,
                ch2,
                bots,
                0,
                bots.mention(f"ma-rule {nonce}"),
                timeout=120.0,
            )
            assert e4["scope"] == "override", (
                f"override must beat the ch2→{_AGENT_1!r} channel rule "
                f"(scope='override' wins over scope='channel'); "
                f"got scope={e4.get('scope')!r} agent={e4.get('agent')!r}"
            )
            assert e4["agent"] == _AGENT_2, (
                f"override should route to {_AGENT_2!r} despite the ch2→"
                f"{_AGENT_1!r} rule; got {e4.get('agent')!r}"
            )
            report.record(
                "#7 override beats channel rule — ch2→Agent1 rule overridden to Agent2",
                "PASS",
                f"with ch2→{_AGENT_1!r} rule set, /talk-to {_AGENT_2!r} + @mention "
                f"→ {_AGENT_2!r} scope=override (step-1 override > step-2 rule)",
            )

            # ── Phase C — dynamic re-override (#7) ────────────────────────
            # Re-point the override at Agent 1 at runtime. The ch2→Agent 1 rule
            # is still set, but the override (not the rule) is the routing
            # reason — assert scope=override, agent=Agent 1.
            e5 = await post_and_wait_new_routing(
                base,
                cid,
                ch2,
                bots,
                0,
                f"/talk-to {_AGENT_1}",
                until_entry=lambda x: x.get("disposition") == "command-intercepted",
                timeout=120.0,
            )
            assert e5["disposition"] == "command-intercepted", (
                f"/talk-to {_AGENT_1!r} should be intercepted; got "
                f"disposition={e5.get('disposition')!r}"
            )
            e6 = await post_and_wait_new_routing(
                base,
                cid,
                ch2,
                bots,
                0,
                bots.mention(f"ma-reoverride {nonce}"),
                timeout=120.0,
            )
            assert e6["agent"] == _AGENT_1, (
                f"dynamic re-override → expected agent={_AGENT_1!r}; got {e6.get('agent')!r}"
            )
            assert e6["scope"] == "override", (
                f"dynamic re-override → expected scope='override'; "
                f"got {e6.get('scope')!r} (agent={e6.get('agent')!r})"
            )
            report.record(
                "#7 dynamic re-override — /talk-to re-settable at runtime",
                "PASS",
                f"/talk-to {_AGENT_1!r} + @mention → {_AGENT_1!r} scope=override "
                "(override re-pointed mid-session)",
            )
    finally:
        # Cleanup: post /new to rotate the session (writes ended_at) so the
        # override clears for re-runnability, then restore the connector's
        # routing to the captured prior value (None is a legitimate prior).
        # Best-effort /new — guard it so a post failure can't mask the routing
        # restore.
        try:
            async with BotDriver(cfg) as cleanup_bots:
                await cleanup_bots.post(0, ch2, "/new")
        except Exception:
            # A stuck override self-clears on the operator's next /new; the
            # routing restore below is the load-bearing cleanup.
            pass
        await restore_connector_routing(base, cid, prior_routing)

    # Surface the evidence table in pytest output for the FD's run record.
    print("\n" + report.render())


async def _get_connector_routing(base_url: str, connector_id: str) -> dict | None:
    """GET the connector and return its ``config.get("routing")`` (or None).

    Phase A runs without a routing change, so the prior routing is captured
    here up front rather than via ``set_connector_routing``'s return value.
    Mirrors the read in ``set_connector_routing`` (no ``secrets`` round-trip).
    """
    import httpx

    path = f"/api/connectors/{connector_id}"
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0, headers=auth_headers()) as http:
        resp = await http.get(path)
        resp.raise_for_status()
        body = resp.json()
    return body.get("config", {}).get("routing")
