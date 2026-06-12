# /quant-score — Alpha Picks-Style Quantitative Stock Scoring Skill

**Date:** 2026-06-12
**Status:** Approved design, pending implementation plan
**Owner:** David

## Goal

A Claude Code skill that takes a US stock ticker and returns a deterministic, five-pillar
quantitative score modeled on Seeking Alpha's Alpha Picks quant system: letter grades
(A+ to F) for Value, Growth, Profitability, Momentum, and EPS Revisions, plus a composite
verdict (Strong Buy / Buy / Hold / Sell / Strong Sell). Invoked as `/quant-score TICKER`
(one or more tickers).

## Decisions Made During Brainstorming

| Decision | Choice |
|---|---|
| Scope | Scoring engine only — no portfolio rules, no universe screening (may come later) |
| Methodology | Sector-relative percentile ranking vs. a peer set (matches the real Alpha Picks method) |
| Personalization | Faithful replica score + separate "David fit" overlay section; the score itself stays objective |
| Validation | Sanity-check basket of ~10 well-understood tickers (no Seeking Alpha access for direct calibration) |
| Architecture | New standalone skill with a deterministic Python engine; Claude interprets, never grades |
| Skill placement | Separate from /us-stock-analysis — different intent ("score X" vs "analyze X"), keeps triggering clean, composable from /find-stock and /trade-now later |

Key sources: public descriptions of Alpha Picks plus a 2026 interview with its creator
(Steve, ex-Morgan Stanley quant). Confirmed mechanics used here: sector-relative scoring,
momentum defined as sector-relative outperformance over 6/9/12 months, 52-week-high
proximity treated as positive, value evidence quoted vs. sector median, a value "circuit
breaker" that auto-caps the verdict at Hold, Strong Buy selectivity ~8% of universe,
universe criteria of market cap > $500M and price > $10.

## Architecture

```
C:\Users\david\.claude\skills\quant-score\
├── SKILL.md                  # trigger description, workflow, report instructions
├── scripts\
│   └── quant_score.py        # entire scoring engine (deterministic, single file)
├── references\
│   ├── methodology.md        # pillar/metric definitions, grading rules
│   └── david-fit.md          # personal overlay rules (editable without touching code)
└── data\
    └── cache\                # peer lists (7-day TTL) + same-day metric snapshots
```

- Single-file Python engine, same auto-install pattern as
  `us-stock-analysis/scripts/fetch_stock_data.py` (yfinance, pandas, numpy — no API key).
- Division of labor: the script does **all** numeric work (fetching, ranking, grading,
  verdict). Claude only interprets results, applies the David-fit overlay from
  `references/david-fit.md`, writes the report, and saves it to trade-reports.
- Expected runtime: ~1–2 min cold, seconds with warm same-day cache.

## Data Flow

1. **Resolve peers.** Get the ticker's `industryKey` from `yf.Ticker(X).info`, pull
   `yf.Industry(key).top_companies`. Filters: dedupe by company name (e.g., BK/BNY
   duplicate entries), `quoteType == 'EQUITY'` only, market cap > $500M, price > $10.
   Use **all** survivors up to ~50 (the API caps top_companies at 50 rows). If fewer
   than 10 names survive, widen to **sibling industries** within the same sector first,
   then to `yf.Sector(key).top_companies` as last resort. Peer lists cached 7 days.
2. **Fetch metrics** for ticker + peers: `.info` ratios, `eps_trend`, `eps_revisions`
   per ticker; price history for **all** tickers via one batched
   `yf.download(tickers, period='1y')` call (atomic same-bar snapshot, ~10x faster than
   per-ticker history). Metric snapshots cached for the day; the snapshot date is part
   of the cache key and stamped in all output.
3. **Score** (see Methodology).
4. **Output** human-readable scorecard to stdout; `--json` emits the same machine-readable.
5. **Claude** interprets, applies overlay, writes and saves the report.

Verified empirically (yfinance 1.2.2, 2026-06-12): `eps_trend` returns a DataFrame
indexed `0q/+1q/0y/+1y` with columns `current/7daysAgo/30daysAgo/60daysAgo/90daysAgo`;
`eps_revisions` has up/down counts for 7- and 30-day windows only (no 90-day breadth);
`top_companies` returns name/rating/market weight only (no cap/price — universe filtering
requires `.info` per candidate; `market weight` can pre-sort candidates to minimize
fetches); no rate limiting at ~25 sequential `.info` calls (~13s).

## Scoring Methodology

### Pillars and Metrics

All metrics percentile-ranked (0–100) against the peer set (ticker included). Pillar
score = weighted mean of its metric percentiles. Metric weights and pillar weights are
config constants at the top of the script (default: equal within pillar, 20% per pillar).

| Pillar | Metrics | Direction |
|---|---|---|
| Value | Trailing P/E, Forward P/E, PEG (`trailingPegRatio`, frequently missing), P/S, P/B, EV/EBITDA, FCF yield | Lower better (FCF yield: higher better) |
| Growth | Revenue growth YoY, EPS growth YoY, 3-yr revenue CAGR (from annual financials), implied forward EPS growth (forwardEps vs trailingEps) | Higher better |
| Profitability | Gross / operating / net margin, ROE, ROA, FCF margin | Higher better |
| Momentum | Price return vs. peer median over 3/6/9/12 months; distance from 52-week high (**closer = better**) | Sector-relative outperformance |
| EPS Revisions | Consensus EPS estimate change over 90 days (current + next FY, from eps_trend; sign-aware deltas), up-vs-down revision breadth (7/30-day windows, weighted **below** the 90-day estimate change) | Net upward better |

### Data-Quality Rules

- **Winsorize** ratios before ranking (e.g., clamp P/E to [0, 150]) — with N≈25–50 one
  extreme peer shifts percentiles materially.
- **Structurally missing ≠ coverage missing.** Negative earnings → assign **worst
  percentile** on P/E, PEG, EV/EBITDA (the field is absent from yfinance for
  unprofitable companies, not negative). Negative FCF → worst percentile on FCF yield.
  Genuinely missing coverage (e.g., no analyst estimates) → drop metric and redistribute
  weight within the pillar, with a note. This prevents unprofitable companies from
  grading *better* because their bad ratios vanished.
- **Sign-aware estimate deltas:** an EPS forecast crossing from positive to negative is
  a downgrade; never compute naive percent change across a zero crossing.
- **Sector metric mask:** for Financials (banks/insurers), exclude EV/EBITDA, FCF yield,
  FCF margin, gross margin (yfinance returns fake `0.0` gross margins and negative OCF
  for banks). REITs: P/FFO is unavailable in yfinance — score with the standard metrics
  and attach a documented limitation note to the report.
- **Pillar N/A:** a pillar with < 2 usable metrics grades N/A and is excluded from the
  composite (remaining pillar weights renormalized), with a visible confidence note.

### Grades, Composite, Verdict

- Pillar percentile → letter (explicit bands):
  A+ ≥ 97 · A 93–97 · A− 90–93 · B+ 85–90 · B 75–85 · B− 65–75 ·
  C+ 58–65 · C 51–58 · C− 45–51 · D+ 38–45 · D 32–38 · D− 25–32 · F < 25.
- Composite = weighted average of pillar percentiles, mapped linearly to a 1.0–5.0 score
  (`1 + 4 × pct/100`).
- Verdict: **Strong Buy ≥ 4.0** *and* no pillar below C− (composite ≥ 4.0 with any
  pillar below C− demotes to Buy) · Buy 3.5–4.0 · Hold 2.5–3.5 ·
  Sell 1.5–2.5 · Strong Sell < 1.5.
  (Original 4.5 threshold was shown to be near-unattainable: it requires ~87.5th
  percentile average across five pillars while Value and Growth anti-correlate. 4.0 ≈
  75th percentile average; calibrate further against the sanity basket.)
- **Value circuit breaker:** Value grade D+ or worse caps the verdict at Hold regardless
  of composite (mirrors the real system's automatic Strong Buy/Buy → Hold demotion when
  valuation gets too expensive).
- **Universe flags:** market cap < $500M or price < $10 does not block scoring but adds
  a "below Alpha Picks universe criteria" warning to the report.

## Output

### Script (stdout)

- Scorecard table: pillar, letter grade, percentile, evidence in sector-median style
  ("P/E 25.1 vs peer median 32.0 → 21% discount").
- Composite score (1.0–5.0) + verdict; circuit-breaker / universe / confidence flags.
- Peer set used (names + count) and data snapshot date.
- `--json` flag: same content as machine-readable JSON (future /find-stock and
  /trade-now composability).
- Multiple tickers in one invocation → individual scorecards + ranked comparison table.

### Claude Report (saved to trade-reports)

Per existing conventions in `D:/AI Stuff/trade-reports/`:

- `reports/{TICKER}/YYYY-MM-DD-quant-score.md` with YAML header (ticker, date, composite,
  verdict, pillar grades).
- Body: scorecard, evidence highlights, **David-fit overlay** (from
  `references/david-fit.md`: hard-pass flag if trailing PE > 100; warning if market cap
  < $1B; growth-over-value orientation fit; 2–5yr hold / 30% CAGR target context),
  caveats and data-quality notes.
- Update `index.md`; add to `watchlist.md` with revisit triggers when verdict is
  Hold-or-below but fundamentals warrant monitoring.

## Error Handling

- Invalid ticker or non-equity (`quoteType != 'EQUITY'`, e.g., SPY) → clean rejection
  with explanation.
- ≥ 2 pillars N/A → report grades but **decline to issue a verdict** ("insufficient
  data"); never fabricate a composite from too little signal.
- Peer pool < 8 names after filtering → low-confidence banner on all output.
- IPOs < 1 year: missing momentum windows dropped with note (batch download returns
  NaN cleanly).
- Network errors → retry with exponential backoff; same-day cache makes re-runs cheap.
- Cache hygiene: purge entries older than 7 days / cap directory size.

## Testing & Validation

Sanity basket (~10 tickers), all four checks must pass before the skill is considered done:

1. **Face validity:** a momentum grower (NVDA-type) grades high on Growth/Momentum; KO
   grades stable-defensive; a deteriorating name (e.g., WBA) lands Sell-ish; SNDK
   partially cross-checks the public "straight-A report card" claim from the interview.
2. **Sector mask:** JPM produces sane grades (no fake-zero gross margin poisoning).
3. **Selectivity:** the basket must not come back mostly Strong Buys; Strong Buy should
   feel rare (real system: ~8% of universe).
4. **Determinism:** same-day re-run → byte-identical scores (snapshot cache).

Calibration loop: tune pillar weights, verdict thresholds, and winsorization bounds
(all config constants) until the basket passes; document final values in
`references/methodology.md`.

## Known Limitations (Documented, Accepted)

- Peer set is the industry's top ~50 names, not SA's full ~5,000-stock sector universe —
  percentiles vs. larger, healthier companies are a slightly *stricter* bar. The report
  always names the peer set.
- Pillar/metric weights are not back-tested (SA weights by predictiveness; we start
  equal and tune by hand).
- REITs lack FFO-based valuation; financials run on a reduced metric set.
- yfinance `.info` intraday values vary between first runs at different times of day;
  determinism is guaranteed within a snapshot day via cache, and the snapshot date is
  always stamped in output.
- Educational/decision-support tool, not investment advice; scores echo Alpha Picks'
  *method*, not its actual proprietary output.

## Out of Scope (Explicit)

- Portfolio management (sell alerts, 180-day Hold rule, position weights).
- Universe-wide screening for monthly picks.
- Backtesting framework.
- Non-US listings.
