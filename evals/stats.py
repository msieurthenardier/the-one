"""Statistics for pass rates (DD10): a Wilson interval and a one-sided Fisher test.

Stdlib only. ``worse_than_baseline`` is the single definition of "worse" that the
gate rules (DD11) use: a one-sided Fisher exact test on (new pass, new fail)
against (baseline pass, baseline fail) with p < 0.05.
"""

from __future__ import annotations

import math

Z_95 = 1.959964
ALPHA = 0.05


def wilson(k: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """The Wilson score interval for ``k`` passes in ``n`` runs. ``n == 0`` gives (0, 1)."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def fisher_one_sided_worse(new_k: int, new_n: int, base_k: int, base_n: int) -> float:
    """P(a pass count this low or lower in ``new``) given the pooled margins.

    The hypergeometric tail ``P(X <= new_k)`` where ``X`` is the number of passes
    among ``new_n`` runs drawn from the pooled ``new_n + base_n`` runs holding
    ``new_k + base_k`` passes. Small means the new run is worse than baseline.
    """
    if new_n <= 0 or base_n <= 0:
        return 1.0
    total = new_n + base_n
    passes = new_k + base_k
    fails = total - passes
    denom = math.comb(total, new_n)
    lo = max(0, new_n - fails)
    tail = sum(math.comb(passes, x) * math.comb(fails, new_n - x) for x in range(lo, new_k + 1))
    return min(1.0, tail / denom)


def worse_than_baseline(new_k: int, new_n: int, base_k: int, base_n: int) -> bool:
    """True when the new pass count is significantly lower than baseline (p < 0.05)."""
    return fisher_one_sided_worse(new_k, new_n, base_k, base_n) < ALPHA
