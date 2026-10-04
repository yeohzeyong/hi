# Uber: Sell a Longer Put and Close Before Earnings? And Is $62 Good Value? (Oct 4, 2026)

> Educational, not personalized advice. Option values are **model estimates**: Black-Scholes with a 40% base volatility, plus an earnings event priced at the market's **±9% implied move**. Check the live option chain before trading.

## 1. The "21-day rule": what it actually says
There are **two different 21s** in the sources:
1. **Selling window (Freeman):** sell options **21–45 days** from expiry.
2. **Management rule (tastytrade; Freeman citing the Spintwig backtest):** after selling ~**45 days out**, **close at 50% profit or when 21 days remain**, whichever comes first. Gamma risk (how fast the option's value swings with the stock price) rises sharply in the last 3 weeks.

**Your idea:** sell the **Nov 20** put (46 days) on Mon Oct 5 and close on **Fri Oct 30**, exactly when 21 days remain, the trading day before Uber's **Nov 3** earnings. That is the textbook tastytrade "sell at 45, manage at 21" trade, and it does avoid the earnings gap.

**The catch: the earnings premium doesn't decay before earnings.** A Nov 20 option contains the earnings event, so its volatility stays high and typically **rises** into the announcement (the "IV ramp"), then collapses afterward (the "IV crush"). If you buy it back on Oct 30, you buy it back **with the full earnings premium still inside it.**

| Model | Volatility on Oct 5 | Volatility on Oct 30 |
|---|---|---|
| Nov 20 put (contains earnings) | ~51% | **~62%** (ramp) |
| Oct 30 put (no earnings) | ~40% | expires |

## 2. Head to head: P&L on Oct 30 for 1 contract
| Uber on Oct 30 | **A: Sell Oct 30 $62.50 put** (credit ~$0.76), hold to expiry | **B: Sell Nov 20 $62.50 put** (credit ~$2.33), buy back Oct 30 | **C: Sell Nov 20 $60 put** (credit ~$1.58), buy back Oct 30 |
|---|---|---|---|
| $74 | +$76 | **+$171** | +$124 |
| $70 | +$76 | **+$111** | +$86 |
| $68.11 (flat) | **+$76** | +$69 | +$58 |
| $66 | **+$76** | +$9 | +$16 |
| $64 | **+$76** | −$64 | −$37 |
| $62 | **+$26** | −$152 | −$105 |
| $60 | −$174 (or take the shares at $61.74) | −$259 | −$189 |
| $57 | −$474 (or take the shares) | −$450 | −$349 |

**Reading it:**
- B and C win only if Uber **rallies** before Oct 30. If it's flat, they earn about the same as A.
- If Uber **drifts down to support ($64–66)**, which is the likeliest path given the downtrend, **A still earns its full premium while B and C lose money.** The earnings ramp makes their buyback expensive.
- B and C, closed on Oct 30, **can never deliver the shares to you.** You realize the loss in cash instead of owning Uber at your chosen price. That breaks the purpose of the wheel.
- B and C behave like a bigger bullish bet. You're not paid extra for that, because the bigger credit is earnings premium you have to buy back.

**Verdict:** for a value-investor wheel, **A (Oct 30 $62.50) is better than "sell Nov, close Oct 30."** Use the sell-at-45 / manage-at-21 method when *no earnings fall inside the option's life*. Uber's next clean 45-day window opens **after Nov 3** (e.g., sell a Dec 18 put on Nov 4–6).

**Check this on your broker before trading:** compare the implied volatility of the Oct 30 and Nov 20 puts at the same strike. A gap of ~10 points (e.g., 40% vs 50%) is the earnings premium.

### The one case for a November put
If you **truly want to own Uber at about $58**, sell the **Nov 20 $60 put (~$1.58)** and **hold it through earnings**. If assigned, your effective cost is **~$58.42**. That's a Buffett-style "name your price" trade. It breaks Freeman's no-earnings rule, but it's honest about the goal: you accept the ±9% gap because you want the shares. Smith does sell through earnings on stable names; Uber isn't one, so keep the size small.

## 3. Is ~$62 a good price for Uber?
### The numbers at $62 (≈2.06B shares → ~$128B market cap)
| Metric | Value at $62 | Context |
|---|---|---|
| 2027 adjusted EPS (consensus $4.43) | **~14x** | S&P 500 ~21–22x forward |
| 2027 FCF (consensus ~$13.05B) | **~10% FCF yield**, or ~8.7% after ~$1.9B stock-based pay | S&P 500 ~3% |
| TTM FCF (> $10B) | ~7.8% (~6.4% after stock-based pay) | |
| Net debt | ~$5B (debt $12.1B vs cash $7.1B at YE2025), offset by equity stakes (Didi, Grab, Aurora, Lucid…) | Investment-grade balance sheet |
| Insider anchor | CEO bought at ~$70.96 | You'd be ~13% below the CEO |

### What the price implies (reverse DCF)
At $62, using a 10% discount rate and 2.5% terminal growth, the market is pricing **only ~4% a year of owner-earnings growth for 10 years**. Uber is currently growing bookings ~20% and EBITDA ~33%. The market is pricing in a meaningful robotaxi hit.

### Scenario values (owner FCF ~$8.6B in 2026, 10% discount rate)
| Scenario | Assumption | Value/share | Weight |
|---|---|---|---|
| Bull | Uber becomes the main robotaxi channel: 15% growth for 5 years, then 10% | ~$127 | 15% |
| Base | 12% for 5 years, then 7% | ~$102 | 40% |
| Muddle | Robotaxis squeeze Uber's fees: 8% for 3 years, then 3% | ~$65 | 25% |
| Bear | Robotaxi makers bypass Uber: +4% for 3 years, then −5%/yr | ~$38 | 15% |
| Severe | Flat, then −10%/yr | ~$25 | 5% |
| **Probability-weighted** | | **~$83** | |

**Verdict on price:**
- **$62 is a good-value price for Uber**, about **25% below** my probability-weighted value (~$83). The market assumes very little growth.
- At an **effective $61.74** (the Oct 30 $62.50 put) you have about a **26% margin of safety**. At ~$58.42 (the Nov $60 put held through earnings), about **30%**.
- But the range is wide: the bear case (~$38) is −39% from $62, and the robotaxi outcome can't be known yet. That's why it's a **satellite position (score 72)**, not a core holding like SPGI or AON. Size accordingly.

## 4. Final plan
1. **Mon Oct 5: sell to open 1 UBER Oct 30 $62.50 put**, limit at the mid (~$0.75–0.90). Place a good-till-cancelled buy-to-close at 50%.
   - For a 25-day trade, the matching management rule is **close at 50%, or with ~5–7 days left if it's still near the money.** Hold to about Thursday Oct 29 if it's comfortably out of the money. Never carry it into earnings week.
2. **If assigned at $62.50:** you own a good-value stock at an effective ~$61.74. Sell calls only *after* Nov 3, at strike ≥ $67.50.
3. **If not assigned:** after earnings (Nov 4–6), sell a **Dec 18 put (~44 days, ~0.20–0.25 delta)** below the new support. That's the clean "sell at 45, manage at 21" setup, with no event inside.
4. **Alternative, only if you want shares at ~$58:** sell the Nov 20 $60 put and hold through earnings.
5. **Size check:** $6,000–6,250 of collateral fits the ≤35% rule only if your total investable money is ≥ ~$18k.

## Sources
- Earnings date and ±9% implied move: [Earnings Watcher](https://earnings-watcher.com/wiki/uber-earnings-options), [Barchart expected move](https://www.barchart.com/stocks/quotes/UBER/expected-move), IV rank ~64: [Opti-view](https://opti-view.com/underlying/UBER/implied-volatility)
- Volatility before and after earnings: [tastylive: The Illusion of Volatility into Earnings](https://www.tastylive.com/shows/options-jive/episodes/the-illusion-of-volatility-into-earnings-04-22-2016), [Option Alpha: IV crush](https://optionalpha.com/learn/iv-crush), [Moomoo earnings options series](https://www.moomoo.com/us/learn/options-earnings-series-2-option-buying-and-selling-strategies-for-earnings), [Barchart: pre- vs post-earnings](https://www.barchart.com/story/news/31395102/trading-pre-earnings-vs-post-earnings-when-options-traders-have-an-edge)
- 21-day management: [tastylive Best Practices](https://www.tastylive.com/shows/best-practices/episodes/trade-entry-and-exit-07-08-2019), [tastylive Market Measures](https://www.tastylive.com/shows/market-measures/episodes/short-put-management-performance-09-12-2018); Freeman *The Options Wheel Strategy* Ch. 2 (21–45-day window) and Ch. 9 (50% / 21 days, Spintwig)
- Uber fundamentals: [Uber 10-K 2025](https://www.sec.gov/Archives/edgar/data/1543151/000154315126000015/uber-20251231.htm) (stock-based pay $1.83B, debt $12.08B, cash $7.1B), [Q2 2026 release](https://s23.q4cdn.com/407969754/files/doc_earnings/2026/q2/earnings-result/Uber-Q2-26-Earnings-Press-Release.pdf), 2027 consensus EPS $4.43 ([Barchart](https://www.barchart.com/story/news/3334045/earnings-preview-what-to-expect-from-uber-technologies-report)), FCF ~$13.05B ([Simply Wall St](https://simplywall.st/stocks/pe/transportation/bvl-uberus/uber-technologies-shares/future)), CEO buy ([Stocktwits](https://stocktwits.com/news-articles/markets/equity/uber-stock-jumps-after-ceo-dara-khosrowshahi-buys-10-million-in-shares/cZtakQ1RJ61))
