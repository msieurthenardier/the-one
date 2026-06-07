from __future__ import annotations

import asyncio

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from the_one import __version__
from the_one.agent.factory import AgentFactory
from the_one.config import settings
from the_one.db import close_connection, init_db
from the_one.db.connection import get_connection
from the_one.db.migration import migrate_json_to_sqlite
from the_one.db.repositories import SQLiteAgentStore
from the_one.llm.base import Role

console = Console()


async def _run_cli() -> None:
    await init_db()
    # M14 F4 L7: prune orphaned box scratch dirs at startup — mirrors web lifespan.
    # Single-process assumption: no live boxed sessions exist yet at this point.
    from the_one.tools.execution import prune_box_scratch

    prune_box_scratch()
    conn = await get_connection()
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
    except ValueError as exc:
        console.print(
            f"[red]No provider configured:[/red] {exc}\n"
            f"Set one up in Admin at http://{settings.host}:{settings.port}"
        )
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
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
    finally:
        await close_connection()


def run() -> None:
    asyncio.run(_run_cli())
