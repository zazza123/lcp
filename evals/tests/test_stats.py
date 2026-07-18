from harness.stats import bootstrap_ci


def test_ci_brackets_the_mean_and_is_deterministic():
    values = [0, 0, 1, 1, 1, 1, 0, 1, 1, 1]
    lo1, hi1 = bootstrap_ci(values, seed=42)
    lo2, hi2 = bootstrap_ci(values, seed=42)
    assert (lo1, hi1) == (lo2, hi2)
    assert lo1 <= sum(values) / len(values) <= hi1
    assert 0.0 <= lo1 < hi1 <= 1.0
