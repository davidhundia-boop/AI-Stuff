# David Fit Overlay

Applied by Claude AFTER the objective score. Never changes grades or the
verdict -- it is a separate "David Fit" section in the report.

## Hard flags

The engine now emits these two conditions mechanically as `[!]` flags
("Extreme trailing valuation: P/E > 100" and "Small cap: market cap < $1B"),
so they don't depend on remembering to re-derive them. Map them to David's
rules whenever the flag is present:

- Trailing P/E > 100 -> "HARD PASS per David's rules (trailing PE > 100)",
  regardless of verdict.
- Market cap < $1B -> "Below David's preferred cap (>$1B). Lottery-ticket
  territory: requires a >200% ROI thesis on a 3-9 month horizon."

Also map the engine's **peak-earnings / cyclical-top** flag when present:
a Strong Buy/Buy carrying it is a momentum trade with a defined exit
(revisions rollover), not a 2-5yr compounding anchor -- call that out
explicitly given David's hold horizon.

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
