"""Packaged-smoke probes for the Windows recipe (Mission 32 Flight 4, leg 3b).

Build-time tooling, run only by .github/workflows/windows-packages.yml with the build venv's
Python and ``PYTHONPATH=<stage dir>`` (the project is never installed, so ``the_one`` is importable
only from the staged copy). Never imported by ``the_one/``.

    smoke.py info EXPECTED_VERSION     frozen ``serve`` answers GET /api/info 200 with that version
    smoke.py single-instance           _select_port sees the running frozen instance as ours

The first asserts the STAGED version (the workflow's input, or ``__version__``), not whatever the
imported ``the_one`` says: the staged copy is the thing that was frozen, and a freeze that picked up
some other copy would report a different number. The credential check is live (Mission 20 Flight 1):
``get_credential()`` reads the runner user's data-dir credential, which the frozen serve shares.
"""

from __future__ import annotations

import sys
import time


def _port() -> int:
    """The port the frozen serve listens on: the app's own setting (8484 unless THE_ONE_PORT)."""
    from the_one.config import settings

    return int(settings.port)


def bearer_header(credential) -> dict[str, str]:
    """``Authorization`` header for a LocalApiCredential.

    Must use ``.encode()``: ``str(credential)`` is the redacted repr
    (``LocalApiCredential(identifier=..., secret=<redacted>)``), which the gate rejects with 401.
    """
    return {"Authorization": f"Bearer {credential.encode()}"}


def describe_credential(data_dir, cred_path, credential_text: str | None) -> str:
    """One diagnostic line: data dir, credential file presence and its ``loc_<id>`` prefix only."""
    exists = cred_path.exists()
    prefix = "n/a"
    if credential_text:
        ident = credential_text.split(".", 1)[0]
        prefix = ident if ident.startswith("loc_") else "unparseable"
    return f"data dir {data_dir}; credential file {cred_path} exists={exists}; id {prefix}"


def info(expected: str) -> int:
    import httpx

    from the_one.api_credential import credential_path, get_credential
    from the_one.config import settings

    port = _port()
    credential = get_credential()
    headers = bearer_header(credential)
    last = "no answer"
    for _ in range(60):
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/api/info", headers=headers, timeout=2.0)
            if r.status_code == 200:
                got = r.json().get("version")
                if got != expected:
                    print(f"FAIL: /api/info version {got!r}, expected {expected!r}")
                    return 1
                print(f"ok: frozen serve answers /api/info 200, version {got}")
                return 0
            last = f"HTTP {r.status_code} body {r.text[:200]!r}"
        except Exception as exc:  # noqa: BLE001 - the server may not be up yet
            last = repr(exc)
        time.sleep(1)
    print(f"FAIL: frozen serve did not answer /api/info 200 within 60 s ({last})")
    print(
        f"port {port}; "
        + describe_credential(settings.data_dir, credential_path(), credential.encode())
    )
    return 1


def single_instance() -> int:
    from the_one.api_credential import credential_path, lookup_credential
    from the_one.config import settings
    from the_one.interfaces.app import _select_port

    port, ours = _select_port("127.0.0.1", _port())
    if not ours:
        cred = lookup_credential() if credential_path().exists() else None
        print(f"FAIL: _select_port returned ({port}, {ours}): not seen as ours")
        print(
            f"port {_port()}; "
            + describe_credential(
                settings.data_dir, credential_path(), cred.encode() if cred else None
            )
        )
        return 1
    print(f"ok: _select_port -> ({port}, {ours})")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "info":
        return info(argv[2])
    if len(argv) == 2 and argv[1] == "single-instance":
        return single_instance()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
