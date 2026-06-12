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
  sibling industries then sector only when under 8 names; max 50;
  cached 7 days as the full industry roster (the scored ticker is
  filtered out on read, so same-industry runs share one roster).
- Winsorization: ratios clamped before ranking (bounds in CONFIG).
- Structural-missing: negative earnings/EBITDA/book -> WORST percentile
  on the affected ratio (NOT dropped). Coverage gaps -> dropped, weight
  redistributed within pillar.
- WORST peers stay in the pool: a peer with a structurally-bad ratio is
  counted at the worst end of the winsorize bounds when ranking, so a
  sector full of money-losers cannot distort the target's rank. The
  peer medians shown as evidence use real peer values only.
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
| 2026-06-12 | strong_buy threshold | 4.0 | spec amendment (4.5 unattainable); sanity basket confirmed selectivity (1 Strong Buy in 7 names) |
| 2026-06-12 | peers.widen_below | 8 (was 10) | widening at 10 polluted peer sets (discount retailers in beverages, fintech in banks); at 8 rosters stay same-industry and every basket name keeps >= 8 peers |
| 2026-06-12 | winsorize bounds | see CONFIG | initial; no change needed in basket validation |

## Validated Reference Points (2026-06-12 basket)

- SNDK 4.24 Strong Buy (A+ momentum), MU 4.26 Strong Buy, NVDA 3.36 Hold,
  KO 3.23 Hold, JPM 2.61 Hold, KHC 3.24 Hold, KRUS 2.71 Hold, O 2.60 Hold
  (circuit breaker active).
- NVDA at Hold is the canonical example of sector-relative momentum:
  NVDA's +13% 3-month return ranked 14th percentile against semiconductor
  peers whose median ran +73%. In a sector-relative system that IS the
  intended behavior, not a bug.

## Known Limitations

- Peer set is top ~50 industry names, not SA's full ~5,000-stock sector
  universe; percentiles vs larger, healthier companies are a stricter bar.
- Industry classification comes from yfinance: occasional odd cohabitants
  (e.g. quantum-computing names classified under computer-hardware) are a
  data artifact, not a widening bug.
- Pillar weights are not back-tested.
- Intraday .info values vary between first runs at different times of
  day; determinism holds within a snapshot day (cache), and the snapshot
  date is stamped in output.
- Educational/decision-support tool; not investment advice. Replicates
  the Alpha Picks METHOD, not its proprietary output.
