# Rent vs Buy Calculator — Design Spec

- **Date:** 2026-06-03
- **Status:** Approved design, ready for implementation planning
- **Owner:** David
- **Rev 2:** Folded in devil's-advocate fixes — annualized **net-worth ratio** (replacing the degenerate differential-IRR idea), flip-threshold **sensitivity**, **incremental** tax deductions, and **multi-crossing** break-even.

## 1. Purpose & scope

A personal decision tool to answer: *for a specific apartment and a given holding period, am I financially better off renting and investing, or buying?* Rigor matters more than polish — the output must be trustworthy and the methodology defensible.

**In scope:** a single self-contained `index.html` that takes editable financial inputs, runs a month-by-month net-worth simulation of both paths, and shows which wins, by how much, the break-even year(s), an annualized advantage, a year-by-year delta table, sensitivity flip-thresholds, and a net-worth chart.

**Non-goals (YAGNI):** no multi-scenario save/compare, no accounts/auth, no backend, no PMI / mortgage points / ARMs / extra-principal / refinancing modeling, no currency conversion or localization beyond a currency symbol, no PDF export, no Monte Carlo (the flip-thresholds in §3.6 cover the real need far more cheaply). Possible future extensions in §8.

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
- The renter's portfolio growth **is** the opportunity cost; the symmetric flip side is that the buyer's capital sits in (leveraged) home equity instead of the market. The comparison is exactly **money-in-a-home vs. money-in-the-market**.
- Investment gains are **after-tax** (capital-gains drag, §3.4).
- **Invariant:** because both paths spend `K` up front and an identical `budget` each month, their external cash flows are identical — they differ *only* in allocation. This is what makes the comparison and the annualized metric (§3.5) fair, and it is asserted as a test (§7).

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
- **Tax saving (incremental, computed yearly):** accumulate the year's deductible interest + deductible property tax (toggles decide which count); credit only the benefit *above* the standard-deduction baseline, optionally capped: `taxSaving_year = min(cap?, max(0, deductibleTotal − standardDeduction)) · marginalRate`. Applied as a credit at each year-end (reduces that year's effective buy cost). With `standardDeduction = 0` and no cap this reduces to the naive full-benefit case. *This is the parameterized stand-in for standard-deduction baselines / SALT-style caps — set both fields to match your jurisdiction.*
- **Effective buy cost** = `M + property tax + maintenance + insurance + HOA` (minus the year-end tax credit in December).
- **Effective rent cost** = `rent (stepped yearly) + renter's insurance`.
- **Invest the difference** into the cheaper path's portfolio; both portfolios then grow by the monthly return factor.

### 3.4 Net worth (marked to market each period)

- **Buyer** = `homeValue − loanBalance − sellingCosts − homeSaleTax + after-tax side portfolio`.
  - `sellingCosts = sellingCostsPct · homeValue` (applied in every period's mark-to-market, so each year reads as "outcome if you exit that year," and break-even reflects the cost of actually realizing).
  - `homeSaleGain = (homeValue − sellingCosts) − (price + closingCosts)`; `taxableGain = max(0, homeSaleGain − homeSaleExclusion)`; `homeSaleTax = taxableGain · capitalGainsRate`.
- **Renter** = `portfolioValue − capitalGainsTax`, where tax = `max(0, portfolioValue − totalContributions) · capitalGainsRate`.
- The buyer's side portfolio carries the same capital-gains treatment as the renter's.
- Both sides are after-"if-liquidated" tax, so the comparison stays apples-to-apples.

### 3.5 Derived outputs

- **$ ahead:** `BuyerNW(horizon) − RenterNW(horizon)` (signed; positive = buying ahead).
- **Annualized net-worth advantage (the primary annualized metric):** `(BuyerNW(H) / RenterNW(H))^(1/H) − 1`. Read as *"buying compounds your net worth ~X%/yr faster than renting"* (negative ⇒ renting compounds faster). Well-defined because both paths receive identical external cash flows (§3.1) and differ only in allocation, so the ratio isolates allocation efficiency.
  - **Why not a per-path "investment return" / differential IRR:** housing is partly *consumption*, so a standalone return per path is ill-defined; and under the equal-budget rule the interior cash flows are identical across paths, so a differential IRR degenerates (all interior flows cancel — only the terminal net worth differs). The net-worth ratio is the clean, well-defined expression of the same intent.
- **Horizon relative gap:** `BuyerNW(H)/RenterNW(H) − 1` (the "+X%" headline figure).
- **Per-year table:** for each year — Buyer NW, Renter NW, `Δ$ = Buy − Rent`, `Δ% = (Buy − Rent) / Rent`.
- **Break-even — all crossings:** scan the yearly Buy−Rent series for *every* sign change. Report as "buying ahead in years X–Y" (or "from year X on" if it never reverses). Explicitly flag when there is more than one crossing — with return > appreciation and a long horizon, the renter's compounding portfolio can re-overtake after the mortgage is paid off, so a single break-even year would mislead.

### 3.6 Sensitivity (flip thresholds)

The verdict is dominated by the spread between expected return and appreciation, so the tool quantifies its own fragility by re-running `computeProjection` across a sweep of the key drivers (all else held fixed):

- **Appreciation flip:** the appreciation rate at which the horizon verdict changes sign ("buying wins only if appreciation > X%").
- **Expected-return flip:** the return at which it flips ("flips to renting if return > Y%").
- A one-line read on how close current inputs sit to a flip; optionally a small secondary line of break-even year vs. appreciation.

Each threshold is found by bisection on the relevant input over a sensible range; report "no flip in range" when the verdict is robust.

## 4. Inputs

All editable, with sensible defaults and a currency-symbol field (default `$`). The big drivers (price, mortgage rate, expected return, appreciation, rent) get a slider paired with the number field for live "drag and watch"; the rest are plain number inputs.

| Group | Fields (default) |
|---|---|
| Property & purchase | price (500,000) · down payment (20%, unit toggle % / $) · closing costs (3%) · appreciation (3%/yr) · selling costs (6%) |
| Mortgage | interest rate (6.5%/yr) · term (30 yr) |
| Ownership costs | property tax (1.1%/yr) · maintenance (1.0%/yr) · insurance (1,500/yr) · HOA (300/mo) |
| Renting | rent (2,400/mo) · rent inflation (3%/yr) · renter's insurance (180/yr) |
| Investing | expected return (7%/yr) · general inflation (3%/yr) |
| Taxes | marginal rate (32%) · capital-gains rate (15%) · interest deductible (on) · property-tax deductible (on) · standard deduction (0; set to your jurisdiction's, e.g. ~29,000) · deduction cap (0 = none; e.g. SALT-style 10,000) · home-sale exclusion (250,000) |
| Horizon | 10 years |

## 5. Output (approved v3 view, updated for the fixes)

Right-hand results panel, recalculated live:

1. **Verdict banner** — exact `$ ahead` and `+X%` at horizon, the annualized advantage ("compounds ~X%/yr faster"), and break-even stated as a range with all crossings ("buying ahead years 8–10"), each with its definition shown.
2. **Annualized advantage** — the net-worth ratio metric as the headline number, plus the horizon relative gap. No per-path "return" is shown (ill-defined for housing — see §3.5).
3. **Sensitivity strip** — the flip thresholds (appreciation and return at which the verdict reverses), so the result's fragility is visible at a glance.
4. **Net-worth chart** — two lines (Buy, Rent) with dashed break-even marker(s) and crossover dot(s).
5. **Year-by-year table** — Year · Buy · Rent · Δ$ · Δ%, break-even and horizon rows highlighted, color-coded (renting-ahead vs buying-ahead).
6. **"Where your capital is working" breakdown** (collapsible) — makes the opportunity cost explicit: investment growth on invested capital, total interest paid, equity built, taxes saved, capital-gains drag.

Definitions: Δ = Buy − Rent. Positive/blue = buying ahead; negative/green = renting ahead.

## 6. Code structure

- **Pure engine:** `computeProjection(inputs)` — DOM-free, returns the monthly/yearly series plus all derived metrics (§3.5) and the sensitivity thresholds (§3.6). All math lives here.
- **UI layer:** reads inputs → calls `computeProjection` → renders verdict, advantage, sensitivity, SVG chart, table, breakdown. No math in the UI layer.
- Single file, but the two layers are clearly separated within it so the logic is isolated and testable.

## 7. Testing & validation

Built-in self-test mode: opening `index.html?test` runs assertions and shows a pass/fail panel. Keeps everything in one file while giving a re-runnable rigor check.

Test cases (minimum):
- **Mortgage payment** matches a known amortization value (e.g., 400,000 @ 6.5% / 30 yr ≈ 2,528.50/mo); the loan fully amortizes to ~0 at term end.
- **Zero-everything sanity** (zero return, appreciation, inflation, tax): results reduce to a clean cash comparison.
- **Equal-budget invariant:** every month, total outlay (cost + invested) is identical across both paths (the foundation of §3.5).
- **Annualized advantage:** when `BuyerNW = RenterNW` every year, advantage = 0 and there is no crossing; for a constructed `BuyerNW(H) = 2·RenterNW(H)` at H=10, advantage ≈ 7.18%/yr.
- **Crossing detection:** a synthetic series with two sign changes is reported as two crossings (no false single break-even); horizon `$ ahead` matches the last table row.
- **Incremental deduction:** with `standardDeduction` above the year's deductible total → tax saving 0; with it at 0 → matches the naive full-benefit value; respects the cap.
- **Sensitivity:** the reported appreciation/return flip thresholds actually flip the verdict when plugged back in (±1 step).

## 8. Decisions locked & deferred

**Locked:** monthly simulation; nominal expected return with inflation via the growth inputs; CG tax marked to market each period; home-sale exclusion applied to home-sale gains; **annualized verdict via the net-worth ratio** (no per-path return / no differential IRR — see §3.5); **incremental tax deduction above a standard-deduction baseline with optional cap**; **all break-even crossings reported**; **flip-threshold sensitivity included in v1**.

**Deferred (possible later, not in v1):** "today's dollars" (inflation-adjusted) display toggle; remember-inputs via `localStorage`; PMI for <20% down (note: with <20% down and no PMI, v1 is optimistic for buying); mortgage points / ARM / extra principal / refinancing; multi-scenario compare; PDF/print export; Monte Carlo.

## 9. Success criteria

- Open `index.html` offline; change any input → results recalc instantly.
- Verdict shows exact `$ ahead`, break-even (all crossings), and the annualized net-worth advantage with definitions; per-year Δ$/Δ% table present; flip-threshold sensitivity shown; chart shows both lines + break-even marker(s); opportunity cost explicit in the breakdown.
- `index.html?test` — all self-tests pass.
- Zero external dependencies.

## 10. File structure

```
Rent vs Buy/
  index.html        # the tool (self-contained)
  README.md         # usage + assumptions and known simplifications
  docs/superpowers/specs/2026-06-03-rent-vs-buy-calculator-design.md
```
