from __future__ import annotations

import asyncio
import logging
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from the_one import __version__
from the_one.agent._context import TurnContext, current_turn
from the_one.agent.factory import AgentFactory, GleepGlorpUnavailableError
from the_one.config import settings
from the_one.db import close_connection, init_db
from the_one.db.connection import get_connection
from the_one.db.key_reconcile import reconcile_pending_key
from the_one.db.migration import migrate_json_to_sqlite
from the_one.db.repositories import SQLiteAgentStore
from the_one.encryption import get_encryptor
from the_one.llm.base import Role

console = Console()
logger = logging.getLogger(__name__)


def step_limit_text(steps: int) -> str:
    """The step-limit wording (the web's, without the link). Below 1 step the count is left out."""
    used = f"used its {steps} steps" if steps >= 1 else "reached its step limit"
    return (
        f"Stopped: this agent {used} for this message. "
        "Send another message to continue, or raise Max iterations in its settings."
    )


def _print_step_limit_notice(agent: Any) -> None:
    """M31 F6 leg 06 (DD8): a dimmed line when the turn ended at the step limit."""
    if getattr(agent, "stopped_at_step_limit", False):
        console.print(f"[dim]{step_limit_text(agent.max_iterations)}[/dim]")


async def _run_cli() -> None:
    await init_db()
    # M14 F4 L7: prune orphaned box scratch dirs at startup — mirrors web lifespan.
    # Single-process assumption: no live boxed sessions exist yet at this point.
    from the_one.tools.execution import prune_box_scratch

    prune_box_scratch()
    conn = await get_connection()
    # Reconcile a leftover rotation sidecar before any encryptor-backed
    # repository is constructed — mirrors the web lifespan's ordering
    # (flight Design Decision Q1 / `the_one.db.key_reconcile`).
    _reconcile_outcome = await reconcile_pending_key(conn, get_encryptor(settings.data_dir))
    if _reconcile_outcome != "absent":
        logger.info("encryption key sidecar reconciled at startup: %s", _reconcile_outcome)
    store = SQLiteAgentStore(conn)
    await migrate_json_to_sqlite(store)

    console.print(
        Panel(
            f"[bold]GleepGlorp AI[/bold] v{__version__}\n"
            "Type [bold]/quit[/bold] to exit, [bold]/reset[/bold] to clear context.",
            title="GleepGlorp AI",
            border_style="blue",
        )
    )

    factory = AgentFactory(store=store)
    try:
        agent = await factory.create()
    except GleepGlorpUnavailableError as exc:
        console.print(f"[red]{exc}[/red] Choose a model in Settings > GleepGlorp.")
        # The database connection's thread would keep the process alive: close it first.
        await close_connection()
        raise SystemExit(1)
    except ValueError as exc:
        console.print(
            f"[red]No provider configured:[/red] {exc}\n"
            f"Set one up in Admin at http://{settings.host}:{settings.port}"
        )
        await close_connection()
        return

    session: PromptSession[str] = PromptSession(
        history=FileHistory(str(settings.data_dir / "cli_history"))
    )

    try:
        while True:
            try:
                user_input = await session.prompt_async("you > ")
            except (EOFError, KeyboardInterrupt):
                break

            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input == "/quit":
                break
            if user_input == "/reset":
                agent.reset()
                console.print("[dim]Context cleared.[/dim]")
                continue

            # M27 F2 DD5: a fresh notes context per CLI turn (no session, no peer).
            turn_token = current_turn.set(TurnContext())
            try:
                async for msg in agent.step(user_input):
                    if msg.role == Role.ASSISTANT:
                        if msg.content:
                            console.print()
                            console.print(Markdown(msg.content))
                        if msg.tool_calls:
                            for tc in msg.tool_calls:
                                console.print(
                                    f"  [dim]-> {tc.name}("
                                    f"{', '.join(f'{k}={v!r}' for k, v in tc.arguments.items())})"
                                    f"[/dim]"
                                )
                    elif msg.role == Role.TOOL and msg.tool_result:
                        output = msg.tool_result.content
                        if len(output) > 500:
                            output = output[:500] + "..."
                        style = "red" if msg.tool_result.is_error else "green"
                        console.print(f"  [{style}]{output}[/{style}]")
                _print_step_limit_notice(agent)
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
            finally:
                current_turn.reset(turn_token)
    finally:
        await close_connection()


def run() -> None:
    asyncio.run(_run_cli())
