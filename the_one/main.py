from __future__ import annotations

import sys

import uvicorn

from the_one.config import settings


def cli_entry() -> None:
    """Main entry point for the `the-one` command."""
    args = sys.argv[1:]

    if not args or args[0] == "chat":
        from the_one.interfaces.cli import run

        run()
    elif args[0] == "serve":
        from the_one.interfaces.web.app import app

        uvicorn.run(app, host=settings.host, port=settings.port)
    elif args[0] == "version":
        from the_one import __version__

        print(f"the-one v{__version__}")
    else:
        print("Usage: the-one [chat|serve|version]")
        print("  chat   - Interactive CLI (default)")
        print(f"  serve  - Start web UI on {settings.host}:{settings.port}")
        print("  version - Show version")
        sys.exit(1)


if __name__ == "__main__":
    cli_entry()
