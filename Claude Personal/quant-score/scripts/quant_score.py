#!/usr/bin/env python3
"""
Alpha Picks-style five-pillar quantitative stock scorer.

Pillars: Value, Growth, Profitability, Momentum, EPS Revisions.
Every metric is percentile-ranked against an industry peer set
(sector-relative), mapped to letter grades (A+..F), combined into a
1.0-5.0 composite and a verdict (Strong Buy / Buy / Hold / Sell /
Strong Sell). Deterministic: same-day re-runs hit a snapshot cache and
return identical results.

Usage:
  python quant_score.py SNDK
  python quant_score.py NVDA SNDK MU          # multi-ticker + ranked table
  python quant_score.py SNDK --json
  python quant_score.py SNDK --refresh        # bypass same-day cache
"""
import argparse
import hashlib
import json
import math
import re
import sys
import time
from datetime import datetime
from pathlib import Path


def ensure_deps():
    import subprocess
    for pkg in ["yfinance", "pandas", "numpy"]:
        try:
            __import__(pkg)
        except ImportError:
            print(f"Installing {pkg}...", file=sys.stderr)
            subprocess.check_call([sys.executable, "-m", "pip", "install",
                                   pkg, "--quiet", "--break-system-packages"])


ensure_deps()
import pandas as pd  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
CACHE_DIR = SCRIPT_DIR.parent / "data" / "cache"

# Sentinel: metric is structurally bad (e.g. negative earnings -> no P/E).
# Ranks at percentile 0, unlike a coverage gap (None) which is dropped.
WORST = "WORST"

PILLARS = ["value", "growth", "profitability", "momentum", "revisions"]

CONFIG = {
    "pillar_weights": {"value": 1, "growth": 1, "profitability": 1,
                       "momentum": 1, "revisions": 1},
    # 90-day estimate change is weighted above 7/30-day breadth (spec).
    "metric_weights": {"revisions": {"delta_fy0": 2, "delta_fy1": 2,
                                     "breadth": 1}},
    "verdict": {"strong_buy": 4.0, "buy": 3.5, "hold": 2.5, "sell": 1.5},
    "strong_buy_pillar_floor": 45.0,   # all pillars >= C- for Strong Buy
    "value_circuit_breaker": 45.0,     # Value pctl < 45 (D+ or worse) caps at Hold
    "universe": {"min_cap": 500e6, "min_price": 10.0},
    "peers": {"min": 8, "widen_below": 10, "max": 50, "cache_days": 7},
    "momentum_windows": {"ret_3m": 63, "ret_6m": 126,
                         "ret_9m": 189, "ret_12m": 252},
    "winsorize": {
        "trailing_pe": (0, 150), "forward_pe": (0, 150), "peg": (0, 10),
        "ps": (0, 60), "pb": (0, 60), "ev_ebitda": (0, 100),
        "fcf_yield": (-0.5, 0.5),
        "rev_growth": (-1, 3), "eps_growth": (-2, 5),
        "rev_cagr_3y": (-1, 2), "fwd_eps_growth": (-2, 2),
        "gross_margin": (-1, 1), "op_margin": (-2, 1), "net_margin": (-2, 1),
        "roe": (-2, 3), "roa": (-1, 1), "fcf_margin": (-2, 1),
    },
    "grade_bands": [(97, "A+"), (93, "A"), (90, "A-"), (85, "B+"),
                    (75, "B"), (65, "B-"), (58, "C+"), (51, "C"),
                    (45, "C-"), (38, "D+"), (32, "D"), (25, "D-"), (0, "F")],
}

# Metrics where a LOWER raw value is better. Everything else: higher better.
LOWER_IS_BETTER = {"trailing_pe", "forward_pe", "peg", "ps", "pb",
                   "ev_ebitda"}

# sectorKey -> metrics excluded entirely (yfinance returns fake 0.0 gross
# margins and negative OCF for banks; EV/EBITDA is meaningless there).
SECTOR_MASKS = {
    "financial-services": {"ev_ebitda", "fcf_yield", "fcf_margin",
                           "gross_margin"},
}

METRIC_LABELS = {
    "trailing_pe": "P/E", "forward_pe": "Fwd P/E", "peg": "PEG",
    "ps": "P/S", "pb": "P/B", "ev_ebitda": "EV/EBITDA",
    "fcf_yield": "FCF yield",
    "rev_growth": "Rev growth", "eps_growth": "EPS growth",
    "rev_cagr_3y": "3y rev CAGR", "fwd_eps_growth": "Fwd EPS growth",
    "gross_margin": "Gross margin", "op_margin": "Op margin",
    "net_margin": "Net margin", "roe": "ROE", "roa": "ROA",
    "fcf_margin": "FCF margin",
    "ret_3m": "3m return", "ret_6m": "6m return",
    "ret_9m": "9m return", "ret_12m": "12m return",
    "dist_52wk_high": "vs 52wk high",
    "delta_fy0": "FY0 est chg 90d", "delta_fy1": "FY1 est chg 90d",
    "breadth": "Revision breadth",
}

# ---------------------------------------------------------------- scoring core

def winsorize(value, bounds):
    """Clamp a raw metric value into [lo, hi]; pass through None/no-bounds."""
    if value is None or bounds is None or not isinstance(value, (int, float)):
        return value
    lo, hi = bounds
    return max(lo, min(hi, value))


def percentile_rank(value, peer_values, lower_is_better=False):
    """Goodness percentile (0=worst, 100=best) of value within the peer pool.

    value=WORST -> 0.0 (structurally bad). value=None/NaN -> None (no data).
    Needs at least 2 valid peer values, else None.
    Ties get midrank so identical values share a percentile.
    """
    pool = [v for v in peer_values
            if isinstance(v, (int, float)) and not math.isnan(v)]
    if isinstance(value, str) and value == WORST:
        return 0.0 if len(pool) >= 2 else None
    if not isinstance(value, (int, float)) or math.isnan(value):
        return None
    if len(pool) < 2:
        return None
    pool = pool + [value]
    below = sum(1 for v in pool if v < value)
    ties = sum(1 for v in pool if v == value) - 1  # exclude self
    rank = (below + 0.5 * ties) / (len(pool) - 1)  # 0..1
    return 100.0 * (1 - rank) if lower_is_better else 100.0 * rank


def grade(pct):
    """Map a 0-100 percentile to a letter grade per CONFIG bands."""
    if pct is None:
        return "N/A"
    for floor, letter in CONFIG["grade_bands"]:
        if pct >= floor:
            return letter
    return "F"


def estimate_delta(current, ago):
    """Sign-aware relative change between two estimates, clamped to [-2, 2].

    Uses abs(ago) as denominator so a zero-crossing (profit -> loss
    forecast) keeps the correct sign instead of flipping it.
    """
    for v in (current, ago):
        if not isinstance(v, (int, float)) or math.isnan(v):
            return None
    denom = max(abs(ago), 0.01)
    return max(-2.0, min(2.0, (current - ago) / denom))


def score_pillar(metric_pcts, weights=None):
    """Weighted mean of a pillar's metric percentiles.

    metric_pcts: dict name -> percentile (0-100) or None (dropped; its
    weight is redistributed). Fewer than 2 usable metrics -> (None, used).
    Returns (pillar_percentile, sorted_used_metric_names).
    """
    usable = {k: v for k, v in metric_pcts.items() if v is not None}
    if len(usable) < 2:
        return None, sorted(usable)
    if weights is None:
        weights = {}
    total = sum(weights.get(k, 1.0) for k in usable)
    score = sum(v * weights.get(k, 1.0) for k, v in usable.items()) / total
    return score, sorted(usable)


def composite_score(pillar_scores, weights):
    """Weighted mean of pillar percentiles -> 1.0-5.0 score.

    N/A pillars are excluded with weights renormalized. Two or more N/A
    pillars -> (None, na_list): not enough signal for any verdict.
    """
    na = sorted(p for p, v in pillar_scores.items() if v is None)
    if len(na) >= 2:
        return None, na
    avail = {p: v for p, v in pillar_scores.items() if v is not None}
    total = sum(weights[p] for p in avail)
    mean_pct = sum(v * weights[p] for p, v in avail.items()) / total
    return 1 + 4 * mean_pct / 100.0, na


def decide_verdict(composite, pillar_scores):
    """Map composite to verdict, applying Strong Buy pillar floor and the
    Value circuit breaker. Returns (verdict, notes)."""
    if composite is None:
        na = sorted(p for p, v in pillar_scores.items() if v is None)
        return "NO VERDICT", [
            f"Insufficient data: pillars N/A: {', '.join(na)}"]
    t = CONFIG["verdict"]
    if composite >= t["strong_buy"]:
        base = "Strong Buy"
    elif composite >= t["buy"]:
        base = "Buy"
    elif composite >= t["hold"]:
        base = "Hold"
    elif composite >= t["sell"]:
        base = "Sell"
    else:
        base = "Strong Sell"
    notes = []
    if base == "Strong Buy":
        floor = CONFIG["strong_buy_pillar_floor"]
        weak = sorted(p for p, v in pillar_scores.items()
                      if v is not None and v < floor)
        if weak:
            base = "Buy"
            notes.append("Demoted from Strong Buy: pillar(s) below C-: "
                         + ", ".join(weak))
    v_pct = pillar_scores.get("value")
    if (v_pct is not None and v_pct < CONFIG["value_circuit_breaker"]
            and base in ("Strong Buy", "Buy")):
        base = "Hold"
        notes.append("Value circuit breaker: valuation D+ or worse "
                     "caps verdict at Hold")
    return base, notes

# ---------------------------------------------------------- metric extraction

def _num(x):
    """Return x as float if it's a usable number, else None.
    Rejects bool explicitly (bool is an int subclass in Python)."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)) and not math.isnan(x):
        return float(x)
    return None


def _pos(x):
    n = _num(x)
    return n is not None and n > 0


def _median(vals):
    vals = sorted(v for v in vals
                  if isinstance(v, (int, float)) and not math.isnan(v))
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


def value_metrics(info):
    """Valuation ratios. Structurally-missing (negative earnings/EBITDA/
    book) -> WORST sentinel; genuine coverage gaps -> None (dropped)."""
    eps_ttm = info.get("trailingEps")
    fcf, mcap = _num(info.get("freeCashflow")), _num(info.get("marketCap"))
    peg = _num(info.get("trailingPegRatio")) or _num(info.get("pegRatio"))
    ebitda = info.get("ebitda")
    m = {
        "trailing_pe": _num(info.get("trailingPE"))
                       or (None if _pos(eps_ttm) else WORST),
        "forward_pe": _num(info.get("forwardPE"))
                      or (None if _pos(info.get("forwardEps")) else WORST),
        "peg": peg or (None if _pos(eps_ttm) else WORST),
        "ps": _num(info.get("priceToSalesTrailing12Months")),
        "pb": _num(info.get("priceToBook")),
        "ev_ebitda": _num(info.get("enterpriseToEbitda"))
                     or (None if (ebitda is None or _pos(ebitda)) else WORST),
        "fcf_yield": (fcf / mcap) if (fcf is not None and mcap) else None,
    }
    # Any negative lower-is-better ratio means a negative denominator
    # (earnings/book/EBITDA): structurally bad, not "cheap".
    for k in list(m):
        if k in LOWER_IS_BETTER and isinstance(m[k], float) and m[k] <= 0:
            m[k] = WORST
    return m


def growth_metrics(info, rev_series=None):
    """rev_series: annual Total Revenue, oldest -> latest (up to 4 values)."""
    m = {
        "rev_growth": _num(info.get("revenueGrowth")),
        "eps_growth": _num(info.get("earningsGrowth")),
        "fwd_eps_growth": estimate_delta(_num(info.get("forwardEps")),
                                         _num(info.get("trailingEps"))),
        "rev_cagr_3y": None,
    }
    if (rev_series and len(rev_series) >= 3
            and _pos(rev_series[0]) and _pos(rev_series[-1])):
        years = len(rev_series) - 1
        m["rev_cagr_3y"] = (rev_series[-1] / rev_series[0]) ** (1 / years) - 1
    return m


def profitability_metrics(info):
    fcf, rev = _num(info.get("freeCashflow")), _num(info.get("totalRevenue"))
    return {
        "gross_margin": _num(info.get("grossMargins")),
        "op_margin": _num(info.get("operatingMargins")),
        "net_margin": _num(info.get("profitMargins")),
        "roe": _num(info.get("returnOnEquity")),
        "roa": _num(info.get("returnOnAssets")),
        "fcf_margin": (fcf / rev) if (fcf is not None and rev) else None,
    }


def momentum_metrics(closes, sym):
    """Trailing returns over 3/6/9/12 months plus distance from 52-week
    high (0 = at the high = best; more negative = further below).
    Returns are ranked vs peers later, making them sector-relative.
    Missing windows (IPO < 1y) stay None and are dropped by score_pillar."""
    m = {**{k: None for k in CONFIG["momentum_windows"]},
         "dist_52wk_high": None}
    if closes is None or sym not in getattr(closes, "columns", []):
        return m
    s = closes[sym].dropna()
    if s.empty:
        return m
    for name, days in CONFIG["momentum_windows"].items():
        if len(s) > days:
            m[name] = float(s.iloc[-1] / s.iloc[-1 - days] - 1)
    tail = s.tail(252)
    if len(tail):
        m["dist_52wk_high"] = float(s.iloc[-1] / tail.max() - 1)
    return m


def revisions_metrics(eps_trend, eps_revisions):
    """eps_trend: {'0y': {'current':..,'90daysAgo':..}, '+1y': {...}}
    eps_revisions: {'0y': {'upLast7days':..,'downLast7Days':..,...}}
    (plain dicts, as cached by fetch_snapshot). Key lookup for breadth is
    case-insensitive because yfinance mixes capitalization."""
    m = {"delta_fy0": None, "delta_fy1": None, "breadth": None}
    if eps_trend:
        r0 = eps_trend.get("0y") or {}
        r1 = eps_trend.get("+1y") or {}
        m["delta_fy0"] = estimate_delta(_num(r0.get("current")),
                                        _num(r0.get("90daysAgo")))
        m["delta_fy1"] = estimate_delta(_num(r1.get("current")),
                                        _num(r1.get("90daysAgo")))
    if eps_revisions:
        row = eps_revisions.get("0y") or {}

        def g(name):
            for k, v in row.items():
                if k.lower() == name.lower():
                    return _num(v) or 0
            return 0

        up = g("upLast7days") + g("upLast30days")
        down = g("downLast7days") + g("downLast30days")
        total = up + down
        m["breadth"] = (up - down) / total if total else None
    return m


def build_all_metrics(snap, closes, sym):
    """All five pillars' raw metrics for one ticker, sector mask applied."""
    info = snap["info"]
    pillars = {
        "value": value_metrics(info),
        "growth": growth_metrics(info, snap.get("rev_series")),
        "profitability": profitability_metrics(info),
        "momentum": momentum_metrics(closes, sym),
        "revisions": revisions_metrics(snap.get("eps_trend"),
                                       snap.get("eps_revisions")),
    }
    mask = SECTOR_MASKS.get(info.get("sectorKey"), set())
    for pm in pillars.values():
        for k in list(pm):
            if k in mask:
                del pm[k]
    return pillars
