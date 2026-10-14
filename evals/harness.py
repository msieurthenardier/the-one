"""The per-run agent setup, clock and zone, tool-free wrapper and conversation driving.

Runs are in-process and sequential, against one scratch data directory per
invocation and one agent per run (DD3). Each run drives the real
``AgentFactory`` / prompt assembly / agent loop the way
``the_one/interfaces/cli.py::_run_cli`` does, with a fresh ``TurnContext`` around
every ``agent.step``. A conversation boundary calls ``AgentFactory.create`` again
for the same agent name, so a fresh ``Agent`` is built with a freshly built system
prompt that reads that run's notes from the same database.

Two module globals are patched, which is why runs are sequential:

- ``the_one.agent.factory.get_provider`` (DD6, DD18), scoped to ``create()`` only:
  it returns the real provider (``tools_off`` overrides the instance's async
  ``supports_tools`` to return False) or a scripted one, and records calls.
- ``the_one.time_zones.utcnow`` / ``detect_system_zone`` (DD8), active across
  every ``create()`` AND every ``agent.step`` of a run, because the
  ``current_time`` tool reads ``time_zones.utcnow`` at call time; restored in a
  ``finally`` at run end.

Containment (DD19): ``HOME`` is the scratch home (set by ``env.startup``); the
filesystem tools' ``path_allowlist`` is narrowed to it; ``web_search`` and
``download_file`` are disabled; ``fetch_url`` / ``http_request`` reach only the
fixture host. The execution tools (``shell``, ``python_exec``, the four
``shell_session_*``) are DISABLED for eval agents: ``host_access`` is a plain tool
argument in ``shell.py`` / ``python_exec.py`` / ``sessions.py`` and no
``ExecutionConfig`` field can refuse it, so a model could escape the box.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from evals.checks import CheckDecl, NoteView, RunTrace, TurnTrace
from evals.fixtures import FIXTURE_HOST, FixtureServer, KBFixtures
from evals.models import Preset, effective_values, provider_row
from evals.scenario import Scenario, Variant, expand

FS_TOOLS = (
    "read_file",
    "write_file",
    "edit_file",
    "delete_file",
    "move_file",
    "mkdir",
    "glob",
    "grep",
    "list_dir",
)
EXEC_TOOLS = (
    "shell",
    "python_exec",
    "shell_session_start",
    "shell_session_send",
    "shell_session_close",
    "shell_session_list",
)
DISABLED_TOOLS = (*EXEC_TOOLS, "web_search", "download_file")
WEB_TOOLS = ("http_request", "fetch_url")
EXECUTION_TOOLS_STATE = "disabled"

DEFAULT_TURN_TIMEOUT_S = 900.0
_TOOL_TIMEOUT = re.compile(r"^tool \S+ timed out after \d+s")


@dataclass(frozen=True)
class RunSpec:
    scenario: Scenario
    variant: Variant
    model: str
    attempt: int = 1

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.scenario.id, self.model, self.variant.id)

    @property
    def agent_name(self) -> str:
        """``ev-{scenario}-{model}-{variant}-{attempt}`` (deterministic, <= 64 chars)."""
        full = f"ev-{self.scenario.id}-{self.model}-{self.variant.id}-{self.attempt}"
        full = re.sub(r"[^A-Za-z0-9_-]", "-", full)
        if len(full) <= 64:
            return full
        digest = hashlib.sha256(full.encode()).hexdigest()[:8]
        return f"{full[:55]}-{digest}"

    @property
    def stem(self) -> str:
        s, m, v = self.key
        return f"{s}__{m}__{v}__a{self.attempt}"


@dataclass
class CallRecorder:
    """Record-only view of the calls a provider receives (no behaviour change)."""

    calls: list[dict[str, Any]] = field(default_factory=list)
    starting_schemas: list[dict[str, Any]] | None = None
    systems: list[str] = field(default_factory=list)
    llm: Any = None
    conversation: int = 0
    _seen_conversations: set[int] = field(default_factory=set)

    def attach(self, llm: Any) -> None:
        self.llm = llm
        if getattr(llm, "_evals_recorded", False):
            return
        orig = llm.stream
        rec = self

        async def stream(*args: Any, **kwargs: Any):
            messages = kwargs.get("messages", args[0] if args else None) or []
            tools = kwargs.get("tools", args[1] if len(args) > 1 else None)
            rec._note(messages, tools)
            async for chunk in orig(*args, **kwargs):
                yield chunk

        llm.stream = stream
        llm._evals_recorded = True

    def _note(self, messages: list[Any], tools: list[dict[str, Any]] | None) -> None:
        system = None
        if messages and getattr(messages[0].role, "value", None) == "system":
            system = messages[0].content
        if self.conversation not in self._seen_conversations:
            self._seen_conversations.add(self.conversation)
            self.systems.append(system if isinstance(system, str) else "")
        if self.starting_schemas is None:
            self.starting_schemas = [dict(t) for t in (tools or [])]
        self.calls.append(
            {
                "conversation": self.conversation,
                "n_messages": len(messages),
                "tools": [t.get("name") for t in (tools or [])],
            }
        )


@dataclass
class Attempt:
    """Everything one attempt at a run produced, including what a failure left behind."""

    trace: RunTrace
    recorder: CallRecorder
    exc: BaseException | None = None
    model_failure: str | None = None
    wall_s: float = 0.0
    turn_s: list[float] = field(default_factory=list)
    effective: dict[str, Any] = field(default_factory=dict)
    fixture_requests: list[tuple[str, str]] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)


async def _supports_no_tools() -> bool:
    return False


@contextlib.contextmanager
def provider_patch(*, tools_off: bool, scripted: Any, recorder: CallRecorder):
    """Scoped to ``AgentFactory.create`` only (DD6, DD18)."""
    from the_one.agent import factory as factory_mod

    original = factory_mod.get_provider

    def patched(name: str, **kwargs: Any) -> Any:
        llm = scripted if scripted is not None else original(name, **kwargs)
        if tools_off:
            llm.supports_tools = _supports_no_tools
        recorder.attach(llm)
        return llm

    factory_mod.get_provider = patched
    try:
        yield
    finally:
        factory_mod.get_provider = original


@contextlib.contextmanager
def clock_patch(instant: datetime, host_zone: str):
    """Hold the clock at ``instant`` for a whole run (create() and every step)."""
    from the_one import time_zones

    orig_utcnow, orig_detect = time_zones.utcnow, time_zones.detect_system_zone
    time_zones.utcnow = lambda: instant
    time_zones.detect_system_zone = lambda: host_zone
    try:
        yield
    finally:
        time_zones.utcnow = orig_utcnow
        time_zones.detect_system_zone = orig_detect


def expected_date_lines(sc: Scenario, variant: Variant | None = None) -> list[str]:
    from the_one import time_zones

    eff = time_zones.EffectiveZone(sc.zone, ZoneInfo(sc.zone))
    wordings = [False] if sc.tools_off else [True, False]
    return [time_zones.date_line(sc.instant_for(variant), eff, tool_available=w) for w in wordings]


class Harness:
    def __init__(
        self,
        env: Any,
        presets: dict[str, Preset],
        *,
        fixture_server: FixtureServer | None = None,
        kb: KBFixtures | None = None,
        model_info: dict[str, dict[str, Any]] | None = None,
        provider_hook: Callable[[RunSpec, str], Any] | None = None,
        turn_timeout: float = DEFAULT_TURN_TIMEOUT_S,
    ) -> None:
        self.env = env
        self.presets = presets
        self.fixture_server = fixture_server
        self.kb = kb
        self.model_info = model_info or {}
        self.provider_hook = provider_hook
        self.turn_timeout = turn_timeout

    @property
    def fixture_base(self) -> str:
        return self.fixture_server.base_url if self.fixture_server else ""

    async def setup(self) -> None:
        """Write the provider rows and the containment ToolConfig rows (once per invocation)."""
        from the_one.config import settings
        from the_one.db.connection import get_connection
        from the_one.db.repositories import LLMProviderRepository, ToolConfigRepository
        from the_one.encryption import get_encryptor

        conn = await get_connection()
        enc = get_encryptor(settings.data_dir)
        providers = LLMProviderRepository(conn, enc)
        for preset in self.presets.values():
            await providers.create(provider_row(preset, self.env.token))
        tools = ToolConfigRepository(conn, enc)
        home = str(self.env.home)
        for name in FS_TOOLS:
            await tools.upsert(name, {"path_allowlist": [home]})
        for name in WEB_TOOLS:
            await tools.upsert(
                name,
                {"extra_allowed_hosts": [FIXTURE_HOST], "host_allowlist": [FIXTURE_HOST]},
            )
        for name in DISABLED_TOOLS:
            await tools.upsert(name, {}, enabled=False)

    async def discard_agent(self, name: str) -> None:
        """Remove a partial attempt's agent (and, by cascade, its notes and rules)."""
        from the_one.db.connection import get_connection
        from the_one.db.repositories import SQLiteAgentStore

        store = SQLiteAgentStore(await get_connection())
        if await store.exists(name):
            await store.delete(name)

    async def _seed(self, spec: RunSpec) -> set[str]:
        """Create the agent, its rules and seeded notes. Returns the seeded note ids."""
        from the_one import time_zones
        from the_one.agent.config import AgentConfig
        from the_one.db.connection import get_connection
        from the_one.db.repositories import (
            AgentNoteRepository,
            AgentRuleRepository,
            SQLiteAgentStore,
        )

        sc = spec.scenario
        preset = self.presets[spec.model]
        conn = await get_connection()
        if sc.kbs and self.kb is None:
            raise RuntimeError("scenario attaches a knowledge base but no KB fixtures are set up")
        kb_ids = [await self.kb.ensure(ref) for ref in sc.kbs] if sc.kbs else []
        await time_zones.save_setting(conn, time_zones.TimeZoneSetting(mode="zone", zone=sc.zone))
        cfg = AgentConfig(
            name=spec.agent_name,
            description=f"eval run {spec.stem}",
            provider_config_id=preset.provider_id,
            llm_model=preset.model,
            system_prompt=sc.persona,
            kb_ids=kb_ids,
            notes_enabled=sc.notes_enabled,
            **({"max_iterations": sc.max_iterations} if sc.max_iterations else {}),
        )
        await SQLiteAgentStore(conn).save(cfg)
        rules = AgentRuleRepository(conn)
        mapping = {**spec.variant.mapping, "fixture_base": self.fixture_base}
        for text in sc.rules:
            await rules.create(spec.agent_name, expand(text, mapping))
        seeded: set[str] = set()
        notes = AgentNoteRepository(conn)
        for seed in sc.seeded_notes:
            note, _created = await notes.create(
                spec.agent_name,
                expand(seed.text, mapping),
                untrusted=seed.untrusted,
                sources=["seeded"] if seed.untrusted else [],
                origin_kind="other",
                origin_session_id=None,
                origin_label="seeded",
                origin_platform=None,
                origin_peer_id=None,
                origin_peer_name=None,
            )
            seeded.add(note.id)
        return seeded

    async def run_once(self, spec: RunSpec) -> Attempt:
        """One attempt at a run. Model and provider exceptions are captured, not raised."""
        from the_one.agent._context import TurnContext, current_turn
        from the_one.agent.factory import AgentFactory
        from the_one.db.connection import get_connection
        from the_one.db.repositories import AgentNoteRepository, SQLiteAgentStore

        sc = spec.scenario
        inst = sc.instantiate(spec.variant, self.fixture_base)
        recorder = CallRecorder()
        trace = RunTrace(date_lines=expected_date_lines(sc, spec.variant))
        attempt = Attempt(trace=trace, recorder=recorder)
        scripted = self.provider_hook(spec, self.fixture_base) if self.provider_hook else None
        fixture_mark = len(self.fixture_server.requests) if self.fixture_server else 0
        seeded: set[str] = set()
        t_run = time.monotonic()
        agent = None
        with clock_patch(sc.instant_for(spec.variant), sc.host_zone):
            try:
                seeded = await self._seed(spec)
                conn = await get_connection()
                factory = AgentFactory(store=SQLiteAgentStore(conn))
                turn_index = 0
                for ci, turns in enumerate(inst.conversations):
                    recorder.conversation = ci
                    with provider_patch(
                        tools_off=sc.tools_off, scripted=scripted, recorder=recorder
                    ):
                        agent = await factory.create(spec.agent_name)
                    trace.system_prompts.append(agent.system_prompt)
                    attempt.effective = effective_values(agent.llm)
                    for text in turns:
                        tt = TurnTrace(conversation=ci, index=turn_index, user=text)
                        trace.turns.append(tt)
                        turn_index += 1
                        t0 = time.monotonic()
                        token = current_turn.set(TurnContext(session_id=f"ev-{spec.stem}-c{ci}"))
                        try:
                            async with asyncio.timeout(self.turn_timeout):
                                async for msg in agent.step(text):
                                    tt.messages.append(msg)
                        except TimeoutError:
                            attempt.model_failure = f"turn timed out after {self.turn_timeout:.0f}s"
                        finally:
                            current_turn.reset(token)
                            attempt.turn_s.append(round(time.monotonic() - t0, 3))
                        if attempt.model_failure:
                            break
                        if not tt.has_final_reply:
                            attempt.model_failure = "max_iterations exhausted with no final reply"
                            break
                        timed_out = _first_tool_timeout(tt)
                        if timed_out:
                            attempt.model_failure = timed_out
                            break
                    attempt.effective = effective_values(agent.llm)
                    await agent.aclose()
                    agent = None
                    if attempt.model_failure:
                        break
            except Exception as exc:  # noqa: BLE001 - classified by the caller
                attempt.exc = exc
            finally:
                if agent is not None:
                    with contextlib.suppress(Exception):
                        attempt.effective = effective_values(agent.llm)
                        await agent.aclose()
                try:
                    conn = await get_connection()
                    stored = await AgentNoteRepository(conn).list_for_agent(spec.agent_name)
                    for n in stored:
                        if n.id in seeded:
                            continue
                        trace.saved_notes.append(NoteView(n.text, n.untrusted, n.untrusted_sources))
                        attempt.notes.append(
                            {
                                "text": n.text,
                                "untrusted": n.untrusted,
                                "sources": n.untrusted_sources,
                            }
                        )
                except Exception as exc:  # noqa: BLE001 - note collection must not mask the run
                    attempt.exc = attempt.exc or exc
        attempt.wall_s = round(time.monotonic() - t_run, 3)
        if self.fixture_server:
            attempt.fixture_requests = list(self.fixture_server.requests[fixture_mark:])
        return attempt


def _first_tool_timeout(tt: TurnTrace) -> str | None:
    for m in tt.messages:
        tr = m.tool_result
        if tr is not None and tr.is_error and _TOOL_TIMEOUT.match(str(tr.content)):
            return "tool call timed out"
    return None


def off_fixture_fetches(trace: RunTrace) -> list[str]:
    """Targets of fetch_url / http_request calls aimed at any host but the fixture server."""
    out = []
    for tc in trace.tool_calls():
        if tc.name in WEB_TOOLS:
            url = str(tc.arguments.get("url", ""))
            if urlparse(url).hostname != FIXTURE_HOST:
                out.append(url)
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "Attempt",
    "CheckDecl",
    "Harness",
    "RunSpec",
    "clock_patch",
    "expected_date_lines",
    "off_fixture_fetches",
    "provider_patch",
]
