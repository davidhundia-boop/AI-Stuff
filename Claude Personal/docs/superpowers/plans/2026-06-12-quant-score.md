# /quant-score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `/quant-score` Claude Code skill — a deterministic Alpha Picks-style five-pillar stock scorer (Value, Growth, Profitability, Momentum, EPS Revisions) with sector-relative letter grades and a Strong Buy..Strong Sell verdict.

**Architecture:** Single-file Python engine (`quant_score.py`) does all numeric work: peer resolution via yfinance Industry/Sector APIs, cached daily snapshots, percentile ranking vs. peers, grading, composite verdict with circuit-breaker rules. Pure scoring functions are unit-tested with pytest (no network); data-layer functions are verified by integration commands. The skill is developed under git in `D:\AI Stuff\Claude Personal\quant-score\` and installed by copying to `C:\Users\david\.claude\skills\quant-score\` (not a git repo).

**Tech Stack:** Python 3.14, yfinance 1.2.2, pandas, numpy, pytest 9.0.2. Windows/PowerShell. No API keys.

**Spec:** `docs/superpowers/specs/2026-06-12-quant-score-design.md` (approved 2026-06-12).

**Working directory for all commands:** `D:\AI Stuff\Claude Personal` (repo root is `D:\AI Stuff`; commit with relative paths).

**Hard rules for the implementer:**
- ALL script output must be ASCII-only (no arrows, no warning glyphs) — David requires ASCII-safe output and Windows consoles mangle Unicode.
- The script never makes a judgment call; every grade and verdict comes from CONFIG-driven math.
- Run tests with: `python -m pytest quant-score/tests -v`

---

## File Structure

```
D:\AI Stuff\Claude Personal\quant-score\        # development home (git source of truth)
├── SKILL.md                                    # skill manifest + Claude workflow
├── scripts\
│   └── quant_score.py                          # entire engine (~450 lines)
├── references\
│   ├── methodology.md                          # pillar/metric/band rules + calibration log
│   └── david-fit.md                            # personal overlay rules (Claude-applied)
└── tests\
    ├── test_scoring.py                         # pure math: ranking, grading, verdict
    └── test_metrics.py                         # metric extraction from fixture dicts/frames

C:\Users\david\.claude\skills\quant-score\      # installed copy (Task 14; no tests)
└── data\cache\                                 # runtime cache (created on install)
```

`quant_score.py` internal layout (top to bottom): docstring/usage → `ensure_deps()` → imports → constants (`WORST`, `CONFIG`, `PILLARS`, `LOWER_IS_BETTER`, `SECTOR_MASKS`, `METRIC_LABELS`) → pure scoring functions → metric extraction → data layer (cache, fetch, peers) → orchestration (`score_ticker`, `run`) → rendering → `main()`.

---

### Task 1: Scaffold + script skeleton (constants, config, deps)

**Files:**
- Create: `quant-score/scripts/quant_score.py`
- Create: `quant-score/tests/test_scoring.py`
- Create: `quant-score/tests/test_metrics.py`

- [ ] **Step 1: Create directories and .gitignore**

```powershell
New-Item -ItemType Directory -Force "quant-score\scripts", "quant-score\references", "quant-score\tests" | Out-Null
Set-Content -Path "quant-score\.gitignore" -Value "data/`n__pycache__/`n*.pyc" -Encoding utf8
```

(The engine writes runtime cache files under `quant-score\data\` when run
from the repo during Tasks 7-11; they must never be committed.)

- [ ] **Step 2: Write the script skeleton**

Create `quant-score/scripts/quant_score.py`:

```python
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
```

- [ ] **Step 3: Write the import smoke test**

Create `quant-score/tests/test_scoring.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import quant_score as qs  # noqa: E402


def test_module_imports():
    assert qs.WORST == "WORST"
    assert set(qs.PILLARS) == {"value", "growth", "profitability",
                               "momentum", "revisions"}
    assert qs.CONFIG["verdict"]["strong_buy"] == 4.0
```

Create `quant-score/tests/test_metrics.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import quant_score as qs  # noqa: E402


def test_sector_mask_exists_for_financials():
    assert "gross_margin" in qs.SECTOR_MASKS["financial-services"]
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest quant-score/tests -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```powershell
git add quant-score
git commit -m "feat(quant-score): scaffold engine skeleton with config, sentinels, gitignore"
```

---

### Task 2: Ranking primitives — winsorize, percentile_rank, grade

**Files:**
- Modify: `quant-score/scripts/quant_score.py` (append after METRIC_LABELS)
- Test: `quant-score/tests/test_scoring.py`

- [ ] **Step 1: Write failing tests** (append to `test_scoring.py`)

```python
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
    assert qs.grade(90) == "A-"
    assert qs.grade(85) == "B+"
    assert qs.grade(75) == "B"
    assert qs.grade(65) == "B-"
    assert qs.grade(45) == "C-"
    assert qs.grade(44.9) == "D+"
    assert qs.grade(24.9) == "F"
    assert qs.grade(0) == "F"
    assert qs.grade(None) == "N/A"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest quant-score/tests/test_scoring.py -v`
Expected: FAIL — `AttributeError: module 'quant_score' has no attribute 'winsorize'`

- [ ] **Step 3: Implement** (append to `quant_score.py`)

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest quant-score/tests/test_scoring.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add quant-score
git commit -m "feat(quant-score): winsorize, midrank percentile ranking, grade bands"
```

---

### Task 3: Sign-aware estimate delta

**Files:**
- Modify: `quant-score/scripts/quant_score.py`
- Test: `quant-score/tests/test_scoring.py`

- [ ] **Step 1: Write failing tests** (append to `test_scoring.py`)

```python
def test_estimate_delta_normal():
    assert qs.estimate_delta(1.2, 1.0) == 0.2


def test_estimate_delta_zero_crossing_is_sign_aware():
    # Forecast flipped from profit to loss: must be NEGATIVE.
    # Naive (new-old)/old with old>0 works, but old<0 flips sign; abs() fixes.
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest quant-score/tests/test_scoring.py -v`
Expected: FAIL — no attribute `estimate_delta`.

- [ ] **Step 3: Implement** (append to `quant_score.py`)

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest quant-score/tests/test_scoring.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add quant-score
git commit -m "feat(quant-score): sign-aware EPS estimate delta with clamping"
```

---

### Task 4: Pillar score, composite, verdict (circuit breaker + demotion)

**Files:**
- Modify: `quant-score/scripts/quant_score.py`
- Test: `quant-score/tests/test_scoring.py`

- [ ] **Step 1: Write failing tests** (append to `test_scoring.py`)

```python
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
    assert comp == 1 + 4 * 0.80  # 4.2
    assert na == []


def test_composite_renormalizes_one_na():
    scores = {"value": 60, "growth": 60, "profitability": 60,
              "momentum": 60, "revisions": None}
    comp, na = qs.composite_score(scores, qs.CONFIG["pillar_weights"])
    assert comp == 1 + 4 * 0.60
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


def test_verdict_none_composite():
    v, notes = qs.decide_verdict(None, {p: None for p in qs.PILLARS})
    assert v == "NO VERDICT"
    assert any("insufficient" in n.lower() for n in notes)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest quant-score/tests/test_scoring.py -v`
Expected: FAIL — no attribute `score_pillar`.

- [ ] **Step 3: Implement** (append to `quant_score.py`)

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest quant-score/tests/test_scoring.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add quant-score
git commit -m "feat(quant-score): pillar scoring, composite, verdict with circuit breaker"
```

---

### Task 5: Metric extraction — value, growth, profitability (+ sector mask)

**Files:**
- Modify: `quant-score/scripts/quant_score.py`
- Test: `quant-score/tests/test_metrics.py`

- [ ] **Step 1: Write failing tests** (append to `test_metrics.py`)

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest quant-score/tests/test_metrics.py -v`
Expected: FAIL — no attribute `value_metrics`.

- [ ] **Step 3: Implement** (append to `quant_score.py`)

```python
# ---------------------------------------------------------- metric extraction

def _num(x):
    """Return x as float if it's a usable number, else None."""
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
```

Also append a first version of `build_all_metrics` (momentum/revisions builders arrive in Task 6 — reference them now; the Task 5 test only exercises value/growth/profitability via the BANK fixture, but define the stubs so the module stays importable):

```python
def momentum_metrics(closes, sym):
    """Implemented in full in Task 6; see there. Returns all-None until then."""
    return {**{k: None for k in CONFIG["momentum_windows"]},
            "dist_52wk_high": None}


def revisions_metrics(eps_trend, eps_revisions):
    """Implemented in full in Task 6; see there."""
    return {"delta_fy0": None, "delta_fy1": None, "breadth": None}


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
```

NOTE: the two stub bodies above are replaced wholesale in Task 6 — that is the plan, not an oversight.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest quant-score/tests -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add quant-score
git commit -m "feat(quant-score): value/growth/profitability extraction with structural-missing rules and sector mask"
```

---

### Task 6: Momentum and EPS-revisions metrics

**Files:**
- Modify: `quant-score/scripts/quant_score.py` (replace the two Task 5 stubs)
- Test: `quant-score/tests/test_metrics.py`

- [ ] **Step 1: Write failing tests** (append to `test_metrics.py`)

```python
import pandas as pd
import numpy as np


def _closes(days=300):
    """Synthetic close prices: WIN doubles linearly, FLAT stays at 100."""
    idx = pd.bdate_range(end="2026-06-12", periods=days)
    return pd.DataFrame({
        "WIN": np.linspace(100, 200, days),
        "FLAT": np.full(days, 100.0),
    }, index=idx)


def test_momentum_winner_beats_flat():
    closes = _closes()
    win = qs.momentum_metrics(closes, "WIN")
    flat = qs.momentum_metrics(closes, "FLAT")
    assert win["ret_6m"] > flat["ret_6m"]
    assert win["dist_52wk_high"] == 0.0      # at its high = best
    assert flat["ret_3m"] == 0.0


def test_momentum_short_history_drops_long_windows():
    closes = _closes(days=80)                # ~4 months of data
    m = qs.momentum_metrics(closes, "WIN")
    assert m["ret_3m"] is not None
    assert m["ret_12m"] is None              # IPO <1y: window dropped
    assert m["dist_52wk_high"] is not None


def test_momentum_unknown_symbol():
    m = qs.momentum_metrics(_closes(), "NOPE")
    assert all(v is None for v in m.values())
    m2 = qs.momentum_metrics(None, "WIN")
    assert all(v is None for v in m2.values())


def test_revisions_metrics():
    eps_trend = {
        "0y": {"current": 1.10, "90daysAgo": 1.00},
        "+1y": {"current": 1.50, "90daysAgo": 1.60},
    }
    eps_revisions = {  # yfinance mixes capitalization: downLast7Days
        "0y": {"upLast7days": 2, "upLast30days": 4,
               "downLast30days": 1, "downLast7Days": 1},
    }
    m = qs.revisions_metrics(eps_trend, eps_revisions)
    assert abs(m["delta_fy0"] - 0.10) < 1e-9
    assert m["delta_fy1"] < 0
    assert abs(m["breadth"] - (6 - 2) / 8) < 1e-9


def test_revisions_metrics_missing_data():
    m = qs.revisions_metrics(None, None)
    assert m == {"delta_fy0": None, "delta_fy1": None, "breadth": None}
    m2 = qs.revisions_metrics({"0y": {}}, {"0y": {}})
    assert m2["delta_fy0"] is None
    assert m2["breadth"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest quant-score/tests/test_metrics.py -v`
Expected: momentum/revisions tests FAIL (stubs return all-None; `test_momentum_winner_beats_flat` raises on None comparison or asserts False).

- [ ] **Step 3: Replace the two stub functions in `quant_score.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest quant-score/tests -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add quant-score
git commit -m "feat(quant-score): momentum and EPS-revisions metric builders"
```

---

### Task 7: Data layer — cache, snapshots, batched prices

**Files:**
- Modify: `quant-score/scripts/quant_score.py`

No unit TDD here (network code); each step ends with a live verification command.

- [ ] **Step 1: Implement cache + retry helpers** (append to `quant_score.py`)

```python
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
```

- [ ] **Step 2: Implement fetchers** (append)

```python
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
```

- [ ] **Step 3: Verify live**

```powershell
python -c "import sys; sys.path.insert(0, 'quant-score/scripts'); import quant_score as qs; s = qs.fetch_snapshot('KO'); print('industryKey:', s['info'].get('industryKey')); print('rev_series:', s['rev_series']); print('eps_trend 0y:', (s['eps_trend'] or {}).get('0y')); c = qs.fetch_prices(['KO','PEP']); print('prices shape:', c.shape)"
```

Expected: prints a real industryKey (e.g. `beverages-non-alcoholic`), a 3-4 element revenue series, an eps_trend dict with `current`/`90daysAgo` keys, and a prices shape around (500, 2). Second run of the same command returns instantly (cache hit).

- [ ] **Step 4: Confirm tests still pass, then commit**

Run: `python -m pytest quant-score/tests -v`
Expected: all pass.

```powershell
git add quant-score
git commit -m "feat(quant-score): cached data layer - snapshots, batched prices, retry, purge"
```

---

### Task 8: Peer resolution (dedupe, universe filter, sibling-industry widening)

**Files:**
- Modify: `quant-score/scripts/quant_score.py`
- Test: `quant-score/tests/test_scoring.py` (only `_norm_name` is pure)

- [ ] **Step 1: Write failing test** (append to `test_scoring.py`)

```python
def test_norm_name_dedupes_corporate_suffixes():
    assert qs._norm_name("The Bank of New York Mellon Corporation") == \
        qs._norm_name("Bank of New York Mellon Corp")
    assert qs._norm_name("Apple Inc.") == qs._norm_name("Apple Inc")
    assert qs._norm_name(None) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest quant-score/tests/test_scoring.py::test_norm_name_dedupes_corporate_suffixes -v`
Expected: FAIL — no attribute `_norm_name`.

- [ ] **Step 3: Implement** (append to `quant_score.py`)

```python
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
    industries then sector if thin. Cached 7 days per industry."""
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
    pool = _filter_universe(candidates(yf.Industry(ik)), sym,
                            seen_names, taken, refresh)
    if len(pool) < CONFIG["peers"]["widen_below"] and sk:
        sec = yf.Sector(sk)
        try:  # sibling industries first (closer comps than whole sector)
            for sib in [str(i) for i in sec.industries.index if str(i) != ik]:
                pool += _filter_universe(candidates(yf.Industry(sib)), sym,
                                         seen_names, taken, refresh)
                if len(pool) >= CONFIG["peers"]["widen_below"]:
                    break
        except Exception:
            pass
        if len(pool) < CONFIG["peers"]["min"]:
            pool += _filter_universe(candidates(sec), sym,
                                     seen_names, taken, refresh)
    pool = pool[:CONFIG["peers"]["max"]]
    save_cache(cache_name, pool)
    return [p for p in pool if p != sym.upper()]
```

- [ ] **Step 4: Run unit test, then verify live**

Run: `python -m pytest quant-score/tests -v`
Expected: all pass.

```powershell
python -c "import sys; sys.path.insert(0, 'quant-score/scripts'); import quant_score as qs; info = qs.fetch_info('SNDK'); peers = qs.resolve_peers('SNDK', info); print(len(peers), 'peers:', peers)"
```

Expected: roughly 10-25 peer symbols from computer-hardware (e.g. WDC, STX, ANET...), no SNDK in the list, no obvious duplicate companies. Takes ~30-60s cold (it fetches `.info` per candidate), instant on re-run.

- [ ] **Step 5: Commit**

```powershell
git add quant-score
git commit -m "feat(quant-score): peer resolution with dedupe, universe filter, sibling-industry widening"
```

---

### Task 9: Scoring orchestration — score_ticker, evidence, flags, run

**Files:**
- Modify: `quant-score/scripts/quant_score.py`
- Test: `quant-score/tests/test_metrics.py`

- [ ] **Step 1: Write failing tests** (append to `test_metrics.py`)

```python
def test_universe_flags():
    flags = qs.universe_flags({"marketCap": 300e6, "currentPrice": 5.0})
    assert len(flags) == 2
    assert qs.universe_flags({"marketCap": 2e9, "currentPrice": 50.0}) == []


def test_evidence_str_ratio_vs_median():
    detail = {"trailing_pe": {"value": 25.0, "structural_worst": False,
                              "pct": 80.0, "peer_median": 32.0}}
    s = qs.evidence_str(detail)
    assert "P/E 25.0 vs median 32.0" in s
    assert "-22%" in s          # (25-32)/32 = -21.9%


def test_evidence_str_percent_metric():
    detail = {"rev_growth": {"value": 0.30, "structural_worst": False,
                             "pct": 90.0, "peer_median": 0.10}}
    s = qs.evidence_str(detail)
    assert "Rev growth 30.0% vs median 10.0%" in s


def test_evidence_str_structural_worst():
    detail = {"trailing_pe": {"value": None, "structural_worst": True,
                              "pct": 0.0, "peer_median": 30.0}}
    assert "negative (worst)" in qs.evidence_str(detail)


def test_evidence_str_empty():
    assert qs.evidence_str({}) == "insufficient data"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest quant-score/tests/test_metrics.py -v`
Expected: FAIL — no attribute `universe_flags`.

- [ ] **Step 3: Implement** (append to `quant_score.py`)

```python
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
    """Score sym against every other symbol in snaps. Pure given inputs."""
    peers = [s for s in snaps if s != sym]
    target = build_all_metrics(snaps[sym], closes, sym)
    peer_metrics = {p: build_all_metrics(snaps[p], closes, p) for p in peers}
    pillar_scores, pillars_out = {}, {}
    for pillar, metrics in target.items():
        pcts, detail = {}, {}
        for mname, mval in metrics.items():
            bounds = CONFIG["winsorize"].get(mname)
            peer_vals = [winsorize(peer_metrics[p][pillar].get(mname), bounds)
                         for p in peers]
            peer_vals = [v for v in peer_vals if isinstance(v, (int, float))]
            v = winsorize(mval, bounds)
            pcts[mname] = percentile_rank(v, peer_vals,
                                          mname in LOWER_IS_BETTER)
            detail[mname] = {
                "value": None if mval == WORST else mval,
                "structural_worst": mval == WORST,
                "pct": pcts[mname],
                "peer_median": _median(peer_vals),
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest quant-score/tests -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add quant-score
git commit -m "feat(quant-score): scoring orchestration with evidence strings and confidence flags"
```

---

### Task 10: Rendering + CLI

**Files:**
- Modify: `quant-score/scripts/quant_score.py`

- [ ] **Step 1: Implement rendering and main** (append to `quant_score.py`)

```python
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
```

- [ ] **Step 2: Verify live — single ticker**

Run: `python quant-score/scripts/quant_score.py KO`
Expected: a scorecard with five pillar rows, letter grades, percentiles, evidence strings with peer medians, a composite line, peer set named. ASCII-only output. Cold run may take 1-2 min (peer .info fetches); re-run is seconds.

- [ ] **Step 3: Verify live — JSON and rejection**

Run: `python quant-score/scripts/quant_score.py KO --json`
Expected: valid JSON array, one object with keys ticker/pillars/composite/verdict/flags/peers/date.

Run: `python quant-score/scripts/quant_score.py SPY`
Expected: exit code 1, stderr `SKIP SPY: not an equity (quoteType='ETF') - cannot score`.

- [ ] **Step 4: Run full test suite, commit**

Run: `python -m pytest quant-score/tests -v`
Expected: all pass.

```powershell
git add quant-score
git commit -m "feat(quant-score): scorecard rendering, ranked comparison, CLI"
```

---

### Task 11: Sanity-basket validation + calibration

**Files:**
- Modify (only if calibration requires): `quant-score/scripts/quant_score.py` (CONFIG values only)

The four spec checks. Run each command and record grades/verdicts.

- [ ] **Step 1: Run the basket**

```powershell
python quant-score/scripts/quant_score.py NVDA
python quant-score/scripts/quant_score.py KO
python quant-score/scripts/quant_score.py JPM
python quant-score/scripts/quant_score.py KHC
python quant-score/scripts/quant_score.py SNDK
python quant-score/scripts/quant_score.py KRUS
python quant-score/scripts/quant_score.py O
python quant-score/scripts/quant_score.py NVDA SNDK MU
```

- [ ] **Step 2: Check face validity**

- NVDA: Growth + Profitability grades in the A/B range; composite >= Buy territory plausible.
- KO: middling composite (Hold-ish); no extreme grades.
- KHC (chronic underperformer): weak Growth/Momentum grades; composite Hold or below.
- SNDK: strong grades overall (the Feb-2026 "straight A" claim may have decayed — directional strength is the bar, not literal straight As).
- KRUS: Value pillar shows "negative (worst)" evidence for P/E-type metrics (structural-missing rule visibly working).

- [ ] **Step 3: Check sector mask, REIT note, ETF rejection**

- JPM: gross margin must NOT appear in profitability evidence; grades sane (no pillar driven by a fake 0.0).
- O: output carries the REIT flag; run completes without error.
- SPY (from Task 10): rejected cleanly.

- [ ] **Step 4: Check selectivity**

Across the 7 scored names, at most 2 may be Strong Buy. If more: raise `CONFIG["verdict"]["strong_buy"]` by 0.1 and re-run (cache makes this fast). If NOTHING in the basket reaches Buy and NVDA-types sit at Hold: lower `strong_buy` to 3.9 or revisit `strong_buy_pillar_floor`. Record any change.

- [ ] **Step 5: Check determinism**

```powershell
python quant-score/scripts/quant_score.py KO --json | Out-File -Encoding utf8 t1.json
python quant-score/scripts/quant_score.py KO --json | Out-File -Encoding utf8 t2.json
git diff --no-index t1.json t2.json
Remove-Item t1.json, t2.json
```

Expected: `git diff` prints nothing (byte-identical).

- [ ] **Step 6: Commit calibration (if any CONFIG changed)**

```powershell
git add quant-score
git commit -m "chore(quant-score): calibrate verdict thresholds against sanity basket"
```

---

### Task 12: Reference docs — methodology.md and david-fit.md

**Files:**
- Create: `quant-score/references/methodology.md`
- Create: `quant-score/references/david-fit.md`

- [ ] **Step 1: Write methodology.md**

Create `quant-score/references/methodology.md` (update the calibration table with the FINAL values from Task 11 if they changed):

```markdown
# Quant Score Methodology

Replica of the Alpha Picks / Seeking Alpha quant approach: five pillars,
each percentile-ranked against an industry peer set, mapped to letter
grades and a composite verdict. All math lives in scripts/quant_score.py
(CONFIG block); this file documents the rules for interpretation.

## Pillars and Metrics

| Pillar | Metrics | Direction |
|---|---|---|
| Value | Trailing P/E, Forward P/E, PEG, P/S, P/B, EV/EBITDA, FCF yield | Lower better (FCF yield: higher) |
| Growth | Rev growth YoY, EPS growth YoY, 3y rev CAGR, fwd EPS growth | Higher better |
| Profitability | Gross/op/net margin, ROE, ROA, FCF margin | Higher better |
| Momentum | Returns over 3/6/9/12m ranked vs peers; distance from 52wk high (closer = BETTER) | Sector-relative |
| EPS Revisions | 90-day consensus estimate change (FY0 + FY1, weight 2x), up/down revision breadth 7+30d (weight 1x) | Net upward better |

## Rules

- Peer set: industry top companies (yfinance), universe-filtered
  (cap > $500M, price > $10, EQUITY only, name-deduped), widened to
  sibling industries then sector if under 10 names; max 50; cached 7 days.
- Winsorization: ratios clamped before ranking (bounds in CONFIG).
- Structural-missing: negative earnings/EBITDA/book -> WORST percentile
  on the affected ratio (NOT dropped). Coverage gaps -> dropped, weight
  redistributed within pillar.
- Sector mask: Financials exclude EV/EBITDA, FCF yield/margin, gross
  margin. REITs: P/FFO unavailable -> flagged limitation.
- Pillar with < 2 usable metrics -> N/A, excluded from composite.
  >= 2 N/A pillars -> NO VERDICT.

## Grades and Verdict

- Percentile -> letter: A+ >=97, A 93-97, A- 90-93, B+ 85-90, B 75-85,
  B- 65-75, C+ 58-65, C 51-58, C- 45-51, D+ 38-45, D 32-38, D- 25-32, F <25.
- Composite = weighted mean of pillar percentiles -> 1 + 4*pct/100 (1.0-5.0).
- Verdict: Strong Buy >= 4.0 AND no pillar below C- (else demoted to Buy);
  Buy >= 3.5; Hold >= 2.5; Sell >= 1.5; else Strong Sell.
- Value circuit breaker: Value percentile < 45 (D+ or worse) caps the
  verdict at Hold.
- Universe violations warn but do not block scoring.

## Calibration Log

| Date | Setting | Value | Reason |
|---|---|---|---|
| 2026-06-12 | pillar weights | equal (1,1,1,1,1) | initial; no backtest data |
| 2026-06-12 | strong_buy threshold | 4.0 | spec amendment (4.5 unattainable) |
| 2026-06-12 | winsorize bounds | see CONFIG | initial |

## Known Limitations

- Peer set is top ~50 industry names, not SA's full ~5,000-stock sector
  universe; percentiles vs larger, healthier companies are a stricter bar.
- Pillar weights are not back-tested.
- Intraday .info values vary between first runs at different times of
  day; determinism holds within a snapshot day (cache), and the snapshot
  date is stamped in output.
- Educational/decision-support tool; not investment advice. Replicates
  the Alpha Picks METHOD, not its proprietary output.
```

- [ ] **Step 2: Write david-fit.md**

Create `quant-score/references/david-fit.md`:

```markdown
# David Fit Overlay

Applied by Claude AFTER the objective score. Never changes grades or the
verdict — it is a separate "David Fit" section in the report.

## Hard flags

- Trailing P/E > 100 -> "HARD PASS per David's rules (trailing PE > 100)",
  regardless of verdict.
- Market cap < $1B -> "Below David's preferred cap (>$1B). Lottery-ticket
  territory: requires a >200% ROI thesis on a 3-9 month horizon."

## Fit signals (comment, do not flag)

- Growth-over-value orientation: Growth >= B+ with Value <= C fits
  David's style better than the reverse combination.
- Horizon: David holds stocks 2-5 years targeting ~30% CAGR. Note whether
  the Growth pillar supports a multi-year compounding thesis.
- Decision weights: David weighs ~70% fundamentals / ~30% technicals.
  Value+Growth+Profitability+Revisions map to his fundamental side;
  Momentum maps to his technical side.
- Philosophy: "If there's any doubt, there's no doubt." If 2+ pillars are
  C or worse, say so plainly and lean Pass.

## Sizing context (mention only when relevant)

- Typical stock position ~$3k on IBKR margin (~10-12% annual interest);
  conviction must clear the margin hurdle.
```

- [ ] **Step 3: Commit**

```powershell
git add quant-score
git commit -m "docs(quant-score): methodology reference and David-fit overlay rules"
```

---

### Task 13: SKILL.md

**Files:**
- Create: `quant-score/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: quant-score
description: Alpha Picks-style five-pillar quantitative stock scoring (Value, Growth, Profitability, Momentum, EPS Revisions) with sector-relative letter grades (A+ to F) and a composite Strong Buy/Buy/Hold/Sell/Strong Sell verdict. Use when the user runs /quant-score TICKER, asks to "quant score" a stock, wants an Alpha Picks-style rating, pillar grades, or a quantitative verdict on a US stock ticker.
compatibility: "powershell/bash, python, yfinance, pandas, numpy"
---

# Quant Score (Alpha Picks-style)

Deterministic five-pillar scorer. ALL grading happens in the Python
engine — never adjust grades or the verdict by judgment. Your job is
interpretation, the David-fit overlay, and the saved report.

## Workflow

1. **Run the engine** (1-2 min cold, seconds cached):
   `python scripts/quant_score.py TICKER [TICKER2 ...] [--json] [--refresh]`
   (paths relative to this SKILL.md)
2. **Interpret**: read the scorecard. For rule details read
   `references/methodology.md`.
3. **Apply the overlay**: read `references/david-fit.md`, write the
   "David Fit" section (hard flags first).
4. **Save to trade-reports** (`D:/AI Stuff/trade-reports/`):
   - Check `reports/{TICKER}/` for prior analyses; reference what changed.
   - Write `reports/{TICKER}/YYYY-MM-DD-quant-score.md` with a YAML
     header: ticker, date, composite, verdict, pillar grades.
   - Update `index.md`. If verdict is Hold-or-below but worth monitoring,
     add a `watchlist.md` entry with a concrete revisit trigger.
5. **Present**: scorecard table, evidence highlights, David Fit,
   flags/caveats. Always state the snapshot date and peer set. This is
   decision support, not investment advice.

## Output handling

- `NO VERDICT` (2+ pillars N/A): present the grades that exist and
  explicitly decline a verdict — never invent one.
- `SKIP`/`ERROR` lines on stderr: relay the reason (e.g. ETFs and
  non-US-equities are not scoreable).
- Flags prefixed `[!]` must appear in the report's caveats section.

## Maintenance

Source of truth: `D:\AI Stuff\Claude Personal\quant-score\` (git).
Edit there, run tests (`python -m pytest quant-score/tests`), then copy
to this directory. Calibration changes go in CONFIG and are logged in
`references/methodology.md`.
```

- [ ] **Step 2: Commit**

```powershell
git add quant-score
git commit -m "feat(quant-score): SKILL.md manifest and Claude workflow"
```

---

### Task 14: Install to skills directory + final verification

**Files:**
- Create: `C:\Users\david\.claude\skills\quant-score\` (copy of SKILL.md, scripts\, references\)

- [ ] **Step 1: Install**

```powershell
$dst = "C:\Users\david\.claude\skills\quant-score"
New-Item -ItemType Directory -Force "$dst\data\cache" | Out-Null
Copy-Item "quant-score\SKILL.md" $dst -Force
Copy-Item "quant-score\scripts" $dst -Recurse -Force
Copy-Item "quant-score\references" $dst -Recurse -Force
Get-ChildItem $dst -Recurse | Select-Object FullName
```

Expected: SKILL.md, scripts\quant_score.py, references\methodology.md, references\david-fit.md, data\cache\ all present.

- [ ] **Step 2: Smoke-test from the installed location**

```powershell
python "C:\Users\david\.claude\skills\quant-score\scripts\quant_score.py" KO
```

Expected: full scorecard (uses its own data\cache next to the installed script — cold run, 1-2 min).

- [ ] **Step 3: Final test suite + commit**

Run: `python -m pytest quant-score/tests -v`
Expected: all pass.

```powershell
git add quant-score
git commit -m "feat(quant-score): install skill to user skills directory"
```

(If nothing changed in the repo since Task 13's commit, skip the commit — the install itself lives outside git.)

---

## Spec Coverage Map

| Spec requirement | Task |
|---|---|
| Five pillars, sector-relative percentiles | 2, 5, 6, 9 |
| Letter bands (explicit) | 2 |
| Composite 1-5, Strong Buy >= 4.0 + pillar floor + demotion | 4 |
| Value circuit breaker | 4 |
| Structural-missing vs coverage-missing | 5 |
| Sign-aware EPS deltas | 3 |
| Sector mask (Financials), REIT note | 5, 9 |
| Peer resolution: dedupe, EQUITY gate, sibling widening, max 50, 7-day cache | 8 |
| Winsorization | 2, 9 |
| Batched price download, snapshot-day determinism | 7, 11 |
| Universe flags (warn, not block) | 9 |
| NO VERDICT on >= 2 N/A pillars | 4, 9 |
| Low-peer-count banner | 9 |
| IPO < 1y momentum handling | 6 |
| ETF/non-equity rejection | 9, 10 |
| Retry/backoff, cache purge | 7 |
| Scorecard + JSON + multi-ticker ranked table | 10 |
| Sanity basket (4 checks) + calibration | 11 |
| methodology.md + david-fit.md | 12 |
| SKILL.md with trade-reports integration | 13 |
| Install to skills dir | 14 |
```
