"""Run the app CLI with stdout and stderr redirected to a file (Mission 32 spike, leg windows-cost).

Run as the app's main module via ``BRIEFCASE_MAIN_MODULE=m32run`` (copied next to ``the_one/`` in a
COPY of the installed app). A Briefcase GUI-subsystem stub may give the embedded Python no usable
stdout, so ``doctor`` (or ``serve``) run through the stub print nothing. This wrapper opens
``$M32_OUT``, points ``sys.stdout`` and ``sys.stderr`` at it, runs ``the_one.main.cli_entry`` with
``$M32_ARGS`` split on spaces, and ends the file with ``rc=N``. It is how the probe still gets
``doctor``'s verdict when the stub is silent; that the stub IS silent is itself the finding.
"""

import os
import sys
import traceback

out = open(os.environ["M32_OUT"], "w", encoding="utf-8", buffering=1)
sys.stdout = out
sys.stderr = out
rc = 0
try:
    from the_one.main import cli_entry

    sys.argv = [sys.argv[0]] + os.environ.get("M32_ARGS", "").split()
    cli_entry()
except SystemExit as exc:
    rc = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
except BaseException:  # noqa: BLE001
    traceback.print_exc()
    rc = 99
out.write("\nrc=%s\n" % rc)
out.close()
os._exit(rc)
