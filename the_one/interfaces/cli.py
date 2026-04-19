from __future__ import annotations

import asyncio

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from the_one.agent.factory import AgentFactory
from the_one.config import settings
from the_one.llm.base import Role

console = Console()


async def _run_cli() -> None:
    factory = AgentFactory()
    agent = factory.create()
    session: PromptSession[str] = PromptSession(
        history=FileHistory(str(settings.data_dir / "cli_history"))
    )

    console.print(
        Panel(
            f"[bold]the-one[/bold] v0.1.0\n"
            f"Provider: {settings.llm_provider} / {settings.llm_model}\n"
            f"Tools: {', '.join(agent.tools.tool_names)}\n"
            f"Type [bold]/quit[/bold] to exit, [bold]/reset[/bold] to clear context.",
            title="the-one",
            border_style="blue",
        )
    )

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
                                f"  [dim]-> {tc.name}({', '.join(f'{k}={v!r}' for k, v in tc.arguments.items())})[/dim]"
                            )
                elif msg.role == Role.TOOL and msg.tool_result:
                    output = msg.tool_result.content
                    if len(output) > 500:
                        output = output[:500] + "..."
                    style = "red" if msg.tool_result.is_error else "green"
                    console.print(f"  [{style}]{output}[/{style}]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


def run() -> None:
    asyncio.run(_run_cli())
