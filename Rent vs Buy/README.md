# Rent vs Buy Calculator

A single self-contained `index.html` — double-click to open in any browser. No install, no internet, no dependencies.

## Use

Edit the inputs on the left; results update live on the right. You get: the verdict (who's ahead and by how much at your horizon), the break-even year(s), the annualized advantage, sensitivity flip-thresholds, a net-worth-over-time chart, a year-by-year delta table, and a collapsible cost/opportunity breakdown.

## Method

Both paths' net worth is simulated month by month. Opportunity cost is central: the renter invests the down payment + closing costs and every monthly cost difference at your expected return (after capital-gains tax); the buyer's capital sits in leveraged home equity. Both paths are held to the **same monthly budget**. Net worth is marked to market each year (after selling costs and taxes), so each year reads as "outcome if you exit that year" — which is why the break-even is realistic.

## Annualized advantage

`(Buy net worth / Rent net worth)^(1/years) − 1` — read as "buying compounds your net worth ~X%/yr faster than renting" (negative = renting faster). A per-path "return" is intentionally **not** shown: housing is partly consumption, so a standalone return per path isn't well-defined.

## Taxes (parameterized — set to your situation)

Editable marginal rate and capital-gains rate; on/off toggles for mortgage-interest and property-tax deductibility; a standard-deduction baseline and optional deduction cap (the model credits only the deductible amount *above* the standard deduction, capped if set — a calculator simplification, not exact IRS SALT mechanics); and a home-sale capital-gains exclusion.

## Known simplifications & limitations

- **Down payment is entered as a percentage only** (the % / $ unit toggle from the design was deferred — enter the equivalent %).
- Tax handling is the parameterized model above — no full itemization / AMT modeling.
- No PMI (with <20% down the result is optimistic for buying), no mortgage points, no ARM / refinancing / extra principal.
- Returns and appreciation are deterministic point estimates — use the sensitivity flip-thresholds to gauge how fragile the verdict is.
- Net worth is shown in nominal dollars.

## Currency

Set the currency-symbol field (default `$`) — it's cosmetic and flows through all money displays.

## Tests

Open `index.html?test` in a browser to run the built-in self-test suite (engine math, invariants, sensitivity). It renders a pass/fail panel and sets the tab title to the summary.
