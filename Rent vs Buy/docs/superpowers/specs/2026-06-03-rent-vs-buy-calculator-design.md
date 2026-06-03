# Rent vs Buy Calculator — Design Spec

- **Date:** 2026-06-03
- **Status:** Approved design, ready for implementation planning
- **Owner:** David

## 1. Purpose & scope

A personal decision tool to answer: *for a specific apartment and a given holding period, am I financially better off renting and investing, or buying?* Rigor matters more than polish — the output must be trustworthy and the methodology defensible.

**In scope:** a single self-contained `index.html` that takes editable financial inputs, runs a month-by-month net-worth simulation of both paths, and shows which wins, by how much, the break-even year, an annualized growth comparison, a year-by-year delta table, and a net-worth chart.

**Non-goals (YAGNI):** no multi-scenario save/compare, no accounts/auth, no backend, no PMI / mortgage points / ARMs / extra-principal / refinancing modeling, no currency conversion or localization beyond a currency symbol, no PDF export. Several of these are noted as possible future extensions in §8.

## 2. Platform & deliverable

One self-contained file: `Rent vs Buy/index.html`.

- Vanilla HTML/CSS/JS. **No build step, no CDN, no external libraries.** Opens by double-click and works fully offline.
- Chart drawn as **inline SVG** (no charting library).
- **Dashboard layout** (approved): inputs pinned left, results live on the right; recalculates on every input change.

## 3. The financial engine (the core)

**Method:** net-worth + opportunity cost. Simulate both paths month-by-month over the horizon, marking each to market ("what is this worth if I liquidated today, after tax and transaction costs"), then aggregate to yearly snapshots.

### 3.1 Opportunity cost (the heart of the model)

Both strategies deploy the same up-front capital and are held to the **same monthly budget**:

- **Up-front capital `K` = down payment + closing costs.** Buying spends it on the home; renting invests it in the market at the expected return from day one.
- **Monthly difference invested.** Each month, `budget = max(effective buy cost, effective rent cost)`. Whichever path is cheaper invests the difference at the expected return. (Early years: owning is usually pricier, so the renter invests the gap. Later years, once a fixed mortgage is overtaken by inflating rent, the buyer may invest the gap into a side portfolio.)
- The renter's portfolio growth **is** the opportunity cost; the symmetric flip side is that the buyer's capital sits in home equity instead of the market. The comparison is exactly **money-in-a-home vs. money-in-the-market**.
- Investment gains are **after-tax** (capital-gains drag, §3.4).

### 3.2 Rate conventions (stated to avoid ambiguity)

- **Mortgage rate:** annual nominal, monthly rate = `rate / 12` (industry standard).
- **Expected investment return:** effective annual; monthly factor = `(1 + r)^(1/12) − 1`.
- **Appreciation, rent inflation, general inflation:** effective annual; monthly factor = `(1 + g)^(1/12) − 1`.
- Inflation-linked recurring costs (insurance, HOA) and rent step up **once per year** by their annual rate.

### 3.3 Monthly loop

Setup: `loan = price − downPayment`; `K = downPayment + closingCosts`; mortgage payment `M = loan · rm / (1 − (1+rm)^(−n))` where `rm = rate/12`, `n = termYears·12` (if `rm = 0`, `M = loan/n`).

For each month:

- **Home value** grows by the monthly appreciation factor.
- **Mortgage:** `interest = balance · rm`; `principal = M − interest`; `balance −= principal` (floored at 0; once paid off, `M = 0`).
- **Ownership costs:** property tax = `propertyTaxPct · homeValue / 12`; maintenance = `maintenancePct · homeValue / 12` (both on *current* value); insurance and HOA = annual amounts / 12, stepped up yearly by inflation.
- **Tax saving:** `(deductible interest + deductible property tax) · marginalRate` (toggles decide which are deductible). Reduces effective buy cost. *Simplification: applies the marginal benefit to the full deductible amount; ignores the standard-deduction threshold — consistent with the parameterized-tax choice.*
- **Effective buy cost** = `M + property tax + maintenance + insurance + HOA − tax saving`.
- **Effective rent cost** = `rent (stepped yearly) + renter's insurance`.
- **Invest the difference** into the cheaper path's portfolio; both portfolios then grow by the monthly return factor.

### 3.4 Net worth (marked to market each period)

- **Buyer** = `homeValue − loanBalance − sellingCosts − homeSaleTax + after-tax side portfolio`.
  - `sellingCosts = sellingCostsPct · homeValue` (applied in every period's mark-to-market, so break-even reflects the cost of actually realizing).
  - `homeSaleGain = (homeValue − sellingCosts) − (price + closingCosts)`; `taxableGain = max(0, homeSaleGain − homeSaleExclusion)`; `homeSaleTax = taxableGain · capitalGainsRate`.
- **Renter** = `portfolioValue − capitalGainsTax`, where tax = `max(0, portfolioValue − totalContributions) · capitalGainsRate`.
- Both sides are after-"if-liquidated" tax, so the comparison stays apples-to-apples.

### 3.5 Derived outputs

- **Break-even year:** first year where Buyer net worth ≥ Renter net worth (or "none within horizon").
- **$ ahead:** `BuyerNW(horizon) − RenterNW(horizon)` (signed; positive = buying ahead).
- **Annualized growth (CAGR):** `(NW(horizon) / K)^(1/horizonYears) − 1` for each path, measured on the common up-front capital `K`. **Annual edge** = `CAGR_buy − CAGR_rent` (in percentage points). *Caveat to surface in the UI note: monthly contributions inflate both CAGRs equally, so this is a fair relative measure, not a pure return on `K` alone.*
- **Per-year table:** for each year — Buyer NW, Renter NW, `Δ$ = Buy − Rent`, `Δ% = (Buy − Rent) / Rent`.

## 4. Inputs

All editable, with sensible defaults and a currency-symbol field (default `$`). The big drivers (price, mortgage rate, expected return, appreciation, rent) get a slider paired with the number field for live "drag and watch"; the rest are plain number inputs.

| Group | Fields (default) |
|---|---|
| Property & purchase | price (500,000) · down payment (20%, unit toggle % / $) · closing costs (3%) · appreciation (3%/yr) · selling costs (6%) |
| Mortgage | interest rate (6.5%/yr) · term (30 yr) |
| Ownership costs | property tax (1.1%/yr) · maintenance (1.0%/yr) · insurance (1,500/yr) · HOA (300/mo) |
| Renting | rent (2,400/mo) · rent inflation (3%/yr) · renter's insurance (180/yr) |
| Investing | expected return (7%/yr) · general inflation (3%/yr) |
| Taxes | marginal rate (32%) · capital-gains rate (15%) · interest deductible (on) · property-tax deductible (on) · home-sale exclusion (250,000) |
| Horizon | 10 years |

## 5. Output (approved v3 view)

Right-hand results panel, recalculated live:

1. **Verdict banner** — exact `$ ahead` and `+X%` at horizon, with the literal math shown, plus the break-even year defined (with the bracketing years).
2. **Annualized growth stats** — Buy %/yr, Rent %/yr, and the annual edge in points, with the CAGR definition noted.
3. **Net-worth chart** — two lines (Buy, Rent) with a dashed break-even marker and crossover dot.
4. **Year-by-year table** — Year · Buy · Rent · Δ$ · Δ%, break-even and horizon rows highlighted, color-coded (renting-ahead vs buying-ahead).
5. **"Where your capital is working" breakdown** (collapsible) — makes the opportunity cost explicit: investment growth on invested capital, total interest paid, equity built, taxes saved, capital-gains drag.

Definitions: Δ = Buy − Rent. Positive/blue = buying ahead; negative/green = renting ahead.

## 6. Code structure

- **Pure engine:** `computeProjection(inputs)` — DOM-free, returns the monthly/yearly series plus all derived metrics (§3.5). All math lives here.
- **UI layer:** reads inputs → calls `computeProjection` → renders verdict, stats, SVG chart, table, breakdown. No math in the UI layer.
- Single file, but the two layers are clearly separated within it so the logic is isolated and testable.

## 7. Testing & validation

Built-in self-test mode: opening `index.html?test` runs assertions and shows a pass/fail panel. Keeps everything in one file while giving a re-runnable rigor check.

Test cases (minimum):
- Mortgage payment matches a known amortization value (e.g., 400,000 @ 6.5% / 30 yr ≈ 2,528.50/mo).
- Loan fully amortizes to ~0 at the end of the term.
- **Zero-return, zero-appreciation, zero-inflation, zero-tax** sanity: results reduce to a clean cash comparison.
- **Equal-budget invariant:** every month, total outlay (cost + invested) is identical across both paths.
- **Break-even monotonicity:** the Buy−Rent delta crosses zero at most where reported; horizon `$ ahead` matches the last table row.
- CAGR consistency: `K · (1+CAGR)^H ≈ NW(horizon)` for each path.

## 8. Decisions locked & deferred

**Locked:** monthly simulation; nominal expected return with inflation via the growth inputs; capital-gains tax applied at the period's mark-to-market (not an annual drag); home-sale exclusion applied to home-sale gains; CAGR measured on common up-front capital `K`; tax-deduction simplification (no standard-deduction threshold).

**Deferred (possible later, not in v1):** "today's dollars" (inflation-adjusted) toggle; remember-inputs via `localStorage`; PMI for <20% down; mortgage points / ARM / extra principal / refinancing; multi-scenario compare; PDF/print export.

## 9. Success criteria

- Open `index.html` offline; change any input → results recalc instantly.
- Verdict shows exact `$ ahead` + break-even with definitions; growth-rate stats and per-year Δ$/Δ% table present; chart shows both lines + break-even marker; opportunity cost explicit in the breakdown.
- `index.html?test` — all self-tests pass.
- Zero external dependencies.

## 10. File structure

```
Rent vs Buy/
  index.html        # the tool (self-contained)
  README.md         # usage + assumptions and known simplifications
  docs/superpowers/specs/2026-06-03-rent-vs-buy-calculator-design.md
```
