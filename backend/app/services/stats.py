"""Statistical helpers built on numpy only (no scipy).

`mann_whitney_u` uses the two-sided normal approximation with tie correction and
continuity correction — a large-sample approximation; exact p-values for tiny
samples will differ slightly.
"""

import math
from collections.abc import Sequence
from typing import NamedTuple

import numpy as np


class MannWhitneyResult(NamedTuple):
    u_statistic: float
    p_value: float


def mean_std(scores: Sequence[float]) -> tuple[float, float]:
    """(mean, sample std with ddof=1); std is 0.0 for a single value."""
    if len(scores) == 0:
        raise ValueError("mean_std requires at least one value")
    arr = np.asarray(scores, dtype=float)
    mean = float(arr.mean())
    std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
    return mean, std


def bootstrap_ci(
    scores: Sequence[float],
    n_resamples: int = 1000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float]:
    """Percentile-method bootstrap CI of the mean."""
    n = len(scores)
    if n == 0:
        raise ValueError("bootstrap_ci requires at least one value")
    if n == 1:
        value = float(scores[0])
        return value, value
    rng = np.random.default_rng(seed)
    arr = np.asarray(scores, dtype=float)
    indices = rng.integers(0, n, size=(n_resamples, n))
    means = arr[indices].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    low = float(np.percentile(means, 100.0 * alpha))
    high = float(np.percentile(means, 100.0 * (1.0 - alpha)))
    return low, high


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """1-based ranks with ties assigned the average of their positions."""
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    n = values.size
    ranks_sorted = np.empty(n, dtype=float)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sorted_values[j + 1] == sorted_values[i]:
            j += 1
        ranks_sorted[i : j + 1] = (i + j) / 2.0 + 1.0
        i = j + 1
    ranks = np.empty(n, dtype=float)
    ranks[order] = ranks_sorted
    return ranks


def mann_whitney_u(a: Sequence[float], b: Sequence[float]) -> MannWhitneyResult:
    """Two-sided Mann-Whitney U via the normal approximation (ties + continuity corrected)."""
    n1, n2 = len(a), len(b)
    if n1 == 0 or n2 == 0:
        raise ValueError("mann_whitney_u requires two non-empty samples")
    pooled = np.concatenate([np.asarray(a, dtype=float), np.asarray(b, dtype=float)])
    total = n1 + n2
    ranks = _average_ranks(pooled)
    r1 = float(ranks[:n1].sum())
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u = min(u1, n1 * n2 - u1)
    _, counts = np.unique(pooled, return_counts=True)
    tie_term = float(np.sum(counts.astype(float) ** 3 - counts))
    sigma_sq = (n1 * n2 / 12.0) * ((total + 1) - tie_term / (total * (total - 1)))
    if sigma_sq <= 0.0:
        # All pooled values identical: no evidence of any difference.
        return MannWhitneyResult(float(u), 1.0)
    sigma = math.sqrt(sigma_sq)
    mu = n1 * n2 / 2.0
    diff = u - mu
    if diff > 0:
        z = (diff - 0.5) / sigma
    elif diff < 0:
        z = (diff + 0.5) / sigma
    else:
        z = 0.0
    # 2 * (1 - Phi(|z|)) == erfc(|z| / sqrt(2))
    p = math.erfc(abs(z) / math.sqrt(2.0))
    return MannWhitneyResult(float(u), float(min(max(p, 0.0), 1.0)))


def interpret_p_value(p: float) -> str:
    if p < 0.001:
        return (
            "Highly significant difference (p < 0.001): it is very unlikely these two runs "
            "perform the same."
        )
    if p < 0.01:
        return f"Significant difference (p = {p:.3f}): strong evidence the runs perform differently."
    if p < 0.05:
        return (
            f"Statistically significant difference (p = {p:.3f}): evidence the runs perform "
            "differently at the 95% confidence level."
        )
    if p < 0.1:
        return (
            f"Weak evidence of a difference (p = {p:.3f}): not significant at the 95% level; "
            "more data may clarify."
        )
    return (
        f"No statistically significant difference (p = {p:.3f}): the observed gap is "
        "consistent with chance."
    )


def ci_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]
