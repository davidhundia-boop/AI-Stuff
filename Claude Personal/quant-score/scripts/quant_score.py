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
