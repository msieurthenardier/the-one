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
    elif args[0] == "app":
        from the_one.interfaces.app import run as run_app

        run_app()
    elif args[0] == "version":
        from the_one import __version__

        print(f"GleepGlorp AI v{__version__}")
    elif args[0] == "doctor":
        from the_one.diagnostics import run_doctor

        sys.exit(run_doctor())
    elif args[0] == "rotate-api-credential":
        from the_one.api_credential import credential_path, rotate_credential

        existed = credential_path().exists()
        rotate_credential()
        action = "replaced" if existed else "created"
        # Deliberately does not print the secret — no caller needs it from
        # stdout, and printing it would put the credential into shell
        # history and terminal scrollback for no benefit. The launcher and
        # test harnesses read the credential file directly.
        print(f"Local API credential {action} at {credential_path()} (mode 0600).")
    else:
        print("Usage: the-one [chat|serve|app|version|doctor|rotate-api-credential]")
        print("  chat   - Interactive CLI (default)")
        print(f"  serve  - Start web UI on {settings.host}:{settings.port}")
        print("  app    - Open the desktop window (native web view)")
        print("  version - Show version")
        print("  doctor - Diagnose the frozen-runtime seam (child spawn, interpreter,")
        print("           desktop shell, LLM providers, model catalog, vector store,")
        print("           FTS5, bundled embedding model, external runtimes); exits")
        print("           non-zero on failure")
        print("  rotate-api-credential - Replace the persisted local API credential")
        print("           (does not print the secret)")
        sys.exit(1)


if __name__ == "__main__":
    cli_entry()
