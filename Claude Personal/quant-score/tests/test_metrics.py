import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import quant_score as qs  # noqa: E402


def test_sector_mask_exists_for_financials():
    assert "gross_margin" in qs.SECTOR_MASKS["financial-services"]


# --- fixtures modeled on real yfinance .info shapes (verified 2026-06-12) ---

PROFITABLE = {  # SNDK-like: profitable, but no PEG coverage
    "trailingPE": 25.1, "forwardPE": 18.0, "trailingEps": 4.0,
    "forwardEps": 5.5, "trailingPegRatio": None,
    "priceToSalesTrailing12Months": 3.2, "priceToBook": 4.1,
    "enterpriseToEbitda": 14.0, "ebitda": 5e9,
    "freeCashflow": 2e9, "marketCap": 50e9, "totalRevenue": 16e9,
    "grossMargins": 0.38, "operatingMargins": 0.22, "profitMargins": 0.18,
    "returnOnEquity": 0.25, "returnOnAssets": 0.11,
    "revenueGrowth": 0.30, "earningsGrowth": 0.45,
    "sectorKey": "technology",
}

UNPROFITABLE = {  # KRUS-like: negative earnings -> P/E & PEG absent
    "trailingEps": -0.5, "forwardEps": -0.1,
    "priceToSalesTrailing12Months": 2.0, "priceToBook": 3.0,
    "ebitda": -10e6, "freeCashflow": -5e6, "marketCap": 700e6,
    "totalRevenue": 250e6,
    "grossMargins": 0.20, "operatingMargins": -0.05, "profitMargins": -0.08,
    "returnOnEquity": -0.10, "returnOnAssets": -0.04,
    "revenueGrowth": 0.25,
    "sectorKey": "consumer-cyclical",
}

BANK = {  # JPM-like: fake 0.0 gross margin, no EV/EBITDA, negative OCF
    "trailingPE": 12.0, "forwardPE": 11.0, "trailingEps": 18.0,
    "forwardEps": 19.5, "trailingPegRatio": 1.4,
    "priceToSalesTrailing12Months": 4.0, "priceToBook": 1.9,
    "grossMargins": 0.0, "operatingMargins": 0.40, "profitMargins": 0.32,
    "returnOnEquity": 0.16, "returnOnAssets": 0.013,
    "revenueGrowth": 0.06, "earningsGrowth": 0.08,
    "marketCap": 600e9, "totalRevenue": 170e9,
    "sectorKey": "financial-services",
}


def test_value_metrics_profitable():
    m = qs.value_metrics(PROFITABLE)
    assert m["trailing_pe"] == 25.1
    assert m["peg"] is None            # coverage gap, NOT structural
    assert m["fcf_yield"] == 2e9 / 50e9


def test_value_metrics_unprofitable_structural_worst():
    m = qs.value_metrics(UNPROFITABLE)
    assert m["trailing_pe"] == qs.WORST
    assert m["forward_pe"] == qs.WORST
    assert m["peg"] == qs.WORST
    assert m["ev_ebitda"] == qs.WORST  # negative EBITDA
    assert m["fcf_yield"] < 0          # negative kept raw -> ranks worst
    assert m["ps"] == 2.0              # P/S unaffected


def test_value_metrics_negative_ratio_becomes_worst():
    info = dict(PROFITABLE, trailingPE=-8.0)
    assert qs.value_metrics(info)["trailing_pe"] == qs.WORST


def test_growth_metrics():
    m = qs.growth_metrics(PROFITABLE, rev_series=[100.0, 150.0, 200.0, 250.0])
    assert m["rev_growth"] == 0.30
    assert abs(m["rev_cagr_3y"] - ((250 / 100) ** (1 / 3) - 1)) < 1e-9
    assert m["fwd_eps_growth"] == qs.estimate_delta(5.5, 4.0)


def test_growth_metrics_negative_base_cagr_dropped():
    m = qs.growth_metrics(PROFITABLE, rev_series=[-50.0, 100.0, 200.0])
    assert m["rev_cagr_3y"] is None
    m2 = qs.growth_metrics(PROFITABLE, rev_series=None)
    assert m2["rev_cagr_3y"] is None


def test_profitability_metrics():
    m = qs.profitability_metrics(PROFITABLE)
    assert m["gross_margin"] == 0.38
    assert m["fcf_margin"] == 2e9 / 16e9


def test_sector_mask_strips_bank_metrics():
    snap = {"info": BANK, "rev_series": None,
            "eps_trend": None, "eps_revisions": None}
    pillars = qs.build_all_metrics(snap, None, "JPM")
    assert "gross_margin" not in pillars["profitability"]
    assert "fcf_margin" not in pillars["profitability"]
    assert "ev_ebitda" not in pillars["value"]
    assert "fcf_yield" not in pillars["value"]
    assert "op_margin" in pillars["profitability"]  # kept


def test_median():
    assert qs._median([3, 1, 2]) == 2
    assert qs._median([1, 2, 3, 4]) == 2.5
    assert qs._median([]) is None
