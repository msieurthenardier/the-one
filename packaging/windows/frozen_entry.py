"""Frozen entry point analysed by PyInstaller (M15 F5 L2, DD7).

This is the script PyInstaller's ``Analysis`` ingests for the Windows one-dir
build (see ``the-one.spec``). It is a *build artifact* — the running app never
imports it; it exists solely so the frozen ``the-one.exe`` boots with
``multiprocessing.freeze_support()`` called **first**, then delegates to the
same ``cli_entry`` dispatcher the console script uses.

``freeze_support()`` is the fork-bomb insurance from DD7: on Windows a frozen
binary re-executes itself for every ``multiprocessing`` child, and without this
guard each re-exec would re-run ``cli_entry`` instead of the child bootstrap,
spawning processes recursively. It is a no-op off Windows / when not frozen, so
it is safe to keep unconditional.
"""

from __future__ import annotations

import multiprocessing

from the_one.main import cli_entry

if __name__ == "__main__":
    multiprocessing.freeze_support()  # DD7: must run before cli_entry()
    cli_entry()
