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

### Interpreting the composite (read this)

The composite is an **ordinal rank tier** — "how this stock ranks against
its ~50-name cohort right now" — not a backtested or calibrated
probability. Pillar weights are equal and the verdict cuts are hand-set
(see Known Limitations). Do not over-read a 3.2 Hold as a considered
neutral call: a stock at the exact median of every pillar lands at
composite 3.0, and **Hold is a wide band (2.5-3.5, i.e. 37.5th-62.5th
pctl)** while Strong Sell (<1.5) is nearly unreachable. Trust the relative
ranking and the pillar grades; treat the Buy/Sell label as a tier, and
always read the flags and David-Fit/Caveats sections before acting.

## Non-Scoring Flags

These surface mechanically in `flags` (rendered `[!]`); they never change a
grade or the verdict. They exist so the interpreter can't forget to mention
the trap, and so the David-Fit overlay's hard rules are robust to LLM recall.

- **Peak-earnings / cyclical-top** (`peak_earnings_flag`): fires when the
  forward P/E ranks top-decile cheap, trailing P/E is >= 1.5x the forward
  P/E (so the cheapness is a rising-estimate artifact), AND FY revisions are
  top-decile. Addresses the system's structural blindness to cyclicality —
  e.g. MU's 8.8x forward P/E is "cheap on peak earnings," not durable value.
- **Peer-set cap mismatch** (`cap_mismatch_flag`): fires when the peer
  median market cap is >10x or <1/10x the target's — the grades are then
  drawn against a different size class (small-cap target vs mega-cap primes).
  Output also lists the 4 largest peers by cap so the cohort is auditable.
- **Extreme valuation** (`extreme_valuation_flags`): objective flags for
  trailing P/E > 100 and market cap < $1B. The David-Fit overlay maps these
  to its hard rules (HARD PASS / lottery-ticket) so they fire mechanically.

## Calibration Log

| Date | Setting | Value | Reason |
|---|---|---|---|
| 2026-06-12 | pillar weights | equal (1,1,1,1,1) | initial; no backtest data |
| 2026-06-12 | strong_buy threshold | 4.0 | spec amendment (4.5 unattainable); sanity basket confirmed selectivity (1 of 7 single-ticker basket names was Strong Buy; 2 Strong Buys across all 8 reference points incl. multi-run MU) |
| 2026-06-12 | peers.widen_below | 8 (was 10) | widening at 10 polluted peer sets (discount retailers in beverages, fintech in banks); at 8 rosters stay same-industry and every basket name keeps >= 8 peers |
| 2026-06-12 | winsorize bounds | see CONFIG | initial; no change needed in basket validation |
| 2026-06-12 | non-scoring flags added | peak_earnings / cap_mismatch / extreme_valuation | post-audit (REVIEW-2026-06-12): surface cyclicality blindness, invisible peer-set, and David hard rules mechanically. Flags only — composite math unchanged. Verified: peak-earnings fires on MU, not on CRM/RDW/AVAV; cap-mismatch fires on MU (target 102x peer median) |

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
- Pillar weights are not back-tested, and the system is structurally blind
  to cyclicality: at a cycle peak, peak earnings (cheap forward P/E), rising
  estimates, and strong momentum coincide, so the highest scores can land at
  the highest forward risk (the MU case). The `peak_earnings` flag surfaces
  the clearest instances mechanically, but the composite itself cannot see
  the cycle — read the flag and the cyclical-risk caveat.
- Not backtest-safe: peers and fundamentals are always today's roster /
  latest TTM-forward consensus (survivorship-biased, no point-in-time
  reconstruction). Scoring a past date with this code would silently use the
  current cohort. It is a current-snapshot ranker, not a backtester.
- Intraday .info values vary between first runs at different times of
  day; determinism holds within a snapshot day (cache), and the snapshot
  date is stamped in output.
- Educational/decision-support tool; not investment advice. Replicates
  the Alpha Picks METHOD, not its proprietary output.
