# Rent vs Buy Calculator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single self-contained `index.html` rent-vs-buy calculator that simulates both paths' net worth month-by-month (opportunity cost included), and shows the verdict, break-even year(s), annualized advantage, sensitivity, a chart, and a year-by-year delta table.

**Architecture:** All logic is small pure functions composed by `computeProjection(inputs)` (DOM-free), plus a UI layer that reads inputs → calls the engine → renders. Tests live in an in-file harness that runs when the page is opened with `?test`. No build, no CDN, no dependencies — double-click to run offline.

**Tech Stack:** Plain HTML + CSS + vanilla JavaScript (ES5-compatible, no modules), inline SVG for the chart.

**Spec:** `docs/superpowers/specs/2026-06-03-rent-vs-buy-calculator-design.md`

**Verification note:** The "test" mechanism is the in-file harness. To "run tests," open `index.html?test` in the IDE preview (or any browser); `runTests()` renders a pass/fail list, returns a summary string, and sets `document.title` to that summary (so it can also be read via `preview_eval` / a headless check). Engine tasks are strict TDD; UI tasks are verified visually in the preview.

**Working location:** Branch `rent-vs-buy-calculator`. All paths below are relative to repo root (`D:/AI Stuff/`). The tool lives in `Rent vs Buy/`.

---

## File structure

| File | Responsibility |
|---|---|
| `Rent vs Buy/index.html` | Everything: `<style>`, input + results DOM, `<script>` with the engine (pure functions + `computeProjection`), the UI layer, and the `?test` harness. |
| `Rent vs Buy/README.md` | How to use it; the assumptions and known simplifications from the spec. |

The single `<script>` is organized top-to-bottom as: (1) engine helpers, (2) `computeProjection`, (3) sensitivity, (4) test harness + tests, (5) UI (defaults, build inputs, render, chart, wire-up).

---

## Task 1: Page skeleton + test harness

**Files:**
- Create: `Rent vs Buy/index.html`

- [ ] **Step 1: Create `index.html` with the shell, CSS, and a test harness containing one sample test**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rent vs Buy</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; background:#f4f6f9; color:#1a1d23;
    font:15px/1.5 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; -webkit-font-smoothing:antialiased; }
  .app { display:grid; grid-template-columns:340px 1fr; gap:18px; max-width:1180px; margin:0 auto; padding:20px; }
  @media (max-width:820px){ .app{ grid-template-columns:1fr; } }
  .inputs, .results { background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:16px; box-shadow:0 1px 2px rgba(0,0,0,.04); }
  .inputs { align-self:start; position:sticky; top:16px; max-height:calc(100vh - 32px); overflow:auto; }
  h1 { font-size:18px; margin:0 0 12px; }
  .grp { margin-bottom:14px; }
  .grp h2 { font-size:11px; letter-spacing:.5px; text-transform:uppercase; color:#6b7280; margin:0 0 6px; }
  .fld { display:flex; align-items:center; gap:8px; margin-bottom:6px; }
  .fld label { flex:1; font-size:13px; color:#374151; }
  .fld input[type=number]{ width:96px; padding:4px 6px; border:1px solid #d1d5db; border-radius:6px; font:inherit; text-align:right; }
  .fld input[type=range]{ flex:1; }
  .fld .unit { width:14px; color:#9ca3af; font-size:12px; }
  .verdict { background:#eff4ff; border:1px solid #bfd3ff; border-radius:10px; padding:14px 16px; margin-bottom:14px; }
  .verdict .big { font-size:19px; font-weight:700; }
  .verdict .defn { color:#475569; font-size:12.5px; line-height:1.6; margin-top:6px; }
  .stats { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:12px; }
  .stat { border-radius:8px; padding:11px 12px; background:#f3f4f6; border:1px solid #e5e7eb; }
  .stat .lbl { font-size:11px; letter-spacing:.4px; text-transform:uppercase; color:#6b7280; }
  .stat .val { font-size:22px; font-weight:700; margin-top:2px; }
  .stat.buy .val{ color:#2563eb; } .stat.rent .val{ color:#16a34a; }
  .sens { font-size:12.5px; color:#475569; background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:9px 12px; margin-bottom:14px; }
  .chartbox { border:1px solid #e5e7eb; border-radius:8px; padding:12px; margin-bottom:14px; }
  .legend { display:flex; gap:16px; font-size:12px; color:#475569; margin-bottom:6px; }
  .legend i { display:inline-block; width:11px; height:11px; border-radius:3px; vertical-align:middle; margin-right:5px; }
  svg { width:100%; max-width:640px; height:auto; display:block; margin:0 auto; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { padding:6px 10px; text-align:right; } th:first-child,td:first-child{ text-align:left; }
  thead th { color:#6b7280; font-weight:600; border-bottom:1px solid #e5e7eb; font-size:12px; }
  tbody tr + tr td { border-top:1px solid #f1f3f5; }
  .neg { color:#16a34a; } .pos { color:#2563eb; }
  .row-be { background:#eff4ff; font-weight:700; } .row-hz { font-weight:700; }
  details.bd { margin-top:12px; border:1px solid #e5e7eb; border-radius:8px; padding:8px 12px; font-size:13px; }
  details.bd summary { cursor:pointer; font-weight:600; }
  /* test harness */
  #tests { max-width:760px; margin:0 auto; padding:20px; }
  .t-pass { color:#16a34a; } .t-fail { color:#dc2626; font-weight:700; }
  .t-row { font:13px/1.6 ui-monospace,Consolas,monospace; }
</style>
</head>
<body>
  <div id="tests" hidden></div>
  <div class="app" id="app">
    <div class="inputs"><h1>Rent vs Buy</h1><div id="inputForm"></div></div>
    <div class="results" id="results"></div>
  </div>
<script>
"use strict";

/* ===== 4. TEST HARNESS ===== */
var TESTS = [];
function test(name, fn){ TESTS.push({name:name, fn:fn}); }
function approx(a, b, eps){ return Math.abs(a - b) <= (eps == null ? 1e-6 : eps); }
function runTests(){
  var el = document.getElementById('tests');
  el.hidden = false; document.getElementById('app').style.display = 'none';
  var passed = 0, failed = 0, html = '<h1>Self-tests</h1>';
  for (var i = 0; i < TESTS.length; i++){
    var r; try { TESTS[i].fn(); r = true; } catch(e){ r = false; var msg = e && e.message; }
    if (r){ passed++; html += '<div class="t-row t-pass">✓ ' + TESTS[i].name + '</div>'; }
    else { failed++; html += '<div class="t-row t-fail">✗ ' + TESTS[i].name + ' — ' + (msg||'') + '</div>'; }
  }
  var summary = passed + ' passed, ' + failed + ' failed';
  el.innerHTML = '<div class="t-row"><b>' + summary + '</b></div>' + html;
  document.title = (failed ? 'FAIL: ' : 'OK: ') + summary;
  return summary;
}

// sample test proves the harness works
test('harness: approx works', function(){ if (!approx(1, 1.0000001, 1e-3)) throw new Error('approx broken'); });

/* ===== UI bootstrap (filled in later tasks) ===== */
function boot(){ /* UI wired up in Task 10+ */ }

if (location.search.indexOf('test') !== -1) runTests(); else boot();
</script>
</body>
</html>
```

- [ ] **Step 2: Verify the harness runs**

Open `Rent vs Buy/index.html?test` in the IDE preview.
Expected: page shows "**1 passed, 0 failed**" and "✓ harness: approx works"; tab title starts with "OK:".

- [ ] **Step 3: Commit**

```bash
git add "Rent vs Buy/index.html"
git commit -m "feat(rent-buy): page skeleton + in-file test harness"
```

---

## Task 2: `monthlyPayment` + `toMonthly`

**Files:**
- Modify: `Rent vs Buy/index.html` (engine helpers section + tests)

- [ ] **Step 1: Add failing tests** (place near the other `test(...)` calls)

```javascript
test('monthlyPayment: 400k @ 6.5% / 30yr', function(){
  if (!approx(monthlyPayment(400000, 6.5, 30), 2528.27, 0.5)) throw new Error('got ' + monthlyPayment(400000,6.5,30));
});
test('monthlyPayment: zero rate', function(){
  if (!approx(monthlyPayment(120000, 0, 30), 333.3333, 1e-3)) throw new Error('got ' + monthlyPayment(120000,0,30));
});
test('toMonthly: 7% compounds back to 7%', function(){
  if (!approx(Math.pow(1 + toMonthly(7), 12) - 1, 0.07, 1e-9)) throw new Error('bad compounding');
});
```

- [ ] **Step 2: Run to verify failure**

Open `index.html?test`. Expected: 3 new tests show ✗ FAIL ("monthlyPayment is not defined").

- [ ] **Step 3: Implement** (top of script, in the engine-helpers section, before the harness)

```javascript
/* ===== 1. ENGINE HELPERS ===== */
function monthlyPayment(principal, annualRatePct, years){
  var n = years * 12, r = annualRatePct / 100 / 12;
  if (r === 0) return principal / n;
  return principal * r / (1 - Math.pow(1 + r, -n));
}
function toMonthly(annualPct){ return Math.pow(1 + annualPct / 100, 1/12) - 1; }
```

- [ ] **Step 4: Run to verify pass**

Open `index.html?test`. Expected: "**4 passed, 0 failed**".

- [ ] **Step 5: Commit**

```bash
git add "Rent vs Buy/index.html"
git commit -m "feat(rent-buy): mortgage payment + monthly rate helpers"
```

---

## Task 3: `splitBudget` (equal-budget invariant)

**Files:**
- Modify: `Rent vs Buy/index.html`

- [ ] **Step 1: Add failing tests**

```javascript
test('splitBudget: owning pricier -> renter invests gap', function(){
  var s = splitBudget(3000, 2000);
  if (!(s.budget === 3000 && s.buyInvest === 0 && s.rentInvest === 1000)) throw new Error('bad split');
});
test('splitBudget: invariant holds (equal total outlay, non-negative)', function(){
  var s = splitBudget(1800.5, 2400.25);
  if (!approx(1800.5 + s.buyInvest, 2400.25 + s.rentInvest)) throw new Error('not equal');
  if (s.buyInvest < 0 || s.rentInvest < 0) throw new Error('negative invest');
});
```

- [ ] **Step 2: Run to verify failure** — Expected: 2 new ✗ FAIL ("splitBudget is not defined").

- [ ] **Step 3: Implement** (engine helpers)

```javascript
function splitBudget(effBuy, effRent){
  var b = Math.max(effBuy, effRent);
  return { budget: b, buyInvest: b - effBuy, rentInvest: b - effRent };
}
```

- [ ] **Step 4: Run to verify pass** — Expected: "**6 passed, 0 failed**".

- [ ] **Step 5: Commit**

```bash
git add "Rent vs Buy/index.html"
git commit -m "feat(rent-buy): equal-budget split helper"
```

---

## Task 4: `annualTaxCredit` (incremental deduction)

**Files:**
- Modify: `Rent vs Buy/index.html`

- [ ] **Step 1: Add failing tests**

```javascript
var TAXP = { interestDeductible:true, propertyTaxDeductible:true, standardDeduction:0, deductionCap:0, marginalRatePct:32 };
test('annualTaxCredit: full benefit when standardDeduction = 0', function(){
  if (!approx(annualTaxCredit(10000, 5000, TAXP), 4800, 1e-6)) throw new Error('got ' + annualTaxCredit(10000,5000,TAXP));
});
test('annualTaxCredit: zero when standardDeduction exceeds deductible', function(){
  var p = Object.assign({}, TAXP, { standardDeduction: 20000 });
  if (!approx(annualTaxCredit(10000, 5000, p), 0)) throw new Error('should be 0');
});
test('annualTaxCredit: cap limits the excess', function(){
  var p = Object.assign({}, TAXP, { deductionCap: 10000 });
  if (!approx(annualTaxCredit(10000, 5000, p), 3200, 1e-6)) throw new Error('got ' + annualTaxCredit(10000,5000,p));
});
test('annualTaxCredit: toggles off exclude that component', function(){
  var p = Object.assign({}, TAXP, { propertyTaxDeductible:false });
  if (!approx(annualTaxCredit(10000, 5000, p), 3200, 1e-6)) throw new Error('got ' + annualTaxCredit(10000,5000,p));
});
```

- [ ] **Step 2: Run to verify failure** — Expected: 4 new ✗ FAIL.

- [ ] **Step 3: Implement**

```javascript
function annualTaxCredit(yearInterest, yearPropertyTax, p){
  var deductible = (p.interestDeductible ? yearInterest : 0) + (p.propertyTaxDeductible ? yearPropertyTax : 0);
  var excess = Math.max(0, deductible - p.standardDeduction);
  if (p.deductionCap > 0) excess = Math.min(excess, p.deductionCap);
  return excess * p.marginalRatePct / 100;
}
```

- [ ] **Step 4: Run to verify pass** — Expected: "**10 passed, 0 failed**".

- [ ] **Step 5: Commit**

```bash
git add "Rent vs Buy/index.html"
git commit -m "feat(rent-buy): incremental tax-deduction credit"
```

---

## Task 5: `annualAdvantage` + `findCrossings`

**Files:**
- Modify: `Rent vs Buy/index.html`

- [ ] **Step 1: Add failing tests**

```javascript
test('annualAdvantage: equal -> 0', function(){
  if (!approx(annualAdvantage(100, 100, 10), 0)) throw new Error('should be 0');
});
test('annualAdvantage: double over 10yr -> ~7.18%/yr', function(){
  if (!approx(annualAdvantage(200, 100, 10), 7.177, 1e-2)) throw new Error('got ' + annualAdvantage(200,100,10));
});
test('findCrossings: single buy-ahead crossing', function(){
  var c = findCrossings([-5,-3,-1,2,4]);
  if (!(c.length === 1 && c[0].toYear === 3 && c[0].direction === 'buy-ahead')) throw new Error(JSON.stringify(c));
});
test('findCrossings: two crossings detected', function(){
  var c = findCrossings([-1, 2, 3, -1]);
  if (!(c.length === 2 && c[0].direction === 'buy-ahead' && c[1].direction === 'rent-ahead')) throw new Error(JSON.stringify(c));
});
```

- [ ] **Step 2: Run to verify failure** — Expected: 4 new ✗ FAIL.

- [ ] **Step 3: Implement**

```javascript
function annualAdvantage(buyH, rentH, years){
  if (rentH <= 0 || buyH <= 0 || years <= 0) return NaN;
  return (Math.pow(buyH / rentH, 1 / years) - 1) * 100;
}
function findCrossings(delta){
  var out = [];
  for (var y = 1; y < delta.length; y++){
    var prev = delta[y-1], cur = delta[y];
    if (prev < 0 && cur >= 0) out.push({ fromYear:y-1, toYear:y, direction:'buy-ahead' });
    else if (prev >= 0 && cur < 0) out.push({ fromYear:y-1, toYear:y, direction:'rent-ahead' });
  }
  return out;
}
```

- [ ] **Step 4: Run to verify pass** — Expected: "**14 passed, 0 failed**".

- [ ] **Step 5: Commit**

```bash
git add "Rent vs Buy/index.html"
git commit -m "feat(rent-buy): annualized advantage + crossing detection"
```

---

## Task 6: `snapshotBuy` + `snapshotRent` (net worth, marked to market)

**Files:**
- Modify: `Rent vs Buy/index.html`

- [ ] **Step 1: Add failing tests**

```javascript
test('snapshotRent: subtracts CG tax on gains', function(){
  // portfolio 120k, contributions 100k, 15% CG -> 120000 - 0.15*20000 = 117000
  if (!approx(snapshotRent(120000, 100000, 0.15), 117000)) throw new Error('got ' + snapshotRent(120000,100000,0.15));
});
test('snapshotBuy: equity net of selling cost, no taxable gain', function(){
  // value 500k, balance 400k, selling 6%, basis 515k -> gain (500k-30k)-515k<0 -> no tax
  var inp = { sellingCostsPct:6, homeSaleExclusion:250000 };
  var nw = snapshotBuy(500000, 400000, 500000, 15000, inp, 0.15, 0, 0);
  if (!approx(nw, 500000 - 400000 - 30000, 1e-6)) throw new Error('got ' + nw);
});
```

- [ ] **Step 2: Run to verify failure** — Expected: 2 new ✗ FAIL.

- [ ] **Step 3: Implement**

```javascript
function snapshotBuy(homeValue, balance, price, closing, inp, cg, portfolio, contrib){
  var selling = inp.sellingCostsPct / 100 * homeValue;
  var gain = (homeValue - selling) - (price + closing);
  var taxable = Math.max(0, gain - inp.homeSaleExclusion);
  var homeSaleTax = taxable * cg;
  var sideTax = Math.max(0, portfolio - contrib) * cg;
  return homeValue - balance - selling - homeSaleTax + (portfolio - sideTax);
}
function snapshotRent(portfolio, contrib, cg){
  return portfolio - Math.max(0, portfolio - contrib) * cg;
}
```

- [ ] **Step 4: Run to verify pass** — Expected: "**16 passed, 0 failed**".

- [ ] **Step 5: Commit**

```bash
git add "Rent vs Buy/index.html"
git commit -m "feat(rent-buy): net-worth snapshots (mark-to-market, after tax)"
```

---

## Task 7: `computeProjection` (assemble the monthly engine)

**Files:**
- Modify: `Rent vs Buy/index.html`

- [ ] **Step 1: Add failing tests** (uses the shared `DEFAULTS` defined here for tests; the UI reuses it in Task 10)

```javascript
var DEFAULTS = {
  price:500000, downPaymentIsPct:true, downPaymentPct:20, downPaymentAmount:100000,
  closingCostsPct:3, appreciationPct:3, sellingCostsPct:6,
  mortgageRatePct:6.5, termYears:30,
  propertyTaxPct:1.1, maintenancePct:1.0, insuranceAnnual:1500, hoaMonthly:300,
  rentMonthly:2400, rentInflationPct:3, rentersInsuranceAnnual:180,
  expectedReturnPct:7, generalInflationPct:3,
  marginalRatePct:32, capitalGainsRatePct:15, interestDeductible:true, propertyTaxDeductible:true,
  standardDeduction:0, deductionCap:0, homeSaleExclusion:250000,
  horizonYears:10, currencySymbol:'$'
};
test('computeProjection: array shapes and year-0 values', function(){
  var p = computeProjection(DEFAULTS);
  if (p.buyNW.length !== 11 || p.rentNW.length !== 11) throw new Error('want 11 yearly points');
  // year 0: renter NW = K = down(100k)+closing(15k) = 115k
  if (!approx(p.rentNW[0], 115000, 1)) throw new Error('rentNW0 ' + p.rentNW[0]);
  // year 0: buyer NW = down - sellingCosts(6% of 500k) = 100k - 30k = 70k
  if (!approx(p.buyNW[0], 70000, 1)) throw new Error('buyNW0 ' + p.buyNW[0]);
});
test('computeProjection: derived metrics are consistent', function(){
  var p = computeProjection(DEFAULTS);
  var H = DEFAULTS.horizonYears;
  if (!approx(p.dollarAhead, p.buyNW[H] - p.rentNW[H], 1e-6)) throw new Error('dollarAhead mismatch');
  if (!approx(p.advantage, annualAdvantage(p.buyNW[H], p.rentNW[H], H), 1e-9)) throw new Error('advantage mismatch');
  if (p.deltaDollar.length !== 11) throw new Error('delta length');
});
```

- [ ] **Step 2: Run to verify failure** — Expected: 2 new ✗ FAIL ("computeProjection is not defined").

- [ ] **Step 3: Implement** (the `2. computeProjection` section; uses helpers from Tasks 2–6)

```javascript
/* ===== 2. computeProjection ===== */
function computeProjection(inp){
  var H = inp.horizonYears, months = H * 12, price = inp.price;
  var downPayment = inp.downPaymentIsPct ? price * inp.downPaymentPct / 100 : inp.downPaymentAmount;
  var closing = price * inp.closingCostsPct / 100;
  var K = downPayment + closing, loan0 = price - downPayment;
  var M = monthlyPayment(loan0, inp.mortgageRatePct, inp.termYears);
  var rm = inp.mortgageRatePct / 100 / 12, ri = toMonthly(inp.expectedReturnPct), ga = toMonthly(inp.appreciationPct);
  var cg = inp.capitalGainsRatePct / 100;

  var homeValue = price, balance = loan0;
  var buyerPortfolio = 0, renterPortfolio = K, buyerContrib = 0, renterContrib = K;
  var yearInterest = 0, yearPropertyTax = 0;
  var totalInterest = 0, totalOwnership = 0, totalRent = 0, totalTaxSaved = 0;

  var years = [0], buyNW = [snapshotBuy(homeValue, balance, price, closing, inp, cg, buyerPortfolio, buyerContrib)];
  var rentNW = [snapshotRent(renterPortfolio, renterContrib, cg)];

  for (var m = 1; m <= months; m++){
    var yi = Math.floor((m - 1) / 12);
    var inflF = Math.pow(1 + inp.generalInflationPct / 100, yi);
    var rentF = Math.pow(1 + inp.rentInflationPct / 100, yi);

    var interest = 0, principal = 0, pay = 0;
    if (balance > 1e-9){
      interest = balance * rm; principal = M - interest;
      if (principal > balance) principal = balance;
      balance -= principal; pay = interest + principal;
    }
    var propTax = inp.propertyTaxPct / 100 * homeValue / 12;
    var maint = inp.maintenancePct / 100 * homeValue / 12;
    var ins = inp.insuranceAnnual / 12 * inflF;
    var hoa = inp.hoaMonthly * inflF;

    yearInterest += interest; yearPropertyTax += propTax;
    totalInterest += interest; totalOwnership += propTax + maint + ins + hoa;

    var effBuy = pay + propTax + maint + ins + hoa;
    if (m % 12 === 0){
      var credit = annualTaxCredit(yearInterest, yearPropertyTax, inp);
      effBuy -= credit; totalTaxSaved += credit; yearInterest = 0; yearPropertyTax = 0;
    }
    var rent = inp.rentMonthly * rentF, rins = inp.rentersInsuranceAnnual / 12 * inflF;
    var effRent = rent + rins; totalRent += rent + rins;

    var s = splitBudget(effBuy, effRent);
    buyerPortfolio = buyerPortfolio * (1 + ri) + s.buyInvest;
    renterPortfolio = renterPortfolio * (1 + ri) + s.rentInvest;
    buyerContrib += s.buyInvest; renterContrib += s.rentInvest;

    homeValue *= (1 + ga);

    if (m % 12 === 0){
      years.push(m / 12);
      buyNW.push(snapshotBuy(homeValue, balance, price, closing, inp, cg, buyerPortfolio, buyerContrib));
      rentNW.push(snapshotRent(renterPortfolio, renterContrib, cg));
    }
  }

  var deltaDollar = [], deltaPct = [];
  for (var y = 0; y <= H; y++){ deltaDollar.push(buyNW[y] - rentNW[y]); deltaPct.push((buyNW[y] - rentNW[y]) / rentNW[y] * 100); }

  return {
    years:years, buyNW:buyNW, rentNW:rentNW, deltaDollar:deltaDollar, deltaPct:deltaPct,
    dollarAhead: buyNW[H] - rentNW[H],
    horizonGapPct: (buyNW[H] / rentNW[H] - 1) * 100,
    advantage: annualAdvantage(buyNW[H], rentNW[H], H),
    crossings: findCrossings(deltaDollar),
    K:K, downPayment:downPayment, closing:closing,
    breakdown: {
      totalInterest:totalInterest, totalOwnership:totalOwnership, totalRent:totalRent, totalTaxSaved:totalTaxSaved,
      equity: homeValue - balance,
      buyerInvestmentGrowth: buyerPortfolio - buyerContrib,
      renterInvestmentGrowth: renterPortfolio - renterContrib
    }
  };
}
```

- [ ] **Step 4: Run to verify pass** — Expected: "**18 passed, 0 failed**".

- [ ] **Step 5: Commit**

```bash
git add "Rent vs Buy/index.html"
git commit -m "feat(rent-buy): computeProjection monthly engine + derived metrics"
```

---

## Task 8: Invariant + zero-everything sanity tests

**Files:**
- Modify: `Rent vs Buy/index.html`

- [ ] **Step 1: Add failing tests** (these assert engine behavior, no new code unless an assert fails)

```javascript
test('engine: equal-budget aggregate invariant (total outlay equal)', function(){
  // re-derive total outlay from a stripped scenario by instrumenting splitBudget via a clone run
  var inp = Object.assign({}, DEFAULTS, { horizonYears:5 });
  var buyTotal = 0, rentTotal = 0;
  var orig = splitBudget;
  splitBudget = function(a,b){ var r = orig(a,b); buyTotal += a + r.buyInvest; rentTotal += b + r.rentInvest; return r; };
  computeProjection(inp); splitBudget = orig;
  if (!approx(buyTotal, rentTotal, 1e-3)) throw new Error('outlay buy ' + buyTotal + ' rent ' + rentTotal);
});
test('engine: zero return -> portfolios equal contributions (no phantom growth)', function(){
  var inp = Object.assign({}, DEFAULTS, {
    expectedReturnPct:0, appreciationPct:0, rentInflationPct:0, generalInflationPct:0,
    capitalGainsRatePct:0, marginalRatePct:0, interestDeductible:false, propertyTaxDeductible:false
  });
  var p = computeProjection(inp);
  // with 0% return and 0% CG, neither portfolio can show growth beyond its contributions
  if (Math.abs(p.breakdown.renterInvestmentGrowth) > 1e-6) throw new Error('renter phantom growth ' + p.breakdown.renterInvestmentGrowth);
  if (Math.abs(p.breakdown.buyerInvestmentGrowth) > 1e-6) throw new Error('buyer phantom growth ' + p.breakdown.buyerInvestmentGrowth);
});
```

- [ ] **Step 2: Run** — Expected: both PASS (engine already satisfies them). If "zero return" fails, the bug is real — fix `computeProjection` growth/contribution order so a 0% return yields `portfolio === contributions`.

- [ ] **Step 3: (Only if a test failed) fix the order of operations** so contributions are added after growth and no growth is applied to the same-month contribution. The implementation in Task 7 already does `portfolio*(1+ri) + invest`, which satisfies this; no change expected.

- [ ] **Step 4: Run to verify pass** — Expected: "**20 passed, 0 failed**".

- [ ] **Step 5: Commit**

```bash
git add "Rent vs Buy/index.html"
git commit -m "test(rent-buy): equal-budget invariant + zero-rate sanity"
```

---

## Task 9: `findFlip` (sensitivity thresholds)

**Files:**
- Modify: `Rent vs Buy/index.html`

- [ ] **Step 1: Add failing tests**

```javascript
test('findFlip: appreciation threshold actually flips the verdict', function(){
  var base = Object.assign({}, DEFAULTS);
  var thr = findFlip(base, 'appreciationPct', -5, 15);
  if (thr === null) throw new Error('expected a flip in range');
  var below = computeProjection(Object.assign({}, base, { appreciationPct: thr - 0.5 })).dollarAhead;
  var above = computeProjection(Object.assign({}, base, { appreciationPct: thr + 0.5 })).dollarAhead;
  if ((below > 0) === (above > 0)) throw new Error('threshold does not flip sign');
});
test('findFlip: returns null when no flip in range', function(){
  var base = Object.assign({}, DEFAULTS);
  if (findFlip(base, 'appreciationPct', 3.0, 3.0001) !== null) throw new Error('should be null in tiny range');
});
```

- [ ] **Step 2: Run to verify failure** — Expected: 2 new ✗ FAIL ("findFlip is not defined").

- [ ] **Step 3: Implement** (the `3. SENSITIVITY` section)

```javascript
/* ===== 3. SENSITIVITY ===== */
function findFlip(baseInp, key, lo, hi, steps){
  steps = steps || 50;
  function f(x){ var c = Object.assign({}, baseInp); c[key] = x; return computeProjection(c).dollarAhead; }
  var a = f(lo), b = f(hi);
  if ((a > 0) === (b > 0)) return null;
  for (var i = 0; i < steps; i++){
    var mid = (lo + hi) / 2, fm = f(mid);
    if ((fm > 0) === (a > 0)){ lo = mid; a = fm; } else { hi = mid; }
  }
  return (lo + hi) / 2;
}
```

- [ ] **Step 4: Run to verify pass** — Expected: "**22 passed, 0 failed**".

- [ ] **Step 5: Commit**

```bash
git add "Rent vs Buy/index.html"
git commit -m "feat(rent-buy): sensitivity flip-threshold finder"
```

---

## Task 10: UI — input panel

**Files:**
- Modify: `Rent vs Buy/index.html` (UI section + `boot`)

- [ ] **Step 1: Implement the inputs UI** (replace the placeholder `boot()` and add the `5. UI` section)

```javascript
/* ===== 5. UI ===== */
// field: [key, label, unit, step, isBigDriver]
var INPUT_CONFIG = [
  ['Property & purchase', [
    ['price','Price','$',1000,true],
    ['downPaymentPct','Down payment','%',1,false],
    ['closingCostsPct','Closing costs','%',0.1,false],
    ['appreciationPct','Appreciation','%/yr',0.1,true],
    ['sellingCostsPct','Selling costs','%',0.1,false]
  ]],
  ['Mortgage', [
    ['mortgageRatePct','Interest rate','%/yr',0.05,true],
    ['termYears','Term','yr',1,false]
  ]],
  ['Ownership costs', [
    ['propertyTaxPct','Property tax','%/yr',0.05,false],
    ['maintenancePct','Maintenance','%/yr',0.1,false],
    ['insuranceAnnual','Insurance','$/yr',50,false],
    ['hoaMonthly','HOA','$/mo',10,false]
  ]],
  ['Renting', [
    ['rentMonthly','Rent','$/mo',25,true],
    ['rentInflationPct','Rent inflation','%/yr',0.1,false],
    ['rentersInsuranceAnnual','Renter’s insurance','$/yr',10,false]
  ]],
  ['Investing', [
    ['expectedReturnPct','Expected return','%/yr',0.1,true],
    ['generalInflationPct','General inflation','%/yr',0.1,false]
  ]],
  ['Taxes', [
    ['marginalRatePct','Marginal rate','%',1,false],
    ['capitalGainsRatePct','Capital-gains rate','%',1,false],
    ['standardDeduction','Standard deduction','$',500,false],
    ['deductionCap','Deduction cap (0=none)','$',500,false],
    ['homeSaleExclusion','Home-sale exclusion','$',5000,false]
  ]],
  ['Horizon', [ ['horizonYears','Horizon','yr',1,true] ]]
];
var BIG_RANGES = { price:[100000,2000000], appreciationPct:[-2,12], mortgageRatePct:[0,12],
  rentMonthly:[500,12000], expectedReturnPct:[0,15], horizonYears:[1,40] };
var state = Object.assign({}, DEFAULTS);

function buildInputs(){
  var host = document.getElementById('inputForm'); host.innerHTML = '';
  INPUT_CONFIG.forEach(function(group){
    var g = document.createElement('div'); g.className = 'grp';
    g.innerHTML = '<h2>' + group[0] + '</h2>';
    group[1].forEach(function(f){
      var key = f[0], label = f[1], unit = f[2], step = f[3], big = f[4];
      var row = document.createElement('div'); row.className = 'fld';
      var num = '<input type="number" id="in_' + key + '" step="' + step + '" value="' + state[key] + '">';
      var rng = '';
      if (big && BIG_RANGES[key]) rng = '<input type="range" id="rg_' + key + '" min="' + BIG_RANGES[key][0] +
        '" max="' + BIG_RANGES[key][1] + '" step="' + step + '" value="' + state[key] + '">';
      row.innerHTML = '<label for="in_' + key + '">' + label + '</label>' + rng + num + '<span class="unit">' + unit + '</span>';
      g.appendChild(row);
    });
    host.appendChild(g);
  });
  // wire events
  INPUT_CONFIG.forEach(function(group){ group[1].forEach(function(f){
    var key = f[0];
    var num = document.getElementById('in_' + key), rng = document.getElementById('rg_' + key);
    function onChange(v){ state[key] = parseFloat(v); if (isNaN(state[key])) state[key] = 0;
      if (num) num.value = state[key]; if (rng) rng.value = state[key]; recompute(); }
    if (num) num.addEventListener('input', function(){ onChange(num.value); });
    if (rng) rng.addEventListener('input', function(){ onChange(rng.value); });
  }); });
}
function recompute(){ render(computeProjection(state)); }
function boot(){ buildInputs(); recompute(); }
```

- [ ] **Step 2: Add a temporary `render` stub so `boot` runs** (will be replaced in Task 11)

```javascript
function render(p){ document.getElementById('results').textContent =
  'Buy ' + Math.round(p.buyNW[state.horizonYears]) + ' vs Rent ' + Math.round(p.rentNW[state.horizonYears]); }
```

- [ ] **Step 3: Verify in preview** — Open `Rent vs Buy/index.html` (no `?test`).
Expected: left panel shows all grouped inputs with defaults; the 6 big drivers have sliders; results panel shows a "Buy … vs Rent …" line that updates live when you drag the price slider or edit a field.

- [ ] **Step 4: Confirm tests still pass** — Open `index.html?test`. Expected: "**22 passed, 0 failed**".

- [ ] **Step 5: Commit**

```bash
git add "Rent vs Buy/index.html"
git commit -m "feat(rent-buy): live input panel with sliders"
```

---

## Task 11: UI — results render (verdict, advantage, sensitivity, table, breakdown)

**Files:**
- Modify: `Rent vs Buy/index.html`

- [ ] **Step 1: Replace the `render` stub with the full renderer** (chart added in Task 12 via `drawChart`)

```javascript
function fmtMoney(v){ var s = state.currencySymbol, n = Math.round(v);
  return (n < 0 ? '-' : '') + s + Math.abs(n).toLocaleString('en-US'); }
function fmtK(v){ return state.currencySymbol + Math.round(v/1000).toLocaleString('en-US') + 'k'; }

function breakevenLabel(p){
  var H = state.horizonYears, c = p.crossings;
  if (p.deltaDollar[H] > 0 && c.length === 0) return 'Buying ahead the entire horizon';
  if (p.deltaDollar[H] <= 0 && c.length === 0) return 'Renting ahead the entire horizon';
  if (c.length === 1) return (c[0].direction === 'buy-ahead')
    ? 'Buying pulls ahead in year ' + c[0].toYear + ' (stays ahead through year ' + H + ')'
    : 'Renting pulls ahead in year ' + c[0].toYear;
  // multiple crossings
  return c.map(function(x){ return x.direction.replace('-', ' ') + ' @ yr ' + x.toYear; }).join(' → ') + ' (verdict reverses — read the chart)';
}

function render(p){
  var H = state.horizonYears, ahead = p.dollarAhead, buyWins = ahead > 0;
  var color = buyWins ? '#2563eb' : '#16a34a';
  var html = '';

  html += '<div class="verdict" style="background:' + (buyWins?'#eff4ff':'#eefaf1') +
    ';border-color:' + (buyWins?'#bfd3ff':'#b7e4c7') + '">' +
    '<div class="big">' + (buyWins?'Buying':'Renting') + ' ends ' + fmtMoney(Math.abs(ahead)) +
    ' ahead at year ' + H + ' (' + (p.horizonGapPct>=0?'+':'') + p.horizonGapPct.toFixed(1) + '%)</div>' +
    '<div class="defn"><b>$ ahead</b> = Buy − Rent net worth at year ' + H + ' = ' +
    fmtMoney(p.buyNW[H]) + ' − ' + fmtMoney(p.rentNW[H]) + '<br>' +
    '<b>' + breakevenLabel(p) + '</b></div></div>';

  html += '<div class="stats">' +
    '<div class="stat"><div class="lbl">Annualized advantage</div><div class="val" style="color:' + color + '">' +
      (p.advantage>=0?'+':'') + p.advantage.toFixed(2) + '%/yr</div></div>' +
    '<div class="stat buy"><div class="lbl">Buy NW · yr ' + H + '</div><div class="val">' + fmtK(p.buyNW[H]) + '</div></div>' +
    '<div class="stat rent"><div class="lbl">Rent NW · yr ' + H + '</div><div class="val">' + fmtK(p.rentNW[H]) + '</div></div>' +
    '</div>';

  // sensitivity
  var aFlip = findFlip(state, 'appreciationPct', -5, 15), rFlip = findFlip(state, 'expectedReturnPct', 0, 20);
  html += '<div class="sens">Sensitivity: ' +
    (aFlip===null ? 'verdict robust to appreciation in ±5% band' :
      'verdict flips at appreciation ≈ <b>' + aFlip.toFixed(1) + '%</b> (now ' + state.appreciationPct + '%)') + ' · ' +
    (rFlip===null ? 'robust to return changes' :
      'flips at expected return ≈ <b>' + rFlip.toFixed(1) + '%</b> (now ' + state.expectedReturnPct + '%)') + '</div>';

  html += '<div class="chartbox"><div class="legend"><span><i style="background:#2563eb"></i>Buy</span>' +
    '<span><i style="background:#16a34a"></i>Rent</span></div><div id="chart"></div></div>';

  // table
  html += '<table><thead><tr><th>Year</th><th>Buy</th><th>Rent</th><th>Δ $</th><th>Δ %</th></tr></thead><tbody>';
  var beYears = {}; p.crossings.forEach(function(c){ beYears[c.toYear] = true; });
  for (var y = 1; y <= H; y++){
    var cls = beYears[y] ? ' class="row-be"' : (y === H ? ' class="row-hz"' : '');
    var dn = p.deltaDollar[y] >= 0 ? 'pos' : 'neg';
    html += '<tr' + cls + '><td>' + y + (beYears[y]?' ◄ break-even':(y===H?' ◄ horizon':'')) + '</td>' +
      '<td>' + fmtK(p.buyNW[y]) + '</td><td>' + fmtK(p.rentNW[y]) + '</td>' +
      '<td class="' + dn + '">' + (p.deltaDollar[y]>=0?'+':'−') + fmtK(Math.abs(p.deltaDollar[y])) + '</td>' +
      '<td class="' + dn + '">' + (p.deltaPct[y]>=0?'+':'') + p.deltaPct[y].toFixed(1) + '%</td></tr>';
  }
  html += '</tbody></table>';

  // breakdown
  var b = p.breakdown;
  html += '<details class="bd"><summary>Where your capital is working (' + H + '-yr totals)</summary>' +
    '<div>Mortgage interest paid: ' + fmtMoney(b.totalInterest) + '</div>' +
    '<div>Ownership costs (tax/maint/ins/HOA): ' + fmtMoney(b.totalOwnership) + '</div>' +
    '<div>Tax deductions saved: ' + fmtMoney(b.totalTaxSaved) + '</div>' +
    '<div>Total rent paid: ' + fmtMoney(b.totalRent) + '</div>' +
    '<div>Renter investment growth (opportunity value): ' + fmtMoney(b.renterInvestmentGrowth) + '</div>' +
    '<div>Buyer side-investment growth: ' + fmtMoney(b.buyerInvestmentGrowth) + '</div>' +
    '</details>';

  document.getElementById('results').innerHTML = html;
  drawChart(p);
}
```

- [ ] **Step 2: Add a temporary `drawChart` stub** (replaced in Task 12)

```javascript
function drawChart(p){ /* implemented in Task 12 */ }
```

- [ ] **Step 3: Verify in preview** — Open `index.html`.
Expected: verdict banner, annualized-advantage + NW stat cards, a yellow sensitivity line with flip thresholds, a full year-by-year table (break-even row highlighted), and a collapsible breakdown. Editing inputs updates everything live.

- [ ] **Step 4: Confirm tests still pass** — `index.html?test` → "**22 passed, 0 failed**".

- [ ] **Step 5: Commit**

```bash
git add "Rent vs Buy/index.html"
git commit -m "feat(rent-buy): results render (verdict, advantage, sensitivity, table, breakdown)"
```

---

## Task 12: UI — inline SVG net-worth chart

**Files:**
- Modify: `Rent vs Buy/index.html`

- [ ] **Step 1: Replace the `drawChart` stub with the real SVG renderer**

```javascript
function drawChart(p){
  var host = document.getElementById('chart'); if (!host) return;
  var W = 640, Hh = 280, padL = 48, padR = 12, padT = 14, padB = 24;
  var H = state.horizonYears;
  var allv = p.buyNW.concat(p.rentNW);
  var maxv = Math.max.apply(null, allv), minv = Math.min.apply(null, allv);
  if (minv > 0) minv = 0;
  function x(yr){ return padL + (yr / H) * (W - padL - padR); }
  function y(v){ return padT + (1 - (v - minv) / (maxv - minv || 1)) * (Hh - padT - padB); }
  function poly(arr, color){
    var pts = arr.map(function(v, i){ return x(i).toFixed(1) + ',' + y(v).toFixed(1); }).join(' ');
    return '<polyline fill="none" stroke="' + color + '" stroke-width="2.5" points="' + pts + '"/>';
  }
  var svg = '<svg viewBox="0 0 ' + W + ' ' + Hh + '">';
  // zero baseline + y label ticks (min, 0, max)
  svg += '<line x1="' + padL + '" y1="' + y(0) + '" x2="' + (W-padR) + '" y2="' + y(0) + '" stroke="#cbd5e1"/>';
  svg += '<text x="' + (padL-6) + '" y="' + (y(maxv)+4) + '" font-size="10" fill="#94a3b8" text-anchor="end">' + fmtK(maxv) + '</text>';
  svg += '<text x="' + (padL-6) + '" y="' + (y(0)+4) + '" font-size="10" fill="#94a3b8" text-anchor="end">0</text>';
  // break-even markers
  p.crossings.forEach(function(c){
    var bx = x(c.toYear);
    svg += '<line x1="' + bx + '" y1="' + padT + '" x2="' + bx + '" y2="' + (Hh-padB) + '" stroke="#94a3b8" stroke-width="1" stroke-dasharray="4 3"/>';
    svg += '<text x="' + bx + '" y="' + (padT-2) + '" font-size="9" fill="#64748b" text-anchor="middle">yr ' + c.toYear + '</text>';
  });
  svg += poly(p.buyNW, '#2563eb') + poly(p.rentNW, '#16a34a');
  // x labels
  svg += '<text x="' + x(0) + '" y="' + (Hh-6) + '" font-size="10" fill="#94a3b8" text-anchor="middle">yr 0</text>';
  svg += '<text x="' + x(H) + '" y="' + (Hh-6) + '" font-size="10" fill="#94a3b8" text-anchor="end">yr ' + H + '</text>';
  svg += '</svg>';
  host.innerHTML = svg;
}
```

- [ ] **Step 2: Verify in preview** — Open `index.html`.
Expected: two lines (blue Buy, green Rent) scaled to the data, a zero baseline, y-axis end labels, and a dashed vertical marker at each break-even year. Dragging the expected-return slider visibly moves the green line and the marker.

- [ ] **Step 3: Confirm tests still pass** — `index.html?test` → "**22 passed, 0 failed**".

- [ ] **Step 4: Commit**

```bash
git add "Rent vs Buy/index.html"
git commit -m "feat(rent-buy): inline SVG net-worth chart with break-even markers"
```

---

## Task 13: README + final verification

**Files:**
- Create: `Rent vs Buy/README.md`

- [ ] **Step 1: Write the README**

```markdown
# Rent vs Buy Calculator

A single self-contained `index.html`. Double-click to open in any browser — no install, no internet.

## Use
Edit the inputs on the left; results update live. The verdict, break-even year(s), annualized advantage, sensitivity, chart, and a year-by-year table are on the right.

## Method
Net worth of both paths is simulated month by month. Opportunity cost is central: the renter invests the down payment + closing costs and every monthly cost difference at your expected return (after capital-gains tax); the buyer's capital sits in leveraged home equity. Both paths spend the same monthly budget. Net worth is marked to market each year (after selling costs and taxes), so each year reads as "outcome if you exit that year."

## Annualized advantage
`(BuyNW / RentNW)^(1/years) − 1` — "buying compounds your net worth ~X%/yr faster than renting." A per-path "return" is intentionally not shown (housing is partly consumption, so it's ill-defined).

## Known simplifications
- Tax deductions: incremental benefit above the **standard deduction** you enter, with an optional cap (set both to 0 for naive full-benefit). No itemization modeling beyond that.
- No PMI (with <20% down the result is optimistic for buying), no mortgage points, no ARM/refinancing.
- Returns/appreciation are deterministic; use the sensitivity flip-thresholds to gauge fragility.
- Net worth is nominal.

## Tests
Open `index.html?test` to run the built-in self-tests (engine math, invariants, sensitivity).
```

- [ ] **Step 2: Final self-test run** — Open `index.html?test`. Expected: "**22 passed, 0 failed**", tab title "OK: 22 passed, 0 failed".

- [ ] **Step 3: Final smoke check** — Open `index.html`. With defaults, confirm: verdict renders, sensitivity shows numeric flip thresholds, chart has both lines, table has 10 rows. Set down payment to a large value so buying clearly wins and confirm the verdict color/text flips to "Buying"; set expected return to 14% and confirm it flips to "Renting".

- [ ] **Step 4: Commit**

```bash
git add "Rent vs Buy/README.md"
git commit -m "docs(rent-buy): README with usage, method, and known simplifications"
```

---

## Self-review (completed during authoring)

**Spec coverage:**
- §3.1 opportunity cost (lump + monthly difference, after-tax) → Tasks 6, 7. §3.2 rate conventions → Task 2 (`toMonthly`), Task 7 (`rm`). §3.3 monthly loop incl. yearly step-ups + tax credit → Tasks 4, 7. §3.4 mark-to-market net worth → Task 6. §3.5 $ ahead / advantage / horizon gap / per-year deltas / all crossings → Tasks 5, 7. §3.6 sensitivity → Task 9, surfaced in Task 11. §4 inputs (incl. standard deduction + cap) → Task 10. §5 output (verdict, advantage, sensitivity, chart, table, breakdown) → Tasks 11–12. §6 structure (pure engine vs UI) → Tasks 2–9 vs 10–12. §7 tests (mortgage, zero-everything, equal-budget invariant, advantage, crossings, incremental deduction, sensitivity) → Tasks 2–9. §9 success criteria → Task 13.
- Gap check: §7 lists a "loan fully amortizes to ~0 at term end" check — covered implicitly by the mortgage formula; an explicit assertion can be added in Task 2 if desired (not load-bearing for the verdict).

**Type consistency:** `computeProjection` returns `{years, buyNW, rentNW, deltaDollar, deltaPct, dollarAhead, horizonGapPct, advantage, crossings, K, downPayment, closing, breakdown}`; consumers (Tasks 11–12) use exactly these. Crossing objects are `{fromYear, toYear, direction}` everywhere (Tasks 5, 11, 12). `state`/`DEFAULTS` keys match `INPUT_CONFIG` keys and engine reads.

**Placeholder scan:** all code steps contain runnable code; the only stubs (`render`, `drawChart`, `boot`) are explicitly temporary and replaced in named later tasks.
