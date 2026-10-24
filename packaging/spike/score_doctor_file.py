"""Score one `doctor` output file with score.score_doctor (Mission 32 spike). Stdlib only.

    python score_doctor_file.py FILE

Prints one JSON line. The file is decoded as UTF-8, falling back to cp1252: a stub whose
embedded Python writes the console code page would otherwise lose the gate lines' em dash.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score  # noqa: E402

raw = Path(sys.argv[1]).read_bytes()
try:
    text = raw.decode("utf-8")
    enc = "utf-8"
except UnicodeDecodeError:
    text = raw.decode("cp1252", errors="replace")
    enc = "cp1252"
text = text.replace("\r\n", "\n")
res = score.score_doctor(text)
res["encoding"] = enc
print(json.dumps(res))
