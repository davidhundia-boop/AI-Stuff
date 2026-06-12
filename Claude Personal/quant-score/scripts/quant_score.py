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


# -------------------------------------------------------------------- data IO

def _today():
    return datetime.now().strftime("%Y-%m-%d")


def with_retry(fn, attempts=3):
    """Run fn() with exponential backoff (1s, 2s) on any exception."""
    for i in range(attempts):
        try:
            return fn()
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(2 ** i)


def load_cache(name, max_age_days):
    f = CACHE_DIR / name
    if not f.exists():
        return None
    age_days = (time.time() - f.stat().st_mtime) / 86400
    if age_days > max_age_days:
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_cache(name, obj):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / name).write_text(
        json.dumps(obj, default=str), encoding="utf-8")


def purge_cache(max_age_days=7):
    """Delete cache files older than max_age_days (keeps the dir bounded)."""
    if not CACHE_DIR.exists():
        return
    cutoff = time.time() - max_age_days * 86400
    for f in CACHE_DIR.iterdir():
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def fetch_info(sym, refresh=False):
    """One ticker's .info dict, cached for the day (cheap universe checks)."""
    name = f"info_{sym}_{_today()}.json"
    if not refresh:
        c = load_cache(name, 1)
        if c is not None:
            return c
    import yfinance as yf
    info = with_retry(lambda: yf.Ticker(sym).info) or {}
    save_cache(name, info)
    return info


def fetch_snapshot(sym, refresh=False):
    """Full per-ticker snapshot: info + revenue series + EPS frames.
    Cached for the day -> same-day re-runs are deterministic."""
    name = f"snap_{sym}_{_today()}.json"
    if not refresh:
        c = load_cache(name, 1)
        if c is not None:
            return c
    import yfinance as yf
    snap = {"info": fetch_info(sym, refresh), "rev_series": None,
            "eps_trend": None, "eps_revisions": None}
    t = yf.Ticker(sym)
    try:
        fin = with_retry(lambda: t.financials)
        if fin is not None and "Total Revenue" in fin.index:
            vals = [_num(v) for v in fin.loc["Total Revenue"].values[:4]]
            vals = [v for v in vals if v is not None]
            snap["rev_series"] = list(reversed(vals))  # oldest -> latest
    except Exception:
        pass
    try:
        et = with_retry(lambda: t.eps_trend)
        if et is not None and not et.empty:
            snap["eps_trend"] = {
                str(idx): {c: _num(v) for c, v in row.items()
                           if c != "currency"}
                for idx, row in et.iterrows()}
    except Exception:
        pass
    try:
        er = with_retry(lambda: t.eps_revisions)
        if er is not None and not er.empty:
            snap["eps_revisions"] = {
                str(idx): {c: _num(v) for c, v in row.items()}
                for idx, row in er.iterrows()}
    except Exception:
        pass
    save_cache(name, snap)
    return snap


def fetch_prices(symbols, refresh=False):
    """Batched 2y daily closes for all symbols in ONE request (atomic
    same-bar snapshot -> deterministic momentum). Cached per day."""
    key = hashlib.md5(",".join(sorted(symbols)).encode()).hexdigest()[:10]
    f = CACHE_DIR / f"prices_{key}_{_today()}.csv"
    if f.exists() and not refresh:
        return pd.read_csv(f, index_col=0, parse_dates=True)
    import yfinance as yf
    df = with_retry(lambda: yf.download(
        list(symbols), period="2y", auto_adjust=True, progress=False))
    closes = df["Close"]
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(list(symbols)[0])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    closes.to_csv(f)
    return closes


# ------------------------------------------------------------ peer resolution

def _norm_name(name):
    """Normalize a company name for duplicate-entity detection
    (BK and BNY both resolve to 'bank of new york mellon')."""
    n = re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).strip()
    if n.startswith("the "):
        n = n[4:]
    for suf in (" incorporated", " corporation", " holdings", " companies",
                " company", " inc", " corp", " plc", " ltd", " co"):
        while n.endswith(suf):
            n = n[: -len(suf)].strip()
    return n


def _filter_universe(symbols, target_sym, seen_names, taken, refresh=False):
    """Apply universe criteria + EQUITY gate + name dedupe to candidate
    symbols (in given order). Mutates seen_names/taken; returns new picks."""
    out = []
    for s in symbols:
        s = str(s).upper()
        if s == target_sym.upper() or s in taken:
            continue
        try:
            info = fetch_info(s, refresh)
        except Exception:
            continue
        if info.get("quoteType") != "EQUITY":
            continue
        if (_num(info.get("marketCap")) or 0) < CONFIG["universe"]["min_cap"]:
            continue
        price = (_num(info.get("currentPrice"))
                 or _num(info.get("regularMarketPrice")) or 0)
        if price < CONFIG["universe"]["min_price"]:
            continue
        nm = _norm_name(info.get("longName") or info.get("shortName"))
        if nm and nm in seen_names:
            continue
        seen_names.add(nm)
        taken.add(s)
        out.append(s)
    return out


def resolve_peers(sym, info, refresh=False):
    """Peer symbols for sym: industry top_companies, widened to sibling
    industries then sector if thin. Cached 7 days per industry.

    The cache stores the FULL industry roster including sym itself so that
    different tickers in the same industry all see a consistent peer set;
    sym is filtered out only on read/return.  Empty pools are never persisted
    so transient network failures self-heal on the next run.
    """
    ik, sk = info.get("industryKey"), info.get("sectorKey")
    if not ik:
        return []
    cache_name = f"peers_{ik}.json"
    if not refresh:
        c = load_cache(cache_name, CONFIG["peers"]["cache_days"])
        if c is not None:
            return [p for p in c if p != sym.upper()]
    import yfinance as yf

    def candidates(container):
        try:
            tc = with_retry(lambda: container.top_companies)
            return [] if tc is None else [str(i) for i in tc.index]
        except Exception:
            return []

    seen_names, taken = set(), set()
    # Pass "" as target_sym so the cached roster includes the current ticker;
    # the target is filtered out on read/return above and at the final return.
    pool = _filter_universe(candidates(yf.Industry(ik)), "",
                            seen_names, taken, refresh)
    if len(pool) < CONFIG["peers"]["widen_below"] and sk:
        sec = yf.Sector(sk)
        try:  # sibling industries first (closer comps than whole sector)
            for sib in [str(i) for i in sec.industries.index if str(i) != ik]:
                pool += _filter_universe(candidates(yf.Industry(sib)), "",
                                         seen_names, taken, refresh)
                if len(pool) >= CONFIG["peers"]["widen_below"]:
                    break
        except Exception:
            pass
        if len(pool) < CONFIG["peers"]["min"]:
            pool += _filter_universe(candidates(sec), "",
                                     seen_names, taken, refresh)
    pool = pool[:CONFIG["peers"]["max"]]
    # Never persist an empty pool; transient failures should self-heal next run.
    if pool:
        save_cache(cache_name, pool)
    return [p for p in pool if p != sym.upper()]


# --------------------------------------------------------------- orchestration

def universe_flags(info):
    flags = []
    if (_num(info.get("marketCap")) or 0) < CONFIG["universe"]["min_cap"]:
        flags.append("Below Alpha Picks universe: market cap < $500M")
    price = (_num(info.get("currentPrice"))
             or _num(info.get("regularMarketPrice")) or 0)
    if price < CONFIG["universe"]["min_price"]:
        flags.append("Below Alpha Picks universe: price < $10")
    return flags


def evidence_str(metric_detail, max_items=2):
    """Headline evidence in Alpha Picks style:
    'P/E 25.1 vs median 32.0 (-22%)'. Picks the first metrics with data."""
    parts = []
    for mname, d in metric_detail.items():
        label = METRIC_LABELS.get(mname, mname)
        if d.get("structural_worst"):
            parts.append(f"{label}: negative (worst)")
            continue
        v, med = d.get("value"), d.get("peer_median")
        if v is None or med is None or d.get("pct") is None:
            continue
        if mname in LOWER_IS_BETTER:
            rel = (v - med) / med * 100 if med else 0
            parts.append(f"{label} {v:.1f} vs median {med:.1f} ({rel:+.0f}%)")
        elif abs(v) < 5:  # margins/growth/returns are fractions
            parts.append(f"{label} {v * 100:.1f}% vs median {med * 100:.1f}%")
        else:
            parts.append(f"{label} {v:.1f} vs median {med:.1f}")
        if len(parts) >= max_items:
            break
    return "; ".join(parts[:max_items]) if parts else "insufficient data"


def score_ticker(sym, snaps, closes):
    """Score sym against every other symbol in snaps. Pure given inputs.

    Peers whose metric is structurally WORST are counted at the worst end
    of that metric's winsorize bounds (instead of being dropped), so a
    sector full of money-losers cannot make the target look worse-ranked
    than it is. The displayed peer_median uses real peer values only.
    """
    peers = [s for s in snaps if s != sym]
    target = build_all_metrics(snaps[sym], closes, sym)
    peer_metrics = {p: build_all_metrics(snaps[p], closes, p) for p in peers}
    pillar_scores, pillars_out = {}, {}
    for pillar, metrics in target.items():
        pcts, detail = {}, {}
        for mname, mval in metrics.items():
            bounds = CONFIG["winsorize"].get(mname)
            real_vals, ranked_vals = [], []
            for p in peers:
                pv = peer_metrics[p][pillar].get(mname)
                if isinstance(pv, str) and pv == WORST:
                    if bounds:
                        ranked_vals.append(
                            bounds[1] if mname in LOWER_IS_BETTER
                            else bounds[0])
                    continue
                pv = winsorize(pv, bounds)
                if isinstance(pv, (int, float)):
                    real_vals.append(pv)
                    ranked_vals.append(pv)
            v = winsorize(mval, bounds)
            pcts[mname] = percentile_rank(v, ranked_vals,
                                          mname in LOWER_IS_BETTER)
            structural = isinstance(mval, str) and mval == WORST
            detail[mname] = {
                "value": None if structural else mval,
                "structural_worst": structural,
                "pct": pcts[mname],
                "peer_median": _median(real_vals),
            }
        weights = CONFIG["metric_weights"].get(pillar)
        score, used = score_pillar(pcts, weights)
        pillar_scores[pillar] = score
        pillars_out[pillar] = {
            "grade": grade(score),
            "percentile": score,
            "evidence": evidence_str(detail),
            "metrics": detail,
            "used_metrics": used,
        }
    comp, na = composite_score(pillar_scores, CONFIG["pillar_weights"])
    verdict, notes = decide_verdict(comp, pillar_scores)
    return {"pillars": pillars_out, "pillar_scores": pillar_scores,
            "composite": comp, "verdict": verdict, "notes": notes,
            "na_pillars": na}


def run(sym, refresh=False):
    """Full pipeline for one ticker. Raises ValueError if unscoreable."""
    sym = sym.upper()
    snap = fetch_snapshot(sym, refresh)
    info = snap["info"]
    if info.get("quoteType") != "EQUITY":
        raise ValueError(f"not an equity (quoteType="
                         f"{info.get('quoteType')!r}) - cannot score")
    if not info.get("industryKey"):
        raise ValueError("no industry classification - cannot build peer set")
    peers = resolve_peers(sym, info, refresh)
    snaps = {sym: snap}
    for p in peers:
        try:
            snaps[p] = fetch_snapshot(p, refresh)
        except Exception:
            pass
    closes = fetch_prices(list(snaps), refresh)
    result = score_ticker(sym, snaps, closes)
    flags = list(result.pop("notes"))
    flags += universe_flags(info)
    peer_count = len(snaps) - 1
    if peer_count < CONFIG["peers"]["min"]:
        flags.append(f"LOW CONFIDENCE: only {peer_count} peers after "
                     "filtering")
    if (info.get("industryKey") or "").startswith("reit"):
        flags.append("REIT: P/FFO unavailable in data source; valuation "
                     "uses standard metrics only")
    if result["na_pillars"]:
        flags.append("Pillars N/A (insufficient data): "
                     + ", ".join(result["na_pillars"]))
    result.update({
        "ticker": sym,
        "name": info.get("longName") or info.get("shortName") or sym,
        "date": _today(),
        "industry": info.get("industryKey"),
        "sector": info.get("sectorKey"),
        "peers": sorted(p for p in snaps if p != sym),
        "peer_count": peer_count,
        "flags": flags,
    })
    return result


# ------------------------------------------------------------------- rendering

def render_text(r):
    w = 72
    lines = ["=" * w]
    lines.append(f"QUANT SCORE: {r['ticker']} ({r['name']})  "
                 f"-  snapshot {r['date']}")
    shown = ", ".join(r["peers"][:12]) + ("..." if r["peer_count"] > 12
                                          else "")
    lines.append(f"Peer set [{r['industry']}], {r['peer_count']} peers: "
                 f"{shown}")
    lines.append("=" * w)
    lines.append(f"{'PILLAR':<15}{'GRADE':<7}{'PCTL':<6}EVIDENCE")
    for p in PILLARS:
        d = r["pillars"][p]
        pct = f"{d['percentile']:.0f}" if d["percentile"] is not None \
            else "--"
        lines.append(f"{p.title():<15}{d['grade']:<7}{pct:<6}{d['evidence']}")
    lines.append("-" * w)
    if r["composite"] is not None:
        lines.append(f"COMPOSITE: {r['composite']:.2f} / 5.00  ->  "
                     f"{r['verdict'].upper()}")
    else:
        lines.append(f"COMPOSITE: N/A  ->  {r['verdict']}")
    for f in r["flags"]:
        lines.append(f"  [!] {f}")
    return "\n".join(lines)


def render_ranked_table(results):
    lines = ["", "RANKED COMPARISON", f"{'TICKER':<8}{'COMPOSITE':<11}"
             f"{'VERDICT':<13}" + "".join(f"{p[:4].upper():<6}"
                                          for p in PILLARS)]
    ordered = sorted(results, key=lambda r: (r["composite"] is None,
                                             -(r["composite"] or 0)))
    for r in ordered:
        comp = f"{r['composite']:.2f}" if r["composite"] is not None \
            else "N/A"
        grades = "".join(f"{r['pillars'][p]['grade']:<6}" for p in PILLARS)
        lines.append(f"{r['ticker']:<8}{comp:<11}{r['verdict']:<13}{grades}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Alpha Picks-style five-pillar quant scorer")
    parser.add_argument("tickers", nargs="+", help="US stock ticker(s)")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable output")
    parser.add_argument("--refresh", action="store_true",
                        help="bypass same-day cache")
    args = parser.parse_args()
    purge_cache()
    results, errors = [], []
    for sym in args.tickers:
        try:
            results.append(run(sym, refresh=args.refresh))
        except ValueError as e:
            errors.append(f"SKIP {sym.upper()}: {e}")
        except Exception as e:
            errors.append(f"ERROR {sym.upper()}: {e}")
    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        for r in results:
            print(render_text(r))
            print()
        if len(results) > 1:
            print(render_ranked_table(results))
    for e in errors:
        print(e, file=sys.stderr)
    if not results:
        sys.exit(1)


if __name__ == "__main__":
    main()
