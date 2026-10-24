"""Probe module run inside a Briefcase app (Mission 32 Flight 1 spike).

Run as the app's main module via ``BRIEFCASE_MAIN_MODULE=m32probe`` (the module is copied
next to ``the_one/`` in the app's source dir first). Prints what the embedded interpreter
looks like from the inside: ``sys.executable``, ``sys.frozen``, ``sys.prefix`` and what the
app's own ``is_frozen()`` / ``resolve_python()`` make of it.
"""

import os
import sys

from the_one.platform.env import _bundle_dir, is_frozen
from the_one.platform.interpreter import resolve_python

print("PROBE sys.executable=%r exists=%s" % (sys.executable, os.path.exists(sys.executable)))
print(
    "PROBE sys.frozen=%r  hasattr(_MEIPASS)=%s"
    % (getattr(sys, "frozen", "<absent>"), hasattr(sys, "_MEIPASS"))
)
print("PROBE sys.prefix=%r base_prefix=%r argv=%r" % (sys.prefix, sys.base_prefix, sys.argv))
print("PROBE version=%s" % sys.version.split()[0])
print("PROBE realpath(executable)=%s" % os.path.realpath(sys.executable))
print(
    "PROBE is_frozen=%r bundle_dir=%r resolve_python=%r"
    % (is_frozen(), _bundle_dir(), resolve_python())
)
