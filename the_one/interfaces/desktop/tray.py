"""System-tray icon builder and notify wrapper.

All GUI-stack imports (pystray, PIL) are **lazy** — deferred inside function
bodies — so importing this module does not require pystray or Pillow to be
installed.  Tests inject mock modules via ``sys.modules`` before calling these
functions, exactly as ``test_desktop_shell.py`` does for webview.

Public surface
--------------
build_tray(*, on_show, on_quit) -> pystray.Icon
    Build and return a configured pystray Icon (not yet started).

notify(icon, message, title)
    Thin wrapper over ``icon.notify(message, title)``; exists so callers can
    patch a single name in tests rather than reaching into pystray internals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable


def _load_icon_image():
    """Load the brand icon as a PIL Image (lazy import of Pillow)."""
    from PIL import Image  # lazy: optional [gui] extra

    import the_one.interfaces.web as _web_pkg

    icon_path = Path(_web_pkg.__file__).parent / "static" / "brand" / "gleepglorp_icon.png"
    return Image.open(icon_path)


def build_tray(*, on_show: Callable, on_quit: Callable):
    """Build and return a pystray Icon with a Show / Quit menu.

    The icon is **not started** by this function; the caller is responsible for
    calling ``icon.run_detached()`` (DD2: pystray on a detached thread while
    pywebview owns the main thread).

    :param on_show: Callback for the "Show" menu item.
    :param on_quit: Callback for the "Quit" menu item.
    :returns: A configured ``pystray.Icon`` instance.
    """
    import pystray  # lazy: optional [gui] extra

    image = _load_icon_image()

    menu = pystray.Menu(
        pystray.MenuItem("Show", on_show, default=True),
        pystray.MenuItem("Quit", on_quit),
    )

    return pystray.Icon("the-one", image, "GleepGlorp AI", menu=menu)


def notify(icon, message: str, title: str) -> None:
    """Show a tray balloon notification.

    Wraps ``icon.notify(message, title)`` so call-site tests can assert the
    correct argument order: ``notify(icon, message, title)`` → the balloon body
    is ``message`` and the balloon title is ``title``.

    :param icon: A pystray Icon instance.
    :param message: The body text of the notification.
    :param title: The title of the notification balloon.
    """
    icon.notify(message, title)
