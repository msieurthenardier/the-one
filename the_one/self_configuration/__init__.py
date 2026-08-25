"""The loopback self-configuration MCP surface.

Mission 21 / Flight 1 / Leg 2 (`self-configuration-surface-read`).

An agent's self-configuration surface is a real ``streamable-http`` MCP
source row, one per enabled agent, pointing at a loopback endpoint the
platform serves itself (DD1 in the flight spec). This package owns:

- ``constants`` — leaf module: the mount path and the gate's confined-source
  map. Import this, not the rest of the package, from anything that must
  stay import-light (``the_one/interfaces/web/middleware.py``).
- ``credentials`` — the per-agent ``agt``-prefixed credential shape and the
  in-memory registry + :class:`~the_one.api_credential.CredentialSource`
  that resolves it.
- ``surface`` — the FastMCP server instance, its four tools (two read, two
  write — added across Legs 2-3), and the caller → agent resolution (DD9's
  refusal).
- ``projection`` — the two read projections as pure functions over
  repositories (LD5's explicit field lists).
- ``manage`` — enable / disable / status / startup-reconcile / rename-cascade
  / delete-cascade.

Nothing in this package is imported by ``the_one/interfaces/web/middleware.py``
except ``constants`` (LD2) — the gate must not gain a heavy import for a
security-sensitive path check.
"""

from __future__ import annotations
