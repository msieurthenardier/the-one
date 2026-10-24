from __future__ import annotations

import sys

import uvicorn

from the_one.config import settings


def _quit_command(wait: bool = False) -> int:
    """``the-one quit [--wait|--no-wait]``: ask the running desktop instance to quit.

    ``wait`` also waits (up to 75 s) for the instance's process to exit. The CLI
    defaults it on when stdout is a terminal and off otherwise (a launcher action).

    Reads the credential with the read-only lookup, never ``get_credential()``
    (which would create a file), and checks the path first so a missing file is
    "not running" rather than a logged warning.
    """
    import httpx

    from the_one.api_credential import CredentialFileError, credential_path, lookup_credential

    port = settings.port
    if not credential_path().exists():
        print("GleepGlorp AI is not running.")
        return 0
    try:
        credential = lookup_credential()
    except CredentialFileError as exc:
        print(f"Cannot read the local API credential: {exc}")
        return 1
    if credential is None:
        print("GleepGlorp AI is not running.")
        return 0
    try:
        r = httpx.post(
            f"http://{settings.host}:{port}/api/window/quit",
            headers={"Authorization": f"Bearer {credential.encode()}"},
            timeout=5.0,
        )
    except httpx.HTTPError:
        print("GleepGlorp AI is not running.")
        return 0
    if r.status_code in (401, 403):
        print(
            f"Another program, or a GleepGlorp AI with a different credential, "
            f"is using port {port}."
        )
        return 1
    if r.status_code in (404, 405):
        print("The running GleepGlorp AI is too old to be quit this way; close it from its window.")
        return 1
    if r.status_code != 200:
        print(f"Unexpected answer from the running instance (HTTP {r.status_code}).")
        return 1
    try:
        body = r.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or "quit" not in body:
        print("Unexpected answer from the running instance.")
        return 1
    if body["quit"] is True:
        print("GleepGlorp AI is quitting.")
        pid = body.get("pid")
        if wait and type(pid) is int and pid > 0:
            from the_one.interfaces.desktop.shell import _wait_for_exit

            if not _wait_for_exit(pid):
                print("GleepGlorp AI did not exit within 75 seconds.")
                return 1
            print("GleepGlorp AI has quit.")
    else:
        print("GleepGlorp AI is running as a server only (`the-one serve`); stop it with Ctrl+C.")
    return 0


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
    elif args[0] == "quit":
        if "--wait" in args[1:]:
            wait = True
        elif "--no-wait" in args[1:]:
            wait = False
        else:
            wait = sys.stdout.isatty()
        sys.exit(_quit_command(wait))
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
        print("Usage: the-one [chat|serve|app|quit|version|doctor|rotate-api-credential]")
        print("  chat   - Interactive CLI (default)")
        print(f"  serve  - Start web UI on {settings.host}:{settings.port}")
        print("  app    - Open the desktop window (native web view)")
        print("  quit   - Quit the running desktop app (window, tray or hidden);")
        print("           --wait waits for it to exit (default on a terminal)")
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
