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


def test_score_pillar_weighted_mean():
    score, used = qs.score_pillar({"a": 80.0, "b": 40.0})
    assert score == 60.0
    assert used == ["a", "b"]


def test_score_pillar_redistributes_dropped_metrics():
    score, used = qs.score_pillar({"a": 80.0, "b": None, "c": 40.0})
    assert score == 60.0
    assert used == ["a", "c"]


def test_score_pillar_custom_weights():
    score, _ = qs.score_pillar({"a": 100.0, "b": 0.0}, {"a": 3, "b": 1})
    assert score == 75.0


def test_score_pillar_under_two_metrics_is_na():
    score, _ = qs.score_pillar({"a": 80.0, "b": None})
    assert score is None


def test_composite_equal_weights():
    scores = {"value": 80, "growth": 80, "profitability": 80,
              "momentum": 80, "revisions": 80}
    comp, na = qs.composite_score(scores, qs.CONFIG["pillar_weights"])
    assert abs(comp - 4.2) < 1e-9
    assert na == []


def test_composite_renormalizes_one_na():
    scores = {"value": 60, "growth": 60, "profitability": 60,
              "momentum": 60, "revisions": None}
    comp, na = qs.composite_score(scores, qs.CONFIG["pillar_weights"])
    assert abs(comp - 3.4) < 1e-9
    assert na == ["revisions"]


def test_composite_two_na_no_verdict():
    scores = {"value": 90, "growth": 90, "profitability": 90,
              "momentum": None, "revisions": None}
    comp, na = qs.composite_score(scores, qs.CONFIG["pillar_weights"])
    assert comp is None
    assert sorted(na) == ["momentum", "revisions"]


def test_verdict_strong_buy():
    scores = {p: 80.0 for p in qs.PILLARS}
    v, notes = qs.decide_verdict(4.2, scores)
    assert v == "Strong Buy"
    assert notes == []


def test_verdict_demoted_when_pillar_below_floor():
    scores = {p: 90.0 for p in qs.PILLARS}
    scores["revisions"] = 40.0  # below C- floor (45)
    v, notes = qs.decide_verdict(4.1, scores)
    assert v == "Buy"
    assert any("emoted" in n for n in notes)


def test_verdict_value_circuit_breaker_caps_at_hold():
    scores = {p: 95.0 for p in qs.PILLARS}
    scores["value"] = 40.0  # D+ or worse
    v, notes = qs.decide_verdict(4.4, scores)
    assert v == "Hold"
    assert any("circuit breaker" in n.lower() for n in notes)


def test_verdict_bands():
    mid = {p: 50.0 for p in qs.PILLARS}
    assert qs.decide_verdict(3.6, mid)[0] == "Buy"
    assert qs.decide_verdict(3.0, mid)[0] == "Hold"
    assert qs.decide_verdict(2.0, mid)[0] == "Sell"
    assert qs.decide_verdict(1.2, mid)[0] == "Strong Sell"


def test_verdict_band_edges_are_inclusive_lower_bound():
    # Thresholds use >=, so a composite landing EXACTLY on a cut takes the
    # higher tier. CRM landed 3.46 (just under Buy) in the wild -> boundary
    # behavior is real-world relevant.
    mid = {p: 50.0 for p in qs.PILLARS}
    assert qs.decide_verdict(3.5, mid)[0] == "Buy"     # exactly at Buy cut
    assert qs.decide_verdict(3.4999, mid)[0] == "Hold"  # a hair below
    assert qs.decide_verdict(2.5, mid)[0] == "Hold"    # exactly at Hold cut
    assert qs.decide_verdict(2.4999, mid)[0] == "Sell"
    assert qs.decide_verdict(4.0, {p: 80.0 for p in qs.PILLARS})[0] \
        == "Strong Buy"                                 # exactly at SB cut


def _pillars_with(forward_pct, trailing_pct, fwd_v, trail_v, rev_pct):
    """Minimal pillars_out shaped like score_ticker's, for flag tests."""
    return {
        "value": {"metrics": {
            "forward_pe": {"pct": forward_pct, "value": fwd_v},
            "trailing_pe": {"pct": trailing_pct, "value": trail_v},
        }},
        "revisions": {"metrics": {
            "delta_fy0": {"pct": rev_pct},
            "delta_fy1": {"pct": 20.0},
        }},
    }


def test_peak_earnings_flag_fires_on_mu_shape():
    # MU 2026-06-12: fwd P/E 8.8 (100th pctl), trailing P/E 46.5, FY0 rev 98th.
    p = _pillars_with(100.0, 81.0, 8.8, 46.5, 98.0)
    f = qs.peak_earnings_flag(p)
    assert f is not None and "peak-earnings" in f


def test_peak_earnings_flag_silent_when_forward_not_top_decile():
    # CRM shape: fwd P/E only 87.8th pctl -> below the 90 trigger.
    assert qs.peak_earnings_flag(
        _pillars_with(87.8, 78.0, 10.7, 19.3, 75.0)) is None


def test_peak_earnings_flag_silent_without_trailing_divergence():
    # Cheap forward AND cheap trailing in absolute terms (ratio < 1.5):
    # genuinely cheap, not a peak-earnings artifact.
    assert qs.peak_earnings_flag(
        _pillars_with(95.0, 95.0, 12.0, 14.0, 95.0)) is None


def test_peak_earnings_flag_silent_without_hot_revisions():
    # Forward cheap + big trailing divergence but revisions NOT top-decile.
    assert qs.peak_earnings_flag(
        _pillars_with(95.0, 60.0, 8.0, 40.0, 50.0)) is None


def test_peak_earnings_flag_handles_structural_worst_trailing():
    # Negative trailing earnings (value=None) must not crash or false-fire.
    p = _pillars_with(95.0, 0.0, 8.0, None, 95.0)
    assert qs.peak_earnings_flag(p) is None


def test_cap_mismatch_flag_fires_when_peers_much_larger():
    # RDW shape: $3B target vs defense primes whose median is hundreds of B.
    f = qs.cap_mismatch_flag(3e9, [300e9, 150e9, 90e9, 200e9])
    assert f is not None and "cap mismatch" in f


def test_cap_mismatch_flag_fires_when_peers_much_smaller():
    # MU shape: $1.1T target vs a median small-cap semi cohort.
    f = qs.cap_mismatch_flag(1.1e12, [8e9, 12e9, 5e9, 20e9])
    assert f is not None


def test_cap_mismatch_flag_silent_when_comparable():
    assert qs.cap_mismatch_flag(50e9, [40e9, 60e9, 55e9, 45e9]) is None


def test_cap_mismatch_flag_guards_missing_data():
    assert qs.cap_mismatch_flag(None, [40e9, 60e9]) is None
    assert qs.cap_mismatch_flag(50e9, [40e9]) is None   # thin pool
    assert qs.cap_mismatch_flag(50e9, []) is None


def test_extreme_valuation_flags():
    f = qs.extreme_valuation_flags({"trailingPE": 140.0, "marketCap": 600e6})
    assert any("P/E" in x for x in f)
    assert any("Small cap" in x for x in f)
    # clean megacap at a normal multiple -> no flags
    assert qs.extreme_valuation_flags(
        {"trailingPE": 22.0, "marketCap": 90e9}) == []


def test_verdict_none_composite():
    v, notes = qs.decide_verdict(None, {p: None for p in qs.PILLARS})
    assert v == "NO VERDICT"
    assert any("insufficient" in n.lower() for n in notes)


def test_norm_name_dedupes_corporate_suffixes():
    assert qs._norm_name("The Bank of New York Mellon Corporation") == \
        qs._norm_name("Bank of New York Mellon Corp")
    assert qs._norm_name("Apple Inc.") == qs._norm_name("Apple Inc")
    assert qs._norm_name(None) == ""
