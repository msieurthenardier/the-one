"""Wilson interval and the one-sided Fisher test (DD10), against reference values."""

from __future__ import annotations

import math

import pytest

from evals.stats import fisher_one_sided_worse, wilson, worse_than_baseline


def test_wilson_reference_values():
    lo, hi = wilson(15, 20)
    assert lo == pytest.approx(0.531299, abs=1e-6)
    assert hi == pytest.approx(0.888138, abs=1e-6)
    lo, hi = wilson(10, 20)
    assert (lo, hi) == pytest.approx((0.299, 0.701), abs=1e-3)


def test_wilson_edges():
    lo, hi = wilson(0, 10)
    assert lo == 0.0
    # closed form: z^2 / (n + z^2)
    z2 = 1.959964**2
    assert hi == pytest.approx(z2 / (10 + z2), abs=1e-9)
    lo, hi = wilson(20, 20)
    assert hi == 1.0 and lo == pytest.approx(20 / (20 + 1.959964**2) * 1 + 0, abs=0.05)
    assert wilson(0, 0) == (0.0, 1.0)


def test_fisher_small_exact_values():
    # pooled 4 runs holding 2 passes; new has 2 runs: P(X <= k) from the hypergeometric
    assert fisher_one_sided_worse(0, 2, 2, 2) == pytest.approx(1 / 6, abs=1e-12)
    assert fisher_one_sided_worse(1, 2, 1, 2) == pytest.approx(5 / 6, abs=1e-12)
    assert fisher_one_sided_worse(2, 2, 2, 2) == pytest.approx(1.0, abs=1e-12)


def test_fisher_matches_direct_enumeration():
    for new_k, new_n, base_k, base_n in [(15, 20, 20, 20), (12, 20, 18, 20), (8, 20, 15, 20)]:
        total, passes = new_n + base_n, new_k + base_k
        want = sum(
            math.comb(passes, x) * math.comb(total - passes, new_n - x)
            for x in range(0, new_k + 1)
            if new_n - x <= total - passes
        ) / math.comb(total, new_n)
        assert fisher_one_sided_worse(new_k, new_n, base_k, base_n) == pytest.approx(want, abs=1e-9)


def test_fisher_known_p_values():
    # 15/20 against a perfect baseline: all 5 pooled failures fall in the new run,
    # so p = C(20,5) / C(40,5) = 0.023562 exactly.
    assert fisher_one_sided_worse(15, 20, 20, 20) == pytest.approx(
        math.comb(20, 5) / math.comb(40, 5), abs=1e-12
    )
    assert fisher_one_sided_worse(15, 20, 20, 20) == pytest.approx(0.023562, abs=1e-6)
    # 16/20: P(>= 4 of the 4 pooled failures in new) = C(20,4) / C(40,4) = 0.052999
    assert fisher_one_sided_worse(16, 20, 20, 20) == pytest.approx(
        math.comb(20, 4) / math.comb(40, 4), abs=1e-12
    )


def test_fisher_zero_runs_is_never_worse():
    assert fisher_one_sided_worse(0, 0, 5, 5) == 1.0
    assert fisher_one_sided_worse(5, 5, 0, 0) == 1.0


@pytest.mark.parametrize(
    "base,flagged,not_flagged",
    [
        (20, 15, 16),  # DD10 table at n = 20
        (18, 12, 13),
        (15, 8, 9),
    ],
)
def test_dd10_table_at_n20(base, flagged, not_flagged):
    assert worse_than_baseline(flagged, 20, base, 20)
    assert not worse_than_baseline(not_flagged, 20, base, 20)
    # and everything lower than the highest flagged value is flagged too
    assert all(worse_than_baseline(k, 20, base, 20) for k in range(0, flagged + 1))
