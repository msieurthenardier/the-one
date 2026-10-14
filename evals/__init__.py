"""Prompt evals: a hand-rolled runner that measures how the platform's prompt text
behaves on real models.

A developer tool, run as ``python -m evals``; it is not part of the product. It
imports ``the_one.*`` (the way ``scripts/`` does) and nothing under ``the_one/``
imports it (an AST test pins that). Keep ``the_one`` imports out of this file so
``--help`` and ``--dry-run`` never touch ``settings``.
"""
