"""What a kind's functions need from the app (Mission 36 F4 L1a, DD3).

``KindDeps`` wraps the agent write services' dependencies. Later kinds add their own
repository fields here. :meth:`KindDeps.of` accepts either type so callers that already
build an ``AgentWriteDeps`` (the eval harness, the web app) do not change.
"""

from __future__ import annotations

from dataclasses import dataclass

from the_one.agent.service import AgentWriteDeps


@dataclass(frozen=True)
class KindDeps:
    agent: AgentWriteDeps

    @classmethod
    def of(cls, deps: AgentWriteDeps | KindDeps) -> KindDeps:
        return deps if isinstance(deps, cls) else cls(agent=deps)
