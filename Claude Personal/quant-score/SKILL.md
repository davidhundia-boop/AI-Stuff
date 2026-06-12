---
name: quant-score
description: Alpha Picks-style five-pillar quantitative stock scoring (Value, Growth, Profitability, Momentum, EPS Revisions) with sector-relative letter grades (A+ to F) and a composite Strong Buy/Buy/Hold/Sell/Strong Sell verdict. Use when the user runs /quant-score TICKER, asks to "quant score" a stock, wants an Alpha Picks-style rating, pillar grades, or a quantitative verdict on a US stock ticker.
compatibility: "powershell/bash, python, yfinance, pandas, numpy"
---

# Quant Score (Alpha Picks-style)

Deterministic five-pillar scorer. ALL grading happens in the Python
engine -- never adjust grades or the verdict by judgment. Your job is
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
  explicitly decline a verdict -- never invent one.
- `SKIP`/`ERROR` lines on stderr: relay the reason (e.g. ETFs and
  non-US-equities are not scoreable).
- Flags prefixed `[!]` must appear in the report's caveats section.
- Sector-relative context matters when explaining: a momentum F can mean
  "the peer group ran harder", not "the stock fell" (see methodology.md
  Validated Reference Points).

## Maintenance

Source of truth: `D:\AI Stuff\Claude Personal\quant-score\` (git).
Edit there, run tests (`python -m pytest quant-score/tests`), then copy
to this directory. Calibration changes go in CONFIG and are logged in
`references/methodology.md`.
