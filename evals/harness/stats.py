"""Seeded bootstrap confidence intervals for the Phase 8 analysis."""

import random


def bootstrap_ci(values, n_boot: int = 10_000, alpha: float = 0.05,
                 seed: int = 42) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean of `values` (deterministic)."""
    rng = random.Random(seed)
    k = len(values)
    means = sorted(
        sum(rng.choices(values, k=k)) / k for _ in range(n_boot)
    )
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[int((1 - alpha / 2) * n_boot) - 1]
    return lo, hi
