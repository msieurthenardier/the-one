"""M11 F15 — live-traffic Discord HAT (Hardware/Apparatus Test) driver.

A committed, re-runnable multi-bot ``discord.py`` driver that posts real
traffic into a test guild and asserts the-one's observable session/routing
behavior over its HTTP API. Gated behind the ``discord_hat`` pytest marker
and ``make test-discord-hat``; every test SKIPs cleanly when the bot-token
env is absent (see :mod:`config`), so the normal backend suite never
collects or runs it.
"""
