import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import quant_score as qs  # noqa: E402


def test_module_imports():
    assert qs.WORST == "WORST"
    assert set(qs.PILLARS) == {"value", "growth", "profitability",
                               "momentum", "revisions"}
    assert qs.CONFIG["verdict"]["strong_buy"] == 4.0


def test_winsorize_clamps():
    assert qs.winsorize(500, (0, 150)) == 150
    assert qs.winsorize(-5, (0, 150)) == 0
    assert qs.winsorize(42, (0, 150)) == 42
    assert qs.winsorize(None, (0, 150)) is None
    assert qs.winsorize(42, None) == 42


def test_percentile_rank_higher_better():
    peers = [1, 2, 3, 4]
    assert qs.percentile_rank(5, peers) == 100.0
    assert qs.percentile_rank(0, peers) == 0.0
    assert qs.percentile_rank(2.5, peers) == 50.0


def test_percentile_rank_lower_better_inverts():
    peers = [10, 20, 30, 40]
    assert qs.percentile_rank(5, peers, lower_is_better=True) == 100.0
    assert qs.percentile_rank(50, peers, lower_is_better=True) == 0.0


def test_percentile_rank_ties_get_midrank():
    assert qs.percentile_rank(2, [2, 2]) == 50.0


def test_percentile_rank_worst_sentinel():
    assert qs.percentile_rank(qs.WORST, [1, 2, 3]) == 0.0
    assert qs.percentile_rank(qs.WORST, []) is None


def test_percentile_rank_missing_or_thin_pool():
    assert qs.percentile_rank(None, [1, 2, 3]) is None
    assert qs.percentile_rank(5, [1]) is None
    assert qs.percentile_rank(float("nan"), [1, 2, 3]) is None


def test_grade_bands():
    assert qs.grade(100) == "A+"
    assert qs.grade(97) == "A+"
    assert qs.grade(96.9) == "A"
    assert qs.grade(93) == "A"
    assert qs.grade(90) == "A-"
    assert qs.grade(85) == "B+"
    assert qs.grade(75) == "B"
    assert qs.grade(65) == "B-"
    assert qs.grade(45) == "C-"
    assert qs.grade(44.9) == "D+"
    assert qs.grade(24.9) == "F"
    assert qs.grade(0) == "F"
    assert qs.grade(None) == "N/A"


def test_estimate_delta_normal():
    assert abs(qs.estimate_delta(1.2, 1.0) - 0.2) < 1e-9


def test_estimate_delta_zero_crossing_is_sign_aware():
    # Forecast flipped from profit to loss: must be NEGATIVE.
    d = qs.estimate_delta(-0.0156, 0.0036)
    assert d is not None and d < 0
    # Recovery from loss to profit must be POSITIVE.
    d2 = qs.estimate_delta(0.50, -0.25)
    assert d2 is not None and d2 > 0


def test_estimate_delta_clamped():
    assert qs.estimate_delta(100.0, 0.5) == 2.0
    assert qs.estimate_delta(-100.0, 0.5) == -2.0


def test_estimate_delta_missing():
    assert qs.estimate_delta(None, 1.0) is None
    assert qs.estimate_delta(1.0, None) is None
    assert qs.estimate_delta(float("nan"), 1.0) is None
