"""Server-side visuals support (M35).

``chart_spec.py`` (and, from M35 F3 L3, ``blocks.py`` and ``outbound.py``) are standard library
only: no web, agent or Pillow imports. ``chart_image.py`` draws a chart as a PNG and imports
Pillow lazily, inside functions, so importing it never imports ``PIL``; it is the only module in
this package that may. The bundled Geist fonts it measures and draws with are in ``fonts/``.
"""
