"""M11 F16 L2 — pairing-approval peers-axis decoupling reproduce-gate.

Reproduces the exact F15 L7 HAT lock-out and proves the F16 L1 fix: after the
account-scope ``allowlist.peers`` axis is narrowed to a SINGLE approved peer
(the post-pairing-approval shape — ``approve_peer_approval`` appends the
approved peer to ``account.config.allowlist.peers``), a guild-channel ``@mention``
from a DIFFERENT, un-approved peer must STILL be admitted (routing
``disposition == "stepped"``) — NOT denied (``no-eligible``).

Pre-F16-L1 substrate: ``_admits_inbound_guild`` consulted the account-scope
``peers`` axis, so a non-empty ``peers`` list narrowed ALL inbound including
guild channels → the different bot's mention routed ``no-eligible`` (the
"connector locked to one peer" lock-out). This test is RED against that
substrate.

Post-F16-L1 substrate: the account-scope ``peers`` axis is DM-only (removed from
``_admits_inbound_guild``; consulted only in ``_admits_inbound_dm``), so the
guild path consults only ``channels`` / ``guilds`` / ``roles`` — the different
bot's channel mention is admitted → ``stepped``. This test is GREEN after.

The ``@mention`` is REQUIRED: a non-mention message could be silently dropped by
the mentions-aware policy gate (``policy-silent``), masking the ACL behavior
under test. The mention forces the ACL path (Architect Q2).

The mutation touches the operator's LIVE connector, so the prior allowlist is
captured before and RESTORED in a ``finally`` (to the captured prior value, not
a hardcoded null) — a mid-test failure must not leave the connector locked, and
a second run must pass without manual cleanup.

Skips cleanly when the HAT env is not provisioned (the default state). This is a
committed, credentials-gated regression artifact — the operator runs it with HAT
creds; it COLLECTS-AND-SKIPS without env. The binding unit gate is L1's
``tests/test_connectors_acl.py``.
"""

from __future__ import annotations

import uuid

import pytest

from .config import skip_if_unconfigured
from .driver import (
    BotDriver,
    post_and_wait_new_routing,
    restore_connector_allowlist,
    set_connector_allowlist,
)
from .report import HatReport

# Sentinel distinguishing "allowlist not yet captured" from a legitimately-None
# prior, so the restore-finally skips a mutation that never happened.
_UNSET = object()


@pytest.mark.discord_hat
async def test_pairing_peers_decoupling_live() -> None:
    cfg = skip_if_unconfigured()
    if not cfg.bot_user_ids:
        pytest.skip(
            "THE_ONE_HAT_BOT_USER_IDS not set — required for the allowlist peers axis "
            "(add comma-separated burner-bot user ids to .env.hat)"
        )
    report = HatReport()
    nonce = uuid.uuid4().hex[:8]
    channel_id = cfg.channel_ids[0]
    connector_id = cfg.connector_id
    base = cfg.base_url

    # Captured pre-test allowlist — restored in the finally (None is a
    # legitimate prior; the _UNSET sentinel marks an un-mutated connector).
    prior_allowlist: object = _UNSET

    async with BotDriver(cfg) as bots:
        try:
            # ── Narrow the account-scope peers axis to ONE approved peer ───
            # Simulate post-pairing-approval: peers = [{id: bot0, dm_allowed}]
            # (the structured v24 shape the validator enforces). Build the
            # narrowed allowlist by capturing the prior first, then overriding
            # only the peers axis so the other required key (channels) and any
            # guilds/roles/dm_admission narrowing carry through unchanged.
            prior_allowlist = await set_connector_allowlist(
                base,
                connector_id,
                _post_approval_allowlist(cfg.bot_user_ids[0]),
            )

            # ── A DIFFERENT bot's channel @mention must still be admitted ──
            # bot1 is NOT in the narrowed peers axis. Pre-fix, the guild path
            # consulted account-scope peers → this routes no-eligible (the
            # lock-out). Post-fix, the guild path ignores account-scope peers →
            # admitted → stepped.
            entry = await post_and_wait_new_routing(
                base,
                connector_id,
                channel_id,
                bots,
                1,  # bot1 — the different, un-approved peer
                bots.mention(f"peers-decouple {nonce} from b1"),
                timeout=90.0,
            )
            assert entry["disposition"] == "stepped", (
                f"a DIFFERENT bot's channel @mention must still be admitted "
                f"when the account-scope peers axis is narrowed to one OTHER "
                f"peer (F16 L1: account-scope peers is DM-only, does not gate "
                f"guild channels) — expected stepped; got "
                f"{entry.get('disposition')!r}. A 'no-eligible' here is the "
                f"F15 L7 lock-out (RED against the pre-F16-L1 substrate)."
            )
            report.record(
                "F16 — account-scope peers narrowing does NOT lock guild channels",
                "PASS",
                f"peers=[{{id: bot0}}]; bot1 channel @mention → "
                f"disposition={entry['disposition']!r} (admitted, not "
                f"no-eligible)",
            )

        finally:
            # Restore the connector's allowlist to its captured prior value
            # (None is a legitimate prior). Skip the restore only if we never
            # mutated the connector (sentinel still set).
            if prior_allowlist is not _UNSET:
                await restore_connector_allowlist(
                    base, connector_id, prior_allowlist  # type: ignore[arg-type]
                )

    # Surface the evidence table in pytest output for the FD's run record.
    print("\n" + report.render())


def _post_approval_allowlist(approved_peer_id: str) -> dict:
    """Build the post-pairing-approval allowlist: account-scope peers narrowed
    to a SINGLE approved peer, with the other axes left open.

    The account-scope ``peers`` entry uses the v24 structured shape
    (``{id, dm_allowed}`` — both keys required, no extras) the Pydantic
    validator at ``the_one/db/models.py:~354-390`` enforces. ``channels`` is the
    second REQUIRED allowlist key (left empty = unrestricted on the channels
    axis); ``guilds`` / ``roles`` / ``dm_admission`` are optional and omitted.
    """
    return {
        "peers": [{"id": approved_peer_id, "dm_allowed": False}],
        "channels": [],
    }
