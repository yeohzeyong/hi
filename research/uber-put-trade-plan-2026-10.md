# Uber Cash-Secured Put — Trade Plan (week of Oct 5, 2026)

> Educational, not personalized advice. Premiums are **Black-Scholes estimates** (implied volatility 42% for October, 46% for an expiry that includes earnings, 36% after earnings). Uber's IV rank is ~64, so premiums are rich. **Use your broker's live bid/ask; your fill will differ.**

## Market facts this plan is built on
| Item | Value |
|---|---|
| Price | $68.11 |
| 50-day moving average | ~$69.26. Price is just below it, a mild downtrend |
| Support | ~$65.4–65.7 (the 52-week low is $65.41) |
| Resistance | ~$75.65 |
| CEO purchase | ~$10M at ~$70.96 (Sep 10) |
| Next earnings | **Tue Nov 3, 2026, before the open.** Options imply **±9%**; the 10-year average move is ±8.9% |
| IV rank | ~64 (premiums historically rich) |
| 1-standard-deviation range to Oct 30 | ~$61.0–76.0 |

## How the gurus pick the put, and what each implies here
| Source | Method | Applied to Uber now |
|---|---|---|
| **Warren Buffett** (KO puts 1993; BNSF puts 2008) | Sell puts at a strike that's a price you'd *love* to own (KO: $35 strike with the stock at $39, ~10% below). Collect premium while you wait; be willing and able to buy | Strike ~8–10% below the price → **$62.50** |
| **tastytrade / tastylive** research | ~45 days to expiry, ~30 delta, prefer IV rank > 30, **close at 50% profit or at 21 days to expiry** | IV rank 64 ✔. A 45-day expiry would include Nov 3 earnings ✘ → use the last expiry *before* earnings, or wait until after |
| **Freeman, *Options Wheel Strategy*** | 21–45 days; **no earnings inside the window**; VIX < 30; prefer price above the 50-day average or at support | **Oct 30** expiry (25 days) ✔. Price at support ✔ (slightly below the 50-day average ~) |
| **Kevin Smith** | Delta −0.20 to −0.30; target 12–24% annualized; roll down and out for a credit ≤ 1–3 months; limit orders at the mid | $62.50 ≈ −0.19 delta, ~20% annualized ✔ |
| **Cboe PutWrite (PUT) index research** | Systematic put-writing on the *S&P 500* earned ~97% of the index's return with ~2/3 the volatility | It works on a *diversified* index. A single stock adds company-specific risk → size carefully |
| **Big ERN (Early Retirement Now), "The Wheel Doesn't Work"** | Taking assignment and then selling calls doesn't "recover" losses. The edge is implied volatility exceeding realized volatility, and losses are part of the business | Don't treat assignment as a safety net. Pick a strike where owning Uber is genuinely acceptable |

## Candidate puts (estimates)
**Oct 30, 2026 expiry: 25 days, ends 2 trading days before earnings**
| Strike | Premium | Delta | Chance it ends in the money | Breakeven | Annualized |
|---|---|---|---|---|---|
| $60 | $0.41 | −0.11 | 13% | $59.59 | 10% |
| **$62.50** | **$0.85** | **−0.19** | **23%** | **$61.65** | **20%** |
| $65 | $1.56 | −0.31 | 35% | $63.44 | 35% |
| $67.50 | $2.59 | −0.44 | 48% | $64.91 | 56% |

**Nov 20, 2026 expiry: 46 days, holds through earnings (±9% gap risk)**
| Strike | Premium | Delta | Chance in the money | Breakeven |
|---|---|---|---|---|
| $57.50 | $0.75 | −0.13 | 16% | $56.75 |
| $60 | $1.24 | −0.19 | 23% | $58.76 |
| $62.50 | $1.92 | −0.26 | 32% | $60.58 |

## ✅ The pick
**Sell to open 1 UBER Oct 30, 2026 $62.50 put.** Limit order at the mid price, roughly **$0.80–0.90** ($80–90 credit). Collateral: **$6,250**.

Why this one:
1. **Buffett-style strike:** $62.50 is ~8% below the price, below the $65.4 support and 52-week low, and ~12% below the CEO's purchase. If you're assigned, your effective cost of **$61.65** is a price where Uber's ~7% free-cash-flow yield becomes ~8%.
2. **Freeman/tastytrade timing:** it expires **before the Nov 3 earnings gap**, it's in the right 21–45-day range (close enough at 25), and IV rank 64 means you're selling expensive insurance.
3. **Smith's delta band:** −0.19 delta, ~77% chance of expiring worthless, ~20% annualized on collateral. Your broker may also pay interest on the $6,250.

**More aggressive alternative** (only if you *want* the shares): the **Oct 30 $65 put** for ~$1.56, effective cost $63.44, ~35% assignment chance. This is the Freeman "write near the money if you want to own it" approach.

**Avoid for now:** Nov or Dec expiries sold *today*. They carry the ±9% earnings gap, which is exactly what Freeman and Smith say not to sell through.

## Managing the trade
| Situation | Action |
|---|---|
| Right after the fill | Place a **good-till-cancelled buy-to-close at 50%** of the credit (~$0.40–0.45), as tastytrade does |
| 50% target hit | Done. Wait for earnings (Nov 3), then go to step 2 |
| Thursday Oct 29, put still open, Uber above $64 | Close it for ≤ $0.05, or let it expire worthless. **Don't carry it into the weekend before earnings week** |
| Uber between $62.50 and $64 near expiry | Close for a small profit or scratch, unless you actively want the shares at $62.50 |
| Uber below $62.50 at expiry, thesis intact | **Take assignment** at an effective $61.65 (Smith's Lever 4). Then sell calls after earnings |
| Uber below $62.50, you don't want shares into earnings | Roll to **Dec 18, $60 or lower, for a net credit only** (Lever 1). Never roll for a debit |
| Thesis-breaking news (e.g., major Waymo/Tesla network bypass, bookings guide cut) and put value ≥ ~3× credit (~$2.50) | Close the put and accept the loss (~$165–250). Don't wheel a broken thesis |

### Step 2: after earnings (~Nov 4–6), if not assigned
- Re-check: did bookings and trips hold up? Where is the new support?
- Sell a **Dec 18 put at ~0.20–0.25 delta** below the post-earnings support. Example with Uber still ~$68 and IV ~36%: **$62.50 put ≈ $1.14** (~15% annualized).
- Same rules: close at 50% or 21 days to expiry; no debit rolls.

### Step 3: if assigned (you own 100 at $62.50; cost basis ~$61.65)
- **Don't sell calls before Nov 3 earnings.** A post-earnings rally is part of your upside.
- After earnings, sell **30–45-day calls at strike ≥ $67.50 (≥ cost basis + ~$6), delta ≤ 0.25**.
- If Uber drops below ~$55, **stop selling calls** (they would only lock in losses). Hold as a value position or exit if the thesis is broken.
- If called away at $67.50: profit ≈ $5.85 + call premium ≈ **$650–750 per cycle**. Restart with a put.

## Outcome table for the pick (Oct 30 $62.50 put, ~$0.85 credit)
| Uber on Oct 30 | Result |
|---|---|
| ≥ $62.50 (~77% probability) | Keep ~$85 (≈1.4% on $6,250 in 25 days) |
| $60 | Assigned. Paper loss ≈ $165 (vs. −$811 if you'd bought 100 shares today at $68.11) |
| $55 (a big non-earnings drop) | Assigned. Paper loss ≈ $665 (vs. −$1,311 buying shares today) |
| $75 | Keep $85 (vs. +$689 buying shares today). **That is the trade-off** |

## Position-size warning
- $6,250 of collateral is a large share of an account that was ~$8.5k plus monthly savings.
- The books' rule: **≤ 35% of the account per CSP when under $30k** (Freeman). This trade only fits that if your total investable money is about **$18k or more**.
- If it's less, you're knowingly concentrating in a stock I scored 72 (moat under robotaxi threat). Consider the $60 strike, or wait until the account is larger.

## Order checklist
1. Options approval: cash-secured puts (usually level 1–2).
2. Order: **Sell to Open → UBER 30 Oct 2026 62.5 Put → qty 1 → Limit (mid) → Day**.
3. Check open interest (aim ≥ 500) and that the bid-ask is ≤ ~$0.05–0.10.
4. Confirm $6,250 is held as collateral. Set the 50% good-till-cancelled close.
5. Log it: date, strike, credit, collateral, breakeven, exit rules.

## Sources
- Uber levels and earnings: [Investing.com technicals](https://www.investing.com/equities/uber-technologies-inc-technical), [StockInvest](https://stockinvest.us/stock/UBER), [Earnings Watcher implied move](https://earnings-watcher.com/wiki/uber-earnings-options), [Barchart expected move](https://www.barchart.com/stocks/quotes/UBER/expected-move), [Opti-view IV rank](https://opti-view.com/underlying/UBER/implied-volatility)
- Buffett puts: [Steady Compounding](https://steadycompounding.substack.com/p/5905474_how-warren-buffett-uses-options), [Nasdaq](https://www.nasdaq.com/articles/how-buffett-used-this-simple-strategy-to-boost-returns-2019-11-06), [Market Folly (BNSF)](https://www.marketfolly.com/2008/10/warren-buffett-sells-puts-on-burlington.html)
- tastytrade: [Best Practices: trade entry and exit](https://www.tastylive.com/shows/best-practices/episodes/trade-entry-and-exit-07-08-2019), [Market Measures: short put management](https://www.tastylive.com/shows/market-measures/episodes/short-put-management-performance-09-12-2018)
- Cboe PUT index: [Indexology (Bondarenko paper)](https://www.indexologyblog.com/2016/02/18/paper-by-professor-bondarenko-has-intriguing-new-analysis-of-put-and-wput-indexes/), [WisdomTree](https://www.wisdomtree.com/us/blog/putwrite-strategy-fund-a-risk-mitigating-allocation-to-investors-portfolios)
- Big ERN: [Why the Wheel Strategy Doesn't Work](https://earlyretirementnow.com/2024/09/17/the-wheel-strategy-doesnt-work-options-series-part-12/), [Spintwig backtest guest post](https://earlyretirementnow.com/2021/11/10/passive-income-through-option-writing-part-9-2016-2021-backtest-guest-post-by-spintwig/)
- Books: Freeman *The Options Wheel Strategy* (Ch. 2, 4, 9, 10); Kevin Smith *A Simple Guide to Selling Options* (delta band, 4 levers, annualized-return test)
