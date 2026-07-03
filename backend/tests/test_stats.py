"""Unit tests for services/stats.py (SPEC section 6)."""

from __future__ import annotations

import numpy as np
import pytest

from app.services.stats import (
    bootstrap_ci,
    ci_overlap,
    interpret_p_value,
    mann_whitney_u,
    mean_std,
)

# ------------------------------------------------------------------ mean_std


def test_mean_std_basic() -> None:
    mean, std = mean_std([1.0, 2.0, 3.0])
    assert mean == pytest.approx(2.0)
    assert std == pytest.approx(1.0)  # sample std, ddof=1


def test_mean_std_single_value_has_zero_std() -> None:
    assert mean_std([4.0]) == (4.0, 0.0)


def test_mean_std_empty_raises() -> None:
    with pytest.raises(ValueError):
        mean_std([])


# -------------------------------------------------------------- bootstrap_ci


def test_bootstrap_ci_deterministic_with_seed() -> None:
    scores = [1.0, 2.0, 2.5, 3.0, 4.5, 5.0]
    assert bootstrap_ci(scores, seed=123) == bootstrap_ci(scores, seed=123)
    assert bootstrap_ci(scores, seed=1) != bootstrap_ci(scores, seed=2)


def test_bootstrap_ci_band_contains_sample_mean_for_symmetric_data() -> None:
    scores = [1.0, 2.0, 3.0, 4.0, 5.0] * 10  # symmetric around 3
    low, high = bootstrap_ci(scores, seed=42)
    assert low <= 3.0 <= high
    assert 1.0 <= low <= high <= 5.0


def test_bootstrap_ci_width_shrinks_as_n_grows() -> None:
    rng = np.random.default_rng(7)
    small = rng.normal(loc=3.0, scale=1.0, size=20).tolist()
    large = rng.normal(loc=3.0, scale=1.0, size=200).tolist()
    low_s, high_s = bootstrap_ci(small, seed=42)
    low_l, high_l = bootstrap_ci(large, seed=42)
    assert (high_l - low_l) < (high_s - low_s)


def test_bootstrap_ci_single_value() -> None:
    assert bootstrap_ci([3.7]) == (3.7, 3.7)


def test_bootstrap_ci_empty_raises() -> None:
    with pytest.raises(ValueError):
        bootstrap_ci([])


# ------------------------------------------------------------ mann_whitney_u


def test_mwu_disjoint_samples_give_u_zero_and_significant_p() -> None:
    result = mann_whitney_u([1.0, 2.0, 3.0, 4.0, 5.0], [6.0, 7.0, 8.0, 9.0, 10.0])
    assert result.u_statistic == 0.0
    assert result.p_value < 0.05


def test_mwu_identical_distributions_give_p_near_one() -> None:
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = mann_whitney_u(a, list(a))
    assert result.p_value > 0.9


def test_mwu_min_side_u_and_p_invariant_under_swap() -> None:
    a = [1.0, 3.0, 5.0, 7.0]
    b = [2.0, 4.0, 6.0, 8.0, 10.0]
    forward = mann_whitney_u(a, b)
    backward = mann_whitney_u(b, a)
    assert forward.u_statistic == pytest.approx(backward.u_statistic)
    assert forward.p_value == pytest.approx(backward.p_value)


def test_mwu_handles_ties() -> None:
    result = mann_whitney_u([1.0, 2.0, 2.0, 3.0], [2.0, 3.0, 3.0, 4.0])
    assert result.u_statistic >= 0.0
    assert 0.0 <= result.p_value <= 1.0


def test_mwu_all_identical_values_give_p_one() -> None:
    result = mann_whitney_u([3.0, 3.0, 3.0, 3.0], [3.0, 3.0, 3.0])
    assert result.p_value == 1.0


def test_mwu_against_scipy_reference() -> None:
    # scipy.stats.mannwhitneyu(a, b, alternative="two-sided") ~ 0.0122 for these samples.
    result = mann_whitney_u(
        [12.0, 15.0, 14.0, 10.0, 18.0], [22.0, 25.0, 19.0, 24.0, 28.0]
    )
    assert result.u_statistic == 0.0
    assert 0.005 < result.p_value < 0.03


def test_mwu_empty_input_raises() -> None:
    with pytest.raises(ValueError):
        mann_whitney_u([], [1.0])
    with pytest.raises(ValueError):
        mann_whitney_u([1.0], [])


# --------------------------------------------------------- interpret_p_value


def test_interpret_p_value_thresholds() -> None:
    assert interpret_p_value(0.0001) == (
        "Highly significant difference (p < 0.001): it is very unlikely these two runs "
        "perform the same."
    )
    assert interpret_p_value(0.005) == (
        "Significant difference (p = 0.005): strong evidence the runs perform differently."
    )
    assert interpret_p_value(0.03).startswith(
        "Statistically significant difference (p = 0.030)"
    )
    assert interpret_p_value(0.07).startswith("Weak evidence of a difference (p = 0.070)")
    assert interpret_p_value(0.5).startswith(
        "No statistically significant difference (p = 0.500)"
    )


# ------------------------------------------------------------------ ci_overlap


def test_ci_overlap_cases() -> None:
    assert ci_overlap((1.0, 2.0), (1.5, 3.0)) is True
    assert ci_overlap((1.0, 2.0), (2.0, 3.0)) is True  # touching endpoints overlap
    assert ci_overlap((1.0, 5.0), (2.0, 3.0)) is True  # containment
    assert ci_overlap((1.0, 2.0), (2.01, 3.0)) is False
    assert ci_overlap((2.01, 3.0), (1.0, 2.0)) is False
